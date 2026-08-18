import sys
import logging
import argparse
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import pandas as pd

# ─── PRIMARY IMPORT: config_bot FIRST ───
import config_bot
import config

from utils.trading_core import forex_market_closed
from utils.strategy_helpers import build_strength_matrix, format_strength_ranking
from telegram_message import send_telegram_message

from config_oanda import OANDA_API_TOKEN, OANDA_ACCOUNT_ID, OANDA_ENV
import oandapyV20
from oandapyV20.endpoints.instruments import InstrumentsCandles

from strategy_decision import StrategyConfig, StrategyEngine, FilterMode, Direction
from data_pipeline import FeatureConfig, FeatureEngine, ModelWrapper, DataFetcher, ATRModule
from fx_trade_bot_utils import (
    pip_size, load_cooldown, get_open_position, close_position,
    open_oanda_order_simple as open_oanda_order, DynamicPositionManager, load_mc_legacy,
    build_mc_telegram, build_trade_telegram
)
from fx_trade_bot_mc import MCGenerator, MCConfig
from fx_trade_bot_ml import ensure_model

# -----------------------------------------------------------------------------
# Unified Config Lookup
# -----------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
sys.path.extend([str(BASE_DIR), str(BASE_DIR / "utils")])

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(BASE_DIR / "bot.log"), logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

def cfg_bot(name, default):
    return getattr(config_bot, name, getattr(config, name, default))

def cfg(name, default):
    return getattr(config, name, default)

# ─── v6.7.1 WEIGHTS ───
W_S = cfg_bot("WEIGHT_STRENGTH", 0.50)
W_R = cfg_bot("WEIGHT_RSI", 0.15)
W_A = cfg_bot("WEIGHT_ADX", 0.15)
W_X = cfg_bot("WEIGHT_XGBOOST", 0.15)
W_M = cfg_bot("WEIGHT_MC", 0.05)
_WEIGHT_SUM = W_S + W_R + W_A + W_X + W_M
if abs(_WEIGHT_SUM - 1.00) > 0.001:
    logger.warning(f"⚠️ Weight sum = {_WEIGHT_SUM:.4f} ≠ 1.00 — normalizing")
    W_S /= _WEIGHT_SUM; W_R /= _WEIGHT_SUM; W_A /= _WEIGHT_SUM; W_X /= _WEIGHT_SUM; W_M /= _WEIGHT_SUM
logger.info(f"⚖️  WEIGHTS: S={W_S:.2f} R={W_R:.2f} A={W_A:.2f} X={W_X:.2f} M={W_M:.2f} | SUM=1.00")

# ─── 🎯 AUTO-RANKING CONFIG (from config_bot) ───
USE_TOP_PAIRS_ONLY = cfg_bot("USE_TOP_PAIRS_ONLY", False)
TOP_PAIRS_COUNT = cfg_bot("TOP_PAIRS_COUNT", 3)
TOP_PAIRS_MIN_GAP = cfg_bot("TOP_PAIRS_MIN_GAP", 1.5)

# -----------------------------------------------------------------------------
# CLI & Runtime
# -----------------------------------------------------------------------------
DEBUG_MODE = cfg_bot("DEBUG_MODE", False)
if not DEBUG_MODE:
    logging.getLogger("oandapyV20").setLevel(logging.WARNING)

MAX_SIMULTANEOUS_TRADES = cfg_bot("MAX_SIMULTANEOUS_TRADES", 5)
TRAILING_TP = cfg_bot("TRAILING_TP", False)
DYNAMIC_TP = cfg_bot("DYNAMIC_TP", True)
MULTI_TF_CONFLUENCE = cfg_bot("MULTI_TF_CONFLUENCE", False)
CONFLUENCE_REQUIRED_TFS = cfg_bot("CONFLUENCE_REQUIRED_TFS", 2)
TP_RAISE_THRESHOLD_PIPS = cfg_bot("TP_RAISE_THRESHOLD_PIPS", 15)

parser = argparse.ArgumentParser(description="FX Trading Bot v6.7.2 | Safe Lookup | ADX Debug")
parser.add_argument("--timeframe", type=str, default="15m", choices=["15m", "1H", "H4"],
                    help="Chart timeframe (default: 15m)")
parser.add_argument("--test-trade", action="store_true", default=False,
                    help="TEST MODE: relaxed filters, threshold=20, no real orders (default: OFF)")
parser.add_argument("--no-test-trade", action="store_false", dest="test_trade",
                    help="LIVE MODE: strict filters, threshold=40, real orders (default: ON)")
parser.add_argument("--confluence", action="store_true")
parser.add_argument("--no-confluence", action="store_false", dest="confluence")
parser.add_argument("--skip-mc", action="store_true")
parser.add_argument("--mc-only", action="store_true")
args = parser.parse_args()

MODE = cfg_bot("MODE", "LEVEL10")
TIMEFRAME = args.timeframe
OANDA_GRANULARITY_MAP = {"15m": "M15", "1H": "H1", "H4": "H4", "D": "D"}
OANDA_GRANULARITY = OANDA_GRANULARITY_MAP.get(TIMEFRAME, "H4")

DEFAULT_LOT_SIZE = cfg_bot("DEFAULT_LOT_SIZE", 10000)

# ✅ Master pair universe — ALWAYS COMPLETE
ALL_PAIRS = cfg_bot("ALL_PAIRS", [
    "EURUSD=X", "GBPUSD=X", "EURJPY=X", "GBPJPY=X",
    "AUDUSD=X", "USDJPY=X", "GBPAUD=X", "USDCHF=X",
    "AUDJPY=X", "EURGBP=X", "NZDUSD=X", "CADJPY=X",
])
DEFAULT_PAIRS = ALL_PAIRS

# ─── ✅ FIXED: DEFAULT MAPPING + MERGE WITH CONFIG ───
_YAHOO_TO_OANDA_DEFAULT = {
    "EURUSD=X": "EUR_USD", "GBPUSD=X": "GBP_USD",
    "EURJPY=X": "EUR_JPY", "GBPJPY=X": "GBP_JPY",
    "AUDUSD=X": "AUD_USD", "USDJPY=X": "USD_JPY",
    "GBPAUD=X": "GBP_AUD", "USDCHF=X": "USD_CHF",
    "AUDJPY=X": "AUD_JPY", "EURGBP=X": "EUR_GBP",
    "NZDUSD=X": "NZD_USD", "CADJPY=X": "CAD_JPY",
}
# Load from config but FILL ANY MISSING entries from defaults
YAHOO_TO_OANDA = cfg_bot("YAHOO_TO_OANDA", _YAHOO_TO_OANDA_DEFAULT.copy())
for _sym, _oanda in _YAHOO_TO_OANDA_DEFAULT.items():
    if _sym not in YAHOO_TO_OANDA:
        YAHOO_TO_OANDA[_sym] = _oanda
logger.info(f"✅ Pair mappings loaded: {len(YAHOO_TO_OANDA)} entries | NZDUSD=X → {YAHOO_TO_OANDA.get('NZDUSD=X','❌ MISSING')}")

COOLDOWN_FILE = BASE_DIR / "cooldown_state.json"
RESULTS_DIR = BASE_DIR / "daily_results"
RESULTS_DIR.mkdir(exist_ok=True)
TODAY_STR = datetime.now(timezone.utc).strftime("%Y%m%d")
MC_MAX_AGE_HOURS = cfg_bot("MC_MAX_AGE_HOURS", 24)
SIMULATIONS = cfg_bot("MC_SIMULATIONS", 5000)
CONFIDENCE = cfg_bot("MC_CONFIDENCE", 0.90)

REMOVE_COOLDOWN = cfg_bot("REMOVE_COOLDOWN", False)
if args.test_trade:
    REMOVE_COOLDOWN = True
    MULTI_TF_CONFLUENCE = False
    logger.info("\n" + "="*60)
    logger.info("🧪 TEST MODE — Cooldown OFF | Threshold=20 | ALL Filters BYPASSED")
    logger.info("="*60 + "\n")
else:
    if args.confluence is not None:
        MULTI_TF_CONFLUENCE = args.confluence

# -----------------------------------------------------------------------------
# MC Config
# -----------------------------------------------------------------------------
if TIMEFRAME in ("H4", "1H", "15m"):
    MCConfig.set_timeframe(TIMEFRAME, {
        "YF_INTERVAL": cfg_bot("YF_INTERVAL", "4h"),
        "YF_PERIOD_FULL": cfg_bot("YF_PERIOD_FULL", "30d"),
        "YF_PERIOD_RESAMPLE": cfg_bot("YF_PERIOD_RESAMPLE", "60d"),
        "MC_LOOKBACK": cfg_bot("H4_LOOKBACK", 90),
        "MC_FORECAST": cfg_bot("H4_FORECAST", 8),
        "PERIODS_YEAR": cfg_bot("PERIODS_YEAR", 252) * 6,
        "MC_REPORT_TITLE": cfg_bot("MC_REPORT_TITLE", "FX H4 MONTE CARLO"),
        "RESULTS_DIR": RESULTS_DIR,
    })
else:
    MCConfig.set_timeframe(TIMEFRAME, {
        "YF_INTERVAL": cfg_bot("YF_INTERVAL_D", "1d"),
        "YF_PERIOD_FULL": cfg_bot("YF_PERIOD_FULL_D", "120d"),
        "YF_PERIOD_RESAMPLE": cfg_bot("YF_PERIOD_RESAMPLE_D", "180d"),
        "MC_LOOKBACK": cfg_bot("DAILY_LOOKBACK", 90),
        "MC_FORECAST": cfg_bot("DAILY_FORECAST", 5),
        "PERIODS_YEAR": cfg_bot("PERIODS_YEAR_D", 252),
        "MC_REPORT_TITLE": cfg_bot("MC_REPORT_TITLE_D", "FX DAILY MONTE CARLO"),
        "RESULTS_DIR": RESULTS_DIR,
    })

# -----------------------------------------------------------------------------
# Pipeline Init
# -----------------------------------------------------------------------------
FEAT_CFG = FeatureConfig(
    use_atr=cfg_bot("USE_ATR", True),
    atr_sl_mult=cfg_bot("ATR_SL_MULT", 2.0),
    atr_tp_mult=cfg_bot("ATR_TP_MULT", 3.0),
    use_macd=cfg_bot("USE_MACD", True),
    use_rsi=cfg_bot("USE_RSI", True),
    use_adx=cfg_bot("USE_ADX", True),
    model_type=cfg_bot("MODEL_TYPE", "xgboost"),
    target_horizon=cfg_bot("TARGET_HORIZON", 6),
    train_lookback_bars=cfg_bot("TRAIN_LOOKBACK_BARS", 5000),
)

min_conv = cfg_bot("MIN_CONVICTION_SCORE", 40.0) if MODE == "LEVEL10" else cfg_bot("MIN_CONVICTION_SCORE_ALT", 45.0)
min_edge = cfg_bot("BASE_MIN_EDGE", 0.50) if MODE == "LEVEL10" else cfg_bot("BASE_MIN_EDGE_ALT", 0.51)

STRAT_CFG = StrategyConfig(
    mode=MODE, min_conviction_score=min_conv, base_min_edge=min_edge,
    mc_filter_mode=FilterMode.PENALIZE, regime_filter_mode=FilterMode.OFF,
    adx_filter_mode=FilterMode.OFF, pivot_filter_mode=FilterMode.PENALIZE,
    strength_gap_filter_mode=FilterMode.PENALIZE, cooldown_filter_mode=FilterMode.BLOCK,
)

api = oandapyV20.API(access_token=OANDA_API_TOKEN, environment=OANDA_ENV)
fetcher = DataFetcher(use_oanda=True, oanda_api=api, oanda_granularity=OANDA_GRANULARITY)
feat_engine = FeatureEngine(FEAT_CFG)
strat_engine = StrategyEngine(STRAT_CFG, model=None, feature_list=[])
atr_mod = ATRModule(period=getattr(FEAT_CFG, "atr_period", cfg_bot("ATR_PERIOD", 14)))

MODEL_PATH = BASE_DIR / "trade_model_xgb.pkl"
model_wrapper = ModelWrapper(FEAT_CFG, model_path=MODEL_PATH)
last_closed = load_cooldown(COOLDOWN_FILE, Direction)

# -----------------------------------------------------------------------------
# ✅ AUTO-RANKING: Build Top N Pairs from Strength Matrix
# -----------------------------------------------------------------------------
def build_top_pairs(strength_scores, all_pairs, top_n=3, min_gap=1.5):
    """Pair Strongest→Weakest, keep gap≥min_gap, return top_n candidates"""
    ranked = sorted(strength_scores.items(), key=lambda x: x[1], reverse=True)
    strongest = [ccy for ccy, _ in ranked[:top_n]]
    weakest = [ccy for ccy, _ in ranked[-top_n:]]

    candidate_pairs = []
    for i in range(min(top_n, len(strongest), len(weakest))):
        base = strongest[i]
        quote = weakest[-(i+1)]
        if base == quote: continue
        gap = strength_scores[base] - strength_scores[quote]
        if abs(gap) >= min_gap:
            symbol = f"{base}{quote}=X"
            if symbol in all_pairs:
                candidate_pairs.append((symbol, abs(gap), base, quote))

    candidate_pairs.sort(key=lambda x: x[1], reverse=True)
    selected = [p[0] for p in candidate_pairs[:top_n]]
    return selected, candidate_pairs

# -----------------------------------------------------------------------------
# ✅ v5-STYLE WEIGHTED SCORE CALCULATOR — Full Breakdown Logged
# -----------------------------------------------------------------------------
def calc_weighted_score(direction: str, gap: float, rsi_val: float, adx_val: float,
                         xgb_prob: float, mc_pct: float, is_test: bool = False) -> dict:
    """
    FINAL = S×50% + R×15% + A×15% + X×15% + M×5%
    v5-Style: Every component shown, every decision explained
    """
    MIN_FINAL_SCORE = 20.0 if is_test else min_conv  # TEST=20 / LIVE=40

    # ─── 1. STRENGTH SCORE (0–100 from gap) ───
    max_expected_gap = 3.5
    if direction == "BUY":
        strength_raw = max(0.0, min(100.0, (gap / max_expected_gap) * 100.0))
    else:
        strength_raw = max(0.0, min(100.0, (-gap / max_expected_gap) * 100.0))
    S = strength_raw

    # ─── 2. RSI SCORE ───
    rsi = max(0.0, min(100.0, rsi_val))
    if direction == "BUY":
        R = 100.0 - ((rsi - 30) / 40.0) * 100.0 if 30 <= rsi <= 70 else (100.0 if rsi < 30 else 0.0)
    else:
        R = ((rsi - 30) / 40.0) * 100.0 if 30 <= rsi <= 70 else (100.0 if rsi > 70 else 0.0)
    R = max(0.0, min(100.0, R))

    # ─── 3. ADX SCORE ───
    A = max(0.0, min(100.0, adx_val))

    # ─── 4. XGBOOST SCORE ───
    X = max(0.0, min(100.0, xgb_prob * 100.0 if xgb_prob else 0.0))
    if X == 0.0:
        X = max(0.0, min(100.0, S * 0.3 + R * 0.3))  # Fallback

    # ─── 5. MC SCORE ───
    M = max(0.0, min(100.0, mc_pct if mc_pct is not None else 50.0))

    # ─── FINAL ───
    FINAL = S*W_S + R*W_R + A*W_A + X*W_X + M*W_M
    PASS = FINAL >= MIN_FINAL_SCORE

    return {
        "S": round(S,1), "R": round(R,1), "A": round(A,1),
        "X": round(X,1), "M": round(M,1),
        "FINAL": round(FINAL,1), "PASS": PASS,
        "THRESHOLD": round(MIN_FINAL_SCORE,1),
        "MODE": "TEST" if is_test else "LIVE"
    }

# -----------------------------------------------------------------------------
# Main Trading Flow — v5-Style Clean Logging
# -----------------------------------------------------------------------------
def main():
    global model_wrapper, strat_engine
    logger.info(f"\n🤖 RUN v6.7.2 — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} | "
                f"TOP_PAIRS={USE_TOP_PAIRS_ONLY} | MODEL=xgboost | MC={MCConfig.TIMEFRAME} | "
                f"TEST={args.test_trade} | MAX_OPEN={MAX_SIMULTANEOUS_TRADES}")

    if forex_market_closed():
        logger.info("Market closed — skipping")
        send_telegram_message("⏸️ FX BOT v6.7.2: Market closed")
        return

    model_wrapper, strat_engine = ensure_model(
        MODEL_PATH, FEAT_CFG, model_wrapper, strat_engine,
        fetcher, feat_engine, ALL_PAIRS, YAHOO_TO_OANDA, cfg_bot,
    )

    logger.info("[STEP 1] Currency Strength...")
    strength_scores = build_strength_matrix()
    logger.info(format_strength_ranking(strength_scores))

    # ─── 🎯 AUTO-RANKING DECISION ───
    if USE_TOP_PAIRS_ONLY:
        DEFAULT_PAIRS, candidates = build_top_pairs(
            strength_scores, ALL_PAIRS,
            top_n=TOP_PAIRS_COUNT, min_gap=TOP_PAIRS_MIN_GAP
        )
        if not DEFAULT_PAIRS:
            logger.warning("⚠️ No pairs met min_gap threshold — scanning ALL pairs instead")
            DEFAULT_PAIRS = ALL_PAIRS[:]
        else:
            logger.info(f"🎯 AUTO-RANK: Top {len(DEFAULT_PAIRS)} pairs selected (min gap ≥ {TOP_PAIRS_MIN_GAP}):")
            for sym, gap, base, quote in candidates:
                flag = "✅" if sym in DEFAULT_PAIRS else "⏭️"
                logger.info(f"   {flag} {base}/{quote} | gap={gap:.2f} → {sym}")
    else:
        DEFAULT_PAIRS = ALL_PAIRS[:]
        logger.info(f"📋 SCAN ALL: {len(DEFAULT_PAIRS)} pairs (AUTO-RANK disabled)")

    # ─── STEP 2: Fetch Data & Log Per-Pair Debug ───
    pair_data = {}
    for pair in DEFAULT_PAIRS:
        # ✅ FIXED: Safe lookup — no KeyError crash
        oanda = YAHOO_TO_OANDA.get(pair)
        if oanda is None:
            logger.warning(f"⚠️ No OANDA mapping for {pair} — skipping")
            continue
        try:
            raw = fetcher.fetch(pair, oanda, count=200)
            if raw.empty:
                logger.warning(f"{pair}: empty data from OANDA")
                continue
            df = feat_engine.build(raw)
            df = df.replace([np.inf, -np.inf], np.nan).ffill().bfill().fillna(0)
            if len(df) < 5:
                logger.warning(f"{pair}: insufficient bars ({len(df)})")
                continue
            atr_val = df.iloc[-1].get("atr", 0.0)
            rsi_val = df.iloc[-1].get("rsi", 50.0)
            adx_val = df.iloc[-1].get("adx", -1.0)  # -1 = not computed
            # ✅ ADX DEBUG
            if adx_val <= 0.0:
                logger.info(f"🔍 ADX DEBUG {pair}: last_5_values={list(df['adx'].tail(5)) if 'adx' in df.columns else 'COLUMN_MISSING'}")
            logger.info(f"📊 {pair}: {len(df)} bars | ATR={atr_val:.6f} | RSI={rsi_val:.1f} | ADX={adx_val:.1f}")
            pair_data[pair] = {"df": df, "oanda": oanda, "raw": raw, "atr": atr_val, "rsi": rsi_val, "adx": adx_val}
        except Exception as e:
            logger.error(f"❌ Fetch failed {pair}: {e}")

    if not pair_data:
        logger.error("No pairs have usable data. Aborting run.")
        send_telegram_message("❌ FX BOT: No usable pair data")
        return

    # ─── STEP 3: Monte Carlo ───
    if cfg_bot("SKIP_MC", False):
        args.skip_mc = True

    mc_cache = {}
    if not args.skip_mc:
        logger.info("[STEP 3] Monte Carlo Forecasts...")
        mc_gen = MCGenerator(fetcher, YAHOO_TO_OANDA, simulations=SIMULATIONS, confidence=CONFIDENCE)
        for pair in DEFAULT_PAIRS:
            if pair not in pair_data:
                continue
            mc_data, ok = mc_gen.run_for_pair(pair, df=pair_data[pair]["raw"])
            if ok:
                mc_cache[pair] = mc_data
                logger.info(f"🎲 MC {pair}: {mc_data['regime']} | 90% Band {mc_data['range_90']} | P_UP={mc_data['p_up']}%")
        if mc_cache:
            send_telegram_message(build_mc_telegram(
                list(mc_cache.values()), MCConfig.MC_REPORT_TITLE,
                MCConfig.TIMEFRAME, MCConfig.MC_LOOKBACK, MCConfig.MC_FORECAST, SIMULATIONS
            ))
    else:
        logger.info("[STEP 3] MC Skipped — loading legacy...")
        for pair in DEFAULT_PAIRS:
            mc_data, ok = load_mc_legacy(pair, RESULTS_DIR, TODAY_STR, MC_MAX_AGE_HOURS)
            if ok:
                mc_cache[pair] = mc_data

    if args.mc_only:
        return

    # ─── STEP 4: Multi-Timeframe Confluence Check ───
    tf_confluence = {}
    if MULTI_TF_CONFLUENCE and not args.test_trade:
        logger.info("[STEP 4] Multi-Timeframe Confluence...")
        TF_GRAN = {"H4": "H4", "1H": "H1", "15m": "M15"}
        for pair in DEFAULT_PAIRS:
            if pair not in pair_data:
                continue
            oanda = pair_data[pair]["oanda"]
            dirs = []
            for gran in TF_GRAN.values():
                try:
                    resp = api.request(InstrumentsCandles(instrument=oanda,
                        params={"granularity": gran, "count": 100, "price": "M"}))
                    raw_tf = pd.DataFrame([{
                        "Time": c["time"], "Open": float(c["mid"]["o"]),
                        "High": float(c["mid"]["h"]), "Low": float(c["mid"]["l"]),
                        "Close": float(c["mid"]["c"])} for c in resp["candles"]]).set_index("Time")
                    if len(raw_tf) < 5:
                        continue
                    sig_tf = strat_engine.generate_signal(pair, oanda, feat_engine.build(raw_tf),
                                                           None, strength_scores, raw_tf.iloc[-1]["Close"], 1.0)
                    if sig_tf:
                        dirs.append(sig_tf.action)
                except Exception:
                    continue
            buy_c, sell_c = dirs.count("BUY"), dirs.count("SELL")
            passes = buy_c >= CONFLUENCE_REQUIRED_TFS or sell_c >= CONFLUENCE_REQUIRED_TFS
            tf_confluence[pair] = {"buy": buy_c, "sell": sell_c, "passes": passes}
            logger.info(f"🔗 CONFLUENCE {pair}: BUY={buy_c} SELL={sell_c} → {'✅ PASS' if passes else '❌ BLOCK'}")

    # ─── STEP 5: Dynamic Exit Manager ───
    def close_wrap(instr):
        return close_position(api, OANDA_ACCOUNT_ID, instr, send_telegram_message)

    logger.info("[STEP 5] Dynamic Exit Manager — Scanning Open Positions...")
    dyn_mgr = DynamicPositionManager(
        api, OANDA_ACCOUNT_ID, TIMEFRAME,
        cfg_bot("BE_TRIGGER_ATR_MULT", 1.5), cfg_bot("TRAIL_TRIGGER_ATR_MULT", 2.5),
        cfg_bot("TRAIL_ATR_MULT", 1.5), cfg_bot("MAX_HOLD_BARS", 12),
        dynamic_tp=DYNAMIC_TP, tp_raise_thresh_pips=TP_RAISE_THRESHOLD_PIPS,
        telegram_send=send_telegram_message
    )
    dyn_mgr.update_all(pair_data, close_wrap)

    # ─── STEP 6: Scan Open Positions ───
    open_pos_by_oanda, open_pos_count = {}, 0
    if not args.test_trade:
        for pair in DEFAULT_PAIRS:
            oanda = YAHOO_TO_OANDA.get(pair)
            if not oanda:
                continue
            try:
                pos = get_open_position(api, OANDA_ACCOUNT_ID, oanda)
            except Exception as e:
                err_text = str(e)
                # OANDA 404 = NO POSITION — NOT an error
                if "NO_SUCH_POSITION" in err_text or "404" in err_text:
                    pos = None
                else:
                    logger.warning(f"⚠️ API error checking {pair}: {e}")
                    pos = None
            open_pos_by_oanda[oanda] = bool(pos)
            if pos:
                open_pos_count += 1

    # ─── STEP 7: Generate Signals — Full Debug Per Pair ───
    logger.info("[STEP 7] Scoring & Signals...")
    min_sl_pips_jpy, min_sl_pips_std = cfg_bot("MIN_SL_PIPS_JPY", 35), cfg_bot("MIN_SL_PIPS", 25)
    trade_lines, signal_count = [], 0
    pip_cache = {pair: pip_size(pair) for pair in DEFAULT_PAIRS}
    pair_parts = {p: (p.replace("=X","")[:3], p.replace("=X","")[3:]) for p in DEFAULT_PAIRS}

    for pair in DEFAULT_PAIRS:
        if pair not in pair_data:
            continue
        oanda = pair_data[pair]["oanda"]
        df = pair_data[pair]["df"]
        atr_val = pair_data[pair]["atr"]
        rsi_val = pair_data[pair]["rsi"]
        adx_val = pair_data[pair]["adx"]

        # Cooldown Check
        if pair in last_closed and not REMOVE_COOLDOWN and not args.test_trade:
            d, r = last_closed[pair]
            if r > 0:
                last_closed[pair] = (d, r-1)
                logger.info(f"⏳ COOLDOWN {pair}: {r-1} runs remaining")
                continue
            else:
                del last_closed[pair]
        elif REMOVE_COOLDOWN and pair in last_closed:
            del last_closed[pair]

        # Already Open Check
        if not args.test_trade:
            try:
                is_open = open_pos_by_oanda.get(oanda, False)
            except:
                is_open = False
            if is_open:
                logger.info(f"⏭️ {pair}: position already open — skip")
                continue

        # if not args.test_trade and open_pos_by_oanda.get(oanda, False):
        #     logger.info(f"⏭️ {pair}: position already open — skip")
        #     continue

        # Get Current Price
        try:
            tick = api.request(InstrumentsCandles(instrument=oanda,
                params={"count":1, "granularity":"M1", "price":"BA"}))["candles"][0]
            if "bid" in tick and tick["bid"] and tick["ask"]:
                bid_c, ask_c = float(tick["bid"]["c"]), float(tick["ask"]["c"])
                current, spread_pips = bid_c, abs(ask_c-bid_c)/pip_cache[pair]
            else:
                current, spread_pips = float(tick["ask"]["c"]), 1.0
        except Exception:
            current, spread_pips = float(df.iloc[-1]["Close"]), 1.0

        # Strength Gap → Direction
        mc_data = mc_cache.get(pair)
        base, quote = pair_parts[pair]
        gap = strength_scores.get(base, 0) - strength_scores.get(quote, 0)
        direction = "BUY" if gap > 0 else "SELL"
        gap_mag = abs(gap)

        # Gap Filter
        gap_thresh = 9.99 if args.test_trade else cfg_bot("STRENGTH_SIGNAL_BLOCK_THRESHOLD", 9.99)
        if gap_mag > gap_thresh:
            logger.info(f"🚫 {pair}: {direction} BLOCKED — gap {gap_mag:.2f} > {gap_thresh}")
            continue

        # Confluence Filter
        if MULTI_TF_CONFLUENCE and not args.test_trade:
            c = tf_confluence.get(pair, {})
            if not c.get("passes", True):
                logger.info(f"🚫 {pair}: confluence fail — skip")
                continue
            if direction == "BUY" and c.get("buy",0) < CONFLUENCE_REQUIRED_TFS:
                logger.info(f"🚫 {pair}: BUY confluence fail — skip")
                continue
            if direction == "SELL" and c.get("sell",0) < CONFLUENCE_REQUIRED_TFS:
                logger.info(f"🚫 {pair}: SELL confluence fail — skip")
                continue

        # ─── WEIGHTED SCORE CALCULATION ───
        sig = strat_engine.generate_signal(pair, oanda, df, mc_data, strength_scores, current, spread_pips)
        prob_raw = getattr(sig,"probability",None) or getattr(sig,"model_prob",None) or getattr(sig,"prob",None) or 0.0
        mc_pct = mc_data.get("p_up", 50.0) if mc_data else 50.0
        if direction == "SELL":
            mc_pct = 100.0 - mc_pct

        w = calc_weighted_score(direction, gap, rsi_val, adx_val, prob_raw, mc_pct, is_test=args.test_trade)

        # ⚖️ v5-STYLE FULL BREAKDOWN
        logger.info(
            f"⚖️  {pair} {direction} | "
            f"S={w['S']:5.1f}×50%={round(w['S']*W_S,1):4.1f}  "
            f"R={w['R']:5.1f}×15%={round(w['R']*W_R,1):4.1f}  "
            f"A={w['A']:5.1f}×15%={round(w['A']*W_A,1):4.1f}  "
            f"X={w['X']:5.1f}×15%={round(w['X']*W_X,1):4.1f}  "
            f"M={w['M']:5.1f}×5% ={round(w['M']*W_M,1):4.1f}  |  "
            f"FINAL={w['FINAL']:5.1f} vs {w['THRESHOLD']} → {'✅ PASS ✅' if w['PASS'] else '❌ FAIL ❌'} [{w['MODE']}]"
        )

        if not w["PASS"]:
            logger.info(f"➖ {pair}: FINAL {w['FINAL']} < {w['THRESHOLD']} — no signal")
            continue

        # ─── SIGNAL PASSED → Calculate SL/TP ───
        signal_count += 1
        sl_pips = max(min_sl_pips_jpy if "JPY" in pair else min_sl_pips_std,
                      round(atr_val / pip_cache[pair] * cfg_bot("ATR_SL_MULT", 2.0), 1))
        tp_pips = round(atr_val / pip_cache[pair] * cfg_bot("ATR_TP_MULT", 3.0), 1) if DYNAMIC_TP else sl_pips * 1.5

        dec = 3 if "JPY" in pair else 5
        if direction == "BUY":
            sl_price = round(current - sl_pips * pip_cache[pair], dec)
            tp_price = round(current + tp_pips * pip_cache[pair], dec)
        else:
            sl_price = round(current + sl_pips * pip_cache[pair], dec)
            tp_price = round(current - tp_pips * pip_cache[pair], dec)

        score_final = w["FINAL"]

        # ─── EXECUTE ───
        if args.test_trade:
            logger.info(f"🧪 TEST MODE — {direction} {pair} @ {current:.{dec}f} | SL={sl_price} | TP={tp_price}")
            trade_lines.append(f"🧪 {pair} {direction} Score={score_final:.1f} SL={sl_price} TP={tp_price}")
        else:
            if open_pos_count >= MAX_SIMULTANEOUS_TRADES:
                logger.info(f"⏭️ {pair}: MAX_OPEN={MAX_SIMULTANEOUS_TRADES} reached — skip")
                continue
            try:
                resp = open_oanda_order(api, OANDA_ACCOUNT_ID, oanda, direction, DEFAULT_LOT_SIZE, sl_price, tp_price)
                trade_id = resp.get("orderFillTransaction",{}).get("id","?")
                logger.info(f"✅ EXECUTED {pair} {direction} | SL={sl_price} | TP={tp_price} | TradeID={trade_id}")
                trade_lines.append(f"✅ {pair} {direction} Score={score_final:.1f} | SL={sl_price} TP={tp_price}")
                open_pos_count += 1
            except Exception as e:
                logger.error(f"❌ ORDER FAILED {pair}: {e}")

    # ─── STEP 8: Final Report ───
    if trade_lines:
        summary = f"🤖 v6.7.2 RUN COMPLETE — {signal_count} SIGNAL(S)\n\n" + "\n".join(trade_lines)
        send_telegram_message(summary)
    else:
        logger.info("📋 No signals passed thresholds this run")
        if args.test_trade:
            send_telegram_message("🤖 v6.7.2 TEST — No signals passed threshold (20.0)")

    logger.info("✅ v6.7.2 Run Complete")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.exception("Fatal error in main loop")
        send_telegram_message(f"❌ FX BOT FATAL ERROR: {e}")
        raise