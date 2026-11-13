# PHASE3_REDESIGN.md — v685 ML System Redesign

| Field | Value |
|---|---|
| Repository | `ai_training_cnn` |
| Branch | `v2026c` |
| Design date | 2026-11-13 |
| Source assessment | `AUDIT_PHASE3.md` |
| Design status | Proposed — architecture baseline |
| Implementation mode | Staged, evidence-driven |
| Live behavior changes | Disabled by default |
| Primary objective | Repair and establish a verifiable ML decision and model lifecycle |

---

# 0. Document Authority and Purpose

## 0.1 Purpose

This document defines the target architecture and implementation plan for the v685 ML system.

It translates the findings in `AUDIT_PHASE3.md` into engineering decisions, component contracts, implementation dependencies, and measurable acceptance criteria.

This is a redesign of the existing system, not a wholesale replacement.

The existing shared `FeatureEngine`, XGBoost model family, feature matrix contract, OANDA data integration, and prediction interface are retained unless subsequent evidence demonstrates that replacement is necessary.

The objective is to establish a system in which:

1. Model predictions are genuine, independently observable outputs.
2. Strategy eligibility does not determine whether ML predictions are calculated.
3. Decision scoring uses consistent units and mathematically valid comparisons.
4. Training and evaluation represent genuine out-of-sample conditions.
5. Training artifacts are reproducible, identifiable, and protected from accidental replacement.
6. Runtime feature generation is consistent with training.
7. Changes can be evaluated in shadow mode before affecting live decisions.
8. Every observation has a defined diagnostic and improvement path.

## 0.2 Relationship with Other Documents

| Document | Responsibility |
|---|---|
| `docs/Development_plan.md` | Highest-level development lifecycle, principles, and architecture authority |
| `AUDIT_PHASE3.md` | Evidence, findings, severity, and outstanding forensic questions |
| `PHASE3_REDESIGN.md` | Phase 3 target architecture, technical decisions, dependencies, and acceptance criteria |
| Implementation task specifications | Exact scope and instructions for individual code changes |
| Test and evaluation reports | Evidence that implementation meets this design |

This document must remain consistent with `docs/Development_plan.md`.

If a proposed change conflicts with the higher-level development plan, implementation must stop until the discrepancy is discussed and resolved.

## 0.3 Authority and Change Control

The following rules apply:

- This document is the Phase 3 implementation reference.
- Implementation agents must not independently redefine architecture.
- A discovered defect does not automatically authorize unrelated refactoring.
- Any proposed deviation must identify the affected design decision, reason, evidence, and consequences.
- Behavior-changing modifications require explicit approval.
- Existing trading behavior must not be silently changed during cleanup.
- No implementation agent may interpret a successful code change as proof of model or trading performance.

## 0.4 Evidence Classification

All implementation reports must distinguish:

- **CONFIRMED**: Directly demonstrated by code, tests, or runtime evidence.
- **MEASURED**: Quantified using actual data or controlled experiments.
- **HYPOTHESIS**: Plausible but not yet established.
- **UNRESOLVED**: Insufficient evidence to make a decision.
- **ACCEPTED**: A technical decision explicitly approved in this design or subsequent change control.

Do not promote hypotheses into facts.

---

# 1. Executive Architecture Decisions

## 1.1 Overall Decision

**REPAIR the existing architecture. Do not replace it wholesale.**

| Component | Decision | Reason |
|---|---|---|
| XGBoost model family | RETAIN | Existing model infrastructure is usable |
| Shared FeatureEngine | RETAIN / REPAIR | Training and inference already share the main implementation |
| Feature matrix contract | RETAIN / STRENGTHEN | Existing strict validation is a useful foundation |
| OANDA data integration | RETAIN / VERIFY | Existing integration should be preserved |
| Decision-layer ML vote | REPAIR | Current abstention handling can fabricate votes |
| Strategy scoring | REPAIR | Strength and MC units are incorrect |
| Cross-validation | REPLACE methodology | Existing split is not genuine chronological out-of-sample validation |
| Feature scaling | INVESTIGATE / REPAIR | Price-unit features may introduce instrument identity shortcuts |
| Artifact management | REPLACE lifecycle | Missing provenance and integrity controls |
| Live auto-retraining | RETIRE | Training must not occur inside the live trading cycle |
| Shadow validation | IMPLEMENT | No reliable new-versus-old comparison currently exists |
| Legacy pickle fallback | RETIRE | Silent model-family substitution is unacceptable |

## 1.2 Core Architectural Principles

The redesigned system follows these rules:

1. Prediction is independent of trade eligibility.
2. A missing prediction is not a neutral prediction.
3. An abstention is a first-class, explicit state.
4. Model quality and trading-system quality are separate evaluation domains.
5. Training data and model artifacts must be reproducible.
6. Feature definitions must be deterministic across hosts.
7. No live model replacement without explicit promotion.
8. No behavior-changing feature is enabled by default.
9. Every shadow observation must be attributable to a specific model, strategy version, and data timestamp.
10. Runtime failures must be visible and classified, not silently converted into plausible-looking values.

---

# 2. Target Architecture

## 2.1 Logical Architecture

The redesigned system has six logical layers.

```text
                 MARKET DATA
                      |
                      v
           DATA VALIDATION LAYER
                      |
                      v
             FEATURE ENGINE
                      |
              Feature Contract
                      |
          +-----------+-----------+
          |                       |
          v                       v
     ML ADVISOR             STRATEGY ENGINE
          |                       |
     ML Prediction          Strategy Eligibility
     P(UP), P(DOWN)          Risk / Filters
     Confidence              Score Breakdown
     Model Identity          Rejection Reasons
          |                       |
          +-----------+-----------+
                      |
                      v
               DECISION LAYER
                      |
             Consensus / Abstain
                      |
                      v
             EXECUTION GATE
                      |
               Existing Order
                 Execution
```

Training and model lifecycle are independent:

```text
 HISTORICAL DATA
       |
       v
 IMMUTABLE DATA SNAPSHOT
       |
       v
 FEATURE GENERATION
       |
       v
 WALK-FORWARD EVALUATION
       |
       v
 MODEL TRAINING
       |
       v
 VALIDATION REPORT
       |
       v
 ARTIFACT MANIFEST
       |
       v
 EXPLICIT PROMOTION
       |
       v
 IMMUTABLE MODEL RELEASE
       |
       v
 RUNTIME MODEL LOADING
```

The runtime system must never silently invoke the training pipeline.

## 2.2 Responsibility Boundaries

| Component | Owns | Must NOT own |
|---|---|---|
| Data validation | Candle validity and completeness | Trade direction |
| FeatureEngine | Deterministic feature generation | Entry permission |
| ML Advisor | Model prediction and prediction status | SL/TP decisions |
| Strategy Engine | Strategy eligibility and score | Fabricated ML predictions |
| Decision Layer | Combining valid decision inputs | Model training |
| Execution Gate | Permission to submit an order | Model evaluation |
| Training Pipeline | Data preparation and model training | Live order execution |
| Artifact Manager | Model identity, integrity, and promotion | Strategy decisions |
| Evaluation System | Statistical and economic assessment | Automatic live promotion |

---

# 3. Decision 1 — ML Advisor Independence

**Priority: P0**

## 3.1 Decision

The ML Advisor must be independent of `generate_signal()` success or failure.

The current architecture incorrectly couples prediction availability to strategy-engine output.

This dependency must be removed.

The ML prediction path must not depend on:

- Strategy score passing a minimum threshold.
- SL/TP construction succeeding.
- Risk/reward filtering.
- Strategy direction being available.
- Entry eligibility.
- Other unrelated strategy filters.

The Advisor may depend on validated market data and valid features.

## 3.2 Prediction Contract

The Advisor must return a structured result rather than an ambiguous signal or `None`.

Target conceptual contract:

```python
@dataclass
class MLPrediction:
    status: str

    p_up: float | None
    p_down: float | None

    predicted_direction: str | None
    confidence: float | None

    model_id: str | None
    model_version: str | None

    instrument: str
    timeframe: str
    candle_timestamp: str | None

    abstain_reason: str | None
```

The exact implementation must follow existing project conventions.

Allowed statuses:

| Status | Meaning |
|---|---|
| `VALID` | A valid prediction was generated |
| `ABSTAIN` | Prediction could not be produced reliably |
| `UNAVAILABLE` | No compatible model is available |
| `INVALID_INPUT` | Input data or feature contract is invalid |

A valid prediction must satisfy:

\[
0 \leq P(UP) \leq 1
\]

\[
0 \leq P(DOWN) \leq 1
\]

If the model represents a binary complementary classification:

\[
P(DOWN)=1-P(UP)
\]

This relationship must be verified against the actual classifier output rather than assumed for arbitrary future model types.

## 3.3 Abstention Reasons

At minimum, support the following diagnostic categories:

- `insufficient_bars`
- `incomplete_candle`
- `missing_feature`
- `nan_feature`
- `invalid_feature_shape`
- `model_missing`
- `artifact_mismatch`
- `prediction_exception`
- `invalid_probability`
- `model_incompatible`

Additional reasons may be added without changing the meaning of existing categories.

A failure must never be silently converted into:

- Neutral vote.
- BUY vote.
- SELL vote.
- Default probability.
- Synthetic XGB score.

## 3.4 Directional Voting

The Advisor returns probabilities.

The Decision Layer determines whether those probabilities qualify for directional voting.

Three possible states are required:

```text
BUY
NEUTRAL
SELL
```

A configurable neutral band must separate BUY and SELL decisions.

Conceptually:

\[
Vote =
\begin{cases}
BUY & P(UP) \geq T_{buy}\\
SELL & P(UP) \leq T_{sell}\\
NEUTRAL & \text{otherwise}
\end{cases}
\]

With:

\[
T_{sell} < T_{buy}
\]

The actual thresholds must be determined through evaluation and explicitly approved.

The existing 0.55 threshold must not automatically be accepted as statistically optimal.

The same probability interpretation and units must be used by ML and MC consumers.

## 3.5 Acceptance Criteria

- ML prediction is produced even when `generate_signal()` rejects entry.
- Strategy rejection does not suppress valid ML predictions.
- Invalid features produce an explicit abstention.
- Exceptions produce an explicit abstention.
- No abstention produces a synthetic vote.
- Every prediction is associated with an instrument, timeframe, timestamp, and model identity.
- Unit tests cover every defined status and abstention reason.

---

# 4. Decision 2 — Strategy Engine Scoring Redesign

**Priority: P0**

## 4.1 Decision

The existing score must not be adjusted through isolated threshold changes.

First establish the mathematical meaning of each score component.

The scoring system must be reconstructed using explicit units, directionality, bounds, and interpretation.

The following findings must be addressed:

- N9: Strength Gap parsing and scale.
- N10: MC percentage-versus-fraction mismatch.
- N11: Engine score versus profile conviction thresholds.
- N2: Directional voting asymmetry.

## 4.2 Strength Score Contract

Instrument parsing must use an explicit currency-pair parser.

For OANDA-style instruments:

```python
base_currency, quote_currency = instrument.split("_")
```

Validation must confirm both currencies exist in the strength matrix.

Missing currencies must produce an explicit unavailable state, not a fabricated score of 50.

The strength-gap calculation must use the actual measured scale.

The current threshold of 10 is not justified when observed scores are approximately +/-2.

The new strength calculation must define:

- Input units.
- Output units.
- Directional interpretation.
- Missing-data behavior.
- Normalization method.
- Threshold calibration method.

No arbitrary threshold adjustment is permitted.

## 4.3 MC Probability Contract

All MC probabilities must use one canonical representation.

Internal representation:

```text
0.0 to 1.0
```

Conversion to percentage is permitted only at presentation boundaries.

The following must never coexist in the same calculation:

```text
0.55
55.0
```

A single probability validator must enforce the contract.

MC score contribution must not automatically saturate at its maximum for ordinary probability values.

## 4.4 Directional Symmetry

For identical market conditions, the score calculation must not inherently favor LONG or SHORT.

The scoring function must distinguish:

- Directional market evidence.
- Directional model evidence.
- Directional MC evidence.
- Strategy-specific eligibility.
- Risk-related rejection.

For a symmetric test input, the directional scoring logic must satisfy an explicitly documented symmetry property.

The acceptance test must state the permitted numerical tolerance and explain any intentional directional asymmetry.

A mathematically symmetric score does not mean that actual market BUY and SELL distributions must be symmetric.

## 4.5 Profile Thresholds

Existing profile thresholds:

- P1: 50
- P2: 45
- P3: 55
- P4: 42

must not be assumed compatible with a redesigned score.

A score of 50 has no intrinsic meaning unless its construction and calibration are established.

New thresholds must be evaluated against:

- Score distribution.
- Directional distribution.
- Entry frequency.
- Rejection frequency.
- Out-of-sample performance.
- Transaction costs.

No threshold should be changed merely to restore the previous trade frequency.

## 4.6 Acceptance Criteria

- Instrument parsing passes all supported currency-pair cases.
- Missing strength inputs are explicitly classified.
- MC probability values use one canonical scale.
- LONG/SHORT mathematical symmetry tests pass.
- Every score has a component-level breakdown.
- Thresholds are traceable to an approved calibration report.
- Existing live scoring remains unchanged until the replacement is explicitly enabled.

---

# 5. Decision 3 — Feature and Runtime Consistency

**Priority: P1**

## 5.1 Decision

Retain the shared `FeatureEngine`.

Do not replace it with separate training and inference feature implementations.

The objective is to establish a deterministic feature contract.

## 5.2 Feature Contract

Every model artifact must define:

- Feature names.
- Feature order.
- Data types.
- Expected shape.
- Feature calculation version.
- Indicator periods.
- Required lookback.
- Missing-value policy.
- Timeframe.
- Candle completeness policy.
- Feature backend identity.

The model must reject incompatible feature inputs.

Feature count alone is insufficient.

The feature names and order must match exactly.

## 5.3 Backend Determinism

`pandas_ta` availability must not silently change model inputs.

The current ATR and RSI implementation differences are unacceptable for reproducible model operation.

Target decision:

1. Establish the intended ATR and RSI formulas.
2. Implement or select one canonical calculation path.
3. Remove runtime dependence on optional backend availability.
4. Verify results against controlled reference datasets.
5. Record the implementation version in the artifact manifest.

The same principle applies to MACD and all other indicators.

Do not introduce silent fallback calculations.

If a required feature cannot be calculated, prediction must abstain.

## 5.4 Lookback Parity

Training currently uses 5000 bars while inference uses approximately 200.

These windows must be investigated before being standardized.

A fixed number of bars is not automatically the correct solution.

The desired behavior is:

- Equivalent feature values for identical historical input.
- Sufficient warm-up for recursive indicators.
- No dependence on arbitrary truncation.
- Consistent treatment of missing data.
- Explicit handling of incomplete candles.

A controlled parity experiment must compare 5000-bar and 200-bar windows over at least 500 end-bar observations.

For every feature, report:

- Maximum absolute difference.
- Mean absolute difference.
- Standard deviation of differences.
- Difference normalized by feature standard deviation.
- Whether the difference changes the resulting prediction.

Non-recursive features should satisfy strict deterministic parity.

Recursive indicators must have measured tolerances based on empirical convergence.

The final inference window must be large enough to meet the approved tolerance.

## 5.5 Missing-Value Policy

Training and inference must share the same missing-value policy.

The current difference between training `dropna()` and inference `ffill/bfill/fillna(0)` must be removed.

The target policy is:

- Do not use future values to repair historical feature rows.
- Do not silently replace unavailable indicators with zero.
- Do not allow training to use rows that inference would reject.
- Preserve missing-value provenance during dataset construction.
- Reject invalid final prediction rows.

Historical warm-up rows may be excluded through an explicit, documented rule.

## 5.6 Candle Completeness

Use OANDA's candle `complete` flag where available.

The clock-based 30-second tolerance must not be the sole source of completeness information.

The same candle eligibility rule must apply during training and inference.

## 5.7 Timeframe Contract

A model must only load when its declared timeframe matches the requested timeframe.

Features with M15-specific assumptions must not be silently reused for H1 or H4.

`MULTI_TF_CONFLUENCE` must not pass different timeframe data to the same model unless the model explicitly declares support for those inputs.

Unsupported combinations must fail visibly.

## 5.8 Configuration Authority

Preserve:

```text
CLI > run.env > config_bot/default
```

Model artifacts may declare the configuration required to interpret their features.

They must not silently overwrite the live configuration.

The old `.cfg.json` behavior that uses `setattr` to mutate `FEAT_CFG` during model loading must be retired.

Configuration incompatibility must produce an explicit result.

## 5.9 Acceptance Criteria

- Training and inference use the same FeatureEngine.
- ATR/RSI/MACD backend behavior is deterministic.
- Feature names and ordering match exactly.
- Missing-value policies are identical.
- Lookback parity meets approved tolerances.
- Incomplete candles are excluded consistently.
- Unsupported timeframe/model combinations are rejected.
- CLI and runtime configuration precedence is preserved.
- No optional library installation can silently alter predictions.

---

# 6. Decision 4 — Model Evaluation Redesign

**Priority: P1**

## 6.1 Decision

Replace the current validation methodology with synchronized, chronological, out-of-sample evaluation.

The presence of `TimeSeriesSplit` alone does not establish valid time-series evaluation.

The current pair-by-pair concatenation must not be used as the basis for model acceptance.

## 6.2 Dataset Construction

Each sample must contain at least:

```text
instrument
timeframe
candle_timestamp
feature_vector
target
target_end_timestamp
dataset_version
```

All instruments must use a common chronological partitioning scheme.

The dataset must preserve instrument and timestamp identity.

Do not concatenate complete per-pair histories and then split by row position.

## 6.3 Walk-Forward Evaluation

All instruments must be partitioned using common time boundaries.

Example:

```text
Fold 1:
    Train: earlier period
    Purge / Embargo
    Validation: next period

Fold 2:
    Train: expanded historical period
    Purge / Embargo
    Validation: subsequent period

Fold 3:
    Train: expanded historical period
    Purge / Embargo
    Validation: subsequent period
```

The actual dates and fold count must be selected according to available historical data.

The essential requirements are:

- Chronological ordering.
- No random shuffling.
- Identical time boundaries across instruments.
- Scaler fitted only on each fold's training data.
- No validation information entering training.
- No overlap between training label horizons and validation periods.

For the existing six-bar prediction horizon, purge at least the six-bar overlapping label region where necessary.

The implementation must define precisely whether the embargo is expressed in bars or timestamps, especially where instruments have missing candles.

## 6.4 Per-Instrument Evaluation

In addition to aggregate results, report performance separately for each instrument.

This is necessary to detect:

- Currency-pair shortcuts.
- Performance concentration.
- Regime dependence.
- Instrument-specific failures.
- Hidden dependence on a small number of pairs.

Aggregate performance must never conceal a consistently failing instrument.

## 6.5 Required Baselines

At minimum:

1. Always-UP baseline.
2. Always-DOWN baseline.
3. Majority-class baseline.
4. Existing production model baseline.

For the six-bar prediction target, the evaluation must compare the model against these baselines using exactly the same samples.

## 6.6 Required Metrics

### Classification

- Accuracy.
- Balanced Accuracy.
- Precision.
- Recall.
- F1.
- ROC-AUC.
- PR-AUC.
- Confusion Matrix.

### Probability Quality

- Brier Score.
- Log Loss.
- Reliability / Calibration Curve.
- Calibration Error, with a documented calculation.

### Trading Relevance

- Prediction-conditioned forward return.
- Directional return before costs.
- Directional return after estimated transaction costs.
- Spread sensitivity.
- Performance by instrument.
- Performance by market regime.

Classification accuracy alone is insufficient to approve a model.

## 6.7 Label and Cost Policy

The existing target is based on a six-bar forward return with a zero threshold.

This target must first be documented and evaluated.

Do not silently change the label definition during evaluation redesign.

A separate experiment must evaluate whether costs, spread, or a minimum economic edge should be incorporated into the target.

Changing the target horizon or target threshold constitutes a behavior-changing model redesign and requires explicit approval.

## 6.8 Final Holdout

A final chronological holdout must be reserved.

It must not be used for:

- Feature selection.
- Hyperparameter optimization.
- Threshold selection.
- Calibration fitting.
- Repeated model experimentation.

Its purpose is to provide an independent final assessment.

After repeated inspection or optimization against the holdout, it is no longer an untouched holdout.

## 6.9 Price-Unit Feature Investigation

ATR, ATR moving average, and MACD may encode instrument price scale.

Before removing or normalizing these features:

1. Record current feature importance.
2. Measure performance by instrument.
3. Compare pooled model performance with per-instrument performance.
4. Conduct a controlled normalized-feature experiment.
5. Compare out-of-sample results using identical time partitions.

Feature removal requires evidence that the resulting model is more robust, not merely a different importance ranking.

## 6.10 Acceptance Criteria

- All folds use synchronized time boundaries.
- Six-bar label overlap is purged.
- Scalers are fitted inside each training fold.
- Baselines are calculated on identical validation samples.
- A final untouched chronological holdout exists.
- Aggregate and per-instrument metrics are reported.
- Probability quality is evaluated.
- Costs are incorporated into economic evaluation.
- The evaluation report identifies dataset and model versions.
- No model is approved solely on in-sample accuracy.

---

# 7. Decision 5 — Artifact and Model Lifecycle

**Priority: P1**

## 7.1 Decision

Replace live-cycle automatic retraining with offline training and explicit model promotion.

The live trading process must load approved, immutable model releases.

It must not:

- Retrain because an artifact is older than seven days.
- Overwrite a model during a trading cycle.
- Silently switch from XGBoost to RandomForest.
- Load incompatible artifacts through legacy fallback.
- Allow concurrent profiles to write to shared model files.

## 7.2 Model Identity

Model identity must represent the actual prediction task, not simply the consuming profile.

Proposed logical identity:

```text
model_family
prediction_target
timeframe
feature_contract_version
training_universe
label_horizon
```

Profiles are model consumers.

They are not automatically separate models.

### Shared versus Profile-Specific Models

Initial decision:

**Use one shared model only when profiles consume the same prediction contract.**

If profiles differ in any material aspect of:

- Prediction target.
- Timeframe.
- Feature definition.
- Label horizon.
- Training universe.
- Data eligibility.

they must not silently share the same artifact.

Separate model identities must be created where these differences change the statistical meaning of the prediction task.

Do not create four independent models simply because there are four profiles.

Likewise, do not force four profiles to share a model simply because the existing implementation does so.

The final mapping must be established through an explicit profile-to-model compatibility matrix.

## 7.3 Artifact Manifest

Every release must contain a machine-readable manifest.

Minimum fields:

```json
{
  "model_id": "string",
  "model_version": "string",
  "training_run_id": "string",
  "git_commit": "string",
  "created_at_utc": "string",

  "model_family": "xgboost",
  "prediction_target": "string",
  "timeframe": "string",
  "label_horizon": 6,

  "training_universe": [],
  "lookback_bars": 0,

  "feature_names": [],
  "feature_order_hash": "string",
  "feature_contract_version": "string",

  "dataset_id": "string",
  "dataset_hash": "string",

  "scaler_hash": "string",
  "model_hash": "string",
  "config_hash": "string",

  "python_version": "string",
  "numpy_version": "string",
  "pandas_version": "string",
  "xgboost_version": "string",
  "sklearn_version": "string",

  "feature_backend": "string",
  "validation_report_id": "string"
}
```

The actual manifest may include additional fields.

Hashes must be calculated over exact artifact bytes.

The manifest must also have an integrity mechanism, such as a separately stored release checksum or trusted release index. A manifest must not be treated as self-authenticating merely because it contains hashes.

## 7.4 Atomic Release

The existing four-file model save must become an atomic release operation.

Recommended release layout:

```text
models/
    releases/
        <model_id>/
            <model_version>/
                model.json
                scaler.joblib
                feature_config.json
                manifest.json
                validation_report.json

    active/
        <model_id>.json
```

The active reference points to a complete immutable release.

Promotion procedure:

1. Build a release in a temporary directory.
2. Validate every file.
3. Verify checksums.
4. Validate the feature contract.
5. Verify the evaluation report.
6. Flush and finalize the release.
7. Atomically update the active reference.
8. Preserve the previous active reference for rollback.

An incomplete release must never become active.

Use a process-safe lock for operations that modify the active reference.

## 7.5 Artifact Loading

At startup:

- Read the approved active reference.
- Load the exact declared release.
- Validate file integrity.
- Validate model family.
- Validate feature names and order.
- Validate timeframe.
- Validate feature contract.
- Validate scaler compatibility.
- Validate runtime dependency compatibility.

Any failure must prevent the incompatible model from generating predictions.

The failure must not trigger automatic retraining.

## 7.6 Legacy Retirement

Retire:

- Automatic stale-mtime retraining.
- Legacy pickle fallback.
- Silent RandomForest substitution.
- Artifact configuration mutation of live `FEAT_CFG`.
- Shared unqualified `scaler.joblib` loading.

Existing artifacts may be retained for forensic comparison but must not be silently promoted or substituted.

## 7.7 Training Data Reproducibility

Every training run must use an immutable dataset snapshot.

Record:

- Source.
- Instruments.
- Timeframe.
- Date range.
- Candle completeness policy.
- Data hash.
- Label generation version.
- Feature contract version.

Live-fetched data must not be treated as reproducible merely because the same API endpoint is queried again later.

## 7.8 Acceptance Criteria

- Every model has a unique model identity and release version.
- Every release has a complete manifest.
- Every artifact file is integrity-checked.
- Model and scaler are loaded from the same release.
- Incomplete releases cannot become active.
- Concurrent promotion is protected.
- Runtime cannot retrain.
- Legacy fallback is disabled.
- Rollback to the previous release is possible.
- Model releases are reproducible from their recorded inputs.

---

# 8. Decision 6 — Shadow Validation and Deployment

**Priority: P1**

## 8.1 Decision

Implement a shadow evaluation path before enabling new decision behavior.

Shadow mode must calculate the new logic without authorizing execution.

The existing production decision path remains the sole execution authority during shadow validation.

## 8.2 Dual Evaluation

For each eligible market observation, calculate:

```text
OLD PATH:
    Existing ML vote
    Existing strategy score
    Existing consensus
    Existing trade eligibility

NEW PATH:
    Independent ML prediction
    New abstention handling
    Corrected strategy score
    New consensus
    New trade eligibility
```

Record the outputs independently.

The new path must not modify:

- Existing orders.
- Existing positions.
- Broker SL/TP.
- Position sizing.
- Execution permissions.
- Existing decision state.

## 8.3 Shadow Comparison Fields

At minimum:

```text
timestamp
instrument
timeframe

old_model_id
new_model_id

old_ml_vote
new_ml_vote

old_strategy_score
new_strategy_score

old_decision
new_decision

old_eligibility
new_eligibility

old_abstain_reason
new_abstain_reason

decision_changed
direction_changed
eligibility_changed

old_execution_authorized
new_execution_authorized
```

Also record individual score components and relevant market input identifiers.

## 8.4 Shadow Analysis

The comparison report must quantify:

- BUY-to-SELL changes.
- SELL-to-BUY changes.
- Trade-to-no-trade changes.
- No-trade-to-trade changes.
- ML abstention frequency.
- Feature failure frequency.
- Score distribution changes.
- Profile-specific differences.
- Instrument-specific differences.

Where forward outcomes are available, evaluate both decision paths against the same market observations.

Do not claim that shadow performance equals actual execution performance.

Actual fills, spread, slippage, and execution conditions remain separate considerations.

## 8.5 Shadow Sample Requirements

The initial minimum of 20 rows is a smoke-test threshold only.

It is not sufficient for statistical acceptance.

Define separate requirements for:

- Functional smoke testing.
- Feature and prediction coverage.
- Statistical evaluation.
- Live behavior approval.

The number of observations required for statistical evaluation must depend on the expected effect size, variance, and confidence requirements.

Do not use an arbitrary number of trading days as proof of validity.

## 8.6 Kill Switches

Every behavior-changing component must have an independent default-off switch.

Initial naming convention:

```text
OPT_XGB_DIRECT_VOTE=false
OPT_ENGINE_SCORE_FIXES=false
OPT_NEW_FEATURE_CONTRACT=false
OPT_NEW_MODEL_RELEASE=false
OPT_SHADOW_EVALUATION=false
```

These are conceptual names. Final names must be reconciled with existing configuration conventions before implementation.

A master safety gate must prevent any shadow component from authorizing execution.

## 8.7 Acceptance Criteria

- Shadow calculations do not alter existing execution behavior.
- Old and new decisions are independently recorded.
- Differences can be reconstructed from logs.
- Model identity is recorded for both paths.
- Shadow abstentions are measurable.
- No new-path execution can occur.
- Kill switches are independently testable.
- Shadow reports contain coverage and comparison metrics.

---

# 9. Training and Runtime Lifecycle

## 9.1 Training Lifecycle

The intended lifecycle is:

```text
DATA ACQUISITION
      |
      v
DATA VALIDATION
      |
      v
IMMUTABLE SNAPSHOT
      |
      v
FEATURE GENERATION
      |
      v
DATASET VALIDATION
      |
      v
WALK-FORWARD EVALUATION
      |
      v
MODEL TRAINING
      |
      v
FINAL HOLDOUT EVALUATION
      |
      v
ARTIFACT CREATION
      |
      v
INTEGRITY VALIDATION
      |
      v
PROMOTION REVIEW
      |
      v
APPROVED MODEL RELEASE
```

Training must be independently executable.

The live bot must not be responsible for deciding when a new model should be trained.

## 9.2 Runtime Lifecycle

```text
STARTUP
   |
   v
LOAD ACTIVE MODEL REFERENCE
   |
   v
VERIFY MODEL RELEASE
   |
   v
VERIFY FEATURE CONTRACT
   |
   v
INITIALIZE ADVISOR
   |
   v
RUN PREDICTIONS
   |
   v
RECORD PREDICTION STATUS
   |
   v
DECISION LAYER
```

A model incompatibility must produce an explicit unavailable state.

The system must not attempt to repair an incompatible model by silently retraining it.

## 9.3 Model Update Lifecycle

A model update must be an explicit operational event:

```text
TRAIN
  |
  v
EVALUATE
  |
  v
COMPARE WITH ACTIVE MODEL
  |
  v
APPROVE
  |
  v
PROMOTE
  |
  v
VERIFY RUNTIME LOAD
  |
  v
ROLLBACK IF REQUIRED
```

Model promotion is not automatic.

A better validation score alone is insufficient to justify promotion.

---

# 10. Scope and Risk Isolation

## 10.1 In-Scope

Phase 3 includes:

- ML Advisor contract.
- Decision-layer vote handling.
- Engine score correctness.
- Feature consistency.
- Model evaluation methodology.
- Model artifact provenance.
- Offline training lifecycle.
- Shadow validation.
- Controlled deployment.

## 10.2 Out-of-Scope

The following are not part of the ML redesign:

- General strategy redesign.
- Entry and exit strategy optimization.
- Position sizing changes.
- SL/TP optimization.
- Risk-profile redesign.
- OANDA execution refactoring unrelated to the ML contract.
- Portfolio management redesign.
- General trend-lifecycle implementation.

## 10.3 Separately Tracked Trading Risks

The audit identified D1:

`_revise_owned_position` may revise TP independently of the intended dynamic TP controls.

This is a potentially important trading-system risk.

It must be handled as a separate risk investigation, not hidden inside Phase 3 ML implementation.

D8 and D9 also remain runtime verification items:

- D8: Price source and account/environment consistency.
- D9: Strength pool coverage and possible shared source pairs.

These findings must be resolved before relying on the affected runtime evidence.

No unrelated trading behavior should be changed under the authority of this document.

---

# 11. Implementation Roadmap

Implementation is divided into independently reviewable stages.

Each stage has its own scope, evidence, acceptance tests, and completion criteria.

No stage may silently absorb work from a later stage.

## Phase 3.0 — Runtime Risk Containment

**Objective:** Establish that the existing runtime cannot accidentally overwrite or invalidate shared model artifacts.

Tasks:

1. Inspect the actual runtime retraining call path.
2. Confirm whether multiple profiles can start simultaneously.
3. Identify shared artifact write locations.
4. Confirm whether concurrent training can overwrite active files.
5. Establish an explicit temporary prohibition on live-cycle artifact writes.
6. Verify the existing active model remains loadable.
7. Separately investigate D1.

Acceptance:

- Runtime artifact writes are identified.
- Concurrent overwrite risk is eliminated or explicitly contained.
- Existing approved artifacts remain intact.
- No unrelated trading logic changes occur.

## Phase 3.1 — Decision Contract and Scoring Repair

**Objective:** Eliminate fabricated votes and establish correct score semantics.

Tasks:

1. Implement the independent ML prediction result contract.
2. Separate Advisor prediction from strategy eligibility.
3. Introduce explicit abstention reasons.
4. Fix instrument parsing.
5. Standardize MC probability units.
6. Define score component ranges and meanings.
7. Define directional symmetry.
8. Define profile threshold calibration requirements.
9. Add deterministic unit tests.

Acceptance:

- N1, N2, N9, N10, N11 are addressed.
- No fabricated ML votes remain.
- Every score is traceable to its inputs.
- Existing production behavior remains unchanged until explicit activation.

## Phase 3.2 — Feature Contract and Runtime Consistency

**Objective:** Make training and inference feature generation deterministic.

Tasks:

1. Inventory all features and their implementation.
2. Establish a canonical backend.
3. Remove silent optional-backend behavior.
4. Implement feature-name and order validation.
5. Establish the missing-value policy.
6. Measure 5000-bar versus 200-bar window parity.
7. Determine the required warm-up window.
8. Enforce timeframe compatibility.
9. Enforce candle completeness.
10. Preserve configuration precedence.
11. Validate both OCI VM and laptop environments.

Acceptance:

- F4, F5, F6, N5, N6, N7, N12 are addressed.
- Feature output is reproducible across supported hosts.
- Unsupported feature configurations fail visibly.
- No silent zero filling or backend substitution remains.

## Phase 3.3 — Evaluation System Redesign

**Objective:** Establish genuine out-of-sample model evaluation.

Tasks:

1. Define immutable dataset schema.
2. Define synchronized time partitions.
3. Implement walk-forward validation.
4. Implement six-bar purge/embargo.
5. Fit scalers inside individual training folds.
6. Establish required baselines.
7. Produce per-instrument metrics.
8. Evaluate probability calibration.
9. Reserve a final holdout.
10. Investigate price-unit features.
11. Compare normalized-feature experiments.
12. Produce a reproducible evaluation report.

Acceptance:

- F2, F3, F10, F11 are addressed.
- No cross-instrument same-period leakage.
- All baselines use identical validation samples.
- Final holdout remains independent.
- Model quality can be assessed separately from trading-system quality.

## Phase 3.4 — Artifact and Training Lifecycle

**Objective:** Establish reproducible and controlled model releases.

Tasks:

1. Define model identity.
2. Define profile-to-model compatibility.
3. Implement manifest generation.
4. Implement dataset and artifact hashing.
5. Implement immutable release directories.
6. Implement atomic release publication.
7. Implement process-safe promotion.
8. Implement strict runtime artifact loading.
9. Retire legacy fallback.
10. Retire runtime auto-retraining.
11. Implement rollback.
12. Document the offline training procedure.

Acceptance:

- F7, F8, N3 are addressed.
- Every release is traceable.
- Artifacts cannot be silently overwritten.
- Runtime cannot train.
- Model rollback is verified.

## Phase 3.5 — Shadow Validation

**Objective:** Evaluate redesigned behavior without changing live execution.

Tasks:

1. Implement independent shadow Advisor.
2. Implement shadow scoring.
3. Implement dual decision calculation.
4. Record old/new decision differences.
5. Verify execution isolation.
6. Generate coverage and comparison reports.
7. Evaluate outcomes on common market observations.
8. Produce an explicit rollout recommendation.

Acceptance:

- T6 passes.
- No shadow order can be submitted.
- All relevant decision differences are measurable.
- No unclassified prediction failures remain.
- The evidence supports a clear go/no-go recommendation.

## Phase 3.6 — Controlled Activation

**Objective:** Introduce approved changes under explicit operational control.

Tasks:

1. Review all phase acceptance reports.
2. Review shadow results.
3. Approve the model and decision configuration.
4. Enable one behavior-changing component at a time.
5. Verify actual runtime behavior.
6. Verify rollback.
7. Monitor error and abstention rates.
8. Document the approved production baseline.

Acceptance:

- Every activated component has explicit approval.
- Each activation is independently reversible.
- Runtime behavior matches the approved specification.
- No unrelated behavior changes occur.

---

# 12. Acceptance Test Matrix

The original audit tests are retained and extended.

| ID | Test | Requirement |
|---|---|---|
| T1 | Feature window parity | 5000/200-bar comparison measured and approved |
| T2 | Backend parity | Canonical indicator results verified |
| T3 | Prediction contract | Invalid input produces explicit abstention |
| T4 | Artifact integrity | Tampered artifact is rejected |
| T5 | Score sanity | Mathematical directional symmetry verified |
| T6 | Shadow isolation | No execution interference |
| T7 | Prediction independence | Strategy rejection does not suppress ML prediction |
| T8 | Abstention integrity | No synthetic ML vote under any failure condition |
| T9 | Probability units | All internal probabilities use 0–1 |
| T10 | Feature identity | Names, order, shape, and version match |
| T11 | Time-series leakage | No overlapping target information across partitions |
| T12 | Scaler isolation | Scaler fitted only on training fold |
| T13 | Baseline comparison | Always-UP, always-DOWN, and majority baseline available |
| T14 | Per-pair evaluation | Every instrument has separate evaluation metrics |
| T15 | Holdout isolation | Final holdout is not used for tuning |
| T16 | Cross-host consistency | OCI VM and laptop feature outputs agree |
| T17 | Model compatibility | Wrong timeframe or feature contract rejected |
| T18 | Concurrent release safety | Parallel processes cannot corrupt active artifacts |
| T19 | Runtime training prohibition | Live cycle cannot invoke training or artifact publication |
| T20 | Rollback | Previous approved model can be restored |
| T21 | Configuration precedence | CLI > run.env > config_bot/default preserved |
| T22 | Decision reconstruction | Old/new decisions reproducible from recorded evidence |

All tests must have explicit pass/fail results.

A test that was not executed must be marked NOT RUN, not PASS.

A test that lacks sufficient evidence must be marked INCONCLUSIVE.

---

# 13. Logging and Observability Contract

Logging must support diagnosis, statistical evaluation, and future improvement.

## 13.1 Prediction-Level Record

Each prediction record must identify:

- Run ID.
- Timestamp.
- Instrument.
- Timeframe.
- Candle timestamp.
- Model ID.
- Model version.
- Feature contract version.
- Prediction status.
- P(UP).
- P(DOWN).
- Predicted direction.
- Confidence.
- Abstention reason.

## 13.2 Decision-Level Record

Each decision record must include:

- Strategy eligibility.
- Strategy rejection reason.
- ML vote.
- MC vote.
- Strength contribution.
- Other score components.
- Final strategy score.
- Decision threshold.
- Final decision.
- Shadow/production path identity.

## 13.3 Operational Metrics

At minimum, calculate:

- Prediction success rate.
- Abstention rate.
- Abstention reasons by frequency.
- Feature failure rate.
- Model loading failure rate.
- Prediction distribution.
- Direction distribution.
- Score distribution.
- Profile coverage.
- Instrument coverage.
- Shadow decision disagreement rate.

## 13.4 Observation-to-Action Rule

Every monitored metric must have:

1. A defined purpose.
2. A calculation method.
3. A baseline or expected range.
4. A trigger for investigation.
5. A possible engineering response.

Example:

| Observation | Investigation | Possible action |
|---|---|---|
| Rising `missing_feature` | Compare feature contracts across hosts | Repair feature backend |
| High abstention rate | Classify reasons | Repair data or input pipeline |
| LONG/SHORT score imbalance | Inspect score components | Correct directional calculation |
| Pair-specific model failure | Compare per-pair feature distributions | Investigate scaling or data quality |
| Model degradation | Compare walk-forward results | Retrain and evaluate a candidate |
| Artifact load failure | Inspect manifest and hashes | Restore approved release |

Logging is not considered a completed engineering outcome unless the resulting data supports a defined diagnostic or action.

---

# 14. Configuration and Safety Requirements

## 14.1 Configuration Precedence

The established precedence must remain:

```text
CLI
  >
run.env
  >
config_bot
  >
default
```

No model-loading procedure may silently reverse this order.

## 14.2 Behavior Change Classification

Every task must be classified.

**Class A — Behavior-preserving**

Examples:

- Diagnostic logging.
- Manifest generation.
- Test additions.
- Explicit error messages.
- Code cleanup with demonstrated equivalence.

**Class B — Behavior-changing**

Examples:

- New ML voting behavior.
- Score formula correction.
- Feature normalization.
- Label changes.
- Prediction thresholds.
- Model selection.
- Training methodology changes that alter the released model.

Class B requirements:

- Dedicated switch.
- Default OFF.
- Explicit acceptance tests.
- Before/after comparison.
- Rollback procedure.
- Explicit activation approval.

## 14.3 Prohibited Silent Behaviors

The following are prohibited:

- Exception converted into neutral ML vote.
- Missing feature replaced by arbitrary zero.
- Incompatible artifact silently retrained.
- Missing XGBoost silently replaced by RandomForest.
- Artifact configuration silently overwriting live settings.
- Invalid model silently falling back to a different model.
- Shadow calculation influencing execution.
- Training occurring inside the live cycle.

---

# 15. Implementation Agent Rules

All implementation tasks must follow this protocol.

## 15.1 Before Modification

The implementation agent must:

1. Identify the exact files and functions involved.
2. Read the relevant call chain.
3. Identify existing configuration precedence.
4. Identify all consumers of the affected interface.
5. Classify the task as A or B.
6. Identify possible changes to runtime behavior.
7. State the intended minimal modification.

No code modification is allowed before the task scope is established.

## 15.2 During Modification

- Do not perform unrelated refactoring.
- Do not modify strategy behavior outside the task.
- Do not introduce new dependencies without justification.
- Do not silently change defaults.
- Do not remove legacy behavior before its replacement is verified.
- Do not modify production artifacts as a side effect of testing.
- Do not introduce network or execution actions into offline tests.

## 15.3 After Modification

Every implementation report must include:

```text
1. Scope completed
2. Files changed
3. Functions changed
4. Behavior changes
5. Configuration changes
6. Tests executed
7. Test results
8. Evidence
9. Known limitations
10. Rollback procedure
```

For Class B changes, additionally include:

- Old behavior.
- New behavior.
- Shadow comparison.
- Activation switch.
- Default switch state.
- Explicit approval requirement.

## 15.4 Completion Definition

A task is not complete merely because:

- Code compiles.
- Imports succeed.
- A unit test passes.
- A script runs without exceptions.

Completion requires that the intended contract is demonstrated by relevant tests and evidence.

---

# 16. Open Decisions and Explicit Decision Register

The following decisions are established by this design.

| ID | Decision | Status |
|---|---|---|
| D01 | Retain shared FeatureEngine | ACCEPTED |
| D02 | ML prediction independent of strategy eligibility | ACCEPTED |
| D03 | Abstention is an explicit prediction state | ACCEPTED |
| D04 | No synthetic ML votes | ACCEPTED |
| D05 | Internal probability scale is 0–1 | ACCEPTED |
| D06 | Strategy score requires mathematical reconstruction | ACCEPTED |
| D07 | Evaluation uses synchronized chronological partitions | ACCEPTED |
| D08 | Six-bar label overlap must be purged | ACCEPTED |
| D09 | Scaler fitted inside each training fold | ACCEPTED |
| D10 | Model training separated from live runtime | ACCEPTED |
| D11 | Artifact releases are immutable and versioned | ACCEPTED |
| D12 | Promotion is explicit | ACCEPTED |
| D13 | Shadow mode cannot authorize execution | ACCEPTED |
| D14 | Behavior changes default OFF | ACCEPTED |
| D15 | Model identity follows prediction contract, not profile name alone | ACCEPTED |

The following implementation details remain subject to evidence:

| ID | Question | Required evidence | Decision point |
|---|---|---|---|
| O01 | Which profiles can share a model? | Profile-to-model compatibility matrix | Phase 3.4 |
| O02 | What is the final feature warm-up window? | Window parity experiment | Phase 3.2 |
| O03 | Which canonical ATR/RSI implementation? | Reference formula comparison | Phase 3.2 |
| O04 | Should price-unit features be normalized or removed? | Controlled out-of-sample experiment | Phase 3.3 |
| O05 | What probability thresholds are appropriate? | Calibration and decision evaluation | Phase 3.1 / 3.5 |
| O06 | Should the target incorporate transaction costs? | Separate target-definition experiment | Phase 3.3 |
| O07 | What is the final model promotion criterion? | Evaluation report and comparison against active model | Phase 3.4 |
| O08 | What is the final statistical sample requirement? | Variance, effect-size, and power analysis | Phase 3.5 |
| O09 | What model release storage location is authoritative? | Repository and runtime deployment review | Phase 3.4 |

An unresolved implementation detail must not be disguised as an approved architectural decision.

---

# 17. Definition of Phase 3 Success

Phase 3 is successful when all of the following are true.

## Prediction Integrity

- ML predictions are independent of strategy eligibility.
- Prediction and abstention states are explicit.
- No synthetic ML votes exist.
- Every prediction can be traced to its model and input.

## Decision Integrity

- Strength and MC calculations use correct units.
- Directional scoring is mathematically valid.
- Profile thresholds have an explicit interpretation.
- Decisions can be reconstructed from component-level evidence.

## Feature Integrity

- Training and inference share deterministic feature definitions.
- Backend differences cannot silently change predictions.
- Missing-value policies are consistent.
- Timeframe and feature contracts are enforced.

## Evaluation Integrity

- Walk-forward validation is genuinely chronological.
- Cross-instrument leakage is prevented.
- Label overlap is purged.
- Baselines and probability metrics are available.
- Final holdout remains independent.
- Performance is assessed both in aggregate and by instrument.

## Artifact Integrity

- Model provenance is complete.
- Training datasets are immutable and identifiable.
- Artifact hashes are verified.
- Releases are atomic and immutable.
- Runtime retraining is disabled.
- Promotion and rollback are explicit.

## Operational Integrity

- Shadow mode is isolated from execution.
- New and old decision paths can be compared.
- Every observation has a defined diagnostic purpose.
- Every activated change is independently reversible.

A successful Phase 3 does not mean the model is necessarily profitable.

It means the system can reliably establish:

1. What the model was trained on.
2. What it predicts.
3. Whether its prediction is valid.
4. How the strategy interprets it.
5. Why a decision was made.
6. Whether the model demonstrates out-of-sample predictive value.
7. Whether an approved model release is running.

Trading profitability remains a separate empirical objective.

---

# 18. Immediate Next Action

Do not start implementing all phases simultaneously.

The first implementation task should be:

**PHASE3.0 — Runtime Risk Containment and Model Lifecycle Inspection**

Scope:

1. Identify every call path that can invoke training.
2. Identify every location that writes model or scaler artifacts.
3. Identify how all four profiles resolve model paths.
4. Determine whether concurrent processes can overwrite shared artifacts.
5. Identify the exact current production model and scaler files.
6. Establish a safe method to prevent runtime artifact replacement.
7. Preserve existing artifacts and runtime behavior.
8. Produce a concise evidence report.

This task is inspection-first.

It must not retrain, replace, delete, or modify the active model.

The subsequent task is Phase 3.1, beginning with the independent ML prediction contract.

---

# Final Engineering Principle

**The objective is not to make the ML system more complicated. It is to make its behavior explainable, measurable, reproducible, and correct.**

We do not need to replace functioning infrastructure simply because its original design is imperfect.

We repair confirmed defects, measure uncertain behavior, and replace components only when evidence demonstrates that repair is insufficient.

No silent behavior changes.

No synthetic evidence.

No unverified model promotion.

No observation without a defined path to improvement.
