# Phase 3.2 — Candidate Feature Source Evidence

**Purpose:** Record the formulas and generation conditions found in the current `data_pipeline.FeatureEngine` source for the 37 candidate features in the Phase 3.2 design.

**Status:** SOURCE EVIDENCE ONLY — no feature is approved for inclusion; no Feature Contract Identity is issued.

**Source inspected:** `data_pipeline.py` (current working tree; `FeatureConfig`, `ATRModule.compute`, `adx`, and `FeatureEngine.build`). The source references below use line numbers from the inspected version. Any source change requires rechecking this record.

## 1. Interpretation rules

- These are descriptions of current code behavior, including its fallback paths and defaults. They are not recommendations or normative contract definitions.
- `p` and `period` are row/bar counts. Despite names such as `ret_1h`, the implementation does not convert the period to elapsed hours; meaning depends on the input timeframe.
- Unless stated otherwise, formulas are applied row-wise to the input order. This method does not validate timestamp order, gaps, timezone, OHLC consistency, or positive prices.
- `n` means `len(df)`. The checks below govern whether a column is created at all; they do not guarantee finite values in every row.
- Default `FeatureConfig` enables returns, volatility, body features, ATR, RSI, and ADX; it disables MACD. Defaults are configurable and do not establish the effective runtime/training configuration.

## 2. Feature-by-feature evidence

| Candidate | Current source expression / semantics | Inputs and parameters | Column creation condition | Source / evidence notes |
|---|---|---|---|---|
| `ret_1h` | `Close.pct_change(1)` | `Close`; lag 1 row | `use_returns` and `n > 1` | `data_pipeline.py:242-248`. First row is missing. “1h” is a name only; no timeframe conversion. |
| `ret_3h` | `Close.pct_change(3)` | `Close`; lag 3 rows | `use_returns` and `n > 3` | `data_pipeline.py:242-246`. First 3 rows are missing. |
| `ret_6h` | `Close.pct_change(6)` | `Close`; lag 6 rows | `use_returns` and `n > 6` | `data_pipeline.py:242-246`. First 6 rows are missing. |
| `ret_12h` | `Close.pct_change(12)` | `Close`; lag 12 rows | `use_returns` and `n > 12` | `data_pipeline.py:242-246`. First 12 rows are missing. |
| `ret_log` | `log(Close / Close.shift(1))` | `Close`; lag 1 row | `use_returns` and `n > 1` | `data_pipeline.py:247-248`. Requires valid positive prices for finite real values; no guard in this method. |
| `vol_12h` | `Close.pct_change().rolling(12, min_periods=1).std() * sqrt(12*4)` | `Close`; window 12 rows; sample std behavior from pandas rolling `.std()` | `use_volatility` and `n > 12` | `data_pipeline.py:250-256`. Return series starts missing; rolling std can remain missing until at least two valid returns. Scale factor is `sqrt(48)`. |
| `vol_24h` | `Close.pct_change().rolling(24, min_periods=1).std() * sqrt(24*4)` | `Close`; window 24 rows | `use_volatility` and `n > 24` | `data_pipeline.py:250-256`. Scale factor is `sqrt(96)`. |
| `vol_48h` | `Close.pct_change().rolling(48, min_periods=1).std() * sqrt(48*4)` | `Close`; window 48 rows | `use_volatility` and `n > 48` | `data_pipeline.py:250-256`. Scale factor is `sqrt(192)`. |
| `body` | `abs(Close - Open) / Open` | `Open`, `Close` | `use_body_features` and `n > 1` | `data_pipeline.py:258-260`. No zero/invalid Open guard. |
| `upper_wick` | `(High - max(Close, Open)) / Open` | `High`, `Open`, `Close` | `use_body_features` and `n > 1` | `data_pipeline.py:261-263`. No OHLC validity or zero Open guard. |
| `lower_wick` | `(min(Close, Open) - Low) / Open` | `Low`, `Open`, `Close` | `use_body_features` and `n > 1` | `data_pipeline.py:264-266`. |
| `range` | `(High - Low) / Open` | `High`, `Low`, `Open` | `use_body_features` and `n > 1` | `data_pipeline.py:267`. No zero Open guard. |
| `direction` | `1` if `Close > Open`, else `-1` | `Close`, `Open` | `use_body_features` and `n > 1` | `data_pipeline.py:268`. Equal Open/Close maps to `-1`, not zero. |
| `atr` | `pandas_ta.atr(High, Low, Close, length=atr_period)`; on any exception/empty result: rolling mean of row-wise maximum of `High-Low`, `abs(High-prev Close)`, `abs(Low-prev Close)`, window `atr_period`, `min_periods=1` | `High`, `Low`, `Close`; default `atr_period=14`; backend is imported at runtime | `use_atr`; for `n < 2` column is created as NaN; for `n >= 2` compute attempted | `data_pipeline.py:116-147, 270-275`. Fallback is not the same formula/initialization as canonical ATR; computation exceptions are caught by `FeatureEngine`, logged, and not re-raised. |
| `atr_pct` | `atr / Close` | `atr`, `Close` | Same as ATR | `data_pipeline.py:123-125,149`. No zero Close guard. |
| `atr_percentile` | Over rolling window `w=min(n,max(2*atr_period,50))`, `(atr - rolling_min(atr))/(rolling_max(atr)-rolling_min(atr))`; zero range becomes NaN, then filled with `0.5`; result clipped to `[0,1]` | `atr`; rolling min/max with `min_periods=1`; default `w=50` at period 14 | Same as ATR; for `n < 2`, constant `0.5` | `data_pipeline.py:123-130,151-158`. This is a rolling min/max position, not an empirical rank percentile. |
| `atr_ma` | `atr.rolling(atr_period, min_periods=1).mean()` | `atr`; default period 14 | Same as ATR; for `n < 2`, NaN | `data_pipeline.py:123-128,160`. |
| `atr_expanding` | Integer `(atr > atr_ma)`; missing comparison filled with `0` | `atr`, `atr_ma` | Same as ATR; for `n < 2`, `0` | `data_pipeline.py:123-129,161`. Name describes a comparison with rolling ATR mean, not a formal expanding-window calculation. |
| `atr_ratio` | `atr / rolling_mean(atr, h)` with `h=min(n,2*atr_period)`, `min_periods=1`; zero mean replaced with NaN, ratio missing filled with `1.0` | `atr`; default `h=28` | Same as ATR; for `n < 2`, `1.0` | `data_pipeline.py:123-129,163-172`. |
| `rsi` | First attempts `pandas_ta.rsi(Close, length=rsi_period)`. On exception or empty/all-missing output, computes gain/loss with clipped one-row delta; EWM means use `alpha=1/period`, `adjust=False`, `min_periods=period`; RSI=`100-100/(1+avg_gain/avg_loss)`. Zero avg loss maps to 100; both averages zero maps to 50. | `Close`; default `rsi_period=14`; pandas-ta or local EWM fallback | `use_rsi` and `n > rsi_period` | `data_pipeline.py:103-104,277-310`. Source asserts local smoothing “matches ta.rsi,” but that is not proof of universal numerical equivalence. |
| `rsi_slope` | `rsi.diff(3)` | `rsi`; lag 3 rows | `use_rsi` and `n > rsi_period+3` | `data_pipeline.py:312-314`. Initial slope rows are missing; requires the RSI column from either backend path. |
| `adx` | Local function: `TR=max(High-Low, abs(High-prev Close), abs(Low-prev Close))`; `+DM` is upward high change when greater than downward low change else 0; `-DM` is downward low change when greater than upward high change else 0. Simple rolling means over `period` produce ATR and directional indicators; `DX=100*abs(+DI--DI)/(+DI+-DI)`; final ADX is simple rolling mean of DX over `period`. Output NaNs are filled with `0.0` by caller. | `High`, `Low`, `Close`; default `adx_period=14` | `use_adx` and `n > adx_period` | `data_pipeline.py:62-87,106-107,316-320`. This is the literal local implementation; zero denominators and initialization/warm-up are not explicitly handled beyond final `fillna(0.0)`. |
| `MACD_12_26_9` | First output column from default `pandas_ta.macd(Close)` | `Close`; default MACD parameters are implicit in call | `use_macd` and `n > 26`; call must return non-empty frame containing the column | `data_pipeline.py:322-331`. Names are expected from library output, but periods/signal/MA mode are not passed explicitly here. |
| `MACDh_12_26_9` | Histogram output from default `pandas_ta.macd(Close)` | Same as MACD | Same as MACD | `data_pipeline.py:322-331`. |
| `MACDs_12_26_9` | Signal output from default `pandas_ta.macd(Close)` | Same as MACD | Same as MACD | `data_pipeline.py:322-331`. A failed call is only logged; columns can be omitted. |
| `dist_high_24` | `(Close - rolling_max(High, 24, min_periods=1))/Close` | `Close`, `High`; window 24 rows | `n > 24` | `data_pipeline.py:333-341`. No zero Close guard. |
| `dist_low_24` | `(Close - rolling_min(Low, 24, min_periods=1))/Close` | `Close`, `Low`; window 24 rows | `n > 24` | `data_pipeline.py:333-341`. |
| `dist_high_48` | `(Close - rolling_max(High, 48, min_periods=1))/Close` | `Close`, `High`; window 48 rows | `n > 48` | `data_pipeline.py:333-341`. |
| `dist_low_48` | `(Close - rolling_min(Low, 48, min_periods=1))/Close` | `Close`, `Low`; window 48 rows | `n > 48` | `data_pipeline.py:333-341`. |
| `dist_high_96` | `(Close - rolling_max(High, 96, min_periods=1))/Close` | `Close`, `High`; window 96 rows | `n > 96` | `data_pipeline.py:333-341`. |
| `dist_low_96` | `(Close - rolling_min(Low, 96, min_periods=1))/Close` | `Close`, `Low`; window 96 rows | `n > 96` | `data_pipeline.py:333-341`. |
| `vol_sma_ratio` | `vol / rolling_mean(vol,24,min_periods=1)`; zero rolling mean replaced with NaN and result filled with `1.0`. `vol` is `Volume.astype(float)` only if Volume exists and its full-frame sum is positive; otherwise `(High-Low)*abs(Close)` proxy is used. | `Volume` or `High`, `Low`, `Close`; rolling window 24 rows | `n > 24` | `data_pipeline.py:343-352`. The proxy switch depends on a whole-input sum, so the same candle can receive a different value depending on the supplied history/window. |
| `vol_trend` | `1` if chosen `vol > vol.shift(1)`, else `-1` | Same selected `vol` as `vol_sma_ratio` | `n > 24` | `data_pipeline.py:343-353`. First comparison and equality map to `-1`. Volume source may be real or proxy as above. |
| `hour` | `DatetimeIndex.hour` | Index timestamps | Always created; zero if index is not a `DatetimeIndex` | `data_pipeline.py:355-365`. No timezone validation/conversion occurs here. |
| `day_of_week` | `DatetimeIndex.dayofweek` (Monday=0 through Sunday=6) | Index timestamps | Always created; zero if index is not a `DatetimeIndex` | `data_pipeline.py:355-365`. |
| `is_london` | Integer indicator `8 <= hour <= 16`, inclusive | `hour` from index | Always created; zero if index is not a `DatetimeIndex` | `data_pipeline.py:356-365`. Uses index's current timezone/hour, not a London timezone conversion or session calendar. |
| `is_ny` | Integer indicator `13 <= hour <= 21`, inclusive | `hour` from index | Always created; zero if index is not a `DatetimeIndex` | `data_pipeline.py:356-365`. Uses index's current timezone/hour, not a New York timezone conversion or daylight-saving calendar. |

## 3. Cross-cutting source observations

1. **The “37” count is conditional.** With the design's configured feature families enabled, `use_macd=True`, a `DatetimeIndex`, at least 97 rows, and successful MACD generation, the source can produce 37 named numeric candidates. The default `FeatureConfig` has `use_macd=False`. Other flags, short inputs, an integer/non-datetime index, or MACD failure change the set.
2. **97 is only the longest source gate.** `dist_*_96` requires `n > 96`; no claim follows about convergence or finite values. `FeatureConfig.required_bars=20` only logs a warning and does not enforce complete candidates.
3. **Missing behavior varies by feature.** Examples include returns/RSI slope rolling warm-up NaNs, ADX NaNs converted to zero, ATR percentile fallback `0.5`, ATR ratio fallback `1.0`, and volume ratio fallback `1.0`. These are current implementation semantics, not an approved missing-value policy.
4. **Backends are not uniformly fail-closed.** ATR and RSI switch to local formulas on broad exceptions; ADX is always local; MACD failure only logs and may omit columns. ATR exceptions escaping its helper are caught and logged by `FeatureEngine.build` without re-raising.
5. **No canonical output order is established by this evidence.** Feature creation statements have an order, but the input frame can already contain columns, and downstream code may select numeric columns dynamically. A stable ordered model schema must be decided separately.
6. **No feature selection decision is made here.** All 37 remain candidates requiring INCLUDE / EXCLUDE / DEFER decisions and owner approval under the design process.

## 4. Open technical questions for TFC-01 / TFC-02

- What declared timeframe will give meaning to the row-based return/volatility names and windows?
- Should MACD parameters be made explicit rather than relying on `pandas_ta` defaults, and which exact library output/version is intended?
- Which ATR/RSI backends and failure semantics will be canonical?
- Should current fallback/default behavior (ADX zero fill, ATR percentile `0.5`, ATR ratio and volume ratio `1.0`, synthetic volume) be retained, rejected, or redesigned?
- Should volume features use actual volume only? Current all-frame sum rule can make per-row values dependent on the requested history span.
- What timezone and daylight-saving/session definition should the four time features use?
- What OHLCV validity and finite-value constraints apply before evaluating the formulas?
- Which candidates are INCLUDE, EXCLUDE, or DEFER, and what evidence supports each decision?

## 5. References

- Current source: [`data_pipeline.py`](../data_pipeline.py), especially `FeatureConfig` (lines 90–114), `adx` (62–87), `ATRModule.compute` (116–175), and `FeatureEngine.build` (227–367).
- Candidate list and unresolved contract decisions: [`PHASE3_2_Tech_Feature_Contract_v1.0_Design.md`](PHASE3_2_Tech_Feature_Contract_v1.0_Design.md), sections 3 and 10.
- Earlier source inventory and path observations: [`PHASE3_2_STAGE_A_SOURCE_RECONCILIATION.md`](PHASE3_2_STAGE_A_SOURCE_RECONCILIATION.md), sections 2 and 4.
