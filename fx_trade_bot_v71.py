#!/usr/bin/env python3
"""
fx_trade_bot_v7 — UNIFIED CONFIG · Single config_bot_v7.py
Profile2/Account002 · Profile3/Account003
✅ All profiles in config_bot.py — NO separate profile config files
✅ CLI selects profile → auto-loads correct account + settings
✅ TREND_FILTER: Profile3=ON · Profile2=OFF — CLI can override
Usage:
    python fx_trade_bot_v7.py -p 2        # profile2, filters OFF
    python fx_trade_bot_v7.py -p 3        # profile3, filters AUTO-ON
    python fx_trade_bot_v7.py -p 3 --timeframe H4
    python fx_trade_bot_v7.py -p 3 --trend-filter-enabled false
"""
import re
import contextlib, argparse, csv
from datetime import datetime, timezone
from pathlib import Path
import numpy as np, pandas as pd

# ─── Separate strategy and OANDA connection configuration ───
from config_bot_v7 import load_profile, cfg
from config_oanda import get_oanda_profile
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
    open_oanda_order_simple as open_oanda_order,
    DynamicPositionManager,
    load_mc_legacy,
    calculate_stop_loss,
    forex_market_closed_schedule as forex_market_closed,
    check_margin_available,
)
from fx_trade_bot_mc import MCGenerator, MCConfig
from fx_trade_bot_ml import ensure_model
from utils.logging_utils import get_logger

VERSION = "7.2"

# ─── ✅ Unified Logging ──────────────────────────────────────────────────────
logger = get_logger(__name__)
# ─── PARSE ARGS & SELECT PROFILE ─────────────────────────────────────────────
parser = argparse.ArgumentParser(description="FX Trade Bot v7.2 · Unified Config")
g_profile = parser.add_mutually_exclusive_group(required=True)
g_profile.add_argument(
    "-p",
    "--profile",
    type=int,
    choices=[1, 2, 3, 4, 9],
    help="Profile number: 1/2/3/4/9(DEMO)",
)
parser.add_argument("--timeframe", type=str, default="15m", choices=["15m", "1H", "H4"])
parser.add_argument(
    "--trend-filter-enabled",
    type=str.lower,
    choices=["true", "false", "1", "0"],
    default=None,
)
parser.add_argument("--confluence", action="store_true", default=None)
parser.add_argument("--no-confluence", action="store_false", dest="confluence")
parser.add_argument("--skip-mc", action="store_true")
parser.add_argument("--mc-only", action="store_true")
parser.add_argument(
    "--dry-run",
    action="store_true",
    default=False,
    help="Dry-run: show actions, NO real orders",
)
parser.add_argument(
    "--account",
    type=str,
    default=None,
    help="Override OANDA account id: 001/002/003/004 or full id (same environment)",
)
parser.add_argument(
    "--zero-strength-guard",
    type=str.lower,
    choices=["on", "off"],
    default=None,
    help="Override ZERO_STRENGTH_GUARD at runtime (on/off)",
)
args = parser.parse_args()
PROFILE_NAME = f"profile{args.profile}"
print(f"🔹 Selected profile → {PROFILE_NAME!r}")
# ─── ✅ LOAD PROFILE ──────────────────────────────────────────────────────────
P = load_profile(PROFILE_NAME)
S = P["strategy"]
# ─── OANDA Connection ───────────────────────────────────────────────────────
oanda_ctx = get_oanda_profile(
    profile_num=str(args.profile), account_override=args.account
)
api = oanda_ctx["api"]
OANDA_ACCOUNT_ID = oanda_ctx["account_id"]
IS_LIVE = oanda_ctx["is_live"]
MODE_RAW = oanda_ctx["env"]
DRY_RUN = args.dry_run or P.get("dry_run", False)
# ─── Core Identifiers ───────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
PROFILE_LABEL = S["LABEL"]
ACCOUNT_NAME = P["account_alias"]
COOLDOWN_FILE = S["COOLDOWN_FILE"]
RESULTS_DIR = Path(S["RESULTS_DIR"])
RESULTS_DIR.mkdir(exist_ok=True)
# ─── Zero Strength Guard (declared early — used in exclusion) ────────────────
ZERO_STRENGTH_GUARD = cfg(P, "ZERO_STRENGTH_GUARD", False)
if args.zero_strength_guard is not None:
    ZERO_STRENGTH_GUARD = args.zero_strength_guard == "on"
    logger.info(f"🔧 CLI OVERRIDE --zero-strength-guard → {ZERO_STRENGTH_GUARD}")
# ─── ✅ EXCLUDE_PAIRS — Single Source ───────────────────────────────────
EXCLUDE_PAIRS = list(cfg(P, "EXCLUDE_PAIRS", []) or [])
_zero_ccys = []  # placeholder — populated after strength scores
# ─── CLI: --account Override ─────────────────────────────────────────────────
if args.account is not None:
    logger.info(f"🔧 CLI OVERRIDE --account → {OANDA_ACCOUNT_ID}")
if api is None:
    parser.error(f"OANDA api not initialized: missing token for {oanda_ctx['env']}")
if not OANDA_ACCOUNT_ID or len(OANDA_ACCOUNT_ID) < 10 or "-" not in OANDA_ACCOUNT_ID:
    logger.critical(f"💥 FATAL: Invalid OANDA_ACCOUNT_ID = '{OANDA_ACCOUNT_ID}'")
    send_telegram_message(f"💥 FATAL ERROR: Invalid Account ID for {PROFILE_LABEL}")
    exit(1)
print(
    f"""
✅ PROFILE {args.profile} LOADED
   Name      : {ACCOUNT_NAME}
   Strategy  : {P['param_set']} ({PROFILE_LABEL})
   Mode      : {MODE_RAW} {'(DRY-RUN)' if DRY_RUN else '🔴 LIVE' if IS_LIVE else '🟢 DEMO'}
   OANDA environment: {oanda_ctx['env']}
   OANDA account: {OANDA_ACCOUNT_ID}
   OANDA api: initialized
"""
)
# ─── Dates & Audit Paths ─────────────────────────────────────────────────────
TODAY_STR = datetime.now(timezone.utc).strftime("%Y%m%d")
TODAY_STR_DASH = datetime.now(timezone.utc).strftime("%Y-%m-%d")
_AUDIT_DIR = RESULTS_DIR
TRADE_LOG_PATH = _AUDIT_DIR / f"{TODAY_STR_DASH}_trade_log.csv"
SIGNAL_LOG_PATH = _AUDIT_DIR / f"{TODAY_STR_DASH}_signal_log.csv"
_TRADE_LOG_HEADER = [
    "timestamp",
    "trade_id",
    "profile",
    "account",
    "pair",
    "direction",
    "entry_price",
    "sl_price",
    "tp_price",
    "score_final",
    "score_s",
    "score_r",
    "score_a",
    "score_x",
    "score_m",
    "pips",
    "profit_usd",
    "exit_reason",
    "exit_time",
]
_SIGNAL_LOG_HEADER = [
    "timestamp",
    "profile",
    "account",
    "pair",
    "score_final",
    "score_s",
    "score_r",
    "score_a",
    "score_x",
    "score_m",
    "action_taken",
]


def _init_csv(path, header):
    if not path.exists():
        try:
            with open(path, "w", newline="") as f:
                csv.DictWriter(f, fieldnames=header).writeheader()
            logger.info(f"📝 AUDIT init: {path}")
        except Exception as e:
            logger.warning(f"⚠️ AUDIT init failed {path}: {e}")


_init_csv(TRADE_LOG_PATH, _TRADE_LOG_HEADER)
_init_csv(SIGNAL_LOG_PATH, _SIGNAL_LOG_HEADER)


def append_to_csv(filepath, row_dict):
    try:
        fn = list(row_dict.keys())
        if filepath.exists():
            with open(filepath, "r", newline="") as f:
                eh = next(csv.reader(f), None)
                if eh and list(eh) != fn:
                    logger.warning(f"⚠️ Header mismatch: {filepath} — skipping")
                    return
        with open(filepath, "a", newline="") as f:
            csv.DictWriter(f, fieldnames=fn).writerow(row_dict)
    except Exception as e:
        logger.warning(f"⚠️ Append failed {filepath}: {e}")


def update_trade_on_close(instrument, exit_reason="UNKNOWN"):
    try:
        if not TRADE_LOG_PATH.exists():
            return
        df = pd.read_csv(TRADE_LOG_PATH, dtype={"trade_id": str})
        for c in ("pips", "profit_usd", "exit_reason", "exit_time"):
            if c in df.columns:
                df[c] = df[c].astype(object)
        if df.empty:
            return
        mask = (df["pair"] == instrument) & df["exit_time"].isna()
        match = df.loc[mask].head(1)
        if match.empty:
            return
        tid = str(match.iloc[0]["trade_id"])
        if tid.startswith("DRY_RUN_"):
            df.loc[match.index, "exit_reason"] = exit_reason
            df.loc[match.index, "exit_time"] = datetime.now(timezone.utc).isoformat()
            df.to_csv(TRADE_LOG_PATH, index=False)
            return
        realized_pl = 0.0
        with contextlib.suppress(Exception):
            from oandapyV20.endpoints.trades import TradeDetails

            t = api.request(TradeDetails(accountID=OANDA_ACCOUNT_ID, tradeID=tid)).get(
                "trade", {}
            )
            realized_pl = float(t.get("realizedPL", 0.0))
        df.loc[match.index, "profit_usd"] = round(realized_pl, 2)
        df.loc[match.index, "exit_reason"] = exit_reason
        df.loc[match.index, "exit_time"] = datetime.now(timezone.utc).isoformat()
        df.to_csv(TRADE_LOG_PATH, index=False)
    except Exception as e:
        logger.warning(f"⚠️ Backfill error {instrument}: {e}")


# ─── Trend Filter Config ─────────────────────────────────────────────────────
TREND_FILTER_ENABLED = cfg(P, "TREND_FILTER_ENABLED", False)
WEEK_EMA100_FILTER_ENABLED = cfg(P, "WEEK_EMA100_FILTER_ENABLED", False)
if args.trend_filter_enabled is not None:
    TREND_FILTER_ENABLED = args.trend_filter_enabled in ("true", "1")
logger.info(
    f"🔍 FILTERS: TREND={TREND_FILTER_ENABLED} | WEEK_EMA100={WEEK_EMA100_FILTER_ENABLED}"
)
# ─── Strategy Parameters ─────────────────────────────────────────────────────
MODE = cfg(P, "MODE", "LEVEL10")
TIMEFRAME = args.timeframe
OANDA_GRANULARITY_MAP = {"15m": "M15", "1H": "H1", "H4": "H4", "D": "D"}
OANDA_GRANULARITY = OANDA_GRANULARITY_MAP.get(TIMEFRAME, "H4")
MIN_CONVICTION_SCORE = cfg(P, "MIN_CONVICTION_SCORE", 30.0)
BASE_MIN_EDGE = cfg(P, "BASE_MIN_EDGE", 0.50)
MAX_OPEN_POSITIONS = cfg(P, "MAX_OPEN_POSITIONS", 4)
DEFAULT_LOT_SIZE = cfg(P, "DEFAULT_LOT_SIZE", 10000)
ATR_SL_MULT = cfg(P, "ATR_SL_MULT", 2.0)
ATR_TP_MULT = cfg(P, "ATR_TP_MULT", 3.0)
ATR_PERIOD = cfg(P, "ATR_PERIOD", 14)
BASE_TP_PIPS = cfg(P, "BASE_TP_PIPS", 50)
TP_MULT = cfg(P, "TP_MULT", 2.0)
TP_STRONG_MULT = cfg(P, "TP_STRONG_MULT", 2.5)
MC_STRONG_THRESHOLD = cfg(P, "MC_STRONG_THRESHOLD", 0.55)
EMA_PERIOD_FAST = cfg(P, "EMA_PERIOD_FAST", 40)
EMA_PERIOD_SLOW = cfg(P, "EMA_PERIOD_SLOW", 80)
EMA100_BUFFER_PIPS = cfg(P, "EMA100_BUFFER_PIPS", 30)       # SAFE/BUFFER/WAIT zone distance
EMA100_TP_FLOOR_PIPS = cfg(P, "EMA100_TP_FLOOR_PIPS", 30)   # Existing TP-floor clearance from weekly EMA100
XGB_BULLISH_THRESHOLD = cfg(P, "XGB_BULLISH_THRESHOLD", 0.55)
MC_BULLISH_THRESHOLD = cfg(P, "MC_BULLISH_THRESHOLD_PCT", 55.0)
REQUIRE_STRONG_MOMENTUM = cfg(P, "REQUIRE_STRONG_MOMENTUM", False)
W_S = cfg(P, "WEIGHT_STRENGTH", 0.40)
W_R = cfg(P, "WEIGHT_RSI", 0.15)
W_A = cfg(P, "WEIGHT_ADX", 0.15)
W_X = cfg(P, "WEIGHT_XGB", 0.20)
W_M = cfg(P, "WEIGHT_MC", 0.10)
assert abs(W_S + W_R + W_A + W_X + W_M - 1.0) < 1e-9, "Weights must sum to 1.0"
CONSENSUS_THRESHOLD = cfg(P, "CONSENSUS_THRESHOLD", 2)
REQUIRE_DIRECTION_CONSENSUS = cfg(P, "REQUIRE_DIRECTION_CONSENSUS", True)
MIN_STRENGTH_GAP = cfg(P, "MIN_SCORE_GAP", 0.10)
USE_DYNAMIC_SL = cfg(P, "USE_DYNAMIC_SL", True)
DYNAMIC_SL_MULT = cfg(P, "DYNAMIC_SL_MULT", 1.5)
ALL_PAIRS = cfg(P, "ALL_PAIRS")
YAHOO_TO_OANDA = cfg(P, "YAHOO_TO_OANDA")
YF_INTERVAL = cfg(P, "YF_INTERVAL", "4h")
YF_PERIOD_FULL = cfg(P, "YF_PERIOD_FULL", "30d")
YF_PERIOD_RESAMPLE = cfg(P, "YF_PERIOD_RESAMPLE", "60d")
YF_INTERVAL_D = cfg(P, "YF_INTERVAL_D", "1d")
PERIODS_YEAR = cfg(P, "PERIODS_YEAR", 252)
MC_MAX_AGE_HOURS = cfg(P, "MC_MAX_AGE_HOURS", 24)
MC_BAND_PCT = cfg(P, "MC_BAND_PCT", 90)
SIMULATIONS = cfg(P, "SIMULATIONS", 5000)
CONFIDENCE = MC_BAND_PCT / 100.0
TRAILING_TP = cfg(P, "TRAILING_TP", True)
DYNAMIC_TP = cfg(P, "DYNAMIC_TP", False)
TP_RAISE_THRESHOLD_PIPS = cfg(P, "TP_RAISE_THRESHOLD_PIPS", 15)
MIN_SL_PIPS = cfg(P, "MIN_SL_PIPS", 35)
MIN_SL_PIPS_JPY = cfg(P, "MIN_SL_PIPS_JPY", MIN_SL_PIPS + 10)
REMOVE_COOLDOWN = cfg(P, "NO_COOLDOWN", True)
DEBUG_MODE = cfg(P, "DEBUG_MODE", False)
SKIP_MC = cfg(P, "SKIP_MC", False)
MULTI_TF_CONFLUENCE = cfg(P, "MULTI_TF_CONFLUENCE", False)
CONFLUENCE_REQUIRED_TFS = cfg(P, "CONFLUENCE_REQUIRED_TFS", 2)
if args.confluence is not None:
    MULTI_TF_CONFLUENCE = args.confluence
USE_TOP_PAIRS_ONLY = cfg(P, "USE_TOP_PAIRS_ONLY", True)
TOP_PAIRS_COUNT = cfg(P, "TOP_PAIRS_COUNT", 4)
TOP_PAIRS_MIN_GAP = cfg(P, "TOP_PAIRS_MIN_GAP", 0.25)


# ─── Helper Functions ────────────────────────────────────────────────────────
def calculate_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()


def fetch_weekly_ema100(oanda_instrument, api):
    try:
        resp = api.request(
            InstrumentsCandles(
                instrument=oanda_instrument,
                params={"granularity": "W", "count": 105, "price": "M"},
            )
        )
        candles = resp.get("candles") or []
        if len(candles) < 100:
            logger.warning(f"⚠️ Weekly EMA100 {oanda_instrument}: insufficient candles")
            return None
        closes = []
        for c in candles:
            mid = c.get("mid") or {}
            with contextlib.suppress(Exception):
                closes.append(float(mid["c"]))
        if len(closes) < 100:
            return None
        ema100 = float(calculate_ema(pd.Series(closes), 100).iloc[-1])
        last_close = float(closes[-1])
        if not np.isfinite(ema100) or ema100 <= 0 or last_close <= 0:
            return None
        return ema100
    except Exception as e:
        logger.warning(f"⚠️ EMA100 fetch failed: {e}")
        return None


def evaluate_trend_and_tp(
    profile_name,
    direction,
    mc_pct_up,
    entry_price,
    pip_value,
    df,
    weekly_ema100,
    ema_cross_filter,
    fast_period,
    slow_period,
    base_tp_pips,
    mc_strong_threshold,
    tp_mult,
    tp_strong_mult,
    ema100_buffer_pips=30,
    ema100_tp_floor_pips=30,
    week_ema100_filter_enabled=False,
    timeframe="15m",
):
    current_price = entry_price
    if ema_cross_filter:
        ema_fast = calculate_ema(df["Close"], fast_period)
        ema_slow = calculate_ema(df["Close"], slow_period)
        fv, sv = ema_fast.iloc[-1], ema_slow.iloc[-1]
        if direction == "BUY" and not (current_price > fv and fv > sv):
            return (
                False,
                0.0,
                f"TREND_FILTER_BLOCKED: TREND MISALIGNED: Price>{fv:.5f}>{sv:.5f}",
                1.0,
                1.0,
            )
        if direction == "SELL" and not (current_price < fv and fv < sv):
            return (
                False,
                0.0,
                f"TREND_FILTER_BLOCKED: TREND MISALIGNED: Price<{fv:.5f}<{sv:.5f}",
                1.0,
                1.0,
            )
    mc_momentum = mc_pct_up / 100.0
    tp_pips = (
        base_tp_pips * tp_strong_mult
        if mc_momentum >= mc_strong_threshold
        else base_tp_pips * tp_mult
    )
    if not week_ema100_filter_enabled:
        return True, tp_pips, "OK: WEEKLY_EMA_SKIPPED", 1.0, 1.0
    if weekly_ema100 is not None and ema_cross_filter:
        if direction == "BUY":
            min_tp_pips = (
                (weekly_ema100 + ema100_tp_floor_pips * pip_value) - current_price
            ) / pip_value
        else:
            min_tp_pips = (
                current_price - (weekly_ema100 - ema100_tp_floor_pips * pip_value)
            ) / pip_value
        tp_pips = max(tp_pips, min_tp_pips)
    lot_mult = 1.0
    tp_mult_reduce = 1.0
    if weekly_ema100 is not None and pip_value > 0:
        dist_pips = abs(current_price - weekly_ema100) / pip_value
        if dist_pips <= ema100_buffer_pips:
            if direction == "BUY" and current_price < weekly_ema100:
                return (
                    False,
                    0.0,
                    f"WAIT_EMA_ALIGNMENT: WAIT_ABOVE_WEEKLY_EMA100 {weekly_ema100:.5f} dist={dist_pips:.1f}p",
                    1.0,
                    1.0,
                )
            if direction == "SELL" and current_price > weekly_ema100:
                return (
                    False,
                    0.0,
                    f"WAIT_EMA_ALIGNMENT: WAIT_BELOW_WEEKLY_EMA100 {weekly_ema100:.5f} dist={dist_pips:.1f}p",
                    1.0,
                    1.0,
                )
            # RISK STRUCTURE:
            # lot × 0.5 -> approximately 0.5× baseline position risk
            # TP  × 0.8 -> approximately 0.4× baseline gross reward
            # Therefore pip-based reward/risk changes from baseline R:1 to R:0.8.
            # These values are experimental and have not yet been statistically validated.
            lot_mult = 0.5
            tp_mult_reduce = 0.8
            tp_pips = tp_pips * tp_mult_reduce
            logger.info(
                f"⚡ BUFFER ZONE {direction}: dist={dist_pips:.1f}p ≤ {ema100_buffer_pips}p → lot×{lot_mult} TP×{tp_mult_reduce}"
            )
        else:
            logger.info(
                f"🛡️ SAFE ZONE {direction}: dist={dist_pips:.1f}p > {ema100_buffer_pips}p"
            )
    return (
        True,
        tp_pips,
        f"TP={tp_pips:.1f}p (lot×{lot_mult} TP×{tp_mult_reduce})",
        lot_mult,
        tp_mult_reduce,
    )


def build_top_pairs(strength_scores, all_pairs, top_n=4, min_gap=0.25):
    ranked = sorted(strength_scores.items(), key=lambda x: x[1], reverse=True)
    strongest = [c for c, _ in ranked[:top_n]]
    weakest = [c for c, _ in ranked[-top_n:]]
    best_by_sym = {}
    for base in strongest:
        for quote in weakest:
            if base == quote:
                continue
            gap = strength_scores[base] - strength_scores[quote]
            if abs(gap) < min_gap:
                continue
            sym = (
                f"{base}{quote}=X"
                if f"{base}{quote}=X" in all_pairs
                else f"{quote}{base}=X"
            )
            if sym not in all_pairs:
                continue
            abs_gap = abs(gap)
            prev = best_by_sym.get(sym)
            if prev is None or abs_gap > prev[1]:
                best_by_sym[sym] = (sym, abs_gap, base, quote)
    result = sorted(best_by_sym.values(), key=lambda x: x[1], reverse=True)
    return [p[0] for p in result[:top_n]], result[:top_n]


def calc_weighted_score(pair, gap, rsi_val, adx_val, xgb_prob, mc_pct_up):
    strength_dir = (
        "BUY"
        if gap >= MIN_STRENGTH_GAP
        else "SELL" if gap <= -MIN_STRENGTH_GAP else "NEUTRAL"
    )
    xgb_dir = "BUY" if (xgb_prob or 0.0) >= XGB_BULLISH_THRESHOLD else "SELL"
    mc_dir = "BUY" if (mc_pct_up or 50.0) >= MC_BULLISH_THRESHOLD else "SELL"
    buy_votes = sum(1 for d in (strength_dir, xgb_dir, mc_dir) if d == "BUY")
    sell_votes = sum(1 for d in (strength_dir, xgb_dir, mc_dir) if d == "SELL")
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
            logger.info(f"⏭️ {pair}: NO CONSENSUS")
            return None, None
    else:
        direction = "BUY" if gap > 0 else "SELL"
    S = max(0.0, min(100.0, abs(gap) / 3.5 * 100.0))
    rsi = max(0.0, min(100.0, rsi_val))
    R = (
        max(0.0, min(100.0, (50.0 - rsi) * 2.0))
        if direction == "BUY"
        else max(0.0, min(100.0, (rsi - 50.0) * 2.0))
    )
    A = max(0.0, min(100.0, adx_val * cfg(P, "ADX_SCALE_FACTOR", 2.0)))
    X = max(0.0, min(100.0, (xgb_prob or 0.0) * 100.0)) or 50.0
    M = max(0.0, min(100.0, mc_pct_up if mc_pct_up is not None else 50.0))
    FINAL = S * W_S + R * W_R + A * W_A + X * W_X + M * W_M
    return direction, {
        "S": round(S, 1),
        "R": round(R, 1),
        "A": round(A, 1),
        "X": round(X, 1),
        "M": round(M, 1),
        "FINAL": round(FINAL, 1),
        "PASS": FINAL >= MIN_CONVICTION_SCORE,
        "THRESHOLD": round(MIN_CONVICTION_SCORE, 1),
    }


# ─── MC Timeframe Config ─────────────────────────────────────────────────────
_tf_cfg = (
    {
        "YF_INTERVAL": YF_INTERVAL,
        "YF_PERIOD_FULL": YF_PERIOD_FULL,
        "YF_PERIOD_RESAMPLE": YF_PERIOD_RESAMPLE,
        "MC_LOOKBACK": cfg(P, "H4_LOOKBACK", 90),
        "MC_FORECAST": cfg(P, "H4_FORECAST", 8),
        "PERIODS_YEAR": PERIODS_YEAR * 6,
        "MC_REPORT_TITLE": f"[{PROFILE_LABEL}] FX {TIMEFRAME} MONTE CARLO",
        "RESULTS_DIR": RESULTS_DIR,
    }
    if TIMEFRAME in ("H4", "1H", "15m")
    else {
        "YF_INTERVAL": cfg(P, "YF_INTERVAL_D", "1d"),
        "YF_PERIOD_FULL": cfg(P, "YF_PERIOD_FULL_D", "120d"),
        "YF_PERIOD_RESAMPLE": cfg(P, "YF_PERIOD_RESAMPLE_D", "180d"),
        "MC_LOOKBACK": cfg(P, "DAILY_LOOKBACK", 90),
        "MC_FORECAST": cfg(P, "DAILY_FORECAST", 5),
        "PERIODS_YEAR": cfg(P, "PERIODS_YEAR_D", 252),
        "MC_REPORT_TITLE": f"[{PROFILE_LABEL}] FX DAILY MONTE CARLO",
        "RESULTS_DIR": RESULTS_DIR,
    }
)
MCConfig.set_timeframe(TIMEFRAME, _tf_cfg)
# ─── Pipeline & Strategy ─────────────────────────────────────────────────────
FEAT_CFG = FeatureConfig(
    use_atr=cfg(P, "USE_ATR", True),
    atr_sl_mult=ATR_SL_MULT,
    atr_tp_mult=ATR_TP_MULT,
    atr_period=ATR_PERIOD,
    use_macd=cfg(P, "USE_MACD", True),
    use_rsi=cfg(P, "USE_RSI", True),
    use_adx=cfg(P, "USE_ADX", True),
    model_type=cfg(P, "MODEL_TYPE", "xgboost"),
    target_horizon=cfg(P, "TARGET_HORIZON", 6),
    train_lookback_bars=cfg(P, "TRAIN_LOOKBACK_BARS", 5000),
)
STRAT_CFG = StrategyConfig(
    mode=MODE,
    min_conviction_score=MIN_CONVICTION_SCORE,
    base_min_edge=BASE_MIN_EDGE,
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
atr_mod = ATRModule(period=ATR_PERIOD)
MODEL_PATH = BASE_DIR / "trade_model_xgb.pkl"
model_wrapper = ModelWrapper(FEAT_CFG, model_path=MODEL_PATH)
last_closed = {} if REMOVE_COOLDOWN else load_cooldown(COOLDOWN_FILE, Direction)


# ─── MAIN ────────────────────────────────────────────────────────────────────
def main():
    global model_wrapper, strat_engine, EXCLUDE_PAIRS, _zero_ccys
    logger.info(
        f"\n🤖 RUN v{VERSION} {PROFILE_LABEL} — {ACCOUNT_NAME} | "
        f"FILTERS={'ON' if TREND_FILTER_ENABLED else 'OFF'} | "
        f"DRY-RUN={'ON 🧊' if DRY_RUN else 'OFF LIVE'} | "
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} | MAX_OPEN={MAX_OPEN_POSITIONS}"
    )
    # Audit reconciliation
    try:
        if TRADE_LOG_PATH.exists():
            _rdf = pd.read_csv(TRADE_LOG_PATH, dtype={"trade_id": str})
            _open_ids = set()
            with contextlib.suppress(Exception):
                from oandapyV20.endpoints.trades import OpenTrades

                _open_ids = {
                    str(t["id"])
                    for t in api.request(OpenTrades(accountID=OANDA_ACCOUNT_ID)).get(
                        "trades", []
                    )
                }
            for _, row in _rdf.iterrows():
                if pd.notna(row.get("exit_time")):
                    continue
                tid = str(row.get("trade_id", ""))
                if not tid or tid.startswith("DRY_RUN_"):
                    continue
                if tid not in _open_ids:
                    update_trade_on_close(str(row.get("pair", "")), "SL_OR_TP_HIT")
    except Exception as e:
        logger.warning(f"⚠️ Reconciliation failed: {e}")
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
        lambda k, d: cfg(P, k, d),
    )
    # Step 1 — Currency Strength
    logger.info("[STEP 1] Currency Strength...")
    strength_scores = build_strength_matrix()
    logger.info(format_strength_ranking(strength_scores))
    # ─── ✅ Zero-Strength Detection & Exclusion Merge ────────────────────────
    _MAJORS_8 = ["USD", "EUR", "GBP", "JPY", "AUD", "NZD", "CAD", "CHF"]
    _zero_ccys = [
        c
        for c in _MAJORS_8
        if c not in strength_scores
        or strength_scores[c] == 0.0
        or np.isnan(strength_scores[c])
    ]
    if ZERO_STRENGTH_GUARD and _zero_ccys:
        logger.warning(
            f"⚠️ Zero-strength currencies: [{', '.join(_zero_ccys)}] → auto-excluded"
        )
        EXCLUDE_PAIRS = sorted(set(EXCLUDE_PAIRS + _zero_ccys))
    # Build selected pairs
    if USE_TOP_PAIRS_ONLY:
        selected_pairs, _ = build_top_pairs(
            strength_scores, ALL_PAIRS, TOP_PAIRS_COUNT, TOP_PAIRS_MIN_GAP
        )
        selected_pairs = selected_pairs or ALL_PAIRS[:]
        logger.info(f"🎯 Top {len(selected_pairs)} pairs selected")
    else:
        selected_pairs = ALL_PAIRS[:]
        logger.info(f"📋 Scanning all {len(selected_pairs)} pairs")
    # ─── ✅ Apply Exclusion ──────────────────────────────────────────────────
    if EXCLUDE_PAIRS:
        before = len(selected_pairs)
        selected_pairs = [
            p for p in selected_pairs if not any(skip in p for skip in EXCLUDE_PAIRS)
        ]
        skipped = sorted(set(ALL_PAIRS) - set(selected_pairs))
        logger.info(
            f"🚫 EXCLUSION: {before}→{len(selected_pairs)} pairs; "
            f"skipped containing {EXCLUDE_PAIRS}: {', '.join(skipped)}"
        )
    if not selected_pairs:
        logger.error("❌ No pairs after exclusion — aborting")
        send_telegram_message(f"❌ {PROFILE_LABEL}: No pairs to scan")
        return
    # Step 2 — Fetch Data
    pair_data, weekly_ema_cache = {}, {}
    for pair in selected_pairs:
        oanda = YAHOO_TO_OANDA.get(pair)
        if not oanda:
            logger.warning(f"⚠️ No OANDA mapping: {pair} — skip")
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
            weekly_ema_cache[oanda] = fetch_weekly_ema100(oanda, api)
        except Exception as e:
            logger.error(f"❌ Fetch failed {pair}: {e}")
    if not pair_data:
        logger.error("❌ No usable data — aborting")
        send_telegram_message(f"❌ {PROFILE_LABEL}: No usable data")
        return
    # Step 3 — Monte Carlo
    mc_cache = {}
    SKIP_MC_RUN = args.skip_mc or SKIP_MC
    if not SKIP_MC_RUN:
        logger.info("[STEP 3] Monte Carlo Forecasts...")
        mc_gen = MCGenerator(
            fetcher, YAHOO_TO_OANDA, simulations=SIMULATIONS, confidence=CONFIDENCE
        )
        for pair in selected_pairs:
            if pair not in pair_data:
                continue
            mc_data, ok = mc_gen.run_for_pair(pair, df=pair_data[pair]["raw"])
            if ok:
                regime = mc_data.get("regime", "")
                if REQUIRE_STRONG_MOMENTUM and "STRONG MOMENTUM" not in regime:
                    logger.info(f"⏭️ {pair}: {regime} — skip")
                    continue
                mc_cache[pair] = mc_data
                logger.info(f"🎲 MC {pair}: {regime} | P_UP={mc_data['p_up']}%")
    else:
        logger.info("[STEP 3] MC skipped — loading legacy...")
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
        for pair in selected_pairs:
            if pair not in pair_data:
                continue
            dirs = []
            for gran in {"H4": "H4", "1H": "H1", "15m": "M15"}.values():
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
                f"🔗 CONFLUENCE {pair}: BUY={buy_c} SELL={sell_c} → {'PASS' if passes else 'BLOCK'}"
            )
    # Step 5 — Dynamic Exit Manager
    logger.info("[STEP 5] Dynamic Exit Manager...")

    def close_wrap(instr):
        _ok = close_position(
            api, OANDA_ACCOUNT_ID, instr, send_telegram_message, dry_run=args.dry_run
        )
        _closed = True
        with contextlib.suppress(Exception):
            _closed = get_open_position(api, OANDA_ACCOUNT_ID, instr) is None
        update_trade_on_close(
            instr, "ROTATION_OR_TIME_EXIT" if _closed else "CLOSE_FAILED"
        )
        return _ok

    dyn_mgr = DynamicPositionManager(
        api,
        OANDA_ACCOUNT_ID,
        TIMEFRAME,
        cfg(P, "BE_TRIGGER_ATR_MULT", 1.5),
        cfg(P, "TRAIL_TRIGGER_ATR_MULT", 2.5),
        cfg(P, "TRAIL_ATR_MULT", 1.5),
        cfg(P, "MAX_HOLD_BARS", 12),
        dynamic_tp=DYNAMIC_TP,
        tp_raise_thresh_pips=TP_RAISE_THRESHOLD_PIPS,
        telegram_send=send_telegram_message,
        dry_run=args.dry_run,
        zone_trailing=cfg(P, "SL_ZONE_TRAILING", False),
        min_sl_step_pips=cfg(P, "SL_MIN_MOVE_PIPS", 15),
        sl_buffer_pips=cfg(P, "SL_TRAIL_BUFFER_PIPS", 25),
        sl_zone_lookback=cfg(P, "SL_TRAIL_ZONE_LOOKBACK", 6),
        use_h4_escale=cfg(P, "USE_H4_ESCALE", False),
        tp_link_sl=cfg(P, "TP_LINK_SL", False),
        instrument_overrides=cfg(P, "INSTRUMENT_OVERRIDES", {}),
    )
    dyn_mgr.update_all(pair_data, close_wrap)
    # Step 6 — Open Positions
    open_pos_by_oanda, open_pos_count = {}, 0
    logger.info("🔍 Checking open positions...")
    for pair in selected_pairs:
        oanda = YAHOO_TO_OANDA.get(pair)
        if not oanda:
            continue
        pos = get_open_position(api, OANDA_ACCOUNT_ID, oanda)
        open_pos_by_oanda[oanda] = pos is not None
        if pos:
            open_pos_count += 1
            logger.info(
                f"📌 OPEN: {pair} → {oanda} | {pos['side'].upper()} | units={pos['units']}"
            )
    open_slots_remaining = max(0, MAX_OPEN_POSITIONS - open_pos_count)
    open_list = [o.replace("_", "/") for o, s in open_pos_by_oanda.items() if s]
    ready_list = [
        p.replace("=X", "")
        for p in selected_pairs
        if not open_pos_by_oanda.get(YAHOO_TO_OANDA.get(p), False)
    ]
    logger.info(
        f"📊 Open: {open_pos_count}/{MAX_OPEN_POSITIONS} | OPEN: {', '.join(open_list) or 'None'} | READY: {', '.join(ready_list) or 'None'}"
    )
    # Step 7 — Score, Filter, Execute
    logger.info("[STEP 7] Scoring + Trend Filter + SMART TP...")
    pip_cache = {p: pip_size(p) for p in selected_pairs}
    pair_parts = {p: (p[:3], p[3:].replace("=X", "")) for p in selected_pairs}
    all_candidates = []
    _audit_sig_rows = {}
    _xgb_drift_check = []
    _step7_eval = 0
    _step7_pass_score = 0
    _step7_blocked_trend = 0
    _step7_blocked_sl = 0
    for pair in selected_pairs:
        if pair not in pair_data:
            continue
        oanda = pair_data[pair]["oanda"]
        atr_val, rsi_val, adx_val = (
            pair_data[pair]["atr"],
            pair_data[pair]["rsi"],
            pair_data[pair]["adx"],
        )
        # Cooldown
        if pair in last_closed:
            d, r = last_closed[pair]
            if r > 0:
                last_closed[pair] = (d, r - 1)
                logger.info(f"⏳ COOLDOWN {pair}: {r-1} runs — skip")
                continue
            del last_closed[pair]
        # Already open
        if open_pos_by_oanda.get(oanda, False):
            logger.info(f"⏭️ {pair}: already open — skip")
            append_to_csv(
                SIGNAL_LOG_PATH,
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "profile": PROFILE_NAME,
                    "account": ACCOUNT_NAME,
                    "pair": pair,
                    "score_final": "",
                    "score_s": "",
                    "score_r": "",
                    "score_a": "",
                    "score_x": "",
                    "score_m": "",
                    "action_taken": "POSITION_ALREADY_OPEN",
                },
            )
            continue
        # Current price
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
        # Strength gap
        base, quote = pair_parts[pair]
        gap = strength_scores.get(base, 0) - strength_scores.get(quote, 0)
        if abs(gap) < MIN_STRENGTH_GAP:
            logger.info(f"⏭️ {pair}: gap={abs(gap):.2f} < {MIN_STRENGTH_GAP} — skip")
            append_to_csv(
                SIGNAL_LOG_PATH,
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "profile": PROFILE_NAME,
                    "account": ACCOUNT_NAME,
                    "pair": pair,
                    "score_final": "",
                    "score_s": "",
                    "score_r": "",
                    "score_a": "",
                    "score_x": "",
                    "score_m": "",
                    "action_taken": "GAP_TOO_SMALL",
                },
            )
            continue
        _step7_eval += 1
        _sig_row = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "profile": PROFILE_NAME,
            "account": ACCOUNT_NAME,
            "pair": pair,
            "score_final": "",
            "score_s": "",
            "score_r": "",
            "score_a": "",
            "score_x": "",
            "score_m": "",
            "action_taken": "PENDING",
        }
        # Confluence
        if MULTI_TF_CONFLUENCE and not tf_confluence.get(pair, {}).get("passes", True):
            logger.info(f"🚫 {pair}: confluence fail — skip")
            _sig_row["action_taken"] = "NO_CONSENSUS"
            append_to_csv(SIGNAL_LOG_PATH, _sig_row)
            continue
        # Model & MC
        sig = strat_engine.generate_signal(
            pair,
            oanda,
            pair_data[pair]["df"],
            mc_cache.get(pair),
            strength_scores,
            current,
            spread_pips,
        )
        prob_raw = getattr(sig, "model_p_up", None) or 0.0
        mc_pct_up = mc_cache.get(pair, {}).get("p_up", 50.0)
        # Score
        direction, w = calc_weighted_score(
            pair, gap, rsi_val, adx_val, prob_raw, mc_pct_up
        )
        # Drift watch (USD pairs only)
        if "USD" in base or "USD" in quote:
            sd = (
                "BUY"
                if gap >= MIN_STRENGTH_GAP
                else "SELL" if gap <= -MIN_STRENGTH_GAP else None
            )
            xd = "BUY" if prob_raw >= XGB_BULLISH_THRESHOLD else "SELL"
            if sd:
                _xgb_drift_check.append((pair, sd, xd))
        if not (direction and w and w["PASS"]):
            if w and not w["PASS"]:
                logger.info(f"➖ {pair}: FINAL {w['FINAL']:.1f} < {w['THRESHOLD']}")
                _sig_row.update(
                    {
                        "score_final": round(w["FINAL"], 2),
                        "score_s": round(w["S"], 2),
                        "score_r": round(w["R"], 2),
                        "score_a": round(w["A"], 2),
                        "score_x": round(w["X"], 2),
                        "score_m": round(w["M"], 2),
                        "action_taken": "BELOW_SCORE_THRESHOLD",
                    }
                )
                append_to_csv(SIGNAL_LOG_PATH, _sig_row)
            else:
                _sig_row["action_taken"] = "NO_CONSENSUS"
                append_to_csv(SIGNAL_LOG_PATH, _sig_row)
            continue
        logger.info(
            f"⚖️ {pair} {direction} | S={w['S']:4.1f}×{W_S:.2f}={w['S']*W_S:4.1f}  "
            f"R={w['R']:4.1f}×{W_R:.2f}={w['R']*W_R:4.1f}  "
            f"A={w['A']:4.1f}×{W_A:.2f}={w['A']*W_A:4.1f}  "
            f"X={w['X']:4.1f}×{W_X:.2f}={w['X']*W_X:4.1f}  "
            f"M={w['M']:4.1f}×{W_M:.2f}={w['M']*W_M:4.1f}  | FINAL={w['FINAL']:4.1f}"
        )
        _sig_row.update(
            {
                "score_final": round(w["FINAL"], 2),
                "score_s": round(w["S"], 2),
                "score_r": round(w["R"], 2),
                "score_a": round(w["A"], 2),
                "score_x": round(w["X"], 2),
                "score_m": round(w["M"], 2),
            }
        )
        # Trend Filter + Smart TP + Weekly EMA100 Buffer Zone
        weekly_ema100_price = weekly_ema_cache.get(oanda)
        (
            allow_entry,
            smart_tp_pips,
            tp_info,
            lot_mult,
            tp_mult_reduce,
        ) = evaluate_trend_and_tp(
            PROFILE_NAME,
            direction,
            mc_pct_up,
            current,
            pip_cache[pair],
            pair_data[pair]["df"],
            weekly_ema100_price,
            ema_cross_filter=TREND_FILTER_ENABLED,
            fast_period=EMA_PERIOD_FAST,
            slow_period=EMA_PERIOD_SLOW,
            base_tp_pips=BASE_TP_PIPS,
            mc_strong_threshold=MC_STRONG_THRESHOLD,
            tp_mult=TP_MULT,
            tp_strong_mult=TP_STRONG_MULT,
            ema100_buffer_pips=EMA100_BUFFER_PIPS,
            ema100_tp_floor_pips=EMA100_TP_FLOOR_PIPS,
            week_ema100_filter_enabled=WEEK_EMA100_FILTER_ENABLED,
            timeframe=TIMEFRAME,
        )
        if not allow_entry:
            _step7_blocked_trend += 1
            action_label, _, human_reason = tp_info.partition(": ")
            logger.info(f"🚫 {action_label} {pair} {direction}: {human_reason}")
            _sig_row["action_taken"] = action_label
            append_to_csv(SIGNAL_LOG_PATH, _sig_row)
            continue
        # SL & TP
        dec = 3 if "JPY" in pair else 5
        if cfg(P, "SL_USE_ZONE_HIERARCHY", True):
            try:
                h4_df = fetch_candles(api, oanda, "H4", count=5)
                if h4_df is None or len(h4_df) < 5:
                    raise ValueError("insufficient H4")
                h4_closed = [
                    {"high": float(r["High"]), "low": float(r["Low"])}
                    for _, r in h4_df.iloc[:-1].iterrows()
                ]
                sl_price, sl_pips, skip_trade = calculate_stop_loss(
                    direction, current, h4_closed, pip_cache[pair]
                )
                if skip_trade:
                    _step7_blocked_sl += 1
                    logger.warning(f"🚫 {pair}: SL > 200pips — abort")
                    _sig_row["action_taken"] = "SL_TOO_WIDE"
                    append_to_csv(SIGNAL_LOG_PATH, _sig_row)
                    continue
                sl_price = round(sl_price, dec)
            except Exception:
                sl_pips = max(
                    MIN_SL_PIPS_JPY if "JPY" in pair else MIN_SL_PIPS,
                    round(atr_val / pip_cache[pair] * ATR_SL_MULT, 1),
                )
                sl_price = (
                    round(current - sl_pips * pip_cache[pair], dec)
                    if direction == "BUY"
                    else round(current + sl_pips * pip_cache[pair], dec)
                )
        else:
            sl_pips = max(
                MIN_SL_PIPS_JPY if "JPY" in pair else MIN_SL_PIPS,
                round(atr_val / pip_cache[pair] * ATR_SL_MULT, 1),
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
        _step7_pass_score += 1
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
                lot_mult,
            )
        )
        _audit_sig_rows[oanda] = _sig_row
    # Drift warning
    if _xgb_drift_check:
        _n_total = len(_xgb_drift_check)
        _n_disagree = sum(1 for _, _sd, _xd in _xgb_drift_check if _sd != _xd)
        if _n_disagree / _n_total > 0.5:
            logger.warning(
                f"⚠️ XGB model drift: disagrees with currency strength on {_n_disagree}/{_n_total} USD pairs — "
                f"consider retraining trade_model_xgb.pkl"
            )
    all_candidates.sort(key=lambda x: x[0])
    logger.info(f"🔍 Total candidates after ranking: {len(all_candidates)}")
    if len(all_candidates) == 0:
        logger.info("🏆 RANKED: 0 passed — no orders this run")
    else:
        logger.info(
            f"🏆 RANKED: {len(all_candidates)} passed → opening top {open_slots_remaining} (slots={open_slots_remaining})"
        )

    executed_in_this_run = set()
    executed_count = 0
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
        tp_pips,
        lot_mult,
    ) in all_candidates:
        if executed_count >= open_slots_remaining:
            logger.info(
                f"🛑 Reached MAX_OPEN={MAX_OPEN_POSITIONS} ({open_pos_count} open + {executed_count} new) → STOPPED"
            )
            break
        if open_pos_by_oanda.get(oanda, False):
            logger.info(f"⏭️ {pair}: already open — SKIP")
            continue
        if oanda in executed_in_this_run:
            logger.info(f"⏭️ {pair}: already selected THIS run — SKIP")
            continue

        lot = int(DEFAULT_LOT_SIZE * lot_mult)
        logger.info(
            f"📤 EXECUTE: {pair} {direction} | SL={sl_price:.{dec}f} | TP={tp_price:.{dec}f} | TP={tp_pips:.1f}p | LOT={lot} (×{lot_mult})"
        )
        if not args.dry_run:
            margin_ok, margin_msg = check_margin_available(
                api, OANDA_ACCOUNT_ID, oanda, lot, current
            )
            if not margin_ok:
                logger.warning(f"⛔ SKIP {pair}: {margin_msg}")
                continue
            logger.info(f"💰 {margin_msg}")
        try:
            result = open_oanda_order(
                api,
                OANDA_ACCOUNT_ID,
                oanda,
                direction,
                lot,
                sl_price=sl_price,
                tp_price=tp_price,
                client_id=oanda,
                dry_run=args.dry_run,
            )
            if result.get("ok"):
                executed_in_this_run.add(oanda)
                executed_count += 1
                logger.info(
                    f"✅ ORDER OPENED: {pair} {direction} | SL={sl_price:.{dec}f} TP={tp_price:.{dec}f}"
                )
                # ── AUDIT trade_log OPEN row — FIX 1: full scores ──────────────
                _t_id = result.get("trade_id") or f"DRY_RUN_{oanda}"
                _sref = _audit_sig_rows.get(oanda, {})
                append_to_csv(
                    TRADE_LOG_PATH,
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "trade_id": _t_id,
                        "profile": PROFILE_NAME,
                        "account": ACCOUNT_NAME,
                        "pair": oanda,
                        "direction": direction,
                        "entry_price": round(current, dec),
                        "sl_price": round(sl_price, dec),
                        "tp_price": round(tp_price, dec),
                        "score_final": _sref.get("score_final", round(FINAL, 2)),
                        # FIX 1: full snapshot — sub-scores from cached signal row
                        "score_s": _sref.get("score_s", ""),
                        "score_r": _sref.get("score_r", ""),
                        "score_a": _sref.get("score_a", ""),
                        "score_x": _sref.get("score_x", ""),
                        "score_m": _sref.get("score_m", ""),
                        "pips": "",  # FIX 2: intentionally empty
                        "profit_usd": "",  # filled on close
                        "exit_reason": "",  # filled on close
                        "exit_time": "",  # filled on close
                    },
                )
                logger.info(f"📝 AUDIT OPEN row trade_id={_t_id} pair={oanda}")
                # ── AUDIT signal_log PASS_GATE ────────────────────────────────
                if _sref:
                    _sref["action_taken"] = "PASS_GATE"
                    append_to_csv(SIGNAL_LOG_PATH, _sref)
            else:
                logger.error(
                    f"❌ ORDER FAILED: {pair} — {result.get('error', 'Unknown error')}"
                )
        except Exception as e:
            logger.error(f"❌ EXCEPTION opening {pair}: {e}")

    # ── FIX 3: write NO_CONSENSUS for gap-qualified pairs evaluated but NOT
    #    executed (slot limit reached / position opened meanwhile / order failed).
    #    Runs AFTER the execution loop so PASS_GATE rows are never double-logged.
    for _oanda, _srow in list(_audit_sig_rows.items()):
        if _srow.get("action_taken") == "PENDING":
            _srow["action_taken"] = "NO_SLOT_MAX_OPEN"
            append_to_csv(SIGNAL_LOG_PATH, _srow)
            logger.info(f"📝 AUDIT signal NO_SLOT_MAX_OPEN pair={_srow.get('pair')}")

    logger.info(
        f"📈 STEP7 summary: evaluated={_step7_eval} | passed_score={_step7_pass_score} | "
        f"blocked_trend={_step7_blocked_trend} | blocked_sl={_step7_blocked_sl} | "
        f"executed={executed_count}"
    )

    logger.info(f"\n✅ {PROFILE_LABEL} RUN COMPLETE")


# ─── ENTRY POINT ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("⏹️ Interrupted by user")
    except Exception as e:
        logger.critical(f"💥 FATAL ERROR: {e}", exc_info=True)
        send_telegram_message(f"💥 FX BOT {PROFILE_LABEL} FATAL ERROR:\n{str(e)}")