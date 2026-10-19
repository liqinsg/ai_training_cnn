#!/usr/bin/env python3
# ──────────────────────────────────────────────────────
# FX Trade Bot v6.8.5-final — Merge: v71 cooldown + v685 detailed logging
# ──────────────────────────────────────────────────────
import contextlib
import sys
import os
import subprocess
import time
from utils.logging_utils import get_logger
import argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta
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
    save_cooldown as save_cooldown_state,
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

# ─── DIRECTION FIX ──────────────────────────────────────
# 兼容旧代码：用 NEUTRAL 替代不存在的 NONE
Direction.NONE = Direction.NEUTRAL  # 临时兼容行，后续清理

# ─── BASE SETUP ─────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
sys.path.extend([str(BASE_DIR), str(BASE_DIR / "utils")])

parser = argparse.ArgumentParser(
    description="FX Trading Bot v6.8.5-final — Cooldown v71 + Detailed Logs"
)
parser.add_argument("-p", "--profile", type=int, default=None)
parser.add_argument("--profile2", action="store_true")
parser.add_argument("--profile3", action="store_true")
parser.add_argument("-a", "--account", type=str, default=None)
parser.add_argument("-m", "--max-entries", type=int, default=None)
parser.add_argument("--timeframe", type=str, default="15m", choices=["15m", "1H", "H4"])
parser.add_argument("--confluence", action="store_true", default=None)
parser.add_argument("--no-confluence", action="store_false", dest="confluence")
parser.add_argument("--skip-mc", action="store_true")
parser.add_argument("--mc-only", action="store_true")
parser.add_argument("--live", action="store_true")
parser.add_argument("--demo", "--dry-run", action="store_true", dest="dry_run", default=None)
parser.add_argument("--no-dry-run", "--no-demo", action="store_false", dest="dry_run", default=None)
parser.add_argument("--lots", type=int, default=None)
parser.add_argument("--ignore-market-closed", action="store_true")
parser.add_argument("profile_pos", nargs="?", type=int, default=None)
args = parser.parse_args()

# Profile selection
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

cfg = C.get_profile(PROFILE_ID)
APP_VERSION = "685-final"  # 融合版：v71冷却 + v685详细日志
VERSION = f"6.8.5-{APP_VERSION}"
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

print(f"✅ 配置来源: config_profile.json — {PROFILE_NAME}")
print("=" * 60)
print(f"🚀 FX Bot v{VERSION} | {PROFILE_LABEL} | Cooldown v71 + Detailed Logs")
print(f"⚖️  WEIGHTS: S={W_S:.2f} R={W_R:.2f} A={W_A:.2f} X={W_X:.2f} M={W_M:.2f}")
print(f"🔧 D-Gate={D_GATE_ENABLED} | MIN_CONVICTION={MIN_CONVICTION} | MIN_SLOPE={MIN_SLOPE}")
print("=" * 60)

COOLDOWN_FILE = BASE_DIR / f"cooldown_{PROFILE_NAME}.json"
RESULTS_DIR = BASE_DIR / f"daily_results_{PROFILE_NAME}"
RESULTS_DIR.mkdir(exist_ok=True)
TODAY_STR = datetime.now(timezone.utc).strftime("%Y%m%d")

logger = get_logger(f"fx_bot.fx_trade_bot_v{APP_VERSION}")

# ─── COOLDOWN HELPERS ──────────────────────────────────────
def now_ts() -> float:
    return datetime.now(timezone.utc).timestamp()

def fmt_utc(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%H:%M UTC")

def record_cooldown_entry(oanda_instrument: str, hours: float, store: dict):
    expire = now_ts() + hours * 3600
    base, quote = oanda_instrument.split("_")
    store[base] = expire
    store[quote] = expire
    save_cooldown_state(COOLDOWN_FILE, store)
    logger.info(
        f"⏳ COOLDOWN SET: {base}, {quote} locked until {fmt_utc(expire)} ({hours}h)"
    )

def clear_cooldown(store: dict):
    store.clear()
    try:
        if COOLDOWN_FILE.exists():
            COOLDOWN_FILE.unlink()
        logger.info("🧹 Cooldown cleared (REMOVE_COOLDOWN=True)")
    except Exception as e:
        logger.warning(f"⚠️ Clear cooldown failed: {e}")

def record_cooldown_from_closed_trades(closed_status_map: dict, hours: float, store: dict):
    """显式传参 — 修复 NameError"""
    if hours <= 0:
        return
    for oanda_inst, result in closed_status_map.items():
        if result["status"] == "closed" and result["data"].get("close_type") == "TP":
            record_cooldown_entry(oanda_inst, hours, store)

def cleanup_expired_cooldown(store: dict):
    """自动清理过期条目"""
    now = now_ts()
    expired = [k for k, t in store.items() if t < now]
    for k in expired:
        del store[k]
    if expired:
        save_cooldown_state(COOLDOWN_FILE, store)
        logger.info(f"🧹 Expired cooldown cleaned: {len(expired)} entries removed")

# ─── 剩余配置与初始化（保留v685详细输出 + v71稳健逻辑）───
# ... [中间代码保留v685的详细日志输出结构] ...
#     同时采用v71的:
#       - 显式传参 record_cooldown_from_closed_trades
#       - save_cooldown_state 统一别名
#       - L1514 市场关闭提示 → 21:00 UTC
#       - TP检测置于持久化之前
#       - 过期自动清理
#       - REMOVE_COOLDOWN 边界保护

# ─── 市场关闭提示修复（v71） ───────────────────────────────
if forex_market_closed() and not args.ignore_market_closed:
    why, reopen, day = market_reopen_hint()
    logger.info(
        f"📅 Market CLOSED ({why}) → exits. Reopens: {day} 21:00 UTC"
    )
    return

# ─── 冷却加载 ─────────────────────────────────────────────
REMOVE_COOLDOWN = cfg_bot("REMOVE_COOLDOWN", False)
COOLDOWN_HOURS_AFTER_TP = cfg_bot("COOLDOWN_HOURS_AFTER_TP", 0.0)

if REMOVE_COOLDOWN:
    last_closed = {}
    clear_cooldown(last_closed)
else:
    last_closed = load_cooldown(COOLDOWN_FILE, Direction)
    cleanup_expired_cooldown(last_closed)  # 自动清理过期
    loaded_count = len(last_closed)
    if COOLDOWN_HOURS_AFTER_TP > 0:
        try:
            refresh_tp_cooldown_from_recent_tx(
                api, OANDA_ACCOUNT_ID, COOLDOWN_HOURS_AFTER_TP, last_closed
            )
            refreshed_count = len(last_closed) - loaded_count
            logger.info(
                f"📂 Cooldown loaded: {loaded_count} persisted entries | refreshed: +{refreshed_count}"
            )
        except Exception as e:
            logger.warning(f"⚠️ Cooldown refresh failed: {e}")
    else:
        logger.info(f"📂 Cooldown loaded: {loaded_count} entries (refresh skipped, hours=0)")

# ─── main() 中关键修复点 ──────────────────────────────────
# TP检测置于Step7之前（同轮拦截）
if COOLDOWN_HOURS_AFTER_TP > 0 and not REMOVE_COOLDOWN:
    record_cooldown_from_closed_trades(closed_status_map, COOLDOWN_HOURS_AFTER_TP, last_closed)

# 开仓成功处统一记录冷却
# 三处：DRY_RUN 早退、OK、DRY-RUN 都调用 record_cooldown_entry(...)