# 【Strict Spec】Phase 3.1 Stage A — Prediction Contract Definition

**Target Repository:** `/Users/liqin/projects/ai_training_cnn`
**Target Branch:** `v2026c`
**Target Phase:** Phase 3.1 — Prediction Contract & Abstention Semantics
**Target Stage:** **Stage A — Contract Definition (documentation only)**
**Mode:** Contract authoring against verified source evidence
**Priority:** P0
**Authorization:** **Documentation only.** No Python file may be modified. No commit. No deployment. No Entry-Authorization change.

> **Revision note (v2).** v1 of this spec incorrectly required **all 12 `generate_signal()` paths** to be mapped to `PredictionStatus`, which re-merged the Prediction and Decision layers. This revision fixes that: the two layers are separated, `ABSTAIN` is restricted to the Prediction layer, `NOT_RUN` is added, and the field-level rules are tightened (P0-1..P0-3, P1-1..P1-4).

---

## 0. Mission

Produce a single authoritative contract document:

```
docs/PHASE3_1_CONTRACT.md
```

It must define, once and completely: the semantics of an ML prediction result, the boundary between **Prediction** and **Decision**, the exhaustive classification of the current `generate_signal()` paths into those two layers, and how every downstream consumer is required to read the result.

This is **Stage A of four** (A: Contract Definition → B: Prediction Adapter → C: Downstream Integration → D: Tests & Shadow Validation). **Only Stage A is authorized now.** Stages B–D each require their own approval.

The problem being solved is **semantic, not statistical**: `generate_signal()` collapses **11 structurally different conditions** into a single `None` ([§3.1](#31-gap-1--exhaustive-none-return-paths-of-generate_signal)). But those conditions do **not** all belong to the same layer — some are prediction outcomes, most are strategy decisions. Phase 3.1 will not fix `None` correctly until that boundary is drawn first.

Phase 3.1 does **not** re-calibrate probabilities, does **not** change thresholds, and does **not** change entry authorization.

---

## 1. Scope and non-goals

### 1.1 In scope (Phase 3.1 overall; Stage A defines the contract for all of it)

| Work item | Phase |
|---|---|
| `PredictionResult` definition | 3.1 |
| Elimination of `None`-as-semantics | 3.1 |
| Prediction-layer abstention rules and statuses | 3.1 |
| Probability validity checks (shape / range / NaN / inf only) | 3.1 |
| Downstream consumption contract | 3.1 |
| **Definition of the Prediction ↔ Decision boundary** | 3.1 |

### 1.2 Explicitly OUT of scope (must be named in `PHASE3_1_CONTRACT.md` as deferred)

| Work item | Belongs to |
|---|---|
| Implementing `DecisionResult` / refactoring the strategy layer | later (contract only now) |
| Model probability **calibration** | later Evaluation |
| The `0.55` threshold optimization | later Evaluation |
| MC scoring rework | separate task |
| Strength scoring rework | separate task |
| `FINAL` weight redistribution | separate task |
| **Entry Authorization modification** | **separate approval** |
| Training set / label / CV rework | later Training & Evaluation |
| Feature-engineering changes | not authorized |
| Changing the MC percentage cache | not authorized (see §4.4.4) |

### 1.3 Hard boundary carried over from Phase 3.0

Phase 3.1 may make the downstream **accurately aware** of whether ML produced a valid prediction. Phase 3.1 may **not** decide, anywhere, whether trading is permitted when ML is unavailable.

> **Entry Authorization remains unchanged and unresolved.**

---

## 2. Preflight — preserve existing work

1. Confirm repository root and branch; record `HEAD`.
2. Record `git status --short`.
3. Read `fx_trade_bot_ml.py` (Phase 3.0 status contract), `strategy_decision.py`, `data_pipeline.py`, `fx_trade_bot.py`.
4. Read `docs/PHASE3_0_CLOSURE_REPORT.md` and `docs/PHASE3_0_IMPLEMENTATION_TASK.md`.

Constraints:

- Do **not** reset, checkout, rebase, stash, or clean.
- Do **not** modify any `.py` file. **Stage A output is documentation only.**
- Do **not** modify `docs/Development_plan.md`.
- Do **not** modify or delete unrelated documentation, including the pre-existing untracked `docs/*.md` and the pre-existing `README_DOC.md` / `README_doc.md` deletions.
- Do **not** commit. Do **not** deploy.

If the repository or branch differs from the target, **stop and report**.

---

## 3. Verified starting evidence (do not re-audit — verify and extend)

Targeted trace of the prediction function and its consumers. Stage A must **verify each row against source** and **extend** it if a row is wrong or a path is missing. Do **not** run a broad repository audit; restrict work to the prediction path and its consumers.

### 3.1 Gap 1 — exhaustive `None` return paths of `generate_signal()`

Function: `StrategyEngine.generate_signal()` in [strategy_decision.py](file:///Users/liqin/projects/ai_training_cnn/strategy_decision.py#L117-L266)

| # | Line | Condition | Returns | **Layer (see §3.3)** |
|---|---|---|---|---|
| 1 | [L135](file:///Users/liqin/projects/ai_training_cnn/strategy_decision.py#L131-L135) | insufficient bars (`< 5`) | `None` | **Prediction input precondition** |
| 2 | [L153](file:///Users/liqin/projects/ai_training_cnn/strategy_decision.py#L139-L153) | `_predict()` raised **any** exception | `None` | **Prediction** (mixed — Gap 2) |
| 3 | [L173](file:///Users/liqin/projects/ai_training_cnn/strategy_decision.py#L168-L173) | `raw_prob < min_prob` | `None` | **Decision** |
| 4 | [L184](file:///Users/liqin/projects/ai_training_cnn/strategy_decision.py#L181-L184) | MC filter BLOCK | `None` | **Decision** |
| 5 | [L193](file:///Users/liqin/projects/ai_training_cnn/strategy_decision.py#L190-L193) | regime filter BLOCK | `None` | **Decision** |
| 6 | [L202](file:///Users/liqin/projects/ai_training_cnn/strategy_decision.py#L199-L202) | ADX filter BLOCK | `None` | **Decision** |
| 7 | [L213](file:///Users/liqin/projects/ai_training_cnn/strategy_decision.py#L208-L213) | pivot filter BLOCK | `None` | **Decision** |
| 8 | [L222](file:///Users/liqin/projects/ai_training_cnn/strategy_decision.py#L219-L222) | strength-gap filter BLOCK | `None` | **Decision** |
| 9 | [L236](file:///Users/liqin/projects/ai_training_cnn/strategy_decision.py#L231-L236) | `score < min_conviction_score` | `None` | **Decision** |
| 10 | [L243](file:///Users/liqin/projects/ai_training_cnn/strategy_decision.py#L241-L243) | SL/TP build failed | `None` | **Decision / Trade Plan** |
| 11 | [L247](file:///Users/liqin/projects/ai_training_cnn/strategy_decision.py#L245-L247) | R/R invalid | `None` | **Decision / Trade Plan** |
| 12 | [L249](file:///Users/liqin/projects/ai_training_cnn/strategy_decision.py#L249-L266) | success | `Signal` | **Decision output** |

**Only rows 1–2 are Prediction-layer.** Rows 3–12 are Decision-layer. This is the central fact of Stage A.

### 3.2 Gap 2 — the exception bucket at L141–L153 collapses incompatible causes

`except Exception as e` at [L141](file:///Users/liqin/projects/ai_training_cnn/strategy_decision.py#L139-L153) maps **all** of the following to one `None`:

- `ScalerMissingError` — raised by `_predict()` at [L294–L298](file:///Users/liqin/projects/ai_training_cnn/strategy_decision.py#L294-L298) and by `predict_p_up()` at [data_pipeline.py:466-467](file:///Users/liqin/projects/ai_training_cnn/data_pipeline.py#L464-L471) → **model not usable**.
- `InferenceFeatureError` / `DimensionMismatchError` — feature/shape contract violation at inference → **result not trustworthy**.
- Genuinely unexpected exceptions → **execution failure**.

The contract **must** separate these three.

### 3.3 Layer classification of the current paths (verified from evidence above)

| Path | Actual semantics | Owning layer |
|---|---|---|
| bars insufficient | input does not satisfy prediction preconditions | **Prediction (input precondition)** |
| `_predict()` exception | model inference failed / model not usable | **Prediction** |
| `raw_prob < min_prob` | strategy probability gate rejected | Decision |
| MC / Regime / ADX / Pivot / StrengthGap BLOCK | strategy filters | Decision |
| conviction insufficient | strategy composite-score rejection | Decision |
| SL/TP build failure | trade-plan construction failure | Decision / Trade Plan |
| R/R invalid | trade-plan validity failure | Decision / Trade Plan |
| returns `Signal` | strategy produced a signal | Decision output |

Key consequence to encode in the contract: **a model predicting BUY does not imply the strategy filters pass; a strategy filter rejecting BUY does not imply the model failed to predict; SL/TP failure does not imply the prediction was invalid; low conviction does not imply the probability was untrustworthy.**

### 3.4 Consumers of `generate_signal()` (live paths only)

| # | Call site | Consumes | Behavior today on `None` |
|---|---|---|---|
| C-1 | [fx_trade_bot.py:2156](file:///Users/liqin/projects/ai_training_cnn/fx_trade_bot.py#L2150-L2174) (Step 4 multi-TF confluence) | `if sig:` then `sig.action` | that TF contributes **no** vote → may fail `CONFLUENCE_REQUIRED_TFS` |
| C-2 | [fx_trade_bot.py:2572](file:///Users/liqin/projects/ai_training_cnn/fx_trade_bot.py#L2572-L2595) (Step 7 scoring feed) | `sig is None or sig.model_p_up is None` → `_sig_model_missing`; `prob_raw` → `calc_weighted_score()` | XGB treated as **NEUTRAL**; `prob_raw=None` flows into scoring |

Both exist identically in `fx_trade_bot_v685.py` (byte-identical twin launched by `launch_dual_bot.sh`).

Other prediction-artifact consumers (must be enumerated; not necessarily changed):

- [attribution_v2/live_hook.py:140](file:///Users/liqin/projects/ai_training_cnn/attribution_v2/live_hook.py#L140) — reads `sig.model_p_up` as "raw P(up) in [0,1]".
- `StrategyEngine.should_close()` [L103–L115](file:///Users/liqin/projects/ai_training_cnn/strategy_decision.py#L103-L115) — calls `_predict()` directly, **not** `generate_signal()`; a **separate prediction surface**.
- `StrategyEngine.select_signals()` [L268–L284](file:///Users/liqin/projects/ai_training_cnn/strategy_decision.py#L268-L284) — consumes `Signal` only.

**Stale / out of scope:** `fx_trade_bot_ml_v1.py`, `fx_trade_bot_v683.py` — not imported by any live entry point. Record as stale; do not design against them.

### 3.5 Current probability surface (what is actually confirmed)

- `predict_p_up()` ([data_pipeline.py:464-471](file:///Users/liqin/projects/ai_training_cnn/data_pipeline.py#L464-L471)) returns `(proba[:, pos_idx], None)`; `pos_idx` comes from `positive_class_index()` ([L458-460](file:///Users/liqin/projects/ai_training_cnn/data_pipeline.py#L458-L460)), which follows `model.classes_`.
- **Only `p_up` is confirmed.** `p_down` is currently derived as `1 - p_up` in the *strategy* code ([L110](file:///Users/liqin/projects/ai_training_cnn/strategy_decision.py#L110), [L155](file:///Users/liqin/projects/ai_training_cnn/strategy_decision.py#L155)) — this is an *assumption in existing code*, not a confirmed model contract. See P1-2 in §4.4.
- `Signal` ([L67–L84](file:///Users/liqin/projects/ai_training_cnn/strategy_decision.py#L67-L84)) carries `raw_prob`, `model_p_up`, `edge`, `conviction_score`, `direction`, `action` — no `p_down`, and no way to express abstention/invalidity.

### 3.6 Phase 3.0 identity surface (what `ModelInitResult` actually provides)

`ModelInitResult` ([fx_trade_bot_ml.py:85-103](file:///Users/liqin/projects/ai_training_cnn/fx_trade_bot_ml.py#L85-L103)) provides: `status`, `reason`, `detail`, `artifact_path`, `release_id`, `manifest_present`, `model_hash`, `scaler_hash`, `features_hash`, `cfg_hash`, `backend`, `host_id`, `profile`, `timestamp`.

It provides **no field named `model_id` or `feature_contract_id`.** Stage A must therefore state the mapping explicitly (e.g. `model_id` ← `release_id` when `manifest_present`, else `model_hash`) and mark `NOT VERIFIED` where no verifiable source exists. It may **not** invent an identity source, and may **not** substitute a filename.

---

## 4. Required deliverable — `docs/PHASE3_1_CONTRACT.md`

The document must follow this six-section structure and contain all sub-requirements below, numbered and complete.

### 4.1 §1 Prediction Contract

**`PredictionStatus`** — minimum set:

| Status | Meaning | Belongs to layer |
|---|---|---|
| `READY` | model executed; a usable probability was produced and passed validity checks | Prediction |
| `ABSTAIN` | **the model/prediction layer itself** declined to produce a direction, by a *prediction-layer* rule | Prediction |
| `NOT_RUN` | the prediction did **not execute** because a precondition was not met (e.g. insufficient input) | Prediction (input precondition) |
| `UNAVAILABLE` | the model does not exist or is not usable right now | Prediction |
| `INVALID` | prediction executed but the result fails a data / probability / format requirement | Prediction |
| `ERROR` | a non-expected exception occurred during execution | Prediction |

Requirements:

- **`ABSTAIN` MUST be reachable only by prediction-layer rules.** Strategy rejections (MC / Regime / ADX / Pivot / StrengthGap / conviction / SL-TP / R/R / `raw_prob < min_prob`) are **Decision-layer outcomes and MUST NOT be expressed as `PredictionStatus.ABSTAIN`.**
- **`NOT_RUN` is preferred over folding input-precondition failures into `UNAVAILABLE`**, so a log can answer directly: *did the model not run because it cannot run, or because prediction was never entered?* If Stage A instead chooses to fold it into `UNAVAILABLE`, it **must** guarantee a distinct reason (`MODEL_UNAVAILABLE` vs `INPUT_INSUFFICIENT`) and justify the choice.
- Stage A must **state whether `ABSTAIN` is reachable at all in the current implementation.** If, with the present binary classifier, no prediction-layer rule can produce it, declare `ABSTAIN` as *defined-but-currently-unreachable* and forbid Stage B from synthesizing it artificially. Do not keep a status only to make the enum look complete, and do not delete a status merely to keep the count small.

**`PredictionReason`** — finer-grained than status; must reproduce every Prediction-layer row of §3.1 and every cause of §3.2. Provide a full code list with one-line meanings.

**`PredictionResult`** — dataclass and per-field contract:

| Field | Type | Contract |
|---|---|---|
| `status` | `PredictionStatus` | always present |
| `reason` | `PredictionReason` | always present, consistent with `status` |
| `direction` | `Optional[str]` | `BUY` / `SELL` / `NONE` — see §4.4 |
| `p_up` | `Optional[float]` | **0–1**, not percent |
| `p_down` | `Optional[float]` | **0–1** — **only if the model contract confirms it** (§4.4, P1-2); else `None`, never fabricated |
| `model_id` | `Optional[str]` | sourced from Phase 3.0 identity (§3.6) or `None` |
| `feature_contract_id` | `Optional[str]` | only when a verifiable identity exists; else `None` |
| `timestamp` | `datetime` | **timezone-aware UTC**, prediction time |
| `diagnostics` | `dict` | auxiliary only; never the sole carrier of truth (§4.1.1) |

For each field, define: presence requirement per status, and forbidden values.

#### 4.1.1 `diagnostics` boundary

- `status` / `reason` are **structured fields** and are the only authority on state.
- `diagnostics` holds **supplementary context only**.
- Downstream **must not** parse `diagnostics` strings to determine model state.
- Text inside `diagnostics` **must not** override or contradict `status` / `reason`.

#### 4.1.2 Legal and illegal state combinations

Enumerate allowed `status × field` combinations and list **forbidden** ones, including at minimum:

- `READY` **must** carry `direction ∈ {BUY, SELL}` and a valid `p_up`.
- `READY` + `direction == NONE` is **illegal**.
- `ABSTAIN` **must not** be usable as a directional vote; its `direction` is `NONE` or `null`.
- `NOT_RUN` / `UNAVAILABLE` / `INVALID` / `ERROR` **must not** expose a value a downstream could consume as a valid direction or a valid probability.
- `ERROR` **must not** fabricate a neutral vote or a default probability.

### 4.2 §2 Decision Contract Boundary

Define, explicitly and without implementing it, what belongs to the **Decision** layer (and, where applicable, a **Trade Plan** sub-layer):

| Concern | Layer | Source path |
|---|---|---|
| `raw_prob < min_prob` probability gate | Decision | §3.1 row 3 |
| MC filter BLOCK | Decision | row 4 |
| Regime filter BLOCK | Decision | row 5 |
| ADX filter BLOCK | Decision | row 6 |
| Pivot filter BLOCK | Decision | row 7 |
| StrengthGap filter BLOCK | Decision | row 8 |
| `conviction < min_conviction_score` | Decision | row 9 |
| SL/TP construction | Decision / Trade Plan | row 10 |
| R/R validity | Decision / Trade Plan | row 11 |
| produced `Signal` | Decision output | row 12 |

Requirements:

- The contract must state that **a valid `PredictionResult` does not imply a Decision accept**, and **a Decision reject does not imply an invalid prediction.**
- It must define a named boundary object for the Decision layer (e.g. `DecisionResult`) **at the type/boundary level only** — this Stage does not implement it. If Stage A chooses *not* to name it, it must still define the boundary explicitly and say why no separate object is needed yet.
- Include this worked example verbatim as the canonical illustration:

```
Model Prediction:
    direction = BUY
    p_up      = 0.61
    status    = READY

Strategy Decision:
    MC filter = BLOCK
    -> Decision REJECTED (Decision layer)
    -> Prediction remains READY (Prediction layer)
```

  The contract must state that representing the above `MC BLOCK` as `PredictionStatus.ABSTAIN` is **incorrect**.

### 4.3 §3 Legacy `generate_signal()` Mapping

Map **every** row of §3.1 line-anchored to `strategy_decision.py`, each with:

1. its **owning layer** (Prediction / Decision / Trade Plan / Decision output);
2. if Prediction → the `(status, reason)` pair;
3. if Decision/Trade Plan → the Decision-layer label, **not** a `PredictionStatus`;
4. what a consumer is permitted to do with it.

**Requirement: do NOT force every path into a `PredictionStatus`.** Only rows 1–2 (§3.1) are Prediction-layer. This table must make the split explicit and auditable.

### 4.4 §4 Consumer Contract, Unit Contract, Identity Contract

#### 4.4.1 Consumer contract

For **every** consumer in §3.4 (C-1, C-2, `attribution_v2/live_hook.py`, `should_close()`, `select_signals()`), state:

1. what it does today with `None` / missing fields;
2. what it is **required** to do to obtain an accurate picture of ML state;
3. what it is **forbidden** to do (implicit conversion of a non-`READY` status into a default probability, a default direction, or a synthesized valid vote).

The contract must make ML state **visible** and must **not** change trading behavior. Any behaviour change — especially at C-2 / Step 7 — is frozen and requires separate approval.

#### 4.4.2 Direction rule (P1-1)

| Status | Allowed `direction` |
|---|---|
| `READY` | **`BUY` or `SELL` only** |
| `ABSTAIN` | `NONE` or `null` |
| all other statuses | `NONE` or `null`; **must not** expose a consumer-usable direction |

Rationale to record: `READY` means "a valid directional prediction exists"; therefore `READY + NONE` must be declared illegal.

#### 4.4.3 Probability contract (P1-2)

- Canonical unit: **0–1** for both `p_up` and `p_down` (not percent).
- Validity checks **must** include `NaN`, `inf`, and range checks — a bare `0 <= p <= 1` comparison is insufficient (`NaN` fails every comparison silently).
- **`p_up` is the only confirmed probability** (§3.5).
- **`p_down` MUST NOT be assumed to equal `1 - p_up`.** It may be populated only after the model's class definition and output structure are confirmed. Until then `p_down` is `None` — never fabricated.
- If both are present, whether they must sum to 1 is a decision **based on the model's output definition**, not on field symmetry. Record the decision or record it as `NOT VERIFIED`.

#### 4.4.4 Unit conversion boundary (P1 / existing)

- Document the existing **percentage** representation in the MC cache (`mc_data["p_up"]`, `mc_data["p_down"]`, `percentile_rank`, see [L305–L318](file:///Users/liqin/projects/ai_training_cnn/strategy_decision.py#L305-L318) and [fx_trade_bot.py:2583](file:///Users/liqin/projects/ai_training_cnn/fx_trade_bot.py#L2583) where `mc_pct_up` defaults to `50.0`).
- Require **one explicit conversion at the new interface boundary**. Forbid implicit reinterpretation (e.g. treating `51.3` as `0.513` or vice-versa).
- **Do not modify the MC cache.**

#### 4.4.5 Identity and timestamp contract (P1-3)

- `timestamp`: **timezone-aware UTC**, recording when the prediction occurred.
- `model_id`: must come from a **verifiable Phase 3.0 identity** (§3.6) — **not** a filename and not a guessed version string.
- `feature_contract_id`: populate **only** if a verifiable feature-contract identity actually exists; otherwise `None`.
- If `ModelInitResult` does not provide a needed field, mark it **`NOT VERIFIED`**. Stage A must not invent an identity source.

### 4.5 §5 Phase 3.0 Interface

- **`ModelStatus` (Phase 3.0) and `PredictionStatus` (Phase 3.1) are two different layers and must NOT be merged into one enum.**
- Define how a Phase 3.0 `ModelInitResult` feeds the 3.1 `PredictionResult` (`model_id` / `feature_contract_id` / `UNAVAILABLE` handling), per §3.6.
- `ModelStatus` remains the authority on model availability; `PredictionStatus` describes the outcome of a single prediction attempt.

### 4.6 §6 Compatibility, Tests, Forbidden Boundaries

- **Legacy compatibility:** define the adapter seam (a single additive function/type at the boundary), how existing call sites keep working unmodified until Stage C is separately approved, how `attribution_v2/live_hook.py` and `should_close()` are handled, and whether `Signal` is extended or wrapped (state the choice and why).
- **Test matrix:** define the cases Stage D will implement, at minimum covering each Prediction-layer row of §3.1, each cause of §3.2, the `READY` happy path, the unit-conversion boundary, the "non-`READY` status is never silently converted to a valid vote" invariant, and the **layer-boundary** cases (a Decision reject must **not** produce a non-`READY` PredictionStatus). Mark which tests are runnable without the heavy inference stack (sklearn/xgboost/joblib) and which are dependency-gated.
- **Forbidden boundary (verbatim list):** Entry Authorization (Step 7), exit logic, SL/TP, position sizing, OANDA order flow, scheduler cadence, training target definitions, feature engineering, ML probability thresholds, MC scoring, Strength scoring, `FINAL` weights, and `docs/Development_plan.md`.

### 4.7 Decision Register (must be resolved, not left implicit)

Stage A **must decide each item and record the rationale.** Leaving any item "to be determined later" fails Stage A.

**Group A — layer ownership (the P0 corrections):**

| D-ID | Question | Required outcome |
|---|---|---|
| D-1 | Which §3.1 rows are Prediction-layer vs Decision-layer? | confirm/refine §3.3; rows 1–2 Prediction, 3–12 Decision/TradePlan |
| D-2 | Is `ABSTAIN` reachable in the current implementation? | state reachable / defined-but-unreachable; forbid synthesizing it |
| D-3 | Input-precondition failure (bars < 5): `NOT_RUN`, or `UNAVAILABLE` + `INPUT_INSUFFICIENT`? | pick one, justify |
| D-4 | Do Decision-layer rejections need a named boundary object now, or only a documented boundary? | pick one, justify |

**Group B — prediction-layer classification:**

| D-ID | Question | Expected |
|---|---|---|
| D-5 | `ScalerMissingError` at predict time → status? | `UNAVAILABLE` |
| D-6 | `InferenceFeatureError` / `DimensionMismatchError` → status? | `INVALID` (confirm the concrete exception sources) |
| D-7 | genuinely unexpected exception → status? | `ERROR` |

**Group C — field rules:**

| D-ID | Question | Expected |
|---|---|---|
| D-8 | Is `READY + NONE` legal? | illegal; `READY` ⇒ `BUY`/`SELL` |
| D-9 | Is `p_down` derivable now? | no — `None` until the model class contract is confirmed |
| D-10 | Are `model_id` / `feature_contract_id` sourceable from Phase 3.0 today? | record actual source or `NOT VERIFIED` |
| D-11 | Where does the MC-percentage ↔ 0–1 conversion happen? | one explicit boundary; MC cache unchanged |

Guiding principle: **`UNAVAILABLE` = the model cannot run; `NOT_RUN` = prediction never started; `ABSTAIN` = the prediction layer itself declined by rule; `INVALID` = the result cannot be trusted; `ERROR` = execution failed.** None of these may be collapsed back into a single ambiguous value — and none may absorb a **Decision**-layer rejection.

### 4.8 Design principle — Prediction ≠ Decision ≠ Authorization

Record as a first-class contract principle:

| Layer | Question | Phase 3.1 role |
|---|---|---|
| **Prediction** | What did the model predict? | defines this precisely |
| **Decision** | How does the strategy interpret and combine evidence? | boundary defined; behavior unchanged |
| **Authorization** | Is execution permitted? | **untouched, pending separate approval** |

A successful prediction does **not** imply the strategy should trade; a strategy direction does **not** imply authorization.

---

## 5. Acceptance criteria for Stage A

| ID | Criterion |
|---|---|
| A-01 | `docs/PHASE3_1_CONTRACT.md` exists and follows the six-section structure §4.1–§4.6 |
| A-02 | Every row of §3.1 / §3.2 / §3.3 is classified by **layer** with a source line reference; rows 3–12 are **not** mapped to `PredictionStatus` |
| A-03 | `ABSTAIN` is defined as Prediction-layer-only, and its reachability is stated |
| A-04 | `NOT_RUN` exists (or its rejection is justified with `MODEL_UNAVAILABLE` / `INPUT_INSUFFICIENT` split) |
| A-05 | `READY + NONE` is declared illegal; direction rules per status are tabulated |
| A-06 | `p_down` is not assumed equal to `1 − p_up`; probability checks include `NaN` / `inf` / range |
| A-07 | `timestamp` / `model_id` / `feature_contract_id` sources are stated; absent sources marked `NOT VERIFIED` |
| A-08 | `diagnostics` is declared auxiliary and non-authoritative |
| A-09 | The boundary object decision (D-4) is resolved with rationale |
| A-10 | All Decision Register items (D-1..D-11) are resolved with rationale |
| A-11 | Every consumer in §3.4 has stated current / required / forbidden behavior |
| A-12 | The worked example in §4.2 is present, and "MC BLOCK ⇒ PredictionStatus.ABSTAIN" is declared incorrect |
| A-13 | `ModelStatus` and `PredictionStatus` are declared separate layers (§4.5) |
| A-14 | The forbidden-boundary list (§4.6) is present verbatim |
| A-15 | **No `.py` file, and no file outside `docs/PHASE3_1_CONTRACT.md`, is modified** |
| A-16 | `docs/Development_plan.md` untouched; pre-existing unrelated changes preserved |
| A-17 | The statement **"Entry Authorization remains unchanged and unresolved."** appears verbatim |
| A-18 | No commit, no deployment |

---

## 6. Report format (return in the Stage A completion message)

1. Repository root / branch / `HEAD` before and after; `git status --short` before and after.
2. Confirmation that **no `.py` file was modified** (diff evidence).
3. The section list of `docs/PHASE3_1_CONTRACT.md`.
4. The resolved Decision Register (D-1..D-11) with a one-line rationale each.
5. Any row of §3.1/§3.2/§3.3/§3.4/§3.5/§3.6 that verification found **wrong or incomplete**, corrected.
6. Items that could **not** be determined from source, marked `NOT VERIFIED` — not guessed.
7. Remaining open questions for the reviewer, if any.

---

## 7. Execution rules

- Stage A is **documentation only**. Do not write the adapter; do not touch `strategy_decision.py`, `fx_trade_bot.py`, `fx_trade_bot_ml.py`, or `data_pipeline.py`.
- Do not re-run a broad repository audit. Restrict investigation to the prediction function and its consumers.
- Do not expand into Phase 3.2–3.6 or the Evaluation phase.
- Do not revisit accepted Phase 3.0 decisions.
- When a question cannot be answered from source, record `NOT VERIFIED` — never guess.
- Stop and report if the preflight (§2) does not match the expected target.

---

> ## Phase status
>
> | Phase | Goal | Status |
> |---|---|---|
> | Phase 3.0 | Runtime Containment | Implementation Complete — Verification Partial |
> | **Phase 3.1** | **Prediction Contract** | **Ready to Start (Stage A authorized; Stages B–D require separate approval)** |
> | Phase 3.2 | Feature / Inference Consistency | Pending |
> | Phase 3.3 | Training & Evaluation Integrity | Pending |
> | Phase 3.4 | Model Calibration & Validation | Pending |
> | Phase 3.5 | Shadow Evaluation | Pending |
> | Phase 3.6 | Controlled Activation | Pending |
>
> **Entry Authorization remains unchanged and unresolved.**
