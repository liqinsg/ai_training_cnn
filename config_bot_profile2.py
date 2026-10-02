# config_bot_profile1.py — v6.8.2 | Profile 1 (Account 001)
# Weights: S=40 R=15 A=15 X=20 M=10 | RSI-FIXED | A/C ending 001
from config_bot import *

# ─── Account Identity ───
from config_oanda import OANDA_ACCOUNT_ID_2 as oanda_account_id
OANDA_ACCOUNT_ID = oanda_account_id
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
MIN_CONVICTION_SCORE = 45.0    # 🔒 CONSERVATIVE: ↑ from 30 — drop borderline signals
BASE_MIN_EDGE = 0.50
MIN_SCORE_GAP = 0.50           # 🔒 CONSERVATIVE: ↑ from 0.25 — avoid range-bound whipsaw

# ─── Auto-Ranking ───
# Read by fx_trade_bot_v683.py (profile module wins over config_bot).
# Setting this False would silently revert to a full scan of 8 pairs.
USE_TOP_PAIRS_ONLY = True
# Single source of truth for N in v683; the profile module is consulted first.
TOP_N_CURRENCIES = 3
# Legacy key for the retired v6.8.x bots. fx_trade_bot_v683.py does NOT read it
# (it would resolve to 4 and contradict TOP_N_CURRENCIES = 3).
TOP_PAIRS_COUNT = 4
TOP_PAIRS_MIN_GAP = 0.50       # 🔒 CONSERVATIVE: ↑ from 0.25 — no open on weak divergence

# ─── Execution Limits ───
MAX_OPEN_POSITIONS = 3         # 🔒 CONSERVATIVE: ↓ from 4 — avoid correlated exposure
DEFAULT_LOT_SIZE = 10000

# ─── Risk & Dynamic SL Behaviour (DynamicPositionManager) ───
# Anti-whipsaw: widen trailing distance, extend hold horizon (per user profile:
# "宁愿被 SL 扫也不要频频被自己扫出局")
TRAIL_ATR_MULT = 2.0           # 🔒 CONSERVATIVE: ↑ from 1.5 — wider SL trail on trend
MAX_HOLD_BARS = 48             # 🔒 CONSERVATIVE: ↑ from 12 (3h → 12h on 15m) — no early exits

# ─── XGB / MC Thresholds ───
XGB_BULLISH_THRESHOLD = 0.55
MC_BULLISH_THRESHOLD_PCT = 55.0

# ─── Pair Whitelist (Ownership Tag, disjoint from Profile3)
# A2: AUD + JPY group (亚系高波动组)
# Profile2 独占：AUDUSD, AUDJPY, EURJPY, GBPJPY, USDJPY
# Profile3 独占：EURUSD, GBPUSD, USDCHF  — 互斥，绝不重叠
ALLOWED_PAIRS = [
    "AUDUSD=X",
    "AUDJPY=X",
    "EURJPY=X",
    "GBPJPY=X",
    "USDJPY=X",
]

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

TREND_FILTER_ENABLED = False   # Set False → skip EMA10 slope + EMA100 checks entirely
# NOTE: with TREND_FILTER_ENABLED=False above, evaluate_trend_and_tp() skips both
# trend blocks, so the Weekly EMA100 check is already unreachable here. Set
# explicitly to False so re-enabling the EMA10 filter cannot silently revive it.
WEEK_EMA100_FILTER_ENABLED = False   # Set False → skip Weekly EMA100 counter-trend check

# ─── D-TIMEFRAME DIRECTION GATE (Phase 0 — SHADOW MODE BY DEFAULT)
# Locks each pair into LONG / SHORT / BOTH based on D-EMA20 × D-EMA50 cross.
# Solves "几小时前卖现在又买" flip-flop problem: daily cross locks direction.
#
# PHASE RULE (per user's "记录≠执行" workflow):
#   SHADOW=True   → Emit diagnostic lines (would_block=yes/no) but do NOT BLOCK
#                   any trades. Collect >= 20 rows with would_block=True plus
#                   their actual outcomes before advancing to enforced.
#   ENABLED=True + SHADOW=False → Real blocking. Anti-flip enforcement active.
D_GATE_ENABLED = True
D_GATE_SHADOW = True          # 🔒 Phase 0 default: observe only, NO blocking
D_GATE_EMA_FAST = 20          # A1: fast EMA
D_GATE_EMA_SLOW = 50          # A1: slow EMA
D_GATE_CONFIRM_BARS = 2       # A2: how many consecutive D-closes must confirm cross
D_GATE_MIN_BUFFER_PCT = 0.002 # A2: 0.2% minimum EMA gap magnitude on flip (anti-whipsaw)

if __name__ == "__main__":
    from utils.oanda_execution import check_oanda_account
    try:
        check_oanda_account(account_id=OANDA_ACCOUNT_ID)
    except Exception as e:
        print('❌ FORBIDDEN / MISMATCH:', e)
