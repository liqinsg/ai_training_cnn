# Phase 3.1 — Stage B Implementation Task（任务单）

**Spec:** `docs/PHASE3_1_STAGE_B_STRICT_SPEC.md` (v3, SHA-256 `7203fb0d…f26c1`)
**Contract:** `docs/PHASE3_1_CONTRACT.md` (v1.3, Stage A.3, SHA-256 `49975ef4…de7b`)
**Phase / Stage:** Phase 3.1 — Stage B — Prediction Adapter Implementation (additive only)
**Branch:** `v2026c`
**Status:** AUTHORIZED — executing
**Task ticket type:** process/audit artifact (Phase 3.0 convention), **not** an implementation file.

---

## 0. Authorization

Per Stage B spec §1, all gates G-A3-1 … G-A3-11 are satisfied:

| Gate | Status | Evidence |
| --- | --- | --- |
| G-A3-1 | PASS | Stage A.3 reconciliation delivered (contract v1.3); completion summarised in §1.1 |
| G-A3-2 | PASS | All mandatory A3 criteria pass (contract §10 `A-28`…`A-33`) |
| G-A3-3 | PASS | `docs/PHASE3_1_CONTRACT.md` present |
| G-A3-4 | PASS | Contract v1.3; SHA-256 `49975ef44b9a3f87909c8fb9f9c1af30f6efbc974f2a8b8efe3caf04f5fdde7b` |
| G-A3-5 | PASS | UP/not-UP reconciled (contract §1.3.2) |
| G-A3-6 | PASS | `SELL = not-UP` accepted (CD-OPEN-1, 2026-11-14) |
| G-A3-7 | PASS | `positive_class_label` / `p_up` / `p_not_up` / `p_down` unambiguous (contract §1.3) |
| G-A3-8 | PASS | CD-OPEN-4 hardening requirements stated (contract §1.3.2 CD-D9/CD-D11, §10 `A-32`) |
| G-A3-9 | PASS | Model SHA-256 + scaler SHA-256 available (§1.1) |
| G-A3-10 | PASS | Explicit user authorization quoted below |
| G-A3-11 | PASS | CONTRACT-CONFIRM outcomes recorded (§3) |

**Exact user authorization (quoted):**

> 授权开始 Stage B（推荐）

> 放心干。老登LLM们讨论的差不多了。该干点实际的东西了。我去睡觉了。明天早上看你的好消息。谢谢

---

## 1. Preflight evidence (spec §1.1)

### 1.1 Repository

| Item | Value |
| --- | --- |
| Repository root | `/home/ubuntu/projects/ai_training_cnn` |
| Branch | `v2026c` |
| `git rev-parse HEAD` (before) | `10147858af1ff3067dc413330b369911b8186e91` |
| Contract version / SHA-256 | v1.3 / `49975ef44b9a3f87909c8fb9f9c1af30f6efbc974f2a8b8efe3caf04f5fdde7b` |
| Model artifact SHA-256 | `94c8751df33daee5190e42634d823bcb08d4a0dbc1e0a2cf2f3e8cfbd91d5942` (`trade_model_xgb.json`) |
| Scaler artifact SHA-256 | `031ea8068a2b8309829624b30acb7db2cde40ce4452240cf423619fae4b2cd8c` (`scaler.joblib`) |
| Features SHA-256 | `3e9e319cae45dc405cf55ba49a2dd87fad8beacb4148d52066b2c79a697605da` |
| Manifest SHA-256 | `9b860295166d06c1445e5b335f621af6dc5d60ad2a905a9807c512a941ca27bb` |
| Accepted CD decision | `CD-OPEN-1: SELL = not-UP` → `CD = VERIFIED` for `trade_model_xgb.json@94c8751d…d5942` (`docs/PHASE3_1_CD_EVIDENCE.md` §F/§G) |
| Stage A.3 acceptance report reference | `docs/PHASE3_1_CONTRACT_A3.md` (spec) + delivered contract v1.3 |
| Runtime | Python 3.12.15 · xgboost 2.0.3 · scikit-learn 1.5.2 · numpy 1.26.4 · pytest 9.1.1 |

### 1.2 `git status --short` (before)

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

Pre-existing work is preserved. No reset / clean / stash / checkout. No commit. No deployment.

### 1.3 Source correspondence

Working tree sources correspond to the declared baseline `10147858`:
`data_pipeline.py`, `fx_trade_bot_ml.py`, `strategy_decision.py` are unmodified (`git status` clean for these).

---

## 2. Implementation map (spec §2.1)

| Item | Decision / evidence |
| --- | --- |
| Adapter module | **`ml/prediction_adapter.py`** (new; spec §2.2 — no embedding in existing modules) |
| Adapter entry point | `run_prediction(*, model, scaler, feature_list, X, pair, timeframe, bar_time, clock, registry=None, identity=None, model_status=None, diagnostics=None) -> PredictionResult` |
| NOT_RUN helper | `build_not_run_result(*, pair, timeframe, bar_time, clock, diagnostics=None) -> PredictionResult` |
| Loader entry point | `load_model_with_identity(*, model_path, scaler_path, clock, model_loader=None, scaler_loader=None, after_read_hook=None) -> LoadedModelIdentity` |
| Registry entry point | `CDRegistryHandle.load(path) -> CDRegistryHandle` (loaded once at startup; read-only) |
| PredictionResult | Frozen dataclass; 18 contract fields; `diagnostics` = `MappingProxyType` over defensive copy; all validation in `__post_init__` |
| Existing inference path reused | `data_pipeline._build_matrix(X, feature_list, scaler)` (feature-contract + scaling authority) then `model.predict_proba(scaled)`. **`predict_p_up()` is deliberately NOT used** because it selects the column via `positive_class_index()`; Stage B requires the fixed structural `EXTRACTION_INDEX=1`. |
| Model availability | Phase 3.0 `ModelInitResult.status` (`fx_trade_bot_ml.py:33-40`); usable = `READY`; unusable = `UNAVAILABLE` / `INCOMPATIBLE` / `LOAD_FAILED` |
| Artifact loading | One read → SHA-256 → construct from same in-memory bytes (`load_method=BYTES`; `TEMPFILE` fallback if the library cannot load from memory) |
| Artifact / scaler hash | Computed once in `load_model_with_identity`; immutable binding in `LoadedModelIdentity`; adapter never recalculates |
| CD Registry | `config/model_cd_registry.json`; `schema_version=1`; loaded once; read-only; runtime SHA-256 exposed |
| Feature validation | `data_pipeline._build_matrix` (`data_pipeline.py:403-455`) |
| Exception mapping | Closed table (§4 below) |
| Caller precondition | Actual bars-count owner stays the caller (`data_guard.has_min_bars`; engine uses a 20-bar floor). Stage B ships only `build_not_run_result`; wiring is Stage C |
| Clock injection | `UtcClock` (production default) / test fake clock; no direct system-clock call in the adapter |
| Test modules | `tests/test_prediction_adapter.py` (B-T01…B-T76); fixtures via `tmp_path` only |
| File allowlist | §5 below |

### 2.2 Existing A.2-era seam (context, not modified)

`ml/live_prediction_engine.py` (committed at `cd3b072`, A.2) already contains a draft
`PredictionResult`/`LivePredictionEngine`, and `ml/integration_hook.py` defines
`evaluate_prediction_guard`. These are **not modified** by Stage B: they are the A.2
draft seam superseded by this stricter adapter, and consumer migration is Stage C scope
(spec §17.2). The committed convention `PredictionReason.NONE` for the READY success
placeholder is reused here (§3, CONTRACT-CONFIRM #5).

---

## 3. CONTRACT-CONFIRM outcomes (spec §0.5, G-A3-11, §22.10)

| # | Item | Contract position | Resolution |
| --- | --- | --- | --- |
| 1 | §5.2 `at_threshold` placement | Contract §1.3 defines **no** `at_threshold` field → silent | Carry in `diagnostics` under key `at_threshold` (bool for READY, absent otherwise). Not a top-level field. |
| 2 | §5.3 `positive_class_label` in UNINTERPRETABLE | Contract §1.3.2 UNINTERPRETABLE example omits it; `p_up` explicitly `None`; CD-T10 forbids inventing `"UP"` | **None** in UNINTERPRETABLE; runtime class value carried in diagnostics as `runtime_class_label_at_extraction_index`. |
| 3 | §7.3.5 row-sum rule | Contract silent | **Include** with `ROW_SUM_TOLERANCE = 1e-5`; failure → INVALID / `PREDICTION_OUTPUT_MALFORMED`. |
| 4 | §7.4 `cd_failure_cause` diagnostic vocabulary | Contract §1.3 `diagnostics` is "supplementary, non-authoritative"; contract does not forbid extra keys | **Allowed in diagnostics only**; never status/reason authority. |
| 5 | §5.5 READY success reason | Contract §1.2 defines no READY reason and forbids inventing one; committed A.2 convention uses `PredictionReason.NONE` | READY pairs with the sentinel `PredictionReason.NONE` (`"NONE"` = "no failure reason"). No new reason invented. |

---

## 4. Closed exception mapping (spec §8 — derived from actual code)

| Exception / condition | Source | Classification |
| --- | --- | --- |
| `ModelInitResult.status ∈ {UNAVAILABLE, INCOMPATIBLE, LOAD_FAILED}` | `fx_trade_bot_ml.py:33-40, 249-298` | UNAVAILABLE / MODEL_NOT_USABLE |
| Runtime model object absent (`model is None`) | adapter step 1 | UNAVAILABLE / MODEL_NOT_USABLE |
| Required scaler absent (`scaler is None`) | adapter step 1 | UNAVAILABLE / MODEL_NOT_USABLE |
| `ScalerMissingError` | `data_pipeline.py:44-45, 409-412` | UNAVAILABLE / MODEL_NOT_USABLE |
| Known model load failure (malformed bytes in loader) | `load_model_with_identity` | UNAVAILABLE / MODEL_NOT_USABLE (no identity produced) |
| `InferenceFeatureError` | `data_pipeline.py:40, 415-453` | INVALID / FEATURE_CONTRACT_VIOLATION |
| `DimensionMismatchError` (if ever raised) | `data_pipeline.py:48-49` | INVALID / FEATURE_CONTRACT_VIOLATION |
| Any unclassified exception at the inference boundary | adapter step 3 | ERROR / EXECUTION_ERROR |

Pre-inference API contract violations **raise** (spec §6.2): invalid required argument,
invalid injection, wrong mandatory argument type, naive `bar_time`.

---

## 5. File allowlist (spec §19)

### 5.1 Implementation files (touched)

1. `ml/prediction_adapter.py` — new adapter module (mandatory)
2. `config/model_cd_registry.json` — new registry, production record only
3. `tests/test_prediction_adapter.py` — new focused adapter tests

### 5.2 Process/audit artifacts (not implementation)

4. `docs/PHASE3_1_STAGE_B_IMPLEMENTATION_TASK.md` — this task ticket
5. `docs/PHASE3_1_STAGE_B_COMPLETION_REPORT.md` — §22 required completion report

### 5.3 Explicitly NOT touched

`docs/Development_plan.md`, training scripts, model artifacts, the Phase 3.0
initialization path, `fx_trade_bot_ml.py`, `strategy_decision.py`, `data_pipeline.py`,
`fx_trade_bot.py`, `ml/live_prediction_engine.py`, `ml/integration_hook.py`,
attribution consumers, scheduler, `run.env`. No commit. No deployment.

---

## 6. Task list

| ID | Task | Status |
| --- | --- | --- |
| SB-01 | Preflight + CONTRACT-CONFIRM + task ticket | DONE |
| SB-02 | Create `config/model_cd_registry.json` | DONE |
| SB-03 | Implement `ml/prediction_adapter.py` | DONE |
| SB-04 | Implement `tests/test_prediction_adapter.py` (B-T01…B-T76) | DONE |
| SB-05 | Run tests + static checks + regression evidence; completion report | DONE |
