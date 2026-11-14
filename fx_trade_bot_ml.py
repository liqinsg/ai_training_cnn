# fx_trade_bot_ml.py — MODEL & TRAINING (RARELY CHANGES)
# Contains: ensure_model(), globals needed for training
#
# ── Phase 3.0 (Runtime Containment & Observability) ─────────────────────────
#   * ensure_model() returns an explicit ModelInitResult instead of silently
#     training the model or raising on an expected availability failure.
#   * The LIVE runtime NEVER trains and NEVER writes / republishes artifacts.
#     Offline training stays in retrain_model.py and is unaffected.
#   * Outcomes are classified as READY / UNAVAILABLE / INCOMPATIBLE /
#     LOAD_FAILED with a separate reason code and full identity for diagnostics.
#   * Unexpected programming errors are NEVER swallowed — they are logged and
#     re-raised so they stay visible (Phase 3.0 §4.4).
#
# NOTE: this module intentionally imports only the stdlib + pandas so the
# runtime status contract can be unit-tested without the heavy inference stack
# (xgboost / scikit-learn).

import hashlib
import logging
import os
import platform
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


# ─── Runtime ML status contract (Phase 3.0 §3.1) ────────────────────────────
class ModelStatus:
    """Broad runtime condition of the model, kept separate from the reason."""

    READY = "READY"                # compatible approved model loaded & validated
    UNAVAILABLE = "UNAVAILABLE"    # no usable model can be provided
    INCOMPATIBLE = "INCOMPATIBLE"  # artifact does not match runtime contract
    LOAD_FAILED = "LOAD_FAILED"    # artifact exists but load/validation failed


# ─── Status reasons (Phase 3.0 §3.2) — separate from the status ─────────────
class ModelReason:
    MODEL_READY = "MODEL_READY"
    MODEL_MISSING = "MODEL_MISSING"
    MODEL_STALE = "MODEL_STALE"
    MODEL_INCOMPATIBLE = "MODEL_INCOMPATIBLE"
    MODEL_LOAD_EXCEPTION = "MODEL_LOAD_EXCEPTION"
    SCALER_MISSING = "SCALER_MISSING"
    FEATURE_CONTRACT_MISMATCH = "FEATURE_CONTRACT_MISMATCH"
    MODEL_VALIDATION_FAILED = "MODEL_VALIDATION_FAILED"
    UNKNOWN_LOAD_FAILURE = "UNKNOWN_LOAD_FAILURE"
    LIVE_TRAINING_BLOCKED = "LIVE_TRAINING_BLOCKED"
    LEGACY_FALLBACK_BLOCKED = "LEGACY_FALLBACK_BLOCKED"


# Exception *names* that represent an EXPECTED model load / validation failure.
# Anything else is treated as an unexpected programming error and re-raised.
# Names (not types) are used so this module does not have to import the heavy
# inference stack just to classify an exception.
_EXPECTED_LOAD_ERRORS = frozenset(
    {
        "FileNotFoundError",
        "InferenceFeatureError",
        "ScalerMissingError",
        "DimensionMismatchError",
        "LiveArtifactWriteError",
        "XGBoostError",
        "OSError",
        "EOFError",
        "UnpicklingError",
        "JSONDecodeError",
        "ImportError",
        "ValueError",
        "KeyError",
    }
)
# Subset → INCOMPATIBLE (runtime contract violation); the rest → LOAD_FAILED.
_INCOMPATIBLE_ERRORS = frozenset(
    {"InferenceFeatureError", "DimensionMismatchError", "ScalerMissingError"}
)


@dataclass
class ModelInitResult:
    """Explicit outcome of one model initialization attempt (Phase 3.0 §6.1)."""

    status: str
    reason: str
    detail: str = ""
    artifact_path: Optional[str] = None
    release_id: Optional[str] = None
    manifest_present: bool = False
    model_hash: Optional[str] = None
    scaler_hash: Optional[str] = None
    features_hash: Optional[str] = None
    cfg_hash: Optional[str] = None
    backend: Optional[str] = None
    host_id: Optional[str] = None
    profile: Optional[str] = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def ok(self) -> bool:
        return self.status == ModelStatus.READY

    def as_log_fields(self) -> str:
        return (
            f"status={self.status} reason={self.reason} "
            f"host={self.host_id} profile={self.profile} "
            f"path={self.artifact_path} release_id={self.release_id} "
            f"manifest={self.manifest_present} backend={self.backend} "
            f"model_hash={self.model_hash} scaler_hash={self.scaler_hash} "
            f"features_hash={self.features_hash} cfg_hash={self.cfg_hash} "
            f"detail={self.detail}"
        )


# ─── Helpers ────────────────────────────────────────────────────────────────
def resolve_artifact_paths(model_path) -> dict:
    """Resolve the artifact set from the model path stem (mirrors ModelWrapper)."""
    path = Path(model_path)
    stem = path.with_suffix("") if path.suffix else path
    return {
        "model": stem.with_suffix(".json"),
        "scaler": stem.parent / "scaler.joblib",
        "features": stem.with_suffix(".features.json"),
        "cfg": stem.with_suffix(".cfg.json"),
        "legacy": stem.with_suffix(".pkl"),
        "manifest": stem.with_suffix(".manifest.json"),
    }


def file_sha256(path) -> Optional[str]:
    """Return the sha256 of a file, or None when it is absent / unreadable."""
    p = Path(path)
    try:
        if not p.exists() or not p.is_file():
            return None
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _host_id() -> str:
    """Safe local host identifier — no network communication (Phase 3.0 §6.2)."""
    return os.getenv("FX_BOT_HOST_ID") or platform.node() or "unknown-host"


def _backend_identity() -> str:
    """Relevant inference backend identity, when importable."""
    try:
        import xgboost as xgb  # noqa: PLC0415

        return f"xgboost={getattr(xgb, '__version__', '?')}"
    except Exception:
        return "xgboost=unavailable"


def _record(result: ModelInitResult) -> None:
    """Emit one structured runtime record for a model initialization attempt."""
    level = logging.INFO if result.ok else logging.WARNING
    logger.log(level, "[ML-INIT] %s", result.as_log_fields())


# ─── ensure_model ───────────────────────────────────────────────────────────
def ensure_model(
    MODEL_PATH,
    FEAT_CFG,
    model_wrapper,
    strat_engine,
    fetcher,
    feat_engine,
    DEFAULT_PAIRS,
    YAHOO_TO_OANDA,
    cfg,
    live: bool = True,
    profile: Optional[str] = None,
) -> ModelInitResult:
    """Resolve the runtime model and return an explicit ``ModelInitResult``.

    Phase 3.0: the live runtime NEVER trains and NEVER writes artifacts. Expected
    availability / load / validation failures are classified and returned;
    unexpected programming errors are logged and re-raised so they remain
    visible.

    ``fetcher`` / ``feat_engine`` / ``DEFAULT_PAIRS`` / ``YAHOO_TO_OANDA`` /
    ``cfg`` are retained for call-site compatibility; the live path no longer
    uses them for training.
    """
    paths = resolve_artifact_paths(MODEL_PATH)
    result = ModelInitResult(
        status=ModelStatus.UNAVAILABLE,
        reason=ModelReason.MODEL_MISSING,
        artifact_path=str(paths["model"]),
        host_id=_host_id(),
        profile=profile,
        backend=_backend_identity(),
        manifest_present=paths["manifest"].exists(),
    )

    # Live runtime is read-only: any attempt to train or publish artifacts is
    # blocked inside ModelWrapper as defence-in-depth (Phase 3.0 §5.2).
    try:
        model_wrapper.read_only = bool(live)
    except Exception:  # pragma: no cover - attribute assignment is best-effort
        logger.warning("could not mark model_wrapper read-only", exc_info=True)

    split_ok = (
        paths["model"].exists()
        and paths["scaler"].exists()
        and paths["features"].exists()
    )
    if not split_ok:
        result.detail = (
            f"split artifacts incomplete (model={paths['model'].exists()} "
            f"scaler={paths['scaler'].exists()} features={paths['features'].exists()})"
        )
        _record(result)
        return result

    # Identity is derived from real bytes (no manifest → no invented release id).
    result.model_hash = file_sha256(paths["model"])
    result.scaler_hash = file_sha256(paths["scaler"])
    result.features_hash = file_sha256(paths["features"])
    result.cfg_hash = file_sha256(paths["cfg"])

    # Existing approved compatibility policy is "retrain when stale"; the live
    # runtime may no longer retrain, so staleness becomes an explicit
    # UNAVAILABLE outcome instead (Phase 3.0 §5.3).
    retrain_days = getattr(FEAT_CFG, "retrain_every_n_days", 30)
    try:
        age_days = (
            pd.Timestamp.now(tz="UTC").timestamp() - paths["model"].stat().st_mtime
        ) / 86400.0
    except OSError as e:
        result.status = ModelStatus.LOAD_FAILED
        result.reason = ModelReason.MODEL_LOAD_EXCEPTION
        result.detail = f"OSError: {e}"
        _record(result)
        return result

    if age_days > retrain_days:
        result.status = ModelStatus.UNAVAILABLE
        result.reason = ModelReason.MODEL_STALE
        result.detail = (
            f"artifact age {age_days:.1f}d > retrain_every_n_days={retrain_days}; "
            f"live retraining is blocked (offline retrain_model.py required)"
        )
        _record(result)
        return result

    # ── Load ──
    try:
        model_wrapper.load()
    except Exception as e:  # noqa: BLE001 — classified immediately below
        name = type(e).__name__
        if name not in _EXPECTED_LOAD_ERRORS:
            # Unexpected programming error → keep it visible.
            logger.exception("[ML-INIT] unexpected error while loading model artifact")
            raise
        if name == "LiveArtifactWriteError":
            result.status = ModelStatus.INCOMPATIBLE
            result.reason = ModelReason.LEGACY_FALLBACK_BLOCKED
        elif name in _INCOMPATIBLE_ERRORS:
            result.status = ModelStatus.INCOMPATIBLE
            result.reason = ModelReason.MODEL_INCOMPATIBLE
        else:
            result.status = ModelStatus.LOAD_FAILED
            result.reason = ModelReason.MODEL_LOAD_EXCEPTION
        result.detail = f"{name}: {e}"
        logger.error("[ML-INIT] model load failed: %s", result.detail, exc_info=True)
        _record(result)
        return result

    # ── Validate the loaded artifact against the runtime contract ──
    if getattr(model_wrapper, "model", None) is None or not getattr(
        model_wrapper, "feature_names", None
    ):
        result.status = ModelStatus.INCOMPATIBLE
        result.reason = ModelReason.FEATURE_CONTRACT_MISMATCH
        result.detail = "model or feature list missing after load"
        logger.error("[ML-INIT] model validation failed: %s", result.detail)
        _record(result)
        return result
    if getattr(model_wrapper, "scaler", None) is None:
        result.status = ModelStatus.INCOMPATIBLE
        result.reason = ModelReason.SCALER_MISSING
        result.detail = "scaler missing after load — incomplete release rejected"
        logger.error("[ML-INIT] model validation failed: %s", result.detail)
        _record(result)
        return result

    # ── READY: wire the SAME instances the wrapper loaded (unchanged) ──
    strat_engine.model = model_wrapper.model
    strat_engine.scaler = model_wrapper.scaler
    strat_engine.features = model_wrapper.feature_names
    result.status = ModelStatus.READY
    result.reason = ModelReason.MODEL_READY
    result.detail = "compatible approved model loaded and validated"
    logger.info(
        "Inference wiring: model_n_features=%s scaler_n_features=%s "
        "features=%s use_macd=%s",
        getattr(model_wrapper.model, "n_features_in_", "?"),
        getattr(model_wrapper.scaler, "n_features_in_", "?"),
        len(model_wrapper.feature_names),
        getattr(FEAT_CFG, "use_macd", "?"),
    )
    _record(result)
    return result
