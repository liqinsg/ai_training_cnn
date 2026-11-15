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
from typing import Any, Optional

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

    # ── Phase 3.1 Stage C (SC-02, path A): loaded-instance provenance surface ─
    # ADDITIVE + best-effort (contract §4.1 freeze; Stage B spec §3.4). When the
    # authoritative adapter is importable, `loaded_identity` holds a
    # `ml.prediction_adapter.LoadedModelIdentity` binding the SHA-256 of the exact
    # bytes read once for each artifact **to the model/scaler instances actually
    # wired into the strategy engine** (single-read byte identity — the hash
    # covers the same bytes that produced the executing instance). Otherwise it
    # stays `None` and `identity_detail` explains why. These fields NEVER
    # influence `status` / `reason` / `ok` / `as_log_fields()` or any control
    # flow — they are purely additive transparency for Stage C consumers.
    loaded_identity: Optional[Any] = None
    identity_detail: Optional[str] = None

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


def _read_artifact_bytes(path) -> tuple[Optional[bytes], Optional[str]]:
    """Read a file's exact bytes once; return ``(bytes, None)`` or ``(None, detail)``."""
    try:
        with open(path, "rb") as f:
            return f.read(), None
    except OSError as e:
        return None, f"{type(e).__name__}: {e}"


def _bind_wired_identity(
    *,
    model_bytes: Optional[bytes],
    scaler_bytes: Optional[bytes],
    model_instance,
    scaler_instance,
    source_path,
    loaded_from_bytes: bool,
    read_detail: Optional[str],
) -> tuple[Optional[Any], Optional[str]]:
    """Path A (SC-02): bind the pre-read bytes to the ALREADY-WIRED instances.

    The bytes were read once and handed to ``model_wrapper.load(...)``, so when
    the loader confirms it built the wired instances from those bytes
    (``_loaded_from_bytes``), the resulting ``LoadedModelIdentity`` proves that
    the SHA-256 covers the *same* bytes that produced the executing model — real
    instance provenance, not a post-load re-read. Returns ``(identity, None)`` on
    success or ``(None, detail)``. **Fail-open by design**: every failure is
    contained here and never propagates, so it cannot change ``ensure_model``'s
    outcome or control flow (contract §4.1 freeze; Stage B spec §3.4). The heavy
    module is imported lazily so this module keeps working without the stack.
    """
    if model_bytes is None or scaler_bytes is None:
        return None, read_detail or "artifact bytes unavailable for identity binding"
    if not loaded_from_bytes:
        return None, (
            "loader did not construct the wired instances from the pre-read bytes "
            "(disk fallback) — no instance provenance available"
        )
    try:
        from ml.prediction_adapter import UtcClock, bind_loaded_identity
    except Exception as e:  # noqa: BLE001 — module/stack unavailable → transparent None
        return None, f"identity module unavailable: {type(e).__name__}: {e}"
    try:
        identity = bind_loaded_identity(
            model_bytes=model_bytes,
            scaler_bytes=scaler_bytes,
            model_instance=model_instance,
            scaler_instance=scaler_instance,
            clock=UtcClock(),
            source_path=str(source_path),
        )
        return identity, None
    except Exception as e:  # noqa: BLE001 — fail-open, never affects the load result
        return None, f"{type(e).__name__}: {e}"


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

    # ── Single authoritative read of the identity artifacts (SC-02, path A) ──
    # These exact bytes are BOTH hashed here and handed to the loader below, so
    # the wired model/scaler instances are constructed from the same bytes the
    # identity binds (single-read byte identity → no A/B swap window).
    model_bytes, model_read_detail = _read_artifact_bytes(paths["model"])
    scaler_bytes, scaler_read_detail = _read_artifact_bytes(paths["scaler"])
    result.model_hash = (
        hashlib.sha256(model_bytes).hexdigest() if model_bytes is not None else None
    )
    result.scaler_hash = (
        hashlib.sha256(scaler_bytes).hexdigest() if scaler_bytes is not None else None
    )
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
        if model_bytes is not None and scaler_bytes is not None:
            # Path A: hand over the bytes already read+hashed above, so the wired
            # instances are built from exactly those bytes (single read).
            model_wrapper.load(model_bytes=model_bytes, scaler_bytes=scaler_bytes)
        else:
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

    # ── Phase 3.1 Stage C (SC-02, path A): bind the identity to the WIRED
    # instances. The hash covers the same bytes the loader used to build
    # `model_wrapper.model` / `model_wrapper.scaler` — the exact instances wired
    # into `strat_engine` above (real instance provenance, not a second read).
    # ADDITIVE + fail-open: this cannot alter the wired instances, `status`,
    # `reason` or any control flow; it only surfaces byte-bound identity (§3.4).
    result.loaded_identity, result.identity_detail = _bind_wired_identity(
        model_bytes=model_bytes,
        scaler_bytes=scaler_bytes,
        model_instance=model_wrapper.model,
        scaler_instance=model_wrapper.scaler,
        source_path=paths["model"],
        loaded_from_bytes=bool(getattr(model_wrapper, "_loaded_from_bytes", False)),
        read_detail=model_read_detail or scaler_read_detail,
    )
    logger.info(
        "[ML-IDENTITY] loaded_identity=%s artifact_sha256=%s scaler_sha256=%s "
        "method=%s instance_provenance=%s detail=%s",
        "single-read-bytes" if result.loaded_identity is not None else "unavailable",
        getattr(result.loaded_identity, "artifact_sha256", None),
        getattr(result.loaded_identity, "scaler_sha256", None),
        getattr(result.loaded_identity, "load_method", None),
        result.loaded_identity is not None,
        result.identity_detail,
    )
    _record(result)
    return result
