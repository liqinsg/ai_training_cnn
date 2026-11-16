# Phase 3.3 — Research Contract

**Document ID:** `PHASE3_3_RESEARCH_CONTRACT`
**Date:** 2026-11-16
**Status:** `DRAFT — PENDING OWNER APPROVAL`
**Nature:** Research governance contract. **Not** a model-implementation specification.
**Scope:** Governing rules for evaluating the **predictive value** of the 33 technically-eligible feature candidates handed over from Phase 3.2.
**Authority:** This contract **does not** authorize execution, model training, artifact writes, deployment, or trading-behavior changes. It records the rules and the unresolved decisions; it grants nothing. (Inherited from `04_AUTHORIZATION_BOUNDARY.md`.)

---

## 1. Purpose and research questions

Phase 3.3 answers **only** whether a handed-over feature candidate carries usable **predictive** information. Technical correctness (Phase 3.2, complete) is a **precondition**, never evidence of predictive value.

Four distinct questions must not be collapsed into one:

| Concept | Question | Status once established |
|---|---|---|
| **Predictive association** | Is there any measurable statistical relationship between the candidate and the target? | Screening signal only — necessary, **not** sufficient |
| **Predictive performance** | How well does the candidate (alone) predict the target out of sample? | Standalone performance — **not** incremental value |
| **Incremental value** | Does the candidate improve a stated metric **beyond a baseline**? | The primary inclusion criterion |
| **Practical value** | Does the improvement survive realistic transaction costs and is it actionable? | Economic relevance — **not** implied by the three above |

Required research questions:

- **Q1** — Does the candidate contain measurable predictive information?
- **Q2** — Does it add **incremental** value beyond an existing baseline?
- **Q3** — Is its value **stable out of sample**?
- **Q4** — Is its value **redundant** with other candidates?
- **Q5** — Does its value **persist across relevant currency pairs and market conditions**?
- **Q6** — Does its value remain **meaningful under realistic cost assumptions**?

## 2. Scope and non-scope

**Phase 3.3 MAY (research only):**

- Receive and study the 33 `TECHNICALLY ELIGIBLE (feature-level)` candidates.
- Preregister and run **leakage-controlled offline** predictive-value evaluations (subject to a **separate** execution authorization).
- Record per-candidate selection/rejection for predictive reasons in a Phase 3.3 disposition register.
- Perform **read-only** scans/validations on existing data and artifacts.

**Phase 3.3 SHALL NOT:**

- Train any (production) model.
- Write, overwrite, or publish model artifacts.
- Wire live prediction (READY / `live_hook`).
- Enable `USE_FEATURE_CONTRACT_V2` by default.
- Activate READY or live hooks.
- Deploy.
- Change trading behavior.

Do **not** interpret research authorization as implementation authorization. A successful research result is **not** implementation approval; each implementation action requires its own separate, explicit owner authorization (see `04_AUTHORIZATION_BOUNDARY.md` §3).

## 3. Research unit and evaluation principles

**Research unit** = one evaluation of a **(candidate × target × instrument universe × fold)** combination against a declared baseline. Scores are reported at this granularity; no aggregation may hide an unstable or weak unit.

Principles:

1. **Preregistration.** Inputs, universe, split definitions, target, label, metrics, tolerances, trial budget and acceptance rules are frozen **before** any result is inspected.
2. **Individual reporting.** Each candidate is reported individually; a group/aggregate score may not conceal a failing member.
3. **Frozen technical identity.** The candidate's technical definition, parameters, order and the Feature Contract Identity are **fixed** and must not be altered.
4. **Downstream disposition.** Any selection/rejection is a **Phase 3.3 disposition only** and never rewrites the signed Phase 3.2 register.
5. **No fabricated design.** The target, horizon, label formula, sample-eligibility rules and split parameters are **not** invented here — they are OPEN decisions (§12).

**Missing design decisions (OPEN — carried to document 07, not created here):** the final prediction **target**, prediction **horizon**, **label** construction, and **sample-eligibility** rules have **not** been owner-approved. They are recorded as OPEN in §12. No value is asserted.

## 4. Data separation and leakage controls

Mandatory principles (leakage risk **R3**):

| Control | Requirement |
|---|---|
| Separation | **Chronological** time-series split only; **never** random shuffle across time |
| purge / embargo | A purge gap ≥ the **actual label span** between train and test, plus an embargo buffer, so **no** train label window overlaps a test window. Exact value **OPEN** (§12) |
| Cross-pair isolation | At a shared timestamp, train and test must not mix instruments whose label windows overlap |
| Fold-local preprocessing | Any scaling/encoding is fit **only** on the train fold; never on validation or holdout |
| No leakage from target | No target-derived statistic may enter preprocessing or feature selection |
| Untouched holdout | One final holdout segment, inspected **once**, at the end |
| Reproducible boundaries | Fold boundaries are declared, recorded, and reproducible from the recorded configuration |

**Purge/embargo caution:** the exact purge/embargo duration is **NOT** fixed to 6 bars and must **not** be adopted blindly. It must be derived from the **approved** prediction horizon and label construction (§3). Because those are **OPEN**, the exact value remains **OPEN** (§12, `OPEN-05`).

> Consistency note (reported, not silently resolved): `02_FEATURE_VALUE_EVALUATION_PROTOCOL.md` §4 currently states a **6-bar** label horizon, sourced from the legacy `data_pipeline.FeatureConfig.target_horizon = 6`. That value is **not** an owner-approved prediction horizon; this contract therefore records the duration as OPEN. See the delivery report for the exact source locations.

## 5. Baselines and evaluation design

Every candidate is evaluated **incrementally** against declared baselines.

| Design element | Purpose | Establishes | Does **not** establish |
|---|---|---|---|
| **B0** trivial baseline (persistence / majority class / random-with-prior) | floor reference | whether the target is learnable at all | feature value |
| **B1** simple reference baseline | reference predictor | whether the candidate beats a simple model | feature value alone |
| Feature-level evaluation | one candidate vs baseline | standalone predictive performance | incremental value or redundancy |
| Feature-group evaluation | family (ATR / RSI / MACD / distance / return / vol / time) | family-level contribution | per-feature necessity |
| Incremental addition | add candidate to baseline | incremental value | necessity if redundant |
| Ablation (drop-one / drop-group) | remove candidate from full set | marginal value in presence of others | standalone value |
| Redundancy analysis | pairwise/collinear structure | whether value is duplicated | that a redundant feature is worthless |
| Combined-candidate evaluation | subsets | interaction effects | causal attribution |

No-feature / trivial baselines are required where meaningful. A feature has value only if it improves a stated metric over the relevant baseline **out of time**, within cost.

## 6. Evaluation metrics

Metric framework (primary vs diagnostic separated):

| Dimension | Example metrics | Role |
|---|---|---|
| Discrimination | AUC, rank IC | primary candidate |
| Probability quality / calibration (if probabilistic outputs are used) | log-loss, Brier score, reliability curve | primary candidate |
| Directional performance (where relevant) | directional hit rate, directional PnL (pre-cost) | diagnostic |
| Incremental performance | Δ metric vs B0/B1, ablations | primary candidate |
| Stability | variance across folds / seeds | primary candidate |
| Practical performance | metric **after** applicable transaction costs | diagnostic → economic claim gate |

Rules:

- **Primary metrics** must be preregistered and fixed across all compared candidates; **diagnostic metrics** support interpretation only.
- Metrics must **not** be selected because they produce favorable results.
- Probability-based metrics require calibration reporting when probabilistic outputs are used.
- Unresolved metric choices (including the **primary metric**) are **OPEN** (§12, `OPEN-06`).

## 7. Multiple-comparison and selection-bias controls

Selection-bias risk **R4**. The research must:

- Record **every** tested candidate and **every** tested combination.
- Record **failed** and **abandoned** experiments (no silent pruning).
- Never report only the best-performing combination.
- Treat multiplicity explicitly across the 33 candidates (e.g. BH-FDR or Bonferroni); report both raw and adjusted results.
- Not repeatedly tune against the final holdout.
- Not apply post-hoc threshold adjustment to rescue a weak candidate.
- Re-confirm any holdout-selected candidate on the untouched holdout exactly once.

## 8. Robustness requirements

Each candidate must be assessed across, at minimum:

| Dimension | Requirement |
|---|---|
| Out-of-time stability | performance holds on later, unseen time segments |
| Cross-currency-pair stability | performance holds across the preregistered instrument set |
| Market-regime sensitivity | stability across regimes — **only** using owner-approved regime definitions |
| Cost sensitivity | result survives realistic cost assumptions |
| Feature distribution drift | monitor train→test feature distribution shift |
| Fold-to-fold variation | report variance, not a single number |

Do **not** invent market-regime definitions. The regime taxonomy is **not** owner-approved; unresolved regime definitions are **OPEN** and must not be fabricated.

## 9. Candidate disposition rules

Permitted downstream dispositions (Phase 3.3 only):

| Disposition | Meaning |
|---|---|
| `SELECTED` | demonstrated incremental, out-of-time, cost-aware value |
| `CONDITIONAL` | promising but gated on an unresolved item (e.g. pending target/robustness) |
| `REJECTED_FOR_VALUE` | technically eligible, but no demonstrated predictive value |
| `INCONCLUSIVE` | insufficient evidence to decide (blocked / underpowered / unresolved prerequisite) |

Rules:

- Every disposition requires recorded **evidence** and **rationale**.
- A disposition is recorded in a **Phase 3.3 Candidate Disposition Register**.
- A disposition must **never** modify the signed Phase 3.2 candidate register, alter frozen feature definitions, or change the Feature Contract Identity `FCV2-bffdb0005083f95e`. (A candidate that is technically eligible but rejected for value is recorded as *eligible / rejected-for-value*; the original 33-column list and `FCV2` are unchanged.)
- A change to any technical definition, parameter, or the identity requires returning to the Phase 3.2 owner decision process (**not** a Phase 3.3 action).

## 10. Reproducibility and evidence

Every experiment must record:

1. Git commit and branch; dirty/clean status.
2. Environment and dependency versions (Python, numpy, pandas, scikit-learn, xgboost, `tzdata`, `pytz`).
3. Dataset identity and source (instruments, period, final candle, input `sha256`).
4. Label-specification identity.
5. **Feature Contract Identity** (`FCV2-bffdb0005083f95e`).
6. Experiment configuration (protocol version, universe, splits, seeds).
7. Random seeds where applicable.
8. Fold boundaries (purge/embargo, holdout boundary).
9. Metrics and outputs (raw + multiplicity-adjusted).
10. Exact execution command.
11. Artifact `sha256` for all research outputs.

**Research artifacts must be stored separately from production artifacts**, with no writes to the production bundle path. Research outputs are not production artifacts and must not be published as such.

## 11. Stop conditions

Stop (or mark `BLOCKED` for) the affected experiment if:

- the prediction **target or label definition is unresolved**;
- a **dataset-integrity** check fails;
- a **leakage-control** (§4) fails;
- a **baseline is not reproducible**;
- the **feature identity is missing or incompatible** (FCID mismatch / non-contract input);
- **sample support is insufficient** (e.g. warm-up not satisfied at 800 bars, RC-02);
- any **unauthorized production or live-system modification** would be required.

A failed prerequisite results in **STOP / BLOCKED — never a silent fallback**. A stop is a result, not permission to improvise a repair.

## 12. Owner decisions required

Unresolved decisions are recorded below. **No owner decision is made by this document.** These are carried forward to the Owner Decision Register (**document 07**, not created here).

| Decision ID | Question | Why it matters | Proposed options (if evidence supports them) | Current status | Owner decision |
|---|---|---|---|---|---|
| `OPEN-01` | Final **prediction target** (e.g. direction, triple-barrier, other) | All metrics, labels and dispositions depend on it | None from an approved source | **OPEN** | *(pending)* |
| `OPEN-02` | Prediction **horizon** | Determines label span, purge/embargo, sample support | None from an approved source; legacy code carries `target_horizon=6` (not owner-approved) | **OPEN** | *(pending)* |
| `OPEN-03` | **Label construction** formula | Defines the quantity being predicted; drives leakage window | None from an approved source | **OPEN** | *(pending)* |
| `OPEN-04` | **Sample-eligibility** rules (warm-up, excluded periods, class balance) | Determines which rows are valid for evaluation | Warm-up is `NaN` during warm-up (FD-09); other rules undefined | **OPEN** (partially constrained) | *(pending)* |
| `OPEN-05` | **Purge / embargo duration** | Prevents train/test label overlap | Structurally ≥ label span + embargo; exact value depends on `OPEN-02`/`OPEN-03` | **OPEN** | *(pending)* |
| `OPEN-06` | **Primary evaluation metric** | Drives selection; must not be chosen post hoc | Candidates: AUC / rank IC / log-loss (dimension-level only) | **OPEN** | *(pending)* |
| `OPEN-07` | **Cross-pair evaluation policy** (pool / per-pair / leave-one-out) | Affects generalisation and leakage control | None from an approved source | **OPEN** | *(pending)* |
| `OPEN-08` | **Transaction cost assumptions** (spread / commission / slippage) | Required for any economic claim | None from an approved source | **OPEN** | *(pending)* |
| `OPEN-09` | **Minimum evidence for `SELECTED`** | Defines the acceptance threshold | None from an approved source | **OPEN** | *(pending)* |

## 13. Inherited constraints (consistency with 00–05)

| Inherited item | Value | Source |
|---|---|---|
| Feature Contract Identity | `FCV2-bffdb0005083f95e` | `00` §2 / `01` §1 / `05` §5 |
| Feature order and definitions | 33-column `ORDERED_FEATURES`, as frozen (FD-01..FD-09) | `01` §2 |
| Excluded | 2 — `vol_sma_ratio`, `vol_trend` (FD-07) | `01` §3 |
| Deferred | 2 — `is_london`, `is_ny` (not eligible; must not enter Phase 3.3) | `01` §4 |
| P1/P2 parity | PASS | `00` §2 / `03` §1 |
| P3–P5 parity | `NOT VERIFIED` | `00` §2 / `03` §1 / `05` §8 |
| `FULL_PARITY_STATUS` | `NOT VERIFIED` | `00` §2 |
| Authorization restrictions | as listed | `04` §1–§6 |
| Phase 3.3 nature | predictive-value **research only** | `00` §7 / `04` §1 |
| Disposition separation | downstream only; never rewrites the signed register or FCID | `00` §8 / `04` §2 |

This contract redefines **no** frozen feature and modifies **no** FCID.

## 14. Document status and approval

- **Status:** `DRAFT — PENDING OWNER APPROVAL`.
- Acceptance of the Phase 3.3 **handover** (`00` §7) does **not** authorize Phase 3.3 research **execution**.
- Execution of any evaluation under this contract requires a **separate, explicit owner authorization** naming the datasets, universe, compute, trial budget, and whether any training is permitted.
- Acceptance of this contract is **acceptance of the rules only**; model training, artifact publication and inference wiring must each be authorized separately.
