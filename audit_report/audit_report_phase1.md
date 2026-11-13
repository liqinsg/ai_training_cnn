我建议不要让 Claude 直接去读 `retrain_model.py`，然后给一个笼统的「代码看起来没问题」的结论。

这次审计应该围绕一个明确目标：

确认 v685 的模型训练阶段与实盘推理阶段，是否使用了完全一致的特征计算逻辑。

尤其是 ATR、MACD，因为我们已经知道当前推理运行出现过：

```
ta.atr failed
MACD failed
```

但目前还不知道训练阶段是否也出现过相同的 fallback。

我建议分成四个阶段，先查证，再验证，最后才决定是否修改。

## 一、审计分成四个阶段

1. 阶段 A：训练链路追踪

   找出 `retrain_model.py` 从数据读取到最终模型保存的完整流程。

   重点：训练到底使用了哪些特征？
2. 阶段 B：推理链路追踪

   找出 `fx_trade_bot_v685.py` 如何加载模型、构造实时特征、排列特征列并进行预测。

   重点：推理是否使用同一套计算逻辑？
3. 阶段 C：数值一致性验证

   用同一份历史行情数据，分别走训练和推理的特征计算路径。

   重点：相同输入是否得到相同输出？
4. 阶段 D：影响评估

   判断当前 fallback 是否影响模型输入、预测结果和模型有效性。

   重点：是否值得修改，以及应该修改哪里？

这里有一个重要区别：

代码一致性不等于数值一致性。

即使两个地方调用了同一个函数，也可能因为输入数据窗口、时间周期、NaN 处理和预热数据不同而产生不同结果。

因此，阶段 C 不能省略。

## 二、具体要审计什么？

我会重点检查以下五个方面。

| 审计项目 | 需要回答的问题                               |
| -------- | -------------------------------------------- |
| 特征定义 | Training 和 Inference 使用相同公式吗？       |
| 参数     | ATR period、MACD fast/slow/signal 是否一致？ |
| 数据     | K线周期、数量、顺序、未完成 K 线是否一致？   |
| 异常处理 | NaN、缺失值、fallback 是否一致？             |
| 模型输入 | 特征名称、顺序、dtype、标准化是否一致？      |

另外有两个容易被忽略的地方：

- Look-ahead bias：训练特征是否意外使用了预测时点之后的数据？
- Scaler 一致性：训练时的 scaler 是否被正确保存，并在推理时使用同一个 scaler？

这些比单纯确认 `pandas_ta` 是否安装更重要。

## 三、第一轮：让 Claude 做只读审计

我建议第一轮不要运行完整的 `retrain_model.py`。

因为它可能会：

- 覆盖模型文件。
- 修改训练数据或指标文件。
- 更新 scaler。
- 产生新的模型版本。
- 改变后续生产推理所加载的模型。

先做静态代码追踪。

下面这份任务可以直接交给 Claude。

# 【Strict Spec】v685 Training / Inference Feature Consistency Audit — Phase 1

## 1. Objective

Audit the complete model training and inference feature pipelines.

Primary target:

- `retrain_model.py`
- `fx_trade_bot_v685.py`
- All shared feature-engineering modules.
- Model/scaler loading and saving code.

Primary question:

Does the production inference pipeline generate exactly the same feature definitions and numerical representations as the training pipeline?

Special attention:

- ATR
- MACD
- All fallback implementations.

## 2. Strict Restrictions

READ-ONLY AUDIT ONLY.

Forbidden:

- Modify any source code.
- Install or uninstall packages.
- Execute model retraining.
- Overwrite models, scalers, datasets or production artifacts.
- Submit orders to OANDA.
- Change account configuration.
- Change `run.env`.
- Change `docs/Development_plan.md`.

Do not assume that running a Python script is harmless. Inspect its side effects before executing anything.

## 3. Phase A — Training Pipeline

Trace `retrain_model.py` from entry point to model artifact creation.

Identify:

1. Historical data source.
2. Data loading and cleaning.
3. Candle timeframe and lookback.
4. Feature-engineering functions.
5. ATR implementation and parameters.
6. MACD implementation and parameters.
7. Fallback behavior when indicators fail.
8. NaN and warm-up handling.
9. Feature selection and column ordering.
10. Scaling/normalization.
11. Train/validation split.
12. Target generation and prediction horizon.
13. Model training and artifact persistence.

For every important finding, provide:

- File path.
- Function name.
- Exact line numbers.
- Actual implementation evidence.

## 4. Phase B — Inference Pipeline

Trace `fx_trade_bot_v685.py` from market-data acquisition to model prediction.

Identify the corresponding items from Phase A.

Pay particular attention to:

- Whether training and inference share the same functions.
- Whether inference uses fallback when `pandas_ta` is unavailable.
- Whether feature columns are reordered.
- Whether missing features are filled with zero or another neutral value.
- Whether the original training scaler is loaded.
- Whether the inference input dtype and column names match training.

## 5. Phase C — Consistency Matrix

Produce a comparison table:

| Feature        | Training | Inference | Parameters | Numerical consistency | Status |
| -------------- | -------- | --------- | ---------- | --------------------- | ------ |
| ATR            |          |           |            |                       |        |
| MACD           |          |           |            |                       |        |
| RSI            |          |           |            |                       |        |
| Other features |          |           |            |                       |        |

Use these classifications:

- CONFIRMED MATCH
- CONFIRMED MISMATCH
- PARTIAL MATCH
- UNKNOWN

Do not classify based on function names alone.

## 6. Phase D — Model Artifact Integrity

Determine:

1. Which model file is actually loaded by v685?
2. Which feature list was used when training that model?
3. Is the scaler saved separately or embedded?
4. Is feature order explicitly validated at inference?
5. Can an old model silently receive a new feature definition?
6. Are model and scaler versions linked reliably?

Distinguish current production behavior from historical training behavior.

## 7. Deliverables

Produce:

A. Executive findings.

B. Complete training pipeline trace.

C. Complete inference pipeline trace.

D. Training/inference consistency matrix.

E. Confirmed facts vs hypotheses vs unresolved questions.

F. List of potential production-impacting mismatches, ranked P0/P1/P2.

G. Recommended next investigation steps.

Every conclusion must have source-code evidence.

## 8. Acceptance Criteria

Phase 1 is complete only when:

- Training and inference feature paths are identified.
- ATR and MACD implementations are traced independently.
- Fallback behavior is understood on both sides.
- Model/scaler artifact relationships are established.
- Unknowns are explicitly documented.

Do not propose a code fix until the evidence is sufficient.

Do not equate absence of an error with correctness.

## 四、第二轮才做数值验证

第一轮完成后，不要立即修改代码。

如果发现训练和推理使用不同实现，再安排第二轮：

使用同一份历史 OHLC 数据，分别执行两条特征计算路径。

建议比较：

| 指标     | 比较内容                     |
| -------- | ---------------------------- |
| ATR      | 每根 K 线的数值差异          |
| MACD     | MACD、Signal、Histogram 三列 |
| RSI      | 完整序列差异                 |
| 全部特征 | 列名、顺序、dtype、NaN       |
| 模型输入 | 最终输入矩阵是否一致         |

数值比较建议记录：

- Maximum Absolute Difference
- Mean Absolute Difference
- Mismatch Count
- Mismatch Percentage
- First Mismatch Timestamp

如果两条路径最终使用相同函数，就进一步检查输入数据和参数是否一致，而不是直接判定通过。

## 五、我希望最终得到什么结论？

不是简单的「ATR 有问题」或「MACD 有问题」。

而是下面四种情况之一：

情况 A

一致

训练和推理都使用 fallback，数值也一致。

结论：暂时不需要改变指标。

情况 B

不一致

训练使用正常指标，推理使用 fallback。

结论：需要调查模型输入分布偏移。

情况 C

部分一致

公式相同，但数据窗口、参数或预处理不同。

结论：需要定位具体差异。

情况 D

证据不足

无法确认历史模型训练时使用的特征实现。

结论：需要追溯训练日志、模型元数据和历史代码版本。

## 六、我的建议：不要急于修复

我想特别强调一个原则：

我们首先要确定当前模型实际上学到了什么，而不是先把指标计算改得更漂亮。

例如，假设模型过去一直使用简单平均 ATR，那么突然切换 Wilder ATR，即使 Wilder ATR 更符合标准定义，也不代表现有模型可以直接使用它。

正确顺序应该是：

1. 确认历史训练特征。
2. 确认当前推理特征。
3. 量化差异。
4. 判断差异对模型的影响。
5. 决定是否统一特征计算。
6. 如有必要，重新训练并在 DEMO 验证。

现在先完成 Phase 1。

把 Claude 的审计报告拿回来，我们一起评审。尤其要看它能不能拿出实际代码证据，而不是根据函数名称推测。

这次审计不应该只是消除两个 warning，而应该建立 v685 的 Training–Inference Consistency 基线。
