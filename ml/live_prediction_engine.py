# ml/live_prediction_engine.py — STAGE B LIVE PREDICTION ENGINE
# Implements the strict prediction state machine, CD validation gate, 
# and self-describing prediction result payload.

import logging
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class PredictionStatus:
    READY = "READY"
    UNINTERPRETABLE = "UNINTERPRETABLE"
    ABSTAIN = "ABSTAIN"
    NOT_RUN = "NOT_RUN"
    UNAVAILABLE = "UNAVAILABLE"
    INVALID = "INVALID"
    ERROR = "ERROR"


class PredictionReason:
    NONE = "NONE"
    CLASS_DEFINITION_UNVERIFIED = "CLASS_DEFINITION_UNVERIFIED"
    INPUT_INSUFFICIENT = "INPUT_INSUFFICIENT"
    MODEL_NOT_USABLE = "MODEL_NOT_USABLE"
    FEATURE_CONTRACT_VIOLATION = "FEATURE_CONTRACT_VIOLATION"
    PREDICTION_INVALID_PROBABILITY = "PREDICTION_INVALID_PROBABILITY"
    DIMENSION_MISMATCH = "DIMENSION_MISMATCH"
    EXECUTION_ERROR = "EXECUTION_ERROR"


class PredictionResult:
    """
    Self-describing, immutable prediction result payload adhering to Phase 3.1 / A.2 contract.
    """
    def __init__(
        self,
        status: str,
        reason: str,
        pair: str,
        timeframe: str,
        bar_time: Optional[datetime] = None,
        raw_probability: Optional[float] = None,
        p_up: Optional[float] = None,
        p_down: Optional[float] = None,
        direction: Optional[str] = None,
        positive_class_label: Optional[str] = None,
        diagnostics: Optional[Dict[str, Any]] = None,
    ):
        self.status = status
        self.reason = reason
        self.pair = pair
        self.timeframe = timeframe
        self.bar_time = bar_time or datetime.now(timezone.utc)
        self.raw_probability = raw_probability
        self.p_up = p_up
        self.p_down = p_down
        self.direction = direction
        self.positive_class_label = positive_class_label
        self.diagnostics = diagnostics or {}

        # Enforce contract invariants at instantiation time
        self._validate_invariants()

    def _validate_invariants(self):
        if self.status == PredictionStatus.UNINTERPRETABLE:
            if self.reason != PredictionReason.CLASS_DEFINITION_UNVERIFIED:
                raise ValueError("UNINTERPRETABLE status must pair with CLASS_DEFINITION_UNVERIFIED reason")
            if self.p_up is not None or self.p_down is not None:
                raise ValueError("p_up and p_down must be None when CD is unverified (use raw_probability)")
            if self.positive_class_label is not None:
                raise ValueError("positive_class_label must be None when CD is unverified")
            if self.direction is not None:
                raise ValueError("direction must be None / NONE when status is UNINTERPRETABLE")


class LivePredictionEngine:
    """
    Executes live model inference with strict state machine and CD verification gating.
    """
    def __init__(self, model_wrapper, feature_engine, config=None):
        self.model_wrapper = model_wrapper
        self.feature_engine = feature_engine
        self.config = config or {}
        
        # Class Definition (CD) Verification flag. 
        # By default unverified in current environment until explicitly signed off.
        self.class_definition_verified = self.config.get("class_definition_verified", False)
        self.positive_class_index = self.config.get("positive_class_index", 1)

    def predict_live(self, pair: str, timeframe: str, raw_candles: pd.DataFrame) -> PredictionResult:
        """
        Executes feature building, model prediction, and state mapping.
        """
        bar_time = raw_candles.index[-1] if not raw_candles.empty and isinstance(raw_candles.index, pd.DatetimeIndex) else datetime.now(timezone.utc)

        # 1. Precondition: Check model usability
        if self.model_wrapper is None or not getattr(self.model_wrapper, "is_loaded", True):
            return PredictionResult(
                status=PredictionStatus.UNAVAILABLE,
                reason=PredictionReason.MODEL_NOT_USABLE,
                pair=pair,
                timeframe=timeframe,
                bar_time=bar_time
            )

        # 2. Precondition: Check input sufficiency
        if raw_candles is None or len(raw_candles) < 20:
            return PredictionResult(
                status=PredictionStatus.NOT_RUN,
                reason=PredictionReason.INPUT_INSUFFICIENT,
                pair=pair,
                timeframe=timeframe,
                bar_time=bar_time
            )

        try:
            # 3. Apply authoritative Feature Contract
            feat_df = self.feature_engine.build(raw_candles)
            feature_cols = self.model_wrapper.feature_names
            
            latest_features = feat_df.iloc[-1][feature_cols].values.reshape(1, -1)

            # Check dimensions
            expected_dim = len(feature_cols)
            if latest_features.shape[1] != expected_dim:
                return PredictionResult(
                    status=PredictionStatus.INVALID,
                    reason=PredictionReason.DIMENSION_MISMATCH,
                    pair=pair,
                    timeframe=timeframe,
                    bar_time=bar_time,
                    diagnostics={"expected": expected_dim, "got": latest_features.shape[1]}
                )

            # Check NaN / Inf
            if pd.isna(latest_features).any() or not np.isfinite(latest_features).all():
                return PredictionResult(
                    status=PredictionStatus.INVALID,
                    reason=PredictionReason.FEATURE_CONTRACT_VIOLATION,
                    pair=pair,
                    timeframe=timeframe,
                    bar_time=bar_time
                )

            # 4. Scaling & Prediction
            scaled_features = self.model_wrapper.scaler.transform(latest_features)
            proba = self.model_wrapper.model.predict_proba(scaled_features)[0]
            
            raw_prob = float(proba[self.positive_class_index]) if len(proba) > self.positive_class_index else float(proba[0])

            # Validate probability bounds [0.0, 1.0]
            if not (0.0 <= raw_prob <= 1.0):
                return PredictionResult(
                    status=PredictionStatus.INVALID,
                    reason=PredictionReason.PREDICTION_INVALID_PROBABILITY,
                    pair=pair,
                    timeframe=timeframe,
                    bar_time=bar_time,
                    raw_probability=raw_prob
                )

            # 5. State Machine Gating: CD Verification Check
            if not self.class_definition_verified:
                # Inference succeeded, probability valid, but CD unverified -> UNINTERPRETABLE
                return PredictionResult(
                    status=PredictionStatus.UNINTERPRETABLE,
                    reason=PredictionReason.CLASS_DEFINITION_UNVERIFIED,
                    pair=pair,
                    timeframe=timeframe,
                    bar_time=bar_time,
                    raw_probability=raw_prob
                )
            else:
                # READY state (CD verified)
                p_up = raw_prob
                p_down = 1.0 - p_up
                direction = "BUY" if p_up > 0.5 else "SELL"
                pos_label = getattr(self.model_wrapper, "positive_class_label", "UP")
                
                return PredictionResult(
                    status=PredictionStatus.READY,
                    reason=PredictionReason.NONE,
                    pair=pair,
                    timeframe=timeframe,
                    bar_time=bar_time,
                    p_up=p_up,
                    p_down=p_down,
                    direction=direction,
                    positive_class_label=pos_label
                )

        except Exception as e:
            logger.error(f"Live prediction execution error for {pair}: {e}", exc_info=True)
            return PredictionResult(
                status=PredictionStatus.ERROR,
                reason=PredictionReason.EXECUTION_ERROR,
                pair=pair,
                timeframe=timeframe,
                bar_time=bar_time,
                diagnostics={"exception": str(e)}
            )