
这一步我建议正式进入 Phase 2：Evidence-Based Consistency Verification。

Phase 1 已经找到了训练与推理之间的潜在分叉，但目前主要是静态代码审计。Phase 2 不应该急着修代码或重新训练模型，而是要回答一个更关键的问题：

当前 v685 使用的模型，其训练条件与实际推理条件究竟相差多少？这些差异是否足以改变交易信号？

下面这份英文任务说明可以直接交给 Claude。它是纯审计任务，不要求 Claude 修改生产代码。

# 【Strict Spec】v685 Training / Inference Feature Consistency Audit — Phase 2

## 1. Objective

Phase 1 identified several potential inconsistencies between model training and production inference.

Phase 2 must move from static code inspection to evidence-based verification.

The primary objective is to establish whether the current production model receives numerically and semantically equivalent features under its actual inference conditions, compared with the conditions under which it was trained.

**This is an investigation and verification task, NOT an implementation task.**

Do not modify production logic, retrain the production model, replace model artifacts, or change trading behavior.

## 2. Strict Operational Constraints

### 2.1 No production changes

- Do NOT modify `fx_trade_bot_v685.py`.
- Do NOT modify `retrain_model.py`.
- Do NOT modify `data_pipeline.py`.
- Do NOT modify production configuration or environment files.
- Do NOT overwrite, regenerate, or replace any existing model artifacts.
- Do NOT trigger `ensure_model()` in a way that could initiate production retraining.
- Do NOT submit orders or interact with a live OANDA account.

### 2.2 Permitted activities

- Read-only source-code inspection.
- Read-only inspection of model artifacts and metadata.
- Read-only inspection of existing logs and deployment records.
- Offline numerical experiments using existing historical candle data.
- Temporary diagnostic scripts outside production source files.
- Temporary reports and experiment outputs in a clearly separated audit directory.

If historical candle data is unavailable, report the limitation. Do not silently substitute newly downloaded data and present it as the original production input.

### 2.3 Evidence discipline

Every finding must be classified as:

- **CONFIRMED** — directly established by source code, artifacts, logs, or reproducible experiments.
- **LIKELY** — supported by evidence but not conclusively established.
- **UNRESOLVED** — insufficient evidence.

Clearly distinguish:

1. What the code is designed to do.
2. What the production runtime actually did.
3. What the numerical experiment demonstrates.

Do not treat a successful import, matching feature count, or successful model load as proof of numerical consistency.

---

# 3. P0 — Establish the Actual Production Model Provenance

Before conducting numerical comparisons, establish what model is actually being evaluated.

The Phase 1 audit found:

- Model artifacts dated November 5, 2026.
- Model input dimension: 37.
- Feature manifest dimension: 37.
- Default retraining interval: 7 days.
- Explicit retraining and production auto-training use different target definitions.
- Explicit retraining uses 500 M15 candles.
- Production auto-training uses a configurable lookback, with a checked-in profile value of 1500.
- Production inference normally fetches 200 candles.
- Inference supports M15, H1, and H4.

These are important facts, but they do not establish the provenance of the current model.

### Required investigation

Establish, where evidence permits:

1. Which training route generated the November 5 model:
   - Explicit `retrain_model.py`
   - Production `ensure_model()` auto-training
   - Another route, if discovered
2. Which target definition was used:
   - `future_return > 0.0005`
   - `future_return > 0`
   - Another definition
3. Which timeframe was used.
4. Which historical lookback was used.
5. Which feature manifest and feature-generation configuration were used.
6. Which dependency versions were active during training.
7. Whether `ensure_model()` was invoked between November 5 and November 13.
8. Whether an automatic retraining attempt succeeded, failed, or was skipped.

### Evidence sources

Inspect available:

- Production logs.
- Retraining logs.
- Artifact timestamps and metadata.
- Deployment records.
- Git history.
- Runtime configuration.
- Model save/load records.

Do not infer the training route from artifact timestamps alone.

### Required output

Produce a provenance table:

| Field                     | Established value | Evidence | Confidence |
| ------------------------- | ----------------- | -------- | ---------- |
| Training route            |                   |          |            |
| Target definition         |                   |          |            |
| Timeframe                 |                   |          |            |
| Training lookback         |                   |          |            |
| Feature count             |                   |          |            |
| Feature manifest          |                   |          |            |
| Dependency versions       |                   |          |            |
| Training timestamp        |                   |          |            |
| Latest retraining attempt |                   |          |            |

If provenance cannot be established, state exactly which missing evidence prevents it.

---

# 4. P0 — Numerical Feature Parity Experiment

This is the central experiment of Phase 2.

The purpose is to measure how much the actual feature values change when the same historical market data is processed under different input-history lengths.

### 4.1 Experimental design

Use identical historical candle data wherever possible.

Use the same:

- Instrument.
- Timeframe.
- Candle timestamps.
- Candle prices.
- Feature configuration.
- FeatureEngine implementation.
- Dependency environment.

For a given instrument and timeframe, construct comparable inputs with:

- 200 candles.
- 500 candles.
- 1500 candles.

The comparison must use the same final candle timestamp.

Do not compare different market periods and attribute the resulting differences to lookback length.

If fewer than 1500 historical candles are available, report the limitation rather than fabricating the missing input.

### 4.2 Features requiring explicit examination

At minimum:

- ATR
- ATR percentage
- ATR moving average
- ATR percentile
- RSI
- MACD
- MACD signal
- MACD histogram
- ADX
- Returns and log returns
- Realized volatility
- Rolling high/low distances
- Candle geometry
- All remaining features in the active 37-feature manifest

Do not restrict the experiment to the features listed above. The objective is to evaluate the entire active feature vector.

### 4.3 Numerical comparison

For each feature, calculate:

- Value at the final common candle.
- Absolute difference.
- Relative difference, where mathematically meaningful.
- Median absolute difference across common timestamps.
- Maximum absolute difference across common timestamps.
- Number of missing or non-finite values.
- Whether the feature changes sign, classification, or threshold state.

Use a comparison table:

| Feature | 200 vs 500 | 200 vs 1500 | Max difference | Missing values | Assessment |
| ------- | ---------- | ----------- | -------------- | -------------- | ---------- |
| ATR     |            |             |                |                |            |
| RSI     |            |             |                |                |            |
| MACD    |            |             |                |                |            |
| ADX     |            |             |                |                |            |

Include the actual numerical values and comparison methodology.

Do not invent a universal acceptable tolerance. Report observed differences first, then explain their potential significance.

### 4.4 Important distinction

A difference between 200 and 500 candles does not automatically establish a defect.

The audit must determine:

- Whether the difference is expected from indicator initialization.
- Whether it persists after sufficient warm-up.
- Whether it affects only early observations or remains material at the final inference row.
- Whether it is large enough to affect downstream predictions.

---

# 5. P1 — Dependency and Fallback Branch Verification

Phase 1 identified a potentially important ATR implementation difference.

The normal branch uses `pandas_ta`, while the fallback uses a rolling arithmetic mean of True Range.

MACD has no equivalent manual fallback.

### Required investigation

Establish the actual dependency environment used by:

1. Explicit training.
2. Production auto-training, if applicable.
3. Production inference.

Inspect actual installed distributions and versions where possible.

Do not rely only on `requirements.txt`.

### ATR experiment

Using identical candles, compare:

- `pandas_ta` ATR output.
- The fallback ATR output.

Report:

- Final ATR values.
- Absolute and relative differences.
- Differences across the common timestamp range.
- Downstream differences in ATR-derived features.

Determine whether the fallback branch is merely a recovery mechanism or a materially different feature-generation algorithm.

### MACD experiment

Establish:

- Whether MACD calculation succeeds in the actual runtime environment.
- Whether the active 37-feature manifest requires MACD-related columns.
- What happens when MACD calculation fails.
- Whether training and inference respond identically to that failure.

Do not introduce a new MACD fallback.

### Required output

A branch verification table:

| Component | Training branch | Inference branch | Numerical equivalence | Evidence |
| --------- | --------------- | ---------------- | --------------------- | -------- |
| ATR       |                 |                  |                       |          |
| RSI       |                 |                  |                       |          |
| MACD      |                 |                  |                       |          |
| ADX       |                 |                  |                       |          |

---

# 6. P0 — Measure the Impact on Model Predictions

Feature differences matter only insofar as they can affect the model's output.

This experiment must measure that impact.

### 6.1 Experimental conditions

Use the same loaded model, scaler, feature manifest, and final candle timestamp.

Compare model predictions using feature vectors generated from:

- 200-candle input.
- 500-candle input.
- 1500-candle input.

Only perform comparisons for conditions where the required features are available and the feature vector can be constructed validly.

Apply the existing scaler and feature ordering exactly as production inference does.

Do not fit a new scaler.

Do not retrain the model.

### 6.2 Required measurements

For every valid comparison, report:

- `P_UP` for each input condition.
- Absolute probability difference.
- Predicted direction.
- Whether the direction changes.
- Whether the result crosses any existing production decision threshold.
- Whether the model output changes from actionable to non-actionable, if that distinction exists in the current implementation.

Do not invent a new threshold.

### 6.3 Interpretation

Classify the results:

- **No material prediction impact observed**
- **Prediction magnitude changes, direction remains stable**
- **Decision boundary sensitivity observed**
- **Direction reversal observed**
- **Unable to evaluate**

A stable direction does not mean the features are equivalent.

A probability change does not automatically mean the model is defective.

Explain the actual significance using the existing production decision logic.

---

# 7. P1 — Training Target Semantic Reconciliation

Phase 1 established two different target definitions:

Explicit retraining:

`future_return > 0.0005`

Production auto-training:

`future_return > 0`

These represent different learning objectives.

### Required investigation

1. Establish which target definition was used for the current model.
2. Quantify how many historical samples would receive different labels under the two definitions.
3. Report the percentage of affected samples.
4. Break down the affected samples by instrument, where possible.
5. Examine the distribution of returns for the samples whose labels change.
6. Explain the practical meaning of the difference.

Use a comparison table:

| Metric                        | Explicit target | Auto-training target |
| ----------------------------- | --------------- | -------------------- |
| Positive samples              |                 |                      |
| Negative samples              |                 |                      |
| Positive rate                 |                 |                      |
| Samples with different labels |                 |                      |
| Percentage affected           |                 |                      |

Do not assume that either target is correct.

Do not recommend changing the target until the consequences are quantified and discussed.

---

# 8. P2 — Artifact Integrity Inspection

Inspect the existing model bundle without changing it.

Evaluate whether the following artifacts can be proven to belong to the same training run:

- Model JSON.
- Scaler.
- Feature manifest.
- Training configuration.
- Any metadata or sidecar files.

Check:

- Feature names and order.
- Feature dimensions.
- Scaler input dimensions.
- Model input dimensions.
- Available timestamps.
- Existing hashes or identifiers.
- Whether the artifact files appear to have been generated together.

A matching dimension of 37 is not sufficient proof of bundle consistency.

Report whether the existing artifact structure can detect:

- A model from one training run paired with another scaler.
- A stale feature manifest.
- A changed feature formula retaining the same feature name.
- A partially completed artifact save.

Do not implement a new artifact format in this phase.

---

# 9. Final Deliverables

Produce one consolidated Phase 2 report with the following sections:

## A. Executive Conclusion

Answer directly:

1. Is the current model's training provenance established?
2. Is training/inference numerical parity established?
3. Are dependency branches consistent?
4. Do lookback differences materially affect the final feature vector?
5. Do observed feature differences affect `P_UP` or trading decisions?
6. Is the current model sufficiently understood to be trusted as a production decision input?

Avoid a vague overall statement such as "mostly consistent."

## B. Evidence Matrix

| Finding | Classification | Evidence | Severity | Remaining uncertainty |
| ------- | -------------- | -------- | -------- | --------------------- |
|         |                |          |          |                       |

## C. Numerical Experiment Results

Include complete feature comparison and prediction comparison tables.

## D. Training Provenance

Document the strongest evidence available for the current model's origin.

## E. Risk Ranking

Use:

- P0 — Prevents reliable interpretation of current production model behavior.
- P1 — Material consistency or reproducibility risk.
- P2 — Integrity, traceability, or maintainability risk.

Explain why each finding receives its priority.

## F. Recommended Next Actions

For every recommendation, specify:

1. The evidence supporting it.
2. The exact problem it addresses.
3. Whether it requires code changes.
4. Whether it requires retraining.
5. What acceptance evidence would demonstrate success.

Separate mandatory actions from optional improvements.

---

# 10. Acceptance Criteria

Phase 2 is complete only when:

- The provenance of the current model has been established, or the missing evidence is explicitly identified.
- Numerical feature comparisons use the same underlying candle data and final timestamp.
- The active 37-feature vector has been examined, not merely a small selection of indicators.
- ATR and MACD dependency/fallback behavior has been verified.
- Prediction impact has been measured using the existing model and scaler, where technically possible.
- The two target definitions have been quantitatively reconciled.
- All conclusions are classified as CONFIRMED, LIKELY, or UNRESOLVED.
- No production source code, model artifacts, or trading behavior has been changed.

**Do not proceed to implementation or retraining as part of this task.**

The final report must give us enough evidence to decide what should change, if anything, in a separate engineering discussion.

## 我特别强调三个审计重点

1\. 不要只比较 ATR、RSI、MACD。

必须比较完整的 37 维 feature vector。否则即使三个指标一致，也不能证明模型实际收到的输入一致。

2\. 不要停在 feature difference。

这是我认为 Phase 2 最重要的一步：把差异继续传递到 `P_UP`，观察它是否改变方向、概率或现有决策门槛。

否则我们只知道特征不一样，却不知道实际影响有多大。

3\. 不要把 Nov 5 模型过期直接等同于已经重新训练。

7 天是配置规则，不是执行证据。必须查日志和 artifact 时间线，确认 Nov 13 的 `ensure_model()` 到底有没有触发、有没有成功。

我的建议是：先让 Claude 完成这份 Phase 2 审计，拿到数值证据后再讨论是否修改 FeatureEngine、统一训练目标或重建 Model Bundle。现在不应该先动代码。
