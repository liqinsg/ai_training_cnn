"""
Central configuration — edit this file to control all strategy behaviour.
Do not hardcode these values elsewhere in the codebase.
"""
import os
from dotenv import load_dotenv

load_dotenv()

DEBUG_EDGE_REASON = True 

# ==========================================
# OANDA CONNECTION
# ==========================================
OANDA_ENV = "practice"
OANDA_API_TOKEN = os.getenv("OANDA_API_TOKEN", "")
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID_1", "")
OANDA_TOKEN = OANDA_API_TOKEN

# ==========================================
# SCHEDULER
# ==========================================
CHECK_INTERVAL_MINUTES = 15

# ==========================================
# SIMPLE JPY TREND STRATEGY
# ==========================================
TRADE_PAIRS = ["USD_JPY", "EUR_JPY", "GBP_JPY", "AUD_JPY"]
SIGNAL_TIMEFRAMES = ["H4", "H1", "M30"]
REQUIRE_ALIGNED = len(SIGNAL_TIMEFRAMES)
TP_PIPS = 100
SL_BUFFER_PIPS = 20
SPREAD_PIPS = 3
SL_PIPS = SL_BUFFER_PIPS
MIN_RR = 1.2

# ==========================================
# RISK LEVEL 1–10
# ==========================================
RISK_LEVEL = 10
RISK_PROFILE = {
    1: {"units": 1000, "min_confidence": 0.90},
    2: {"units": 2000, "min_confidence": 0.85},
    3: {"units": 3000, "min_confidence": 0.80},
    4: {"units": 4000, "min_confidence": 0.75},
    5: {"units": 5000, "min_confidence": 0.70},
    6: {"units": 6000, "min_confidence": 0.65},
    7: {"units": 7000, "min_confidence": 0.60},
    8: {"units": 8000, "min_confidence": 0.55},
    9: {"units": 9000, "min_confidence": 0.50},
    10: {"units": 10000, "min_confidence": 0.40},
}

# ==========================================
# AI / GEMINI
# ==========================================
USE_GEMINI_AI = True
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_NEWS_MODEL = "gemini-3.5-flash"
GEMINI_NEWS_FALLBACK_MODEL = "gemini-flash-lite-latest"

# ==========================================
# ADVANCED STRATEGY / META
# ==========================================
META_MODE = "MANUAL"
MANUAL_STRATEGY = 1
STRATEGY_PULLBACK = 4
ADX_TREND_THRESHOLD = 25
ADX_BREAKOUT_THRESHOLD = 20
ATR_GRANULARITY = "D"
ATR_CANDLE_COUNT = 20
ATR_MULTIPLIER_SL = 0.75
ATR_MULTIPLIER_TP = 2.0
RANGE_LOOKBACK = 20
RANGE_TP_RATIO = 0.6
RANGE_SL_RATIO = 0.25
BREAKOUT_DURATION_HOURS = 4
BREAKOUT_WIDTH_PCT = 2.0
FORCE_TEST_PAIR = False
TEST_PAIR = None
EXPIRE_AFTER = 1440

# ==========================================
# CURRENCY STRENGTH / JPY TREND
# ==========================================
MIN_QUALIFYING_PAIRS = 1
INSTRUMENT = 'EUR_USD'
CURRENCIES = ["USD", "EUR", "GBP", "AUD", "NZD", "JPY", "CHF"]
STRENGTH_PAIRS = [
    "EUR_USD", "GBP_USD", "AUD_USD", "USD_JPY", "EUR_GBP",
    "EUR_JPY", "EUR_AUD", "GBP_JPY", "GBP_AUD", "AUD_JPY"
]
STRENGTH_TIMEFRAMES = {"H1": 1, "H4": 3, "H8": 6}
STRENGTH_FAST_LOOKBACK = 5
STRENGTH_SLOW_LOOKBACK = 20
STRENGTH_FAST_WEIGHT = 0.7
STRENGTH_SLOW_WEIGHT = 0.3
ENABLE_STRENGTH_ACCELERATION = False
STRENGTH_ACCELERATION_WEIGHT = 0.5
STRENGTH_ATR_PERIOD = 14
ENABLE_EMA_TREND = False
ENABLE_ATR_NORMALIZED_STRENGTH = False
ENABLE_BREAKOUT_CONFIRMATION = False
BREAKOUT_CONFIRMATION_CLOSES = 2
ENABLE_ATR_SLTP = True
ENABLE_NEWS_FILTER = False
NEWS_LOG_PATH = "news_events.log"
NEWS_CURRENCIES = ["USD", "JPY", "EUR", "GBP"]
MIN_DOMINANCE_RATIO = 1.5
ENABLE_VOLATILITY_NORMALIZED_DOMINANCE = False
DOMINANCE_ATR_PERIOD = 14
JPY_PIP = 0.01
MIN_MARKET_STRENGTH = 0.03
FRONT_RUN_PIPS = 15
JPY_ATR_PERIOD = 14
JPY_ATR_HISTORY_LOOKBACK = 50
JPY_ATR_SL_MULTIPLIER_NORMAL = 2.2
JPY_ATR_SL_MULTIPLIER_HIGH_VOL = 2.8
JPY_ATR_SL_MULTIPLIER_LOW_VOL = 1.8
JPY_ATR_RR_MULTIPLE = 2.0

# ==========================================
# DATA SOURCE
# ==========================================
DATA_SOURCE = "OANDA_WITH_YAHOO_FALLBACK"
USE_YFINANCE_DATA = False
USE_OANDA_DATA = True

# ==========================================
# ML LAYER
# ==========================================
ENABLE_ML_CONFIRMATION = False
ML_MIN_CONFIDENCE = 0.50
ML_MODEL_PATH = "ml_trade_model.pkl"
ENABLE_ML_WEIGHTED_DOMINANCE = False
ML_RETRAIN_HOURS = 24
ML_TRAIN_GRANULARITY = "H1"
ML_TRAIN_CANDLE_COUNT = 3000
ML_HOLDOUT_FRACTION = 0.2
ML_LABEL_HORIZON = 3
ML_MIN_HOLDOUT_F1 = 0.0
ML_TRAIN_PAIR = "USDJPY=X"
DEMO_MODE = False

# ==========================================
# RANGE / SIDEWAYS DETECTION
# ==========================================
ENABLE_RANGE_DETECTOR = False
RANGE_DETECT_LOOKBACK_DAYS = 3
RANGE_DETECT_MAX_RANGE_PCT = 2.0
RANGE_DETECT_MIN_VOL_RATIO = 0.6
SKIP_SIDEWAYS_PAIRS = False
MACRO_PROTECTION_PIPS = 10
MIN_VALID_PAIRS_TO_TRADE = 1
DEBUG_SLTP = True
TRADE_TOP_PAIRS = 1
MIN_STRENGTH_GAP = 1.2
SIDEWAYS_LOOKBACK_DAYS = 7
MIN_LONG_TREND_ANGLE = 15
BREAKOUT_LOOKBACK_DAYS = 30
MAX_SIDEWAYS_RANGE_PCT = 1.8
BREAKOUT_THRESHOLD_PCT = 0.3
ENABLE_MACRO_PROTECTION = False

# ==========================================
# FX TRADE BOT — BASE DEFAULTS
# ==========================================
TIMEFRAME = "15m"
MC_MAX_AGE_HOURS = 24
CLOSE_THRESHOLD = 55.0
REOPEN_DELAY_RUNS = 2
NORMAL_MIN_PROB = 51.0
DEFAULT_LOT_SIZE = 10000
USE_DEFAULT_LOT_SIZE = True
DEFAULT_PAIRS = [
    "EURUSD=X", "GBPUSD=X", "EURJPY=X", "GBPJPY=X",
    "AUDUSD=X", "USDJPY=X", "GBPAUD=X", "USDCHF=X"
]
YAHOO_TO_OANDA = {
    "EURUSD=X": "EUR_USD", "GBPUSD=X": "GBP_USD", "EURJPY=X": "EUR_JPY",
    "GBPJPY=X": "GBP_JPY", "AUDUSD=X": "AUD_USD", "USDJPY=X": "USD_JPY",
    "GBPAUD=X": "GBP_AUD", "USDCHF=X": "USD_CHF"
}
ENABLE_PIVOTS = True
PIVOT_METHOD = "Classic"
PIVOT_TIMEFRAME = "D"
PIVOT_BIAS_CHECK = True
DIRECTION = 'auto'
REGIME_FAST_EMA = 20
REGIME_SLOW_EMA = 30
RISK_MULTIPLE = 1.0
REWARD_MULTIPLE = 2.0
MAX_BARS = 20
ATR_PERIOD = 14
TRAIN_WINDOW = 3000
TEST_WINDOW = 500
STEP_SIZE = 500
THRESHOLD = 0.6
LOOKBACKS = [5, 10, 20, 50]
TEST_MODE = True
MOCK_SIGNAL = 'BUY'
MC_TP_MAX_BAND_PCT = 0.7

# ==========================================
# 🚀 ONE‑CLICK PRESET SWITCH — UNCOMMENT ONE
# ==========================================
# PRESET = "CONSERVATIVE"
# PRESET = "BALANCED"
PRESET = "LEVEL10"
NO_SIDE_WAYS_TRADE = True
MIN_REWARD_RISK = 1.2
MIN_CONVICTION_SCORE = 45

# ──────────────────────────────────────────
# AUTO‑APPLY PRESET (OVERRIDES BASE DEFAULTS)
# ──────────────────────────────────────────
if PRESET == "BALANCED":
    MODE = "NORMAL"
    MIN_PROB = 0.52
    NORMAL_MIN_PROB = 51.0
    RELAXED_MIN_PROB = 50.5
    STRENGTH_GAP_THRESHOLD = 10
    MC_TP_MAX_BAND_PCT = 0.7
    MAX_TOTAL_TRADES = 4 #2
    MAX_PER_USD_GROUP = 4 # 2
    MAX_PER_JPY_GROUP = 4 #2
    TREND_THRESHOLD = 25
    REOPEN_DELAY_RUNS = 2
elif PRESET == "CONSERVATIVE":
    MODE = "NORMAL"
    MIN_PROB = 0.55
    NORMAL_MIN_PROB = 53.0
    RELAXED_MIN_PROB = 51.0
    STRENGTH_GAP_THRESHOLD = 12
    MC_TP_MAX_BAND_PCT = 0.6
    MAX_TOTAL_TRADES = 1
    MAX_PER_USD_GROUP = 1
    MAX_PER_JPY_GROUP = 1
    TREND_THRESHOLD = 30
    REOPEN_DELAY_RUNS = 3
elif PRESET == "LEVEL9":
    MODE = "LEVEL9"
    MIN_PROB = 0.45
    NORMAL_MIN_PROB = 45.0
    RELAXED_MIN_PROB = 45.0
    # === TESTING: LOOPS ENTRY FILTERS ===
    STRENGTH_GAP_THRESHOLD = 1.0    # Was 7 → catch smaller gaps
    MIN_TREND_STRENGTH = 0.001       # Lower → detect mild moves
    ALLOW_TOP_N = 4                 # More candidates
    ALLOW_BOTTOM_N = 4
    # === KEEP RISK & TP LOGIC UNCHANGED ===
    MC_TP_MAX_BAND_PCT = 0.7
    MAX_TOTAL_TRADES = 4            # More pairs for testing
    MAX_PER_USD_GROUP = 3
    MAX_PER_JPY_GROUP = 3
    TREND_THRESHOLD = 20
    REOPEN_DELAY_RUNS = 2
    NO_SIDE_WAYS_TRADE = False
elif PRESET == "LEVEL10":
    MODE = "LEVEL10"
    MIN_PROB = 0.35
    NORMAL_MIN_PROB = 45.0
    RELAXED_MIN_PROB = 45.0
    STRENGTH_GAP_THRESHOLD = 1.0
    MIN_TREND_STRENGTH = 0.01
    NO_SIDE_WAYS_TRADE = False
    ALLOW_TOP_N = 5          # ✅ More candidates
    ALLOW_BOTTOM_N = 5       # ✅ More candidates
    # === RISK LIMITS — UP TO 5 TOTAL ===
    MAX_TOTAL_TRADES = 5     # ✅ Allow up to 5 open positions
    MAX_PER_USD_GROUP = 3    # ✅ Max 3 USD pairs
    MAX_PER_JPY_GROUP = 3    # ✅ Max 3 JPY pairs
    MC_TP_MAX_BAND_PCT = 0.7
    TREND_THRESHOLD = 20
    REOPEN_DELAY_RUNS = 2
    MIN_REWARD_RISK = 1.001
    MIN_CONVICTION_SCORE = 40
    STRENGTH_SIGNAL_BLOCK_THRESHOLD = 2.5



# ==========================================
# 📏 DYNAMIC TP & MARKET REGIME SETTINGS
# ==========================================
VOL_LOW_THRESHOLD = 4.0        # % — below = sideways/low vol
VOL_HIGH_THRESHOLD = 7.0       # % — above = strong trend
RANGE_LOW_PCT = 0.20           # Price position in MC range = sideways
RANGE_HIGH_PCT = 0.50          # Price position = trending
TP_MULT_SIDEWAYS = 1.5         # Quick take-profit
TP_MULT_NORMAL = 2.0           # Standard trend
TP_MULT_STRONG = 2.5           # Let profits run
MIN_TREND_STRENGTH = 0.05      # % price change required to confirm trend

# ==========================================
# RE-ENTRY CONTROL — PREVENT OVERTRADING
# ==========================================
# After TP: wait for price to pull back before re-entering same direction
REENTRY_COOLDOWN_MINUTES = 0.001 #60     # Also wait 60min minimum after TP/SL
REENTRY_MIN_PULLBACK_PIPS = 8.0   # Wait 8+ pips retracement before re-entry
REENTRY_STRENGTH_CONFIRM = True  # Require currency strength still aligned
# Only enter when price is near MC range boundary
ENTRY_PERCENTILE_LOW = 15    # LONG only if price in bottom 15% of range
ENTRY_PERCENTILE_HIGH = 85   # SHORT only if price in top 15% of range

# DEBUG_API = False
DEBUG_MODE = False
MIN_SL_PIPS = 35
MIN_SL_PIPS_JPY = MIN_SL_PIPS + 10  # 15 for JPY pairs
TRAILING_TP = False
COOLDOWN_RUNS = 0
REMOVE_COOLDOWN = True

TRAILING_TP = False          # OANDA server-side trailing TP
DYNAMIC_TP = True            # ✅ Bot actively RAISES TP as price trends
TP_RAISE_THRESHOLD_PIPS = 15 # Only raise TP when ≥15 pips higher (prevents noise)

# Max number of open positions allowed AT ANY TIME
MAX_SIMULTANEOUS_TRADES = 5   # ← Change this! e.g. 1, 2, 3, 5...

SKIP_MC = True
