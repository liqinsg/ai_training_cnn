# config_bot_profile1.py — v6.8.2 | Profile 1 (Account 001)
# Weights: S=40 R=15 A=15 X=20 M=10 | RSI-FIXED | A/C ending 001

# ─── Account Identity ───
from config_oanda import OANDA_ACCOUNT_ID_2 as OANDA_ACCOUNT_ID

# ─── Feature & ATR Settings ───
USE_ATR = True
ATR_SL_MULT = 2.0
ATR_TP_MULT = 3.0
ATR_PERIOD = 14

USE_MACD = True
USE_RSI = True
USE_ADX = True

# ─── ML Model Settings ───
MODEL_TYPE = "xgboost"
TARGET_HORIZON = 6
TRAIN_LOOKBACK_BARS = 5000

# ─── Weighted Scoring (BALANCED Profile) ───
WEIGHT_STRENGTH = 0.40
WEIGHT_RSI = 0.15
WEIGHT_ADX = 0.15
WEIGHT_XGB = 0.20
WEIGHT_MC = 0.10

# ─── Strategy Conviction Thresholds ───
MODE = "LEVEL10"
MIN_CONVICTION_SCORE = 30.0
BASE_MIN_EDGE = 0.50
MIN_SCORE_GAP = 0.25

# ─── Auto-Ranking ───
USE_TOP_PAIRS_ONLY = False
TOP_PAIRS_COUNT = 4
TOP_PAIRS_MIN_GAP = 0.25

# ─── Execution Limits ───
MAX_OPEN_POSITIONS = 4
DEFAULT_LOT_SIZE = 10000

# ─── XGB / MC Thresholds ───
XGB_BULLISH_THRESHOLD = 0.55
MC_BULLISH_THRESHOLD_PCT = 55.0

# ─── RSI-FIXED Toggle ───
RSI_DIRECTION_AWARE = True  # ✅ RSI only scores if it AGREES with trade direction

# ─── Data Intervals ───
YF_INTERVAL = "4h"
YF_PERIOD_FULL = "30d"
YF_PERIOD_RESAMPLE = "60d"
YF_INTERVAL_D = "1d"
PERIODS_YEAR = 252

# ─── Monte Carlo ───
MC_REPORT_TITLE = "FX H4 MONTE CARLO"
MC_BAND_PCT = 90
MC_SIGNIFICANT_PCT = 60
MC_MOMENTUM_BAND = 0.001

if __name__ == "__main__":
    from utils.oanda_execution import check_oanda_account
    try:
        check_oanda_account(account_id=OANDA_ACCOUNT_ID)
    except Exception as e:
        print('❌ FORBIDDEN / MISMATCH:', e)
