# PHASE3_REDESIGN.md

**Version:** v1.2  
**Status:** PROPOSED — revised after actual design review  
**Project:** v685 ML System  
**Repository:** `ai_training_cnn`  
**Target branch:** `v2026c`  
**Reviewed source baseline:** `e13c3e47d083ad64813b17793a440dbdd129dd29`  
**Review date:** 2026-11-13

---

## 0. Document authority and change control

### 0.1 Purpose

This document defines the proposed architecture, engineering boundaries, development sequence, and evaluation framework for the v685 ML system redesign.

It is intended to be the highest-level Phase 3 design reference. Implementation tasks must conform to this document unless a deviation is explicitly discussed and approved.

The redesign follows:

**REPAIR → VERIFY → EVALUATE → SHADOW → CONTROLLED ACTIVATION**

The objective is not to replace existing code indiscriminately. Existing usable components should be repaired and integrated where appropriate. Replacement is justified only where evidence demonstrates that repair is insufficient.

### 0.2 Approval status

This document remains **PROPOSED**.

The actual review verdict was:

**APPROVE WITH SPECIFIC CORRECTIONS**

This means a bounded Phase 3.0 implementation task can be designed after the corrections in this version are incorporated. It does not mean that the complete redesign, its individual decisions, or any live behavior change has been approved.

All decision-register entries D01–D15 are therefore marked `PROPOSED`.

### 0.3 Source baseline and audit reference

The actual review used:

- Repository branch: `v2026c`
- Source commit: `e13c3e47d083ad64813b17793a440dbdd129dd29`
- Redesign document: `docs/phase3_redesign.md`
- Available audit report: `audit_report/audit_report_phase3_report.md`

The audit report contains a commit placeholder. The redesign previously referred to `AUDIT_PHASE3.md`, which did not match the available filename. This version uses the actual available filename and records the reviewed source commit above.

The source commit identifies the review baseline; it does not establish that the uncommitted redesign or audit document was part of that commit.

Before implementation, the task author must record the actual working-tree state and verify the referenced files exist. Do not silently substitute a different audit report or source revision.

### 0.4 Owner approval boundary

The following changes require explicit project-owner approval before implementation or activation:

- Entry decisions or entry authorization.
- Exit decisions or exit behavior.
- Position sizing.
- Stop-loss or take-profit behavior.
- Live order flow or execution authorization.

A design proposal, audit finding, shadow result, passing unit test, or implementation agent recommendation does not constitute this approval.

---

## 1. Current system assessment

### 1.1 Design principle: repair before replacement

The audit identified existing components that should be reused where their contracts are sound:

- Shared runtime `FeatureEngine`.
- Existing time-series splitting utilities.
- Existing UTC-oriented data handling.
- Existing inference and model-wrapper interfaces.

The redesign must not assume that a new module is automatically better than a repaired existing component.

In particular, a proposed `ml/features.py` must remain separate from the runtime `FeatureEngine` until an explicit integration decision is made. The repository review did not find a runtime import of `ml/features.py`.

### 1.2 Main architectural problems

The audit identifies several distinct classes of defects.

**Model and training lifecycle**

- Probability gate can become a no-op.
- Current cross-validation is not a valid synchronized out-of-sample evaluation.
- Scaling occurs before the CV split.
- Six-bar label overlap is not purged or embargoed.
- No untouched final holdout exists in the runtime training path.
- Pooled price-unit features may encode instrument identity.
- Feature calculations can differ depending on optional dependency availability.
- Model artifacts lack a sufficiently strict compatibility and release contract.
- Runtime retraining can overwrite artifacts without a promotion gate.

**Prediction and decision semantics**

- `generate_signal() -> None` conflates multiple failure and abstention reasons.
- Missing predictions can become synthetic or substituted votes.
- Directional probability thresholds create an unintended SELL region.
- MC probability units are not consistently interpreted.
- Strength parsing and scoring contain instrument-format and scale problems.
- Profile conviction thresholds do not necessarily represent comparable calibrated confidence.

**Runtime and operational safety**

- Model initialization failure can interrupt work that should be independent of ML.
- Model initialization and runtime retraining are coupled to the live cycle.
- Artifact write behavior and model-load failure behavior are insufficiently specified.
- Two live hosts need visible, comparable model-release identity.
- Feature and dependency differences between hosts can produce inconsistent inference behavior.

**Separate execution-risk findings**

The audit also identifies execution and position-management concerns. These are not automatically ML redesign tasks. They must be assigned to separate tracks and must not expand Phase 3.0.

### 1.3 Runtime authority

The runtime architecture remains:

**Data Validation → Feature Engine → ML Advisor → Strategy/Decision → Execution Authorization**

Training and model lifecycle are separate from live inference:

**Offline Data → Training/Evaluation → Artifact Validation → Release/Promotion**

A prediction is not an execution authorization.

The ML component may provide a valid assessment, abstain, or be unavailable. It must not independently submit orders.

---

## 2. Target architecture

### 2.1 Runtime responsibilities

| Component | Responsibility | Must not do |
|---|---|---|
| Data Validation | Validate candle availability, completeness, ordering, and time alignment | Invent missing market observations |
| Feature Engine | Produce canonical, deterministic feature values | Silently change calculation backend |
| ML Advisor | Return prediction, abstention, or unavailable status | Authorize an order |
| Strategy/Decision | Combine valid inputs according to an explicit decision contract | Treat missing data as a neutral vote |
| Execution Authorization | Apply the existing approved execution boundary | Accept an unvalidated ML result |
| Training Lifecycle | Train and evaluate offline; create candidate releases | Train or publish artifacts in a live cycle |

### 2.2 Model state is not a prediction

The system must distinguish at least these states:

| State | Meaning | Decision implication |
|---|---|---|
| `READY` | A compatible, validated model is loaded | A prediction may be requested |
| `ABSTAIN` | Model assessment was deliberately withheld or is not valid for this case | No model vote is available |
| `UNAVAILABLE` | A usable model cannot be provided | No model-dependent entry authorization |
| `INCOMPATIBLE` | Artifact does not match the required runtime contract | Do not use the artifact |
| `LOAD_FAILED` | An artifact exists but cannot be loaded or validated | Do not silently substitute another artifact |

`ABSTAIN`, `UNAVAILABLE`, `INCOMPATIBLE`, and `LOAD_FAILED` are not directional predictions and are not neutral votes.

A valid neutral prediction, if the later decision contract supports one, must be represented separately from these states.

### 2.3 Failure isolation

Model initialization is not a prerequisite for independent position management.

If ML initialization fails:

1. Record the failure and its reason.
2. Continue independent existing-position and exit-management paths.
3. Skip model-dependent entry and confluence work where the required assessment is unavailable.
4. Do not manufacture an XGB score, neutral vote, or substitute model result.
5. Do not trigger runtime training or artifact publication as a recovery mechanism.
6. Do not change unrelated exit, sizing, SL/TP, or execution behavior.

The actual call graph must be verified before implementation. It is not sufficient to assume that all later position-management code is independent of ML.

The relevant paths include the applicable Step 5 and owned-position logic, as well as QUICK-FLIP where reachable. Their reachability and dependencies must be established through tests.

### 2.4 Prediction abstention and unavailable state

`generate_signal()` currently returns `None` for multiple unrelated reasons, including prediction errors, low score, and SL/TP validation failures.

The redesign must ultimately replace this ambiguous contract with an explicit typed result. However, the complete prediction-vote redesign belongs to Phase 3.1.

Phase 3.0 has a narrower obligation:

- Establish an explicit model availability boundary.
- Prevent initialization or prediction failure from being interpreted as a valid vote.
- Guard model-dependent confluence and Step 7 operations.
- Ensure unavailable ML cannot authorize a new entry.
- Preserve existing behavior when ML is available, except for the minimum safety protections explicitly required by Phase 3.0.

Do not use a broad exception handler that silently converts every error into a neutral or default score.

### 2.5 Monte Carlo probability adapter

The existing MC cache may contain percentage values.

The new Phase 3 decision path must use a clearly defined probability unit, preferably the normalized range `[0, 1]`, through an explicit adapter.

Do not mutate the shared legacy cache as a shortcut. Existing consumers may include weighted scoring, TP thresholds, and Fibonacci-related logic.

The adapter must be local to the new decision path until all consumers and compatibility requirements have been verified.

### 2.6 ML must not block independent exits

The runtime must preserve the distinction:

- ML assesses whether a new entry is supported.
- Existing position-management logic determines how an existing position is managed under its own approved rules.

A missing or failed ML model must not automatically disable independent position management.

This is a safety requirement, not authorization to redesign exits. Any proposed change to exit behavior remains subject to explicit owner approval.

---

## 3. Model lifecycle and artifact architecture

### 3.1 Offline-only training

Training, retraining, validation, and artifact publication belong to the offline model lifecycle.

The live process must not:

- Train a new model.
- Retrain because an artifact is missing or stale.
- Rewrite model, scaler, feature-list, or configuration artifacts.
- Silently fall back to another model type.
- Silently load a legacy artifact and republish it.
- Promote a candidate artifact.
- Modify an approved artifact in place.

A live process may load and validate an approved artifact. It may record diagnostics and release identity without modifying the artifact.

### 3.2 Phase 3.0 write barrier and failure policy

A write prohibition must have an explicit failure policy.

| Runtime condition | Required behavior |
|---|---|
| Approved compatible artifact exists | Load and validate it; record release identity |
| Artifact missing | Mark ML unavailable; do not train |
| Artifact stale under a legacy age rule | Do not retrain; apply explicit compatibility policy and report status |
| Artifact incompatible | Mark incompatible; do not use or silently replace |
| Artifact load fails | Record `LOAD_FAILED`; do not silently fall back |
| Artifact files are incomplete or mismatched | Reject the release; do not combine files from different releases |
| Artifact write is attempted | Block it and record the attempted path/reason |

The live process must not turn a prohibited write into an unexplained crash, but it must also not pretend that an unavailable model is usable.

### 3.3 Artifact identity

A model release must be identifiable as a coherent unit.

The release manifest should include at least:

- Unique model/release ID.
- Model file hash.
- Scaler file hash.
- Feature contract and ordered feature names/hash.
- Target definition and horizon.
- Timeframe.
- Training universe.
- Training-data period and provenance.
- Training code revision.
- Model type and relevant hyperparameters.
- Random seed where applicable.
- Dependency versions.
- Artifact creation time.
- Git commit and dirty-working-tree state.
- Runtime compatibility requirements.

The model, scaler, feature contract, and configuration must be tied to the same release identity.

A model file without its compatible scaler and feature contract is not a valid release.

### 3.4 Atomic release and promotion

The full release lifecycle belongs primarily to Phase 3.4.

The target design is:

1. Create a candidate release in an isolated location.
2. Validate file presence, hashes, and manifest consistency.
3. Run compatibility checks.
4. Run the required evaluation gates.
5. Promote the complete release atomically.
6. Keep the promoted release immutable.
7. Make rollback a release-selection operation, not an in-place rewrite.

Phase 3.0 must not implement a full promotion framework. It must identify current write paths, prevent live-cycle training/publication, and make current artifact identity or failure visible.

### 3.5 Cross-host identity

The user-provided operational context is that `scheduled_runner_v3.py --live` runs on both the Oracle VM and laptop against one OANDA account. This deployment fact was not independently verified by the reviewed checkout.

Phase 3.0 must therefore make the model identity visible in each host's run records.

At minimum, record:

- Host identifier.
- Profile and resolved artifact path.
- Model/release ID, if loaded.
- Manifest or artifact hash.
- Load status and failure reason.
- Feature-contract identity.
- Relevant dependency/backend identity.

The bounded task must verify whether the two hosts resolve to the same or different artifact locations and whether those locations are shared or independently writable.

Do not assume that matching filenames mean matching model releases.

Do not introduce a new shared-write mechanism or change deployment topology as part of Phase 3.0.

If the two hosts use different release identities, the difference must be visible. Do not silently switch either host to the other's artifact.

---

## 4. Canonical feature contract

### 4.1 One definition for training and inference

Training and inference must use the same feature semantics.

The contract must define:

- Feature names and ordering.
- Data types.
- Units and normalization.
- Required lookback.
- Warm-up behavior.
- Missing-value policy.
- Timeframe.
- Candle-completeness policy.
- Calculation backend and version.
- Compatibility identity.

A feature vector is valid only if it satisfies the artifact's declared contract.

### 4.2 Deterministic indicator calculations

Optional dependency availability must not silently change feature semantics.

The audit identified differences between pandas_ta and fallback calculations, including ATR/RSI behavior and MACD availability.

The redesign must select and validate a canonical calculation implementation. A fallback is acceptable only if its equivalence is demonstrated by tests over representative data and edge cases.

A host missing a required dependency must not silently produce a different feature vector.

### 4.3 Missing values and lookback

Training currently uses a different missing-value path from inference.

The redesign must define a common policy and test it.

The required lookback must be derived from the complete feature dependency graph, including warm-up periods and rolling windows. A fixed bar count must not be assumed sufficient without evidence.

The policy must also cover:

- Partial warm-up windows.
- Terminal rows without a complete future label.
- Incomplete candles.
- Missing or duplicated timestamps.
- Non-finite feature values.

### 4.4 Configuration authority

Runtime configuration must have a clear precedence.

The intended authority remains:

**CLI > run.env > configuration defaults**

Artifact loading must not silently mutate runtime feature configuration.

The model artifact may declare compatibility requirements, but it must not override the operator's runtime configuration without an explicit compatibility check and an approved configuration decision.

---

## 5. Evaluation architecture

### 5.1 Evaluation must demonstrate value, not merely produce a score

A high accuracy figure is not sufficient evidence of predictive value.

The evaluation must answer:

1. Does the model generalize to future timestamps?
2. Does it outperform simple baselines?
3. Is performance consistent across instruments?
4. Are probabilities calibrated?
5. Does performance survive transaction costs?
6. Is the measured edge sufficiently stable to justify a model vote?
7. Does the model add information beyond existing strategy inputs?

No model should be activated merely because training completes successfully.

### 5.2 Synchronized temporal splits

All instruments must be evaluated on a common time basis.

The validation design must not allow one instrument's observation at a timestamp into training while another instrument's observation at the same timestamp is placed in validation.

The evaluation should use chronological folds with synchronized timestamp boundaries.

### 5.3 Purge and embargo

The target uses a six-bar forward horizon in the audited path.

Training labels whose information windows overlap validation periods must be purged. An appropriate embargo must be applied where required by the split design.

The exact boundary rules must be derived from the target construction, not chosen arbitrarily.

Purging and embargo address label-window leakage. They are not substitutes for synchronized instrument splits.

### 5.4 Fold-local preprocessing

All learned preprocessing, including scaler fitting, must occur inside each training fold.

The validation fold must not influence scaler parameters or other learned transformations.

After model selection, the final training process may fit on the approved development data, but the untouched final holdout must remain isolated until the final evaluation.

### 5.5 Baselines

At minimum, compare against:

- Always-up / majority-class baseline.
- Simple non-ML directional baseline.
- Existing strategy decision without the proposed ML contribution.

The baseline must use the same time windows and comparable evaluation conditions.

A model that does not demonstrate value over appropriate baselines must not receive a live decision vote.

### 5.6 Final holdout

The final holdout must be chronologically later than the development and model-selection data.

It must not be used for:

- Feature selection.
- Hyperparameter tuning.
- Threshold selection.
- Repeated model iteration.
- Informal promotion decisions.

If the holdout has been repeatedly inspected and used to make design decisions, it is no longer an untouched holdout.

### 5.7 Per-instrument evaluation

Pooled metrics alone are insufficient.

Report results by instrument and in aggregate. The evaluation must reveal whether a small number of instruments dominate the pooled result or whether performance is materially inconsistent across instruments.

### 5.8 Price-unit feature risk

The audit identified pooled price-unit features such as ATR and MACD as potential instrument-identity proxies.

The evaluation must test whether the model relies on these scale differences.

This is a risk to investigate, not proof that the model has learned instrument identity.

Compare the existing representation with a justified normalized representation. Report the effect on per-instrument performance and generalization.

### 5.9 Probability calibration and decision thresholds

Probability output must be evaluated for calibration, not merely directional accuracy.

Thresholds must be justified using validation data and the intended decision costs.

The LEVEL10 probability gate must not be accepted if its threshold is mathematically or operationally a no-op.

A threshold must have a measurable effect on candidate acceptance and must be tested against relevant baselines.

### 5.10 Transaction costs and uncertainty

Performance must be evaluated after realistic transaction costs.

Any uncertainty interval or resampling method must answer a defined decision question.

A synchronized block bootstrap may be used to estimate uncertainty by resampling contiguous timestamp blocks jointly across instruments. This can preserve cross-instrument dependence and some temporal structure.

It does **not** prevent train/validation label overlap. Purging and embargo address that separate problem.

Do not add bootstrap complexity unless the resulting interval informs a concrete decision, such as whether the model's measured edge exceeds a baseline after costs.

### 5.11 No forced edge

Possible evaluation outcomes:

| Outcome | Required response |
|---|---|
| Clear improvement over baselines and costs | Eligible for later shadow evaluation |
| No demonstrated improvement | Do not activate an ML vote |
| Worse than baseline | Reject or remove the proposed ML contribution |
| Inconclusive evidence | Do not activate; identify the specific missing evidence |
| Material per-instrument instability | Investigate scope and generalization before activation |

A model is allowed to fail evaluation. The process must not manufacture a positive conclusion.

---

## 6. Development roadmap

The roadmap is sequential in terms of dependencies. A later phase must not be treated as authorized merely because an earlier phase is complete.

### Phase 3.0 — Runtime containment and observability

**Objective:** Make the existing live runtime safe when ML is missing, incompatible, or fails to initialize, without redesigning normal trading behavior.

Scope:

1. Establish an explicit ML initialization success/failure boundary around `ensure_model()`.
2. Ensure independent position-management and exit paths remain reachable when ML initialization fails.
3. Guard model-dependent confluence and Step 7 calculations.
4. Ensure unavailable ML cannot authorize a new entry.
5. Identify all runtime training and artifact-write paths.
6. Prohibit live-cycle training and artifact publication.
7. Define missing, stale, incompatible, and failed-load behavior.
8. Record model status and release identity.
9. Make release identity visible in both hosts' run records.
10. Identify profile-specific model paths and shared-path/concurrency risks.
11. Verify that approved artifact bytes remain unchanged.

**Diagnostics:** Always on, limited to status, failure reason, release identity, and relevant execution-path evidence. Diagnostics must not alter decisions.

**Failure isolation:** Unconditional safety behavior, not an optional feature flag.

**Artifact write protection:** Unconditional for the live cycle.

**Explicit exclusions:**

- No new prediction-vote contract activation.
- No full scoring redesign.
- No threshold tuning.
- No model retraining or promotion.
- No change to entry scoring when ML is healthy.
- No change to position sizing, SL/TP, QUICK-FLIP, exits, or order flow.
- No D1 investigation or execution-risk refactor.
- No unrelated cleanup.

#### Phase 3.0 acceptance criteria

The implementation task must provide tests demonstrating:

1. With `ensure_model()` forced to raise, `main()` records an explicit ML-unavailable state.
2. The run proceeds to the independently reachable position-management and exit paths.
3. Existing positions remain eligible for the applicable Step 5 and owned-position logic.
4. QUICK-FLIP reachability is preserved wherever it is independent of ML.
5. No new-entry candidate or order is authorized when its required ML assessment is unavailable.
6. A model initialization failure does not trigger fallback training or artifact publication.
7. A prediction failure in multi-timeframe confluence is recorded as unavailable.
8. An unavailable prediction cannot become a fabricated XGB vote or substituted score.
9. All runtime model/scaler/config/feature artifact write paths are enumerated and blocked.
10. Existing approved artifact bytes remain unchanged.
11. Missing, incompatible, stale, and failed-load cases produce explicit status and reason.
12. Each host's run record identifies the loaded release or explicit failure.
13. Differing release identities across hosts are visible.
14. Diagnostics do not alter existing live decisions or execution behavior when the model is healthy.
15. The tests verify the actual call paths rather than assuming that later code is independent.

A passing compilation or a mocked unit test alone is not sufficient. The task must include focused integration tests for the actual runtime control flow.

### Phase 3.1 — Decision contract and early shadow

**Objective:** Define explicit prediction and abstention semantics and reconstruct the decision contribution of ML.

Scope:

- Replace ambiguous `None` semantics with an explicit typed prediction result.
- Distinguish valid directional prediction, valid neutral assessment if supported, abstention, and unavailability.
- Prohibit synthetic votes and implicit score substitution.
- Define directional probability semantics and a neutral band.
- Correct probability-unit handling through the explicit MC adapter.
- Correct strength parsing and scoring scale.
- Reconstruct score contributions and profile threshold meaning.
- Establish a decision record with reason codes.
- Add an early shadow path using the existing model only if it can be safely loaded.
- Keep shadow decisions separate from live authorization.

The early shadow path must not submit orders or change production entry/exit decisions.

### Phase 3.2 — Canonical feature contract

**Objective:** Make feature generation deterministic and consistent between training and inference.

Scope:

- Canonical feature definitions and ordering.
- Canonical indicator calculation backend.
- Missing-value and warm-up policy.
- Lookback and bar-guard requirements.
- Candle completeness and timestamp policy.
- Timeframe compatibility.
- Configuration precedence.
- Cross-host feature parity.
- Compatibility tests for old and new artifacts.

Do not integrate `ml/features.py` into the runtime `FeatureEngine` without an explicit design decision.

### Phase 3.3 — Evaluation redesign

**Objective:** Establish credible evidence of out-of-sample predictive value.

Scope:

- Synchronized cross-instrument chronological splits.
- Purge and embargo based on label horizon.
- Fold-local scaling and preprocessing.
- Untouched final holdout.
- Baseline comparisons.
- Per-instrument performance.
- Price-unit feature investigation.
- Probability calibration.
- Transaction-cost-aware results.
- Uncertainty estimates where they inform a concrete decision.
- Explicit accept/reject/inconclusive criteria.

### Phase 3.4 — Artifact lifecycle

**Objective:** Establish reproducible, immutable, verifiable model releases.

Scope:

- Complete manifest.
- Model/scaler/feature-contract pairing.
- Hash validation.
- Dependency and training provenance.
- Candidate artifact validation.
- Atomic release publication.
- Explicit promotion and rollback.
- Legacy artifact retirement.
- Cross-host release verification.

No live runtime training is introduced.

### Phase 3.5 — Integrated shadow

**Objective:** Evaluate the complete repaired feature and decision path without live execution effects.

Requirements:

- Feature contract and model release must be compatible.
- The integrated shadow must record inputs, prediction state, score contribution, abstention reason, and proposed decision.
- Shadow outputs must be comparable with existing live decisions.
- No shadow output may submit or modify an order.
- Shadow/live differences must be explainable and attributable.

### Phase 3.6 — Controlled activation

**Objective:** Consider a narrowly scoped activation only after evidence and owner approval.

Preconditions:

- Phase 3.0–3.5 acceptance criteria complete.
- Approved artifact release identified and immutable.
- Evaluation demonstrates value over baselines and transaction costs.
- Per-instrument behavior is understood.
- Probability calibration and threshold behavior are justified.
- Cross-host release identity is verified.
- Rollback procedure is tested.
- Explicit project-owner approval is recorded for the exact behavior being activated.

Activation must be controlled, reversible, and separately authorized. Completion of the roadmap does not itself authorize live activation.

---

## 7. Phase 3.0 implementation contract

This section is normative for the next implementation-task design.

### 7.1 In-scope source areas

The implementation task must inspect and, only where necessary, modify:

- `fx_trade_bot.py::main()`
- `fx_trade_bot.py` multi-timeframe confluence path
- `fx_trade_bot.py` Step 5 and Step 7 boundaries
- `fx_trade_bot_ml.py::ensure_model()`
- `data_pipeline.py::ModelWrapper.fit()`
- `data_pipeline.py::ModelWrapper.save()`
- `data_pipeline.py::ModelWrapper.load()`
- Profile/model path resolution
- All model/scaler/config/feature artifact write call sites

The exact source call graph and all relevant paths must be verified at the implementation commit. The above list is a scope guide, not proof that it exhaustively names every call site.

### 7.2 State handling

At minimum, the runtime needs an explicit state that distinguishes:

- Initialization succeeded.
- Initialization failed.
- Artifact missing.
- Artifact incompatible.
- Artifact load failed.

The implementation may use an enum, structured result, or equivalent explicit representation. It must not rely on `None` alone to encode several unrelated conditions.

The exact type and field names are implementation details, provided the semantics are explicit and tested.

### 7.3 No silent recovery

The following are prohibited:

- Training because a model is missing.
- Training because a model is stale.
- Falling back to a different model type without an approved compatibility policy.
- Treating a failed prediction as a neutral vote.
- Reusing a previous prediction without an explicit freshness contract.
- Combining model, scaler, or feature files from different releases.
- Silently changing artifact paths to find a different model.

### 7.4 Normal healthy-path preservation

When the existing approved model loads and operates successfully:

- Existing entry scoring remains unchanged.
- Existing thresholds remain unchanged.
- Existing order flow remains unchanged.
- Existing sizing remains unchanged.
- Existing SL/TP remains unchanged.
- Existing position-management and exit rules remain unchanged.

Any unavoidable difference must be documented, explained, and separately approved if it crosses the owner-approval boundary.

### 7.5 Feature flags and defaults

| Change | Flag required? | Default | Live effect |
|---|---|---|---|
| Diagnostic instrumentation | No | On | Records status and identity only |
| Failure isolation | No | Always on | Prevents ML failure from blocking independent management; unavailable ML cannot authorize entries |
| Artifact write protection | No | Always on | Live process cannot train or publish artifacts |
| New decision shadow | Yes | Off | No production effect until separately enabled |
| Controlled ML activation | Yes, plus owner approval | Off | No effect until explicitly authorized |

Failure isolation and artifact write protection are unconditional protections. They must not be made optional merely to preserve an unsafe fallback path.

### 7.6 Phase 3.0 completion evidence

The implementation report must contain:

- Exact commit and working-tree state.
- Files and functions changed.
- Complete inventory of runtime model write paths.
- Complete inventory of model path resolution by profile.
- Test names, commands, and results.
- Failure-injection evidence.
- Position/exit path reachability evidence.
- Healthy-path equivalence evidence.
- Artifact hashes before and after.
- Host identity fields and sample run records.
- Explicit statement that no live order behavior was changed.
- Explicit statement of any unverified deployment assumption.

No claim of completion may rely only on compilation or successful model loading.

---

## 8. Audit traceability

The following table assigns each audited finding to an owning phase or separate track. `YES`, `PARTIAL`, `NO`, `WITHDRAWN`, and `MOOT` describe design coverage, not proof that implementation has been completed.

| Finding | Owning phase / track | Design coverage | Notes |
|---|---|---|---|
| F1 | 3.1 | PARTIAL | Probability-gate calibration and meaningful threshold behavior remain to be demonstrated |
| F2 | 3.3 | YES | Synchronized chronological folds, purge/embargo, fold-local scaling, and final holdout |
| F3 | 3.3 | YES | Price-unit feature risk and normalized-feature evaluation |
| F4 | 3.2 | YES | Canonical calculation backend and deterministic feature generation |
| F5 | 3.2 | YES | Timeframe compatibility in the feature contract |
| F6 | 3.2 | YES | Configuration precedence; artifact must not silently mutate runtime configuration |
| F7 | 3.4 | YES | Manifest, hashes, immutable releases, and atomic promotion |
| F8 | 3.4 | YES | Legacy fallback retirement and runtime training prohibition |
| F9 | — | WITHDRAWN | Supplied audit withdrew this finding because the relevant model exit method is not called by this bot |
| F10 | 3.3 | PARTIAL | Dataset and label redesign; explicitly test terminal-label construction |
| F11 | 3.2 / 3.3 | PARTIAL | Warm-up and missing-value policy; add explicit acceptance conditions |
| F12 | 3.2 | PARTIAL | Required lookback and bar-guard parity need direct tests |
| F13 | — | MOOT | Supplied audit marks the unreachable data path moot |
| N1 | 3.1 | YES | Explicit prediction/abstention contract; no synthetic vote |
| N2 | 3.1 | YES | Directional voting and neutral-band semantics |
| N3 | 3.0 / 3.4 | PARTIAL | Phase 3.0 blocks live writes; Phase 3.4 establishes full release lifecycle |
| N4 | — | MOOT | No N4 entry exists in the supplied audit; this is an absent identifier, not a verified closed finding |
| N5 | 3.2 | YES | Shared train/inference missing-value policy |
| N6 | 3.2 | YES | Lookback parity experiment |
| N7 | 3.2 | YES | Candle completeness policy |
| N8 | 3.2 | YES | Configuration authority and precedence |
| N9 | 3.1 | YES | Strength parsing and scale |
| N10 | 3.1 | YES | MC probability-unit standardization |
| N11 | 3.1 | PARTIAL | Score reconstruction; profile threshold meaning and calibration remain open |
| N12 | 3.2 | YES | Backend determinism and cross-host feature consistency |

### 8.1 Separate execution and operational tracks

These findings must not be silently absorbed into the ML implementation sequence.

| Finding | Owner track | Phase 3 relationship |
|---|---|---|
| D1 | Separate owner-approved execution track | TP behavior in `_revise_owned_position()`; removed from Phase 3.0 |
| D2 | Separate execution-risk track | Outside ML redesign |
| D3 | Separate execution-risk track | Outside ML redesign |
| D4 | Separate operations/configuration track | Outside ML redesign |
| D5 | Separate execution-risk track | Outside ML redesign |
| D6 | Documentation/configuration maintenance | Outside ML redesign |
| D7 | Separate execution-risk track | Outside ML redesign |
| D8 | Bounded runtime verification, if retained | May be separately scheduled; not a Phase 3.0 implementation dependency |
| D9 | Bounded data/config verification, if retained | May be separately scheduled; not a Phase 3.0 implementation dependency |

D1 is explicitly excluded from Phase 3.0. No TP behavior investigation or change is authorized by this redesign review.

D2–D7 require separate ownership and scope. D8/D9 may be verified through bounded operational reviews if they remain relevant.

---

## 9. Open decisions

All entries below remain open unless separately approved.

| ID | Open question | Owning phase |
|---|---|---|
| O01 | What is the final typed prediction-result contract and its reason codes? | 3.1 |
| O02 | What directional probability thresholds and neutral-band semantics are justified? | 3.1 |
| O03 | What is the final strength-score parsing and scale contract? | 3.1 |
| O04 | How should profile conviction thresholds be interpreted and calibrated? | 3.1 |
| O05 | What exact canonical feature backend and dependency versions are required? | 3.2 |
| O06 | What is the final missing-value, warm-up, and required-lookback policy? | 3.2 |
| O07 | What synchronized temporal split and embargo boundaries follow from the actual target construction? | 3.3 |
| O08 | What evidence and uncertainty criteria are sufficient to establish value after costs? | 3.3 |
| O09 | What is the final immutable artifact manifest, release, and rollback contract? | 3.4 |
| O10 | How are runtime abstention, runtime unavailability, and lack of demonstrated predictive value kept distinct in the decision process? | 3.1 |

O10 is defined here explicitly. It is not permission to treat abstention as neutral or to automatically renormalize remaining votes.

---

## 10. Acceptance test catalogue

The following catalogue defines the test intent. The implementation task must map these requirements to concrete test files and test commands. Test IDs are stable references; they do not imply that tests already exist or pass.

### 10.1 Runtime and failure containment

| ID | Test | Expected result |
|---|---|---|
| T1 | Normal model initialization | Compatible approved artifact loads and reports `READY` |
| T2 | Missing model artifact | Explicit unavailable status; no training |
| T3 | Model load exception | Explicit `LOAD_FAILED`; no silent fallback |
| T4 | Incompatible artifact | Rejected with compatibility reason |
| T5 | Stale artifact | No runtime retraining; explicit policy outcome |
| T6 | `ensure_model()` forced to raise | Main cycle records failure and continues independent management |
| T7 | Position-management reachability | Applicable Step 5 and owned-position paths remain reachable |
| T8 | QUICK-FLIP reachability | Existing independent path remains reachable where applicable |
| T9 | ML unavailable during entry evaluation | No new-entry authorization requiring ML |
| T10 | Confluence prediction failure | Explicit unavailable/abstain status; no fabricated vote |
| T11 | Healthy-path equivalence | Existing entry and execution behavior unchanged when model is healthy |
| T12 | Exception isolation | Failure in one model-dependent operation does not silently corrupt unrelated runtime state |

### 10.2 Artifact and host integrity

| ID | Test | Expected result |
|---|---|---|
| T13 | Runtime write-path inventory | Every model/scaler/config/feature write path is identified |
| T14 | Live write barrier | Training and artifact publication are blocked |
| T15 | Artifact immutability | Approved artifact hashes remain unchanged |
| T16 | Release pairing | Model, scaler, feature contract, and config resolve to one release |
| T17 | Host identity | Each host records release identity or explicit failure |
| T18 | Cross-host comparison | Different release identities and paths are visible |
| T19 | No implicit fallback | Missing or failed artifact does not select another model silently |

### 10.3 Feature and evaluation correctness

| ID | Test | Expected result |
|---|---|---|
| T20 | Feature determinism | Equivalent inputs produce equivalent feature values on supported hosts |
| T21 | Training/inference parity | Same feature definitions, ordering, and missing-value policy |
| T22 | Feature-contract compatibility | Incompatible timeframe, feature set, or lookback is rejected |

### 10.4 Explicit additions from the review

| ID | Test | Expected result |
|---|---|---|
| T23 | MC adapter isolation | New decision path receives normalized probability while legacy shared cache values and consumers remain unchanged |
| T24 | Terminal-label and split integrity | Terminal labels, synchronized folds, purge/embargo, and fold-local preprocessing are tested in the evaluation phase |
| T25 | ML failure versus independent management | Injected initialization and prediction failures cannot prevent independently reachable existing-position management; no new entry is authorized on unavailable ML |

T23 and T25 are explicitly defined here to remove the previous dangling references. T24 provides a stable identifier for the label/split integrity requirement. Their implementation ownership remains with the phases shown above.

---

## 11. Decision register

D01–D15 are retained as proposed design decisions. None is marked `ACCEPTED` in this version because the supplied review did not provide project-owner approval evidence.

| Decision ID | Status | Authority |
|---|---|---|
| D01 | PROPOSED | Requires explicit project-owner approval |
| D02 | PROPOSED | Requires explicit project-owner approval |
| D03 | PROPOSED | Requires explicit project-owner approval |
| D04 | PROPOSED | Requires explicit project-owner approval |
| D05 | PROPOSED | Requires explicit project-owner approval |
| D06 | PROPOSED | Requires explicit project-owner approval |
| D07 | PROPOSED | Requires explicit project-owner approval |
| D08 | PROPOSED | Requires explicit project-owner approval |
| D09 | PROPOSED | Requires explicit project-owner approval |
| D10 | PROPOSED | Requires explicit project-owner approval |
| D11 | PROPOSED | Requires explicit project-owner approval |
| D12 | PROPOSED | Requires explicit project-owner approval |
| D13 | PROPOSED | Requires explicit project-owner approval |
| D14 | PROPOSED | Requires explicit project-owner approval |
| D15 | PROPOSED | Requires explicit project-owner approval |

The substantive proposals remain subject to the architecture sections and their owning phases. A status label is not implementation authorization.

If a decision is later approved, record:

- Exact decision ID.
- Approved wording and scope.
- Approval date.
- Project-owner approval evidence.
- Affected phase and implementation task.
- Whether the decision changes live behavior.

Do not change a decision's status merely because an implementation agent recommends it.

---

## 12. Phase gates and authorization

| Gate | Required evidence | What it permits |
|---|---|---|
| G0 — Design correction | v1.2 corrections incorporated and scope agreed | Phase 3.0 task design |
| G1 — Phase 3.0 implementation | Bounded task, tests, artifact integrity, runtime failure isolation | Runtime containment and diagnostics only |
| G2 — Phase 3.1 | Explicit prediction contract and shadow-only tests | Decision-contract development and shadow evaluation |
| G3 — Phase 3.2 | Canonical feature contract and parity tests | Feature-contract integration |
| G4 — Phase 3.3 | Valid OOS evaluation and baselines | Evidence-based model assessment |
| G5 — Phase 3.4 | Validated immutable release lifecycle | Candidate release and promotion workflow |
| G6 — Phase 3.5 | Integrated shadow evidence | Complete shadow evaluation |
| G7 — Phase 3.6 | All gates satisfied and explicit owner approval | Only the specifically approved controlled activation |

Passing one gate does not automatically authorize the next.

---

## 13. Explicit non-goals and prohibitions

The Phase 3 redesign must not become an excuse for unrelated changes.

Unless separately discussed and approved, the following are outside scope:

- Rewriting the entire bot architecture.
- Replacing the existing runtime `FeatureEngine` merely to create a new module.
- Changing OANDA execution behavior.
- Changing position sizing.
- Changing SL/TP or existing exit behavior.
- Changing QUICK-FLIP behavior.
- Introducing runtime retraining.
- Introducing silent model fallback.
- Combining artifacts from different releases.
- Activating a new ML decision path in production before its gate.
- Moving D1 or other execution-risk changes into Phase 3.0.
- Treating a shadow result as permission to trade.
- Treating logging as a substitute for a defined diagnostic and follow-up action.

Observation must be purposeful: every diagnostic should identify what is being measured, what failure or uncertainty it addresses, and which later decision it informs.

---

## 14. Immediate next step

The next deliverable is:

**PHASE3_0_IMPLEMENTATION_TASK.md — Strict Spec**

It must be a finite implementation task, not another broad audit.

It must contain:

1. Exact source files and function boundaries.
2. Verified call graph around `ensure_model()` and position management.
3. Explicit ML runtime states and transition rules.
4. All model-dependent branches before and after initialization.
5. All artifact write and model path resolution sites.
6. Required host-visible release identity.
7. Failure-injection test scenarios.
8. Healthy-path equivalence tests.
9. Artifact immutability checks.
10. Explicit exclusions and no-change requirements.
11. Acceptance criteria and exact test commands.
12. A completion report format with evidence.

The implementation task may verify source details needed to execute this bounded scope. It must not restart a repository-wide audit or expand into unrelated refactoring.

**No code changes are authorized by this document. No live behavior change is authorized by this document.**

---

## 15. Version history

| Version | Change |
|---|---|
| v1.0 | Initial Phase 3 redesign architecture and roadmap |
| v1.1 | Incorporated prior design refinements: explicit abstention, shadow path, feature/model compatibility, evaluation controls, artifact provenance, and acceptance framework |
| v1.2 | Incorporated actual Claude review: Phase 3.0 runtime failure isolation, independent position-management continuity, no-write/load-failure policy, cross-host release identity, D1 removal, decision-status correction, audit reference reconciliation, finding ownership, and test-ID reconciliation |

**End of document.**
