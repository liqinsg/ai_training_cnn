# tests/test_integration_hook.py — STAGE B INTEGRATION GUARD TESTS
# Validates §4.1.1 isolation rules: non-READY results are blocked from ML vote /
# Entry Authorization, and the hook preserves the frozen legacy C-2 signal.
#
# Note: the hook does NOT re-run the legacy strategy. `legacy_signal` is the
# value the frozen path already produced, so tests pass it in directly rather
# than mocking a (nonexistent) legacy `evaluate()` method.

import pytest
import pandas as pd

from ml.integration_hook import evaluate_prediction_guard, guarded_live_polling_hook
from ml.live_prediction_engine import (
    PredictionResult,
    PredictionStatus,
    PredictionReason,
)


# --- test doubles ---

class _StubLiveEngine:
    """Minimal LivePredictionEngine stand-in with an explicit call counter."""

    def __init__(self, result=None, error=None):
        self._result = result
        self._error = error
        self.calls = 0

    def predict_live(self, pair, timeframe, raw_candles):
        self.calls += 1
        if self._error is not None:
            raise self._error
        return self._result


@pytest.fixture
def candles():
    return pd.DataFrame({"close": [1.0500, 1.0520]})


# --- guard: blocking ---

def test_guard_blocks_uninterpretable():
    """UNINTERPRETABLE (valid inference, unverified CD) must be blocked."""
    res = PredictionResult(
        status=PredictionStatus.UNINTERPRETABLE,
        reason=PredictionReason.CLASS_DEFINITION_UNVERIFIED,
        pair="EUR_USD",
        timeframe="1H",
        raw_probability=0.73,
    )
    assert evaluate_prediction_guard(res) is False


@pytest.mark.parametrize(
    "status,reason",
    [
        (PredictionStatus.UNAVAILABLE, PredictionReason.MODEL_NOT_USABLE),
        (PredictionStatus.NOT_RUN, PredictionReason.INPUT_INSUFFICIENT),
        (PredictionStatus.INVALID, PredictionReason.FEATURE_CONTRACT_VIOLATION),
        (PredictionStatus.ERROR, PredictionReason.EXECUTION_ERROR),
    ],
)
def test_guard_blocks_every_non_ready_status(status, reason):
    """Only READY may pass; all other statuses are blocked (§1.5, §4.2)."""
    res = PredictionResult(
        status=status,
        reason=reason,
        pair="EUR_USD",
        timeframe="1H",
    )
    assert evaluate_prediction_guard(res) is False


# --- guard: allowance ---

def test_guard_allows_ready():
    """A READY result with a valid direction passes the guard."""
    res = PredictionResult(
        status=PredictionStatus.READY,
        reason=PredictionReason.NONE,
        pair="EUR_USD",
        timeframe="1H",
        p_up=0.85,
        p_down=0.15,
        direction="BUY",
        positive_class_label="UP",
    )
    assert evaluate_prediction_guard(res) is True


# --- hook: dual-track behaviour ---

def test_hook_preserves_legacy_signal_and_audits(candles):
    """UNINTERPRETABLE prediction is blocked; the legacy signal is returned."""
    live_engine = _StubLiveEngine(
        result=PredictionResult(
            status=PredictionStatus.UNINTERPRETABLE,
            reason=PredictionReason.CLASS_DEFINITION_UNVERIFIED,
            pair="EUR_USD",
            timeframe="1H",
            raw_probability=0.73,
        )
    )

    signal = guarded_live_polling_hook(
        pair="EUR_USD",
        timeframe="1H",
        raw_candles=candles,
        live_engine=live_engine,
        legacy_signal="BUY",
    )

    assert signal == "BUY"
    assert live_engine.calls == 1


def test_hook_isolates_live_engine_failure(candles):
    """A live-engine failure must not leak out; the legacy signal is returned."""
    live_engine = _StubLiveEngine(error=RuntimeError("inference backend down"))

    signal = guarded_live_polling_hook(
        pair="EUR_USD",
        timeframe="1H",
        raw_candles=candles,
        live_engine=live_engine,
        legacy_signal="SELL",
    )

    assert signal == "SELL"
    assert live_engine.calls == 1


def test_hook_returns_none_when_legacy_signal_absent(candles):
    """With no legacy signal supplied, the hook returns None (no fabricated vote)."""
    live_engine = _StubLiveEngine(
        result=PredictionResult(
            status=PredictionStatus.UNAVAILABLE,
            reason=PredictionReason.MODEL_NOT_USABLE,
            pair="EUR_USD",
            timeframe="1H",
        )
    )

    signal = guarded_live_polling_hook(
        pair="EUR_USD",
        timeframe="1H",
        raw_candles=candles,
        live_engine=live_engine,
    )

    assert signal is None
