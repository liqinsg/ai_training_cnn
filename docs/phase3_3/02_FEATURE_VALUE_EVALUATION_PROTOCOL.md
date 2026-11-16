# Phase 3.3 — Feature Value Evaluation Protocol

**Document ID:** `PHASE3_3_FEATURE_VALUE_EVALUATION_PROTOCOL`
**Date:** 2026-11-16
**Status:** DRAFT — **not yet authorized for execution**. Execution requires its own owner authorization (see §15). Being in Phase 3.3 does **not** grant training, artifact, or wiring rights.
**Applies to:** the 33 `TECHNICALLY ELIGIBLE` candidates in `01_FEATURE_CANDIDATE_REGISTER.md`.

---

## 1. Purpose

Define **how the predictive value** of each eligible candidate is evaluated, so that the question "which features earn a place in the final model?" is answered by a preregistered, leakage-controlled, cost-aware procedure rather than by exploratory correlation.

Technical correctness (Phase 3.2, done) is a **precondition**, not evidence of predictive value.

## 2. Preregistration discipline

- No result may be inspected before inputs, split definitions, metrics, tolerances, trial budget and acceptance rules are frozen.
- Tolerances and hypotheses must not be relaxed after seeing results.
- Each feature is reported **individually**; no aggregate score may hide a weak or unstable feature.

## 3. Data and universe

- **Timeframe:** M15; timestamp semantics **candle-OPEN** (IC-02 / RC-03); no look-ahead.
- **History:** production length **800 bars** (RC-02); a feature's warm-up must be satisfied at that length.
- **Universe:** instrument set to be preregistered (OANDA-native names, e.g. `EUR_USD`). Instrument selection must be fixed before evaluation.
- **Calendar:** gaps/closed periods follow `PHASE3_2_CALENDAR_CONTRACT` (v0.2, fail-closed). No synthetic filling across unexplained gaps.
- **Target:** the prediction target (horizon, direction/triple-barrier, class balance) must be preregistered and held fixed across all candidates being compared.

## 4. Validation design

| Element | Requirement |
|---|---|
| Split type | time-series (chronological) only; never random shuffle |
| Scheme | walk-forward with expanding/rolling train, fixed test windows |
| **purge / embargo** | mandatory gap between train and test equal to the **label horizon** (purge) plus an **embargo** buffer, so no train label window overlaps a test window. The label horizon is **6 bars** (M15; `target_horizon = 6`): each label at *t* spans [*t*, *t*+6], so the purge must be **≥ 6 bars**, plus the embargo buffer. |
| Fold-local preprocessing | any scaling/encoding fit **only** on the train fold; never on the test fold |
| Final holdout | one untouched, never-inspected tail segment reserved for confirmation |
| Cross-instrument isolation | at a shared timestamp, train and test must not mix instruments whose label windows overlap |

## 5. Leakage controls (registered risk R3)

Before any run, confirm each item; a "no" is a stop condition (§13):

1. Feature at time *t* uses only data with timestamp ≤ *t* (no future bars).
2. Label windows never overlap across the train/test boundary (purge enforced).
3. Same-timestamp cross-instrument correlation is isolated (no leakage via a shared bar).
4. No target-derived statistics (e.g. target mean) leak into preprocessing.
5. Preprocessing is fold-local.
6. Any resampling/alignment is causal.
7. The holdout segment is inspected **once**, at the end.

> Rationale: Phase 3.2's technical correctness can be invalidated by a leaky Phase 3.3 experiment. Correct feature construction (P1/P2) does **not** imply leak-free evaluation.

## 6. Baselines

Every candidate is measured **incrementally** against, at minimum:

- **B0** — trivial baseline (persistence / majority class / random with correct prior).
- **B1** — the all-candidates reference model (with the candidate removed → ablation).
- **B2** — where relevant, simple single-feature baselines.

A feature has predictive value only if it improves a stated metric over the relevant baseline **out-of-time**, within cost.

## 7. Methods

| Method | Purpose |
|---|---|
| Univariate association (Spearman / rank IC) | screening only; not sufficient for inclusion |
| Grouped feature ablation (drop-one, and drop-group for ATR / RSI / MACD / distance / return / vol / time families) | incremental value |
| Permutation importance on the out-of-time fold | stability |
| Multiple seeds / folds | report variance, not a single number |
| Calibration check | reliability of any probability output |

## 8. Cost model

Any **economic** claim (profitability / tradability) must apply a preregistered cost model — spread, commission, slippage — before being reported. A statistically predictive feature is not automatically tradable.

## 9. Multiple-comparison and selection bias (registered risk R4)

- Preregister the **hypothesis set** and the **maximum number of trials** per feature.
- Correct for multiplicity across the 33 candidates (e.g. BH-FDR or Bonferroni); report both raw and adjusted results.
- Any candidate selected on the same data it was evaluated on must be **re-confirmed on the untouched holdout**.
- Report the full trial count; no silent pruning of unsuccessful trials.
- Do **not** present the best of many trials as a single result.

## 10. Metrics and acceptance

- Report ranking/discrimination metrics (AUC, rank IC) **and** log-loss/Brier with calibration.
- Acceptance is **incremental over baseline, out-of-time, after cost and multiplicity correction**, with variance reported across folds/seeds.
- A candidate may be **selected or rejected for predictive reasons only**; its **technical definition must not change** (a change returns to the Phase 3.2 owner process).

## 11. Deliverables (per experiment)

1. Experiment ID + protocol version.
2. Git commit + clean/dirty status; runtime/dependency identity.
3. Exact data identity (instruments, period, final candle, sha256 of inputs).
4. Split definitions, purge/embargo sizes, holdout boundary.
5. Target definition and class balance.
6. Per-feature per-fold results (raw + multiplicity-adjusted).
7. Baseline comparison and incremental value.
8. Cost model and (if claimed) economic result.
9. PASS / FAIL / NOT RUN / BLOCKED + failure reason + reproducible evidence.
10. Statement of whether the run touched any holdout, and how many times.

## 12. Relationship to Phase 3.2

- Phase 3.3 may **select or reject** candidates for predictive reasons only.
- Phase 3.3 **must not**: alter a technical definition, change a frozen parameter, re-issue the Feature Contract Identity, or freeze the model/prediction schema.
- The final ordered model schema requires **both** Phase 3.2 technical eligibility and Phase 3.3 predictive-value decisions.

## 13. Stop conditions

Stop the affected experiment if:

- the runtime/dependency identity differs from the preregistered environment;
- a leakage control (§5) fails;
- a result requires changing the target, split, formula, or tolerance;
- a hidden fallback / data repair is detected;
- any model training, artifact write, deployment, READY activation or trading-behavior change would be required.

A stop is a result, not permission to improvise a repair.

## 14. What this protocol does not do

- It does **not** authorize execution.
- It does **not** authorize training, artifact writes, publishing, deployment, READY activation, or trading-behavior changes.
- It does **not** freeze the prediction schema or issue a model identity.

## 15. Authorization

Execution of any evaluation under this protocol requires a **separate, explicit owner authorization** that names: the datasets, the compute/scope, the maximum trial budget, and whether any training is permitted. This document is the protocol only; it is not a grant.

> Proposed new standing clause: Phase 3.3 predictive-value research **does not** constitute a re-freeze of the Phase 3.2 Feature Contract and **does not** automatically grant production-implementation, model-training, or runtime-wiring rights.
