"""
PHASE 1-C — offline inference-consistency tests for the v685 ML path.

Scope: StrategyEngine._predict() must be byte-for-byte the same pre-processing
path as ModelWrapper.predict_proba() — same fitted scaler instance, same feature
order (.features.json), same P(UP) class index — and must fail loudly instead of
inventing a prediction when the contract is broken.

No network, no OANDA, no orders, no training/saving of repository artifacts.
Everything below is a synthetic in-memory model.

Run:  python -m pytest tests/test_inference_consistency_v685.py -q
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from sklearn.preprocessing import StandardScaler

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from data_pipeline import (  # noqa: E402
    FeatureConfig,
    InferenceFeatureError,
    ModelWrapper,
    ScalerMissingError,
    positive_class_index,
    predict_p_up,
)

from fx_trade_bot_ml import ensure_model  # noqa: E402
from strategy_decision import StrategyConfig, StrategyEngine  # noqa: E402

FEATURES = ["ret_1h", "ret_3h", "atr_pct", "rsi", "adx", "MACD_12_26_9"]


@pytest.fixture(scope="module")
def fitted():
    """A tiny in-memory XGB model + the scaler it was actually trained with."""
    xgb = pytest.importorskip("xgboost")
    rng = np.random.default_rng(7)
    X = rng.normal(0.0, 1.0, size=(240, len(FEATURES)))
    y = (
        1.2 * X[:, 0] - 0.7 * X[:, 2] + X[:, 4] + rng.normal(0, 0.5, len(X)) > 0
    ).astype(int)

    scaler = StandardScaler().fit(X)
    model = xgb.XGBClassifier(
        n_estimators=12,
        max_depth=2,
        learning_rate=0.2,
        random_state=0,
        n_jobs=1,
    )
    model.fit(scaler.transform(X), y)

    frame = pd.DataFrame(X, columns=FEATURES)
    frame["Close"] = 1.1  # non-feature column, as in the bot's feature frame
    return SimpleNamespace(model=model, scaler=scaler, frame=frame)


def make_wrapper(fitted, feature_names=None):
    """ModelWrapper wired by hand — never calls load()/save()."""
    wrapper = ModelWrapper(
        FeatureConfig(), model_path=Path("/nonexistent/trade_model_xgb")
    )
    wrapper.model = fitted.model
    wrapper.scaler = fitted.scaler
    wrapper.feature_names = list(feature_names or FEATURES)
    return wrapper


def make_engine(fitted, scaler="default"):
    return StrategyEngine(
        StrategyConfig(),
        model=fitted.model,
        feature_list=list(FEATURES),
        scaler=fitted.scaler if scaler == "default" else scaler,
    )


# ─── 1. Same input → identical probability ───────────────────────────────────


def test_engine_matches_wrapper_exactly(fitted):
    wrapper = make_wrapper(fitted)
    engine = make_engine(fitted)
    row_df = fitted.frame.iloc[[10]]
    row_series = fitted.frame.iloc[10]

    expected = wrapper.predict_proba(row_df)[0, 1]
    got = engine._predict(row_series)

    print(f"   wrapper={expected:.12f} engine={got:.12f} diff={got - expected:.3e}")
    assert got == pytest.approx(expected, abs=1e-12)


def test_mixed_dtype_series_row_matches_dataframe(fitted):
    """`df.iloc[-1]` on a real feature frame is an *object* Series.

    The production frame carries int columns (hour, is_ny) next to float
    features, so a row Series has dtype object.  That must still be accepted
    and must produce the identical probability as the DataFrame path.
    """
    frame = fitted.frame.copy()
    frame["hour"] = 12  # int column, as produced by FeatureEngine
    frame["is_ny"] = True  # bool column
    row = frame.iloc[10]
    assert row.dtype == object, "precondition: mixed dtypes give an object Series"

    wrapper = make_wrapper(fitted)
    engine = make_engine(fitted)
    expected = wrapper.predict_proba(frame.iloc[[10]])[0, 1]

    print(f"   wrapper={expected:.12f} engine={engine._predict(row):.12f}")
    assert engine._predict(row) == pytest.approx(expected, abs=1e-12)


def test_feature_order_follows_features_json_not_dataframe(fitted):
    wrapper = make_wrapper(fitted)
    engine = make_engine(fitted)
    reference = engine._predict(fitted.frame.iloc[10])

    shuffled = fitted.frame[list(reversed(FEATURES)) + ["Close"]]
    assert engine._predict(shuffled.iloc[10]) == pytest.approx(reference, abs=1e-12)
    assert wrapper.predict_proba(shuffled.iloc[[10]])[0, 1] == pytest.approx(
        reference, abs=1e-12
    )


def test_predict_p_up_accepts_series_dataframe_and_array(fitted):
    wrapper = make_wrapper(fitted)
    engine = make_engine(fitted)
    row = fitted.frame.iloc[10]

    from_series = predict_p_up(fitted.model, fitted.scaler, FEATURES, row)[0]
    from_frame = predict_p_up(
        fitted.model, fitted.scaler, FEATURES, fitted.frame.iloc[[10]]
    )[0]
    from_array = predict_p_up(
        fitted.model, fitted.scaler, FEATURES, row[FEATURES].to_numpy(dtype=float)
    )[0]

    assert engine._predict(row) == pytest.approx(from_series, abs=1e-12)
    assert from_frame == pytest.approx(from_series, abs=1e-12)
    assert from_array == pytest.approx(from_series, abs=1e-12)
    assert wrapper.predict_proba(fitted.frame.iloc[[10]])[0, 1] == pytest.approx(
        from_series, abs=1e-12
    )


# ─── 2. Probability range ────────────────────────────────────────────────────


def test_probability_always_in_unit_interval(fitted):
    engine = make_engine(fitted)
    values = [engine._predict(fitted.frame.iloc[i]) for i in range(20)]
    assert all(0.0 <= v <= 1.0 for v in values), values
    assert len(set(values)) > 1, "model should not return a constant probability"
    print(f"   min={min(values):.6f} max={max(values):.6f}")


# ─── 3. p_up is the positive-class column ────────────────────────────────────


def test_p_up_is_positive_class_probability(fitted):
    classes = list(fitted.model.classes_)
    assert classes == [0, 1]
    assert positive_class_index(fitted.model, 2) == 1


def test_positive_class_index_follows_classes_order():
    class ReversedClassesModel:
        classes_ = np.array([1, 0])

        def predict_proba(self, X):
            return np.tile(np.array([[0.70, 0.30]]), (len(X), 1))

    X = np.zeros((1, len(FEATURES)))
    got = predict_p_up(
        ReversedClassesModel(), StandardScaler().fit(X), FEATURES, X
    )[0]
    assert got == pytest.approx(0.70), "P(UP) must follow classes_, not column 1"


# ─── 4. Broken contract → clear error, never a fake prediction ──────────────


def test_missing_scaler_raises(fitted):
    engine = make_engine(fitted, scaler=None)
    with pytest.raises(ScalerMissingError, match="no scaler"):
        engine._predict(fitted.frame.iloc[10])


def test_unfitted_scaler_raises(fitted):
    wrapper = make_wrapper(fitted)
    wrapper.scaler = StandardScaler()  # not fitted
    with pytest.raises(ScalerMissingError, match="not fitted"):
        wrapper.predict_proba(fitted.frame.iloc[[10]])


def test_feature_scaler_dimension_mismatch_raises(fitted):
    engine = StrategyEngine(
        StrategyConfig(),
        model=fitted.model,
        feature_list=FEATURES[:-1],  # 5 names vs scaler 6
        scaler=fitted.scaler,
    )
    with pytest.raises(InferenceFeatureError, match="mismatch"):
        engine._predict(fitted.frame.iloc[10])


def test_wrapper_dimension_mismatch_raises(fitted):
    wrapper = make_wrapper(fitted, feature_names=FEATURES + ["extra"])
    with pytest.raises(InferenceFeatureError, match="mismatch"):
        wrapper.predict_proba(fitted.frame.iloc[[10]])


def test_loaded_artifact_dimension_mismatch_raises(fitted):
    wrapper = make_wrapper(fitted, feature_names=FEATURES[:-1])
    with pytest.raises(InferenceFeatureError, match="Artifact dimension mismatch"):
        wrapper._validate_loaded_artifacts()


def test_missing_feature_column_raises_instead_of_zero_fill(fitted):
    engine = make_engine(fitted)
    row = fitted.frame.iloc[10].drop(index=FEATURES[2])
    with pytest.raises(InferenceFeatureError, match="Missing"):
        engine._predict(row)


def test_nan_and_inf_raise(fitted):
    engine = make_engine(fitted)

    with_nan = fitted.frame.iloc[10].copy()
    with_nan[FEATURES[1]] = np.nan
    with pytest.raises(InferenceFeatureError, match="Non-finite"):
        engine._predict(with_nan)

    with_inf = fitted.frame.iloc[10].copy()
    with_inf[FEATURES[0]] = np.inf
    with pytest.raises(InferenceFeatureError, match="Non-finite"):
        engine._predict(with_inf)


def test_object_dtype_raises(fitted):
    engine = make_engine(fitted)
    row = fitted.frame.iloc[10].astype(object)
    row[FEATURES[3]] = "not-a-number"
    with pytest.raises(InferenceFeatureError, match="Non-numeric"):
        engine._predict(row)


# ─── 5. Dependency injection: one scaler instance, no second copy ───────────


def test_ensure_model_injects_same_scaler_instance(tmp_path, fitted):
    # A synthetic artifact trio makes ensure_model take the "load" branch
    # without ever touching the repository's real model files.
    (tmp_path / "trade_model_xgb.json").write_text("{}")
    (tmp_path / "scaler.joblib").write_bytes(b"stub")
    (tmp_path / "trade_model_xgb.features.json").write_text("[]")

    wrapper = make_wrapper(fitted)
    wrapper.load = lambda *args, **kwargs: None  # read-only stub (accepts model_bytes/scaler_bytes)

    engine = StrategyEngine(StrategyConfig(), model=None, feature_list=[])
    feat_cfg = SimpleNamespace(retrain_every_n_days=7, use_macd=True)

    result = ensure_model(
        tmp_path / "trade_model_xgb.pkl",
        feat_cfg,
        wrapper,
        engine,
        fetcher=None,
        feat_engine=None,
        DEFAULT_PAIRS=[],
        YAHOO_TO_OANDA={},
        cfg=None,
    )

    assert result.ok, f"expected READY, got status={result.status} reason={result.reason}"
    # ensure_model wires the SAME instances the wrapper loaded into the engine
    # (in place), so a second scaler copy must never appear.
    assert engine.scaler is wrapper.scaler, "scaler must not be re-loaded"
    assert engine.model is wrapper.model
    assert engine.features is wrapper.feature_names
    assert engine._predict(fitted.frame.iloc[10]) == pytest.approx(
        wrapper.predict_proba(fitted.frame.iloc[[10]])[0, 1], abs=1e-12
    )
