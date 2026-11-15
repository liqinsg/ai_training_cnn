# Phase 3.2 — Stage A Source Reconciliation

**Spec:** `docs/PHASE3_2_STRICT_SPEC.md` v0.3
**Baseline HEAD:** `05bf31e8a8f1f07da03c32983dc379fa246b70ed`
**Stage A status:** COMPLETE — proceed to Stage B

## 1. Effective source and dependency baseline

The experiment baseline is the recorded `HEAD` plus the working-tree changes below and the active `ai-sprint` Python environment. No dependency changes were made.

`git status --short` at capture:

```text
 M .gitignore
 M docs/PHASE3_2_STRICT_SPEC.md
 M monte_carlo/monte_carlo_kf.py
 M requirements.txt
```

There were no staged changes and no untracked files reported by `git ls-files --others --exclude-standard`. Source diffs for `.gitignore`, `monte_carlo/monte_carlo_kf.py`, and `requirements.txt` are preserved in `docs/PHASE3_2_STAGE_A_SOURCE_DIFF.patch` (SHA-256 `30aa803028f2fc9d471190b489b845c028c669c9283e199693f5b0ac96e967c2`). The Stage A spec diff, reconstructed with the pre-approval status line, is preserved in `docs/PHASE3_2_STAGE_A_SPEC_DIFF.patch` (SHA-256 `9325e8e88bd342406c0aafb027989e9d813e8e5403f40acd4fcc971c7324cc49`). SHA-256 fingerprints of individual `git diff --binary -- <path>` outputs at Stage A capture are:

| Path | Diff SHA-256 |
| --- | --- |
| `.gitignore` | `42de7bdd89edb26970146b8ae6e3f6fba17529f5e3c3cca18c78ada1b94f5f49` |
| `monte_carlo/monte_carlo_kf.py` | `a9b2d7ee14a82dde75134d2d4802f54854fa12d779f8dd5a069c4d2b19f837c4` |
| `requirements.txt` | `5ec60147447c38fe8d3b018c8d484abd904846cf1ad496fff0d37780ee310d99` |
| `docs/PHASE3_2_STRICT_SPEC.md` | `b2debdd2f68d6e998231f40067e039e946c8f7b9cc0854eb46c10f6ee4ab80aa` |

Staged diff SHA-256: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` (empty diff).

The Stage A spec diff fingerprint is its state at Stage A capture; after the owner approved Stages A–C, only the spec status line changed from pending approval to approved within scope. Evidence reports and this patch archive were created as Stage A/B outputs after the initial status capture.

Active environment:

| Component | Version |
| --- | --- |
| Python | 3.12.16 |
| NumPy | 2.2.6 |
| pandas | 3.1.1 |
| pandas-ta | 0.4.71b0 |
| pandas-ta-classic | 0.6.52 |
| scikit-learn | 1.9.1 |
| XGBoost | 3.3.0 |

The requirements file and active environment agree on the listed numerical/ML dependency versions. Stage B must use this recorded environment and must not alter dependencies without separate authorization.

Operational note from Stage B entry: importing XGBoost fails because `libomp.dylib` is unavailable on this host. FeatureEngine-only experiments can run with the optional XGBoost import disabled; model loading, fitting, and inference cannot be validated in this environment.

## 2. Current feature inventory

Authoritative implementation is `data_pipeline.FeatureEngine`; `ml/features.py` is marked non-authoritative and is not wired into the inspected live path.

| Feature family | Columns / behavior | Dependencies and conditions |
| --- | --- | --- |
| Returns | `ret_1h`, `ret_3h`, `ret_6h`, `ret_12h`, `ret_log` | Enabled by config; columns depend on input length. |
| Realized volatility | `vol_12h`, `vol_24h`, `vol_48h` | Enabled by config; rolling price returns. |
| Candle body | `body`, `upper_wick`, `lower_wick`, `range`, `direction` | Requires more than one row. |
| ATR | `atr`, `atr_pct`, `atr_percentile`, `atr_ma`, `atr_expanding`, `atr_ratio`; categorical `vol_regime` | `pandas_ta` ATR or manual rolling-mean TR fallback; rolling windows and fill defaults. |
| RSI | `rsi`, `rsi_slope` | `pandas_ta` or manual Wilder EWM fallback; slope requires additional rows. |
| ADX | `adx` | Local implementation, then `fillna(0.0)`. |
| MACD | Three columns from `ta.macd()` | Only when enabled and input length > 26; failure logs warning and omits columns. |
| Extremes | `dist_high_24/48/96`, `dist_low_24/48/96` | Generated only when row count exceeds the respective window. |
| Volume | `vol_sma_ratio`, `vol_trend` | Only when row count > 24; zero/missing volume uses `(High-Low)*abs(Close)`. |
| Time | `hour`, `day_of_week`, `is_london`, `is_ny` | Datetime index uses index fields; non-datetime index fills zeros. |

Numeric model feature selection is dynamic: `retrain_model.py` selects numeric columns present after feature construction, excluding target/metadata columns. It then passes the selected matrix into the scaler/model path without an explicit feature-wide `dropna()` in this script. Therefore input length and MACD success can change selected columns, and NaN acceptance/handling remains to be tested.

## 3. Training and inference call paths

| Path | Data and timeframe | Feature / cleaning path | Minimum checks / outcome |
| --- | --- | --- | --- |
| Training | `retrain_model.py`, M15, requests `LOOKBACK_BARS=500` | Fetch/closed-candle trim → reject if <200 → FeatureEngine → replace Inf with NaN → `ffill` → `bfill` → `fillna(0)` → numeric columns selected dynamically | Fewer than 200 raw rows skips pair. Training then drops rows with NaN in selected features/target. |
| Main trading scan and position coverage | Runtime CLI timeframe `15m`, `1H`, or `H4`; requests 200 rows | FeatureEngine → replace Inf with NaN → `ffill` → `bfill` → `fillna(0)` | Actual returned length may be lower than requested; data assembly checks empty; `generate_signal()` requires 5 rows. |
| Multi-timeframe Confluence | Fetches M15/H1/H4 candles separately | Calls `FeatureEngine.build(raw_tf)` and passes result directly to strategy; no matching cleaning chain | Caller skips raw inputs under 5 rows; strategy also checks 5; feature validation can reject missing/non-finite model inputs. |
| Indicator provider | Separate utility consumer | Uses data guard before its own indicator work | `MIN_REQUIRED_BARS=200` applies here when default is used; it is not the main strategy guard. |

Prediction path aligns the latest row to the stored feature order and applies the scaler through `predict_p_up`; missing columns, object dtypes and non-finite values are rejected rather than synthesized. The active model/scaler/feature-list bundle is unavailable locally, so the runtime alignment cannot be exercised against the declared active bundle.

## 4. Feature dependencies and warm-up map

| Dependency | Minimum generation threshold in current implementation | Warm-up / missing behavior to test in Stage B |
| --- | --- | --- |
| Returns | `n > p` for each lag; `n > 1` for log return | Initial lag rows are missing; post-build cleaning differs by consumer. |
| Volatility | `n > window` | Rolling standard deviation can be NaN at the beginning; `min_periods=1` applies to the volatility window after `pct_change`. |
| Candle body | `n > 1` | Zero Open and invalid OHLC values can produce non-finite numbers. |
| ATR | `n >= 2` computes ATR family | Backend warm-up differs; local fallback uses rolling mean with `min_periods=1`; ATR-derived feature defaults may mask early missing values. |
| RSI | `n > rsi_period` | Backend/fallback initialization and recursive history sensitivity require direct comparison. |
| RSI slope | `n > rsi_period + 3` | First slope rows missing. |
| ADX | `n > adx_period` | Local implementation fills NaN with zero. |
| MACD | Enabled and `n > 26` | Failure can omit columns entirely. |
| Extreme distances | `n > 24`, `n > 48`, `n > 96` respectively | Feature set depends on total input length. |
| Volume | `n > 24` | Ratio fills zero denominator with 1.0; fallback proxy when volume sum is zero. |

`FeatureConfig.required_bars=20` only warns. It does not enforce the maximum feature window or guarantee a complete, finite model vector.

## 5. Configuration authority and timeframe matrix

| Configuration | Current authority / observation | Stage B/C implication |
| --- | --- | --- |
| Runtime timeframe | CLI selects 15m, 1H, or H4; `DataFetcher` receives mapped OANDA granularity. | Model timeframe compatibility is not established. |
| Training timeframe | `retrain_model.py::TIMEFRAME = "15m"` → M15. | Training is M15 by source configuration. |
| Feature config | Runtime values are assembled through `cfg_bot(...)`; training has a separate `FEAT_CFG`. | Compare exact effective feature config values, not only defaults. |
| Artifact config | `ModelWrapper.load()` sets fields on its `cfg`; live `FeatureEngine` and wrapper receive the same `FEAT_CFG` object. | Artifact can mutate runtime config; `ATRModule` captures its period at engine construction. |
| Contract timeframe metadata | Current `.cfg.json` has feature settings but no training granularity; manifest has no timeframe field. | Compatibility cannot be inferred from existing metadata. |

The model configuration file is present and sets `use_macd=true`. The manifest is present and declares 34 feature names but does not list the three MACD outputs. Source training configuration also enables MACD, and its comment says MACD changes the selected feature count from 34 to 37. This is a concrete metadata/config discrepancy, but without the active model, scaler and `.features.json`, it does not prove which bundle was actually trained or used.

## 6. Missing-value and candle integrity matrix

| Concern | Current source behavior | Evidence status |
| --- | --- | --- |
| Inf/NaN cleaning | Training and main trading paths replace Inf, then forward-fill, backward-fill, and zero-fill. Confluence does not use that same chain. | Confirmed from source. |
| Future-to-past fill | `bfill()` is applied to training rows. | Potential future-row influence; magnitude/effect not measured. |
| Timestamp parsing | OANDA timestamps are parsed with `pd.to_datetime`; candles are indexed by parsed time. | Exact timezone and cross-source behavior require fixture-level validation. |
| Incomplete latest candle | `DataFetcher._from_oanda()` calls `trim_to_closed_candles()`. | Latest candle handling exists on this path. |
| Sort, duplicate, gap validation | No comprehensive validation in the inspected fetch/build path. | Not verified/enforced by this path. |
| All consumers' candle policy | Confluence uses a separate `fetch_candles()` path. | Must compare its timestamp/closed-candle behavior in Stage B. |

## 7. NOT VERIFIED register and bounded Stage A exit

- Active model JSON, scaler, and `.features.json` are absent locally; the manifest and config alone cannot prove bundle compatibility.
- 34-feature manifest versus MACD-enabled 37-column training expectation remains unresolved.
- 200-bar versus 500-bar latest feature sensitivity is not measured.
- `pandas_ta` versus manual ATR/RSI equivalence and MACD failure behavior are not experimentally assessed.
- Actual numeric tolerance must be pre-registered before looking at Stage B results.
- Runtime-effective `cfg_bot` settings under a live launch environment are not queried; no bot was launched and no credentials were read.
- Full historical compatibility with absent `docs/Development_plan.md` remains unverified.

Stage A is closed because source paths, config sources, effective dependency versions, artifact evidence gaps, and unresolved questions are now enumerated. These gaps are bounded experiment inputs or explicit compatibility blockers; no broad audit remains necessary before Stage B.

## 8. Stage B entry decision

Proceed to deterministic offline experiments using synthetic fixed OHLCV fixtures and the recorded local environment. Preregistered numeric comparison rule before examining results: pass only if values satisfy `abs(candidate-reference) <= 1e-10 + 1e-8*abs(reference)`; integer/categorical features require exact equality; column names/order and missing/non-finite status require exact agreement where parity is claimed. Report absolute and relative deltas regardless of pass/fail. Do not relax these tolerances after seeing results; any exception requires the owner approval described in v0.3.

Include at minimum the same-final-candle 200-versus-500-bars sensitivity experiment, feature-column and finite-value checks over 5–200 bars, and indicator backend comparisons. No OANDA account, model training, artifact writes, or trading execution is needed or authorized.
