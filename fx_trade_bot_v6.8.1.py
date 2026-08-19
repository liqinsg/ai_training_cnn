# fx_trade_bot_v6.8.1.py
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

import oandapyV20

from portfolio_balance import balance_from_config
from sl_zone_hierarchy import compute_sl_zone

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

# ══════════════════════════════════════════════════════════════
# v6.8 NEW CONFIG — P0 + P1 + P2
# ══════════════════════════════════════════════════════════════

# P0: DIRECTION CONSENSUS
REQUIRE_DIRECTION_CONSENSUS = cfg_bot("REQUIRE_DIRECTION_CONSENSUS", True)
CONSENSUS_THRESHOLD = cfg_bot("CONSENSUS_THRESHOLD", 2)
XGB_BULLISH_THRESHOLD = cfg_bot("XGB_BULLISH_THRESHOLD", 0.55)
MC_BULLISH_THRESHOLD = cfg_bot("MC_BULLISH_THRESHOLD", 55.0)

# P1: ADX NORMALIZATION + Floor/Bonus
ADX_SCALE_FACTOR = cfg_bot("ADX_SCALE_FACTOR", 2.0)
ADX_FLOOR_ENABLED = cfg_bot("ADX_FLOOR_ENABLED", True)
ADX_MIN_SCORE = cfg_bot("ADX_MIN_SCORE", 20.0)
ADX_BOOST_ENABLED = cfg_bot("ADX_BOOST_ENABLED", True)
ADX_BOOST_THRESHOLD = cfg_bot("ADX_BOOST_THRESHOLD", 30.0)
ADX_BOOST_VALUE = cfg_bot("ADX_BOOST_VALUE", 10.0)

# P2: WEIGHTS — S=0.50 R=0.15 A=0.15 X=0.12 M=0.08
W_S = cfg_bot("WEIGHT_STRENGTH", 0.50)
W_R = cfg_bot("WEIGHT_RSI", 0.15)
W_A = cfg_bot("WEIGHT_ADX", 0.15)
W_X = cfg_bot("WEIGHT_XGBOOST", 0.12)  # ↓ from 0.15
W_M = cfg_bot("WEIGHT_MC", 0.08)       # ↑ from 0.05

_WEIGHT_SUM = W_S + W_R + W_A + W_X + W_M
if abs(_WEIGHT_SUM - 1.00) > 0.001:
    logger.warning(f"⚠️ Weight sum = {_WEIGHT_SUM:.4f} ≠ 1.00 — normalizing")
    weights = [W_S, W_R, W_A, W_X, W_M]
    weights = [w / _WEIGHT_SUM for w in weights]
    W_S, W_R, W_A, W_X, W_M = weights
logger.info(f"⚖️  WEIGHTS: S={W_S:.2f} R={W_R:.2f} A={W_A:.2f} X={W_X:.2f} M={W_M:.2f} | SUM=1.00")

# 🎯 Tunable thresholds
MIN_STRENGTH_GAP = cfg_bot("MIN_STRENGTH_GAP", 0.3)
DEBUG_DETAIL = cfg_bot("DEBUG_DETAIL", True)

# ─── 🎯 AUTO-RANKING CONFIG ───
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

parser = argparse.ArgumentParser(description="FX Trading Bot v6.8 | Consensus + ADX-Norm + MC↑")
parser.add_argument("--timeframe", type=str, default="15m", choices=["15m", "1H", "H4"],
                    help="Chart timeframe (default: 15m)")
parser.add_argument("--test-trade", action="store_true", default=False,
                    help="TEST MODE: relaxed filters, threshold=20, no real orders")
parser.add_argument("--no-test-trade", action="store_false", dest="test_trade",
                    help="LIVE MODE: strict filters, real orders")
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

# ✅ Master pair universe
ALL_PAIRS = cfg_bot("ALL_PAIRS", [
    "EURUSD=X", "GBPUSD=X", "EURJPY=X", "GBPJPY=X",
    "AUDUSD=X", "USDJPY=X", "GBPAUD=X", "USDCHF=X",
    "AUDJPY=X", "EURGBP=X", "NZDUSD=X", "CADJPY=X",
])

# ─── ✅ OANDA MAPPING ───
_YAHOO_TO_OANDA_DEFAULT = {
    "EURUSD=X": "EUR_USD", "GBPUSD=X": "GBP_USD",
    "EURJPY=X": "EUR_JPY", "GBPJPY=X": "GBP_JPY",
    "AUDUSD=X": "AUD_USD", "USDJPY=X": "USD_JPY",
    "GBPAUD=X": "GBP_AUD", "USDCHF=X": "USD_CHF",
    "AUDJPY=X": "AUD_JPY", "EURGBP=X": "EUR_GBP",
    "NZDUSD=X": "NZD_USD", "CADJPY=X": "CAD_JPY",
}
YAHOO_TO_OANDA = cfg_bot("YAHOO_TO_OANDA", _YAHOO_TO_OANDA_DEFAULT.copy())
for _sym, _oanda in _YAHOO_TO_OANDA_DEFAULT.items():
    if _sym not in YAHOO_TO_OANDA:
        YAHOO_TO_OANDA[_sym] = _oanda
logger.info(f"✅ Pair mappings loaded: {len(YAHOO_TO_OANDA)} entries")

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
    logger.info("🧪 TEST MODE — Cooldown OFF | Threshold=20 | Filters BYPASSED")
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
# Auto-Ranking
# -----------------------------------------------------------------------------
def build_top_pairs(strength_scores, all_pairs, top_n=3, min_gap=1.5):
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
            if symbol not in all_pairs:
                symbol = f"{quote}{base}=X"
            if symbol in all_pairs:
                candidate_pairs.append((symbol, abs(gap), base, quote))
    candidate_pairs.sort(key=lambda x: x[1], reverse=True)
    selected = [p[0] for p in candidate_pairs[:top_n]]
    return selected, candidate_pairs

# -----------------------------------------------------------------------------
# ✅ v6.8 WEIGHTED SCORE + DIRECTION CONSENSUS + ADX NORM
# -----------------------------------------------------------------------------
def calc_weighted_score(pair: str, gap: float, rsi_val: float, adx_val: float,
                        xgb_prob: float, mc_pct_up: float, is_test: bool = False):
    """Returns (direction, score_dict) — direction=None means SKIP"""
    MIN_FINAL_SCORE = 20.0 if is_test else min_conv

    # ══════════════════════════════════════════════════════════════
    # P0 — DIRECTION CONSENSUS VOTING (Strength + XGB + MC)
    # ══════════════════════════════════════════════════════════════
    strength_dir = "BUY" if gap >= MIN_STRENGTH_GAP else "SELL" if gap <= -MIN_STRENGTH_GAP else "NEUTRAL"
    xgb_bullish = xgb_prob >= XGB_BULLISH_THRESHOLD
    xgb_dir = "BUY" if xgb_bullish else "SELL"
    mc_bullish = mc_pct_up >= MC_BULLISH_THRESHOLD
    mc_dir = "BUY" if mc_bullish else "SELL"

    buy_votes = sum(1 for d in [strength_dir, xgb_dir, mc_dir] if d == "BUY")
    sell_votes = sum(1 for d in [strength_dir, xgb_dir, mc_dir] if d == "SELL")

    logger.info(f"🤝 {pair}: Strength={strength_dir} | XGB={xgb_dir} | MC={mc_dir} | BUY={buy_votes}/3")

    direction = None

    if REQUIRE_DIRECTION_CONSENSUS:
        if buy_votes >= CONSENSUS_THRESHOLD:
            direction = "BUY"
            logger.info(f"✅ {pair}: BUY consensus ({buy_votes}/3)")
        elif sell_votes >= CONSENSUS_THRESHOLD:
            direction = "SELL"
            logger.info(f"✅ {pair}: SELL consensus ({sell_votes}/3)")
        else:
            logger.info(f"⏭️  {pair}: NO CONSENSUS → SKIP")
            return None, None  # SKIP
    else:
        # Legacy fallback: strength only
        direction = "BUY" if gap > 0 else "SELL"
        logger.info(f"ℹ️  Consensus OFF — using Strength only: {direction}")

    # ══════════════════════════════════════════════════════════════
    # SCORE CALCULATION — All 5 Components
    # ══════════════════════════════════════════════════════════════

    # 1. STRENGTH
    max_expected_gap = 3.5
    strength_raw = abs(gap) / max_expected_gap * 100.0
    S = max(0.0, min(100.0, strength_raw))

    # 2. RSI
    rsi = max(0.0, min(100.0, rsi_val))
    if direction == "BUY":
        R = 100.0 - ((rsi - 30) / 40.0) * 100.0 if 30 <= rsi <= 70 else (100.0 if rsi < 30 else 0.0)
    else:
        R = ((rsi - 30) / 40.0) * 100.0 if 30 <= rsi <= 70 else (100.0 if rsi > 70 else 0.0)
    R = max(0.0, min(100.0, R))

    # 3. ADX — P1: NORMALIZE + Floor/Bonus
    raw_adx = adx_val
    adx_normalized = min(raw_adx * ADX_SCALE_FACTOR, 100.0)

    if ADX_FLOOR_ENABLED and adx_normalized < ADX_MIN_SCORE:
        A = ADX_MIN_SCORE
        logger.debug(f"🛡️ ADX FLOOR: raw={raw_adx:.1f}→norm={adx_normalized:.1f}→floor={A}")
    elif ADX_BOOST_ENABLED and raw_adx >= ADX_BOOST_THRESHOLD:
        A = min(100.0, adx_normalized + ADX_BOOST_VALUE)
        logger.debug(f"🚀 ADX BOOST: raw={raw_adx:.1f}≥{ADX_BOOST_THRESHOLD}→{A:.1f}")
    else:
        A = adx_normalized
        logger.debug(f"📐 ADX NORM: raw={raw_adx:.1f}→{A:.1f}")
    A = max(0.0, min(100.0, A))

    # 4. XGBOOST
    X = max(0.0, min(100.0, xgb_prob * 100.0 if xgb_prob else 0.0))
    if X == 0.0:
        X = max(0.0, min(100.0, S * 0.3 + R * 0.3))

    # 5. MONTE CARLO
    M = max(0.0, min(100.0, mc_pct_up if mc_pct_up is not None else 50.0))

    # FINAL SCORE
    FINAL = S*W_S + R*W_R + A*W_A + X*W_X + M*W_M
    PASS = FINAL >= MIN_FINAL_SCORE

    score = {
        "S": round(S,1), "R": round(R,1), "A": round(A,1),
        "X": round(X,1), "M": round(M,1),
        "FINAL": round(FINAL,1), "PASS": PASS,
        "THRESHOLD": round(MIN_FINAL_SCORE,1), "MODE": "TEST" if is_test else "LIVE"
    }
    return direction, score

# -----------------------------------------------------------------------------
# Main Trading Flow — v6.8
# -----------------------------------------------------------------------------
def main():
    global model_wrapper, strat_engine
    logger.info(f"\n🤖 RUN v6.8 — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} | "
                f"TOP_PAIRS={USE_TOP_PAIRS_ONLY} | MODEL=xgboost | MC={MCConfig.TIMEFRAME} | "
                f"TEST={args.test_trade} | MAX_OPEN={MAX_SIMULTANEOUS_TRADES} | MIN_GAP={MIN_STRENGTH_GAP}")

    if forex_market_closed():
        logger.info("Market closed — skipping")
        send_telegram_message("⏸️ FX BOT v6.8: Market closed")
        return

    model_wrapper, strat_engine = ensure_model(
        MODEL_PATH, FEAT_CFG, model_wrapper, strat_engine,
        fetcher, feat_engine, ALL_PAIRS, YAHOO_TO_OANDA, cfg_bot,
    )

    logger.info("[STEP 1] Currency Strength...")
    strength_scores = build_strength_matrix()
    logger.info(format_strength_ranking(strength_scores))

    # ─── AUTO-RANKING ───
    if USE_TOP_PAIRS_ONLY:
        selected_pairs, candidates = build_top_pairs(
            strength_scores, ALL_PAIRS,
            top_n=TOP_PAIRS_COUNT, min_gap=TOP_PAIRS_MIN_GAP
        )
        if not selected_pairs:
            logger.warning("⚠️ No pairs met min_gap — scanning ALL pairs")
            selected_pairs = ALL_PAIRS[:]
        else:
            logger.info(f"🎯 AUTO-RANK: Top {len(selected_pairs)} pairs selected")
    else:
        selected_pairs = ALL_PAIRS[:]
        logger.info(f"📋 SCAN ALL: {len(selected_pairs)} pairs")

    # ─── STEP 2: Fetch Data ───
    pair_data = {}
    for pair in selected_pairs:
        oanda = YAHOO_TO_OANDA.get(pair)
        if oanda is None:
            logger.warning(f"⚠️ No OANDA mapping for {pair} — skipping")
            continue
        try:
            raw = fetcher.fetch(pair, oanda, count=200)
            if raw.empty:
                logger.warning(f"{pair}: empty data")
                continue
            df = feat_engine.build(raw)
            df = df.replace([np.inf, -np.inf], np.nan).ffill().bfill().fillna(0)
            if len(df) < 5:
                logger.warning(f"{pair}: insufficient bars")
                continue
            atr_val = df.iloc[-1].get("atr", 0.0)
            rsi_val = df.iloc[-1].get("rsi", 50.0)
            adx_val = df.iloc[-1].get("adx", -1.0)
            if adx_val < 10:
                logger.info(f"⚠️ ADX {pair} = {adx_val:.1f} — possibly flat market")
            logger.info(f"📊 {pair}: {len(df)} bars | ATR={atr_val:.6f} | RSI={rsi_val:.1f} | ADX={adx_val:.1f}")
            pair_data[pair] = {"df": df, "oanda": oanda, "raw": raw, "atr": atr_val, "rsi": rsi_val, "adx": adx_val}
        except Exception as e:
            logger.error(f"❌ Fetch failed {pair}: {e}")

    if not pair_data:
        logger.error("No pairs have usable data. Aborting.")
        send_telegram_message("❌ FX BOT: No usable data")
        return

    # ─── STEP 3: Monte Carlo ───
    if cfg_bot("SKIP_MC", False):
        args.skip_mc = True
    mc_cache = {}
    if not args.skip_mc:
        logger.info("[STEP 3] Monte Carlo Forecasts...")
        mc_gen = MCGenerator(fetcher, YAHOO_TO_OANDA, simulations=SIMULATIONS, confidence=CONFIDENCE)
        for pair in selected_pairs:
            if pair not in pair_data: continue
            mc_data, ok = mc_gen.run_for_pair(pair, df=pair_data[pair]["raw"])
            if ok:
                # ─── 🔒 STRONG MOMENTUM FILTER ──────────────────────────────
                # SKIP unless MC shows "STRONG MOMENTUM" (if enabled in config)
                _require_strong_mc_momentum = cfg_bot("REQUIRE_STRONG_MOMENTUM", True)
                if _require_strong_mc_momentum:
                    mc_text = mc_data.get("regime", "")  # e.g. "⚡ 15m STRONG MOMENTUM"
                    if "STRONG MOMENTUM" not in mc_text:
                        regime_type = mc_text.split(' ')[1] if len(mc_text.split(' '))>=2 else "UNKNOWN"
                        logger.info(f"⏭️ {pair}: MC regime={regime_type} — SKIP (requires STRONG MOMENTUM)")
                        continue  # ⛔ Skip this pair entirely
                    logger.info(f"✅ {pair}: MC STRONG MOMENTUM confirmed — QUALIFIED")
                mc_cache[pair] = mc_data
                logger.info(f"🎲 MC {pair}: {mc_data['regime']} | Band {mc_data['range_90']} | P_UP={mc_data['p_up']}%")
    else:
        logger.info("[STEP 3] MC Skipped — loading legacy...")
        for pair in selected_pairs:
            mc_data, ok = load_mc_legacy(pair, RESULTS_DIR, TODAY_STR, MC_MAX_AGE_HOURS)
            if ok: mc_cache[pair] = mc_data
    if args.mc_only:
        return

    # ─── STEP 4: Multi-Timeframe Confluence ───
    tf_confluence = {}
    if MULTI_TF_CONFLUENCE and not args.test_trade:
        logger.info("[STEP 4] Multi-Timeframe Confluence...")
        TF_GRAN = {"H4": "H4", "1H": "H1", "15m": "M15"}
        for pair in selected_pairs:
            if pair not in pair_data: continue
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
                    if len(raw_tf) < 5: continue
                    sig_tf = strat_engine.generate_signal(pair, oanda, feat_engine.build(raw_tf),
                        None, strength_scores, raw_tf.iloc[-1]["Close"], 1.0)
                    if sig_tf: dirs.append(sig_tf.action)
                except Exception: continue
            buy_c, sell_c = dirs.count("BUY"), dirs.count("SELL")
            passes = buy_c >= CONFLUENCE_REQUIRED_TFS or sell_c >= CONFLUENCE_REQUIRED_TFS
            tf_confluence[pair] = {"buy": buy_c, "sell": sell_c, "passes": passes}
            logger.info(f"🔗 CONFLUENCE {pair}: BUY={buy_c} SELL={sell_c} → {'✅ PASS' if passes else '❌ BLOCK'}")

    # ─── STEP 5: Dynamic Exit Manager ───
    def close_wrap(instr):
        return close_position(api, OANDA_ACCOUNT_ID, instr, send_telegram_message)
    logger.info("[STEP 5] Dynamic Exit Manager...")
    dyn_mgr = DynamicPositionManager(
        api, OANDA_ACCOUNT_ID, TIMEFRAME,
        cfg_bot("BE_TRIGGER_ATR_MULT", 1.5), cfg_bot("TRAIL_TRIGGER_ATR_MULT", 2.5),
        cfg_bot("TRAIL_ATR_MULT", 1.5), cfg_bot("MAX_HOLD_BARS", 12),
        dynamic_tp=DYNAMIC_TP, tp_raise_thresh_pips=TP_RAISE_THRESHOLD_PIPS,
        telegram_send=send_telegram_message
    )
    orig_level = logging.getLogger("oandapyV20").level
    logging.getLogger("oandapyV20").setLevel(logging.CRITICAL)
    dyn_mgr.update_all(pair_data, close_wrap)
    logging.getLogger("oandapyV20").setLevel(orig_level)

    # ─── STEP 6: Scan Open Positions ───
    open_pos_by_oanda, open_pos_count = {}, 0
    if not args.test_trade:
        for pair in selected_pairs:
            oanda = YAHOO_TO_OANDA.get(pair)
            if not oanda: continue
            try:
                pos = get_open_position(api, OANDA_ACCOUNT_ID, oanda)
            except Exception as e:
                err_text = str(e)
                pos = None if ("NO_SUCH_POSITION" in err_text or "404" in err_text) else None
            open_pos_by_oanda[oanda] = bool(pos)
            if pos: open_pos_count += 1

    # ══════════════════════════════════════════════════════════════
    # STEP 7: Score → Collect → Sort → Execute
    # ══════════════════════════════════════════════════════════════
    logger.info("[STEP 7] Scoring & Signals...")
    min_sl_pips_jpy, min_sl_pips_std = cfg_bot("MIN_SL_PIPS_JPY", 35), cfg_bot("MIN_SL_PIPS", 25)
    trade_lines, signal_count = [], 0
    pip_cache = {pair: pip_size(pair) for pair in selected_pairs}
    pair_parts = {p: (p.replace("=X","")[:3], p.replace("=X","")[3:]) for p in selected_pairs}
    all_candidates = []

    for pair in selected_pairs:
        if pair not in pair_data: continue
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
                logger.info(f"⏳ COOLDOWN {pair}: {r-1} runs remaining — SKIP")
                continue
            else:
                del last_closed[pair]
        elif REMOVE_COOLDOWN and pair in last_closed:
            del last_closed[pair]

        # Already Open Check
        if not args.test_trade:
            try: is_open = open_pos_by_oanda.get(oanda, False)
            except: is_open = False
            if is_open:
                logger.info(f"⏭️ {pair}: position already open — SKIP")
                continue

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

        # Strength Gap
        mc_data = mc_cache.get(pair)
        base, quote = pair_parts[pair]
        gap = strength_scores.get(base, 0) - strength_scores.get(quote, 0)
        gap_mag = abs(gap)

        # Gap Filter
        if gap_mag < MIN_STRENGTH_GAP:
            logger.info(f"⏭️ {pair}: gap={gap_mag:.2f} < MIN={MIN_STRENGTH_GAP} — SKIP")
            continue
        logger.info(f"📈 {pair}: gap={gap_mag:.2f} ≥ {MIN_STRENGTH_GAP} — QUALIFIED")

        # Confluence Filter
        if MULTI_TF_CONFLUENCE and not args.test_trade:
            c = tf_confluence.get(pair, {})
            if not c.get("passes", True):
                logger.info(f"🚫 {pair}: confluence fail — SKIP")
                continue

        # Get XGB & MC values
        sig = strat_engine.generate_signal(pair, oanda, df, mc_data, strength_scores, current, spread_pips)
        prob_raw = getattr(sig,"probability",None) or getattr(sig,"model_prob",None) or getattr(sig,"prob",None) or 0.0
        mc_pct_up = mc_data.get("p_up", 50.0) if mc_data else 50.0

        # ⭐ v6.8 CONSENSUS + SCORING
        direction, w = calc_weighted_score(pair, gap, rsi_val, adx_val, prob_raw, mc_pct_up, args.test_trade)
        if direction is None or w is None:
            continue  # No consensus — skipped inside function

        # Score Log — updated weights shown
        logger.info(
            f"⚖️  SCORE {pair} {direction} | "
            f"S={w['S']:5.1f}×{W_S:.2f}={round(w['S']*W_S,1):4.1f}  "
            f"R={w['R']:5.1f}×{W_R:.2f}={round(w['R']*W_R,1):4.1f}  "
            f"A={w['A']:5.1f}×{W_A:.2f}={round(w['A']*W_A,1):4.1f}  "
            f"X={w['X']:5.1f}×{W_X:.2f}={round(w['X']*W_X,1):4.1f}  "
            f"M={w['M']:5.1f}×{W_M:.2f}={round(w['M']*W_M,1):4.1f}  |  "
            f"FINAL={w['FINAL']:5.1f} vs THRESHOLD={w['THRESHOLD']} → "
            f"{'✅ PASS' if w['PASS'] else '❌ FAIL'}"
        )

        if not w["PASS"]:
            logger.info(f"➖ REASON: FINAL {w['FINAL']:.1f} < {w['THRESHOLD']}")
            continue

        # ─── 🆕 HIERARCHICAL ZONE SL: H4→H8→Daily → ATR Fallback ───
        tp_pips = round(atr_val / pip_cache[pair] * cfg_bot("ATR_TP_MULT", 3.0), 1) if DYNAMIC_TP else sl_pips * 1.5

        dec = 3 if "JPY" in pair else 5

        if cfg_bot("SL_USE_ZONE_HIERARCHY", True):
            # 🆕 Zone-based SL — dedicated module
            sl_price, sl_info = compute_sl_zone(
                api, oanda, direction, current, pip_cache[pair], cfg_bot
            )
            sl_price = round(sl_price, dec)
        else:
            # Legacy fixed/ATR SL — untouched
            sl_pips = max(min_sl_pips_jpy if "JPY" in pair else min_sl_pips_std,
                round(atr_val / pip_cache[pair] * cfg_bot("ATR_SL_MULT", 2.0), 1))
            if direction == "BUY":
                sl_price = round(current - sl_pips * pip_cache[pair], dec)
            else:
                sl_price = round(current + sl_pips * pip_cache[pair], dec)

        # ─── TP: 100% UNCHANGED ───
        if direction == "BUY":
            tp_price = round(current + tp_pips * pip_cache[pair], dec)
        else:
            tp_price = round(current - tp_pips * pip_cache[pair], dec)

    # ✅ RANK & EXECUTE
    # ⚖️ Apply balanced LONG/SHORT selection (from separate module)
    all_candidates.append((-FINAL, FINAL, pair, oanda, direction, current, sl_price, tp_price, tp_pips, dec))

    logger.info(f"🏆 RANKED: {len(all_candidates)} passed → opening top {min(MAX_SIMULTANEOUS_TRADES, len(all_candidates))}")
    for i, (_, score, pair, _, dir, _, _, _, _, _) in enumerate(all_candidates, 1):
        logger.info(f"   #{i} — {pair} {dir} SCORE={score:.1f}")

    for neg_score, FINAL, pair, oanda, direction, current, sl_price, tp_price, spread_pips, dec in all_candidates:
        if args.test_trade:
            logger.info(f"🧪 TEST — {direction} {pair} @ {current:.{dec}f} | SL={sl_price} | TP={tp_price}")
            trade_lines.append(f"🧪 {pair} {direction} Score={FINAL:.1f} SL={sl_price} TP={tp_price}")
            continue
        if open_pos_count >= MAX_SIMULTANEOUS_TRADES:
            logger.info(f"⏭️ {pair}: MAX_OPEN reached — SKIP")
            continue
        try:
            resp = open_oanda_order(api, OANDA_ACCOUNT_ID, oanda, direction, DEFAULT_LOT_SIZE, sl_price, tp_price)
            trade_id = resp.get("orderFillTransaction",{}).get("id","?")
            logger.info(f"✅ EXECUTED {pair} {direction} | SL={sl_price} | TP={tp_price} | TradeID={trade_id}")
            trade_lines.append(f"✅ {pair} {direction} Score={FINAL:.1f} | SL={sl_price} TP={tp_price}")
            open_pos_count += 1
        except Exception as e:
            logger.error(f"❌ ORDER FAILED {pair}: {e}")

    # ─── FINAL REPORT ───
    if trade_lines:
        summary = f"🤖 v6.8 RUN COMPLETE — {signal_count} SIGNAL(S)\n\n" + "\n".join(trade_lines)
        send_telegram_message(summary)
    else:
        logger.info("📋 No signals passed thresholds")
        if args.test_trade:
            send_telegram_message("🤖 v6.8 TEST — No signals passed threshold (20.0)")

    logger.info("✅ v6.8 Run Complete")

# -----------------------------------------------------------------------------
# CONFIG OVERRIDE — Add these to config_bot.py to toggle features
# -----------------------------------------------------------------------------
"""
# Add to config_bot.py to revert ANY v6.8 change instantly:
REQUIRE_DIRECTION_CONSENSUS = False   # ← P0 OFF = use strength-only direction
ADX_SCALE_FACTOR = 1.0                 # ← P1 OFF = raw ADX values
WEIGHT_STRENGTH=0.50; WEIGHT_RSI=0.15; WEIGHT_ADX=0.15; WEIGHT_XGBOOST=0.15; WEIGHT_MC=0.05  # ← P2 OFF = original weights
"""

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.exception("Fatal error in main loop")
        send_telegram_message(f"❌ FX BOT FATAL ERROR: {e}")
        raise