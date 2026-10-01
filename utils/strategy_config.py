"""
strategy_config.py — Currency Strength Configuration Only
Sourced from original config.py — 2026-10-01 extracted
"""

# ========== Timeframes ==========
SIGNAL_TIMEFRAMES = ["H4", "H1", "M30", "M15"]

# ========== Currency Universe ==========
CURRENCIES = ["EUR", "USD", "GBP", "JPY", "AUD", "CHF"]

# ========== Strength Calculation Pairs ==========
STRENGTH_PAIRS = [
    "AUD_USD",
    "EUR_USD",
    "GBP_USD",
    "EUR_JPY",
    "USD_JPY",
    "AUD_JPY",
    "USD_CHF",
    "GBP_JPY"
]

# ========== Strength Lookback & Weight ==========
STRENGTH_TIMEFRAMES = {
    "H4": 3.0,
    "H1": 2.0,
    "M30": 1.5,
    "M15": 1.0,
}
STRENGTH_FAST_LOOKBACK = 5
STRENGTH_SLOW_LOOKBACK = 20
STRENGTH_FAST_WEIGHT = 0.4
STRENGTH_SLOW_WEIGHT = 0.6

# ========== Acceleration ==========
ENABLE_STRENGTH_ACCELERATION = True
STRENGTH_ACCELERATION_WEIGHT = 0.3

# ========== ATR Normalization ==========
ENABLE_ATR_NORMALIZED_STRENGTH = True
STRENGTH_ATR_PERIOD = 14

# ========== Top-N Pair Filtering ==========
# CURRENCIES = 6 → TOP_N=3 = clean top3 vs bottom3 (no overlap)
USE_TOP_PAIRS_ONLY = True
TOP_N_CURRENCIES = 3
TOP_PAIRS_MIN_GAP = 0.25
MIN_STRENGTH_GAP = 0.25
