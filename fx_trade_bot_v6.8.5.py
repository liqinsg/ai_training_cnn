#!/usr/bin/env python3
"""
    fx_trade_bot_v6.8.5.py — v6.8.5
    Multi-Profile: Profile2/Account002 · Profile3/Account003
    ✅ RSI-FIXED | Consensus | ADX Boost | Monte Carlo | SL Zone Hierarchy
    ✅ TREND FILTER: EMA Fast/Slow Crossover + Weekly EMA100 Counter-Trend Block
    ✅ SMART TP: Fully unified config — TP_MULT + TP_STRONG_MULT
    ✅ EMA100 Buffer logic preserved in TP calc
    ✅ Account IDs from profile config only
    ✅ DUPLICATE-ORDER PROTECTION — Instrument + Run guards
    ✅ MARKET CLOSED = Silent Exit — No Telegram message
    ✅ ALL runs execute live — No test-trade flag
    ✅ Profile3: Trend Filter ON by default | Profile2: Filter OFF


    Usage:
        python fx_trade_bot_v6.8.5.py --profile2   # default, filters OFF
        python fx_trade_bot_v6.8.5.py --profile3   # filters AUTO-ON
        python fx_trade_bot_v6.8.5.py --profile3 --timeframe H4
        python fx_trade_bot_v6.8.5.py --profile3 --trend-filter-enabled false  # override OFF
"""
import contextlib
import sys
import os
import logging
import argparse
import importlib
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import pandas as pd

# ─── PRIMARY IMPORT: config_bot FIRST ───
import config_bot
import config

from utils.trading_core import forex_market_closed
from utils.strategy_helpers import build_strength_matrix, format_strength_ranking, get_live_prices
from telegram_message import send_telegram_message
from oandapyV20.endpoints.instruments import InstrumentsCandles
from strategy_decision import StrategyConfig, StrategyEngine, FilterMode, Direction
from data_pipeline import FeatureConfig, FeatureEngine, ModelWrapper, DataFetcher, ATRModule
from fx_trade_bot_utils import (
    pip_size, load_cooldown, get_open_position, close_position, fetch_candles,
    open_oanda_order_simple as open_oanda_order, DynamicPositionManager, load_mc_legacy,
    calculate_stop_loss,
)
from fx_trade_bot_mc import MCGenerator, MCConfig
from fx_trade_bot_ml import ensure_model
from config_oanda import api

# ─── BASE SETUP ──────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
sys.path.extend([str(BASE_DIR), str(BASE_DIR / "utils")])

# ─── TREND HELPERS ──────────────────────────────────────────────────────────
def calculate_ema(series, period):
    """Calculate Exponential Moving Average"""
    return series.ewm(span=period, adjust=False).mean()


def _pips_to_price(entry, direction, pips, pip_value):
    offset = pips * pip_value
    return entry + offset if direction == "BUY" else entry - offset


def _price_to_pips(entry, tp_price, pip_value):
    return abs(tp_price - entry) / pip_value


def fetch_weekly_ema100(oanda_instrument, api):
    """Fetch Weekly candles and EMA100 for trend filter.

    Safety guards:
      - Missing / short / malformed data → return None (filter bypassed)
      - Never return dummy values that could gate trades
    """
    try:
        resp = api.request(InstrumentsCandles(
            instrument=oanda_instrument,
            params={"granularity": "W", "count": 105, "price": "M"}
        ))
        candles = resp.get("candles") or []
        if len(candles) < 100:
            logger.warning(f"⚠️ Weekly EMA100 {oanda_instrument}: only {len(candles)} candles — filter bypassed")
            return None

        closes = []
        for c in candles:
            try:
                mid = c.get("mid") or {}
                closes.append(float(mid["c"]))
            except (KeyError, TypeError, ValueError):
                continue
        if len(closes) < 100:
            logger.warning(f"⚠️ Weekly EMA100 {oanda_instrument}: not enough valid closes — filter bypassed")
            return None

        series = pd.Series(closes)
        ema100 = float(calculate_ema(series, 100).iloc[-1])

        closes_arr = np.asarray(closes, dtype=float)
        mean_close = float(closes_arr.mean())
        last_close = float(closes[-1])
        flat_corrupt = (mean_close > 0 and float(closes_arr.std()) / mean_close < 1e-6)

        # Plausibility guards
        if not np.isfinite(ema100) or ema100 <= 0 or last_close <= 0:
            logger.warning(f"⚠️ Weekly EMA100 {oanda_instrument}: invalid EMA={ema100:.5f} — filter bypassed")
            return None
        if flat_corrupt:
            logger.warning(
                f"⚠️ Weekly EMA100 {oanda_instrument}: flat/corrupt weekly series "
                f"(std/mean={float(closes_arr.std()) / mean_close:.2e}) — filter bypassed"
            )
            return None
        if abs(ema100 - last_close) / last_close > 0.25:
            logger.warning(
                f"⚠️ Weekly EMA100 {oanda_instrument}: implausible EMA={ema100:.5f} "
                f"vs last weekly close={last_close:.5f} — filter bypassed"
            )
            return None

        return ema100
    except Exception as e:
        logger.warning(f"⚠️ Cannot fetch Weekly EMA100 for {oanda_instrument}: {e}")
        return None


def evaluate_trend_and_tp(profile_name, direction, mc_pct_up,
                          entry_price, pip_value, df, weekly_ema100,
                          ema_cross_filter, fast_period, slow_period,
                          base_tp_pips, mc_strong_threshold,
                          tp_mult, tp_strong_mult,
                          ema100_buffer_pips=30,
                          timeframe="15m"):
    """
    ENTRY FILTERS:
      A — EMA Crossover Alignment: Price → EMA_Fast → EMA_Slow
      B — No counter-trend vs Weekly EMA100
    TP LOGIC:
      Profile-aware multipliers + EMA100 buffer protection
    """
    current_price = entry_price

    # ─── RULE A: EMA CROSSOVER TREND ALIGNMENT ───────────────────────
    if ema_cross_filter:
        ema_fast = calculate_ema(df["Close"], fast_period)
        ema_slow = calculate_ema(df["Close"], slow_period)
        fast_val = ema_fast.iloc[-1]
        slow_val = ema_slow.iloc[-1]

        if direction == "BUY":
            # ✅ Uptrend = Price > Fast AND Fast > Slow
            uptrend_aligned = (current_price > fast_val) and (fast_val > slow_val)
            if not uptrend_aligned:
                reason = (f"{timeframe} TREND MISALIGNED — Price={current_price:.5f}, "
                          f"EMA{fast_period}={fast_val:.5f}, EMA{slow_period}={slow_val:.5f} → NOT UPTREND")
                logger.info(f"⏭️ SKIP BUY: {reason}")
                return False, 0.0, reason
        else:  # SELL
            # ✅ Downtrend = Price < Fast AND Fast < Slow
            downtrend_aligned = (current_price < fast_val) and (fast_val < slow_val)
            if not downtrend_aligned:
                reason = (f"{timeframe} TREND MISALIGNED — Price={current_price:.5f}, "
                          f"EMA{fast_period}={fast_val:.5f}, EMA{slow_period}={slow_val:.5f} → NOT DOWNTREND")
                logger.info(f"⏭️ SKIP SELL: {reason}")
                return False, 0.0, reason

    # ─── RULE B: Weekly EMA100 Counter-Trend Check ────────────────────
    # weekly_ema100 = None → filter OFF → skip entirely
    if weekly_ema100 is not None:
        if direction == "BUY" and current_price < weekly_ema100:
            reason = f"COUNTER-TREND vs WEEKLY EMA100 — Price below {weekly_ema100:.5f}"
            logger.info(f"⏭️ SKIP BUY: {reason}")
            return False, 0.0, reason

        if direction == "SELL" and current_price > weekly_ema100:
            reason = f"COUNTER-TREND vs WEEKLY EMA100 — Price above {weekly_ema100:.5f}"
            logger.info(f"⏭️ SKIP SELL: {reason}")
            return False, 0.0, reason

    # ─── TP CALCULATION + EMA100 Buffer Protection ─────────────────────
    mc_momentum = mc_pct_up / 100.0
    if mc_momentum >= mc_strong_threshold:
        tp_pips = base_tp_pips * tp_strong_mult
    else:
        tp_pips = base_tp_pips * tp_mult

    # ✅ Buffer: TP never lands inside Weekly EMA100 zone
    if weekly_ema100 is not None and ema_cross_filter:
        if direction == "BUY":
            min_tp_price = weekly_ema100 + ema100_buffer_pips * pip_value
            min_tp_pips = (min_tp_price - current_price) / pip_value
            if tp_pips < min_tp_pips:
                logger.info(f"🛡️ TP adjusted — buffer {ema100_buffer_pips}p above Weekly EMA100 → {min_tp_pips:.1f}p")
                tp_pips = min_tp_pips
        else:
            max_tp_price = weekly_ema100 - ema100_buffer_pips * pip_value
            min_tp_pips = (current_price - max_tp_price) / pip_value
            if tp_pips < min_tp_pips:
                logger.info(f"🛡️ TP adjusted — buffer {ema100_buffer_pips}p below Weekly EMA100 → {min_tp_pips:.1f}p")
                tp_pips = min_tp_pips

    return True, tp_pips, f"TP={tp_pips:.1f}p"


# ─── SINGLE PARSER + PROFILE SELECTION ──────────────────────────────────────
parser = argparse.ArgumentParser(
    description="FX Trading Bot v6.8.5 — Multi-Profile"
)
parser.add_argument("--profile2", action="store_true", help="Use Profile2 / Account002")
parser.add_argument("--profile3", action="store_true", help="Use Profile3 / Account003")
parser.add_argument("--timeframe", type=str, default="15m", choices=["15m", "1H", "H4"])
parser.add_argument("--trend-filter-enabled", type=str.lower, choices=["true","false","1","0"], default=None,
                    help="Override TREND_FILTER_ENABLED (default: Profile3=ON, Profile2=OFF)")
parser.add_argument("--confluence", action="store_true", default=None)
parser.add_argument("--no-confluence", action="store_false", dest="confluence")
parser.add_argument("--skip-mc", action="store_true")
parser.add_argument("--mc-only", action="store_true")
args = parser.parse_args()


# ─── DETERMINE PROFILE FROM ARGS ──────────────────────────────────────────────
if args.profile3:
    PROFILE_MODULE = "config_bot_profile3"
    PROFILE_LABEL = "PROFILE3"
    ACCOUNT_NAME = "Account 003"
    PROFILE_NAME = "profile3"
    COOLDOWN_FILE = BASE_DIR / "cooldown_profile3.json"
    RESULTS_DIR = BASE_DIR / "daily_results_profile3"
else:
    PROFILE_MODULE = "config_bot_profile2"
    PROFILE_LABEL = "PROFILE2"
    ACCOUNT_NAME = "Account 002"
    PROFILE_NAME = "profile2"
    COOLDOWN_FILE = BASE_DIR / "cooldown_profile2.json"
    RESULTS_DIR = BASE_DIR / "daily_results_profile2"


# ✅ Load profile config
profile_cfg = importlib.import_module(PROFILE_MODULE)


# ✅ Account ID COMES ONLY FROM PROFILE CONFIG — single source of truth
OANDA_ACCOUNT_ID = getattr(profile_cfg, "OANDA_ACCOUNT_ID", None)
if not OANDA_ACCOUNT_ID:
    raise RuntimeError(f"OANDA_ACCOUNT_ID not found in {PROFILE_MODULE}. Please define it there.")


# ─── CENTRAL CONFIG LOOKUP ──────────────────────────────────────────────────
def cfg_bot(name, default):
    """Lookup priority: profile_cfg → config_bot → config → default"""
    return getattr(profile_cfg, name, getattr(config_bot, name, getattr(config, name, default)))


def cfg(name, default):
    return getattr(config, name, default)


# ─── TREND FILTER + SMART TP CONFIGURATION ──────────────────────────────────
# ✅ Fully unified — cfg_bot() auto-loads Profile2 OR Profile3 values
# ✅ TP_STRONG_MULT defaults to 1.0 = NO boost unless explicitly set
# ✅ EMA periods: Fast = EMA_PERIOD, Slow = EMA_PERIOD × 2
base_tp_pips = cfg_bot("BASE_TP_PIPS", 30)
mc_strong_threshold = cfg_bot("MC_STRONG_THRESHOLD", 0.75)
ema_period_fast = cfg_bot("EMA_PERIOD", 10)
ema_period_slow = ema_period_fast * 2
ema100_buffer_pips = cfg_bot("EMA100_BUFFER_PIPS", 30)
tp_mult = cfg_bot("TP_MULT", 1.0)
tp_strong_mult = cfg_bot("TP_STRONG_MULT", 1.0)

# ✅ TREND FILTER: Profile3=ON by default | Profile2=OFF by default
TREND_FILTER_ENABLED = (PROFILE_NAME == "profile3")

# ✅ CLI flag overrides profile default
if args.trend_filter_enabled is not None:
    TREND_FILTER_ENABLED = args.trend_filter_enabled in ("true", "1")
    logger_info_cli = f"🔧 CLI OVERRIDE: TREND_FILTER_ENABLED={TREND_FILTER_ENABLED}"
else:
    logger_info_cli = f"🔍 AUTO: TREND_FILTER_ENABLED={TREND_FILTER_ENABLED} | profile={PROFILE_NAME}"


# ─── INIT FOLDERS & LOGGING ──────────────────────────────────────────────────
RESULTS_DIR.mkdir(exist_ok=True)
TODAY_STR = datetime.now(timezone.utc).strftime("%Y%m%d")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(BASE_DIR / f"bot_{PROFILE_LABEL.lower()}.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# Log CLI or auto-detected filter state
logger.info(logger_info_cli)

# ─── CONSOLIDATED STRATEGY CONSTANTS ─────────────────────────────────────────
REQUIRE_DIRECTION_CONSENSUS = cfg_bot("REQUIRE_DIRECTION_CONSENSUS", True)
CONSENSUS_THRESHOLD = cfg_bot("CONSENSUS_THRESHOLD", 2)
XGB_BULLISH_THRESHOLD = cfg_bot("XGB_BULLISH_THRESHOLD", 0.55)
MC_BULLISH_THRESHOLD = cfg_bot("MC_BULLISH_THRESHOLD_PCT", 55.0)

ADX_SCALE_FACTOR = cfg_bot("ADX_SCALE_FACTOR", 2.0)
ADX_FLOOR_ENABLED = cfg_bot("ADX_FLOOR_ENABLED", True)
ADX_MIN_SCORE = cfg_bot("ADX_MIN_SCORE", 20.0)
ADX_BOOST_ENABLED = cfg_bot("ADX_BOOST_ENABLED", True)
ADX_BOOST_THRESHOLD = cfg_bot("ADX_BOOST_THRESHOLD", 30.0)
ADX_BOOST_VALUE = cfg_bot("ADX_BOOST_VALUE", 10.0)

W_S = cfg_bot("WEIGHT_STRENGTH", 0.40)
W_R = cfg_bot("WEIGHT_RSI", 0.15)
W_A = cfg_bot("WEIGHT_ADX", 0.15)
W_X = cfg_bot("WEIGHT_XGB", 0.20)
W_M = cfg_bot("WEIGHT_MC", 0.10)

_WEIGHT_SUM = W_S + W_R + W_A + W_X + W_M
if abs(_WEIGHT_SUM - 1.00) > 0.001:
    logger.warning(f"⚠️ Weight sum = {_WEIGHT_SUM:.4f} ≠ 1.00 — normalizing")
    weights = [w / _WEIGHT_SUM for w in [W_S, W_R, W_A, W_X, W_M]]
    W_S, W_R, W_A, W_X, W_M = weights
logger.info(f"⚖️  {PROFILE_LABEL} WEIGHTS: S={W_S:.2f} R={W_R:.2f} A={W_A:.2f} X={W_X:.2f} M={W_M:.2f} | SUM=1.00")

MIN_STRENGTH_GAP = cfg_bot("MIN_SCORE_GAP", 0.25)
DEBUG_DETAIL = cfg_bot("DEBUG_DETAIL", True)
USE_TOP_PAIRS_ONLY = cfg_bot("USE_TOP_PAIRS_ONLY", False)
TOP_PAIRS_COUNT = cfg_bot("TOP_PAIRS_COUNT", 4)
TOP_PAIRS_MIN_GAP = cfg_bot("TOP_PAIRS_MIN_GAP", 0.25)

DEBUG_MODE = cfg_bot("DEBUG_MODE", False)
if not DEBUG_MODE:
    logging.getLogger("oandapyV20").setLevel(logging.WARNING)
MAX_SIMULTANEOUS_TRADES = cfg_bot("MAX_OPEN_POSITIONS", 4)
MAX_OPEN = MAX_SIMULTANEOUS_TRADES
TRAILING_TP = cfg_bot("TRAILING_TP", False)
DYNAMIC_TP = cfg_bot("DYNAMIC_TP", True)
MULTI_TF_CONFLUENCE = cfg_bot("MULTI_TF_CONFLUENCE", False)
CONFLUENCE_REQUIRED_TFS = cfg_bot("CONFLUENCE_REQUIRED_TFS", 2)
TP_RAISE_THRESHOLD_PIPS = cfg_bot("TP_RAISE_THRESHOLD_PIPS", 15)

# ─── CLI MODE OVERRIDES ──────────────────────────────────────────────────────
MODE = cfg_bot("MODE", "LEVEL10")
TIMEFRAME = args.timeframe
OANDA_GRANULARITY_MAP = {"15m": "M15", "1H": "H1", "H4": "H4", "D": "D"}
OANDA_GRANULARITY = OANDA_GRANULARITY_MAP.get(TIMEFRAME, "H4")
DEFAULT_LOT_SIZE = cfg_bot("DEFAULT_LOT_SIZE", 10000)

ALL_PAIRS = cfg_bot("ALL_PAIRS", [
    "EURUSD=X", "GBPUSD=X", "EURJPY=X", "GBPJPY=X",
    "AUDUSD=X", "USDJPY=X", "GBPAUD=X", "USDCHF=X",
    "AUDJPY=X", "EURGBP=X", "NZDUSD=X", "CADJPY=X",
])
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
    YAHOO_TO_OANDA.setdefault(_sym, _oanda)
logger.info(f"✅ Pair mappings loaded: {len(YAHOO_TO_OANDA)} entries")

MC_MAX_AGE_HOURS = cfg_bot("MC_MAX_AGE_HOURS", 24)
SIMULATIONS = cfg_bot("MC_SIMULATIONS", 5000)
CONFIDENCE = cfg_bot("MC_BAND_PCT", 90) / 100.0

REMOVE_COOLDOWN = cfg_bot("REMOVE_COOLDOWN", False)
if args.confluence is not None:
    MULTI_TF_CONFLUENCE = args.confluence

# ─── MC TIMEFRAME CONFIG ─────────────────────────────────────────────────────
if TIMEFRAME in ("H4", "1H", "15m"):
    MCConfig.set_timeframe(TIMEFRAME, {
        "YF_INTERVAL": cfg_bot("YF_INTERVAL", "4h"),
        "YF_PERIOD_FULL": cfg_bot("YF_PERIOD_FULL", "30d"),
        "YF_PERIOD_RESAMPLE": cfg_bot("YF_PERIOD_RESAMPLE", "60d"),
        "MC_LOOKBACK": cfg_bot("H4_LOOKBACK", 90),
        "MC_FORECAST": cfg_bot("H4_FORECAST", 8),
        "PERIODS_YEAR": cfg_bot("PERIODS_YEAR", 252) * 6,
        "MC_REPORT_TITLE": f"[{PROFILE_LABEL}] FX {TIMEFRAME} MONTE CARLO",
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
        "MC_REPORT_TITLE": f"[{PROFILE_LABEL}] FX DAILY MONTE CARLO",
        "RESULTS_DIR": RESULTS_DIR,
    })

# ─── PIPELINE & STRATEGY CONFIG ──────────────────────────────────────────────
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
min_conv = cfg_bot("MIN_CONVICTION_SCORE", 30.0) if MODE == "LEVEL10" else cfg_bot("MIN_CONVICTION_SCORE_ALT", 45.0)
min_edge = cfg_bot("BASE_MIN_EDGE", 0.50) if MODE == "LEVEL10" else cfg_bot("BASE_MIN_EDGE_ALT", 0.51)
STRAT_CFG = StrategyConfig(
    mode=MODE, min_conviction_score=min_conv, base_min_edge=min_edge,
    mc_filter_mode=FilterMode.PENALIZE, regime_filter_mode=FilterMode.OFF,
    adx_filter_mode=FilterMode.OFF, pivot_filter_mode=FilterMode.PENALIZE,
    strength_gap_filter_mode=FilterMode.PENALIZE, cooldown_filter_mode=FilterMode.BLOCK,
)

fetcher = DataFetcher(use_oanda=True, oanda_api=api, oanda_granularity=OANDA_GRANULARITY)
feat_engine = FeatureEngine(FEAT_CFG)
strat_engine = StrategyEngine(STRAT_CFG, model=None, feature_list=[])
atr_mod = ATRModule(period=getattr(FEAT_CFG, "atr_period", cfg_bot("ATR_PERIOD", 14)))
MODEL_PATH = BASE_DIR / "trade_model_xgb.pkl"
model_wrapper = ModelWrapper(FEAT_CFG, model_path=MODEL_PATH)
last_closed = {} if REMOVE_COOLDOWN else load_cooldown(COOLDOWN_FILE, Direction)

# ─── HELPER FUNCTIONS ─────────────────────────────────────────────────────────
def build_top_pairs(strength_scores, all_pairs, top_n=4, min_gap=0.25):
    ranked = sorted(strength_scores.items(), key=lambda x: x[1], reverse=True)
    strongest = [ccy for ccy, _ in ranked[:top_n]]
    weakest = [ccy for ccy, _ in ranked[-top_n:]]
    candidate_pairs = []
    for i in range(min(top_n, len(strongest), len(weakest))):
        base, quote = strongest[i], weakest[-(i+1)]
        if base == quote: continue
        gap = strength_scores[base] - strength_scores[quote]
        if abs(gap) >= min_gap:
            symbol = f"{base}{quote}=X" if f"{base}{quote}=X" in all_pairs else f"{quote}{base}=X"
            if symbol in all_pairs:
                candidate_pairs.append((symbol, abs(gap), base, quote))
    candidate_pairs.sort(key=lambda x: x[1], reverse=True)
    return [p[0] for p in candidate_pairs[:top_n]], candidate_pairs


def calc_weighted_score(pair: str, gap: float, rsi_val: float, adx_val: float,
                        xgb_prob: float, mc_pct_up: float):
    """RSI-FIXED Direction-Aware Consensus Scoring — shared across profiles"""
    MIN_FINAL_SCORE = min_conv

    strength_dir = "BUY" if gap >= MIN_STRENGTH_GAP else "SELL" if gap <= -MIN_STRENGTH_GAP else "NEUTRAL"
    xgb_dir = "BUY" if (xgb_prob or 0.0) >= XGB_BULLISH_THRESHOLD else "SELL"
    mc_dir = "BUY" if (mc_pct_up or 50.0) >= MC_BULLISH_THRESHOLD else "SELL"

    buy_votes  = sum(1 for d in (strength_dir, xgb_dir, mc_dir) if d == "BUY")
    sell_votes = sum(1 for d in (strength_dir, xgb_dir, mc_dir) if d == "SELL")
    logger.info(f"🤝 {pair}: Strength={strength_dir} | XGB={xgb_dir} | MC={mc_dir} | BUY={buy_votes}/3")

    if REQUIRE_DIRECTION_CONSENSUS:
        if buy_votes >= CONSENSUS_THRESHOLD:
            direction = "BUY"; logger.info(f"✅ {pair}: BUY consensus ({buy_votes}/3)")
        elif sell_votes >= CONSENSUS_THRESHOLD:
            direction = "SELL"; logger.info(f"✅ {pair}: SELL consensus ({sell_votes}/3)")
        else:
            logger.info(f"⏭️  {pair}: NO CONSENSUS → SKIP")
            return None, None
    else:
        direction = "BUY" if gap > 0 else "SELL"
        logger.info(f"ℹ️  Consensus OFF — using Strength only: {direction}")

    S = max(0.0, min(100.0, abs(gap) / 3.5 * 100.0))
    rsi = max(0.0, min(100.0, rsi_val))
    if direction == "BUY":
        R = max(0.0, min(100.0, (50.0 - rsi) * 2.0))
    else:
        R = max(0.0, min(100.0, (rsi - 50.0) * 2.0))

    adx_normalized = min(adx_val * ADX_SCALE_FACTOR, 100.0)
    if ADX_FLOOR_ENABLED and adx_normalized < ADX_MIN_SCORE:
        A = ADX_MIN_SCORE
    elif ADX_BOOST_ENABLED and adx_val >= ADX_BOOST_THRESHOLD:
        A = min(100.0, adx_normalized + ADX_BOOST_VALUE)
    else:
        A = adx_normalized
    A = max(0.0, min(100.0, A))

    X = max(0.0, min(100.0, (xgb_prob or 0.0) * 100.0))
    if X == 0.0:
        X = max(0.0, min(100.0, S * 0.3 + R * 0.3))
    M = max(0.0, min(100.0, mc_pct_up if mc_pct_up is not None else 50.0))

    FINAL = S*W_S + R*W_R + A*W_A + X*W_X + M*W_M
    return direction, {
        "S": round(S,1), "R": round(R,1), "A": round(A,1),
        "X": round(X,1), "M": round(M,1), "FINAL": round(FINAL,1),
        "PASS": FINAL >= MIN_FINAL_SCORE, "THRESHOLD": round(MIN_FINAL_SCORE,1),
    }


# ─── MAIN TRADING FLOW ───────────────────────────────────────────────────────
def main():
    global model_wrapper, strat_engine
    logger.info(f"\n🤖 RUN v6.8.5 {PROFILE_LABEL} — {ACCOUNT_NAME} | "
                f"FILTERS={'ON' if TREND_FILTER_ENABLED else 'OFF'} | "
                f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} | "
                f"MAX_OPEN={MAX_OPEN} | MIN_GAP={MIN_STRENGTH_GAP}")
    logger.info(f"🔑 OANDA Account ID: {OANDA_ACCOUNT_ID}")

    # ✅ MARKET CLOSED = SILENT EXIT — no Telegram message
    if forex_market_closed():
        return

    model_wrapper, strat_engine = ensure_model(
        MODEL_PATH, FEAT_CFG, model_wrapper, strat_engine,
        fetcher, feat_engine, ALL_PAIRS, YAHOO_TO_OANDA, cfg_bot,
    )

    # Step 1 — Currency Strength
    logger.info("[STEP 1] Currency Strength...")
    strength_scores = build_strength_matrix()
    logger.info(format_strength_ranking(strength_scores))

    if USE_TOP_PAIRS_ONLY:
        selected_pairs, _ = build_top_pairs(strength_scores, ALL_PAIRS,
                                            top_n=TOP_PAIRS_COUNT, min_gap=TOP_PAIRS_MIN_GAP)
        selected_pairs = selected_pairs or ALL_PAIRS[:]
        logger.info(f"🎯 AUTO-RANK: Top {len(selected_pairs)} pairs selected")
    else:
        selected_pairs = ALL_PAIRS[:]
        logger.info(f"📋 SCAN ALL: {len(selected_pairs)} pairs")

    # Step 2 — Fetch Data
    pair_data = {}
    weekly_ema_cache = {}
    for pair in selected_pairs:
        oanda = YAHOO_TO_OANDA.get(pair)
        if not oanda:
            logger.warning(f"⚠️ No OANDA mapping for {pair} — skipping")
            continue
        try:
            raw = fetcher.fetch(pair, oanda, count=200)
            if raw.empty: continue
            df = feat_engine.build(raw).replace([np.inf, -np.inf], np.nan).ffill().bfill().fillna(0)
            if len(df) < 5: continue
            pair_data[pair] = {
                "df": df, "oanda": oanda, "raw": raw,
                "atr": df.iloc[-1].get("atr", 0.0),
                "rsi": df.iloc[-1].get("rsi", 50.0),
                "adx": df.iloc[-1].get("adx", -1.0),
            }
            if pair_data[pair]["adx"] < 10:
                logger.info(f"⚠️ ADX {pair} = {pair_data[pair]['adx']:.1f} — possibly flat market")
            logger.info(f"📊 {pair}: {len(df)} bars | ATR={pair_data[pair]['atr']:.6f} | "
                        f"RSI={pair_data[pair]['rsi']:.1f} | ADX={pair_data[pair]['adx']:.1f}")
            weekly_ema_cache[oanda] = fetch_weekly_ema100(oanda, api)
        except Exception as e:
            logger.error(f"❌ Fetch failed {pair}: {e}")
    if not pair_data:
        logger.error("No pairs have usable data. Aborting.")
        send_telegram_message(f"❌ FX BOT {PROFILE_LABEL}: No usable data")
        return

    # Step 3 — Monte Carlo
    if cfg_bot("SKIP_MC", False):
        args.skip_mc = True
    mc_cache = {}
    if not args.skip_mc:
        logger.info("[STEP 3] Monte Carlo Forecasts...")
        mc_gen = MCGenerator(fetcher, YAHOO_TO_OANDA, simulations=SIMULATIONS, confidence=CONFIDENCE)
        require_mc_momentum = cfg_bot("REQUIRE_STRONG_MOMENTUM", True)
        for pair in selected_pairs:
            if pair not in pair_data: continue
            mc_data, ok = mc_gen.run_for_pair(pair, df=pair_data[pair]["raw"])
            if ok:
                regime = mc_data.get("regime", "")
                if require_mc_momentum and "STRONG MOMENTUM" not in regime:
                    logger.info(f"⏭️ {pair}: MC regime={regime.split()[1] if ' ' in regime else 'UNKNOWN'} — SKIP")
                    continue
                mc_cache[pair] = mc_data
                logger.info(f"🎲 MC {pair}: {regime} | Band {mc_data['range_90']} | P_UP={mc_data['p_up']}%")
    else:
        logger.info("[STEP 3] MC Skipped — loading legacy...")
        for pair in selected_pairs:
            mc_data, ok = load_mc_legacy(pair, RESULTS_DIR, TODAY_STR, MC_MAX_AGE_HOURS)
            if ok: mc_cache[pair] = mc_data
    if args.mc_only:
        return

    # Step 4 — Multi-Timeframe Confluence
    tf_confluence = {}
    if MULTI_TF_CONFLUENCE:
        logger.info("[STEP 4] Multi-Timeframe Confluence...")
        TF_GRAN = {"H4": "H4", "1H": "H1", "15m": "M15"}
        for pair in selected_pairs:
            if pair not in pair_data: continue
            dirs = []
            for gran in TF_GRAN.values():
                with contextlib.suppress(Exception):
                    raw_tf = fetch_candles(pair_data[pair]["oanda"], gran)
                    if len(raw_tf) < 5: continue
                    sig = strat_engine.generate_signal(pair, pair_data[pair]["oanda"],
                                                        feat_engine.build(raw_tf), None,
                                                        strength_scores, raw_tf.iloc[-1]["Close"], 1.0)
                    if sig: dirs.append(sig.action)
            buy_c, sell_c = dirs.count("BUY"), dirs.count("SELL")
            passes = buy_c >= CONFLUENCE_REQUIRED_TFS or sell_c >= CONFLUENCE_REQUIRED_TFS
            tf_confluence[pair] = {"buy": buy_c, "sell": sell_c, "passes": passes}
            logger.info(f"🔗 CONFLUENCE {pair}: BUY={buy_c} SELL={sell_c} → {'✅ PASS' if passes else '❌ BLOCK'}")

    # Step 5 — Dynamic Exit Manager
    logger.info("[STEP 5] Dynamic Exit Manager...")
    def close_wrap(instr):
        return close_position(api, OANDA_ACCOUNT_ID, instr, send_telegram_message)
    dyn_mgr = DynamicPositionManager(
        api, OANDA_ACCOUNT_ID, TIMEFRAME,
        cfg_bot("BE_TRIGGER_ATR_MULT", 1.5), cfg_bot("TRAIL_TRIGGER_ATR_MULT", 2.5),
        cfg_bot("TRAIL_ATR_MULT", 1.5), cfg_bot("MAX_HOLD_BARS", 12),
        dynamic_tp=DYNAMIC_TP, tp_raise_thresh_pips=TP_RAISE_THRESHOLD_PIPS,
        telegram_send=send_telegram_message,
    )
    oanda_level = logging.getLogger("oandapyV20").level
    logging.getLogger("oandapyV20").setLevel(logging.CRITICAL)
    dyn_mgr.update_all(pair_data, close_wrap)
    logging.getLogger("oandapyV20").setLevel(oanda_level)

    # Step 6 — Scan Open Positions
    open_pos_by_oanda, open_pos_count = {}, 0
    logger.info("🔍 Checking open positions...")
    for pair in selected_pairs:
        oanda_inst = YAHOO_TO_OANDA.get(pair)
        if not oanda_inst: continue
        pos = get_open_position(api, OANDA_ACCOUNT_ID, oanda_inst)
        is_open = pos is not None
        open_pos_by_oanda[oanda_inst] = is_open
        if is_open:
            open_pos_count += 1
            logger.info(f"📌 OPEN POSITION: {pair} → {oanda_inst} | {pos['side'].upper()} | units={pos['units']}")
    open_list = [o.replace("_","/") for o,s in open_pos_by_oanda.items() if s]
    ready_list = [p.replace("=X","") for p in selected_pairs if not open_pos_by_oanda.get(YAHOO_TO_OANDA.get(p), False)]
    logger.info(f"📊 Open positions: {open_pos_count}/{MAX_OPEN} | OPEN: {', '.join(open_list) or 'None'} | READY: {', '.join(ready_list) or 'None'}")

    # Step 7 — Score, Trend Filter, Smart TP & Execute
    logger.info("[STEP 7] Scoring + TREND FILTER + SMART TP...")
    min_sl_pips_jpy, min_sl_pips_std = cfg_bot("MIN_SL_PIPS_JPY", 35), cfg_bot("MIN_SL_PIPS", 25)
    trade_lines, pip_cache, pair_parts = {}, {p: pip_size(p) for p in selected_pairs}, {p: (p[:3], p[3:].replace("=X","")) for p in selected_pairs}
    all_candidates = []

    for pair in selected_pairs:
        if pair not in pair_data: continue
        oanda = pair_data[pair]["oanda"]
        atr_val, rsi_val, adx_val = pair_data[pair]["atr"], pair_data[pair]["rsi"], pair_data[pair]["adx"]

        # Cooldown
        if pair in last_closed:
            d, r = last_closed[pair]
            if r > 0:
                last_closed[pair] = (d, r-1)
                logger.info(f"⏳ COOLDOWN {pair}: {r-1} runs remaining — SKIP")
                continue
            else:
                del last_closed[pair]

        # Already Open → SKIP DUPLICATE
        if open_pos_by_oanda.get(oanda, False):
            logger.info(f"⏭️ {pair}: position already open — SKIP DUPLICATE")
            continue

        # Current Price
        try:
            prices = get_live_prices(oanda)
            if prices and "bid" in prices and "ask" in prices:
                current = prices["bid"]
                spread_pips = abs(prices["ask"] - prices["bid"]) / pip_cache[pair]
            else:
                raise ValueError()
        except Exception:
            current = float(pair_data[pair]["df"].iloc[-1]["Close"])
            spread_pips = 1.0

        # Strength Gap
        base, quote = pair_parts[pair]
        gap = strength_scores.get(base, 0) - strength_scores.get(quote, 0)
        if abs(gap) < MIN_STRENGTH_GAP:
            logger.info(f"⏭️ {pair}: gap={abs(gap):.2f} < MIN={MIN_STRENGTH_GAP} — SKIP")
            continue
        logger.info(f"📈 {pair}: gap={abs(gap):.2f} ≥ {MIN_STRENGTH_GAP} — QUALIFIED")

        # Confluence Filter
        if MULTI_TF_CONFLUENCE and not tf_confluence.get(pair, {}).get("passes", True):
            logger.info(f"🚫 {pair}: confluence fail — SKIP")
            continue

        # Get Model & MC
        sig = strat_engine.generate_signal(pair, oanda, pair_data[pair]["df"], mc_cache.get(pair),
                                            strength_scores, current, spread_pips)
        prob_raw = getattr(sig, "model_p_up", None)
        if prob_raw is None:
            prob_raw = 0.0
        mc_pct_up = mc_cache.get(pair, {}).get("p_up", 50.0)

        # Score
        direction, w = calc_weighted_score(pair, gap, rsi_val, adx_val, prob_raw, mc_pct_up)
        if not (direction and w and w["PASS"]):
            if w and not w["PASS"]:
                logger.info(f"➖ REASON: FINAL {w['FINAL']:.1f} < {w['THRESHOLD']}")
            continue

        logger.info(
            f"⚖️  SCORE {pair} {direction} | "
            f"S={w['S']:5.1f}×{W_S:.2f}={w['S']*W_S:4.1f}  "
            f"R={w['R']:5.1f}×{W_R:.2f}={w['R']*W_R:4.1f}  "
            f"A={w['A']:5.1f}×{W_A:.2f}={w['A']*W_A:4.1f}  "
            f"X={w['X']:5.1f}×{W_X:.2f}={w['X']*W_X:4.1f}  "
            f"M={w['M']:5.1f}×{W_M:.2f}={w['M']*W_M:4.1f}  | FINAL={w['FINAL']:5.1f}"
        )

        # ─── ✅ TREND FILTER + SMART TP ────────────────────────────────
        weekly_ema100_price = weekly_ema_cache.get(oanda)
        weekly_ema100 = weekly_ema100_price if TREND_FILTER_ENABLED else None

        allow_entry, smart_tp_pips, tp_info = evaluate_trend_and_tp(
            PROFILE_NAME, direction, mc_pct_up,
            current, pip_cache[pair],
            pair_data[pair]["df"], weekly_ema100,
            ema_cross_filter=TREND_FILTER_ENABLED,
            fast_period=ema_period_fast,
            slow_period=ema_period_slow,
            base_tp_pips=base_tp_pips,
            mc_strong_threshold=mc_strong_threshold,
            tp_mult=tp_mult,
            tp_strong_mult=tp_strong_mult,
            ema100_buffer_pips=ema100_buffer_pips,
            timeframe=TIMEFRAME
        )

        if not allow_entry:
            continue  # TREND FILTER REJECTED

        # SL & TP — SMART TP instead of fixed ATR multiplier
        dec = 3 if "JPY" in pair else 5
        if cfg_bot("SL_USE_ZONE_HIERARCHY", True):
            # ── SL Zone Hierarchy: closed H4 candles only + offset + cap ──
            try:
                h4_df = fetch_candles(api, oanda, "H4", count=5)
                if h4_df is None or len(h4_df) < 5:
                    raise ValueError(
                        f"insufficient H4 candles ({0 if h4_df is None else len(h4_df)})"
                    )
                # ✅ Drop forming candle → use ONLY closed bars
                h4_closed = [
                    {"high": float(r["High"]), "low": float(r["Low"])}
                    for _, r in h4_df.iloc[:-1].iterrows()
                ]
                sl_price, sl_pips, skip_trade = calculate_stop_loss(
                    direction, current, h4_closed, pip_cache[pair]
                )
                if skip_trade:
                    logger.warning(f"🚫 {pair}: SL distance > 200 pips — TRADE ABORTED")
                    continue
                sl_price = round(sl_price, dec)
            except Exception as e:
                logger.error(f"⚠️ {pair}: calculate_stop_loss failed ({e}) — falling back to ATR SL")
                sl_pips = max(min_sl_pips_jpy if "JPY" in pair else min_sl_pips_std,
                              round(atr_val / pip_cache[pair] * cfg_bot("ATR_SL_MULT", 2.0), 1))
                sl_price = round(current - sl_pips * pip_cache[pair], dec) if direction == "BUY" else \
                           round(current + sl_pips * pip_cache[pair], dec)
        else:
            sl_pips = max(min_sl_pips_jpy if "JPY" in pair else min_sl_pips_std,
                          round(atr_val / pip_cache[pair] * cfg_bot("ATR_SL_MULT", 2.0), 1))
            sl_price = round(current - sl_pips * pip_cache[pair], dec) if direction == "BUY" else \
                       round(current + sl_pips * pip_cache[pair], dec)

        tp_price = round(current + smart_tp_pips * pip_cache[pair], dec) if direction == "BUY" else \
                   round(current - smart_tp_pips * pip_cache[pair], dec)

        all_candidates.append((-w["FINAL"], w["FINAL"], pair, oanda, direction, current, sl_price, tp_price, dec, smart_tp_pips))

    # Execute Top Candidates
    logger.info(f"🏆 RANKED: {len(all_candidates)} passed → opening top {min(MAX_OPEN, len(all_candidates))}")
    for i, (_, score, pair, _, dir, _, _, _, _, tp_pips) in enumerate(all_candidates, 1):
        logger.info(f"   #{i} — {pair} {dir} SCORE={score:.1f} SMART-TP={tp_pips:.1f}p")

    # ✅ DUPLICATE GUARD: Track instruments THIS run
    executed_in_this_run = set()

    for _, FINAL, pair, oanda, direction, current, sl_price, tp_price, dec, smart_tp_pips in all_candidates:
        # ✅ Double guard: existing position OR already selected THIS run
        if open_pos_by_oanda.get(oanda, False):
            logger.info(f"⏭️ {pair} ({oanda}): position already open — SKIP DUPLICATE")
            continue
        if oanda in executed_in_this_run:
            logger.info(f"⏭️ {pair} ({oanda}): already selected THIS run — SKIP DUPLICATE")
            continue

        # ✅ Execute Trade
        tp_info = f"TP={smart_tp_pips:.1f}p"
        logger.info(f"📤 EXECUTE: {pair} {direction} | SL={sl_price:.{dec}f} | TP={tp_price:.{dec}f} | {tp_info}")
        try:
            lot_size = DEFAULT_LOT_SIZE
            order_result = open_oanda_order(
                api, OANDA_ACCOUNT_ID, oanda,
                direction=direction,
                units=lot_size if direction == "BUY" else -lot_size,
                sl_price=sl_price,
                tp_price=tp_price,
            )
            if order_result.get("status") != "OK":
                raise RuntimeError(order_result.get("message", "OANDA order failed"))
            executed_in_this_run.add(oanda)
            logger.info(f"✅ ORDER OPENED: {pair} {direction} SL={sl_price:.{dec}f} TP={tp_price:.{dec}f}")

            # ✅ Record to cooldown
            last_closed[pair] = (datetime.now(timezone.utc), 2)

        except Exception as e:
            logger.error(f"❌ ORDER FAILED {pair} {direction}: {e}")

    # ─── SAVE COOLDOWN ───────────────────────────────────────────────────
    import json
    with open(COOLDOWN_FILE, "w") as f:
        json.dump({
            k: [v[0].isoformat(), v[1]] for k, v in last_closed.items()
        }, f, indent=2)

    logger.info(f"\n✅ v6.8.5 {PROFILE_LABEL} Run Complete — {ACCOUNT_NAME} | "
                f"FILTERS={'ON' if TREND_FILTER_ENABLED else 'OFF'}")


if __name__ == "__main__":
    main()