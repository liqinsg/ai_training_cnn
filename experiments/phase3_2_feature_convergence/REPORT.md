# Phase 3.2 Step 4 — History-Length Convergence Report

**Status:** OFFLINE EXPERIMENT OUTPUT — not an approval, not a freeze.

- History lengths: `[200, 300, 500, 800]`
- Main acceptance pairs: `[(300, 500), (500, 800)]`  |  Diagnostic pairs: `[(200, 300), (200, 500), (200, 800)]`
- Tolerance: `|A-B| <= atol + rtol*|B|`, atol=1e-10, rtol=1e-08 (B = longer history)
- Contract under test: proposed Feature Contract (Doc 02 §2/§3, Revision Plan §6). Not production code.

## 0. ADX break/reseed unit check
- result: **PASS** — seed@27=30.000000, gap@44=nan, reseed@58=50.000000, step@59=50.000000

## Fixture `up`
- rows: 800  | sha256(OHLC): `868f2eaf590625066cc3b56e79fb647316b9a5995eec92fc67768c47f037fc3c`
- final candle: `2026-01-13T07:45:00+00:00`

### Main acceptance (300v500, 500v800)

| feature | class | 300v500 | 500v800 | verdict |
|---|---|---|---|---|
| `return_15m` | E | PASS | PASS | PASS |
| `return_45m` | E | PASS | PASS | PASS |
| `return_90m` | E | PASS | PASS | PASS |
| `return_3h` | E | PASS | PASS | PASS |
| `log_return_15m` | E | PASS | PASS | PASS |
| `horizon_vol_3h` | E | PASS | PASS | PASS |
| `horizon_vol_6h` | E | PASS | PASS | PASS |
| `horizon_vol_12h` | E | PASS | PASS | PASS |
| `body` | E | PASS | PASS | PASS |
| `upper_wick` | E | PASS | PASS | PASS |
| `lower_wick` | E | PASS | PASS | PASS |
| `range` | E | PASS | PASS | PASS |
| `direction` | E | PASS | PASS | PASS |
| `dist_high_6h` | E | PASS | PASS | PASS |
| `dist_low_6h` | E | PASS | PASS | PASS |
| `dist_high_12h` | E | PASS | PASS | PASS |
| `dist_low_12h` | E | PASS | PASS | PASS |
| `dist_high_24h` | E | PASS | PASS | PASS |
| `dist_low_24h` | E | PASS | PASS | PASS |
| `utc_hour` | E | PASS | PASS | PASS |
| `utc_day_of_week` | E | PASS | PASS | PASS |
| `atr` | R | PASS | PASS | PASS |
| `atr_pct` | R | PASS | PASS | PASS |
| `atr_ecdf_50bar` | R | PASS | PASS | PASS |
| `atr_ma` | R | PASS | PASS | PASS |
| `atr_above_sma14` | R | PASS | PASS | PASS |
| `atr_ratio` | R | PASS | PASS | PASS |
| `rsi` | R | PASS | PASS | PASS |
| `rsi_slope_45m` | R | PASS | PASS | PASS |
| `macd` | R | PASS | PASS | PASS |
| `macd_signal` | R | PASS | PASS | PASS |
| `macd_hist` | R | PASS | PASS | PASS |
| `adx` | R | PASS | PASS | PASS |

### Diagnostic pairs (final-candle |A-B|)

| feature | 200v300 | 200v500 | 200v800 |
|---|---|---|---|
| `return_15m` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `return_45m` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `return_90m` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `return_3h` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `log_return_15m` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `horizon_vol_3h` | 8.830e-19 | 6.795e-17 | 9.789e-17 |
| `horizon_vol_6h` | 3.031e-18 | 1.004e-17 | 6.129e-17 |
| `horizon_vol_12h` | 7.992e-18 | 4.143e-17 | 1.930e-16 |
| `body` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `upper_wick` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `lower_wick` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `range` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `direction` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `dist_high_6h` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `dist_low_6h` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `dist_high_12h` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `dist_low_12h` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `dist_high_24h` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `dist_low_24h` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `utc_hour` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `utc_day_of_week` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `atr` | 2.287e-11 | 2.288e-11 | 2.288e-11 |
| `atr_pct` | 1.816e-11 | 1.816e-11 | 1.816e-11 |
| `atr_ecdf_50bar` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `atr_ma` | 3.870e-11 | 3.871e-11 | 3.871e-11 |
| `atr_above_sma14` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `atr_ratio` | 9.451e-08 | 9.454e-08 | 9.454e-08 |
| `rsi` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `rsi_slope_45m` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `macd` | 5.577e-10 | 5.580e-10 | 5.580e-10 |
| `macd_signal` | 8.202e-10 | 8.205e-10 | 8.205e-10 |
| `macd_hist` | 2.625e-10 | 2.626e-10 | 2.626e-10 |
| `adx` | 5.780e-05 | 5.781e-05 | 5.781e-05 |

## Fixture `down`
- rows: 800  | sha256(OHLC): `116f327daf01714783f31c37947f3ae41dab78bbbc446d019df45dd43fee07a8`
- final candle: `2026-01-13T07:45:00+00:00`

### Main acceptance (300v500, 500v800)

| feature | class | 300v500 | 500v800 | verdict |
|---|---|---|---|---|
| `return_15m` | E | PASS | PASS | PASS |
| `return_45m` | E | PASS | PASS | PASS |
| `return_90m` | E | PASS | PASS | PASS |
| `return_3h` | E | PASS | PASS | PASS |
| `log_return_15m` | E | PASS | PASS | PASS |
| `horizon_vol_3h` | E | PASS | PASS | PASS |
| `horizon_vol_6h` | E | PASS | PASS | PASS |
| `horizon_vol_12h` | E | PASS | PASS | PASS |
| `body` | E | PASS | PASS | PASS |
| `upper_wick` | E | PASS | PASS | PASS |
| `lower_wick` | E | PASS | PASS | PASS |
| `range` | E | PASS | PASS | PASS |
| `direction` | E | PASS | PASS | PASS |
| `dist_high_6h` | E | PASS | PASS | PASS |
| `dist_low_6h` | E | PASS | PASS | PASS |
| `dist_high_12h` | E | PASS | PASS | PASS |
| `dist_low_12h` | E | PASS | PASS | PASS |
| `dist_high_24h` | E | PASS | PASS | PASS |
| `dist_low_24h` | E | PASS | PASS | PASS |
| `utc_hour` | E | PASS | PASS | PASS |
| `utc_day_of_week` | E | PASS | PASS | PASS |
| `atr` | R | PASS | PASS | PASS |
| `atr_pct` | R | PASS | PASS | PASS |
| `atr_ecdf_50bar` | R | PASS | PASS | PASS |
| `atr_ma` | R | PASS | PASS | PASS |
| `atr_above_sma14` | R | PASS | PASS | PASS |
| `atr_ratio` | R | PASS | PASS | PASS |
| `rsi` | R | PASS | PASS | PASS |
| `rsi_slope_45m` | R | PASS | PASS | PASS |
| `macd` | R | PASS | PASS | PASS |
| `macd_signal` | R | PASS | PASS | PASS |
| `macd_hist` | R | PASS | PASS | PASS |
| `adx` | R | PASS | PASS | PASS |

### Diagnostic pairs (final-candle |A-B|)

| feature | 200v300 | 200v500 | 200v800 |
|---|---|---|---|
| `return_15m` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `return_45m` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `return_90m` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `return_3h` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `log_return_15m` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `horizon_vol_3h` | 2.716e-18 | 4.822e-18 | 1.801e-16 |
| `horizon_vol_6h` | 6.430e-18 | 1.327e-17 | 2.362e-17 |
| `horizon_vol_12h` | 7.897e-18 | 3.649e-18 | 4.502e-17 |
| `body` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `upper_wick` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `lower_wick` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `range` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `direction` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `dist_high_6h` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `dist_low_6h` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `dist_high_12h` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `dist_low_12h` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `dist_high_24h` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `dist_low_24h` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `utc_hour` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `utc_day_of_week` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `atr` | 5.700e-12 | 5.701e-12 | 5.701e-12 |
| `atr_pct` | 4.596e-12 | 4.597e-12 | 4.597e-12 |
| `atr_ecdf_50bar` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `atr_ma` | 9.644e-12 | 9.646e-12 | 9.646e-12 |
| `atr_above_sma14` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `atr_ratio` | 2.186e-08 | 2.186e-08 | 2.186e-08 |
| `rsi` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `rsi_slope_45m` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `macd` | 5.577e-10 | 5.580e-10 | 5.580e-10 |
| `macd_signal` | 8.202e-10 | 8.205e-10 | 8.205e-10 |
| `macd_hist` | 2.625e-10 | 2.626e-10 | 2.626e-10 |
| `adx` | 1.409e-06 | 1.428e-06 | 1.428e-06 |

## Fixture `varying`
- rows: 800  | sha256(OHLC): `aea6ffbd9cebe7ba8bd962506f250764cf55169a6b5f11611cf5369d6d21e11c`
- final candle: `2026-01-13T07:45:00+00:00`

### Main acceptance (300v500, 500v800)

| feature | class | 300v500 | 500v800 | verdict |
|---|---|---|---|---|
| `return_15m` | E | PASS | PASS | PASS |
| `return_45m` | E | PASS | PASS | PASS |
| `return_90m` | E | PASS | PASS | PASS |
| `return_3h` | E | PASS | PASS | PASS |
| `log_return_15m` | E | PASS | PASS | PASS |
| `horizon_vol_3h` | E | PASS | PASS | PASS |
| `horizon_vol_6h` | E | PASS | PASS | PASS |
| `horizon_vol_12h` | E | PASS | PASS | PASS |
| `body` | E | PASS | PASS | PASS |
| `upper_wick` | E | PASS | PASS | PASS |
| `lower_wick` | E | PASS | PASS | PASS |
| `range` | E | PASS | PASS | PASS |
| `direction` | E | PASS | PASS | PASS |
| `dist_high_6h` | E | PASS | PASS | PASS |
| `dist_low_6h` | E | PASS | PASS | PASS |
| `dist_high_12h` | E | PASS | PASS | PASS |
| `dist_low_12h` | E | PASS | PASS | PASS |
| `dist_high_24h` | E | PASS | PASS | PASS |
| `dist_low_24h` | E | PASS | PASS | PASS |
| `utc_hour` | E | PASS | PASS | PASS |
| `utc_day_of_week` | E | PASS | PASS | PASS |
| `atr` | R | PASS | PASS | PASS |
| `atr_pct` | R | PASS | PASS | PASS |
| `atr_ecdf_50bar` | R | PASS | PASS | PASS |
| `atr_ma` | R | PASS | PASS | PASS |
| `atr_above_sma14` | R | PASS | PASS | PASS |
| `atr_ratio` | R | PASS | PASS | PASS |
| `rsi` | R | PASS | PASS | PASS |
| `rsi_slope_45m` | R | PASS | PASS | PASS |
| `macd` | R | PASS | PASS | PASS |
| `macd_signal` | R | PASS | PASS | PASS |
| `macd_hist` | R | PASS | PASS | PASS |
| `adx` | R | PASS | PASS | PASS |

### Diagnostic pairs (final-candle |A-B|)

| feature | 200v300 | 200v500 | 200v800 |
|---|---|---|---|
| `return_15m` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `return_45m` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `return_90m` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `return_3h` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `log_return_15m` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `horizon_vol_3h` | 0.000e+00 | 2.168e-19 | 1.518e-18 |
| `horizon_vol_6h` | 8.674e-19 | 8.674e-19 | 1.735e-18 |
| `horizon_vol_12h` | 4.337e-19 | 1.301e-18 | 4.337e-19 |
| `body` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `upper_wick` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `lower_wick` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `range` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `direction` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `dist_high_6h` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `dist_low_6h` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `dist_high_12h` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `dist_low_12h` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `dist_high_24h` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `dist_low_24h` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `utc_hour` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `utc_day_of_week` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `atr` | 3.077e-11 | 3.080e-11 | 3.080e-11 |
| `atr_pct` | 2.766e-11 | 2.768e-11 | 2.768e-11 |
| `atr_ecdf_50bar` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `atr_ma` | 5.207e-11 | 5.211e-11 | 5.211e-11 |
| `atr_above_sma14` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `atr_ratio` | 9.777e-08 | 9.785e-08 | 9.785e-08 |
| `rsi` | 9.163e-06 | 9.161e-06 | 9.161e-06 |
| `rsi_slope_45m` | 2.220e-06 | 2.220e-06 | 2.220e-06 |
| `macd` | 2.661e-10 | 2.662e-10 | 2.662e-10 |
| `macd_signal` | 3.913e-10 | 3.915e-10 | 3.915e-10 |
| `macd_hist` | 1.252e-10 | 1.253e-10 | 1.253e-10 |
| `adx` | 1.547e-04 | 1.548e-04 | 1.548e-04 |

## Fixture `alternating`
- rows: 800  | sha256(OHLC): `3dcd026a64c7e97c6c0e8cb060ec27ee828dd3b62e759757a41903992674a94e`
- final candle: `2026-01-13T07:45:00+00:00`

### Main acceptance (300v500, 500v800)

| feature | class | 300v500 | 500v800 | verdict |
|---|---|---|---|---|
| `return_15m` | E | PASS | PASS | PASS |
| `return_45m` | E | PASS | PASS | PASS |
| `return_90m` | E | PASS | PASS | PASS |
| `return_3h` | E | PASS | PASS | PASS |
| `log_return_15m` | E | PASS | PASS | PASS |
| `horizon_vol_3h` | E | PASS | PASS | PASS |
| `horizon_vol_6h` | E | PASS | PASS | PASS |
| `horizon_vol_12h` | E | PASS | PASS | PASS |
| `body` | E | PASS | PASS | PASS |
| `upper_wick` | E | PASS | PASS | PASS |
| `lower_wick` | E | PASS | PASS | PASS |
| `range` | E | PASS | PASS | PASS |
| `direction` | E | PASS | PASS | PASS |
| `dist_high_6h` | E | PASS | PASS | PASS |
| `dist_low_6h` | E | PASS | PASS | PASS |
| `dist_high_12h` | E | PASS | PASS | PASS |
| `dist_low_12h` | E | PASS | PASS | PASS |
| `dist_high_24h` | E | PASS | PASS | PASS |
| `dist_low_24h` | E | PASS | PASS | PASS |
| `utc_hour` | E | PASS | PASS | PASS |
| `utc_day_of_week` | E | PASS | PASS | PASS |
| `atr` | R | PASS | PASS | PASS |
| `atr_pct` | R | PASS | PASS | PASS |
| `atr_ecdf_50bar` | R | PASS | PASS | PASS |
| `atr_ma` | R | PASS | PASS | PASS |
| `atr_above_sma14` | R | PASS | PASS | PASS |
| `atr_ratio` | R | PASS | PASS | PASS |
| `rsi` | R | PASS | PASS | PASS |
| `rsi_slope_45m` | R | PASS | PASS | PASS |
| `macd` | R | PASS | PASS | PASS |
| `macd_signal` | R | PASS | PASS | PASS |
| `macd_hist` | R | PASS | PASS | PASS |
| `adx` | R | PASS | PASS | PASS |

### Diagnostic pairs (final-candle |A-B|)

| feature | 200v300 | 200v500 | 200v800 |
|---|---|---|---|
| `return_15m` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `return_45m` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `return_90m` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `return_3h` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `log_return_15m` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `horizon_vol_3h` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `horizon_vol_6h` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `horizon_vol_12h` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `body` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `upper_wick` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `lower_wick` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `range` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `direction` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `dist_high_6h` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `dist_low_6h` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `dist_high_12h` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `dist_low_12h` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `dist_high_24h` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `dist_low_24h` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `utc_hour` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `utc_day_of_week` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `atr` | 4.427e-11 | 4.426e-11 | 4.426e-11 |
| `atr_pct` | 4.026e-11 | 4.025e-11 | 4.025e-11 |
| `atr_ecdf_50bar` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `atr_ma` | 7.491e-11 | 7.488e-11 | 7.488e-11 |
| `atr_above_sma14` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `atr_ratio` | 8.589e-08 | 8.586e-08 | 8.586e-08 |
| `rsi` | 2.057e-06 | 2.058e-06 | 2.058e-06 |
| `rsi_slope_45m` | 5.121e-07 | 5.124e-07 | 5.124e-07 |
| `macd` | 8.580e-11 | 8.584e-11 | 8.584e-11 |
| `macd_signal` | 1.262e-10 | 1.262e-10 | 1.262e-10 |
| `macd_hist` | 4.038e-11 | 4.040e-11 | 4.040e-11 |
| `adx` | 1.709e-05 | 1.710e-05 | 1.710e-05 |

## Fixture `adx_break`
- rows: 800  | sha256(OHLC): `5eaf24a832eff0f9952adccc309d9ca08083371fa145657834a23ff2369e7777`
- final candle: `2026-01-13T07:45:00+00:00`

### Main acceptance (300v500, 500v800)

| feature | class | 300v500 | 500v800 | verdict |
|---|---|---|---|---|
| `return_15m` | E | PASS | PASS | PASS |
| `return_45m` | E | PASS | PASS | PASS |
| `return_90m` | E | PASS | PASS | PASS |
| `return_3h` | E | PASS | PASS | PASS |
| `log_return_15m` | E | PASS | PASS | PASS |
| `horizon_vol_3h` | E | PASS | PASS | PASS |
| `horizon_vol_6h` | E | PASS | PASS | PASS |
| `horizon_vol_12h` | E | PASS | PASS | PASS |
| `body` | E | PASS | PASS | PASS |
| `upper_wick` | E | PASS | PASS | PASS |
| `lower_wick` | E | PASS | PASS | PASS |
| `range` | E | PASS | PASS | PASS |
| `direction` | E | PASS | PASS | PASS |
| `dist_high_6h` | E | PASS | PASS | PASS |
| `dist_low_6h` | E | PASS | PASS | PASS |
| `dist_high_12h` | E | PASS | PASS | PASS |
| `dist_low_12h` | E | PASS | PASS | PASS |
| `dist_high_24h` | E | PASS | PASS | PASS |
| `dist_low_24h` | E | PASS | PASS | PASS |
| `utc_hour` | E | PASS | PASS | PASS |
| `utc_day_of_week` | E | PASS | PASS | PASS |
| `atr` | R | PASS | PASS | PASS |
| `atr_pct` | R | PASS | PASS | PASS |
| `atr_ecdf_50bar` | R | PASS | PASS | PASS |
| `atr_ma` | R | PASS | PASS | PASS |
| `atr_above_sma14` | R | PASS | PASS | PASS |
| `atr_ratio` | R | PASS | PASS | PASS |
| `rsi` | R | PASS | PASS | PASS |
| `rsi_slope_45m` | R | PASS | PASS | PASS |
| `macd` | R | PASS | PASS | PASS |
| `macd_signal` | R | PASS | PASS | PASS |
| `macd_hist` | R | PASS | PASS | PASS |
| `adx` | R | PASS | PASS | PASS |

### Diagnostic pairs (final-candle |A-B|)

| feature | 200v300 | 200v500 | 200v800 |
|---|---|---|---|
| `return_15m` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `return_45m` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `return_90m` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `return_3h` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `log_return_15m` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `horizon_vol_3h` | 1.168e-16 | 1.219e-15 | 1.253e-15 |
| `horizon_vol_6h` | 3.816e-16 | 4.526e-16 | 4.526e-16 |
| `horizon_vol_12h` | 7.410e-16 | 1.324e-15 | 1.801e-15 |
| `body` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `upper_wick` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `lower_wick` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `range` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `direction` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `dist_high_6h` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `dist_low_6h` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `dist_high_12h` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `dist_low_12h` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `dist_high_24h` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `dist_low_24h` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `utc_hour` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `utc_day_of_week` | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `atr` | 5.976e-11 | 5.977e-11 | 5.977e-11 |
| `atr_pct` | 5.187e-11 | 5.188e-11 | 5.188e-11 |
| `atr_ecdf_50bar` | 9.200e-01 | 9.200e-01 | 9.200e-01 |
| `atr_ma` | 1.011e-10 | 1.011e-10 | 1.011e-10 |
| `atr_above_sma14` | 1.000e+00 | 1.000e+00 | 1.000e+00 |
| `atr_ratio` | 4.449e-07 | 4.450e-07 | 4.450e-07 |
| `rsi` | 2.438e-05 | 2.438e-05 | 2.438e-05 |
| `rsi_slope_45m` | 6.069e-06 | 6.069e-06 | 6.069e-06 |
| `macd` | 5.164e-10 | 5.166e-10 | 5.166e-10 |
| `macd_signal` | 7.594e-10 | 7.598e-10 | 7.598e-10 |
| `macd_hist` | 2.430e-10 | 2.431e-10 | 2.431e-10 |
| `adx` | 6.894e-04 | 6.894e-04 | 6.894e-04 |

## Summary
- ADX reseed unit check: PASS
- All fixtures x main pairs x all features PASS: **YES**
- E-class features carry no recursive state, so identical final candles give bit-identical final values; R-class features show the initialization-tailoff behaviour.
- Limitations recorded: a mid-series exact `+DI=-DI=0` break is mathematically degenerate and is not constructible from valid OHLC within the tested horizon; the reseed rule is therefore verified by the direct DX check in §0.
