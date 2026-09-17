"""
ALL strategy/profile settings in ONE file.
Pairs loaded from: forex_pairs.yml
OANDA connection/account/environment configuration belongs to config_oanda.py.
Run directly to test: python config_bot.py
"""

from __future__ import annotations
from pathlib import Path
from typing import Any
import yaml
import json

# ==========================================
# 🔧 File Paths
# ==========================================
BASE_DIR = Path(__file__).resolve().parent
PAIRS_FILE = BASE_DIR / "forex_pairs.yml"


# ==========================================
# 📋 Load Trading Pairs — Smart Parser
# ==========================================
def load_pairs_from_yaml(pairs_path: Path) -> tuple[list[str], dict[str, str]]:
    if not pairs_path.exists():
        raise FileNotFoundError(f"Pairs file not found: {pairs_path}")

    with open(pairs_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    print(f"🔍 YAML type: {type(data).__name__}")
    if isinstance(data, dict):
        print(f"🔍 YAML keys: {list(data.keys())}")

    if isinstance(data, list):
        pair_codes = data
    elif isinstance(data, dict) and "pairs" in data:
        pair_codes = data["pairs"]
    elif isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, list) and len(value) > 0 and isinstance(value[0], str):
                print(f"🔍 Using list under key: '{key}'")
                pair_codes = value
                break
        else:
            raise ValueError(
                f"Cannot find pair list in {pairs_path}. Keys: {list(data.keys())}"
            )
    else:
        raise ValueError(f"Unexpected YAML structure: {type(data).__name__}")

    if not pair_codes:
        raise ValueError(f"No currency pairs found in {pairs_path}")

    ALL_PAIRS = [f"{code}=X" for code in pair_codes]
    YAHOO_TO_OANDA = {f"{code}=X": code[:3] + "_" + code[3:] for code in pair_codes}
    return ALL_PAIRS, YAHOO_TO_OANDA


ALL_PAIRS, YAHOO_TO_OANDA = load_pairs_from_yaml(PAIRS_FILE)

# ==========================================
# GLOBAL DEFAULTS
# ==========================================
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

MULTI_TF_CONFLUENCE = False
CONFLUENCE_REQUIRED_TFS = 2
TRAILING_TP = True
DYNAMIC_TP = False
TP_RAISE_THRESHOLD_PIPS = 15
H4_LOOKBACK = 90
H4_FORECAST = 8
DAILY_LOOKBACK = 90
DAILY_FORECAST = 5
USE_ATR = True
USE_MACD = True
USE_RSI = True
USE_ADX = True
MODEL_TYPE = "xgboost"
TARGET_HORIZON = 6
TRAIN_LOOKBACK_BARS = 5000

_GLOBAL_CONSTANT_KEYS: tuple[str, ...] = (
    "ALL_PAIRS",
    "YAHOO_TO_OANDA",
    "YF_INTERVAL",
    "YF_PERIOD_FULL",
    "YF_PERIOD_RESAMPLE",
    "YF_INTERVAL_D",
    "YF_PERIOD_FULL_D",
    "YF_PERIOD_RESAMPLE_D",
    "PERIODS_YEAR",
    "MC_BAND_PCT",
    "MC_MAX_AGE_HOURS",
    "SIMULATIONS",
    "CONFIDENCE",
    "ATR_PERIOD",
    "BASE_TP_PIPS",
    "EMA100_BUFFER_PIPS",
    "MIN_SL_PIPS",
    "MIN_SL_PIPS_JPY",
    "DEBUG_MODE",
    "NO_COOLDOWN",
    "DEFAULT_LOT_SIZE",
    "MULTI_TF_CONFLUENCE",
    "CONFLUENCE_REQUIRED_TFS",
    "TRAILING_TP",
    "DYNAMIC_TP",
    "TP_RAISE_THRESHOLD_PIPS",
    "H4_LOOKBACK",
    "H4_FORECAST",
    "DAILY_LOOKBACK",
    "DAILY_FORECAST",
    "USE_ATR",
    "USE_MACD",
    "USE_RSI",
    "USE_ADX",
    "MODEL_TYPE",
    "TARGET_HORIZON",
    "TRAIN_LOOKBACK_BARS",
    "D_STRATEGY_GROUPS",
    "EXCLUDE_PAIRS_GLOBAL",
    "PAIRS_FILE",
)

# ==========================================
# 📊 PROFILE STRATEGY CONFIG
# ==========================================
PROFILE_CFG = {
    "profile2": {
        "LABEL": "CONSERVATIVE",
        "DESCRIPTION": "Low-frequency, high-confidence mode. Higher conviction threshold, no trend filter, wider trailing. Designed for capital preservation — fewer trades, higher bar for entry.",
        "ACCOUNT_NAME": "Account 002",
        "COOLDOWN_FILE": "cooldown_profile2.json",
        "RESULTS_DIR": "daily_results_profile2",
        "EXCLUDE_PAIRS": [],
        "MODE": "LEVEL10",
        "BASE_MIN_EDGE": 0.55,
        "WEIGHT_STRENGTH": 0.35,
        "WEIGHT_RSI": 0.20,
        "WEIGHT_ADX": 0.15,
        "WEIGHT_XGB": 0.20,
        "WEIGHT_MC": 0.10,
        "MIN_CONVICTION_SCORE": 28.0,
        "MIN_SCORE_GAP": 0.12,
        "MAX_OPEN_POSITIONS": 6,
        "MAX_OPEN_PER_RUN": 2,
        "XGB_BULLISH_THRESHOLD": 0.55,
        "MC_BULLISH_THRESHOLD_PCT": 55.0,
        "MC_STRONG_THRESHOLD": 0.60,
        "REQUIRE_DIRECTION_CONSENSUS": True,
        "CONSENSUS_THRESHOLD": 2,
        "CONSENSUS_REQUIRED_VOTES": 2,
        "REQUIRE_STRONG_MOMENTUM": False,
        "ADX_SCALE_FACTOR": 2.0,
        "TREND_FILTER_ENABLED": False,
        "WEEK_EMA100_FILTER_ENABLED": False,
        "EMA_PERIOD_FAST": 20,
        "EMA_PERIOD_SLOW": 40,
        "TP_MULT": 2.0,
        "TP_STRONG_MULT": 2.5,
        "ATR_SL_MULT": 2.0,
        "ATR_TP_MULT": 2.5,
        "USE_DYNAMIC_SL": 2,
        "DYNAMIC_SL_MULT": 1.5,
        "BE_TRIGGER_ATR_MULT": 2.5,
        "TRAIL_TRIGGER_ATR_MULT": 3.5,
        "TRAIL_ATR_MULT": 2.8,
        "MAX_HOLD_BARS": 24,
        "SL_USE_ZONE_HIERARCHY": True,
        "USE_TOP_PAIRS_ONLY": True,
        "TOP_PAIRS_COUNT": 4,
        "TOP_PAIRS_MIN_GAP": 0.25,
        "SKIP_MC": False,
        "SL_ZONE_TRAILING": True,
    },
    "profile3": {
        "LABEL": "BALANCED",
        "DESCRIPTION": "Recommended default — balanced risk/opportunity. Tuned to produce consistent signals without overtrading. EMA100 trend protection active, consensus relaxed, moderate conviction. Best for steady live execution.",
        "ACCOUNT_NAME": "Account 003",
        "COOLDOWN_FILE": "cooldown_profile3.json",
        "RESULTS_DIR": "daily_results_profile3",
        "EXCLUDE_PAIRS": [],
        "MODE": "LEVEL10",
        "BASE_MIN_EDGE": 0.50,
        "WEIGHT_STRENGTH": 0.40,
        "WEIGHT_RSI": 0.15,
        "WEIGHT_ADX": 0.15,
        "WEIGHT_XGB": 0.20,
        "WEIGHT_MC": 0.10,
        "MIN_CONVICTION_SCORE": 22.0,
        "MIN_SCORE_GAP": 0.12,
        "MAX_OPEN_POSITIONS": 3,
        "MAX_OPEN_PER_RUN": 1,
        "XGB_BULLISH_THRESHOLD": 0.55,
        "MC_BULLISH_THRESHOLD_PCT": 56.0,
        "MC_STRONG_THRESHOLD": 0.56,
        "REQUIRE_DIRECTION_CONSENSUS": True,
        "CONSENSUS_THRESHOLD": 2,
        "CONSENSUS_REQUIRED_VOTES": 2,
        "REQUIRE_STRONG_MOMENTUM": False,
        "ADX_SCALE_FACTOR": 2.2,
        "TREND_FILTER_ENABLED": True,
        "WEEK_EMA100_FILTER_ENABLED": True,
        "EMA_PERIOD_FAST": 40,
        "EMA_PERIOD_SLOW": 80,
        "TP_MULT": 2.2,
        "TP_STRONG_MULT": 2.8,
        "ATR_SL_MULT": 2.2,
        "ATR_TP_MULT": 2.8,
        "USE_DYNAMIC_SL": 2,
        "DYNAMIC_SL_MULT": 1.3,
        "BE_TRIGGER_ATR_MULT": 1.3,
        "TRAIL_TRIGGER_ATR_MULT": 2.2,
        "TRAIL_ATR_MULT": 1.3,
        "MAX_HOLD_BARS": 10,
        "SL_USE_ZONE_HIERARCHY": True,
        "USE_TOP_PAIRS_ONLY": True,
        "TOP_PAIRS_COUNT": 3,
        "TOP_PAIRS_MIN_GAP": 0.32,
        "SKIP_MC": False,
        "SL_ZONE_TRAILING": True,
    },
    "profile4": {
        "LABEL": "AGGRESSIVE / DEMO",
        "DESCRIPTION": "High-activity mode for demo & active markets. Lower thresholds, expanded pair selection, faster EMA crossovers, relaxed filters. Larger position limits with half-size lots. Higher risk — more signals, not for unchecked live use.",
        "ACCOUNT_NAME": "Account 004",
        "COOLDOWN_FILE": "cooldown_profile4.json",
        "RESULTS_DIR": "daily_results_profile4",
        "EXCLUDE_PAIRS": [],
        "MODE": "LEVEL10",
        "BASE_MIN_EDGE": 0.50,
        "DEFAULT_LOT_SIZE": 5000,
        "WEIGHT_STRENGTH": 0.40,
        "WEIGHT_RSI": 0.15,
        "WEIGHT_ADX": 0.15,
        "WEIGHT_XGB": 0.20,
        "WEIGHT_MC": 0.10,
        "MIN_CONVICTION_SCORE": 15.0,
        "MIN_SCORE_GAP": 0.05,
        "MAX_OPEN_POSITIONS": 10,
        "MAX_OPEN_PER_RUN": 3,
        "MAX_OPEN_HIGH_VOL": 6,
        "MAX_OPEN_MID_VOL": 2,
        "MAX_OPEN_LOW_VOL": 2,
        "JPY_CONSENSUS_MIN": 2,
        "JPY_MAX_OPEN_PER_RUN": 2,
        "MIN_SL_PIPS": 35,
        "MIN_SL_PIPS_JPY": 60,
        "SL_MAX_ALLOWED_PIPS": 200,
        "SL_MAX_ALLOWED_PIPS_JPY": 500,
        "XGB_BULLISH_THRESHOLD": 0.52,
        "MC_BULLISH_THRESHOLD_PCT": 52.0,
        "MC_STRONG_THRESHOLD": 0.55,
        "REQUIRE_DIRECTION_CONSENSUS": True,
        "CONSENSUS_THRESHOLD": 2,
        "CONSENSUS_REQUIRED_VOTES": 2,
        "REQUIRE_STRONG_MOMENTUM": False,
        "ADX_SCALE_FACTOR": 2.0,
        "TREND_FILTER_ENABLED": True,
        "WEEK_EMA100_FILTER_ENABLED": False,
        "EMA_PERIOD_FAST": 15,
        "EMA_PERIOD_SLOW": 30,
        "TP_MULT": 2.5,
        "TP_STRONG_MULT": 3.0,
        "ATR_SL_MULT": 2.5,
        "ATR_TP_MULT": 3.0,
        "USE_DYNAMIC_SL": 2,
        "DYNAMIC_SL_MULT": 1.5,
        "BE_TRIGGER_ATR_MULT": 1.5,
        "TRAIL_TRIGGER_ATR_MULT": 2.5,
        "TRAIL_ATR_MULT": 1.5,
        "MAX_HOLD_BARS": 12,
        "USE_H4_ESCALE": True,
        "TP_LINK_SL": True,
        "SL_USE_ZONE_HIERARCHY": True,
        "USE_TOP_PAIRS_ONLY": True,
        "TOP_PAIRS_COUNT": 3,
        "TOP_PAIRS_MIN_GAP": 0.28,
        "SKIP_MC": False,
        "SL_ZONE_TRAILING": True,
    },
}

# ==========================================
# 🌐 Global Shared Resources
# ==========================================
D_STRATEGY_GROUPS = {
    "GBP_AUD": {
        "bar_hours": 24,
        "max_hold": 12,
        "sl_granularity": "D",
        "confirm_on_close": True,
    },
    "EUR_AUD": {
        "bar_hours": 24,
        "max_hold": 12,
        "sl_granularity": "D",
        "confirm_on_close": True,
    },
    "EUR_GBP": {
        "bar_hours": 24,
        "max_hold": 12,
        "sl_granularity": "D",
        "confirm_on_close": True,
    },
}
EXCLUDE_PAIRS_GLOBAL = []


# ==========================================
# 🔌 load_profile()
# ==========================================
def load_profile(profile_num: str | list):
    # 解包列表/元组情况
    if isinstance(profile_num, (list, tuple)) and len(profile_num) == 1:
        profile_num = profile_num[0]
    # 纯数字直接用，带前缀也兼容
    profile_num = str(profile_num).strip()
    if profile_num.startswith("profile"):
        num = profile_num.replace("profile", "")
    else:
        num = profile_num
    key = f"profile{num}"

    # Load parameter library
    with open("profiles_all.json") as f:
        param_lib = json.load(f)
    # Load strategy/profile bindings (no OANDA connection settings)
    with open("config_bot_v7.yml") as f:
        bindings = yaml.safe_load(f)["profiles"]

    if key not in bindings:
        raise ValueError(
            f"Profile '{key}' not defined. Available: {list(bindings.keys())}"
        )

    binding = bindings[key]
    params = param_lib.get(binding["param_set"])
    if not params:
        raise ValueError(
            f"Param set '{binding['param_set']}' not found in profiles_all.json"
        )

    print(f"\n  ✅ PROFILE {num} → {binding['account_alias']}")
    print(f"     Strategy: {binding['param_set']} ({params['LABEL']})")

    return {
        **binding,
        **params,
        "strategy": params,
        "ALL_PAIRS": ALL_PAIRS,
        "YAHOO_TO_OANDA": YAHOO_TO_OANDA,
    }


def cfg(P: dict, key: str, default: Any = None) -> Any:
    return P.get(key, default) if P else default


# ==========================================
# 🧪 TEST MAIN BLOCK
# ==========================================
if __name__ == "__main__":
    import sys

    print("=" * 70)
    print("🧪 CONFIG BOT — Unified Import Edition")
    print("=" * 70)
    print(
        f"\n📁 Pairs File: {PAIRS_FILE} | Found: {PAIRS_FILE.exists()} | Total: {len(ALL_PAIRS)}"
    )

    for pname in PROFILE_CFG:
        print(f"\n{'═' * 70}")
        try:
            P = load_profile(pname)
            print(f"  ▶ {cfg(P, 'LABEL')} — {pname}")
            print(f"  {cfg(P, 'DESCRIPTION')}")
            print(f"{'─' * 70}")
            print(f"  Account        : {cfg(P, 'ACCOUNT_NAME')}")
            print(f"  Conviction     : {cfg(P, 'MIN_CONVICTION_SCORE')}")
            print(f"  Max Positions  : {cfg(P, 'MAX_OPEN_POSITIONS')}")
            print(f"  Exclusions     : {cfg(P, 'EXCLUDE_PAIRS') or 'None'}")
        except Exception as e:
            print(f"  ❌ FAILED: {e}")
            import traceback

            traceback.print_exc()
            sys.exit(1)

    print(f"\n{'=' * 70}")
    print("✅ All profiles loaded — Unified import OK")
    print(f"{'=' * 70}")
