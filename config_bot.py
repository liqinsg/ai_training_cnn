# config_bot.py — v6.8.4 | Profile4 fully integrated
# Credentials stay in config_oanda.py; legacy fallbacks in config.py
import json as _json
import os as _os
import sys

# ✅ Standard: cfg = build_profile_cfg(PROFILE_ID)
# ❌ Avoid: direct config_bot.* reads

# CANONICAL NAMES — Use these only:
#   MIN_CONVICTION_SCORE, MIN_SCORE_GAP
#   MC_BULLISH_THRESHOLD, MC_BAND_PCT
#   SL_MIN_PIPS, SL_MIN_PIPS_JPY
# Avoid: THRESHOLD_SCORE, *_ALT, *_PCT, MIN_SL_PIPS, SL_MIN_DISTANCE_PIPS
# These will be removed in a future release


def _load_forex_pairs():
    _path = _os.path.join(
        _os.path.dirname(_os.path.abspath(__file__)), "forex_pairs.json"
    )
    with open(_path, "r", encoding="utf-8") as _f:
        return _json.load(_f)


def _with_suffix(pair):
    return pair if pair.endswith("=X") else f"{pair}=X"


def _yahoo_to_oanda(pair):
    _s = pair[:-2] if pair.endswith("=X") else pair
    return f"{_s[:-3]}_{_s[-3:]}"


_forex_data = _load_forex_pairs()
DEFAULT_PAIRS = [_with_suffix(p) for p in _forex_data["DEFAULT_PAIRS"]]
YAHOO_TO_OANDA = {p: _yahoo_to_oanda(p) for p in DEFAULT_PAIRS}
_WHITELIST_JSON = {
    k: [_with_suffix(p) for p in v] for k, v in _forex_data["WHITELIST"].items()
}
_PROFILE_WHITELIST_KEY = {
    1: "1",
    2: "2",
    3: "3",
    4: "4",
}
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
TRAIN_LOOKBACK_BARS = 1500
# ─── Strategy Conviction Thresholds ───
MODE = "LEVEL10"
BASE_MIN_EDGE = 0.50
MIN_CONVICTION_SCORE_ALT = 45.0
BASE_MIN_EDGE_ALT = 0.51
# ─── Data & Timeframe Intervals ───
YF_INTERVAL = "4h"
YF_PERIOD_FULL = "30d"
YF_PERIOD_RESAMPLE = "60d"
def _calc_periods_year(yf_interval):
    if yf_interval == "15m":
        return 6240
    elif yf_interval == "4h":
        return 1560
    elif yf_interval == "1d":
        return 252
    else:
        return 252

PERIODS_YEAR = _calc_periods_year(YF_INTERVAL)
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
SL_MIN_PIPS = 25
SL_MIN_PIPS_JPY = 35
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
STRENGTH_SIGNAL_BLOCK_THRESHOLD = 0.80
# ─── Cooldown & Debug ───
REMOVE_COOLDOWN = False
DEBUG_MODE = False
# ─── Auto-Ranking Feature ───
USE_TOP_PAIRS_ONLY = False
TOP_PAIRS_COUNT = 5
TOP_PAIRS_MIN_GAP = 1.5
MIN_STRENGTH_GAP = 0.25
MIN_CONVICTION_SCORE = 30  # fallback only
# ─────────────────────────────────────────────
# ✅ v6.8 ACTIVE SETTINGS
# ─────────────────────────────────────────────
REQUIRE_DIRECTION_CONSENSUS = True
CONSENSUS_THRESHOLD = 2
XGB_BULLISH_THRESHOLD = 0.55
MC_BULLISH_THRESHOLD = 55.0
ADX_SCALE_FACTOR = 2.0
ADX_FLOOR_ENABLED = True
ADX_MIN_SCORE = 20.0
ADX_BOOST_ENABLED = True
ADX_BOOST_THRESHOLD = 30.0
ADX_BOOST_VALUE = 10.0
WEIGHT_STRENGTH = 0.50
WEIGHT_RSI = 0.15
WEIGHT_ADX = 0.15
WEIGHT_XGB = 0.12
WEIGHT_XGBOOST = WEIGHT_XGB
WEIGHT_MC = 0.08
THRESHOLD_SCORE = 25.0
MAX_OPEN = 3
MAX_SIMULTANEOUS_TRADES = 3
MAX_OPEN_POSITIONS = 3
PREFER_YAHOO_DATA = True
REQUIRE_STRONG_MOMENTUM = False
ENFORCE_LONGS_SHORTS = True
MIN_PER_SIDE = 1
MAX_RATIO = 0.75
PREFER_BALANCED = True
SL_USE_ZONE_HIERARCHY = True
SL_BUFFER_PIPS = 25
SL_MIN_DISTANCE_PIPS = 20
SL_H4_LOOKBACK_BARS = 6
SL_H8_LOOKBACK_BARS = 4
SL_DAILY_LOOKBACK_BARS = 2
SL_FALLBACK_FIXED_PIPS = 35
TREND_FILTER_ENABLED = True
WEEK_EMA100_FILTER_ENABLED = False
# ─────────────────────────────────────────────
# ✅ UNIFIED PROFILE REGISTRY (v6.8.4)
# ─────────────────────────────────────────────
WEIGHTS_BASE = {
    "S": WEIGHT_STRENGTH,
    "R": WEIGHT_RSI,
    "A": WEIGHT_ADX,
    "X": WEIGHT_XGB,
    "M": WEIGHT_MC,
}
_PROFILE_BASE_COMMON = {
    "WEIGHTS": {"S": 0.40, "R": 0.15, "A": 0.15, "X": 0.20, "M": 0.10},
    "MAX_OPEN": 3,
    "MAX_ENTRIES_THIS_RUN": 3,
    "MIN_CONVICTION": 45.0,
    "MIN_GAP": 0.25,
    "D_GATE_BUFFER_PCT": 0.15,
    "D_GATE_SHADOW": False,
    "D_GATE_CONFIRM": "2H1",
}
_PROFILE_BASE_NO_DGATE = {
    **_PROFILE_BASE_COMMON,
    "D_GATE_ENABLED": False,
}
_PROFILE_BASE_DGATE = {
    **_PROFILE_BASE_COMMON,
    "D_GATE_ENABLED": True,
}
PROFILES = {
    1: {**_PROFILE_BASE_NO_DGATE, "NAME": "Profile1", "WHITELIST": _WHITELIST_JSON[_PROFILE_WHITELIST_KEY[1]]},
    2: {**_PROFILE_BASE_NO_DGATE, "NAME": "Profile2", "WHITELIST": _WHITELIST_JSON[_PROFILE_WHITELIST_KEY[2]]},
    3: {**_PROFILE_BASE_DGATE, "NAME": "Profile3", "WHITELIST": _WHITELIST_JSON[_PROFILE_WHITELIST_KEY[3]]},
    4: {**_PROFILE_BASE_DGATE, "NAME": "Profile4", "WHITELIST": _WHITELIST_JSON[_PROFILE_WHITELIST_KEY[4]]},
}
_PROFILE_EXTRAS_COMMON = {
    "MIN_SCORE_GAP": 0.50,
    "USE_TOP_PAIRS_ONLY": True,
    "TOP_N_CURRENCIES": 3,
    "TOP_PAIRS_COUNT": 4,
    "TRAIL_ATR_MULT": 2.0,
    "MAX_HOLD_BARS": 48,
    "YF_INTERVAL": "4h",
    "MC_BAND_PCT": 90,
    "MC_SIGNIFICANT_PCT": 60,
    "MC_MOMENTUM_BAND": 0.001,
    "RSI_DIRECTION_AWARE": True,
    "D_GATE_EMA_FAST": 20,
    "D_GATE_EMA_SLOW": 50,
}
_PROFILE_EXTRAS_NO_DGATE = {
    **_PROFILE_EXTRAS_COMMON,
    "TREND_FILTER_ENABLED": False,
    "SLOPE_DIAG": False,
    "SL_PAIR_FLOOR_OVERRIDES": {"GBPJPY=X": 50},
}
_PROFILE_EXTRAS_DGATE = {
    **_PROFILE_EXTRAS_COMMON,
    "TREND_FILTER_ENABLED": True,
    "SLOPE_DIAG": True,
    "SL_PAIR_FLOOR_OVERRIDES": {},
}
_PROFILE_EXTRAS = {
    1: dict(_PROFILE_EXTRAS_NO_DGATE),
    2: dict(_PROFILE_EXTRAS_NO_DGATE),
    3: dict(_PROFILE_EXTRAS_DGATE),
    4: dict(_PROFILE_EXTRAS_DGATE),
}


def get_profile(profile_id):
    pid = int(profile_id)
    if pid not in PROFILES:
        raise ValueError(f"Invalid profile {pid}. Available: {list(PROFILES.keys())}")
    return PROFILES[pid]


def _oanda_account_id(pid):
    from config_oanda import (
        OANDA_ACCOUNT_ID_1,
        OANDA_ACCOUNT_ID_2,
        OANDA_ACCOUNT_ID_3,
        OANDA_ACCOUNT_ID_4,
    )

    pid = int(pid)
    if pid == 2:
        return OANDA_ACCOUNT_ID_2
    elif pid == 3:
        return OANDA_ACCOUNT_ID_3
    elif pid == 4:
        return OANDA_ACCOUNT_ID_4
    elif pid == 1:
        return OANDA_ACCOUNT_ID_1

    raise ValueError(f"No OANDA account ID defined for profile {pid}")


def build_profile_cfg(profile_id):
    from types import SimpleNamespace

    pid = int(profile_id)
    p = get_profile(pid)
    d = {k: v for k, v in globals().items() if not k.startswith("_")}
    w = p["WEIGHTS"]
    d["WEIGHT_STRENGTH"] = w["S"]
    d["WEIGHT_RSI"] = w["R"]
    d["WEIGHT_ADX"] = w["A"]
    d["WEIGHT_XGB"] = w["X"]
    d["WEIGHT_XGBOOST"] = w["X"]
    d["WEIGHT_MC"] = w["M"]
    d["NAME"] = p["NAME"]
    d["ALLOWED_PAIRS"] = list(p["WHITELIST"])
    d["MAX_OPEN_POSITIONS"] = p["MAX_OPEN"]
    d["MAX_OPEN"] = d["MAX_SIMULTANEOUS_TRADES"] = p["MAX_OPEN"]
    d["MAX_ENTRIES_THIS_RUN"] = p["MAX_ENTRIES_THIS_RUN"]
    d["MIN_CONVICTION_SCORE"] = p["MIN_CONVICTION"]
    d["MIN_STRENGTH_GAP"] = p["MIN_GAP"]
    # DEPRECATED — use MIN_CONVICTION_SCORE
    d["THRESHOLD_SCORE"] = d["MIN_CONVICTION_SCORE"]
    d["MIN_CONVICTION_SCORE_ALT"] = d["MIN_CONVICTION_SCORE"]
    d["D_GATE_ENABLED"] = p["D_GATE_ENABLED"]
    d["D_GATE_SHADOW"] = p["D_GATE_SHADOW"]
    d["D_GATE_MIN_BUFFER_PCT"] = p["D_GATE_BUFFER_PCT"] / 100.0
    d["D_GATE_CONFIRM_BARS"] = int(str(p["D_GATE_CONFIRM"]).split("H", 1)[0])
    d |= _PROFILE_EXTRAS[pid]
    d["PERIODS_YEAR"] = _calc_periods_year(d["YF_INTERVAL"])
    # DEPRECATED — use MIN_SCORE_GAP (sync after _PROFILE_EXTRAS merge)
    d["TOP_PAIRS_MIN_GAP"] = d["MIN_SCORE_GAP"]
    # DEPRECATED — use canonical names (sync after _PROFILE_EXTRAS merge)
    d["MC_BULLISH_THRESHOLD_PCT"] = d["MC_BULLISH_THRESHOLD"]
    d["MC_CONFIDENCE"] = d["MC_BAND_PCT"] / 100.0  # align units
    # DEPRECATED — use SL_MIN_PIPS / SL_MIN_PIPS_JPY
    d["MIN_SL_PIPS"] = d["SL_MIN_PIPS"]
    d["SL_MIN_DISTANCE_PIPS"] = d["SL_MIN_PIPS"]
    d["OANDA_ACCOUNT_ID"] = _oanda_account_id(pid)
    ns = SimpleNamespace()
    ns.__dict__.update(d)
    return ns


# ─────────────────────────────────────────────
# ✅ CONFIG VALIDATION
# ─────────────────────────────────────────────

CONFIG_VALIDATION_ENABLED = True
CONFIG_TOLERANCE = 0.005


def validate_config(profile_id=None):
    if not CONFIG_VALIDATION_ENABLED:
        msg = "⚠️  Config validation — DISABLED"
        print(msg)
        return (True, msg)

    errors = []
    warns = []
    lines = []

    if profile_id is not None:
        pid = int(profile_id)
        cfg = build_profile_cfg(pid)
        prefix = f"[Profile{pid}] "
        lines.append(f"\n🔍 CONFIG VALIDATION — Profile{pid} ({cfg.NAME if hasattr(cfg,'NAME') else ''}) v6.8.4")
        weights = {
            "S": cfg.WEIGHT_STRENGTH,
            "R": cfg.WEIGHT_RSI,
            "A": cfg.WEIGHT_ADX,
            "X": cfg.WEIGHT_XGB,
            "M": cfg.WEIGHT_MC,
        }
        weight_sum = sum(weights.values())
        lines.append("─────────────────────────────────────")
        for k, v in weights.items():
            lines.append(f"   Weight {k}: {v:.4f}")
        lines.append(f"   ── SUM: {weight_sum:.4f}  (target: 1.0000)")
        if abs(weight_sum - 1.0) > CONFIG_TOLERANCE:
            errors.append(
                f"{prefix}Weight sum = {weight_sum:.4f}, expected 1.0 ± {CONFIG_TOLERANCE}"
            )
        elif abs(weight_sum - 1.0) > 0.0001:
            warns.append(f"{prefix}Weights sum = {weight_sum:.4f} (minor rounding)")
        for name, w in weights.items():
            if not (0.0 <= w <= 1.0):
                errors.append(f"{prefix}Weight {name} = {w:.4f} — out of range [0.0, 1.0], expected 0.0–1.0")
        min_conviction = cfg.MIN_CONVICTION_SCORE
        if not (0 <= min_conviction <= 100):
            errors.append(f"{prefix}MIN_CONVICTION_SCORE = {min_conviction} — out of range [0, 100], expected 0–100")
        min_gap = cfg.MIN_SCORE_GAP
        if not (0.0 <= min_gap <= 5.0):
            errors.append(f"{prefix}MIN_SCORE_GAP = {min_gap} — out of range [0.0, 5.0], expected 0.0–5.0")
        max_open = cfg.MAX_OPEN_POSITIONS
        if max_open < 1 or max_open > 20:
            warns.append(f"{prefix}MAX_OPEN_POSITIONS = {max_open} — unusual (suggest 1–8)")
        max_hold = cfg.MAX_HOLD_BARS
        if max_hold < 1 or max_hold > 500:
            errors.append(f"{prefix}MAX_HOLD_BARS = {max_hold} — out of range [1, 500], expected 1–500")
        trail_mult = cfg.TRAIL_ATR_MULT
        if trail_mult <= 0 or trail_mult > 10:
            errors.append(f"{prefix}TRAIL_ATR_MULT = {trail_mult} — out of range (0, 10], expected 0.1–10.0")
        if cfg.REMOVE_COOLDOWN is True:
            warns.append(f"{prefix}REMOVE_COOLDOWN = True — stop-out 后立刻重入，风险放大 (建议 False)")
        lookback = cfg.TRAIN_LOOKBACK_BARS
        if lookback > 2000:
            errors.append(f"{prefix}TRAIN_LOOKBACK_BARS = {lookback} — exceeds 2000, Yahoo Finance 60d 窗口无法覆盖，expected ≤ 2000")
        periods_year = cfg.PERIODS_YEAR
        expected_py = _calc_periods_year(cfg.YF_INTERVAL)
        if periods_year != expected_py:
            errors.append(f"{prefix}PERIODS_YEAR = {periods_year} — mismatch for YF_INTERVAL={cfg.YF_INTERVAL}, expected {expected_py}")
        strength_block = cfg.STRENGTH_SIGNAL_BLOCK_THRESHOLD
        if strength_block > 5.0:
            warns.append(f"{prefix}STRENGTH_SIGNAL_BLOCK_THRESHOLD = {strength_block} — 值过大基本关闭过滤 (建议 0.7–0.9)")
        if hasattr(cfg, "D_GATE_ENABLED") and cfg.D_GATE_ENABLED:
            if hasattr(cfg, "D_GATE_SHADOW") and cfg.D_GATE_SHADOW:
                warns.append(f"{prefix}D_GATE_SHADOW = True — 只打日志不拦单 (Shadow mode: logs only)")
    else:
        lines.append("\n🔍 CONFIG VALIDATION — GLOBAL (v6.8.4)")
        lines.append("   Profile-specific weights reported at bot startup.")
        weights = dict(WEIGHTS_BASE)
        weight_sum = sum(weights.values())
        lines.append("─────────────────────────────────────")
        for k, v in weights.items():
            lines.append(f"   Weight {k}: {v:.4f}")
        lines.append(f"   ── SUM: {weight_sum:.4f}  (target: 1.0000)")
        if abs(weight_sum - 1.0) > CONFIG_TOLERANCE:
            errors.append(
                f"GLOBAL Weight sum = {weight_sum:.4f}, expected 1.0 ± {CONFIG_TOLERANCE}"
            )
        elif abs(weight_sum - 1.0) > 0.0001:
            warns.append(f"Weights sum = {weight_sum:.4f} (minor rounding)")
        for name, w in weights.items():
            if not (0.0 <= w <= 1.0):
                errors.append(f"Weight {name} = {w:.4f} — out of range [0.0, 1.0]")
        if ADX_SCALE_FACTOR < 0.5 or ADX_SCALE_FACTOR > 5.0:
            warns.append(f"ADX_SCALE_FACTOR = {ADX_SCALE_FACTOR} — unusual")
        if REQUIRE_DIRECTION_CONSENSUS:
            if not (1 <= CONSENSUS_THRESHOLD <= 3):
                errors.append(f"CONSENSUS_THRESHOLD = {CONSENSUS_THRESHOLD} — must be 1–3")
        if not (0 <= THRESHOLD_SCORE <= 100):
            errors.append(f"THRESHOLD_SCORE = {THRESHOLD_SCORE} — must be 0–100")
        if not (0 <= MIN_CONVICTION_SCORE <= 100):
            errors.append(f"MIN_CONVICTION_SCORE = {MIN_CONVICTION_SCORE} — must be 0–100")
        if MAX_OPEN < 1 or MAX_OPEN > 20:
            warns.append(f"MAX_OPEN = {MAX_OPEN} — unusual (suggest 1–8)")

    lines.append("─────────────────────────────────────")
    for line in lines:
        print(line)
    if warns:
        for w in warns:
            print(f"⚠️  WARN: {w}")
    if errors:
        for e in errors:
            print(f"❌ ERROR: {e}")
        err_msg = f"{len(errors)} CONFIG ERROR(S) — Please fix before running!"
        print(f"\n❌ {err_msg}\n")
        return (False, err_msg + " | " + "; ".join(errors))
    ok_msg = "ALL CHECKS PASSED"
    if warns:
        ok_msg += f" — {len(warns)} warning(s)"
        print(f"✅ CHECKS PASSED — {len(warns)} warning(s)\n")
    else:
        print("✅ ALL CHECKS PASSED — Config OK\n")
    return (True, ok_msg)


if "CONFIG_VALIDATION_ENABLED" in globals() and CONFIG_VALIDATION_ENABLED:
    _all_ok = True
    _all_msgs = []
    print("\n" + "=" * 60)
    print("🚀 CONFIG BOOTSTRAP VALIDATION — All 4 Profiles")
    print("=" * 60)
    for _pid in [1, 2, 3, 4]:
        _ok, _msg = validate_config(_pid)
        if not _ok:
            _all_ok = False
            _all_msgs.append(f"Profile{_pid} FAILED: {_msg}")
    print("=" * 60)
    if _all_ok:
        print("✅ BOOTSTRAP: All 4 profiles validated successfully.")
    else:
        for _m in _all_msgs:
            print(f"❌ BOOTSTRAP FAIL: {_m}")
        print("⚠️  WARNING: Config validation errors detected. "
              "Calling code must check via validate_config(profile_id) before proceeding.")
    print("=" * 60 + "\n")