#!/usr/bin/env python3
# ──────────────────────────────────────────────────────
# FX Trade Bot v6.8.5 — Fixed TP Cooldown (No External Tracker)
# ──────────────────────────────────────────────────────
import contextlib
import sys
import os
import subprocess
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
from oandapyV20.endpoints.instruments import InstrumentsCandles
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
    check_and_record_tp_cooldown,
    get_open_position,
    has_open_trade_with_tags,
    list_open_trades,
    close_position,
    fetch_candles,
    open_oanda_order_simple as open_oanda_order,
    DynamicPositionManager,
    load_mc_legacy,
    load_mc_bundle,
    get_mc_results_dir,
    PositionStatus,
)
from fx_trade_bot_ml import ensure_model
from sl_zone_hierarchy import compute_sl_zone
from config_oanda import (
    api,
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
from fx_trade_closed_status import check_instrument

# ─── BASE SETUP ──────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
sys.path.extend([str(BASE_DIR), str(BASE_DIR / "utils")])
parser = argparse.ArgumentParser(
    description="FX Trading Bot v6.8.5 | PF-B Balanced + TP Cooldown"
)
parser.add_argument(
    "-p", "--profile", type=int, default=None, help="Profile number (1/2/3/4)"
)
parser.add_argument("--profile2", action="store_true", help="Force Profile2")
parser.add_argument("--profile3", action="store_true", help="Force Profile3")
parser.add_argument(
    "-a", "--account", type=str, default=None, help="Account number 1-4"
)
parser.add_argument(
    "-m", "--max-entries", type=int, default=None, help="Max signals per cycle"
)
parser.add_argument("--timeframe", type=str, default="15m", choices=["15m", "1H", "H4"])
parser.add_argument("--confluence", action="store_true", default=None)
parser.add_argument("--no-confluence", action="store_false", dest="confluence")
parser.add_argument("--skip-mc", action="store_true")
parser.add_argument("--mc-only", action="store_true")
parser.add_argument("--live", action="store_true", help="Connect LIVE environment")
parser.add_argument(
    "--demo",
    "--dry-run",
    action="store_true",
    dest="dry_run",
    default=None,
    help="Force DRY-RUN — no mutating calls",
)
parser.add_argument(
    "--no-dry-run",
    "--no-demo",
    action="store_false",
    dest="dry_run",
    default=None,
    help="Force EXECUTION — send real orders",
)
parser.add_argument("--lots", type=int, default=None, help="Override lot size")
parser.add_argument(
    "--ignore-market-closed",
    action="store_true",
    help="Skip weekend/holiday guard (debug)",
)
parser.add_argument(
    "profile_pos", nargs="?", type=int, default=None, help="Profile number positional"
)
args = parser.parse_args()

# ===== 1. Profile Selection =====
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
profile_id = PROFILE_ID

# ===== 2. Load Config =====
cfg = C.get_profile(PROFILE_ID)
APP_VERSION = "685"
VERSION = cfg["VERSION"]
PROFILE_NAME = f"profile{PROFILE_ID}"
PROFILE_LABEL = cfg["PROFILE_LABEL"]
OWNER_TAGS = ["fx_bot", f"v{APP_VERSION}", PROFILE_NAME]
OWNER_COMMENT = f"fx_bot_v{APP_VERSION}_{PROFILE_NAME}_entry"
OWNER_CLIENT_EXT_ID = f"fx_bot_v{APP_VERSION}_{PROFILE_NAME}"
OWNER_CLIENT_EXT_TAG = f"fx_bot_v{APP_VERSION}_{PROFILE_NAME}_entry"

W_S = cfg["W_S"]
W_R = cfg["W_R"]
W_A = cfg["W_A"]
W_X = cfg["W_X"]
W_M = cfg["W_M"]
MIN_CONVICTION = cfg["MIN_CONVICTION"]
MIN_SLOPE = cfg["MIN_SLOPE"]
D_GATE_ENABLED = cfg["D_GATE_ENABLED"]
MAX_OPEN_POS = cfg["MAX_OPEN"]
TOP_N = cfg["TOP_N"]
SL_MIN_PIPS = cfg["SL_MIN_PIPS"]
SL_MIN_PIPS_JPY = cfg["SL_MIN_PIPS_JPY"]
DEFAULT_LOT_SIZE = cfg["DEFAULT_LOT_SIZE"]
XGB_THRESHOLD = cfg["XGB_BULLISH_THRESHOLD"]
ADX_MIN = cfg["ADX_MIN_SCORE"]

CONFIG_SOURCE = "config_profile.json"
print(f"✅ 配置来源: {CONFIG_SOURCE} — {PROFILE_NAME}")
print("=" * 50)
print(f"🚀 FX Bot v{VERSION} | {PROFILE_NAME}")
print(
    f"⚖️  {PROFILE_LABEL} WEIGHTS: S={W_S:.2f} R={W_R:.2f} A={W_A:.2f} X={W_X:.2f} M={W_M:.2f}"
)
print(
    f"🔧 D-Gate={D_GATE_ENABLED} | MIN_CONVICTION={MIN_CONVICTION:.1f} | MIN_SLOPE={MIN_SLOPE}"
)
print("=" * 50)

COOLDOWN_FILE = BASE_DIR / f"cooldown_{PROFILE_NAME}.json"
RESULTS_DIR = BASE_DIR / f"daily_results_{PROFILE_NAME}"
P = config_bot.get_profile(profile_id)
WEIGHTS = P["WEIGHTS"]
ALLOWED_PAIRS = P["WHITELIST"]
MAX_OPEN = P["MAX_OPEN"]
MAX_ENTRIES_THIS_RUN = P["MAX_ENTRIES_THIS_RUN"]
MIN_GAP = P["MIN_GAP"]
D_GATE_BUFFER_PCT = P["D_GATE_BUFFER_PCT"]
D_GATE_SHADOW = P["D_GATE_SHADOW"]
D_GATE_CONFIRM = P["D_GATE_CONFIRM"]
WEIGHT_STRENGTH = WEIGHTS["S"]
WEIGHT_RSI = WEIGHTS["R"]
WEIGHT_ADX = WEIGHTS["A"]
WEIGHT_XGB = WEIGHTS["X"]
WEIGHT_MC = WEIGHTS["M"]

USE_TOP_PAIRS_ONLY = True
TOP_N_CURRENCIES = 3
TOP_PAIRS_COUNT = TOP_N_CURRENCIES
TOP_PAIRS_MIN_GAP = MIN_GAP
MAX_SIMULTANEOUS_TRADES = MAX_OPEN
D_GATE_EMA_FAST = 20
D_GATE_EMA_SLOW = 50
RSI_DIRECTION_AWARE = True
TREND_FILTER_ENABLED = False
WEEK_EMA100_FILTER_ENABLED = False
SL_PAIR_FLOOR_OVERRIDES = {"GBPJPY=X": 50}
SLOPE_DIAG = True

_TREND_TP_CONFIG = {
    "base_tp_pips": 30,
    "mc_strong_threshold": 0.625,
    "weekly_ema_period": 100,
    "ema100_buffer_pips": 30,
    "profile1": {
        "tp_normal_mult": 1.0,
        "tp_strong_mult": 2.0,
        "ema_period": 10,
        "slope_lookback": 5,
        "min_slope": 0.001,
    },
    "profile2": {
        "tp_normal_mult": 1.0,
        "tp_strong_mult": 2.0,
        "ema_period": 10,
        "slope_lookback": 5,
        "min_slope": 0.001,
    },
    "profile3": {
        "tp_normal_mult": 1.0,
        "tp_strong_mult": 2.0,
        "ema_period": 10,
        "slope_lookback": 5,
        "min_slope_rung": 0.0003,
    },
    "profile4": {
        "tp_normal_mult": 1.0,
        "tp_strong_mult": 2.0,
        "ema_period": 10,
        "slope_lookback": 5,
        "min_slope_rung": 0.0003,
    },
}
MIN_SLOPE_LADDER = (0.0003, 0.0005, 0.0007, 0.001)


def resolve_min_slope(profile_cfg, profile_name):
    rung = profile_cfg.get("min_slope_rung")
    if rung is None:
        return profile_cfg["min_slope"]
    if rung not in MIN_SLOPE_LADDER:
        logger.warning(
            f"⚠️ {profile_name}: rung={rung} invalid, using {MIN_SLOPE_LADDER[-1]}"
        )
        return MIN_SLOPE_LADDER[-1]
    return rung


SLOPE_DIAG_BASELINE = 0.001


def calculate_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()


def calculate_ema_slope(ema_series, lookback_bars):
    ema_now = ema_series.iloc[-1]
    ema_prev = ema_series.iloc[-lookback_bars]
    return (ema_now - ema_prev) / ema_prev, ema_now


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
        closes = [float(c["mid"]["c"]) for c in resp["candles"]]
        if len(closes) < 100:
            return None
        return calculate_ema(pd.Series(closes), 100).iloc[-1]
    except Exception as e:
        logger.warning(f"⚠️ Weekly EMA100 fetch failed {oanda_instrument}: {e}")
        return None


D_GATE_LONG = "LONG"
D_GATE_SHORT = "SHORT"
D_GATE_BOTH = "BOTH"


def d_gate_compute_direction(
    daily_closes,
    ema_fast_period=20,
    ema_slow_period=50,
    confirm_bars=2,
    min_buffer_pct=0.002,
):
    n = len(daily_closes)
    min_bars = max(ema_slow_period + confirm_bars + 2, 42)
    if n < min_bars:
        logger.info(f"🧭 D-GATE: BOTH (insufficient bars {n}<{min_bars})")
        return D_GATE_BOTH
    ema_fast = calculate_ema(daily_closes, ema_fast_period)
    ema_slow = calculate_ema(daily_closes, ema_slow_period)
    diff_pct = (ema_fast - ema_slow) / ema_slow.replace(0.0, np.nan)
    tail = diff_pct.iloc[-confirm_bars:].tolist()
    if any(pd.isna(x) for x in tail):
        logger.info("🧭 D-GATE: BOTH (NaN tail)")
        return D_GATE_BOTH
    above = [x >= min_buffer_pct for x in tail]
    below = [x <= -min_buffer_pct for x in tail]
    if all(above):
        return D_GATE_LONG
    if all(below):
        return D_GATE_SHORT
    return D_GATE_BOTH


def d_gate_fetch_h1(fetcher, pair, oanda, count=500):
    try:
        raw = fetcher.fetch(pair, oanda, count=count, granularity="H1")
        if raw is None or raw.empty or len(raw["Close"].dropna()) < 100:
            return None
        return raw["Close"].dropna().reset_index(drop=True)
    except Exception as e:
        logger.info(f"D-Gate H1 fetch {pair}: {e}")
        return None


def d_gate_allows(pair_direction, trade_direction):
    if pair_direction == D_GATE_BOTH:
        return True
    if pair_direction == D_GATE_LONG:
        return trade_direction == "BUY"
    if pair_direction == D_GATE_SHORT:
        return trade_direction == "SELL"
    return True


def market_reopen_hint(now_utc=None):
    from datetime import timedelta

    now = now_utc or datetime.now(timezone.utc)
    wd = now.weekday()
    if wd == 4 and now.hour >= 21:
        days_ahead, why = 2, "weekend close (Fri)"
    elif wd == 5:
        days_ahead, why = 1, "weekend (Sat)"
    elif wd == 6:
        days_ahead, why = 0, "weekend (Sun, before open)"
    else:
        days_ahead, why = 0, "holiday/market closed"
    reopen = (now + timedelta(days=days_ahead)).replace(
        hour=21, minute=0, second=0, microsecond=0
    )
    day = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][reopen.weekday()]
    return why, reopen, day


def resolve_weekly_ema100(cached_ema, filter_enabled):
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
    cfg = _TREND_TP_CONFIG[profile_name]
    base_pips = _TREND_TP_CONFIG["base_tp_pips"]
    mc_momentum = mc_pct_up / 100.0
    ema10 = calculate_ema(df_h1["Close"], cfg["ema_period"])
    slope, ema_level = calculate_ema_slope(ema10, cfg["slope_lookback"])
    min_slope = resolve_min_slope(cfg, profile_name)
    current_price = entry_price
    if TREND_FILTER_ENABLED:
        ok_price = (
            current_price > ema_level
            if direction == "BUY"
            else current_price < ema_level
        )
        ok_slope = slope >= min_slope if direction == "BUY" else slope <= -min_slope
        if not (ok_price and ok_slope):
            reason = f"TREND MISALIGNED — price/slope fail"
            logger.info(f"⏭️ SKIP {direction}: {reason}")
            return False, 0.0, reason
    if weekly_ema100:
        if direction == "BUY" and current_price < weekly_ema100:
            return False, 0.0, f"COUNTER-TREND vs Weekly EMA100"
        if direction == "SELL" and current_price > weekly_ema100:
            return False, 0.0, f"COUNTER-TREND vs Weekly EMA100"
    tp_mult = (
        cfg["tp_strong_mult"]
        if mc_momentum >= _TREND_TP_CONFIG["mc_strong_threshold"]
        else cfg["tp_normal_mult"]
    )
    tp_pips = base_pips * tp_mult
    tp_price = _pips_to_price(entry_price, direction, tp_pips, pip_value)
    if weekly_ema100:
        buffer_dist = _TREND_TP_CONFIG["ema100_buffer_pips"] * pip_value
        if abs(tp_price - weekly_ema100) < buffer_dist:
            tp_price = (
                weekly_ema100 + buffer_dist
                if direction == "BUY"
                else weekly_ema100 - buffer_dist
            )
            tp_pips = _price_to_pips(entry_price, tp_price, pip_value)
    return True, round(tp_pips, 1), f"TP={tp_pips:.1f}p"


def cfg_bot(name, default):
    if name in P:
        return P[name]
    return getattr(config_bot, name, getattr(config, name, default))


def cfg(name, default):
    return getattr(config, name, default)


RESULTS_DIR.mkdir(exist_ok=True)
TODAY_STR = datetime.now(timezone.utc).strftime("%Y%m%d")
logger = get_logger(f"fx_trade_bot_v{APP_VERSION}")
TREND_TP_CONFIG = cfg("TREND_TP_CONFIG", _TREND_TP_CONFIG)
_profile_slope_cfg = TREND_TP_CONFIG.setdefault(PROFILE_NAME, {})
_profile_slope_cfg.pop("min_slope_rung", None)
_profile_slope_cfg["min_slope"] = MIN_SLOPE
ACTIVE_MIN_SLOPE = resolve_min_slope(_profile_slope_cfg, PROFILE_NAME)
logger.info(
    f"🪜 MIN_SLOPE LADDER: active rung={ACTIVE_MIN_SLOPE} (ladder {MIN_SLOPE_LADDER}; widest first)"
)

D_GATE_EMA_FAST = cfg_bot("D_GATE_EMA_FAST", 20)
D_GATE_EMA_SLOW = cfg_bot("D_GATE_EMA_SLOW", 50)
try:
    D_GATE_CONFIRM_BARS = int(str(D_GATE_CONFIRM).strip().lower().split("h")[0])
except:
    D_GATE_CONFIRM_BARS = cfg_bot("D_GATE_CONFIRM_BARS", 2)
D_GATE_MIN_BUFFER_PCT = D_GATE_BUFFER_PCT / 100.0
D_GATE_DIRECTIONS = {}
if D_GATE_ENABLED:
    logger.info(
        f"🧭 D-GATE: {'SHADOW' if D_GATE_SHADOW else 'ACTIVE'} — EMA{D_GATE_EMA_FAST}×EMA{D_GATE_EMA_SLOW} (D_GATE_CONFIRM={D_GATE_CONFIRM})"
    )
else:
    logger.info("🧭 D-GATE: DISABLED — skipped entirely per profile config")

REQUIRE_DIRECTION_CONSENSUS = cfg_bot("REQUIRE_DIRECTION_CONSENSUS", True)
CONSENSUS_THRESHOLD = cfg_bot("CONSENSUS_THRESHOLD", 2)
XGB_BULLISH_THRESHOLD = cfg_bot("XGB_BULLISH_THRESHOLD", 0.55)
MC_BULLISH_THRESHOLD = cfg_bot("MC_BULLISH_THRESHOLD_PCT", 55.0)
ADX_SCALE_FACTOR = cfg_bot("ADX_SCALE_FACTOR", 2.0)
ADX_MIN_SCORE = cfg_bot("ADX_MIN_SCORE", 20.0)

_WEIGHT_SUM = W_S + W_R + W_A + W_X + W_M
if abs(_WEIGHT_SUM - 1.0) > 0.001:
    ws = [w / _WEIGHT_SUM for w in [W_S, W_R, W_A, W_X, W_M]]
    W_S, W_R, W_A, W_X, W_M = ws
logger.info(f"⚖️ WEIGHTS: S={W_S:.2f} R={W_R:.2f} A={W_A:.2f} X={W_X:.2f} M={W_M:.2f}")

USE_TOP_PAIRS_ONLY = (
    USE_TOP_PAIRS_ONLY
    if USE_TOP_PAIRS_ONLY is not None
    else cfg_bot("USE_TOP_PAIRS_ONLY", STRATEGY_USE_TOP_PAIRS_ONLY)
)
TOP_N_CURRENCIES = TOP_N_CURRENCIES or cfg_bot(
    "TOP_N_CURRENCIES", STRATEGY_TOP_N_CURRENCIES
)
TOP_PAIRS_MIN_GAP = TOP_PAIRS_MIN_GAP or cfg_bot(
    "TOP_PAIRS_MIN_GAP", STRATEGY_TOP_PAIRS_MIN_GAP
)
MIN_STRENGTH_GAP = MIN_GAP or cfg_bot("MIN_STRENGTH_GAP", STRATEGY_MIN_STRENGTH_GAP)
MAX_SIMULTANEOUS_TRADES = MAX_OPEN
TRAILING_TP = cfg_bot("TRAILING_TP", False)
DYNAMIC_TP = cfg_bot("DYNAMIC_TP", True)
MULTI_TF_CONFLUENCE = (
    args.confluence
    if args.confluence is not None
    else cfg_bot("MULTI_TF_CONFLUENCE", False)
)
CONFLUENCE_REQUIRED_TFS = cfg_bot("CONFLUENCE_REQUIRED_TFS", 2)
TP_RAISE_THRESHOLD_PIPS = cfg_bot("TP_RAISE_THRESHOLD_PIPS", 15)

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
LIVE_MODE = bool(args.live)
if args.account:
    try:
        aidx = int(args.account)
        amap = LIVE_ACCOUNTS if LIVE_MODE else DEMO_ACCOUNTS
        _account_override = aidx
    except ValueError:
        parser.error(f"-a/--account must be 1-4, got {args.account}")
else:
    _account_override = None
OANDA_ACCOUNT_ID, _account_source = C.resolve_account_id(
    PROFILE_ID,
    LIVE_MODE,
    _account_override,
    LIVE_ACCOUNTS if _account_override else None,
)
_ENV_LABEL = "LIVE" if LIVE_MODE else "DEMO"
_prof = get_oanda_profile("live" if LIVE_MODE else "practice")
api = _prof["oanda_client"]
_ACCT_SUFFIX = (
    OANDA_ACCOUNT_ID.split("-")[-1] if "-" in OANDA_ACCOUNT_ID else OANDA_ACCOUNT_ID
)
ACCOUNT_NAME = f"{_ENV_LABEL} Account {_ACCT_SUFFIX}"
logger.info(
    f"🧪 PRACTICE/DEMO ENVIRONMENT (no --live) | Account: {OANDA_ACCOUNT_ID}"
    if not LIVE_MODE
    else f"🔴 LIVE ENVIRONMENT | Account: {OANDA_ACCOUNT_ID}"
)
logger.info(
    f"🌐 OANDA API client: environment={_prof['env']} | account={OANDA_ACCOUNT_ID} | ({_ENV_LABEL})"
)

_DRY_RUN_ENV_RAW = os.getenv("DRY_RUN", "true").strip()
_DRY_RUN_ENV = _DRY_RUN_ENV_RAW.lower() in ("1", "true", "yes", "on")
if args.dry_run is None:
    DRY_RUN_MODE = _DRY_RUN_ENV
    _dry_run_source = f"env DRY_RUN={_DRY_RUN_ENV_RAW or '<unset→true>'}"
else:
    DRY_RUN_MODE = bool(args.dry_run)
    _dry_run_source = "CLI --dry-run" if args.dry_run else "CLI --no-dry-run"
logger.info(
    f"🚦 EXECUTION GATE: DRY_RUN={DRY_RUN_MODE} (source: {_dry_run_source}) | "
    f"account env selected solely by --live={'ON' if args.live else 'OFF'}"
)
if DRY_RUN_MODE:
    logger.info(
        "🧪 DRY_RUN MODE | Full pipeline will run; ONLY "
        "mutating OANDA calls (Open/Close/SL/TP update) are suppressed; "
        "ALL read-only calls (positions, prices, candles, account info) "
        "still execute normally."
    )

MAX_ENTRIES = args.max_entries if args.max_entries is not None else MAX_ENTRIES_THIS_RUN
OANDA_GRANULARITY_MAP = {"15m": "M15", "1H": "H1", "H4": "H4", "D": "D"}
OANDA_GRANULARITY = OANDA_GRANULARITY_MAP.get(args.timeframe, "H4")

_env_label_str = (
    f"🔴 LIVE-ENV Account={OANDA_ACCOUNT_ID}"
    if LIVE_MODE
    else f"🧪 DEMO-ENV Account={OANDA_ACCOUNT_ID}"
)
_exec_label_str = (
    "DRY_RUN (NO Open/Close/SL-update/TP-update writes)"
    if DRY_RUN_MODE
    else "EXECUTE (mutating OANDA write calls ALLOWED)"
)
_max_entries_label = f"{MAX_ENTRIES}" if MAX_ENTRIES else "unlimited (within MAX_OPEN)"
logger.info(
    f"🖥️  RUN MODE: {_env_label_str} | {_exec_label_str} | "
    f"MAX_OPEN={MAX_OPEN} | MAX_ENTRIES_THIS_RUN={_max_entries_label}"
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
for s, o in _YAHOO_TO_OANDA_DEFAULT.items():
    YAHOO_TO_OANDA.setdefault(s, o)
logger.info(f"✅ Pair mappings loaded: {len(YAHOO_TO_OANDA)} entries")

if ALLOWED_PAIRS is not None:
    _known = set(YAHOO_TO_OANDA.keys())
    _invalid = [p for p in ALLOWED_PAIRS if p not in _known]
    if _invalid:
        logger.warning(
            f"⚠️  ALLOWED_PAIRS contains unknown symbols (will be ignored): {_invalid}"
        )
    ALLOWED_PAIRS = [p for p in ALLOWED_PAIRS if p in _known]
    logger.info(
        f"🔒 WHITELIST [{PROFILE_LABEL}] active = {len(ALLOWED_PAIRS)} pairs | "
        f"ALLOWED: {ALLOWED_PAIRS}"
    )
else:
    logger.info(f"ℹ️  No ALLOWED_PAIRS set — full pool enabled (no whitelist filter)")

MC_MAX_AGE_HOURS = cfg_bot("MC_MAX_AGE_HOURS", 24)
SIMULATIONS = cfg_bot("MC_SIMULATIONS", 5000)
REMOVE_COOLDOWN = cfg_bot("REMOVE_COOLDOWN", False)
COOLDOWN_HOURS_AFTER_TP = cfg_bot("COOLDOWN_HOURS_AFTER_TP", 0.0)
logger.info(
    f"⏳ TP-COOLDOWN: {COOLDOWN_HOURS_AFTER_TP}h | REMOVE_COOLDOWN={REMOVE_COOLDOWN}"
)

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
min_conv = MIN_CONVICTION
min_edge = cfg_bot("BASE_MIN_EDGE", 0.50)
STRAT_CFG = StrategyConfig(
    mode="LEVEL10",
    min_conviction_score=min_conv,
    base_min_edge=min_edge,
    mc_filter_mode=FilterMode.PENALIZE,
    cooldown_filter_mode=FilterMode.BLOCK,
)
fetcher = DataFetcher(
    use_oanda=True, oanda_api=api, oanda_granularity=OANDA_GRANULARITY
)
feat_engine = FeatureEngine(FEAT_CFG)
strat_engine = StrategyEngine(STRAT_CFG, model=None, feature_list=[])
atr_mod = ATRModule(period=cfg_bot("ATR_PERIOD", 14))
MODEL_PATH = BASE_DIR / "trade_model_xgb.pkl"
model_wrapper = ModelWrapper(FEAT_CFG, model_path=MODEL_PATH)

last_closed = {} if REMOVE_COOLDOWN else load_cooldown(COOLDOWN_FILE, Direction)
if COOLDOWN_HOURS_AFTER_TP > 0 and not REMOVE_COOLDOWN:
    try:
        refresh_tp_cooldown_from_recent_tx(
            api, OANDA_ACCOUNT_ID, COOLDOWN_HOURS_AFTER_TP, last_closed
        )
    except Exception as e:
        logger.warning(f"Cooldown refresh failed: {e}")


def build_top_pairs(
    strength_scores,
    all_pairs,
    oanda_map,
    top_n=TOP_N_CURRENCIES,
    min_gap=MIN_STRENGTH_GAP,
):
    ranked = sorted(strength_scores.items(), key=lambda x: x[1], reverse=True)
    strongest = [c for c, _ in ranked[:top_n]]
    weakest = [c for c, _ in ranked[-top_n:]]
    logger.info(f"🏆 STRONGEST {top_n}: {strongest} | WEAKEST {top_n}: {weakest}")
    candidates = []
    seen = set()
    for s in strongest:
        for w in weakest:
            if s == w:
                continue
            gap = strength_scores[s] - strength_scores[w]
            if abs(gap) < min_gap:
                continue
            for b, q in [(s, w), (w, s)]:
                sym = f"{b}{q}=X"
                if sym in all_pairs and sym not in seen:
                    seen.add(sym)
                    candidates.append(
                        {
                            "pair": sym,
                            "oanda": oanda_map[sym],
                            "gap": gap,
                            "gap_abs": abs(gap),
                        }
                    )
    candidates.sort(key=lambda x: x["gap_abs"], reverse=True)
    selected = [c["pair"] for c in candidates]
    for c in candidates[:6]:
        logger.info(
            f"   {c['pair']}: gap={c['gap']:+.3f} → {'BUY' if c['gap']>0 else 'SELL'}"
        )
    return selected, candidates


def calc_weighted_score(pair, gap, rsi_val, adx_val, xgb_prob, mc_pct_up):
    strength_dir = (
        "BUY"
        if gap >= MIN_STRENGTH_GAP
        else "SELL" if gap <= -MIN_STRENGTH_GAP else "NEUTRAL"
    )
    xgb_dir = "BUY" if (xgb_prob or 0) >= XGB_BULLISH_THRESHOLD else "SELL"
    mc_dir = "BUY" if (mc_pct_up or 50) >= MC_BULLISH_THRESHOLD else "SELL"
    buy_votes = sum(d == "BUY" for d in (strength_dir, xgb_dir, mc_dir))
    sell_votes = sum(d == "SELL" for d in (strength_dir, xgb_dir, mc_dir))
    logger.info(
        f"🤝 {pair}: Strength={strength_dir} XGB={xgb_dir} MC={mc_dir} BUY={buy_votes}/3"
    )
    if REQUIRE_DIRECTION_CONSENSUS:
        if buy_votes >= CONSENSUS_THRESHOLD:
            direction = "BUY"
        elif sell_votes >= CONSENSUS_THRESHOLD:
            direction = "SELL"
        else:
            logger.info(f"⏭️ {pair}: NO CONSENSUS")
            return None, None
    else:
        direction = "BUY" if gap > 0 else "SELL"
    S = max(0, min(100, abs(gap) / 3.5 * 100))
    R = max(0, min(100, abs(rsi_val - 50) * 2))
    A = max(0, min(100, adx_val * ADX_SCALE_FACTOR))
    _xgb_aligned = (xgb_prob or 0) if direction == "BUY" else (1 - (xgb_prob or 0))
    X = max(0, min(100, _xgb_aligned * 100))
    M = max(0, min(100, mc_pct_up or 50))
    FINAL = S * W_S + R * W_R + A * W_A + X * W_X + M * W_M
    return direction, {
        "S": round(S, 1),
        "R": round(R, 1),
        "A": round(A, 1),
        "X": round(X, 1),
        "M": round(M, 1),
        "FINAL": round(FINAL, 1),
        "PASS": FINAL >= MIN_CONVICTION,
    }


def main():
    global model_wrapper, strat_engine
    logger.info(
        f"\n🤖 RUN {PROFILE_LABEL} — {ACCOUNT_NAME} | {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    )
    if forex_market_closed() and not args.ignore_market_closed:
        why, reopen, day = market_reopen_hint()
        logger.info(f"📅 Market closed ({why}) → exits. Reopens: {day} 06:00 UTC")
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

    # Step 1 — Strength
    strength_scores = build_strength_matrix()
    logger.info(format_strength_ranking(strength_scores))
    if USE_TOP_PAIRS_ONLY:
        selected_pairs, _ = build_top_pairs(strength_scores, ALL_PAIRS, YAHOO_TO_OANDA)
    else:
        selected_pairs = ALL_PAIRS[:]

    # Step 2 — Data
    pair_data = {}
    weekly_ema_cache = {}
    for p in selected_pairs:
        oanda = YAHOO_TO_OANDA.get(p)
        if not oanda:
            continue
        try:
            raw = fetcher.fetch(p, oanda, count=200)
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
            pair_data[p] = {
                "df": df,
                "oanda": oanda,
                "atr": df.iloc[-1].get("atr", 0),
                "rsi": df.iloc[-1].get("rsi", 50),
                "adx": df.iloc[-1].get("adx", -1),
            }
            if cfg_bot("WEEK_EMA100_FILTER_ENABLED", False):
                weekly_ema_cache[oanda] = fetch_weekly_ema100(oanda, api)
        except Exception as e:
            logger.error(f"❌ Fetch {p}: {e}")
    if not pair_data:
        logger.error("No usable data")
        return

    # Step 2.5 — D-Gate
    D_GATE_DIRECTIONS.clear()
    if not D_GATE_ENABLED:
        D_GATE_DIRECTIONS.update({inst: D_GATE_BOTH for inst in ALL_PAIRS})
    else:
        for p in ALL_PAIRS:
            oanda = YAHOO_TO_OANDA.get(p)
            if not oanda:
                continue
            closes = d_gate_fetch_h1(fetcher, p, oanda)
            D_GATE_DIRECTIONS[p] = (
                d_gate_compute_direction(
                    closes,
                    D_GATE_EMA_FAST,
                    D_GATE_EMA_SLOW,
                    D_GATE_CONFIRM_BARS,
                    D_GATE_MIN_BUFFER_PCT,
                )
                if closes
                else D_GATE_BOTH
            )

    # Step 3 — MC
    mc_cache = {}
    if not args.skip_mc:
        mc_dir = get_mc_results_dir()
        d_bundle, ok, _ = load_mc_bundle(mc_dir, "D")
        if not ok:
            logger.error("No MC bundle")
            return
        mc_cache = {p: d_bundle[p] for p in selected_pairs if p in d_bundle}

    # Step 5 — Dynamic Exit
    def close_wrap(i, r=None, d=""):
        return close_position(
            api,
            OANDA_ACCOUNT_ID,
            i,
            send_telegram_message,
            dry_run=DRY_RUN_MODE,
            reason_code=r,
            detail_msg=d,
        )

    dyn_mgr = DynamicPositionManager(
        api,
        OANDA_ACCOUNT_ID,
        args.timeframe,
        cfg_bot("BE_TRIGGER_ATR_MULT", 1.5),
        cfg_bot("TRAIL_TRIGGER_ATR_MULT", 2.5),
        cfg_bot("TRAIL_ATR_MULT", 1.5),
        cfg_bot("MAX_HOLD_BARS", 12),
        dynamic_tp=DYNAMIC_TP,
        tp_raise_thresh_pips=TP_RAISE_THRESHOLD_PIPS,
        telegram_send=send_telegram_message,
        dry_run=DRY_RUN_MODE,
    )
    dyn_mgr.update_all(pair_data, close_wrap)

    # Step 6 — Open Positions + TP Cooldown Trigger
    open_pos_by_oanda = {}
    for p in selected_pairs:
        oanda = YAHOO_TO_OANDA.get(p)
        if not oanda:
            continue

        status_res = check_instrument(oanda, OANDA_ACCOUNT_ID, api)
        status = status_res["status"]
        data = status_res["data"]

        if status == "open":
            open_pos_by_oanda[oanda] = True
            logger.info(f"📌 {p} ({oanda}) → holding | ID: {data['trade_id']}")
            continue
        elif status == "closed":
            open_pos_by_oanda[oanda] = False
            ctype = data["close_type"]
            reason_raw = data["reason_raw"]
            pl = data["realized_pl"]
            logger.info(
                f"✅ {p} ({oanda}) → closed | type: {ctype} | PnL: {pl:.4f} | reason: {reason_raw}"
            )

            # ✅ TP-only cooldown — 2h lock, base+quote
            if ctype == "TP" and COOLDOWN_HOURS_AFTER_TP > 0 and not REMOVE_COOLDOWN:
                ts = (
                    datetime.now(timezone.utc).timestamp()
                    + COOLDOWN_HOURS_AFTER_TP * 3600
                )
                base, quote = oanda.split("_")
                last_closed[base] = ts
                last_closed[quote] = ts
                logger.info(
                    f"⏳ TP-COOLDOWN: {base}, {quote} locked for {COOLDOWN_HOURS_AFTER_TP}h"
                )
            continue
        else:
            open_pos_by_oanda[oanda] = False

    # Step 7 — Scoring & Execute
    min_sl_pips_jpy, min_sl_pips_std = cfg_bot("MIN_SL_PIPS_JPY", 35), cfg_bot(
        "MIN_SL_PIPS", 25
    )
    pip_cache = {p: pip_size(p) for p in selected_pairs}
    pair_parts = {p: (p[:3], p[3:].replace("=X", "")) for p in selected_pairs}
    all_candidates = []

    for p in selected_pairs:
        if p not in pair_data:
            continue
        oanda = pair_data[p]["oanda"]

        # ✅ Cooldown check — file-based, auto-clean expired
        _cd_key = oanda if oanda in last_closed else p
        if _cd_key in last_closed:
            rem = last_closed[_cd_key] - datetime.now(timezone.utc).timestamp()
            if rem > 0:
                logger.info(f"⏳ COOLDOWN {p}: {rem/3600:.1f}h remaining — SKIP")
                continue
            else:
                del last_closed[_cd_key]

        if open_pos_by_oanda.get(oanda, False):
            logger.info(f"⏭️ {p}: already open — SKIP")
            continue
        if ALLOWED_PAIRS and p not in ALLOWED_PAIRS:
            logger.info(f"🔒 {p}: not in whitelist — SKIP")
            continue

        gap = strength_scores.get(pair_parts[p][0], 0) - strength_scores.get(
            pair_parts[p][1], 0
        )
        if abs(gap) < MIN_STRENGTH_GAP:
            logger.info(f"⏭️ {p}: gap={abs(gap):.2f} < {MIN_STRENGTH_GAP} — SKIP")
            continue

        try:
            prices = get_live_prices(oanda)
            current = prices["bid"]
            spread_pips = abs(prices["ask"] - prices["bid"]) / pip_cache[p]
        except:
            current = float(pair_data[p]["df"].iloc[-1]["Close"])
            spread_pips = 1.0

        sig = strat_engine.generate_signal(
            p,
            oanda,
            pair_data[p]["df"],
            mc_cache.get(p),
            strength_scores,
            current,
            spread_pips,
        )
        xgb_prob = getattr(sig, "model_p_up", None) or 0.0
        mc_pct_up = mc_cache.get(p, {}).get("p_up", 50.0)
        direction, w = calc_weighted_score(
            p, gap, pair_data[p]["rsi"], pair_data[p]["adx"], xgb_prob, mc_pct_up
        )

        if not (direction and w and w["PASS"]):
            continue
        if D_GATE_ENABLED and not d_gate_allows(
            D_GATE_DIRECTIONS.get(p, D_GATE_BOTH), direction
        ):
            if not D_GATE_SHADOW:
                continue

        weekly_ema100 = resolve_weekly_ema100(
            weekly_ema_cache.get(oanda), cfg_bot("WEEK_EMA100_FILTER_ENABLED", False)
        )
        allow_entry, tp_pips, _ = evaluate_trend_and_tp(
            PROFILE_NAME,
            direction,
            mc_pct_up,
            current,
            pip_cache[p],
            pair_data[p]["df"],
            weekly_ema100,
        )
        if not allow_entry:
            continue

        dec = 3 if "JPY" in p else 5
        if cfg_bot("SL_USE_ZONE_HIERARCHY", True):
            sl_price, _ = compute_sl_zone(
                api, oanda, direction, current, pip_cache[p], cfg_bot
            )
            sl_price = round(sl_price, dec)
        else:
            sl_pips = max(
                min_sl_pips_jpy if "JPY" in p else min_sl_pips_std,
                round(pair_data[p]["atr"] / pip_cache[p] * 2, 1),
            )
            sl_price = (
                round(current - sl_pips * pip_cache[p], dec)
                if direction == "BUY"
                else round(current + sl_pips * pip_cache[p], dec)
            )
        tp_price = (
            round(current + tp_pips * pip_cache[p], dec)
            if direction == "BUY"
            else round(current - tp_pips * pip_cache[p], dec)
        )

        all_candidates.append(
            (-w["FINAL"], w["FINAL"], p, oanda, direction, current, sl_price, tp_price)
        )

    # Conflict Resolution
    from collections import defaultdict

    qdirs = defaultdict(list)
    for i, (_, _, p, o, d, *_) in enumerate(all_candidates):
        qdirs[p[3:] if "JPY" not in p else p[:6]].append((d, i))
    skip_idx = set()
    for q, ents in qdirs.items():
        has_buy = any(d == "BUY" for d, _ in ents)
        has_sell = any(d == "SELL" for d, _ in ents)
        if has_buy and has_sell:
            for _, i in ents:
                skip_idx.add(i)
            logger.warning(f"⚔️ Conflict: {q} has BUY+SELL → all skipped")
    all_candidates = [c for i, c in enumerate(all_candidates) if i not in skip_idx]

    # Execute
    open_count = sum(1 for v in open_pos_by_oanda.values() if v)
    limit = min(MAX_OPEN - open_count, MAX_ENTRIES or 9999, len(all_candidates))
    executed = set()
    trade_lines = {}

    for _, score, p, oanda, dir, curr, sl, tp in sorted(all_candidates)[:limit]:
        if oanda in executed or open_pos_by_oanda.get(oanda, False):
            continue
        if open_count >= MAX_OPEN:
            logger.info(f"⏭️ {p}: MAX_OPEN reached — SKIP")
            continue

        if DRY_RUN_MODE:
            logger.info(f"🧪 DRY-RUN {p} {dir} | SL={sl} TP={tp} | Score={score:.1f}")
            trade_lines[p] = f"✅ {p} {dir} Score={score:.1f}\n🧪 DRY-RUN"
            executed.add(oanda)
            open_count += 1
            continue

        try:
            resp = open_oanda_order(
                api,
                OANDA_ACCOUNT_ID,
                oanda,
                dir,
                DEFAULT_LOT_SIZE,
                sl,
                tp,
                dry_run=DRY_RUN_MODE,
                tags=OWNER_TAGS,
                comment=OWNER_COMMENT,
                client_ext={"id": OWNER_CLIENT_EXT_ID, "tag": OWNER_CLIENT_EXT_TAG},
            )
            if resp.get("status") == "OK":
                logger.info(f"✅ Opened {p} {dir} | SL={sl} TP={tp}")
                trade_lines[p] = f"✅ {p} {dir} Score={score:.1f}"
                executed.add(oanda)
                open_count += 1
        except Exception as e:
            logger.error(f"❌ Order failed {p}: {e}")

    if trade_lines:
        send_telegram_message(
            f"🤖 {PROFILE_LABEL} Run Complete\n" + "\n".join(trade_lines.values())
        )
    if not REMOVE_COOLDOWN and last_closed:
        save_cooldown(COOLDOWN_FILE, last_closed)
        logger.info(f"💾 Cooldown saved: {len(last_closed)} entries")


if __name__ == "__main__":
    from utils.utils import apply_jitter

    try:
        apply_jitter(1.0, 10.0)
        main()
    except Exception as e:
        logger.exception("Main loop error")
        send_telegram_message(f"❌ FX BOT {PROFILE_LABEL} FATAL ERROR: {e}")
        raise
