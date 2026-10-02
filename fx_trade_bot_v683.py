#!/usr/bin/env python3
"""
    fx_trade_bot_v6.8.3.3.py — v6.8.3.3 + Top-N Strength Filter
    Multi-Profile: Profile2/Account002 · Profile3/Account003
    ✅ RSI-FIXED | Consensus | ADX Boost | Monte Carlo | SL Zone Hierarchy
    ✅ TREND FILTER: H1 EMA10 Slope + Weekly EMA100 Counter-Trend Block
    ✅ SMART TP: Profile2=×1.0/×2.0 @75%MC  |  Profile3=Fixed ×1.2
    ✅ TOP-N STRENGTH: strongest 3 × weakest 3 → candidate pairs only
"""
import contextlib
import sys
import os
import logging
import argparse
import importlib
from pathlib import Path
from datetime import datetime, timezone

# ─── BASE SETUP ──────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
sys.path.extend([str(BASE_DIR), str(BASE_DIR / "utils")])

# ─── FULL ARGPARSE FIRST (so --help exits before any config import) ──────────
parser = argparse.ArgumentParser(
    description="FX Trading Bot v6.8.3.3 | TREND+TP+TOP-N"
)
parser.add_argument("-a", "--account", "--profile", type=str, default=None,
                    help="Account/profile: '2'/'profile2' or '3'/'profile3' (default: profile2)")
parser.add_argument("--profile2", action="store_true",
                    help="Force Profile2 / Account 002 (shorthand for -a 2)")
parser.add_argument("--profile3", action="store_true",
                    help="Force Profile3 / Account 003 (shorthand for -a 3)")
parser.add_argument("--timeframe", type=str, default="15m", choices=["15m", "1H", "H4"])
parser.add_argument("--confluence", action="store_true", default=None)
parser.add_argument("--no-confluence", action="store_false", dest="confluence")
parser.add_argument("--skip-mc", action="store_true")
parser.add_argument("--mc-only", action="store_true")
parser.add_argument("--live", action="store_true",
                    help="Actually execute trades. Default is DRY-RUN (signals logged, no orders sent).")
parser.add_argument("--dry-run", action="store_true",
                    help="Explicit dry-run — no orders sent to OANDA (this is the default).")
parser.add_argument("-p", "--max-entries", type=int, default=None,
                    help="Max signals to enter per cycle; 1=top only, 2+=basket (overrides MAX_OPEN_POSITIONS)")
parser.add_argument("--lots", type=int, default=None,
                    help="Override lot size / units per trade (overrides DEFAULT_LOT_SIZE from config)")
args = parser.parse_args()

# ─── PROFILE SELECTION ────────────────────────────────────────────────────────
if args.profile3 or (args.account and args.account.lower() in ("3", "profile3", "account003", "003")):
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

# ─── NOW import config (delayed so --help works first) ───────────────────────
import numpy as np
import pandas as pd
import config_bot
import config
from utils.trading_core import forex_market_closed
from utils.strategy_helpers import (
    build_strength_matrix,
    format_strength_ranking,
    get_live_prices,
)
from utils.strategy_config import (
    CURRENCIES,
    USE_TOP_PAIRS_ONLY as STRATEGY_USE_TOP_PAIRS_ONLY,
    TOP_N_CURRENCIES as STRATEGY_TOP_N_CURRENCIES,
    TOP_PAIRS_MIN_GAP as STRATEGY_TOP_PAIRS_MIN_GAP,
    MIN_STRENGTH_GAP as STRATEGY_MIN_STRENGTH_GAP,
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
    open_oanda_order_simple as open_oanda_order,
    DynamicPositionManager,
    load_mc_legacy,
    PositionStatus,
)
from fx_trade_bot_mc import MCGenerator, MCConfig
from fx_trade_bot_ml import ensure_model
from portfolio_balance import balance_from_config
from sl_zone_hierarchy import compute_sl_zone
from config_oanda import api, get_oanda_profile, OANDA_ACCOUNT_ID_2_LIVE, OANDA_ACCOUNT_ID_3_LIVE

# ─── TREND FILTER + SMART TP CONFIGURATION ──────────────────────────────────
_TREND_TP_CONFIG = {
    "base_tp_pips": 30,
    "mc_strong_threshold": 0.75,
    "weekly_ema_period": 100,
    "ema100_buffer_pips": 30,
    "profile2": {
        "tp_normal_mult": 1.0,
        "tp_strong_mult": 2.0,
        "ema_period": 10,
        "slope_lookback": 5,
        "min_slope": 0.001,
    },
    "profile3": {
        "tp_mult": 1.2,
        "ema_period": 10,
        "slope_lookback": 5,
        # Widened from 0.001 to 0.0003. Three separate live runs showed this
        # relaxation changed nothing (the blocked candidates failed the price
        # leg, not the slope one), so it is currently unproven either way.
        #
        # Tightening ladder — widen first, tighten only on evidence. To advance
        # a rung, edit ONLY `min_slope_rung` below (profile config also works);
        # no code change is needed. Guardrails live in resolve_min_slope().
        # Advance only when SLOPE_DIAG rows with would_flip=True have
        # accumulated (target >= 20) AND those signals' outcomes are known.
        # Never advance on elapsed time alone: with would_flip rows near zero
        # there is no statistical basis for the change either way.
        "min_slope_rung": 0.0003,
    },
}

# Tightening-ladder rungs, widest first. The last entry is the original,
# strictest value, so completing the ladder is equivalent to reverting the
# relaxation. Any value outside this list is refused by resolve_min_slope().
MIN_SLOPE_LADDER = (0.0003, 0.0005, 0.0007, 0.001)


def resolve_min_slope(profile_cfg, profile_name):
    """Resolve the active min_slope rung for a profile, with guardrails.

    Precedence: `min_slope_rung` (the ladder knob) → legacy `min_slope`.
    A rung outside MIN_SLOPE_LADDER is refused rather than silently accepted,
    so a typo cannot widen the filter beyond the agreed floor.
    """
    rung = profile_cfg.get("min_slope_rung")
    if rung is None:
        return profile_cfg["min_slope"]
    if rung not in MIN_SLOPE_LADDER:
        logger.warning(
            f"⚠️ {profile_name}: min_slope_rung={rung} is not a ladder rung "
            f"{MIN_SLOPE_LADDER} — using {MIN_SLOPE_LADDER[-1]} instead"
        )
        return MIN_SLOPE_LADDER[-1]
    return rung

# Tightening-ladder baseline: the original, strictest min_slope value.
# SLOPE_DIAG uses it to decide whether a candidate's outcome changed because of
# the relaxation:
#   |slope| < SLOPE_DIAG_BASELINE and |slope| >= current min_slope
#   → exactly the candidates the relaxation let through.
# It is an absolute magnitude and does not track any profile's min_slope, so
# each rung of the ladder (0.0003 -> 0.0005 -> 0.0007 -> 0.001) needs no edit
# here.
SLOPE_DIAG_BASELINE = 0.001


# ─── TREND HELPERS ──────────────────────────────────────────────────────────
def calculate_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()


def calculate_ema_slope(ema_series, lookback_bars):
    ema_now = ema_series.iloc[-1]
    ema_prev = ema_series.iloc[-lookback_bars]
    slope_pct = (ema_now - ema_prev) / ema_prev
    return slope_pct, ema_now


def _pips_to_price(entry, direction, pips, pip_value):
    offset = pips * pip_value
    return entry + offset if direction == "BUY" else entry - offset


def _price_to_pips(entry, tp_price, pip_value):
    return abs(tp_price - entry) / pip_value


def fetch_weekly_ema100(oanda_instrument, api):
    try:
        resp = api.request(
            InstrumentsCandles(
                instrument=oanda_instrument,
                params={"granularity": "W", "count": 105, "price": "M"},
            )
        )
        candles = resp["candles"]
        if len(candles) < 100:
            return None
        closes = [float(c["mid"]["c"]) for c in candles]
        series = pd.Series(closes)
        return calculate_ema(series, 100).iloc[-1]
    except Exception as e:
        logger.warning(f"⚠️ Cannot fetch Weekly EMA100 for {oanda_instrument}: {e}")
        return None


# ─── D-TIMEFRAME DIRECTION GATE (D-Gate) ────────────────────────────────────
# Locks each currency pair into a LONG / SHORT / BOTH bias based on the daily
# (Timeframe "D") EMA20 × EMA50 cross. Prevents the 15m engine from flip-flopping
# between BUY/SELL on the same pair within hours.
#
# Design (answers = A/A/A per user spec):
#   A1: EMA_FAST=20, EMA_SLOW=50 on daily closes
#   A2: Flip confirmation: 2 consecutive daily closes past cross (min_buffer_pct
#       = 0.2% gap between EMAs on flip bar) → prevents 1-day whipsaws
#   A3: All pairs evaluate their OWN D-EMA cross (simple, no DXY synthetic).
#       USD-quote pairs naturally vote the same direction, so USD exposure is
#       implicitly one-sided; JPY crosses are independent.
#   SHADOW mode (default True): emit a DIAG line but DO NOT block. Use for
#   Phase-0 evidence collection (>= 20 rows with would_block=True required
#   before advancing to ENFORCED).
D_GATE_LONG = "LONG"
D_GATE_SHORT = "SHORT"
D_GATE_BOTH = "BOTH"  # EMA within buffer or insufficient bars → no gate


def d_gate_compute_direction(
    daily_closes: pd.Series,
    ema_fast_period: int = 20,
    ema_slow_period: int = 50,
    confirm_bars: int = 2,
    min_buffer_pct: float = 0.002,
) -> str:
    """Return LONG/SHORT/BOTH from a series of daily-close prices.

    Flip rule: bias is persistent. To switch from the previous direction (if
    known) we need `confirm_bars` consecutive closes where
        (ema_fast - ema_slow) / ema_slow  has the SAME sign and absolute
        magnitude >= min_buffer_pct.
    For the first call (no prior) we relax to 1 confirmed bar so the gate
    still takes effect without waiting 2 days.
    """
    n = len(daily_closes)
    need = max(ema_slow_period + confirm_bars, 52)
    if n < need:
        return D_GATE_BOTH

    ema_fast = calculate_ema(daily_closes, ema_fast_period)
    ema_slow = calculate_ema(daily_closes, ema_slow_period)
    diff_pct = (ema_fast - ema_slow) / ema_slow.replace(0.0, np.nan)

    signals = []
    for i in range(-confirm_bars, 0):
        d = diff_pct.iloc[i]
        if pd.isna(d):
            return D_GATE_BOTH
        if d >= min_buffer_pct:
            signals.append(+1)
        elif d <= -min_buffer_pct:
            signals.append(-1)
        else:
            signals.append(0)

    all_pos = all(s == +1 for s in signals)
    all_neg = all(s == -1 for s in signals)
    any_pos = any(s == +1 for s in signals)
    any_neg = any(s == -1 for s in signals)

    one_bar_ok = signals[-1] == +1 or signals[-1] == -1
    if not one_bar_ok:
        return D_GATE_BOTH

    if confirm_bars == 1:
        return D_GATE_LONG if signals[-1] == +1 else D_GATE_SHORT

    if all_pos:
        return D_GATE_LONG
    if all_neg:
        return D_GATE_SHORT
    if any_pos and not any_neg:
        if confirm_bars >= 2 and signals[-1] == +1 and signals[-2] == +1:
            return D_GATE_LONG
        return D_GATE_BOTH
    if any_neg and not any_pos:
        if confirm_bars >= 2 and signals[-1] == -1 and signals[-2] == -1:
            return D_GATE_SHORT
        return D_GATE_BOTH
    return D_GATE_BOTH


def d_gate_fetch_daily(fetcher, pair: str, oanda: str, count: int = 150):
    """Fetch daily candles for a pair via the existing fetcher (reuses yfinance
    session already authenticated). Falls back safely to BOTH on failure."""
    try:
        raw = fetcher.fetch(pair, oanda, count=count, granularity="1d")
        if raw is None or raw.empty:
            return None
        closes = raw["Close"].dropna()
        if len(closes) < 55:
            return None
        return closes.reset_index(drop=True)
    except Exception:
        try:
            raw2 = fetcher.fetch(pair, oanda, count=count)
            if raw2 is None or raw2.empty:
                return None
            closes2 = raw2["Close"].dropna()
            return closes2.reset_index(drop=True) if len(closes2) >= 55 else None
        except Exception as e2:
            logger.info(f"ℹ️  D-Gate daily fetch fallthrough {pair}: {e2}")
            return None


def d_gate_allows(pair_direction: str, trade_direction: str) -> bool:
    """True iff the trade direction is allowed by this pair's D-gate bias."""
    if pair_direction == D_GATE_BOTH:
        return True
    if pair_direction == D_GATE_LONG:
        return trade_direction == "BUY"
    if pair_direction == D_GATE_SHORT:
        return trade_direction == "SELL"
    return True


def resolve_weekly_ema100(cached_ema, filter_enabled):
    """Return the Weekly EMA100 level to filter on, or None to skip that filter.

    Replaces a short-circuit `cached_ema and filter_enabled` gate, which
    returned the *boolean* `filter_enabled` instead of the cached level
    whenever the cache was populated — so the filter silently compared
    prices against `True` (== 1.0) rather than the real EMA100 level.
    """
    if not filter_enabled:
        return None
    return cached_ema


def evaluate_trend_and_tp(
    profile_name,
    direction,
    mc_pct_up,
    entry_price,
    pip_value,
    df_h1,
    weekly_ema100,
    timeframe="H1",
):
    cfg = TREND_TP_CONFIG[profile_name]
    base_pips = TREND_TP_CONFIG["base_tp_pips"]
    mc_momentum = mc_pct_up / 100.0
    ema_cross_filter = cfg_bot("TREND_FILTER_ENABLED", False)
    logger.info(
        f"🔍 {timeframe} TREND FILTER: ema_cross_filter={ema_cross_filter} | profile={profile_name}"
    )

    ema10 = calculate_ema(df_h1["Close"], cfg["ema_period"])
    slope, ema_level = calculate_ema_slope(ema10, cfg["slope_lookback"])
    min_slope = resolve_min_slope(cfg, profile_name)
    current_price = entry_price

    if SLOPE_DIAG:
        # Mirror the filter's own branch so the diagnostic reports the real
        # decision, not a proxy. The previous version only compared |slope|
        # against a band, omitting the price condition entirely — so a candidate
        # blocked purely by price (e.g. slope=+0.000092 with "Price above EMA10")
        # was reported as a slope-sensitive sample and skewed the tuning data.
        if direction == "BUY":
            price_ok = current_price > ema_level
            # >= and <= mirror the filter's own comparisons exactly; strict >/<
            # would disagree with it on a slope exactly equal to the threshold.
            slope_ok_loose = slope >= min_slope
            slope_ok_strict = slope >= SLOPE_DIAG_BASELINE
            cmp_loose, cmp_strict = "<=", "<="
        else:
            price_ok = current_price < ema_level
            slope_ok_loose = slope <= -min_slope
            slope_ok_strict = slope <= -SLOPE_DIAG_BASELINE
            cmp_loose, cmp_strict = ">=", ">="
        # Orthogonal flags on purpose:
        #   sensitive   — the relaxation alone changes the SLOPE verdict
        #                 (migrated from the band check, now exact and not
        #                 masked by the price condition, so the slope
        #                 distribution of every candidate stays measurable)
        #   would_flip  — the candidate only passes because of the relaxation
        #                 (price gate satisfied AND slope in the widened band).
        #                 These are the exact rows the tightening ladder needs.
        sensitive = slope_ok_loose and not slope_ok_strict
        would_flip = price_ok and sensitive
        logger.info(
            f"📊 SLOPE DIAG: profile={profile_name} dir={direction} tf={timeframe} "
            f"slope={slope:.6f} min_slope={min_slope:.6f} "
            f"price_ok={price_ok} "
            f"loose({-min_slope:.6f}{cmp_loose})={slope_ok_loose} "
            f"strict({-SLOPE_DIAG_BASELINE:.6f}{cmp_strict})={slope_ok_strict} "
            f"sensitive={sensitive} would_flip={would_flip}"
        )

    if ema_cross_filter:
        if direction == "BUY":
            filter_slope = slope >= min_slope
            if not (current_price > ema_level and filter_slope):
                reason = f"{timeframe} TREND MISALIGNED — Price below EMA10 or slope={slope:.6f} < {min_slope}"
                logger.info(f"⏭️ SKIP BUY: {reason}")
                return False, 0.0, reason
        else:
            filter_slope = slope <= -min_slope
            if not (current_price < ema_level and filter_slope):
                reason = f"{timeframe} TREND MISALIGNED — Price above EMA10 or slope={slope:.6f} > {-min_slope}"
                logger.info(f"⏭️ SKIP SELL: {reason}")
                return False, 0.0, reason

    if weekly_ema100:
        if direction == "BUY" and current_price < weekly_ema100:
            reason = f"COUNTER-TREND vs WEEKLY EMA100 — Price below {weekly_ema100:.5f}"
            logger.info(f"⏭️ SKIP BUY: {reason}")
            return False, 0.0, reason
        if direction == "SELL" and current_price > weekly_ema100:
            reason = f"COUNTER-TREND vs WEEKLY EMA100 — Price above {weekly_ema100:.5f}"
            logger.info(f"⏭️ SKIP SELL: {reason}")
            return False, 0.0, reason

    if profile_name == "profile2":
        if mc_momentum >= TREND_TP_CONFIG["mc_strong_threshold"]:
            tp_pips = base_pips * cfg["tp_strong_mult"]
            tp_mode = f"✅ STRONG MOMENTUM ×2 — MC={mc_pct_up:.1f}% → TP={tp_pips:.1f}p"
        else:
            tp_pips = base_pips * cfg["tp_normal_mult"]
            tp_mode = f"✅ NORMAL ×1 — MC={mc_pct_up:.1f}% → TP={tp_pips:.1f}p"
    else:
        tp_pips = base_pips * cfg["tp_mult"]
        tp_mode = f"✅ FIXED ×{cfg['tp_mult']} — TP={tp_pips:.1f}p"

    if weekly_ema100:
        tp_price = _pips_to_price(entry_price, direction, tp_pips, pip_value)
        buffer_dist = TREND_TP_CONFIG["ema100_buffer_pips"] * pip_value
        if abs(tp_price - weekly_ema100) < buffer_dist:
            if direction == "BUY":
                tp_price = weekly_ema100 + buffer_dist
            else:
                tp_price = weekly_ema100 - buffer_dist
            tp_pips = _price_to_pips(entry_price, tp_price, pip_value)
            tp_mode += f" | 📌 TP shifted away from Weekly EMA100 → {tp_pips:.1f}p"

    logger.info(tp_mode)
    return True, round(tp_pips, 1), tp_mode


# ─── PROFILE MODULE LOAD ─────────────────────────────────────────────────────
profile_cfg = importlib.import_module(PROFILE_MODULE)
OANDA_ACCOUNT_ID = getattr(profile_cfg, "OANDA_ACCOUNT_ID", None)
if not OANDA_ACCOUNT_ID:
    raise RuntimeError(f"OANDA_ACCOUNT_ID not found in {PROFILE_MODULE}")


def cfg_bot(name, default):
    return getattr(
        profile_cfg, name, getattr(config_bot, name, getattr(config, name, default))
    )


def cfg(name, default):
    return getattr(config, name, default)


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

# ─── CONSOLIDATED STRATEGY CONSTANTS ─────────────────────────────────────────
TREND_TP_CONFIG = cfg("TREND_TP_CONFIG", _TREND_TP_CONFIG)
ACTIVE_MIN_SLOPE = resolve_min_slope(TREND_TP_CONFIG.get(PROFILE_NAME, {}), PROFILE_NAME)
logger.info(
    f"🪜 MIN_SLOPE LADDER: active rung={ACTIVE_MIN_SLOPE} "
    f"(ladder {MIN_SLOPE_LADDER}, widest first; last entry = original strictest)"
)
# ─── D-Gate CONFIG (resolved at import, directions computed per-run in main)
D_GATE_ENABLED = cfg_bot("D_GATE_ENABLED", False)
D_GATE_SHADOW = cfg_bot("D_GATE_SHADOW", True)  # Phase 0: log-only by default
D_GATE_EMA_FAST = cfg_bot("D_GATE_EMA_FAST", 20)
D_GATE_EMA_SLOW = cfg_bot("D_GATE_EMA_SLOW", 50)
D_GATE_CONFIRM_BARS = cfg_bot("D_GATE_CONFIRM_BARS", 2)
D_GATE_MIN_BUFFER_PCT = cfg_bot("D_GATE_MIN_BUFFER_PCT", 0.002)
D_GATE_DIRECTIONS: dict[str, str] = {}  # populated in main(), keyed by yahoo pair
if D_GATE_ENABLED:
    mode = "SHADOW (log-only)" if D_GATE_SHADOW else "ENFORCED (real blocking)"
    logger.info(
        f"🧭 D-GATE: {mode} | EMA{D_GATE_EMA_FAST}×EMA{D_GATE_EMA_SLOW} | "
        f"confirm={D_GATE_CONFIRM_BARS}D | buffer={D_GATE_MIN_BUFFER_PCT*100:.2f}%"
    )
else:
    logger.info("ℹ️  D-GATE: disabled (D_GATE_ENABLED=False)")
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
logger.info(
    f"⚖️  {PROFILE_LABEL} WEIGHTS: S={W_S:.2f} R={W_R:.2f} A={W_A:.2f} X={W_X:.2f} M={W_M:.2f}"
)

# ===== TOP-N STRENGTH — CONFIG-RESOLVED =====
# Resolution order per key: active profile module → config (via cfg_bot) →
# utils/strategy_config (authoritative) → explicit default.
#
# config_bot's own values are legacy and must NOT win over strategy_config:
#   config_bot.py: USE_TOP_PAIRS_ONLY = False, TOP_PAIRS_MIN_GAP = 1.5
# If those won, every run would fall back to "📋 MODE: Full scan — 8 pairs".
# A profile module can still override either key deliberately, because the
# profile module is consulted first.
#
# NOTE: TOP_N_CURRENCIES is the only key read here. The TOP_PAIRS_COUNT fallback
# was removed when the v6.8.x bots that read it were retired — do NOT fall back
# to it, because config_bot.py still defines TOP_PAIRS_COUNT = 5 and that value
# would silently become this bot's default.
USE_TOP_PAIRS_ONLY = cfg_bot("USE_TOP_PAIRS_ONLY", STRATEGY_USE_TOP_PAIRS_ONLY)
TOP_N_CURRENCIES = cfg_bot("TOP_N_CURRENCIES", STRATEGY_TOP_N_CURRENCIES)
# Legacy alias kept for this file's own log lines/history.
TOP_PAIRS_COUNT = TOP_N_CURRENCIES
TOP_PAIRS_MIN_GAP = cfg_bot("TOP_PAIRS_MIN_GAP", STRATEGY_TOP_PAIRS_MIN_GAP)
MIN_STRENGTH_GAP = cfg_bot("MIN_STRENGTH_GAP", STRATEGY_MIN_STRENGTH_GAP)
# ===========================================================
DEBUG_MODE = cfg_bot("DEBUG_MODE", False)
# 独立的斜率诊断开关：不挂在 DEBUG_MODE 上，避免为了拿 slope 分布
# 而连带把 oandapyV20 的 HTTP 日志放出来污染日志文件。
SLOPE_DIAG = cfg_bot("SLOPE_DIAG", False)
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
if args.live and args.dry_run:
    logger.warning("⚠️  Both --live and --dry-run given — --live wins, running LIVE")
LIVE_MODE = args.live
if args.live:
    _live = get_oanda_profile("live")
    api = _live["api"]
    OANDA_ACCOUNT_ID = OANDA_ACCOUNT_ID_3_LIVE if PROFILE_NAME == "profile3" else OANDA_ACCOUNT_ID_2_LIVE
    logger.info(f"🔴 LIVE ENVIRONMENT | Account: {OANDA_ACCOUNT_ID}")
MAX_ENTRIES = args.max_entries
OANDA_GRANULARITY_MAP = {"15m": "M15", "1H": "H1", "H4": "H4", "D": "D"}
OANDA_GRANULARITY = OANDA_GRANULARITY_MAP.get(TIMEFRAME, "H4")
DEFAULT_LOT_SIZE = cfg_bot("DEFAULT_LOT_SIZE", 10000)
if args.lots is not None:
    DEFAULT_LOT_SIZE = args.lots

_run_mode_label = "LIVE (real orders)" if LIVE_MODE else "DRY-RUN (no orders sent)"
_max_entries_label = f"{MAX_ENTRIES}" if MAX_ENTRIES else "unlimited (within MAX_OPEN)"
logger.info(
    f"🖥️  RUN MODE: {_run_mode_label} | MAX_OPEN={MAX_OPEN} | "
    f"MAX_ENTRIES_THIS_RUN={_max_entries_label}"
)

ALL_PAIRS = cfg_bot(
    "ALL_PAIRS",
    [
        "EURUSD=X",
        "GBPUSD=X",
        "EURJPY=X",
        "GBPJPY=X",
        "AUDUSD=X",
        "USDJPY=X",
        "USDCHF=X",
        "AUDJPY=X",
    ],
)
_YAHOO_TO_OANDA_DEFAULT = {
    "EURUSD=X": "EUR_USD",
    "GBPUSD=X": "GBP_USD",
    "EURJPY=X": "EUR_JPY",
    "GBPJPY=X": "GBP_JPY",
    "AUDUSD=X": "AUD_USD",
    "USDJPY=X": "USD_JPY",
    "USDCHF=X": "USD_CHF",
    "AUDJPY=X": "AUD_JPY",
}
YAHOO_TO_OANDA = cfg_bot("YAHOO_TO_OANDA", _YAHOO_TO_OANDA_DEFAULT.copy())
for _sym, _oanda in _YAHOO_TO_OANDA_DEFAULT.items():
    YAHOO_TO_OANDA.setdefault(_sym, _oanda)
logger.info(f"✅ Pair mappings loaded: {len(YAHOO_TO_OANDA)} entries")

# ─── PAIR WHITELIST + DISJOINT SAFETY LOCK ───────────────────────────────────
# Whitelist (Ownership Tag): restrict this profile to its own currency pool so
# Profile2 / Profile3 never open the same pair on the same signal (prevents
# correlated double-sizing when both crons run in parallel).
ALLOWED_PAIRS = cfg_bot("ALLOWED_PAIRS", None)
if ALLOWED_PAIRS is not None:
    _known = set(YAHOO_TO_OANDA.keys())
    _invalid = [p for p in ALLOWED_PAIRS if p not in _known]
    if _invalid:
        logger.warning(
            f"⚠️  ALLOWED_PAIRS contains unknown symbols (will be ignored): {_invalid} "
            f"— valid set: {sorted(_known)}"
        )
    ALLOWED_PAIRS = [p for p in ALLOWED_PAIRS if p in _known]
    logger.info(
        f"🔒 WHITELIST [{PROFILE_LABEL}] active = {len(ALLOWED_PAIRS)} pairs | "
        f"ALLOWED: {ALLOWED_PAIRS}"
    )

    # Safety lock: cross-check disjointness with the *other* profile's whitelist
    # by importing its config module (best-effort, never crash on failure).
    try:
        _other_module_name = (
            "config_bot_profile3" if PROFILE_NAME == "profile2"
            else "config_bot_profile2"
        )
        _other_cfg = importlib.import_module(_other_module_name)
        _other_whitelist = set(getattr(_other_cfg, "ALLOWED_PAIRS", []) or [])
        _mine = set(ALLOWED_PAIRS)
        _overlap = _mine & _other_whitelist
        if _overlap:
            logger.error(
                f"🚨 WHITELIST OVERLAP with {_other_module_name}! "
                f"Shared pairs = {sorted(_overlap)} — this doubles exposure on the "
                f"same signals. Fix the ALLOWED_PAIRS in one or both profile configs."
            )
        else:
            _union = _mine | _other_whitelist
            logger.info(
                f"🔐 WHITELIST disjoint ✅ | overlap=0 | union covers {len(_union)} "
                f"pairs vs {len(_known)} total available"
            )
    except Exception as _e:
        logger.info(f"ℹ️  Skipped cross-profile overlap check: {_e}")
else:
    logger.info("ℹ️  No ALLOWED_PAIRS set — full 8-pair pool enabled (no whitelist filter)")

MC_MAX_AGE_HOURS = cfg_bot("MC_MAX_AGE_HOURS", 24)
SIMULATIONS = cfg_bot("MC_SIMULATIONS", 5000)
CONFIDENCE = cfg_bot("MC_BAND_PCT", 90) / 100.0
REMOVE_COOLDOWN = cfg_bot("REMOVE_COOLDOWN", False)
if args.confluence is not None:
    MULTI_TF_CONFLUENCE = args.confluence

# ─── MC TIMEFRAME CONFIG ─────────────────────────────────────────────────────
if TIMEFRAME in ("H4", "1H", "15m"):
    MCConfig.set_timeframe(
        TIMEFRAME,
        {
            "YF_INTERVAL": cfg_bot("YF_INTERVAL", "4h"),
            "YF_PERIOD_FULL": cfg_bot("YF_PERIOD_FULL", "30d"),
            "YF_PERIOD_RESAMPLE": cfg_bot("YF_PERIOD_RESAMPLE", "60d"),
            "MC_LOOKBACK": cfg_bot("H4_LOOKBACK", 90),
            "MC_FORECAST": cfg_bot("H4_FORECAST", 8),
            "PERIODS_YEAR": cfg_bot("PERIODS_YEAR", 252) * 6,
            "MC_REPORT_TITLE": f"[{PROFILE_LABEL}] FX {TIMEFRAME} MONTE CARLO",
            "RESULTS_DIR": RESULTS_DIR,
        },
    )
else:
    MCConfig.set_timeframe(
        TIMEFRAME,
        {
            "YF_INTERVAL": cfg_bot("YF_INTERVAL_D", "1d"),
            "YF_PERIOD_FULL": cfg_bot("YF_PERIOD_FULL_D", "120d"),
            "YF_PERIOD_RESAMPLE": cfg_bot("YF_PERIOD_RESAMPLE_D", "180d"),
            "MC_LOOKBACK": cfg_bot("DAILY_LOOKBACK", 90),
            "MC_FORECAST": cfg_bot("DAILY_FORECAST", 5),
            "PERIODS_YEAR": cfg_bot("PERIODS_YEAR_D", 252),
            "MC_REPORT_TITLE": f"[{PROFILE_LABEL}] FX DAILY MONTE CARLO",
            "RESULTS_DIR": RESULTS_DIR,
        },
    )

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
min_conv = (
    cfg_bot("MIN_CONVICTION_SCORE", 30.0)
    if MODE == "LEVEL10"
    else cfg_bot("MIN_CONVICTION_SCORE_ALT", 45.0)
)
min_edge = (
    cfg_bot("BASE_MIN_EDGE", 0.50)
    if MODE == "LEVEL10"
    else cfg_bot("BASE_MIN_EDGE_ALT", 0.51)
)
STRAT_CFG = StrategyConfig(
    mode=MODE,
    min_conviction_score=min_conv,
    base_min_edge=min_edge,
    mc_filter_mode=FilterMode.PENALIZE,
    regime_filter_mode=FilterMode.OFF,
    adx_filter_mode=FilterMode.OFF,
    pivot_filter_mode=FilterMode.PENALIZE,
    strength_gap_filter_mode=FilterMode.PENALIZE,
    cooldown_filter_mode=FilterMode.BLOCK,
)
fetcher = DataFetcher(
    use_oanda=True, oanda_api=api, oanda_granularity=OANDA_GRANULARITY
)
feat_engine = FeatureEngine(FEAT_CFG)
strat_engine = StrategyEngine(STRAT_CFG, model=None, feature_list=[])
atr_mod = ATRModule(period=getattr(FEAT_CFG, "atr_period", cfg_bot("ATR_PERIOD", 14)))
MODEL_PATH = BASE_DIR / "trade_model_xgb.pkl"
model_wrapper = ModelWrapper(FEAT_CFG, model_path=MODEL_PATH)
last_closed = [] if REMOVE_COOLDOWN else load_cooldown(COOLDOWN_FILE, Direction)


# ─── HELPER: TOP-N STRENGTH PAIR BUILDER ─────────────────────────────────────
def build_top_pairs(
    strength_scores,
    all_pairs,
    oanda_map,
    top_n=TOP_N_CURRENCIES,
    min_gap=TOP_PAIRS_MIN_GAP,
):
    """Build candidate pairs: strongest N × weakest N cross-combination"""
    ranked = sorted(strength_scores.items(), key=lambda x: x[1], reverse=True)
    strongest = [ccy for ccy, _ in ranked[:top_n]]
    weakest = [ccy for ccy, _ in ranked[-top_n:]]

    logger.info(f"🏆 STRONGEST {top_n}: {strongest}")
    logger.info(f"📉 WEAKEST  {top_n}: {weakest}")

    candidates = []
    seen = set()
    for strong in strongest:
        for weak in weakest:
            if strong == weak:
                continue
            gap = strength_scores[strong] - strength_scores[weak]
            if abs(gap) < min_gap:
                continue
            for base, quote in [(strong, weak), (weak, strong)]:
                yahoo_sym = f"{base}{quote}=X"
                if yahoo_sym in all_pairs and yahoo_sym not in seen:
                    oanda_inst = oanda_map.get(yahoo_sym)
                    if oanda_inst:
                        seen.add(yahoo_sym)
                        candidates.append(
                            {
                                "pair": yahoo_sym,
                                "oanda": oanda_inst,
                                "gap": gap,
                                "gap_abs": abs(gap),
                            }
                        )

    candidates.sort(key=lambda x: x["gap_abs"], reverse=True)
    selected = [c["pair"] for c in candidates]

    logger.info(f"🎯 Top-{top_n} matrix → {len(selected)} qualified pairs")
    for c in candidates[:6]:
        dir_s = "BUY" if c["gap"] > 0 else "SELL"
        logger.info(f"   {c['pair']}: gap={c['gap']:+.3f} → {dir_s}")

    return selected, candidates


def calc_weighted_score(
    pair: str,
    gap: float,
    rsi_val: float,
    adx_val: float,
    xgb_prob: float,
    mc_pct_up: float,
):
    MIN_FINAL_SCORE = min_conv
    strength_dir = (
        "BUY"
        if gap >= MIN_STRENGTH_GAP
        else "SELL" if gap <= -MIN_STRENGTH_GAP else "NEUTRAL"
    )
    xgb_dir = "BUY" if (xgb_prob or 0.0) >= XGB_BULLISH_THRESHOLD else "SELL"
    mc_dir = "BUY" if (mc_pct_up or 50.0) >= MC_BULLISH_THRESHOLD else "SELL"
    # buy_votes = sum(1 for d in (strength_dir, xgb_dir, mc_dir) if d == "BUY")
    buy_votes = sum(bool(d == "BUY") for d in (strength_dir, xgb_dir, mc_dir))
    # sell_votes = sum(1 for d in (strength_dir, xgb_dir, mc_dir) if d == "SELL")
    sell_votes = sum(bool(d == "SELL") for d in (strength_dir, xgb_dir, mc_dir))

    logger.info(
        f"🤝 {pair}: Strength={strength_dir} | XGB={xgb_dir} | MC={mc_dir} | BUY={buy_votes}/3"
    )

    if REQUIRE_DIRECTION_CONSENSUS:
        if buy_votes >= CONSENSUS_THRESHOLD:
            direction = "BUY"
            logger.info(f"✅ {pair}: BUY consensus ({buy_votes}/3)")
        elif sell_votes >= CONSENSUS_THRESHOLD:
            direction = "SELL"
            logger.info(f"✅ {pair}: SELL consensus ({sell_votes}/3)")
        else:
            logger.info(f"⏭️  {pair}: NO CONSENSUS → SKIP")
            return None, None
    else:
        direction = "BUY" if gap > 0 else "SELL"
        logger.info(f"ℹ️  Consensus OFF — using Strength only: {direction}")

    S = max(0.0, min(100.0, abs(gap) / 3.5 * 100.0))
    rsi = max(0.0, min(100.0, rsi_val))
    # Score the deviation from the 50 midline in the direction of the trade.
    # The previous form — `(rsi - 50) * 2` for a SELL, floored at 0 — was not a
    # measurement of RSI but a hard gate at 50: any short with RSI <= 50 scored
    # exactly 0, so the configured 15% RSI weight vanished for roughly half of
    # all candidates purely because the reading landed on the wrong side of the
    # midline (e.g. RSI 47.5 → 0.0 while RSI 63.5 → 26.9).
    # |rsi - 50| * 2 keeps the same 0-100 scale at the extremes and stays
    # monotonic in RSI conviction, with 50 → 0 exactly as the midline implies.
    R = max(0.0, min(100.0, abs(rsi - 50.0) * 2.0))

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

    FINAL = S * W_S + R * W_R + A * W_A + X * W_X + M * W_M
    return direction, {
        "S": round(S, 1),
        "R": round(R, 1),
        "A": round(A, 1),
        "X": round(X, 1),
        "M": round(M, 1),
        "FINAL": round(FINAL, 1),
        "PASS": FINAL >= MIN_FINAL_SCORE,
        "THRESHOLD": round(MIN_FINAL_SCORE, 1),
    }


# ─── MAIN TRADING FLOW ───────────────────────────────────────────────────────
def main():
    global model_wrapper, strat_engine
    logger.info(
        f"\n🤖 RUN v6.8.3.3 {PROFILE_LABEL} — {ACCOUNT_NAME} | TREND+TP+TOP-N | "
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} | "
        f"MAX_OPEN={MAX_OPEN} | MIN_GAP={MIN_STRENGTH_GAP} | TOP_N={TOP_PAIRS_COUNT}"
    )
    logger.info(
        f"🧭 STRENGTH POOL: {len(CURRENCIES)} currencies "
        f"[{' '.join(CURRENCIES)}] | "
        f"TOP_N={TOP_N_CURRENCIES} (strongest × weakest) | "
        f"USE_TOP_PAIRS_ONLY={USE_TOP_PAIRS_ONLY} | "
        f"TOP_PAIRS_MIN_GAP={TOP_PAIRS_MIN_GAP}"
    )
    logger.info(f"🔑 OANDA Account ID: {OANDA_ACCOUNT_ID}")

    if forex_market_closed():
        return

    model_wrapper, strat_engine = ensure_model(
        MODEL_PATH,
        FEAT_CFG,
        model_wrapper,
        strat_engine,
        fetcher,
        feat_engine,
        ALL_PAIRS,
        YAHOO_TO_OANDA,
        cfg_bot,
    )

    # Step 1 — Currency Strength + Top-N Filter
    logger.info("[STEP 1] Currency Strength Matrix...")
    strength_scores = build_strength_matrix()
    logger.info(format_strength_ranking(strength_scores))

    if USE_TOP_PAIRS_ONLY:
        selected_pairs, _ = build_top_pairs(
            strength_scores,
            ALL_PAIRS,
            YAHOO_TO_OANDA,
            top_n=TOP_PAIRS_COUNT,
            min_gap=TOP_PAIRS_MIN_GAP,
        )
        if not selected_pairs:
            logger.warning("⚠️ No high-gap pairs found — falling back to full scan")
            selected_pairs = ALL_PAIRS[:]
        logger.info(
            f"🎯 MODE: Top-{TOP_PAIRS_COUNT} strength active → {len(selected_pairs)} candidates"
        )
    else:
        selected_pairs = ALL_PAIRS[:]
        logger.info(f"📋 MODE: Full scan — {len(selected_pairs)} pairs")

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
            if raw.empty:
                continue
            df = (
                feat_engine.build(raw)
                .replace([np.inf, -np.inf], np.nan)
                .ffill()
                .bfill()
                .fillna(0)
            )
            if len(df) < 5:
                continue
            pair_data[pair] = {
                "df": df,
                "oanda": oanda,
                "raw": raw,
                "atr": df.iloc[-1].get("atr", 0.0),
                "rsi": df.iloc[-1].get("rsi", 50.0),
                "adx": df.iloc[-1].get("adx", -1.0),
            }
            if pair_data[pair]["adx"] < 10:
                logger.info(
                    f"⚠️ ADX {pair} = {pair_data[pair]['adx']:.1f} — possibly flat market"
                )
            logger.info(
                f"📊 {pair}: {len(df)} bars | ATR={pair_data[pair]['atr']:.6f} | "
                f"RSI={pair_data[pair]['rsi']:.1f} | ADX={pair_data[pair]['adx']:.1f}"
            )
            weekly_ema_cache[oanda] = fetch_weekly_ema100(oanda, api)
        except Exception as e:
            logger.error(f"❌ Fetch failed {pair}: {e}")

    if not pair_data:
        logger.error("No pairs have usable data. Aborting.")
        send_telegram_message(f"❌ FX BOT {PROFILE_LABEL}: No usable data")
        return

    # Step 2.5 — D-Gate: compute D-EMA20 × D-EMA50 direction for ALL pool pairs
    D_GATE_DIRECTIONS.clear()
    if D_GATE_ENABLED:
        logger.info("[STEP 2.5] D-GATE — Daily Direction Locks...")
        # Need ALL_PAIRS (not just selected) because WhiteList filter happens
        # later, and USD-group majority works better if we see the whole pool.
        for pair in ALL_PAIRS:
            oanda = YAHOO_TO_OANDA.get(pair)
            if not oanda:
                continue
            daily = d_gate_fetch_daily(fetcher, pair, oanda, count=180)
            if daily is None:
                D_GATE_DIRECTIONS[pair] = D_GATE_BOTH
                continue
            direction = d_gate_compute_direction(
                daily,
                ema_fast_period=D_GATE_EMA_FAST,
                ema_slow_period=D_GATE_EMA_SLOW,
                confirm_bars=D_GATE_CONFIRM_BARS,
                min_buffer_pct=D_GATE_MIN_BUFFER_PCT,
            )
            D_GATE_DIRECTIONS[pair] = direction
        long_n = sum(1 for v in D_GATE_DIRECTIONS.values() if v == D_GATE_LONG)
        short_n = sum(1 for v in D_GATE_DIRECTIONS.values() if v == D_GATE_SHORT)
        both_n = sum(1 for v in D_GATE_DIRECTIONS.values() if v == D_GATE_BOTH)
        logger.info(
            f"🧭 D-GATE SUMMARY: LONG={long_n} SHORT={short_n} BOTH={both_n} | "
            f"SHADOW={D_GATE_SHADOW} (log-only, no block)"
        )
        for pair in sorted(D_GATE_DIRECTIONS.keys()):
            logger.info(f"   {pair}: {D_GATE_DIRECTIONS[pair]}")

    # Step 3 — Monte Carlo
    if cfg_bot("SKIP_MC", False):
        args.skip_mc = True
    mc_cache = {}
    if not args.skip_mc:
        logger.info("[STEP 3] Monte Carlo Forecasts...")
        mc_gen = MCGenerator(
            fetcher, YAHOO_TO_OANDA, simulations=SIMULATIONS, confidence=CONFIDENCE
        )
        require_mc_momentum = cfg_bot("REQUIRE_STRONG_MOMENTUM", True)
        for pair in selected_pairs:
            if pair not in pair_data:
                continue
            mc_data, ok = mc_gen.run_for_pair(pair, df=pair_data[pair]["raw"])
            if ok:
                regime = mc_data.get("regime", "")
                if require_mc_momentum and "STRONG MOMENTUM" not in regime:
                    logger.info(f"⏭️ {pair}: MC regime={regime} — SKIP")
                    continue
                mc_cache[pair] = mc_data
                logger.info(
                    f"🎲 MC {pair}: {regime} | Band {mc_data['range_90']} | P_UP={mc_data['p_up']}%"
                )
    else:
        logger.info("[STEP 3] MC Skipped — loading legacy...")
        for pair in selected_pairs:
            mc_data, ok = load_mc_legacy(pair, RESULTS_DIR, TODAY_STR, MC_MAX_AGE_HOURS)
            if ok:
                mc_cache[pair] = mc_data

    if args.mc_only:
        return

    # Step 4 — Multi-Timeframe Confluence
    tf_confluence = {}
    if MULTI_TF_CONFLUENCE:
        logger.info("[STEP 4] Multi-Timeframe Confluence...")
        TF_GRAN = {"H4": "H4", "1H": "H1", "15m": "M15"}
        for pair in selected_pairs:
            if pair not in pair_data:
                continue
            dirs = []
            for gran in TF_GRAN.values():
                with contextlib.suppress(Exception):
                    raw_tf = fetch_candles(pair_data[pair]["oanda"], gran)
                    if len(raw_tf) < 5:
                        continue
                    sig = strat_engine.generate_signal(
                        pair,
                        pair_data[pair]["oanda"],
                        feat_engine.build(raw_tf),
                        None,
                        strength_scores,
                        raw_tf.iloc[-1]["Close"],
                        1.0,
                    )
                    if sig:
                        dirs.append(sig.action)
            buy_c, sell_c = dirs.count("BUY"), dirs.count("SELL")
            passes = (
                buy_c >= CONFLUENCE_REQUIRED_TFS or sell_c >= CONFLUENCE_REQUIRED_TFS
            )
            tf_confluence[pair] = {"buy": buy_c, "sell": sell_c, "passes": passes}
            logger.info(
                f"🔗 CONFLUENCE {pair}: BUY={buy_c} SELL={sell_c} → {'✅ PASS' if passes else '❌ BLOCK'}"
            )

    # Step 5 — Dynamic Exit Manager
    logger.info("[STEP 5] Dynamic Exit Manager...")

    def close_wrap(instr):
        return close_position(api, OANDA_ACCOUNT_ID, instr, send_telegram_message)

    dyn_mgr = DynamicPositionManager(
        api,
        OANDA_ACCOUNT_ID,
        TIMEFRAME,
        cfg_bot("BE_TRIGGER_ATR_MULT", 1.5),
        cfg_bot("TRAIL_TRIGGER_ATR_MULT", 2.5),
        cfg_bot("TRAIL_ATR_MULT", 1.5),
        cfg_bot("MAX_HOLD_BARS", 12),
        dynamic_tp=DYNAMIC_TP,
        tp_raise_thresh_pips=TP_RAISE_THRESHOLD_PIPS,
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
        if not oanda_inst:
            continue
        status, pos = get_open_position(api, OANDA_ACCOUNT_ID, oanda_inst)

        is_open = status == PositionStatus.OPEN
        open_pos_by_oanda[oanda_inst] = is_open
        if is_open:
            open_pos_count += 1
            logger.info(
                f"📌 OPEN POSITION: {pair} → {oanda_inst} | {pos['side'].upper()} | units={pos['units']}"
            )
    open_list = [o.replace("_", "/") for o, s in open_pos_by_oanda.items() if s]
    ready_list = [
        p.replace("=X", "")
        for p in selected_pairs
        if not open_pos_by_oanda.get(YAHOO_TO_OANDA.get(p), False)
    ]
    logger.info(
        f"📊 Open positions: {open_pos_count}/{MAX_OPEN} | OPEN: {', '.join(open_list) or 'None'} | READY: {', '.join(ready_list) or 'None'}"
    )

    # Step 7 — Score, Trend Filter, Smart TP & Execute
    logger.info("[STEP 7] Scoring + TREND FILTER + SMART TP...")
    min_sl_pips_jpy, min_sl_pips_std = cfg_bot("MIN_SL_PIPS_JPY", 35), cfg_bot(
        "MIN_SL_PIPS", 25
    )
    trade_lines, pip_cache, pair_parts = (
        {},
        {p: pip_size(p) for p in selected_pairs},
        {p: (p[:3], p[3:].replace("=X", "")) for p in selected_pairs},
    )
    all_candidates = []

    for pair in selected_pairs:
        if pair not in pair_data:
            continue
        oanda = pair_data[pair]["oanda"]
        atr_val, rsi_val, adx_val = (
            pair_data[pair]["atr"],
            pair_data[pair]["rsi"],
            pair_data[pair]["adx"],
        )

        # ─── Whitelist filter (Ownership Tag) — enforce disjoint pools for multi-account isolation
        if ALLOWED_PAIRS is not None and pair not in ALLOWED_PAIRS:
            logger.info(f"🔒 {pair}: not in {PROFILE_LABEL} ALLOWED_PAIRS — SKIP")
            continue

        if pair in last_closed:
            d, r = last_closed[pair]
            if r > 0:
                last_closed[pair] = (d, r - 1)
                logger.info(f"⏳ COOLDOWN {pair}: {r-1} runs remaining — SKIP")
                continue
            else:
                del last_closed[pair]

        if open_pos_by_oanda.get(oanda, False):
            logger.info(f"⏭️ {pair}: position already open — SKIP DUPLICATE")
            continue

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

        base, quote = pair_parts[pair]
        gap = strength_scores.get(base, 0) - strength_scores.get(quote, 0)
        if abs(gap) < MIN_STRENGTH_GAP:
            logger.info(f"⏭️ {pair}: gap={abs(gap):.2f} < MIN={MIN_STRENGTH_GAP} — SKIP")
            continue
        logger.info(f"📈 {pair}: gap={abs(gap):.2f} ≥ {MIN_STRENGTH_GAP} — QUALIFIED")

        if MULTI_TF_CONFLUENCE and not tf_confluence.get(pair, {}).get("passes", True):
            logger.info(f"🚫 {pair}: confluence fail — SKIP")
            continue

        sig = strat_engine.generate_signal(
            pair,
            oanda,
            pair_data[pair]["df"],
            mc_cache.get(pair),
            strength_scores,
            current,
            spread_pips,
        )
        prob_raw = (
            getattr(sig, "probability", None)
            or getattr(sig, "model_prob", None)
            or getattr(sig, "prob", None)
            or 0.0
        )
        mc_pct_up = mc_cache.get(pair, {}).get("p_up", 50.0)

        direction, w = calc_weighted_score(
            pair, gap, rsi_val, adx_val, prob_raw, mc_pct_up
        )
        if direction and w:
            tag = "✅" if w["PASS"] else "❌"
            logger.info(
                f"{tag} SCORE {pair} {direction} | "
                f"S={w['S']:5.1f}×{W_S:.2f}={w['S']*W_S:4.1f}  "
                f"R={w['R']:5.1f}×{W_R:.2f}={w['R']*W_R:4.1f}  "
                f"A={w['A']:5.1f}×{W_A:.2f}={w['A']*W_A:4.1f}  "
                f"X={w['X']:5.1f}×{W_X:.2f}={w['X']*W_X:4.1f}  "
                f"M={w['M']:5.1f}×{W_M:.2f}={w['M']*W_M:4.1f}  | FINAL={w['FINAL']:.2f}"
            )

        if not (direction and w and w["PASS"]):
            if w and not w["PASS"]:
                logger.info(
                    f"➖ REASON: FINAL {w['FINAL']:.2f} < MIN_CONVICTION={min_conv:.2f}"
                )
            continue

        weekly_ema100 = resolve_weekly_ema100(
            weekly_ema_cache.get(oanda),
            cfg_bot("WEEK_EMA100_FILTER_ENABLED", False),
        )
        allow_entry, smart_tp_pips, tp_info = evaluate_trend_and_tp(
            PROFILE_NAME,
            direction,
            mc_pct_up,
            current,
            pip_cache[pair],
            pair_data[pair]["df"],
            weekly_ema100,
            timeframe=args.timeframe,
        )
        if not allow_entry:
            continue

        dec = 3 if "JPY" in pair else 5
        if cfg_bot("SL_USE_ZONE_HIERARCHY", True):
            sl_price, _ = compute_sl_zone(
                api, oanda, direction, current, pip_cache[pair], cfg_bot
            )
            sl_price = round(sl_price, dec)
        else:
            sl_pips = max(
                min_sl_pips_jpy if "JPY" in pair else min_sl_pips_std,
                round(atr_val / pip_cache[pair] * cfg_bot("ATR_SL_MULT", 2.0), 1),
            )
            sl_price = (
                round(current - sl_pips * pip_cache[pair], dec)
                if direction == "BUY"
                else round(current + sl_pips * pip_cache[pair], dec)
            )

        tp_price = (
            round(current + smart_tp_pips * pip_cache[pair], dec)
            if direction == "BUY"
            else round(current - smart_tp_pips * pip_cache[pair], dec)
        )

        all_candidates.append(
            (
                -w["FINAL"],
                w["FINAL"],
                pair,
                oanda,
                direction,
                current,
                sl_price,
                tp_price,
                dec,
                smart_tp_pips,
            )
        )

    # Execute Top Candidates
    _cap = MAX_ENTRIES or MAX_OPEN
    _rank_limit = min(MAX_OPEN - open_pos_count, _cap, len(all_candidates))
    logger.info(
        f"🏆 RANKED: {len(all_candidates)} passed → opening top "
        f"{max(0, _rank_limit)} (MAX_OPEN={MAX_OPEN}, existing={open_pos_count}, "
        f"MAX_ENTRIES={MAX_ENTRIES or 'unlimited'})"
    )
    for i, (_, score, pair, _, dir, _, _, _, _, tp_pips) in enumerate(
        all_candidates, 1
    ):
        logger.info(f"   #{i} — {pair} {dir} SCORE={score:.1f} SMART-TP={tp_pips:.1f}p")

    executed_in_this_run = set()
    entries_this_run = 0
    for (
        _,
        FINAL,
        pair,
        oanda,
        direction,
        current,
        sl_price,
        tp_price,
        dec,
        _,
    ) in all_candidates:
        if open_pos_by_oanda.get(oanda, False):
            logger.info(f"⏭️ {pair} ({oanda}): already open — SKIP DUPLICATE")
            continue
        if oanda in executed_in_this_run:
            logger.info(f"⏭️ {pair} ({oanda}): selected in this run — SKIP DUPLICATE")
            continue
        if open_pos_count >= MAX_OPEN:
            logger.info(f"⏭️ {pair}: MAX_OPEN={MAX_OPEN} reached — SKIP")
            continue
        if MAX_ENTRIES and entries_this_run >= MAX_ENTRIES:
            logger.info(
                f"⏭️ {pair}: MAX_ENTRIES this run = {MAX_ENTRIES} reached — SKIP"
            )
            continue

        if not LIVE_MODE:
            logger.info(
                f"🧪 [DRY-RUN] SIGNAL {pair} {direction} | "
                f"SL={sl_price} | TP={tp_price} | Score={FINAL:.1f} — NO ORDER SENT"
            )
            trade_lines[pair] = (
                f"🧪 [DRY-RUN] {pair} {direction} Score={FINAL:.1f} | SL={sl_price} TP={tp_price}"
            )
            entries_this_run += 1
            open_pos_count += 1
            executed_in_this_run.add(oanda)
            continue

        try:
            resp = open_oanda_order(
                api,
                OANDA_ACCOUNT_ID,
                oanda,
                direction,
                DEFAULT_LOT_SIZE,
                sl_price,
                tp_price,
            )
            status = resp.get("status", "UNKNOWN")
            tid = resp.get("trade_id", "") or "?"

            if status == "OK":
                logger.info(
                    f"✅ EXECUTED {pair} {direction} | SL={sl_price} | TP={tp_price} | TradeID={tid}"
                )
                trade_lines[pair] = (
                    f"✅ {pair} {direction} Score={FINAL:.1f} | SL={sl_price} TP={tp_price}"
                )
                entries_this_run += 1
                open_pos_count += 1
                executed_in_this_run.add(oanda)
            elif status == "DRY_RUN":
                logger.info(
                    f"🧪 DRY_RUN {pair} {direction} | SL={sl_price} | TP={tp_price} — validated, no API call"
                )
                trade_lines[pair] = (
                    f"🧪 [DRY_RUN] {pair} {direction} Score={FINAL:.1f} | SL={sl_price} TP={tp_price}"
                )
                entries_this_run += 1
                open_pos_count += 1
                executed_in_this_run.add(oanda)
            elif status == "REDUCED":
                logger.warning(
                    f"⚠️ {pair} {direction} — fill REDUCED existing pos, no new trade opened"
                )
                trade_lines[pair] = (
                    f"⚠️ [REDUCED] {pair} {direction} Score={FINAL:.1f} — reduced existing pos"
                )
            else:
                reason = resp.get("message") or resp.get("reason") or status
                logger.error(
                    f"❌ ORDER FAILED {pair} {direction} — status={status} | {reason}"
                )
                trade_lines[pair] = (
                    f"❌ [FAILED {status}] {pair} {direction} Score={FINAL:.1f} — {reason}"
                )
        except Exception as e:
            logger.error(f"❌ ORDER FAILED {pair}: {type(e).__name__}: {e}")
            trade_lines[pair] = (
                f"❌ [EXCEPTION] {pair} {direction} Score={FINAL:.1f} — {type(e).__name__}: {e}"
            )

    if trade_lines:
        summary = (
            f"🤖 v6.8.3.3 {PROFILE_LABEL} RUN COMPLETE — {ACCOUNT_NAME}\n\n"
            + "\n".join(trade_lines.values())
        )
        send_telegram_message(summary)
    else:
        logger.info("📋 No signals passed all filters")

    logger.info(
        f"✅ v6.8.3.3 {PROFILE_LABEL} Run Complete — {ACCOUNT_NAME} — TOP-N STRENGTH ACTIVE"
    )


if __name__ == "__main__":
    from utils.utils import apply_jitter

    try:
        apply_jitter(1.0, 10.0)
        main()
    except Exception as e:
        logger.exception(f"Fatal error in {PROFILE_LABEL} main loop")
        send_telegram_message(f"❌ FX BOT {PROFILE_LABEL} FATAL ERROR: {e}")
        raise