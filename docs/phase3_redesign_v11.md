
# Claude Review Request — PHASE3_REDESIGN.md v1.1

## Role

Act as an independent senior ML systems architect and trading-system reliability reviewer.

Review `PHASE3_REDESIGN.md v1.1` against the original `AUDIT_PHASE3.md` and the actual repository source.

This is a **design validation review**, not an implementation task.

Do not modify code or documents.

## Primary objective

Determine whether v1.1 is sufficiently complete, internally consistent, technically sound, and safely sequenced to authorize a separately scoped Phase 3.0 implementation task.

The goal is to close material design gaps, not to create another endless audit cycle.

## Review rules

1. Inspect the actual repository and cite exact files, functions, and line ranges for source-based claims.
2. Separate:
   - Confirmed source facts.
   - Runtime facts.
   - Design concerns.
   - Hypotheses.
   - Items that cannot be verified.
3. Do not invent repository behavior.
4. Do not recommend wholesale replacement when a bounded repair is sufficient.
5. Do not expand scope into unrelated execution or risk-management refactors.
6. Do not recommend waiting several days without defining what will be measured, what decision the measurement supports, and what action follows.
7. Do not propose changes to live behavior without identifying the exact behavior and approval boundary.
8. Do not repeat findings already adequately addressed in v1.1 unless the proposed solution is technically insufficient.
9. Do not treat more logging as a substitute for fixing a known correctness defect.
10. Do not require another audit phase if the required evidence can be collected within a bounded Phase 3.0 task.

## Review checklist

### A. Document integrity

- Are all decisions correctly marked PROPOSED?
- Are PD identifiers distinct from audit finding identifiers?
- Are any sections contradictory?
- Is the relationship with `docs/Development_plan.md` correctly represented?
- Are any requirements impossible to test or too vague to implement?

### B. Runtime failure isolation

Inspect the actual call sequence around `main()`, `ensure_model()`, and subsequent position-management/exit logic.

Determine:

- Can model initialization failure abort the run?
- What is the smallest safe exception boundary?
- Can independent exits and position management continue?
- Are there other model-dependent branches that can still prevent exit execution?
- Does T1/T23 cover the actual failure paths?

Do not merely recommend wrapping the entire trading run in a broad exception handler.

### C. Abstention and decision semantics

Inspect every relevant `generate_signal()` consumer and the actual score calculation.

Determine:

- Does `None` have multiple meanings?
- Is the proposed prediction contract sufficient?
- Is the O10 fail-closed policy internally consistent?
- Does it accidentally block unrelated position management?
- Are the distinction between runtime abstention, model unavailability, and no demonstrated predictive value correctly represented?
- Is there any remaining path that fabricates a directional or neutral vote?

If the abstention policy has an operational problem, propose the smallest evidence-based correction.

### D. MC unit isolation

Trace every consumer of the shared MC cache, especially:

- Weighted scoring.
- TP thresholds.
- Fib-related logic.
- Any other consumer found in source.

Determine whether the adapter boundary in v1.1 is sufficient to prevent a unit fix from silently changing legacy behavior.

Identify any unlisted consumer that must be included in T25.

### E. Feature and model compatibility

Inspect the actual training and inference feature paths.

Determine:

- Whether one canonical feature implementation is practical.
- Whether pandas_ta/fallback divergence is real.
- Whether the proposed feature contract covers all compatibility dimensions.
- Whether training and inference use compatible history lengths.
- Whether warm-up and missing-value rules are enforceable.
- Whether the model can be accidentally loaded for an incompatible timeframe.
- Whether the release pairing requirement prevents old-model/new-feature combinations.

### F. Evaluation validity

Inspect the actual dataset construction, label generation, splitting, scaling, and evaluation code.

Determine whether v1.1 adequately prevents:

- Cross-instrument temporal leakage.
- Scaler leakage.
- Label-window overlap.
- Pair identity proxy effects.
- Final holdout contamination.
- Misleading pooled performance.
- Overconfident confidence intervals due to overlapping labels.

Assess whether the synchronized block-bootstrap proposal is technically appropriate. If not, propose a specific alternative.

Do not add evaluation metrics without explaining what decision each metric supports.

### G. Artifact lifecycle

Inspect the actual save/load paths and runtime retraining triggers.

Determine:

- Whether all artifact writes are covered.
- Whether model/scaler/manifest promotion can be atomic.
- Whether cross-host identity is sufficient.
- Whether profile compatibility is represented correctly.
- Whether legacy fallback paths can bypass approval.
- Whether runtime can still train or mutate an artifact through an indirect path.

### H. Audit traceability

Review the mapping for F1–F13, N1–N12, and D1–D9.

Identify:

- Any material finding without an owner or phase.
- Any phase that does not actually address its assigned finding.
- Any execution-risk finding incorrectly mixed into the ML workstream.
- Any unnecessary scope expansion.

### I. Phase sequence and implementation readiness

Determine whether the proposed sequence is executable:

3.0 Runtime containment and observability
3.1 Decision contract and early shadow
3.2 Canonical feature contract
3.3 Evaluation redesign
3.4 Artifact lifecycle
3.5 Integrated shadow
3.6 Controlled activation

In particular, identify whether Phase 3.0 can be implemented safely without first resolving any open design decision.

## Required output

Produce one concise but technically substantive report:

### 1. Verdict

Choose exactly one:

- APPROVE FOR PHASE 3.0 TASK DESIGN
- APPROVE WITH SPECIFIC CORRECTIONS
- NOT READY — MATERIAL DESIGN GAP

### 2. Material blockers

Only list issues that could cause:

- Incorrect decisions.
- Failure to manage existing positions.
- Invalid evaluation conclusions.
- Incompatible model/feature artifacts.
- Unauthorized live behavior changes.

For each issue provide:

- Evidence.
- Exact location.
- Consequence.
- Smallest correction.
- Whether it blocks Phase 3.0 or a later phase.

### 3. Non-blocking improvements

List only improvements that are genuinely useful. Do not turn preferences into blockers.

### 4. Audit traceability exceptions

List any material audit findings not adequately mapped or addressed.

### 5. Phase 3.0 readiness

State whether a bounded Phase 3.0 task can now be written.

If yes, specify its exact scope and acceptance criteria.

If no, identify the minimum design correction required.

### 6. Final change list

Provide a short, prioritized list of changes to v1.1, if any.

Do not rewrite the whole document.

## Important constraint

Do not recommend another broad audit simply because some implementation details remain unknown.

If a detail can be verified by a bounded source inspection inside Phase 3.0, identify it as a Phase 3.0 verification item rather than a design blocker.

The intended outcome is a stable design that can move into controlled implementation—not another cycle of open-ended analysis.
