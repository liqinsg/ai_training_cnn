# tests/test_features_parity.py — FEATURE CONTRACT PARITY TESTS (PHASE 3)
# Validates 100% numerical parity between training and inference feature pipelines.

import pytest
import numpy as np
import pandas as pd

from ml.features import FeatureContractEngine, SCHEMA_VERSION


@pytest.fixture
def synthetic_ohlcv_data():
    """Generates deterministic synthetic OHLCV candle data for parity testing."""
    np.random.seed(42)
    n_rows = 100
    base_price = 1.0800
    
    # Generate random walk price series
    returns = np.random.normal(loc=0.0001, scale=0.002, size=n_rows)
    close = base_price * np.cumprod(1 + returns)
    high = close * (1 + np.random.uniform(0.0005, 0.002, size=n_rows))
    low = close * (1 - np.random.uniform(0.0005, 0.002, size=n_rows))
    open_p = close * (1 + np.random.uniform(-0.001, 0.001, size=n_rows))
    volume = np.random.randint(1000, 50000, size=n_rows)

    df = pd.DataFrame({
        "open": open_p,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }, index=pd.date_range(start="2026-01-01", periods=n_rows, freq="1h"))
    
    return df


def test_training_inference_feature_numerical_parity(synthetic_ohlcv_data):
    """
    Core Parity Test: Verifies that two independent instances of FeatureContractEngine 
    produce identical feature values and column orders when given identical raw data.
    """
    # Simulate Offline Training Feature Engine
    train_engine = FeatureContractEngine()
    train_df = train_engine.build(synthetic_ohlcv_data.copy())
    train_features = train_engine.get_feature_columns(train_df)

    # Simulate Online Inference Feature Engine
    inference_engine = FeatureContractEngine()
    inference_df = inference_engine.build(synthetic_ohlcv_data.copy())
    inference_features = inference_engine.get_feature_columns(inference_df)

    # 1. Verify column names and deterministic ordering match 100%
    assert train_features == inference_features, "Feature column names or ordering drifted!"
    assert train_engine.schema_version == inference_engine.schema_version

    # 2. Verify exact numerical parity across all feature columns
    for col in train_features:
        try:
            pd.testing.assert_series_equal(
                train_df[col], inference_df[col], check_names=True
            )
        except AssertionError as exc:  # 保留列级诊断信息（obj_name 在新版 pandas 已移除）
            raise AssertionError(
                f"Feature '{col}' parity mismatch between training and inference: {exc}"
            ) from exc


def test_feature_contract_column_validation():
    """Verifies that missing critical price columns trigger immediate exceptions."""
    engine = FeatureContractEngine()
    # 行数需 >= 20 才能越过长度检查，进入列校验分支
    invalid_df = pd.DataFrame({"volume": list(range(30))})  # Missing open, high, low, close

    with pytest.raises(KeyError) as excinfo:
        engine.build(invalid_df)
    assert "Missing required price column" in str(excinfo.value)


def test_target_label_construction(synthetic_ohlcv_data):
    """Verifies authoritative target/label horizon calculations."""
    engine = FeatureContractEngine()
    df_feat = engine.build(synthetic_ohlcv_data)
    df_labeled = engine.build_target(df_feat, horizon=5, threshold=0.001)

    assert "target" in df_labeled.columns
    # Check that target values are strictly binary (0 or 1)
    unique_targets = df_labeled["target"].unique()
    assert set(unique_targets).issubset({0, 1})
