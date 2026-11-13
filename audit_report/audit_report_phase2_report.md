# v685 Training / Inference Feature Consistency Audit — Phase 2

## A. Executive conclusion

1. **Current model provenance is not established.** The local model files are dated Nov 5, 2026, but available logs do not identify the training route or target definition. The saved config records a 5,000-bar lookback, which is evidence *against* the current explicit `retrain_model.py` route, configured for 500 bars. It is consistent with the current auto-training default, but does not prove that route ran.
2. **Numerical feature parity is not established.** The workspace contains no historical OHLC candle archive with which to compare 200-, 500-, and 1,500-bar inputs at a common timestamp. I did not substitute newly downloaded data.
3. **Dependency branch consistency is unresolved.** The Python environments available in this workspace do not have `pandas-ta`, `scikit-learn`, `xgboost`, or `joblib` installed. `requirements.txt` lists intended versions, but that does not establish the historical training or production runtime environment.
4. **Lookback impact is unmeasured.** Source shows that ATR, RSI, and MACD depend on input history, but no matched-candle experiment is possible with the available files.
5. **Prediction impact is unmeasured.** The Nov 5 and Nov 6 logs contain XGB probabilities, but not the saved feature vectors or alternate lookback predictions. They cannot answer whether lookback changes moved `P_UP` across an existing decision boundary.
6. **The model is not sufficiently understood to establish safe feature parity as a production input.** This is an evidence limitation, not proof that the model is defective.

**Phase 2 is therefore not complete against its numerical acceptance criteria.** I completed the available provenance, source, artifact, log, and environment checks. No production code, artifacts, configuration, or trading behavior were changed; I did not run the bot, retrain, contact OANDA, or install packages.

## B. Evidence matrix

| Finding                                                                                     | Classification                                          | Evidence                                                                                                                                                                                                                                                                                                                                                                                                                                                                     | Severity | Remaining uncertainty                                                            |
| ------------------------------------------------------------------------------------------- | ------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- | -------------------------------------------------------------------------------- |
| Model files in this workspace have Nov 5, 2026 timestamps                                   | **CONFIRMED**                                     | Local filesystem metadata for model, scaler, manifest, and config                                                                                                                                                                                                                                                                                                                                                                                                            | P0       | Whether the deployed production files are identical                              |
| Current XGBoost model and feature manifest both specify 37 features                         | **CONFIRMED**                                     | Model JSON `num_feature=37`; manifest has 37 names                                                                                                                                                                                                                                                                                                                                                                                                                         | P2       | Scaler dimension could not be read in the available environment                  |
| Saved config records `train_lookback_bars: 5000`                                          | **CONFIRMED**                                     | [trade_model_xgb.cfg.json:18](/home/qili/projects/ai_training_cnn/trade_model_xgb.cfg.json:18)                                                                                                                                                                                                                                                                                                                                                                                | P0       | Whether this records the data actually fetched                                   |
| Explicit retraining code configures 500 bars and M15                                        | **CONFIRMED**                                     | [retrain_model.py:31](/home/qili/projects/ai_training_cnn/retrain_model.py:31), [retrain_model.py:43](/home/qili/projects/ai_training_cnn/retrain_model.py:43)                                                                                                                                                                                                                                                                                                                 | P0       | Whether this route produced the current model                                    |
| Current auto-training path’s effective lookback default is 5,000, not the profile’s 1,500 | **CONFIRMED** for checked-in source/config wiring | v685 requests `cfg_bot("TRAIN_LOOKBACK_BARS", 5000)` at [fx_trade_bot_v685.py:1217](/home/qili/projects/ai_training_cnn/fx_trade_bot_v685.py:1217). `config_bot.build_profile_cfg()` does not add that key in its returned config at [config_bot.py:171](/home/qili/projects/ai_training_cnn/config_bot.py:171). `cfg_bot()` then falls through to `config` or the default at [fx_trade_bot_v685.py:772](/home/qili/projects/ai_training_cnn/fx_trade_bot_v685.py:772). | P0       | Whether production used this exact checked-in source/config                      |
| Auto-training is the likely route for the Nov 5 bundle                                      | **LIKELY**                                        | Saved config says 5,000; current explicit retraining path sets and serializes 500, while the current auto-training path defaults to 5,000                                                                                                                                                                                                                                                                                                                                    | P0       | No training log, run ID, or target metadata proves it                            |
| Current model target was `future_return > 0`                                              | **UNRESOLVED**                                    | Auto-training uses this target; explicit retraining uses `> 0.0005`; config does not record the threshold                                                                                                                                                                                                                                                                                                                                                                  | P0       | Training route and source version at training time                               |
| Timeframe used to train the current model                                                   | **UNRESOLVED**                                    | Explicit retraining fixes M15; config does not record timeframe; available inference logs do not identify candle granularity                                                                                                                                                                                                                                                                                                                                                 | P0       | Actual training-run record or source data                                        |
| Same-timestamp lookback parity for the active feature vector                                | **UNRESOLVED**                                    | No OHLC candle archive found in workspace                                                                                                                                                                                                                                                                                                                                                                                                                                    | P0       | Historical candles for the relevant instrument/timeframe                         |
| Actual historical dependency versions                                                       | **UNRESOLVED**                                    | Requirements list versions, but the available system Python 3.12 and bundled `.conda` Python 3.14 environments lack the relevant packages                                                                                                                                                                                                                                                                                                                                  | P1       | Runtime environment inventory from training/deployment                           |
| Bot inference ran on Nov 5 and Nov 6                                                        | **CONFIRMED** for the logged runtime              | Logs record 199-bar snapshots and XGB probabilities, e.g. [fx_bot_20261105.log:67](/home/qili/projects/ai_training_cnn/logs/fx_bot_20261105.log:67), [fx_bot_20261105.log:170](/home/qili/projects/ai_training_cnn/logs/fx_bot_20261105.log:170), [fx_bot_20261106.log:224](/home/qili/projects/ai_training_cnn/logs/fx_bot_20261106.log:224)                                                                                                                                   | P1       | Logs identify runtime as v6.8.4, not the exact current v685 source or model hash |
| `ensure_model()` was invoked or auto-training attempted between Nov 5 and Nov 13          | **UNRESOLVED**                                    | Available logs do not contain `Model stale`, training, model-load, or save records; Nov 13 bot logs are empty                                                                                                                                                                                                                                                                                                                                                              | P0       | Missing deployment/service logs and training stdout/stderr                       |
| Model/scaler/manifest bundle is version-bound                                               | **CONFIRMED: no such binding in inspected code**  | Separate sequential writes and no shared ID/hash in [data_pipeline.py:582](/home/qili/projects/ai_training_cnn/data_pipeline.py:582)                                                                                                                                                                                                                                                                                                                                          | P2       | A deployment process outside this repository may add controls                    |

## C. Numerical experiment results

### Experiment availability

The requested comparison needs identical historical candles—at least 1,500 bars for the 200/500/1500 comparison—and a common final timestamp. The workspace has trade/order CSVs and runtime logs, but **no OHLC candle archive**. The Nov 5 log’s “199 bars” confirms an inference-window size in that run; it does not contain those candles or the final timestamp’s full input vector.

The system Python and bundled `.conda` Python were checked for package metadata. Neither has `pandas-ta`, `pandas-ta-classic`, `scikit-learn`, `xgboost`, or `joblib`. I did not install them. Thus I could not reproduce the feature calculations, load the scaler, or run the model on alternative feature vectors.

No new market data was downloaded or presented as historical training input.

### Active feature vector

The checked-in `trade_model_xgb.features.json` contains these 37 model inputs:

`ret_1h`, `ret_3h`, `ret_6h`, `ret_12h`, `ret_log`, `vol_12h`, `vol_24h`, `vol_48h`, `body`, `upper_wick`, `lower_wick`, `range`, `direction`, `atr`, `atr_pct`, `atr_percentile`, `atr_ma`, `atr_expanding`, `atr_ratio`, `rsi`, `rsi_slope`, `adx`, `MACD_12_26_9`, `MACDh_12_26_9`, `MACDs_12_26_9`, `dist_high_24`, `dist_low_24`, `dist_high_48`, `dist_low_48`, `dist_high_96`, `dist_low_96`, `vol_sma_ratio`, `vol_trend`, `hour`, `day_of_week`, `is_london`, `is_ny`.

**Every feature’s 200-vs-500 and 200-vs-1500 differences, final values, common-timestamp medians/maxima, and missing counts are unmeasured.** There is no evidence basis for numeric entries; reporting “zero” or estimating values would be misleading. The same limitation applies to sign changes and threshold-state changes.

| Feature group                                                                                                     | 200 vs 500   | 200 vs 1500  | Final value/difference | Missing/non-finite count |
| ----------------------------------------------------------------------------------------------------------------- | ------------ | ------------ | ---------------------- | ------------------------ |
| ATR and derived features (`atr`, `atr_pct`, `atr_percentile`, `atr_ma`, `atr_expanding`, `atr_ratio`) | Not measured | Not measured | Not measured           | Not measured             |
| RSI and `rsi_slope`                                                                                             | Not measured | Not measured | Not measured           | Not measured             |
| MACD line, signal, histogram                                                                                      | Not measured | Not measured | Not measured           | Not measured             |
| ADX                                                                                                               | Not measured | Not measured | Not measured           | Not measured             |
| Returns, log return, volatility                                                                                   | Not measured | Not measured | Not measured           | Not measured             |
| High/low distances                                                                                                | Not measured | Not measured | Not measured           | Not measured             |
| Candle geometry                                                                                                   | Not measured | Not measured | Not measured           | Not measured             |
| Volume ratio/trend                                                                                                | Not measured | Not measured | Not measured           | Not measured             |
| Time features                                                                                                     | Not measured | Not measured | Not measured           | Not measured             |

### Prediction impact

**Unable to evaluate.** The model JSON is readable and declares 37 inputs, but the available environment lacks the packages needed to load the scaler/model as a unit, and the historical candle inputs are absent. No new scaler was fitted and no model prediction was run.

Available logs show historical probabilities and a configured threshold of `0.55` for some XGB vote reporting—for example, `prob_buy=0.555` and threshold `0.55` in [fx_bot_20261105.log:170](/home/qili/projects/ai_training_cnn/logs/fx_bot_20261105.log:170). That is evidence of an inference result in that logged run, **not** evidence about how a different lookback would affect probability or decisions.

Prediction classification: **Unable to evaluate.**

## D. Training provenance

| Field                     | Established value                                                                                        | Evidence                                                                                                                                                         | Confidence                                                              |
| ------------------------- | -------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| Training route            | Likely auto-training or another 5,000-lookback route; not proven                                         | Saved config records 5,000, whereas current explicit retraining configures 500. No training event log was found.                                                 | **LIKELY**                                                        |
| Target definition         | Unknown; if auto-training ran, source target is `future_return > 0`; explicit script uses `> 0.0005` | [data_pipeline.py:359](/home/qili/projects/ai_training_cnn/data_pipeline.py:359), [retrain_model.py:106](/home/qili/projects/ai_training_cnn/retrain_model.py:106) | **UNRESOLVED**                                                    |
| Timeframe                 | Not recorded; explicit script’s timeframe is M15                                                        | [retrain_model.py:31](/home/qili/projects/ai_training_cnn/retrain_model.py:31)                                                                                    | **UNRESOLVED**                                                    |
| Training lookback         | Saved config says 5,000; actual fetch not proven                                                         | [trade_model_xgb.cfg.json:18](/home/qili/projects/ai_training_cnn/trade_model_xgb.cfg.json:18)                                                                    | **CONFIRMED** as metadata; actual data count **UNRESOLVED** |
| Feature count             | 37 in model and feature manifest                                                                         | Model JSON and `trade_model_xgb.features.json`                                                                                                                 | **CONFIRMED**                                                     |
| Feature manifest          | Local 37-name manifest; same-run linkage not cryptographically established                               | File exists, but model artifacts are ignored by Git and no hash/run ID is present                                                                                | **CONFIRMED** content; provenance **UNRESOLVED**            |
| Dependency versions       | Intended versions in requirements; historical/runtime versions unknown                                   | [requirements.txt:22](/home/qili/projects/ai_training_cnn/requirements.txt:22); available Python environments lack those packages                                 | **UNRESOLVED**                                                    |
| Training timestamp        | Local artifact mtimes: Nov 5, 2026 around 21:24 Singapore time                                           | Filesystem metadata                                                                                                                                              | **CONFIRMED** as local file times, not as a training event        |
| Latest retraining attempt | No attempt/success/failure record found in available logs                                                | Nov 5/6 logs contain inference output; Nov 13 logs are empty; no training markers                                                                                | **UNRESOLVED**                                                    |

Additional provenance evidence:

- The repository’s Nov 5 Git checkpoint is timestamped 21:33, after the local model artifacts’ 21:24 timestamps. That checkpoint does not prove how the artifacts were created.
- Model JSON, scaler, and feature manifest are ignored by Git; their history cannot identify the current model’s training run.
- Nov 5 and Nov 6 logs contain inference outputs but no retraining or model-save record. The logged runtime identifies as v6.8.4, so it cannot be reliably equated with the current checked-in v685 source.
- The checked-in profile says `TRAIN_LOOKBACK_BARS=1500`, but `build_profile_cfg()` does not expose that key, and `cfg_bot()` falls through to the default. In the checked-in v685 code, the effective auto-training fallback is **5,000**, matching the saved model config—not 1,500.

## E. Dependency and fallback branch verification

| Component | Training branch                                                                             | Inference branch                                                                                | Numerical equivalence                                                                                      | Evidence                                                                                                                                                         |
| --------- | ------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ATR       | `pandas_ta.atr(...)`; on exception, manual true range followed by rolling arithmetic mean | Same shared `ATRModule`                                                                       | **UNRESOLVED in actual runtimes.** Source has two different algorithms; which branch ran is unknown. | [data_pipeline.py:123](/home/qili/projects/ai_training_cnn/data_pipeline.py:123)                                                                                  |
| RSI       | `ta.rsi(..., length=14)`; manual Wilder fallback                                          | Same shared `FeatureEngine`                                                                   | **UNRESOLVED in actual runtimes.** Same source, but branch/version and input candles unknown.        | [data_pipeline.py:267](/home/qili/projects/ai_training_cnn/data_pipeline.py:267)                                                                                  |
| MACD      | `ta.macd(Close)`; exception logs warning and omits columns; no manual fallback            | Same shared code; missing required manifest columns cause prediction input construction to fail | **UNRESOLVED in actual runtimes.** No runtime package or branch evidence.                            | [data_pipeline.py:312](/home/qili/projects/ai_training_cnn/data_pipeline.py:312), [data_pipeline.py:421](/home/qili/projects/ai_training_cnn/data_pipeline.py:421) |
| ADX       | Project rolling implementation, period 14                                                   | Same shared implementation                                                                      | **LIKELY same calculation** if same source and candle input; actual candles/timeframe are not proven | [data_pipeline.py:52](/home/qili/projects/ai_training_cnn/data_pipeline.py:52), [data_pipeline.py:306](/home/qili/projects/ai_training_cnn/data_pipeline.py:306)   |

The fallback is a materially different ATR algorithm by construction: the fallback uses a rolling simple mean with `min_periods=1`; the primary call is `pandas_ta.atr`. Exact differences were not measured. A MACD failure is not silently replaced with neutral values: the missing feature should fail input validation for a model manifest that requires it. Historical Nov 5/6 XGB outputs show some predictions were produced, but do not prove the active MACD branch or package version.

## F. Target semantic reconciliation

The source defines two different label rules:

- Explicit retraining: `future_return > 0.0005` — [retrain_model.py:106](/home/qili/projects/ai_training_cnn/retrain_model.py:106).
- Auto-training: `future_return > 0` — [data_pipeline.py:359](/home/qili/projects/ai_training_cnn/data_pipeline.py:359).

No eligible historical OHLC training dataset was found. Therefore the requested positive/negative counts, affected-sample count and percentage, per-instrument breakdown, and changed-label return distribution **cannot be calculated**.

| Metric                            | Explicit target (`> 0.0005`) | Auto-training target (`> 0`) |
| --------------------------------- | -----------------------------: | -----------------------------: |
| Positive samples                  |                 Not measurable |                 Not measurable |
| Negative samples                  |                 Not measurable |                 Not measurable |
| Positive rate                     |                 Not measurable |                 Not measurable |
| Samples assigned different labels |                 Not measurable |                 Not measurable |
| Percentage affected               |                 Not measurable |                 Not measurable |
| Changed-label return distribution |                 Not measurable |                 Not measurable |

The semantic distinction is clear: returns in `(0, 0.0005]` are positive under the auto-training rule and negative under the explicit rule. How many samples fall in that interval is unknown.

## G. Artifact integrity

- **Model dimension:** 37, confirmed from the model JSON.
- **Manifest dimension/order:** 37 names, confirmed from the local JSON.
- **Scaler dimension:** not directly established. `joblib`/`scikit-learn` are unavailable in the inspected environments, so I did not deserialize the scaler.
- **Load-time validation:** source validates model/scaler dimensions when those objects expose `n_features_in_`, and inference selects feature columns in saved manifest order. This establishes intended behavior, not that the current production runtime successfully loaded this exact bundle.
- **Bundle generation:** the local files have closely grouped Nov 5 timestamps, which is consistent with a single save operation, but no common run ID/hash proves it.
- **Cross-run model/scaler pairing:** source does not compare run IDs or hashes; compatible dimensions can pass.
- **Stale manifest:** feature-name order is used, but no model-side semantic feature check binds names to the trained columns.
- **Changed formula under same name:** not detected by dimension or name checks.
- **Partial save:** writer saves model, scaler, features, and config sequentially; no atomic bundle or completeness marker is visible in the inspected code.

## H. Risk ranking

| Priority     | Finding                                                                                                   | Why it receives this priority                                                                                              |
| ------------ | --------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| **P0** | Training route, target, timeframe, and actual data window for current model are not established           | Without them, the intended training conditions cannot be compared to production inference conditions.                      |
| **P0** | No matched historical candles, so feature parity and prediction-impact experiments could not be performed | The central Phase 2 question remains unanswered.                                                                           |
| **P0** | No evidence whether auto-training was attempted after the model crossed the seven-day age threshold       | The local files still show Nov 5 timestamps, but production deployment state and runtime logs after Nov 6 are unavailable. |
| **P1** | ATR primary and fallback paths are different algorithms; actual branch is unknown                         | Runtime dependency or availability differences can change ATR and derived inputs.                                          |
| **P1** | MACD has no fallback, and its active runtime branch is unknown                                            | Missing MACD columns can make inference fail; auto-training could save a manifest with a different feature set.            |
| **P1** | Explicit and auto-training targets differ                                                                 | The learned objective may differ depending on route; current model provenance does not resolve which applied.              |
| **P2** | Artifact bundle lacks run ID/hash binding and atomic persistence                                          | Same-sized cross-run files or partial updates are not reliably detected.                                                   |
| **P2** | Profile’s 1,500 lookback setting is not wired through `config_bot` in the inspected code               | The active code’s fallback is 5,000, affecting auto-training conditions.                                                  |

## I. Recommended next actions

### Mandatory to finish the evidence audit

1. **Obtain the exact historical OHLC candles used for the Nov 5 training run**, including instrument, timeframe, timestamps, and enough rows to support the requested 1,500-bar comparison.

   - Addresses: feature parity, prediction impact, and label-count comparisons.
   - Code changes: no. Retraining: no.
   - Acceptance evidence: reproducible 200/500/1500 feature tables at the same final candle and label-difference counts.
2. **Obtain the training process logs or run record for the artifact save around Nov 5**, including command/entry point, effective config, target rule, timeframe, fetched row counts, and save outcome.

   - Addresses: model provenance.
   - Code changes/retraining: no.
   - Acceptance evidence: a run record tied to the model/scaler/manifest files, ideally with hashes.
3. **Obtain dependency inventory from the training and deployed inference environments.**

   - Addresses: actual ATR/RSI/MACD branch and version parity.
   - Code changes/retraining: no.
   - Acceptance evidence: package names and versions captured for both environments.
4. **Obtain bot/service logs from Nov 7–13 and confirm the deployed artifact hashes.**

   - Addresses: whether `ensure_model()` ran, whether retraining was attempted, and whether production still used the local Nov 5 bundle.
   - Code changes/retraining: no.
   - Acceptance evidence: logs showing model load/train/save outcomes plus deployed file hashes.

### Optional artifact-integrity improvement for a separate engineering discussion

Consider a later review of bundle versioning and atomic save/load behavior. This is supported by the sequential independent writes and lack of run IDs/hashes. It would require code changes, but does not require retraining merely to design. Acceptance evidence would be a load-time check that rejects model/scaler/manifest/config files whose recorded run identity or hashes do not match. No such change was made here.

**No implementation or retraining is recommended as part of this audit.** The current evidence supports identifying risks, but not choosing a feature, fallback, or target change.
