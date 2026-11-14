# 【Strict Spec】Phase 3.1 Stage A.3 — Prediction Contract Reconciliation

**Priority:** P0
**Target Repository:** `/Users/liqin/projects/ai_training_cnn`
**Target Branch:** `v2026c`
**Target File:** `docs/PHASE3_1_CONTRACT_A3.md`
**Task Type:** Documentation-only contract reconciliation
**Authorization:** Stage A.3 only. No Python changes, no Stage B implementation, no commit, no deployment.

---

## 0. Mission

Reconcile the current Phase 3.1 Prediction Contract with the completed live-host Class Definition (CD) evidence and the explicit authoritative decision:

> **CD-OPEN-1: Accept `SELL = not-UP`, not `SELL = DOWN`.**

The current contract contains semantic inconsistencies that must be corrected before Stage B can be specified safely.

Stage A.3 must produce one internally consistent, authoritative `docs/PHASE3_1_CONTRACT.md`.

This is a focused contract-reconciliation task, not another broad audit.

**Do not restart CD evidence acquisition. Do not retrain the model. Do not revisit the accepted `SELL = not-UP` decision. Do not silently upgrade partial evidence to full evidence.**

Stage A.3 does not authorize implementation or activation.

### Required outcome

At completion:

1. The contract uses `UP / not-UP` semantics consistently.
2. The exact artifact-specific CD decision and its evidence limitations are recorded accurately.
3. No field or probability is given a meaning that the evidence does not support.
4. The READY requirements are explicit and implementable.
5. The Decision Register and test matrix contain no unresolved contradictions.
6. Stage B can be designed from the reconciled contract without having to reinterpret its semantics.

---

## 1. Source of truth and precedence

Use these materials as the task's authoritative inputs:

| Source                                                            | Role                                                                                 |
| ----------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| Current `docs/PHASE3_1_CONTRACT.md`                             | Existing contract; preserve valid decisions and content                              |
| CD Evidence Record, including Live Host Evidence dated 2026-11-14 | Artifact fingerprint, runtime probe, training-target semantics, evidence limitations |
| Stage A Strict Spec v2                                            | Original scope, layer boundaries, non-goals and acceptance philosophy                |
| Explicit CD-OPEN-1 decision                                       | Authoritative operational definition: `SELL = not-UP`                              |

### Precedence rules

1. The explicit decision `SELL = not-UP` is authoritative for the operational direction semantics.
2. The exact-artifact live-host evidence is authoritative for what was actually observed.
3. The existing contract remains authoritative for all unrelated accepted decisions unless a direct contradiction is identified.
4. Where evidence is incomplete, preserve the limitation as `PARTIAL`, `NOT VERIFIED`, or `OPEN` as appropriate.
5. Do not infer additional facts from general ML conventions.

Do not use this task to change accepted Phase 3.0 decisions or unrelated Phase 3.1 design decisions.

---

## 2. Execution preflight

Before editing:

1. Confirm repository root and branch.
2. Record `git rev-parse HEAD`.
3. Record `git status --short`.
4. Confirm `docs/PHASE3_1_CONTRACT.md` exists.
5. Read the current contract and the CD Evidence Record.
6. Identify pre-existing modifications and untracked files.

Preservation rules:

- Do not reset, checkout, rebase, stash, clean, or discard existing work.
- Do not overwrite unrelated changes.
- Do not modify `docs/Development_plan.md`.
- Do not modify any file other than `docs/PHASE3_1_CONTRACT.md`.
- If the target repository or branch is wrong, stop and report.
- If the contract has changed since the declared baseline, reconcile against the actual current file; do not replace it with an older generated copy.

Record the actual preflight state in the completion report.

---

## 3. P0 — Resolve the UP / DOWN semantic contradiction

### 3.1 Correct the CD definition

The current contract describes CD as evidence needed to interpret output as `UP/DOWN`.

This is incorrect for the verified model's target semantics.

The two training paths examined define:

- Label `1`: `future_return > threshold`, meaning `UP`.
- Label `0`: the complement of that condition, meaning `not-UP`.
- Label `0` does not mean exclusively `DOWN`. It includes flat, small positive, and negative outcomes that do not exceed the applicable threshold.

The contract must consistently use:

- `UP`
- `not-UP`

It must not describe the model as a genuine UP/DOWN classifier.

Update all relevant sections, including:

- CD definition;
- CD evidence requirements;
- READY requirements;
- direction derivation;
- probability semantics;
- legal and illegal state combinations;
- Decision Register;
- test matrix;
- current verification status;
- deferred/open items.

Search the complete contract for remaining statements that incorrectly equate `not-UP` with `DOWN`.

### 3.2 Record the authoritative operational decision

Include an explicit decision entry:

**CD-OPEN-1 — RESOLVED**

- Authoritative decision date: 2026-11-14.
- Accepted operational semantics: `SELL = not-UP`.
- `BUY` represents the verified UP class.
- `SELL` represents the complementary not-UP class.
- `SELL` must not be described as a prediction that the market will necessarily fall.

Do not reinterpret this decision as a claim that the model predicts three distinct outcomes or that label `0` means DOWN.

### 3.3 Direction rule

The contract must state the direction rule precisely:

```text
p_up = probability assigned to the verified UP class

direction =
    BUY  if p_up > 0.5
    SELL if p_up <= 0.5
```

The tie rule is strict and must remain consistent with the existing accepted contract decision:

- `p_up > 0.5` → BUY
- `p_up == 0.5` → SELL
- `p_up < 0.5` → SELL

The meaning of SELL is `not-UP`, not `DOWN`.

Do not change the threshold, introduce a neutral band, or create a new abstention rule.

---

## 4. P0 — Reconcile the six CD evidence requirements

The contract currently requires six evidence elements. The live-host evidence record reports:

| # | Evidence element                                          | Live-host evidence                                                                                                               | Required treatment                                                                 |
| - | --------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| 1 | Exact artifact SHA-256                                    | Available for the exact `trade_model_xgb.json`                                                                                 | PASS                                                                               |
| 2 | Actual `classes_` values and order                      | Runtime `[0, 1]`; XGBoost 2.0.3 synthesizes this property as `np.arange(n_classes_)`; JSON does not store the original array | PARTIAL, explicitly qualified                                                      |
| 3 | Positive-class index and `predict_proba` column mapping | Index 1; column 1 corresponds to the selected positive-class probability                                                         | PASS                                                                               |
| 4 | Training-target semantics                                 | Label 1 = UP; label 0 = not-UP; authoritative decision accepts SELL = not-UP                                                     | PASS under the accepted operational definition                                     |
| 5 | Binary complementary/exhaustive output semantics          | `binary:logistic`, two output columns, observed sum = 1                                                                        | PASS for the verified binary output                                                |
| 6 | Reproducible evidence provenance                          | Live-host, artifact fingerprint, runtime, source references and reproduction procedure recorded                                  | PASS as documented in the evidence record, with producer-route limitation retained |

### 4.1 Do not falsify requirement #2

The evidence establishes:

- The loaded runtime exposes `classes_ = [0, 1]`.
- In XGBoost 2.0.3, this is a library-generated property.
- The model JSON does not serialize the original training `classes_` array.
- The runtime positive-class index and `predict_proba` column mapping were observed.

The contract must distinguish:

1. **Runtime effective class order:** observed and reproducible.
2. **Original training class array stored inside the artifact:** not available; the artifact does not contain it.

Do not claim that the original training `classes_` array was recovered from the JSON.

Do not claim that requirement #2 is an unqualified PASS.

Do not automatically conclude that CD must revert to NOT VERIFIED merely because the artifact does not serialize this property. Evaluate the requirement according to the actual contract wording and the evidence available.

The contract must explain why the runtime class order, XGBoost binary objective, output-column mapping and training-label evidence are sufficient—or insufficient—for the operational CD decision.

If the existing requirement is ambiguous, rewrite it to distinguish runtime class-order verification from artifact-serialized class metadata.

### 4.2 Requirement #4 must use the accepted semantics

Replace the old requirement:

> Prove which label means UP and which label means DOWN.

With a requirement that accurately describes this model:

> Prove which class means UP and which class means not-UP, and document the operational interpretation of the complementary class.

Do not claim that the model has a DOWN class.

### 4.3 Requirement #6 — preserve the provenance limitation

The evidence record states that the exact artifact-producing route cannot be pinned to a particular committed script version.

It also identifies two candidate training paths whose target semantics agree.

The contract must preserve this distinction:

- Reproduction of the live artifact probe is documented.
- The artifact fingerprint is available.
- Candidate training-source semantics are available and directionally consistent.
- The exact committed producer script/version for this artifact is not conclusively established.

Do not rewrite this as proof that the exact training run was reproduced from its original source commit.

If this limitation does not invalidate the operational CD decision, explain why and record the residual provenance limitation separately.

### 4.4 CD verdict

Preserve the explicit live-host decision:

**`CD = VERIFIED` for the exact artifact fingerprint recorded in the CD Evidence Record, under the accepted operational definition `SELL = not-UP`.**

The contract must state the scope of that verdict and its limitations.

It must not imply:

- every artifact in the repository has verified CD;
- future retrained models inherit this verification;
- another model hash automatically inherits this verification;
- the original training `classes_` array was recovered from the JSON;
- the artifact's exact producer commit was conclusively identified;
- READY activation or Stage B implementation has been authorized.

CD verification is artifact-specific.

A different model artifact hash requires its own CD verification.

---

## 5. P0 — Correct probability and field semantics

### 5.1 `raw_probability`

Keep `raw_probability` as the neutral inference output.

It must not silently become `p_up` before the class interpretation is verified.

For the verified artifact, document that the runtime output selected by positive-class index 1 corresponds to the UP class under the accepted CD evidence.

### 5.2 `positive_class_label`

The contract must distinguish a raw class label from its semantic meaning.

For this artifact:

```text
positive_class_label = 1
positive_class_semantics = UP
```

The numeric class label `1` is not itself the string `"UP"`.

Requirements:

- Never use a guessed default such as `positive_class_label="UP"`.
- Never substitute a semantic name for the actual class label.
- The field must represent the actual runtime class value.
- The contract must define an appropriate type for a class label that may be numeric or string-valued; do not incorrectly restrict it to `Optional[str]`.
- Semantic interpretation must come from the artifact-specific CD evidence, not from the label's textual appearance.

Do not introduce an implementation or modify Python typing in this stage.

### 5.3 `p_down` versus `p_not_up`

The current field name `p_down` is semantically misleading.

The verified complement is:

```text
p_not_up = 1.0 - p_up
```

It is not:

```text
p_down = probability of an actual downward market move
```

Stage A.3 must make the following contract decision:

1. `p_down` must not be populated or presented as the probability of DOWN.
2. The semantic complement of `p_up` is `p_not_up`.
3. The contract may describe `p_not_up = 1 - p_up` because the exact artifact's binary output is verified as complementary.
4. Do not introduce a new runtime field or modify an API in Stage A.3.
5. If the existing `p_down` field is retained for compatibility in the conceptual schema, explicitly mark it as deprecated/reserved and state that it must remain `None` until a separately approved interface migration. It must never carry `p_not_up` under a misleading name.

The contract must clearly separate semantic correctness from future API compatibility decisions.

### 5.4 Probability units and validity

Preserve the existing canonical probability unit:

- 0–1, not percent.
- Reject NaN.
- Reject positive and negative infinity.
- Reject values outside `[0, 1]`.
- Do not infer units from numeric magnitude.
- Do not change MC cache units or MC scoring.

Do not alter existing unit-conversion decisions unrelated to this reconciliation.

---

## 6. P0 — READY requirements after CD verification

The contract must make the following distinction explicit:

- `ModelStatus.READY` means model initialization permits inference.
- `CD = VERIFIED` means the exact artifact's class semantics have been verified.
- `PredictionStatus.READY` means a particular inference attempt completed and produced a valid, interpretable directional prediction.

These are three separate conditions.

### READY requirements

`PredictionStatus.READY` requires all of the following:

1. Model is usable for inference.
2. Inference completed successfully.
3. Output structure and probability extraction are valid.
4. Probability is finite and within `[0,1]`.
5. The exact model artifact hash matches the CD verification record.
6. The class-to-output-column mapping is established.
7. The positive class is verified as UP.
8. The complementary class is interpreted as not-UP, not DOWN.
9. Direction follows the accepted strict tie rule.
10. No unverified class label or semantic default is used.

If any required condition is not met, READY is illegal.

### `UNINTERPRETABLE`

Preserve the existing rule:

Successful inference + valid raw probability + CD not verified for the exact artifact:

```text
status            = UNINTERPRETABLE
reason            = CLASS_DEFINITION_UNVERIFIED
raw_probability   = valid numeric value
p_up              = None
p_down            = None
direction         = NONE or None
```

Do not use `UNINTERPRETABLE` for unavailable, invalid, execution-error or Decision-layer outcomes.

### Artifact mismatch

If a CD verification record exists but its artifact hash does not match the currently loaded model:

- Do not reuse the old verification.
- Do not produce READY on the basis of the old record.
- Classify the outcome using the existing status/reason semantics.
- State explicitly that artifact-specific CD verification is absent for the current artifact.

Do not invent a new status unless the existing enum genuinely cannot express the case. If a new status appears necessary, STOP and report the proposed change rather than silently expanding the enum.

---

## 7. P0 — CD-OPEN-4 disposition

The CD Evidence Record identifies:

**CD-OPEN-4:** pre-activation hardening for guessed `positive_class_label="UP"` and unconditional `p_down = 1 - p_up`.

Stage A.3 must update this item carefully.

Required disposition:

- The semantic contract defects are resolved in documentation by Sections 3–5 of this task.
- The actual Python implementation is not modified.
- The existence of the old implementation pattern must not be treated as proof that the runtime implementation is already compliant.
- Any implementation hardening required before activation remains an implementation prerequisite.
- CD-OPEN-4 must not be marked fully implementation-resolved merely because the documentation was corrected.

Record separately:

1. Contract-level semantic resolution.
2. Runtime implementation verification status.
3. Required Stage B implementation constraints.
4. Any remaining pre-activation condition.

Do not claim that the guessed default or unconditional complement has been removed from the code.

---

## 8. Update the Decision Register

Review all existing decisions D-1 through D-22.

Preserve unrelated decisions.

Add or revise entries as necessary so the following questions are explicitly resolved:

| ID     | Question                                                        | Required outcome                                                                        |
| ------ | --------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| CD-D1  | Is the model a UP/DOWN classifier?                              | No. It is UP/not-UP under the accepted target semantics.                                |
| CD-D2  | What does label 0 mean?                                         | not-UP, not DOWN.                                                                       |
| CD-D3  | What does SELL mean?                                            | not-UP.                                                                                 |
| CD-D4  | What is the complement of `p_up`?                             | `p_not_up`, not a genuine DOWN probability.                                           |
| CD-D5  | Can `p_down` carry the complement?                            | No. It must not be semantically mislabeled.                                             |
| CD-D6  | Is the original `classes_` array stored in the JSON artifact? | No. XGBoost 2.0.3 synthesizes the runtime property.                                     |
| CD-D7  | Is runtime class order observed?                                | Yes, `[0,1]`, with the evidence qualification recorded.                               |
| CD-D8  | Is CD verified for the exact artifact?                          | Yes, under the explicit accepted operational definition; preserve evidence limitations. |
| CD-D9  | Does CD verification authorize Stage B or READY activation?     | No. Separate approval is required.                                                      |
| CD-D10 | Does the verification transfer to future artifacts?             | No. Verification is hash-specific.                                                      |
| CD-D11 | Is CD-OPEN-4 implementation-resolved?                           | No. Documentation resolution does not prove code hardening.                             |

Use the existing Decision Register format if possible. Avoid creating a second, competing register.

Every decision must include a concise rationale and, where relevant, an evidence reference.

No decision may silently override an existing accepted decision outside the scope of this task.

---

## 9. Update the test matrix

This is a documentation task. Do not implement tests.

The contract's test matrix must include explicit future acceptance cases for:

| Test   | Scenario                                                       | Expected result                                                 |
| ------ | -------------------------------------------------------------- | --------------------------------------------------------------- |
| CD-T01 | Exact artifact hash matches verified CD record                 | CD evidence may be used for that artifact                       |
| CD-T02 | Artifact hash differs from verified record                     | Existing CD verification must not be reused                     |
| CD-T03 | Runtime class order is `[0,1]`                               | Record actual runtime values; do not claim JSON serialized them |
| CD-T04 | Positive-class index is 1 and output column 1 is selected      | Raw output maps to the verified UP class                        |
| CD-T05 | Label 0 is interpreted                                         | not-UP, never DOWN                                              |
| CD-T06 | `p_up = 0.73`                                                | `p_not_up = 0.27`; no claim of a 27% DOWN probability         |
| CD-T07 | `p_up = 0.50`                                                | Direction SELL under the accepted tie rule                      |
| CD-T08 | `p_up = 0.49`                                                | Direction SELL                                                  |
| CD-T09 | `p_up = 0.51`                                                | Direction BUY                                                   |
| CD-T10 | `positive_class_label` is not captured                       | Do not invent `"UP"`                                          |
| CD-T11 | `p_down` is requested                                        | Do not populate it with `1 - p_up` under a DOWN meaning       |
| CD-T12 | Successful inference but CD is not verified for the exact hash | UNINTERPRETABLE; no direction                                   |
| CD-T13 | READY with artifact mismatch                                   | Rejected as illegal                                             |
| CD-T14 | Model initialization READY but prediction invalid              | Prediction must not be READY                                    |
| CD-T15 | MC filter BLOCK after valid prediction                         | Prediction remains READY; Decision is rejected separately       |

Retain all valid existing tests T-01 onward. Avoid duplicate test IDs. Renumber only if strictly necessary and update every cross-reference.

Each test must state whether it is:

- data-only;
- structural/unit;
- stub-based;
- dependency-gated;
- integration-level.

Do not claim tests were executed.

---

## 10. Explicitly frozen boundaries

The following are not authorized by Stage A.3:

- Any `.py` file modification.
- `data_pipeline.py` changes.
- `strategy_decision.py` changes.
- `fx_trade_bot.py` changes.
- `fx_trade_bot_ml.py` changes.
- `ModelWrapper` or XGBoost loading changes.
- Training target changes.
- Model retraining.
- Artifact regeneration or replacement.
- Feature engineering.
- Feature contract redesign.
- Probability calibration.
- ML threshold changes.
- MC cache changes.
- MC scoring changes.
- Strength scoring changes.
- `FINAL` weight changes.
- Entry Authorization changes.
- Exit logic changes.
- SL/TP changes.
- Position sizing changes.
- OANDA order flow changes.
- Scheduler changes.
- Phase 3.2–3.6 implementation.
- `docs/Development_plan.md` changes.
- Commit.
- Deployment.

**Entry Authorization remains unchanged and unresolved.**

No behavior-changing implementation is authorized.

---

## 11. Acceptance criteria — all mandatory

Stage A.3 is complete only when every criterion below passes.

### A. Contract consistency

| ID    | Acceptance criterion                                                                          |
| ----- | --------------------------------------------------------------------------------------------- |
| A3-01 | The contract defines the model semantics as UP/not-UP, not UP/DOWN.                           |
| A3-02 | Every relevant reference to DOWN is reviewed and corrected where it incorrectly means not-UP. |
| A3-03 | The explicit CD-OPEN-1 decision `SELL = not-UP` is recorded as authoritative and resolved.  |
| A3-04 | The direction rule is exactly BUY when `p_up > 0.5`, otherwise SELL.                        |
| A3-05 | The tie case `p_up == 0.5` remains SELL.                                                    |
| A3-06 | SELL is never described as proof or probability of an actual downward market move.            |

### B. CD evidence integrity

| ID    | Acceptance criterion                                                                                             |
| ----- | ---------------------------------------------------------------------------------------------------------------- |
| A3-07 | The exact artifact SHA-256 is bound to the CD verdict.                                                           |
| A3-08 | Runtime `classes_=[0,1]` is recorded accurately.                                                               |
| A3-09 | The contract explicitly says XGBoost 2.0.3 synthesizes `classes_`; the JSON does not store the original array. |
| A3-10 | Evidence requirement #2 is not silently upgraded from PARTIAL to unqualified PASS.                               |
| A3-11 | The contract distinguishes runtime class order from artifact-serialized training class metadata.                 |
| A3-12 | Evidence requirement #4 uses UP/not-UP semantics.                                                                |
| A3-13 | The exact producer-script/commit limitation is retained.                                                         |
| A3-14 | CD is recorded as VERIFIED only within the exact artifact and accepted operational definition.                   |
| A3-15 | No future artifact inherits this CD verdict automatically.                                                       |

### C. Field and probability semantics

| ID    | Acceptance criterion                                                                       |
| ----- | ------------------------------------------------------------------------------------------ |
| A3-16 | `raw_probability` remains semantically neutral until CD permits interpretation.          |
| A3-17 | `positive_class_label` represents the actual class value, not a guessed semantic string. |
| A3-18 | The contract forbids a guessed default such as `"UP"`.                                   |
| A3-19 | The conceptual type of `positive_class_label` can represent numeric labels.              |
| A3-20 | The complement is identified as `p_not_up`, not a genuine `p_down`.                    |
| A3-21 | `p_down` is not populated with the not-UP complement under a misleading name.            |
| A3-22 | No runtime API or field migration is implemented in Stage A.3.                             |
| A3-23 | Probability range, finite-number and unit rules remain intact.                             |

### D. Status and activation semantics

| ID    | Acceptance criterion                                                                                 |
| ----- | ---------------------------------------------------------------------------------------------------- |
| A3-24 | READY requires exact artifact-hash matching and all required CD evidence.                            |
| A3-25 | ModelStatus READY is not conflated with PredictionStatus READY.                                      |
| A3-26 | UNINTERPRETABLE remains restricted to successful inference with valid probability and unverified CD. |
| A3-27 | Artifact mismatch cannot reuse an old CD verification.                                               |
| A3-28 | CD verification does not authorize Stage B, READY activation or trading behavior changes.            |
| A3-29 | CD-OPEN-4 distinguishes documentation resolution from implementation resolution.                     |

### E. Decision Register and tests

| ID    | Acceptance criterion                                                                                |
| ----- | --------------------------------------------------------------------------------------------------- |
| A3-30 | Existing D-1 through D-22 decisions are reviewed and preserved unless directly affected.            |
| A3-31 | CD-D1 through CD-D11 are resolved or mapped into the existing register without duplicate authority. |
| A3-32 | CD-T01 through CD-T15 are included or mapped to equivalent existing tests.                          |
| A3-33 | No duplicate test IDs or broken cross-references remain.                                            |
| A3-34 | Test execution is not claimed when only test requirements have been documented.                     |

### F. Scope and repository integrity

| ID    | Acceptance criterion                                                                                   |
| ----- | ------------------------------------------------------------------------------------------------------ |
| A3-35 | Only `docs/PHASE3_1_CONTRACT.md` is modified.                                                        |
| A3-36 | No `.py` file is modified.                                                                           |
| A3-37 | `docs/Development_plan.md` remains untouched.                                                        |
| A3-38 | All pre-existing unrelated modifications and untracked files are preserved.                            |
| A3-39 | No commit is created.                                                                                  |
| A3-40 | No deployment is performed.                                                                            |
| A3-41 | The exact statement **"Entry Authorization remains unchanged and unresolved."** remains present. |
| A3-42 | The contract explicitly states that Stage B requires separate approval.                                |

**Any failed mandatory criterion means Stage A.3 is NOT COMPLETE.**

Do not declare completion with a list of unresolved contradictions.

---

## 12. Required completion report

Return one concise but evidence-based report with:

### 12.1 Repository integrity

- Repository root.
- Branch.
- HEAD before and after.
- `git status --short` before and after.
- Exact modified-file list.
- Confirmation that only `docs/PHASE3_1_CONTRACT.md` changed.
- Diff evidence showing no `.py` modification.
- Confirmation of no commit and no deployment.

### 12.2 Contract changes

List the exact sections changed and summarize each change.

At minimum:

- CD definition.
- UP/not-UP semantics.
- Six evidence requirements.
- READY requirements.
- `positive_class_label`.
- `p_down` / `p_not_up`.
- CD-OPEN-4.
- Decision Register.
- Test matrix.
- Phase status.

### 12.3 CD evidence disposition

Provide a final table for requirements #1–#6 with:

- evidence;
- status;
- qualification or limitation;
- contract section where recorded.

Do not hide PARTIAL evidence.

### 12.4 Acceptance results

Provide A3-01 through A3-42 as PASS/FAIL with concise evidence.

If any criterion fails, state:

**Stage A.3 Status: NOT COMPLETE**

Do not claim success based on partial completion.

### 12.5 Remaining issues

Separate:

- resolved contract issues;
- unresolved implementation issues;
- remaining evidence limitations;
- issues requiring separate approval.

Do not create new workstreams unless necessary to prevent a false contract assertion.

---

## 13. Stop conditions

Stop and report without guessing if:

1. The current contract or CD Evidence Record contradicts the stated authoritative decision in a way that cannot be reconciled without changing that decision.
2. The exact artifact fingerprint cannot be established from the supplied evidence.
3. The evidence does not support the claimed probability-column mapping.
4. A proposed change would alter the existing Prediction/Decision/Authorization boundary.
5. Completing the task would require a Python modification or an unauthorized behavior change.
6. An unrelated pre-existing modification would be overwritten or lost.

Do not solve a stop condition by inventing evidence, changing the training target, or weakening the acceptance criteria.

---

## 14. Final authorization boundary

Stage A.3 is a documentation reconciliation task only.

Its successful completion means:

- The Prediction Contract is internally consistent.
- The exact artifact's CD evidence and limitations are represented accurately.
- The semantic basis for a future Prediction Adapter is explicit.
- The future implementation requirements are testable.

It does **not** mean:

- Stage B has started.
- A Prediction Adapter exists.
- Runtime code has been hardened.
- READY has been activated.
- ML voting has changed.
- Entry Authorization has changed.
- Live trading behavior has changed.

**Stage A.3 completion is not Stage B authorization.**

Stop after delivering the reconciled contract and the completion report. Wait for explicit approval before proceeding.
