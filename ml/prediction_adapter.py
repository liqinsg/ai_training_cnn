"""ml/prediction_adapter.py — Phase 3.1 Stage B Prediction Adapter.

Additive, narrowly scoped Prediction-layer module (Stage B / spec v3). It converts
one model-inference attempt into a structured, immutable ``PredictionResult``.

Scope (spec §0.4): Prediction boundary only. It implements no Decision, no Entry
Authorization, no consumer migration, no production-loader wiring, and changes no
trading behaviour. The production runtime is not wired to this module (Stage C).

Reused existing inference path (spec §2.1, §6.1):
    ``data_pipeline._build_matrix(X, feature_list, scaler)``  (feature-contract +
    scaling authority) followed by ``model.predict_proba(scaled)``. The adapter
    deliberately does not call ``data_pipeline.predict_p_up()`` because that helper
    selects the probability column via ``positive_class_index()``; Stage B requires
    the fixed structural ``EXTRACTION_INDEX = 1`` (spec §7.2).

No second feature pipeline, no strategy filtering, no second model loader, no
fallback direction and no fabricated probability (spec §0.2, §18).
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Callable, Mapping, Optional, Sequence, Tuple

import numpy as np

from data_pipeline import (
    DimensionMismatchError,
    InferenceFeatureError,
    ScalerMissingError,
    _build_matrix,
)

__all__ = [
    "PredictionStatus",
    "PredictionReason",
    "PredictionResult",
    "PredictionResultInvariantError",
    "PredictionAdapterContractError",
    "LoadedModelIdentity",
    "load_model_with_identity",
    "CDRegistryHandle",
    "CDRecord",
    "CDLookup",
    "Clock",
    "UtcClock",
    "run_prediction",
    "build_not_run_result",
    "DECISION_THRESHOLD",
    "COMPLEMENT_TOLERANCE",
    "ROW_SUM_TOLERANCE",
    "EXTRACTION_INDEX",
]

# ─────────────────────────────── constants ──────────────────────────────────
DECISION_THRESHOLD = 0.5           # spec §5.4.1 / §11.4
COMPLEMENT_TOLERANCE = 1e-9        # spec §5.4.3 (construction-time complement)
ROW_SUM_TOLERANCE = 1e-5           # spec §7.3.5 (float32-sized)
EXTRACTION_INDEX = 1               # spec §7.2 — fixed structural constant

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

# Diagnostics bounds (spec §5.1) — oversized / non-serializable entries are rejected.
_MAX_DIAG_ITEMS = 64
_MAX_DIAG_KEY = 128
_MAX_DIAG_STR = 4096
_MAX_DIAG_DEPTH = 6

# CD-matching outcomes (spec §7.4).
_CD_MATCHED = "MATCHED"
_CD_MISSING = "RECORD_MISSING"
_CD_DUPLICATE = "RECORD_DUPLICATE"

_CD_DECISION_VERIFIED = "VERIFIED"
_CD_SEMANTICS_POSITIVE = "UP"
_CD_SEMANTICS_NEGATIVE = "NOT_UP"
_CD_PROBABILITY_SEMANTICS = "BINARY_EXCLUSIVE_EXHAUSTIVE"


# ─────────────────────────────── statuses ───────────────────────────────────
class PredictionStatus:
    """Outcome of one prediction attempt (contract §1.1). Protocol-free enum-like."""

    READY = "READY"
    UNINTERPRETABLE = "UNINTERPRETABLE"
    ABSTAIN = "ABSTAIN"          # defined-but-unreachable (contract §1.1; spec §12.3)
    NOT_RUN = "NOT_RUN"
    UNAVAILABLE = "UNAVAILABLE"
    INVALID = "INVALID"
    ERROR = "ERROR"


class PredictionReason:
    """Authoritative reason paired with a status (contract §1.2)."""

    NONE = "NONE"                                     # READY success placeholder
    INPUT_INSUFFICIENT = "INPUT_INSUFFICIENT"
    MODEL_NOT_USABLE = "MODEL_NOT_USABLE"
    FEATURE_CONTRACT_VIOLATION = "FEATURE_CONTRACT_VIOLATION"
    DIMENSION_MISMATCH = "DIMENSION_MISMATCH"         # reserved / unreachable today
    PREDICTION_INVALID_PROBABILITY = "PREDICTION_INVALID_PROBABILITY"
    PREDICTION_OUTPUT_MALFORMED = "PREDICTION_OUTPUT_MALFORMED"
    EXECUTION_ERROR = "EXECUTION_ERROR"
    CLASS_DEFINITION_UNVERIFIED = "CLASS_DEFINITION_UNVERIFIED"
    ABSTAIN_BY_PREDICTION_RULE = "ABSTAIN_BY_PREDICTION_RULE"  # reserved / unreachable


_ALL_STATUSES = frozenset(
    {
        PredictionStatus.READY,
        PredictionStatus.UNINTERPRETABLE,
        PredictionStatus.ABSTAIN,
        PredictionStatus.NOT_RUN,
        PredictionStatus.UNAVAILABLE,
        PredictionStatus.INVALID,
        PredictionStatus.ERROR,
    }
)

# Spec §5.5 — status / reason compatibility (closed).
_STATUS_REASON_COMPAT = {
    PredictionStatus.READY: frozenset({PredictionReason.NONE}),
    PredictionStatus.UNINTERPRETABLE: frozenset({PredictionReason.CLASS_DEFINITION_UNVERIFIED}),
    PredictionStatus.NOT_RUN: frozenset({PredictionReason.INPUT_INSUFFICIENT}),
    PredictionStatus.UNAVAILABLE: frozenset({PredictionReason.MODEL_NOT_USABLE}),
    PredictionStatus.INVALID: frozenset(
        {
            PredictionReason.FEATURE_CONTRACT_VIOLATION,
            PredictionReason.DIMENSION_MISMATCH,
            PredictionReason.PREDICTION_INVALID_PROBABILITY,
            PredictionReason.PREDICTION_OUTPUT_MALFORMED,
        }
    ),
    PredictionStatus.ERROR: frozenset({PredictionReason.EXECUTION_ERROR}),
    PredictionStatus.ABSTAIN: frozenset({PredictionReason.ABSTAIN_BY_PREDICTION_RULE}),
}

_DIRECTION_BUY = "BUY"
_DIRECTION_SELL = "SELL"
_DIRECTION_NONE = "NONE"


# ─────────────────────────────── exceptions ─────────────────────────────────
class PredictionResultInvariantError(Exception):
    """Raised when a ``PredictionResult`` would violate a contract invariant."""


class PredictionAdapterContractError(ValueError):
    """Pre-inference API contract violation (spec §6.2) — the only ``raise`` path."""


class CDRegistryError(Exception):
    """Raised when the CD Registry cannot be loaded at all."""


class _MemoryLoadUnsupported(Exception):
    """Internal: the model library cannot construct from in-memory bytes."""


# ─────────────────────────────── clock ──────────────────────────────────────
class Clock:
    """Injectable clock (spec §13.1). Production default: :class:`UtcClock`."""

    def now(self) -> datetime:  # pragma: no cover - interface
        raise NotImplementedError


class UtcClock(Clock):
    """Production UTC clock — the only permitted system-clock call site (spec §13.3)."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


def _require_clock(clock: Any) -> Any:
    if clock is None or not callable(getattr(clock, "now", None)):
        raise PredictionAdapterContractError("clock must be an object exposing now()")
    return clock


def _to_utc(value: datetime, *, field_name: str, allow_none: bool = False) -> Optional[datetime]:
    """Normalize to UTC; reject naive values; never assume naive == UTC (spec §6.4)."""
    if value is None:
        if allow_none:
            return None
        raise PredictionAdapterContractError(f"{field_name} is required and must be timezone-aware")
    if not isinstance(value, datetime):
        raise PredictionAdapterContractError(
            f"{field_name} must be a datetime, got {type(value).__name__}"
        )
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise PredictionAdapterContractError(
            f"{field_name} must be timezone-aware (naive datetime rejected)"
        )
    return value.astimezone(timezone.utc)


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA256_RE.match(value))


# ───────────────────── artifact identity + single-read loader ───────────────
@dataclass(frozen=True)
class LoadedModelIdentity:
    """Immutable binding of the exact loaded bytes to the model/scaler instances.

    The binding cannot be rebound (spec §3.5); the library instances themselves stay
    mutable, which is out of scope.
    """

    artifact_sha256: str
    scaler_sha256: str
    model_instance: Any
    scaler_instance: Any
    load_timestamp: datetime
    source_path: Optional[str] = None
    load_method: str = "BYTES"      # "BYTES" | "TEMPFILE" (spec §3.2)

    def __post_init__(self) -> None:
        if not _is_sha256(self.artifact_sha256):
            raise ValueError("artifact_sha256 must be a full 64-char lowercase hex SHA-256")
        if not _is_sha256(self.scaler_sha256):
            raise ValueError("scaler_sha256 must be a full 64-char lowercase hex SHA-256")
        if self.load_method not in ("BYTES", "TEMPFILE"):
            raise ValueError("load_method must be 'BYTES' or 'TEMPFILE'")
        ts = self.load_timestamp
        if not isinstance(ts, datetime) or ts.tzinfo is None or ts.tzinfo.utcoffset(ts) is None:
            raise ValueError("load_timestamp must be a timezone-aware datetime")
        object.__setattr__(self, "load_timestamp", ts.astimezone(timezone.utc))


def _load_xgb_from_path(path: str) -> Any:
    import xgboost as xgb

    model = xgb.XGBClassifier()
    model.load_model(path)
    return model


def _default_model_loader(raw: bytes) -> Any:
    """Construct an XGBClassifier from in-memory bytes (single-read identity, spec §3.2)."""
    import xgboost as xgb

    model = xgb.XGBClassifier()
    try:
        model.load_model(bytearray(raw))
    except TypeError as exc:  # library cannot construct from memory → TEMPFILE fallback
        raise _MemoryLoadUnsupported(str(exc)) from None
    return model


def _default_scaler_loader(raw: bytes) -> Any:
    import joblib

    with _suppress_joblib_warnings():
        return joblib.load(io.BytesIO(raw))


class _suppress_joblib_warnings:
    def __enter__(self):
        import warnings

        self._ctx = warnings.catch_warnings()
        self._ctx.__enter__()
        warnings.simplefilter("ignore", DeprecationWarning)
        return self

    def __exit__(self, *exc):
        return self._ctx.__exit__(*exc)


def load_model_with_identity(
    *,
    model_path,
    scaler_path,
    clock: Clock,
    model_loader: Optional[Callable[[bytes], Any]] = None,
    scaler_loader: Optional[Callable[[bytes], Any]] = None,
    model_path_loader: Optional[Callable[[str], Any]] = None,
    after_read_hook: Optional[Callable[[], None]] = None,
) -> LoadedModelIdentity:
    """Read each artifact once, hash those exact bytes, then construct from them.

    Hashing a file and loading an independent read later is prohibited (spec §3.1,
    §3.7). ``after_read_hook`` is invoked after all bytes are read but before
    construction, so tests can prove the loader ignores later on-disk changes
    (spec B-T49).
    """
    _require_clock(clock)
    model_loader = model_loader or _default_model_loader
    scaler_loader = scaler_loader or _default_scaler_loader
    model_path_loader = model_path_loader or _load_xgb_from_path

    with open(model_path, "rb") as fh:
        model_bytes = fh.read()
    artifact_sha256 = hashlib.sha256(model_bytes).hexdigest()

    with open(scaler_path, "rb") as fh:
        scaler_bytes = fh.read()
    scaler_sha256 = hashlib.sha256(scaler_bytes).hexdigest()

    if after_read_hook is not None:
        after_read_hook()

    load_method = "BYTES"
    try:
        model_instance = model_loader(model_bytes)
    except _MemoryLoadUnsupported:
        load_method = "TEMPFILE"
        model_instance = _load_via_private_tempfile(model_bytes, model_path_loader)

    scaler_instance = scaler_loader(scaler_bytes)

    return LoadedModelIdentity(
        artifact_sha256=artifact_sha256,
        scaler_sha256=scaler_sha256,
        model_instance=model_instance,
        scaler_instance=scaler_instance,
        load_timestamp=clock.now(),
        source_path=str(model_path),
        load_method=load_method,
    )


def _load_via_private_tempfile(raw: bytes, path_loader: Callable[[str], Any]) -> Any:
    """Private 0600 temp file, mode-restricted, deleted immediately after load (spec §3.2)."""
    fd, tmp_path = tempfile.mkstemp(prefix="cd_model_", suffix=".json")
    try:
        os.chmod(tmp_path, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(raw)
        return path_loader(tmp_path)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:  # pragma: no cover - best effort cleanup
            pass


# ─────────────────────────── CD registry ────────────────────────────────────
@dataclass(frozen=True)
class CDRecord:
    """One exact-artifact CD record (spec §4.2)."""

    artifact_sha256: Optional[str] = None
    scaler_sha256: Optional[str] = None
    decision: Optional[str] = None
    positive_class_label: Any = None
    positive_class_index: Optional[int] = None
    positive_class_semantics: Optional[str] = None
    negative_class_semantics: Optional[str] = None
    probability_semantics: Optional[str] = None
    evidence_record: Optional[str] = None
    evidence_record_version: Optional[str] = None
    decision_id: Optional[str] = None

    FIELDS: Tuple[str, ...] = (
        "artifact_sha256",
        "scaler_sha256",
        "decision",
        "positive_class_label",
        "positive_class_index",
        "positive_class_semantics",
        "negative_class_semantics",
        "probability_semantics",
        "evidence_record",
        "evidence_record_version",
        "decision_id",
    )


@dataclass(frozen=True)
class CDLookup:
    """Result of one exact-artifact registry lookup."""

    outcome: str                       # MATCHED | RECORD_MISSING | RECORD_DUPLICATE
    record: Optional[CDRecord] = None


class CDRegistryHandle:
    """Read-only, startup-loaded CD registry handle (spec §4.3.11).

    ``load()`` never raises for a missing / malformed registry — it returns a handle
    with ``ok == False`` so the adapter fails closed (spec §4.3.10, §7.4).
    """

    def __init__(
        self,
        records: Sequence[CDRecord],
        registry_sha256: Optional[str],
        source_path: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        self._records: Tuple[CDRecord, ...] = tuple(records)
        self._registry_sha256 = registry_sha256
        self._source_path = source_path
        self._error = error

    @property
    def ok(self) -> bool:
        return self._error is None

    @property
    def error(self) -> Optional[str]:
        return self._error

    @property
    def registry_sha256(self) -> Optional[str]:
        return self._registry_sha256

    @property
    def source_path(self) -> Optional[str]:
        return self._source_path

    @property
    def records(self) -> Tuple[CDRecord, ...]:
        return self._records

    @classmethod
    def load(cls, path) -> "CDRegistryHandle":
        try:
            with open(path, "rb") as fh:
                raw = fh.read()
        except OSError as exc:
            return cls((), None, str(path), error=f"REGISTRY_UNREADABLE: {exc}")

        registry_sha256 = hashlib.sha256(raw).hexdigest()
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            return cls((), registry_sha256, str(path), error=f"REGISTRY_MALFORMED: {exc}")

        try:
            if not isinstance(payload, dict):
                raise ValueError("registry root must be an object")
            if payload.get("schema_version") != 1:
                raise ValueError("unsupported registry schema_version")
            raw_records = payload["records"]
            if not isinstance(raw_records, list):
                raise ValueError("registry 'records' must be a list")
        except (KeyError, ValueError) as exc:
            return cls((), registry_sha256, str(path), error=f"REGISTRY_MALFORMED: {exc}")

        records = []
        for item in raw_records:
            if not isinstance(item, Mapping):
                return cls((), registry_sha256, str(path), error="REGISTRY_MALFORMED: record is not an object")
            records.append(CDRecord(**{k: item.get(k) for k in CDRecord.FIELDS}))

        return cls(tuple(records), registry_sha256, str(path))

    def lookup(self, artifact_sha256: Optional[str], scaler_sha256: Optional[str]) -> CDLookup:
        """Exact-artifact lookup: both hashes must match (spec §4.6). No filename / family match."""
        if not self.ok:
            return CDLookup(_CD_MISSING, None)
        matches = [
            r
            for r in self._records
            if r.artifact_sha256 == artifact_sha256 and r.scaler_sha256 == scaler_sha256
        ]
        if not matches:
            return CDLookup(_CD_MISSING, None)
        if len(matches) > 1:
            return CDLookup(_CD_DUPLICATE, None)
        return CDLookup(_CD_MATCHED, matches[0])


# ─────────────────────── diagnostics sanitisation ───────────────────────────
def _assert_json_safe(value: Any, depth: int = 0) -> None:
    if depth > _MAX_DIAG_DEPTH:
        raise PredictionResultInvariantError("diagnostics nesting too deep")
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise PredictionResultInvariantError("diagnostics float must be finite")
        return
    if isinstance(value, str):
        if len(value) > _MAX_DIAG_STR:
            raise PredictionResultInvariantError("diagnostics string too long")
        return
    if isinstance(value, (list, tuple)):
        if len(value) > _MAX_DIAG_ITEMS:
            raise PredictionResultInvariantError("diagnostics sequence too long")
        for item in value:
            _assert_json_safe(item, depth + 1)
        return
    if isinstance(value, Mapping):
        if len(value) > _MAX_DIAG_ITEMS:
            raise PredictionResultInvariantError("diagnostics mapping too large")
        for key, item in value.items():
            if not isinstance(key, str):
                raise PredictionResultInvariantError("diagnostics keys must be strings")
            _assert_json_safe(item, depth + 1)
        return
    raise PredictionResultInvariantError(
        f"non-JSON-serializable diagnostics value: {type(value).__name__}"
    )


def _sanitize_diagnostics(diagnostics: Any) -> Mapping[Any, Any]:
    if diagnostics is None:
        return MappingProxyType({})
    if not isinstance(diagnostics, Mapping):
        raise PredictionResultInvariantError("diagnostics must be a mapping")
    if len(diagnostics) > _MAX_DIAG_ITEMS:
        raise PredictionResultInvariantError("diagnostics too large")
    copy = {}
    for key, value in diagnostics.items():
        if not isinstance(key, str):
            raise PredictionResultInvariantError("diagnostics keys must be strings")
        if len(key) > _MAX_DIAG_KEY:
            raise PredictionResultInvariantError("diagnostics key too long")
        _assert_json_safe(value)
        copy[key] = value
    return MappingProxyType(copy)


# ─────────────────────────── PredictionResult ───────────────────────────────
def _is_unit_float(value: Any) -> bool:
    return isinstance(value, float) and math.isfinite(value) and 0.0 <= value <= 1.0


@dataclass(frozen=True)
class PredictionResult:
    """Immutable, self-describing prediction result (contract §1.3; spec §5)."""

    status: str
    reason: Optional[str]
    pair: str
    timeframe: str
    bar_time: Optional[datetime] = None
    direction: Optional[str] = None
    raw_probability: Optional[float] = None
    positive_class_label: Any = None
    p_up: Optional[float] = None
    p_not_up: Optional[float] = None
    p_down: Optional[float] = None
    model_id: Optional[str] = None
    model_artifact_hash: Optional[str] = None
    release_id: Optional[str] = None
    feature_contract_id: Optional[str] = None
    features_hash: Optional[str] = None
    timestamp: Optional[datetime] = None
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "diagnostics", _sanitize_diagnostics(self.diagnostics))
        object.__setattr__(self, "bar_time", _coerce_optional_utc(self.bar_time, "bar_time"))
        object.__setattr__(self, "timestamp", _coerce_optional_utc(self.timestamp, "timestamp"))
        if self.direction is None:
            object.__setattr__(self, "direction", _DIRECTION_NONE)
        _check_result_invariants(self)


def _coerce_optional_utc(value: Any, name: str) -> Optional[datetime]:
    if value is None:
        return None
    if not isinstance(value, datetime) or value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise PredictionResultInvariantError(f"{name} must be a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def _check_result_invariants(r: "PredictionResult") -> None:
    def bad(message: str) -> "PredictionResultInvariantError":
        return PredictionResultInvariantError(message)

    if r.status not in _ALL_STATUSES:
        raise bad(f"unknown status: {r.status!r}")
    allowed_reasons = _STATUS_REASON_COMPAT[r.status]
    if r.reason not in allowed_reasons:
        raise bad(f"status {r.status!r} cannot pair with reason {r.reason!r}")
    if not isinstance(r.pair, str) or not r.pair:
        raise bad("pair must be a non-empty string")
    if not isinstance(r.timeframe, str) or not r.timeframe:
        raise bad("timeframe must be a non-empty string")
    if r.p_down is not None:
        raise bad("p_down is deprecated/reserved and must always be None")

    if r.status == PredictionStatus.READY:
        if r.direction not in (_DIRECTION_BUY, _DIRECTION_SELL):
            raise bad("READY requires direction BUY or SELL")
        if not _is_unit_float(r.raw_probability):
            raise bad("READY requires a valid raw_probability in [0, 1]")
        if not _is_unit_float(r.p_up):
            raise bad("READY requires a valid p_up in [0, 1]")
        if not _is_unit_float(r.p_not_up):
            raise bad("READY requires a valid p_not_up in [0, 1]")
        if r.raw_probability != r.p_up:
            raise bad("READY requires raw_probability == p_up (same float)")
        if abs((r.p_up + r.p_not_up) - 1.0) > COMPLEMENT_TOLERANCE:
            raise bad("READY requires p_up + p_not_up == 1 within COMPLEMENT_TOLERANCE")
        expected = _DIRECTION_BUY if r.p_up > DECISION_THRESHOLD else _DIRECTION_SELL
        if r.direction != expected:
            raise bad(f"READY direction {r.direction!r} contradicts p_up under the §1.3.2 rule")
        if r.positive_class_label is None:
            raise bad("READY requires a Registry-verified positive_class_label")
        if not _is_sha256(r.model_artifact_hash):
            raise bad("READY requires a full model_artifact_hash")
        if "at_threshold" not in r.diagnostics:
            raise bad("READY requires diagnostics['at_threshold']")
        if r.diagnostics["at_threshold"] != (r.p_up == DECISION_THRESHOLD):
            raise bad("at_threshold must equal (p_up == DECISION_THRESHOLD)")
        return

    if r.status == PredictionStatus.UNINTERPRETABLE:
        if not _is_unit_float(r.raw_probability):
            raise bad("UNINTERPRETABLE requires a valid raw_probability")
        if r.p_up is not None or r.p_not_up is not None:
            raise bad("UNINTERPRETABLE must not expose interpreted probabilities")
        if r.positive_class_label is not None:
            raise bad("UNINTERPRETABLE must not expose a positive_class_label")
        return

    # NOT_RUN / UNAVAILABLE / INVALID / ERROR / ABSTAIN — no usable direction or value.
    if r.direction != _DIRECTION_NONE:
        raise bad(f"{r.status} must not expose a consumer-usable direction")
    if r.raw_probability is not None:
        raise bad(f"{r.status} must not carry raw_probability")
    if r.p_up is not None or r.p_not_up is not None:
        raise bad(f"{r.status} must not carry interpreted probabilities")
    if r.positive_class_label is not None:
        raise bad(f"{r.status} must not carry a positive_class_label")


# ─────────────────── probability validation (spec §10) ─────────────────────
def _validate_probability(value: Any) -> Tuple[bool, Optional[float]]:
    """Accept Python/NumPy int & float scalars; reject bool/Decimal/array/complex/str."""
    if isinstance(value, (bool, np.bool_)):
        return False, None
    if isinstance(value, np.ndarray):
        return False, None            # 0-D and n-D arrays are not scalar probabilities
    if isinstance(value, (int, np.integer)):
        candidate = float(value)
    elif isinstance(value, (float, np.floating)):
        candidate = float(value)
    else:
        return False, None
    if not math.isfinite(candidate):
        return False, None
    if candidate < 0.0 or candidate > 1.0:
        return False, None
    return True, candidate


def _strict_int_label(value: Any) -> Optional[int]:
    """Accept int / NumPy integer; reject bool, numpy.bool_, str, float, None (spec §11.1.1)."""
    if isinstance(value, (bool, np.bool_)):
        return None
    if isinstance(value, (int, np.integer)):
        return int(value)
    return None


def _labels_match(runtime_label: Any, registry_label: Any) -> bool:
    left = _strict_int_label(runtime_label)
    right = _strict_int_label(registry_label)
    if left is None or right is None:
        return False
    return left == right


def _diag_scalar(value: Any) -> Any:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return float(value)
    if isinstance(value, str):
        return value
    return str(value)


# ─────────────── deterministic validation pipeline (spec §7) ────────────────
_ALL_USABLE_MODEL_STATUS = "READY"


def _model_unusable(model: Any, scaler: Any, model_status: Optional[str]) -> bool:
    if model is None or scaler is None:
        return True
    if model_status is not None and model_status != _ALL_USABLE_MODEL_STATUS:
        return True
    return False


def _validate_output_structure(proba: Any, model: Any) -> bool:
    """Spec §7.2 — all must hold, else PREDICTION_OUTPUT_MALFORMED."""
    if not hasattr(proba, "ndim") or not hasattr(proba, "shape"):
        return False
    if proba.ndim != 2 or proba.shape[0] != 1:
        return False
    classes = getattr(model, "classes_", None)
    if classes is None:
        return False
    try:
        class_list = list(classes)
    except TypeError:
        return False
    if len(class_list) != 2:
        return False
    if proba.shape[1] != len(class_list):
        return False
    try:
        if bool(class_list[0] == class_list[1]):
            return False
    except Exception:  # pragma: no cover - exotic class values
        return False
    return True


def _evaluate_cd_binding(
    *, identity: Optional[LoadedModelIdentity], registry: Any, runtime_class_label: Any
) -> Tuple[bool, Optional[CDRecord], Optional[str]]:
    """Spec §7.4 — first failure wins; returns (matched, record, cd_failure_cause)."""
    artifact_hash = identity.artifact_sha256 if identity is not None else None
    scaler_hash = identity.scaler_sha256 if identity is not None else None
    if not _is_sha256(artifact_hash) or not _is_sha256(scaler_hash):
        return False, None, "HASH_UNAVAILABLE"

    if registry is None or not getattr(registry, "ok", False):
        return False, None, "REGISTRY_UNAVAILABLE"

    lookup = registry.lookup(artifact_hash, scaler_hash)
    if lookup.outcome == _CD_DUPLICATE:
        return False, None, "RECORD_DUPLICATE"
    if lookup.outcome != _CD_MATCHED or lookup.record is None:
        return False, None, "RECORD_MISSING"

    record = lookup.record
    if record.decision != _CD_DECISION_VERIFIED:
        return False, record, "DECISION_NOT_VERIFIED"
    if record.positive_class_index != EXTRACTION_INDEX:
        return False, record, "INDEX_MISMATCH"
    if not _labels_match(runtime_class_label, record.positive_class_label):
        return False, record, "LABEL_MISMATCH"
    if (
        record.positive_class_semantics != _CD_SEMANTICS_POSITIVE
        or record.negative_class_semantics != _CD_SEMANTICS_NEGATIVE
        or record.probability_semantics != _CD_PROBABILITY_SEMANTICS
    ):
        return False, record, "SEMANTICS_UNSUPPORTED"
    return True, record, None


def _construct_result(**kwargs: Any) -> PredictionResult:
    """Thin construction seam (monkeypatchable) so the §5.6 fallback is testable."""
    return PredictionResult(**kwargs)


def _evaluate(
    *,
    model: Any,
    scaler: Any,
    feature_list: Sequence[str],
    X: Any,
    pair: str,
    timeframe: str,
    bar_time: datetime,
    clock: Any,
    registry: Any,
    identity: Optional[LoadedModelIdentity],
    model_status: Optional[str],
    diagnostics: Optional[Mapping[str, Any]],
) -> PredictionResult:
    timestamp = _require_clock(clock).now()
    artifact_hash = identity.artifact_sha256 if identity is not None else None
    scaler_hash = identity.scaler_sha256 if identity is not None else None
    base_diag = dict(diagnostics) if diagnostics else {}

    def _common(**extra: Any) -> dict:
        merged = dict(base_diag)
        merged.update(extra)
        if artifact_hash is not None:
            merged["model_artifact_hash"] = artifact_hash
        if scaler_hash is not None:
            merged["scaler_sha256"] = scaler_hash
        return merged

    # ── step 1: model / scaler usability ──
    if _model_unusable(model, scaler, model_status):
        return _construct_result(
            status=PredictionStatus.UNAVAILABLE,
            reason=PredictionReason.MODEL_NOT_USABLE,
            pair=pair,
            timeframe=timeframe,
            bar_time=bar_time,
            direction=_DIRECTION_NONE,
            model_artifact_hash=artifact_hash,
            timestamp=timestamp,
            diagnostics=_common(model_status=model_status),
        )

    # ── step 2: input feature contract ──
    try:
        scaled = _build_matrix(X, feature_list, scaler)
    except ScalerMissingError:
        return _construct_result(
            status=PredictionStatus.UNAVAILABLE,
            reason=PredictionReason.MODEL_NOT_USABLE,
            pair=pair,
            timeframe=timeframe,
            bar_time=bar_time,
            direction=_DIRECTION_NONE,
            model_artifact_hash=artifact_hash,
            timestamp=timestamp,
            diagnostics=_common(failure_detail="scaler missing"),
        )
    except (InferenceFeatureError, DimensionMismatchError) as exc:
        return _construct_result(
            status=PredictionStatus.INVALID,
            reason=PredictionReason.FEATURE_CONTRACT_VIOLATION,
            pair=pair,
            timeframe=timeframe,
            bar_time=bar_time,
            direction=_DIRECTION_NONE,
            model_artifact_hash=artifact_hash,
            timestamp=timestamp,
            diagnostics=_common(exception_type=type(exc).__name__),
        )
    except Exception as exc:
        return _construct_result(
            status=PredictionStatus.ERROR,
            reason=PredictionReason.EXECUTION_ERROR,
            pair=pair,
            timeframe=timeframe,
            bar_time=bar_time,
            direction=_DIRECTION_NONE,
            model_artifact_hash=artifact_hash,
            timestamp=timestamp,
            diagnostics=_common(exception_type=type(exc).__name__, failure_stage="feature_contract"),
        )

    # ── step 3: inference execution ──
    try:
        proba = model.predict_proba(scaled)
    except Exception as exc:
        return _construct_result(
            status=PredictionStatus.ERROR,
            reason=PredictionReason.EXECUTION_ERROR,
            pair=pair,
            timeframe=timeframe,
            bar_time=bar_time,
            direction=_DIRECTION_NONE,
            model_artifact_hash=artifact_hash,
            timestamp=timestamp,
            diagnostics=_common(exception_type=type(exc).__name__, failure_stage="inference"),
        )

    # ── step 4: output structure (no Registry read) ──
    if not _validate_output_structure(proba, model):
        return _construct_result(
            status=PredictionStatus.INVALID,
            reason=PredictionReason.PREDICTION_OUTPUT_MALFORMED,
            pair=pair,
            timeframe=timeframe,
            bar_time=bar_time,
            direction=_DIRECTION_NONE,
            model_artifact_hash=artifact_hash,
            timestamp=timestamp,
            diagnostics=_common(failure_stage="output_structure"),
        )

    classes = list(model.classes_)
    runtime_class_label = classes[EXTRACTION_INDEX]
    complement_index = 1 - EXTRACTION_INDEX

    # ── step 5: neutral extraction + numeric validity (no Registry read) ──
    candidate_ok, candidate = _validate_probability(proba[0, EXTRACTION_INDEX])
    if not candidate_ok:
        return _construct_result(
            status=PredictionStatus.INVALID,
            reason=PredictionReason.PREDICTION_INVALID_PROBABILITY,
            pair=pair,
            timeframe=timeframe,
            bar_time=bar_time,
            direction=_DIRECTION_NONE,
            model_artifact_hash=artifact_hash,
            timestamp=timestamp,
            diagnostics=_common(
                invalid_candidate_safe_repr=_safe_repr(proba[0, EXTRACTION_INDEX])
            ),
        )
    complement_ok, complement = _validate_probability(proba[0, complement_index])
    if not complement_ok:
        return _construct_result(
            status=PredictionStatus.INVALID,
            reason=PredictionReason.PREDICTION_INVALID_PROBABILITY,
            pair=pair,
            timeframe=timeframe,
            bar_time=bar_time,
            direction=_DIRECTION_NONE,
            model_artifact_hash=artifact_hash,
            timestamp=timestamp,
            diagnostics=_common(
                invalid_complement_safe_repr=_safe_repr(proba[0, complement_index])
            ),
        )
    if abs((candidate + complement) - 1.0) > ROW_SUM_TOLERANCE:
        return _construct_result(
            status=PredictionStatus.INVALID,
            reason=PredictionReason.PREDICTION_OUTPUT_MALFORMED,
            pair=pair,
            timeframe=timeframe,
            bar_time=bar_time,
            direction=_DIRECTION_NONE,
            model_artifact_hash=artifact_hash,
            timestamp=timestamp,
            diagnostics=_common(row_sum=float(candidate + complement)),
        )

    raw_probability = candidate

    # ── step 6: artifact identity + CD binding (first Registry read) ──
    matched, record, cause = _evaluate_cd_binding(
        identity=identity, registry=registry, runtime_class_label=runtime_class_label
    )
    if not matched:
        return _construct_result(
            status=PredictionStatus.UNINTERPRETABLE,
            reason=PredictionReason.CLASS_DEFINITION_UNVERIFIED,
            pair=pair,
            timeframe=timeframe,
            bar_time=bar_time,
            direction=_DIRECTION_NONE,
            raw_probability=raw_probability,
            model_artifact_hash=artifact_hash,
            timestamp=timestamp,
            diagnostics=_common(
                cd_failure_cause=cause,
                runtime_class_label_at_extraction_index=_diag_scalar(runtime_class_label),
                runtime_classes=[_diag_scalar(c) for c in classes],
                registry_sha256=getattr(registry, "registry_sha256", None),
            ),
        )

    # ── step 7: probability interpretation (CD verified for the exact artifact) ──
    p_up = raw_probability
    p_not_up = 1.0 - p_up
    direction = _DIRECTION_BUY if p_up > DECISION_THRESHOLD else _DIRECTION_SELL
    at_threshold = p_up == DECISION_THRESHOLD

    # ── step 8: PredictionResult construction ──
    return _construct_result(
        status=PredictionStatus.READY,
        reason=PredictionReason.NONE,
        pair=pair,
        timeframe=timeframe,
        bar_time=bar_time,
        direction=direction,
        raw_probability=raw_probability,
        positive_class_label=_diag_scalar(record.positive_class_label),
        p_up=p_up,
        p_not_up=p_not_up,
        p_down=None,
        model_artifact_hash=artifact_hash,
        timestamp=timestamp,
        diagnostics=_common(
            at_threshold=at_threshold,
            runtime_class_label_at_extraction_index=_diag_scalar(runtime_class_label),
            runtime_classes=[_diag_scalar(c) for c in classes],
            positive_class_index=EXTRACTION_INDEX,
            registry_sha256=getattr(registry, "registry_sha256", None),
            cd_decision_id=record.decision_id,
            cd_evidence_record=record.evidence_record,
        ),
    )


def _safe_repr(value: Any) -> str:
    try:
        text = repr(value)
    except Exception:  # pragma: no cover - exotic __repr__
        text = f"<{type(value).__name__}>"
    return text[:200]


def _fallback_error_result(
    *, pair: Any, timeframe: Any, bar_time: Optional[datetime], clock: Any, exception_name: str
) -> PredictionResult:
    """Spec §5.6 last-resort result — literal None values only, cannot fail the same invariant."""
    timestamp = None
    if clock is not None and callable(getattr(clock, "now", None)):
        try:
            timestamp = clock.now()
        except Exception:  # pragma: no cover - defensive
            timestamp = None
    return PredictionResult(
        status=PredictionStatus.ERROR,
        reason=PredictionReason.EXECUTION_ERROR,
        pair=pair if isinstance(pair, str) and pair else "UNKNOWN",
        timeframe=timeframe if isinstance(timeframe, str) and timeframe else "UNKNOWN",
        bar_time=bar_time,
        direction=_DIRECTION_NONE,
        raw_probability=None,
        positive_class_label=None,
        p_up=None,
        p_not_up=None,
        p_down=None,
        timestamp=timestamp,
        diagnostics={
            "failure_category": "INTERNAL_INVARIANT_VIOLATION",
            "exception_type": exception_name,
        },
    )


# ─────────────────────────── public entry points ────────────────────────────
def run_prediction(
    *,
    model: Any,
    scaler: Any,
    feature_list: Sequence[str],
    X: Any,
    pair: str,
    timeframe: str,
    bar_time: datetime,
    clock: Clock,
    registry: Optional[CDRegistryHandle] = None,
    identity: Optional[LoadedModelIdentity] = None,
    model_status: Optional[str] = None,
    diagnostics: Optional[Mapping[str, Any]] = None,
) -> PredictionResult:
    """Convert one inference attempt into an immutable ``PredictionResult``.

    Inference-time failures always return a result (spec §6.2). Only pre-inference
    API contract violations raise: invalid required argument, invalid injection,
    wrong mandatory argument type, or a naive ``bar_time`` (spec §6.4).
    """
    if not isinstance(pair, str) or not pair:
        raise PredictionAdapterContractError("pair must be a non-empty string")
    if not isinstance(timeframe, str) or not timeframe:
        raise PredictionAdapterContractError("timeframe must be a non-empty string")
    _require_clock(clock)
    bar_time_utc = _to_utc(bar_time, field_name="bar_time")

    try:
        return _evaluate(
            model=model,
            scaler=scaler,
            feature_list=feature_list,
            X=X,
            pair=pair,
            timeframe=timeframe,
            bar_time=bar_time_utc,
            clock=clock,
            registry=registry,
            identity=identity,
            model_status=model_status,
            diagnostics=diagnostics,
        )
    except PredictionResultInvariantError as exc:  # adapter bug → §5.6 last-resort
        return _fallback_error_result(
            pair=pair,
            timeframe=timeframe,
            bar_time=bar_time_utc,
            clock=clock,
            exception_name=type(exc).__name__,
        )


def build_not_run_result(
    *,
    pair: str,
    timeframe: str,
    bar_time: Optional[datetime],
    clock: Clock,
    diagnostics: Optional[Mapping[str, Any]] = None,
) -> PredictionResult:
    """Pure NOT_RUN helper (spec §9.2) — no inference, no bars-threshold read.

    The caller that owns bar history decides the invocation; this helper only
    constructs a legal ``NOT_RUN / INPUT_INSUFFICIENT`` result. Wiring it into the
    caller is Stage C.
    """
    if not isinstance(pair, str) or not pair:
        raise PredictionAdapterContractError("pair must be a non-empty string")
    if not isinstance(timeframe, str) or not timeframe:
        raise PredictionAdapterContractError("timeframe must be a non-empty string")
    _require_clock(clock)
    bar_time_utc = _to_utc(bar_time, field_name="bar_time", allow_none=True)
    return _construct_result(
        status=PredictionStatus.NOT_RUN,
        reason=PredictionReason.INPUT_INSUFFICIENT,
        pair=pair,
        timeframe=timeframe,
        bar_time=bar_time_utc,
        direction=_DIRECTION_NONE,
        timestamp=clock.now(),
        diagnostics=dict(diagnostics) if diagnostics else {},
    )
