# Phase 3.2 — Sequential Development Task Plan

**Version:** 0.1
**Date:** 2026-11-15
**Status:** DRAFT — PLAN ONLY; OWNER ACCEPTANCE REQUIRED BEFORE EACH GATE
**Execution mode:** One step at a time. A step is complete only after its stated evidence is reviewed and explicitly accepted. The next step remains blocked until then.

## 1. Purpose and authority

This plan turns the Phase 3.2 Owner Decision Pack into an ordered sequence of decision, experiment, freeze, and later implementation tasks. It is a work plan, not an approval of the five decision documents and not an authorization to change production code.

The five Owner Decision Pack files are now present in this directory:

1. [01_INPUT_CONTRACT_OWNER_DECISION.md](01_INPUT_CONTRACT_OWNER_DECISION.md)
2. [02_FEATURE_TECHNICAL_DEFINITIONS_AND_ELIGIBILITY.md](02_FEATURE_TECHNICAL_DEFINITIONS_AND_ELIGIBILITY.md)
3. [03_EXPERIMENT_AUTHORIZATION_AND_ACCEPTANCE.md](03_EXPERIMENT_AUTHORIZATION_AND_ACCEPTANCE.md)
4. [04_RUNTIME_CONFIGURATION_DECISIONS.md](04_RUNTIME_CONFIGURATION_DECISIONS.md)
5. [05_TECHNICALLY_ELIGIBLE_CANDIDATE_FREEZE.md](05_TECHNICALLY_ELIGIBLE_CANDIDATE_FREEZE.md)

Supporting evidence includes the [technical decision matrix](PHASE3_2_TECHNICAL_FEATURE_DECISION_MATRIX_v0.1.md), [source evidence](PHASE3_2_FEATURE_SOURCE_EVIDENCE.md), [train/inference parity report](PHASE3_2_TRAIN_INFERENCE_PARITY_REPORT.md), [source reconciliation](PHASE3_2_STAGE_A_SOURCE_RECONCILIATION.md), and [strict specification](PHASE3_2_STRICT_SPEC.md).

All five Owner Decision Pack documents currently remain draft/pending or template/not-frozen. The plan preserves their authorization boundaries:

- Approving input or feature decisions freezes semantics only.
- Experiment execution requires explicit approval of Document 03.
- Candidate freeze does not authorize production implementation.
- Training, artifact writes, deployment, READY activation, and trading behavior changes are outside this plan.
- Production implementation requires a separate, explicit implementation authorization after the final schema and contract scope are ready.

## 2. Sequential acceptance rule

- Only one numbered step may be active at a time.
- Each step must produce the listed evidence and receive explicit owner acceptance in the relevant approval register or written task record.
- “File exists,” “code runs,” or “no issue was noticed” is not acceptance by itself.
- If a gate fails, stop at that step, record the failure, revise only the affected deliverable, and repeat its acceptance. Do not begin downstream work.
- A deferred candidate does not block freezing other candidates that independently pass every prerequisite; it must remain `DEFER` and cannot enter the eligible set.
- Any scope expansion or change to an approved definition returns to the affected decision gate before implementation continues.

## 3. Decision and evidence stages

### Step 0 — Accept this plan and confirm the decision pack

**Purpose:** Agree on the sequential gates and ensure the team is using the same source pack and evidence set.

**Work:** Review this task plan; confirm the five decision files are in this directory; confirm their pending/template statuses and the supporting evidence references. Record repository commit and working-tree status immediately before any later experiment or implementation task. Do not change feature or runtime definitions here.

**Acceptance evidence:** Owner accepts this plan revision and pack inventory; pending decisions remain clearly pending; no draft is represented as approved. Source baseline/working-tree state will be captured again for the specific experiment or implementation task where it matters.

**Gate owner accepts:** This plan and decision-pack inventory.
**Next step:** Step 1 only, after explicit plan acceptance.

### Step 1 — Approve the shared input contract

**Source of truth:** Document 01, with any cross-document decisions reflected in Document 04.

**Work:** Resolve IC-01 through IC-08: target timeframe; candle timestamp open/close convention; UTC normalization; incomplete-candle exclusion; expected cadence and approved calendar exceptions; whole-batch rejection; training/inference parity.

**Acceptance evidence:** Document 01 approval register is filled with concrete values, approver, and date. Invalid-input cases and calendar exceptions are unambiguous. Training and inference use the same stated boundary.

**Gate owner accepts:** Signed/recorded input-contract decisions.
**Stop condition:** If timeframe, timestamp convention, incomplete-candle rule, or calendar behavior remains ambiguous, stop; do not finalize time-based formulas or run dependent experiments.
**Next step:** Step 2 only.

### Step 2 — Approve feature definitions and technical dispositions

**Source of truth:** Document 02, reconciled with the technical matrix and the approved Step 1 input contract.

**Work:** Review all 37 candidate rows. Approve exact names, formulas, input meaning, parameters, units, timeframe mapping, backend/version, warm-up, and invalidity behavior for any candidate proposed as technically eligible. Resolve ATR, RSI, MACD, and ADX parameters/backend details. Mark unresolved Volume and Session candidates `DEFER` unless their source/clock semantics are decided. Do not make predictive-value decisions here.

**Acceptance evidence:** Document 02 decision register is complete; every candidate has an owner-approved disposition and no `ACCEPTABLE AS-IS`/`REDEFINE` entry bypasses the nine-point eligibility gate. Any retained `DEFER` has a specific blocker. ADX break/reseed semantics and horizon-volatility names/formulas match the approved decision.

**Gate owner accepts:** Technical definition/disposition record.
**Stop condition:** Any eligible candidate with an unresolved formula, backend, warm-up, invalidity, or timeframe meaning blocks that candidate; do not silently infer a definition from current source.
**Next step:** Step 3 only.

### Step 3 — Approve and authorize the bounded experiment protocol

**Source of truth:** Document 03, using the exact input and feature decisions accepted in Steps 1–2.

**Work:** Freeze the code identity, fixture identity, dependency/backend identity, comparison procedure, per-feature tolerance, history sequence `200 → 300 → 500 → 800`, longer-history reference for each pair, two required passing pairs, ADX break/reseed fixtures, report format, and stop conditions. Production history length remains a separate `NOT YET APPROVED` decision.

**Acceptance evidence:** Document 03 approval register is complete, including explicit authorization for the bounded offline experiment scope. The protocol distinguishes implementation correctness/parity from history convergence and says no extension beyond 800 without a new preregistered decision.

**Gate owner accepts:** Experiment protocol and execution authorization.
**Stop condition:** No experiment result is inspected before this gate is accepted. This acceptance authorizes only the stated offline experiments, not production implementation or training.
**Next step:** Step 4 only.

### Step 4 — Execute approved offline experiments

**Work:** Run only the fixtures and comparisons approved in Document 03. If a small isolated harness is needed, keep it outside production paths and identify it in the report. Use fixed final candles and raw feature values before scaling/cleaning that is not part of the approved contract. Record results independently for each candidate and each experiment class.

**Acceptance evidence:** Complete per-experiment records include protocol version, commit/dirty status, runtime and dependency identity, fixture/final candle identity, expected and actual values, absolute deltas, reference value, tolerance, and `PASS` / `FAIL` / `NOT RUN` / `BLOCKED` disposition. Every eligible candidate passes applicable formula, validation, parity, warm-up, and convergence checks. Failed or unrun candidates stay deferred.

**Gate owner accepts:** Experiment report and dispositions.
**Stop condition:** Stop on fixture drift, dependency drift, hidden fallback/repair, unexpected partial output, or any need to change a formula/tolerance. Do not improvise; propose a protocol revision and obtain approval first.
**Next step:** Step 5 only.

### Step 5 — Decide runtime configuration, including production history

**Source of truth:** Document 04, informed by accepted Step 4 results.

**Work:** Record runtime values consistently with Document 01 and resolve remaining runtime choices. Do not contradict or silently reopen the accepted input contract. Decide production history length only after evidence review. If it is outside `200, 300, 500, 800`, preregister and obtain approval for its comparison with the 800-bar result before inspecting that comparison. Resolve Volume source/comparability/invalidity and Session intervals/calendar if those candidates are intended to leave `DEFER`. Pin IANA timezone data if Session features are retained.

**Acceptance evidence:** Document 04 approval register contains concrete values or explicitly retained `DEFER` decisions, approver, and date. Production length is either approved with feature-specific support evidence or remains `NOT YET APPROVED`; no claim of production warm-up support is made without the required comparison.

**Gate owner accepts:** Runtime decision record.
**Stop condition:** Document 05 prerequisite 10 requires an approved production history length and support evidence for every candidate being frozen. If production history is not approved, no candidate can be frozen as technically eligible. Unresolved Volume/Session semantics keep those features deferred.
**Next step:** Step 6 only.

### Step 6 — Freeze the technically eligible candidate set

**Source of truth:** Document 05.

**Work:** Populate the candidate register only from approved definitions, accepted experiment reports, and approved runtime settings. Preserve `DEFER`/`EXCLUDE` statuses and reasons. Keep the technically eligible list separate from the final ordered model schema and predictive-value choices.

**Acceptance evidence:** All Document 05 freeze prerequisites and evidence links are satisfied for each candidate marked `TECHNICALLY ELIGIBLE`; owner, date, and evidence bundle identity/hash are recorded. No candidate with an unresolved blocker, failed experiment, or missing production-length support is frozen as eligible. Document 05 explicitly keeps the ordered model input schema and Feature Contract Identity unissued where Phase 3.3 decisions remain.

**Gate owner accepts:** Document 05 freeze record.
**Next step:** Step 7 handoff only.

### Step 7 — Hand off eligible candidates to Phase 3.3

**Work:** Provide only technically eligible candidates and their immutable technical definitions/evidence to the Phase 3.3 predictive-value process. Deferred items remain excluded from that candidate set unless their blockers are later resolved through the same gates.

**Acceptance evidence:** Handoff inventory is acknowledged; Phase 3.3 selects/rejects candidates for predictive value without changing their technical meanings. Record resulting final ordered schema separately.

**Gate owner accepts:** Phase 3.3 handoff record.
**Stop condition:** No final ordered schema or Feature Contract Identity is inferred from the technical freeze alone.
**Next step:** Implementation preparation may be proposed only after the later prerequisite below.

## 4. Later implementation stages — separately authorized

The current decision pack does not authorize these tasks. They are listed to show the eventual engineering sequence, not to start it. Before Step 8, require: approved Phase 3.2 decisions and candidate freeze; completed Phase 3.3 schema decisions where required; a concrete implementation scope; and explicit owner authorization for code changes.

### Step 8 — Approve a concrete implementation task

**Work:** Convert approved contract decisions into a file-by-file implementation proposal, migration/compatibility behavior, rollback boundary, and acceptance tests. Identify production paths that would change and confirm that excluded actions (training, artifacts, deployment, trading behavior) remain excluded unless separately authorized.

**Acceptance evidence:** Owner approves the exact implementation scope and per-step acceptance criteria. No source code changes before approval.

### Step 9 — Implement and accept one engineering layer at a time

Do not combine these into one broad change. Each substep gets its own review and acceptance before the next starts:

1. **Shared candle validation:** Implement approved timestamp/OHLC/cadence/calendar validation; verify whole-batch rejection and no partial feature output.
2. **Pure feature calculations:** Implement only approved, technically eligible formulas with fixed backends, names, parameters, and warm-up behavior; keep deferred features unavailable.
3. **Missing-value and ordered projection:** Apply the approved validity policy and explicit feature order; reject missing/non-finite/wrong-order inputs with named errors.
4. **Training/inference parity adapters:** Route both paths through the shared semantics; verify identical raw vectors and identical invalid-input outcomes before model scaling.
5. **Contract identity serialization:** Specify canonical serialization and compute an identity only after all identity fields and the final ordered schema are approved. Bind metadata without letting artifacts override runtime semantics.
6. **Production wiring:** Treat as a separate final task requiring explicit authorization and its own deployment/operational review. This plan does not authorize activation, training, artifact writes, deployment, READY wiring, or trading changes.

For each substep, acceptance requires the approved specification's exact outputs, explicit failure behavior, and reproducible verification evidence. A failed substep blocks every later substep.

## 5. Current state and immediate next action

- The Owner Decision Pack is extracted into `docs/phase3_2/` from the repository-root archive `phase3_2_owner_decision_pack.zip`.
- Documents 01–04 remain pending owner decisions/authorization; Document 05 remains a not-frozen template.
- The 37-candidate matrix and existing Phase 3.2 evidence are design inputs, not implementation authorization.
- No experiment, source change, model training, artifact write, deployment, or runtime/trading change is performed by this plan.

**Immediate next action:** Owner reviews and accepts this plan (Step 0). After that gate is accepted, complete Step 1 in Document 01; Step 2 remains blocked until Step 1 is explicitly accepted.

## 6. Plan acceptance record

| Field | Value |
|---|---|
| Plan accepted by | PENDING |
| Acceptance date | PENDING |
| Approved plan revision | PENDING |
| Notes / required edits | PENDING |
