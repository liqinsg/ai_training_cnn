# Phase 3.1 — Stage B Completion Report

**Spec:** `docs/PHASE3_1_STAGE_B_STRICT_SPEC.md` (v3, SHA-256 `7203fb0dac6d4ad0b8fbaf7edea0bd838d7490cd62dd070d5f838cd4496f26c1`)
**Contract:** `docs/PHASE3_1_CONTRACT.md` (v1.3, Stage A.3, SHA-256 `49975ef44b9a3f87909c8fb9f9c1af30f6efbc974f2a8b8efe3caf04f5fdde7b`)
**Task ticket:** `docs/PHASE3_1_STAGE_B_IMPLEMENTATION_TASK.md`
**Branch:** `v2026c` · **HEAD:** `10147858af1ff3067dc413330b369911b8186e91` (unchanged before/after)
**Stage B Status: COMPLETE** (definition per spec §24; see §9 wait-for-approval statement)

---

## 22.1 Implementation summary

| Item | Value |
| --- | --- |
| Adapter module (new) | `ml/prediction_adapter.py` — SHA-256 `8b5463dca4d687429208d9bb9e7498a467247e432fffb698ffb4499d1310de9d` |
| Adapter entry point | `run_prediction(*, model, scaler, feature_list, X, pair, timeframe, bar_time, clock, registry=None, identity=None, model_status=None, diagnostics=None) -> PredictionResult` |
| NOT_RUN helper | `build_not_run_result(*, pair, timeframe, bar_time, clock, diagnostics=None) -> PredictionResult` |
| Loader | `load_model_with_identity(*, model_path, scaler_path, clock, model_loader=None, scaler_loader=None, model_path_loader=None, after_read_hook=None) -> LoadedModelIdentity` |
| Registry handle | `CDRegistryHandle.load(path)` (startup load, read-only, never raises; fail-closed) |
| `PredictionResult` | Frozen dataclass; 18 contract fields (`status, reason, pair, timeframe, bar_time, direction, raw_probability, positive_class_label, p_up, p_not_up, p_down, model_id, model_artifact_hash, release_id, feature_contract_id, features_hash, timestamp, diagnostics`); all validation in `__post_init__` |
| Immutability | `frozen=True` + `MappingProxyType` diagnostics over a defensive copy; `PredictionResultInvariantError` on any illegal combination (B-T23, B-T46, B-T66–B-T72) |
| Existing inference path reused | `data_pipeline._build_matrix(X, feature_list, scaler)` then `model.predict_proba(scaled)`. `data_pipeline.predict_p_up()` is deliberately **not** used because it selects the column via `positive_class_index()`; Stage B requires the fixed structural `EXTRACTION_INDEX = 1` (spec §7.2) |
| Files changed (implementation) | `ml/prediction_adapter.py` (new), `config/model_cd_registry.json` (new), `tests/test_prediction_adapter.py` (new) |
| Process artifacts (not implementation) | `docs/PHASE3_1_STAGE_B_IMPLEMENTATION_TASK.md`, this report |
| Files inspected, not changed | `data_pipeline.py`, `fx_trade_bot_ml.py`, `strategy_decision.py`, `ml/live_prediction_engine.py`, `ml/integration_hook.py`, `config.py`, `data_guard.py` |

Deterministic constants: `DECISION_THRESHOLD = 0.5`, `COMPLEMENT_TOLERANCE = 1e-9`, `ROW_SUM_TOLERANCE = 1e-5`, `EXTRACTION_INDEX = 1`.

### Ownership evidence (spec §9.3)

| Item | Value |
| --- | --- |
| Actual caller | `strategy_decision.StrategyEngine.generate_signal()` is the live ML consumer today (C-1/C-2/C-3). The Stage B adapter is **not** wired to any caller. |
| Actual bars precondition | `data_guard.has_min_bars(df, 5, context="StrategyEngine.generate_signal")` (`strategy_decision.py:131`); the engine also uses a 20-bar floor on its own polling path. Stage B does not read, redefine or duplicate it (B-06, §9.1). |
| Existing threshold source | `data_guard.has_min_bars` (caller-owned). The adapter ships no threshold constant. |
| Intended Stage C NOT_RUN location | The caller that owns bar history, at the point where it currently decides not to call inference — using `build_not_run_result(...)`. Delivered as a pure helper only (B-T01). |

---

## 22.2 Artifact identity evidence

| Item | Value |
| --- | --- |
| Exact artifact SHA-256 | `94c8751df33daee5190e42634d823bcb08d4a0dbc1e0a2cf2f3e8cfbd91d5942` (`trade_model_xgb.json`) |
| Exact scaler SHA-256 | `031ea8068a2b8309829624b30acb7db2cde40ce4452240cf423619fae4b2cd8c` (`scaler.joblib`) |
| Source of loaded bytes | One `open(path, "rb").read()` per artifact inside `load_model_with_identity`; the model instance is constructed from **those same in-memory bytes** (`model.load_model(bytearray(raw))`). |
| Hash computation point | Immediately after the single read, before any construction, in `load_model_with_identity`. |
| `load_method` | `BYTES` on the live host (verified below); `TEMPFILE` (private 0600 file, deleted immediately) only if the library cannot construct from memory. |
| Loader consumed the hashed bytes (B-T49) | `tests/test_prediction_adapter.py::test_B_T49_loader_consumes_the_hashed_bytes` — an `after_read_hook` overwrites the on-disk file *after* the read; the loader still receives the original bytes and `identity.artifact_sha256 == sha256(original)`. |
| Immutable binding (B-10) | `LoadedModelIdentity` is `frozen=True`; `test_B_T63_identity_fields_cannot_be_reassigned`. |
| No per-prediction disk rehash (B-11) | The adapter never receives a path; `test_B_T65_adapter_performs_no_filesystem_read` monkeypatches `builtins.open` to raise and a READY prediction still succeeds. |

**Real-artifact end-to-end evidence (exact accepted artifact, spec §16.8):**

```text
$ python - <<'PY'   # load real artifacts with the new loader, then predict
load_method: BYTES
artifact_sha256: 94c8751df33daee5190e42634d823bcb08d4a0dbc1e0a2cf2f3e8cfbd91d5942
scaler_sha256:   031ea8068a2b8309829624b30acb7db2cde40ce4452240cf423619fae4b2cd8c
artifact_matches_evidence: True   scaler_matches_evidence: True
registry_ok: True  registry_sha256: 5e9278e3525f950789090c0223357100644d0d1006015d5e3c5107dddc21852a  records: 1
n_features: 34
status/reason: READY NONE
direction: BUY | raw: 0.6497586965560913 | p_up: 0.6497586965560913 | p_not_up: 0.3502413034439087
positive_class_label: 1 int      p_down: None
model_artifact_hash_ok: True
at_threshold: False | cd_failure_cause: None
runtime_classes: [0, 1] | positive_class_index: 1
cd_decision_id: CD-OPEN-1: SELL = not-UP (accepted 2026-11-14)
```

> **Identity binding is proven in the new loader and tests, not on the production path (Stage C).**
> `fx_trade_bot_ml.ModelWrapper.load()` / `fx_trade_bot_ml.ensure_model()` are unchanged; the production
> runtime still calls the legacy loader and does not produce `LoadedModelIdentity`. Wiring is Stage C.

---

## 22.3 CD Registry evidence

| Item | Value |
| --- | --- |
| Registry path | `config/model_cd_registry.json` (new; `schema_version = 1`) |
| Registry SHA-256 | `5e9278e3525f950789090c0223357100644d0d1006015d5e3c5107dddc21852a` (685 bytes) |
| Git revision | Present in the version-controlled tree under `config/`; **not committed** (Stage B forbids commits, B-69). The SHA-256 above is the revision identity for this report. |
| Matching record | `artifact_sha256 = 94c8751d…d5942`, `scaler_sha256 = 031ea806…2cd8c`, `decision = VERIFIED` |
| Positive class index / label | `positive_class_index = 1`, `positive_class_label = 1` |
| UP / not-UP semantics | `positive_class_semantics = UP`, `negative_class_semantics = NOT_UP`, `probability_semantics = BINARY_EXCLUSIVE_EXHAUSTIVE` |
| Evidence record reference | `docs/PHASE3_1_CD_EVIDENCE.md`, version `Live Host Evidence (arm / 2026-11-14)`, `decision_id = CD-OPEN-1: SELL = not-UP (accepted 2026-11-14)` |
| Authorship (B-19) | Transcribed strictly from the accepted A.3 evidence (§A fingerprints, §F verdict, §G adjudication). No field was invented; the adapter cannot self-certify CD. |
| Read-only / loaded once (B-13) | `CDRegistryHandle.load()` reads once at startup and exposes read-only properties; it never writes. |

Fail-closed test results: missing file → `REGISTRY_UNAVAILABLE` (B-T48); malformed JSON → `REGISTRY_UNAVAILABLE` (B-T48b); duplicate record → `RECORD_DUPLICATE` (B-T47); no exact match → `RECORD_MISSING` (B-T13, B-T15, B-T75); non-`VERIFIED` → `DECISION_NOT_VERIFIED` (B-T55); record without `scaler_sha256` → `RECORD_MISSING` (B-T76); registry SHA-256 recorded (B-T50).

**CD evidence limitations preserved (B-20, B-21).** Runtime `classes_` is a **consistency check, not proof**:
XGBoost 2.0.3 synthesizes `classes_` as `np.arange(n_classes_)` and does not demonstrate that the original
training class array was serialized into the `.json` artifact (CD evidence element #2 **PARTIAL**). The
producer-route limitation (#6) also remains. `CD = VERIFIED` is **hash-specific** and does not transfer to
any other or future artifact. **CD verification does not authorize Stage B, `READY` activation, ML voting
or any trading-behaviour change** (CD-D9/CD-D10).

---

## 22.4 Exception and validation evidence

Closed exception mapping (derived from actual code; spec §8):

| Exception / condition | Source location | Classification |
| --- | --- | --- |
| `ModelInitResult.status ∈ {UNAVAILABLE, INCOMPATIBLE, LOAD_FAILED}` | `fx_trade_bot_ml.py:33-40, 249-298` | UNAVAILABLE / MODEL_NOT_USABLE |
| Runtime model object absent (`model is None`) | adapter step 1 | UNAVAILABLE / MODEL_NOT_USABLE |
| Required scaler absent (`scaler is None`) | adapter step 1 | UNAVAILABLE / MODEL_NOT_USABLE |
| `ScalerMissingError` | `data_pipeline.py:44-45, 409-412` | UNAVAILABLE / MODEL_NOT_USABLE |
| Known model load failure (malformed artifact bytes) | `load_model_with_identity` (no identity produced) | UNAVAILABLE / MODEL_NOT_USABLE |
| `InferenceFeatureError` | `data_pipeline.py:40, 415-453` | INVALID / FEATURE_CONTRACT_VIOLATION |
| `DimensionMismatchError` (reserved; unreachable today) | `data_pipeline.py:48-49` | INVALID / FEATURE_CONTRACT_VIOLATION |
| Any unclassified exception at the inference boundary | adapter steps 2/3 | ERROR / EXECUTION_ERROR |

The table is closed. No broad rule ("all `ValueError` → INVALID") is used. `Exception` is caught, never `BaseException` (spec §6.3).

Validation order (spec §7) and its proof:

| Order | Check | Failure result | Test |
| ---: | --- | --- | --- |
| 1 | Model/scaler usability | UNAVAILABLE / MODEL_NOT_USABLE | B-T02, B-T02b, B-T03, B-T41 |
| 2 | Input feature contract | INVALID / FEATURE_CONTRACT_VIOLATION | B-T04 |
| 3 | Inference execution | ERROR / EXECUTION_ERROR | B-T05, B-T42 |
| 4 | Output structure | INVALID / PREDICTION_OUTPUT_MALFORMED | B-T06, B-T07, B-T08 |
| 5 | Neutral extraction + numeric validity | INVALID / PREDICTION_INVALID_PROBABILITY (or MALFORMED) | B-T09–B-T12, B-T31–B-T40, B-T57, B-T58 |
| 6 | Artifact identity + CD binding | UNINTERPRETABLE / CLASS_DEFINITION_UNVERIFIED | B-T13–B-T16, B-T47, B-T48, B-T51–B-T56, B-T75, B-T76 |
| 7 | Probability interpretation | READY | B-T17–B-T21, B-T74 |
| 8 | `PredictionResult` construction | Invariant violation → §5.6 fallback | B-T73 |

Multi-fault precedence: `test_B_T41...` (model unusable **and** invalid input → UNAVAILABLE) and
`test_B_T60...` (invalid candidate **and** missing registry record → INVALID) prove the fixed order with two
independent pairs.

Inference-time failures return a `PredictionResult`; only pre-inference API contract violations raise
(invalid required argument, invalid injection, wrong mandatory argument type, naive `bar_time`). Fallback
test: `test_B_T73_forced_internal_invariant_violation_returns_fallback` (B-T74/B-74).

---

## 22.5 Probability evidence

| Aspect | Evidence |
| --- | --- |
| Valid extraction | `candidate = proba[0, 1]` at the fixed structural index (B-T17–B-T20, real-artifact run above) |
| Invalid type rejection | B-T31 (Python `bool`), B-T32 (`np.bool_`), B-T34 (0-D array), B-T35 (1-D/2-D array), B-T36–B-T37 (`Decimal`), B-T38 (complex), B-T39 (str), B-T40 (custom numeric object) |
| Accepted NumPy scalars | B-T33 (`float32`, `float64`, `int64`) accepted when finite and in range |
| Invalid numeric rejection | NaN / ±inf / `< 0` / `> 1` → INVALID with `raw_probability = None` (B-T09–B-T12, B-T57) |
| Actual class mapping | `model.classes_` read at runtime; extraction index fixed at `1` (B-T51, B-T52–B-T54) |
| UP / not-UP interpretation | `p_up = raw_probability`, `p_not_up = 1.0 - p_up` (real-artifact run: `0.6497586965560913` / `0.3502413034439087`) |
| Tie handling | `p_up == 0.5` → `SELL`, `at_threshold = True` (B-T19, B-T74) |
| `p_down` | Always `None`; never populated with the not-UP complement (B-T24, B-T69) |
| Approximate complement | Complement assertions use `pytest.approx(..., abs=1e-6)` (spec §11.6), covering `float32` output (B-T17–B-T20, B-T33) |
| Row-sum rule | Sum must equal `1.0` within `ROW_SUM_TOLERANCE = 1e-5`; violation → INVALID / `PREDICTION_OUTPUT_MALFORMED` (B-T58) |

Direction rule: `BUY if p_up > 0.5 else SELL` (strict `>`); `p_up == 0.5` → `SELL`.

---

## 22.6 Status evidence

| Status | Test evidence |
| --- | --- |
| READY | B-T14, B-T17–B-T20, B-T21, B-T25, B-T26, real-artifact run |
| UNINTERPRETABLE | B-T13, B-T15, B-T16, B-T47, B-T48, B-T51–B-T56, B-T75, B-T76 |
| NOT_RUN | B-T01 (`build_not_run_result`, no inference; `bar_time` may be `None`) |
| UNAVAILABLE | B-T02, B-T02b, B-T03, B-T41, B-T43, B-T62 |
| INVALID | B-T04, B-T06–B-T12, B-T31–B-T40, B-T57, B-T58, B-T60 |
| ERROR | B-T05, B-T42, B-T73 |
| ABSTAIN | static inspection only: B-T30 |

`ABSTAIN remains defined but unreachable in Stage B.` The enum member is retained for contract
compatibility; the adapter contains no `status=PredictionStatus.ABSTAIN` construction path and never passes
`ABSTAIN_BY_PREDICTION_RULE` as a reason (proven by `test_B_T30_no_abstain_construction_path`).

---

## 22.7 Test report

Environment: Python 3.12.15 · pytest 9.1.1 · numpy 1.26.4 · pandas 2.2.3 · scikit-learn 1.5.2 · xgboost 2.0.3 · joblib 1.5.3 · Linux (`arm`).

| Group | Command | Passed | Failed | Skipped |
| --- | --- | ---: | ---: | ---: |
| Stage B adapter suite (B-T01…B-T76 + static checks) | `python -m pytest tests/test_prediction_adapter.py -q` | **102** | 0 | 0 |
| Phase 3.0 / prediction-related regression set | `python -m pytest tests/test_prediction_adapter.py tests/test_live_prediction_engine.py tests/test_prediction_contract.py tests/test_integration_hook.py tests/test_phase3_runtime_containment.py -q` | **157** | 0 | 0 |

```text
tests/test_prediction_adapter.py ................................  [ 70%]
................................                                  [100%]
102 passed in 1.18s
```

Dependency / environment limitations (reported separately, never counted as passed):

- `flake8`, `pycodestyle`, `pyflakes`, `ruff` are **not installed** in the `ai-sprint` environment → the
  repo's `.flake8` style gate could not be executed. Substitute checks actually run:
  `python -m py_compile ml/prediction_adapter.py tests/test_prediction_adapter.py` (OK) and a
  line-length check against the configured `max-line-length = 500` (0 violations in both new files).
- No test is skipped. No test is weakened to obtain a pass (§16.8).
- Mocked CD matches prove adapter logic only, never real artifact semantics; stubbed inference does not
  prove real model loading. The one real-artifact run is reported separately in §22.2.

### Test matrix traceability (B-T01…B-T76)

| Range | Coverage |
| --- | --- |
| B-T01–B-T05 | `test_B_T01…`, `test_B_T02…`, `test_B_T02b…`, `test_B_T03…`, `test_B_T04…`, `test_B_T05…` |
| B-T06–B-T12 | `test_B_T06…` (param), `test_B_T07…`, `test_B_T08…` (param), `test_B_T09_T12…` (param) |
| B-T13–B-T21 | `test_B_T13…`, `test_B_T14…`, `test_B_T15…`, `test_B_T16…`, `test_B_T17_T20…` (param), `test_B_T21…` |
| B-T22–B-T30 | `test_B_T22…`, `test_B_T23…`, `test_B_T24…`, `test_B_T25…`, `test_B_T26…`, `test_B_T27…`, `test_B_T28…`, `test_B_T29…`, `test_B_T30…` |
| B-T31–B-T45 | `test_B_T31_T40…` (param), `test_B_T33…` (param), `test_B_T41…`, `test_B_T42…`, `test_B_T43…`, `test_B_T44…`, `test_B_T45…` |
| B-T46–B-T50 | `test_B_T46…`, `test_B_T47…`, `test_B_T48…`, `test_B_T48b…`, `test_B_T49…`, `test_B_T50…` |
| B-T51–B-T60 | `test_B_T51…`, `test_B_T52…`, `test_B_T53…`, `test_B_T54…` (param), `test_B_T55…`, `test_B_T56…` (param), `test_B_T57…`, `test_B_T58…`, `test_B_T59…`, `test_B_T60…` |
| B-T61–B-T65, B-T75, B-T76 | `test_B_T61…`, `test_B_T62…`, `test_B_T63…`, `test_B_T64…` (param), `test_B_T65…`, `test_B_T75…`, `test_B_T76…` |
| B-T66–B-T74 | `test_B_T66…` … `test_B_T74…` |
| 16.6 multi-fault | B-T41 and B-T60 |
| 16.7 static checks | `test_static_no_direct_system_clock_calls`, `test_static_no_guessed_class_label_default`, `test_static_constants_match_the_contract`, `test_static_public_api_surface_is_present`, plus `test_B_T27…`, `test_B_T29…`, `test_B_T30…` |

---

## 22.8 Compatibility evidence

Confirmed unchanged:

| Item | Evidence |
| --- | --- |
| `generate_signal()` signature and behaviour | `strategy_decision.py` has **zero modified lines** (`git diff --name-only` lists only docs). `test_B_T28…` asserts the exact parameter list and `-> Optional[Signal]` plus the `Direction.LONG if p_up > p_down else Direction.SHORT` rule |
| `Signal` structure, strategy thresholds, scoring | Not touched; no import of `strategy_decision` in the adapter |
| C-1 Step 4 multi-TF confluence | Unchanged (no modified lines) |
| C-2 Step 7 scoring feed | Unchanged; still the registered known exception (§4.1.1.6) |
| C-3 open-reason log | Unchanged |
| C-4 attribution live hook | Unchanged |
| C-5 attribution data bridge | Unchanged |
| C-6 `should_close()` | Dormant, unchanged |
| C-7 `select_signals()` | Dormant, unchanged |
| Entry Authorization / ML Vote / MC / Strength / FINAL weights | Unchanged — the adapter contains no Decision, Authorization, scoring or execution logic (`test_B_T27…`, `test_B_T29…`) |
| OANDA execution, scheduler, `run.env` | Untouched |
| Production loader / Phase 3.0 init path | `fx_trade_bot_ml.py` unmodified (B-71) |

`git diff --stat` (tracked files, before and after — identical; both entries pre-date Stage B):

```text
 docs/PHASE3_1_CD_EVIDENCE.md | 257 +++++++++++++-
 docs/PHASE3_1_CONTRACT.md    | 802 +++++++++++++++++++++------------------
 2 files changed, 724 insertions(+), 335 deletions(-)
```

Changed-file list for Stage B (all newly created, all inside the approved allowlist):

```text
ml/prediction_adapter.py
config/model_cd_registry.json
tests/test_prediction_adapter.py
docs/PHASE3_1_STAGE_B_IMPLEMENTATION_TASK.md
docs/PHASE3_1_STAGE_B_COMPLETION_REPORT.md
```

Function-level diff inspection: `git diff --name-only` returns only `docs/PHASE3_1_CD_EVIDENCE.md` and
`docs/PHASE3_1_CONTRACT.md` — no `.py` file tracked at HEAD has any modified line, so no function in any
production module was altered.

---

## 22.9 Repository integrity

| Item | Value |
| --- | --- |
| Repository root | `/home/ubuntu/projects/ai_training_cnn` |
| Branch | `v2026c` |
| HEAD before | `10147858af1ff3067dc413330b369911b8186e91` |
| HEAD after | `10147858af1ff3067dc413330b369911b8186e91` (unchanged) |

`git status --short` before Stage B (recorded in the task ticket §1.2):

```text
 M docs/PHASE3_1_CD_EVIDENCE.md
 M docs/PHASE3_1_CONTRACT.md
?? docs/PHASE3_1_CONTRACT_A3.md
?? docs/PHASE3_1_STAGE_B_STRICT_SPEC.md
?? launch_dual_bot_p4.sh
?? tests/test_direction_flip_exit.py
?? tests/test_mc_results_dir_resolution.py
?? trade_model_xgb.manifest.json
```

`git status --short` after Stage B:

```text
 M docs/PHASE3_1_CD_EVIDENCE.md
 M docs/PHASE3_1_CONTRACT.md
?? config/
?? docs/PHASE3_1_CONTRACT_A3.md
?? docs/PHASE3_1_STAGE_B_IMPLEMENTATION_TASK.md
?? docs/PHASE3_1_STAGE_B_STRICT_SPEC.md
?? launch_dual_bot_p4.sh
?? ml/prediction_adapter.py
?? tests/test_direction_flip_exit.py
?? tests/test_mc_results_dir_resolution.py
?? tests/test_prediction_adapter.py
?? trade_model_xgb.manifest.json
```

Pre-existing unrelated changes (`launch_dual_bot_p4.sh`, `tests/test_direction_flip_exit.py`,
`tests/test_mc_results_dir_resolution.py`, `trade_model_xgb.manifest.json`, and both doc modifications)
were **preserved untouched**. No `reset`, `clean`, `stash` or `checkout` was executed.
**No commit was created. No deployment was performed.** No training script or model artifact was changed.

---

## 22.10 CONTRACT-CONFIRM outcomes

| # | Item | Contract position | Implementation |
| --- | --- | --- | --- |
| 1 | §5.2 `at_threshold` placement | Contract §1.3 defines no `at_threshold` field → silent | Carried in `diagnostics["at_threshold"]` (bool for READY only; absent otherwise). Not a top-level field. Enforced by `_check_result_invariants` and B-T74. |
| 2 | §5.3 `positive_class_label` in UNINTERPRETABLE | Contract §1.3.2 omits it and sets `p_up = None`; CD-T10 forbids inventing `"UP"` | `None` in UNINTERPRETABLE; the runtime class value is carried in `diagnostics["runtime_class_label_at_extraction_index"]`. Enforced by `_check_result_invariants` and B-T68. |
| 3 | §7.3.5 row-sum rule | Contract silent | **Included**, `ROW_SUM_TOLERANCE = 1e-5`; failure → INVALID / `PREDICTION_OUTPUT_MALFORMED`. B-T58. |
| 4 | §7.4 `cd_failure_cause` vocabulary | Contract §1.3 `diagnostics` is "supplementary, non-authoritative"; extra keys not forbidden | Allowed in diagnostics **only**; never status/reason authority. Emitted values: `HASH_UNAVAILABLE`, `REGISTRY_UNAVAILABLE`, `RECORD_MISSING`, `RECORD_DUPLICATE`, `DECISION_NOT_VERIFIED`, `INDEX_MISMATCH`, `LABEL_MISMATCH`, `SEMANTICS_UNSUPPORTED`. Covered by B-T13, B-T15, B-T16, B-T47, B-T48, B-T51–B-T56, B-T75, B-T76. |
| 5 | §5.5 READY success reason | Contract §1.2 defines no READY reason and forbids inventing one | Sentinel `PredictionReason.NONE` (`"NONE"` = "no failure reason"), reusing the committed A.2 convention. No new reason invented. |

---

## Acceptance criteria (spec §20) — result

Every mandatory criterion was reviewed against its required evidence source (spec §21).

| IDs | Result | Evidence |
| --- | --- | --- |
| B-01–B-08 | PASS | Independent module; structured result distinct from `Signal`; existing `_build_matrix` path reused; no second pipeline; caller owns bars; `ModelStatus` vs `PredictionStatus` separate; no Decision/Authorization logic |
| B-09–B-11 | PASS | §22.2; B-T49, B-T61–B-T65 |
| B-12–B-15 | PASS | Registry schema, path, SHA-256, provenance fields; B-T50 |
| B-16–B-T21 group (B-16–B-21) | PASS | Exact dual-hash equality; fail-closed; no CD transfer; adapter cannot self-certify; `classes_` limitation documented |
| B-22 | PASS | CD-OPEN-4 hardenings implemented in the new adapter: no guessed `positive_class_label` default (value comes only from a verified registry record, else `None`) and `p_down` always `None`. The pre-existing A.2 seam `ml/live_prediction_engine.py:180-182` still contains the old pattern; it is unmodified and its removal is Stage C / Phase 3.6. CD-OPEN-4 remains OPEN repository-wide. |
| B-23–B-25 | PASS | Frozen dataclass + invariants; B-T23, B-T46, B-T66–B-T72 |
| B-26–B-30 | PASS | B-T06–B-T12, B-T31–B-T40, B-T57, B-T58 |
| B-31–B-38 | PASS | B-T13, B-T17–B-T24, B-T74 |
| B-39–B-40 | PASS | B-T41, B-T59, B-T60 + validation-order inspection |
| B-41–B-44 | PASS | §22.4 closed mapping; B-T05, B-T42, B-T43, B-T44, B-T73 |
| B-45 | PASS | `build_not_run_result` + B-T01 |
| B-46 | PASS | B-T30 static inspection |
| B-47–B-49 | PASS | B-T26, B-T44, B-T45 |
| B-50–B-52 | PASS | B-T27, `test_B_T65` (no filesystem read), no fallback direction in the adapter |
| B-53–B-57 | PASS | B-T28, B-T29, `git diff` evidence (§22.8) |
| B-58–B-63 | PASS (with noted environment limitation) | §22.7 — 102/102 and 157/157 passed, 0 skipped; `flake8` unavailable (substitute checks recorded) |
| B-64–B-70 | PASS | §22.9 — only allowlisted files created; no commit; no deployment |
| B-71 | PASS | `fx_trade_bot_ml.py` and the Phase 3.0 init path have no modified lines |
| B-72 | PASS | B-T75, B-T76, identity construction tests |
| B-73 | PASS | B-T59, B-T60 |
| B-74 | PASS | B-T73 |
| B-75 | PASS | B-T52–B-T54 |
| B-76 | PASS | B-T71, B-T72 |
| B-77 | PASS | §22.10 and the task ticket §3 |

---

## Stop statement (spec §24)

**Stage B completion is not Stage C authorization.** The production runtime is not wired to the adapter;
consumers still use `Signal`; ML Vote is unchanged; Step 7 is unchanged; Entry Authorization is unchanged;
C-1 through C-7 are not migrated; `READY` activation is not authorized; no trading behaviour changed.

Work now stops. Separate explicit approval is required before consumer migration, production-loader
wiring, authorization changes, or any behaviour-changing work.
