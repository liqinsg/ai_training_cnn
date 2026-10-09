"""
test_core.py — Unit tests for attribution_core.py
All tests MUST pass before proceeding.
(ai-sprint) qili@NBK202500000057 ~/projects/ai_training_cnn/attribution_v2 (v2026)$ python -m pytest tests/test_core.py -v
=================================================== test session starts ====================================================
platform linux -- Python 3.12.13, pytest-9.1.1, pluggy-1.6.0 -- /home/qili/miniconda3/envs/ai-sprint/bin/python
cachedir: .pytest_cache
rootdir: /home/qili/projects/ai_training_cnn/attribution_v2
plugins: asyncio-1.4.0, anyio-4.12.1
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 10 items

tests/test_core.py::test_buy_sign_symmetry PASSED                                                                    [ 10%]
tests/test_core.py::test_sell_sign_symmetry PASSED                                                                   [ 20%]
tests/test_core.py::test_abs_trap_negative_rejects PASSED                                                            [ 30%]
tests/test_core.py::test_threshold_boundaries PASSED                                                                 [ 40%]
tests/test_core.py::test_missing_factor_renormalizes PASSED                                                          [ 50%]
tests/test_core.py::test_missing_not_converted_to_zero PASSED                                                        [ 60%]
tests/test_core.py::test_counterfactual_delta_correct PASSED                                                         [ 70%]
tests/test_core.py::test_counterfactual_flip_detected PASSED                                                         [ 80%]
tests/test_core.py::test_neutral_band_edge PASSED                                                                    [ 90%]
tests/test_core.py::test_consensus_counts PASSED                                                                     [100%]
==================================================== 10 passed in 0.02s ====================================================
"""

import pytest
from attribution_core import (
    candidate_relative,
    classify_score,
    weighted_calc,
    decision_from_score,
    counterfactuals_full,
    calc_consensus,
    decision_sensitive_factors,
)


# ════════════════════════════════════════════════
# TEST 1: Sign Symmetry — BUY
# ════════════════════════════════════════════════
def test_buy_sign_symmetry():
    """All factors +1 → relative +1 for BUY."""
    assert candidate_relative(+1.0, "BUY") == +1.0
    assert candidate_relative(+0.82, "BUY") == +0.82
    assert candidate_relative(-0.50, "BUY") == -0.50


# ════════════════════════════════════════════════
# TEST 2: Sign Symmetry — SELL
# ════════════════════════════════════════════════
def test_sell_sign_symmetry():
    """Raw -0.82 (bearish) → relative +0.82 for SELL candidate."""
    assert candidate_relative(-1.0, "SELL") == +1.0
    assert candidate_relative(-0.82, "SELL") == pytest.approx(+0.82)
    assert candidate_relative(+0.50, "SELL") == -0.50


# ════════════════════════════════════════════════
# TEST 3: ABS() Trap — CRITICAL
# ════════════════════════════════════════════════
def test_abs_trap_negative_rejects():
    """Negative score MUST reject — never abs() to pass."""
    thresholds = {"pass": 0.70, "watch": 0.50}
    assert decision_from_score(-0.72, thresholds) == "REJECT"
    assert decision_from_score(-0.55, thresholds) == "REJECT"
    assert decision_from_score(-0.01, thresholds) == "REJECT"


# ════════════════════════════════════════════════
# TEST 4: Threshold Boundaries
# ════════════════════════════════════════════════
def test_threshold_boundaries():
    """Exact boundary values."""
    t = {"pass": 0.70, "watch": 0.50}
    assert decision_from_score(0.70, t) == "PASS"
    assert decision_from_score(0.699999, t) == "WATCH"
    assert decision_from_score(0.50, t) == "WATCH"
    assert decision_from_score(0.499999, t) == "REJECT"
    assert decision_from_score(0.00, t) == "REJECT"
    assert decision_from_score(-0.50, t) == "REJECT"


# ════════════════════════════════════════════════
# TEST 5: Missing Factor → Renormalize
# ════════════════════════════════════════════════
def test_missing_factor_renormalizes():
    """Missing XGB → weights redistribute among others."""
    factors = {"trend": 1.0, "location": 1.0, "xgb": None, "mc": 1.0}
    weights = {"trend": 0.34, "location": 0.33, "xgb": 0.16, "mc": 0.17}

    score, contribs, missing, degraded = weighted_calc(factors, weights)

    assert degraded is True
    assert "xgb" in missing
    assert "xgb" not in contribs
    # Remaining weights sum to 1.0
    assert sum(contribs.values()) == pytest.approx(score)
    assert score == pytest.approx(1.0)


# ════════════════════════════════════════════════
# TEST 6: Missing ≠ Neutral — None stays None
# ════════════════════════════════════════════════
def test_missing_not_converted_to_zero():
    """Missing factor must NOT silently become 0/neutral."""
    factors = {"trend": None, "location": 1.0, "xgb": None, "mc": 1.0}
    weights = {"trend": 0.25, "location": 0.25, "xgb": 0.25, "mc": 0.25}

    _, _, missing, degraded = weighted_calc(factors, weights)

    assert degraded is True
    assert "trend" in missing
    assert "xgb" in missing
    assert len(missing) == 2


# ════════════════════════════════════════════════
# TEST 7: Counterfactual Delta
# ════════════════════════════════════════════════
def test_counterfactual_delta_correct():
    """delta = cf_score - full_score exactly."""
    factors = {"trend": 1.0, "location": 0.0, "xgb": 0.0, "mc": 0.0}
    weights = {"trend": 0.40, "location": 0.30, "xgb": 0.15, "mc": 0.15}
    t = {"pass": 0.70, "watch": 0.50}

    cfs = counterfactuals_full(factors, weights, t)
    full = cfs["FULL"]["rel_score"]
    no_trend = cfs["NO_TREND"]["rel_score"]

    assert cfs["NO_TREND"]["delta"] == pytest.approx(no_trend - full)


# ════════════════════════════════════════════════
# TEST 8: Counterfactual Flip Detection
# ════════════════════════════════════════════════
def test_counterfactual_flip_detected():
    """flipped = cf_action != full_action."""
    # Trend alone pushes just over threshold
    factors = {"trend": 1.0, "location": 0.0, "xgb": 0.0, "mc": 0.0}
    weights = {"trend": 0.71, "location": 0.10, "xgb": 0.09, "mc": 0.10}
    t = {"pass": 0.70, "watch": 0.50}

    cfs = counterfactuals_full(factors, weights, t)

    assert cfs["FULL"]["action"] == "PASS"
    assert cfs["NO_TREND"]["action"] == "REJECT"
    assert cfs["NO_TREND"]["flipped"] is True
    assert cfs["NO_LOCATION"]["flipped"] is False


# ════════════════════════════════════════════════
# TEST 9: Neutral Band Classification
# ════════════════════════════════════════════════
def test_neutral_band_edge():
    assert classify_score(0.099) == "NEUTRAL"
    assert classify_score(0.100) == "SUPPORT"
    assert classify_score(-0.099) == "NEUTRAL"
    assert classify_score(-0.100) == "OPPOSE"
    # Custom band
    assert classify_score(0.085, neutral_band=0.08) == "SUPPORT"


# ════════════════════════════════════════════════
# TEST 10: Consensus Counts
# ════════════════════════════════════════════════
def test_consensus_counts():
    factors = {"a": 1.0, "b": 0.5, "c": 0.0, "d": -0.5, "e": None}
    c = calc_consensus(factors, neutral_band=0.10)
    assert c["SUPPORT"] == 2
    assert c["NEUTRAL"] == 1
    assert c["OPPOSE"] == 1
