# fx_trade_bot_integrated_v6.5.1.py — v6.5.1 + DYNAMIC TP + MAX TRADES LIMIT (Optimized)

import sys
import logging
import argparse
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import pandas as pd

import config
from config import MAX_SIMULTANEOUS_TRADES

from utils.trading_core import get_candles as get_oanda_candles, forex_market_closed
from utils.calculate_currency_strength import calculate_currency_strength
from utils.strategy_helpers import build_strength_matrix, format_strength_ranking
from telegram_message import send_telegram_message

from config_oanda import OANDA_API_TOKEN, OANDA_ACCOUNT_ID, OANDA_ENV
import oandapyV20
from oandapyV20.endpoints.instruments import InstrumentsCandles

from strategy_decision import StrategyConfig, StrategyEngine, FilterMode, Direction
from data_pipeline import (
    FeatureConfig,
    FeatureEngine,
    ModelWrapper,
    DataFetcher,
    ATRModule,
)

from fx_trade_bot_utils import (
    pip_size,
    load_cooldown,
    save_cooldown,
    get_open_position,
    close_position,
    open_oanda_order,
    update_order_tp,
    get_account_equity,
    should_close_by_strength,
    load_mc_legacy,
    build_mc_telegram,
    build_trade_telegram,
    DynamicPositionManager,
)
from fx_trade_bot_mc import MCGenerator, MCConfig
from fx_trade_bot_ml import ensure_model


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
sys.path.extend([str(BASE_DIR), str(BASE_DIR / "utils")])

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(BASE_DIR / "bot.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


def cfg(name, default):
    return getattr(config, name, default)


# -----------------------------------------------------------------------------
# Config / CLI
# -----------------------------------------------------------------------------
if not cfg("DEBUG_MODE", False):
    logging.getLogger("oandapyV20").setLevel(logging.WARNING)

MAX_SIMULTANEOUS_TRADES = cfg("MAX_SIMULTANEOUS_TRADES", 5)
TRAILING_TP = cfg("TRAILING_TP", False)
DYNAMIC_TP = cfg("DYNAMIC_TP", True)
MULTI_TF_CONFLUENCE = cfg("MULTI_TF_CONFLUENCE", False)
CONFLUENCE_REQUIRED_TFS = cfg("CONFLUENCE_REQUIRED_TFS", 2)
TP_RAISE_THRESHOLD_PIPS = cfg("TP_RAISE_THRESHOLD_PIPS", 15)

parser = argparse.ArgumentParser(description="FX Trading Bot v6.3 + Dynamic TP")
parser.add_argument("--timeframe", type=str, default="H4", choices=["15m", "1H", "H4"])
parser.add_argument("--test-trade", action="store_true", default=True)
parser.add_argument("--no-test-trade", action="store_false", dest="test_trade")
parser.add_argument("--confluence", action="store_true")
parser.add_argument("--no-confluence", action="store_false", dest="confluence")
parser.add_argument("--skip-mc", action="store_true")
parser.add_argument("--mc-only", action="store_true")
args = parser.parse_args()

if args.test_trade:
    REMOVE_COOLDOWN = True
    MULTI_TF_CONFLUENCE = False
    logger.info(
        "=" * 60
        + "\n⚠️ TEST MODE — Cooldown OFF | Confluence OFF | Filters BYPASSED | SHOW ALL SIGNALS\n"
        + "=" * 60
    )
else:
    REMOVE_COOLDOWN = cfg("REMOVE_COOLDOWN", False)
    MULTI_TF_CONFLUENCE = cfg("MULTI_TF_CONFLUENCE", False)
    if args.confluence is not None:
        MULTI_TF_CONFLUENCE = args.confluence

MODE = cfg("PRESET", "LEVEL10")
TIMEFRAME = args.timeframe
OANDA_GRANULARITY_MAP = {"15m": "M15", "1H": "H1", "H4": "H4", "D": "D"}
OANDA_GRANULARITY = OANDA_GRANULARITY_MAP.get(TIMEFRAME, "H4")

DEFAULT_LOT_SIZE = cfg("DEFAULT_LOT_SIZE", 10000)
DEFAULT_PAIRS = cfg(
    "DEFAULT_PAIRS",
    [
        "EURUSD=X", "GBPUSD=X", "EURJPY=X", "GBPJPY=X",
        "AUDUSD=X", "USDJPY=X", "GBPAUD=X", "USDCHF=X",
    ],
)
YAHOO_TO_OANDA = cfg(
    "YAHOO_TO_OANDA",
    {
        "EURUSD=X": "EUR_USD", "GBPUSD=X": "GBP_USD",
        "EURJPY=X": "EUR_JPY", "GBPJPY=X": "GBP_JPY",
        "AUDUSD=X": "AUD_USD", "USDJPY=X": "USD_JPY",
        "GBPAUD=X": "GBP_AUD", "USDCHF=X": "USD_CHF",
    },
)

COOLDOWN_FILE = BASE_DIR / "cooldown_state.json"
RESULTS_DIR = BASE_DIR / "daily_results"
RESULTS_DIR.mkdir(exist_ok=True)
TODAY_STR = datetime.now(timezone.utc).strftime("%Y%m%d")
MC_MAX_AGE_HOURS = cfg("MC_MAX_AGE_HOURS", 24)
SIMULATIONS = cfg("MC_SIMULATIONS", 5000)
CONFIDENCE = cfg("MC_CONFIDENCE", 0.90)

# -----------------------------------------------------------------------------
# MC timeframe config
# -----------------------------------------------------------------------------
if TIMEFRAME in ("H4", "1H", "15m"):
    MCConfig.set_timeframe(TIMEFRAME, {
        "YF_INTERVAL": "4h",
        "YF_PERIOD_FULL": "30d",
        "YF_PERIOD_RESAMPLE": "60d",
        "MC_LOOKBACK": cfg("H4_LOOKBACK", 90),
        "MC_FORECAST": cfg("H4_FORECAST", 8),
        "PERIODS_YEAR": 252 * 6,
        "MC_REPORT_TITLE": "FX H4 MONTE CARLO",
        "RESULTS_DIR": RESULTS_DIR,
    })
else:
    MCConfig.set_timeframe(TIMEFRAME, {
        "YF_INTERVAL": "1d",
        "YF_PERIOD_FULL": "120d",
        "YF_PERIOD_RESAMPLE": "180d",
        "MC_LOOKBACK": cfg("DAILY_LOOKBACK", 90),
        "MC_FORECAST": cfg("DAILY_FORECAST", 5),
        "PERIODS_YEAR": 252,
        "MC_REPORT_TITLE": "FX DAILY MONTE CARLO",
        "RESULTS_DIR": RESULTS_DIR,
    })

# -----------------------------------------------------------------------------
# Pipeline init
# -----------------------------------------------------------------------------
import config_bot

FEAT_CFG = FeatureConfig(
    use_atr=config_bot.USE_ATR,
    atr_sl_mult=config_bot.ATR_SL_MULT,
    atr_tp_mult=config_bot.ATR_TP_MULT,
    use_macd=config_bot.USE_MACD,
    use_rsi=config_bot.USE_RSI,
    use_adx=config_bot.USE_ADX,
    model_type=config_bot.MODEL_TYPE,
    target_horizon=config_bot.TARGET_HORIZON,
    train_lookback_bars=config_bot.TRAIN_LOOKBACK_BARS,
)

STRAT_CFG = StrategyConfig(
    mode=MODE,
    # min_conviction_score=45.0,
    min_conviction_score= 40.0 if MODE == "LEVEL10" else cfg("MIN_CONVICTION_SCORE", 45.0),
    base_min_edge=0.50 if MODE == "LEVEL10" else 0.51,
    mc_filter_mode=FilterMode.PENALIZE,
    regime_filter_mode=FilterMode.OFF,
    adx_filter_mode=FilterMode.OFF,
    pivot_filter_mode=FilterMode.PENALIZE,
    strength_gap_filter_mode=FilterMode.PENALIZE,
    cooldown_filter_mode=FilterMode.BLOCK,
)

api = oandapyV20.API(access_token=OANDA_API_TOKEN, environment=OANDA_ENV)

fetcher = DataFetcher(use_oanda=True, oanda_api=api, oanda_granularity=OANDA_GRANULARITY)
feat_engine = FeatureEngine(FEAT_CFG)
strat_engine = StrategyEngine(STRAT_CFG, model=None, feature_list=[])
atr_mod = ATRModule(period=FEAT_CFG.atr_period)

MODEL_PATH = BASE_DIR / "trade_model_xgb.pkl"
model_wrapper = ModelWrapper(FEAT_CFG, model_path=MODEL_PATH)

last_closed = load_cooldown(COOLDOWN_FILE, Direction)


# -----------------------------------------------------------------------------
# Main trading flow
# -----------------------------------------------------------------------------
def main():
    global model_wrapper, strat_engine

    logger.info(
        f"\n🤖 RUN — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} | "
        f"MODE={MODE} | MODEL=XGBoost | DATA=OANDA | MC={MCConfig.TIMEFRAME} | "
        f"TP={'TRAILING' if TRAILING_TP else ('DYNAMIC' if DYNAMIC_TP else 'FIXED')} | TEST={args.test_trade} | "
        f"MAX_OPEN={MAX_SIMULTANEOUS_TRADES}"
    )

    if forex_market_closed():
        logger.info("Market closed — skipping")
        send_telegram_message("⏸️ FX BOT: Market closed")
        return

    # ── Load or train model
    model_wrapper, strat_engine = ensure_model(
        MODEL_PATH, FEAT_CFG, model_wrapper, strat_engine,
        fetcher, feat_engine, DEFAULT_PAIRS, YAHOO_TO_OANDA, cfg,
    )

    # ── Strength
    logger.info("[STEP 1] Currency Strength...")
    strength_scores = build_strength_matrix()
    logger.info(format_strength_ranking(strength_scores))

    # ── Fetch all pair data
    pair_data = {}
    for pair in DEFAULT_PAIRS:
        oanda = YAHOO_TO_OANDA[pair]
        try:
            raw = fetcher.fetch(pair, oanda, count=200)
            if raw.empty:
                logger.warning(f"{pair}: empty data")
                continue

            df = feat_engine.build(raw)
            
            df = df.replace([np.inf, -np.inf], np.nan)
            df = df.ffill().bfill().fillna(0)  # Forward-fill → Back-fill → Zero-fill            
            
            if len(df) < 5:
                logger.warning(f"{pair}: insufficient bars")
                continue

            atr_val = df.iloc[-1].get("atr", "N/A")
            logger.info(f"📊 {pair}: {len(df)} bars, ATR={atr_val}")

            pair_data[pair] = {"df": df, "oanda": oanda, "raw": raw, "atr": atr_val}
        except Exception as e:
            logger.error(f"Fetch failed {pair}: {e}")

    if not pair_data:
        logger.error("No usable data")
        send_telegram_message("❌ No data")
        return

    # If SKIP_MC = True in config.py → auto-set --skip-mc behavior
    if cfg("SKIP_MC", False):
        args.skip_mc = True

    # ── Monte Carlo
    mc_cache = {}
    if not args.skip_mc:
        logger.info("[MONTE CARLO] Generating forecasts...")
        mc_gen = MCGenerator(
            fetcher, YAHOO_TO_OANDA,
            simulations=SIMULATIONS,
            confidence=CONFIDENCE
        )
        for pair in DEFAULT_PAIRS:
            if pair not in pair_data:
                continue
            mc_data, ok = mc_gen.run_for_pair(pair, df=pair_data[pair]["raw"])
            if ok:
                mc_cache[pair] = mc_data
                rng = mc_data["range_90"]
                logger.info(f"🎲 MC {pair}: {mc_data['regime']} | 90% {rng} | P_up={mc_data['p_up']}%")

        if mc_cache:
            send_telegram_message(build_mc_telegram(
                list(mc_cache.values()), MCConfig.MC_REPORT_TITLE,
                MCConfig.TIMEFRAME, MCConfig.MC_LOOKBACK, MCConfig.MC_FORECAST, SIMULATIONS,
            ))
    else:
        logger.info("[MC] Skipped by config/flag — loading cached forecasts...")
        for pair in DEFAULT_PAIRS:
            mc_data, ok = load_mc_legacy(pair, RESULTS_DIR, TODAY_STR, MC_MAX_AGE_HOURS)
            if ok:
                mc_cache[pair] = mc_data

    if args.mc_only:
        return

    # ── Confluence check
    tf_confluence = {}
    if MULTI_TF_CONFLUENCE and not args.test_trade:
        logger.info("[CONFLUENCE] Multi-Timeframe...")
        TF_GRAN = {"H4": "H4", "1H": "H1", "15m": "M15"}
        for pair in DEFAULT_PAIRS:
            if pair not in pair_data:
                continue

            oanda = pair_data[pair]["oanda"]
            dirs = []

            for tf_label, gran in TF_GRAN.items():
                try:
                    resp = api.request(InstrumentsCandles(instrument=oanda, params={
                        "granularity": gran, "count": 100, "price": "M",
                    }))

                    raw_tf = pd.DataFrame([{
                        "Time": c["time"],
                        "Open": float(c["mid"]["o"]),
                        "High": float(c["mid"]["h"]),
                        "Low": float(c["mid"]["l"]),
                        "Close": float(c["mid"]["c"]),
                    } for c in resp["candles"]]).set_index("Time")

                    if len(raw_tf) < 5:
                        logger.debug(f"  ⏭️ {pair} {tf_label}: insufficient bars")
                        continue

                    sig_tf = strat_engine.generate_signal(
                        pair, oanda, feat_engine.build(raw_tf), None,
                        strength_scores, raw_tf.iloc[-1]["Close"], 1.0,
                    )
                    if sig_tf:
                        dirs.append(sig_tf.action)

                except Exception as e:
                    logger.debug(f"  ⚠️ {pair} {tf_label}: {e}")
                    continue

            buy_c = dirs.count("BUY")
            sell_c = dirs.count("SELL")
            passes = buy_c >= CONFLUENCE_REQUIRED_TFS or sell_c >= CONFLUENCE_REQUIRED_TFS
            tf_confluence[pair] = {"buy": buy_c, "sell": sell_c, "passes": passes}

            logger.info(
                f"🔗 CONFLUENCE {pair}: BUY={buy_c} SELL={sell_c} → "
                f"{'✅ PASS' if passes else '❌ BLOCK'}"
            )

    # ── Close Helper
    def close_wrap(instr):
        return close_position(api, OANDA_ACCOUNT_ID, instr, send_telegram_message)

    # ── Dynamic manager
    logger.info("[DYNAMIC MANAGER] Scanning open positions...")
    dyn_mgr = DynamicPositionManager(
        api, OANDA_ACCOUNT_ID, TIMEFRAME,
        cfg("BE_TRIGGER_ATR_MULT", 1.5),
        cfg("TRAIL_TRIGGER_ATR_MULT", 2.5),
        cfg("TRAIL_ATR_MULT", 1.5),
        cfg("MAX_HOLD_BARS", 12),
        dynamic_tp=DYNAMIC_TP,
        tp_raise_thresh_pips=cfg("TP_RAISE_THRESHOLD_PIPS", 15),
        telegram_send=send_telegram_message,
    )
    dyn_mgr.update_all(pair_data, close_wrap)

    # ── Cache open positions once (fixes O(N^2) bug/slow path)
    open_pos_by_oanda = {}
    open_pos_count = 0
    if not args.test_trade:
        for pair in DEFAULT_PAIRS:
            oanda = YAHOO_TO_OANDA[pair]
            try:
                pos = get_open_position(api, OANDA_ACCOUNT_ID, oanda)
            except Exception:
                pos = None
            has_pos = bool(pos)
            open_pos_by_oanda[oanda] = has_pos
            if has_pos:
                open_pos_count += 1

    # ── NEW SIGNALS
    logger.info("[SIGNALS] Generating trade signals...")
    strength_signal_th = cfg("STRENGTH_SIGNAL_BLOCK_THRESHOLD", 1.0)
    trade_lines = []
    signal_count = 0

    # Precompute pip sizes & pair base/quote parsing (small speed win)
    pip_cache = {}
    pair_parts = {}
    for pair in DEFAULT_PAIRS:
        pip_cache[pair] = pip_size(pair)
        clean = pair.replace("=X", "").replace("_", "")
        base, quote = clean[:3], clean[3:]
        pair_parts[pair] = (base, quote)

    for pair in DEFAULT_PAIRS:
        if pair not in pair_data:
            continue

        oanda = pair_data[pair]["oanda"]
        df = pair_data[pair]["df"]
        atr_val = pair_data[pair]["atr"]

        # ── Cooldown check
        if pair in last_closed and not REMOVE_COOLDOWN and not args.test_trade:
            d, r = last_closed[pair]
            if r > 0:
                last_closed[pair] = (d, r - 1)
                logger.info(f"⏳ COOLDOWN {pair}: {r-1} runs left")
                continue
            else:
                del last_closed[pair]
        elif REMOVE_COOLDOWN and pair in last_closed:
            logger.info(f"🧪 COOLDOWN BYPASS {pair}")
            del last_closed[pair]

        # ── Skip if already open (use cache)
        if not args.test_trade and open_pos_by_oanda.get(oanda, False):
            logger.info(f"⏭️ {pair}: already open → check SL/TP update above")
            continue

        # ── Current price + spread (kept, but only once per candidate)
        try:
            tick = api.request(InstrumentsCandles(instrument=oanda, params={
                "count": 1, "granularity": "M1", "price": "BA",
            }))["candles"][0]

            if "bid" in tick and tick["bid"] and tick["ask"]:
                bid_c = float(tick["bid"]["c"])
                ask_c = float(tick["ask"]["c"])
                current = bid_c  # consistent with original intent
                spread_pips = abs(ask_c - bid_c) / pip_cache[pair]
            else:
                current = float(tick["ask"]["c"])
                spread_pips = 1.0

        except Exception:
            current = float(df.iloc[-1]["Close"])
            spread_pips = 1.0

        mc_data = mc_cache.get(pair)

        # ── Strength gap
        base, quote = pair_parts[pair]
        gap = strength_scores.get(base, 0) - strength_scores.get(quote, 0)

        # ── Signal
        sig = strat_engine.generate_signal(
            pair, oanda, df, mc_data,
            strength_scores, current, spread_pips
        )

        logger.info(f"  DEBUG: {pair} | features_count={len(df.columns)}, has_nan={df.isna().any().any()}")
        logger.info(f"  DEBUG: model_raw_output={getattr(sig, 'raw_score', 'N/A') if sig else 'NO_SIG'}")

        if not sig:
            debug_score = round(getattr(sig, 'conviction_score', 0), 1) if sig else 0.0
            debug_prob = round(getattr(sig, 'model_prob', 0)*100, 1) if sig else 0.0
            logger.info(f"➖ {pair}: no signal | Score={debug_score} | Prob={debug_prob}%")
            continue
                
        # ── Confluence filter
        if MULTI_TF_CONFLUENCE and not args.test_trade:
            c = tf_confluence.get(pair, {})
            if not c.get("passes", True):
                logger.info(f"🚫 {pair}: confluence fail")
                continue
            if sig.action == "BUY" and c.get("buy", 0) < CONFLUENCE_REQUIRED_TFS:
                logger.info(f"🚫 {pair}: BUY confluence fail")
                continue
            if sig.action == "SELL" and c.get("sell", 0) < CONFLUENCE_REQUIRED_TFS:
                logger.info(f"🚫 {pair}: SELL confluence fail")
                continue

        # ── Strength gap filter
        if not args.test_trade:
            if sig.action == "SELL" and gap > strength_signal_th:
                logger.info(f"🚫 {pair}: SELL blocked — gap {gap:.2f} > {strength_signal_th}")
                continue
            if sig.action == "BUY" and -gap > strength_signal_th:
                logger.info(f"🚫 {pair}: BUY blocked — gap {-gap:.2f} > {strength_signal_th}")
                continue
        else:
            logger.info(f"⚠️ TEST MODE: strength veto bypassed {pair}")

        # ── Calculate SL / ✅ DYNAMIC TP


        # ── ✅ ENFORCE MINIMUM SL PIPS — avoid being stopped out by noise
        is_jpy = "JPY" in pair
        min_sl_pips = cfg("MIN_SL_PIPS_JPY", 35) if is_jpy else cfg("MIN_SL_PIPS", 25)
        min_sl_dist = min_sl_pips * pip_cache[pair]

        # Use ATR but NEVER smaller than minimum pips
        atr_sl_dist = atr_val * FEAT_CFG.atr_sl_mult
        sl_distance = max(atr_sl_dist, min_sl_dist)   # ✅ Larger of ATR or MIN

        # Recalculate SL/TP with ENFORCED minimum distance
        if sig.action == "SELL":
            sl = current + sl_distance
            tp = current - (sl_distance * (FEAT_CFG.atr_tp_mult / FEAT_CFG.atr_sl_mult))
        else:  # BUY
            sl = current - sl_distance
            tp = current + (sl_distance * (FEAT_CFG.atr_tp_mult / FEAT_CFG.atr_sl_mult))

        sig.stop_loss, sig.take_profit = sl, tp

        signal_count += 1

        # Probability lookup
        prob_raw = (
            getattr(sig, "probability", None) or getattr(sig, "model_prob", None)
            or getattr(sig, "prob", None) or getattr(sig, "up_prob", None)
            or getattr(sig, "p_up", None)
        )
        prob_val = round(prob_raw * 100, 1) if prob_raw is not None else 0.0
        score_val = round(getattr(sig, "conviction_score", 0), 1)
        breakdown = getattr(sig, "breakdown", {})
        notes = getattr(sig, "notes", [])

        units = int(DEFAULT_LOT_SIZE)        
        
        logger.info(
            f"📈 SIGNAL {pair} | {sig.action} | Score={score_val} | Prob={prob_val}% | "
            f"SL={sl:.5f} | TP={tp:.5f} | Units={units}"
        )
        if breakdown:
            logger.info(f"    Breakdown: {breakdown}")
        if notes:
            logger.info(f"    Notes: {notes}")

        # ── ✅ Enforce MAX SIMULTANEOUS TRADES (O(1) now)
        if not args.test_trade:
            if open_pos_count >= MAX_SIMULTANEOUS_TRADES:
                logger.info(
                    f"🛑 MAX TRADES LIMIT ({MAX_SIMULTANEOUS_TRADES}) — "
                    f"{open_pos_count} already open → skipping {pair}"
                )
                continue

        # ── Execute or display
        if not args.test_trade:
            res = open_oanda_order(
                {"pair": oanda, "action": sig.action, "stop_loss": sl, "take_profit": tp},
                units, current, api, OANDA_ACCOUNT_ID, OANDA_API_TOKEN,
                TRAILING_TP,
                dynamic_tp=DYNAMIC_TP,
            )

            trade_lines.append(f"{sig.action} {pair} → {res.get('status', 'UNKNOWN')}")

            # If order likely opened, bump local count to avoid multiple opens in same run
            # (Since we don't re-query after each order)
            # Conservative: bump count if status indicates success.
            status = str(res.get("status", "")).lower()
            if "fill" in status or "open" in status or "created" in status or res.get("orderFillTransaction"):
                open_pos_count += 1
                open_pos_by_oanda[oanda] = True
        else:
            logger.info(f"🧪 TEST MODE: {sig.action} {pair} | SL={sl:.5f} TP={tp:.5f} | Units={units}")
            trade_lines.append(f"[TEST] {sig.action} {pair} | SL={sl:.5f} TP={tp:.5f} | Units={units}")

    if trade_lines:
        send_telegram_message(build_trade_telegram(trade_lines))
        logger.info(f"📋 Telegram report sent — {signal_count} signal(s) found")
    else:
        logger.info("📋 No trade signals this run")

    logger.info("✅ Run complete\n")


if __name__ == "__main__":
    main()