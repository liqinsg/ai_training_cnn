"""
attribution_profiles.py — 4 independent attribution profiles
Each profile = complete config: weights + thresholds + neutral_band
All independent — no shared state.
(ai-sprint) qili@NBK202500000057 ~/projects/ai_training_cnn/attribution_v2 (v2026)$ python -m pytest tests/test_profiles.py -v
=================================================== test session starts ====================================================
platform linux -- Python 3.12.13, pytest-9.1.1, pluggy-1.6.0 -- /home/qili/miniconda3/envs/ai-sprint/bin/python
cachedir: .pytest_cache
rootdir: /home/qili/projects/ai_training_cnn/attribution_v2
plugins: asyncio-1.4.0, anyio-4.12.1
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 19 items

tests/test_profiles.py::test_four_profiles_defined PASSED                                                            [  5%]
tests/test_profiles.py::test_weights_sum_to_one[PF-A] PASSED                                                         [ 10%]
tests/test_profiles.py::test_weights_sum_to_one[PF-B] PASSED                                                         [ 15%]
tests/test_profiles.py::test_weights_sum_to_one[PF-C] PASSED                                                         [ 21%]
tests/test_profiles.py::test_weights_sum_to_one[PF-D] PASSED                                                         [ 26%]
tests/test_profiles.py::test_pfa_structure PASSED                                                                    [ 31%]
tests/test_profiles.py::test_pfb_balance PASSED                                                                      [ 36%]
tests/test_profiles.py::test_pfc_data_dominant PASSED                                                                [ 42%]
tests/test_profiles.py::test_pfd_structure_stricter PASSED                                                           [ 47%]
tests/test_profiles.py::test_profile_isolation PASSED                                                                [ 52%]
tests/test_profiles.py::test_threshold_order[PF-A] PASSED                                                            [ 57%]
tests/test_profiles.py::test_threshold_order[PF-B] PASSED                                                            [ 63%]
tests/test_profiles.py::test_threshold_order[PF-C] PASSED                                                            [ 68%]
tests/test_profiles.py::test_threshold_order[PF-D] PASSED                                                            [ 73%]
tests/test_profiles.py::test_validate_bad_configs PASSED                                                             [ 78%]
tests/test_profiles.py::test_all_valid[PF-A] PASSED                                                                  [ 84%]
tests/test_profiles.py::test_all_valid[PF-B] PASSED                                                                  [ 89%]
tests/test_profiles.py::test_all_valid[PF-C] PASSED                                                                  [ 94%]
tests/test_profiles.py::test_all_valid[PF-D] PASSED                                                                  [100%]
==================================================== 19 passed in 0.23s ====================================================
"""

import copy
from typing import Dict, Any, List

# ══════════════════════════════════════════════════════════════
# 4 PROFILE DEFINITIONS — PF-A through PF-D
# ══════════════════════════════════════════════════════════════

PROFILES: Dict[str, Dict[str, Any]] = {
    "PF-A": {
        "name": "Trend-Light",
        "description": "Trend + Price Structure dominant",
        "weights": {
            "trend": 0.40,
            "location": 0.30,
            "xgb": 0.15,
            "mc": 0.15
        },
        "thresholds": {
            "pass": 0.70,
            "watch": 0.50
        },
        "neutral_band": 0.10
    },

    "PF-B": {
        "name": "Balance-Equal",
        "description": "All four factors equally weighted",
        "weights": {
            "trend": 0.25,
            "location": 0.25,
            "xgb": 0.25,
            "mc": 0.25
        },
        "thresholds": {
            "pass": 0.70,
            "watch": 0.50
        },
        "neutral_band": 0.10
    },

    "PF-C": {
        "name": "Data-Driven",
        "description": "XGBoost + Monte Carlo dominant, easier thresholds",
        "weights": {
            "trend": 0.15,
            "location": 0.15,
            "xgb": 0.35,
            "mc": 0.35
        },
        "thresholds": {
            "pass": 0.65,
            "watch": 0.45
        },
        "neutral_band": 0.10
    },

    "PF-D": {
        "name": "Structure-Focus",
        "description": "Trend + Support/Resistance dominant, stricter thresholds",
        "weights": {
            "trend": 0.35,
            "location": 0.35,
            "xgb": 0.15,
            "mc": 0.15
        },
        "thresholds": {
            "pass": 0.75,
            "watch": 0.55
        },
        "neutral_band": 0.08
    }
}


# ══════════════════════════════════════════════════════════════
# API Functions
# ══════════════════════════════════════════════════════════════

def get_profile(profile_id: str) -> Dict[str, Any]:
    """Return a deep copy so caller cannot mutate global config."""
    if profile_id not in PROFILES:
        raise KeyError(f"Unknown profile: {profile_id}. Available: {list(PROFILES.keys())}")
    return copy.deepcopy(PROFILES[profile_id])


def list_profiles() -> List[str]:
    """Return all available profile IDs."""
    return list(PROFILES.keys())


def validate_profile(profile: Dict[str, Any]) -> bool:
    """
    Validate profile structure & integrity:
    - weights sum ≈ 1.0
    - pass > watch
    - all required keys present
    """
    required_keys = ["name", "description", "weights", "thresholds", "neutral_band"]
    for k in required_keys:
        if k not in profile:
            return False

    w = profile["weights"]
    if not set(w.keys()) == {"trend", "location", "xgb", "mc"}:
        return False
    if abs(sum(w.values()) - 1.0) > 1e-6:
        return False

    t = profile["thresholds"]
    if t["pass"] <= t["watch"]:
        return False

    if not isinstance(profile["neutral_band"], (int, float)) or profile["neutral_band"] <= 0:
        return False

    return True