#!/usr/bin/env python3
"""
config_bot.py — FX Bot v6.8.4 Config Loader & Validator
Source of truth: config_profile.json
Usage:
  - CLI self-test: python config_bot.py
  - Import in bot: import config_bot as C; cfg = C.get_profile(2)
"""

import json
import os
import logging
from typing import Dict, Optional

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# ─── Paths ───
CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(CONFIG_DIR, "config_profile.json")
FOREX_PAIRS_FILE = os.path.join(CONFIG_DIR, "forex_pairs.json")
# ─── Load ───
with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    _FULL = json.load(f)

# ─── Pair universe (DEFAULT_PAIRS / WHITELIST) ───
# Held in forex_pairs.json (bare symbols, no "=X") — surfaced here so the bot can
# read P["WHITELIST"] from the unified profile dict like every other key.
def _with_suffix(pair: str) -> str:
    return pair if pair.endswith("=X") else f"{pair}=X"


def _yahoo_to_oanda(pair: str) -> str:
    s = pair[:-2] if pair.endswith("=X") else pair
    return f"{s[:-3]}_{s[-3:]}"


try:
    with open(FOREX_PAIRS_FILE, "r", encoding="utf-8") as f:
        _FOREX = json.load(f)
    DEFAULT_PAIRS = [_with_suffix(p) for p in _FOREX["DEFAULT_PAIRS"]]
    WHITELIST = {
        str(k): [_with_suffix(p) for p in v] for k, v in _FOREX["WHITELIST"].items()
    }
    YAHOO_TO_OANDA = {p: _yahoo_to_oanda(p) for p in DEFAULT_PAIRS}
    logger.info(f"   forex_pairs.json ✅ {len(DEFAULT_PAIRS)} default pairs, "
                f"{len(WHITELIST)} whitelist bucket(s)")
except (OSError, KeyError, ValueError) as err:
    logger.warning(f"⚠️  forex_pairs.json unavailable ({err}) — pair lists empty")
    DEFAULT_PAIRS = []
    WHITELIST = {}
    YAHOO_TO_OANDA = {}

VERSION = _FULL["version"]
GLOBAL: Dict = _FULL["global"]
PROFILE_DEFAULTS: Dict = _FULL["profile_defaults"]
PROFILES: Dict = _FULL["profiles"]
PROFILE_IDS = sorted([int(k) for k in PROFILES.keys()])

# ─── Helper: nested get ───
def get_global(dotted_key: str):
    """Get global config by dotted path: get_global('risk_trade.SL_MIN_PIPS')"""
    parts = dotted_key.split(".")
    v = GLOBAL
    for p in parts:
        v = v[p]
    return v

# ─── Build merged profile ───
def build_profile_cfg(profile_id: int) -> Dict:
    """Merge profile → defaults → global; return flat dict ready for bot"""
    pid = str(profile_id)
    if pid not in PROFILES:
        raise ValueError(f"Profile {profile_id} not found in config")
    p = PROFILES[pid]
    d = PROFILE_DEFAULTS

    cfg = {
        "VERSION": VERSION,
        "PROFILE_ID": profile_id,
        "PROFILE_LABEL": p["NAME"],
        "WEIGHTS": p["WEIGHTS"],
        "W_S": p["WEIGHTS"]["S"],
        "W_R": p["WEIGHTS"]["R"],
        "W_A": p["WEIGHTS"]["A"],
        "W_X": p["WEIGHTS"]["X"],
        "W_M": p["WEIGHTS"]["M"],
        # Canonical WEIGHT_* names — the bot scores via cfg_bot("WEIGHT_XGB", ...),
        # which consults P first. Without these keys the lookup fell through to
        # config.py / hard-coded defaults (S=0.40 X=0.20) and silently ignored
        # the profile's real weights.
        "WEIGHT_STRENGTH": p["WEIGHTS"]["S"],
        "WEIGHT_RSI": p["WEIGHTS"]["R"],
        "WEIGHT_ADX": p["WEIGHTS"]["A"],
        "WEIGHT_XGB": p["WEIGHTS"]["X"],
        "WEIGHT_XGBOOST": p["WEIGHTS"]["X"],
        "WEIGHT_MC": p["WEIGHTS"]["M"],
        "MIN_CONVICTION": p["MIN_CONVICTION"],
        "MIN_GAP": p.get("MIN_GAP", d["MIN_GAP"]),
        "MIN_STRENGTH_GAP": p.get("MIN_GAP", d["MIN_GAP"]),
        "MIN_SLOPE": p["MIN_SLOPE"],
        # Slope-filter / confluence switches that cfg_bot() resolves from P.
        "TREND_FILTER_ENABLED": get_global("confluence_filter.TREND_FILTER_ENABLED"),
        "WEEK_EMA100_FILTER_ENABLED": get_global("confluence_filter.WEEK_EMA100_FILTER_ENABLED"),
        "RSI_DIRECTION_AWARE": get_global("confluence_filter.RSI_DIRECTION_AWARE"),
        "MULTI_TF_CONFLUENCE": get_global("confluence_filter.MULTI_TF_CONFLUENCE"),
        "CONFLUENCE_REQUIRED_TFS": get_global("confluence_filter.CONFLUENCE_REQUIRED_TFS"),
        "REQUIRE_STRONG_MOMENTUM": GLOBAL["monte_carlo"].get("REQUIRE_STRONG_MOMENTUM", True),
        "D_GATE_ENABLED": p["D_GATE_ENABLED"],
        "D_GATE_BUFFER_PCT": p.get("D_GATE_BUFFER_PCT", d["D_GATE_BUFFER_PCT"]),
        "D_GATE_CONFIRM": p.get("D_GATE_CONFIRM", d["D_GATE_CONFIRM"]),
        "D_GATE_EMA_FAST": GLOBAL["d_gate_base"]["D_GATE_EMA_FAST"],
        "D_GATE_EMA_SLOW": GLOBAL["d_gate_base"]["D_GATE_EMA_SLOW"],
        "D_GATE_SHADOW": p.get("D_GATE_SHADOW", GLOBAL["d_gate_base"]["D_GATE_SHADOW"]),
        "MAX_OPEN": p["MAX_OPEN"],
        "MAX_OPEN_POSITIONS": p["MAX_OPEN"],
        "MAX_ENTRIES_THIS_RUN": p.get("MAX_ENTRIES_THIS_RUN", d["MAX_ENTRIES_THIS_RUN"]),
        "TOP_N": p["TOP_N"],
        "TOP_N_CURRENCIES": p["TOP_N"],
        "USE_TOP_PAIRS_ONLY": p.get("USE_TOP_PAIRS_ONLY", d.get("USE_TOP_PAIRS_ONLY", True)),
        "WHITELIST": list(WHITELIST.get(pid, DEFAULT_PAIRS)),
        "ALL_PAIRS": list(WHITELIST.get(pid, DEFAULT_PAIRS)),
        "ACCOUNT_SUFFIX": p["ACCOUNT_SUFFIX"],
        "TP_MULTIPLIER": p.get("TP_MULTIPLIER", 1.0),
        "MAX_HOLD_BARS": p.get("MAX_HOLD_BARS", d["MAX_HOLD_BARS"]),
        # feature_settings
        "USE_ATR": get_global("feature_settings.USE_ATR"),
        "ATR_SL_MULT": get_global("feature_settings.ATR_SL_MULT"),
        "ATR_TP_MULT": get_global("feature_settings.ATR_TP_MULT"),
        "ATR_PERIOD": get_global("feature_settings.ATR_PERIOD"),
        "USE_MACD": get_global("feature_settings.USE_MACD"),
        "USE_RSI": get_global("feature_settings.USE_RSI"),
        "USE_ADX": get_global("feature_settings.USE_ADX"),
        # ml_settings
        "MODEL_TYPE": get_global("ml_settings.MODEL_TYPE"),
        "XGB_BULLISH_THRESHOLD": get_global("ml_settings.XGB_BULLISH_THRESHOLD"),
        # monte_carlo
        "MC_MAX_AGE_HOURS": get_global("monte_carlo.MC_MAX_AGE_HOURS"),
        "MC_SIMULATIONS": get_global("monte_carlo.MC_SIMULATIONS"),
        "MC_CONFIDENCE": get_global("monte_carlo.MC_CONFIDENCE"),
        # risk_trade
        "DEFAULT_LOT_SIZE": get_global("risk_trade.DEFAULT_LOT_SIZE"),
        "SL_MIN_PIPS": get_global("risk_trade.SL_MIN_PIPS"),
        "SL_MIN_PIPS_JPY": get_global("risk_trade.SL_MIN_PIPS_JPY"),
        # tp_trailing
        "DYNAMIC_TP": get_global("tp_trailing.DYNAMIC_TP"),
        "TRAILING_TP": get_global("tp_trailing.TRAILING_TP"),
        "TP_RAISE_THRESHOLD_PIPS": get_global("tp_trailing.TP_RAISE_THRESHOLD_PIPS"),
        "TRAIL_ATR_MULT": get_global("tp_trailing.TRAIL_ATR_MULT"),
        # confluence
        "REQUIRE_DIRECTION_CONSENSUS": get_global("confluence_filter.REQUIRE_DIRECTION_CONSENSUS"),
        "CONSENSUS_THRESHOLD": get_global("confluence_filter.CONSENSUS_THRESHOLD"),
        "SLOPE_DIAG": get_global("confluence_filter.SLOPE_DIAG"),
        # adx
        "ADX_MIN_SCORE": get_global("adx_logic.ADX_MIN_SCORE"),
        "ADX_BOOST_THRESHOLD": get_global("adx_logic.ADX_BOOST_THRESHOLD"),
        "ADX_BOOST_VALUE": get_global("adx_logic.ADX_BOOST_VALUE"),
        "ADX_SCALE_FACTOR": get_global("adx_logic.ADX_SCALE_FACTOR"),
    }
    return cfg

def get_profile(profile_id: int) -> Dict:
    """Public API — return merged config for given profile ID"""
    return build_profile_cfg(profile_id)

# ─── Validation ───
def validate_weights(weights: Dict, label: str, tol: float = 0.005) -> bool:
    s = sum(weights.values())
    ok = abs(s - 1.0) <= tol
    status = "✅" if ok else "⚠️"
    logger.info(f"   {label}")
    for k, v in weights.items():
        logger.info(f"   Weight {k}: {v:.4f}")
    logger.info(f"   ── SUM: {s:.4f}  (target: 1.0000)")
    if not ok:
        logger.warning(f"⚠️  WARN: Weights sum = {s:.4f}")
    return ok

def self_test():
    print("="*60)
    print(f"🚀 FX BOT CONFIG SELF-TEST — v{VERSION}")
    print("="*60)

    print("[1/4] File & Structure Check")
    print("─"*36)
    print(f"  config_profile.json ✅ version: {VERSION}")
    print(f"  Profiles loaded    ✅ count: {len(PROFILES)} — IDs: {PROFILE_IDS}")

    print("\n[2/4] Global Validation")
    print("─"*36)
    global_weights = {k: v for k, v in {
        "S": 0.50, "R": 0.15, "A": 0.15, "X": 0.12, "M": 0.08
    }.items()}
    validate_weights(global_weights, "Global defaults")

    print("\n[3/4] Per-Profile Validation")
    print("─"*36)
    all_ok = True
    for pid in PROFILE_IDS:
        p = PROFILES[str(pid)]
        ok = validate_weights(p["WEIGHTS"], f"Profile{pid} ({p['NAME']})")
        print("✅ ALL CHECKS PASSED\n" if ok else "")
        all_ok = all_ok and ok

    print("[4/4] Smoke Test — build_profile_cfg()")
    print("─"*36)
    for pid in PROFILE_IDS:
        cfg = build_profile_cfg(pid)
        print(f"  Profile{pid} ✅ {cfg['PROFILE_LABEL']} | "
              f"min_conv={cfg['MIN_CONVICTION']} | "
              f"dgate={cfg['D_GATE_ENABLED']} | "
              f"sum={cfg['W_S']+cfg['W_R']+cfg['W_A']+cfg['W_X']+cfg['W_M']:.4f}")

    print("="*60)
    if all_ok:
        print("✅ ✅ ✅ ALL SELF-TESTS PASSED — Ready to trade ✅ ✅ ✅")
    else:
        print("⚠️  Some validations had warnings — review above")
    print("="*60)

if __name__ == "__main__":
    self_test()