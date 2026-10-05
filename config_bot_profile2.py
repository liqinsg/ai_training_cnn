# ═══════════════════════════════════════════════════════════════════════════════
# Profile 2 (Account 002) — UNIVERSE BUCKET / EXECUTION UNIT
#   ROLE:       Asia / JPY Theme — executes signals on JPY-cross universe only
#   STRATEGY:   IDENTICAL to Profile3 (same weights, same TP, same filters).
#               Strategy parameters are intentionally kept in sync with P3 so
#               performance divergence can be cleanly attributed to universe.
#   OANDA:      -002 account, separated cooldown/results from P3.
# ═══════════════════════════════════════════════════════════════════════════════
# config_bot_profile1.py — v6.8.3.4 | Profile 2 (Account 002)
# Weights: S=40 R=15 A=15 X=20 M=10 | RSI-FIXED | Universe = JPY Bucket (4 pairs)
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
# Universe Bucket Definition (P2 = Pure JPY Cross Theme, 4 pairs):
#   P2 owns: AUDJPY, EURJPY, GBPJPY, USDJPY     (all include JPY quote)
#   P3 owns: AUDUSD, EURUSD, GBPUSD, USDCHF     (no JPY — EUR/GBP/CHF/AUD theme)
#
# RULES (hard invariant, verified by startup safety lock):
#   union(P2, P3)  = ALL_PAIRS (8 total, full coverage)
#   intersection() = empty set (no pair is double-booked across accounts)
ALLOWED_PAIRS = [
    "AUDJPY=X",
    "EURJPY=X",
    "GBPJPY=X",
    "USDJPY=X",
]

# ─── Per-Pair SL Floor Override (Gemini P0 advice)
# GBPJPY daily ATR ≈ 120-150 pips vs typical AUDUSD 50-70 pips. The universal
# SL_MIN_DISTANCE_PIPS = 20 (zone floor) + SL_FALLBACK_FIXED_PIPS = 35 are too
# tight for GBPJPY's natural volatility and would trigger early "unexpected"
# stop-outs on routine intra-day swings. Set a per-pair floor MIN_DIST = 50.
SL_PAIR_FLOOR_OVERRIDES = {
    "GBPJPY=X": 50,
}

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

# ─── H1-TIMEFRAME DIRECTION GATE (Phase 0 — SHADOW MODE BY DEFAULT)
# Locks each pair into LONG / SHORT / BOTH based on H1-EMA20 × H1-EMA50 cross.
# Solves "几小时前卖现在又买" flip-flop problem: H1 cross locks direction.
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
D_GATE_CONFIRM_BARS = 2       # A2: how many consecutive H1-closes must confirm cross
D_GATE_MIN_BUFFER_PCT = 0.002 # A2: 0.2% minimum EMA gap magnitude on flip (anti-whipsaw)

if __name__ == "__main__":
    from utils.oanda_execution import check_oanda_account
    try:
        check_oanda_account(account_id=OANDA_ACCOUNT_ID)
    except Exception as e:
        print('❌ FORBIDDEN / MISMATCH:', e)