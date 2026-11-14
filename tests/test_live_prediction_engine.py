# tests/test_live_prediction_engine.py — STAGE B LIVE PREDICTION ENGINE TESTS
# Validates state machine branches: READY, UNINTERPRETABLE, INVALID, ERROR, UNAVAILABLE.

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timezone

from ml.live_prediction_engine import (
    LivePredictionEngine,
    PredictionStatus,
    PredictionReason,
    PredictionResult
)


# --- Mocks & Fixtures ---

class MockModelWrapper:
    def __init__(self, n_features=3, return_invalid_prob=False, raise_exception=False):
        self.feature_names = [f"feat_{i}" for i in range(n_features)]
        self.model = MockSklearnModel(return_invalid_prob, raise_exception)
        self.scaler = MockSklearnScaler()
        self.is_loaded = True
        self.positive_class_label = "UP"


class MockSklearnModel:
    def __init__(self, return_invalid_prob=False, raise_exception=False):
        self.return_invalid_prob = return_invalid_prob
        self.raise_exception = raise_exception

    def predict_proba(self, X):
        if self.raise_exception:
            raise RuntimeError("Model inference hardware failure")
        if self.return_invalid_prob:
            return np.array([[1.5, -0.5]]) # Invalid probability out of [0, 1]
        return np.array([[0.27, 0.73]]) # p_down=0.27, p_up=0.73


class MockSklearnScaler:
    def transform(self, X):
        return X


class MockFeatureEngine:
    def __init__(self, inject_nan=False, raise_error=False):
        self.inject_nan = inject_nan
        self.raise_error = raise_error

    def build(self, df):
        if self.raise_error:
            raise ValueError("Feature calculation core exception")
        for col in ["open", "high", "low", "close"]:
            if col not in df.columns:
                df[col] = 100.0
        df["feat_0"] = 1.0
        df["feat_1"] = 2.0
        if self.inject_nan:
            df["feat_2"] = np.nan
        else:
            df["feat_2"] = 3.0
        return df


@pytest.fixture
def valid_ohlcv_data():
    """Generates 25 rows of synthetic candle data (meets min 20 bars requirement)."""
    return pd.DataFrame({
        "open": np.linspace(100, 105, 25),
        "high": np.linspace(101, 106, 25),
        "low": np.linspace(99, 104, 25),
        "close": np.linspace(100.5, 105.5, 25),
    }, index=pd.date_range(start="2026-01-01", periods=25, freq="1h"))


# --- Test Cases ---

def test_engine_uninterpretable_default(valid_ohlcv_data):
    """
    Branch 1: UNINTERPRETABLE
    Inference succeeds and probability is valid (0.73), but Class Definition (CD) 
    is unverified by default. Must yield UNINTERPRETABLE + raw_probability with p_up=None.
    """
    engine = LivePredictionEngine(
        model_wrapper=MockModelWrapper(),
        feature_engine=MockFeatureEngine(),
        config={"class_definition_verified": False}
    )

    result = engine.predict_live("EUR_USD", "1H", valid_ohlcv_data)

    assert result.status == PredictionStatus.UNINTERPRETABLE
    assert result.reason == PredictionReason.CLASS_DEFINITION_UNVERIFIED
    assert result.raw_probability == 0.73
    assert result.p_up is None
    assert result.p_down is None
    assert result.direction is None


def test_engine_ready_when_cd_verified(valid_ohlcv_data):
    """
    Branch 2: READY
    When class_definition_verified=True, successful inference yields READY status,
    populates p_up, p_down, and direction.
    """
    engine = LivePredictionEngine(
        model_wrapper=MockModelWrapper(),
        feature_engine=MockFeatureEngine(),
        config={"class_definition_verified": True}
    )

    result = engine.predict_live("EUR_USD", "1H", valid_ohlcv_data)

    assert result.status == PredictionStatus.READY
    assert result.reason == PredictionReason.NONE
    assert result.p_up == 0.73
    assert result.p_down == 0.27
    assert result.direction == "BUY"  # 0.73 > 0.5
    assert result.positive_class_label == "UP"


def test_engine_invalid_feature_contract(valid_ohlcv_data):
    """
    Branch 3: INVALID (Feature Contract Violation)
    If engineered features contain NaN or Inf, state machine catches it 
    and returns INVALID / FEATURE_CONTRACT_VIOLATION.
    """
    engine = LivePredictionEngine(
        model_wrapper=MockModelWrapper(),
        feature_engine=MockFeatureEngine(inject_nan=True),
        config={"class_definition_verified": False}
    )

    result = engine.predict_live("EUR_USD", "1H", valid_ohlcv_data)

    assert result.status == PredictionStatus.INVALID
    assert result.reason == PredictionReason.FEATURE_CONTRACT_VIOLATION


def test_engine_error_branch(valid_ohlcv_data):
    """
    Branch 4: ERROR
    If an unexpected exception occurs inside feature building or prediction,
    it must be caught gracefully and return ERROR / EXECUTION_ERROR.
    """
    engine = LivePredictionEngine(
        model_wrapper=MockModelWrapper(),
        feature_engine=MockFeatureEngine(raise_error=True),
        config={"class_definition_verified": False}
    )

    result = engine.predict_live("EUR_USD", "1H", valid_ohlcv_data)

    assert result.status == PredictionStatus.ERROR
    assert result.reason == PredictionReason.EXECUTION_ERROR
    assert "exception" in result.diagnostics


def test_engine_unavailable_model(valid_ohlcv_data):
    """
    Branch 5: UNAVAILABLE
    If the model wrapper is missing or unloaded, return UNAVAILABLE / MODEL_NOT_USABLE.
    """
    engine = LivePredictionEngine(
        model_wrapper=None,
        feature_engine=MockFeatureEngine(),
        config={}
    )

    result = engine.predict_live("EUR_USD", "1H", valid_ohlcv_data)

    assert result.status == PredictionStatus.UNAVAILABLE
    assert result.reason == PredictionReason.MODEL_NOT_USABLE