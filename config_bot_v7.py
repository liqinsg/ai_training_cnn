# config_bot.py — v7.8 · Strict group3 + profile1
"""
- forex_pairs.yml 是唯一货币对来源:
    all_pairs → profile1/2/4 的 ACTIVE_PAIRS（全量）
    group3    → profile3  的 ACTIVE_PAIRS（active pairs）
- profile3 → exact group3 from YAML; ERROR if missing/empty
- profile1/2/4 → all_pairs
- 自动去重（保持 YAML 顺序）— 重复项只取第一次
- CLI: --profile N / -p N  (N=1,2,3,4)
"""
from __future__ import annotations
from pathlib import Path
from typing import Any
import yaml
import argparse
import sys

# ==========================================
# 📂 Load from YAML — EXACT values only
# ==========================================
_YAML_PATH = Path(__file__).resolve().parent / "forex_pairs.yml"
def _load_pairs_from_yaml():
    if not _YAML_PATH.exists():
        raise FileNotFoundError(f"Cannot find {_YAML_PATH} — place it alongside config_bot.py")
    
    with open(_YAML_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    
    clean_all = data.get("all_pairs", [])
    if not clean_all:
        raise ValueError("forex_pairs.yml: 'all_pairs' list is empty or missing")
    
    clean_group3 = data.get("group3")
    if not clean_group3:
        raise ValueError("forex_pairs.yml: 'group3' is missing or empty — please define it!")
    
    def _to_symbols(names):
        """YAML 名称 → Yahoo/OANDA 符号（自动去重，保持原顺序）"""
        ya = []
        oa_map = {}
        seen = set()
        for name in names:
            if name in seen:
                continue
            seen.add(name)
            ys = f"{name}=X"
            os = f"{name[:3]}_{name[3:]}" if len(name) == 6 else name
            ya.append(ys)
            oa_map[ys] = os
        return ya, oa_map
    
    ALL_PAIRS, YAHOO_TO_OANDA = _to_symbols(clean_all)
    GROUP3_PAIRS, _ = _to_symbols(clean_group3)
    
    PAIR_GROUPS = {
        "group3": GROUP3_PAIRS,
        "all": ALL_PAIRS,
    }
    return ALL_PAIRS, YAHOO_TO_OANDA, PAIR_GROUPS, GROUP3_PAIRS

ALL_PAIRS, YAHOO_TO_OANDA, PAIR_GROUPS, GROUP3_PAIRS = _load_pairs_from_yaml()

# ==========================================
# Global defaults
# ==========================================
ACTIVE_PAIRS = list(ALL_PAIRS)
EXCLUDE_PAIRS = []
EXCLUDE_OANDA = []
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

# ==========================================
# 🔑 Account IDs
# ==========================================
try:
    from config_oanda import api as OANDA_API
    from config_oanda import (
        OANDA_ACCOUNT_ID_1 as OANDA_ACCOUNT_ID_PROFILE1,
        OANDA_ACCOUNT_ID_2 as OANDA_ACCOUNT_ID_PROFILE2,
        OANDA_ACCOUNT_ID_3 as OANDA_ACCOUNT_ID_PROFILE3,
        OANDA_ACCOUNT_ID_4 as OANDA_ACCOUNT_ID_PROFILE4,
    )
    _HAVE_OANDA = True
except ImportError:
    _HAVE_OANDA = False
    OANDA_API = None
    OANDA_ACCOUNT_ID_PROFILE1 = OANDA_ACCOUNT_ID_PROFILE2 = OANDA_ACCOUNT_ID_PROFILE3 = OANDA_ACCOUNT_ID_PROFILE4 = "NOT_CONFIGURED"

# ==========================================
# Exported Keys
# ==========================================
_GLOBAL_CONSTANT_KEYS: tuple[str, ...] = (
    "ALL_PAIRS", "YAHOO_TO_OANDA", "EXCLUDE_PAIRS", "ACTIVE_PAIRS", "EXCLUDE_OANDA",
    "PAIR_GROUPS", "YF_INTERVAL", "YF_PERIOD_FULL", "YF_PERIOD_RESAMPLE",
    "YF_INTERVAL_D", "YF_PERIOD_FULL_D", "YF_PERIOD_RESAMPLE_D",
    "PERIODS_YEAR", "MC_BAND_PCT", "MC_MAX_AGE_HOURS", "SIMULATIONS", "CONFIDENCE",
    "ATR_PERIOD", "BASE_TP_PIPS", "EMA100_BUFFER_PIPS", "MIN_SL_PIPS", "MIN_SL_PIPS_JPY",
    "DEBUG_MODE", "NO_COOLDOWN", "DEFAULT_LOT_SIZE",
    "MULTI_TF_CONFLUENCE", "CONFLUENCE_REQUIRED_TFS",
    "TRAILING_TP", "DYNAMIC_TP", "TP_RAISE_THRESHOLD_PIPS",
    "H4_LOOKBACK", "H4_FORECAST", "DAILY_LOOKBACK", "DAILY_FORECAST",
    "USE_ATR", "USE_MACD", "USE_RSI", "USE_ADX", "MODEL_TYPE",
    "TARGET_HORIZON", "TRAIN_LOOKBACK_BARS",
    "D_STRATEGY_GROUPS", "EXCLUDE_CURRENCIES_GLOBAL",
)

# ==========================================
# 📊 Profile Config
# ==========================================
PROFILE_CFG = {
    "profile1": {
        "LABEL": "PROFILE1",
        "ACCOUNT_NAME": "Account 001",
        "OANDA_ACCOUNT_ID": OANDA_ACCOUNT_ID_PROFILE1,
        "COOLDOWN_FILE": "cooldown_profile1.json",
        "RESULTS_DIR": "daily_results_profile1",
        "MODE": "LEVEL10",
        "BASE_MIN_EDGE": 0.50,
        "WEIGHT_STRENGTH": 0.35, "WEIGHT_RSI": 0.20, "WEIGHT_ADX": 0.15,
        "WEIGHT_XGB": 0.20, "WEIGHT_MC": 0.10,
        "MIN_CONVICTION_SCORE": 30.0, "MIN_SCORE_GAP": 0.10,
        "MAX_OPEN_POSITIONS": 3, "MAX_OPEN_PER_RUN": 1,
        "XGB_BULLISH_THRESHOLD": 0.52, "MC_BULLISH_THRESHOLD_PCT": 52.0,
        "MC_STRONG_THRESHOLD": 0.60,
        "REQUIRE_DIRECTION_CONSENSUS": True,
        "CONSENSUS_THRESHOLD": 2, "CONSENSUS_REQUIRED_VOTES": 2,
        "REQUIRE_STRONG_MOMENTUM": False, "ADX_SCALE_FACTOR": 2.0,
        "TREND_FILTER_ENABLED": False, "WEEK_EMA100_FILTER_ENABLED": False,
        "EMA_PERIOD_FAST": 20, "EMA_PERIOD_SLOW": 40,
        "TP_MULT": 2.0, "TP_STRONG_MULT": 2.5,
        "ATR_SL_MULT": 2.0, "ATR_TP_MULT": 2.5,
        "USE_DYNAMIC_SL": 2, "DYNAMIC_SL_MULT": 1.5,
        "BE_TRIGGER_ATR_MULT": 2.5, "TRAIL_TRIGGER_ATR_MULT": 3.5,
        "TRAIL_ATR_MULT": 2.8, "MAX_HOLD_BARS": 24,
        "SL_USE_ZONE_HIERARCHY": True, "USE_TOP_PAIRS_ONLY": False,
        "TOP_PAIRS_COUNT": 4, "TOP_PAIRS_MIN_GAP": 0.25,
        "SKIP_MC": False,
    },
    "profile2": {
        "LABEL": "PROFILE2",
        "ACCOUNT_NAME": "Account 002",
        "OANDA_ACCOUNT_ID": OANDA_ACCOUNT_ID_PROFILE2,
        "COOLDOWN_FILE": "cooldown_profile2.json",
        "RESULTS_DIR": "daily_results_profile2",
        "MODE": "LEVEL10",
        "BASE_MIN_EDGE": 0.50,
        "WEIGHT_STRENGTH": 0.35, "WEIGHT_RSI": 0.20, "WEIGHT_ADX": 0.15,
        "WEIGHT_XGB": 0.20, "WEIGHT_MC": 0.10,
        "MIN_CONVICTION_SCORE": 30.0, "MIN_SCORE_GAP": 0.10,
        "MAX_OPEN_POSITIONS": 3, "MAX_OPEN_PER_RUN": 1,
        "XGB_BULLISH_THRESHOLD": 0.52, "MC_BULLISH_THRESHOLD_PCT": 52.0,
        "MC_STRONG_THRESHOLD": 0.60,
        "REQUIRE_DIRECTION_CONSENSUS": True,
        "CONSENSUS_THRESHOLD": 2, "CONSENSUS_REQUIRED_VOTES": 2,
        "REQUIRE_STRONG_MOMENTUM": False, "ADX_SCALE_FACTOR": 2.0,
        "TREND_FILTER_ENABLED": False, "WEEK_EMA100_FILTER_ENABLED": False,
        "EMA_PERIOD_FAST": 20, "EMA_PERIOD_SLOW": 40,
        "TP_MULT": 2.0, "TP_STRONG_MULT": 2.5,
        "ATR_SL_MULT": 2.0, "ATR_TP_MULT": 2.5,
        "USE_DYNAMIC_SL": 2, "DYNAMIC_SL_MULT": 1.5,
        "BE_TRIGGER_ATR_MULT": 2.5, "TRAIL_TRIGGER_ATR_MULT": 3.5,
        "TRAIL_ATR_MULT": 2.8, "MAX_HOLD_BARS": 24,
        "SL_USE_ZONE_HIERARCHY": True, "USE_TOP_PAIRS_ONLY": False,
        "TOP_PAIRS_COUNT": 4, "TOP_PAIRS_MIN_GAP": 0.25,
        "SKIP_MC": False,
    },
    "profile3": {
        "LABEL": "PROFILE3",
        "ACCOUNT_NAME": "Account 003",
        "OANDA_ACCOUNT_ID": OANDA_ACCOUNT_ID_PROFILE3,
        "COOLDOWN_FILE": "cooldown_profile3.json",
        "RESULTS_DIR": "daily_results_profile3",
        "MODE": "LEVEL10",
        "BASE_MIN_EDGE": 0.52,
        "WEIGHT_STRENGTH": 0.45, "WEIGHT_RSI": 0.15, "WEIGHT_ADX": 0.15,
        "WEIGHT_XGB": 0.15, "WEIGHT_MC": 0.10,
        "MIN_CONVICTION_SCORE": 38.0, "MIN_SCORE_GAP": 0.18,
        "MAX_OPEN_POSITIONS": 3, "MAX_OPEN_PER_RUN": 1,
        "XGB_BULLISH_THRESHOLD": 0.57, "MC_BULLISH_THRESHOLD_PCT": 57.0,
        "MC_STRONG_THRESHOLD": 0.62,
        "REQUIRE_DIRECTION_CONSENSUS": True,
        "CONSENSUS_THRESHOLD": 2, "CONSENSUS_REQUIRED_VOTES": 2,
        "REQUIRE_STRONG_MOMENTUM": True, "ADX_SCALE_FACTOR": 2.0,
        "TREND_FILTER_ENABLED": True, "WEEK_EMA100_FILTER_ENABLED": True,
        "EMA_PERIOD_FAST": 40, "EMA_PERIOD_SLOW": 80,
        "TP_MULT": 1.8, "TP_STRONG_MULT": 2.1,
        "ATR_SL_MULT": 2.3, "ATR_TP_MULT": 2.4,
        "USE_DYNAMIC_SL": 2, "DYNAMIC_SL_MULT": 1.5,
        "BE_TRIGGER_ATR_MULT": 2.2, "TRAIL_TRIGGER_ATR_MULT": 3.0,
        "TRAIL_ATR_MULT": 2.0, "MAX_HOLD_BARS": 10,
        "SL_USE_ZONE_HIERARCHY": True, "SL_ZONE_TRAILING": True,
        "USE_TOP_PAIRS_ONLY": True, "TOP_PAIRS_COUNT": 3, "TOP_PAIRS_MIN_GAP": 0.22,
        "SKIP_MC": False,
    },
    "profile4": {
        "LABEL": "PROFILE4",
        "ACCOUNT_NAME": "Account 004",
        "OANDA_ACCOUNT_ID": OANDA_ACCOUNT_ID_PROFILE4,
        "COOLDOWN_FILE": "cooldown_profile4.json",
        "RESULTS_DIR": "daily_results_profile4",
        "MODE": "LEVEL10",
        "BASE_MIN_EDGE": 0.50, "DEFAULT_LOT_SIZE": 5000,
        "WEIGHT_STRENGTH": 0.40, "WEIGHT_RSI": 0.15, "WEIGHT_ADX": 0.15,
        "WEIGHT_XGB": 0.20, "WEIGHT_MC": 0.10,
        "MIN_CONVICTION_SCORE": 15.0, "MIN_SCORE_GAP": 0.05,
        "MAX_OPEN_POSITIONS": 10, "MAX_OPEN_PER_RUN": 3,
        "MAX_OPEN_HIGH_VOL": 6, "MAX_OPEN_MID_VOL": 2, "MAX_OPEN_LOW_VOL": 2,
        "JPY_CONSENSUS_MIN": 2, "JPY_MAX_OPEN_PER_RUN": 2,
        "MIN_SL_PIPS": 35, "MIN_SL_PIPS_JPY": 60,
        "SL_MAX_ALLOWED_PIPS": 200, "SL_MAX_ALLOWED_PIPS_JPY": 500,
        "XGB_BULLISH_THRESHOLD": 0.52, "MC_BULLISH_THRESHOLD_PCT": 52.0,
        "MC_STRONG_THRESHOLD": 0.55,
        "REQUIRE_DIRECTION_CONSENSUS": True,
        "CONSENSUS_THRESHOLD": 2, "CONSENSUS_REQUIRED_VOTES": 2,
        "REQUIRE_STRONG_MOMENTUM": False, "ADX_SCALE_FACTOR": 2.0,
        "TREND_FILTER_ENABLED": True, "WEEK_EMA100_FILTER_ENABLED": False,
        "EMA_PERIOD_FAST": 15, "EMA_PERIOD_SLOW": 30,
        "TP_MULT": 2.5, "TP_STRONG_MULT": 3.0,
        "ATR_SL_MULT": 2.5, "ATR_TP_MULT": 3.0,
        "USE_DYNAMIC_SL": 2, "DYNAMIC_SL_MULT": 1.5,
        "BE_TRIGGER_ATR_MULT": 1.5, "TRAIL_TRIGGER_ATR_MULT": 2.5,
        "TRAIL_ATR_MULT": 1.5, "MAX_HOLD_BARS": 12,
        "USE_H4_ESCALE": True, "TP_LINK_SL": True,
        "SL_USE_ZONE_HIERARCHY": True, "USE_TOP_PAIRS_ONLY": False,
        "TOP_PAIRS_COUNT": 4, "TOP_PAIRS_MIN_GAP": 0.25,
        "SKIP_MC": False,
    },
}

# ==========================================
# Shared
# ==========================================
D_STRATEGY_GROUPS = {
    "GBP_AUD": {"bar_hours": 24, "max_hold": 12, "sl_granularity": "D", "confirm_on_close": True},
}
EXCLUDE_CURRENCIES_GLOBAL = []

# ==========================================
# 🔌 load_profile — STRICT group3 ✅
# ==========================================
def load_profile(profile_name: str) -> dict:
    import copy
    base_dir = Path(__file__).resolve().parent
    template = PROFILE_CFG.get(profile_name, PROFILE_CFG["profile2"])
    final: dict[str, Any] = copy.deepcopy(template)
    
    for key in _GLOBAL_CONSTANT_KEYS:
        if key in final:
            continue
        final[key] = globals()[key]
    
    # Exact assignment — no silent fallback ✅
    if profile_name == "profile3":
        final["ACTIVE_PAIRS"] = list(GROUP3_PAIRS)
        final["_ACTIVE_SOURCE"] = f"forex_pairs.yml → group3 ({len(GROUP3_PAIRS)} pairs)"
    else:
        final["ACTIVE_PAIRS"] = list(ALL_PAIRS)
        final["_ACTIVE_SOURCE"] = f"forex_pairs.yml → all_pairs ({len(ALL_PAIRS)} pairs)"
    
    final["EXCLUDE_PAIRS"] = []
    final["EXCLUDE_OANDA"] = []
    
    if profile_name == "profile3":
        final["INSTRUMENT_OVERRIDES"] = D_STRATEGY_GROUPS
        final["EXCLUDE_CURRENCIES"] = list(EXCLUDE_CURRENCIES_GLOBAL)
    else:
        final["INSTRUMENT_OVERRIDES"] = {}
        final["EXCLUDE_CURRENCIES"] = []
    
    if _HAVE_OANDA:
        final["OANDA_API"] = OANDA_API
    
    final["BASE_DIR"] = base_dir
    final["PROFILE_NAME"] = profile_name
    final["COOLDOWN_FILE_PATH"] = base_dir / final.get("COOLDOWN_FILE", f"cooldown_{profile_name}.json")
    final["RESULTS_DIR_PATH"] = base_dir / final.get("RESULTS_DIR", f"daily_results_{profile_name}")
    
    return final

def cfg(P: dict, key: str, default: Any = None) -> Any:
    return P.get(key, default) if P else default

# ==========================================
# 🧪 Test CLI — NEW SYNTAX: --profile N / -p N
# ==========================================
def _format_value(v):
    if isinstance(v, list):
        return f"[{len(v)} items] → {v}"
    elif isinstance(v, dict):
        return f"[{len(v)} keys] → keys: {list(v.keys())}"
    else:
        return str(v)

def _print_profile(P: dict, profile_name: str):
    sep = "=" * 70
    print(f"\n{sep}")
    print(f"📊 PROFILE: {profile_name}  |  {P.get('ACCOUNT_NAME')}")
    print(sep)
    sections = [
        ("🔑 Identity", ["LABEL", "ACCOUNT_NAME", "OANDA_ACCOUNT_ID", "MODE"]),
        ("📈 Pairs — FULL LIST", ["ALL_PAIRS", "ACTIVE_PAIRS", "_ACTIVE_SOURCE", "PAIR_GROUPS"]),
        ("🎯 Position Limits", ["MAX_OPEN_POSITIONS", "MAX_OPEN_PER_RUN", "DEFAULT_LOT_SIZE"]),
        ("⚖️ Thresholds", ["MIN_CONVICTION_SCORE", "MIN_SCORE_GAP", "BASE_MIN_EDGE",
                          "XGB_BULLISH_THRESHOLD", "MC_BULLISH_THRESHOLD_PCT", "MC_STRONG_THRESHOLD"]),
        ("🏋️ Weights", ["WEIGHT_STRENGTH", "WEIGHT_RSI", "WEIGHT_ADX", "WEIGHT_XGB", "WEIGHT_MC"]),
        ("🔄 Filters", ["REQUIRE_STRONG_MOMENTUM", "TREND_FILTER_ENABLED", "EMA_PERIOD_FAST", "EMA_PERIOD_SLOW"]),
        ("🛡️ SL/TP", ["ATR_SL_MULT", "ATR_TP_MULT", "TP_MULT", "MAX_HOLD_BARS"]),
        ("📁 Paths", ["COOLDOWN_FILE_PATH", "RESULTS_DIR_PATH"]),
    ]
    for title, keys in sections:
        print(f"\n{title}")
        print("-" * 50)
        for k in keys:
            v = P.get(k, "—")
            print(f"  {k:<35} {_format_value(v)}")
    print(f"\n{sep}\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Config Bot — Exact Group3 Print")
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--profile", "-p", type=int, choices=[1, 2, 3, 4],
                   help="Profile number: 1, 2, 3, or 4")
    args = parser.parse_args()
    name = f"profile{args.profile}"
    
    try:
        P = load_profile(name)
        _print_profile(P, name)
    except Exception as e:
        print(f"\n❌ ERROR: {e}\n")
        sys.exit(1)