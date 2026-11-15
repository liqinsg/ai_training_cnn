# tests/test_prediction_adapter.py — PHASE 3.1 STAGE B PREDICTION ADAPTER TESTS
#
# Traceability to spec docs/PHASE3_1_STAGE_B_STRICT_SPEC.md §16 (B-T01…B-T76).
# All fixtures live under tmp_path. The production CD registry
# (config/model_cd_registry.json) is NEVER written by these tests (§16.8).
#
# No live OANDA account and no real model training are required. Artifact-identity
# tests use the exact accepted artifact hashes where the matrix asks for them, and
# otherwise use in-memory fakes — mock CD matches prove adapter logic only, never
# real artifact semantics (§16.8).

import builtins
import dataclasses
import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import numpy as np
import pytest

from ml import prediction_adapter as pa
from ml.prediction_adapter import (
    CDRecord,
    CDRegistryHandle,
    Clock,
    COMPLEMENT_TOLERANCE,
    DECISION_THRESHOLD,
    EXTRACTION_INDEX,
    LoadedModelIdentity,
    PredictionAdapterContractError,
    PredictionReason,
    PredictionResult,
    PredictionResultInvariantError,
    PredictionStatus,
    ROW_SUM_TOLERANCE,
    bind_loaded_identity,
    build_not_run_result,
    load_model_with_identity,
    run_prediction,
)

# Exact accepted artifact fingerprints (docs/PHASE3_1_CD_EVIDENCE.md §A).
ARTIFACT_HASH = "94c8751df33daee5190e42634d823bcb08d4a0dbc1e0a2cf2f3e8cfbd91d5942"
SCALER_HASH = "031ea8068a2b8309829624b30acb7db2cde40ce4452240cf423619fae4b2cd8c"

FIXED_NOW = datetime(2026, 11, 15, 12, 0, 0, tzinfo=timezone.utc)
FEATURE_LIST = ["f1", "f2", "f3"]

_REPO_ROOT = Path(pa.__file__).resolve().parents[1]


# ─────────────────────────────── helpers ────────────────────────────────────
class FakeClock(Clock):
    def __init__(self, now=FIXED_NOW):
        self._now = now

    def now(self):
        return self._now


class FakeScaler:
    def __init__(self, n_features=3):
        self.n_features_in_ = n_features

    def transform(self, X):
        return np.asarray(X, dtype=float)


class FakeModel:
    """Minimal predict_proba stand-in; `classes=None` omits the `classes_` attribute."""

    def __init__(self, proba, classes=(0, 1), exc=None):
        if classes is not None:
            self.classes_ = np.asarray(classes)
        self._proba = proba
        self._exc = exc
        self.calls = 0

    def predict_proba(self, X):
        self.calls += 1
        if self._exc is not None:
            raise self._exc
        return self._proba


def valid_proba(p_up=0.73):
    return np.array([[1.0 - p_up, p_up]])


def obj_proba(cell):
    arr = np.empty((1, 2), dtype=object)
    arr[0, 0] = 0.27
    arr[0, 1] = cell
    return arr


def make_identity(model, scaler, artifact_hash=ARTIFACT_HASH, scaler_hash=SCALER_HASH, clock=None):
    return LoadedModelIdentity(
        artifact_sha256=artifact_hash,
        scaler_sha256=scaler_hash,
        model_instance=model,
        scaler_instance=scaler,
        load_timestamp=(clock or FakeClock()).now(),
        source_path="<in-memory>",
        load_method="BYTES",
    )


def make_record(**over):
    base = dict(
        artifact_sha256=ARTIFACT_HASH,
        scaler_sha256=SCALER_HASH,
        decision="VERIFIED",
        positive_class_label=1,
        positive_class_index=1,
        positive_class_semantics="UP",
        negative_class_semantics="NOT_UP",
        probability_semantics="BINARY_EXCLUSIVE_EXHAUSTIVE",
        evidence_record="docs/PHASE3_1_CD_EVIDENCE.md",
        evidence_record_version="Live Host Evidence (arm / 2026-11-14)",
        decision_id="CD-OPEN-1: SELL = not-UP (accepted 2026-11-14)",
    )
    base.update(over)
    return CDRecord(**base)


def make_handle(records, sha="c" * 64):
    return CDRegistryHandle(list(records), sha, source_path="<test-registry>")


def run(**over):
    """Invoke the adapter with a valid default context; override any keyword."""
    model = over.pop("model", FakeModel(valid_proba()))
    scaler = over.pop("scaler", FakeScaler())
    kwargs = dict(
        model=model,
        scaler=scaler,
        feature_list=FEATURE_LIST,
        X=np.array([1.0, 2.0, 3.0]),
        pair="EUR_USD",
        timeframe="1H",
        bar_time=FIXED_NOW,
        clock=FakeClock(),
        registry=over.pop("registry", make_handle([make_record()])),
        identity=over.pop("identity", make_identity(model, scaler)),
        model_status=over.pop("model_status", "READY"),
        diagnostics=over.pop("diagnostics", None),
    )
    kwargs.update(over)
    return run_prediction(**kwargs)


def _adapter_source():
    return Path(pa.__file__).read_text(encoding="utf-8")


def _read(relative):
    return (_REPO_ROOT / relative).read_text(encoding="utf-8")


def _stub_caller(bar_count, minimum, clock):
    """Stubbed bars-precondition owner; the adapter is only reached when bars suffice."""
    if bar_count < minimum:
        return build_not_run_result(pair="EUR_USD", timeframe="1H", bar_time=None, clock=clock)
    raise AssertionError("inference path is out of scope for this stub")


class SpyRegistry(CDRegistryHandle):
    def __init__(self, records, sha="c" * 64):
        super().__init__(list(records), sha, source_path="<spy>")
        self.lookups = 0

    def lookup(self, artifact_sha256, scaler_sha256):
        self.lookups += 1
        return super().lookup(artifact_sha256, scaler_sha256)


# ═══════════════════════ 16.1 Core adapter tests ════════════════════════════
def test_B_T01_stubbed_caller_emits_not_run_and_adapter_not_invoked(monkeypatch):
    invoked = {"n": 0}

    def _spy(*args, **kwargs):
        invoked["n"] += 1
        raise AssertionError("adapter must not be invoked")

    monkeypatch.setattr(pa, "_evaluate", _spy)
    result = _stub_caller(bar_count=3, minimum=20, clock=FakeClock())

    assert result.status == PredictionStatus.NOT_RUN
    assert result.reason == PredictionReason.INPUT_INSUFFICIENT
    assert result.direction == "NONE"
    assert result.raw_probability is None and result.p_up is None and result.p_not_up is None
    assert result.p_down is None
    assert result.timestamp == FIXED_NOW
    assert invoked["n"] == 0
    # bar_time may be None for NOT_RUN when the caller genuinely has none (§5.4.7)
    assert result.bar_time is None


def test_B_T02_model_unavailable():
    result = run(model=None, identity=None)
    assert (result.status, result.reason) == (PredictionStatus.UNAVAILABLE, PredictionReason.MODEL_NOT_USABLE)


def test_B_T02b_model_status_unusable_maps_to_unavailable():
    result = run(model_status="LOAD_FAILED")
    assert (result.status, result.reason) == (PredictionStatus.UNAVAILABLE, PredictionReason.MODEL_NOT_USABLE)


def test_B_T03_required_scaler_missing_none():
    result = run(scaler=None)
    assert (result.status, result.reason) == (PredictionStatus.UNAVAILABLE, PredictionReason.MODEL_NOT_USABLE)


def test_B_T04_feature_contract_invalid():
    result = run(X=np.array([1.0, 2.0]))  # too few columns for the feature list
    assert (result.status, result.reason) == (
        PredictionStatus.INVALID,
        PredictionReason.FEATURE_CONTRACT_VIOLATION,
    )


def test_B_T05_unexpected_inference_exception_is_error():
    result = run(model=FakeModel(None, exc=RuntimeError("boom")))
    assert (result.status, result.reason) == (PredictionStatus.ERROR, PredictionReason.EXECUTION_ERROR)
    assert result.diagnostics["exception_type"] == "RuntimeError"


@pytest.mark.parametrize(
    "proba",
    [
        np.array([0.27, 0.73]),                       # 1-D
        np.array([[0.27, 0.73], [0.3, 0.7]]),         # two rows
        np.array(0.73),                               # 0-D
    ],
)
def test_B_T06_malformed_output_structure(proba):
    result = run(model=FakeModel(proba))
    assert (result.status, result.reason) == (
        PredictionStatus.INVALID,
        PredictionReason.PREDICTION_OUTPUT_MALFORMED,
    )


def test_B_T07_probability_column_count_differs_from_classes():
    result = run(model=FakeModel(np.array([[0.2, 0.3, 0.5]]), classes=(0, 1)))
    assert (result.status, result.reason) == (
        PredictionStatus.INVALID,
        PredictionReason.PREDICTION_OUTPUT_MALFORMED,
    )


@pytest.mark.parametrize("classes", [None, (0,), (0, 1, 2), (1, 1)])
def test_B_T08_classes_missing_wrong_length_or_duplicate(classes):
    result = run(model=FakeModel(valid_proba(), classes=classes))
    assert (result.status, result.reason) == (
        PredictionStatus.INVALID,
        PredictionReason.PREDICTION_OUTPUT_MALFORMED,
    )


@pytest.mark.parametrize("cell", [float("nan"), float("inf"), float("-inf"), -0.01, 1.01])
def test_B_T09_T12_invalid_candidate_numeric(cell):
    result = run(model=FakeModel(np.array([[0.27, cell]])))
    assert (result.status, result.reason) == (
        PredictionStatus.INVALID,
        PredictionReason.PREDICTION_INVALID_PROBABILITY,
    )
    assert result.raw_probability is None


def test_B_T13_valid_extraction_without_registry_record_is_uninterpretable():
    result = run(registry=make_handle([make_record(artifact_sha256="a" * 64)]))
    assert result.status == PredictionStatus.UNINTERPRETABLE
    assert result.reason == PredictionReason.CLASS_DEFINITION_UNVERIFIED
    assert result.raw_probability == pytest.approx(0.73)
    assert result.p_up is None and result.p_not_up is None
    assert result.diagnostics["cd_failure_cause"] == "RECORD_MISSING"


def test_B_T14_exact_artifact_and_scaler_hashes_match_registry():
    result = run()
    assert result.status == PredictionStatus.READY
    assert result.diagnostics["cd_decision_id"].startswith("CD-OPEN-1")


def test_B_T15_artifact_hash_mismatch_no_cd_inheritance():
    identity = make_identity(FakeModel(valid_proba()), FakeScaler(), artifact_hash="f" * 64)
    result = run(identity=identity)
    assert result.status == PredictionStatus.UNINTERPRETABLE
    assert result.diagnostics["cd_failure_cause"] == "RECORD_MISSING"
    assert result.p_up is None and result.direction == "NONE"


def test_B_T16_artifact_hash_unavailable():
    result = run(identity=None)
    assert result.status == PredictionStatus.UNINTERPRETABLE
    assert result.raw_probability == pytest.approx(0.73)
    assert result.diagnostics["cd_failure_cause"] == "HASH_UNAVAILABLE"


@pytest.mark.parametrize(
    "p_up,direction,at_threshold",
    [(0.73, "BUY", False), (0.51, "BUY", False), (0.50, "SELL", True), (0.49, "SELL", False)],
)
def test_B_T17_T20_direction_threshold_matrix(p_up, direction, at_threshold):
    result = run(model=FakeModel(valid_proba(p_up)))
    assert result.status == PredictionStatus.READY
    assert result.direction == direction
    assert result.p_up == pytest.approx(p_up)
    assert result.p_not_up == pytest.approx(1.0 - p_up, abs=1e-6)
    assert result.diagnostics["at_threshold"] is at_threshold


def test_B_T21_numeric_positive_class_label_preserved():
    result = run()
    assert result.positive_class_label == 1
    assert isinstance(result.positive_class_label, int)


def test_B_T22_non_ready_results_expose_no_usable_direction():
    results = [
        run(model=None, identity=None),
        run(model=FakeModel(None, exc=RuntimeError("x"))),
        run(X=np.array([1.0, 2.0])),
        run(identity=None),
        build_not_run_result(pair="EUR_USD", timeframe="1H", bar_time=FIXED_NOW, clock=FakeClock()),
    ]
    for result in results:
        assert result.status != PredictionStatus.READY
        assert result.direction == "NONE"


def test_B_T23_ready_with_none_direction_is_rejected():
    with pytest.raises(PredictionResultInvariantError):
        PredictionResult(
            status=PredictionStatus.READY,
            reason=PredictionReason.NONE,
            pair="EUR_USD",
            timeframe="1H",
            bar_time=FIXED_NOW,
            direction="NONE",
            raw_probability=0.6,
            positive_class_label=1,
            p_up=0.6,
            p_not_up=0.4,
            model_artifact_hash=ARTIFACT_HASH,
            timestamp=FIXED_NOW,
            diagnostics={"at_threshold": False},
        )


def test_B_T24_p_down_is_never_populated():
    result = run()
    assert result.p_down is None
    assert "p_down" not in result.diagnostics


def test_B_T25_formal_identity_fields_are_none():
    result = run()
    assert result.model_id is None
    assert result.release_id is None
    assert result.feature_contract_id is None


def test_B_T26_injected_clock_yields_deterministic_timestamp():
    stamp = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    result = run(clock=FakeClock(stamp))
    assert result.timestamp == stamp
    assert result.bar_time == FIXED_NOW  # bar time is not replaced by prediction time


def test_B_T27_adapter_failure_is_contained_and_isolated():
    result = run(model=FakeModel(None, exc=RuntimeError("boom")))
    assert isinstance(result, PredictionResult)
    assert (result.status, result.reason) == (PredictionStatus.ERROR, PredictionReason.EXECUTION_ERROR)

    source = _adapter_source()
    for forbidden in ("strategy_decision", "oanda_execution", "trading_bot", "fx_trade_bot", "attribution"):
        assert forbidden not in source


def test_B_T28_generate_signal_signature_and_behaviour_unchanged():
    source = _read("strategy_decision.py")
    assert "def generate_signal(" in source
    for fragment in (
        "pair: str,",
        "oanda_symbol: str,",
        "df: pd.DataFrame,",
        "mc_data: Optional[dict],",
        "strength_scores: dict,",
        "current_price: float,",
        "spread_pips: float,",
        ") -> Optional[Signal]:",
    ):
        assert fragment in source
    assert "Direction.LONG if p_up > p_down else Direction.SHORT" in source


def test_B_T29_c1_through_c7_not_migrated_by_the_adapter():
    source = _adapter_source()
    for consumer in (
        "fx_trade_bot",
        "attribution_v2",
        "live_hook",
        "data_bridge",
        "strategy_decision",
        "should_close",
        "select_signals",
    ):
        assert consumer not in source


def test_B_T30_no_abstain_construction_path():
    source = _adapter_source()
    assert "ABSTAIN = " in source                      # the enum member remains (§12.3)
    assert "status=PredictionStatus.ABSTAIN" not in source
    assert "ABSTAIN_BY_PREDICTION_RULE)" not in source  # never passed as a reason argument


# ═══════════ 16.2 Type, order, time, registry and identity edge cases ═══════
class _NumericLike:
    def __float__(self):
        return 0.7


@pytest.mark.parametrize(
    "cell",
    [
        True,                     # B-T31 Python bool
        np.bool_(True),           # B-T32 NumPy boolean scalar
        np.array(0.7),            # B-T34 NumPy 0-D array
        np.array([0.7]),          # B-T35 1-D array
        np.array([[0.7]]),        # B-T35 2-D array
        Decimal("0.7"),           # B-T36 finite in-range Decimal
        Decimal("NaN"),           # B-T37 Decimal NaN
        Decimal("Infinity"),      # B-T37 Decimal infinity
        complex(0.7, 0.0),        # B-T38 complex
        "0.7",                    # B-T39 string
        _NumericLike(),           # B-T40 unsupported custom numeric object
    ],
)
def test_B_T31_T40_rejected_probability_types(cell):
    result = run(model=FakeModel(obj_proba(cell)))
    assert (result.status, result.reason) == (
        PredictionStatus.INVALID,
        PredictionReason.PREDICTION_INVALID_PROBABILITY,
    )
    assert result.raw_probability is None


@pytest.mark.parametrize("dtype", [np.float32, np.float64, np.int64])
def test_B_T33_numpy_scalars_accepted_when_finite_and_in_range(dtype):
    if dtype is np.int64:
        proba = np.array([[0, 1]], dtype=np.int64)
    else:
        proba = np.array([[0.27, 0.73]], dtype=dtype)
    result = run(model=FakeModel(proba))
    assert result.status == PredictionStatus.READY
    assert isinstance(result.raw_probability, float)


def test_B_T41_model_unavailable_wins_over_invalid_input():
    result = run(model=None, identity=None, X=np.array([1.0, 2.0]))
    assert (result.status, result.reason) == (PredictionStatus.UNAVAILABLE, PredictionReason.MODEL_NOT_USABLE)


class _CustomInferenceError(Exception):
    pass


def test_B_T42_unknown_inference_exception_is_error():
    result = run(model=FakeModel(None, exc=_CustomInferenceError("x")))
    assert (result.status, result.reason) == (PredictionStatus.ERROR, PredictionReason.EXECUTION_ERROR)
    assert result.diagnostics["exception_type"] == "_CustomInferenceError"


class _UnfittedScaler:
    def transform(self, X):
        return np.asarray(X, dtype=float)


def test_B_T43_known_model_usability_exception_is_unavailable():
    scaler = _UnfittedScaler()
    result = run(scaler=scaler, identity=make_identity(FakeModel(valid_proba()), scaler))
    assert (result.status, result.reason) == (PredictionStatus.UNAVAILABLE, PredictionReason.MODEL_NOT_USABLE)


def test_B_T44_naive_bar_time_raises_before_inference():
    model = FakeModel(valid_proba())
    with pytest.raises(PredictionAdapterContractError):
        run(model=model, bar_time=datetime(2026, 1, 1, 12, 0, 0))
    assert model.calls == 0


def test_B_T45_non_utc_aware_bar_time_is_normalized_to_utc():
    tz = timezone(timedelta(hours=5))
    bar_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=tz)
    result = run(bar_time=bar_time)
    assert result.bar_time.tzinfo == timezone.utc
    assert result.bar_time == bar_time.astimezone(timezone.utc)


def test_B_T46_prediction_result_mutation_attempt_rejected():
    result = run()
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.status = PredictionStatus.ERROR


def test_B_T47_registry_duplicate_entries_fail_closed():
    result = run(registry=make_handle([make_record(), make_record()]))
    assert result.status == PredictionStatus.UNINTERPRETABLE
    assert result.diagnostics["cd_failure_cause"] == "RECORD_DUPLICATE"


def test_B_T48_registry_missing_file_fails_closed(tmp_path):
    handle = CDRegistryHandle.load(tmp_path / "does_not_exist.json")
    assert handle.ok is False and handle.error
    result = run(registry=handle)
    assert result.status == PredictionStatus.UNINTERPRETABLE
    assert result.diagnostics["cd_failure_cause"] == "REGISTRY_UNAVAILABLE"


def test_B_T48b_registry_malformed_json_fails_closed(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text("{ this is not json", encoding="utf-8")
    handle = CDRegistryHandle.load(path)
    assert handle.ok is False
    result = run(registry=handle)
    assert result.status == PredictionStatus.UNINTERPRETABLE
    assert result.diagnostics["cd_failure_cause"] == "REGISTRY_UNAVAILABLE"


def test_B_T49_loader_consumes_the_hashed_bytes(tmp_path):
    model_file = tmp_path / "model.json"
    scaler_file = tmp_path / "scaler.joblib"
    original = b"ORIGINAL-MODEL-BYTES"
    model_file.write_bytes(original)
    scaler_file.write_bytes(b"SCALER-BYTES")

    captured = {}

    def model_loader(raw):
        captured["model"] = raw
        return object()

    def scaler_loader(raw):
        captured["scaler"] = raw
        return object()

    def swap_on_disk():
        model_file.write_bytes(b"SWAPPED-BYTES-AFTER-READ")

    identity = load_model_with_identity(
        model_path=model_file,
        scaler_path=scaler_file,
        clock=FakeClock(),
        model_loader=model_loader,
        scaler_loader=scaler_loader,
        after_read_hook=swap_on_disk,
    )

    assert captured["model"] == original
    assert identity.artifact_sha256 == hashlib.sha256(original).hexdigest()
    assert model_file.read_bytes() == b"SWAPPED-BYTES-AFTER-READ"


def test_B_T50_registry_sha256_and_git_revision_recorded(tmp_path):
    path = tmp_path / "registry.json"
    record = make_record()
    payload = {"schema_version": 1, "records": [{k: getattr(record, k) for k in CDRecord.FIELDS}]}
    raw = json.dumps(payload).encode("utf-8")
    path.write_bytes(raw)

    handle = CDRegistryHandle.load(path)
    assert handle.ok is True
    assert handle.registry_sha256 == hashlib.sha256(raw).hexdigest()
    assert len(handle.records) == 1
    assert handle.records[0].positive_class_label == 1


# ═══════════════════ 16.3 CD binding and ordering ══════════════════════════
def test_B_T51_registry_positive_class_index_mismatch():
    result = run(registry=make_handle([make_record(positive_class_index=0)]))
    assert result.status == PredictionStatus.UNINTERPRETABLE
    assert result.diagnostics["cd_failure_cause"] == "INDEX_MISMATCH"


def test_B_T52_runtime_label_disagrees_with_registry():
    result = run(model=FakeModel(valid_proba(), classes=(1, 0)))
    assert result.status == PredictionStatus.UNINTERPRETABLE
    assert result.diagnostics["cd_failure_cause"] == "LABEL_MISMATCH"


def test_B_T53_runtime_bool_label_is_label_mismatch():
    # object dtype preserves the Python bool; a mixed int array would coerce True -> 1.
    classes = np.array([0, True], dtype=object)
    result = run(model=FakeModel(valid_proba(), classes=classes))
    assert result.diagnostics["cd_failure_cause"] == "LABEL_MISMATCH"


@pytest.mark.parametrize("label", ["1", 1.0])
def test_B_T54_runtime_string_or_float_label_is_label_mismatch(label):
    classes = np.array([0, label], dtype=object)
    result = run(model=FakeModel(valid_proba(), classes=classes))
    assert result.diagnostics["cd_failure_cause"] == "LABEL_MISMATCH"


def test_B_T55_registry_decision_not_verified():
    result = run(registry=make_handle([make_record(decision="REVOKED")]))
    assert result.status == PredictionStatus.UNINTERPRETABLE
    assert result.diagnostics["cd_failure_cause"] == "DECISION_NOT_VERIFIED"


@pytest.mark.parametrize(
    "override",
    [
        {"positive_class_semantics": "DOWN"},
        {"negative_class_semantics": "UP"},
        {"probability_semantics": "LOGITS"},
    ],
)
def test_B_T56_unsupported_registry_semantics(override):
    result = run(registry=make_handle([make_record(**override)]))
    assert result.status == PredictionStatus.UNINTERPRETABLE
    assert result.diagnostics["cd_failure_cause"] == "SEMANTICS_UNSUPPORTED"


def test_B_T57_valid_candidate_with_nan_complement_is_invalid():
    result = run(model=FakeModel(np.array([[float("nan"), 0.73]])))
    assert (result.status, result.reason) == (
        PredictionStatus.INVALID,
        PredictionReason.PREDICTION_INVALID_PROBABILITY,
    )
    assert result.raw_probability is None


def test_B_T58_row_sum_beyond_tolerance_is_malformed():
    result = run(model=FakeModel(np.array([[0.10, 0.73]])))  # sums to 0.83
    assert (result.status, result.reason) == (
        PredictionStatus.INVALID,
        PredictionReason.PREDICTION_OUTPUT_MALFORMED,
    )


def test_B_T59_registry_is_not_read_before_step_six():
    structure_spy = SpyRegistry([make_record()])
    structure_failure = run(model=FakeModel(np.array([0.27, 0.73])), registry=structure_spy)
    assert structure_failure.reason == PredictionReason.PREDICTION_OUTPUT_MALFORMED
    assert structure_spy.lookups == 0

    numeric_spy = SpyRegistry([make_record()])
    numeric_failure = run(model=FakeModel(np.array([[float("nan"), 0.73]])), registry=numeric_spy)
    assert numeric_failure.reason == PredictionReason.PREDICTION_INVALID_PROBABILITY
    assert numeric_spy.lookups == 0

    success_spy = SpyRegistry([make_record()])
    success = run(registry=success_spy)
    assert success.status == PredictionStatus.READY
    assert success_spy.lookups == 1


def test_B_T60_invalid_probability_wins_over_missing_registry_record():
    result = run(model=FakeModel(np.array([[0.27, float("nan")]])), registry=make_handle([]))
    assert (result.status, result.reason) == (
        PredictionStatus.INVALID,
        PredictionReason.PREDICTION_INVALID_PROBABILITY,
    )


# ═══════════════════════════ 16.4 Loader binding ═══════════════════════════
def _load_pair(model_bytes, scaler_bytes, directory):
    model_file = directory / "m.json"
    scaler_file = directory / "s.joblib"
    model_file.write_bytes(model_bytes)
    scaler_file.write_bytes(scaler_bytes)
    return load_model_with_identity(
        model_path=model_file,
        scaler_path=scaler_file,
        clock=FakeClock(),
        model_loader=lambda raw: object(),
        scaler_loader=lambda raw: object(),
    )


def test_B_T61_one_bit_change_changes_hash_and_breaks_cd_match(tmp_path):
    identity_a = _load_pair(b"\x00\x01\x02", b"SCALER", tmp_path)
    identity_b = _load_pair(b"\x00\x01\x03", b"SCALER", tmp_path)
    assert identity_a.artifact_sha256 != identity_b.artifact_sha256

    registry = make_handle(
        [make_record(artifact_sha256=identity_a.artifact_sha256, scaler_sha256=identity_a.scaler_sha256)]
    )
    result = run(identity=identity_b, registry=registry)
    assert result.status == PredictionStatus.UNINTERPRETABLE
    assert result.diagnostics["cd_failure_cause"] == "RECORD_MISSING"


def test_B_T62_malformed_artifact_produces_no_identity(tmp_path):
    model_file = tmp_path / "m.json"
    scaler_file = tmp_path / "s.joblib"
    model_file.write_bytes(b"not-an-xgboost-model")
    scaler_file.write_bytes(b"not-a-scaler")

    with pytest.raises(Exception):
        load_model_with_identity(model_path=model_file, scaler_path=scaler_file, clock=FakeClock())

    # No identity is produced, so the adapter classifies the model as unusable.
    result = run(model=None, identity=None)
    assert (result.status, result.reason) == (PredictionStatus.UNAVAILABLE, PredictionReason.MODEL_NOT_USABLE)


def test_B_T63_identity_fields_cannot_be_reassigned():
    identity = make_identity(FakeModel(valid_proba()), FakeScaler())
    with pytest.raises(dataclasses.FrozenInstanceError):
        identity.artifact_sha256 = "0" * 64


@pytest.mark.parametrize("bad", ["abc", "Z" * 64, "A" * 64, "0" * 63, "0" * 65, None, 123, b"0" * 64])
def test_B_T64_identity_hash_must_be_64_lowercase_hex(bad):
    with pytest.raises(ValueError):
        LoadedModelIdentity(
            artifact_sha256=bad,
            scaler_sha256=SCALER_HASH,
            model_instance=None,
            scaler_instance=None,
            load_timestamp=FIXED_NOW,
        )


def test_B_T65_adapter_performs_no_filesystem_read(monkeypatch):
    def _forbidden(*args, **kwargs):
        raise AssertionError("the adapter must not read the filesystem")

    monkeypatch.setattr(builtins, "open", _forbidden)
    result = run()
    assert result.status == PredictionStatus.READY


# ═════════════════ 16.4b SC-02 path A: bind already-read bytes ═══════════════
# ``bind_loaded_identity`` ties the SHA-256 of the *already-read* bytes to the
# *already-wired* instances (production loaded-instance provenance). It must do no
# I/O and construct nothing — the caller guarantees the instances came from those
# bytes in a single read.
def test_sc02_bind_loaded_identity_hashes_the_pre_read_bytes():
    model_bytes = b"PRE-READ-MODEL-BYTES"
    scaler_bytes = b"PRE-READ-SCALER-BYTES"
    model = FakeModel(valid_proba())
    scaler = FakeScaler()

    identity = bind_loaded_identity(
        model_bytes=model_bytes,
        scaler_bytes=scaler_bytes,
        model_instance=model,
        scaler_instance=scaler,
        clock=FakeClock(),
    )

    assert identity.artifact_sha256 == hashlib.sha256(model_bytes).hexdigest()
    assert identity.scaler_sha256 == hashlib.sha256(scaler_bytes).hexdigest()
    assert identity.model_instance is model
    assert identity.scaler_instance is scaler
    assert identity.load_timestamp == FIXED_NOW


def test_sc02_bind_loaded_identity_normalizes_source_path_and_load_method():
    identity = bind_loaded_identity(
        model_bytes=b"m",
        scaler_bytes=b"s",
        model_instance=object(),
        scaler_instance=object(),
        clock=FakeClock(),
        source_path=Path("/tmp/model.json"),
        load_method="TEMPFILE",
    )
    assert identity.source_path == "/tmp/model.json"
    assert isinstance(identity.source_path, str)
    assert identity.load_method == "TEMPFILE"


def test_sc02_bind_loaded_identity_defaults_source_path_to_none():
    identity = bind_loaded_identity(
        model_bytes=b"m",
        scaler_bytes=b"s",
        model_instance=object(),
        scaler_instance=object(),
        clock=FakeClock(),
    )
    assert identity.source_path is None
    assert identity.load_method == "BYTES"


def test_sc02_bind_loaded_identity_accepts_bytearray():
    model_bytes = bytearray(b"BYTEARRAY-MODEL")
    identity = bind_loaded_identity(
        model_bytes=model_bytes,
        scaler_bytes=bytearray(b"BYTEARRAY-SCALER"),
        model_instance=object(),
        scaler_instance=object(),
        clock=FakeClock(),
    )
    assert identity.artifact_sha256 == hashlib.sha256(bytes(model_bytes)).hexdigest()


@pytest.mark.parametrize("bad", ["not-bytes", None, 123, ["b"]])
def test_sc02_bind_loaded_identity_rejects_non_bytes(bad):
    with pytest.raises(PredictionAdapterContractError):
        bind_loaded_identity(
            model_bytes=bad,
            scaler_bytes=b"scaler",
            model_instance=object(),
            scaler_instance=object(),
            clock=FakeClock(),
        )


def test_sc02_bind_loaded_identity_requires_a_clock():
    with pytest.raises(PredictionAdapterContractError):
        bind_loaded_identity(
            model_bytes=b"m",
            scaler_bytes=b"s",
            model_instance=object(),
            scaler_instance=object(),
            clock=None,
        )


def test_sc02_bind_loaded_identity_performs_no_io(monkeypatch):
    def _forbidden(*args, **kwargs):
        raise AssertionError("bind_loaded_identity must not perform any I/O")

    monkeypatch.setattr(builtins, "open", _forbidden)
    identity = bind_loaded_identity(
        model_bytes=b"m",
        scaler_bytes=b"s",
        model_instance=object(),
        scaler_instance=object(),
        clock=FakeClock(),
    )
    assert identity.artifact_sha256 == hashlib.sha256(b"m").hexdigest()


def test_B_T75_scaler_hash_mismatch_breaks_cd_match():
    identity = make_identity(FakeModel(valid_proba()), FakeScaler(), scaler_hash="d" * 64)
    result = run(identity=identity)
    assert result.status == PredictionStatus.UNINTERPRETABLE
    assert result.diagnostics["cd_failure_cause"] == "RECORD_MISSING"


def test_B_T76_record_without_scaler_hash_fails_closed():
    result = run(registry=make_handle([make_record(scaler_sha256=None)]))
    assert result.status == PredictionStatus.UNINTERPRETABLE
    assert result.diagnostics["cd_failure_cause"] == "RECORD_MISSING"


# ═══════════════════════════ 16.5 Result integrity ═════════════════════════
def _ready_kwargs(**over):
    kwargs = dict(
        status=PredictionStatus.READY,
        reason=PredictionReason.NONE,
        pair="EUR_USD",
        timeframe="1H",
        bar_time=FIXED_NOW,
        direction="BUY",
        raw_probability=0.7,
        positive_class_label=1,
        p_up=0.7,
        p_not_up=0.3,
        model_artifact_hash=ARTIFACT_HASH,
        timestamp=FIXED_NOW,
        diagnostics={"at_threshold": False},
    )
    kwargs.update(over)
    return kwargs


def test_B_T66_ready_direction_contradicting_p_up_is_rejected():
    with pytest.raises(PredictionResultInvariantError):
        PredictionResult(**_ready_kwargs(p_up=0.4, raw_probability=0.4, p_not_up=0.6, direction="BUY"))


def test_B_T67_ready_raw_probability_must_equal_p_up():
    with pytest.raises(PredictionResultInvariantError):
        PredictionResult(**_ready_kwargs(raw_probability=0.6))


def test_B_T68_uninterpretable_must_not_expose_interpreted_probabilities():
    with pytest.raises(PredictionResultInvariantError):
        PredictionResult(
            status=PredictionStatus.UNINTERPRETABLE,
            reason=PredictionReason.CLASS_DEFINITION_UNVERIFIED,
            pair="EUR_USD",
            timeframe="1H",
            bar_time=FIXED_NOW,
            direction="NONE",
            raw_probability=0.7,
            p_up=0.7,
            p_not_up=0.3,
            timestamp=FIXED_NOW,
        )


def test_B_T69_non_none_p_down_is_rejected_on_any_status():
    with pytest.raises(PredictionResultInvariantError):
        PredictionResult(
            status=PredictionStatus.NOT_RUN,
            reason=PredictionReason.INPUT_INSUFFICIENT,
            pair="EUR_USD",
            timeframe="1H",
            bar_time=FIXED_NOW,
            direction="NONE",
            p_down=0.4,
            timestamp=FIXED_NOW,
        )


def test_B_T70_status_reason_pair_outside_the_closed_set_is_rejected():
    with pytest.raises(PredictionResultInvariantError):
        PredictionResult(**_ready_kwargs(reason=PredictionReason.EXECUTION_ERROR))


def test_B_T71_diagnostics_cannot_be_mutated_after_construction():
    result = run()
    with pytest.raises(TypeError):
        result.diagnostics["injected"] = True


def test_B_T72_non_serializable_diagnostics_value_is_rejected():
    with pytest.raises(PredictionResultInvariantError):
        PredictionResult(
            status=PredictionStatus.NOT_RUN,
            reason=PredictionReason.INPUT_INSUFFICIENT,
            pair="EUR_USD",
            timeframe="1H",
            direction="NONE",
            bar_time=FIXED_NOW,
            timestamp=FIXED_NOW,
            diagnostics={"bad": object()},
        )


def test_B_T73_forced_internal_invariant_violation_returns_fallback(monkeypatch):
    def _boom(**kwargs):
        raise PredictionResultInvariantError("forced")

    monkeypatch.setattr(pa, "_construct_result", _boom)
    result = run()

    assert (result.status, result.reason) == (PredictionStatus.ERROR, PredictionReason.EXECUTION_ERROR)
    assert result.raw_probability is None
    assert result.p_up is None and result.p_not_up is None and result.p_down is None
    assert result.direction == "NONE"
    assert result.diagnostics["failure_category"] == "INTERNAL_INVARIANT_VIOLATION"
    assert result.diagnostics["exception_type"] == "PredictionResultInvariantError"


def test_B_T74_at_threshold_population_matches_the_matrix():
    assert run(model=FakeModel(valid_proba(0.73))).diagnostics["at_threshold"] is False
    assert run(model=FakeModel(valid_proba(0.50))).diagnostics["at_threshold"] is True

    for result in (
        run(model=None, identity=None),
        run(identity=None),
        run(X=np.array([1.0, 2.0])),
        build_not_run_result(pair="EUR_USD", timeframe="1H", bar_time=FIXED_NOW, clock=FakeClock()),
    ):
        assert "at_threshold" not in result.diagnostics


# ═══════════════════════════ 16.7 Static checks ════════════════════════════
def test_static_no_direct_system_clock_calls():
    source = _adapter_source()
    for banned in ("datetime.now(", "datetime.utcnow(", "datetime.today(", "time.time(", "date.today("):
        assert source.count(banned) <= (1 if banned == "datetime.now(" else 0)


def test_static_no_guessed_class_label_default():
    source = _adapter_source()
    assert 'positive_class_label = "UP"' not in source
    assert "positive_class_label=positive_class_label or" not in source


def test_static_constants_match_the_contract():
    assert DECISION_THRESHOLD == 0.5
    assert COMPLEMENT_TOLERANCE == 1e-9
    assert ROW_SUM_TOLERANCE == 1e-5
    assert EXTRACTION_INDEX == 1


def test_static_public_api_surface_is_present():
    for name in (
        "run_prediction",
        "build_not_run_result",
        "load_model_with_identity",
        "bind_loaded_identity",
        "CDRegistryHandle",
        "LoadedModelIdentity",
        "PredictionResult",
    ):
        assert hasattr(pa, name)
