# Phase 3.3 — Owner Decision Register

**Document ID:** `PHASE3_3_OWNER_DECISION_REGISTER`
**Date:** 2026-11-16
**Status:** `DRAFT — PENDING OWNER DECISIONS`
**Nature:** Decision-management record. Not a research plan and not an authorization.
**Source of items:** the nine OPEN decisions in `06_RESEARCH_CONTRACT.md` §12.
**Authority:** This register **makes no decision**. The Owner decides each item. Creating this register is **not** permission to execute experiments.

---

## 1. Purpose and how to use this register

- Centralise the nine unresolved research-design decisions (`OPEN-01`..`OPEN-09`) identified in `06_RESEARCH_CONTRACT.md`.
- Make each decision **explicit, traceable, independently approvable, and evidence-backed**.
- Keep **approved decisions**, **legacy code behavior**, and **Agent recommendations** strictly separate.
- The Agent **does not** decide on the Owner's behalf. Owner columns stay blank until the Owner fills them.

Status vocabulary: `OPEN` · `PROPOSED` · `OWNER APPROVED` · `REJECTED` · `DEFERRED`.

## 2. Source record

| Item | Reference |
|---|---|
| OPEN items inherited from | `06_RESEARCH_CONTRACT.md` §12 (`OPEN-01`..`OPEN-09`) |
| Feature Contract Identity | `FCV2-bffdb0005083f95e` (`00` §2) |
| Frozen 33 candidates / 2 EXCLUDE / 2 DEFER | `01` §2–§4 |
| P1/P2 PASS · P3–P5 `NOT VERIFIED` · `FULL_PARITY_STATUS = NOT VERIFIED` | `00` §2 / `03` §1 / `05` §8 |
| Authorization restrictions | `04_AUTHORIZATION_BOUNDARY.md` |
| Legacy evidence inspected (code) | `data_pipeline.py`, `retrain_model.py`, `fx_trade_bot_v685.py`, `utils/ml_confirmation.py`, `fx_model_xgb.py` |
| Production config evidence | `docs/phase3_2/04_RUNTIME_CONFIGURATION_DECISIONS.md` (RC-02 = 800 bars) |

**Rule:** legacy code values are **not** approved research decisions. They are recorded only to distinguish them from what the Owner has actually approved.

## 3. Decision records

### 3.1 `OPEN-01` — Prediction Target

| Field | Content |
|---|---|
| **Decision ID** | `OPEN-01` |
| **Decision question** | What quantity does Phase 3.3 predict? (direction / return / other explicitly defined target) |
| **Why it matters** | Every metric, label, baseline and disposition depends on the target; changing it invalidates all prior evaluation. |
| **Existing evidence** | `06` §1, §3, §12. Phase 3.2 `02_FEATURE_TECHNICAL_DEFINITIONS_AND_ELIGIBILITY.md` §1 states predictive value is **out of scope** → **no approved target exists**. |
| **Legacy behavior** | Binary direction, not an approved decision: `data_pipeline.py:373` `df["target"] = (future_return > 0).astype(int)`; `utils/ml_confirmation.py:210` same; `fx_model_xgb.py:62` `target = np.where(future_return > 0, 1, 0)`. |
| **Available options** | `INSUFFICIENT EVIDENCE` — no approved source. Categories named in `06` §12 (direction / return / triple-barrier) are **illustrative only**, not options endorsed by evidence. |
| **Consequences** | Target choice determines the label, the leakage window (via `OPEN-03`), the choice of metric (`OPEN-06`), and the economic interpretation (`OPEN-08`). |
| **Recommendation** | None (Owner decision). Rationale: no evidence-backed basis in the approved record. |
| **Status** | `OPEN` |
| **Owner decision** | *(blank — pending)* |
| **Decision date** | *(blank)* |

### 3.2 `OPEN-02` — Prediction Horizon

| Field | Content |
|---|---|
| **Decision ID** | `OPEN-02` |
| **Decision question** | Over how many future bars (M15) is the target observed? |
| **Why it matters** | Sets the label span, the minimum purge/embargo (`OPEN-05`), and the achievable sample support. |
| **Existing evidence** | No approved Phase 3.2 decision defines a predictive horizon. `docs/phase3_2/04_RUNTIME_CONFIGURATION_DECISIONS.md` defines **history length** (RC-02 = 800 bars), which is a different quantity. |
| **Legacy behavior** | `data_pipeline.py:110` `target_horizon: int = 6`; `retrain_model.py:37` `TARGET_HORIZON = 6`; `fx_trade_bot_v685.py:1216` `target_horizon=cfg_bot("TARGET_HORIZON", 6)`. A **different** legacy value exists: `utils/ml_confirmation.py:94` `ML_LABEL_HORIZON_DEFAULT = 3`. None is owner-approved. |
| **Available options** | `INSUFFICIENT EVIDENCE`. Must distinguish three separate things: (a) legacy `target_horizon=6`; (b) any previously approved horizon — **none found**; (c) the proposed Phase 3.3 horizon — **not yet proposed**. |
| **Consequences** | Larger horizon → longer label overlap → larger purge (`OPEN-05`) and fewer independent samples; smaller horizon → noisier labels. |
| **Recommendation** | None (Owner decision). The legacy value `6` must **not** be treated as approved. |
| **Status** | `OPEN` |
| **Owner decision** | *(blank — pending)* |
| **Decision date** | *(blank)* |

### 3.3 `OPEN-03` — Label Construction

| Field | Content |
|---|---|
| **Decision ID** | `OPEN-03` |
| **Decision question** | What is the exact label formula, and how does it relate to the target (`OPEN-01`) and horizon (`OPEN-02`)? What information enters the label, and what is the resulting information-overlap window? |
| **Why it matters** | Defines the quantity being predicted and the temporal overlap that purge/embargo must cover (`OPEN-05`). |
| **Existing evidence** | None approved (Phase 3.2 predictive work is out of scope). `06` §12 records this as OPEN. |
| **Legacy behavior** | Thresholded direction, not approved: `retrain_model.py:135-136` `future_return = df["Close"].shift(-TARGET_HORIZON) / df["Close"] - 1; df["target"] = (df["future_return"] > TARGET_THRESHOLD).astype(int)`, with `TARGET_THRESHOLD = 0.0005` (`retrain_model.py:38`); `data_pipeline.py:372-374` uses threshold `0.0`. Because the label uses `shift(-H)`, the **information-overlap window = H bars**. No final implementation is written here. |
| **Available options** | `INSUFFICIENT EVIDENCE` — no approved formula. |
| **Consequences** | A threshold/near-tie rule affects class balance and metric choice; a stop/target (barrier) construction changes the overlap window and the purge requirement. |
| **Recommendation** | None (Owner decision). Report the legacy overlap window (`shift(-H)` ⇒ H bars) only as context. |
| **Status** | `OPEN` |
| **Owner decision** | *(blank — pending)* |
| **Decision date** | *(blank)* |

### 3.4 `OPEN-04` — Sample Eligibility

| Field | Content |
|---|---|
| **Decision ID** | `OPEN-04` |
| **Decision question** | Which samples are valid? Rules for: feature warm-up; missing/invalid samples; class balance and minimum class support; excluded periods; instrument eligibility; other sample-quality restrictions. |
| **Why it matters** | Determines which rows are valid for evaluation and how many independent samples exist. |
| **Existing evidence** | Warm-up is **partially constrained** by the frozen feature contract: FD-09 (approved) requires warm-up **feature outputs** to stay `NaN` and never be filled (Phase 3.2 `02_…` §6). **`MIN_BARS = 2` (`ml/feature_contract.py:56`) is a minimum input-batch guard only** — it raises `InputContractError` when the candle batch is shorter than 2 (`:110-111`); it is **not** a minimum research sample size and must **not** be read as sample-eligibility evidence. Calendar Contract §6 leaves **per-instrument coverage UNRESOLVED**. Class-balance/minimum-support rules are undefined. |
| **Legacy behavior** | `retrain_model.py:36` `LOOKBACK_BARS = 500`, `:39` `TRAIN_TEST_SPLIT = 0.20`; legacy reports class balance (`retrain_model.py:207` prints UP ratio). These are legacy training choices, not approved research rules. |
| **Available options** | Mostly `INSUFFICIENT EVIDENCE`; warm-up behaviour is constrained by FD-09 (not selectable). |
| **Consequences** | Stricter eligibility → fewer samples but lower noise; excluded periods (holidays, gaps) interact with the Calendar Contract (§7 holidays UNRESOLVED). |
| **Recommendation** | Preserve the frozen Feature Contract output exactly: warm-up values remain `NaN` and must never be imputed. Research sample eligibility may exclude rows containing unavailable or invalid feature values, **provided that this exclusion occurs downstream and does not modify the frozen feature definitions or outputs**. |
| **Status** | `OPEN` (partially constrained by FD-09) |
| **Owner decision** | *(blank — pending)* |
| **Decision date** | *(blank)* |

### 3.5 `OPEN-05` — Purge / Embargo

| Field | Content |
|---|---|
| **Decision ID** | `OPEN-05` |
| **Decision question** | What purge and embargo durations are required, derived from the approved target, horizon and label construction? |
| **Why it matters** | Prevents train/test label overlap (leakage). Too small → optimistic bias; too large → lost samples. |
| **Existing evidence** | `06` §4 fixes the **structural rule**: purge ≥ actual label span + embargo buffer. The **numeric value is not approved and must not be assumed to be 6 bars**. `02_FEATURE_VALUE_EVALUATION_PROTOCOL.md` §4 currently asserts a 6-bar horizon (see §6 conflict `C-03`). |
| **Legacy behavior** | Legacy training uses a single chronological split `retrain_model.py:39` `TRAIN_TEST_SPLIT = 0.20` with **no evident purge/embargo**. |
| **Available options** | Structure fixed (`≥ label span + embargo`); the **numeric value** is `INSUFFICIENT EVIDENCE` pending `OPEN-02` and `OPEN-03`. |
| **Consequences** | Directly controls leakage risk (R3) and sample count; an under-sized purge silently inflates reported value. |
| **Recommendation** | Defer the numeric value until `OPEN-02`/`OPEN-03` are decided; express it as *label span + embargo* once known. |
| **Status** | `OPEN` |
| **Owner decision** | *(blank — pending)* |
| **Decision date** | *(blank)* |

### 3.6 `OPEN-06` — Primary Evaluation Metric

| Field | Content |
|---|---|
| **Decision ID** | `OPEN-06` |
| **Decision question** | What is/are the **primary** metric(s) for candidate evaluation? |
| **Why it matters** | Drives selection and the disposition (`OPEN-09`); must be fixed **before** results are seen. |
| **Existing evidence** | `06` §6 lists dimensions (discrimination / calibration / incremental / stability / practical-after-cost) but selects **no primary metric**. |
| **Legacy behavior** | Legacy reports accuracy (`retrain_model.py:234` `accuracy_score`) and uses `predict_proba`; this is a legacy training diagnostic, not an approved research metric. |
| **Available options** | Dimension-level candidates only (`AUC` / `rank IC` / `log-loss`); the **choice** is `INSUFFICIENT EVIDENCE`. |
| **Consequences** | Metric choice determines which candidates appear to add value; probabilistic metrics require calibration reporting. |
| **Recommendation** | None (Owner decision). Must be preregistered; must not be chosen after inspecting candidate results. |
| **Status** | `OPEN` |
| **Owner decision** | *(blank — pending)* |
| **Decision date** | *(blank)* |

### 3.7 `OPEN-07` — Cross-Pair Evaluation Policy

| Field | Content |
|---|---|
| **Decision ID** | `OPEN-07` |
| **Decision question** | What is the instrument evaluation structure: pooled / per-pair / leave-one-pair-out? How are shared timestamps isolated? Is the claim instrument-specific or generalisable? |
| **Why it matters** | Affects generalisation claims and cross-instrument leakage control; currency pairs are **not** statistically independent. |
| **Existing evidence** | `06` §4 requires cross-pair isolation at shared timestamps. Calendar Contract §6 leaves per-instrument coverage UNRESOLVED. The evaluation instrument set is **not enumerated**. |
| **Legacy behavior** | Legacy trains one **pooled** model across `config.DEFAULT_PAIRS` (`retrain_model.py:189-201` concatenates per-pair arrays). Not an approved research policy. |
| **Available options** | `INSUFFICIENT EVIDENCE` — no approved policy. |
| **Consequences** | Pooled evaluation can leak information across pairs; per-pair evaluation reduces sample size; leave-one-pair-out tests generalisability at higher cost. |
| **Recommendation** | None (Owner decision); note that shared-timestamp isolation (`06` §4) must hold under any policy. |
| **Status** | `OPEN` |
| **Owner decision** | *(blank — pending)* |
| **Decision date** | *(blank)* |

### 3.8 `OPEN-08` — Transaction Cost Assumptions

| Field | Content |
|---|---|
| **Decision ID** | `OPEN-08` |
| **Decision question** | What cost assumptions apply for practical-value claims: spread, commission, slippage, data availability/source, and whether costs vary by instrument or time? |
| **Why it matters** | Any economic/practical claim (`06` §1 practical value; §6 practical performance) is meaningless without costs. |
| **Existing evidence** | None approved. `06` §12 records this as OPEN. |
| **Legacy behavior** | No cost model was located in the reviewed training/inference path. |
| **Available options** | `INSUFFICIENT EVIDENCE` — no approved cost data. Historical cost data must **not** be invented. |
| **Consequences** | Without costs, only statistical (not practical) value can be claimed; cost magnitude can flip a candidate's practical verdict. |
| **Recommendation** | None (Owner decision); costs are required before any practical/economic claim. |
| **Status** | `OPEN` |
| **Owner decision** | *(blank — pending)* |
| **Decision date** | *(blank)* |

### 3.9 `OPEN-09` — Minimum Evidence for `SELECTED`

| Field | Content |
|---|---|
| **Decision ID** | `OPEN-09` |
| **Decision question** | What minimum evidence is required to assign the disposition `SELECTED`? |
| **Why it matters** | Defines the acceptance threshold and prevents post-hoc relaxation. |
| **Existing evidence** | `06` §9 defines the disposition vocabulary but sets **no** threshold. |
| **Legacy behavior** | No selection gate exists in the legacy path. |
| **Available options** | `INSUFFICIENT EVIDENCE`. Consideration areas (incremental value over baseline, out-of-time performance, fold stability, cross-pair evidence, multiplicity adjustment, cost sensitivity, minimum sample support) are **criteria to decide on**, not a threshold. No numeric threshold is invented here. |
| **Consequences** | A loose threshold admits spurious candidates; a strict one discards weak-but-real signal. |
| **Recommendation** | None (Owner decision); thresholds must be Owner-approved and preregistered before results are seen. |
| **Status** | `OPEN` |
| **Owner decision** | *(blank — pending)* |
| **Decision date** | *(blank)* |

## 4. Execution authorization prerequisites (inherited from `06` §14)

These are **authorization prerequisites**, not approved decisions. Creating this register does **not** authorize execution.

| # | Prerequisite | Status |
|---|---|---|
| A1 | Dataset identity and location (instruments, period, final candle, input `sha256`) | **NOT PROVIDED** |
| A2 | Instrument universe (explicit instrument list) | **NOT PROVIDED** |
| A3 | Available compute / resources | **NOT PROVIDED** |
| A4 | Permitted experiment / trial budget | **NOT PROVIDED** |
| A5 | Whether offline training is permitted | **NOT PROVIDED** |
| A6 | Research artifact storage location (separate from production) | **NOT PROVIDED** |
| A7 | Execution start authorization | **NOT PROVIDED** |

## 5. Decision dependencies

| Decision | Blocks (downstream) | Depends on |
|---|---|---|
| `OPEN-01` Target | Doc 08 (Dataset & Label Spec) | — |
| `OPEN-02` Horizon | Doc 08; `OPEN-05` | — |
| `OPEN-03` Label construction | Doc 08; `OPEN-05` | `OPEN-01`, `OPEN-02` |
| `OPEN-04` Sample eligibility | Valid sample construction (Doc 08 / Doc 09) | FD-09 (already constrains warm-up) |
| `OPEN-05` Purge / embargo | Doc 09 (splitting) | `OPEN-02`, `OPEN-03` |
| `OPEN-06` Primary metric | Evaluation protocol finalisation (Doc 09) | `OPEN-01` (target) |
| `OPEN-07` Cross-pair policy | **Doc 09** (dataset splitting; cross-instrument evaluation) — **not** a Doc 08 gate | `OPEN-04` (instrument eligibility) |
| `OPEN-08` Costs | Any practical/economic value claim (Doc 11 / Doc 14) | `OPEN-06` (metric) |
| `OPEN-09` Min evidence for `SELECTED` | Disposition Register (Doc 13) | `OPEN-06`, `OPEN-08` |

**Document 08 scope (Dataset & Label Specification):** target (`OPEN-01`), horizon (`OPEN-02`), label construction (`OPEN-03`), and sample eligibility (`OPEN-04`). Dataset **splitting** and **cross-instrument evaluation** are outside Doc 08 scope and belong to Doc 09 (Experiment Execution Plan).

**Minimum gate to finalise document 08:** `OPEN-01`, `OPEN-02`, `OPEN-03`, and `OPEN-04` must be resolved. `OPEN-07` is **not** a Doc 08 gate; it blocks Doc 09.

**Owner-confirmed documentation-architecture decision (signed 2026-11-16).** Document 08 (Dataset & Label Specification) scope = **target, horizon, label construction, sample eligibility** (`OPEN-01`–`OPEN-04`); dataset **splitting** and **cross-instrument evaluation** belong to **Doc 09**. `OPEN-07` therefore does **not** gate Doc 08.

> **Owner:** owner · **Date:** 2026-11-16 · **Decision:** Doc 08 scope = option 1 (target / horizon / label / sample-eligibility) — **ACCEPTED**.
> This is a **documentation-architecture** decision only. It does **not** approve `OPEN-01`–`OPEN-09` (all remain `OPEN`) and does **not** authorize creating Document 08 or any execution.

## 6. Source conflicts and cross-document findings

Recorded per the spec's conflict rule. **Not silently resolved.** Documents `00`–`06` are **not** edited by this register.

**`C-01` (P0) — Self-conflict inside `06`, holdout usage.**
- Location A: `06_RESEARCH_CONTRACT.md` §4 — "Untouched holdout | One final holdout segment, inspected **once**, at the end".
- Location B: `06_RESEARCH_CONTRACT.md` §7 — "Re-confirm any holdout-selected candidate on the untouched holdout exactly once."
- Nature: B implies a candidate may be **selected** off the holdout and then re-confirmed on it, contradicting A (holdout inspected once, untouched).
- Suggested resolution (Owner-provided wording; **not applied** here): remove B and replace with — "Candidate selection, feature selection, and hyperparameter decisions must be completed without accessing the final holdout. The final holdout shall be evaluated once, after all selection decisions have been frozen. No candidate may be selected or rescued based on final-holdout results."
- Status: **OPEN** (requires an Owner-approved edit to `06`).

**`C-02` (P1) — `06` §11 conflates production history length with research sample validity.**
- Location A: `06_RESEARCH_CONTRACT.md` §11 — "sample support is insufficient (e.g. warm-up not satisfied at 800 bars, RC-02)".
- Location B: `docs/phase3_2/04_RUNTIME_CONFIGURATION_DECISIONS.md` §3 + RC table — "800 bars" is the **production input history length** (RC-02, L2-B, 2026-11-15), i.e. a production input-contract value.
- Nature: the phrase links a **production input-history** value to **research sample validity** without establishing the relationship. These are distinct: RC-02 governs the live input contract; research sample validity is governed by `OPEN-04`.
- Suggested handling: keep RC-02 as the production input-history contract; express research sample validity through `OPEN-04`; do not assert a numeric research threshold derived from 800 without Owner approval.
- Status: **OPEN** (clarification; may require an Owner-approved edit to `06`).

**`C-03` (P1, previously reported) — 6-bar label horizon divergence.**
- Location A: `02_FEATURE_VALUE_EVALUATION_PROTOCOL.md` §4 — asserts a **6-bar** label horizon (sourced from legacy `data_pipeline.FeatureConfig.target_horizon = 6`).
- Location B: `06_RESEARCH_CONTRACT.md` §4 & §12 — records the horizon/purge as **OPEN**, explicitly not fixed to 6 bars.
- Nature: A presupposes a horizon that is not Owner-approved; B (correctly) leaves it OPEN. **Recorded here without resolving the source conflict.** `OPEN-02` and `OPEN-05` remain `OPEN`. The conflicting statement in document `02` remains unchanged, pending an Owner-approved correction.
- Status: **OPEN** (expected to close when `OPEN-02`/`OPEN-05` are decided).

## 7. Status and boundary

- **Status:** `DRAFT — PENDING OWNER DECISIONS`.
- All nine decisions `OPEN-01`..`OPEN-09` remain `OPEN`; every Owner-decision field is blank.
- Second-stage document 07 acceptance **does not** approve the nine decisions; `OPEN` must not be auto-promoted to `APPROVED`.
- This register authorises **nothing**: no dataset generation, no label generation, no experiments, no training, no artifact writes, no live wiring, no deployment, no trading-behavior change (per `04_AUTHORIZATION_BOUNDARY.md` and `06` §2/§14).
- No document `00`–`06` and no source code is modified by this register.
