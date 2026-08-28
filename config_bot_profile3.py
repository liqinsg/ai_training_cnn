# config_bot_profile3.py — v6.8.6 | Profile 3 (Account 003)
# Weights: S=40 R=15 A=15 X=20 M=10 | RSI-FIXED | Conservative
from config_bot import *


# ─── Account Identity ───
from config_oanda import OANDA_ACCOUNT_ID_3 as OANDA_ACCOUNT_ID


# ─── Feature & ATR Settings ───
USE_ATR = True
ATR_SL_MULT = 2.5
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
MIN_CONVICTION_SCORE = 20.0          # ✅ Lowered — passes AUDUSD=22.9
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
MC_BULLISH_THRESHOLD_PCT = 55.0      # ✅ Matched live AUDUSD=59.9%


# ─── RSI-FIXED Toggle ───
RSI_DIRECTION_AWARE = True            # ✅ RSI only scores if direction agrees


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
MC_STRONG_THRESHOLD = 0.55           # ✅ 55% instead of strict 75%
REQUIRE_STRONG_MOMENTUM = False       # ✅ Allow normal MC trades


# ─── Trend Filter (Profile3 = Conservative) ───
TREND_FILTER_ENABLED = True           # ✅ EMA40/80 crossover ON
WEEK_EMA100_FILTER_ENABLED = True    # ✅ Weekly EMA100 safety ON
PRICE_ON_CORRECT_SIDE = True
EMA_MIN_SLOPE = 0.0001                # ✅ Fixed typo: SLOP → SLOPE
EMA_PERIOD = 40
EMA_PERIOD_FAST = 40                  # ✅ 15m = H1 EMA10 equivalent
EMA_PERIOD_SLOW = 80                  # ✅ 15m = H1 EMA20 equivalent


# ─── Unified TP (v6.8.4+) ───
BASE_TP_PIPS = 50                     # ✅ Custom base
TP_MULT = 2.5                         # ✅ Normal TP multiplier
TP_STRONG_MULT = 3.0                  # ✅ Strong momentum TP multiplier


# ─── Dynamic SL ───
USE_DYNAMIC_SL: int = 3
DYNAMIC_SL_MULT: float = 1.5


# ─── CONSENSUS ← THE KEY FROM SUCCESSFUL RUN ───
CONSENSUS_THRESHOLD = 2               # ✅ 2/3 votes = PASS (DO NOT LOWER!)
CONSENSUS_REQUIRED_VOTES = 2          # ✅ Match above
REQUIRE_DIRECTION_CONSENSUS = True    # ✅ Direction must align
MIN_STRENGTH_GAP = 0.10               # ✅ Permissive but sane


if __name__ == "__main__":
    from config_oanda import OANDA_ACCOUNT_ID_3 as OANDA_ACCOUNT_ID
    print(OANDA_ACCOUNT_ID)
    from utils.oanda_execution import check_oanda_account
    try:
        check_oanda_account(account_id=OANDA_ACCOUNT_ID)
    except Exception as e:
        print('❌ FORBIDDEN / MISMATCH:', e)