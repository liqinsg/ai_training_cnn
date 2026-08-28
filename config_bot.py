# config_bot.py — v6.8 | Centralized Strategy & Bot Configuration + FULL VALIDATION
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
# MIN_CONVICTION_SCORE = 35
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
    "CADJPY=X",
    "NZDUSD=X",
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
    "NZDUSD=X": "NZD_USD",
    "AUDJPY=X": "AUD_JPY",
    "EURGBP=X": "EUR_GBP",
    "CADJPY=X": "CAD_JPY",
}


MIN_SL_PIPS = 25
MIN_SL_PIPS_JPY = MIN_SL_PIPS + 10
MIN_HOLD_BARS = 4

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

USE_DYNAMIC_SL = 2
# ─── Cooldown & Debug ───
REMOVE_COOLDOWN = True
DEBUG_MODE = False

# ─── Auto-Ranking Feature ───
USE_TOP_PAIRS_ONLY = False
TOP_PAIRS_COUNT = 5
TOP_PAIRS_MIN_GAP = 1.5
MIN_STRENGTH_GAP = 0.25  # ↓ from 0.35
MIN_CONVICTION_SCORE = 30  # ↓ from 35

# ─────────────────────────────────────────────
# ✅ v6.8 ACTIVE SETTINGS — Last values WINS!
# ─────────────────────────────────────────────

# P0: DIRECTION CONSENSUS
REQUIRE_DIRECTION_CONSENSUS = True  # ✅ ENABLED
CONSENSUS_THRESHOLD = 2  # Need ≥2 of 3
XGB_BULLISH_THRESHOLD = 0.55  # XGB bullish threshold
MC_BULLISH_THRESHOLD = 55.0  # MC bullish threshold

# P1: ADX NORMALIZATION
ADX_SCALE_FACTOR = 2.0  # ✅ ADX × 2
ADX_FLOOR_ENABLED = True
ADX_MIN_SCORE = 20.0
ADX_BOOST_ENABLED = True
ADX_BOOST_THRESHOLD = 30.0
ADX_BOOST_VALUE = 10.0

# P2: WEIGHTS — S=0.50 R=0.15 A=0.15 X=0.12 M=0.08
WEIGHT_STRENGTH = 0.50
WEIGHT_RSI = 0.15
WEIGHT_ADX = 0.15
WEIGHT_XGBOOST = 0.12
WEIGHT_MC = 0.08  # ✅ ↑ from 0.05

#THRESHOLD_SCORE = 35.0
THRESHOLD_SCORE = 25.0
MAX_OPEN = 4  # Aligned with MAX_SIMULTANEOUS_TRADES

# ─────────────────────────────────────────────
# ✅ DATA SOURCE — YAHOO FINANCE PRIMARY
# ─────────────────────────────────────────────
PREFER_YAHOO_DATA = True  # Use Yahoo FIRST; OANDA = fallback only
YF_INTERVAL = "15m"  # Match bot timeframe exactly
YF_PERIOD_FULL = "30d"
YF_PERIOD_RESAMPLE = "60d"

# ─────────────────────────────────────────────
# MC REGIME FILTER (Live Phase)
# ─────────────────────────────────────────────
# ✅ Phase1=False → open all qualified
# ✅ Phase2=True  → ⚡ ONLY strong momentum
REQUIRE_STRONG_MOMENTUM = False

# ─────────────────────────────────────────────
# ⚖️ PORTFOLIO BALANCE — LONG/SHORT CONTROL
# ─────────────────────────────────────────────
ENFORCE_LONGS_SHORTS = True  # Toggle ON/OFF with one line
MIN_PER_SIDE = 1  # Minimum 1 LONG + 1 SHORT
MAX_RATIO = 0.75  # Max 75% one side → at least 25% opposite
PREFER_BALANCED = True  # Auto-balance even if lower-scoring needed

# ─── HIERARCHICAL SL SETTINGS ───
SL_USE_ZONE_HIERARCHY = True  # ✅ Toggle ON/OFF
SL_BUFFER_PIPS = 25  # ✅ ±25p from zone
SL_MIN_DISTANCE_PIPS = 20  # ✅ Minimum 20p SL distance
SL_H4_LOOKBACK_BARS = 6  # ✅ H4 lookback bars
SL_H8_LOOKBACK_BARS = 4  # ✅ H8 fallback lookback
SL_DAILY_LOOKBACK_BARS = 2  # ✅ Daily fallback lookback
SL_FALLBACK_FIXED_PIPS = 35  # ✅ Final fallback fixed pips

# ─────────────────────────────────────────────
# ✅ v6.8 CONFIG VALIDATION — Runs on Import
# ─────────────────────────────────────────────
import sys

CONFIG_VALIDATION_ENABLED = True  # Set False to skip checks
CONFIG_TOLERANCE = 0.005  # Allow ±0.5% rounding error

# ─── Trend & TP Shared Defaults ───
BASE_TP_PIPS = 30
TP_MULT = 1.0
TP_STRONG_MULT = 2.0   # Profile2 default: strong MC → ×2 TP
TREND_FILTER_ENABLED = False   # ✅ PROFILE2: NO EMA CROSS FILTER
MC_STRONG_THRESHOLD = 0.75
WEEKLY_EMA_PERIOD = 100
EMA100_BUFFER_PIPS = 30
EMA_PERIOD = 10
SLOPE_LOOKBACK = 5
MIN_SLOPE = 0.001

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
        errors.append(
            f"Weight sum = {weight_sum:.4f}, expected 1.0000 ± {CONFIG_TOLERANCE}"
        )
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
    if ADX_BOOST_ENABLED and not (ADX_BOOST_THRESHOLD > 0 and ADX_BOOST_VALUE > 0):
        warns.append(f"ADX_BOOST misconfigured — threshold/value should be positive")

    # ── Check Consensus Settings ──
    if REQUIRE_DIRECTION_CONSENSUS:
        if not (1 <= CONSENSUS_THRESHOLD <= 3):
            errors.append(f"CONSENSUS_THRESHOLD = {CONSENSUS_THRESHOLD} — must be 1–3")
        if not (0.4 <= XGB_BULLISH_THRESHOLD <= 0.9):
            warns.append(
                f"XGB_BULLISH_THRESHOLD = {XGB_BULLISH_THRESHOLD:.2f} — unusual (suggest 0.5–0.6)"
            )
        if not (40 <= MC_BULLISH_THRESHOLD <= 65):
            warns.append(
                f"MC_BULLISH_THRESHOLD = {MC_BULLISH_THRESHOLD:.1f} — unusual (suggest 50–60)"
            )

    # ── Check Gap & Threshold ──
    if MIN_STRENGTH_GAP < 0 or MIN_STRENGTH_GAP > 5:
        warns.append(
            f"MIN_STRENGTH_GAP = {MIN_STRENGTH_GAP} — unusual (suggest 0.5–1.5)"
        )
    if THRESHOLD_SCORE < 0 or THRESHOLD_SCORE > 100:
        errors.append(f"THRESHOLD_SCORE = {THRESHOLD_SCORE} — must be 0–100")
    if MIN_CONVICTION_SCORE < 0 or MIN_CONVICTION_SCORE > 100:
        errors.append(f"MIN_CONVICTION_SCORE = {MIN_CONVICTION_SCORE} — must be 0–100")

    # ── Check ATR Settings ──
    if ATR_SL_MULT < 0.5 or ATR_SL_MULT > 5.0:
        warns.append(f"ATR_SL_MULT = {ATR_SL_MULT} — unusual (suggest 1.5–3.0)")
    if ATR_TP_MULT < 0.5 or ATR_TP_MULT > 8.0:
        warns.append(f"ATR_TP_MULT = {ATR_TP_MULT} — unusual (suggest 2.0–4.0)")
    if not (5 <= ATR_PERIOD <= 30):
        warns.append(f"ATR_PERIOD = {ATR_PERIOD} — unusual (suggest 10–14)")

    # ── Check HIERARCHICAL SL Settings ──
    if SL_USE_ZONE_HIERARCHY:
        if not (5 <= SL_BUFFER_PIPS <= 50):
            warns.append(f"SL_BUFFER_PIPS = {SL_BUFFER_PIPS} — unusual (suggest 15–30)")
        if not (5 <= SL_MIN_DISTANCE_PIPS <= 50):
            warns.append(
                f"SL_MIN_DISTANCE_PIPS = {SL_MIN_DISTANCE_PIPS} — unusual (suggest 15–30)"
            )
        if (
            SL_H4_LOOKBACK_BARS < 1
            or SL_H8_LOOKBACK_BARS < 1
            or SL_DAILY_LOOKBACK_BARS < 1
        ):
            errors.append("SL lookback bars must be ≥1")
        if SL_FALLBACK_FIXED_PIPS < 10 or SL_FALLBACK_FIXED_PIPS > 100:
            warns.append(
                f"SL_FALLBACK_FIXED_PIPS = {SL_FALLBACK_FIXED_PIPS} — unusual (suggest 25–50)"
            )

    # ── Check MC Settings ──
    if not (1000 <= MC_SIMULATIONS <= 20000):
        warns.append(
            f"MC_SIMULATIONS = {MC_SIMULATIONS} — unusual (suggest 2000–10000)"
        )
    if not (0.80 <= MC_CONFIDENCE <= 0.99):
        warns.append(
            f"MC_CONFIDENCE = {MC_CONFIDENCE:.2f} — unusual (suggest 0.85–0.95)"
        )
    if MC_MAX_AGE_HOURS < 1 or MC_MAX_AGE_HOURS > 168:
        warns.append(f"MC_MAX_AGE_HOURS = {MC_MAX_AGE_HOURS} — unusual (suggest 12–48)")

    # ── Check Risk & Trade Settings ──
    if MAX_SIMULTANEOUS_TRADES < 1 or MAX_SIMULTANEOUS_TRADES > 20:
        warns.append(
            f"MAX_SIMULTANEOUS_TRADES = {MAX_SIMULTANEOUS_TRADES} — unusual (suggest 1–8)"
        )
    if MAX_OPEN < 1 or MAX_OPEN > 20:
        warns.append(f"MAX_OPEN = {MAX_OPEN} — unusual (suggest 1–8)")
    if MAX_SIMULTANEOUS_TRADES != MAX_OPEN:
        warns.append(
            f"MAX_SIMULTANEOUS_TRADES={MAX_SIMULTANEOUS_TRADES} ≠ MAX_OPEN={MAX_OPEN} — consider aligning"
        )
    if DEFAULT_LOT_SIZE < 100 or DEFAULT_LOT_SIZE > 100000:
        warns.append(f"DEFAULT_LOT_SIZE = {DEFAULT_LOT_SIZE} — verify lot size")

    # ── Check Portfolio Balance Settings ──
    if ENFORCE_LONGS_SHORTS:
        if not (0 < MIN_PER_SIDE <= MAX_SIMULTANEOUS_TRADES // 2):
            warns.append(f"MIN_PER_SIDE = {MIN_PER_SIDE} — may be too high/low")
        if not (0.5 <= MAX_RATIO <= 1.0):
            errors.append(f"MAX_RATIO = {MAX_RATIO} — must be 0.5–1.0")

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
    if warns:
        print(f"✅ CHECKS PASSED — {len(warns)} warning(s) shown above\n")
    else:
        print("✅ ALL CHECKS PASSED — Config OK\n")
    return True


# Run validation immediately on import
if "CONFIG_VALIDATION_ENABLED" in globals() and CONFIG_VALIDATION_ENABLED:
    if not validate_config():
        sys.exit(1)  # Halt on error — set to 'pass' to ignore and continue
