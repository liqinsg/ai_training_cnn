# Phase 3.3 — Experiment Execution Plan

**Document ID:** `PHASE3_3_EXPERIMENT_EXECUTION_PLAN`
**Date:** 2026-11-16
**Revision:** R4 — protocol freeze for Demo preparation (Owner-accepted 2026-11-16). See §15.8.
**Status:** `FROZEN (experimental protocol) — OWNER-ACCEPTED 2026-11-16 for Demo preparation` · inference validity remains `NOT VERIFIED — provisional`
**Nature:** Preregistration of the Phase 3.3 predictive-value experiment design — *how* the Doc 08 dataset is split, evaluated and verified. Not a model-implementation specification and **not** an authorization.
**Upstream:** `06_RESEARCH_CONTRACT.md` (§4–§11), `07_OWNER_DECISION_REGISTER.md`, `08_DATASET_AND_LABEL_SPECIFICATION.md`; frozen freeze record `docs/phase3_2/05_TECHNICALLY_ELIGIBLE_CANDIDATE_FREEZE.md`.

---

## 0. Prior-value convention

Per Owner delegation (2026-11-16) the Agent assigns **explicit priors** to the design parameters that were still `OPEN`, so the experiment is specified end-to-end without inventing anything silently.

| Tag | Meaning |
|---|---|
| `FROZEN (Owner)` | Owner-frozen value; must not be altered here |
| `PRIOR (Agent-proposed)` | A preregistered default proposed by the Agent. **Not** an Owner decision. Frozen *for the run*, Owner-overridable **before** execution, and **never** changed after results are inspected |
| `OPEN (out of scope here)` | Belongs to another document (`OPEN-08` → Doc 11/14, `OPEN-09` → Doc 13) |

Every prior below is labelled and traceable; §12 collects them in one register. A prior is a *default*, not an approval.

**Object-level glossary (used throughout, not interchangeable):**

| Term | Definition | Primary comparison |
|---|---|---|
| **Standalone predictive value** | Predictive performance of a model using **only** the candidate | `{c}` vs **B0** |
| **Incremental value** | Improvement from **adding** the candidate to a fixed reference set that does **not** contain it | **B2** vs **B1** |
| **Marginal contribution** | Degradation from **removing** the candidate from the full set | **B4** vs **B3** |
| **Generalisation** | Whether any of the above holds out of time and across instruments | holdout / LOPO (`06` §8) |

These four quantities answer different questions and are reported separately; no one of them implies another (`06` §1).

## 1. Purpose and scope

Doc 09 answers: *given the Doc 08 dataset, how do we measure whether a candidate carries predictive value, and how do we prove the measurement is trustworthy?*

**In scope:** dataset splitting and purge/embargo (`OPEN-05`), cross-instrument evaluation policy (`OPEN-07`), primary/diagnostic metric selection (`OPEN-06`), the baseline comparison matrix, fold and holdout discipline, multiple-comparison control and statistical inference, robustness protocol, reproducibility record, stop conditions.

**Out of scope:** target / horizon / label / sample eligibility (`OPEN-01`–`OPEN-04b`, **inherited from Doc 08, unchanged**); transaction costs (`OPEN-08`, Doc 11/14); the `SELECTED` evidence threshold (`OPEN-09`, Doc 13).

## 2. Inherited frozen constraints (must not be altered)

| Item | Value | Source |
|---|---|---|
| Prediction target | binary — `1` = UP, `0` = NON-UP | Doc 08 §3 (`OPEN-01` FROZEN) |
| Horizon | 6 completed M15 bars | Doc 08 §4 (`OPEN-02` FROZEN) |
| Label | `Close_(t+6)/Close_t - 1 > 0` | Doc 08 §5 (`OPEN-03` FROZEN) |
| Eligibility | strict; warm-up NaN dropped row-wise; no interpolation / ffill / bfill / fillna0 / gap pad | Doc 08 §6 (`OPEN-04` FROZEN) |
| Support baseline | ≥ 1,000 per class; majority share ≤ 70% | Doc 08 §7 (`OPEN-04b` FROZEN) |
| Label span (information overlap) | **H = 6 bars** | Doc 08 §5 |
| Feature set | frozen 33-column `ORDERED_FEATURES`; order and definitions unchanged | `ml/feature_contract.py` |
| Feature Contract Identity | `FCV2-bffdb0005083f95e` | `00` §2 |
| Excluded (2) | `vol_sma_ratio`, `vol_trend` | `01` §3 |
| Deferred (2) | `is_london`, `is_ny` | `01` §4 |
| Parity | P1 PASS · P2 PASS · P3–P5 `NOT VERIFIED`; `FULL_PARITY_STATUS = NOT VERIFIED` | `00` §2 / `05` §8 |

Doc 09 redefines no frozen feature, modifies no FCID, and changes no Doc 08 decision. **H = 6 bars is frozen and is the numerical input to every purge rule below.**

## 3. Research unit and evaluation structure

**Research unit** = one evaluation of a **(candidate × target × instrument universe × fold)** combination against a declared baseline. Scores are reported at this granularity; no aggregation may conceal an unstable or weak unit.

Evaluation matrices (from `06` §5), each run under the single split from §4 and the baseline matrix from §6:

| Matrix | Purpose | Establishes | Baseline mapping |
|---|---|---|---|
| Feature-level (one candidate alone) | standalone predictive performance | screening signal only | `{c}` vs **B0a** |
| Feature-group (family: return / vol / candle / ATR / RSI / ADX / MACD / distance / time) | family contribution | family-level value | `group` vs **B0a** (own family) |
| Incremental addition | incremental value | the primary inclusion criterion | **B2** vs **B1** |
| Ablation (drop-one / drop-group from the full 33) | marginal value in the presence of others | per-feature necessity | **B4** vs **B3** |
| Redundancy (pairwise / collinear structure) | duplicated value | duplication, not worthlessness | diagnostic |
| Combined subsets | interaction effects | not causal attribution | **B4** vs subset |

**Reporting rule:** every tested unit is reported individually, including failures. **Screening (standalone), incremental value and generalisation must not be conflated** — a candidate with strong standalone AUC but zero incremental value is reported as such.

## 4. Data splitting, purge and embargo (`OPEN-05`)

### 4.1 Split axis and definitions

| Element | Value | Tag |
|---|---|---|
| Split axis | the **global eligible timestamp grid** `T` (pooled across instruments, sorted, unique) — every instrument is cut at the same wall-clock stamps | `FROZEN` (06 §4) |
| Final holdout | **last 20%** of `T`, chronological, inspected **once** | `PRIOR` |
| Development period | `T` minus the holdout = first 80% | derived |
| Fold scheme | **expanding-window walk-forward, K = 5 folds** over the development period | `PRIOR` |
| Initial training seed | first **30%** of the development period (training-only; never evaluated) | `PRIOR` |
| Purge | **H = 6 bars**, applied **trailing** (before each test window) | `PRIOR` (structurally mandatory = label span) |
| Embargo | **0 bars** | `PRIOR` (revised — see §4.4) |
| Total train/test separation per fold boundary | **6 bars (90 min)** — purge only, **not** purge + embargo | `PRIOR` (revised from 12) |
| Fold-local preprocessing | scaler / encoder fit **on the train fold only** | `FROZEN` (06 §4) |

All index quantities are **integer half-open intervals** `[start, end)` over the **timestamp grid**: the start position is included, the end position is excluded. All arithmetic is on integer *positions* in `T`, i.e. on **unique eligible timestamps** — **never** on pooled row counts. Each timestamp position is then mapped to each instrument's rows by timestamp value (§4.7).

### 4.2 Exact index construction (deterministic)

```
n_T        = len(T)
n_holdout  = floor(0.20 * n_T)
dev        = T[0 : n_T - n_holdout]                 # development period
D          = len(dev)
seed_len   = floor(0.30 * D)                         # initial training seed length
edges      = round_to_int(linspace(seed_len, D, K+1))# K=5 → 6 edges, monotone, edges[0]=seed_len, edges[K]=D
test_k     = [edges[k-1], edges[k])                  # k = 1..K  (contiguous, disjoint, cover dev[seed_len:D])
```

- **Coverage:** the union of `test_1..test_5` equals **all** of `dev[seed_len:D]` (the last 70% of the development period). The first 30% (`dev[0:seed_len]`) is the training seed and is **never** evaluated. This is stated explicitly so that "full coverage" is unambiguous.
- **Contiguity / overlap:** test windows are contiguous and **non-overlapping** (`edges[k] == edges[k-1]` chains), and `edges[K] = D` closes the dev period.
- **Expanding train window for fold k:**

```
purge          = H = 6
train_k        = [0, edges[k-1] - purge)             # expands with k; ends 6 bars before the test window
test_k_usable  = [edges[k-1], edges[k])
if k == K:  test_k_usable = [edges[k-1], edges[k] - purge)   # §4.3 dev/holdout boundary purge
```

- **Time, not rows.** `edges[]` are positions in the **unique-timestamp grid `T`**; they are **not** pooled row indices. Splitting by pooled row count is rejected because instruments have unequal row counts and must share the same wall-clock boundaries.
- **Timestamp → instrument mapping (§4.7):** a row belongs to fold window `[edges[k-1], edges[k])` iff that row's timestamp position in `T` lies in the window. A fold's test set is the union, over instruments, of their rows in that window.

### 4.3 Purge semantics (what is removed)

| Boundary | Rule | Removed samples |
|---|---|---|
| Each fold train/test boundary `edges[k-1]` | drop training rows whose **label window** `[i, i+H]` reaches into the test window: `i + H >= edges[k-1]` | the **last H = 6** rows of the expanding train set |
| Development / holdout boundary | drop the **last H = 6 unique development timestamps** from the development evaluation (i.e. the tail of `test_5`) | dev samples whose label window reaches into the holdout period |

Rationale: the label at row `i` uses information up to `i + H` (`08` §5). Any training row whose label window overlaps the test span would leak test-period information; the trailing purge of exactly `H` rows removes precisely those rows. Causal **feature look-back** (e.g. `dist_high_24h` uses up to 96 bars of *past* data) is **not** leakage and needs no purge.

### 4.4 Embargo semantics (why embargo = 0)

- In a **strictly expanding** walk-forward scheme, **every** training sample precedes **every** test sample in its fold: `train_k = [0, edges[k-1]-H)` lies entirely in the past of `test_k`. There is **no post-test training data** in any fold, so the classic embargo (which guards training observations *following* a test window against serial-correlation leakage) has **no eligible samples to remove**.
- The only leakage channel at a fold boundary is **train-label ↔ test-window overlap**, which is fully covered by the `H = 6` trailing purge (§4.3). Purge and embargo are **not additive** here; the earlier "6 + 6 = 12 bars" was an unjustified sum and is corrected to **6 bars**.
- Therefore the revised prior is **embargo = 0 bars**. If the Owner prefers a conservative buffer against residual feature autocorrelation, set `embargo E > 0`; the effect is to enlarge the trailing removal to `H + E` bars at each boundary. The default prior is `E = 0` because it is structurally unnecessary under §4.

### 4.5 Boundary test cases (worked example)

Toy dev period `D = 800`, `K = 5`, `seed_len = floor(0.30·800) = 240`, `H = 6`:

| Fold | test window (timestamps) | purge | train window |
|---|---|---|---|
| 1 | `[240, 352)` | 6 | `[0, 234)` |
| 2 | `[352, 464)` | 6 | `[0, 346)` |
| 3 | `[464, 576)` | 6 | `[0, 458)` |
| 4 | `[576, 688)` | 6 | `[0, 570)` |
| 5 | `[688, 794)` (last 6 dropped: `[794, 800)` reaches into holdout) | 6 | `[0, 682)` |

Assertions an implementation must satisfy:
1. `edges[0] == seed_len` and `edges[K] == D`.
2. `edges` is strictly increasing; every `test_k` is non-empty.
3. `union(test_k) == [seed_len, D)`.
4. `max(train_k) < min(test_k_usable)` and `min(test_k_usable) - max(train_k) - 1 >= H`.
5. No training label window `[i, i+H]` intersects any test window (given the purge).
6. Holdout timestamps appear in **no** train or test set of any fold.

### 4.6 Holdout discipline

- The holdout is the last 20% of `T` **by unique-timestamp position**, disjoint from every fold's train and test set (§4.5 assertion 6).
- The **last `H = 6` unique development timestamps are excluded from the development evaluation**, so that **no development sample's label window uses a price inside the holdout**. This exclusion is enforced by **timestamp position**, not by row count.
- The holdout is **invisible during model selection**: candidate selection, feature selection, hyperparameter choices, calibration and the inference procedure are all fixed **before** the holdout is opened.
- The holdout is evaluated **once**, after selection is frozen. No candidate may be selected or rescued using holdout results (resolves the `C-01` conflict recorded in `07` §6).
- Holdout features use **only past data** (causal look-back), so opening the holdout introduces no look-ahead.

### 4.7 Instrument mapping, missing timestamps and empty folds

The split is defined on the global timestamp grid, so cross-instrument boundaries are identical (§4.1). Mapping rules:

1. **Mapping.** A data row `(instrument, timestamp)` belongs to fold window `w` iff `timestamp ∈ T[edges[k-1]:edges[k]]` for that window. Each instrument's rows are assigned independently by timestamp value.
2. **Missing timestamps.** A timestamp at which an instrument has **no eligible row** (holiday, halt, gap, or dropped by Doc 08 §6) contributes **no** sample for that instrument. Gaps are **never** imputed or forward-filled (Doc 08 §6 / FD-09).
3. **Instrument with no rows in a fold.** Reported as `NO_SAMPLES_IN_FOLD` for that fold; its **per-pair metric there is `undefined`** (not `0`, not skipped silently). The instrument is **not** dropped from the run.
4. **Empty test window.** A fold whose test window is empty across **all** instruments ⇒ `BLOCKED` (§11).
5. **No instrument is added or removed** by the split; the universe is the Doc 08 whitelist (`[PENDING DATA PROFILING SCAN]`).

## 5. Cross-instrument evaluation policy (`OPEN-07`)

| Element | Value | Tag |
|---|---|---|
| Primary policy | **pooled training + per-pair metric reporting** | `PRIOR` |
| Per-pair requirement | a candidate is valuable only if the primary metric holds **per pair**, not only in the pool | `PRIOR` |
| Generalisation gate | **leave-one-pair-out (LOPO)** over the universe | `PRIOR` |
| Shared-timestamp isolation | enforced by the single global time cut (§4.1): all instruments share the fold boundaries | `FROZEN` (06 §4) |

Rules:

- Currency pairs are **not** statistically independent; a pooled score must never be read as independent replication.
- A **generalisation claim** (Q5, `06` §1) is made **only** if LOPO holds; otherwise the disposition is at most `CONDITIONAL`.
- LOPO reuses the **same** global fold boundaries (§4): for each held-out pair, training uses all other pairs and the identical `train_k / test_k` index windows.
- The evaluation instrument set is **resolved** (Owner 2026-11-16): the **intersection** of the `mc_data.yml` `pairs` list and the `config_bot.py` whitelist (`forex_pairs.json` `WHITELIST` buckets ∪ `DEFAULT_PAIRS`, normalised to OANDA-native names). That intersection is **13 pairs**: `AUD_JPY, EUR_JPY, GBP_JPY, USD_JPY, AUD_USD, EUR_USD, GBP_USD, USD_CHF, GBP_AUD, EUR_CHF, AUD_CHF, GBP_CHF, EUR_AUD`. `mc_data.yml` symbols outside the whitelist are excluded by construction (Demo loader, §4.7). Dataset identity (period, final candle, `sha256`) remains per-run evidence (§10).

## 6. Baseline comparison matrix (revised)

A candidate's value is defined **only** relative to declared baselines, measured **out of time** under the §4 split. The matrix below replaces the earlier self-contradictory definition (where `B1` already contained the candidate, so `B1 + candidate` added nothing).

| ID | Model | Feature set | Tag | Establishes |
|---|---|---|---|---|
| **B0a** | majority-class constant | none | `PRIOR` | floor reference; constant prediction ⇒ **ROC-AUC = 0.5** exactly (no discrimination) |
| **B0b** | persistence | none (uses past prices only; no training) | `PRIOR` | floor reference under a momentum/persistence rule (see §6.0) |
| **B1** | reference model | fixed reference set **R** (see §6.1) | `PRIOR` | performance of a fixed, non-candidate reference |
| **B2** | reference + candidate | `R ∪ {c}` | `PRIOR` | **incremental value** of `c` |
| **B3** | full model − candidate | all 33 features minus `{c}` | `PRIOR` | ablation input |
| **B4** | full model | all 33 features | `PRIOR` | **marginal contribution** reference |

Model class: to isolate *feature value* from *model capacity*, **B1–B4 use the same learner** (logistic regression with fold-local `StandardScaler`) unless an Owner-approved protocol specifies otherwise. **B0a / B0b are model-free** (§6.0).

Derived quantities:

| Quantity | Formula | Interpretation |
|---|---|---|
| Standalone predictive value of `c` | `metric({c}) − metric(B0a)` | screening only |
| Value of `c` beyond persistence | `metric({c}) − metric(B0b)` | screening vs the persistence floor |
| **Incremental value of `c`** | `metric(B2) − metric(B1)` = `metric(R ∪ {c}) − metric(R)`, **only for `c ∉ R`** | the primary inclusion criterion |
| **Marginal contribution of `c`** | `metric(B4) − metric(B3)` = `metric(F) − metric(F \ {c})`, `F` = all 33 | necessity in the presence of others |
| Group value (family `g`) | `metric(group g) − metric(B0a)` | family-level screening |

**Consistency rule (resolves the old contradiction):**
1. `B2` is **genuinely incremental** only when `c ∉ R`; the construction guarantees a new feature is added.
2. `B3` **genuinely removes** `c`; for `c ∈ R` the ablation is still well-defined because `B3` drops `c` from the full 33-set, not from `R`.
3. For a candidate `c ∈ R` — here **exactly `return_15m`** — the **forward incremental test (`B2` vs `B1`) is `N/A by construction`** and is reported as **`N/A (c ∈ R)`**, never as `0`. Such a candidate is evaluated by **standalone value** (`{c}` vs `B0a` / `B0b`) and **marginal contribution** (`B4` vs `B3`) only, and both results are **retained**. This is the reason `R` is deliberately kept to a single feature (§6.1).

### 6.0 B0 sub-baselines (majority-class ≠ persistence)

The two floors are **separate baselines** and must not be conflated:

| ID | Rule | Expected AUC |
|---|---|---|
| **B0a** majority-class constant | predict the training-fold majority class with a constant probability for every test row | **0.5 exactly** (constant scores ⇒ all ties) |
| **B0b** persistence | deterministic, **no training**: `label_t = 1` iff the last **realized** `H=6`-bar return `Close_t / Close_{t-6} − 1 > 0`, else `0` (tie ⇒ `0`) | `> 0.5` only if the 6-bar direction persists |

- `B0a` establishes whether the target is learnable **beyond base rates**; `B0b` establishes whether the naive **momentum/persistence** rule already explains part of the signal. They answer different questions and both are reported.
- A candidate's *standalone value* is measured against **B0a**; its *value beyond persistence* is measured against **B0b**.
- **Metrics under ties.** For `B0a`, accuracy equals the majority-class share and ROC-AUC is `0.5`; threshold diagnostics (precision / recall) use the majority-class label. For `B0b`, predictions are hard labels; AUC uses the implied `{0,1}` scores.
- `B0b`'s exact rule is a `PRIOR` (`PRIOR-B1`, §12); it uses **only past prices** at decision time `t` (`Close_t`, `Close_{t-6}`), so it is leakage-free.

### 6.1 Reference feature set `R` — `PRIOR-R1`

No upstream document defines a reference feature set for `B1` (`06` §5 names a "simple reference baseline" but lists no features). Per the revision instruction, this is assigned an **explicit prior** rather than invented silently.

| Field | Value |
|---|---|
| **Prior ID** | `PRIOR-R1` (Agent-proposed; **not** an upstream `OPEN` item) |
| **Value** | `R = {return_15m}` — the single shortest-horizon return feature |
| **Source** | Frozen 33-column `ORDERED_FEATURES` (`ml/feature_contract.py`); family partition in `01` §2 / freeze record §3 |
| **Rationale** | `return_15m` is the most elementary, lowest-order, no-lookback predictor (classic naive momentum/mean-reversion reference). It defines a floor any candidate must beat, needs no rolling window (minimal warm-up), and is a single feature so the degenerate `c ∈ R` set is bounded to exactly one candidate. |
| **Alternatives considered** | (a) empty set → reduces `B1` to `B0`, losing incremental meaning; (b) candle-geometry family `{body, upper_wick, lower_wick, range, direction}` → larger degenerate set; (c) the return family → 5 features, larger degenerate set. |
| **Owner override** | *(blank — pending)* |

If the Owner supplies a different reference set, `B1`/`B2` are recomputed with it before execution; `PRIOR-R1` is a default, not an approval.

**Note — `R` is itself a candidate.** `return_15m` is one of the 33 candidates, so it can have **no** forward incremental test against `R` (`B2` would equal `B1`). Its incremental result is recorded **`N/A (c ∈ R)`**, and it is evaluated by **standalone value** (`{c}` vs `B0a` / `B0b`) and **marginal contribution** (`B4` vs `B3`) only, both retained (§6 consistency rule 3).

## 7. Metrics (`OPEN-06`)

| Role | Metric | Tag |
|---|---|---|
| **Primary** | **ROC-AUC** — fold mean ± std, reported pooled **and per pair**, and per baseline (B0–B4) | `PRIOR` |
| **Co-primary (calibration)** | **log-loss**, with a reliability curve, whenever probabilistic outputs are consumed | `PRIOR` |
| Incremental | **ΔAUC** (primary) and Δlog-loss vs the declared baseline | `PRIOR` |
| Diagnostic | accuracy, precision, recall, Brier score, rank IC, pre-cost directional hit rate | `PRIOR` |

Rules (from `06` §6):

- Primary and co-primary metrics are **fixed across all compared candidates** and preregistered; diagnostic metrics support interpretation only.
- Metrics must **not** be selected because they yield favourable results.
- Probability-based claims require calibration reporting.
- **Calibration belongs to the model-training pipeline, if used at all.** Any calibrator (e.g. Platt scaling / isotonic) is fit **fold-locally on the training fold only** (via internal CV within that fold). A calibrator must **never** be fit on the test fold or the holdout, and the test set must never be used to fit or tune it. If the learner is already probabilistic (plain logistic regression), **no** post-hoc calibrator is applied and log-loss / Brier reflect the raw model probabilities.
- log-loss, Brier score and the reliability curve are computed on **out-of-fold predictions only**; the calibration procedure is a `PRIOR` (`PRIOR-C1`, §12).
- **No acceptance threshold is set here.** The minimum evidence for `SELECTED` is `OPEN-09` → out of scope (Doc 13). This document defines *how* metrics are measured, not *when* a candidate passes.

## 8. Multiple-comparison control and statistical inference

Selection-bias risk **R4** (`06` §7). Two separate obligations: (a) honest reporting of everything tested, (b) a defensible inference procedure.

### 8.1 Reporting obligations (non-negotiable)

- Record **every** tested candidate and **every** tested combination, including failed and abandoned experiments (no silent pruning).
- Never report only the best-performing combination.
- Not repeatedly tune against the final holdout.
- Not apply post-hoc threshold adjustment to rescue a weak candidate.
- Priors (§0, §12) are frozen before execution and never changed after results are inspected.

### 8.2 Hypothesis families (multiplicity is controlled per family)

| Family | Hypotheses | Size | Control | Tag |
|---|---|---|---|---|
| **F1** | per-candidate incremental value (`B2 > B1`) and marginal contribution (`B4 > B3`) | ≤ 33 candidates × 2 contrasts | **BH-FDR q = 0.05** within F1 | `PRIOR` |
| **F2** | feature-**group** value (9 families) | 9 | **BH-FDR q = 0.05** within F2 | `PRIOR` |
| **F3** | **combined-subset** effects | declared per run | **BH-FDR q = 0.05** within F3 | `PRIOR` |

Rules:
- F1, F2 and F3 are **separate** families: they answer different questions under different null hypotheses, so mixing them into one FDR pool is inappropriate. Each is controlled at its own `q = 0.05`; a **global BH across all families** is additionally reported as a conservative cross-check.
- Feature groups and combined subsets therefore **do not** share a family with per-candidate tests.
- The total number of tested hypotheses (the trial budget) is recorded, so the family definitions are auditable.

### 8.3 Inference procedure (autocorrelation-aware)

Temporally dependent observations must **not** be treated as independent samples. Proposed procedure (`PRIOR`, provisional):

| Element | Procedure | Tag |
|---|---|---|
| Resampling unit | **contiguous time blocks on the global grid `T`** — never individual rows | `PRIOR` |
| Cross-instrument sampling | a sampled block is **synchronized across instruments**: every instrument's rows whose timestamp falls in the block are drawn **together**, preserving contemporaneous cross-pair dependence (essential — pairs are not independent, §5) | `PRIOR` |
| Block length | `L_b = 2·H = 12 bars` — a **prior, not a validated dependence length**; sensitivity must be reported at `{6, 12, 24, 48}` bars | `PRIOR` |
| Point estimate | fold mean of the primary metric over the K = 5 folds (± std) | `PRIOR` |
| Cross-fold aggregation | the metric is recomputed **within each fold** from that fold's resampled blocks, then aggregated as the **K-fold mean**; folds are **not** pooled into one i.i.d. sample | `PRIOR` |
| Replicates | `B = 2,000` bootstrap replicates (CI/p-value resolution ≈ 1/B) | `PRIOR` |
| Confidence interval | percentile bootstrap CI (95%) over the K-fold mean | `PRIOR` |
| p-value (incremental) | **paired** block bootstrap of `ΔAUC = metric(B2) − metric(B1)` on the **same** blocks; preregistered one-sided H1: `ΔAUC > 0`; `p = P(ΔAUC* ≤ 0)` | `PRIOR` |
| p-value (marginal) | paired block bootstrap of `metric(B4) − metric(B3)`, one-sided `> 0` | `PRIOR` |
| Fold-level view | report per-fold ΔAUC dispersion; a fold-level paired test is **not** used as primary (K = 5 dependent folds is too few) | `PRIOR` |
| Reporting | raw `p`, BH-adjusted `p`, `q`-value, CI, per-fold ΔAUC, effect size, and the decision | `PRIOR` |

Rules:
- **BH-FDR input validity.** BH-FDR assumes its input p-values are **valid** (uniform under the null). Block-bootstrap p-values are only as valid as `L_b`: if `L_b` under-covers the true autocorrelation, the p-values are **anti-conservative** and BH-FDR inherits that bias. Hence `L_b` is a prior **to be validated by the reported length-sensitivity**, and adjusted results are reported but flagged (caveat below).
- **Synchronized sampling is mandatory** (see table row): sampling instruments independently would break the contemporaneous dependence structure and invalidate pooled inference.
- **Trial budget.** The number of tested hypotheses per family (F1/F2/F3) is recorded so the BH input size is auditable (§8.2).

**Validity caveat (fail-closed on certainty):** the finite-sample accuracy of the block bootstrap under the true dependence structure is **itself not yet established**. Therefore:

- Only **effect sizes, confidence intervals and fold dispersion** are reported as computed.
- Any **statistical-significance** claim — **including BH-FDR adjusted p-values** — carries the prefix **`NOT VERIFIED — provisional`** until the Owner accepts the inference procedure (or a replacement).
- If no defensible procedure is available for a comparison, the affected conclusion is marked **`NOT VERIFIED`** rather than asserting certainty (per the revision instruction).

## 9. Robustness protocol

| Dimension | Requirement |
|---|---|
| Out-of-time stability | primary metric holds on later, unseen folds |
| Cross-pair stability | holds per pair and under LOPO (§5) |
| Market-regime sensitivity | **no regime definitions are invented**; the taxonomy is not Owner-approved → unsatisfied cases return `CONDITIONAL` / `BLOCKED`, never a fabricated regime |
| Cost sensitivity | **deferred to `OPEN-08` / Doc 11**; until then every practical-value claim is labelled **pre-cost only** |
| Feature-distribution drift | monitor train→test distribution shift per feature |
| Fold-to-fold variation | report variance across folds, never a single number |

## 10. Reproducibility and evidence record

Per `06` §10, every experiment records:

1. Git commit and branch; dirty/clean status.
2. Environment and dependency versions (Python, numpy, pandas, scikit-learn, xgboost, `tzdata`, `pytz`).
3. Dataset identity and source (instruments, period, final candle, input `sha256`, Doc 08 §10 fingerprint).
4. Label-specification identity (Doc 08).
5. Feature Contract Identity (`FCV2-bffdb0005083f95e`).
6. Experiment configuration (protocol version, universe, splits, seeds, priors from §12).
7. Random seeds (learner + bootstrap).
8. Fold boundaries: `n_T`, `n_holdout`, `seed_len`, `edges[]`, per-fold purge, embargo, and the dev/holdout boundary.
9. Metrics and outputs (raw + multiplicity-adjusted).
10. Exact execution command.
11. Artifact `sha256` for all research outputs.

**Research artifacts are stored separately from production artifacts**; no writes to the production bundle path; research outputs are never published as production artifacts.

## 11. Stop / blocked conditions

Stop — or mark `BLOCKED` — the affected experiment if (`06` §11, Doc 08):

- the prediction target or label definition is unresolved;
- a dataset-integrity check fails;
- a leakage control (§4) fails;
- a baseline is not reproducible;
- the feature identity is missing or incompatible (FCID mismatch / non-contract input);
- sample support fails the Doc 08 §7 gate;
- the fold structure cannot be reproduced deterministically (§4.2 / §4.5 assertions);
- any unauthorized production or live-system modification would be required.

**Fail closed:** a failed prerequisite yields `STOP` / `BLOCKED`, never a silent fallback.

## 12. Owner decisions and priors

`OPEN-05`, `OPEN-06`, `OPEN-07` are filled with Agent-proposed priors per the §0 delegation. Prerequisite items A1–A7 (`07` §4 / `06` §14) remain **NOT PROVIDED** and are unaffected by this document.

| Decision | Question | Prior value | Tag | Rationale | Owner override |
|---|---|---|---|---|---|
| `OPEN-05` | Purge / embargo duration | purge = **6 bars** (trailing); embargo = **0 bars**; total separation = **6 bars**; holdout = last **20%**; folds = **5**; initial train seed = **30%** of dev | `PRIOR` | purge = label span (H = 6, Doc 08 §5); embargo = 0 because expanding walk-forward has no post-test training data (§4.4) | *(blank — pending)* |
| `OPEN-06` | Primary evaluation metric | **ROC-AUC** (primary) · **log-loss** (co-primary calibration) · ΔAUC (incremental) | `PRIOR` | threshold-free, prevalence-invariant for a binary probabilistic classifier; calibration complements it | *(blank — pending)* |
| `OPEN-07` | Cross-pair evaluation policy | **pooled training + per-pair reporting**, generalisation gated by **LOPO** | `PRIOR` | keeps sample size while forcing cross-pair stability; LOPO is the honest generalisation test | *(blank — pending)* |
| `PRIOR-R1` | Reference feature set for `B1` | **`R = {return_15m}`** | `PRIOR` (no upstream `OPEN` item) | elementary, no-lookback naive reference; minimal degenerate set (§6.1) | *(blank — pending)* |
| `PRIOR-B1` | B0b persistence rule | last realized `H=6`-bar return sign (`Close_t/Close_{t-6}−1 > 0` ⇒ UP; tie ⇒ `0`) | `PRIOR` | deterministic, no-training persistence floor (§6.0) | *(blank — pending)* |
| `PRIOR-C1` | Probability calibration | fold-local, train-fold only (internal CV); **none** if the learner is already probabilistic | `PRIOR` | prevents test/holdout-fitted calibrators (§7) | *(blank — pending)* |
| `PRIOR-I1` | Bootstrap settings | `B = 2,000`; blocks synchronized across instruments; `L_b` sensitivity `{6,12,24,48}` | `PRIOR` | CI/p-value resolution vs cost (§8.3) | *(blank — pending)* |
| `OPEN-08` | Transaction costs | — | `OPEN (out of scope here)` | Doc 11/14 | *(blank)* |
| `OPEN-09` | Minimum evidence for `SELECTED` | — | `OPEN (out of scope here)` | Doc 13 | *(blank)* |

**Owner-provided run decisions (2026-11-16)** — supplied with the Demo-preparation authorization (§15.8). These are **Owner decisions**, not Agent priors:

| Item | Value | Tag | Effect |
|---|---|---|---|
| Instrument universe | `mc_data.yml` `pairs` ∩ `config_bot.py` whitelist, OANDA-native = **13 pairs** (§5) | `FROZEN (Owner)` | fixes the `OPEN-07` evaluation set |
| Compute budget | Oracle VM: **4 vCPU / 24 GB RAM** | `FROZEN (Owner)` | bounds `B`, learner choice; forbids a global grid search |
| Training policy | training allowed **only** as an in-fold single fit + internal-CV, train-fold-only calibration (§7); **no** global hyper-parameter grid search | `FROZEN (Owner)` | consistent with the §6 learner and §7 calibration rules |

The `PRIOR` rows above remain Agent-proposed defaults: they are **frozen for the run once execution begins** and Owner-overridable **only before** execution. They are **not** relabelled as Owner-approved values.

Creating this plan (or freezing its protocol) authorizes nothing. Execution still requires a separate, explicit Owner authorization naming datasets, universe, compute, trial budget, and whether any training is permitted (`06` §14, `07` §4).

## 13. Relation to the baseline sanity run

`phase3_3_baseline.py` produces a **baseline sanity run** on the Doc 08 dataset using a simple 80/20 chronological split + `TimeSeriesSplit(5)`. It is a *pipeline validation*, **not** this protocol: it applies no purge/embargo, reports no multiplicity adjustment, defines no reference set, and makes no value claim. This document supersedes it for any Phase 3.3 research conclusion.

## 14. Status and boundary

- **Status:** `FROZEN (experimental protocol) — OWNER-ACCEPTED 2026-11-16 for Demo preparation` (Revision R4). Inference validity remains `NOT VERIFIED — provisional` (§8.3).
- All `PRIOR` values are **Agent-proposed defaults**, not Owner decisions; each is Owner-overridable before execution and frozen once the run begins. Freezing the *protocol* does **not** convert priors into Owner-approved values.
- This document authorizes **nothing**: no dataset generation, no training, no artifact writes, no `USE_FEATURE_CONTRACT_V2` default-ON, no READY / live-hook wiring, no deployment, no trading-behavior change (`04_AUTHORIZATION_BOUNDARY.md`, `06` §2/§14). The Owner-provided run decisions (§12) scope the *Demo* only; they are **not** an execution authorization.
- No document `00`–`08` and no source code is modified by this plan.

## 15. Revision log and change report

### 15.0 Revision history

| Rev | Scope |
|---|---|
| **R1** | Initial draft with `FROZEN / PRIOR / OPEN` convention |
| **R2** | Targeted correction: baseline matrix, purge/embargo semantics, executable fold structure, statistical inference |
| **R3** | Targeted review round: B0 split, timestamp-based splitting/isolation, inference & calibration detail |
| **R4** | **Protocol freeze for Demo preparation**: Owner acceptance recorded; instrument universe and compute/training constraints fixed (§12, §15.8) |

### 15.1 Change summary (R2)

| # | Issue | Section(s) changed | What changed |
|---|---|---|---|
| P0-1 | `B1` internal contradiction (already contained the candidate) | §3, §6, §6.1, §0 glossary | Replaced with explicit **B0–B4** matrix; defined reference set `R` (`PRIOR-R1`); separated standalone / incremental / marginal; added `c ∈ R` handling |
| P0-2 | Purge/embargo treated as additive | §4.3, §4.4, §4.5, §12 | Purge = trailing `H = 6`; embargo = **0** (justified); total separation 12 → **6**; added index math + boundary test cases |
| P1-1 | Fold structure underspecified | §4.1, §4.2, §4.5 | Added initial train seed (30%), deterministic `edges[]` construction, coverage/overlap rules, time-axis diagram, numeric toy example |
| P1-2 | Inference/multiplicity incomplete | §8.2, §8.3 | Added family definitions F1–F3, block-bootstrap CI/p-value procedure, autocorrelation handling, reporting format, `NOT VERIFIED` fail-closed caveat |
| — | Consistency review | §0, §7, §11, §14 | Added object glossary; stated no acceptance threshold (OPEN-09); added fold-reproducibility stop condition |

### 15.2 Before/after table for changed priors (R2)

| Prior | Before (R1) | After (R2) | Reason |
|---|---|---|---|
| Purge | 6 bars | 6 bars (trailing, one-sided) | unchanged value; semantics now explicit |
| Embargo | 6 bars | **0 bars** | structurally unnecessary under expanding walk-forward (§4.4) |
| Total separation | 12 bars | **6 bars** | purge + embargo are not additive |
| Holdout | last 20% | last 20% | unchanged |
| Folds | 5 walk-forward | 5 walk-forward | unchanged (now fully specified) |
| Initial train seed | *(undefined)* | **30% of dev** | new, makes fold 1 trainable |
| `OPEN-06` metric | ROC-AUC / log-loss / ΔAUC | same | unchanged |
| `OPEN-07` policy | pooled + per-pair + LOPO | same | unchanged |
| Reference set `R` | *(implicit = all 33; contradictory)* | **`{return_15m}`** (`PRIOR-R1`) | new, resolves P0-1 |

### 15.3 Unresolved issues (carried forward, not silently closed)

1. `PRIOR-R1` reference set is Agent-proposed; Owner may override.
2. Inference procedure (§8.3) is provisional; significance claims remain `NOT VERIFIED` until the procedure is accepted.
3. Block length `L_b` and the `K = 5` / seed `30%` / holdout `20%` choices are priors, not data-derived.
4. Instrument whitelist and dataset identity remain `[PENDING DATA PROFILING SCAN]` (Doc 08 §10).
5. `C-01` / `C-02` conflicts in `06` remain recorded in `07` §6 and are **not** edited here.
6. `OPEN-08` / `OPEN-09` are out of scope (Doc 11/14 / Doc 13).

### 15.4 Confirmations (R2 and R3)

- **Docs `00`–`08` and source code are unchanged** by these revisions.
- **No training, experiment, or Demo was executed.** These revisions are documentation only.
- Every proposed value remains explicitly labelled `PRIOR`; **nothing is marked `OWNER APPROVED`.**
- No upstream frozen decision (`H = 6`, FCID, 33-column contract, Doc 08 label) was altered. `STOP` was not triggered.

### 15.5 Change summary (R3)

| # | Review point | Section(s) changed | What changed |
|---|---|---|---|
| 1 | B0: majority-class ≠ persistence | §3, §6, §6.0 | Split single `B0` into **B0a** (majority-class constant, AUC = 0.5) and **B0b** (deterministic persistence rule, `PRIOR-B1`); standalone vs beyond-persistence comparisons separated |
| 2 | `R` is itself a candidate | §6 consistency rule 3, §6.1 | Made explicit: `return_15m ∈ R` ⇒ incremental = **`N/A (c ∈ R)`** (never `0`); standalone + ablation retained |
| 3 | Split by pooled rows, not timestamps | §4.1, §4.2, §4.7 | Splitting defined on the **unique-timestamp grid `T`**; added timestamp→instrument mapping, missing-timestamp policy, `NO_SAMPLES_IN_FOLD`, empty-fold `BLOCKED` |
| 4 | Holdout contamination at the dev tail | §4.3, §4.6 | Last `H = 6` **unique development timestamps** excluded from development evaluation; holdout invisibility during model selection stated explicitly |
| 5 | Bootstrap under-specified | §8.3 | Added resampling unit, **synchronized cross-instrument sampling**, `B = 2,000`, cross-fold aggregation, BH-FDR input-validity rule; `L_b = 12` flagged as an unvalidated prior |
| 6 | Calibration pipeline ambiguity | §7 | Calibration is fold-local (train-fold only, internal CV); never test/holdout-fitted; none if the learner is already probabilistic; out-of-fold-only metrics |

### 15.6 Prior changes introduced/confirmed (R3)

| Prior | R2 | R3 | Reason |
|---|---|---|---|
| `B0` | single model (majority / persistence) | **split → B0a + B0b** | different baselines, different AUC behaviour |
| `PRIOR-B1` persistence rule | *(undefined)* | last realized `H=6`-bar return sign | new, makes B0b deterministic & leakage-free |
| `PRIOR-C1` calibration | *(undefined)* | fold-local train-fold only | new, prevents test-fitted calibrators |
| `PRIOR-I1` bootstrap `B` | *(undefined)* | `2,000` | new, fixes CI/p-value resolution |
| Split unit | timestamp grid (implied) | **explicitly** unique timestamps + mapping rules | removes pooled-row ambiguity |
| `L_b = 12` | presented as block length | flagged **prior, not validated**; sensitivity required | avoids presenting it as a verified dependence length |
| Purge / embargo / holdout / folds / seed | 6 / 0 / 20% / 5 / 30% | unchanged | R2 values retained |

### 15.7 Unresolved issues (R3, carried forward)

1. `L_b` is a prior, **not** a validated autocorrelation length; block-bootstrap and BH-FDR outputs remain `NOT VERIFIED — provisional`.
2. `B0b` persistence rule (`PRIOR-B1`) and calibration policy (`PRIOR-C1`) are Agent-proposed; Owner may override.
3. `PRIOR-R1` reference set still Agent-proposed (unchanged from R2).
4. Instrument **universe** resolved in R4 (§5 = 13 pairs); **dataset identity** (period, final candle, `sha256`) remains per-run evidence (Doc 08 §10).
5. `06` `C-01` / `C-02` remain recorded in `07` §6 and are **not** edited here.
6. `OPEN-08` / `OPEN-09` remain out of scope (Doc 11/14 / Doc 13).

### 15.8 Freeze record (R4)

- **Owner acceptance:** 2026-11-16 — the experimental protocol (splits, purge/embargo, baselines B0a/B0b/B1–B4, metrics, families, calibration, reporting) is **frozen** for Demo preparation.
- **Owner-provided run decisions fixed** (§12): instrument universe = 13 pairs (`mc_data.yml` ∩ `config_bot.py` whitelist); compute budget = 4 vCPU / 24 GB; training = in-fold single fit + train-fold-only calibration, **no** global grid search.
- **Not frozen / still open:** the inference procedure's *validity* (`L_b` is an unvalidated prior → all significance output stays `NOT VERIFIED — provisional`); `PRIOR-R1` / `PRIOR-B1` / `PRIOR-C1` remain Agent priors; `06` `C-01` / `C-02` untouched; `OPEN-08` / `OPEN-09` out of scope.
- **Authorizes nothing.** This freeze enables *Demo preparation* only — building the harness. Running the Demo (fetching OANDA data, in-fold training, writing research outputs) requires a **separate explicit Owner execution authorization** naming dataset, universe, compute, trial budget, and permitted training (`06` §14, `07` §4).
- Docs `00`–`08` and source code remain unchanged by this revision.

**Freeze note:** freezing the protocol does **not** freeze the inference procedure's validity — significance claims stay `NOT VERIFIED — provisional` until the block-bootstrap procedure is itself validated.
