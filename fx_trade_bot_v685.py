#!/usr/bin/env python3
# fx_trade_bot_v685
# ──────────────────────────────────────────────────────
# FX Trade Bot v6.8.5 — 配置统一入口
# 唯一来源: config_profile.json → config_bot.py
# ──────────────────────────────────────────────────────
import contextlib
import copy
import sys
import os
import time

from utils.logging_utils import get_logger
import argparse
from pathlib import Path
from datetime import datetime, timezone
import config_bot as C
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
from strategy_decision import StrategyConfig, StrategyEngine, FilterMode, Direction
from data_pipeline import (
    FeatureConfig,
    FeatureEngine,
    ModelWrapper,
    DataFetcher,
    ATRModule,
)
from fx_trade_bot_utils_v1 import (
    pip_size,
    load_cooldown,
    save_cooldown,
    refresh_tp_cooldown_from_recent_tx,
    get_open_position,
    has_open_trade_with_tags,
    list_open_trades,
    close_position,
    fetch_candles,
    fetch_weekly_ema100,
    update_order_tp,
    update_order_sl,
    record_cooldown_from_closed_trades,
    audit_owned_closed_trades,
    open_oanda_order_simple as open_oanda_order,
    DynamicPositionManager,
    load_mc_legacy,
    load_mc_bundle,
    get_mc_results_dir,
    should_close_by_opposite_signal,
    PositionStatus,
)
from fx_trade_bot_ml import ensure_model
from utils.ml_alert_reporting import report_ml_init_result
from oandapyV20.endpoints.pricing import PricingInfo

# from portfolio_balance import balance_from_config
from sl_zone_hierarchy import compute_sl_zone
from utils.prob_zone_sizing import (
    PROB_FACTORS,
    apply_strong_momentum_bonus,
    below_min_prob_factor,
    compute_prob_plan,
    d_regime_for_decision,
    format_prob_audit,
    is_strong_momentum_regime,
    load_prob_index,
    min_prob_factor_units,
    next_prob_rung_up,
    normalize_to_prob_factor,
    prob_tier_for_units,
    to_mc_key,
)
from utils.risk_parity_sizing import (
    compute_risk_parity,
    log_sizing_shadow,
    apply_if_enabled,
)
from utils.wide_range_sizing import (
    compute_atr_ratio,
    compute_d_skew,
    dynamic_max_open,
    log_wide_range_shadow,
    portfolio_volatility_tier,
    update_trade_id,
)
from utils.mc_boundary_watch import (
    bars_from_dataframe,
    watch_mc_boundaries,
)
from utils.mc_error_reporting import report_mc_refresh_error
from config_oanda import (
    # api,
    get_oanda_profile,
    OANDA_ACCOUNT_ID_1_LIVE,
    OANDA_ACCOUNT_ID_2_LIVE,
    OANDA_ACCOUNT_ID_3_LIVE,
    OANDA_ACCOUNT_ID_4_LIVE,
    OANDA_ACCOUNT_ID_DEMO_1,
    OANDA_ACCOUNT_ID_DEMO_2,
    OANDA_ACCOUNT_ID_DEMO_3,
    OANDA_ACCOUNT_ID_DEMO_4,
)

from utils.structured_logger import StructuredLogger

log = get_logger(__name__)

# ─── BASE SETUP ──────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
sys.path.extend([str(BASE_DIR), str(BASE_DIR / "utils")])

# // FIX-2026-10-10: oandapyV20.API.__init__ logs "setting up API-client for
# environment <env>" via the "oandapyV20.oandapyV20" logger EVERY time a client
# is constructed. Six modules build one at import time, so the line printed 6x
# and always said "practice" (the import-time env) even under --live.
# Raise that logger to WARNING before any config import, then print ONE
# consolidated line ourselves once the real environment is known.

# ─── FULL ARGPARSE FIRST (so --help exits before any config import) ──────────
parser = argparse.ArgumentParser(
    description="FX Trading Bot v6.8.4 | PF-B Balanced (unified profile config)"
)
parser.add_argument(
    "-p",
    "--profile",
    type=int,
    default=None,
    help="Profile number (1/2/3/4); compatible with --profile2 / --profile3",
)
parser.add_argument(
    "--profile2", action="store_true", help="Force Profile2 (shorthand for -p 2)"
)
parser.add_argument(
    "--profile3", action="store_true", help="Force Profile3 (shorthand for -p 3)"
)
parser.add_argument(
    "-a",
    "--account",
    type=str,
    default=None,
    help="Account number override (numeric index, e.g. '2' / '3' / '4')",
)
parser.add_argument(
    "-m",
    "--max-entries",
    type=int,
    default=None,
    help="Max signals to enter per cycle; overrides PROFILE's MAX_ENTRIES_THIS_RUN",
)
parser.add_argument("--timeframe", type=str, default="15m", choices=["15m", "1H", "H4"])
parser.add_argument("--confluence", action="store_true", default=None)
parser.add_argument("--no-confluence", action="store_false", dest="confluence")
parser.add_argument("--skip-mc", action="store_true")
parser.add_argument("--mc-only", action="store_true")
parser.add_argument(
    "--live", action="store_true", help="Connect the LIVE real-money environment"
)
parser.add_argument(
    "--demo",
    "--dry-run",
    action="store_true",
    dest="dry_run",
    default=None,
    help="Force DRY-RUN — no mutating OANDA calls, orders are logged only",
)
parser.add_argument(
    "--no-dry-run",
    "--no-demo",
    action="store_false",
    dest="dry_run",
    default=None,
    help="Force EXECUTION — send orders to OANDA (overrides run.env DRY_RUN)",
)
parser.add_argument(
    "--lots",
    type=int,
    default=None,
    help="Override lot size / units per trade (overrides DEFAULT_LOT_SIZE from config)",
)

parser.add_argument(
    "--ignore-market-closed",
    action="store_true",
    help="Skip the weekend/holiday guard and run the full pipeline (debug)",
)
# Optional bare positional profile number: `python fx_trade_bot_v685.py 2`.
# nargs="?" keeps it optional so `python fx_trade_bot_v685.py` still works.
parser.add_argument(
    "profile_pos",
    nargs="?",
    type=int,
    default=None,
    help="Profile number as a bare positional (e.g. 2)",
)
args = parser.parse_args()

# ===== 1. 选择运行的配置方案 =====
# 命令行启动:  python fx_trade_bot_v685.py 1 → Profile1
#             python fx_trade_bot_v685.py 2 → Profile2 (默认)
# Resolution: -p N > --profile3 / --profile2 > first positional digit > default 2
if args.profile is not None:
    PROFILE_ID = args.profile
elif args.profile3:
    PROFILE_ID = 3
elif args.profile2:
    PROFILE_ID = 2
elif args.profile_pos is not None:
    PROFILE_ID = args.profile_pos
else:
    PROFILE_ID = 2

# The unified loader below still reads the legacy name `profile_id`; keep both
# aliases in sync so every downstream reference resolves to the same value.
profile_id = PROFILE_ID

# ===== 2. 一次性加载全部参数 — 之后直接用 cfg['键名'] =====
cfg = C.get_profile(PROFILE_ID)

# ===== 3. 常用变量直接映射（复制/对照用）=====
# NOTE: APP_VERSION feeds OWNER_TAGS/OWNER_CLIENT_EXT_ID (the multi-account
# ownership tag), so changing it makes this build stop recognising positions
# opened by builds tagged "v685". Kept in sync with VERSION below instead.
APP_VERSION = "685-2"
VERSION = cfg["VERSION"]
PROFILE_NAME = f"profile{PROFILE_ID}"
PROFILE_LABEL = cfg["PROFILE_LABEL"]
OWNER_TAGS = ["fx_bot", f"v{APP_VERSION}", PROFILE_NAME]
OWNER_COMMENT = f"fx_bot_v{APP_VERSION}_{PROFILE_NAME}_entry"
OWNER_CLIENT_EXT_ID = f"fx_bot_v{APP_VERSION}_{PROFILE_NAME}"
OWNER_CLIENT_EXT_TAG = f"fx_bot_v{APP_VERSION}_{PROFILE_NAME}_entry"
# NOTE: two distinct names on purpose —
#   PROFILE_NAME  : internal key used by _TREND_TP_CONFIG / TREND_TP_CONFIG lookups
#                   ("profile1".."profile4"), so it MUST stay the lowercase
#                   profile<n> form, not the friendly label.
#   PROFILE_LABEL : the human-facing name from config_profile.json ("PF-B Balanced").

# weight factors
W_S = cfg["W_S"]  # Strength
W_R = cfg["W_R"]  # RSI
W_G = cfg.get("W_G", 0.0)  # Trend direction (EMA fast/slow alignment)
W_A = cfg["W_A"]  # ADX
W_X = cfg["W_X"]  # XGB
W_M = cfg["W_M"]  # MonteCarlo

TREND_G_ENABLED = cfg.get("TREND_G_ENABLED", False)
TREND_G_ADX_MODULATION = cfg.get("TREND_G_ADX_MODULATION", False)

if not TREND_G_ENABLED:
    W_G = 0.0

# decision thresholds
MIN_CONVICTION = cfg["MIN_CONVICTION"]  # 最低置信分
MIN_SLOPE = cfg["MIN_SLOPE"]  # 趋势斜率门槛
D_GATE_ENABLED = cfg["D_GATE_ENABLED"]  # 是否启用D-Gate
MAX_OPEN_POS = cfg["MAX_OPEN"]  # 同时最大持仓
TOP_N = cfg["TOP_N"]  # 选前N个交易对

# risk management
SL_MIN_PIPS = cfg["SL_MIN_PIPS"]  # 普通货币对最小止损
SL_MIN_PIPS_JPY = cfg["SL_MIN_PIPS_JPY"]  # 日元对最小止损
DEFAULT_LOT = cfg["DEFAULT_LOT_SIZE"]  # 手数

# signal thresholds
XGB_THRESHOLD = cfg["XGB_BULLISH_THRESHOLD"]
ADX_MIN = cfg["ADX_MIN_SCORE"]

# ===== 4. Startup Confirmation Log =====
print("=" * 50)
print(f"🚀 FX Bot v{VERSION} | {PROFILE_NAME}")
print(
    f"⚖️  Weight: S={W_S:.2f} R={W_R:.2f} G={W_G:.2f} A={W_A:.2f} X={W_X:.2f} M={W_M:.2f}"
)
print(f"🧭 Trend-G={TREND_G_ENABLED} | ADX-Mod={TREND_G_ADX_MODULATION}")
print(f"🔧 D-Gate={D_GATE_ENABLED} | 最低置信={MIN_CONVICTION} | 斜率门槛={MIN_SLOPE}")
print(f"✅ Params Data Source: config_profile.json — Profile{PROFILE_ID}")
print("=" * 50)

# ─── PROFILE_BUNDLE + UNIFIED PROFILE LOADER ────────────────────────────────
# COOLDOWN_FILE / RESULTS_DIR / PROFILE_LABEL / PROFILE_NAME were previously
# derived from a per-profile if/elif block; the unified loader derives them from
# the merged PROFILE dict so all four profiles are handled without duplication.
# Cooldown state is per (profile, environment). The DEMO and LIVE legs of the
# same profile (e.g. `-p 2` vs `-p 2 --live`) otherwise share ONE file and
# overwrite each other's locks on every cycle, which surfaced as spurious
# short-side cooldowns. Suffixing the file by environment isolates them.
_ENV_SUFFIX = "live" if getattr(args, "live", False) else "demo"
COOLDOWN_FILE = BASE_DIR / f"cooldown_{PROFILE_NAME}_{_ENV_SUFFIX}.json"
RESULTS_DIR = BASE_DIR / f"daily_results_{PROFILE_NAME}"
LOGS_DIR = BASE_DIR / "logs"

P = config_bot.get_profile(profile_id)

WEIGHTS = P["WEIGHTS"]
ALLOWED_PAIRS = P["WHITELIST"]
MAX_OPEN = P["MAX_OPEN"]
MAX_ENTRIES_THIS_RUN = P["MAX_ENTRIES_THIS_RUN"]
MIN_CONVICTION = P["MIN_CONVICTION"]
MIN_GAP = P["MIN_GAP"]
D_GATE_ENABLED = P["D_GATE_ENABLED"]
D_GATE_BUFFER_PCT = P["D_GATE_BUFFER_PCT"]
D_GATE_SHADOW = P["D_GATE_SHADOW"]
D_GATE_CONFIRM = P["D_GATE_CONFIRM"]

# ─── STRATEGY WEIGHTS (from unified PROFILE) ─────────────────────────────────
# The bot scores with cfg_bot("WEIGHT_XGB", ...) — the canonical key. The unified
# PROFILE dicts carry short keys (S/R/A/X/M); expose them under the canonical
# WEIGHT_* names so the resolution chain picks the PROFILE values, not the
# legacy config_bot.py defaults.
WEIGHT_STRENGTH = WEIGHTS["S"]
WEIGHT_RSI = WEIGHTS["R"]
WEIGHT_ADX = WEIGHTS["A"]
WEIGHT_XGB = WEIGHTS["X"]
WEIGHT_MC = WEIGHTS["M"]

# ─── TOP-N / RANKING (from unified PROFILE) ──────────────────────────────────
# Same values as the former config_bot_profile{2,3}.py modules: top-pairs mode
# ON, N=3 strongest × 3 weakest, ranking gap = MIN_GAP (0.25).
USE_TOP_PAIRS_ONLY = True
TOP_N_CURRENCIES = 3
TOP_PAIRS_COUNT = TOP_N_CURRENCIES
TOP_PAIRS_MIN_GAP = MIN_GAP

# ─── EXECUTION LIMITS (from unified PROFILE) ─────────────────────────────────
MAX_OPEN_POSITIONS = MAX_OPEN

# ─── D-GATE EMA / CONFIRM SETTINGS (from unified PROFILE) ────────────────────
D_GATE_EMA_FAST = 20
D_GATE_EMA_SLOW = 50

# ─── RSI / TREND FILTER (from former profile modules) ────────────────────────
RSI_DIRECTION_AWARE = True
TREND_FILTER_ENABLED = False
WEEK_EMA100_FILTER_ENABLED = False

# ─── RISK OVERRIDES (former profile2 GBPJPY SL floor) ────────────────────────
SL_PAIR_FLOOR_OVERRIDES = {"GBP_JPY": 50}

# ─── SLOPE_DIAG (former profile3 evidence-collection switch) ─────────────────
SLOPE_DIAG = True

# ─── TREND FILTER + SMART TP CONFIGURATION ──────────────────────────────────
# NOTE (v6.8.3.4, ChatGPT P0 advice + Gemini audit lock-in):
# Core strategy parameters are IDENTICAL across profile2/profile3.
# Performance divergence must come from pair universe (JPY bucket vs Majors
# bucket), NOT from TP/filter tuning. Minor pair-specific RISK overrides (e.g.
# GBPJPY SL floor) are ALLOWED where justified by instrument volatility —
# they are not considered "strategy divergence" because they only cap drawdown
# on a single high-vol instrument and never change the signal direction or
# ranking.
#
# ⚠️ MC STRONG THRESHOLD — LOCKED TO 0.625 (mc_pct_up ≥ 62.5%).
#    Authoritative value (broker-state-level truth): the actual field below
#    is "mc_strong_threshold" compared vs mc_pct_up/100.0. DO NOT EVER WRITE
#    0.75 (= 75%) here or claim 75% in docs — that was a historical typo.
#    Corresponds to MC bias ≥ |P_up - 0.50| ≥ 12.5% (one-sided).
_TREND_TP_CONFIG = {
    "base_tp_pips": 30,
    "mc_strong_threshold": 0.625,  # ⚠️ 🔒 LOCKED: mc_pct_up ≥ 62.5% triggers STRONG ×2 TP (NOT 75%)
    "weekly_ema_period": 100,
    "ema100_buffer_pips": 30,
    "profile1": {
        # Family = non-DGATE (same as profile2): strict slope filter, D-GATE OFF.
        "tp_normal_mult": 1.0,
        "tp_strong_mult": 2.0,
        "ema_period": 10,
        "slope_lookback": 5,
        "min_slope": 0.001,
    },
    "profile2": {
        # Family = non-DGATE: strict slope filter, D-GATE OFF.
        "tp_normal_mult": 1.0,
        "tp_strong_mult": 2.0,
        "ema_period": 10,
        "slope_lookback": 5,
        "min_slope": 0.001,
    },
    "profile3": {
        # Family = DGATE-enabled (same as profile4): widened slope rung because
        # D-GATE already filters direction; slope filter must not double-block.
        # Same MC-adaptive TP as profile2 (Strategy = identical).
        "tp_normal_mult": 1.0,
        "tp_strong_mult": 2.0,
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
    "profile4": {
        # Family = DGATE-enabled (same as profile3): widened slope rung mirrors
        # profile3's rationale — D-GATE already filters direction, so slope
        # filter must not double-block.
        "tp_normal_mult": 1.0,
        "tp_strong_mult": 2.0,
        "ema_period": 10,
        "slope_lookback": 5,
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
        log.warning(
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


# ─── H1-TIMEFRAME DIRECTION GATE (D-Gate) ────────────────────────────────────
# Locks each currency pair into a LONG / SHORT / BOTH bias based on the H1
# (Timeframe "H1") EMA20 × EMA50 cross. Prevents the 15m engine from flip-flopping
# between BUY/SELL on the same pair within hours.
#
# Design (answers = A/A/A per user spec):
#   A1: EMA_FAST=20, EMA_SLOW=50 on H1 closes
#   A2: Flip confirmation: 2 consecutive H1 closes past cross (min_buffer_pct
#       = 0.2% gap between EMAs on flip bar) → prevents 1-bar whipsaws
#   A3: All pairs evaluate their OWN H1-EMA cross (simple, no DXY synthetic).
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
    n = len(daily_closes)
    min_bars = max(ema_slow_period + confirm_bars + 2, 42)
    if n < min_bars:
        log.info(f"🧭 D-GATE: BOTH (insufficient bars: {n} < min={min_bars})")
        return D_GATE_BOTH

    ema_fast = calculate_ema(daily_closes, ema_fast_period)
    ema_slow = calculate_ema(daily_closes, ema_slow_period)
    diff_pct = (ema_fast - ema_slow) / ema_slow.replace(0.0, np.nan)

    tail = diff_pct.iloc[-confirm_bars:].tolist()
    if any(pd.isna(x) for x in tail):
        log.info("🧭 D-GATE: BOTH (NaN in EMA tail)")
        return D_GATE_BOTH

    close_last = float(daily_closes.iloc[-1])
    e20_last = float(ema_fast.iloc[-1])
    e50_last = float(ema_slow.iloc[-1])
    dist_pct = (e20_last - e50_last) / e50_last * 100.0

    above = [x >= min_buffer_pct for x in tail]
    below = [x <= -min_buffer_pct for x in tail]
    tail_vals = "[" + ", ".join(f"{x*100:+.4f}%" for x in tail) + "]"

    if all(above):
        result = D_GATE_LONG
    elif all(below):
        result = D_GATE_SHORT
    else:
        result = D_GATE_BOTH

    log.info(
        f"🧭 D-GATE DIAG | Close={close_last:.4f} | "
        f"EMA{ema_fast_period}={e20_last:.4f} | EMA{ema_slow_period}={e50_last:.4f} | "
        f"Gap={dist_pct:+.4f}% (buf±{min_buffer_pct*100:.2f}%) | "
        f"Tail({confirm_bars})={tail_vals} → {result}"
    )
    return result


def d_gate_fetch_h1(fetcher, pair: str, oanda: str, count: int = 500):
    try:
        raw = fetcher.fetch(pair, oanda, count=count, granularity="H1")
        if raw is None or raw.empty:
            log.info(f"ℹ️  D-Gate H1 fetch empty (gran=H1): {pair}")
            return None
        closes = raw["Close"].dropna()
        if len(closes) < 100:
            log.info(f"ℹ️  D-Gate H1 fetch too few bars ({len(closes)}<100): {pair}")
            return None
        return closes.reset_index(drop=True)
    except TypeError as te:
        log.warning(
            f"🚨 D-GATE FETCH API BUG: fetcher.fetch() rejected granularity=H1 "
            f"with TypeError ({te}). Falling back — this fetcher may not support "
            f"H1 granularity natively. Verify data_pipeline.py::DataFetcher.fetch "
            f"has a granularity kwarg."
        )
        if _opt("DGATE_NO_TF_FALLBACK", True):  # [OPT-4]
            log.warning(
                f"🧭 D-GATE: {pair} → BOTH (fetcher has no granularity kwarg; "
                f"refusing to treat default-timeframe bars as H1)"
            )
            return None
        try:
            raw2 = fetcher.fetch(pair, oanda, count=count)
            if raw2 is None or raw2.empty:
                return None
            closes2 = raw2["Close"].dropna()
            return closes2.reset_index(drop=True) if len(closes2) >= 100 else None
        except Exception as e2:
            log.info(f"ℹ️  D-Gate H1 fetch fallthrough {pair}: {e2}")
            return None
    except Exception as e:
        log.info(f"ℹ️  D-Gate H1 fetch {pair}: {type(e).__name__}: {e}")
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


# // FIX-2026-10-10: explain WHY we are exiting and WHEN trading resumes, so a
# weekend run is not mistaken for a hang. weekday(): Mon=0 … Sun=6.
#
# The guard forex_market_closed() (utils/trading_core.py) evaluates in
# Europe/London: Saturday all day, Sunday before 21:00 London, Friday from
# 21:00 London. THIS HELPER DOES NOT CHANGE THAT LOGIC — it only renders the
# reason and the next-open instant.
def market_reopen_hint(now_utc=None):
    """Return (reason, reopen_datetime, weekday_label) for the next FX open.

    FX reopens Sunday 21:00 UTC (22:00 London). Sunday 21:00 UTC is also the
    Monday-session open, which is why the label reads "Mon 06:00 UTC" in the
    Sydney trading-week anchor used by the request.
    """
    from datetime import timedelta

    now = now_utc or datetime.now(timezone.utc)
    wd = now.weekday()
    if wd == 4 and now.hour >= 21:  # Friday after 21:00 UTC
        days_ahead, why = 2, "weekend close (Friday)"
    elif wd == 5:  # Saturday
        days_ahead, why = 1, "weekend (Saturday)"
    elif wd == 6:  # Sunday before open
        days_ahead, why = 0, "weekend (Sunday, before open)"
    else:
        days_ahead, why = 0, "holiday / market closed"

    reopen = (now + timedelta(days=days_ahead)).replace(
        hour=21, minute=0, second=0, microsecond=0
    )
    day = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][reopen.weekday()]
    return why, reopen, day


# // FIX-2026-11-17: OANDA tradeable probe (v685-only, does NOT touch
# utils/trading_core.py). forex_market_closed() above is a PURE CLOCK test
# (Europe/London weekday+hour): it cannot see weekday holidays, exchange halts,
# or the Fri/Sun 21:00-22:00 London open/close boundary, so it both stops
# sessions that are actually open and misses weekday halts. Ask OANDA directly:
# PricingInfo reports tradeable=True/False per instrument. The probe is
# authoritative; when the probe itself FAILS (network / transient 403 burst) we
# return None so the caller falls back to the clock — an intermittent error must
# never be reported as "closed".
_MARKET_PROBE_INSTRUMENT = (os.getenv("MARKET_PROBE", "EUR_USD") or "EUR_USD").strip()


def probe_market_open(api, account_id, instrument=None, attempts=2, base_delay=0.6):
    """Return True (tradeable), False (halted/closed) or None (probe failed).

    None means "could not tell" — callers MUST fall back to the clock guard and
    must never treat None as closed.
    """
    inst = instrument or _MARKET_PROBE_INSTRUMENT
    for attempt in range(1, attempts + 1):
        try:
            r = api.request(
                PricingInfo(accountID=account_id, params={"instruments": inst})
            )
        except Exception as e:  # noqa: BLE001 — return None below on final attempt
            code = getattr(e, "code", None)
            msg = getattr(e, "msg", None) or str(e)
            if attempt < attempts:
                log.warning(
                    f"⚠️ Market probe [{inst}] attempt {attempt}/{attempts} "
                    f"(status={code}): {str(msg)[:160]} — retrying in {base_delay:.1f}s"
                )
                time.sleep(base_delay)
            else:
                log.error(
                    f"❌ Market probe [{inst}] failed after {attempts} attempts "
                    f"(status={code}): {str(msg)[:200]}"
                )
        else:
            prices = r.get("prices") or []
            if not prices:
                return False
            return bool(prices[0].get("tradeable", False))
    return None


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
    log.info(
        f"🔍 {timeframe} TREND FILTER: ema_cross_filter={ema_cross_filter} | profile={profile_name}"
    )

    ema10 = calculate_ema(df_h1["Close"], cfg["ema_period"])
    slope, ema_level = calculate_ema_slope(ema10, cfg["slope_lookback"])
    abs_slope = abs(slope)
    base_min_slope = resolve_min_slope(cfg, profile_name)
    # [OPT-8] sorted ASC + "first rung <= abs_slope" always returns 0.0003 once
    # abs_slope >= 0.0003, so the configured min_slope (e.g. P2 = 0.0007) never
    # applied. SLOPE_HONOR_CONFIG=1 uses the configured value instead.
    if _opt("SLOPE_HONOR_CONFIG", False):
        min_slope = base_min_slope
    else:
        min_slope = next(
            (s for s in sorted(MIN_SLOPE_LADDER) if abs_slope >= s),
            base_min_slope,
        )
    current_price = entry_price
    log.info(
        f"📐 SLOPE LADDER: abs_slope={abs_slope:.6f} "
        f"→ base={base_min_slope:.6f} → selected={min_slope:.6f} "
        f"({'dynamic' if min_slope != base_min_slope else 'profile-default'})"
    )

    if SLOPE_DIAG:
        # Mirror the filter's own branch so the diagnostic reports the real
        # decision, not a proxy. The previous version only compared |slope|
        # against a band, omitting the price condition entirely — so a candidate
        # blocked purely by price (e.g. slope=+0.000092 with "Price above EMA10")
        # was reported as a slope-sensitive sample and skewed the tuning data.
        # // FIX-2026-10-10: the printed comparison must be the one actually
        # evaluated. The old code tested `slope >= min_slope` for a BUY but
        # printed `(min_slope <=)` — and `slope <= -min_slope` for a SELL while
        # printing `(-min_slope >=)` — i.e. the operator was the negation of the
        # real test. That made a correct `loose=False` look like a logic error
        # in the log (e.g. "loose(-0.000300>=)=False" next to slope=+0.000320)
        # and undermined exactly the evidence the tightening ladder is built on.
        # Now each branch names its own operator explicitly, so the rendered
        # expression matches the evaluated one for both directions.
        if direction == "BUY":
            price_ok = current_price > ema_level
            # >= / >= mirror the filter's own comparisons exactly; strict >/<
            # would disagree with it on a slope exactly equal to the threshold.
            slope_ok_loose = slope >= min_slope
            slope_ok_strict = slope >= SLOPE_DIAG_BASELINE
            cmp_loose, cmp_strict = ">=", ">="
        else:
            price_ok = current_price < ema_level
            slope_ok_loose = slope <= -min_slope
            slope_ok_strict = slope <= -SLOPE_DIAG_BASELINE
            cmp_loose, cmp_strict = "<=", "<="
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
        log.info(
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
            price_ok = current_price > ema_level
            slope_ok = filter_slope
            if not (price_ok and slope_ok):
                failed = []
                if not price_ok:
                    failed.append(
                        f"price {current_price:.5f} below EMA10 {ema_level:.5f}"
                    )
                if not slope_ok:
                    failed.append(f"slope {slope:.6f} < min_slope {min_slope:.6f}")
                reason = f"{timeframe} TREND MISALIGNED — " + " AND ".join(failed)
                log.info(f"⏭️ SKIP BUY: {reason}")
                return False, 0.0, reason
        else:
            filter_slope = slope <= -min_slope
            price_ok = current_price < ema_level
            slope_ok = filter_slope
            if not (price_ok and slope_ok):
                failed = []
                if not price_ok:
                    failed.append(
                        f"price {current_price:.5f} above EMA10 {ema_level:.5f}"
                    )
                if not slope_ok:
                    failed.append(f"slope {slope:.6f} > -min_slope {-min_slope:.6f}")
                reason = f"{timeframe} TREND MISALIGNED — " + " AND ".join(failed)
                log.info(f"⏭️ SKIP SELL: {reason}")
                return False, 0.0, reason

    if weekly_ema100:
        if direction == "BUY" and current_price < weekly_ema100:
            reason = f"COUNTER-TREND vs WEEKLY EMA100 — Price below {weekly_ema100:.5f}"
            log.info(f"⏭️ SKIP BUY: {reason}")
            return False, 0.0, reason
        if direction == "SELL" and current_price > weekly_ema100:
            reason = f"COUNTER-TREND vs WEEKLY EMA100 — Price above {weekly_ema100:.5f}"
            log.info(f"⏭️ SKIP SELL: {reason}")
            return False, 0.0, reason

    # Smart TP — UNIFORM across ALL profiles (P2=P3, Core Strategy Identical).
    # Uses per-profile tp_normal_mult / tp_strong_mult from TREND_TP_CONFIG
    # which both default to ×1 / ×2 (MC≥62.5%). No P2/P3 behavioral difference.
    # LOCKED THRESHOLD (authoritative): mc_pct_up ≥ 62.5% = STRONG momentum
    profile_tp_cfg = TREND_TP_CONFIG.get(PROFILE_NAME, {})
    tp_normal_mult = profile_tp_cfg.get("tp_normal_mult", 1.0)
    tp_strong_mult = profile_tp_cfg.get("tp_strong_mult", 2.0)
    strong_thr_pct = TREND_TP_CONFIG["mc_strong_threshold"] * 100.0  # = 62.5%
    if mc_momentum >= TREND_TP_CONFIG["mc_strong_threshold"]:
        tp_pips = base_pips * tp_strong_mult
        tp_mode = (
            f"✅ STRONG MOMENTUM ×{tp_strong_mult:.1f} — MC={mc_pct_up:.1f}% "
            f"(≥{strong_thr_pct:.1f}% 🔒locked) → TP={tp_pips:.1f}p ({PROFILE_LABEL})"
        )
    else:
        tp_pips = base_pips * tp_normal_mult
        tp_mode = (
            f"✅ NORMAL ×{tp_normal_mult:.1f} — MC={mc_pct_up:.1f}% "
            f"(<{strong_thr_pct:.1f}%) → TP={tp_pips:.1f}p ({PROFILE_LABEL})"
        )

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

    log.info(tp_mode)
    return True, round(tp_pips, 1), tp_mode


def cfg_bot(name, default):
    # Resolution: active PROFILE dict → config_bot.py → config.py → default.
    if name in P:
        return P[name]
    return getattr(config_bot, name, getattr(config, name, default))


# ─── PROBABILITY-FACTOR EXECUTION SIZING ─────────────────────────────────────
# The only sizing path adjusts size_units / tp_pips / skip; signal direction,
# score, SL and MC fusion remain owned by their existing stages.
PROB_ZONE_CFG = cfg_bot("PROB_ZONE_CFG", config_bot.PROB_ZONE_DEFAULTS)
PROB_ZONE_TF = "D"


def _log_prob_zone_loaded(n_records):
    """Emit the shared 『PROB-ZONE loaded』 config banner for either data source."""
    log.info(
        f"🎲 PROB-ZONE: loaded {n_records} pair records | "
        f"S0={PROB_ZONE_CFG.get('S0')} S1={PROB_ZONE_CFG.get('S1')} "
        f"F_LO={PROB_ZONE_CFG.get('F_LO')} R_REF={PROB_ZONE_CFG.get('R_REF')} "
        f"C_LO={PROB_ZONE_CFG.get('C_LO')} MIN_LOT={PROB_ZONE_CFG.get('MIN_LOT')} "
        f"MIN_ALIGNED={PROB_ZONE_CFG.get('MC_MIN_ALIGNED_PCT')} "
        f"REGIME_MIN_MULT={PROB_ZONE_CFG.get('REGIME_MIN_MULT')} "
        f"VERDICT_MODE={PROB_ZONE_CFG.get('VERDICT_MODE')} "
        f"VERDICT_SOFT_MULT={PROB_ZONE_CFG.get('VERDICT_SOFT_MULT')} "
        f"TP_MARGIN={PROB_ZONE_CFG.get('TP_BAND_MARGIN')} "
        f"TP_MAX_MULT={PROB_ZONE_CFG.get('TP_MAX_MULT')}"
    )


def _load_prob_index_once(mc_cache=None):
    """加载一次 MC 快照 ``results`` 索引（每轮 1 次，绝不每对重读）。

    MC data unavailable → ``{}``; candidates still use the probability plan's
    configured fail-closed behavior.

    Data source（PROB_USE_FUSED，仅改数据来源、不改任何阈值/权重）：
      - True （默认）：Profile 2 已把 W+D 融合结果写回 ``mc_cache``，此处直接
        复用该索引（键 ``EUR_USD`` → 重映射为快照键 ``EURUSD=X``），使
        conv / risk_cap / 开仓门控 与共识层读取**同一份**融合记录，不再重读原始 D。
      - False 或 mc_cache 无融合记录 → 降级为旧的「独立重读原始 D JSON」行为。
    两条路径都会打印 ``📤 PROB_SOURCE:`` 供每轮核对口径。
    """
    # 融合记录的唯一凭据：blend 块写入的 "blend_source" 字段（见 STEP 3）。
    fused_ready = bool(mc_cache) and any(
        isinstance(v, dict) and v.get("blend_source") for v in mc_cache.values()
    )

    if PROB_USE_FUSED and fused_ready:
        prob_index = {
            to_mc_key(k): v for k, v in mc_cache.items() if isinstance(v, dict)
        }
        log.info(
            f"📤 PROB_SOURCE: FUSED — reusing {len(prob_index)} blended mc_cache "
            f"records (no raw-D re-read)"
        )
        _log_prob_zone_loaded(len(prob_index))
        return prob_index

    # ── Fallback: legacy independent read of the raw D JSON ──────────────────
    if PROB_USE_FUSED:
        if not mc_cache:
            log.warning(
                "⚠️ PROB_SOURCE: FUSED requested but mc_cache is empty/unavailable — "
                "falling back to raw D JSON"
            )
        elif not fused_ready:
            log.info(
                f"ℹ️ PROB_SOURCE: mc_cache carries no blended records "
                f"(profile {PROFILE_ID} has no W blend) — using raw D JSON"
            )

    prob_index = load_prob_index(TODAY_STR, PROB_ZONE_TF)
    if not prob_index:
        log.info(f"📤 PROB_SOURCE: D_ONLY — raw D JSON ({TODAY_STR}, tf={PROB_ZONE_TF})")
        log.warning(
            f"⚠️ PROB-ZONE: no usable MC snapshot for {TODAY_STR} "
            f"(tf={PROB_ZONE_TF}) — probability plan uses its configured "
            "fail-closed behavior"
        )
        return {}
    log.info(f"📤 PROB_SOURCE: D_ONLY — raw D JSON ({TODAY_STR}, tf={PROB_ZONE_TF})")
    _log_prob_zone_loaded(len(prob_index))
    return prob_index


# ── FUSION SYNC (方案A · 完整重算) ────────────────────────────────────────────
# Profile 2 W+D 融合只更新了顶层 p_up/p_down/drift/range_90/regime，派生块
# （belief / prob_bands / distribution）仍是原始日线 D 的旧值 —— 同一记录里
# 「顶层融合口径」与「底层 D 口径」并存（如顶层 p_up=45.5% 与下文 posterior=63.7%），
# 健康闸门 / 风控罚分 / TP 目标各自读到不一致的依据。
# 下面在融合后按**与生成器 (prob_mc_segment.py) 完全同构**的公式重算这三块，
# 使记录口径自洽。不改动 w_w 权重、P_UP/P_DOWN 原始计算，也不触碰任何下单逻辑。
_FUSE_STATES = ("UP", "DOWN", "RANGE")
_FUSE_PRIOR_GAMMA = 2.0          # 同 prob_mc_segment.PRIOR_GAMMA
_FUSE_THRESHOLD_TAU = 0.55       # 同 prob_mc_segment.THRESHOLD_TAU
_FUSE_MIN_WIDTH_PCT_GATE = 1.2   # 同 prob_mc_segment.MIN_WIDTH_PCT_GATE
_FUSE_DEFAULT_W_RANGE = 1.0
_FUSE_W_RANGE_MAP = (
    ("CONSOLIDATION RANGE", 1.3),
    ("NEUTRAL", 1.0),
    ("OVERBOUGHT", 0.7),
    ("OVERSOLD", 0.7),
    ("STRONG MOMENTUM", 0.5),
)


def _fuse_num(x):
    """数值(排除 bool) → float；否则 None（fail-closed）。"""
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    return float(x)


def _fuse_pair2(v):
    """[lo, hi] → (float, float)；非法 → (None, None)。"""
    if isinstance(v, (list, tuple)) and len(v) == 2:
        return _fuse_num(v[0]), _fuse_num(v[1])
    return None, None


def _fuse_w_range(regime):
    """regime 串 → RANGE 先验权重；未知回退 NEUTRAL 权重（同生成器 w_range_for）。"""
    if not regime:
        return _FUSE_DEFAULT_W_RANGE
    up = str(regime).upper()
    for token, weight in _FUSE_W_RANGE_MAP:
        if token in up:
            return weight
    return _FUSE_DEFAULT_W_RANGE


def _fuse_normalize(raw, decimals=4):
    """同生成器 _normalize：按总和归一化；总和<=0 → 均匀分布。"""
    total = sum(raw.values())
    if total <= 0:
        uniform = round(1.0 / len(raw), decimals)
        return {k: uniform for k in raw}
    return {k: round(v / total, decimals) for k, v in raw.items()}


def _fuse_sync_derived_blocks(d_blend, fused_p_up, fused_p_down, d_range, fused_range):
    """把派生块重锚到融合口径（方案A · 完整重算）。

    * ``belief.prior/posterior``：以融合 p_up/p_down 为先验锚（似然均匀 → posterior==prior）
    * ``belief.verdict/edge``：按新 posterior 重判
    * ``prob_bands.shape.prob_below/prob_above``：= 融合 p_down / p_up
    * ``distribution``（整块）与 ``prob_bands`` 价格边界：以融合 range_90 为中心、
      按宽度比 **等比例映射**（仿射，保持分位结构相对形状）

    三块齐备且区间可映射 → True（供写 ``blend_complete``）；否则 False（保持原值）。
    仅重算派生量，不改变任何权重/阈值/原始概率计算。
    """
    dist = d_blend.get("distribution")
    pb = d_blend.get("prob_bands")
    belief = d_blend.get("belief")
    if not (isinstance(dist, dict) and isinstance(pb, dict) and isinstance(belief, dict)):
        return False

    d_lo, d_hi = _fuse_pair2(d_range)
    f_lo, f_hi = _fuse_pair2(fused_range)
    if None in (d_lo, d_hi, f_lo, f_hi):
        return False
    d_half = (d_hi - d_lo) / 2.0
    f_half = (f_hi - f_lo) / 2.0
    if d_half <= 0 or f_half <= 0:
        return False
    scale = f_half / d_half
    d_center = (d_hi + d_lo) / 2.0
    f_center = (f_hi + f_lo) / 2.0

    def _map(x):
        return f_center + (x - d_center) * scale

    decimals = 3 if "JPY" in str(d_blend.get("pair", "")) else 5

    # ── distribution：整块等比例（quantiles + min/max/mean/std）──────────────
    q = dist.get("quantiles")
    if isinstance(q, dict):
        dist["quantiles"] = {
            k: (round(_map(v), decimals) if _fuse_num(v) is not None else v)
            for k, v in q.items()
        }
    for field in ("min", "max", "mean"):
        v = _fuse_num(dist.get(field))
        if v is not None:
            dist[field] = round(_map(v), decimals)
    v = _fuse_num(dist.get("std"))
    if v is not None:
        dist["std"] = round(abs(v * scale), decimals)

    # ── prob_bands：价格边界同一仿射映射 + prob_below/above 对齐融合口径 ─────
    for band in pb.get("bands") or []:
        if not isinstance(band, dict):
            continue
        for edge in ("price_lo", "price_hi"):
            v = _fuse_num(band.get(edge))
            if v is not None:
                band[edge] = round(_map(v), decimals)
    cur = pb.get("current")
    if isinstance(cur, dict):
        for edge in ("price_lo", "price_hi"):
            v = _fuse_num(cur.get(edge))
            if v is not None:
                cur[edge] = round(_map(v), decimals)
        lo, hi = _fuse_num(cur.get("price_lo")), _fuse_num(cur.get("price_hi"))
        price = _fuse_num(d_blend.get("current_price"))
        if None not in (lo, hi, price) and hi > lo:
            cur["position_in_band_pct"] = round(
                max(0.0, min(100.0, (price - lo) / (hi - lo) * 100.0)), 1
            )
    shape = pb.get("shape")
    if isinstance(shape, dict):
        shape["prob_below"] = round(fused_p_down, 1)
        shape["prob_above"] = round(fused_p_up, 1)
        sq = shape.get("quantiles")
        if isinstance(sq, dict):
            shape["quantiles"] = {
                k: (round(_map(v), decimals) if _fuse_num(v) is not None else v)
                for k, v in sq.items()
            }
        for field in ("mean", "median", "mode"):
            v = _fuse_num(shape.get(field))
            if v is not None:
                shape[field] = round(_map(v), decimals)

    # ── belief：以融合 p_up/p_down 重锚先验 → 后验（似然均匀）→ edge/verdict ─
    spread = abs(fused_p_up - fused_p_down) / 100.0
    d_regime = d_blend.get("regime_D", "")
    w_range = _fuse_w_range(d_regime)
    prior = _fuse_normalize({
        "UP": fused_p_up / 100.0,
        "DOWN": fused_p_down / 100.0,
        "RANGE": ((1.0 - spread) ** _FUSE_PRIOR_GAMMA) * w_range,
    })
    likelihood = {s: round(1.0 / len(_FUSE_STATES), 4) for s in _FUSE_STATES}
    belief["prior"] = {s: prior[s] for s in _FUSE_STATES}
    belief["posterior"] = {s: prior[s] for s in _FUSE_STATES}
    belief["likelihood"] = dict(likelihood)
    belief["evidence"] = [{
        "name": "regime",
        "value": d_regime,
        "spread": round(spread, 4),
        "likelihood": dict(likelihood),
    }]
    order = sorted(_FUSE_STATES, key=lambda s: prior[s], reverse=True)
    belief["edge"] = {
        "argmax": order[0],
        "value": round(prior[order[0]], 4),
        "spread": round(prior[order[0]] - prior[order[1]], 4),
    }
    tau = _fuse_num(belief.get("threshold_tau"))
    tau = _FUSE_THRESHOLD_TAU if tau is None else tau
    price = _fuse_num(d_blend.get("current_price"))
    range_pct = ((f_hi - f_lo) / price * 100.0) if (price and price > 0) else None
    narrow = range_pct is None or range_pct < _FUSE_MIN_WIDTH_PCT_GATE
    degenerate = bool(dist.get("degenerate", False)) or bool(pb.get("degenerate", False))
    belief["verdict"] = (
        "NO_EDGE"
        if (degenerate or narrow or prior[order[0]] < tau)
        else order[0]
    )
    return True


def cfg_mod(name, default):  # [OPT-12] was cfg(): shadowed `cfg = C.get_profile(...)`
    return getattr(config, name, default)


# [OPT-0] runtime switches: env OPT_<NAME> > profile/config OPT_<NAME> > default
def _opt(name, default):
    raw = os.getenv(f"OPT_{name}")
    if raw is not None:
        return raw.strip().lower() in ("1", "true", "yes", "on")
    return bool(cfg_bot(f"OPT_{name}", default))


# [OPT-0] 字符串运行时开关：env OPT_<NAME> > config OPT_<NAME> > default
def _opt_str(name, default):
    raw = os.getenv(f"OPT_{name}")
    if raw is not None and raw.strip():
        return raw.strip()
    return str(cfg_bot(f"OPT_{name}", default))


# Prob-route DATA-SOURCE switch. Default ON → prob_index reuses the already-loaded
# mc_cache (which Profile 2 has already W+D-blended) instead of re-reading the raw
# D JSON, so conv / risk_cap / entry-gate see the SAME fused record as the
# consensus layer. Set OPT_PROB_USE_FUSED=0 to fall back to the legacy raw-D read
# (pair-for-pair A/B control). Data source only — no threshold/weight changes.
PROB_USE_FUSED = _opt("PROB_USE_FUSED", True)

# ─── W+D FUSION WEIGHT MODE (Profile 2 only) ─────────────────────────────────
# 只改融合「加权公式」，不改原始 D/W p_up/p_down 计算、不改下单阈值/风控参数。
#   CONSERVATIVE_DECAY (默认): 分歧 ↑ ⇒ 信息质量 ↓ ⇒ 两边都少信
#       w_w = clip(BASE_W_WEIGHT − deviation×DECAY_RATE, MIN_W_WEIGHT, MAX_W_WEIGHT)
#       effective_confidence = 1 − deviation×CONFIDENCE_DECAY   ∈ [0.5, 1.0]
#       blend_position_scale = effective_confidence  (仅作乘子，不改 base_lot / 风控上限)
#   LEGACY_W_DOMINANT (对照): 旧行为 w_w = min(0.65 + deviation×0.6, 0.85), conf = 1.0
#     → 逐对精确复现修复前结果（误差 < 0.15pp）。
# 切换: env OPT_FUSION_WEIGHT_MODE 或 config OPT_FUSION_WEIGHT_MODE。
FUSION_WEIGHT_MODE = _opt_str("FUSION_WEIGHT_MODE", "CONSERVATIVE_DECAY")
BASE_W_WEIGHT = float(cfg_bot("BASE_W_WEIGHT", 0.55))     # W 基础先验：略偏长期
MAX_W_WEIGHT = float(cfg_bot("MAX_W_WEIGHT", 0.70))       # W 上限：避免单边主导
MIN_W_WEIGHT = float(cfg_bot("MIN_W_WEIGHT", 0.40))       # W 下限：分歧极大时略偏 D
DECAY_RATE = float(cfg_bot("DECAY_RATE", 0.30))           # 分歧→权重衰减（10%分歧 → −3%）
CONFIDENCE_DECAY = float(cfg_bot("CONFIDENCE_DECAY", 0.50))  # 分歧→信心衰减（10%分歧 → −5%）

# ─── INIT FOLDERS & LOGGING ──────────────────────────────────────────────────
RESULTS_DIR.mkdir(exist_ok=True)
TODAY_STR = datetime.now(timezone.utc).strftime("%Y%m%d")
# logger = get_logger(...)  # DEAD — superseded by top-level log = get_logger(__name__)

# ─── CONSOLIDATED STRATEGY CONSTANTS ─────────────────────────────────────────
TREND_TP_CONFIG = cfg_mod("TREND_TP_CONFIG", _TREND_TP_CONFIG)
# config_profile.json is the single source of truth for MIN_SLOPE. The
# _TREND_TP_CONFIG defaults above are only fallbacks, so overwrite the active
# profile's slope knob with the value the unified config actually declares
# (e.g. Profile2 = 0.0007). Without this, the hardcoded 0.001 silently won and
# the bot filtered on a stricter slope than the configured one.
_profile_slope_cfg = TREND_TP_CONFIG.setdefault(PROFILE_NAME, {})
_profile_slope_cfg.pop("min_slope_rung", None)
_profile_slope_cfg["min_slope"] = MIN_SLOPE
ACTIVE_MIN_SLOPE = resolve_min_slope(_profile_slope_cfg, PROFILE_NAME)
log.info(
    f"🪜 MIN_SLOPE LADDER: active rung={ACTIVE_MIN_SLOPE} "
    f"(ladder {MIN_SLOPE_LADDER}, widest first; last entry = original strictest)"
)
# ─── D-Gate CONFIG (from unified profile; directions computed per-run in main)
# D_GATE_ENABLED / D_GATE_SHADOW / D_GATE_BUFFER_PCT / D_GATE_CONFIRM are read
# from the active PROFILE dict by the unified loader above. The per-pair
# DIAG/SUMMARY block only runs when D_GATE_ENABLED is True (Profile3); Profile2
# skips it entirely — no compute, no logs.
D_GATE_EMA_FAST = cfg_bot("D_GATE_EMA_FAST", 20)
D_GATE_EMA_SLOW = cfg_bot("D_GATE_EMA_SLOW", 50)
# D_GATE_CONFIRM is a human label like "2H1" → 2 consecutive H1 closes.
# Fall back to the legacy numeric D_GATE_CONFIRM_BARS key when absent.
try:
    D_GATE_CONFIRM_BARS = int(str(D_GATE_CONFIRM).strip().lower().split("h")[0])
except (TypeError, ValueError):
    D_GATE_CONFIRM_BARS = cfg_bot("D_GATE_CONFIRM_BARS", 2)
# D_GATE_BUFFER_PCT is in percent (0.15) → convert to a fraction (0.0015).
D_GATE_MIN_BUFFER_PCT = D_GATE_BUFFER_PCT / 100.0
D_GATE_DIRECTIONS: dict[str, str] = {}  # populated in main(), keyed by yahoo pair
if D_GATE_ENABLED:
    mode = "SHADOW (log-only)" if D_GATE_SHADOW else "ACTIVE"
    log.info(
        f"🧭 D-GATE: {mode} | EMA{D_GATE_EMA_FAST}×EMA{D_GATE_EMA_SLOW} | "
        f"confirm={D_GATE_CONFIRM} | buffer={D_GATE_BUFFER_PCT:.2f}%"
    )
else:
    log.info("🧭 D-GATE: DISABLED — skipped entirely per profile config")
REQUIRE_DIRECTION_CONSENSUS = cfg_bot("REQUIRE_DIRECTION_CONSENSUS", True)
CONSENSUS_THRESHOLD = cfg_bot("CONSENSUS_THRESHOLD", 2)
XGB_BULLISH_THRESHOLD = cfg_bot("XGB_BULLISH_THRESHOLD", 0.55)
MC_BULLISH_THRESHOLD = cfg_bot("MC_BULLISH_THRESHOLD_PCT", 55.0)
# Symmetric bearish thresholds: a voter only casts SELL when it is genuinely
# bearish, otherwise it ABSTAINS (NEUTRAL). Previously every reading below the
# bullish threshold voted SELL, so a near-neutral voter (e.g. MC P_UP=54) still
# pushed the 3-voter consensus short — a structural bearish bias.
XGB_BEARISH_THRESHOLD = cfg_bot("XGB_BEARISH_THRESHOLD", 1.0 - XGB_BULLISH_THRESHOLD)
MC_BEARISH_THRESHOLD = cfg_bot("MC_BEARISH_THRESHOLD_PCT", 100.0 - MC_BULLISH_THRESHOLD)
# [MC-SCORE] MC factor amplification + regime amplitude modulation.
# M is a direction-aligned probability living in ~[39, 61], so on its own it
# moves FINAL by only ~1-2 pts (W_M=0.08). We amplify it around the 50 midline
# (dead-zone ±MC_M_DEADZONE suppresses noise) and then let the DIRECTIONLESS MC
# regime text scale its magnitude: momentum/overbought/oversold (edge present)
# -> ×1.0; consolidation/neutral (no edge) -> ×MC_REGIME_RANGE_MULT. The weight
# W_M itself is NOT changed. Set OPT_MC_REGIME_MOD=0 to disable only the regime
# part; set MC_M_GAIN=1.0 to restore the legacy unamplified M.
MC_M_GAIN = float(cfg_bot("MC_M_GAIN", 3.0))
MC_M_DEADZONE = float(cfg_bot("MC_M_DEADZONE", 3.0))
MC_REGIME_MOD = _opt("MC_REGIME_MOD", True)
MC_REGIME_RANGE_MULT = float(cfg_bot("MC_REGIME_RANGE_MULT", 0.7))
ADX_SCALE_FACTOR = cfg_bot("ADX_SCALE_FACTOR", 2.0)
ADX_FLOOR_ENABLED = cfg_bot("ADX_FLOOR_ENABLED", True)
ADX_MIN_SCORE = cfg_bot("ADX_MIN_SCORE", 20.0)
ADX_BOOST_ENABLED = cfg_bot("ADX_BOOST_ENABLED", True)
ADX_BOOST_THRESHOLD = cfg_bot("ADX_BOOST_THRESHOLD", 30.0)
ADX_BOOST_VALUE = cfg_bot("ADX_BOOST_VALUE", 10.0)

W_S = cfg_bot("WEIGHT_STRENGTH", 0.40)
W_R = cfg_bot("WEIGHT_RSI", 0.15)
W_G = cfg_bot("WEIGHT_TREND", cfg_bot("WEIGHT_G", 0.0))
W_A = cfg_bot("WEIGHT_ADX", 0.15)
W_X = cfg_bot("WEIGHT_XGB", 0.20)
W_M = cfg_bot("WEIGHT_MC", 0.10)

_TREND_G_ON = cfg_bot("TREND_G_ENABLED", False)
_TREND_G_ADX_MOD = cfg_bot("TREND_G_ADX_MODULATION", False)
if not _TREND_G_ON:
    W_G = 0.0

# G factor full-credit scale: the relative EMA_fast/EMA_slow separation that maps
# to 100. Live M15 EMA20/EMA50 gaps run ~0.05%–0.16% (see D-GATE DIAG logs), so
# 0.25% = full credit. The former `abs(_diff) * 500` capped G at ~0.8 for real
# data — i.e. a factor carrying a real weight that never contributed.
TREND_G_FULL_SCALE = cfg_bot("TREND_G_FULL_SCALE", 0.0025)

_WEIGHT_SUM = W_S + W_R + W_G + W_A + W_X + W_M
if abs(_WEIGHT_SUM - 1.00) > 0.001:
    log.warning(f"⚠️ Weight sum = {_WEIGHT_SUM:.4f} ≠ 1.00 — normalizing")
    weights = [w / _WEIGHT_SUM for w in [W_S, W_R, W_G, W_A, W_X, W_M]]
    W_S, W_R, W_G, W_A, W_X, W_M = weights
log.info(
    f"⚖️  {PROFILE_LABEL} WEIGHTS: S={W_S:.2f} R={W_R:.2f} G={W_G:.2f} A={W_A:.2f} X={W_X:.2f} M={W_M:.2f} | "
    f"TREND_G={_TREND_G_ON} ADX_MOD={_TREND_G_ADX_MOD}"
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
# Profile-derived values are authoritative: read them from the module-level
# names set by the unified loader, falling back to config_bot/config/default.
USE_TOP_PAIRS_ONLY = (
    USE_TOP_PAIRS_ONLY
    if USE_TOP_PAIRS_ONLY is not None
    else cfg_bot("USE_TOP_PAIRS_ONLY", STRATEGY_USE_TOP_PAIRS_ONLY)
)
TOP_N_CURRENCIES = (
    TOP_N_CURRENCIES
    if TOP_N_CURRENCIES is not None
    else cfg_bot("TOP_N_CURRENCIES", STRATEGY_TOP_N_CURRENCIES)
)
# Legacy alias kept for this file's own log lines/history.
TOP_PAIRS_COUNT = TOP_N_CURRENCIES
# MIN_GAP comes from the unified PROFILE (config_bot.PROFILES); TOP_PAIRS_MIN_GAP
# remains the top-pairs ranking gap from strategy_config.
TOP_PAIRS_MIN_GAP = (
    TOP_PAIRS_MIN_GAP
    if TOP_PAIRS_MIN_GAP is not None
    else cfg_bot("TOP_PAIRS_MIN_GAP", STRATEGY_TOP_PAIRS_MIN_GAP)
)
MIN_STRENGTH_GAP = (
    MIN_GAP
    if MIN_GAP is not None
    else cfg_bot("MIN_STRENGTH_GAP", STRATEGY_MIN_STRENGTH_GAP)
)
# ===========================================================
DEBUG_MODE = cfg_bot("DEBUG_MODE", False)
# 独立的斜率诊断开关：不挂在 DEBUG_MODE 上，避免为了拿 slope 分布
# 而连带把 oandapyV20 的 HTTP 日志放出来污染日志文件。
SLOPE_DIAG = SLOPE_DIAG if SLOPE_DIAG is not None else cfg_bot("SLOPE_DIAG", False)

MAX_SIMULTANEOUS_TRADES = MAX_OPEN  # from unified PROFILE (config_bot.PROFILES)
TRAILING_TP = cfg_bot("TRAILING_TP", False)
TRAILING_SL = cfg_bot("TRAILING_SL", False)
DYNAMIC_TP = cfg_bot("DYNAMIC_TP", False)

# ─── 持仓期自动改写 SL/TP（_revise_owned_position）总开关 ─────────────────────
# 该路径在浮盈 ≥15p 时把 SL 上移（结构位，上限夹到保本 entry±1pip），并把 TP 外扩到
# 现价 ±3×ATR —— 即目前唯一在跑的「跟随/保本」类退出逻辑。
# Owner 裁定（2026-11-18）默认【关闭】：硬抗（固定 SL/TP + 时间到期/方向翻转）更能
# 抵御区间震荡；跟踪止损另立课题，以后再评估。可逆：env OPT_REVISE_OWNED_POSITION=1
# 或 config_profile.json 的 OPT_REVISE_OWNED_POSITION=true 即恢复。
REVISE_OWNED_POSITION = _opt("REVISE_OWNED_POSITION", False)
if not REVISE_OWNED_POSITION:
    log.info(
        "🛑 REVISE-OWNED-POSITION: DISABLED — 持仓期不再自动上移 SL / 外扩 TP "
        "(固定 SL/TP 硬抗；恢复请设 OPT_REVISE_OWNED_POSITION=1)"
    )

# ─── L2 风险定额仓位（risk-parity sizing）总开关 ──────────────────────────────
# units ∝ 风险预算 / SL_pips：把「结构 SL 比 ATR 应然更宽」的笔数按比例缩量，使每笔
# SL 的美元亏损大致定额（削尾）。只缩不放大（rp_mult ∈ [RP_F_LO, 1.0]），与 prob
# overlay 的 size_units 相乘互补。Owner 拍板（2026-11-18）先走【影子】：
#   False（默认）= 只落盘 logs/sizing_shadow_*.jsonl，不改任何下单决策
#   True          = 把 size_units 换成 units_l2（生效）
# 详见 docs/NEXT_DEV_PLAN_20261117.md §2.1，可逆：OPT_RISK_PARITY_SIZING=1。
RISK_PARITY_SIZING = _opt("RISK_PARITY_SIZING", False)
log.info(
    "🎯 RISK-PARITY SIZING: "
    + (
        "ON (size_units ← units_l2)"
        if RISK_PARITY_SIZING
        else "OFF (shadow only → logs/sizing_shadow_*.jsonl)"
    )
)

# ─── §3 宽幅震荡判别（wide-range shadow）总开关 ───────────────────────────────
# ATR_pct = 当日 ATR / 近 20 日 ATR 的 rolling 中位 → narrow(<0.8)/normal/wide(≥1.3)。
# 本轮**只落盘**、不改任何决策（Owner 纪律 §5.5）：
#   True（默认）= 逐候选落盘 logs/wide_range_shadow_*.jsonl（额外一次只读日线拉取）
#   False        = 完全跳过（不发请求、不落盘）
# 详见 docs/NEXT_DEV_PLAN_20261117.md §3.1，可逆：OPT_WIDE_RANGE_SHADOW=0。
WIDE_RANGE_SHADOW = _opt("WIDE_RANGE_SHADOW", True)
log.info(
    "📏 WIDE-RANGE SHADOW: "
    + (
        "ON (shadow only → logs/wide_range_shadow_*.jsonl)"
        if WIDE_RANGE_SHADOW
        else "OFF"
    )
)

# ─── MC 概率带边界观察（只观察 · 不改仓位）────────────────────────────────────
# 监控当前生效 prob_bands.bands[] 的四条内部边界（Q20/Q40/Q60/Q80），用已完成
# M15 的 high/low + 前一根 close 判定 touch / cross；不读取静态 prob_bands.current，
# 不改变任何下单/仓位决策。落盘 logs/mc_boundary_watch_*.jsonl。
#   True （默认）= 开启观察
#   False        = 完全跳过（不落盘）
# 可逆：OPT_MC_BOUNDARY_WATCH=0。
MC_BOUNDARY_WATCH = _opt("MC_BOUNDARY_WATCH", True)
log.info(
    "🎯 MC-BOUNDARY WATCH: "
    + (
        "ON (observe only → logs/mc_boundary_watch_*.jsonl)"
        if MC_BOUNDARY_WATCH
        else "OFF"
    )
)

# ─── 动态 MAX_OPEN（波动率档驱动 · 仅 Profile 2）──────────────────────────────
# 按全组合 ATR_pct 中位数的波动率档收紧**并发持仓上限**这一个旋钮：
#   wide / extreme → base − 2（地板 MIN_OPEN=1）；narrow / normal / unknown → base。
# 只改 MAX_OPEN，不动任何下单/仓位/信号逻辑；数据缺失一律回退 base。
#   默认：Profile 2 = ON，其余 profile = OFF。
#   可逆：OPT_MAX_OPEN_DYNAMIC=0/1 覆盖。
MAX_OPEN_DYNAMIC = _opt("MAX_OPEN_DYNAMIC", PROFILE_ID == 2)
log.info(
    f"📐 MAX_OPEN DYNAMIC: {'ON' if MAX_OPEN_DYNAMIC else 'OFF'} "
    f"(profile={PROFILE_ID}, base={MAX_OPEN})"
)

MULTI_TF_CONFLUENCE = cfg_bot("MULTI_TF_CONFLUENCE", False)
CONFLUENCE_REQUIRED_TFS = cfg_bot("CONFLUENCE_REQUIRED_TFS", 2)
TP_RAISE_THRESHOLD_PIPS = cfg_bot("TP_RAISE_THRESHOLD_PIPS", 15)

# ─── 补仓 / 金字塔加仓（pyramiding · averaging-down）总开关 ───────────────────
# 当某 pair 已有同向持仓、且仓位 < 标准仓（base_lot）、且现价套牢（underwater）、
# 且本次开仓条件仍满足时，允许追加一单把总仓位抬到下一个 SIZE_LADDER 档位。
# 与「只缩不放」的归一化互补：归一化只缩，补仓只在套牢时加仓，且永不超过 base_lot。
#   False（默认）= 关闭，保持原 SKIP DUPLICATE 行为
#   True          = 开启补仓（受 PYRAMID_MAX_LEVELS / PYRAMID_UNDERWATER_PIPS 约束）
# 可逆：OPT_PYRAMID_ENABLED=1。
PYRAMID_ENABLED = _opt("PYRAMID_ENABLED", False)
PYRAMID_MAX_LEVELS = cfg_bot("PYRAMID_MAX_LEVELS", 1)  # 最多补仓次数（不含首单）
PYRAMID_UNDERWATER_PIPS = cfg_bot("PYRAMID_UNDERWATER_PIPS", 0.0)  # 套牢多少 pips 才补
log.info(
    "🔺 PYRAMID (补仓): "
    + (
        f"ON | max_levels={PYRAMID_MAX_LEVELS} | underwater>={PYRAMID_UNDERWATER_PIPS}p"
        if PYRAMID_ENABLED
        else "OFF (SKIP DUPLICATE preserved)"
    )
)

# ─── CLI MODE OVERRIDES ──────────────────────────────────────────────────────
# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ MODE SEMANTICS (v6.8.3.5 AUTHORITATIVE POLICY):                        ║
# ║                                                                          ║
# ║ ① --live  selects the BROKER ACCOUNT:                                   ║
# ║      OFF (default) → always connect Practice/Demo environment          ║
# ║      ON              → connect LIVE real-money environment            ║
# ║      This flag has NOTHING to do with whether orders are sent.         ║
# ║                                                                          ║
# ║ ② DRY_RUN controls the EXECUTION GATE (whether mutating OANDA        ║
# ║      write calls are issued). Resolution priority:                    ║
# ║        CLI (--dry-run / --no-dry-run) > run.env DRY_RUN > default(true)║
# ║      ON (default) → FULL pipeline runs end-to-end (all reads +        ║
# ║                       evaluations), but EVERY mutating call           ║
# ║                       (Open / Close / SL update / TP update) is       ║
# ║                       short-circuited into a 🧪 DRY_RUN log.          ║
# ║      OFF          → Open orders are SENT to OANDA.                    ║
# ║      Read-only calls (get_open_position / OpenTrades / AccountDetails /║
# ║      PricingInfo / Candles / PositionDetails) are ALWAYS allowed,     ║
# ║      regardless of DRY_RUN, so the pipeline can still see real        ║
# ║      positions/prices when dry-run is used on the LIVE account.       ║
# ║                                                                          ║
# ║ ③ Combined behaviours (4 valid combos):                                ║
# ║   (neither flag)     Practice/Demo env + real order execution         ║
# ║   --dry-run only      Practice/Demo env + full pipeline + NO writes   ║
# ║   --live only         LIVE real env   + real order execution         ║
# ║   --live --dry-run    LIVE real env   + full pipeline + NO writes    ║
# ║     (Portfolio Observer pattern — inspect LIVE state safely)          ║
# ║   NOTE: before v6.8.3.6 the ENTRY path was wrongly gated on --live    ║
# ║   (not DRY_RUN), so combos 1/2 could never send orders. Fixed.        ║
# ╚══════════════════════════════════════════════════════════════════════════╝
MODE = cfg_bot("MODE", "LEVEL10")
TIMEFRAME = args.timeframe

# ── 1) Broker account selection driven SOLELY by --live (never by --dry-run)
LIVE_ACCOUNTS = {
    1: OANDA_ACCOUNT_ID_1_LIVE,
    2: OANDA_ACCOUNT_ID_2_LIVE,
    3: OANDA_ACCOUNT_ID_3_LIVE,
    4: OANDA_ACCOUNT_ID_4_LIVE,
}
DEMO_ACCOUNTS = {
    1: OANDA_ACCOUNT_ID_DEMO_1,
    2: OANDA_ACCOUNT_ID_DEMO_2,
    3: OANDA_ACCOUNT_ID_DEMO_3,
    4: OANDA_ACCOUNT_ID_DEMO_4,
}
LIVE_MODE = bool(args.live)  # False = Practice/Demo; True = LIVE
if args.account is not None:
    try:
        _account_index = int(args.account)
    except ValueError:
        parser.error(
            f"-a/--account must be an account number from 1 to 4; got {args.account!r}"
        )
    _account_map = LIVE_ACCOUNTS if LIVE_MODE else DEMO_ACCOUNTS
    _account_override = _account_index
else:
    _account_map = None
    _account_override = None
try:
    OANDA_ACCOUNT_ID, _account_source = C.resolve_account_id(
        PROFILE_ID,
        LIVE_MODE,
        account_override=_account_override,
        indexed_accounts=_account_map,
    )
except ValueError as exc:
    parser.error(str(exc))

_ENV_LABEL = "LIVE" if LIVE_MODE else "DEMO"
_cfg_lot = cfg_bot("DEFAULT_LOT_SIZE", 10000)
_lot_source = "config"
DEFAULT_LOT_SIZE = _cfg_lot
_env_lot_key = "LIVE_LOT_SIZE" if LIVE_MODE else "DEMO_LOT_SIZE"
_env_lot_raw = os.getenv(_env_lot_key)
if _env_lot_raw is not None:
    try:
        DEFAULT_LOT_SIZE = int(_env_lot_raw)
        _lot_source = f"run.env [{_env_lot_key}]"
    except ValueError:
        pass
if args.lots is not None:
    DEFAULT_LOT_SIZE = args.lots
    _lot_source = "CLI --lots"
log.info(f"⚙️ Profile: {PROFILE_ID}")
log.info(f"🔑 Account: {_account_source} → {OANDA_ACCOUNT_ID} [{_ENV_LABEL}]")
log.info(f"📦 Lot size: {DEFAULT_LOT_SIZE}  (source: {_lot_source})")

# The minimum probability-factor rung is environment-specific.
_MIN_LOT_KEY = "MIN_LOT_LIVE" if LIVE_MODE else "MIN_LOT_DEMO"
PROB_ZONE_CFG["MIN_LOT"] = PROB_ZONE_CFG.get(_MIN_LOT_KEY, 1 if LIVE_MODE else 1000)
log.info(
    f"🎚️ Probability min lot: {PROB_ZONE_CFG['MIN_LOT']} units [{_ENV_LABEL}]"
)

_prof = get_oanda_profile("live" if LIVE_MODE else "practice")
api = _prof["oanda_client"]

_ACCT_SUFFIX = (
    OANDA_ACCOUNT_ID.split("-")[-1] if "-" in OANDA_ACCOUNT_ID else OANDA_ACCOUNT_ID
)
ACCOUNT_NAME = f"{_ENV_LABEL} Account {_ACCT_SUFFIX}"

# // FIX-2026-10-10: single consolidated replacement for the 6 chatter lines the
# third-party logger used to emit (and which always claimed "practice"). This
# line reports the environment actually in use, so --live is never mislabelled.
log.info(
    f"🌐 OANDA API client: environment={_prof['env']} | "
    f"account={OANDA_ACCOUNT_ID} | ({_ENV_LABEL})"
)

# ── 2) Execution gate: CLI (--dry-run / --no-dry-run) > run.env DRY_RUN > default(true)
# Requirement #2: "--dry-run和账号没有关系。跑完全程只是不操作OANDA的
#                 open,close,update操作。get info还是可以的"
# NOTE (v6.8.3.6): this gate previously read ONLY args.dry_run while the actual
#                  order path was gated on LIVE_MODE (line ~1515), so run.env's
#                  DRY_RUN was silently ignored AND the RUN MODE banner could
#                  claim "EXECUTE" while every order was still suppressed.
#                  Both are now unified on DRY_RUN_MODE below.
_DRY_RUN_ENV_RAW = os.getenv("DRY_RUN", "true").strip()
_DRY_RUN_ENV = _DRY_RUN_ENV_RAW.lower() in ("1", "true", "yes", "on")
if args.dry_run is None:
    DRY_RUN_MODE = _DRY_RUN_ENV  # no CLI flag → run.env DRY_RUN (default: true)
    _dry_run_source = f"env DRY_RUN={_DRY_RUN_ENV_RAW or '<unset→true>'}"
else:
    DRY_RUN_MODE = bool(args.dry_run)  # CLI wins in BOTH directions
    _dry_run_source = "CLI --dry-run" if args.dry_run else "CLI --no-dry-run"
log.info(
    f"🚦 EXECUTION GATE: DRY_RUN={DRY_RUN_MODE} (source: {_dry_run_source}) | "
    f"account env selected solely by --live={'ON' if args.live else 'OFF'}"
)
# [OPT-13] real money + real orders: demand an explicit env acknowledgement
if (
    LIVE_MODE
    and not DRY_RUN_MODE
    and _opt("REQUIRE_LIVE_CONFIRM", False)
    and os.getenv("CONFIRM_LIVE") != "YES"
):
    parser.error(
        "LIVE + EXECUTE blocked: set CONFIRM_LIVE=YES (OPT_REQUIRE_LIVE_CONFIRM is on)"
    )
if DRY_RUN_MODE:
    log.info(
        "🧪 DRY_RUN MODE | Full pipeline will run; ONLY "
        "mutating OANDA calls (Open/Close/SL/TP update) are suppressed; "
        "ALL read-only calls (positions, prices, candles, account info) "
        "still execute normally."
    )
# CLI -p/--max-entries overrides the unified PROFILE's MAX_ENTRIES_THIS_RUN.
MAX_ENTRIES = args.max_entries if args.max_entries is not None else MAX_ENTRIES_THIS_RUN
OANDA_GRANULARITY_MAP = {"15m": "M15", "1H": "H1", "H4": "H4", "D": "D"}
OANDA_GRANULARITY = OANDA_GRANULARITY_MAP.get(TIMEFRAME, "H4")

# Build run mode banner from TWO INDEPENDENT AXES (account env × execution gate)
_env_label = (
    f"🔴 LIVE-ENV Account={OANDA_ACCOUNT_ID}"
    if LIVE_MODE
    else f"🧪 DEMO-ENV Account={OANDA_ACCOUNT_ID}"
)
_exec_label = (
    "DRY_RUN (NO Open/Close/SL-update/TP-update writes)"
    if DRY_RUN_MODE
    else "EXECUTE (mutating OANDA write calls ALLOWED)"
)
_run_mode_label = f"{_env_label} | {_exec_label}"
_max_entries_label = f"{MAX_ENTRIES}" if MAX_ENTRIES else "unlimited (within MAX_OPEN)"
log.info(
    f"🖥️  RUN MODE: {_run_mode_label} | MAX_OPEN={MAX_OPEN} | "
    f"MAX_ENTRIES_THIS_RUN={_max_entries_label}"
)
# ═════════════ 结构化日志初始化 ═════════════
json_log = StructuredLogger(PROFILE_LABEL)

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
# Phase‑1: OANDA native names — identity fallback
_YAHOO_TO_OANDA_DEFAULT = {
    "EUR_USD": "EUR_USD",
    "GBP_USD": "GBP_USD",
    "AUD_USD": "AUD_USD",
    "USD_CHF": "USD_CHF",
    "USD_JPY": "USD_JPY",
    "EUR_JPY": "EUR_JPY",
    "GBP_JPY": "GBP_JPY",
    "AUD_JPY": "AUD_JPY",
}
YAHOO_TO_OANDA = cfg_bot("YAHOO_TO_OANDA", _YAHOO_TO_OANDA_DEFAULT.copy())
for _sym, _oanda in _YAHOO_TO_OANDA_DEFAULT.items():
    YAHOO_TO_OANDA.setdefault(_sym, _oanda)
log.info(f"✅ Pair mappings loaded: {len(YAHOO_TO_OANDA)} entries")

# ─── PAIR WHITELIST + DISJOINT SAFETY LOCK ───────────────────────────────────
# Whitelist (Ownership Tag) comes from the unified PROFILE dict. Profiles now
# share pairs (P3 includes P2's JPY bucket), so the whitelist is a universe
# filter only — it is no longer treated as an error if two profiles overlap.
ALLOWED_PAIRS = (
    ALLOWED_PAIRS if ALLOWED_PAIRS is not None else cfg_bot("ALLOWED_PAIRS", None)
)
if ALLOWED_PAIRS is not None:
    _known = set(YAHOO_TO_OANDA.keys())
    _invalid = [p for p in ALLOWED_PAIRS if p not in _known]
    if _invalid:
        log.warning(
            f"⚠️  ALLOWED_PAIRS contains unknown symbols (will be ignored): {_invalid} "
            f"— valid set: {sorted(_known)}"
        )
    ALLOWED_PAIRS = [p for p in ALLOWED_PAIRS if p in _known]
    log.info(
        f"🔒 WHITELIST [{PROFILE_LABEL}] active = {len(ALLOWED_PAIRS)} pairs | "
        f"ALLOWED: {ALLOWED_PAIRS}"
    )
else:
    log.info(
        "ℹ️  No ALLOWED_PAIRS set — full 8-pair pool enabled (no whitelist filter)"
    )

MC_MAX_AGE_HOURS = cfg_bot("MC_MAX_AGE_HOURS", 24)
SIMULATIONS = cfg_bot("MC_SIMULATIONS", 5000)
CONFIDENCE = cfg_bot("MC_BAND_PCT", 90) / 100.0
REMOVE_COOLDOWN = cfg_bot("REMOVE_COOLDOWN", False)
COOLDOWN_HOURS_AFTER_TP = cfg_bot("COOLDOWN_HOURS_AFTER_TP", 0.0)
DIRECTION_FLIP_EXIT_ENABLED = cfg_bot("DIRECTION_FLIP_EXIT_ENABLED", True)
COOLDOWN_SCOPE = os.environ.get("COOLDOWN_SCOPE", cfg_bot("COOLDOWN_SCOPE", "currency"))
log.info(
    f"⏳ TP-COOLDOWN: hours={COOLDOWN_HOURS_AFTER_TP} "
    f"REMOVE_COOLDOWN={REMOVE_COOLDOWN} scope={COOLDOWN_SCOPE}"
)
log.info(f"🔄 DIRECTION-FLIP EXIT: enabled={DIRECTION_FLIP_EXIT_ENABLED}")
if COOLDOWN_SCOPE == "currency" and _opt("LEGACY_SCOPE_WARNING", False):  # [OPT-2]
    log.warning(
        "⚠️  COOLDOWN_SCOPE=currency (default) — cooldown matches on bare 3-letter "
        "currency codes (e.g. JPY), which blocks ALL JPY pairs after any TP. "
        "If you want cooldown to be pair-specific (recommended), set "
        "COOLDOWN_SCOPE=pair in config_profile.json or env."
    )
if args.confluence is not None:
    MULTI_TF_CONFLUENCE = args.confluence

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
min_conv = MIN_CONVICTION  # from unified PROFILE (config_bot.PROFILES)
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
# Model stem override — FX_BOT_MODEL_STEM=models_fcv2/trade_model_xgb points this
# process at a separate artifact set without touching the default
# trade_model_xgb.* used by the live leg.  Default unchanged (reversible).
MODEL_PATH = BASE_DIR / f"{os.getenv('FX_BOT_MODEL_STEM', 'trade_model_xgb')}.pkl"
# Phase 3.0 §5.2: the live runtime constructs the wrapper read-only, so no live
# code path can train or write / republish model artifacts.  ensure_model()
# re-asserts this as defence-in-depth.  Offline training (retrain_model.py)
# constructs its own writable wrapper and is unaffected.
model_wrapper = ModelWrapper(FEAT_CFG, model_path=MODEL_PATH, read_only=True)


# ─── [OPT-14] Phase 3.2 Feature Contract v2 (reversible, default OFF) ────────
# When ON, each per-pair feature frame is built by the Phase 3.2 Feature Contract
# (ml/feature_contract.py) instead of the legacy FeatureEngine. Default OFF keeps
# the shipped runtime path byte-identical. The contract emits a DIFFERENT ordered
# schema than the legacy engine, so it requires a model artifact whose feature
# list matches it; otherwise the downstream matrix build fails closed rather than
# silently misaligning columns. No silent fallback: contract errors propagate.
USE_FEATURE_CONTRACT_V2 = _opt("USE_FEATURE_CONTRACT_V2", False)


def _build_pair_features(raw):
    """Per-pair feature frame: legacy FeatureEngine by default, Phase 3.2 Feature
    Contract behind USE_FEATURE_CONTRACT_V2 (lazy import; fail-closed)."""
    if USE_FEATURE_CONTRACT_V2:
        from ml.feature_contract import build_features as _contract_build

        feats = _contract_build(raw)
        # The Feature Contract frame carries ONLY the 33 ordered feature columns —
        # no OHLC/Volume. The bot's non-ML consumers still expect OHLC on the SAME
        # frame: pivot resample (_eval_pivots -> _resample_daily: Open/High/Low/
        # Close/Volume), the last-close fallback (pair_data[pair]["df"]["Close"]),
        # and evaluate_trend_and_tp (df["Close"]). Re-attach the raw OHLCV columns
        # so those paths work unchanged. The ML path selects columns BY NAME
        # (predict_p_up -> _build_matrix -> X[feature_list]), so the extra columns
        # are ignored there — the 33-feature vector is unchanged.
        ohlcv = raw.reindex(feats.index)[["Open", "High", "Low", "Close", "Volume"]]
        return feats.join(ohlcv)
    return feat_engine.build(raw)


last_closed = {} if REMOVE_COOLDOWN else load_cooldown(COOLDOWN_FILE, Direction)


# ─── COOLDOWN HELPERS (v71-aligned) ──────────────────────────────────────────
# State format is owned by fx_trade_bot_utils_v1: {key: (Direction, until_ts)}
# with until_ts an ABSOLUTE UTC epoch (float). load_cooldown(), the TP-close
# writer and refresh_tp_cooldown_from_recent_tx() all agree on that shape, so
# the helpers below only ever read element [1] — never a bare float.
def save_cooldown_state(state: dict):
    """Persist the cooldown state (no-op when there is nothing to persist)."""
    if REMOVE_COOLDOWN or not state:
        return
    try:
        save_cooldown(COOLDOWN_FILE, state)
        log.info(
            f"💾 Cooldown saved: {len(state)} instrument(s) → {COOLDOWN_FILE.name}"
        )
    except Exception as e:
        log.warning(f"⚠️ save_cooldown failed: {e!s}")


def _cooldown_probe_keys(pair: str, oanda_instrument: str) -> list[str]:
    """Keys to probe for cooldown — pair-level only.

    Canonical key is ``oanda_instrument`` (e.g. ``EUR_USD``).  ``pair``
    (Yahoo symbol, e.g. ``EURUSD=X``) is probed as a secondary alias so
    persisted state from older pair-level writes still works.

    Bare ISO currency keys (``EUR``, ``USD``) are intentionally excluded.
    A TP close on ``EUR_USD`` must never block ``EUR_GBP`` or ``GBP_USD``.
    """
    keys: list[str] = [oanda_instrument, pair]
    seen: set[str] = set()
    out: list[str] = []
    for k in keys:
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out


def cooldown_key(pair: str, oanda_instrument: str) -> str:
    """Return the canonical cooldown key (oanda_instrument).

    Kept for API compatibility with any external callers.  The canonical
    pair-level key (e.g. ``EUR_USD``) is always returned."""
    return oanda_instrument


def is_in_cooldown(pair: str, oanda_instrument: str):
    """Return (in_cooldown, remaining_minutes, matched_key).

    Probes pair-level canonical key (oanda_instrument) only.  Bare
    currency keys are intentionally not probed — a TP close on ``EUR_USD``
    must not block ``EUR_GBP``.  Auto-cleans expired entries and legacy
    bare-currency keys from the old implementation.
    """
    now_ts = datetime.now(timezone.utc).timestamp()
    best_key, best_remain = None, float("inf")
    for key in _cooldown_probe_keys(pair, oanda_instrument):
        if key not in last_closed:
            continue
        until_ts = last_closed[key][1]
        remain_sec = until_ts - now_ts
        if remain_sec > 0:
            if remain_sec < best_remain:
                best_remain = remain_sec
                best_key = key
        else:
            del last_closed[key]
            log.debug(f"🧹 Expired cooldown removed: {key}")
    for _k in list(last_closed.keys()):
        if "_" not in _k and len(_k) == 3 and _k.isalpha():
            del last_closed[_k]
            log.debug(f"🧹 Legacy bare-currency cooldown cleaned: {_k}")
    if best_key is not None:
        return True, round(best_remain / 60.0, 1), best_key
    return False, 0.0, None


def set_cooldown(pair: str, oanda_instrument: str):
    """Lock the pair (OANDA instrument key) for COOLDOWN_HOURS_AFTER_TP.

    Keyed per PAIR (e.g. ``EUR_USD``).  A TP close on one instrument blocks
    only that instrument.  Crosses sharing a currency remain independently
    eligible under their own entry rules.
    """
    if COOLDOWN_HOURS_AFTER_TP <= 0 or REMOVE_COOLDOWN:
        return
    # [OPT-3] a dry-run "entry" is not a trade; locking the pair here is saved to
    # disk at the end of main() and then blocks the next REAL run.
    if DRY_RUN_MODE and not _opt("DRYRUN_PERSIST_COOLDOWN", False):
        log.info(
            f"🧪 DRY_RUN: cooldown NOT set for {oanda_instrument} "
            f"(would lock {COOLDOWN_HOURS_AFTER_TP}h)"
        )
        return
    expire_ts = datetime.now(timezone.utc).timestamp() + COOLDOWN_HOURS_AFTER_TP * 3600
    last_closed[oanda_instrument] = (Direction.NONE, expire_ts)
    log.info(
        f"⏳ COOLDOWN SET: {oanda_instrument} locked until "
        f"{datetime.fromtimestamp(expire_ts, tz=timezone.utc).strftime('%H:%M UTC')} "
        f"({COOLDOWN_HOURS_AFTER_TP}h)"
    )


def clear_cooldown(pair: str, oanda_instrument: str):
    """REMOVE_COOLDOWN=True branch: drop the pair's cooldown entries."""
    removed = [k for k in (oanda_instrument, pair) if last_closed.pop(k, None)]
    if removed:
        log.info(f"♻️ COOLDOWN REMOVED: {', '.join(removed)}")


# ── 启动时加载持久化 + 从最近交易刷新 TP 触发的 cooldown ──
if REMOVE_COOLDOWN:
    log.info("⏳ Cooldown load: SKIPPED — REMOVE_COOLDOWN=True (state starts empty)")
elif COOLDOWN_HOURS_AFTER_TP > 0:
    try:
        _loaded_count = len(last_closed)
        log.info(f"📂 Cooldown loaded: {_loaded_count} persisted entries")
        refresh_tp_cooldown_from_recent_tx(
            api,
            OANDA_ACCOUNT_ID,
            COOLDOWN_HOURS_AFTER_TP,
            last_closed,
            Direction=Direction,
        )
        log.info(
            f"📂 Cooldown refreshed from recent trades: +{len(last_closed) - _loaded_count}"
        )
    except Exception as _e:
        log.warning(f"⚠️ Cooldown refresh failed: {_e!s}")
else:
    log.info("⏳ Cooldown load: SKIPPED — COOLDOWN_HOURS_AFTER_TP=0 (feature off)")


# ── P0 · 退出可观测性（只读影子）：冷启动补录券商侧 SL/TP 平仓 ──
# profile_*.jsonl 只记自平仓（TIME_EXPIRY / DIRECTION_FLIP），券商侧
# STOP_LOSS_ORDER / TAKE_PROFIT_ORDER 从不落盘。此处从 OANDA 补录，只写日志、
# 不参与任何决策。
try:
    _audit = audit_owned_closed_trades(
        api,
        OANDA_ACCOUNT_ID,
        OWNER_CLIENT_EXT_ID,
        OWNER_CLIENT_EXT_TAG,
        LOGS_DIR,
        results_dir=RESULTS_DIR,
        profile_name=PROFILE_NAME,
    )
    log.info(
        f"🧾 EXIT-AUDIT cold-start: scanned={_audit.get('scanned')} "
        f"owned={_audit.get('owned')} new={_audit.get('new')} "
        f"[TP={_audit.get('tp')} SL={_audit.get('sl')} ACTIVE={_audit.get('active')}]"
    )
except Exception as _e:
    log.warning(f"⚠️ EXIT-AUDIT cold-start failed: {_e!s}")


# ─── HELPER: TOP-N STRENGTH PAIR BUILDER ─────────────────────────────────────
def build_top_pairs(
    strength_scores,
    all_pairs,
    oanda_map,
    top_n=TOP_N_CURRENCIES,
    min_gap=TOP_PAIRS_MIN_GAP,
    whitelist=None,
):
    """Build OANDA-native candidates from the strongest × weakest matrix."""
    ranked = sorted(strength_scores.items(), key=lambda x: x[1], reverse=True)
    strongest = [ccy for ccy, _ in ranked[:top_n]]
    weakest = [ccy for ccy, _ in ranked[-top_n:]]

    log.info(f"🏆 STRONGEST {top_n}: {strongest}")
    log.info(f"📉 WEAKEST  {top_n}: {weakest}")

    def normalize_pair(pair):
        symbol = pair.strip().upper()
        if symbol.endswith("=X"):
            symbol = symbol[:-2]
        symbol = symbol.replace("_", "").replace("/", "")
        if len(symbol) != 6:
            return None
        return f"{symbol[:3]}_{symbol[3:]}"

    all_pairs_normalized = {
        normalized
        for pair in all_pairs
        if (normalized := normalize_pair(pair)) is not None
    }
    whitelist_normalized = (
        None
        if whitelist is None
        else {
            normalized
            for pair in whitelist
            if (normalized := normalize_pair(pair)) is not None
        }
    )
    oanda_map_normalized = {
        normalized: instrument
        for pair, instrument in oanda_map.items()
        if (normalized := normalize_pair(pair)) is not None
    }

    generated = []
    rejected = []
    for strong in strongest:
        for weak in weakest:
            if strong == weak:
                rejected.append(f"{strong}/{weak}: same currency")
                continue
            gap_base_positive = strength_scores[strong] - strength_scores[weak]
            if abs(gap_base_positive) < min_gap:
                rejected.append(
                    f"{strong}/{weak}: gap {gap_base_positive:+.3f} "
                    f"below min_gap {min_gap:.3f}"
                )
                continue
            for base, quote in [(strong, weak), (weak, strong)]:
                yahoo_sym = f"{base}{quote}=X"
                generated.append(
                    {
                        "raw": yahoo_sym,
                        "pair": normalize_pair(yahoo_sym),
                        "base": base,
                        "quote": quote,
                    }
                )

    log.info(f"🧩 Top-{top_n} generated candidates: {[c['raw'] for c in generated]}")
    log.info(
        "🔄 Top-%s normalized candidates: %s",
        top_n,
        [(c["raw"], c["pair"]) for c in generated],
    )

    candidates = []
    whitelist_matches = []
    mapping_hits = []
    seen = set()
    for candidate in generated:
        pair = candidate["pair"]
        if pair is None:
            rejected.append(f"{candidate['raw']}: invalid pair format")
        elif pair not in all_pairs_normalized:
            rejected.append(f"{candidate['raw']} → {pair}: not in ALL_PAIRS")
        elif whitelist_normalized is not None and pair not in whitelist_normalized:
            rejected.append(f"{candidate['raw']} → {pair}: not in whitelist")
        else:
            if pair not in whitelist_matches:
                whitelist_matches.append(pair)
            oanda_inst = oanda_map_normalized.get(pair)
            if not oanda_inst:
                rejected.append(f"{candidate['raw']} → {pair}: missing OANDA mapping")
            elif pair in seen:
                rejected.append(
                    f"{candidate['raw']} → {pair}: duplicate normalized pair"
                )
            else:
                seen.add(pair)
                mapping_hits.append((pair, oanda_inst))
                pair_gap = (
                    strength_scores[candidate["base"]]
                    - strength_scores[candidate["quote"]]
                )
                candidates.append(
                    {
                        "pair": pair,
                        "oanda": oanda_inst,
                        "gap": pair_gap,
                        "gap_abs": abs(pair_gap),
                    }
                )

    candidates.sort(key=lambda x: x["gap_abs"], reverse=True)
    selected = [c["pair"] for c in candidates]

    log.info(f"🔒 Top-{top_n} whitelist matches: {whitelist_matches}")
    log.info(f"🗺️ Top-{top_n} mapping hits: {mapping_hits}")
    log.info(f"🚫 Top-{top_n} rejected candidates: {rejected}")
    log.info(f"🎯 Top-{top_n} matrix → {len(selected)} qualified pairs")
    for c in candidates[:6]:
        dir_s = "BUY" if c["gap"] > 0 else "SELL"
        log.info(f"   {c['pair']}: gap={c['gap']:+.3f} → {dir_s}")

    return selected, candidates


def _mc_regime_factor(regime_str: str) -> float:
    """Directionless amplitude modifier derived from the MC regime text.

    The regime hint carries NO sign — it only tells us whether price is in a
    trending/momentum state (an edge is present) or a consolidation/neutral
    state (no edge). So it scales M's magnitude rather than voting a direction:
    momentum / overbought / oversold -> 1.0 (keep full amplitude);
    consolidation / range / neutral  -> MC_REGIME_RANGE_MULT (attenuate).
    Unrecognised text (incl. P2's fused label) also returns 1.0 — we never
    invent attenuation we cannot justify from the hint.
    """
    if not MC_REGIME_MOD:
        return 1.0
    s = (regime_str or "").upper()
    if "MOMENTUM" in s or "OVERBOUGHT" in s or "OVERSOLD" in s:
        return 1.0
    if "CONSOLIDATION" in s or "RANGE" in s or "NEUTRAL" in s:
        return MC_REGIME_RANGE_MULT
    return 1.0


def calc_weighted_score(
    pair: str,
    gap: float,
    rsi_val: float,
    adx_val: float,
    xgb_prob: float,
    mc_pct_up: float,
    closes=None,
    regime_str: str = "",
):
    MIN_FINAL_SCORE = min_conv
    strength_dir = (
        "BUY"
        if gap >= MIN_STRENGTH_GAP
        else "SELL" if gap <= -MIN_STRENGTH_GAP else "NEUTRAL"
    )
    # [OPT-9] Distinguish "model missing (None)" from "model genuinely returned 0.0".
    # Only None triggers the NEUTRAL abstain; a real 0.0 still votes SELL below.
    _xgb_missing = _opt("XGB_MISSING_NEUTRAL", True) and (xgb_prob is None)
    xgb_prob = xgb_prob if xgb_prob is not None else 0.0
    mc_pct_up = mc_pct_up if mc_pct_up is not None else 50.0
    xgb_dir = (
        "NEUTRAL"
        if _xgb_missing
        else (
            "BUY"
            if xgb_prob >= XGB_BULLISH_THRESHOLD
            else "SELL" if xgb_prob <= XGB_BEARISH_THRESHOLD else "NEUTRAL"
        )
    )
    # Symmetric three-state: a near-neutral reading abstains instead of voting
    # SELL (the old two-state rule made every sub-threshold value a SELL vote).
    mc_dir = (
        "BUY"
        if mc_pct_up >= MC_BULLISH_THRESHOLD
        else "SELL" if mc_pct_up <= MC_BEARISH_THRESHOLD else "NEUTRAL"
    )
    # buy_votes = sum(1 for d in (strength_dir, xgb_dir, mc_dir) if d == "BUY")
    buy_votes = sum(bool(d == "BUY") for d in (strength_dir, xgb_dir, mc_dir))
    # sell_votes = sum(1 for d in (strength_dir, xgb_dir, mc_dir) if d == "SELL")
    sell_votes = sum(bool(d == "SELL") for d in (strength_dir, xgb_dir, mc_dir))
    log.info(
        f"🤝 {pair}: "
        f"Strength={strength_dir} (gap={gap:+.3f}, ±thr=±{MIN_STRENGTH_GAP}) | "
        f"XGB={xgb_dir} (prob_buy={xgb_prob:.3f}, thr={XGB_BULLISH_THRESHOLD}) | "
        f"MC={mc_dir} (P_UP={mc_pct_up:.1f}%, thr={MC_BULLISH_THRESHOLD}%) | "
        f"BUY={buy_votes}/3"
    )

    if REQUIRE_DIRECTION_CONSENSUS:
        if buy_votes >= CONSENSUS_THRESHOLD:
            direction = "BUY"
            votes_unanimous = buy_votes == 3
            log.info(
                f"✅ {pair}: BUY consensus ({buy_votes}/3, unanimous={votes_unanimous})"
            )
        elif sell_votes >= CONSENSUS_THRESHOLD:
            direction = "SELL"
            votes_unanimous = sell_votes == 3
            log.info(
                f"✅ {pair}: SELL consensus ({sell_votes}/3, unanimous={votes_unanimous})"
            )
        else:
            log.info(f"⏭️  {pair}: NO CONSENSUS → SKIP")
            return None, None

        # ─── Gemini P1 advice + Gemini-audit P0-6 upgrade: Dynamic Position
        #     Sizing (Phase 0 — SHADOW DIAG ONLY). 3:0 unanimous = full lot;
        #     2:1 split = possibly 50% lot in a future phase.
        #     NOW LOGS THE DISAGREED VOTER (exactly which of Strength/XGB/MC
        #     was the outlier) so we can later attribute the low-quality
        #     signal source accurately.
        #
        #     Evidence-chain grep target:
        #       grep "VOTE SIZE DIAG" logs/bot_profile*.log
        #     Accumulate >= 20 rows, THEN compare PnL of 2:1 vs 3:0 AND
        #     split the 2:1 set by Disagreed voter to see if MC dissent is
        #     more harmful than Strength dissent, etc.
        #
        #     REAL 0.5x lot sizing stays OFF until statistical evidence
        #     clearly justifies it.
        if not votes_unanimous:
            # Determine which voter (Strength/XGB/MC) dissented from the
            # winning direction. Only called when 2:1 split so exactly ONE
            # voter will be mismatched (Strength/XGB/MC ∈ {BUY, NEUTRAL, SELL}).
            winner_dir = direction
            # strength_dir ∈ {BUY,SELL,NEUTRAL}; treat NEUTRAL as auto-dissent
            if strength_dir != winner_dir:
                disagreed = "Strength"
                detail = f"Strength={strength_dir} vs winner={winner_dir}"
            elif xgb_dir != winner_dir:
                disagreed = "XGB"
                detail = f"Strength={strength_dir}, XGB={xgb_dir} (vs winner {winner_dir}), MC={mc_dir}"
            else:
                disagreed = "MC"
                detail = f"Strength={strength_dir}, XGB={xgb_dir}, MC={mc_dir} (vs winner {winner_dir})"

            log.info(
                f"📊 VOTE SIZE DIAG [{pair}]: 2:1 split consensus "
                f"(BUY={buy_votes}, SELL={sell_votes}) | "
                f"Disagreed: {disagreed} ({detail}) -> would_halve=True "
                f"(Phase0: log-only; actual lot unchanged)"
            )
    else:
        direction = "BUY" if gap > 0 else "SELL"
        log.info(f"ℹ️  Consensus OFF — using Strength only: {direction}")

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

    _xgb_p_up = xgb_prob or 0.0
    _xgb_aligned = _xgb_p_up if direction == "BUY" else (1.0 - _xgb_p_up)
    X = max(0.0, min(100.0, _xgb_aligned * 100.0))
    if X == 0.0 or _xgb_missing:
        X = max(0.0, min(100.0, S * 0.3 + R * 0.3))
    # M is scored in the direction of the trade, mirroring X: a high P_UP that
    # contradicts a SELL consensus must not still hand the short a full MC score
    # (the old direction-blind form systematically over-credited shorts).
    _mc_aligned = mc_pct_up if direction == "BUY" else (100.0 - mc_pct_up)
    # [MC-SCORE] The raw aligned P_UP lives in ~[39, 61], so M barely moves
    # FINAL. Amplify around the 50 midline (a ±MC_M_DEADZONE dead-zone keeps
    # near-neutral readings pinned at 50 instead of amplifying noise), then
    # scale by the directionless regime hint. W_M is deliberately untouched.
    _mc_dev = _mc_aligned - 50.0
    if abs(_mc_dev) <= MC_M_DEADZONE:
        _mc_amp = 50.0
    else:
        _mc_dev_eff = _mc_dev - (MC_M_DEADZONE if _mc_dev > 0 else -MC_M_DEADZONE)
        _mc_amp = 50.0 + _mc_dev_eff * MC_M_GAIN
    _rg_factor = _mc_regime_factor(regime_str)
    M = max(0.0, min(100.0, _mc_amp * _rg_factor))

    G = 0.0
    if W_G > 0.0 and closes is not None and len(closes) >= 55:
        _ema_fast = calculate_ema(closes, D_GATE_EMA_FAST)
        _ema_slow = calculate_ema(closes, D_GATE_EMA_SLOW)
        _diff = (
            (_ema_fast - _ema_slow).iloc[-1] / _ema_slow.iloc[-1]
            if _ema_slow.iloc[-1] != 0
            else 0.0
        )
        _align = 1.0 if _diff > 0.0005 else (-1.0 if _diff < -0.0005 else 0.0)
        _trend_dir = "BUY" if _align > 0 else ("SELL" if _align < 0 else "NEUTRAL")
        _aligned = _trend_dir == direction
        _raw = (
            abs(_diff) / TREND_G_FULL_SCALE * 100.0 if TREND_G_FULL_SCALE > 0 else 0.0
        )
        _raw = max(0.0, min(100.0, _raw))
        G = _raw if _aligned else _raw * 0.2
        if TREND_G_ADX_MODULATION:
            _adx_mod = max(0.2, min(1.0, adx_val / 50.0)) if adx_val else 0.2
            G = G * _adx_mod
        G = round(max(0.0, min(100.0, G)), 1)

    FINAL = S * W_S + R * W_R + G * W_G + A * W_A + X * W_X + M * W_M
    return direction, {
        "S": round(S, 1),
        "R": round(R, 1),
        "G": round(G, 1),
        "A": round(A, 1),
        "X": round(X, 1),
        "M": round(M, 1),
        "M_RAW": round(max(0.0, min(100.0, _mc_amp)), 1),
        "RG": round(_rg_factor, 2),
        "FINAL": round(FINAL, 1),
        "PASS": FINAL >= MIN_FINAL_SCORE,
        "THRESHOLD": round(MIN_FINAL_SCORE, 1),
    }


# ─── MAIN TRADING FLOW ───────────────────────────────────────────────────────
def main():
    # Dynamic MAX_OPEN may reassign the concurrency cap below (Profile 2 only).
    global MAX_OPEN, MAX_OPEN_POSITIONS, MAX_SIMULTANEOUS_TRADES
    log.info(
        f"\n🤖 RUN v{VERSION} {PROFILE_LABEL} — {ACCOUNT_NAME} | TREND+TP+TOP-N | "
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} | "
        f"MAX_OPEN={MAX_OPEN} | MIN_GAP={MIN_STRENGTH_GAP} | TOP_N={TOP_PAIRS_COUNT}"
    )
    log.info(
        f"🧭 STRENGTH POOL: {len(CURRENCIES)} currencies "
        f"[{' '.join(CURRENCIES)}] | "
        f"TOP_N={TOP_N_CURRENCIES} (strongest × weakest) | "
        f"USE_TOP_PAIRS_ONLY={USE_TOP_PAIRS_ONLY} | "
        f"TOP_PAIRS_MIN_GAP={TOP_PAIRS_MIN_GAP}"
    )
    log.info(f"🔑 OANDA Account ID: {OANDA_ACCOUNT_ID}")

    # // FIX-2026-10-10: report the reason + next open instead of a silent return.
    # // FIX-2026-11-17: ask OANDA whether the instrument is tradeable FIRST;
    # only fall back to the pure-clock guard when the probe cannot tell (None).
    _closed = None
    if _opt("MARKET_PROBE", True):
        _probe = probe_market_open(api, OANDA_ACCOUNT_ID)
        if _probe is not None:
            _closed = not _probe
            _gate_src = (
                "OANDA probe: tradeable"
                if _probe
                else "OANDA probe: NOT tradeable (halt)"
            )
    if _closed is None:
        # probe disabled, or probe failed → clock guard (never fail closed here)
        _closed = forex_market_closed()
        _gate_src = "clock guard (no probe / probe failed)"
    log.info(f"🕒 MARKET GATE: {'CLOSED' if _closed else 'OPEN'} — {_gate_src}")

    if _closed:
        if args.ignore_market_closed:
            log.warning(
                f"📅 Market is CLOSED ({_gate_src}) but --ignore-market-closed "
                "was given → continuing full pipeline (debug mode)."
            )
        else:
            why, reopen, day = market_reopen_hint()
            log.info(
                f"📅 Market is CLOSED ({why} | {_gate_src}) → exits. "
                f"Reopens: {day} 21:00 UTC "
                f"(= {reopen.strftime('%Y-%m-%d %H:%M')} UTC). "
                f"Use --ignore-market-closed to run the pipeline anyway."
            )
            return

    # ── ML initialisation (Phase 3.0 runtime containment) ────────────────────
    # ensure_model() now returns an explicit ModelInitResult and NEVER trains,
    # NEVER writes/republishes artifacts and NEVER raises on an EXPECTED
    # availability / load / validation failure — so a model failure can no
    # longer abort the cycle before the genuinely ML-independent paths
    # (Step 5 Dynamic Exit, Step 6 owned-position snapshot, QUICK-FLIP /
    # _revise_owned_position) are reached.  Unexpected programming errors are
    # still raised inside ensure_model() and stay visible here.
    # NOTE: the ML-dependent entry path (Step 4 confluence / Step 7 scoring) is
    # deliberately UNCHANGED — see PHASE3_0_IMPLEMENTATION_TASK §4.5.  Entry
    # authorization remains unchanged and unresolved.
    ml_init = ensure_model(
        MODEL_PATH,
        FEAT_CFG,
        model_wrapper,
        strat_engine,
        fetcher,
        feat_engine,
        ALL_PAIRS,
        YAHOO_TO_OANDA,
        cfg_bot,
        live=True,
        profile=PROFILE_NAME,
    )
    if ml_init.ok:
        log.info(f"✅ ML READY — {ml_init.as_log_fields()}")
    else:
        log.warning(
            f"⚠️ ML NOT READY ({ml_init.status}/{ml_init.reason}) — {ml_init.detail}. "
            f"Independent position management (Step 5/Step 6/owned positions) "
            f"still runs; ML-dependent entry scoring keeps its EXISTING "
            f"(unresolved) synthetic-X behavior — Phase 3.0 §4.5 approval pending."
        )
        # Telegram alert (throttled per reason) so a stale/mismatched/missing
        # model is pushed to the operator instead of silently degrading to
        # synthetic-X neutral votes.  Position management still runs below.
        report_ml_init_result(PROFILE_LABEL, ml_init)

    # ── Dynamic MAX_OPEN (volatility-tier driven · Profile 2 only) ─────────────
    #    Adjust ONLY the concurrency cap; no order / size / signal logic touched.
    #    wide/extreme → base−2 (floor MIN_OPEN=1); narrow/normal/unknown → base (fail-closed).
    if MAX_OPEN_DYNAMIC:
        _pv = portfolio_volatility_tier(
            [YAHOO_TO_OANDA[p] for p in ALL_PAIRS if YAHOO_TO_OANDA.get(p)]
        )
        _dyn_max_open = dynamic_max_open(MAX_OPEN, _pv["tier"])
        log.info(
            f"📐 MAX_OPEN DYNAMIC: base={MAX_OPEN} tier={_pv['tier']} "
            f"atr_pct={_pv['atr_pct']} n={_pv['n_instruments']} → {_dyn_max_open}"
        )
        MAX_OPEN = _dyn_max_open
        MAX_OPEN_POSITIONS = _dyn_max_open
        MAX_SIMULTANEOUS_TRADES = _dyn_max_open

    # ── MAX_OPEN EARLY-GATE: quick pre-scan of owned positions BEFORE running
    #    Strength Matrix, D-Gate, MC bundle, scoring, or Step-7 candidate eval.
    #    If we are already at/over MAX_OPEN we skip all signal-generation work
    #    entirely but STILL run Dynamic Exit Manager (Step 5) so existing
    #    positions continue to be managed normally.
    # [OPT-10] one has_open_trade_with_tags per pair, shared with the minimal fetch loop
    _early_owned = {}

    def _owned_cached(_inst):
        if _inst not in _early_owned:
            _early_owned[_inst] = has_open_trade_with_tags(
                api,
                OANDA_ACCOUNT_ID,
                _inst,
                OWNER_TAGS,
                client_ext_id=OWNER_CLIENT_EXT_ID,
                client_ext_tag=OWNER_CLIENT_EXT_TAG,
            )
        return _early_owned[_inst]

    _early_open_count = 0
    for _p in ALL_PAIRS:
        _o = YAHOO_TO_OANDA.get(_p)
        if not _o:
            continue
        _f, _ = _owned_cached(_o)
        if _f:
            _early_open_count += 1
    _skip_signal_generation = (
        _early_open_count >= MAX_OPEN and not DIRECTION_FLIP_EXIT_ENABLED
    )
    log.info(
        f"🔍 MAX_OPEN EARLY-GATE: {_early_open_count}/{MAX_OPEN} owned positions "
        f"→ {'SKIP signal generation' if _skip_signal_generation else 'proceed'}"
    )
    if _early_open_count >= MAX_OPEN and DIRECTION_FLIP_EXIT_ENABLED:
        log.info(
            "🔄 MAX_OPEN early-gate bypassed — keep signal evaluation on for direction-flip exits"
        )

    if _skip_signal_generation:
        # ── Minimal Step 6 snapshot so Step 5 (Dynamic Exit) has pair_data ──
        log.info(
            "⏭️ MAX_OPEN reached — skipping Steps 1-4 (Strength/MC/D-Gate/Scoring)"
        )
        pair_data_minimal = {}
        for _p in ALL_PAIRS:
            _o = YAHOO_TO_OANDA.get(_p)
            if not _o:
                continue
            _f, _ = _owned_cached(_o)
            if not _f:
                continue
            try:
                _raw = fetcher.fetch(_p, _o, count=200)
                if _raw is None or _raw.empty:
                    continue
                _df = (
                    _build_pair_features(_raw)
                    .replace([np.inf, -np.inf], np.nan)
                    .ffill()
                    .bfill()
                    .fillna(0)
                )
                if len(_df) < 5:
                    continue
                pair_data_minimal[_p] = {
                    "df": _df,
                    "oanda": _o,
                    "raw": _raw,
                    "atr": _df.iloc[-1].get("atr", 0.0),
                    "rsi": _df.iloc[-1].get("rsi", 50.0),
                    "adx": _df.iloc[-1].get("adx", -1.0),
                }
            except Exception as _e:
                log.error(f"❌ MINIMAL fetch failed {_p}: {_e}")

        # ── Dynamic Exit + Full Position Snapshot ──
        log.info("[STEP 5] Dynamic Exit Manager...")
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
            dry_run=DRY_RUN_MODE,
            json_log=json_log,
            **(
                {} if _opt("EARLY_EXIT_PARITY", True) else {"enabled": TRAILING_SL}
            ),  # [OPT-7]
        )

        def _early_close_wrap(instr, reason_code=None, detail_msg=""):
            return close_position(
                api,
                OANDA_ACCOUNT_ID,
                instr,
                send_telegram_message,
                dry_run=DRY_RUN_MODE,
                reason_code=reason_code,
                detail_msg=detail_msg,
                json_log=json_log,
            )

        if _opt("EARLY_EXIT_PARITY", True):
            dyn_mgr.update_all(pair_data_minimal, _early_close_wrap)
        else:
            dyn_mgr.update_all(pair_data_minimal)

        # ── Full Step 6 snapshot ──
        selected_pairs = [p for p in ALL_PAIRS if YAHOO_TO_OANDA.get(p)]
        open_pos_by_oanda = {}
        open_pos_count = 0
        for pair in selected_pairs:
            oanda_inst = YAHOO_TO_OANDA.get(pair)
            found, trade = has_open_trade_with_tags(
                api,
                OANDA_ACCOUNT_ID,
                oanda_inst,
                OWNER_TAGS,
                client_ext_id=OWNER_CLIENT_EXT_ID,
                client_ext_tag=OWNER_CLIENT_EXT_TAG,
            )
            open_pos_by_oanda[oanda_inst] = found
            if found:
                open_pos_count += 1
                ce = trade.get("client_ext", {})
                log.info(
                    f"📌 OWNED POSITION: {pair} → {oanda_inst} | {trade['direction'].upper()} | "
                    f"units={trade['units']} | tradeID={trade['trade_id']} | "
                    f"client_ext={ce}"
                )
        open_list = [o.replace("_", "/") for o, s in open_pos_by_oanda.items() if s]
        log.info(
            f"📊 Open positions (MAX_OPEN EARLY-GATE): {open_pos_count}/{MAX_OPEN} | OPEN: {', '.join(open_list) or 'None'}"
        )

        # ── Persist cooldown + finish ──
        save_cooldown_state(last_closed)
        log.info(
            f"✅ MAX_OPEN EARLY-GATE run complete — EXIT MGR ran, signal generation skipped. "
            f"{open_pos_count} positions still under management."
        )
        return

    # Step 1 — Currency Strength + Top-N Filter
    log.info("[STEP 1] Currency Strength Matrix...")
    strength_scores = build_strength_matrix()
    log.info(format_strength_ranking(strength_scores))

    if USE_TOP_PAIRS_ONLY:
        selected_pairs, _ = build_top_pairs(
            strength_scores,
            ALL_PAIRS,
            YAHOO_TO_OANDA,
            top_n=TOP_PAIRS_COUNT,
            min_gap=TOP_PAIRS_MIN_GAP,
            whitelist=ALLOWED_PAIRS,
        )
        if not selected_pairs:
            log.warning("⚠️ No high-gap pairs found — falling back to full scan")
            selected_pairs = ALL_PAIRS[:]
        log.info(
            f"🎯 MODE: Top-{TOP_PAIRS_COUNT} strength active → {len(selected_pairs)} candidates"
        )
    else:
        selected_pairs = ALL_PAIRS[:]
        log.info(f"📋 MODE: Full scan — {len(selected_pairs)} pairs")

    # Step 2 — Fetch Data
    pair_data = {}
    weekly_ema_cache = {}
    for pair in selected_pairs:
        oanda = YAHOO_TO_OANDA.get(pair)
        if not oanda:
            log.warning(f"⚠️ No OANDA mapping for {pair} — skipping")
            continue
        try:
            raw = fetcher.fetch(pair, oanda, count=200)
            if raw.empty:
                continue
            df = (
                _build_pair_features(raw)
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
                log.info(
                    f"⚠️ ADX {pair} = {pair_data[pair]['adx']:.1f} — possibly flat market"
                )
            log.info(
                f"📊 {pair}: {len(df)} bars | ATR={pair_data[pair]['atr']:.6f} | "
                f"RSI={pair_data[pair]['rsi']:.1f} | ADX={pair_data[pair]['adx']:.1f}"
            )
            if cfg_bot("WEEK_EMA100_FILTER_ENABLED", False):
                weekly_ema_cache[oanda] = fetch_weekly_ema100(oanda, api)
        except Exception as e:
            log.error(f"❌ Fetch failed {pair}: {e}")

    if not pair_data:
        log.error("No pairs have usable data. Aborting.")
        send_telegram_message(f"❌ FX BOT {PROFILE_LABEL}: No usable data")
        return

    # Step 2.5 — D-Gate: compute H1-EMA20 × H1-EMA50 direction for ALL pool pairs
    D_GATE_DIRECTIONS.clear()
    if not D_GATE_ENABLED:
        log.info("🧭 D-GATE: DISABLED — skipped entirely per profile config")
        D_GATE_DIRECTIONS.update({inst: D_GATE_BOTH for inst in ALL_PAIRS})
        SKIP_DGATE = True
    else:
        SKIP_DGATE = False
        log.info("[STEP 2.5] D-GATE — H1 Direction Locks...")
        # Need ALL_PAIRS (not just selected) because WhiteList filter happens
        # later, and USD-group majority works better if we see the whole pool.
        # [OPT-11] pairs outside ALLOWED_PAIRS are skipped in Step 7 anyway; their
        # D-Gate lookup falls back to BOTH via .get(), so don't pay 500-bar fetches.
        _dgate_pairs = [
            p
            for p in ALL_PAIRS
            if not (
                _opt("DGATE_WHITELIST_ONLY", True)
                and ALLOWED_PAIRS is not None
                and p not in ALLOWED_PAIRS
            )
        ]
        for pair in _dgate_pairs:
            oanda = YAHOO_TO_OANDA.get(pair)
            if not oanda:
                continue
            daily = d_gate_fetch_h1(fetcher, pair, oanda, count=500)
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
        log.info(
            f"🧭 D-GATE SUMMARY: LONG={long_n} SHORT={short_n} BOTH={both_n} | "
            f"SHADOW={D_GATE_SHADOW} (log-only, no block)"
        )
        for pair in sorted(D_GATE_DIRECTIONS.keys()):
            log.info(f"   {pair}: {D_GATE_DIRECTIONS[pair]}")

    # Step 3 — Monte Carlo
    if cfg_bot("SKIP_MC", False):
        args.skip_mc = True
    mc_cache = {}
    mc_weekly_cache = {}

    mc_results_dir = get_mc_results_dir()

    if not args.skip_mc:
        log.info(
            f"[STEP 3] Monte Carlo — loading pre-computed bundles from {mc_results_dir}..."
        )

        d_bundle, d_ok, d_name = load_mc_bundle(mc_results_dir, "D")
        if d_ok:
            mc_cache = {p: d_bundle[p] for p in selected_pairs if p in d_bundle}
            log.info(
                f"📦 MC DAILY bundle: {d_name} | "
                f"loaded {len(mc_cache)}/{len(selected_pairs)} pairs"
            )
            for p in selected_pairs:
                if p in mc_cache:
                    m = mc_cache[p]
                    log.info(
                        f"🎲 MC {p}: {m.get('regime', '?')} | "
                        f"Band {m.get('range_90', '?')} | P_UP={m.get('p_up', '?')}%"
                    )
                else:
                    log.info(f"⏭️ {p}: not found in D bundle — SKIP")
        else:
            mc_sh = Path.home() / "projects" / "fx_monte_carlo" / "run_fx_mc.sh"
            report_mc_refresh_error(
                PROFILE_LABEL,
                mc_sh,
                mc_results_dir,
                send_telegram_message,
            )
            log.warning("🛑 Aborting this run — D bundle required.")
            return

        w_bundle, w_ok, w_name = load_mc_bundle(mc_results_dir, "W")
        if w_ok:
            mc_weekly_cache = {p: w_bundle[p] for p in selected_pairs if p in w_bundle}
            log.info(
                f"📦 MC WEEKLY bundle: {w_name} | "
                f"loaded {len(mc_weekly_cache)}/{len(selected_pairs)} pairs"
            )

        if PROFILE_ID == 2 and mc_weekly_cache:
            log.info(
                "🧪 [PROFILE-2 EXPERIMENT] W+D MC blend enabled — fusing weekly into daily..."
            )
            for p, d in list(mc_cache.items()):
                w = mc_weekly_cache.get(p)
                if not w:
                    continue
                w_up = w.get("p_up", 50.0)
                d_up = d.get("p_up", 50.0)
                deviation = abs(w_up - d_up) / 100.0
                if str(FUSION_WEIGHT_MODE).strip().upper() == "LEGACY_W_DOMINANT":
                    # 旧对照模式：分歧越大越信 W — 精确复现修复前行为
                    w_weight = min(0.65 + deviation * 0.6, 0.85)
                    effective_confidence = 1.0
                else:
                    # 保守衰减模式：分歧 = 信息质量下降 → W 权重下调 + 整体信心衰减
                    w_weight = min(
                        max(BASE_W_WEIGHT - deviation * DECAY_RATE, MIN_W_WEIGHT),
                        MAX_W_WEIGHT,
                    )
                    effective_confidence = max(
                        0.5, 1.0 - deviation * CONFIDENCE_DECAY
                    )
                d_weight = 1.0 - w_weight
                # blend_position_scale 仅作为「方向强度」之外的乘子，不改 base_lot / 风控上限
                blend_position_scale = effective_confidence
                fused_p_up = w_up * w_weight + d_up * d_weight
                fused_p_down = 100.0 - fused_p_up
                fused_ann_drift = (
                    w.get("ann_drift_pct", 0) * w_weight
                    + d.get("ann_drift_pct", 0) * d_weight
                )
                w_lo, w_hi = w.get("range_90", [0, 0])
                d_lo, d_hi = d.get("range_90", [0, 0])
                fused_range_lo = w_lo + (d_lo - w_lo) * 0.3
                fused_range_hi = w_hi + (d_hi - w_hi) * 0.3
                d_regime = d.get("regime", "?")
                w_regime = w.get("regime", "?")
                # 原始标签（末词）：MOMENTUM / RANGE / NEUTRAL（+ OVERBOUGHT/OVERSOLD）
                # D regime 保留用于决策；W regime 仅保留为观察字段。
                d_label = str(d_regime).split()[-1] if str(d_regime).strip() else "?"
                w_label = str(w_regime).split()[-1] if str(w_regime).strip() else "?"
                d_blend = dict(d)
                # 深拷贝派生块：避免与原始 D 记录共享同一对象（浅拷贝正是"半融合"根因）
                d_blend["distribution"] = copy.deepcopy(d.get("distribution"))
                d_blend["prob_bands"] = copy.deepcopy(d.get("prob_bands"))
                d_blend["belief"] = copy.deepcopy(d.get("belief"))
                d_blend["p_up"] = round(fused_p_up, 1)
                d_blend["p_down"] = round(fused_p_down, 1)
                d_blend["p_up_pct"] = round(fused_p_up, 1)
                d_blend["p_down_pct"] = round(fused_p_down, 1)
                d_blend["ann_drift_pct"] = round(fused_ann_drift, 2)
                d_blend["ann_vol_pct"] = w.get("ann_vol_pct", d.get("ann_vol_pct", 0))
                d_blend["range_90"] = [
                    round(fused_range_lo, 5),
                    round(fused_range_hi, 5),
                ]
                d_blend["expected_price"] = d.get(
                    "expected_price", d.get("current_price", 0)
                )
                # 保存 D/W 原始标签；交易逻辑只消费 D，复合标签仅用于展示。
                regime_fused = f"🧬 FUSED | D:{d_label} W:{w_label}"
                d_blend["regime_D"] = d_label
                d_blend["regime_W"] = w_label
                d_blend["regime_fused"] = regime_fused
                # 顶层 regime 保留复合串供旧展示路径兼容，禁止用于交易判断。
                d_blend["regime"] = regime_fused
                d_blend["blend_source"] = {
                    "D": d_name,
                    "W": w_name,
                    "w_weight": round(w_weight, 2),
                }
                # 审计字段：融合模式 / 归一化分歧 / 有效信心 / 仓位乘子
                d_blend["blend_mode"] = FUSION_WEIGHT_MODE
                d_blend["deviation"] = round(deviation, 4)
                d_blend["effective_confidence"] = round(effective_confidence, 4)
                d_blend["blend_position_scale"] = round(blend_position_scale, 4)
                # 方案A：派生块（belief / prob_bands / distribution）同步重锚到融合口径，
                # 使顶层 p_up/p_down/range_90 与底层 posterior/prob_below/quantiles 自洽。
                _synced = _fuse_sync_derived_blocks(
                    d_blend,
                    d_blend["p_up"],
                    d_blend["p_down"],
                    [d_lo, d_hi],
                    d_blend["range_90"],
                )
                d_blend["blend_complete"] = bool(_synced)
                mc_cache[p] = d_blend
                if _synced:
                    _bl = d_blend.get("belief") or {}
                    _sh = (d_blend.get("prob_bands") or {}).get("shape") or {}
                    log.info(
                        f"✅ FUSION SYNC — {p}: belief/prob_bands/quantiles 已同步更新 | "
                        f"p_up={d_blend['p_up']} p_down={d_blend['p_down']} "
                        f"posterior={_bl.get('posterior')} "
                        f"prob_below={_sh.get('prob_below')} verdict={_bl.get('verdict')}"
                    )
                else:
                    log.warning(
                        f"⚠️ FUSION SYNC — {p}: 派生块缺失或区间不可映射，"
                        f"blend_complete=False（保留原始 D 派生值）"
                    )
                log.info(
                    f"🧬 FUSION [{p}] w_w={w_weight:.0%} dev={deviation*100:.0f}pp "
                    f"conf={effective_confidence:.0%} scale={blend_position_scale:.2f} "
                    f"mode={FUSION_WEIGHT_MODE} | "
                    f"P_UP D={d_up:.1f} W={w_up:.1f} → {fused_p_up:.1f}% | "
                    f"range W={[round(w_lo,5), round(w_hi,5)]} D={[round(d_lo,5), round(d_hi,5)]} "
                    f"→ [{round(fused_range_lo,5)}, {round(fused_range_hi,5)}]"
                )
        elif PROFILE_ID != 2:
            log.info(f"ℹ️ Profile {PROFILE_ID} — using pure D bundle (no W blend)")
    else:
        log.info("[STEP 3] MC Skipped — loading legacy...")
        for pair in selected_pairs:
            mc_data, ok = load_mc_legacy(pair, RESULTS_DIR, TODAY_STR, MC_MAX_AGE_HOURS)
            if ok:
                mc_cache[pair] = mc_data

    if args.mc_only:
        return

    # Step 4 — Multi-Timeframe Confluence
    tf_confluence = {}
    if MULTI_TF_CONFLUENCE:
        log.info("[STEP 4] Multi-Timeframe Confluence...")
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
                        _build_pair_features(raw_tf),
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
            log.info(
                f"🔗 CONFLUENCE {pair}: BUY={buy_c} SELL={sell_c} → {'✅ PASS' if passes else '❌ BLOCK'}"
            )
            # [Stage C / C-1] Transparency only: these counts are derived from the
            # legacy Decision-layer `signal.action`, NOT from verified
            # PredictionResults. No ML vote is invented for a non-READY state
            # (contract §4.1 C-1). The vote arithmetic above is unchanged.
            log.info(
                f"🔎 [ML-STATE] CONFLUENCE {pair}: votes=legacy_derived "
                f"(signal.action; not verified PredictionResult) "
                f"| ml_votes_invented=0"
            )

    # [OPT-6] pair_data only holds Top-N pairs; an owned position on a pair that
    # dropped out of Top-N got NO trailing/time-expiry management in this path
    # (the MAX_OPEN early-gate path already handles this). Add them.
    if _opt("EXIT_COVER_OWNED", True):
        for _p in ALL_PAIRS:
            if _p in pair_data:
                continue
            _o = YAHOO_TO_OANDA.get(_p)
            if not _o:
                continue
            _f, _ = has_open_trade_with_tags(
                api,
                OANDA_ACCOUNT_ID,
                _o,
                OWNER_TAGS,
                client_ext_id=OWNER_CLIENT_EXT_ID,
                client_ext_tag=OWNER_CLIENT_EXT_TAG,
            )
            if not _f:
                continue
            try:
                _raw = fetcher.fetch(_p, _o, count=200)
                if _raw is None or _raw.empty:
                    continue
                _df = (
                    _build_pair_features(_raw)
                    .replace([np.inf, -np.inf], np.nan)
                    .ffill()
                    .bfill()
                    .fillna(0)
                )
                if len(_df) < 5:
                    continue
                pair_data[_p] = {
                    "df": _df,
                    "oanda": _o,
                    "raw": _raw,
                    "atr": _df.iloc[-1].get("atr", 0.0),
                    "rsi": _df.iloc[-1].get("rsi", 50.0),
                    "adx": _df.iloc[-1].get("adx", -1.0),
                }
                log.info(
                    f"🛡️ EXIT-COVER: {_p} owned but outside Top-N → added to Step 5"
                )
            except Exception as _e:
                log.error(f"❌ EXIT-COVER fetch failed {_p}: {_e}")

    # Step 5 — Dynamic Exit Manager
    log.info("[STEP 5] Dynamic Exit Manager...")

    def close_wrap(instr, reason_code=None, detail_msg=""):
        return close_position(
            api,
            OANDA_ACCOUNT_ID,
            instr,
            send_telegram_message,
            dry_run=DRY_RUN_MODE,
            reason_code=reason_code,
            detail_msg=detail_msg,
            json_log=json_log,
        )

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
        dry_run=DRY_RUN_MODE,
        json_log=json_log,
    )
    dyn_mgr.update_all(pair_data, close_wrap)

    # Step 6 — Scan Open Positions (OWNERSHIP-AWARE via OANDA tags)
    open_pos_by_oanda, owned_trade_by_oanda, open_pos_count = {}, {}, 0
    owned_positions_snapshot = []
    log.info(
        f"🔍 Checking open positions (owner_client_ext_id={OWNER_CLIENT_EXT_ID}, tag={OWNER_CLIENT_EXT_TAG})..."
    )
    # [OPT-5] The early gate counts owned positions over ALL_PAIRS, but this scan
    # only looked at Top-N pairs -> a position on a pair that fell out of Top-N
    # was invisible here, so open_pos_count < real and MAX_OPEN could be exceeded.
    _owned_scan_pairs = (
        ALL_PAIRS if _opt("OWNED_SCAN_ALL_PAIRS", True) else selected_pairs
    )
    for pair in _owned_scan_pairs:
        oanda_inst = YAHOO_TO_OANDA.get(pair)
        if not oanda_inst:
            continue
        found, trade = has_open_trade_with_tags(
            api,
            OANDA_ACCOUNT_ID,
            oanda_inst,
            OWNER_TAGS,
            client_ext_id=OWNER_CLIENT_EXT_ID,
            client_ext_tag=OWNER_CLIENT_EXT_TAG,
        )
        open_pos_by_oanda[oanda_inst] = found
        owned_trade_by_oanda[oanda_inst] = trade if found else None
        if found:
            open_pos_count += 1
            sl_str = f"SL={trade['sl']}" if trade.get("sl") else "SL=NONE"
            tp_str = f"TP={trade['tp']}" if trade.get("tp") else "TP=NONE"
            ce = trade.get("client_ext", {})
            log.info(
                f"📌 OWNED POSITION: {pair} → {oanda_inst} | {trade['direction'].upper()} | "
                f"units={trade['units']} | tradeID={trade['trade_id']} | "
                f"{sl_str} | {tp_str} | client_ext={ce}"
            )
            owned_positions_snapshot.append(
                {
                    "pair": pair,
                    "oanda_instrument": oanda_inst,
                    "trade_id": trade["trade_id"],
                    "direction": trade["direction"],
                    "units": trade["units"],
                    "entry_price": trade.get("price"),
                    "sl": trade.get("sl"),
                    "tp": trade.get("tp"),
                    "client_ext": trade.get("client_ext"),
                }
            )
        else:
            status, pos = get_open_position(api, OANDA_ACCOUNT_ID, oanda_inst)
            if status == PositionStatus.OPEN:
                other_trades = list_open_trades(api, OANDA_ACCOUNT_ID, oanda_inst)
                trade_summary = (
                    ", ".join(
                        f"{t['trade_id']}(units={t['units']}, client_ext_id={t.get('client_ext_id','')})"
                        for t in other_trades
                    )
                    or "(no per-trade data from OpenTrades)"
                )
                log.warning(
                    f"⚠️  {pair}: INSTRUMENT has aggregate position but NO owned trade — "
                    f"likely opened by another process / older bot version WITHOUT clientExtensions. "
                    f"BLOCKING new entry to prevent position stacking "
                    f"(aggregate units={pos['units']}, side={pos['side']})."
                )
                log.warning(
                    f"  🔍 OWNER_CLIENT_EXT_ID={OWNER_CLIENT_EXT_ID} | "
                    f"existing trade(s) on {oanda_inst}: {trade_summary}"
                )
                open_pos_by_oanda[oanda_inst] = True
    json_log.positions_snapshot(owned_positions_snapshot)

    # ── TP 平仓检测 → 写冷却（必须在持久化之前，否则本次的 lock 不会落盘）──
    # Runs BEFORE any new entry this cycle so freshly-locked instruments are
    # covered by the Step 7 cooldown check below (no same-cycle re-entry).
    record_cooldown_from_closed_trades(
        api,
        OANDA_ACCOUNT_ID,
        [YAHOO_TO_OANDA[p] for p in selected_pairs if p in YAHOO_TO_OANDA],
        OWNER_CLIENT_EXT_ID,
        OWNER_CLIENT_EXT_TAG,
        COOLDOWN_HOURS_AFTER_TP,
        REMOVE_COOLDOWN,
        last_closed,
        Direction,
    )

    # ── P0 · 退出可观测性（只读影子）：增量补录券商侧 SL/TP 平仓 ──
    try:
        audit_owned_closed_trades(
            api,
            OANDA_ACCOUNT_ID,
            OWNER_CLIENT_EXT_ID,
            OWNER_CLIENT_EXT_TAG,
            LOGS_DIR,
            results_dir=RESULTS_DIR,
            profile_name=PROFILE_NAME,
        )
    except Exception as _e:
        log.warning(f"⚠️ EXIT-AUDIT failed: {_e!s}")

    open_list = [o.replace("_", "/") for o, s in open_pos_by_oanda.items() if s]
    ready_list = [
        p.replace("=X", "")
        for p in selected_pairs
        if not open_pos_by_oanda.get(YAHOO_TO_OANDA.get(p), False)
    ]
    log.info(
        f"📊 Open positions: {open_pos_count}/{MAX_OPEN} | OPEN: {', '.join(open_list) or 'None'} | READY: {', '.join(ready_list) or 'None'}"
    )

    def _revise_owned_position(
        pair,
        oanda_inst,
        owned_trade,
        open_side,
        entry,
        current,
        pip_size_val,
        decimals,
        profit_pips,
        atr_val,
        min_profit_pips_for_sl=15.0,
        atr_tp_mult=3.0,
    ):
        trade_id = owned_trade.get("trade_id")
        if not trade_id:
            return
        curr_sl = owned_trade.get("sl")
        curr_tp = owned_trade.get("tp")
        if curr_sl is not None:
            try:
                curr_sl = float(curr_sl)
            except Exception:
                curr_sl = None
        if curr_tp is not None:
            try:
                curr_tp = float(curr_tp)
            except Exception:
                curr_tp = None

        revised_sl = curr_sl
        revised_tp = curr_tp

        if profit_pips >= min_profit_pips_for_sl:
            try:
                new_sl, _ = compute_sl_zone(
                    api, oanda_inst, open_side, current, pip_size_val, cfg_bot
                )
                new_sl = round(new_sl, decimals)
                if open_side == "long":
                    be_price = round(entry + pip_size_val, decimals)
                    new_sl = min(new_sl, be_price)
                    if revised_sl is None or new_sl > revised_sl:
                        revised_sl = new_sl
                else:
                    be_price = round(entry - pip_size_val, decimals)
                    new_sl = max(new_sl, be_price)
                    if revised_sl is None or new_sl < revised_sl:
                        revised_sl = new_sl
            except Exception as _e:
                log.warning(f"⚠️ {pair}: compute_sl_zone failed — skip SL revise: {_e}")

        new_tp_by_atr = round(
            (
                current + atr_tp_mult * atr_val
                if open_side == "long"
                else current - atr_tp_mult * atr_val
            ),
            decimals,
        )
        if open_side == "long":
            if curr_tp is None or new_tp_by_atr > curr_tp:
                revised_tp = new_tp_by_atr
        else:
            if curr_tp is None or new_tp_by_atr < curr_tp:
                revised_tp = new_tp_by_atr

        sl_changed = revised_sl is not None and (
            curr_sl is None or abs(revised_sl - curr_sl) >= pip_size_val
        )
        tp_changed = revised_tp is not None and (
            curr_tp is None or abs(revised_tp - curr_tp) >= pip_size_val
        )

        if not sl_changed and not tp_changed:
            return

        parts = [
            f"🔧 REVISE {pair} #{trade_id} {open_side.upper()} profit={profit_pips:.1f}p"
        ]
        if sl_changed:
            old_sl_s = "NONE" if curr_sl is None else f"{curr_sl:.{decimals}f}"
            parts.append(f"SL: {old_sl_s} → {revised_sl:.{decimals}f}")
        if tp_changed:
            old_tp_s = "NONE" if curr_tp is None else f"{curr_tp:.{decimals}f}"
            parts.append(f"TP: {old_tp_s} → {revised_tp:.{decimals}f}")
        log.info(" | ".join(parts))

        if sl_changed and revised_sl is not None:
            update_order_sl(
                api,
                OANDA_ACCOUNT_ID,
                trade_id,
                oanda_inst,
                revised_sl,
                send_telegram=send_telegram_message,
                dry_run=DRY_RUN_MODE,
                old_sl_price=curr_sl,
                update_reason="STRUCT_REVISE",
                json_log=json_log,
            )
        if tp_changed and revised_tp is not None:
            update_order_tp(
                api,
                OANDA_ACCOUNT_ID,
                trade_id,
                oanda_inst,
                revised_tp,
                send_telegram=send_telegram_message,
                dry_run=DRY_RUN_MODE,
                old_tp_price=curr_tp,
                update_reason="STRUCT_REVISE",
                json_log=json_log,
            )

    # Step 7 — Score, Trend Filter, Smart TP & Execute
    log.info("[STEP 7] Scoring + TREND FILTER + SMART TP...")
    min_sl_pips_jpy, min_sl_pips_std = cfg_bot("MIN_SL_PIPS_JPY", 35), cfg_bot(
        "MIN_SL_PIPS", 25
    )
    signal_eval_pairs = list(
        dict.fromkeys(
            selected_pairs
            + [
                p
                for p in pair_data.keys()
                if open_pos_by_oanda.get(YAHOO_TO_OANDA.get(p), False)
            ]
        )
    )
    trade_lines, pip_cache, pair_parts, _open_reasons = (
        {},
        {p: pip_size(p) for p in signal_eval_pairs},
        {p: (p[:3], p[4:]) for p in signal_eval_pairs},
        {},
    )
    all_candidates = []
    _prob_audit = {}  # pair -> probability sizing audit line

    # Probability sizing uses the fused MC cache where available, otherwise raw D.
    prob_index = _load_prob_index_once(mc_cache)

    for pair in signal_eval_pairs:
        if pair not in pair_data:
            continue
        oanda = pair_data[pair]["oanda"]
        owned_trade = owned_trade_by_oanda.get(oanda)
        atr_val, rsi_val, adx_val = (
            pair_data[pair]["atr"],
            pair_data[pair]["rsi"],
            pair_data[pair]["adx"],
        )

        # ─── Whitelist filter (Ownership Tag) — enforce disjoint pools for multi-account isolation
        if ALLOWED_PAIRS is not None and pair not in ALLOWED_PAIRS:
            log.info(f"🔒 {pair}: not in {PROFILE_LABEL} ALLOWED_PAIRS — SKIP")
            continue

        # ✅ Cooldown check — file-based, auto-clean expired, show remaining
        if not owned_trade:
            _in_cd, _remain_mins, _matched_key = is_in_cooldown(pair, oanda)
            if _in_cd:
                log.info(
                    f"⏭️ {oanda} IN COOLDOWN scope=pair "
                    f"matched_key={_matched_key} "
                    f"remaining={_remain_mins}min — SKIP"
                )
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
        mc_pct_up_now = mc_cache.get(pair, {}).get("p_up", 50.0)

        # ─── MC 概率带边界观察（只观察 · 不改仓位）────────────────────────────
        # 读「实际生效」记录：PROB_USE_FUSED 时 prob_index 复用的即 mc_cache 融合记录。
        # 用已完成 M15 的 high/low + 前一根 close 判 Q20/Q40/Q60/Q80 触及/穿越；
        # 位置由 bands[] 区间包含得出，不使用静态 prob_bands.current。
        if MC_BOUNDARY_WATCH:
            _eff_rec = prob_index.get(to_mc_key(pair)) if prob_index else None
            if not isinstance(_eff_rec, dict):
                _eff_rec = (
                    mc_cache.get(pair) if isinstance(mc_cache.get(pair), dict) else {}
                )
            _watch = watch_mc_boundaries(
                pair,
                _eff_rec.get("prob_bands"),
                bars_from_dataframe(pair_data[pair]["df"]),
                _eff_rec.get("generated_utc") or "unknown",
                current=current,
            )
            log.info(
                f"🎯 MC-BAND {pair} | band={_watch['current_band']} "
                f"| price={current:.5f} | new_touch={_watch['n_new']}"
            )
            for _ev in _watch["new_events"]:
                log.info(
                    f"   └─ {_ev['boundary']}@{_ev['boundary_price']} "
                    f"{_ev['kind']}({_ev['direction']}) "
                    f"open={_ev['open_time']} "
                    f"H={_ev['high']} L={_ev['low']} C={_ev['close']}"
                )

        # ─── QUICK-FLIP + REVISE SL/TP for OWNED positions ───
        if owned_trade:
            _open_side = owned_trade.get("direction", "")
            _entry = float(owned_trade["price"])
            _dec = 3 if "JPY" in pair else 5
            _pip = pip_cache[pair]
            _profit_pips = (
                (current - _entry) / _pip
                if _open_side == "long"
                else (_entry - current) / _pip
            )
            _strength_flip = (_open_side == "long" and gap < -0.5) or (
                _open_side == "short" and gap > 0.5
            )
            _mc_flip = (_open_side == "long" and mc_pct_up_now < 45) or (
                _open_side == "short" and mc_pct_up_now > 55
            )
            _flip_count = sum([_strength_flip, _mc_flip])

            if _flip_count >= 2 and DIRECTION_FLIP_EXIT_ENABLED:
                _detail = (
                    f"strength_flip={_strength_flip}, mc_flip={_mc_flip}, "
                    f"gap={gap:+.2f}, mc_pct_up={mc_pct_up_now:.0f}%, "
                    f"profit={_profit_pips:.1f}p"
                )
                log.warning(
                    f"🔄 QUICK-FLIP EXIT {pair} ({_open_side.upper()}): {_detail}"
                )
                if close_wrap(oanda, reason_code="DIRECTION_FLIP", detail_msg=_detail):
                    owned_trade = None
                    owned_trade_by_oanda[oanda] = None
                    open_pos_by_oanda[oanda] = False
                    open_pos_count = max(0, open_pos_count - 1)
                    trade_lines[pair] = f"📤 {pair} quick-flip\n└─ {_detail}"
                    log.info(
                        f"✅ {pair}: quick-flip closed — proceeding to re-entry eval"
                    )
                else:
                    log.error(f"❌ {pair}: quick-flip close FAILED — keeping position")

            if owned_trade is not None:
                # 硬抗：持仓期不再自动上移 SL / 外扩 TP（Owner 2026-11-18）。
                # 仍 continue —— 已持仓的 pair 不参与本轮再入场评估。
                if REVISE_OWNED_POSITION:
                    _revise_owned_position(
                        pair,
                        oanda,
                        owned_trade,
                        _open_side,
                        _entry,
                        current,
                        _pip,
                        _dec,
                        _profit_pips,
                        atr_val,
                    )
                continue

        # ─── MIN_STRENGTH_GAP gate ───
        if abs(gap) < MIN_STRENGTH_GAP:
            log.info(f"⏭️ {pair}: gap={abs(gap):.2f} < MIN={MIN_STRENGTH_GAP} — SKIP")
            continue
        log.info(f"📈 {pair}: gap={abs(gap):.2f} ≥ {MIN_STRENGTH_GAP} — QUALIFIED")

        if MULTI_TF_CONFLUENCE and not tf_confluence.get(pair, {}).get("passes", True):
            log.info(f"🚫 {pair}: confluence fail — SKIP")
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
        _sig_model_missing = sig is None or getattr(sig, "model_p_up", None) is None
        prob_raw = getattr(sig, "model_p_up", None) if sig else None
        mc_pct_up = mc_cache.get(pair, {}).get("p_up", 50.0)
        if _sig_model_missing:
            log.warning(
                f"⚠️ {pair}: XGB model missing — "
                f"sig={'None' if sig is None else 'OK'} "
                f"model_p_up={getattr(sig, 'model_p_up', None) if sig else 'N/A'} — "
                f"treating XGB as NEUTRAL (OPT_XGB_MISSING_NEUTRAL)"
            )

        # [Stage C / C-2] ML-state transparency (contract §4.1.1).
        # Records the TRUE ML state separately from the legacy decision output.
        # This log changes NO scoring input — `prob_raw` below still feeds
        # calc_weighted_score exactly as before (C-2 is a frozen known exception).
        if _sig_model_missing:
            log.info(
                f"🔎 [ML-STATE] {pair}: prediction=NOT_AVAILABLE "
                f"| scoring_input=SYNTHESIZED_NEUTRAL "
                f"| label=legacy scoring behaviour"
            )
        else:
            log.info(
                f"🔎 [ML-STATE] {pair}: prediction=AVAILABLE "
                f"| source=legacy Signal.model_p_up={prob_raw!r} "
                f"| scoring_input=LEGACY_SIGNAL (frozen, C-2 known exception)"
            )

        _df_closes = pair_data[pair]["df"]["Close"].dropna().reset_index(drop=True)
        _regime_str = d_regime_for_decision(mc_cache.get(pair, {}))
        direction, w = calc_weighted_score(
            pair,
            gap,
            rsi_val,
            adx_val,
            prob_raw,
            mc_pct_up,
            closes=_df_closes,
            regime_str=_regime_str,
        )
        if direction and w:
            tag = "✅" if w["PASS"] else "❌"
            log.info(
                f"{tag} SCORE {pair} {direction} | "
                f"S={w['S']:5.1f}×{W_S:.2f}={w['S']*W_S:4.1f}  "
                f"R={w['R']:5.1f}×{W_R:.2f}={w['R']*W_R:4.1f}  "
                f"G={w['G']:5.1f}×{W_G:.2f}={w['G']*W_G:4.1f}  "
                f"A={w['A']:5.1f}×{W_A:.2f}={w['A']*W_A:4.1f}  "
                f"X={w['X']:5.1f}×{W_X:.2f}={w['X']*W_X:4.1f}  "
                f"M={w['M']:5.1f}×{W_M:.2f}={w['M']*W_M:4.1f}  | FINAL={w['FINAL']:.2f}"
            )
            log.info(
                f"🎛️ MC-DIAG {pair}: P_UP={mc_pct_up:.1f}% "
                f"| M_raw={w['M_RAW']:.1f} RG_factor={w['RG']:.2f} → M={w['M']:.1f} "
                f"| regime={_regime_str or '?'}"
            )

        if not (direction and w and w["PASS"]):
            if w and not w["PASS"]:
                log.info(
                    f"➖ REASON: FINAL {w['FINAL']:.2f} < MIN_CONVICTION={min_conv:.2f}"
                )
            continue

        # ─── D-Gate: enforce D-timeframe direction lock (Solves flip-flop issue)
        if D_GATE_ENABLED:
            pair_gate = D_GATE_DIRECTIONS.get(pair, D_GATE_BOTH)
            gate_ok = d_gate_allows(pair_gate, direction)
            if not gate_ok:
                if D_GATE_SHADOW:
                    # Phase 0: DIAGNOSTIC ONLY — record that we WOULD block here
                    # but let the order go through so we can collect outcomes.
                    log.warning(
                        f"🧭 D-GATE SHADOW DIAG {pair}: D-dir={pair_gate} but "
                        f"15m-wants {direction} — would_block=YES (SHADOW=True, "
                        f"NO action taken yet)"
                    )
                else:
                    log.warning(
                        f"🚫 D-GATE ENFORCED: {pair} {direction} BLOCKED "
                        f"(D-dir={pair_gate})"
                    )
                    continue
            else:
                # Always log the allow case, so evidence chain knows gate was OK
                log.info(f"🧭 D-GATE: {pair} {direction} ALLOWED (D-dir={pair_gate})")

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

        if owned_trade:
            close_now, close_detail = should_close_by_opposite_signal(
                owned_trade,
                direction,
                pair=pair,
            )
            if DIRECTION_FLIP_EXIT_ENABLED and close_now:
                log.warning(f"🔄 DIRECTION-FLIP EXIT {pair}: {close_detail}")
                if close_wrap(
                    oanda,
                    reason_code="DIRECTION_FLIP",
                    detail_msg=close_detail,
                ):
                    open_pos_by_oanda[oanda] = False
                    owned_trade_by_oanda[oanda] = None
                    open_pos_count = max(0, open_pos_count - 1)
                    trade_lines[pair] = (
                        f"📤 {pair} closed on opposite signal\n└─ {close_detail}"
                    )
                    log.info(
                        f"✅ {pair}: owned position closed on opposite signal — same-cycle re-entry skipped"
                    )
                else:
                    log.error(
                        f"❌ {pair}: opposite-signal close failed — keeping existing position"
                    )
                continue

            # ─── 补仓 / 金字塔加仓（pyramiding · averaging-down）────────────────
            # 同向已有持仓时，不再一律 SKIP DUPLICATE；若满足补仓条件（仓位 < 标准仓、
            # 现价套牢、未超最大补仓次数），追加一单把总仓位抬到下一个 SIZE_LADDER 档位。
            # 补仓 size = next_prob_rung_up(current_units) - current_units。
            # 补仓单复用已有持仓的 SL/TP（整仓统一退出），开仓条件已在上方全部通过。
            _pyramid_done = False
            if PYRAMID_ENABLED:
                _owned_dir = str(owned_trade.get("direction", "")).upper()
                _sig_dir = direction.upper()
                _same_dir = (_owned_dir in ("LONG", "BUY") and _sig_dir == "BUY") or (
                    _owned_dir in ("SHORT", "SELL") and _sig_dir == "SELL"
                )
                if _same_dir:
                    _cur_units = abs(int(float(owned_trade.get("units", 0) or 0)))
                    _entry = float(owned_trade.get("price") or 0)
                    _pip = pip_cache.get(pair, 0.0)
                    # 套牢判断：LONG 现价 < entry - threshold；SHORT 现价 > entry + threshold
                    if _sig_dir == "BUY":
                        _underwater_pips = (_entry - current) / _pip if _pip > 0 else 0.0
                    else:
                        _underwater_pips = (current - _entry) / _pip if _pip > 0 else 0.0
                    _underwater = _underwater_pips >= PYRAMID_UNDERWATER_PIPS
                    # 统计该 pair 已有多少笔自有交易（含首单），用于限制补仓次数
                    _all_owned = [
                        t for t in list_open_trades(api, OANDA_ACCOUNT_ID, oanda)
                        if (t.get("client_ext_id") or "").startswith(OWNER_CLIENT_EXT_ID)
                    ]
                    _n_owned = len(_all_owned)
                    _target_rung, _add_on = next_prob_rung_up(
                        current_units=_cur_units,
                        base_lot=DEFAULT_LOT_SIZE,
                        min_units=PROB_ZONE_CFG.get("MIN_LOT", 1),
                    )
                    _can_pyramid = (
                        _underwater
                        and _cur_units < DEFAULT_LOT_SIZE
                        and _n_owned <= PYRAMID_MAX_LEVELS
                        and _add_on > 0
                    )
                    log.info(
                        f"🔺 PYRAMID-CHECK {pair} {_sig_dir} | cur={_cur_units} "
                        f"underwater={_underwater_pips:.1f}p(need>={PYRAMID_UNDERWATER_PIPS}) "
                        f"n_owned={_n_owned}(max={PYRAMID_MAX_LEVELS}) "
                        f"next_rung={_target_rung} add_on={_add_on} "
                        f"→ {'ADD' if _can_pyramid else 'SKIP'}"
                    )
                    if _can_pyramid:
                        _p_sl = owned_trade.get("sl")
                        _p_tp = owned_trade.get("tp")
                        log.info(
                            f"🔺 PYRAMID ADD {pair} {_sig_dir} +{_add_on} units "
                            f"(cur {_cur_units} → target {_target_rung}) | "
                            f"SL={_p_sl} TP={_p_tp}"
                        )
                        if DRY_RUN_MODE:
                            log.info(
                                f"🧪 [DRY-RUN] PYRAMID {pair} {_sig_dir} +{_add_on} — NO ORDER"
                            )
                        else:
                            _p_resp = open_oanda_order(
                                api,
                                OANDA_ACCOUNT_ID,
                                oanda,
                                direction,
                                _add_on,
                                _p_sl,
                                _p_tp,
                                dry_run=DRY_RUN_MODE,
                                tags=OWNER_TAGS,
                                comment=OWNER_COMMENT,
                                client_ext={
                                    "id": f"{OWNER_CLIENT_EXT_ID}_{oanda}",
                                    "tag": OWNER_CLIENT_EXT_TAG,
                                },
                            )
                            _p_status = _p_resp.get("status", "UNKNOWN")
                            _p_tid = _p_resp.get("trade_id", "") or "?"
                            log.info(
                                f"🔺 PYRAMID EXECUTED {pair} {_sig_dir} +{_add_on} | "
                                f"TradeID={_p_tid} status={_p_status}"
                            )
                            send_telegram_message(
                                f"🔺 PYRAMID {pair} {_sig_dir} +{_add_on} units\n"
                                f"└─ cur {_cur_units} → {_target_rung} | "
                                f"underwater {_underwater_pips:.1f}p"
                            )
                        _pyramid_done = True
                if _pyramid_done:
                    continue
                # 不满足补仓条件 → SKIP DUPLICATE
            log.info(f"⏭️ {pair}: owned position already open — SKIP DUPLICATE")
            continue

        dec = 3 if "JPY" in pair else 5
        # ─── Probability-factor sizing / TP ──────────────────────────────────
        # Runs AFTER direction/score/D-Gate/trend-TP are final and BEFORE SL/TP
        # prices are built. It may only change size_units + tp_pips (or skip);
        # SL stays 100% compute_sl_zone()'s output.
        prob_rec = prob_index.get(to_mc_key(pair), {}) if prob_index else {}
        _sizing_regime_record = prob_rec
        plan = compute_prob_plan(
            rec=prob_rec,
            direction=direction,
            cfg=PROB_ZONE_CFG,
            base_lot=DEFAULT_LOT_SIZE,
            base_tp_pips=smart_tp_pips,
            current_price=current,
            pip_value=pip_cache[pair],
            regime=_regime_str,
        )
        audit_line = format_prob_audit(pair, direction, plan)
        log.info(f"🎲 PROB-ZONE {pair} {direction} | {audit_line}")
        # Fusion records expose their raw D/W labels separately; the composite
        # label is retained only for display and compatibility.
        _rec_d = prob_rec.get("regime_D") if isinstance(prob_rec, dict) else None
        _rec_w = prob_rec.get("regime_W") if isinstance(prob_rec, dict) else None
        _rm = plan.get("regime_mult")
        if (_rec_d or _rec_w) and isinstance(_rm, (int, float)):
            log.info(
                f"ℹ️ REGIME {pair} D={_rec_d or '-'} (sizing) | "
                f"W={_rec_w or '-'} (observation only) | D_mult={_rm:.2f}"
            )
        if plan["skip"]:
            log.info(
                f"⏭️ PROB-ZONE SKIP {pair} {direction} — reason={plan['reason']} "
                f"P_UP={plan['p_up']} aligned={plan['aligned']} — NO ORDER"
            )
            continue
        tp_pips_eff = plan["tp_pips"]
        size_units = plan["size_units"]
        _prob_audit[pair] = audit_line

        # ─── W+D 融合仓位乘子（仅 Profile 2 融合记录）────────────────────────
        # blend_position_scale = effective_confidence ∈ [0.5, 1.0]，只缩不放。
        # LEGACY 模式恒为 1.0 → 零影响（逐对精确复现）。仅作乘子：
        # 不改 base_lot、不触碰风控上限 / 单笔上限；随后仍走 ladder 归一化。
        # PROB_USE_FUSED=0（原始 D 对照）时整条融合口径停用 → 完全回退。
        _blend_rec = (
            mc_cache.get(pair) if (PROFILE_ID == 2 and PROB_USE_FUSED) else None
        )
        _blend_scale = (
            float(_blend_rec.get("blend_position_scale", 1.0))
            if isinstance(_blend_rec, dict)
            else 1.0
        )
        if 0.0 < _blend_scale < 1.0:
            _units_pre_blend = int(size_units)
            # L5：融合缩量后不得跌破 MIN_LOT（否则后续被判 below-min 直接 SKIP）
            size_units = max(
                int(PROB_ZONE_CFG.get("MIN_LOT", 1)),
                int(size_units * _blend_scale),
            )
            log.info(
                f"🧬 BLEND-SIZE {pair} {direction} | "
                f"{_units_pre_blend} × {_blend_scale:.2f} → {size_units}"
            )

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
            round(current + tp_pips_eff * pip_cache[pair], dec)
            if direction == "BUY"
            else round(current - tp_pips_eff * pip_cache[pair], dec)
        )

        # ─── L2 · 风险定额仓位（risk-parity sizing）──────────────────────────────
        # SL/TP 价格定型后、入选候选前：rp_mult = clamp(ATR应然SL / 实际SL,
        # RP_F_LO, 1.0) —— 只缩不放大。默认影子（RISK_PARITY_SIZING=False）：
        # 仅落盘 logs/sizing_shadow_*.jsonl，不改变下单 size_units。见计划 §2.1。
        _rp_planned_sl_pips = max(
            min_sl_pips_jpy if "JPY" in pair else min_sl_pips_std,
            round(atr_val / pip_cache[pair] * cfg_bot("ATR_SL_MULT", 2.0), 1),
        )
        _rp_sl_pips_act = abs(current - sl_price) / pip_cache[pair]
        _rp = compute_risk_parity(
            size_units=size_units,
            sl_pips_act=_rp_sl_pips_act,
            ref_pips=_rp_planned_sl_pips,
            min_lot=PROB_ZONE_CFG.get("MIN_LOT", 1),
            f_lo=cfg_bot("RP_F_LO", 0.25),
        )
        log_sizing_shadow(
            {
                "profile": PROFILE_LABEL,
                "pair": pair,
                "direction": direction,
                "entry_price": float(current),
                "sl_price": float(sl_price),
                "tp_price": float(tp_price),
                "sl_use_zone": bool(cfg_bot("SL_USE_ZONE_HIERARCHY", True)),
                "planned_sl_pips": round(_rp_planned_sl_pips, 1),
                "sl_pips_act": round(_rp_sl_pips_act, 1),
                "rp_mult": round(_rp["rp_mult"], 4),
                "units_prob": int(size_units),
                "units_raw": _rp["units_raw"],
                # MIN_LOT 硬边界：缩量后低于最小手数 → None（转正后不下单）
                "units_l2": (
                    int(_rp["units_l2"]) if _rp["units_l2"] is not None else None
                ),
                "below_min": bool(_rp["below_min"]),
                "would_reject": bool(_rp["would_reject"]),
                "pip_value_usd": _rp["pip_value_usd"],
                "jpy_net_units": _rp["jpy_net_units"],
                "applied": bool(RISK_PARITY_SIZING),
            }
        )
        if RISK_PARITY_SIZING:
            _rp_decision = apply_if_enabled(_rp, True)
            if _rp_decision["rejected"]:
                log.info(
                    f"⏭️ RISK-PARITY REJECT {pair} {direction} — "
                    f"units_raw={_rp['units_raw']} < MIN_LOT "
                    f"{PROB_ZONE_CFG.get('MIN_LOT', 1)} — NO ORDER"
                )
                continue
            size_units = _rp_decision["size_units"]

        # Skip any post-risk reduction below the probability minimum factor.
        _min_lot_norm = PROB_ZONE_CFG.get("MIN_LOT", 1)
        _minimum_factor_units = min_prob_factor_units(DEFAULT_LOT_SIZE)
        if size_units <= 0 or below_min_prob_factor(size_units, DEFAULT_LOT_SIZE):
            log.info(
                f"⏭️ PROB-ZONE SKIP {pair} {direction} — "
                f"size={size_units} below 0.125 factor "
                f"({_minimum_factor_units} units) — NO ORDER"
            )
            continue

        # Snap continuous confidence/risk sizing to the four probability tiers.
        _units_before_norm = int(size_units)
        size_units = normalize_to_prob_factor(
            size_units=size_units,
            base_lot=DEFAULT_LOT_SIZE,
            min_units=_min_lot_norm,
        )
        if size_units != _units_before_norm:
            log.info(
                f"📏 LOT-NORMALIZE {pair} {direction} | "
                f"{_units_before_norm} → {size_units} "
                f"(factors={PROB_FACTORS}, min_units={_min_lot_norm})"
            )

        # Bonus is applied only after existing skip/risk/ladder decisions and
        # reads the D regime only; W/M regimes are not trade inputs.
        _regime_sources = [_regime_str]
        for _record in (mc_cache.get(pair), _sizing_regime_record):
            if isinstance(_record, dict):
                _d_label = d_regime_for_decision(_record)
                if _d_label:
                    _regime_sources.append(_d_label)
        _strong_momentum = any(
            is_strong_momentum_regime(_value) for _value in _regime_sources
        )
        if _strong_momentum and size_units > 0:
            _base_units = int(size_units)
            _max_bonus_units = max(2 * DEFAULT_LOT_SIZE, _min_lot_norm)
            size_units = apply_strong_momentum_bonus(
                _base_units,
                enabled=True,
                min_units=_min_lot_norm,
                max_units=_max_bonus_units,
            )
            _tier = prob_tier_for_units(_base_units, DEFAULT_LOT_SIZE)
            log.info(
                f"✅ STRONG_MOMENTUM — TIER {_tier}/4 — base={_base_units} "
                f"boosted={size_units} (+1 tier) | {pair} {direction}"
            )

        # ─── L5 · MIN_LOT 终端兜底（整数 + 地板，链路末端权威边界）────────────
        # 职责：① 信号不顺但策略仍有边时"退回最小仓"；② LIVE 不允许小数手
        # （0.6 → 1 向上取整）。无论前面怎么乘/减半，末端不得低于 MIN_LOT。
        # 常规路径上游已保证 → 此处为显式兜底（对其它 profile 为 no-op）。
        size_units = max(int(size_units + 0.5), _min_lot_norm)

        # ─── §3 · 宽幅震荡影子（wide-range shadow）────────────────────────────
        # ATR_pct = 当日 ATR / 近 20 日 ATR 的 rolling 中位 → narrow/normal/wide。
        # **只落盘、不改任何决策**（Owner 纪律 §5.5）。见计划 §3.1。
        if WIDE_RANGE_SHADOW:
            _wr = compute_atr_ratio(oanda)
            _d_skew = compute_d_skew(mc_cache.get(pair), current)
            _client_order_id = f"{OWNER_CLIENT_EXT_ID}_{oanda}"
            log_wide_range_shadow(
                {
                    "profile": PROFILE_LABEL,
                    "pair": pair,
                    "oanda": oanda,
                    "direction": direction,
                    "atr_pct": (
                        round(_wr["atr_pct"], 4)
                        if _wr["atr_pct"] is not None
                        else None
                    ),
                    "atr_current": _wr["atr_current"],
                    "atr_median": _wr["atr_median"],
                    "tier": _wr["tier"],
                    "n_points": _wr["n_points"],
                    "d_skew": _d_skew,
                    "d_skew_available": _d_skew is not None,
                    "client_order_id": _client_order_id,
                    "trade_id": None,  # 下单成功后回填（见 update_trade_id）
                    "applied": False,
                }
            )

        d_gate_label = (
            D_GATE_DIRECTIONS.get(pair, D_GATE_BOTH) if D_GATE_ENABLED else "N/A"
        )
        # [Stage C / C-3] Transparency: a missing `model_p_up` is NOT a real
        # 0.0 probability. Label the synthesized fallback so the open reason
        # never presents a fabricated value as a model output (contract §4.1 C-3).
        _p_up_true = getattr(sig, "model_p_up", None) if sig else None
        xgb_score = _p_up_true if _p_up_true is not None else 0.0
        xgb_label = (
            f"{xgb_score:.2f}"
            if _p_up_true is not None
            else f"{xgb_score:.2f}(SYNTHETIC)"
        )
        _open_reasons[pair] = (
            f"STRENGTH_GAP={abs(gap):.2f} | XGB_SCORE={xgb_label} | "
            f"MC_P_UP={mc_pct_up:.0f}% | D-GATE={d_gate_label} | "
            f"FINAL={w['FINAL']:.2f}"
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
                tp_pips_eff,
                size_units,
            )
        )

    # ─── Conflict Detection: shared quote currency with opposite direction ─────
    # Within this profile's group, if two or more candidates share the same
    # quote currency but have opposite directions (e.g. short AUDUSD + long
    # EURUSD → both quote USD), ALL candidates in that quote group are skipped.
    from collections import defaultdict

    quote_dirs = defaultdict(list)
    for i, (_, score, pair, oanda, direction, *_rest) in enumerate(all_candidates):
        base, quote = pair_parts[pair]
        quote_dirs[quote].append((direction, pair, score, i))

    conflict_idx = set()
    for quote, entries in quote_dirs.items():
        has_buy = any(d == "BUY" for d, _, _, _ in entries)
        has_sell = any(d == "SELL" for d, _, _, _ in entries)
        if has_buy and has_sell:
            for d, pair, score, i in entries:
                conflict_idx.add(i)
            log.warning(
                f"⚔️  CONFLICT: quote={quote} has both BUY and SELL — "
                f"skipping ALL {len(entries)} candidates: "
                f"{[(p, d) for d, p, _, _ in entries]}"
            )

    if conflict_idx:
        before = len(all_candidates)
        all_candidates = [
            c for i, c in enumerate(all_candidates) if i not in conflict_idx
        ]
        log.info(
            f"⚔️  After conflict resolution: {len(all_candidates)}/{before} remain "
            f"({before - len(all_candidates)} skipped)"
        )

    # Execute Top Candidates
    _cap = MAX_ENTRIES or MAX_OPEN
    _rank_limit = min(MAX_OPEN - open_pos_count, _cap, len(all_candidates))
    log.info(
        f"🏆 RANKED: {len(all_candidates)} passed → opening top "
        f"{max(0, _rank_limit)} (MAX_OPEN={MAX_OPEN}, existing={open_pos_count}, "
        f"MAX_ENTRIES={MAX_ENTRIES or 'unlimited'})"
    )
    for i, (_, score, pair, _, dir, _, _, _, _, tp_pips, units) in enumerate(
        all_candidates, 1
    ):
        log.info(
            f"   #{i} — {pair} {dir} SCORE={score:.1f} "
            f"SMART-TP={tp_pips:.1f}p UNITS={units}"
        )

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
        size_units,
    ) in all_candidates:
        if open_pos_by_oanda.get(oanda, False):
            log.info(f"⏭️ {pair} ({oanda}): already open — SKIP DUPLICATE")
            continue
        if oanda in executed_in_this_run:
            log.info(f"⏭️ {pair} ({oanda}): selected in this run — SKIP DUPLICATE")
            continue
        if open_pos_count >= MAX_OPEN:
            log.info(f"⏭️ {pair}: MAX_OPEN={MAX_OPEN} reached — SKIP")
            continue
        if MAX_ENTRIES and entries_this_run >= MAX_ENTRIES:
            log.info(f"⏭️ {pair}: MAX_ENTRIES this run = {MAX_ENTRIES} reached — SKIP")
            continue

        if DRY_RUN_MODE:
            _r = _open_reasons.get(pair, "UNKNOWN")
            log.info(f"✅ OPEN {pair} {direction} lots={size_units} → {_r}")
            log.info(
                f"🎲 PROB-ZONE APPLIED {pair} {direction} | "
                f"{_prob_audit.get(pair, 'n/a')}"
            )
            log.info(
                f"🧪 [DRY-RUN] SIGNAL {pair} {direction} | "
                f"SL={sl_price} | TP={tp_price} | Score={FINAL:.1f} — NO ORDER SENT"
            )
            trade_lines[pair] = (
                f"✅ {pair} {direction} Score={FINAL:.1f} | SL={sl_price} TP={tp_price}\n"
                f"└─ {_r}\n🧪 DRY-RUN"
            )
            send_telegram_message(
                f"✅ OPEN {pair} {direction} lots={size_units}\n"
                f"└─ {_r}\n🧪 DRY-RUN (no real order)"
            )
            set_cooldown(pair, oanda)
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
                size_units,
                sl_price,
                tp_price,
                dry_run=DRY_RUN_MODE,  # defence-in-depth (entry gate above already blocks)
                tags=OWNER_TAGS,
                comment=OWNER_COMMENT,
                client_ext={
                    "id": f"{OWNER_CLIENT_EXT_ID}_{oanda}",
                    "tag": OWNER_CLIENT_EXT_TAG,
                },
            )
            status = resp.get("status", "UNKNOWN")
            tid = resp.get("trade_id", "") or "?"
            _r = _open_reasons.get(pair, "UNKNOWN")

            if status == "OK":
                log.info(
                    f"✅ EXECUTED {pair} {direction} | SL={sl_price} | TP={tp_price} | TradeID={tid}"
                )
                log.info(f"✅ OPEN {pair} {direction} lots={size_units} → {_r}")
                # TASK-3：把 trade_id 回填到 wide_range_shadow（供 exit_audit 主键 join）
                if WIDE_RANGE_SHADOW and tid and tid != "?":
                    update_trade_id(
                        LOGS_DIR, f"{OWNER_CLIENT_EXT_ID}_{oanda}", str(tid)
                    )
                trade_lines[pair] = (
                    f"✅ {pair} {direction} Score={FINAL:.1f} | SL={sl_price} TP={tp_price}\n"
                    f"└─ {_r}"
                )

                json_log.bot_open(
                    pair=pair,
                    direction=direction,
                    units=size_units,
                    entry_price=float(current),
                    trade_id=str(tid),
                    sl=float(sl_price),
                    tp=float(tp_price),
                    score_final=float(FINAL),
                )

                send_telegram_message(
                    f"✅ OPEN {pair} {direction} lots={size_units} | TradeID={tid}\n"
                    f"└─ {_r}"
                )
                set_cooldown(pair, oanda)
                entries_this_run += 1
                open_pos_count += 1
                executed_in_this_run.add(oanda)
            elif status == "DRY_RUN":
                log.info(f"✅ OPEN {pair} {direction} lots={size_units} → {_r}")
                log.info(
                    f"🧪 DRY_RUN {pair} {direction} | SL={sl_price} | TP={tp_price} — validated, no API call"
                )
                trade_lines[pair] = (
                    f"✅ {pair} {direction} Score={FINAL:.1f} | SL={sl_price} TP={tp_price}\n"
                    f"└─ {_r}\n🧪 DRY-RUN"
                )
                send_telegram_message(
                    f"✅ OPEN {pair} {direction} lots={size_units}\n"
                    f"└─ {_r}\n🧪 DRY-RUN (no real order)"
                )
                set_cooldown(pair, oanda)
                entries_this_run += 1
                open_pos_count += 1
                executed_in_this_run.add(oanda)
            elif status == "REDUCED":
                log.warning(
                    f"⚠️ {pair} {direction} — fill REDUCED existing pos, no new trade opened"
                )
                trade_lines[pair] = (
                    f"⚠️ [REDUCED] {pair} {direction} Score={FINAL:.1f} — reduced existing pos"
                )
            else:
                reason = resp.get("message") or resp.get("reason") or status
                log.error(
                    f"❌ ORDER FAILED {pair} {direction} — status={status} | {reason}"
                )
                trade_lines[pair] = (
                    f"❌ [FAILED {status}] {pair} {direction} Score={FINAL:.1f} — {reason}"
                )
        except Exception as e:
            log.error(f"❌ ORDER FAILED {pair}: {type(e).__name__}: {e}")
            trade_lines[pair] = (
                f"❌ [EXCEPTION] {pair} {direction} Score={FINAL:.1f} — {type(e).__name__}: {e}"
            )

    if trade_lines:
        summary = (
            f"🤖 v{VERSION} {PROFILE_LABEL} RUN COMPLETE — {ACCOUNT_NAME}\n\n"
            + "\n".join(trade_lines.values())
        )
        send_telegram_message(summary)
    else:
        log.info("📋 No signals passed all filters")

    log.info(
        f"✅ v{VERSION} {PROFILE_LABEL} Run Complete — {ACCOUNT_NAME} — TOP-N STRENGTH ACTIVE"
    )

    # ── 持久化 cooldown 状态 ──
    save_cooldown_state(last_closed)


if __name__ == "__main__":
    from utils.utils import apply_jitter

    try:
        apply_jitter(1.0, 10.0)
        main()
    except Exception as e:
        log.exception(f"Fatal error in {PROFILE_LABEL} main loop")
        send_telegram_message(f"❌ FX BOT {PROFILE_LABEL} FATAL ERROR: {e}")
        raise
