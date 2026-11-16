# Phase 3.3 — Baseline Dataset & Model Report

**Document:** `docs/phase3_3/08_DATASET_AND_LABEL_SPECIFICATION.md` (DRAFT, `OPEN-01`–`OPEN-04b` FROZEN)
**Nature:** research baseline sanity run — **not** the Doc 09 experiment protocol; not an approval; no artifact written.

## 0. Run identity
- Python: 3.12.15
- numpy: 1.26.4 | pandas: 2.2.3
- xgboost: 2.0.3
- scikit-learn: 1.5.2
- instruments: `EUR_USD, USD_JPY`
- requested bars per instrument: 5000 | granularity: M15
- label fingerprint (sha256): `f496d9eda912db9e9e18aeb683a9db439377927816ed90c28f424bf68fb0c8b9`

## 1. Frozen parameters in force

| Decision | Value |
|---|---|
| `OPEN-01` target | binary, 1 = UP / 0 = NON-UP |
| `OPEN-02` horizon | 6 completed M15 bars |
| `OPEN-03` label | `Close_(t+6)/Close_t - 1 > 0.0` |
| `OPEN-04` eligibility | drop warm-up NaN rows; label present; 6 forward bars contiguous (no interpolation / ffill / bfill / fillna0 / gap pad) |
| `OPEN-04b` support | >= 1000 per class; majority share <= 70.00% |
| Feature Contract | frozen 33 `ORDERED_FEATURES`; FCID `FCV2-bffdb0005083f95e` |

## 2. Exclusion accounting (raw → eligible)

| instrument | raw | −unclosed | −warm-up NaN | −label/gap | eligible | UP | NON-UP |
|---|---|---|---|---|---|---|---|
| EUR_USD | 5000 | 1 | 95 | 72 | 4832 | 2288 | 2544 |
| USD_JPY | 5000 | 1 | 95 | 72 | 4832 | 2568 | 2264 |
| **TOTAL** | **10000** | **2** | **190** | **144** | **9664** | **4856** | **4808** |

Bucket priority: warm-up NaN first, then label-unavailable / non-contiguous; buckets are disjoint.

## 3. `OPEN-04b` support baseline

- smallest class: **4808** (threshold 1000) → **PASS**
- majority-class share: **50.25%** (cap 70.00%) → **PASS**

## 4. Baseline model (XGBoost) — sanity run only

- ordered 80/20 chronological holdout; CV = `TimeSeriesSplit(n_splits=5)` on the training portion.
- scaler is fit **fold-locally** (leakage-safe default); purge/embargo is Doc 09.
- total 9664 | train 7731 | test 1933 | split at 2026-11-01 23:45:00+00:00
- UP share — train 50.16% | test 50.59%

### Cross-validation (mean ± std over folds)

| metric | mean | std |
|---|---|---|
| accuracy | 0.5219 | 0.0238 |
| precision | 0.5252 | 0.0153 |
| recall | 0.4932 | 0.0812 |

| fold | n | accuracy | precision | recall |
|---|---|---|---|---|
| 1 | 1288 | 0.4837 | 0.5140 | 0.3785 |
| 2 | 1288 | 0.5349 | 0.5070 | 0.5977 |
| 3 | 1288 | 0.5241 | 0.5187 | 0.4590 |
| 4 | 1288 | 0.5116 | 0.5464 | 0.4575 |
| 5 | 1288 | 0.5551 | 0.5398 | 0.5735 |

### Holdout

- Accuracy: **0.4790** | Precision (UP): **0.4853** | Recall (UP): **0.4898**

| | predicted NON-UP | predicted UP |
|---|---|---|
| **actual NON-UP** | 447 | 508 |
| **actual UP** | 499 | 479 |

### Top 10 features by importance

| feature | importance |
|---|---|
| `utc_day_of_week` | 0.0407 |
| `horizon_vol_12h` | 0.0386 |
| `atr_ma` | 0.0383 |
| `horizon_vol_6h` | 0.0367 |
| `macd_signal` | 0.0360 |
| `atr` | 0.0352 |
| `dist_low_24h` | 0.0347 |
| `dist_high_24h` | 0.0343 |
| `dist_high_6h` | 0.0337 |
| `dist_high_12h` | 0.0337 |

## 5. Boundary

- Baseline sanity run only; no Doc 09 experiment protocol, no purge/embargo, no artifact, no live wiring.
- Outputs written only under `experiments/phase3_3_baseline/`.
- Instrument whitelist / pooled-vs-per-pair / dataset fingerprint remain `[PENDING DATA PROFILING SCAN]`.
