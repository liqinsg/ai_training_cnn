# Phase 3.2 — P1/P2 Train–Inference Parity Report

**Experiment ID:** `PARITY-P1P2-01`  |  **Protocol:** Doc 03 §10 (preregistered 2026-11-16)
**Status:** OFFLINE EXPERIMENT OUTPUT — not an approval, not a freeze.

- Tolerance: `|A-B| <= atol + rtol*|B|`, atol=1e-10, rtol=1e-08 (A = training path, B = inference path)
- P1 and P2 are reported separately; neither substitutes for the other.
- Inference entry representation: bot ON-branch is source-verified to be a transform-free call into `ml.feature_contract.build_features` (Doc 03 §10.3 deviation).

## 0. Recorded identity
- git HEAD: `152cfcc951168bf3b599c5abb4929970b408b31f`
- git status (porcelain): `M docs/phase3_2/03_EXPERIMENT_AUTHORIZATION_AND_ACCEPTANCE.md
 M docs/phase3_2/05_TECHNICALLY_ELIGIBLE_CANDIDATE_FREEZE.md
 M retrain_model.py
 M tests/test_feature_contract.py
?? docs/phase3_2/PHASE3_2_HANDOVER.md
?? experiments/phase3_2_feature_convergence/PARITY_P1P2_REPORT.md
?? experiments/phase3_2_feature_convergence/parity_harness.py`
- Python: 3.12.15
- numpy: 1.26.4 | pandas: 2.2.3
- xgboost: 2.0.3
- tzdata: 2026.5
- pytz: 2026.1
- zoneinfo.TZPATH: ('/home/ubuntu/miniconda3/envs/ai-sprint/share/zoneinfo', '/home/ubuntu/miniconda3/envs/ai-sprint/share/tzinfo')

- Post-build cleaning chain identity (supporting): **SAME** — retrain_model.py=ok, fx_trade_bot.py=ok, fx_trade_bot_v685.py=ok

## P1 — raw OHLCV input consistency (invalid fixtures)

| # | case | training | inference | parity |
|---|---|---|---|---|
| 1 | duplicate_timestamp | REJECT(InputContractError) | REJECT(InputContractError) | PASS |
| 2 | non_monotonic_index | REJECT(InputContractError) | REJECT(InputContractError) | PASS |
| 3 | missing_column | REJECT(InputContractError) | REJECT(InputContractError) | PASS |
| 4 | non_finite_inf | REJECT(InputContractError) | REJECT(InputContractError) | PASS |
| 5 | non_finite_nan | REJECT(InputContractError) | REJECT(InputContractError) | PASS |
| 6 | non_positive_price | REJECT(InputContractError) | REJECT(InputContractError) | PASS |
| 7 | high_below_low | REJECT(InputContractError) | REJECT(InputContractError) | PASS |
| 8 | hl_not_bounding | REJECT(InputContractError) | REJECT(InputContractError) | PASS |
| 9 | naive_index | REJECT(InputContractError) | REJECT(InputContractError) | PASS |
| 10 | too_few_bars | REJECT(InputContractError) | REJECT(InputContractError) | PASS |
| 11 | empty_batch | REJECT(InputContractError) | REJECT(InputContractError) | PASS |

- **P1 verdict: PASS** (base fixture `varying`, sha256=aea6ffbd9cebe7ba…)

## P2 — raw feature-output consistency (valid fixtures, pre-scaling)

Per feature: full-frame comparison (all 800 rows). `max|A-B|` and `max allowed` are over the finite cells.

### Fixture `up`
- rows: 800  | sha256(OHLC): `868f2eaf590625066cc3b56e79fb647316b9a5995eec92fc67768c47f037fc3c`
- columns: True (33 == 33)

| feature | verdict | max|A-B| | max allowed |
|---|---|---|---|
| `return_15m` | PASS | 0.000e+00 | 1.018e-10 |
| `return_45m` | PASS | 0.000e+00 | 1.055e-10 |
| `return_90m` | PASS | 0.000e+00 | 1.109e-10 |
| `return_3h` | PASS | 0.000e+00 | 1.218e-10 |
| `log_return_15m` | PASS | 0.000e+00 | 1.018e-10 |
| `horizon_vol_3h` | PASS | 0.000e+00 | 1.000e-10 |
| `horizon_vol_6h` | PASS | 0.000e+00 | 1.000e-10 |
| `horizon_vol_12h` | PASS | 0.000e+00 | 1.000e-10 |
| `body` | PASS | 0.000e+00 | 1.018e-10 |
| `upper_wick` | PASS | 0.000e+00 | 1.057e-10 |
| `lower_wick` | PASS | 0.000e+00 | 1.067e-10 |
| `range` | PASS | 0.000e+00 | 1.108e-10 |
| `direction` | PASS | 0.000e+00 | 1.010e-08 |
| `atr` | PASS | 0.000e+00 | 1.064e-10 |
| `atr_pct` | PASS | 0.000e+00 | 1.052e-10 |
| `atr_ecdf_50bar` | PASS | 0.000e+00 | 1.010e-08 |
| `atr_ma` | PASS | 0.000e+00 | 1.062e-10 |
| `atr_above_sma14` | PASS | 0.000e+00 | 1.010e-08 |
| `atr_ratio` | PASS | 0.000e+00 | 1.185e-08 |
| `rsi` | PASS | 0.000e+00 | 1.000e-06 |
| `rsi_slope_45m` | PASS | 0.000e+00 | 1.000e-10 |
| `adx` | PASS | 0.000e+00 | 9.999e-07 |
| `macd` | PASS | 0.000e+00 | 1.140e-10 |
| `macd_signal` | PASS | 0.000e+00 | 1.140e-10 |
| `macd_hist` | PASS | 0.000e+00 | 1.019e-10 |
| `dist_high_6h` | PASS | 0.000e+00 | 1.057e-10 |
| `dist_low_6h` | PASS | 0.000e+00 | 1.497e-10 |
| `dist_high_12h` | PASS | 0.000e+00 | 1.057e-10 |
| `dist_low_12h` | PASS | 0.000e+00 | 1.923e-10 |
| `dist_high_24h` | PASS | 0.000e+00 | 1.057e-10 |
| `dist_low_24h` | PASS | 0.000e+00 | 2.764e-10 |
| `utc_hour` | PASS | 0.000e+00 | 2.301e-07 |
| `utc_day_of_week` | PASS | 0.000e+00 | 6.010e-08 |

### Fixture `down`
- rows: 800  | sha256(OHLC): `116f327daf01714783f31c37947f3ae41dab78bbbc446d019df45dd43fee07a8`
- columns: True (33 == 33)

| feature | verdict | max|A-B| | max allowed |
|---|---|---|---|
| `return_15m` | PASS | 0.000e+00 | 1.016e-10 |
| `return_45m` | PASS | 0.000e+00 | 1.048e-10 |
| `return_90m` | PASS | 0.000e+00 | 1.097e-10 |
| `return_3h` | PASS | 0.000e+00 | 1.193e-10 |
| `log_return_15m` | PASS | 0.000e+00 | 1.016e-10 |
| `horizon_vol_3h` | PASS | 0.000e+00 | 1.000e-10 |
| `horizon_vol_6h` | PASS | 0.000e+00 | 1.000e-10 |
| `horizon_vol_12h` | PASS | 0.000e+00 | 1.000e-10 |
| `body` | PASS | 0.000e+00 | 1.016e-10 |
| `upper_wick` | PASS | 0.000e+00 | 1.047e-10 |
| `lower_wick` | PASS | 0.000e+00 | 1.048e-10 |
| `range` | PASS | 0.000e+00 | 1.092e-10 |
| `direction` | PASS | 0.000e+00 | 1.010e-08 |
| `atr` | PASS | 0.000e+00 | 1.061e-10 |
| `atr_pct` | PASS | 0.000e+00 | 1.048e-10 |
| `atr_ecdf_50bar` | PASS | 0.000e+00 | 1.010e-08 |
| `atr_ma` | PASS | 0.000e+00 | 1.058e-10 |
| `atr_above_sma14` | PASS | 0.000e+00 | 1.010e-08 |
| `atr_ratio` | PASS | 0.000e+00 | 1.164e-08 |
| `rsi` | PASS | 0.000e+00 | 1.000e-10 |
| `rsi_slope_45m` | PASS | 0.000e+00 | 1.000e-10 |
| `adx` | PASS | 0.000e+00 | 1.000e-06 |
| `macd` | PASS | 0.000e+00 | 1.140e-10 |
| `macd_signal` | PASS | 0.000e+00 | 1.140e-10 |
| `macd_hist` | PASS | 0.000e+00 | 1.019e-10 |
| `dist_high_6h` | PASS | 0.000e+00 | 1.427e-10 |
| `dist_low_6h` | PASS | 0.000e+00 | 1.048e-10 |
| `dist_high_12h` | PASS | 0.000e+00 | 1.814e-10 |
| `dist_low_12h` | PASS | 0.000e+00 | 1.048e-10 |
| `dist_high_24h` | PASS | 0.000e+00 | 2.583e-10 |
| `dist_low_24h` | PASS | 0.000e+00 | 1.048e-10 |
| `utc_hour` | PASS | 0.000e+00 | 2.301e-07 |
| `utc_day_of_week` | PASS | 0.000e+00 | 6.010e-08 |

### Fixture `varying`
- rows: 800  | sha256(OHLC): `aea6ffbd9cebe7ba8bd962506f250764cf55169a6b5f11611cf5369d6d21e11c`
- columns: True (33 == 33)

| feature | verdict | max|A-B| | max allowed |
|---|---|---|---|
| `return_15m` | PASS | 0.000e+00 | 1.133e-10 |
| `return_45m` | PASS | 0.000e+00 | 1.263e-10 |
| `return_90m` | PASS | 0.000e+00 | 1.296e-10 |
| `return_3h` | PASS | 0.000e+00 | 1.401e-10 |
| `log_return_15m` | PASS | 0.000e+00 | 1.133e-10 |
| `horizon_vol_3h` | PASS | 0.000e+00 | 1.218e-10 |
| `horizon_vol_6h` | PASS | 0.000e+00 | 1.262e-10 |
| `horizon_vol_12h` | PASS | 0.000e+00 | 1.331e-10 |
| `body` | PASS | 0.000e+00 | 1.133e-10 |
| `upper_wick` | PASS | 0.000e+00 | 1.058e-10 |
| `lower_wick` | PASS | 0.000e+00 | 1.070e-10 |
| `range` | PASS | 0.000e+00 | 1.177e-10 |
| `direction` | PASS | 0.000e+00 | 1.010e-08 |
| `atr` | PASS | 0.000e+00 | 1.080e-10 |
| `atr_pct` | PASS | 0.000e+00 | 1.073e-10 |
| `atr_ecdf_50bar` | PASS | 0.000e+00 | 1.010e-08 |
| `atr_ma` | PASS | 0.000e+00 | 1.077e-10 |
| `atr_above_sma14` | PASS | 0.000e+00 | 1.010e-08 |
| `atr_ratio` | PASS | 0.000e+00 | 1.277e-08 |
| `rsi` | PASS | 0.000e+00 | 8.144e-07 |
| `rsi_slope_45m` | PASS | 0.000e+00 | 2.622e-07 |
| `adx` | PASS | 0.000e+00 | 5.764e-07 |
| `macd` | PASS | 0.000e+00 | 1.117e-10 |
| `macd_signal` | PASS | 0.000e+00 | 1.114e-10 |
| `macd_hist` | PASS | 0.000e+00 | 1.044e-10 |
| `dist_high_6h` | PASS | 0.000e+00 | 1.394e-10 |
| `dist_low_6h` | PASS | 0.000e+00 | 1.585e-10 |
| `dist_high_12h` | PASS | 0.000e+00 | 1.519e-10 |
| `dist_low_12h` | PASS | 0.000e+00 | 1.698e-10 |
| `dist_high_24h` | PASS | 0.000e+00 | 1.908e-10 |
| `dist_low_24h` | PASS | 0.000e+00 | 1.832e-10 |
| `utc_hour` | PASS | 0.000e+00 | 2.301e-07 |
| `utc_day_of_week` | PASS | 0.000e+00 | 6.010e-08 |

### Fixture `alternating`
- rows: 800  | sha256(OHLC): `3dcd026a64c7e97c6c0e8cb060ec27ee828dd3b62e759757a41903992674a94e`
- columns: True (33 == 33)

| feature | verdict | max|A-B| | max allowed |
|---|---|---|---|
| `return_15m` | PASS | 0.000e+00 | 1.073e-10 |
| `return_45m` | PASS | 0.000e+00 | 1.073e-10 |
| `return_90m` | PASS | 0.000e+00 | 1.000e-10 |
| `return_3h` | PASS | 0.000e+00 | 1.000e-10 |
| `log_return_15m` | PASS | 0.000e+00 | 1.073e-10 |
| `horizon_vol_3h` | PASS | 0.000e+00 | 1.263e-10 |
| `horizon_vol_6h` | PASS | 0.000e+00 | 1.364e-10 |
| `horizon_vol_12h` | PASS | 0.000e+00 | 1.509e-10 |
| `body` | PASS | 0.000e+00 | 1.073e-10 |
| `upper_wick` | PASS | 0.000e+00 | 1.059e-10 |
| `lower_wick` | PASS | 0.000e+00 | 1.074e-10 |
| `range` | PASS | 0.000e+00 | 1.154e-10 |
| `direction` | PASS | 0.000e+00 | 1.010e-08 |
| `atr` | PASS | 0.000e+00 | 1.123e-10 |
| `atr_pct` | PASS | 0.000e+00 | 1.112e-10 |
| `atr_ecdf_50bar` | PASS | 0.000e+00 | 1.010e-08 |
| `atr_ma` | PASS | 0.000e+00 | 1.119e-10 |
| `atr_above_sma14` | PASS | 0.000e+00 | 1.010e-08 |
| `atr_ratio` | PASS | 0.000e+00 | 1.105e-08 |
| `rsi` | PASS | 0.000e+00 | 5.186e-07 |
| `rsi_slope_45m` | PASS | 0.000e+00 | 4.056e-08 |
| `adx` | PASS | 0.000e+00 | 3.201e-07 |
| `macd` | PASS | 0.000e+00 | 1.013e-10 |
| `macd_signal` | PASS | 0.000e+00 | 1.010e-10 |
| `macd_hist` | PASS | 0.000e+00 | 1.006e-10 |
| `dist_high_6h` | PASS | 0.000e+00 | 1.132e-10 |
| `dist_low_6h` | PASS | 0.000e+00 | 1.146e-10 |
| `dist_high_12h` | PASS | 0.000e+00 | 1.132e-10 |
| `dist_low_12h` | PASS | 0.000e+00 | 1.146e-10 |
| `dist_high_24h` | PASS | 0.000e+00 | 1.132e-10 |
| `dist_low_24h` | PASS | 0.000e+00 | 1.146e-10 |
| `utc_hour` | PASS | 0.000e+00 | 2.301e-07 |
| `utc_day_of_week` | PASS | 0.000e+00 | 6.010e-08 |

### Fixture `adx_break`
- rows: 800  | sha256(OHLC): `5eaf24a832eff0f9952adccc309d9ca08083371fa145657834a23ff2369e7777`
- columns: True (33 == 33)

| feature | verdict | max|A-B| | max allowed |
|---|---|---|---|
| `return_15m` | PASS | 0.000e+00 | 1.026e-10 |
| `return_45m` | PASS | 0.000e+00 | 1.078e-10 |
| `return_90m` | PASS | 0.000e+00 | 1.156e-10 |
| `return_3h` | PASS | 0.000e+00 | 1.311e-10 |
| `log_return_15m` | PASS | 0.000e+00 | 1.026e-10 |
| `horizon_vol_3h` | PASS | 0.000e+00 | 1.071e-10 |
| `horizon_vol_6h` | PASS | 0.000e+00 | 1.101e-10 |
| `horizon_vol_12h` | PASS | 0.000e+00 | 1.143e-10 |
| `body` | PASS | 0.000e+00 | 1.018e-10 |
| `upper_wick` | PASS | 0.000e+00 | 1.055e-10 |
| `lower_wick` | PASS | 0.000e+00 | 1.054e-10 |
| `range` | PASS | 0.000e+00 | 1.101e-10 |
| `direction` | PASS | 0.000e+00 | 1.010e-08 |
| `atr` | PASS | 0.000e+00 | 1.058e-10 |
| `atr_pct` | PASS | 0.000e+00 | 1.051e-10 |
| `atr_ecdf_50bar` | PASS | 0.000e+00 | 1.010e-08 |
| `atr_ma` | PASS | 0.000e+00 | 1.054e-10 |
| `atr_above_sma14` | PASS | 0.000e+00 | 1.010e-08 |
| `atr_ratio` | PASS | 0.000e+00 | 2.082e-07 |
| `rsi` | PASS | 0.000e+00 | 1.000e-06 |
| `rsi_slope_45m` | PASS | 0.000e+00 | 5.001e-07 |
| `adx` | PASS | 0.000e+00 | 1.000e-06 |
| `macd` | PASS | 0.000e+00 | 1.210e-10 |
| `macd_signal` | PASS | 0.000e+00 | 1.210e-10 |
| `macd_hist` | PASS | 0.000e+00 | 1.049e-10 |
| `dist_high_6h` | PASS | 0.000e+00 | 1.599e-10 |
| `dist_low_6h` | PASS | 0.000e+00 | 1.486e-10 |
| `dist_high_12h` | PASS | 0.000e+00 | 2.224e-10 |
| `dist_low_12h` | PASS | 0.000e+00 | 1.914e-10 |
| `dist_high_24h` | PASS | 0.000e+00 | 3.474e-10 |
| `dist_low_24h` | PASS | 0.000e+00 | 2.759e-10 |
| `utc_hour` | PASS | 0.000e+00 | 2.301e-07 |
| `utc_day_of_week` | PASS | 0.000e+00 | 6.010e-08 |

## Summary

- P1 (invalid-fixture accept/reject parity): **PASS**
- P2 (raw feature-output parity, all fixtures × all features): **PASS**
- Post-build cleaning chain identity (supporting): SAME
- Both ON-branches resolve to the single shared implementation `ml/feature_contract.build_features`; parity is therefore a property of routing identity + determinism of that function.
- **`FULL_PARITY_STATUS` remains `NOT VERIFIED`**: P3–P5 (scaler / tensor / prediction-output) require an active model / scaler / `.features.json` bundle that is not in the repository. P3–P5 are not marked pass/waived/`NOT REQUIRED`.
