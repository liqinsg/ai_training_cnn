"""
test_profiles.py — Validation for 4 independent profile configs
"""
import pytest
from profiles.attribution_profiles import (
    PROFILES,
    get_profile,
    list_profiles,
    validate_profile
)


# ════════════════════════════════════════════════
# TEST 1: All 4 profiles exist
# ════════════════════════════════════════════════
def test_four_profiles_defined():
    ids = list_profiles()
    assert set(ids) == {"PF-A", "PF-B", "PF-C", "PF-D"}
    assert len(PROFILES) == 4


# ════════════════════════════════════════════════
# TEST 2: Weights sum to 1.0 for every profile
# ════════════════════════════════════════════════
@pytest.mark.parametrize("pid", ["PF-A", "PF-B", "PF-C", "PF-D"])
def test_weights_sum_to_one(pid):
    p = get_profile(pid)
    total = sum(p["weights"].values())
    assert abs(total - 1.0) < 1e-6, f"{pid} weights sum = {total}, expected 1.0"


# ════════════════════════════════════════════════
# TEST 3: Profile A — Trend-Light
# ════════════════════════════════════════════════
def test_pfa_structure():
    p = get_profile("PF-A")
    assert p["weights"]["trend"] == 0.40
    assert p["weights"]["location"] == 0.30
    assert p["weights"]["xgb"] == 0.15
    assert p["weights"]["mc"] == 0.15
    assert p["thresholds"]["pass"] == 0.70
    assert p["thresholds"]["watch"] == 0.50
    assert p["neutral_band"] == 0.10


# ════════════════════════════════════════════════
# TEST 4: Profile B — Equal balance
# ════════════════════════════════════════════════
def test_pfb_balance():
    p = get_profile("PF-B")
    assert all(v == 0.25 for v in p["weights"].values())


# ════════════════════════════════════════════════
# TEST 5: Profile C — Data dominant
# ════════════════════════════════════════════════
def test_pfc_data_dominant():
    p = get_profile("PF-C")
    ml_total = p["weights"]["xgb"] + p["weights"]["mc"]
    assert ml_total == 0.70
    assert p["thresholds"]["pass"] == 0.65   # Easier to pass
    assert p["thresholds"]["watch"] == 0.45


# ════════════════════════════════════════════════
# TEST 6: Profile D — Structure focus
# ════════════════════════════════════════════════
def test_pfd_structure_stricter():
    p = get_profile("PF-D")
    structure_total = p["weights"]["trend"] + p["weights"]["location"]
    assert structure_total == 0.70
    assert p["neutral_band"] == 0.08  # Tighter band
    assert p["thresholds"]["pass"] == 0.75  # Hardest to pass
    assert p["thresholds"]["watch"] == 0.55


# ════════════════════════════════════════════════
# TEST 7: Deep copy — no cross-contamination
# ════════════════════════════════════════════════
def test_profile_isolation():
    a = get_profile("PF-A")
    b = get_profile("PF-B")
    original_trend = a["weights"]["trend"]

    # Mutate returned copy
    a["weights"]["trend"] = 999

    # Global & other profile unchanged
    fresh = get_profile("PF-A")
    assert fresh["weights"]["trend"] == original_trend
    assert get_profile("PF-B")["weights"]["trend"] == b["weights"]["trend"]


# ════════════════════════════════════════════════
# TEST 8: Threshold ordering
# ════════════════════════════════════════════════
@pytest.mark.parametrize("pid", ["PF-A", "PF-B", "PF-C", "PF-D"])
def test_threshold_order(pid):
    t = get_profile(pid)["thresholds"]
    assert t["pass"] > t["watch"], f"{pid}: pass must be > watch"


# ════════════════════════════════════════════════
# TEST 9: Validate function catches bad config
# ════════════════════════════════════════════════
def test_validate_bad_configs():
    assert validate_profile({}) is False

    bad_sum = get_profile("PF-A")
    bad_sum["weights"]["trend"] = 0.99
    assert validate_profile(bad_sum) is False

    bad_threshold = get_profile("PF-A")
    bad_threshold["thresholds"]["pass"] = 0.40
    bad_threshold["thresholds"]["watch"] = 0.50
    assert validate_profile(bad_threshold) is False


# ════════════════════════════════════════════════
# TEST 10: Valid profiles all pass validation
# ════════════════════════════════════════════════
@pytest.mark.parametrize("pid", ["PF-A", "PF-B", "PF-C", "PF-D"])
def test_all_valid(pid):
    assert validate_profile(get_profile(pid)) is True