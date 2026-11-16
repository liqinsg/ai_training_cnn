# Phase 3.3 — Baseline Dataset & Model Report

**Document:** `docs/phase3_3/08_DATASET_AND_LABEL_SPECIFICATION.md` (DRAFT, `OPEN-01`–`OPEN-04b` FROZEN)
**Nature:** research baseline sanity run — **not** the Doc 09 experiment protocol; not an approval; no artifact written.

## 0. Run identity
- Python: 3.12.15
- numpy: 1.26.4 | pandas: 2.2.3
- xgboost: 2.0.3
- scikit-learn: 1.5.2
- instruments: `EUR_USD, GBP_USD, AUD_USD, USD_CHF, USD_JPY, GBP_JPY`
- requested bars per instrument: 5000 | granularity: M15
- label fingerprint (sha256): `9dbf82a708f3a70c520dd362874403fb34ceff2c1189f64d9e565d0ccd8d0dad`

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
| EUR_USD | 5000 | 1 | 95 | 72 | 4832 | 2289 | 2543 |
| GBP_USD | 5000 | 1 | 95 | 72 | 4832 | 2415 | 2417 |
| AUD_USD | 5000 | 1 | 95 | 72 | 4832 | 2345 | 2487 |
| USD_CHF | 5000 | 1 | 95 | 73 | 4831 | 2535 | 2296 |
| USD_JPY | 5000 | 1 | 95 | 72 | 4832 | 2567 | 2265 |
| GBP_JPY | 5000 | 1 | 95 | 72 | 4832 | 2503 | 2329 |
| **TOTAL** | **30000** | **6** | **570** | **433** | **28991** | **14654** | **14337** |

Bucket priority: warm-up NaN first, then label-unavailable / non-contiguous; buckets are disjoint.

## 3. `OPEN-04b` support baseline

- smallest class: **14337** (threshold 1000) → **PASS**
- majority-class share: **50.55%** (cap 70.00%) → **PASS**

## 4. Baseline model (XGBoost) — sanity run only

- ordered 80/20 chronological holdout; CV = `TimeSeriesSplit(n_splits=5)` on the training portion.
- scaler is fit **fold-locally** (leakage-safe default); purge/embargo is Doc 09.
- total 28991 | train 23192 | test 5799 | split at 2026-11-02 00:00:00+00:00
- UP share — train 50.94% | test 48.97%

### Cross-validation (mean ± std over folds)

| metric | mean | std |
|---|---|---|
| accuracy | 0.5137 | 0.0252 |
| precision | 0.5280 | 0.0391 |
| recall | 0.5204 | 0.0645 |

| fold | n | accuracy | precision | recall |
|---|---|---|---|---|
| 1 | 3865 | 0.4810 | 0.4920 | 0.4661 |
| 2 | 3865 | 0.4911 | 0.4864 | 0.6001 |
| 3 | 3865 | 0.5514 | 0.5705 | 0.4972 |
| 4 | 3865 | 0.5245 | 0.5786 | 0.4452 |
| 5 | 3865 | 0.5206 | 0.5124 | 0.5933 |

### Holdout

- Accuracy: **0.4961** | Precision (UP): **0.4879** | Recall (UP): **0.5824**

| | predicted NON-UP | predicted UP |
|---|---|---|
| **actual NON-UP** | 1223 | 1736 |
| **actual UP** | 1186 | 1654 |

### Top 10 features by importance

| feature | importance |
|---|---|
| `utc_hour` | 0.0418 |
| `utc_day_of_week` | 0.0393 |
| `horizon_vol_12h` | 0.0390 |
| `dist_high_6h` | 0.0377 |
| `horizon_vol_6h` | 0.0361 |
| `atr_pct` | 0.0354 |
| `dist_high_24h` | 0.0350 |
| `dist_low_24h` | 0.0346 |
| `rsi` | 0.0341 |
| `atr_ratio` | 0.0339 |

## 5. Boundary

- Baseline sanity run only; no Doc 09 experiment protocol, no purge/embargo, no artifact, no live wiring.
- Outputs written only under `experiments/phase3_3_baseline/`.
- Instrument whitelist / pooled-vs-per-pair / dataset fingerprint remain `[PENDING DATA PROFILING SCAN]`.
