"""
data_pipeline.py — FX Bot Feature Engineering & Inference Matrix Builder
Integrates: Phase1 dtype/scaler fix + Phase2 MACD/NaN gap protection
Version: 6.8.5-2 | Date: 2026-10-22
"""
import numpy as np
import pandas as pd
import logging
from typing import Optional, Tuple, List, Dict, Any
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)

# ─── Constants ───
MIN_REQUIRED_BARS = 34          # MACD theoretical minimum: 26+9-1
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

# ─── Exception Classes ───
class InferenceFeatureError(ValueError):
    """Raised when features cannot be computed/validated — fail explicitly, not zero-fill"""
    pass

class ScalerMissingError(RuntimeError):
    """Scaler not provided or unfitted when required"""
    pass

class DimensionMismatchError(ValueError):
    """Input/scaler/model dimension mismatch"""
    pass

class FeatureConfig:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def _build_matrix(X, feature_list, scaler) -> np.ndarray:
    if scaler is None:
        raise ScalerMissingError("Scaler not provided")
    if not hasattr(scaler, "n_features_in_"):
        raise ScalerMissingError("Scaler not fitted")

    if len(feature_list) != scaler.n_features_in_:
        raise InferenceFeatureError(
            f"Scaler dimension mismatch: scaler expects {scaler.n_features_in_}, "
            f"feature list has {len(feature_list)}")

    if isinstance(X, pd.Series):
        missing = [c for c in feature_list if c not in X.index]
        if missing:
            raise InferenceFeatureError(f"Missing required features: {missing}")
        sel = X.loc[list(feature_list)]
        try:
            raw = sel.to_numpy(dtype=float).reshape(1, -1)
        except (ValueError, TypeError) as e:
            raise InferenceFeatureError(f"Non-numeric values in inference input: {e}") from e
    elif isinstance(X, pd.DataFrame):
        missing = [c for c in feature_list if c not in X.columns]
        if missing:
            raise InferenceFeatureError(f"Missing required features: {missing}")
        sel = X[list(feature_list)]
        try:
            raw = sel.to_numpy(dtype=float)
        except (ValueError, TypeError) as e:
            raise InferenceFeatureError(f"Non-numeric values in inference input: {e}") from e
    elif isinstance(X, np.ndarray):
        raw = X.reshape(1, -1) if X.ndim == 1 else X
        if raw.shape[1] != len(feature_list):
            raise InferenceFeatureError(
                f"Input dimension mismatch: {raw.shape[1]} vs {len(feature_list)}")
    else:
        raise TypeError(f"Unsupported input type: {type(X)}")

    try:
        vals = np.asarray(raw, dtype=np.float64)
    except (ValueError, TypeError) as e:
        raise InferenceFeatureError(f"Non-numeric values in inference input: {e}") from e

    if not np.isfinite(vals).all():
        raise InferenceFeatureError("Non-finite values in inference matrix")

    return scaler.transform(vals)


class ModelWrapper:
    """Minimal implementation matching test expectations"""
    def __init__(self, config=None, model_path=None, feature_list=None, **kwargs):
        self.config = config or FeatureConfig()
        self.model_path = model_path
        self.feature_names = feature_list or []
        self.model = kwargs.get("model")
        self.scaler = kwargs.get("scaler")

    def predict_proba(self, X):
        if self.model is None:
            raise RuntimeError("Model not set")
        X_scaled = _build_matrix(X, self.feature_names, self.scaler)
        return self.model.predict_proba(X_scaled)

    def _validate_loaded_artifacts(self):
        n = len(self.feature_names)
        if not n:
            raise InferenceFeatureError("Artifact dimension mismatch: no feature list")
        for label, obj in (("scaler", self.scaler), ("model", self.model)):
            k = getattr(obj, "n_features_in_", None)
            if k is not None and k != n:
                raise InferenceFeatureError(
                    f"Artifact dimension mismatch: {n} features vs {label} expects {k}")


def positive_class_index(model, num_classes=None):
    """Return index of positive class — [0,1]→1; [1,0]→0"""
    classes = list(model.classes_) if hasattr(model, 'classes_') else [0, 1]
    return 1 if classes[1] > classes[0] else 0


def predict_p_up(model, scaler, feature_list, X):
    if scaler is None:
        raise ScalerMissingError("Scaler not fitted or provided")

    X_scaled = _build_matrix(X, feature_list, scaler)
    proba = model.predict_proba(X_scaled)
    pos_idx = positive_class_index(model)
    return proba[:, pos_idx], None

__all__ = [
    "FeatureConfig",
    "ModelWrapper",
    "InferenceFeatureError",
    "ScalerMissingError",
    "DimensionMismatchError",
    "positive_class_index",
    "predict_p_up",
    "prepare_inference_matrix",
    "build_feature_dataframe",
    "compute_macd_safe",
    "validate_input_length",
]

# ─── Phase 2: Gap-Resilient Price & MACD Features ───
def compute_macd_safe(df: pd.DataFrame) -> Tuple[pd.Series, pd.Series, pd.Series]:
    close = df["Close"].copy()

    gap_count = close.isna().sum()
    if gap_count > 0:
        logger.warning(
            f"[DATA-GAP] Close column has {gap_count} NaN value(s) "
            f"→ forward-fill then back-fill applied"
        )
        close = close.ffill().bfill()

    if close.isna().any():
        raise InferenceFeatureError(
            "[MACD-FAIL] Persistent NaN in Close after filling — cannot compute MACD"
        )

    try:
        import talib
        # ✅ 关键修复：确保 float64 numpy 数组传给 TA-Lib
        close_np = close.values.astype(np.float64)
        macd_line, signal_line, hist_line = talib.MACD(
            close_np,
            fastperiod=MACD_FAST,
            slowperiod=MACD_SLOW,
            signalperiod=MACD_SIGNAL,
        )
        idx = df.index
        macd_line = pd.Series(macd_line, index=idx)
        signal_line = pd.Series(signal_line, index=idx)
        hist_line = pd.Series(hist_line, index=idx)
    except ImportError:
        # Pandas fallback
        ema_fast = close.ewm(span=MACD_FAST, adjust=False).mean()
        ema_slow = close.ewm(span=MACD_SLOW, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=MACD_SIGNAL, adjust=False).mean()
        hist_line = macd_line - signal_line

    if macd_line.isna().all() or signal_line.isna().all() or hist_line.isna().all():
        raise InferenceFeatureError(
            "[MACD-FAIL] All MACD values are NaN after gap fill — insufficient data range"
        )

    macd_line = macd_line.ffill().fillna(0.0)
    signal_line = signal_line.ffill().fillna(0.0)
    hist_line = hist_line.ffill().fillna(0.0)

    return macd_line, signal_line, hist_line

def build_feature_dataframe(
    df: pd.DataFrame,
    feature_list: List[str],
    use_macd: bool = True,
) -> pd.DataFrame:
    """
    Build aligned feature DataFrame matching .features.json order & definition.
    Only columns listed in feature_list are returned.
    """
    X = pd.DataFrame(index=df.index)

    # ─── Price / Basic ───
    if "return_1" in feature_list:
        X["return_1"] = df["Close"].pct_change(1)
    if "return_4" in feature_list:
        X["return_4"] = df["Close"].pct_change(4)
    if "return_12" in feature_list:
        X["return_12"] = df["Close"].pct_change(12)
    if "volatility_12" in feature_list:
        X["volatility_12"] = df["Close"].pct_change(1).rolling(12).std()
    if "high_low_range" in feature_list:
        X["high_low_range"] = (df["High"] - df["Low"]) / df["Close"]
    if "close_vs_ma20" in feature_list:
        ma20 = df["Close"].rolling(20).mean()
        X["close_vs_ma20"] = (df["Close"] - ma20) / ma20

    # ─── RSI ───
    if any(c.startswith("rsi_") for c in feature_list):
        delta = df["Close"].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss + 1e-8)
        rsi = 100 - (100 / (1 + rs))
        if "rsi" in feature_list:
            X["rsi"] = rsi
        if "rsi_slope" in feature_list:
            X["rsi_slope"] = rsi.diff(3)

    # ─── MACD (Phase 2 protected) ───
    macd_cols = ["macd_line", "macd_signal", "macd_hist"]
    if use_macd and any(c in feature_list for c in macd_cols):
        try:
            ml, ms, mh = compute_macd_safe(df)
            if "macd_line" in feature_list:
                X["macd_line"] = ml
            if "macd_signal" in feature_list:
                X["macd_signal"] = ms
            if "macd_hist" in feature_list:
                X["macd_hist"] = mh
        except InferenceFeatureError as e:
            logger.warning(f"[BUILD-SKIP] {e} — MACD columns will be missing")

    # ─── Time features ───
    if "hour" in feature_list:
        X["hour"] = df.index.hour
    if "day_of_week" in feature_list:
        X["day_of_week"] = df.index.dayofweek
    if "is_ny" in feature_list:
        # NY session approx: UTC 12–21
        X["is_ny"] = ((df.index.hour >= 12) & (df.index.hour < 21)).astype(int)

    # ─── Reorder to EXACT match training feature list ───
    missing = [c for c in feature_list if c not in X.columns]
    if missing:
        raise InferenceFeatureError(f"Missing required features: {missing}")

    return X[feature_list].copy()


# ─── Phase 1 Core Fix: Mixed-dtype Series Row Handling ───
def prepare_inference_matrix(
    X_input,
    feature_list: List[str],
    scaler: Optional[StandardScaler] = None,
    validate_dims: bool = True,
) -> np.ndarray:
    """
    Convert raw feature input to model-ready matrix — Phase 1 dtype fix included.
    
    Fix: pd.Series row from .iloc[-1] collapses mixed int/float/bool → object dtype.
    Build frame column-by-column to preserve dtypes instead of .to_frame().T.
    """
    names = list(feature_list)

    # ─── Input shape normalization ───
    if isinstance(X_input, pd.Series):
        # Phase 1 FIX: preserve per-column dtypes instead of object cast
        X_input = pd.DataFrame({c: [X_input[c]] for c in names if c in X_input.index})
    elif isinstance(X_input, np.ndarray):
        if X_input.ndim == 1:
            X_input = pd.DataFrame([dict(zip(names, X_input))], columns=names)
        else:
            X_input = pd.DataFrame(X_input, columns=names[:X_input.shape[1]])

    if not isinstance(X_input, pd.DataFrame):
        raise TypeError(f"Unsupported input type: {type(X_input)}")

    # ─── Align columns ───
    if list(X_input.columns) != names:
        try:
            X_input = X_input[names]
        except KeyError as e:
            raise InferenceFeatureError(f"Feature name mismatch: {e}") from e

    # ─── dtype validation ───
    object_cols = X_input.select_dtypes(include=["object"]).columns.tolist()
    if object_cols:
        raise InferenceFeatureError(
            f"Non-numeric columns in inference: {object_cols} — dtype preservation failed"
        )

    # ─── Scaler transform ───
    values = X_input.values.astype(np.float64)

    if scaler is not None:
        if validate_dims:
            expect_feat = getattr(scaler, "n_features_in_", len(names))
            if values.shape[1] != expect_feat:
                raise InferenceFeatureError(
                    f"Scaler dimension mismatch: scaler expects {expect_feat}, "
                    f"input has {values.shape[1]}"
                )
        values = scaler.transform(values)

    # ─── Sanitize extremities ───
    # ─── Sanitize extremities ───
    if np.isnan(values).any():
        raise InferenceFeatureError("Non-finite values in inference matrix")
    if np.isinf(values).any():
        raise InferenceFeatureError("Non-finite values in inference matrix")

    return values


# ─── Utility ───
def validate_input_length(df: pd.DataFrame, required: int = MIN_REQUIRED_BARS) -> None:
    n = len(df)
    if n < required:
        raise InferenceFeatureError(
            f"Insufficient data: {n} bars available, minimum {required} required"
        )
    logger.debug(f"Input length OK: {n} bars ≥ {required} minimum")