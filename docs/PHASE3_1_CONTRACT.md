# PHASE 3.1 CONTRACT — Prediction Contract & Abstention Semantics

**Status:** Stage A deliverable — contract definition only  
**Phase:** Phase 3.1 — Prediction Contract & Abstention Semantics  
**Stage:** A — Contract Definition; Stage A.2 baseline with approved revisions incorporated (tie rule §1.3.2, self-describing fields §1.3, reconciliation §3.7, freeze exception §4.1.1)  
**Repository:** `/Users/liqin/projects/ai_training_cnn`  
**Branch:** `v2026c`  
**Baseline `HEAD`:** `0a7e212385cbb536a594fd9b3baef62ceb3306d0`  
**Scope:** Documentation only — no `.py` file modified, no commit, no deployment.

> This document is the authoritative Phase 3.1 prediction contract. It defines the
> semantics of one ML prediction attempt, the boundary between Prediction and
> Decision, the classification of the current `generate_signal()` paths, and the
> requirements imposed on downstream consumers. It implements nothing. Stage B,
> C, and D each require separate approval.

---

## 0. Evidence base and verification status

### 0.1 Source files examined

| File | Purpose |
|---|---|
| `strategy_decision.py` | `generate_signal()`, `should_close()`, `select_signals()`, `_predict()` |
| `data_pipeline.py` | `predict_p_up()`, `positive_class_index()`, `_build_matrix()`, inference exceptions |
| `fx_trade_bot_ml.py` | Phase 3.0 `ModelStatus`, `ModelReason`, `ModelInitResult`, `ensure_model()` |
| `fx_trade_bot.py` | Live call sites, MC cache production, `calc_weighted_score()` |
| `fx_trade_bot_v685.py` | Byte-identical twin of `fx_trade_bot.py` |
| `attribution_v2/live_hook.py` | `derive_xgb_p_up()` |
| `attribution_v2/data_bridge.py` | `model_p_up` → `xgb_p_up` mapping |

The source line references below refer to the declared baseline HEAD. They are
not a claim that the current working tree has been independently re-read during
this document revision. Before implementation, the Stage B owner must confirm
that the working tree still corresponds to the declared baseline or record and
review any intervening source changes.

### 0.2 Verified corrections carried forward

| ID | Earlier specification | Verified finding | Contract treatment |
|---|---|---|---|
| V-1 | `DimensionMismatchError` was listed as a concrete inference cause. | The type is defined at `data_pipeline.py:48-49` but has no raise site. Dimension disagreement is raised as `InferenceFeatureError` at `data_pipeline.py:414-418` and `:444-447`. | `DIMENSION_MISMATCH` remains reserved/unreachable; actual feature/dimension violations map to `FEATURE_CONTRACT_VIOLATION`. |
| V-2 | `model_id` might be inferred from `release_id` when a manifest exists. | `release_id` is declared but never assigned; the manifest is existence-checked, not parsed. | `release_id` remains `None`; no identity is invented. |
| V-3 | Only two live `generate_signal()` consumers were listed. | A third live log consumer reads `sig.model_p_up` at `fx_trade_bot.py:2736`; attribution bridge paths also map this field. | Consumers C-3 and C-5 are included. |
| V-4 | `should_close()` was described as a separate active prediction surface. | `should_close()` and `select_signals()` have no repository callers and are dormant. | They are recorded as dormant; activation must adopt the prediction contract. |

### 0.3 Current verification limits

The source confirms how the positive-class column is selected from
`model.classes_`. It does **not**, by itself, prove that the selected class
semantically means UP. The model artifact and its training-label definition were
not sufficiently available to verify that mapping. Therefore:

- `CD` (Class Definition) is **NOT VERIFIED** at this contract baseline.
- A successful inference with a valid numeric probability does not establish a
  directional prediction.
- `READY` is prohibited until the CD verification requirements in §1.3.2 are
  satisfied for the exact model artifact.
- The contract does not authorize Stage B to manufacture missing evidence.

---

## 1. Prediction Contract

### 1.1 `PredictionStatus`

`PredictionStatus` describes the outcome of **one prediction attempt** at the
model-inference boundary. It is Prediction-layer state only.

| Status | Meaning | Layer |
|---|---|---|
| `READY` | Inference completed; a valid probability was produced; CD is verified for the exact artifact; a valid direction was derived under §1.3.2. | Prediction |
| `UNINTERPRETABLE` | Inference completed and produced a valid raw probability, but CD is not verified for the exact artifact; no directional interpretation is permitted. | Prediction |
| `ABSTAIN` | The Prediction layer itself declined to produce a direction under an explicit prediction-layer rule. | Prediction |
| `NOT_RUN` | Prediction did not execute because an input precondition was not met. | Prediction / input precondition |
| `UNAVAILABLE` | The model cannot be used for inference at this time (for example, model/scaler unavailable or unusable). | Prediction |
| `INVALID` | Inference output or inference input violates a defined data, feature, probability, or format requirement. | Prediction |
| `ERROR` | An unexpected execution failure occurred. | Prediction |

**Hard rules**

1. All statuses in this enum belong to the Prediction layer. Strategy filters,
   conviction gates, SL/TP construction, and R/R checks are Decision or Trade
   Plan outcomes. They must never be represented as Prediction statuses.
2. `NOT_RUN` is distinct from `UNAVAILABLE`: the former means the prediction
   attempt did not start; the latter means it could not run because the model
   was not usable.
3. `ABSTAIN` is declared **DEFINED-BUT-CURRENTLY-UNREACHABLE**. The current
   prediction surface is a binary-classifier probability and contains no
   prediction-layer neutral band. The existing `raw_prob < min_prob` check is a
   Decision gate. Stage B must not synthesize `ABSTAIN`.
4. `UNINTERPRETABLE` is not a catch-all. It is permitted only when inference
   succeeded, the raw probability is valid, and CD is unverified for the exact
   artifact. It must not absorb unavailable, invalid, error, or Decision causes.
5. `READY` is a strong assertion: the result is not merely numerically valid;
   it is semantically interpretable as a direction under verified evidence.

### 1.2 `PredictionReason`

Each result has exactly one authoritative reason consistent with its status.

| `PredictionReason` | Meaning | Paired status | Reachability |
|---|---|---|---|
| `INPUT_INSUFFICIENT` | Input precondition failed, such as insufficient bars. | `NOT_RUN` | Reachable |
| `MODEL_NOT_USABLE` | No usable model/scaler at prediction time, including `ScalerMissingError`. | `UNAVAILABLE` | Reachable |
| `FEATURE_CONTRACT_VIOLATION` | Inference input violates the trained feature contract, including missing, non-numeric, non-finite, or dimension-inconsistent features. | `INVALID` | Reachable |
| `DIMENSION_MISMATCH` | Reserved for a distinct `DimensionMismatchError` cause if a real raise path is introduced in a separately approved change. | `INVALID` | Unreachable today |
| `PREDICTION_INVALID_PROBABILITY` | A probability was successfully extracted, but its numeric value is invalid: non-finite or outside `[0,1]`. | `INVALID` | Reachable |
| `PREDICTION_OUTPUT_MALFORMED` | Output structure cannot be parsed: unusable rank/shape, missing class column, invalid class index, or ambiguous output-to-class mapping. | `INVALID` | Reachable |
| `EXECUTION_ERROR` | An unexpected exception occurred during prediction execution. | `ERROR` | Reachable |
| `CLASS_DEFINITION_UNVERIFIED` | Inference succeeded and the raw probability is valid, but CD is not verified for the exact artifact. | `UNINTERPRETABLE` | Reachable today |
| `ABSTAIN_BY_PREDICTION_RULE` | A future, explicitly specified Prediction-layer rule declined to produce a direction. | `ABSTAIN` | Unreachable today |

**Non-overlap rule for output failures**

- Use `PREDICTION_OUTPUT_MALFORMED` when the output cannot be structurally
  interpreted or the target probability cannot be unambiguously extracted.
- Use `PREDICTION_INVALID_PROBABILITY` only after a single candidate probability
  has been successfully extracted and that number fails numeric validity.
- Do not assign both reasons to one event. If extraction is impossible, there
  is no extracted probability to classify as numerically invalid.

`DIMENSION_MISMATCH` and `ABSTAIN_BY_PREDICTION_RULE` are declared but currently
unreachable. Their existence does not authorize fabricated outcomes.

`PredictionReason.MODEL_NOT_USABLE` is distinct from Phase 3.0's
`ModelReason.*`; the namespaces must not be merged.

### 1.3 `PredictionResult` — field contract

```text
PredictionResult
  status                : PredictionStatus
  reason                : PredictionReason
  pair                  : str                 # instrument pair, e.g. "EUR_USD"
  timeframe             : str                 # bar timeframe, e.g. "M15"
  bar_time              : datetime            # timezone-aware UTC bar time
  direction             : Optional[str]       # "BUY" | "SELL" | "NONE"
  raw_probability       : Optional[float]     # neutral numeric output, 0–1
  positive_class_label  : Optional[str]       # model.classes_[pos_idx]; semantic key for raw_probability
  p_up                  : Optional[float]     # interpreted probability of UP
  p_down                : Optional[float]     # only when supported by verified CD
  model_id              : Optional[str]       # formal model version identity
  model_artifact_hash   : Optional[str]       # SHA-256 of exact model artifact
  release_id            : Optional[str]       # manifest release identity
  feature_contract_id   : Optional[str]       # formal feature contract identity
  features_hash         : Optional[str]       # SHA-256 provenance fingerprint
  timestamp             : datetime            # timezone-aware UTC
  diagnostics           : dict                 # supplementary, non-authoritative
```

| Field | Presence and meaning | Forbidden |
|---|---|---|
| `status` | Always present. | Values outside the enum. |
| `reason` | Always present; must pair with status per §1.2. | A mismatched reason/status pair. |
| `pair` | Always present. Identifies which instrument the attempt concerns. | Empty or guessed pair. |
| `timeframe` | Always present. Identifies the bar timeframe of the attempt. | Empty or guessed timeframe. |
| `bar_time` | Always present; timezone-aware UTC time of the bar being predicted. | Naive datetime or bar unrelated to `timeframe`. |
| `direction` | `READY` requires `BUY` or `SELL`; every other status requires `NONE` or `None`. | A consumer-usable direction on any non-`READY` result. |
| `raw_probability` | Present when inference completed and a numeric value passed the §4.3 validity check. It is neutral and does not assert that the selected class is UP. | Calling it `p_up` while CD is unverified; percent scale; NaN/inf/out-of-range values presented as valid. |
| `positive_class_label` | `model.classes_[pos_idx]` captured from the loaded artifact, so `raw_probability` stays auditable once CD is verified. `None` until the class labels are captured. | A guessed label; a label not derived from the artifact's `classes_`. |
| `p_up` | The interpreted probability that the model's positive class is UP. Required for `READY`; `None` for `UNINTERPRETABLE`. | Populating while CD is unverified. |
| `p_down` | `None` unless the verified model output definition supports it. | Assuming `1 - p_up` without verified binary-complement semantics. |
| `model_id` | Formal model version identity. `None` today because not verified. | Hash, filename, or guessed version string. |
| `model_artifact_hash` | SHA-256 fingerprint of the exact model artifact when available. | Treating a hash as logical version identity. |
| `release_id` | Manifest release identity. `None` today; source field is unassigned. | Invented release ID. |
| `feature_contract_id` | Formal feature-contract identity. `None` today. | Substituting `features_hash` or filename. |
| `features_hash` | SHA-256 provenance fingerprint of the features artifact when available. | Treating it as formal contract identity. |
| `timestamp` | Always present, timezone-aware UTC. | Naive datetime or local-time timestamp. |
| `diagnostics` | Supplementary context only; may be empty. | Sole carrier of state or authority. |

#### 1.3.1 Prediction boundary is upstream of Decision

The contract describes the model-inference result, not whether a `Signal` was
ultimately produced.

- A `READY` PredictionResult may exist even when `generate_signal()` returns
  `None` because a later Decision gate rejects it.
- `generate_signal() is None` does not prove that prediction failed.
- The current `Optional[Signal]` interface cannot distinguish these causes;
  the additive PredictionResult seam is intended to make the inference outcome
  independently observable.

#### 1.3.2 CD verification and READY direction derivation (P0)

`CD` means the complete, artifact-specific class-definition evidence needed to
interpret the model's output as UP/DOWN.

**CD verification requirements**

CD may be marked `VERIFIED` only when all of the following are established and
recorded:

1. **Exact artifact binding:** the evidence is bound to the exact model artifact
   by its SHA-256 (`model_artifact_hash`). Evidence for another file, another
   training run, or a filename-only match is insufficient.
2. **Actual class labels:** the model's actual `classes_` values and their
   ordering are captured from the loaded artifact/runtime.
3. **Positive-class mapping:** the selected positive-class label/index is
   explicitly identified, and the `predict_proba()` output columns are shown to
   correspond to `classes_` in that same order.
4. **Training target semantics:** the training label/target definition proves
   which label means UP and which means DOWN. Variable names, comments, or
   inference helper names alone are not proof.
5. **Binary semantics:** the evidence establishes whether the model is exactly
   binary and whether its class probabilities are mutually exclusive and
   exhaustive. Only if this is established may the complementary relation
   `p_down = 1 - p_up` be used.
6. **Evidence provenance:** the verification record identifies the source
   artifact(s), relevant target/label definition, model artifact hash, evidence
   date/version, and reviewer or verification procedure. The record must be
   reproducible.

If any item is missing, ambiguous, inconsistent, or cannot be linked to the
exact artifact, CD remains `NOT VERIFIED`. A successful model load, valid
floating-point output, `positive_class_index()` implementation, or a field
named `p_up` is not sufficient evidence.

**Direction rule**

When and only when CD is verified for the exact artifact, and CD confirms a
binary model whose positive class is UP:

```text
p_up = probability assigned to the verified UP class
p_down = 1.0 - p_up
direction = BUY if p_up > 0.5 else SELL
```

The direction rule operates directly on verified `p_up`; it must not compare
against an unverified or absent `p_down`.

The comparison is strict (`>`), matching the legacy tactic at
`strategy_decision.py:158` (`LONG if p_up > p_down else SHORT`). That path
returned `SHORT` when `p_up == p_down`, i.e. at `p_up == 0.5`. The contract
therefore resolves the boundary tie to `SELL` instead of introducing a new tie
behaviour.

If CD is not verified, the direction rule is undefined and `READY` is illegal.

**Current evidence status:** CD is `NOT VERIFIED` at this contract baseline.
Therefore a successful inference returning a valid numeric probability must
produce:

```text
status            = UNINTERPRETABLE
reason            = CLASS_DEFINITION_UNVERIFIED
raw_probability   = 0.73       # example only
p_up              = None
p_down            = None
direction         = NONE       # or None
```

It must not produce `READY`, `BUY`, `SELL`, or a field labelled `p_up`.

**CD verification is not delegated to Stage B.** Stage B may consume a verified
CD evidence record; it may not invent, infer, or self-certify the missing
training-label semantics.

#### 1.3.3 Historical raw probability and later CD verification (P0)

A historical `UNINTERPRETABLE` record is immutable as an account of what was
known and asserted at prediction time.

If CD is verified later, a historical raw probability may be *reinterpreted*
only through a separate, explicit, auditable offline operation. All conditions
below are mandatory:

1. The historical record contains the exact `model_artifact_hash` used for
   inference.
2. The later CD evidence is verified against that exact same artifact hash.
3. The historical raw probability is known to have been extracted from the
   class column identified by the verified CD evidence. If the historical
   extraction path or class-column mapping cannot be established, no
   reinterpretation is permitted.
4. The reinterpreter records the original prediction record unchanged, the
   CD evidence reference/version, the artifact hash, the reinterpretation time,
   and the derived interpretation.
5. The reinterpreted result is stored as a separate derived record/view. It
   does not overwrite the original status, reason, timestamp, or raw value.
6. Reinterpretation is not retroactive authorization and must not feed live
   Entry Authorization or alter historical trade decisions.

If any condition fails, the historical result remains
`UNINTERPRETABLE`. The default rule is **do not reinterpret**. A later verified
CD enables new predictions to become `READY`; it does not silently rewrite
historical records.

#### 1.3.4 Identity is not provenance

A content fingerprint answers whether two files are byte-identical; it does not
establish a formal model or feature-contract version identity.

| Field | Concept | Current status |
|---|---|---|
| `model_id` | Formal model version identity | NOT VERIFIED; `None` |
| `model_artifact_hash` | Model artifact SHA-256 | Verifiable when artifact exists |
| `release_id` | Manifest release identity | Unassigned; `None` |
| `feature_contract_id` | Formal feature-contract identity | NOT VERIFIED; `None` |
| `features_hash` | Features artifact SHA-256 provenance | Verifiable when artifact exists |

### 1.4 Diagnostics boundary

- `status` and `reason` are the sole authorities for prediction state.
- `diagnostics` is supplementary and may explain details, but cannot override
  or contradict status/reason.
- Downstream consumers must not parse diagnostic strings to infer state.
- While CD is unverified, `raw_probability` must not be relabelled `p_up` in
  logs, diagnostics, status messages, or downstream fields.

### 1.5 Legal and illegal status × field combinations

| Combination | Verdict | Rule |
|---|---|---|
| `READY` + `BUY`/`SELL` + valid `p_up` + artifact-specific verified CD | Legal | Only valid directional prediction representation. |
| `READY` + `NONE`/`None` | Illegal | READY requires direction. |
| `READY` + missing/invalid `p_up` | Illegal | READY requires valid interpreted probability. |
| `READY` while CD is unverified | Illegal | No verified direction semantics. |
| `READY` direction derived from unverified `p_down` | Illegal | Direction uses verified `p_up` and CD. |
| `UNINTERPRETABLE` + valid `raw_probability` + `p_up=None` + no direction | Legal | Successful inference, valid number, unverified CD. |
| `UNINTERPRETABLE` + BUY/SELL | Illegal | No direction is interpretable. |
| `UNINTERPRETABLE` + populated `p_up` | Illegal | Would assert unverified class semantics. |
| `UNINTERPRETABLE` for unavailable/invalid/error/Decision cause | Illegal | Not a catch-all. |
| `ABSTAIN` + no direction | Legal shape; unreachable today | Requires a future explicit prediction-layer rule. |
| `ABSTAIN` + BUY/SELL | Illegal | Abstention is not a direction. |
| Any non-READY status + BUY/SELL | Illegal | No consumer-usable direction. |
| `ERROR` + default probability or neutral fabricated vote | Illegal | Error carries no vote. |

---

## 2. Decision Contract Boundary

This section defines what belongs to Decision and Trade Plan. These outcomes
are not Prediction statuses.

| Concern | Layer | Legacy path |
|---|---|---|
| `raw_prob < min_prob` | Decision | §3 row 3 |
| MC filter BLOCK | Decision | §3 row 4 |
| Regime filter BLOCK | Decision | §3 row 5 |
| ADX filter BLOCK | Decision | §3 row 6 |
| Pivot filter BLOCK | Decision | §3 row 7 |
| StrengthGap filter BLOCK | Decision | §3 row 8 |
| `conviction < min_conviction_score` | Decision | §3 row 9 |
| SL/TP construction | Decision / Trade Plan | §3 row 10 |
| R/R validity | Decision / Trade Plan | §3 row 11 |
| Produced `Signal` | Decision output | §3 row 12 |

Mandatory boundary statements:

- A valid PredictionResult does not imply Decision acceptance.
- A Decision rejection does not invalidate a prediction.
- A model predicting BUY does not imply strategy filters pass.
- A strategy rejecting BUY does not imply model inference failed.
- SL/TP failure does not invalidate the prediction.
- Low conviction does not make the model probability untrustworthy.

**Decision boundary object (D-4):** Stage A names `DecisionResult` at the
type/boundary level only. It does not implement the object, define its complete
field set, or authorize strategy-layer refactoring.

### 2.1 Canonical example

```text
Model Prediction:
    status    = READY
    direction = BUY
    p_up      = 0.61

Strategy Decision:
    MC filter = BLOCK
    result    = Decision REJECTED

Prediction remains READY.
```

This example assumes CD is verified for the exact artifact. If CD is
unverified, the valid raw number is represented as `UNINTERPRETABLE`, not READY.

Under the current baseline CD is `NOT VERIFIED`, so this example is
**unreachable** today; it describes the target state only. The legacy
`Signal.direction` that may still appear is legacy-derived and unverified
(§3.7).

Representing an MC BLOCK as `PredictionStatus.ABSTAIN` is incorrect.

---

## 3. Legacy `generate_signal()` Mapping

`StrategyEngine.generate_signal()` is located at
`strategy_decision.py:117-266` in the declared baseline.

| # | Source | Condition | Legacy return | Owning layer | Contract mapping |
|---|---|---|---|---|---|
| 1 | `:131-135` | Insufficient bars (`< 5`) | `None` | Prediction input precondition | `(NOT_RUN, INPUT_INSUFFICIENT)` |
| 2 | `:139-153` | `_predict()` raises | `None` | Prediction | Classify as UNAVAILABLE, INVALID, or ERROR according to actual cause (§3.2) |
| 3 | `:163-173` | `raw_prob < min_prob` | `None` | Decision | `DECISION_PROBABILITY_GATE_BELOW_MIN` |
| 4 | `:182-184` | MC BLOCK | `None` | Decision | `DECISION_FILTER_MC_BLOCK` |
| 5 | `:191-193` | Regime BLOCK | `None` | Decision | `DECISION_FILTER_REGIME_BLOCK` |
| 6 | `:200-202` | ADX BLOCK | `None` | Decision | `DECISION_FILTER_ADX_BLOCK` |
| 7 | `:211-213` | Pivot BLOCK | `None` | Decision | `DECISION_FILTER_PIVOT_BLOCK` |
| 8 | `:220-222` | StrengthGap BLOCK | `None` | Decision | `DECISION_FILTER_STRENGTH_GAP_BLOCK` |
| 9 | `:231-236` | Conviction below minimum | `None` | Decision | `DECISION_CONVICTION_BELOW_MIN` |
| 10 | `:241-243` | SL/TP construction fails | `None` | Decision / Trade Plan | `TRADE_PLAN_SLTP_CONSTRUCTION_FAILED` |
| 11 | `:245-247` | R/R invalid | `None` | Decision / Trade Plan | `TRADE_PLAN_RR_INVALID` |
| 12 | `:249-266` | Success | `Signal` | Decision output | `DECISION_ACCEPTED` |

Only rows 1–2 are Prediction-layer paths. Rows 3–12 must not map to any
PredictionStatus.

### 3.1 Exhaustive `None` paths

The baseline contains eleven `return None` statements and one `return Signal`.
The reported `None` line numbers are 135, 153, 173, 184, 193, 202, 213, 222,
236, 243, and 247; the successful `Signal` return begins at 249.

### 3.2 Exception classification

| Actual cause | Evidence site | Status/reason |
|---|---|---|
| `ScalerMissingError` | `strategy_decision.py:294-298`; `data_pipeline.py:409-412`, `:466-467` | `(UNAVAILABLE, MODEL_NOT_USABLE)` |
| `InferenceFeatureError` | `data_pipeline.py:414-453` | `(INVALID, FEATURE_CONTRACT_VIOLATION)` |
| `DimensionMismatchError` | Defined at `data_pipeline.py:48-49`; no raise site | Reserved `(INVALID, DIMENSION_MISMATCH)`; unreachable today |
| Any other exception | Example: unexpected `TypeError` in inference path | `(ERROR, EXECUTION_ERROR)` |

A successful `predict_p_up()` call is not an exception. If it returns a valid
number while CD is unverified, the outcome is
`(UNINTERPRETABLE, CLASS_DEFINITION_UNVERIFIED)`.

### 3.3 Layer classification summary

| Path | Semantics | Layer |
|---|---|---|
| Insufficient bars | Input precondition not met | Prediction |
| `_predict()` exception | Inference unavailable, invalid, or failed | Prediction |
| Probability minimum gate | Strategy rejection | Decision |
| MC / Regime / ADX / Pivot / StrengthGap BLOCK | Strategy filters | Decision |
| Insufficient conviction | Composite-score rejection | Decision |
| SL/TP failure | Trade-plan construction failure | Decision / Trade Plan |
| R/R invalid | Trade-plan validity failure | Decision / Trade Plan |
| `Signal` returned | Strategy produced a signal | Decision output |

### 3.4 Consumers of `generate_signal()`

| ID | Consumer | Current behaviour | Contract requirement |
|---|---|---|---|
| C-1 | Step 4 multi-TF confluence (`fx_trade_bot.py:2156`) | `if sig` then `sig.action`; `None` contributes no vote and may fail confluence. | Record PredictionResult independently; distinguish non-READY prediction from later Decision rejection. |
| C-2 | Step 7 scoring feed (`:2572-2595`) | Missing signal/model probability becomes XGB NEUTRAL; `prob_raw=None` may lead to synthesized X from S/R. | Record true ML state separately and label legacy fallback distinctly. |
| C-3 | Open-reason log (`:2736-2741`) | `sig.model_p_up or 0.0`; log/diagnostic only. | Report status; never present 0.0 as model probability when it is a fallback. |
| C-4 | `attribution_v2/live_hook.py:137-140` | Reads `model_p_up`, then falls back to `w["X"]`, then `raw_prob`; observer only. | Use `PredictionResult.p_up` only for READY; otherwise report no interpreted P(up). |
| C-5 | `attribution_v2/data_bridge.py:95-110` | Maps `model_p_up` / `prob_raw` through scale-aware clipping. | Record source and preserve explicit unit semantics. |
| C-6 | `StrategyEngine.should_close()` | Calls `_predict()` directly; dormant, no repository caller. | Must adopt PredictionResult if activated. |
| C-7 | `StrategyEngine.select_signals()` | Consumes Signal only; dormant, no repository caller. | No current change; must not bypass contract if later activated. |

C-1/C-2/C-3 are reported to exist identically in `fx_trade_bot_v685.py`,
the byte-identical twin used by `launch_dual_bot.sh`.

Stale/out of scope: `fx_trade_bot_ml_v1.py` and `fx_trade_bot_v683.py` are not
imported by a live entry point in the verified baseline.

### 3.5 Current probability surface

- `predict_p_up()` at `data_pipeline.py:464-471` returns the selected probability
  column and a second tuple element that is currently unused.
- `positive_class_index()` follows `model.classes_`; it does not simply assume
  column 1.
- The current strategy derives `p_down = 1 - p_up`, but that is existing
  strategy behaviour, not proof of the training-label semantics.
- `Signal` contains `raw_prob`, `model_p_up`, `edge`, `conviction_score`,
  `direction`, and `action`; it has no `p_down` and no explicit representation
  for abstention or invalidity.

### 3.6 Phase 3.0 identity surface

`ModelInitResult` provides `status`, `reason`, `detail`, `artifact_path`,
`release_id`, `manifest_present`, `model_hash`, `scaler_hash`, `features_hash`,
`cfg_hash`, `backend`, `host_id`, `profile`, and `timestamp`.

- It has no `model_id` or `feature_contract_id`.
- `release_id` is declared but unassigned; the manifest is existence-checked,
  not parsed.
- Hashes are byte digests. `model_hash` is `None` when the model artifact is
  absent.
- These values are populated by a live `ensure_model()` run and are distinct
  from the per-prediction result.

### 3.7 `Signal` versus `PredictionResult` reconciliation

For the same prediction attempt, `generate_signal()` and the additive
`PredictionResult` describe different layers and may legitimately disagree
today:

- While CD is unverified, a successful inference is `UNINTERPRETABLE` and
  carries no direction (§1.3.2).
- The legacy `generate_signal()` path still derives a direction from
  `p_up > p_down` (`strategy_decision.py:155-159`) using the unverified class
  definition, and may return a `Signal` with `BUY` or `SELL`.

This divergence is expected and must be represented explicitly, never hidden:

1. A direction produced by the legacy path while CD is unverified is
   **legacy-derived, unverified**. It is existing strategy behaviour, not a
   verified ML directional prediction.
2. Such a direction must never be presented, logged, or upgraded as a `READY`
   `PredictionResult`, a verified model direction, or an interpreted `p_up`.
3. While CD is unverified, `READY` and the §2.1 canonical example are
   **unreachable**. §2.1 is retained as the target-state example only.
4. Where the two surfaces must be reconciled, `PredictionResult` is the
   prediction authority; the legacy `Signal.direction` is a Decision-layer
   output whose class semantics remain unverified.
5. This reconciliation only makes the current divergence auditable. It does not
   authorize rewiring C-2, changing Step 7 scoring, or altering Entry
   Authorization (§4.1.1).

---

## 4. Consumer, Probability, Unit, Identity, and Timestamp Contracts

### 4.1 Consumer contract

| Consumer | Required behaviour | Forbidden behaviour |
|---|---|---|
| C-1 | Read PredictionResult status separately from Decision outcome. | Inventing a vote for non-READY. |
| C-2 | Record true ML state independently; distinguish it from legacy scoring fallback. | Presenting fallback as a valid ML prediction or changing its trading impact without approval. |
| C-3 | Log status alongside score; distinguish missing/default values. | Presenting `0.0` as an actual model probability when synthesized. |
| C-4 | Consume `p_up` only when READY. | Synthesizing P(up) from non-READY state. |
| C-5 | Preserve scale-aware boundary behaviour and record source/unit. | Silent unit reinterpretation. |
| C-6 | Adopt PredictionResult if `should_close()` is ever activated. | Bypassing the contract. |
| C-7 | Remains dormant and unaffected. | Reintroducing an untracked prediction path. |

**Freeze:** ML state transparency is in scope; trading behaviour is frozen.
Any change to Step 7 scoring, fallback, votes, weights, or Entry Authorization
requires separate approval.

#### 4.1.1 C-2: ML-state transparency versus legacy scoring

1. PredictionResult records the real ML state independently.
2. Logs distinguish true model output from legacy XGB NEUTRAL and synthesized X.
3. The legacy fallback may remain through Stage C, but must be labelled
   `legacy scoring behaviour`.
4. Removing, replacing, or changing the trading impact of that fallback requires
   separate approval.
5. A non-`READY` `PredictionResult` is not a valid ML directional prediction.
   No **new `PredictionResult` consumer** (the additive Stage B seam) may count
   it as an ML vote or pass it to Entry Authorization.
6. The existing live Step 7 scoring path (C-2) is today **not** a
   `PredictionResult` consumer: it still reads the legacy `Signal`/`model_p_up`
   surface. It is registered here as a **known exception**, not implied
   non-compliance. That path is frozen by §4.1 and may only be changed under a
   separate approval gate (candidate: Phase 3.6 Controlled Activation). Its
   presence does not mean the live system is already contract-compliant, and
   this contract does not assert that it is.

### 4.2 Direction rule

| Status | Allowed direction |
|---|---|
| `READY` | `BUY` or `SELL` only |
| `UNINTERPRETABLE` | `NONE` or `None` |
| `ABSTAIN` | `NONE` or `None` |
| All other statuses | `NONE` or `None` |

The READY direction is produced only by §1.3.2. A READY result without a
verified derivation is illegal.

### 4.3 Probability contract

- Canonical probability unit is 0–1, not percent.
- Numeric validity requires:
  `p is not None and math.isfinite(p) and 0.0 <= p <= 1.0`.
- `NaN`, positive/negative infinity, and out-of-range values are invalid.
- `raw_probability` carries a valid numeric inference output without asserting
  class semantics.
- `positive_class_label` records `model.classes_[pos_idx]` from the loaded
  artifact without asserting that the label means UP. It is what keeps
  `raw_probability` auditable if CD is verified later.
- `p_up` is populated only when CD confirms the positive class is UP.
- `p_down` is not assumed to equal `1 - p_up`; that relation is permitted only
  when artifact-specific CD confirms binary complementary semantics.
- Output structure failure and numeric invalidity use distinct reasons as
  defined in §1.2.

### 4.4 Unit conversion boundary (P0)

#### 4.4.1 New Prediction Interface

The new interface has a canonical **input/output contract of 0–1 probability
units**.

The phrase “exactly one explicit conversion” means **at most one conversion
operation at one designated boundary when the declared source unit differs
from the canonical target unit**. It does not mean every value must be
mathematically transformed.

Rules:

1. The source unit must be declared by the producing interface or source
   contract. It must not be guessed from the numeric magnitude.
2. If source unit is already 0–1, no conversion is performed.
3. If source unit is explicitly percent (0–100), conversion to 0–1 occurs once
   at the designated adapter boundary.
4. The adapter records source unit, target unit, and whether conversion was
   applied.
5. Downstream consumers receive canonical 0–1 values and must not convert them
   again.
6. Values such as `0.61` must not be multiplied by 100; values such as `51.3`
   must not be divided by 100 unless the source contract explicitly declares
   percent.
7. Ambiguous or undeclared source units are rejected as malformed/invalid
   input according to the actual failure: inability to establish the unit or
   parse the interface is `PREDICTION_OUTPUT_MALFORMED`; a parsed number that
   violates the canonical range is `PREDICTION_INVALID_PROBABILITY`.

This contract does not assert that the current `predict_p_up()` path needs a
conversion. Its source is expected to be verified before adapter implementation.

#### 4.4.2 Existing MC path — OPEN / unresolved

- MC cache producer stores probabilities on a 0–100 scale, including
  `mc_data["p_up"]`, `mc_data["p_down"]`, and percentile values.
- The same dictionary is passed to `generate_signal()` and read by `_eval_mc()`,
  whose defaults and thresholds are on a 0–1 scale.
- This is a verified scale mismatch in the declared baseline, recorded but not
  fixed by Phase 3.1.
- `attribution_v2` `_prob_clip` is a separate path and is not evidence that the
  MC path converts correctly.
- MC cache and MC scoring remain unchanged and out of scope. Any fix requires a
  separate task and approval.

### 4.5 Identity and timestamp contract

- Timestamp is timezone-aware UTC and records prediction time.
- `model_id` and `feature_contract_id` remain `None` until formal identities
  are established.
- `model_artifact_hash` and `features_hash` are provenance fingerprints only.
- `release_id` remains `None` until the manifest is actually parsed and a
  validated release identity is available.
- No filename, path, hash, or guessed string may be substituted for a formal
  identity.

---

## 5. Phase 3.0 Interface

`ModelStatus` and `PredictionStatus` are separate enums and separate layers.

- `ModelStatus` describes runtime model availability, resolved at
  `ensure_model()` time.
- `PredictionStatus` describes one prediction attempt.
- `ModelReason` and `PredictionReason` remain separate namespaces.

| Phase 3.0 ModelInitResult.status | Phase 3.1 effect |
|---|---|
| `READY` | Prediction may run. It does not imply PredictionResult READY. |
| `UNAVAILABLE` | `(UNAVAILABLE, MODEL_NOT_USABLE)` |
| `INCOMPATIBLE` | `(UNAVAILABLE, MODEL_NOT_USABLE)` |
| `LOAD_FAILED` | `(UNAVAILABLE, MODEL_NOT_USABLE)` |

A READY ModelInitResult permits inference but does not establish CD. Successful
inference with valid probability and unverified CD remains
`UNINTERPRETABLE`.

---

## 6. Compatibility, Adapter Boundary, Tests, and Forbidden Scope

### 6.1 Compatibility and adapter boundary

A single additive prediction-boundary entry point is the designated seam. It
wraps the existing inference path and returns a PredictionResult. Stage A
defines the contract only; it does not select or implement the code structure.

**Adapter input contract**

The adapter receives an already prepared inference input and the model/runtime
context needed to execute the prediction. It does not independently rebuild
features or invent a second feature pipeline.

**Precondition ownership**

- The caller that owns the source data and bar history is responsible for the
  bars-count precondition.
- If the precondition fails before the adapter is invoked, the caller records
  `(NOT_RUN, INPUT_INSUFFICIENT)` as the prediction-attempt outcome.
- The adapter must not duplicate or redefine the bars-count threshold.
- Once invoked, the adapter owns inference-boundary checks: model usability,
  input feature contract, output structure, probability numeric validity, CD
  interpretability, and prediction result construction.
- The exact placement of the adapter relative to `generate_signal()` is a
  Stage B implementation decision, but the precondition must have one
  authoritative owner and one documented threshold.

This avoids two independent bars checks drifting apart while preserving the
distinction between “prediction never started” and “prediction started but
failed.”

**Compatibility rules**

- Existing call sites remain unchanged until Stage C is separately approved.
- `generate_signal()` retains its existing signature and `Optional[Signal]`
  return during Stage A.
- `Signal` remains a Decision output and is wrapped, not extended with its own
  PredictionStatus. It may hold a reference to the PredictionResult from which
  it was derived, but PredictionResult remains the prediction authority.
- `attribution_v2/live_hook.py` and dormant `should_close()` are not rewired in
  Stage A.
- Entry Authorization is untouched.

### 6.2 Test matrix for Stage D

| ID | Case | Expected result | Dependency |
|---|---|---|---|
| T-01 | Bars precondition fails before adapter invocation | `NOT_RUN / INPUT_INSUFFICIENT` | Data-only |
| T-02 | `ScalerMissingError` | `UNAVAILABLE / MODEL_NOT_USABLE` | Stub/type test |
| T-03 | `InferenceFeatureError` | `INVALID / FEATURE_CONTRACT_VIOLATION` | Stub/type test |
| T-04 | Unexpected exception | `ERROR / EXECUTION_ERROR` | Stub |
| T-05 | Valid inference with verified CD | READY, valid p_up, BUY/SELL | Dependency/artifact gated |
| T-06 | Decision rows 3–11 reject | Prediction state remains independently recorded | Structural |
| T-07 | MC BLOCK | Does not create ABSTAIN or alter PredictionResult | Structural |
| T-08 | READY + direction NONE | Rejected as illegal | Data-only |
| T-09 | NaN/inf/out-of-range probability | `INVALID / PREDICTION_INVALID_PROBABILITY` | Data-only |
| T-10 | p_down without verified binary CD | Remains None | Data-only |
| T-11 | Unit contract | No conversion for declared 0–1; one conversion only for explicitly declared percent; no magnitude guessing | Data-only |
| T-12 | Non-READY result | Never represented as valid ML prediction/vote; legacy fallback remains separately labelled | Structural |
| T-13 | ABSTAIN reachability | No synthetic ABSTAIN | Structural |
| T-14 | ModelStatus vs PredictionStatus | Distinct enums/namespaces | Structural |
| T-15 | Identity/provenance | Formal IDs remain None; hashes remain fingerprints | Structural |
| T-16 | Direction derivation | Uses verified p_up + artifact-specific CD, never unverified p_down | Stub/evidence gated |
| T-17 | C-2 transparency | True ML state and legacy fallback separately recorded; scoring unchanged | Stub/integration |
| T-18 | Successful inference + unverified CD | UNINTERPRETABLE; raw_probability populated; p_up None; no direction | Stub |
| T-19 | UNINTERPRETABLE exclusivity | Not used for unavailable/invalid/error; identity fields follow contract | Data-only |
| T-20 | CD evidence completeness | Each of six evidence requirements in §1.3.2 is required for VERIFIED | Data-only/evidence fixture |
| T-21 | Artifact binding | CD evidence hash must equal prediction artifact hash | Data-only |
| T-22 | Historical reinterpretation | Original record immutable; derived record requires exact artifact match and full audit metadata | Data-only |
| T-23 | Output reason separation | Unparseable structure → MALFORMED; extracted but invalid number → INVALID_PROBABILITY | Data-only |
| T-24 | Adapter precondition ownership | Bars check has one owner; adapter does not redefine threshold | Structural |
| T-25 | Tie rule at `p_up == 0.5` | Resolves to `SELL`, matching legacy; no new tie behaviour | Data-only |
| T-26 | `Signal`/`PredictionResult` reconciliation | Legacy direction is legacy-derived, unverified; never upgraded to READY; `READY` and §2.1 unreachable while CD unverified | Structural |
| T-27 | Self-describing fields | `pair`, `timeframe`, `bar_time`, `positive_class_label` present per §1.3 | Data-only |

Dependency-gated tests must not trigger dependency installation or upgrades.
Existing environment constraints remain in force.

### 6.3 Forbidden boundary

The following remain outside this contract and are not authorized:

- Entry Authorization / Step 7 behaviour changes
- Exit logic
- SL/TP behaviour
- Position sizing
- OANDA order flow
- Scheduler cadence
- Training target definitions
- Feature engineering
- ML probability threshold changes
- MC scoring or MC cache changes
- Strength scoring
- `FINAL` weights
- `docs/Development_plan.md`

---

## 7. Decision Register (D-1 … D-22)

### Group A — Layer ownership

| ID | Decision | Rationale |
|---|---|---|
| D-1 | `generate_signal()` rows 1–2 are Prediction; rows 3–12 are Decision/Trade Plan/output. | Strategy gates do not define model outcome. |
| D-2 | ABSTAIN is defined but currently unreachable. | No prediction-layer abstention rule exists. |
| D-3 | Insufficient bars maps to NOT_RUN / INPUT_INSUFFICIENT. | Separates not-started from model unavailable. |
| D-4 | Name DecisionResult at boundary/type level only; do not implement in Stage A. | Makes layer boundary explicit without authorizing refactor. |

### Group B — Prediction classification

| ID | Decision | Rationale |
|---|---|---|
| D-5 | ScalerMissingError → UNAVAILABLE / MODEL_NOT_USABLE. | Model cannot run. |
| D-6 | InferenceFeatureError → INVALID / FEATURE_CONTRACT_VIOLATION; DimensionMismatchError reserved/unreachable. | Actual raise paths are verified. |
| D-7 | Unexpected exception → ERROR / EXECUTION_ERROR. | Never fabricate neutral vote/default probability. |

### Group C — Field semantics

| ID | Decision | Rationale |
|---|---|---|
| D-8 | READY + NONE is illegal. | READY asserts an interpretable direction. |
| D-9 | p_down is None until artifact-specific CD confirms binary complementary semantics. | Do not assume `1-p_up`. |
| D-10 | model_id and feature_contract_id remain None; hashes are provenance only; release_id remains None today. | No formal identities verified. |
| D-11a | New interface uses canonical 0–1; conversion only when declared source unit differs, at one designated boundary. | Avoid both missing and duplicate conversions. |
| D-11b | Existing MC 0–100 vs `_eval_mc` 0–1 mismatch remains OPEN; MC cache unchanged. | Separate path; not fixed here. |
| D-12 | READY direction rule is conditional on verified CD; CD is NOT VERIFIED today. | No fabricated direction. |
| D-13 | Successful inference + valid probability + unverified CD → UNINTERPRETABLE / CLASS_DEFINITION_UNVERIFIED. | Gives the success path a truthful legal state. |
| D-14 | CD VERIFIED requires the complete six-part evidence chain in §1.3.2 and exact artifact binding. | Prevents names/code shape from being mistaken for target semantics. |
| D-15 | Historical raw_probability is not silently reinterpreted; any reinterpretation is a separate immutable-derived-record operation under §1.3.3. | Preserves historical audit truth. |
| D-16 | Unit conversion is conditional on declared source units; already-canonical values are not transformed; magnitude guessing is forbidden. | Clarifies “exactly one conversion.” |
| D-17 | `PREDICTION_OUTPUT_MALFORMED` covers structural/extraction failure; `PREDICTION_INVALID_PROBABILITY` covers an extracted but invalid numeric value. | Eliminates reason overlap. |
| D-18 | Bars precondition has one owner outside the adapter; adapter owns inference-boundary checks and does not duplicate the threshold. | Prevents divergent precondition logic. |

### Group D — Stage A.2 approved revisions

| ID | Decision | Rationale |
|---|---|---|
| D-19 | A direction tie at `p_up == 0.5` resolves to `SELL`, matching legacy `strategy_decision.py:158` (`p_up > p_down`). | Aligns the contract with unchanged legacy behaviour instead of inventing a new tie rule. |
| D-20 | `PredictionResult` is self-describing: it always carries `pair`, `timeframe`, `bar_time`, and `positive_class_label` (`model.classes_[pos_idx]`). | Makes each result auditable on its own and keeps `raw_probability` interpretable once CD is verified. |
| D-21 | While CD is unverified, `READY` and §2.1 are unreachable and the legacy `Signal.direction` is recorded as legacy-derived, unverified (§3.7). | Prevents the two prediction surfaces from silently disagreeing for the same attempt. |
| D-22 | The non-`READY` no-vote / no-Entry-Authorization rule binds new `PredictionResult` consumers; the legacy C-2 path is a registered known exception under the §4.1 freeze (later gate, e.g. Phase 3.6). | Avoids implying that the live system is already contract-compliant. |

### Guiding principle

`UNAVAILABLE` = model cannot run.  
`NOT_RUN` = prediction never started.  
`ABSTAIN` = Prediction layer declined by an explicit rule.  
`INVALID` = input/output violates the prediction contract.  
`ERROR` = unexpected execution failure.  
`UNINTERPRETABLE` = inference succeeded with a valid number, but CD is not
verified, so no direction can be interpreted.  
`READY` = inference succeeded and the result is valid and directionally
interpretable under artifact-specific verified CD.

None of these states may be collapsed into an ambiguous `None`, and none may
absorb a Decision-layer rejection.

---

## 8. Design Principle — Prediction ≠ Decision ≠ Authorization

| Layer | Question | Phase 3.1 role |
|---|---|---|
| Prediction | What did the model output, and can it be interpreted? | Defines this precisely. |
| Decision | How does the strategy interpret/combine evidence? | Boundary defined; behaviour unchanged. |
| Authorization | Is execution permitted? | Untouched; separate approval required. |

A successful prediction does not imply a trade should occur. A strategy
direction does not imply execution is authorized. A numerically valid output
does not imply a semantically verified direction.

---

## 9. Deferred Work

| Work item | Status |
|---|---|
| Implement DecisionResult / refactor strategy layer | Deferred; separate approval |
| Model probability calibration | Later Evaluation |
| `0.55` threshold optimization | Later Evaluation |
| MC scoring rework | Separate task |
| Strength scoring rework | Separate task |
| FINAL weight redistribution | Separate task |
| Entry Authorization modification | Separate approval |
| Training set / label / CV rework | Later Training & Evaluation |
| Feature engineering changes | Not authorized |
| MC percentage cache changes | Not authorized |
| CD evidence acquisition/verification | Evidence task; must precede READY activation |
| Historical reinterpretation tooling | Separate offline task; not live activation |

---

## 10. Acceptance Mapping

| ID | Acceptance criterion | Contract location |
|---|---|---|
| A-01 | Six principal contract areas: Prediction, Decision, legacy mapping, consumer/unit/identity, Phase 3.0, compatibility/tests | §§1–6 |
| A-02 | Every legacy return path classified by layer | §3 |
| A-03 | ABSTAIN is Prediction-only and reachability stated | §1.1, D-2 |
| A-04 | NOT_RUN distinct; successful inference with unverified CD represented | §1.1, D-3, D-13 |
| A-05 | READY + NONE illegal; direction requires verified CD | §§1.3.2, 1.5, 4.2 |
| A-06 | p_down not assumed; finite/range checks required | §§1.2, 4.3 |
| A-07 | Identity and provenance separated | §§1.3.4, 4.5 |
| A-08 | Diagnostics non-authoritative | §1.4 |
| A-09 | DecisionResult named at boundary only | §2, D-4 |
| A-10 | Decision register D-1 through D-22 resolved | §7 |
| A-11 | All identified consumers have required/forbidden behaviour | §§3.4, 4.1 |
| A-12 | Worked example; MC BLOCK is not ABSTAIN | §2.1 |
| A-13 | ModelStatus and PredictionStatus separate | §5 |
| A-14 | Forbidden boundary explicit | §6.3 |
| A-15 | Stage A documentation-only scope; no `.py` changes | Execution record required |
| A-16 | `docs/Development_plan.md` untouched; unrelated changes preserved | Execution record required |
| A-17 | Exact statement “Entry Authorization remains unchanged and unresolved.” included | §11 |
| A-18 | No commit and no deployment | Execution record required |
| A-19 | CD VERIFIED has an artifact-specific evidence standard | §1.3.2, D-14, T-20/T-21 |
| A-20 | Historical reinterpretation is explicit, immutable, and artifact-bound | §1.3.3, D-15, T-22 |
| A-21 | Unit conversion has declared source unit, one boundary, no magnitude guessing | §4.4.1, D-16, T-11 |
| A-22 | Malformed output and invalid numeric probability reasons do not overlap | §1.2, D-17, T-23 |
| A-23 | Adapter input and precondition ownership are unambiguous | §6.1, D-18, T-24 |
| A-24 | Direction tie at `p_up == 0.5` resolves to `SELL`, matching legacy | §§1.3.2, D-19, T-25 |
| A-25 | `PredictionResult` is self-describing (`pair`/`timeframe`/`bar_time`/`positive_class_label`) | §1.3, D-20, T-27 |
| A-26 | `Signal`/`PredictionResult` reconciliation stated; `READY` unreachable while CD unverified | §§2.1, 3.7, D-21, T-26 |
| A-27 | Non-`READY` no-vote rule binds new consumers; legacy C-2 registered as a known exception | §4.1.1, D-22 |

**Execution evidence is separate from contract text.** A-15, A-16, and A-18
cannot be proven by this document alone. They require a Stage A execution report
and repository status evidence.

---

## 11. Phase Status

| Phase | Goal | Status |
|---|---|---|
| Phase 3.0 | Runtime Containment | Implementation Complete — Verification Partial |
| Phase 3.1 | Prediction Contract | Stage A contract revised through Stage A.2; Gate A.2 pending explicit review/approval |
| Phase 3.2 | Feature / Inference Consistency | Pending |
| Phase 3.3 | Training & Evaluation Integrity | Pending |
| Phase 3.4 | Model Calibration & Validation | Pending |
| Phase 3.5 | Shadow Evaluation | Pending |
| Phase 3.6 | Controlled Activation | Pending |

**Entry Authorization remains unchanged and unresolved.**

**Stage B is not authorized by this document.** Stage B may begin only after
explicit Gate A.2 approval. Approval of this contract does not authorize Stage C,
Stage D, behaviour changes, commit, or deployment.
