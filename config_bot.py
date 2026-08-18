# config_bot.py — v6.8 | Centralized Strategy & Bot Configuration
# Credentials stay in config_oanda.py; legacy fallbacks in config.py


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


# ─── Strategy Conviction Thresholds ───
MODE = "LEVEL10"
MIN_CONVICTION_SCORE = 35
BASE_MIN_EDGE = 0.50
MIN_CONVICTION_SCORE_ALT = 45.0
BASE_MIN_EDGE_ALT = 0.51


# ─── Data & Timeframe Intervals ───
YF_INTERVAL = "4h"
YF_PERIOD_FULL = "30d"
YF_PERIOD_RESAMPLE = "60d"
PERIODS_YEAR = 252

YF_INTERVAL_D = "1d"
YF_PERIOD_FULL_D = "120d"
YF_PERIOD_RESAMPLE_D = "180d"
PERIODS_YEAR_D = 252


# ─── Monte Carlo Settings ───
MC_REPORT_TITLE = "FX H4 MONTE CARLO"
MC_REPORT_TITLE_D = "FX DAILY MONTE CARLO"
MC_MAX_AGE_HOURS = 24
MC_SIMULATIONS = 5000
MC_CONFIDENCE = 0.90
SKIP_MC = False

H4_LOOKBACK = 90
H4_FORECAST = 8
DAILY_LOOKBACK = 90
DAILY_FORECAST = 5


# ─── Risk & Trade Execution ───
DEFAULT_LOT_SIZE = 10000
MAX_SIMULTANEOUS_TRADES = 4
DEFAULT_PAIRS = [
    "EURUSD=X", "GBPUSD=X", "EURJPY=X", "GBPJPY=X",
    "AUDUSD=X", "USDJPY=X", "GBPAUD=X", "USDCHF=X",
    "AUDJPY=X", "EURGBP=X", "CADJPY=X", "NZDUSD=X"
]
YAHOO_TO_OANDA = {
    "EURUSD=X": "EUR_USD", "GBPUSD=X": "GBP_USD", "EURJPY=X": "EUR_JPY",
    "GBPJPY=X": "GBP_JPY", "AUDUSD=X": "AUD_USD", "USDJPY=X": "USD_JPY",
    "GBPAUD=X": "GBP_AUD", "USDCHF=X": "USD_CHF", "NZDUSD=X": "NZD_USD",
    "AUDJPY=X": "AUD_JPY", "EURGBP=X": "EUR_GBP", "CADJPY=X": "CAD_JPY",
}

MIN_SL_PIPS = 25
MIN_SL_PIPS_JPY = MIN_SL_PIPS + 10


# ─── Dynamic TP / Trailing ───
DYNAMIC_TP = False
TRAILING_TP = True
TP_RAISE_THRESHOLD_PIPS = 15
BE_TRIGGER_ATR_MULT = 1.5
TRAIL_TRIGGER_ATR_MULT = 2.5
TRAIL_ATR_MULT = 1.5
MAX_HOLD_BARS = 12


# ─── Multi-Timeframe Confluence ───
MULTI_TF_CONFLUENCE = False
CONFLUENCE_REQUIRED_TFS = 2


# ─── Currency Strength Filter ───
STRENGTH_SIGNAL_BLOCK_THRESHOLD = 9.99  # Disabled


# ─── Cooldown & Debug ───
REMOVE_COOLDOWN = True
DEBUG_MODE = False


# ─── Auto-Ranking Feature ───
USE_TOP_PAIRS_ONLY = False
TOP_PAIRS_COUNT = 5
TOP_PAIRS_MIN_GAP = 1.5
MIN_STRENGTH_GAP = 0.8


# ─────────────────────────────────────────────
# ✅ v6.8 ACTIVE SETTINGS — Last values WINS!
# ─────────────────────────────────────────────

# P0: DIRECTION CONSENSUS
REQUIRE_DIRECTION_CONSENSUS = True    # ✅ ENABLED
CONSENSUS_THRESHOLD = 2               # Need ≥2 of 3
XGB_BULLISH_THRESHOLD = 0.55          # XGB bullish threshold
MC_BULLISH_THRESHOLD = 55.0           # MC bullish threshold

# P1: ADX NORMALIZATION
ADX_SCALE_FACTOR = 2.0                # ✅ ADX × 2
ADX_FLOOR_ENABLED = True
ADX_MIN_SCORE = 20.0
ADX_BOOST_ENABLED = True
ADX_BOOST_THRESHOLD = 30.0
ADX_BOOST_VALUE = 10.0

# P2: WEIGHTS — S=0.50 R=0.15 A=0.15 X=0.12 M=0.08
WEIGHT_STRENGTH = 0.50
WEIGHT_RSI      = 0.15
WEIGHT_ADX      = 0.15
WEIGHT_XGBOOST  = 0.12
WEIGHT_MC       = 0.08                 # ✅ ↑ from 0.05

THRESHOLD_SCORE = 35.0
MAX_OPEN = 8 # 1-3


# ─────────────────────────────────────────────
# ✅ DATA SOURCE — YAHOO FINANCE PRIMARY
# ─────────────────────────────────────────────
PREFER_YAHOO_DATA = True          # Use Yahoo FIRST; OANDA = fallback only
YF_INTERVAL = "15m"              # Match bot timeframe exactly
YF_PERIOD_FULL = "30d"
YF_PERIOD_RESAMPLE = "60d"

# ─────────────────────────────────────────────
# MC REGIME FILTER (Live Phase)
# ─────────────────────────────────────────────
REQUIRE_STRONG_MOMENTUM = False     # ✅ Phase1=False → open all qualified
                                    # ✅ Phase2=True  → ⚡ ONLY strong momentum

# ─────────────────────────────────────────────
# ⚖️ PORTFOLIO BALANCE — LONG/SHORT CONTROL
# ─────────────────────────────────────────────
ENFORCE_LONGS_SHORTS = True    # Toggle ON/OFF with one line
MIN_PER_SIDE = 1               # Minimum 1 LONG + 1 SHORT
MAX_RATIO = 0.75               # Max 75% one side → at least 25% opposite
PREFER_BALANCED = True          # Auto-balance even if lower-scoring needed

# ─────────────────────────────────────────────
# ✅ v6.8 CONFIG VALIDATION — Runs on Import
# ─────────────────────────────────────────────
import sys

CONFIG_VALIDATION_ENABLED = True   # Set False to skip checks
CONFIG_TOLERANCE = 0.005          # Allow ±0.5% rounding error

def validate_config():
    if not CONFIG_VALIDATION_ENABLED:
        print("⚠️  Config validation — DISABLED")
        return True

    errors = []
    warns = []

    # ── Check Weight Sum ──
    weights = {
        "S": WEIGHT_STRENGTH,
        "R": WEIGHT_RSI,
        "A": WEIGHT_ADX,
        "X": WEIGHT_XGBOOST,
        "M": WEIGHT_MC,
    }
    weight_sum = sum(weights.values())

    print("\n🔍 CONFIG VALIDATION — v6.8")
    print("─────────────────────────────────────")
    for k, v in weights.items():
        print(f"   Weight {k}: {v:.4f}")
    print(f"   ── SUM: {weight_sum:.4f}  (target: 1.0000)")

    if abs(weight_sum - 1.0) > CONFIG_TOLERANCE:
        errors.append(f"Weight sum = {weight_sum:.4f}, expected 1.0000 ± {CONFIG_TOLERANCE}")
    elif abs(weight_sum - 1.0) > 0.0001:
        warns.append(f"Weights sum = {weight_sum:.4f} (minor rounding)")

    # ── Check Individual Weight Ranges ──
    for name, w in weights.items():
        if not (0.0 <= w <= 1.0):
            errors.append(f"Weight {name} = {w:.4f} — out of range [0.0, 1.0]")

    # ── Check ADX Settings ──
    if ADX_SCALE_FACTOR < 0.5 or ADX_SCALE_FACTOR > 5.0:
        warns.append(f"ADX_SCALE_FACTOR = {ADX_SCALE_FACTOR} — unusual value")
    if ADX_FLOOR_ENABLED and not (0 <= ADX_MIN_SCORE <= 50):
        warns.append(f"ADX_MIN_SCORE = {ADX_MIN_SCORE} — unusual floor")

    # ── Check Consensus Settings ──
    if REQUIRE_DIRECTION_CONSENSUS:
        if not (1 <= CONSENSUS_THRESHOLD <= 3):
            errors.append(f"CONSENSUS_THRESHOLD = {CONSENSUS_THRESHOLD} — must be 1–3")
        if not (0.4 <= XGB_BULLISH_THRESHOLD <= 0.9):
            warns.append(f"XGB_BULLISH_THRESHOLD = {XGB_BULLISH_THRESHOLD:.2f} — unusual")
        if not (40 <= MC_BULLISH_THRESHOLD <= 65):
            warns.append(f"MC_BULLISH_THRESHOLD = {MC_BULLISH_THRESHOLD:.1f} — unusual")

    # ── Check Gap & Threshold ──
    if MIN_STRENGTH_GAP < 0 or MIN_STRENGTH_GAP > 5:
        warns.append(f"MIN_STRENGTH_GAP = {MIN_STRENGTH_GAP} — unusual")
    if THRESHOLD_SCORE < 0 or THRESHOLD_SCORE > 100:
        errors.append(f"THRESHOLD_SCORE = {THRESHOLD_SCORE} — must be 0–100")

    # ── Report ──
    print("─────────────────────────────────────")
    if warns:
        for w in warns:
            print(f"⚠️  WARN: {w}")
    if errors:
        for e in errors:
            print(f"❌ ERROR: {e}")
        print(f"\n❌ {len(errors)} CONFIG ERROR(S) — Please fix before running!")
        print("─────────────────────────────────────\n")
        return False
    print("✅ ALL CHECKS PASSED — Config OK\n")
    return True

# Run validation immediately on import
if 'CONFIG_VALIDATION_ENABLED' in globals() and CONFIG_VALIDATION_ENABLED:
    if not validate_config():
        sys.exit(1)  # Halt on error — set to 'pass' to ignore and continue