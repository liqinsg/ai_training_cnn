
# Phase 2.1 — Model Provenance Forensics

## A. Executive conclusion

The evidence supports a **likely reconstruction**, but does not establish the exact training event.

1. **Training process:** **LIKELY** the v685 bot’s `ensure_model()` auto-training route. The bot run began at 21:23:29 on Nov 5; the four model artifacts were written sequentially around 21:24:06, before the same run’s first feature snapshot at 21:24:24. The saved config’s 5,000-bar lookback also matches that route’s effective default. There is no training log or run ID to confirm it.
2. **Exact Git commit:** **UNRESOLVED.** `v2026b` at `75e9eae` was the latest branch commit before the artifact timestamp, so it is the strongest source candidate. No deployment record proves it was the code running then. The current checkout is `v2026c` at `3bec4af`; I did not switch branches.
3. **Training timeframe:** **LIKELY M15**, based on the bot’s default `--timeframe 15m`. The run log does not record its command line or candle granularity.
4. **Lookback and sample count:** the config records 5,000; **LIKELY** that was the auto-training request. Returned, closed, cleaned, and fitted row counts are **UNRESOLVED**.
5. **Target definition:** **LIKELY** `future_return > 0` if auto-training ran. The explicit trainer uses `> 0.0005`; no historical execution record determines which route produced this model.
6. **Historical dependency versions:** **UNRESOLVED.** An Oct 7 package freeze exists, but it is not tied to the Nov 5 run. The model JSON carries XGBoost version metadata `[3,3,0]`, which is supporting evidence for that XGBoost version, not a complete runtime inventory.
7. **Artifact relationship:** **LIKELY** the four local files were written by one `ModelWrapper.save()` call. Their timestamps are clustered within milliseconds in the order used by that writer. They have no shared run ID or hash manifest, so the relationship is not proven.
8. **Retraining after Nov 5:** no successful update appears in this local artifact set after Nov 5. Whether production checked for staleness or retrained elsewhere between Nov 5 and Nov 13 is **UNRESOLVED**.
9. **Recoverability:** this checkout lacks the Nov 5 training log, candle data, timestamped shell history, and a deployed artifact directory. Those are the missing records needed to prove the event.

**Assessment: PARTIALLY COMPLETE.** There is meaningful circumstantial evidence for auto-training, but not enough to state the exact historical route, data window, target, or deployed code version as fact.

## B. Reconstructed timeline

| Timestamp                             | Event                                                                              | Evidence                                                                                                                                                                               | Classification                                                               |
| ------------------------------------- | ---------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| Nov 5, 17:31 SGT                      | `v2026b` commit `75e9eae` recorded                                             | Git history; this is the latest `v2026b` commit before the artifact times                                                                                                            | **CONFIRMED** as repository history; deployed use **UNRESOLVED** |
| Nov 5, 21:23:29 SGT                   | Bot run banner logged for profile 2                                                | [fx_bot_20261105.log:47](/home/qili/projects/ai_training_cnn/logs/fx_bot_20261105.log:47)                                                                                               | **CONFIRMED** that this run was logged                                 |
| Nov 5, 21:24:06.448–21:24:06.455 SGT | Model, scaler, manifest, config mtimes, in that order                              | Local filesystem metadata and initial SHA-256 snapshot                                                                                                                                 | **CONFIRMED** as local file times; common run **LIKELY**         |
| Nov 5, 21:24:09 SGT                   | Bot proceeds to early gate and signal evaluation                                   | [fx_bot_20261105.log:50](/home/qili/projects/ai_training_cnn/logs/fx_bot_20261105.log:50)                                                                                               | **CONFIRMED**                                                          |
| Nov 5, 21:24:24 SGT                   | First logged feature snapshots show 199 bars                                       | [fx_bot_20261105.log:67](/home/qili/projects/ai_training_cnn/logs/fx_bot_20261105.log:67)                                                                                               | **CONFIRMED** for inference snapshots; not training fetch counts       |
| Nov 5, 21:24:57 SGT                   | XGB output appears in scoring; one pair logs a missing model signal                | [fx_bot_20261105.log:163](/home/qili/projects/ai_training_cnn/logs/fx_bot_20261105.log:163), [fx_bot_20261105.log:170](/home/qili/projects/ai_training_cnn/logs/fx_bot_20261105.log:170) | **CONFIRMED** for logged inference behavior                            |
| Nov 6, 18:04 SGT                      | Another bot run logs 199-bar snapshots                                             | [fx_bot_20261106.log:25](/home/qili/projects/ai_training_cnn/logs/fx_bot_20261106.log:25), [fx_bot_20261106.log:54](/home/qili/projects/ai_training_cnn/logs/fx_bot_20261106.log:54)     | **CONFIRMED** for logged inference                                     |
| Nov 7–13                             | No nonempty app logs found in the local `logs/` directory                        | Log inventory; Nov 13 files are empty                                                                                                                                                  | **CONFIRMED** for this checkout, not for remote production             |
| At audit                              | Active local crontab has no retrain or v685 entries; systemd unit is not installed | Read-only `crontab -l` count and `systemctl show`                                                                                                                                  | **CONFIRMED** for the audit host only                                  |

The timing fits `ensure_model()` running during the Nov 5 bot startup, but the app log contains **no** `Model stale`, training, model-save, or training-complete message. That missing evidence is why the route remains **LIKELY**, not **CONFIRMED**.

## C. Training provenance matrix

| Provenance field       | Finding                                                                                                        | Evidence                                                                                                                                                                                                              | Classification                                                       |
| ---------------------- | -------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| Training entry point   | Likely `fx_trade_bot_v685.main()` → `ensure_model()` → `ModelWrapper.fit()` → `ModelWrapper.save()` | At `75e9eae`, v685 calls `ensure_model()`; the helper trains when the split is missing or stale. See historical `fx_trade_bot_v685.py:1622` and `fx_trade_bot_ml.py:31–63`.                                  | **LIKELY**                                                     |
| Git commit             | Candidate: `75e9eae` on `v2026b`; exact deployed commit unknown                                            | It is the latest `v2026b` commit before Nov 5, 21:24. No deployment record or commit ID appears in the logs.                                                                                                        | **UNRESOLVED**                                                 |
| Training route         | Auto-training is more likely than explicit retraining                                                          | Artifact timestamp sequence overlaps the bot startup; saved lookback is 5,000, versus 500 in the explicit script; no Nov 5 explicit-trainer log or new timestamped backup is present.                                 | **LIKELY**                                                     |
| Timeframe              | Likely M15 under the bot default                                                                               | Historical bot source defaults `--timeframe` to `15m` (`75e9eae:fx_trade_bot_v685.py:133`) and maps that to OANDA granularity. The Nov 5 log does not record timeframe or command arguments.                    | **LIKELY**                                                     |
| Requested bars         | Likely 5,000 if auto-training ran                                                                              | Saved config has `train_lookback_bars: 5000`; `ensure_model()` passes that value as fetch `count` (`75e9eae:fx_trade_bot_ml.py:47`). The explicit trainer sets 500 (`75e9eae:retrain_model.py:35,70`).      | **LIKELY**                                                     |
| Returned candles       | Unknown                                                                                                        | No training fetch log or candle archive. The inference log’s 199 bars are not training data.                                                                                                                         | **UNRESOLVED**                                                 |
| Closed candles         | Unknown                                                                                                        | Source trims to closed candles, but no training response or count was logged.                                                                                                                                         | **UNRESOLVED**                                                 |
| Valid feature rows     | Unknown                                                                                                        | No recorded post-feature count by instrument.                                                                                                                                                                         | **UNRESOLVED**                                                 |
| Final training samples | Unknown                                                                                                        | No `Training on N rows` or fit sample count in available logs.                                                                                                                                                      | **UNRESOLVED**                                                 |
| Target rule            | Likely `future_return > 0` if auto-training ran; explicit route is `> 0.0005`                              | Auto path calls `FeatureEngine.build_target()` (`data_pipeline.py:359–364`); explicit script uses `TARGET_THRESHOLD=0.0005` (`retrain_model.py:37,106–108`). Config has no target threshold or route field. | **UNRESOLVED**                                                 |
| Target horizon         | Six candles in saved config                                                                                    | `target_horizon: 6` in saved config; both code paths use horizon 6.                                                                                                                                                 | **CONFIRMED** as saved config; historical use **LIKELY** |
| Feature configuration  | Saved config enables ATR, RSI, MACD, ADX; periods 14; 37 names in manifest                                     | `trade_model_xgb.cfg.json` and `trade_model_xgb.features.json`                                                                                                                                                    | **CONFIRMED** as local artifact contents                       |
| Instrument universe    | Likely profile 2’s 13 configured pairs if the auto path ran                                                   | Nov 5 bot log shows 13 candidates; auto-training receives the bot’s pair list. Successful training fetches per pair are not recorded.                                                                                | **LIKELY**                                                     |
| Dependency versions    | Oct 7 candidate freeze lists versions; Nov 5 runtime versions unknown                                          | `/home/qili/ai-sprint-freeze-20261007.txt`; model metadata includes `[3,3,0]`                                                                                                                                     | **UNRESOLVED**                                                 |
| Artifact run identity  | No run ID/hash linkage                                                                                         | No ID in model JSON, scaler, manifest, or config                                                                                                                                                                      | **CONFIRMED**                                                  |

The saved 5,000-bar value is metadata, not proof that 5,000 candles were returned or fitted. The current `config_profile.json` value of 1,500 is not the effective value in the inspected bot code: `build_profile_cfg()` does not expose `TRAIN_LOOKBACK_BARS`, and `cfg_bot()` falls through to the 5,000 default (`75e9eae:config_bot.py:171–181`; `fx_trade_bot_v685.py:772–776,1215`).

## D. Artifact integrity findings

### Initial and final snapshots

The artifact hashes and metadata were identical before and after the investigation.

| Local artifact                    |          Size | Local modification time (SGT) | SHA-256                                                              |
| --------------------------------- | ------------: | ----------------------------- | -------------------------------------------------------------------- |
| `trade_model_xgb.json`          | 791,167 bytes | Nov 5, 21:24:06.448557380     | `d11c33cdbf09e01422ddd8e94bd52a4c0a88dd428587a315fc63cf027612984e` |
| `scaler.joblib`                 |   1,455 bytes | Nov 5, 21:24:06.454082205     | `1853009b03bd3a5d6d880c4ccca3e3686a81ad09bfd3b2eaffe812ef99fab7a7` |
| `trade_model_xgb.features.json` |     540 bytes | Nov 5, 21:24:06.454438785     | `a4d38adb0f7054d44dd7f432fbf9e216ee10f7dd226ec5b3dba6566deaa168cd` |
| `trade_model_xgb.cfg.json`      |     455 bytes | Nov 5, 21:24:06.455903204     | `e3ff196491dc503da1d85c9b30c8471044b8108c379677a836b4354d0f5c88f4` |

- `trade_model_xgb.pkl` is **absent** locally. The model artifact is the JSON file; the scaler is separate.
- The model JSON declares 37 features and 200 trees. Its embedded `feature_names` is empty; the external manifest supplies the names and order.
- The manifest has 37 names. The config records feature flags/periods, target horizon 6, and lookback 5,000, but no target expression, timeframe, training route, source commit, or run ID.
- The four files’ mtimes are separated by milliseconds and match `ModelWrapper.save()`’s write order. This is strong evidence for a common save call, but not proof of one training run or correct pairing.
- I did not deserialize `scaler.joblib`: the available Python environments lack `joblib` and scikit-learn, and the spec prohibits installing packages. Its feature dimension therefore remains **UNRESOLVED**.
- The model/scaler/manifest/config have no observed shared hash or training-run identifier. The model JSON’s feature dimension matching the manifest does not prove the scaler belongs to it.

The repository was on `v2026c` at `3bec4af30352304a32c379964c5534ceb631bfdb` both before and after inspection. The only working-tree entries were pre-existing untracked audit reports; tracked-file diffs were empty. No investigated file changed.

## E. Historical environment and execution records

The Oct 7 package freeze lists:

| Component         | Candidate snapshot                                                               | Historical Nov 5 training environment                      |
| ----------------- | -------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| Python            | Not recorded in pip freeze; separate `environment.yml` declares Python 3.12.13 | **UNRESOLVED**                                       |
| pandas            | 3.0.6                                                                            | **UNRESOLVED**                                       |
| numpy             | 2.5.3                                                                            | **UNRESOLVED**                                       |
| pandas-ta         | 0.4.71b0                                                                         | **UNRESOLVED**                                       |
| pandas-ta-classic | 0.6.52                                                                           | **UNRESOLVED**                                       |
| scikit-learn      | 1.9.1                                                                            | **UNRESOLVED**                                       |
| xgboost           | 3.3.0 in freeze; model JSON metadata is `[3,3,0]`                              | **LIKELY**, not proven as the exact training package |
| joblib            | 1.5.3                                                                            | **UNRESOLVED**                                       |

The freeze predates the event and is not tied to the Nov 5 process. The candidate `ai-sprint` executable paths referenced in the checked-in scheduler files are not present on this audit host.

Other execution evidence:

- The readable Bash history contains no `retrain_model.py` reference. It has no timestamp markers, so it cannot establish the absence of an invocation on a particular date.
- The checked-in `crontab` file contains a daily explicit retraining entry, but it is not the active crontab. The active local crontab has no matching trainer or v685 entry.
- The checked-in service file points to an older `fx_trade_bot_v6.py` path under `/home/nie`; `systemctl` reports no such installed unit on this host.
- No `bot_cron.log` or separate retraining log was found in the inspected project directories.
- Nov 5/6 app logs record bot inference. Available app logs contain no retraining markers. Nov 13 app logs are empty.

These records do not establish what ran on a separate deployment host.

## F. Remaining unknowns and evidence needed

| Unresolved question                                    | Evidence needed                                                                                   |
| ------------------------------------------------------ | ------------------------------------------------------------------------------------------------- |
| Did `ensure_model()` produce the Nov 5 bundle?       | Nov 5 training stdout/stderr or service log recording stale decision, fetched data, fit, and save |
| Was the deployed source exactly `75e9eae`?           | Deployment checkout/commit record or a deployed source snapshot/hash from that run                |
| Was the actual target `> 0` or `> 0.0005`?         | Training log/source commit tied to the save event, or run metadata recording the expression       |
| What timeframe was used?                               | Recorded command line or training fetch log showing OANDA granularity                             |
| How many candles and samples were used?                | Per-instrument fetch counts, closed-candle counts, post-clean counts, and fit sample count        |
| Which dependency versions were active?                 | `pip freeze`/environment export from the exact trainer process or deployment host on Nov 5      |
| Does the scaler match this model/manifest?             | Scaler metadata from the exact environment or a trusted saved dimension/hash record               |
| Was there a successful production retrain after Nov 5? | Nov 7–13 deployment logs and deployed artifact hashes                                            |
| Are local files the deployed files?                    | Read-only comparison of deployed model/scaler/manifest/config hashes                              |

## G. Phase 2.1 completion assessment

**PARTIALLY COMPLETE.**

The timing, saved 5,000-bar config, model save order, and source behavior make auto-training the strongest explanation for the Nov 5 artifact write. The precise training route, commit, label rule, candle timeframe, actual sample counts, and historical environment cannot be confirmed without training/deployment logs or a run manifest. Local artifacts are unchanged.

**Smallest next action:** recover the Nov 5 training/service log and the Nov 7–13 deployment logs from the host that ran this bot, with artifact hashes if available. That evidence would resolve the route, target, actual fetch counts, and whether later retraining succeeded. No implementation or retraining should start on the basis of the current evidence.
