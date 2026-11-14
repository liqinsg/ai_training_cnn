"""
Phase 3.0 — Runtime Containment & Observability (Stage E regression tests).

Scope of this file (see docs/PHASE3_0_IMPLEMENTATION_TASK.md):

  * §3/§4  explicit ML status contract + failure isolation  (fx_trade_bot_ml.py)
  * §5     live artifact write protection                   (data_pipeline.py)
  * §6     host / profile / release observability
  * §7     healthy-path preservation
  * §4.5 / §9.2  the ML-dependent ENTRY path is FROZEN — it is asserted to be
    untouched, never exercised through a fabricated vote.

Deferred by explicit owner decision (Option 2, "Entry Authorization frozen"):
  P3T-09 / P3T-16 / P3T-19 are NOT executed here.  Changing the entry path
  needs the §4.5 checkpoint approval, which was explicitly withheld.  The
  frozen behaviour is instead *pinned* by the boundary tests in
  "Entry-authorisation boundary" below, so an accidental change fails CI.

No network, no OANDA calls, no real orders, no live deployment.

Run:  python -m pytest tests/test_phase3_runtime_containment.py -q
"""

import ast
import importlib.util
import logging
import os
import sys
import types
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import fx_trade_bot_ml as ml  # noqa: E402  (stdlib + pandas only — always importable)

LIVE_BOTS = [BASE_DIR / "fx_trade_bot.py", BASE_DIR / "fx_trade_bot_v685.py"]


# ─── test doubles ───────────────────────────────────────────────────────────
class _FakeModel:
    n_features_in_ = 2


class _FakeScaler:
    n_features_in_ = 2


class _FakeWrapper:
    """Minimal ModelWrapper stand-in: proves the live path never trains/writes."""

    def __init__(self, load_impl=None):
        self.model = None
        self.scaler = None
        self.feature_names = []
        self.read_only = False
        self.load_calls = 0
        self.fit_calls = 0
        self.save_calls = 0
        self._load_impl = load_impl

    def load(self):
        self.load_calls += 1
        if self._load_impl is not None:
            self._load_impl(self)
            return
        self.model = _FakeModel()
        self.scaler = _FakeScaler()
        self.feature_names = ["f1", "f2"]

    def fit(self, *a, **k):  # pragma: no cover - must never run
        self.fit_calls += 1
        raise AssertionError("live runtime must never call fit()")

    def save(self):  # pragma: no cover - must never run
        self.save_calls += 1
        raise AssertionError("live runtime must never call save()")


class _FakeStrategy:
    def __init__(self):
        self.model = None
        self.scaler = None
        self.features = []


# Exception classes that only carry their *name* into fx_trade_bot_ml: the module
# classifies load failures by exception name so it stays free of the heavy
# inference stack.  These local twins reproduce the production names exactly.
class InferenceFeatureError(ValueError):
    pass


class ScalerMissingError(RuntimeError):
    pass


class LiveArtifactWriteError(RuntimeError):
    pass


class XGBoostError(Exception):
    """Twin of xgboost.core.XGBoostError (matched by name only)."""
    pass


def _write_release(tmp_path, tag=b"a"):
    """Create a complete split-release quartet; return the MODEL_PATH the bot uses."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    stem = tmp_path / "trade_model_xgb"
    stem.with_suffix(".json").write_bytes(b"model-" + tag)
    (tmp_path / "scaler.joblib").write_bytes(b"scaler-" + tag)
    stem.with_suffix(".features.json").write_bytes(b"feat-" + tag)
    stem.with_suffix(".cfg.json").write_bytes(b"cfg-" + tag)
    return stem.with_suffix(".pkl")


def _release_hashes(model_path):
    paths = ml.resolve_artifact_paths(model_path)
    return {k: ml.file_sha256(v) for k, v in paths.items() if k != "legacy"}


def _cfg(days=30):
    return types.SimpleNamespace(retrain_every_n_days=days, use_macd=True)


def _ensure(model_path, wrapper, strategy, cfg=None):
    return ml.ensure_model(
        model_path,
        cfg or _cfg(),
        wrapper,
        strategy,
        None,  # fetcher   — unused on the live path
        None,  # feat_engine
        [],    # DEFAULT_PAIRS
        {},    # YAHOO_TO_OANDA
        None,  # cfg callable
        live=True,
        profile="profile2",
    )


# ─── §8.1 initialization tests ──────────────────────────────────────────────
def test_p3t01_ready_records_release_identity(tmp_path):
    """P3T-01 normal approved load → READY + identity recorded."""
    model_path = _write_release(tmp_path)
    wrapper, strategy = _FakeWrapper(), _FakeStrategy()

    result = _ensure(model_path, wrapper, strategy)

    assert result.status == ml.ModelStatus.READY
    assert result.reason == ml.ModelReason.MODEL_READY
    assert result.ok is True
    assert result.profile == "profile2"
    assert result.host_id
    assert result.model_hash and result.scaler_hash and result.features_hash
    # hashes must be the real bytes on disk, not placeholders
    assert result.model_hash == _release_hashes(model_path)["model"]
    assert str(model_path.with_suffix(".json")) == result.artifact_path
    # DEPENDENCY INJECTION: the strategy engine gets the wrapper's own instances
    assert strategy.model is wrapper.model
    assert strategy.scaler is wrapper.scaler
    assert strategy.features is wrapper.feature_names
    assert wrapper.fit_calls == 0 and wrapper.save_calls == 0


def test_p3t02_missing_artifacts_is_unavailable_and_never_trains(tmp_path):
    """P3T-02 model artifact missing → UNAVAILABLE/MODEL_MISSING, no training."""
    wrapper, strategy = _FakeWrapper(), _FakeStrategy()

    result = _ensure(tmp_path / "trade_model_xgb.pkl", wrapper, strategy)

    assert result.status == ml.ModelStatus.UNAVAILABLE
    assert result.reason == ml.ModelReason.MODEL_MISSING
    assert result.ok is False
    assert wrapper.fit_calls == 0 and wrapper.save_calls == 0
    assert wrapper.load_calls == 0
    assert list(tmp_path.iterdir()) == []  # nothing was created/published
    assert wrapper.read_only is True  # defence-in-depth armed by the live path


def test_p3t03_load_raises_expected_error_is_load_failed(tmp_path):
    """P3T-03 model load raises → LOAD_FAILED with the reason recorded."""
    model_path = _write_release(tmp_path)

    def boom(_w):
        raise ValueError("corrupt artifact")

    wrapper = _FakeWrapper(boom)
    result = _ensure(model_path, wrapper, _FakeStrategy())

    assert result.status == ml.ModelStatus.LOAD_FAILED
    assert result.reason == ml.ModelReason.MODEL_LOAD_EXCEPTION
    assert "ValueError" in result.detail


def test_p3t04_incompatible_release_is_rejected(tmp_path):
    """P3T-04/05 model/scaler or feature contract incompatible → INCOMPATIBLE."""
    model_path = _write_release(tmp_path)

    for exc, expect_reason in (
        (InferenceFeatureError("Artifact dimension mismatch"), ml.ModelReason.MODEL_INCOMPATIBLE),
    ):
        def boom(_w, _exc=exc):
            raise _exc

        result = _ensure(model_path, _FakeWrapper(boom), _FakeStrategy())
        assert result.status == ml.ModelStatus.INCOMPATIBLE
        assert result.reason == expect_reason


def test_p3t04b_scaler_missing_after_load_rejects_release(tmp_path):
    """§5.3 scaler missing → the incomplete release is rejected."""
    model_path = _write_release(tmp_path)

    def no_scaler(w):
        w.model = _FakeModel()
        w.feature_names = ["f1", "f2"]
        w.scaler = None

    result = _ensure(model_path, _FakeWrapper(no_scaler), _FakeStrategy())

    assert result.status == ml.ModelStatus.INCOMPATIBLE
    assert result.reason == ml.ModelReason.SCALER_MISSING
    assert result.ok is False


def test_p3t05_feature_contract_mismatch_after_load_is_rejected(tmp_path):
    """§5.3 feature-contract mismatch → reject the release, never predict."""
    model_path = _write_release(tmp_path)

    def no_features(w):
        w.model = _FakeModel()
        w.scaler = _FakeScaler()
        w.feature_names = []

    wrapper, strategy = _FakeWrapper(no_features), _FakeStrategy()
    result = _ensure(model_path, wrapper, strategy)

    assert result.status == ml.ModelStatus.INCOMPATIBLE
    assert result.reason == ml.ModelReason.FEATURE_CONTRACT_MISMATCH
    # nothing was injected into the strategy engine → no fabricated model state
    assert strategy.model is None and strategy.scaler is None


def test_p3t06_stale_artifact_no_retraining(tmp_path):
    """P3T-06 stale artifact → explicit outcome, no runtime retraining."""
    model_path = _write_release(tmp_path)
    old = 1_500_000_000  # far in the past
    for p in ml.resolve_artifact_paths(model_path).values():
        if p.exists():
            os.utime(p, (old, old))

    wrapper = _FakeWrapper()
    result = _ensure(model_path, wrapper, _FakeStrategy(), cfg=_cfg(days=7))

    assert result.status == ml.ModelStatus.UNAVAILABLE
    assert result.reason == ml.ModelReason.MODEL_STALE
    assert wrapper.load_calls == 0  # stale short-circuits before load
    assert wrapper.fit_calls == 0 and wrapper.save_calls == 0


def test_p3t07_legacy_fallback_is_blocked_not_republished(tmp_path):
    """P3T-07 legacy fallback → blocked, never a silent load-and-republish."""
    model_path = _write_release(tmp_path)

    def legacy_blocked(_w):
        raise LiveArtifactWriteError("legacy artifact migration blocked")

    wrapper = _FakeWrapper(legacy_blocked)
    result = _ensure(model_path, wrapper, _FakeStrategy())

    assert result.status == ml.ModelStatus.INCOMPATIBLE
    assert result.reason == ml.ModelReason.LEGACY_FALLBACK_BLOCKED
    assert wrapper.save_calls == 0


# ─── §4 exception-classification targets (name-based, no heavy deps) ────────
def test_xgboost_error_is_classified_as_load_failure(tmp_path):
    """XGBoostError during load → LOAD_FAILED / MODEL_LOAD_EXCEPTION.

    The module classifies by exception *name*, so this is exercised with a twin
    class named XGBoostError — no xgboost install required.
    """
    model_path = _write_release(tmp_path)

    def boom(_w):
        raise XGBoostError("xgboost: invalid model format")

    result = _ensure(model_path, _FakeWrapper(boom), _FakeStrategy())

    assert result.status == ml.ModelStatus.LOAD_FAILED
    assert result.reason == ml.ModelReason.MODEL_LOAD_EXCEPTION
    assert "XGBoostError" in result.detail


def test_missing_inference_dependency_is_classified_as_load_failure(tmp_path):
    """Missing sklearn/xgboost at load → ImportError → LOAD_FAILED, not a crash."""
    model_path = _write_release(tmp_path)

    def boom(_w):
        raise ImportError("No module named 'sklearn'")

    result = _ensure(model_path, _FakeWrapper(boom), _FakeStrategy())

    assert result.status == ml.ModelStatus.LOAD_FAILED
    assert result.reason == ml.ModelReason.MODEL_LOAD_EXCEPTION
    assert result.ok is False


# ─── §8.2 runtime failure isolation ─────────────────────────────────────────
def test_p3t15_unexpected_programming_error_is_not_swallowed(tmp_path):
    """P3T-15 an unexpected error must stay visible, not become UNAVAILABLE."""
    model_path = _write_release(tmp_path)

    def bug(_w):
        raise TypeError("programming error, not an availability failure")

    with pytest.raises(TypeError):
        _ensure(model_path, _FakeWrapper(bug), _FakeStrategy())


def test_p3t08_expected_failures_never_raise_so_cycle_can_continue(tmp_path):
    """P3T-08/§4.2 the failure is recorded and returned — the caller can continue.

    Every expected failure mode must come back as a ModelInitResult instead of
    propagating, which is what keeps the ML-independent position-management
    paths (Step 5 / Step 6 / owned positions) reachable downstream.
    """
    cases = {
        "missing": (_FakeWrapper(), tmp_path / "absent.pkl"),
        "load_failed": (_FakeWrapper(lambda _w: (_ for _ in ()).throw(OSError("io"))), None),
        "incompatible": (
            _FakeWrapper(lambda _w: (_ for _ in ()).throw(InferenceFeatureError("mm"))),
            None,
        ),
    }
    for name, (wrapper, path) in cases.items():
        if path is None:
            path = _write_release(tmp_path / f"case_{name}", tag=name.encode())
        result = _ensure(path, wrapper, _FakeStrategy())
        assert isinstance(result, ml.ModelInitResult), name
        assert result.ok is False, name


def test_p3t12_live_runtime_never_trains_or_publishes(tmp_path):
    """P3T-20/21/22/32 init (healthy or failing) performs no training or writes."""
    for tag, wrapper in (("healthy", _FakeWrapper()), ("missing", _FakeWrapper())):
        wrapper = _FakeWrapper()
        path = _write_release(tmp_path / tag, tag=tag.encode()) if tag == "healthy" else (
            tmp_path / "absent.pkl"
        )
        before = {p.name: ml.file_sha256(p) for p in tmp_path.rglob("*") if p.is_file()}

        for _ in range(3):  # P3T-32 no hidden retry that trains/writes
            _ensure(path, wrapper, _FakeStrategy())

        after = {p.name: ml.file_sha256(p) for p in tmp_path.rglob("*") if p.is_file()}
        assert before == after, tag
        assert wrapper.fit_calls == 0 and wrapper.save_calls == 0, tag


def test_p3t24_approved_artifact_bytes_are_immutable(tmp_path, caplog):
    """P3T-24 hashes of the approved artifacts are identical before/after a run."""
    model_path = _write_release(tmp_path)
    paths = ml.resolve_artifact_paths(model_path)
    covered = ["model", "scaler", "features", "cfg"]
    before = {k: ml.file_sha256(paths[k]) for k in covered}
    assert all(before.values())

    wrapper, strategy = _FakeWrapper(), _FakeStrategy()
    with caplog.at_level(logging.WARNING, logger="fx_trade_bot_ml"):
        result = _ensure(model_path, wrapper, strategy)

    after = {k: ml.file_sha256(paths[k]) for k in covered}
    assert after == before
    assert result.status == ml.ModelStatus.READY


# ─── §8.5 observability ─────────────────────────────────────────────────────
def test_p3t25_26_diagnostic_record_has_required_fields(tmp_path, caplog, monkeypatch):
    """P3T-25/26 one structured record carries host, profile, path, status, reason."""
    monkeypatch.setenv("FX_BOT_HOST_ID", "host-unit-1")
    model_path = _write_release(tmp_path)

    with caplog.at_level(logging.INFO, logger="fx_trade_bot_ml"):
        result = _ensure(model_path, _FakeWrapper(), _FakeStrategy())

    record = [r for r in caplog.records if r.name == "fx_trade_bot_ml" and "ML-INIT" in r.message or "ML-INIT" in r.getMessage()]
    assert record, "no [ML-INIT] runtime record was emitted"
    text = record[-1].getMessage()
    for token in ("status=READY", "reason=MODEL_READY", "host=host-unit-1", "profile=profile2"):
        assert token in text, f"missing {token!r} in {text!r}"
    assert result.host_id == "host-unit-1"
    assert str(model_path.with_suffix(".json")) in text


def test_p3t26_unavailable_record_reports_reason(tmp_path, caplog, monkeypatch):
    monkeypatch.setenv("FX_BOT_HOST_ID", "host-unit-2")

    with caplog.at_level(logging.WARNING, logger="fx_trade_bot_ml"):
        result = _ensure(tmp_path / "absent.pkl", _FakeWrapper(), _FakeStrategy())

    assert result.status == ml.ModelStatus.UNAVAILABLE
    text = [r.getMessage() for r in caplog.records][-1]
    assert "status=UNAVAILABLE" in text and "reason=MODEL_MISSING" in text
    assert "host=host-unit-2" in text


def test_p3t27_two_hosts_different_releases_are_distinguishable(tmp_path, monkeypatch):
    """P3T-27 matching filenames do not imply identical artifacts (§6.3)."""
    path_a, path_b = tmp_path / "a", tmp_path / "b"
    path_a.mkdir(); path_b.mkdir()
    model_a = _write_release(path_a, tag=b"host-A-release")
    model_b = _write_release(path_b, tag=b"host-B-release")

    monkeypatch.setenv("FX_BOT_HOST_ID", "oracle-vm")
    res_a = _ensure(model_a, _FakeWrapper(), _FakeStrategy())
    monkeypatch.setenv("FX_BOT_HOST_ID", "laptop")
    res_b = _ensure(model_b, _FakeWrapper(), _FakeStrategy())

    assert res_a.host_id == "oracle-vm" and res_b.host_id == "laptop"
    assert res_a.model_hash != res_b.model_hash
    assert res_a.artifact_path != res_b.artifact_path


def test_p3t28_missing_manifest_reports_no_invented_identity(tmp_path):
    """P3T-28 no manifest → explicitly reported, and no release id is invented."""
    model_path = _write_release(tmp_path)
    result = _ensure(model_path, _FakeWrapper(), _FakeStrategy())

    assert result.manifest_present is False
    assert result.release_id is None
    # identity comes from real bytes instead
    assert result.model_hash and result.scaler_hash and result.features_hash
    # backend identity is recorded (or explicitly unavailable), never guessed
    assert result.backend


def test_manifest_presence_is_detected(tmp_path):
    model_path = _write_release(tmp_path)
    ml.resolve_artifact_paths(model_path)["manifest"].write_text("{}")
    result = _ensure(model_path, _FakeWrapper(), _FakeStrategy())
    assert result.manifest_present is True


# ─── §5.2/§5.3 ModelWrapper write protection (needs the inference stack) ────
pytestmark_deppresent = importlib.util.find_spec("sklearn") is not None


@pytest.mark.skipif(not pytestmark_deppresent, reason="BLOCKED: sklearn not installed in this interpreter (§9.3 no dependency changes)")
def test_p3t21_22_readonly_wrapper_blocks_fit_and_save(tmp_path):
    """P3T-21/22 a read-only wrapper refuses to train or write artifacts."""
    import pandas as pd

    from data_pipeline import FeatureConfig, LiveArtifactWriteError as LAW, ModelWrapper

    w = ModelWrapper(FeatureConfig(), model_path=tmp_path / "trade_model_xgb.pkl")
    w.read_only = True

    with pytest.raises(LAW):
        w.fit(pd.DataFrame({"f1": [1.0] * 200, "target": [0] * 200}), ["f1"])
    with pytest.raises(LAW):
        w.save()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(not pytestmark_deppresent, reason="BLOCKED: sklearn not installed in this interpreter (§9.3 no dependency changes)")
def test_p3t07_legacy_load_republish_blocked_in_readonly(tmp_path):
    """§5.3 legacy .pkl must not be silently migrated + republished by live."""
    import pickle

    from data_pipeline import FeatureConfig, LiveArtifactWriteError as LAW, ModelWrapper

    stem = tmp_path / "trade_model_xgb"
    with open(stem.with_suffix(".pkl"), "wb") as f:
        pickle.dump({"model": None, "scaler": None, "feature_names": ["f1"]}, f)

    w = ModelWrapper(FeatureConfig(), model_path=stem.with_suffix(".pkl"))
    w.read_only = True
    with pytest.raises(LAW):
        w.load()


@pytest.mark.skipif(not pytestmark_deppresent, reason="BLOCKED: sklearn not installed in this interpreter (§9.3 no dependency changes)")
def test_p3t20_readonly_init_writes_nothing(tmp_path):
    """P3T-20 live initialisation never writes model/scaler/config/feature files."""
    from data_pipeline import FeatureConfig, ModelWrapper

    w = ModelWrapper(FeatureConfig(), model_path=tmp_path / "trade_model_xgb.pkl")
    w.read_only = True
    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(not pytestmark_deppresent, reason="BLOCKED: sklearn not installed in this interpreter (§9.3 no dependency changes)")
def test_readonly_constructor_flag_is_enforced(tmp_path):
    """§5.2 constructor-time enforcement (not a later flip).

    The live bots now pass read_only=True at construction; this proves the
    parameter is honoured by the real ModelWrapper.
    """
    from data_pipeline import FeatureConfig, LiveArtifactWriteError as LAW, ModelWrapper

    w = ModelWrapper(
        FeatureConfig(), model_path=tmp_path / "trade_model_xgb.pkl", read_only=True
    )
    assert w.read_only is True
    with pytest.raises(LAW):
        w.save()
    assert list(tmp_path.iterdir()) == []


# ─── source-backed evidence (no heavy deps, no live execution) ──────────────
def _source(path):
    return path.read_text(encoding="utf-8")


def _main_node(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            return node
    raise AssertionError("main() not found")


@pytest.mark.parametrize("bot", LIVE_BOTS, ids=lambda p: p.name)
def test_p3t08_ensure_model_call_is_not_fatal(bot):
    """§4.2/AC-03: the live bots consume a ModelInitResult and keep running.

    The call must be a plain single-target assignment inside main()'s own body —
    i.e. NOT tuple-unpacked from a raising contract and NOT wrapped in a
    try/except that aborts the cycle.
    """
    tree = ast.parse(_source(bot))
    main = _main_node(tree)

    calls = [
        n
        for n in ast.walk(main)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "ensure_model"
    ]
    assert len(calls) == 1, f"expected exactly one ensure_model() call in {bot.name}"
    assert any(
        isinstance(n, ast.Assign)
        and isinstance(n.targets[0], ast.Name)
        and n.targets[0].id == "ml_init"
        and n.value is calls[0]
        for n in main.body
    ), "ensure_model() must be assigned to `ml_init` directly in main()'s body (no tuple unpack, no try/except abort)"

    # Unexpected errors must still surface at the top level (visibility, §4.4).
    assert "log.exception" in _source(bot)


@pytest.mark.parametrize("bot", LIVE_BOTS, ids=lambda p: p.name)
def test_step5_step6_owned_positions_are_ml_independent(bot):
    """AC-03: the Step 5 / Step 6 region must not touch the model at all.

    Only the Step 4 confluence call and the Step 7 scoring call may use
    `strat_engine`; the owned-position management block between them is
    genuinely ML-independent.
    """
    src = _source(bot)
    begin = src.rindex("# Step 5 — Dynamic Exit Manager")
    end = src.index("# Step 7 — Score, Trend Filter, Smart TP & Execute")
    region = src[begin:end]
    assert region, "could not isolate the Step 5 → Step 7 region"

    for forbidden in ("strat_engine", "model_wrapper", "ml_init"):
        assert forbidden not in region, f"{forbidden} leaked into the ML-independent region"
    # ...and the region really is the position-management block
    assert "DynamicPositionManager" in region
    assert "owned_trade_by_oanda" in region


@pytest.mark.parametrize("bot", LIVE_BOTS, ids=lambda p: p.name)
def test_p3t13_quick_flip_is_ml_independent(bot):
    """AC-04: QUICK-FLIP / _revise_owned_position runs without any ML input."""
    src = _source(bot)
    begin = src.index("# ─── QUICK-FLIP + REVISE SL/TP for OWNED positions ───")
    end = src.index("# ─── MIN_STRENGTH_GAP gate ───")
    region = src[begin:end]

    for forbidden in ("strat_engine", "model_wrapper", "ml_init", "generate_signal", "model_p_up"):
        assert forbidden not in region, f"QUICK-FLIP depends on {forbidden}"
    assert "close_wrap" in region and "_revise_owned_position" in region


# ─── Entry-authorisation boundary (FROZEN — §4.5) ──────────────────────────
@pytest.mark.parametrize("bot", LIVE_BOTS, ids=lambda p: p.name)
def test_entry_authorization_is_unchanged_and_unresolved(bot):
    """ENTRY AUTHORIZATION REMAINS UNCHANGED AND UNRESOLVED.

    The §4.5 approval for changing the entry path was explicitly withheld, so
    the shipped behaviour is pinned here: ML unavailability still reaches the
    scoring path with `xgb_prob is None`, and the synthetic X fallback
    (`X = 0.3S + 0.3R`) still participates in FINAL.  If this test fails, the
    entry path was changed without the owner's §4.5 approval.
    """
    src = _source(bot)
    assert "if X == 0.0 or _xgb_missing:" in src
    assert "X = max(0.0, min(100.0, S * 0.3 + R * 0.3))" in src
    assert '_xgb_missing = _opt("XGB_MISSING_NEUTRAL", True) and (xgb_prob is None)' in src


@pytest.mark.parametrize("bot", LIVE_BOTS, ids=lambda p: p.name)
def test_ml_status_does_not_gate_entry(bot):
    """The MAX_OPEN skip-gate must stay derived from MAX_OPEN only.

    Wiring ML status into this gate would silently turn ML unavailability into a
    no-entry decision — an unapproved entry-authorization change.
    """
    src = _source(bot)
    assert (
        "_skip_signal_generation = (\n"
        "        _early_open_count >= MAX_OPEN and not DIRECTION_FLIP_EXIT_ENABLED\n"
        "    )"
    ) in src
    assert "ml_init" not in src.split("_skip_signal_generation = (")[1].split(")", 1)[0]


def test_no_dead_skip_helper_was_added_to_the_ml_module():
    """The rejected `should_skip_signal_generation` helper must not come back."""
    assert not hasattr(ml, "should_skip_signal_generation")


def test_ml_module_stays_free_of_the_heavy_stack():
    """fx_trade_bot_ml must remain importable without sklearn/xgboost.

    Only MODULE-LEVEL imports affect importability: the module is allowed a
    lazy, try/except-guarded backend probe (see _backend_identity) because it
    only runs when called.
    """
    src = _source(BASE_DIR / "fx_trade_bot_ml.py")
    tree = ast.parse(src)
    imported = {
        alias.name.split(".")[0]
        for node in tree.body  # module-level only
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        (node.module or "").split(".")[0]
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
    }
    assert not ({"sklearn", "xgboost", "joblib", "data_pipeline", "oandapyV20"} & imported)
    # any nested xgboost import must sit behind try/except so a missing stack
    # yields "xgboost=unavailable" instead of an ImportError at call time.
    assert "except" in src


# ─── §5.2 offline training stays functional ─────────────────────────────────
def _model_wrapper_init():
    """Locate ModelWrapper.__init__ in the shipped data_pipeline source."""
    tree = ast.parse(_source(BASE_DIR / "data_pipeline.py"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "ModelWrapper":
            for fn in node.body:
                if isinstance(fn, ast.FunctionDef) and fn.name == "__init__":
                    return fn
    raise AssertionError("ModelWrapper.__init__ not found")


def _init_keyword_defaults(init_fn):
    """Map keyword-arg name → default *node* for a function definition."""
    names = [a.arg for a in init_fn.args.args]
    offset = len(names) - len(init_fn.args.defaults)
    return {names[offset + i]: d for i, d in enumerate(init_fn.args.defaults)}


def test_p3t23_offline_trainer_uses_a_writable_wrapper():
    """AC-08/C03: read_only is opt-in, so retrain_model.py keeps working."""
    default = _init_keyword_defaults(_model_wrapper_init())["read_only"]
    assert isinstance(default, ast.Constant) and default.value is False, (
        "ModelWrapper.read_only must default to False (writable) for offline training"
    )

    retrain = _source(BASE_DIR / "retrain_model.py")
    assert "wrapper.save()" in retrain
    assert "read_only" not in retrain, "offline trainer must not be forced read-only"


# ─── C01 live construction is read-only (source-backed) ─────────────────────
@pytest.mark.parametrize("bot", LIVE_BOTS, ids=lambda p: p.name)
def test_live_bots_construct_model_wrapper_read_only(bot):
    """C01/§5.2: the live runtime must CONSTRUCT the wrapper read-only.

    Relying on a later mutation (ensure_model) is not enough — construction
    itself must be read-only so no live path can ever train or publish.
    """
    tree = ast.parse(_source(bot))
    calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "ModelWrapper"
    ]
    assert calls, f"{bot.name}: ModelWrapper construction not found"
    for call in calls:
        kwargs = {k.arg: k.value for k in call.keywords}
        assert "read_only" in kwargs, f"{bot.name}: read_only must be explicit"
        value = kwargs["read_only"]
        assert isinstance(value, ast.Constant) and value.value is True, (
            f"{bot.name}: live ModelWrapper must be constructed with read_only=True"
        )

