# config_bot.py — v6.8.6 · UNIFIED STRATEGY CONFIG
"""
ALL strategy/profile settings in ONE file.
OANDA API/connection → config_oanda.py (KEPT SEPARATE)

Purpose: Strategy & profile parameters ONLY.
Connection tokens/env → config_oanda.py (runtime config)
"""

# ==========================================
# GLOBAL DEFAULTS — shared across profiles
# ==========================================
ALL_PAIRS = [
    "EURUSD=X",
    "GBPUSD=X",
    "EURJPY=X",
    "GBPJPY=X",
    "AUDUSD=X",
    "USDJPY=X",
    "GBPAUD=X",
    "USDCHF=X",
    "AUDJPY=X",
    "EURGBP=X",
    "NZDUSD=X",
    "CADJPY=X",
]
YAHOO_TO_OANDA = {
    "EURUSD=X": "EUR_USD",
    "GBPUSD=X": "GBP_USD",
    "EURJPY=X": "EUR_JPY",
    "GBPJPY=X": "GBP_JPY",
    "AUDUSD=X": "AUD_USD",
    "USDJPY=X": "USD_JPY",
    "GBPAUD=X": "GBP_AUD",
    "USDCHF=X": "USD_CHF",
    "AUDJPY=X": "AUD_JPY",
    "EURGBP=X": "EUR_GBP",
    "NZDUSD=X": "NZD_USD",
    "CADJPY=X": "CAD_JPY",
}

# Data / MC defaults
YF_INTERVAL = "4h"
YF_PERIOD_FULL = "30d"
YF_PERIOD_RESAMPLE = "60d"
YF_INTERVAL_D = "1d"
YF_PERIOD_FULL_D = "120d"
YF_PERIOD_RESAMPLE_D = "180d"

PERIODS_YEAR = 252
MC_BAND_PCT = 90
MC_MAX_AGE_HOURS = 24
SIMULATIONS = 5000
CONFIDENCE = MC_BAND_PCT / 100.0

ATR_PERIOD = 14
BASE_TP_PIPS = 50
EMA100_BUFFER_PIPS = 30
MIN_SL_PIPS = 35
MIN_SL_PIPS_JPY = MIN_SL_PIPS + 10

DEBUG_MODE = False
NO_COOLDOWN = True
DEFAULT_LOT_SIZE = 10000

# Confluence / multi-TF
MULTI_TF_CONFLUENCE = False
CONFLUENCE_REQUIRED_TFS = 2

# Dynamic TP / Exit
TRAILING_TP = True
DYNAMIC_TP = False
TP_RAISE_THRESHOLD_PIPS = 15

# Lookback / Forecast
H4_LOOKBACK = 90
H4_FORECAST = 8
DAILY_LOOKBACK = 90
DAILY_FORECAST = 5

# Feature / Model
USE_ATR = True
USE_MACD = True
USE_RSI = True
USE_ADX = True
MODEL_TYPE = "xgboost"
TARGET_HORIZON = 6
TRAIN_LOOKBACK_BARS = 5000

# ==========================================
# 🔑 ACCOUNT IDs ONLY — reference config_oanda connection
# ==========================================
from config_oanda import (
    OANDA_ACCOUNT_ID_2 as OANDA_ACCOUNT_ID_PROFILE2,
    OANDA_ACCOUNT_ID_3 as OANDA_ACCOUNT_ID_PROFILE3,
    OANDA_ACCOUNT_ID_4 as OANDA_ACCOUNT_ID_PROFILE4,
)

# ==========================================
# 📊 PROFILE STRATEGY CONFIG — ALL IN ONE
# ==========================================
PROFILE_CFG = {
    "profile2": {
        "LABEL": "PROFILE2",
        "ACCOUNT_NAME": "Account 002",
        "OANDA_ACCOUNT_ID": OANDA_ACCOUNT_ID_PROFILE2,
        "COOLDOWN_FILE": "cooldown_profile2.json",
        "RESULTS_DIR": "daily_results_profile2",
        # ── Identity ──
        "MODE": "LEVEL10",
        "BASE_MIN_EDGE": 0.50,
        # ── Weights: S=35 R=20 A=15 X=20 M=10 ──
        "WEIGHT_STRENGTH": 0.35,
        "WEIGHT_RSI": 0.20,
        "WEIGHT_ADX": 0.15,
        "WEIGHT_XGB": 0.20,
        "WEIGHT_MC": 0.10,
        # ── Thresholds ──
        "MIN_CONVICTION_SCORE": 30.0,
        "MIN_SCORE_GAP": 0.10,
        "MAX_OPEN_POSITIONS": 3,
        "MAX_OPEN_PER_RUN": 1,
        "XGB_BULLISH_THRESHOLD": 0.52,
        "MC_BULLISH_THRESHOLD_PCT": 52.0,
        "MC_STRONG_THRESHOLD": 0.60,
        "REQUIRE_DIRECTION_CONSENSUS": True,
        "CONSENSUS_THRESHOLD": 2,
        "CONSENSUS_REQUIRED_VOTES": 2,
        "REQUIRE_STRONG_MOMENTUM": False,
        "ADX_SCALE_FACTOR": 2.0,
        # ── TREND FILTER: Profile2 = OFF ──
        "TREND_FILTER_ENABLED": False,
        "WEEK_EMA100_FILTER_ENABLED": False,
        "EMA_PERIOD_FAST": 20,
        "EMA_PERIOD_SLOW": 40,
        # ── TP/SL multipliers ──
        "TP_MULT": 2.0,
        "TP_STRONG_MULT": 2.5,
        "ATR_SL_MULT": 2.0,
        "ATR_TP_MULT": 2.5,
        # ── Dynamic Exit ──
        "USE_DYNAMIC_SL": 2,
        "DYNAMIC_SL_MULT": 1.5,
        "BE_TRIGGER_ATR_MULT": 2.5,  # 1.5 → 2.5 · 晚一点推保本，让利润先跑
        "TRAIL_TRIGGER_ATR_MULT": 3.5,  # 2.5 → 3.5 · 更大盈利才启动 trailing
        "TRAIL_ATR_MULT": 2.8,  # 1.5 → 2.8 · trailing 距离加宽，给回调留空间
        "MAX_HOLD_BARS": 24,  # 12 → 24 · 15m TF: 3h → 6h，单边行情更多时间
        # ── SL Strategy ──
        "SL_USE_ZONE_HIERARCHY": True,
        # ── Pair Selection ──
        "USE_TOP_PAIRS_ONLY": False,
        "TOP_PAIRS_COUNT": 4,
        "TOP_PAIRS_MIN_GAP": 0.25,
        # ── MC ──
        "SKIP_MC": False,
        "EXCLUDE_CURRENCIES": ["NZD", "CAD", "CHF", "JPY"],  # 🚫 不碰 NZD/CAD/CHF
    },
    "profile3": {
        "LABEL": "PROFILE3",
        "ACCOUNT_NAME": "Account 003",
        "OANDA_ACCOUNT_ID": OANDA_ACCOUNT_ID_PROFILE3,
        "COOLDOWN_FILE": "cooldown_profile3.json",
        "RESULTS_DIR": "daily_results_profile3",
        # ── Identity ──
        "MODE": "LEVEL10",
        "BASE_MIN_EDGE": 0.50,
        # ── Weights: S=40 R=15 A=15 X=20 M=10 ──
        "WEIGHT_STRENGTH": 0.40,
        "WEIGHT_RSI": 0.15,
        "WEIGHT_ADX": 0.15,
        "WEIGHT_XGB": 0.20,
        "WEIGHT_MC": 0.10,
        # ── Thresholds ──
        "MIN_CONVICTION_SCORE": 20.0,
        "MIN_SCORE_GAP": 0.10,
        "MAX_OPEN_POSITIONS": 6,
        "MAX_OPEN_PER_RUN": 2,
        "XGB_BULLISH_THRESHOLD": 0.55,
        "MC_BULLISH_THRESHOLD_PCT": 55.0,
        "MC_STRONG_THRESHOLD": 0.55,
        "REQUIRE_DIRECTION_CONSENSUS": True,
        "CONSENSUS_THRESHOLD": 2,
        "CONSENSUS_REQUIRED_VOTES": 2,
        "REQUIRE_STRONG_MOMENTUM": False,
        "ADX_SCALE_FACTOR": 2.0,
        # ── TREND FILTER: Profile3 = ON + Weekly EMA100 ──
        "TREND_FILTER_ENABLED": True,
        "WEEK_EMA100_FILTER_ENABLED": True,
        "EMA_PERIOD_FAST": 40,
        "EMA_PERIOD_SLOW": 80,
        # ── TP/SL multipliers ──
        "TP_MULT": 2.5,
        "TP_STRONG_MULT": 3.0,
        "ATR_SL_MULT": 2.5,
        "ATR_TP_MULT": 3.0,
        # ── Dynamic Exit ──
        "USE_DYNAMIC_SL": 2,
        "DYNAMIC_SL_MULT": 1.5,
        "BE_TRIGGER_ATR_MULT": 1.5,
        "TRAIL_TRIGGER_ATR_MULT": 2.5,
        "TRAIL_ATR_MULT": 1.5,
        "MAX_HOLD_BARS": 12,
        # ── SL Strategy ──
        "SL_USE_ZONE_HIERARCHY": True,
        # ── Pair Selection ──
        "USE_TOP_PAIRS_ONLY": False,
        "TOP_PAIRS_COUNT": 4,
        "TOP_PAIRS_MIN_GAP": 0.25,
        # ── MC ──
        "SKIP_MC": False,
        "SL_ZONE_TRAILING": True,
        # ── Pair Exclusion ──
        "EXCLUDE_CURRENCIES": [],
    },
    # ✅ ─── Profile4 / Account004 · DEMO 全新独立 ───
    "profile4": {
        "LABEL": "PROFILE4",
        "ACCOUNT_NAME": "Account 004",
        "OANDA_ACCOUNT_ID": OANDA_ACCOUNT_ID_PROFILE4,
        "COOLDOWN_FILE": "cooldown_profile4.json",
        "RESULTS_DIR": "daily_results_profile4",
        # ── Identity ──
        "MODE": "LEVEL10",
        "BASE_MIN_EDGE": 0.50,
        "DEFAULT_LOT_SIZE": 5000,  # ✅ Added: Demo half-size
        # ── Weights: S=40 R=15 A=15 X=20 M=10 ──
        "WEIGHT_STRENGTH": 0.40,
        "WEIGHT_RSI": 0.15,
        "WEIGHT_ADX": 0.15,
        "WEIGHT_XGB": 0.20,
        "WEIGHT_MC": 0.10,
        # ── Thresholds (FINAL · 关 WEEKLY EMA100，留 TREND FILTER) ──
        "MIN_CONVICTION_SCORE": 15.0,  # 20.0 → 15.0 · 捞回擦边球
        "MIN_SCORE_GAP": 0.05,  # 0.10 → 0.05 · 低 gap 也能参与共识
        # ── Position Limits ──
        "MAX_OPEN_POSITIONS": 10,
        "MAX_OPEN_PER_RUN": 3,
        "MAX_OPEN_HIGH_VOL": 6,
        "MAX_OPEN_MID_VOL": 2,
        "MAX_OPEN_LOW_VOL": 2,
        # ── JPY 方向共识 ──
        "JPY_CONSENSUS_MIN": 2,
        "JPY_MAX_OPEN_PER_RUN": 2,
        # ── SL caps ──
        "MIN_SL_PIPS": 35,
        "MIN_SL_PIPS_JPY": 60,
        "SL_MAX_ALLOWED_PIPS": 200,
        "SL_MAX_ALLOWED_PIPS_JPY": 500,
        "XGB_BULLISH_THRESHOLD": 0.52,  # 0.55 → 0.52 · 减少 strength/XGB 分裂投票
        "MC_BULLISH_THRESHOLD_PCT": 52.0,  # 55.0 → 52.0 · MC 信号更平衡
        "MC_STRONG_THRESHOLD": 0.55,
        "REQUIRE_DIRECTION_CONSENSUS": True,
        "CONSENSUS_THRESHOLD": 2,
        "CONSENSUS_REQUIRED_VOTES": 2,
        "REQUIRE_STRONG_MOMENTUM": False,
        "ADX_SCALE_FACTOR": 2.0,
        # ── TREND FILTER: 关周 EMA100（最大瓶颈），留 EMA crossover（这版本紧要之处） ──
        "TREND_FILTER_ENABLED": True,
        "WEEK_EMA100_FILTER_ENABLED": False,  # True → False · 🔴 周一亚盘挡了 6+ 单
        "EMA_PERIOD_FAST": 15,  # 40 → 20 · 更敏捷
        "EMA_PERIOD_SLOW": 30,  # 80 → 40 · 减少滞后挡单
        # ── TP/SL multipliers ──
        "TP_MULT": 2.5,
        "TP_STRONG_MULT": 3.0,
        "ATR_SL_MULT": 2.5,
        "ATR_TP_MULT": 3.0,
        # ── Dynamic Exit ──
        "USE_DYNAMIC_SL": 2,
        "DYNAMIC_SL_MULT": 1.5,
        "BE_TRIGGER_ATR_MULT": 1.5,
        "TRAIL_TRIGGER_ATR_MULT": 2.5,
        "TRAIL_ATR_MULT": 1.5,
        "MAX_HOLD_BARS": 12,
        # ── PROFILE4 H4-ESCALE + TP LINK ──
        "USE_H4_ESCALE": True,
        "TP_LINK_SL": True,
        # ── SL Strategy ──
        "SL_USE_ZONE_HIERARCHY": True,
        # ── Pair Selection ──
        "USE_TOP_PAIRS_ONLY": False,
        "TOP_PAIRS_COUNT": 4,
        "TOP_PAIRS_MIN_GAP": 0.25,
        # ── MC ──
        "SKIP_MC": False,
        # ── Pair Exclusion ──
        "EXCLUDE_CURRENCIES": [],
    },
}

# ==========================================
# 🎯 PAIR STRATEGY GROUPS — per-pair overrides (profile3 only)
# ==========================================
# 新增一组 = 加一个 dict entry，无需改代码
# 每个 group 可以 override: timeframe, sl_lookback_bars, sl_buffer_pips,
# min_sl_pips, max_sl_pips, confirmation_candle, min_hold_bars, max_hold_bars

PAIR_STRATEGY_GROUPS = {
    # ── D1 Daily 模式组 ──
    "GBP_AUD": {
        "label": "D1_DAILY_HIGH_BETA",
        "timeframe_override": "D1",  # D = Daily
        "sl_lookback_bars": 10,
        "sl_buffer_pips": 20,
        "min_sl_pips": 50,
        "max_sl_pips": 200,
        "confirmation_candle": "CLOSE",  # SL/trailing 只在 D1 收盘后触发
        "min_hold_bars": 4,
        "max_hold_bars": 12,
    },
    # ── 未来可加的组 ──
    # "EUR_USD": {
    #     "label": "TREND_FOLLOWER",
    #     "timeframe_override": "H4",
    #     ...
    # },
}