#!/usr/bin/env python3
"""
fx_trade_bot_v6.8.6_hardcoded.py — v6.8.6 (ALL DEFAULTS HARD-CODED)
Multi-Profile: Profile2/Account002 · Profile3/Account003
✅ ALL config values hard-coded — independent of profile config files
✅ RSI-FIXED | Consensus | ADX Boost | Monte Carlo | SL Zone Hierarchy
✅ TREND FILTER: M15 EMA40/80 Crossover + Weekly EMA100
✅ SMART TP: Fully unified config — TP_MULT + TP_STRONG_MULT
✅ ATR TRAILING EXIT: Min hold 4 bars + close-only + ratchet
✅ DUPLICATE-ORDER PROTECTION — Instrument + Run guards
✅ MARKET CLOSED = Silent Exit — No Telegram message
✅ Profile3: Trend Filter ON by default | Profile2: Filter OFF

M15 = H1 Equivalent Scaling:
  EMA40 (M15) ≈ EMA10 (H1)
  EMA80 (M15) ≈ EMA20 (H1)
"""

import contextlib
from statistics import mode
import sys
import os
import logging
import argparse
import importlib
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import pandas as pd

# ──────────────────────────────────────────────────────────────────────────────
# 📋 ALL CONFIGURATION — HARD-CODED DEFAULTS (OVERRIDE HERE)
# ──────────────────────────────────────────────────────────────────────────────
class BotDefaults:
    # ─── TREND FILTER ───
    TREND_FILTER_ENABLED_PROFILE2 = False
    TREND_FILTER_ENABLED_PROFILE3 = True
    EMA_PERIOD_FAST = 40
    EMA_PERIOD_SLOW = 80
    WEEKLY_EMA_PERIOD = 100
    EMA100_BUFFER_PIPS = 30

    # ─── TAKE PROFIT ───
    BASE_TP_PIPS = 30
    TP_MULT = 1.0
    TP_STRONG_MULT = 1.0
    MC_STRONG_THRESHOLD = 0.75  # 75%

    # ─── MONTE CARLO ───
    REQUIRE_STRONG_MOMENTUM = False
    MC_BULLISH_THRESHOLD_PCT = 55.0  # %

    # ─── CONSENSUS / VOTING ───
    REQUIRE_DIRECTION_CONSENSUS = True
    CONSENSUS_THRESHOLD = 2  # 2 out of 3 signals
    XGB_BULLISH_THRESHOLD = 0.55  # ≥ 0.55 = BUY

    # ─── SCORE THRESHOLDS ───
    MIN_CONVICTION_SCORE = 30.0
    MIN_CONVICTION_SCORE_ALT = 45.0
    MIN_STRENGTH_GAP = 0.25
    BASE_MIN_EDGE = 0.50
    BASE_MIN_EDGE_ALT = 0.51

    # ─── ADX BOOST ───
    ADX_SCALE_FACTOR = 2.0
    ADX_FLOOR_ENABLED = True
    ADX_MIN_SCORE = 20.0
    ADX_BOOST_ENABLED = True
    ADX_BOOST_THRESHOLD = 30.0
    ADX_BOOST_VALUE = 10.0

    # ─── WEIGHTS (S+R+A+X+M = 1.0) ───
    WEIGHT_STRENGTH = 0.40
    WEIGHT_RSI = 0.15
    WEIGHT_ADX = 0.15
    WEIGHT_XGB = 0.20
    WEIGHT_MC = 0.10

    # ─── POSITION LIMITS ───
    MAX_OPEN_POSITIONS = 4
    DEFAULT_LOT_SIZE = 10000

    # ─── PAIR SELECTION ───
    USE_TOP_PAIRS_ONLY = False
    TOP_PAIRS_COUNT = 4
    TOP_PAIRS_MIN_GAP = 0.25

    # ─── ATR EXIT ───
    ATR_EXIT_MULT = 2.0
    MIN_HOLD_BARS = 4
    USE_DYNAMIC_SL = 1  # 0=H4 only | 1=HYBRID | 2=ATR only
    MAX_SL_PIPS = 200

    # ─── TP BEHAVIOR ───
    TRAILING_TP = False
    DYNAMIC_TP = True
    TP_RAISE_THRESHOLD_PIPS = 15

    # ─── MULTI-TIMEFRAME CONFLUENCE ───
    MULTI_TF_CONFLUENCE = False
    CONFLUENCE_REQUIRED_TFS = 2

    # ─── DEBUG ───
    DEBUG_DETAIL = True
    DEBUG_MODE = False
    REMOVE_COOLDOWN = False

    # ─── STRATEGY MODE ───
    MODE = "LEVEL10"

# ─────────────────── END OF CONFIG — EDIT ABOVE ───────────────────

# ─── PRIMARY IMPORT: config_bot FIRST ───
import config_bot
import config

from utils.trading_core import forex_market_closed
from utils.strategy_helpers import (
    build_strength_matrix,
    format_strength_ranking,
    get_live_prices,
)
from telegram_message import send_telegram_message
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
    get_open_position,
    close_position,
    fetch_candles,
    DynamicPositionManager,
    load_mc_legacy,
    calculate_stop_loss,
)
from fx_trade_bot_mc import MCGenerator, MCConfig
from fx_trade_bot_ml import ensure_model
from config_oanda import api, OANDA_ACCOUNT_ID_2, OANDA_ACCOUNT_ID_3

from utils.logging_utils import get_logger
logger = get_logger(__name__)

# ─── BASE SETUP ──────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
sys.path.extend([str(BASE_DIR), str(BASE_DIR / "utils")])

# ─── TREND HELPERS ──────────────────────────────────────────────────────────
def calculate_ema(series, period):
    """Calculate Exponential Moving Average"""
    return series.ewm(span=period, adjust=False).mean()


def update_oanda_sl(api, account_id, trade_id, new_sl_price):
    """Update StopLoss for an open Trade via OANDA API — TradeCRCDO"""
    from oandapyV20.endpoints.trades import TradeCRCDO
    try:
        data = {
            "stopLoss": {
                "price": f"{new_sl_price:.5f}".rstrip("0").rstrip("."),
                "timeInForce": "GTC",
            }
        }
        resp = api.request(
            TradeCRCDO(accountID=account_id, tradeID=str(trade_id), data=data)
        )
        return {"status": "OK", "response": resp}
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}


def calculate_atr_exit_level(
    entry_price, direction, atr_value, pip_size,
    atr_mult=2.0, min_hold_bars=4, current_bar_index=0, prior_exit_level=None,
):
    """ATR TRAILING EXIT — Min hold + Ratchet logic"""
    if current_bar_index < min_hold_bars:
        return None, "HOLD"

    offset = atr_value * atr_mult
    if direction == "BUY":
        new_exit = entry_price - offset
        if prior_exit_level is not None:
            new_exit = max(new_exit, prior_exit_level)
    else:
        new_exit = entry_price + offset
        if prior_exit_level is not None:
            new_exit = min(new_exit, prior_exit_level)

    return round(new_exit, 5), "TRAILING"


def _pips_to_price(entry, direction, pips, pip_value):
    offset = pips * pip_value
    return entry + offset if direction == "BUY" else entry - offset


def _price_to_pips(entry, tp_price, pip_value):
    return abs(tp_price - entry) / pip_value


def fetch_weekly_ema100(oanda_instrument, api):
    """Fetch Weekly candles and EMA100 for trend filter"""
    try:
        resp = api.request(
            InstrumentsCandles(
                instrument=oanda_instrument,
                params={"granularity": "W", "count": 105, "price": "M"},
            )
        )
        candles = resp.get("candles") or []
        if len(candles) < 100:
            logger.warning(f"⚠️ Weekly EMA100 {oanda_instrument}: insufficient data — bypassed")
            return None

        closes = []
        for c in candles:
            mid = c.get("mid") or {}
            closes.append(float(mid["c"]))
        if len(closes) < 100:
            return None

        series = pd.Series(closes)
        ema100 = float(calculate_ema(series, 100).iloc[-1])
        last_close = float(closes[-1])

        if not np.isfinite(ema100) or ema100 <= 0 or last_close <= 0:
            return None
        if abs(ema100 - last_close) / last_close > 0.25:
            logger.warning(f"⚠️ Weekly EMA100 {oanda_instrument}: implausible — bypassed")
            return None
        return ema100
    except Exception as e:
        logger.warning(f"⚠️ Cannot fetch Weekly EMA100 for {oanda_instrument}: {e}")
        return None


def evaluate_trend_and_tp(
    profile_name, direction, mc_pct_up, entry_price, pip_value, df,
    weekly_ema100, ema_cross_filter, fast_period, slow_period,
    base_tp_pips, mc_strong_threshold, tp_mult, tp_strong_mult,
    ema100_buffer_pips=30, timeframe="15m",
):
    """EMA Crossover + Weekly EMA100 Filter + TP Calculation"""
    current_price = entry_price

    # ─── RULE A: EMA CROSSOVER TREND ALIGNMENT ───
    if ema_cross_filter:
        ema_fast = calculate_ema(df["Close"], fast_period)
        ema_slow = calculate_ema(df["Close"], slow_period)
        fast_val, slow_val = ema_fast.iloc[-1], ema_slow.iloc[-1]

        if direction == "BUY":
            aligned = (current_price > fast_val) and (fast_val > slow_val)
            reason = f"{timeframe} TREND MISALIGNED — Price={current_price:.5f} > EMA{fast_period}={fast_val:.5f} > EMA{slow_period}={slow_val:.5f}"
        else:
            aligned = (current_price < fast_val) and (fast_val < slow_val)
            reason = f"{timeframe} TREND MISALIGNED — Price={current_price:.5f} < EMA{fast_period}={fast_val:.5f} < EMA{slow_period}={slow_val:.5f}"

        if not aligned:
            logger.info(f"⏭️ SKIP {direction}: {reason}")
            return False, 0.0, reason

    # ─── RULE B: Weekly EMA100 Counter-Trend ───
    if weekly_ema100 is not None:
        if direction == "BUY" and current_price < weekly_ema100:
            reason = f"COUNTER-TREND vs WEEKLY EMA100 — Price below {weekly_ema100:.5f}"
            logger.info(f"⏭️ SKIP BUY: {reason}")
            return False, 0.0, reason
        if direction == "SELL" and current_price > weekly_ema100:
            reason = f"COUNTER-TREND vs WEEKLY EMA100 — Price above {weekly_ema100:.5f}"
            logger.info(f"⏭️ SKIP SELL: {reason}")
            return False, 0.0, reason

    # ─── TP CALCULATION ───
    mc_momentum = mc_pct_up / 100.0
    tp_pips = base_tp_pips * tp_strong_mult if mc_momentum >= mc_strong_threshold else base_tp_pips * tp_mult

    # Buffer protection
    if weekly_ema100 is not None and ema_cross_filter:
        if direction == "BUY":
            min_tp_price = weekly_ema100 + ema100_buffer_pips * pip_value
            min_tp_pips = (min_tp_price - current_price) / pip_value
            tp_pips = max(tp_pips, min_tp_pips)
        else:
            max_tp_price = weekly_ema100 - ema100_buffer_pips * pip_value
            min_tp_pips = (current_price - max_tp_price) / pip_value
            tp_pips = max(tp_pips, min_tp_pips)

    return True, tp_pips, f"TP={tp_pips:.1f}p"


# ─── PARSER ──────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="FX Trading Bot v6.8.6 — HARDCODED")
parser.add_argument("--profile2", action="store_true")
parser.add_argument("--profile3", action="store_true")
parser.add_argument("--timeframe", type=str, default="15m", choices=["15m", "1H", "H4"])
parser.add_argument("--trend-filter-enabled", type=str.lower, choices=["true", "false", "1", "0"], default=None)
parser.add_argument("--confluence", action="store_true", default=None)
parser.add_argument("--no-confluence", action="store_false", dest="confluence")
parser.add_argument("--skip-mc", action="store_true")
parser.add_argument("--mc-only", action="store_true")
args = parser.parse_args()

# ─── PROFILE SELECTION ───────────────────────────────────────────────────────
if args.profile3:
    PROFILE_LABEL = "PROFILE3"
    ACCOUNT_NAME = "Account 003"
    OANDA_ACCOUNT_ID = OANDA_ACCOUNT_ID_3
    PROFILE_NAME = "profile3"
    TREND_FILTER_DEFAULT = BotDefaults.TREND_FILTER_ENABLED_PROFILE3
else:
    PROFILE_LABEL = "PROFILE2"
    ACCOUNT_NAME = "Account 002"
    OANDA_ACCOUNT_ID = OANDA_ACCOUNT_ID_2
    PROFILE_NAME = "profile2"
    TREND_FILTER_DEFAULT = BotDefaults.TREND_FILTER_ENABLED_PROFILE2

COOLDOWN_FILE = BASE_DIR / f"cooldown_{PROFILE_NAME}.json"
RESULTS_DIR = BASE_DIR / f"daily_results_{PROFILE_NAME}"
RESULTS_DIR.mkdir(exist_ok=True)

# ─── TREND FILTER OVERRIDE ───────────────────────────────────────────────────
TREND_FILTER_ENABLED = TREND_FILTER_DEFAULT
if args.trend_filter_enabled is not None:
    TREND_FILTER_ENABLED = args.trend_filter_enabled in ("true", "1")
    logger_info_cli = f"🔧 CLI OVERRIDE: TREND_FILTER_ENABLED={TREND_FILTER_ENABLED}"
else:
    logger_info_cli = f"🔍 AUTO: TREND_FILTER_ENABLED={TREND_FILTER_ENABLED} | profile={PROFILE_NAME}"

# ─── CONSOLIDATED CONSTANTS (ALL FROM BotDefaults) ──────────────────────────
base_tp_pips = BotDefaults.BASE_TP_PIPS
mc_strong_threshold = BotDefaults.MC_STRONG_THRESHOLD
ema_period_fast = BotDefaults.EMA_PERIOD_FAST
ema_period_slow = BotDefaults.EMA_PERIOD_SLOW
ema100_buffer_pips = BotDefaults.EMA100_BUFFER_PIPS
tp_mult = BotDefaults.TP_MULT
tp_strong_mult = BotDefaults.TP_STRONG_MULT
ATR_EXIT_MULT = BotDefaults.ATR_EXIT_MULT
MIN_HOLD_BARS = BotDefaults.MIN_HOLD_BARS

REQUIRE_DIRECTION_CONSENSUS = BotDefaults.REQUIRE_DIRECTION_CONSENSUS
CONSENSUS_THRESHOLD = BotDefaults.CONSENSUS_THRESHOLD
XGB_BULLISH_THRESHOLD = BotDefaults.XGB_BULLISH_THRESHOLD
MC_BULLISH_THRESHOLD = BotDefaults.MC_BULLISH_THRESHOLD_PCT
REQUIRE_STRONG_MOMENTUM = BotDefaults.REQUIRE_STRONG_MOMENTUM

ADX_SCALE_FACTOR = BotDefaults.ADX_SCALE_FACTOR
ADX_FLOOR_ENABLED = BotDefaults.ADX_FLOOR_ENABLED
ADX_MIN_SCORE = BotDefaults.ADX_MIN_SCORE
ADX_BOOST_ENABLED = BotDefaults.ADX_BOOST_ENABLED
ADX_BOOST_THRESHOLD = BotDefaults.ADX_BOOST_THRESHOLD
ADX_BOOST_VALUE = BotDefaults.ADX_BOOST_VALUE

W_S = BotDefaults.WEIGHT_STRENGTH
W_R = BotDefaults.WEIGHT_RSI
W_A = BotDefaults.WEIGHT_ADX
W_X = BotDefaults.WEIGHT_XGB
W_M = BotDefaults.WEIGHT_MC

_WEIGHT_SUM = W_S + W_R + W_A + W_X + W_M
if abs(_WEIGHT_SUM - 1.00) > 0.001:
    logger.warning(f"⚠️ Weight sum = {_WEIGHT_SUM:.4f} ≠ 1.00 — normalizing")
    W_S, W_R, W_A, W_X, W_M = [w / _WEIGHT_SUM for w in [W_S, W_R, W_A, W_X, W_M]]

MIN_STRENGTH_GAP = BotDefaults.MIN_STRENGTH_GAP
DEBUG_DETAIL = BotDefaults.DEBUG_DETAIL
USE_TOP_PAIRS_ONLY = BotDefaults.USE_TOP_PAIRS_ONLY
TOP_PAIRS_COUNT = BotDefaults.TOP_PAIRS_COUNT
TOP_PAIRS_MIN_GAP = BotDefaults.TOP_PAIRS_MIN_GAP
DEBUG_MODE = BotDefaults.DEBUG_MODE
MAX_OPEN = BotDefaults.MAX_OPEN_POSITIONS
MAX_SIMULTANEOUS_TRADES = MAX_OPEN
TRAILING_TP = BotDefaults.TRAILING_TP
DYNAMIC_TP = BotDefaults.DYNAMIC_TP
MULTI_TF_CONFLUENCE = BotDefaults.MULTI_TF_CONFLUENCE
CONFLUENCE_REQUIRED_TFS = BotDefaults.CONFLUENCE_REQUIRED_TFS
TP_RAISE_THRESHOLD_PIPS = BotDefaults.TP_RAISE_THRESHOLD_PIPS
MODE = BotDefaults.MODE
TIMEFRAME = args.timeframe
DEFAULT_LOT_SIZE = BotDefaults.DEFAULT_LOT_SIZE
USE_DYNAMIC_SL = BotDefaults.USE_DYNAMIC_SL
MAX_SL_PIPS = BotDefaults.MAX_SL_PIPS
REMOVE_COOLDOWN = BotDefaults.REMOVE_COOLDOWN

min_conv = BotDefaults.MIN_CONVICTION_SCORE if MODE == "LEVEL10" else BotDefaults.MIN_CONVICTION_SCORE_ALT
min_edge = BotDefaults.BASE_MIN_EDGE if MODE == "LEVEL10" else BotDefaults.BASE_MIN_EDGE_ALT

# ─── LOGGING ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(BASE_DIR / f"bot_{PROFILE_NAME}.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)
logger.info(logger_info_cli)
logger.info(f"📈 v6.8.6 TREND: EMA{ema_period_fast}/{ema_period_slow} @ {TIMEFRAME}")
logger.info(f"⚖️  {PROFILE_LABEL} WEIGHTS: S={W_S:.2f} R={W_R:.2f} A={W_A:.2f} X={W_X:.2f} M={W_M:.2f} | SUM=1.00")

# ─── TIMEFRAME & PAIRS ───────────────────────────────────────────────────────
OANDA_GRANULARITY_MAP = {"15m": "M15", "1H": "H1", "H4": "H4", "D": "D"}
OANDA_GRANULARITY = OANDA_GRANULARITY_MAP.get(TIMEFRAME, "H4")
ALL_PAIRS = [
    "EURUSD=X", "GBPUSD=X", "EURJPY=X", "GBPJPY=X", "AUDUSD=X",
    "USDJPY=X", "GBPAUD=X", "USDCHF=X", "AUDJPY=X", "EURGBP=X",
    "NZDUSD=X", "CADJPY=X",
]
YAHOO_TO_OANDA = {
    "EURUSD=X": "EUR_USD", "GBPUSD=X": "GBP_USD", "EURJPY=X": "EUR_JPY",
    "GBPJPY=X": "GBP_JPY", "AUDUSD=X": "AUD_USD", "USDJPY=X": "USD_JPY",
    "GBPAUD=X": "GBP_AUD", "USDCHF=X": "USD_CHF", "AUDJPY=X": "AUD_JPY",
    "EURGBP=X": "EUR_GBP", "NZDUSD=X": "NZD_USD", "CADJPY=X": "CAD_JPY",
}
logger.info(f"✅ Pair mappings loaded: {len(YAHOO_TO_OANDA)} entries")

MC_MAX_AGE_HOURS = 24
SIMULATIONS = 5000
CONFIDENCE = 0.90

# CLI overrides
if args.confluence is not None:
    MULTI_TF_CONFLUENCE = args.confluence

# ─── MC TIMEFRAME ─────────────────────────────────────────────────────────────
if TIMEFRAME in ("H4", "1H", "15m"):
    MCConfig.set_timeframe(TIMEFRAME, {
        "YF_INTERVAL": "4h", "YF_PERIOD_FULL": "30d", "YF_PERIOD_RESAMPLE": "60d",
        "MC_LOOKBACK": 90, "MC_FORECAST": 8, "PERIODS_YEAR": 252 * 6,
        "MC_REPORT_TITLE": f"[{PROFILE_LABEL}] FX {TIMEFRAME} MONTE CARLO",
        "RESULTS_DIR": RESULTS_DIR,
    })
else:
    MCConfig.set_timeframe(TIMEFRAME, {
        "YF_INTERVAL": "1d", "YF_PERIOD_FULL": "120d", "YF_PERIOD_RESAMPLE": "180d",
        "MC_LOOKBACK": 90, "MC_FORECAST": 5, "PERIODS_YEAR": 252,
        "MC_REPORT_TITLE": f"[{PROFILE_LABEL}] FX DAILY MONTE CARLO",
        "RESULTS_DIR": RESULTS_DIR,
    })

# ─── PIPELINE INIT ──────────────────────────────────────────────────────────
FEAT_CFG = FeatureConfig(
    use_atr=True, atr_sl_mult=2.0, atr_tp_mult=3.0,
    use_macd=True, use_rsi=True, use_adx=True,
    model_type="xgboost", target_horizon=6, train_lookback_bars=5000,
)
STRAT_CFG = StrategyConfig(
    mode=MODE, min_conviction_score=min_conv, base_min_edge=min_edge,
    mc_filter_mode=FilterMode.PENALIZE, regime_filter_mode=FilterMode.OFF,
    adx_filter_mode=FilterMode.OFF, pivot_filter_mode=FilterMode.PENALIZE,
    strength_gap_filter_mode=FilterMode.PENALIZE, cooldown_filter_mode=FilterMode.BLOCK,
)

fetcher = DataFetcher(use_oanda=True, oanda_api=api, oanda_granularity=OANDA_GRANULARITY)
feat_engine = FeatureEngine(FEAT_CFG)
strat_engine = StrategyEngine(STRAT_CFG, model=None, feature_list=[])
atr_mod = ATRModule(period=14)
MODEL_PATH = BASE_DIR / "trade_model_xgb.pkl"
model_wrapper = ModelWrapper(FEAT_CFG, model_path=MODEL_PATH)
last_closed = {} if REMOVE_COOLDOWN else load_cooldown(COOLDOWN_FILE, Direction)

# ─── HELPER FUNCTIONS ─────────────────────────────────────────────────────────
def build_top_pairs(strength_scores, all_pairs, top_n=4, min_gap=0.25):
    ranked = sorted(strength_scores.items(), key=lambda x: x[1], reverse=True)
    strongest = [ccy for ccy, _ in ranked[:top_n]]
    weakest = [ccy for ccy, _ in ranked[-top_n:]]
    candidates = []
    for i in range(min(top_n, len(strongest), len(weakest))):
        base, quote = strongest[i], weakest[-(i + 1)]
        if base == quote: continue
        gap = strength_scores[base] - strength_scores[quote]
        if abs(gap) >= min_gap:
            sym = f"{base}{quote}=X" if f"{base}{quote}=X" in all_pairs else f"{quote}{base}=X"
            if sym in all_pairs: candidates.append((sym, abs(gap), base, quote))
    return [p[0] for p in sorted(candidates, key=lambda x: x[1], reverse=True)[:top_n]]

def calc_weighted_score(pair, gap, rsi_val, adx_val, xgb_prob, mc_pct_up):
    MIN_FINAL_SCORE = min_conv
    strength_dir = "BUY" if gap >= MIN_STRENGTH_GAP else "SELL" if gap <= -MIN_STRENGTH_GAP else "NEUTRAL"
    xgb_dir = "BUY" if (xgb_prob or 0.0) >= XGB_BULLISH_THRESHOLD else "SELL"
    mc_dir = "BUY" if (mc_pct_up or 50.0) >= MC_BULLISH_THRESHOLD else "SELL"

    buy_votes = sum(1 for d in (strength_dir, xgb_dir, mc_dir) if d == "BUY")
    sell_votes = sum(1 for d in (strength_dir, xgb_dir, mc_dir) if d == "SELL")
    logger.info(f"🤝 {pair}: Strength={strength_dir} | XGB={xgb_dir} | MC={mc_dir} | BUY={buy_votes}/3")

    if REQUIRE_DIRECTION_CONSENSUS:
        if buy_votes >= CONSENSUS_THRESHOLD: direction = "BUY"; logger.info(f"✅ {pair}: BUY consensus ({buy_votes}/3)")
        elif sell_votes >= CONSENSUS_THRESHOLD: direction = "SELL"; logger.info(f"✅ {pair}: SELL consensus ({sell_votes}/3)")
        else: logger.info(f"⏭️  {pair}: NO CONSENSUS → SKIP"); return None, None
    else:
        direction = "BUY" if gap > 0 else "SELL"

    S = max(0.0, min(100.0, abs(gap) / 3.5 * 100.0))
    rsi = max(0.0, min(100.0, rsi_val))
    R = max(0.0, min(100.0, (50.0 - rsi) * 2.0)) if direction == "BUY" else max(0.0, min(100.0, (rsi - 50.0) * 2.0))
    adx_norm = min(adx_val * ADX_SCALE_FACTOR, 100.0)
    A = max(0.0, min(100.0, max(adx_norm, ADX_MIN_SCORE) if ADX_FLOOR_ENABLED else adx_norm))
    if ADX_BOOST_ENABLED and adx_val >= ADX_BOOST_THRESHOLD: A = min(100.0, A + ADX_BOOST_VALUE)
    X = max(0.0, min(100.0, (xgb_prob or 0.0) * 100.0))
    M = max(0.0, min(100.0, mc_pct_up if mc_pct_up is not None else 50.0))
    FINAL = S * W_S + R * W_R + A * W_A + X * W_X + M * W_M
    return direction, {"S": round(S,1),"R":round(R,1),"A":round(A,1),"X":round(X,1),"M":round(M,1),"FINAL":round(FINAL,1),"PASS":FINAL>=MIN_FINAL_SCORE,"THRESHOLD":round(MIN_FINAL_SCORE,1)}

# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    global model_wrapper, strat_engine
    logger.info(f"\n🤖 RUN v6.8.6 {PROFILE_LABEL} — {ACCOUNT_NAME} | FILTERS={'ON' if TREND_FILTER_ENABLED else 'OFF'} | EMA{ema_period_fast}/{ema_period_slow} @ {TIMEFRAME} | ATR-EXIT ×{ATR_EXIT_MULT} min{MIN_HOLD_BARS}bars | {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} | MAX_OPEN={MAX_OPEN} | MIN_GAP={MIN_STRENGTH_GAP}")
    logger.info(f"🔑 OANDA Account ID: {OANDA_ACCOUNT_ID}")

    if forex_market_closed(): return

    model_wrapper, strat_engine = ensure_model(MODEL_PATH, FEAT_CFG, model_wrapper, strat_engine, fetcher, feat_engine, ALL_PAIRS, YAHOO_TO_OANDA, lambda k,d=None: getattr(BotDefaults,k,getattr(config_bot,k,getattr(config,k,d))))

    logger.info("[STEP 1] Currency Strength...")
    strength_scores = build_strength_matrix()
    logger.info(format_strength_ranking(strength_scores))

    selected_pairs = build_top_pairs(strength_scores, ALL_PAIRS, TOP_PAIRS_COUNT, TOP_PAIRS_MIN_GAP) if USE_TOP_PAIRS_ONLY else ALL_PAIRS[:]
    logger.info(f"📋 SCAN ALL: {len(selected_pairs)} pairs")

    pip_cache = {YAHOO_TO_OANDA[p]: pip_size(p) for p in selected_pairs if p in YAHOO_TO_OANDA}
    for o,ps in pip_cache.items(): logger.info(f"🔧 PIP_SIZE {o} = {ps}")

    pair_data, weekly_ema_cache = {}, {}
    for pair in selected_pairs:
        oanda = YAHOO_TO_OANDA.get(pair)
        if not oanda: continue
        try:
            raw = fetcher.fetch(pair, oanda, count=200)
            if raw.empty: continue
            df = feat_engine.build(raw).replace([np.inf,-np.inf],np.nan).ffill().bfill().fillna(0)
            if len(df)<5: continue
            pair_data[pair] = {"df":df,"oanda":oanda,"raw":raw,"atr":df.iloc[-1].get("atr",0.0),"rsi":df.iloc[-1].get("rsi",50.0),"adx":df.iloc[-1].get("adx",-1.0)}
            logger.info(f"📊 {pair}: {len(df)} bars | ATR={pair_data[pair]['atr']:.6f} | RSI={pair_data[pair]['rsi']:.1f} | ADX={pair_data[pair]['adx']:.1f}")
            weekly_ema_cache[oanda] = fetch_weekly_ema100(oanda, api)
        except Exception as e: logger.error(f"❌ Fetch failed {pair}: {e}")
    if not pair_data: return

    # Step 3 — MC
    mc_cache = {}
    if not args.skip_mc:
        logger.info("[STEP 3] Monte Carlo Forecasts...")
        mc_gen = MCGenerator(fetcher, YAHOO_TO_OANDA, simulations=SIMULATIONS, confidence=CONFIDENCE)
        for pair in selected_pairs:
            if pair not in pair_data: continue
            mc_data, ok = mc_gen.run_for_pair(pair, df=pair_data[pair]["raw"])
            if ok:
                regime = mc_data.get("regime","")
                if REQUIRE_STRONG_MOMENTUM and "STRONG MOMENTUM" not in regime:
                    logger.info(f"⏭️ {pair}: MC regime={regime} — SKIP"); continue
                mc_cache[pair] = mc_data
                logger.info(f"🎲 MC {pair}: {regime} | Band {mc_data['range_90']} | P_UP={mc_data['p_up']}%")
    if args.mc_only: return

    # Step 4 — Confluence
    tf_confluence = {}
    if MULTI_TF_CONFLUENCE:
        logger.info("[STEP 4] Multi-Timeframe Confluence...")
        for pair in selected_pairs:
            if pair not in pair_data: continue
            dirs = []
            for gran in {"H4":"H4","1H":"H1","15m":"M15"}.values():
                with contextlib.suppress(Exception):
                    raw_tf = fetch_candles(api, pair_data[pair]["oanda"], gran, count=200)
                    if len(raw_tf)>=5: dirs.append(strat_engine.generate_signal(pair,pair_data[pair]["oanda"],feat_engine.build(raw_tf),None,strength_scores,raw_tf.iloc[-1]["Close"],1.0,None).action)
            buy_c, sell_c = dirs.count("BUY"), dirs.count("SELL")
            passes = buy_c>=CONFLUENCE_REQUIRED_TFS or sell_c>=CONFLUENCE_REQUIRED_TFS
            tf_confluence[pair] = {"buy":buy_c,"sell":sell_c,"passes":passes}
            logger.info(f"🔗 CONFLUENCE {pair}: BUY={buy_c} SELL={sell_c} → {'✅ PASS' if passes else '❌ BLOCK'}")

    # Step 5 — Exit Manager
    logger.info("[STEP 5] Dynamic Exit Manager...")
    dyn_mgr = DynamicPositionManager(api, OANDA_ACCOUNT_ID, TIMEFRAME, 1.5, 2.5, 1.5, 12, dynamic_tp=DYNAMIC_TP, tp_raise_thresh_pips=TP_RAISE_THRESHOLD_PIPS, telegram_send=send_telegram_message)
    oanda_level = logging.getLogger("oandapyV20").level
    logging.getLogger("oandapyV20").setLevel(logging.CRITICAL)
    dyn_mgr.update_all(pair_data, lambda i: close_position(api, OANDA_ACCOUNT_ID, i, send_telegram_message))
    logging.getLogger("oandapyV20").setLevel(oanda_level)

    # Step 6 — Open Positions
    open_pos_by_oanda, open_pos_count = {}, 0
    logger.info("🔍 Checking open positions...")
    for pair in selected_pairs:
        oanda = YAHOO_TO_OANDA.get(pair)
        if not oanda: continue
        is_open = get_open_position(api, OANDA_ACCOUNT_ID, oanda) is not None
        open_pos_by_oanda[oanda] = is_open
        if is_open: open_pos_count += 1
    open_list = [o.replace("_","/") for o,s in open_pos_by_oanda.items() if s]
    ready_list = [p.replace("=X","") for p in selected_pairs if not open_pos_by_oanda.get(YAHOO_TO_OANDA.get(p),False)]
    logger.info(f"📊 Open positions: {open_pos_count}/{MAX_OPEN} | OPEN: {', '.join(open_list) or 'None'} | READY: {', '.join(ready_list) or 'None'}")

    # ─── EVALUATE & EXECUTE ──────────────────────────────────────────────
    all_candidates = []
    executed_in_this_run = set()

    for pair in selected_pairs:
        if pair not in pair_data or pair not in mc_cache: continue
        df = pair_data[pair]["df"]
        oanda_sym = pair_data[pair]["oanda"]
        current = float(df.iloc[-1]["Close"])
        rsi_val = pair_data[pair]["rsi"]
        adx_val = pair_data[pair]["adx"]
        mc_data = mc_cache[pair]
        mc_pct_up = mc_data["p_up"]
        xgb_prob = mc_data.get("xgb_prob", 0.5)
        gap = strength_scores.get(pair[:3], 0) - strength_scores.get(pair[3:] if len(pair)>6 else "USD", 0)

        direction, scores = calc_weighted_score(pair, gap, rsi_val, adx_val, xgb_prob, mc_pct_up)
        if direction is None: continue
        if not scores["PASS"]:
            logger.info(f"⏭️ {pair}: SCORE={scores['FINAL']:.1f} < {scores['THRESHOLD']} → SKIP"); continue

        # Trend + TP
        weekly_ema100 = weekly_ema_cache.get(oanda_sym) if TREND_FILTER_ENABLED else None
        allow_entry, tp_pips, tp_info = evaluate_trend_and_tp(
            PROFILE_NAME, direction, mc_pct_up, current, pip_cache[oanda_sym], df,
            weekly_ema100, TREND_FILTER_ENABLED, ema_period_fast, ema_period_slow,
            base_tp_pips, mc_strong_threshold, tp_mult, tp_strong_mult, ema100_buffer_pips, TIMEFRAME
        )
        if not allow_entry: continue

        # SL Calc
        try:
            h4_df = fetch_candles(api, oanda_sym, "H4", count=15)
            h4_closed = [{"high":float(r["High"]),"low":float(r["Low"])} for _,r in h4_df.iloc[:-1].iterrows()] if h4_df is not None and len(h4_df)>=5 else None
            if not h4_closed or len(h4_closed)<4:
                logger.info(f"⏭️ {pair}: insufficient H4 data for SL → SKIP"); continue
            sl_price, sl_pips, skip = calculate_stop_loss(direction, current, h4_closed, pip_cache[oanda_sym])
            if skip or sl_pips > MAX_SL_PIPS:
                logger.info(f"⏭️ {pair}: SL={sl_pips:.1f}p > {MAX_SL_PIPS}p cap → SKIP"); continue
        except Exception as e: logger.info(f"⏭️ {pair}: SL calc failed → SKIP ({e})"); continue

        decimals = 3 if "JPY" in oanda_sym else 5
        tp_price = _pips_to_price(current, direction, tp_pips, pip_cache[oanda_sym])
        FINAL = scores["FINAL"]
        all_candidates.append((-FINAL, True, pair, oanda_sym, direction, current, round(sl_price,decimals), round(tp_price,decimals), decimals, tp_info))

    # ─── EXECUTE ──────────────────────────────────────────────────────────
    all_candidates.sort()
    for _, FINAL, pair, oanda, direction, current, sl_price, tp_price, dec, _ in all_candidates:
        if open_pos_by_oanda.get(oanda, False):
            logger.info(f"⏭️ {pair} ({oanda}): position already open — SKIP DUPLICATE"); continue
        if oanda in executed_in_this_run:
            logger.info(f"⏭️ {pair} ({oanda}): already selected THIS run — SKIP DUPLICATE"); continue
        if len(executed_in_this_run) >= MAX_OPEN:
            logger.info(f"⏭️ {pair}: MAX_OPEN={MAX_OPEN} reached — SKIP"); continue

        logger.info(f"📤 EXECUTE: {pair} {direction} | SL={sl_price:.{dec}f} | TP={tp_price:.{dec}f}")
        try:
            from fx_trade_bot_utils import open_oanda_order_simple as open_oanda_order
            open_oanda_order(api, OANDA_ACCOUNT_ID, oanda, direction, DEFAULT_LOT_SIZE, sl_price, tp_price)
            executed_in_this_run.add(oanda)
            logger.info(f"✅ ORDER OPENED: {pair} {direction}")
        except Exception as e:
            logger.error(f"❌ FAILED to open {pair}: {e}")

    # ─── SAVE COOLDOWN ───────────────────────────────────────────────────
    import json
    with open(COOLDOWN_FILE, "w") as f:
        json.dump({k: [v[0].isoformat(), v[1]] for k,v in last_closed.items()}, f, indent=2)

    logger.info(f"\n✅ v6.8.6 {PROFILE_LABEL} Run Complete — {ACCOUNT_NAME} | FILTERS={'ON' if TREND_FILTER_ENABLED else 'OFF'}")

if __name__ == "__main__":
    main()