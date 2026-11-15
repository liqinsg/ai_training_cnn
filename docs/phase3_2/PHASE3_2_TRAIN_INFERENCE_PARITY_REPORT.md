# Phase 3.2 — Stage B Train / Inference Parity Report

**Spec:** `docs/PHASE3_2_STRICT_SPEC.md` v0.3
**Stage A evidence:** `docs/PHASE3_2_STAGE_A_SOURCE_RECONCILIATION.md`
**Status:** Offline synthetic experiments complete; parity NOT ESTABLISHED

## 1. Experiment protocol

Experiments ran in the recorded `ai-sprint` environment: Python 3.12.16, NumPy 2.2.6, pandas 3.1.1, pandas-ta 0.4.71b0, pandas-ta-classic 0.6.52, scikit-learn 1.9.1, and XGBoost 3.3.0. The XGBoost wheel cannot import because `libomp.dylib` is missing. The experiments disabled only the optional XGBoost import in-process; no XGBoost model, scaler, OANDA endpoint, or artifact was loaded or written. This exercises feature construction only.

Synthetic baseline: 500 UTC-indexed OHLCV rows at 15-minute spacing. For row index `t`:

```text
Close = 1.10 + 0.00001*t + 0.001*sin(t/7) + 0.0003*sin(t/1.6)
Open[t] = Close[t-1] (first row uses Close[0])
spread[t] = 0.00012 + 0.00002*(1 + sin(t/5))
High = max(Open, Close) + spread
Low = min(Open, Close) - spread
Volume = 100 + 30*(1 + sin(t/9))
```

Feature configuration enabled ATR, returns, volatility, candle body, RSI, MACD and ADX. Output was cleaned using the training/live main-path chain (`replace Inf with NaN → ffill → bfill → fillna(0)`). The 200-bar input was the last 200 rows of the same 500-row input, preserving the final completed candle.

Pre-registered numeric rule: `abs(candidate-reference) <= 1e-10 + 1e-8*abs(reference)`. Integers/categories, column names/order, and missing/non-finite status require exact agreement where parity is claimed. Tolerances were not changed after observing results.

## 2. 200 bars versus 500 bars

| Comparison | Result |
| --- | --- |
| Final candle | Same instrument proxy, same 15m index, same final OHLCV row |
| Numeric FeatureEngine columns | 37 in both inputs |
| Manifest features compared | 34 |
| Manifest features within tolerance | 31 / 34 |
| All generated numeric features within tolerance | 31 / 37 |
| Maximum absolute delta | `rsi`: `2.635298024245003e-05` |
| Maximum relative delta | `rsi`: `4.561828329007056e-07` |

Features outside the preregistered tolerance:

| Feature | 200 bars | 500 bars | Absolute delta |
| --- | ---: | ---: | ---: |
| `rsi` | 57.76848746511971 | 57.76846111213947 | 2.635298024245003e-05 |
| `rsi_slope` | -22.189141315746745 | -22.189134641005488 | 6.674741257484129e-06 |
| `atr_percentile` | 0.37539918621418494 | 0.37539921283959843 | 2.662541348508185e-08 |
| `MACD_12_26_9` | 0.0003953117426571673 | 0.00039531149080662686 | 2.5185054042253796e-10 |
| `MACDh_12_26_9` | 9.775778513875877e-06 | 9.775897031760511e-06 | 1.185178846339549e-10 |
| `MACDs_12_26_9` | 0.0003855359641432914 | 0.00038553559377486635 | 3.7036842505649287e-10 |

**Decision:** The latest 200-bar vector is not equivalent to the latest 500-bar vector under the pre-registered rule. The differences are small in relative terms on this fixture but exceed the approved tolerance. This does not establish that 500 bars is required; it establishes that the existing 200/500 policies need an explicit contract or further approved convergence analysis.

## 3. Lookback-dependent feature schema

With the same feature configuration, dynamic numeric feature counts were:

| Bars | Numeric features | Missing declared manifest columns |
| ---: | ---: | --- |
| 5 | 18 | 16 (includes long returns/volatility, RSI/ADX, extremes, volume features) |
| 14 | 21 | 13 |
| 15 | 23 | 11 |
| 20 | 24 | 10 |
| 24 | 24 | 10 |
| 25–27 | 29 | 5 |
| 48 | 32 | 5 |
| 49–96 | 35 | 2 (`dist_high_96`, `dist_low_96`) |
| 97, 200, 500 | 37 | 0 |

The generated numeric feature count reaches 37 at 97 bars. The current manifest declares 34 names and omits the three MACD columns. Thus a five-bar guard can pass while the declared feature columns are missing; at 97 bars all manifest names exist, but three additional numeric MACD columns are also generated. Actual model compatibility cannot be concluded because the active model, scaler and `.features.json` are absent.

## 4. Indicator backend comparison

| Fixture (500 rows) | ATR abs delta: pandas-ta vs manual rolling-mean TR | RSI abs delta: pandas-ta vs manual Wilder EWM |
| --- | ---: | ---: |
| Smooth oscillating baseline | 3.361621673199453e-05 | 7.105427357601002e-15 |
| Monotonic rise | 7.589415207398531e-19 | 0 |
| Monotonic decline | 1.734723475976807e-18 | 0 |
| Flat | 0 | 0 |
| High volatility | 7.190482467776468e-06 | 1.4210854715202004e-14 |
| Price gap | 1.0374735467423568e-11 | 0 |

**Decision:** RSI fallback matched the installed backend within tolerance on these fixtures; this is fixture evidence, not a universal proof. ATR fallback did not match on the varying-range fixtures: the current manual fallback uses a rolling mean of true range while the installed `pandas_ta` path produces a different smoothing result. Fallback equivalence is disproven for the tested inputs.

MACD has no fallback. An injected offline backend exception yielded no MACD columns, confirming that failure changes the output schema.

## 5. Cleaning and data-integrity fixtures

For each 500-row fixture (rise, decline, flat, high volatility, price gap, zero volume, one missing Close, one infinite High, duplicate timestamp, and out-of-order timestamp), the current build plus main-path cleaning completed with 37 numeric columns and zero remaining non-finite numeric cells. This demonstrates that the cleaning chain can yield finite output on these synthetic cases; it does not mean malformed candles are rejected.

The engine accepted the duplicate and out-of-order indexes without raising or normalizing them. A deleted 15-minute candle also remained an unvalidated 30-minute timestamp gap while the engine returned 37 numeric features. The feature builder itself therefore does not enforce uniqueness, strict ordering, or gap policy.

With the training cleaning chain on the synthetic baseline, `bfill()` supplied future-derived values to leading missing feature cells, including 33 initial MACD cells, 17 RSI-slope cells, 14 RSI and ATR cells, 12 `ret_12h` cells, and other initial return/volatility cells. The downstream training effect was not assessed against a model because no active model bundle is available.

Changing the same 500 OHLCV rows' index spacing from 15-minute to hourly retained 37 numeric feature columns but changed time-derived values. `FeatureEngine` does not take a timeframe argument; timeframe identity must be carried and validated by the caller/artifact contract.

## 6. Overall Stage B decision and remaining evidence gaps

- Training/inference parity: **NOT ESTABLISHED**. Cleaning differs on Confluence; active artifact pair unavailable; 200-versus-500 differs beyond preregistered tolerance.
- Feature schema: **NOT STABLE across lookback/backend outcomes**. Short histories omit declared columns; MACD failure omits three columns; successful MACD adds three beyond the 34-name manifest.
- Backend equivalence: **ATR fallback FAILS** tested parity; RSI fallback PASSES tested fixtures only; MACD fallback does not exist.
- Candle integrity: **NOT ENFORCED** by the feature builder for duplicate, unordered, or missing candle timestamps.
- Cross-host determinism: **NOT VERIFIED** (one host/environment only).
- Model/scaler dimension and timeframe compatibility: **NOT VERIFIED** (active artifacts unavailable and XGBoost native import is unavailable in this host environment).

Stage B ends on repeatable synthetic comparisons and explicit decisions; no time-based observation remains. Before Phase 3.2 can claim deployed artifact compatibility, obtain the active model, scaler and ordered `.features.json`, plus trustworthy training-timeframe metadata. No production implementation, retraining, deployment, READY wiring, or trading-flow change was performed.
