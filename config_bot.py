# config_bot.py — v6.8.5.1 · UNIFIED SINGLE-FILE CONFIG
"""
Central configuration — ALL profiles in one file.
Usage: fx_trade_bot.py --profile2 / --profile3
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# 🔐 OANDA CONNECTION (Global)
# ==========================================
OANDA_ENV = "practice"
OANDA_API_TOKEN = os.getenv("OANDA_API_TOKEN", "")
OANDA_ACCOUNT_ID_1 = os.getenv("OANDA_ACCOUNT_ID_1", "")
OANDA_ACCOUNT_ID_2 = os.getenv("OANDA_ACCOUNT_ID_2", "")
OANDA_ACCOUNT_ID_3 = os.getenv("OANDA_ACCOUNT_ID_3", "")
OANDA_TOKEN = OANDA_API_TOKEN


# ==========================================
# ⚙️ BASE DEFAULTS / LEVEL10 PRESET
# ==========================================
CHECK_INTERVAL_MINUTES = 15
TIMEFRAME = "15m"
DEFAULT_LOT_SIZE = 10000
MAX_SIMULTANEOUS_TRADES = 5
MIN_CONVICTION_SCORE = 40.0
MIN_REWARD_RISK = 1.001
REQUIRE_DIRECTION_CONSENSUS = True
CONSENSUS_THRESHOLD = 2
CONSENSUS_REQUIRED_VOTES = 2
ATR_PERIOD = 14
BASE_TP_PIPS = 50
EMA100_BUFFER_PIPS = 30
# ——— 货币对 / 数据源 / 时间周期 / 风控阈值等全部保留 ———
ALL_PAIRS = [
    "EURUSD=X", "GBPUSD=X", "EURJPY=X", "GBPJPY=X",
    "AUDUSD=X", "USDJPY=X", "GBPAUD=X", "USDCHF=X",
    "AUDJPY=X", "EURGBP=X", "NZDUSD=X", "CADJPY=X",
]
YAHOO_TO_OANDA = {
    "EURUSD=X": "EUR_USD", "GBPUSD=X": "GBP_USD",
    "EURJPY=X": "EUR_JPY", "GBPJPY=X": "GBP_JPY",
    "AUDUSD=X": "AUD_USD", "USDJPY=X": "USD_JPY",
    "GBPAUD=X": "GBP_AUD", "USDCHF=X": "USD_CHF",
    "AUDJPY=X": "AUD_JPY", "EURGBP=X": "EUR_GBP",
    "NZDUSD=X": "NZD_USD", "CADJPY=X": "CAD_JPY",
}
YF_INTERVAL = "4h"
YF_PERIOD_FULL = "30d"
YF_PERIOD_RESAMPLE = "60d"
YF_INTERVAL_D = "1d"
PERIODS_YEAR = 252
MC_BAND_PCT = 90
MC_SIGNIFICANT_PCT = 60
MC_MOMENTUM_BAND = 0.001
REENTRY_COOLDOWN_MINUTES = 0.001
REENTRY_MIN_PULLBACK_PIPS = 8.0
TRAILING_TP = True
DYNAMIC_TP = False
TP_RAISE_THRESHOLD_PIPS = 15
MIN_SL_PIPS = 35
MIN_SL_PIPS_JPY = MIN_SL_PIPS + 10
REMOVE_COOLDOWN = True
DEBUG_MODE = False
DATA_SOURCE = "OANDA_WITH_YAHOO_FALLBACK"
USE_OANDA_DATA = True
USE_YFINANCE_DATA = False
ENABLE_ML_CONFIRMATION = False
ML_MIN_CONFIDENCE = 0.50


# ==========================================
# 📊 PROFILE CONFIGURATION — ALL IN ONE PLACE
# ==========================================
PROFILE_CFG = {
    "profile2": {
        "LABEL": "PROFILE2",
        "ACCOUNT_NAME": "Account 002",
        "OANDA_ACCOUNT_ID": OANDA_ACCOUNT_ID_2,
        "COOLDOWN_FILE": "cooldown_profile2.json",
        "RESULTS_DIR": "daily_results_profile2",

        # Weights: S=35 R=20 A=15 X=20 M=10
        "WEIGHT_STRENGTH": 0.35,
        "WEIGHT_RSI": 0.20,
        "WEIGHT_ADX": 0.15,
        "WEIGHT_XGB": 0.20,
        "WEIGHT_MC": 0.10,

        "MIN_CONVICTION_SCORE": 30.0,
        "MAX_OPEN_POSITIONS": 5,
        "XGB_BULLISH_THRESHOLD": 0.52,
        "MC_BULLISH_THRESHOLD_PCT": 52.0,
        "MC_STRONG_THRESHOLD": 0.60,

        # Trend Filter — Profile2: OFF by default
        "TREND_FILTER_ENABLED": False,
        "WEEK_EMA100_FILTER_ENABLED": False,
        "EMA_PERIOD_FAST": 20,
        "EMA_PERIOD_SLOW": 60,

        # ATR / TP / SL
        "ATR_SL_MULT": 2.0,
        "ATR_TP_MULT": 2.5,
        "TP_MULT": 2.2,
        "TP_STRONG_MULT": 2.8,
        "USE_DYNAMIC_SL": 2,
        "DYNAMIC_SL_MULT": 1.3,
    },

    "profile3": {
        "LABEL": "PROFILE3",
        "ACCOUNT_NAME": "Account 003",
        "OANDA_ACCOUNT_ID": OANDA_ACCOUNT_ID_3,
        "COOLDOWN_FILE": "cooldown_profile3.json",
        "RESULTS_DIR": "daily_results_profile3",

        # Weights: S=40 R=15 A=15 X=20 M=10
        "WEIGHT_STRENGTH": 0.40,
        "WEIGHT_RSI": 0.15,
        "WEIGHT_ADX": 0.15,
        "WEIGHT_XGB": 0.20,
        "WEIGHT_MC": 0.10,

        "MIN_CONVICTION_SCORE": 20.0,
        "MAX_OPEN_POSITIONS": 4,
        "XGB_BULLISH_THRESHOLD": 0.55,
        "MC_BULLISH_THRESHOLD_PCT": 55.0,
        "MC_STRONG_THRESHOLD": 0.55,
        "REQUIRE_STRONG_MOMENTUM": False,

        # Trend Filter — Profile3: ON by default + Weekly EMA100
        "TREND_FILTER_ENABLED": True,
        "WEEK_EMA100_FILTER_ENABLED": True,
        "EMA_PERIOD_FAST": 40,
        "EMA_PERIOD_SLOW": 80,

        # ATR / TP / SL
        "ATR_SL_MULT": 2.5,
        "ATR_TP_MULT": 3.0,
        "TP_MULT": 2.5,
        "TP_STRONG_MULT": 3.0,
        "USE_DYNAMIC_SL": 3,
        "DYNAMIC_SL_MULT": 1.5,
    }
}