
好。我们正式进入 Phase 2.1 — Model Provenance Forensics。

这次只追查 Nov 5 模型的来源，不再扩展到 feature 数值实验，也不修改任何生产代码。

调查的核心不是猜测它来自 auto-training，而是尽可能恢复一条完整的证据链：

`Training Entry Point → Effective Configuration → Data Fetch → Label Generation → Model Fit → Artifact Save`

最终要能回答：Nov 5 的 model、scaler、feature manifest 和 config，究竟由哪一次训练产生？

## 给 Claude 的执行任务

# 【Strict Spec】Phase 2.1 — Model Provenance Forensics

## 1. Mission

Determine, using recoverable evidence, the exact training process that produced the local November 5, 2026 v685 model artifacts.

Repository:
`~/projects/ai_training_cnn`

Known branch:
`v2026b`

Artifacts under investigation:

- `trade_model_xgb.json`
- `trade_model_xgb.pkl` or the corresponding scaler artifact
- `trade_model_xgb.features.json`
- `trade_model_xgb.cfg.json`

The exact filenames and artifact relationships must be verified before proceeding.

### Primary question

Can we identify the exact training pipeline and effective training configuration that produced the November 5 model artifacts?

The investigation must establish, or explicitly fail to establish:

1. Training entry point and route.
2. Actual source-code version used.
3. Effective runtime configuration.
4. Requested and returned candle counts.
5. Actual training timeframe.
6. Actual target/label definition.
7. Actual feature-generation configuration.
8. Python and dependency versions.
9. Model/scaler/manifest/config artifact relationships.
10. Training completion and artifact-save outcome.

This is a forensic investigation, not an implementation task.

---

## 2. 【Strict Spec】Operational Restrictions

### Absolutely prohibited

- Do NOT modify production source code.
- Do NOT modify `retrain_model.py`, `data_pipeline.py`, `fx_trade_bot_v685.py`, or configuration files.
- Do NOT execute the production bot.
- Do NOT call OANDA APIs.
- Do NOT initiate training or retraining.
- Do NOT call `ensure_model()` if it could initiate training.
- Do NOT overwrite, regenerate, rename, or move model artifacts.
- Do NOT install packages or alter Python environments.
- Do NOT change cron jobs, services, environment variables, or deployment configuration.
- Do NOT expose credentials, API tokens, account IDs, or other secrets in the report.

### Permitted

- Read-only Git inspection.
- Read-only filesystem metadata inspection.
- Read-only examination of existing logs.
- Read-only shell-history inspection where available and authorized.
- Read-only cron/systemd/service configuration inspection.
- Read-only artifact metadata and hashes.
- Read-only Python environment and package inventory.
- Read-only deployment-directory comparison.

If access is unavailable, report it. Do not attempt to gain access by changing permissions or credentials.

### Integrity protection

Before examining artifacts:

1. Record exact paths, sizes, modification timestamps and SHA-256 hashes.
2. Record Git branch, HEAD commit and working-tree status.
3. Do not alter any investigated file.
4. At the end, repeat the artifact hash and metadata checks.
5. Report any difference between initial and final snapshots.

The investigation must leave the repository and artifacts unchanged.

---

## 3. P0 — Recover the November 5 Training Event

Establish whether there is evidence of a specific training event that generated the artifacts.

### 3.1 Search existing logs

Inspect relevant available logs for:

- Model training start/end.
- `ensure_model()` invocation.
- Missing-model detection.
- Model stale detection.
- Retraining decisions.
- Data fetching.
- Training sample counts.
- Feature generation.
- Model fitting.
- Scaler fitting.
- Model save.
- Scaler save.
- Feature manifest save.
- Configuration save.
- Exceptions or interrupted runs.

Prioritize the period surrounding November 5, 2026.

Extend the search to November 4–7 if needed to establish the event timeline.

Do not treat ordinary inference messages as training evidence.

### 3.2 Search shell and process history

Where accessible, inspect:

- Shell history.
- Available command history.
- Existing process logs.
- Cron execution records.
- Service logs.
- Existing deployment scripts.
- Existing task-runner logs.

Search for execution of:

- `retrain_model.py`
- `fx_trade_bot_v685.py`
- Related training scripts.
- Any alternative model-generation scripts discovered in the repository.

Do not print credentials or sensitive command arguments into the report.

A shell-history command is evidence that a command was entered, not proof that it completed successfully.

### 3.3 Search Git history

Inspect Git history around November 4–7 and any relevant later commits.

Establish:

- Which code versions existed at the time.
- Whether training-related code changed.
- Whether the explicit retraining route was different at that point.
- Whether auto-training implementation or configuration changed.
- Whether any deployment script selected a particular branch or commit.

Use historical source inspection where possible.

Do not assume current source code is identical to the source used on November 5.

Required evidence should include relevant commit hashes and source locations.

---

## 4. P0 — Reconstruct the Effective Training Configuration

The Phase 2 audit found:

- Explicit retraining configures 500 bars and M15.
- Current auto-training wiring appears to default to 5,000 bars.
- The saved model config records `train_lookback_bars: 5000`.
- The profile's apparent 1,500-bar setting is not necessarily effective.

Investigate the actual historical source and configuration.

### Required fields

| Field                  | Required finding                |
| ---------------------- | ------------------------------- |
| Training entry point   | Exact script/function           |
| Git commit             | Exact commit or unresolved      |
| Branch                 | Exact branch or unresolved      |
| Training route         | Explicit / auto / other         |
| Timeframe              | Actual configured granularity   |
| Requested lookback     | Requested bars                  |
| Returned candles       | Actual fetched bars             |
| Closed candles         | Actual usable closed bars       |
| Valid feature rows     | Rows remaining after processing |
| Final training samples | Samples passed to model fitting |
| Target rule            | Exact expression                |
| Target horizon         | Exact number of candles         |
| Feature configuration  | Actual settings                 |
| Instrument universe    | Actual instruments              |
| Dependency environment | Python and package versions     |

### Important distinction

Do not conflate:

- Requested lookback.
- API-returned candles.
- Closed candles.
- Rows remaining after feature generation.
- Rows remaining after cleaning.
- Samples used for fitting.

The saved config value of 5,000 is metadata. It is not proof that 5,000 candles were successfully retrieved or used.

---

## 5. P0 — Establish the Actual Target Definition

The current source contains two different definitions:

Explicit retraining:

`future_return > 0.0005`

Auto-training:

`future_return > 0`

Do not infer which one produced the November 5 model from current source alone.

### Required investigation

1. Identify the source version that executed the training.
2. Inspect the exact target-generation implementation at that version.
3. Establish the target horizon.
4. Establish any filtering, shift, or row-dropping behavior applied before fitting.
5. Identify whether the target definition was configurable or hardcoded.
6. Determine whether the saved config contains any target-related metadata.

Report the exact expression and its source evidence.

If no historical execution evidence exists, the result must remain UNRESOLVED.

Do not reconstruct labels from a modern source version and claim they were the historical labels.

---

## 6. P0 — Establish the Artifact Generation Relationship

Investigate whether the November 5 files can be linked to one specific training run.

### Required checks

- Exact artifact paths.
- File sizes.
- Modification timestamps.
- SHA-256 hashes.
- Any embedded model attributes.
- Any embedded training metadata.
- Scaler metadata, where readable without installing packages.
- Feature manifest contents and ordering.
- Config contents.
- Existing training-run identifiers.
- Existing save logs or completion markers.

Determine whether the files were:

1. Saved by one common training process.
2. Saved by separate processes.
3. Copied from another directory.
4. Deployed from another machine.
5. Generated by a process that cannot be identified.

A close grouping of modification timestamps is supporting evidence only.

A matching 37-feature dimension is not proof that model, scaler and manifest belong to the same training run.

Do not deserialize artifacts if doing so requires installing missing packages or changing environments. Report the limitation.

---

## 7. P1 — Recover the Historical Runtime Environment

Inspect existing environment records.

Potential sources:

- `requirements.txt`
- `pip freeze` outputs, if already saved
- Conda environment YAML files
- Existing environment metadata
- Deployment logs
- Service configuration
- Python executable paths in logs
- Existing package inventory files

Required packages include:

- pandas
- numpy
- pandas-ta
- pandas-ta-classic
- scikit-learn
- xgboost
- joblib

Report:

| Component         | Training environment | Current available environment | Evidence |
| ----------------- | -------------------- | ----------------------------- | -------- |
| Python            |                      |                               |          |
| pandas            |                      |                               |          |
| numpy             |                      |                               |          |
| pandas-ta         |                      |                               |          |
| pandas-ta-classic |                      |                               |          |
| scikit-learn      |                      |                               |          |
| xgboost           |                      |                               |          |
| joblib            |                      |                               |          |

Do not present `requirements.txt` as evidence of installed historical versions.

If historical environment evidence cannot be recovered, mark the field UNRESOLVED.

---

## 8. P1 — Establish Whether Production Retrained After November 5

Investigate November 6–13, 2026.

The default retraining interval is seven days, but configuration alone does not establish execution.

Find evidence of:

- Bot startup.
- `ensure_model()` invocation.
- Model age calculation.
- Stale-model decision.
- Retraining start.
- Data fetch.
- Training completion or failure.
- Artifact replacement.
- Model reload.
- Deployment of updated artifacts.

Distinguish these outcomes:

- Model was never checked.
- Model was checked and considered fresh.
- Model was considered stale but training was not started.
- Training started but failed.
- Training completed and artifacts were saved.
- Training completed but artifacts were not deployed.
- Outcome unknown.

If available, compare local and deployed artifact hashes.

Do not assume local filesystem timestamps represent production deployment timestamps.

---

## 9. Evidence Classification

Every conclusion must use one of these labels:

**CONFIRMED**
Directly supported by reliable historical evidence.

**LIKELY**
Supported by multiple clues, but the exact event cannot be established.

**UNRESOLVED**
Evidence is missing, ambiguous, or insufficient.

For every major finding, include:

- Evidence source.
- Exact file/path.
- Timestamp, if applicable.
- Git commit, if applicable.
- Relevant source line or log excerpt.
- What the evidence proves.
- What it does not prove.

Separate current-source behavior from historical runtime behavior.

---

## 10. Final Deliverables

Produce one report with the following sections.

### A. Executive Conclusion

Answer directly:

1. Do we know which training process produced the November 5 model?
2. Do we know the exact Git commit?
3. Do we know the actual training timeframe?
4. Do we know the actual lookback and number of samples used?
5. Do we know the exact target definition?
6. Do we know the historical dependency versions?
7. Can we link the model, scaler, manifest and config to the same run?
8. Did any successful retraining occur after November 5?
9. Which evidence can no longer be recovered?

### B. Reconstructed Training Timeline

Use a chronological table.

| Timestamp | Event | Evidence | Classification |
| --------- | ----- | -------- | -------------- |
|           |       |          |                |

Do not invent missing events.

### C. Training Provenance Matrix

| Provenance field      | Finding | Evidence | Classification |
| --------------------- | ------- | -------- | -------------- |
| Training entry point  |         |          |                |
| Git commit            |         |          |                |
| Training route        |         |          |                |
| Timeframe             |         |          |                |
| Requested bars        |         |          |                |
| Actual bars           |         |          |                |
| Training samples      |         |          |                |
| Target definition     |         |          |                |
| Target horizon        |         |          |                |
| Dependency versions   |         |          |                |
| Artifact run identity |         |          |                |

### D. Artifact Integrity Findings

Explain whether the current artifacts can be tied to one training run and what evidence supports that conclusion.

### E. Remaining Unknowns

List each unresolved question and the exact evidence that would be needed to resolve it.

### F. Phase 2.1 Completion Assessment

Choose one:

- COMPLETE — provenance established with sufficient evidence.
- PARTIALLY COMPLETE — some provenance recovered, critical fields unresolved.
- BLOCKED — necessary historical evidence is unavailable.

Explain the decision.

### G. Recommended Next Action

Recommend only the smallest next action supported by the findings.

Do not jump to implementation, retraining, or numerical parity experiments unless the provenance evidence justifies proceeding.

---

## 11. Acceptance Criteria

Phase 2.1 is complete only if:

- The training route is established or explicitly marked unresolved.
- Historical source version is established or explicitly marked unresolved.
- Actual target definition is established or explicitly marked unresolved.
- Actual timeframe and effective data window are established or explicitly marked unresolved.
- Artifact relationships are investigated.
- Post-November 5 retraining status is investigated.
- Every major finding has evidence and a confidence classification.
- Initial and final artifact hashes match.
- No production code, model artifacts, configuration, environment, or trading behavior has changed.

**Important: An honest BLOCKED or PARTIALLY COMPLETE result is acceptable. A plausible but unsupported training story is not.**

Do not begin Phase 2.2 or make any implementation changes within this task.

## 执行后的验收重点

我会特别检查 Claude 有没有犯这三个错误：

1. 把 5,000 config 当成 5,000 根实际训练数据。
2. 用当前 Git 源码推断 Nov 5 的历史执行行为。
3. 把文件时间接近当成同一训练任务的证明。

这三项如果没有处理好，报告即使很长，也不能算完成 provenance recovery。

等 Claude 返回结果，把完整报告贴过来。我们再判断是 `COMPLETE`、`PARTIALLY COMPLETE` 还是 `BLOCKED`，再决定 Phase 2.2。

如果你希望我明天提醒你检查 Claude 的调查结果，可以用下面的提醒设置：

🔎Remind me to review Phase 2.1 resultsTap to set up
