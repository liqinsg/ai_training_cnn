# PHASE3_0_IMPLEMENTATION_TASK.md

**Version:** 1.0  
**Status:** IMPLEMENTATION TASK — PROPOSED FOR EXECUTION  
**Project:** v685 ML System  
**Repository:** `ai_training_cnn`  
**Target branch:** `v2026c`  
**Design authority:** `PHASE3_REDESIGN.md v1.2`  
**Reviewed source baseline:** `e13c3e47d083ad64813b17793a440dbdd129dd29`

---

# 0. Mission

## 0.1 Objective

Implement Phase 3.0 Runtime Containment and Observability.

The primary objective is to ensure that an ML initialization or prediction failure cannot unnecessarily interrupt independent existing-position management, while an unavailable ML assessment cannot be treated as a valid vote or silently authorize a new ML-dependent entry.

The secondary objective is to establish runtime artifact integrity:

- No live-cycle training.
- No live-cycle artifact publication.
- No silent model fallback.
- No accidental mixing of incompatible model artifacts.
- Explicit model status and release identity in runtime records.
- Visible release identity on both live hosts.

This is a bounded engineering task.

**Do not conduct another repository-wide audit. Do not redesign the complete ML architecture. Do not expand the scope into unrelated trading logic.**

## 0.2 Required outcome

At completion, the runtime must demonstrate the following:

1. Model initialization failure is isolated.
2. Independently reachable existing-position management remains reachable.
3. Model-dependent entry calculations do not consume fabricated or invalid ML votes.
4. Live-cycle training and artifact writes are prevented.
5. Artifact load failures have explicit outcomes.
6. Model/release identity is visible in runtime diagnostics.
7. Normal healthy-model behavior remains unchanged, except for explicitly approved safety changes.

## 0.3 Authorization boundary

This document defines an implementation task. It does not authorize unrelated changes or automatic live deployment.

The following owner-approval boundary is mandatory:

Any code change that changes entry authorization, exit behavior, position sizing, SL/TP, or live order flow requires explicit project-owner approval.

In particular, the requirement that unavailable ML must not authorize a new entry is a safety requirement, but implementing it may alter existing entry behavior when ML is unavailable.

Therefore:

- The implementation agent may inspect the relevant path and prepare the minimal patch.
- The implementation agent may implement diagnostics, artifact protections, and failure isolation that do not cross the owner-approval boundary.
- Before applying a change that alters entry authorization, the agent must present the exact affected path, current behavior, proposed behavior, and minimal diff for approval.
- No live order test or live deployment is authorized by this task.

Do not interpret approval of this task document as approval of every possible behavior-changing patch.

---

# 1. Strict scope

## 1.1 In scope

| ID | Work item | Priority |
|---|---|---|
| P0-01 | Trace actual runtime entrypoint and `ensure_model()` call path | P0 |
| P0-02 | Establish explicit ML initialization status | P0 |
| P0-03 | Isolate ML initialization failure from independent position management | P0 |
| P0-04 | Guard ML-dependent confluence and Step 7 operations | P0 |
| P0-05 | Identify and prevent live-cycle training and artifact writes | P0 |
| P0-06 | Define missing/incompatible/failed-load runtime outcomes | P0 |
| P0-07 | Add model/release identity to runtime diagnostics | P0 |
| P0-08 | Test healthy-path behavior preservation | P0 |
| P0-09 | Verify artifact immutability | P0 |
| P1-01 | Record resolved model paths and profile identity | P1 |
| P1-02 | Make cross-host release differences observable | P1 |
| P1-03 | Add focused integration and failure-injection tests | P1 |

## 1.2 Out of scope

The following must not be implemented in this task:

- Full prediction-result contract redesign.
- Full `generate_signal()` redesign.
- Directional probability threshold tuning.
- Neutral-band design.
- MC scoring redesign beyond protecting existing cache values and preventing invalid use.
- Strength calculation redesign.
- Profile conviction recalibration.
- Feature-engine replacement.
- Indicator algorithm replacement.
- Training pipeline redesign.
- New model architecture.
- Model retraining or promotion.
- New artifact release framework.
- Full synchronized OOS evaluation.
- Purge/embargo implementation.
- Bootstrap evaluation.
- D1 TP behavior investigation or modification.
- D2–D9 execution-risk refactors.
- OANDA API, order, position-sizing, SL/TP, or exit refactors.
- General cleanup or unrelated code formatting.

If a discovered issue belongs to a later phase or a separate track, document it and leave it unchanged.

---

# 2. Preflight and source verification

This is a bounded source verification step, not a broad audit.

## 2.1 Repository preflight

Before changing any file, record:

- Repository root.
- Current branch.
- Current HEAD commit.
- Working-tree status.
- Existing uncommitted changes.
- Python environment/version.
- Relevant dependency versions.
- Existing test framework and test command.

Expected target branch: `v2026c`.

The reviewed baseline is `e13c3e47d083ad64813b17793a440dbdd129dd29`.

If HEAD differs from the reviewed baseline:

1. Do not reset, rebase, or switch branches.
2. Determine whether the relevant runtime files have changed since the reviewed baseline.
3. Report the differences that affect this task.
4. Continue only if the target branch and relevant source state are understood.

If the working tree contains unrelated user changes:

- Do not overwrite them.
- Do not include them in the task diff.
- Stop if they make the target files ambiguous or unsafe to modify.

## 2.2 Identify the actual runtime entrypoint

Do not assume that the file containing `main()` is necessarily the process entrypoint.

Trace the actual live runtime path beginning at the scheduled runner and its imported modules.

Candidate areas already identified in the design:

- `scheduled_runner_v3.py`
- `fx_trade_bot.py`
- `fx_trade_bot_ml.py`
- `data_pipeline.py`
- Profile/model path resolution
- Runtime configuration loading

Verify which files are actually involved in the current branch.

Do not modify the scheduled runner unless it is demonstrably necessary for the bounded task.

## 2.3 Required call-path trace

Produce one concise call-path diagram showing:

1. Live runner entry.
2. Bot initialization.
3. `ensure_model()` invocation.
4. Model loading and validation.
5. Prediction generation.
6. Multi-timeframe confluence.
7. Step 5.
8. Step 7.
9. Existing-position and owned-position management.
10. QUICK-FLIP, where applicable.
11. Entry authorization and execution boundary.

For each relevant branch, classify it:

- `ML_REQUIRED`
- `ML_OPTIONAL`
- `ML_INDEPENDENT`
- `UNKNOWN`

`UNKNOWN` must not be treated as independent.

The call-path trace must identify every model-dependent branch before and after `ensure_model()`.

## 2.4 Required source evidence

For each modified or protected path, record:

- File path.
- Function or method name.
- Actual caller.
- Actual callee.
- Current exception behavior.
- Current return semantics.
- Whether the path can execute when ML initialization fails.
- Whether it can influence entry or existing-position management.

Use exact line references from the current checkout in the implementation report.

Do not invent line references or assume that v1.2's candidate file list is exhaustive.

## 2.5 Stop conditions

Stop and report before implementation if any of the following is true:

- The actual live entrypoint cannot be established.
- The `ensure_model()` call path cannot be traced sufficiently to isolate failure.
- Existing-position management cannot be distinguished from ML-dependent entry logic.
- A proposed fix would require an unapproved change to exits, SL/TP, sizing, or order flow.
- The current working tree prevents safe modification of relevant files.
- The required tests would require placing real OANDA orders.

Do not turn a stop condition into a reason for broad refactoring.

---

# 3. Runtime ML status contract

## 3.1 Required states

The runtime must distinguish model initialization status from prediction results.

At minimum:

| State | Definition | Permitted use |
|---|---|---|
| `READY` | Compatible approved model loaded and validated | Prediction may be requested |
| `UNAVAILABLE` | No usable model can be provided | No ML-dependent entry authorization |
| `INCOMPATIBLE` | Artifact does not match required runtime contract | Artifact must not be used |
| `LOAD_FAILED` | Artifact exists but loading or validation failed | Artifact must not be used |

A missing artifact may be represented as `UNAVAILABLE` with reason `MODEL_MISSING`.

A stale artifact must have an explicit policy outcome. Do not assume stale means either usable or unusable without checking the existing approved compatibility policy.

The implementation may use an enum, dataclass, structured result, or equivalent explicit representation.

Exact names may differ, but semantics must not.

## 3.2 Status and reason must be separate

A status identifies the broad runtime condition.

A reason identifies what happened.

Suggested reason codes:

- `MODEL_READY`
- `MODEL_MISSING`
- `MODEL_STALE`
- `MODEL_INCOMPATIBLE`
- `MODEL_LOAD_EXCEPTION`
- `SCALER_MISSING`
- `SCALER_INCOMPATIBLE`
- `FEATURE_CONTRACT_MISMATCH`
- `MODEL_VALIDATION_FAILED`
- `UNKNOWN_LOAD_FAILURE`

These are suggested identifiers, not mandatory API names.

Do not encode unrelated conditions into a single generic `None`.

## 3.3 Initialization behavior

When `ensure_model()` succeeds:

- Preserve the existing model object and healthy-path behavior.
- Record `READY`.
- Record the model/release identity.

When `ensure_model()` fails:

- Record the appropriate explicit status and reason.
- Do not silently substitute a neutral prediction.
- Do not silently create a new model.
- Do not start training.
- Do not publish or rewrite artifacts.
- Do not abort independently reachable position-management paths.

## 3.4 Prediction failure

Phase 3.0 must not redesign the complete prediction-result contract.

However, when a prediction fails in a model-dependent caller:

- Record that the required prediction is unavailable.
- Do not interpret the failure as a valid directional or neutral prediction.
- Do not manufacture an XGB vote.
- Do not reuse an old prediction without an existing, verified freshness contract.
- Do not silently replace the result with a default score.

The full typed prediction/abstention contract remains Phase 3.1.

---

# 4. Failure isolation and runtime control flow

## 4.1 Core requirement

The current risk is that model initialization may occur before existing-position management.

The task must establish whether a failure in `ensure_model()` prevents the runtime from reaching independent position-management paths.

If it does, implement the smallest safe isolation change.

Do not restructure the entire `main()` function.

## 4.2 Required behavior

When model initialization fails:

1. Record the model failure.
2. Preserve the runtime cycle sufficiently to reach independent management paths.
3. Do not execute ML-dependent entry scoring as though a valid model exists.
4. Do not create a synthetic vote.
5. Do not submit an ML-dependent new entry.
6. Preserve existing-position management wherever the call path is genuinely independent.
7. Preserve existing approved exit behavior.
8. Preserve error visibility.

## 4.3 Required path verification

Verify the actual dependencies of:

- Step 5.
- Owned-position logic.
- QUICK-FLIP.
- Multi-timeframe confluence.
- Step 7.
- Entry authorization.

Do not assume that a function is independent merely because it does not directly call `ensure_model()`.

Inspect its downstream dependencies and data requirements.

If an existing-position path uses an ML-dependent value, classify that dependency explicitly. Do not silently substitute a value to make the path continue.

## 4.4 Exception boundaries

Catch model initialization failures at the narrowest appropriate boundary.

Do not:

- Add a broad `except Exception: pass`.
- Hide unexpected programming errors.
- Convert every exception into `MODEL_MISSING`.
- Suppress failures from independent position-management logic.
- Continue into a model-dependent branch with invalid state.

The runtime should distinguish:

- Expected model availability failures.
- Model loading/validation failures.
- Unexpected programming errors.

Unexpected errors must remain visible.

## 4.5 Entry authorization approval checkpoint

The implementation must identify the exact path where unavailable ML can influence a new-entry decision.

Before modifying that path, produce:

| Required item | Description |
|---|---|
| Current behavior | What happens today when ML is unavailable |
| Reachability | Exact caller/callee path |
| Current vote/score | Whether missing ML is converted, omitted, or substituted |
| Proposed behavior | Exact change when ML is unavailable |
| Healthy-path impact | Evidence that normal READY behavior is unchanged |
| Tests | Failure injection and regression tests |
| Diff | Minimal proposed code diff |

Present this checkpoint for explicit project-owner approval before applying the entry-authorization behavior change.

No unrelated entry scoring changes are permitted.

---

# 5. Artifact write protection

## 5.1 Scope

Identify all live-runtime paths that can:

- Train a model.
- Call `fit()`.
- Save a model.
- Save a scaler.
- Write model configuration.
- Write feature metadata.
- Rewrite a legacy artifact.
- Publish a candidate or promoted artifact.

Known candidate methods include:

- `ModelWrapper.fit()`
- `ModelWrapper.save()`
- `ModelWrapper.load()`

Verify the actual call sites and all other relevant write paths.

Do not assume that these methods are only called by live runtime or only called by offline training.

## 5.2 Required behavior

The live runtime must not train or publish artifacts.

This protection applies to the live orchestration path, not indiscriminately to the offline training tools.

Offline training must remain usable.

The implementation must therefore:

- Block live-cycle calls that initiate training or artifact publication.
- Preserve explicitly invoked offline training workflows.
- Avoid globally disabling shared `fit()` or `save()` methods if they are required by offline workflows.
- Record any blocked live write attempt.
- Make the failure visible.

If a write attempt is blocked, do not silently pretend the write succeeded.

## 5.3 Missing and stale artifacts

| Condition | Required behavior |
|---|---|
| Artifact missing | Explicit unavailable status; no training |
| Artifact stale | Apply explicit existing compatibility policy; no runtime retraining |
| Artifact incompatible | Reject artifact |
| Model load failure | Record `LOAD_FAILED`; no silent fallback |
| Scaler missing | Reject the incomplete release |
| Model/scaler mismatch | Reject the release |
| Feature-contract mismatch | Reject the release |
| Legacy fallback path | Do not silently load and republish as a new release |

Do not invent a new artifact-promotion policy in Phase 3.0.

## 5.4 Artifact immutability

Before and after the test run, record hashes for all relevant approved model artifacts.

At minimum, cover:

- Model file.
- Scaler file.
- Model configuration.
- Feature metadata, if present.

The exact inventory must be derived from the actual artifact layout.

Acceptance requires that the live-runtime tests do not change the bytes of approved artifacts.

Do not run a training command against the live artifact directory.

---

# 6. Model and host observability

## 6.1 Required diagnostic fields

For each runtime initialization attempt, record:

| Field | Requirement |
|---|---|
| Timestamp | Runtime event timestamp |
| Host ID | Identifies the local execution host |
| Profile | Resolved active profile |
| Model status | `READY`, `UNAVAILABLE`, `INCOMPATIBLE`, or `LOAD_FAILED` |
| Reason | Explicit status reason |
| Artifact path | Resolved path, with sensitive path details handled appropriately |
| Release ID | Manifest/model release ID, when available |
| Model hash | Hash, when available |
| Scaler hash | Hash, when available |
| Feature contract ID | Identity, when available |
| Dependency/backend identity | Relevant inference dependency information |

Use existing logging conventions where possible.

Do not add an external telemetry service or network communication.

Do not log credentials, API tokens, account secrets, or unrelated sensitive information.

## 6.2 Host identity

The live deployment has two hosts:

- Oracle VM.
- Laptop.

Both run `scheduled_runner_v3.py --live` against one OANDA account, according to the project-owner-provided deployment context.

Do not assume this is independently verified by the current source checkout.

Each host must record enough local identity to distinguish its runtime records.

Use existing deployment configuration where available. If no host label exists, use a safe local identifier without introducing network communication.

## 6.3 Cross-host release comparison

The task must establish whether both hosts resolve:

- The same artifact path.
- Different local artifact paths.
- The same model/release identity.
- Different model/release identities.

Do not assume matching filenames mean identical artifacts.

Do not introduce:

- Network-based artifact synchronization.
- Shared write locks.
- A new shared artifact store.
- Automatic release copying.
- Deployment topology changes.

The deliverable is visibility and evidence, not deployment redesign.

---

# 7. Healthy-path preservation

## 7.1 Principle

When a compatible approved model loads successfully, normal existing behavior must remain unchanged.

The task is runtime containment, not a strategy rewrite.

## 7.2 Required regression evidence

Compare before/after behavior using controlled inputs and mocked external execution boundaries.

Cover at least:

- Model initialization success.
- Prediction success.
- Existing scoring inputs.
- Existing profile thresholds.
- Existing multi-timeframe flow.
- Existing entry decision output.
- Existing position-management reachability.
- Existing exit-management reachability.

For unchanged paths, compare relevant outputs and decision traces.

If an output differs, identify the exact cause.

Do not dismiss a difference as harmless without evidence.

## 7.3 No live execution

All tests must use mocks, fixtures, or isolated test accounts that cannot place real orders.

This task does not authorize:

- Real OANDA order submission.
- Real position modification.
- Live SL/TP changes.
- Live deployment.
- Automatic rollout to either host.

---

# 8. Required test plan

Use the repository's existing test framework and conventions. Do not introduce a new testing framework without a specific necessity.

Record exact test commands and results.

## 8.1 Initialization tests

| ID | Scenario | Expected result |
|---|---|---|
| P3T-01 | Normal approved model load | `READY`; release identity recorded |
| P3T-02 | Model artifact missing | `UNAVAILABLE`; no training |
| P3T-03 | Model load raises exception | `LOAD_FAILED`; reason recorded |
| P3T-04 | Model/scaler incompatible | Release rejected |
| P3T-05 | Feature contract incompatible | Release rejected |
| P3T-06 | Stale artifact | Explicit compatibility outcome; no retraining |
| P3T-07 | Legacy fallback path reached | No silent fallback or republishing |

## 8.2 Runtime failure-isolation tests

| ID | Scenario | Expected result |
|---|---|---|
| P3T-08 | `ensure_model()` forced to raise | Failure recorded; independent management remains reachable |
| P3T-09 | Model initialization returns unavailable | No model-dependent entry calculation consumes a fabricated vote |
| P3T-10 | Prediction raises during confluence | Explicit prediction failure; no synthetic vote |
| P3T-11 | Step 5 path with ML unavailable | Actual dependency behavior verified |
| P3T-12 | Owned-position path with ML unavailable | Independent management remains reachable |
| P3T-13 | QUICK-FLIP with ML unavailable | Existing reachability and dependencies verified |
| P3T-14 | Step 7 with ML unavailable | No invalid model-dependent result consumed |
| P3T-15 | Unexpected programming exception | Not swallowed as a normal unavailable state |

P3T-11 to P3T-14 must test the actual current call graph. If a path is not independent of ML, record that fact rather than manufacturing an input to force it through.

## 8.3 Entry-path tests

| ID | Scenario | Expected result |
|---|---|---|
| P3T-16 | ML unavailable at entry authorization | No invalid ML vote or score substitution |
| P3T-17 | ML unavailable but existing position present | Existing independent management remains reachable |
| P3T-18 | Healthy model entry path | Existing output preserved |
| P3T-19 | Missing prediction in multi-timeframe flow | No implicit neutral or directional vote |

The final behavior-changing entry tests must be completed only after the owner-approval checkpoint in Section 4.5.

## 8.4 Artifact integrity tests

| ID | Scenario | Expected result |
|---|---|---|
| P3T-20 | Live runtime initialization | No model/scaler/config/feature artifact writes |
| P3T-21 | Live runtime attempts training | Training blocked and attempt recorded |
| P3T-22 | Live runtime attempts artifact save | Write blocked and attempt recorded |
| P3T-23 | Offline training workflow | Existing offline workflow remains functional |
| P3T-24 | Before/after artifact hashes | Approved artifact bytes unchanged |

## 8.5 Observability tests

| ID | Scenario | Expected result |
|---|---|---|
| P3T-25 | Model READY | Host, profile, path and release identity recorded |
| P3T-26 | Model unavailable | Host, profile and failure reason recorded |
| P3T-27 | Two hosts with different releases | Difference can be identified from records |
| P3T-28 | Missing manifest/release ID | Explicitly reported; no invented identity |

## 8.6 Regression and integration tests

| ID | Scenario | Expected result |
|---|---|---|
| P3T-29 | Healthy-path regression | Existing decisions unchanged |
| P3T-30 | Failure-injection integration | ML failure does not prevent independent management |
| P3T-31 | Full mocked runtime cycle | No real order submission; status and paths are traceable |
| P3T-32 | Repeated initialization failure | No hidden retry loop that trains or writes artifacts |

A test may be marked `NOT APPLICABLE` only with a source-backed explanation. Do not mark untested behavior as passed.

---

# 9. Implementation rules

## 9.1 Minimal patch

Modify only files required for the scoped behavior.

Prefer:

- Narrow exception boundaries.
- Explicit runtime status.
- Small caller-side guards.
- Existing logging infrastructure.
- Existing test conventions.

Avoid:

- New architecture layers without necessity.
- Large function rewrites.
- Broad API changes.
- Unrelated renaming.
- Unrelated formatting.
- General cleanup.
- Silent fallback logic.

## 9.2 No unrelated modifications

Do not modify:

- `docs/Development_plan.md`
- `PHASE3_REDESIGN.md`
- Training evaluation methodology.
- Feature-generation algorithms.
- Profile scoring parameters.
- Entry thresholds.
- Exit logic.
- SL/TP logic.
- Position sizing.
- OANDA API configuration.
- Scheduler cadence.

If an unavoidable dependency requires a change outside this list, stop and explain why before making it.

## 9.3 No dependency changes

Do not install, upgrade, downgrade, or remove dependencies as part of this task.

If a missing dependency prevents a required test:

- Record the exact missing dependency.
- Record the affected test.
- Do not modify the environment to work around it.
- Report the blocker.

## 9.4 No hidden behavior changes

Every behavior-changing line must be identified in the final diff report.

For each such change, state:

- Previous behavior.
- New behavior.
- Trigger condition.
- Expected runtime effect.
- Relevant test.
- Whether owner approval was required and obtained.

---

# 10. Execution sequence

Follow this sequence. Do not skip ahead.

## Stage A — Bounded source confirmation

Deliver:

1. Repository preflight.
2. Actual live entrypoint.
3. `ensure_model()` call path.
4. Relevant branch classification.
5. Position-management dependency trace.
6. Runtime artifact write-path inventory.
7. Model path resolution by profile.
8. Exact proposed minimal change list.

This stage is not a broad audit. Do not inspect unrelated strategy components.

**Gate A:** If the source evidence reveals an owner-approval boundary or an unresolved call-path dependency, report it before making the relevant behavior change.

## Stage B — Runtime status and failure isolation

Implement:

1. Explicit initialization status.
2. Narrow failure isolation.
3. Independent management reachability protection.
4. Model-dependent caller guards.
5. Explicit diagnostics.

Do not redesign the prediction-result contract.

## Stage C — Live artifact containment

Implement:

1. Live-cycle training prevention.
2. Live-cycle artifact-write prevention.
3. Explicit missing/incompatible/load-failure behavior.
4. Preservation of offline training workflows.
5. Artifact hash verification.

## Stage D — Host and release observability

Implement:

1. Host identity.
2. Profile identity.
3. Resolved artifact path.
4. Release/model identity.
5. Load status and reason.
6. Cross-host comparison evidence.

No network synchronization or deployment redesign.

## Stage E — Tests and regression

Execute the required tests in Section 8.

Provide evidence for:

- Failure isolation.
- Existing-position management reachability.
- Healthy-path preservation.
- No invalid ML vote.
- No live artifact writes.
- Artifact immutability.
- Host/release identity.

## Stage F — Final report

Produce the completion report in Section 12.

Do not deploy to either live host.

---

# 11. Acceptance criteria

Phase 3.0 is complete only when all mandatory criteria are supported by evidence.

| Acceptance ID | Requirement | Mandatory |
|---|---|---|
| AC-01 | Actual live runtime entrypoint and call graph established | Yes |
| AC-02 | `ensure_model()` failure has explicit status and reason | Yes |
| AC-03 | Independent position-management reachability verified | Yes |
| AC-04 | QUICK-FLIP dependency/reachability verified | Yes |
| AC-05 | ML-dependent callers cannot consume fabricated votes | Yes |
| AC-06 | Entry behavior under ML unavailability matches the explicitly approved contract | Yes |
| AC-07 | Live runtime cannot train or publish model artifacts | Yes |
| AC-08 | Offline training remains functional | Yes |
| AC-09 | Missing/incompatible/failed-load behavior explicit | Yes |
| AC-10 | Approved artifact bytes remain unchanged | Yes |
| AC-11 | Model/release identity recorded per host | Yes |
| AC-12 | Cross-host release differences visible | Yes |
| AC-13 | Healthy-path regression tests pass | Yes |
| AC-14 | No unapproved changes to exit, sizing, SL/TP, or order flow | Yes |
| AC-15 | Exact diff and test evidence supplied | Yes |

A test failure must not be hidden by weakening the acceptance criterion.

If an acceptance criterion cannot be verified, mark it `NOT VERIFIED` and explain the exact missing evidence.

Do not claim Phase 3.0 completion while a mandatory acceptance criterion is unverified.

---

# 12. Required completion report

The implementation agent must return the following report.

## A. Executive result

Choose exactly one:

- `PASS — PHASE 3.0 COMPLETE`
- `PARTIAL — SPECIFIC ACCEPTANCE ITEMS REMAIN`
- `BLOCKED — SOURCE OR APPROVAL ISSUE`
- `FAILED — IMPLEMENTATION DID NOT MEET REQUIREMENTS`

## B. Repository state

- Repository path:
- Branch:
- Base commit:
- Final commit:
- Working-tree status:
- Python version:
- Dependency status:

Do not commit unless explicitly instructed.

## C. Source-path evidence

Include:

- Actual runtime entrypoint.
- `ensure_model()` call path.
- Relevant caller/callee trace.
- Position-management path.
- QUICK-FLIP path.
- Entry authorization boundary.
- Exact source file and line references.

## D. Changed files

For each changed file:

| File | Functions changed | Reason | Behavior impact |
|---|---|---|---|

Include the complete diff summary.

## E. Runtime state behavior

Document:

- State definitions.
- Reason codes.
- Initialization failure behavior.
- Prediction failure behavior.
- Missing/stale/incompatible artifact behavior.

## F. Artifact integrity

Include:

- All live write paths found.
- How each path is prevented.
- Offline training compatibility evidence.
- Before/after artifact hashes.
- Any unresolved write path.

## G. Host/release identity

Provide representative runtime records from each available host.

Include:

- Host ID.
- Profile.
- Artifact path.
- Release ID/hash.
- Feature contract identity.
- Status and reason.

If only one host is available during implementation, state that cross-host runtime verification remains incomplete. Do not claim both hosts were tested.

## H. Test evidence

| Test ID | Command | Result | Evidence |
|---|---|---|---|

Include failures and skipped tests.

Do not report a test as passed merely because the test process exited without an exception if the relevant assertion was not exercised.

## I. Healthy-path regression

Describe:

- Inputs used.
- Outputs compared.
- Differences found.
- Evidence that normal READY behavior remains unchanged.

## J. Owner approval

List each behavior-changing patch that crossed an approval boundary.

For each:

- Approval required?
- Approval obtained?
- Exact approved scope.
- Implemented scope.

If approval was not obtained, the relevant change must not have been applied.

## K. Explicit exclusions confirmed

Confirm whether the task changed any of the following:

- Entry scoring.
- Exit logic.
- Position sizing.
- SL/TP.
- QUICK-FLIP behavior.
- OANDA order flow.
- Scheduler behavior.
- Training/evaluation methodology.

The expected answer is `NO`, except for any specifically approved change. Explain any exception.

## L. Remaining blockers

List only concrete blockers, with:

- Evidence.
- Impact.
- Required next action.
- Owning phase or separate track.

Do not append unrelated audit findings.

---

# 13. Final instruction to the implementation agent

This task is about **runtime containment, not strategy improvement**.

Do not optimize scores.  
Do not tune thresholds.  
Do not retrain.  
Do not replace the feature engine.  
Do not refactor exits.  
Do not change SL/TP.  
Do not change position sizing.  
Do not change order execution.  
Do not expand into a repository-wide audit.

The required engineering result is narrow:

**When ML works, preserve the existing healthy path. When ML fails, isolate that failure, keep genuinely independent position management reachable, prevent invalid ML results from being used, and leave the live artifact set untouched.**

Every change must be supported by source evidence and tests.

If the implementation cannot satisfy a requirement without crossing an approval boundary, stop at that boundary and present the minimal proposed diff.

**No live deployment is authorized by this task.**

---
