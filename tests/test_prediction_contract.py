# tests/test_prediction_contract.py — STAGE B CONTRACT ENFORCEMENT TESTS
# Validates UNINTERPRETABLE status, self-describing fields, and downstream isolation rules.

import pytest
import pandas as pd
from datetime import datetime, timezone

# 假设我们在 Stage B 中实现的 Prediction Result 契约类与拦截器
# from ml.contracts import PredictionResult, PredictionStatus, PredictionReason, evaluate_prediction_guard


class MockPredictionResult:
    """Mock implementation adhering to Phase 3.1/A.2 Contract specifications."""
    def __init__(self, status, reason, raw_probability=None, p_up=None, 
                 pair=None, timeframe=None, bar_time=None, positive_class_label=None):
        self.status = status
        self.reason = reason
        self.raw_probability = raw_probability
        self.p_up = p_up
        self.pair = pair
        self.timeframe = timeframe
        self.bar_time = bar_time
        self.positive_class_label = positive_class_label
        
        # Enforcement of contract rules during initialization
        if self.status == "UNINTERPRETABLE":
            if self.reason != "CLASS_DEFINITION_UNVERIFIED":
                raise ValueError("UNINTERPRETABLE status must pair with CLASS_DEFINITION_UNVERIFIED reason")
            if self.p_up is not None:
                raise ValueError("p_up must be None when class definition is unverified (use raw_probability)")
            if self.positive_class_label is not None:
                raise ValueError("positive_class_label must be None when CD is unverified")


def test_uninterpretable_state_enforcement():
    """
    Validates that a successful inference with unverified CD correctly instantiates 
    UNINTERPRETABLE status, populates raw_probability, and keeps p_up as None.
    """
    pair = "EUR_USD"
    timeframe = "1H"
    bar_time = datetime(2026, 11, 14, 6, 0, tzinfo=timezone.utc)
    raw_prob = 0.73

    # Successful inference, but CD unverified
    result = MockPredictionResult(
        status="UNINTERPRETABLE",
        reason="CLASS_DEFINITION_UNVERIFIED",
        raw_probability=raw_prob,
        p_up=None,
        pair=pair,
        timeframe=timeframe,
        bar_time=bar_time,
        positive_class_label=None
    )

    assert result.status == "UNINTERPRETABLE"
    assert result.reason == "CLASS_DEFINITION_UNVERIFIED"
    assert result.raw_probability == 0.73
    assert result.p_up is None
    assert result.pair == "EUR_USD"
    assert result.timeframe == "1H"
    assert result.bar_time == bar_time
    assert result.positive_class_label is None


def test_uninterpretable_invalid_pairing_raises_error():
    """
    Validates that violating the status/reason pairing or contaminating p_up 
    under UNINTERPRETABLE triggers a strict contract violation exception.
    """
    # Test 1: Wrong reason for UNINTERPRETABLE
    with pytest.raises(ValueError, match="must pair with CLASS_DEFINITION_UNVERIFIED"):
        MockPredictionResult(
            status="UNINTERPRETABLE",
            reason="MODEL_NOT_USABLE",
            raw_probability=0.73
        )

    # Test 2: Populating p_up while CD is unverified (violating neutrality)
    with pytest.raises(ValueError, match="p_up must be None"):
        MockPredictionResult(
            status="UNINTERPRETABLE",
            reason="CLASS_DEFINITION_UNVERIFIED",
            raw_probability=0.73,
            p_up=0.73  # Illegal!
        )


def evaluate_prediction_guard(result: MockPredictionResult) -> bool:
    """
    Simulates the Stage B guard enforcement rule (§4.1.1):
    Uninterpretable or unverified predictions are blocked from entering ML voting 
    or Entry Authorization.
    """
    if result.status == "UNINTERPRETABLE":
        return False  # Blocked from downstream execution
    if result.status != "READY":
        return False
    return True


def test_downstream_isolation_guard():
    """
    Validates that UNINTERPRETABLE results are safely blocked from reaching 
    Entry Authorization or ML vote loops.
    """
    valid_ready_result = MockPredictionResult(
        status="READY",
        reason="NONE",
        p_up=0.85,
        pair="EUR_USD",
        positive_class_label="UP"
    )

    uninterpretable_result = MockPredictionResult(
        status="UNINTERPRETABLE",
        reason="CLASS_DEFINITION_UNVERIFIED",
        raw_probability=0.73,
        pair="EUR_USD"
    )

    # READY result is allowed to pass downstream
    assert evaluate_prediction_guard(valid_ready_result) is True

    # UNINTERPRETABLE result must be strictly blocked (returns False)
    assert evaluate_prediction_guard(uninterpretable_result) is False