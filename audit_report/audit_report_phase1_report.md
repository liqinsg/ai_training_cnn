# v685 Training / Inference Feature Consistency Audit — Phase 1

## A. Executive findings

**The feature code is shared, but exact numerical equivalence is not established.** `retrain_model.py` and v685 both use `FeatureEngine.build()` from `data_pipeline.py`. With the same candles, timeframe, dependency behavior, and configuration, they use the same feature formulas and preprocessing. The production path reorders inputs to the saved feature list and applies a fitted scaler.

The principal qualifications are:

- **ATR and MACD use different history lengths in the explicit training script and normal inference.** Training requests 500 M15 bars; inference normally requests 200. ATR and MACD use history-dependent calculations, so matching code alone does not prove identical final values.
- **ATR’s fallback is not numerically equivalent to its `pandas_ta` path.** The fallback is a rolling arithmetic mean with `min_periods=1`; the `pandas_ta` path calls `ta.atr`. Both training and inference share this branch, but their results can differ if dependency availability or behavior differs between the environments.
- **MACD has no manual fallback.** If `pandas_ta` import or calculation fails, the columns are omitted. With an existing model manifest that requires them, inference rejects the row; with auto-training, the feature list can instead be trained without them.
- **There are two training routes with different labels and preprocessing.** The explicit retraining script labels future returns above `0.0005`; production’s age-triggered auto-training labels any positive future return. The stored artifacts do not establish which route created the current model.
- **The current split artifacts are dimensionally consistent:** the model declares 37 input features, and the feature manifest contains 37 names. They have matching Nov 5, 2026 timestamps. The scaler is a separate `scaler.joblib`, but I did not deserialize it; source code says its dimension is validated at load.
- **The pipeline does not cryptographically or version-bind the model, scaler, feature list, and config.** Equal feature counts can pass validation even if the files come from different training runs or feature formulas have changed.

I did not run scripts, tests, model loading, training, or any OANDA operations. This is a static source and artifact inspection.

## B. Training pipeline trace

### Explicit `retrain_model.py` route

| Stage               | Evidence and behavior                                                                                                                                                                                                                                                                                                                                                  |
| ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Entry point         | Work starts only under `if __name__ == "__main__"`; it calls `fetch_all_data()`, `train_model()`, and `save_model()`. See [retrain_model.py:252](/home/qili/projects/ai_training_cnn/retrain_model.py:252).                                                                                                                                                     |
| Historical source   | `fetch_all_data()` constructs an OANDA API client and `DataFetcher(use_oanda=True, ...)`. See [retrain_model.py:80](/home/qili/projects/ai_training_cnn/retrain_model.py:80). The fetcher requests OANDA candle mid prices, converts OHLCV to floats, and trims to closed candles: [data_pipeline.py:672](/home/qili/projects/ai_training_cnn/data_pipeline.py:672). |
| Timeframe/lookback  | Hard-coded `TIMEFRAME = "15m"` maps to OANDA `M15`; `LOOKBACK_BARS = 500`. Each pair fetches up to 500 bars and is skipped below 200. See [retrain_model.py:31](/home/qili/projects/ai_training_cnn/retrain_model.py:31) and [retrain_model.py:67](/home/qili/projects/ai_training_cnn/retrain_model.py:67).                                                       |
| Feature config      | ATR, RSI, ADX, and MACD are enabled; MACD is explicitly true. See [retrain_model.py:43](/home/qili/projects/ai_training_cnn/retrain_model.py:43). `FeatureConfig` defaults ATR/RSI/ADX periods to 14; `use_macd` defaults false but is overridden here. See [data_pipeline.py:80](/home/qili/projects/ai_training_cnn/data_pipeline.py:80).                          |
| Feature calculation | `fetch_all_data()` calls `feat_engine.build(raw)` from the shared `FeatureEngine`: [retrain_model.py:88](/home/qili/projects/ai_training_cnn/retrain_model.py:88), [retrain_model.py:99](/home/qili/projects/ai_training_cnn/retrain_model.py:99). Formulas are listed below.                                                                                      |
| Cleaning            | Replaces infinities with NaN, then forward-fills, backward-fills, and fills remaining NaN with zero: [retrain_model.py:102](/home/qili/projects/ai_training_cnn/retrain_model.py:102).                                                                                                                                                                                  |
| Target and horizon  | `future_return = Close.shift(-6) / Close - 1`; target is 1 only when return exceeds `0.0005`: [retrain_model.py:35](/home/qili/projects/ai_training_cnn/retrain_model.py:35), [retrain_model.py:106](/home/qili/projects/ai_training_cnn/retrain_model.py:106).                                                                                                      |
| Feature selection   | Excludes target, future return, pair, raw OHLCV, and selected metadata; retains numeric columns in dataframe order: [retrain_model.py:129](/home/qili/projects/ai_training_cnn/retrain_model.py:129).                                                                                                                                                                   |
| Split               | Per pair, preserves time order; uses 80% of the non-final-six bars for training and the next 20% for validation: [retrain_model.py:154](/home/qili/projects/ai_training_cnn/retrain_model.py:154).                                                                                                                                                                      |
| Scaling/model       | Fits `StandardScaler` on training rows, transforms validation rows, then trains an XGBoost classifier with 200 estimators, depth 5, learning rate 0.05: [retrain_model.py:182](/home/qili/projects/ai_training_cnn/retrain_model.py:182).                                                                                                                             |
| Artifacts           | `save_model()` delegates persistence to `ModelWrapper.save()`: [retrain_model.py:228](/home/qili/projects/ai_training_cnn/retrain_model.py:228). The wrapper writes model JSON, separate scaler, feature JSON, and config JSON: [data_pipeline.py:582](/home/qili/projects/ai_training_cnn/data_pipeline.py:582).                                                    |

### ATR, MACD, RSI, and other feature definitions

- **ATR:** `ATRModule.compute()` first calls `pandas_ta.atr(High, Low, Close, length=period)`. On exception, it computes true range as the maximum of high-low and the two previous-close gaps, then applies `rolling(period, min_periods=1).mean()`. It derives `atr_pct`, rolling percentile, `atr_ma`, `atr_expanding`, and `atr_ratio`. See [data_pipeline.py:106](/home/qili/projects/ai_training_cnn/data_pipeline.py:106) and [data_pipeline.py:123](/home/qili/projects/ai_training_cnn/data_pipeline.py:123). Period is 14 in the current saved config [trade_model_xgb.cfg.json:1](/home/qili/projects/ai_training_cnn/trade_model_xgb.cfg.json:1).
- **MACD:** when enabled and there are more than 26 rows, calls `ta.macd(Close)` and appends returned columns. No manual fallback or explicit empty-result error exists; exceptions are logged and skipped. See [data_pipeline.py:312](/home/qili/projects/ai_training_cnn/data_pipeline.py:312). The manifest’s column names are `MACD_12_26_9`, `MACDh_12_26_9`, and `MACDs_12_26_9`, indicating the `pandas_ta` defaults represented by the saved model.
- **RSI:** calls `ta.rsi(Close, length=14)`. On failure or empty output, it uses manual Wilder-style exponential smoothing with alpha `1/period`: [data_pipeline.py:267](/home/qili/projects/ai_training_cnn/data_pipeline.py:267).
- **ADX:** uses the project’s own rolling implementation with period 14 and fills NaN with zero: [data_pipeline.py:52](/home/qili/projects/ai_training_cnn/data_pipeline.py:52), [data_pipeline.py:306](/home/qili/projects/ai_training_cnn/data_pipeline.py:306).
- **Other features:** returns, log return, realized volatility, candle body/wicks/range/direction, distances from rolling highs/lows, volume proxies/ratios/trend, and time features are defined in [data_pipeline.py:232](/home/qili/projects/ai_training_cnn/data_pipeline.py:232).

### Production auto-training route

v685 also calls `ensure_model()`. If split artifacts are absent or the model JSON is older than `retrain_every_n_days`, it fetches `FEAT_CFG.train_lookback_bars`, builds shared features, calls `FeatureEngine.build_target()`, concatenates frames, drops NaN, selects features, and fits `ModelWrapper`: [fx_trade_bot_ml.py:22](/home/qili/projects/ai_training_cnn/fx_trade_bot_ml.py:22).

This route differs materially from the explicit script:

- Target is `future_return > 0`, with no `0.0005` threshold: [data_pipeline.py:359](/home/qili/projects/ai_training_cnn/data_pipeline.py:359).
- It uses the configured lookback (the checked-in profile sets 1500) rather than the script’s fixed 500.
- It uses concatenated pair data and `ModelWrapper.fit()`; that method fits the scaler on the full clean dataset, evaluates `TimeSeriesSplit`, then trains the final model on all rows: [data_pipeline.py:520](/home/qili/projects/ai_training_cnn/data_pipeline.py:520).

As of the workspace date, Nov 13, the checked-in model is dated Nov 5 and the default retrain interval is seven days. Therefore the source’s age check would select auto-training on a normal run where `ensure_model()` is reached. I did not run the bot to determine live runtime state.

## C. Inference pipeline trace

1. `fx_trade_bot_v685.py` sets `TIMEFRAME = args.timeframe`; the CLI defaults to `15m` but permits `1H` and `H4`. It maps that selection to OANDA granularity. See [fx_trade_bot_v685.py:998](/home/qili/projects/ai_training_cnn/fx_trade_bot_v685.py:998) and [fx_trade_bot_v685.py:1110](/home/qili/projects/ai_training_cnn/fx_trade_bot_v685.py:1110).
2. It creates `DataFetcher` with OANDA enabled and a shared `FeatureEngine`: [fx_trade_bot_v685.py:1207](/home/qili/projects/ai_training_cnn/fx_trade_bot_v685.py:1207).
3. `main()` calls `ensure_model()` before signal evaluation: [fx_trade_bot_v685.py:1700](/home/qili/projects/ai_training_cnn/fx_trade_bot_v685.py:1700).
4. Normal candidate inference fetches 200 candles, then calls the same `feat_engine.build(raw)`, replaces infinities, forward-fills, backward-fills, and fills remaining NaN with zero: [fx_trade_bot_v685.py:1893](/home/qili/projects/ai_training_cnn/fx_trade_bot_v685.py:1893). The early position-management path uses the same preparation at [fx_trade_bot_v685.py:1764](/home/qili/projects/ai_training_cnn/fx_trade_bot_v685.py:1764).
5. `ensure_model()` injects the loaded/trained model, scaler, and feature names into `StrategyEngine`: [fx_trade_bot_ml.py:70](/home/qili/projects/ai_training_cnn/fx_trade_bot_ml.py:70).
6. `StrategyEngine._predict()` calls shared `predict_p_up()`: [strategy_decision.py:286](/home/qili/projects/ai_training_cnn/strategy_decision.py:286). `_build_matrix()` selects columns in manifest order, converts them to `float64`, rejects missing/non-finite data, and applies the scaler: [data_pipeline.py:393](/home/qili/projects/ai_training_cnn/data_pipeline.py:393).

**Missing feature behavior:** inference does not zero-fill absent columns. The earlier dataframe-wide NaN fill only fills present columns. `_build_matrix()` raises on a missing required feature. `generate_signal()` catches the prediction error and returns no signal: [strategy_decision.py:137](/home/qili/projects/ai_training_cnn/strategy_decision.py:137).

**Fallback behavior:** ATR and RSI fallback code is shared by training and inference. MACD has no manual fallback. `requirements.txt` lists `pandas-ta==0.4.71b0` and `pandas-ta-classic==0.6.52`, but static inspection cannot establish which distribution is installed in the production runtime: [requirements.txt:22](/home/qili/projects/ai_training_cnn/requirements.txt:22).

## D. Consistency matrix

| Feature                                                      | Training                                                                             | Inference                                                            | Parameters                                                                                   | Numerical consistency                                                                                                                                                                                                       | Status                                                              |
| ------------------------------------------------------------ | ------------------------------------------------------------------------------------ | -------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| ATR                                                          | Shared `ATRModule.compute()`; `pandas_ta` then manual rolling-mean fallback      | Same shared implementation                                           | Period 14; fallback rolling window 14, `min_periods=1`; extra rolling-derived ATR features | Same formula branch if same dependency path and same input series. Explicit training uses 500 bars; live inference normally uses 200, and recursive ATR can depend on earlier history. Fallback differs from `pandas_ta`. | **PARTIAL MATCH**                                             |
| MACD                                                         | `ta.macd(Close)`, only if enabled and `n > 26`; no manual fallback               | Same shared call; same failure behavior                              | Defaults correspond to fast 12, slow 26, signal 9                                            | Same implementation under same dependency and same input history. 500 vs 200 bars can change EMA initialization; alternate CLI timeframe changes candle series. Missing output makes required-feature inference fail.       | **PARTIAL MATCH**                                             |
| RSI                                                          | `ta.rsi(length=14)` or manual Wilder fallback                                      | Same shared implementation                                           | Period 14                                                                                    | Same branch on identical data; recursive smoothing plus 500 vs 200 bars means exact numerical equality is unproven.                                                                                                         | **PARTIAL MATCH**                                             |
| ADX                                                          | Shared custom rolling ADX; NaN filled with zero                                      | Same                                                                 | Period 14                                                                                    | Shared formula; on identical overlapping candles, rolling dependencies are bounded. Different timeframe changes values.                                                                                                     | **CONFIRMED MATCH** for same timeframe/data                   |
| Returns, volatility, candle, distance, volume, time features | Shared `FeatureEngine.build()`                                                     | Same                                                                 | Rolling periods 1/3/6/12, 12/24/48, distances 24/48/96, volume window 24                     | Same definitions and preprocessing. Some are time- or input-dependent; inference default uses 200 bars, explicit retraining uses 500.                                                                                       | **CONFIRMED MATCH** for same timeframe/data and shared config |
| Feature order/scaling                                        | Numeric columns selected in dataframe order; `StandardScaler` fit on training data | Manifest order selected; fitted scaler transforms `float64` matrix | Current manifest has 37 columns                                                              | Inference explicitly reorders by saved names and checks dimensions.                                                                                                                                                         | **CONFIRMED MATCH** for current checked-in dimensions         |

“Confirmed match” here means the source formulas and contract agree when the inputs and configuration agree; it does not certify that the market data or runtime dependencies match.

## E. Artifact integrity

1. **Model path loaded by v685:** `MODEL_PATH` is set to `trade_model_xgb.pkl`, but `ModelWrapper` strips `.pkl` and resolves the split artifact stem. The loaded model is `trade_model_xgb.json`, alongside `scaler.joblib` and `trade_model_xgb.features.json`: [fx_trade_bot_v685.py:1242](/home/qili/projects/ai_training_cnn/fx_trade_bot_v685.py:1242), [data_pipeline.py:470](/home/qili/projects/ai_training_cnn/data_pipeline.py:470).
2. **Feature list:** the checked-in model manifest lists 37 features. The XGBoost JSON declares `num_feature: 37`; source artifact timestamps for model, scaler, manifest, and config are all Nov 5, 2026. `features_list.json` is a different 24-feature list and is not referenced by this load path.
3. **Scaler:** saved separately as `scaler.joblib`; it is not embedded in the XGBoost JSON. The `ModelWrapper.load()` path reads the scaler sidecar and feature manifest: [data_pipeline.py:601](/home/qili/projects/ai_training_cnn/data_pipeline.py:601).
4. **Order validation:** inference orders by the manifest and checks that manifest length equals scaler dimension. Loaded artifacts are checked for model/scaler dimensions when those objects expose `n_features_in_`: [data_pipeline.py:563](/home/qili/projects/ai_training_cnn/data_pipeline.py:563). This does not validate feature semantics or prove that same-sized sidecars belong to the model.
5. **Could old models receive new feature definitions?** Yes. Current code computes features by name, then uses the artifact’s saved names. A formula can change while retaining the same name and dimension; dimension checks would not detect that.
6. **Version linkage:** no shared run ID, hash, or atomic bundle is present in the inspected save/load code. Save writes the model, scaler, feature list, and config as separate files in sequence: [data_pipeline.py:582](/home/qili/projects/ai_training_cnn/data_pipeline.py:582). A partial or mixed update with compatible dimensions is not reliably detected.

## F. Production-impacting mismatches, ranked

| Rank         | Finding                                                                  | Evidence / impact                                                                                                                                                                                                                                                                                                                                                                                                    |
| ------------ | ------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **P1** | Alternate inference timeframe can differ from training timeframe         | Explicit training is fixed to M15; v685 accepts `1H` and `H4` as well as `15m`. A feature manifest does not encode or validate timeframe. See [retrain_model.py:31](/home/qili/projects/ai_training_cnn/retrain_model.py:31), [fx_trade_bot_v685.py:135](/home/qili/projects/ai_training_cnn/fx_trade_bot_v685.py:135), [fx_trade_bot_v685.py:998](/home/qili/projects/ai_training_cnn/fx_trade_bot_v685.py:998). |
| **P1** | Explicit retraining and production auto-training define different labels | `retrain_model.py` requires future return `> 0.0005`; `ensure_model()` uses `> 0`. The resulting model behavior can differ even though feature names match.                                                                                                                                                                                                                                                  |
| **P1** | ATR fallback changes numerical definition                                | `pandas_ta` ATR and manual rolling-mean fallback are not the same algorithm. A training/inference environment difference can alter ATR and every ATR-derived feature.                                                                                                                                                                                                                                              |
| **P1** | MACD dependency failure removes required columns                         | No fallback is implemented. Existing manifest-based prediction then rejects missing MACD features; auto-training can produce a different manifest without them.                                                                                                                                                                                                                                                      |
| **P2** | Feature-history lengths differ                                           | Explicit training uses 500 bars, regular inference 200, and auto-training uses configured lookback (1500 in checked-in profile). Recursive ATR/RSI/MACD can be history-sensitive.                                                                                                                                                                                                                                    |
| **P2** | Split artifacts are not version-bound                                    | Same-sized mismatched scaler/manifest/model files, or changed formulas under unchanged names, may pass dimension checks.                                                                                                                                                                                                                                                                                             |
| **P2** | Unknown provenance of current model                                      | Current model files are dated Nov 5, but artifact config does not record the target threshold or training route; source cannot establish whether the explicit or auto-training path produced them.                                                                                                                                                                                                                   |

## G. Confirmed facts, hypotheses, and unresolved questions

**Confirmed from source/artifacts**

- Both explicit training and v685 use `FeatureEngine.build()`.
- Normal v685 inference uses 200 OANDA candles and the same infinity/NaN filling sequence as the explicit retraining script.
- The current manifest and model input dimension are both 37.
- The scaler is a separate sidecar; source loads it and validates dimensions.
- The explicit training script uses M15/500 bars and a `0.0005` target threshold.
- Production auto-training uses configured lookback and a zero-return target threshold.
- ATR has a manual fallback; MACD does not.

**Hypotheses / conditional conclusions**

- On Nov 13, a normal call to `ensure_model()` would consider the Nov 5 model stale under the seven-day interval and auto-train. This follows from file timestamps and source logic; I did not execute the bot or confirm runtime configuration.
- ATR/MACD values will differ between explicit training and inference when the different lookback histories affect recursive initialization. The code establishes history dependence and unequal windows, but exact value deltas require a controlled data comparison, which was outside this read-only static pass.

**Unresolved**

- Which training route produced the Nov 5 model.
- Which `pandas_ta` implementation/version was actually active when that model was trained and in production.
- Whether production has invoked auto-training since Nov 5 or whether its live artifacts differ from the workspace.
- Whether actual runtime launches use `15m`, `1H`, or `H4`.

## Recommended next investigation steps

1. Read production run logs or artifact deployment records to establish model provenance and active timeframe.
2. In an isolated, non-production environment, compare the shared feature outputs for the same OANDA candle tail under 500-bar and 200-bar inputs, covering ATR, MACD, and RSI separately.
3. Compare `pandas_ta` and fallback outputs on fixed candles, and confirm the package/version used by the training and inference environments.
4. Inspect scaler metadata without altering artifacts, then verify its 37-feature dimension and ordering against the deployed manifest.
5. Reconcile the explicit and auto-training target definitions before treating artifacts from either route as equivalent.

No code changes were made. No scripts or tests were run.
