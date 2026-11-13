这份 Phase 2 报告有一个很重要的进展：它没有用无法取得的数据制造“数值一致性结论”，而是明确划出了证据边界。 这比给出一张看似完整、实际没有实验依据的 parity 表更有价值。

但我认为报告还揭示了一个比最初 200/500/1500 lookback 更值得优先追查的问题：

当前模型的训练身份不明，而且配置中出现了 5,000 bars。

这意味着我们现在甚至不能确定应该拿哪一套训练条件作为比较基准。

## 1. 我的审计判断

CONFIRMED

&#x20;已经可以确定的事实：

- 当前本地模型、Scaler、Manifest、Config 文件时间集中在 Nov 5。
- 模型和 Manifest 都是 37 维。
- 保存的 config 写着 `train_lookback_bars: 5000`。
- 当前检查的 explicit retraining 路径是 500 bars、M15。
- 当前检查的 auto-training 路径，在该配置 wiring 下默认是 5,000 bars。
- 两条训练路径的 label 定义不同。
- ATR 有两个不同算法分支。
- Artifact 没有共同的 run ID/hash 绑定。

LIKELY

&#x20;最合理但尚未证实的解释：

Nov 5 模型可能来自 auto-training，或者另一条使用 5,000 bars 的训练路径。

但不能把它写成已确认事实。保存的 config 可能反映的是配置意图，而不是实际抓取的数据量。

UNRESOLVED

&#x20;最关键的未知：

- Nov 5 模型究竟由哪条训练路径产生？
- 实际 label 是 `>0` 还是 `>0.0005`？
- 训练 timeframe 是什么？
- 实际使用的 dependency branch 是什么？
- Nov 5 之后有没有发生自动重训练？
- 当前生产部署的模型是否就是这套本地 artifact？

这些问题没有解决前，数值 parity 实验即使以后完成，也可能是在比较错误的训练基准。

## 2. 我认为下一步不应该直接重复 Phase 2

Claude 的 Phase 2 把几个不同的问题放在了一起。建议拆成两个有明确先后顺序的工作。

### 第一优先级：Model Provenance Recovery

先回答 Nov 5 模型到底是谁训练出来的。

我会把调查重点放在以下位置：

| 优先级 | 调查内容                | 要获得的证据                               |
| ------ | ----------------------- | ------------------------------------------ |
| P0     | Nov 5 artifact 生成过程 | 训练入口、启动命令、训练日志               |
| P0     | Config 的 5000 bars     | 实际请求数量、实际返回数量、清洗后样本数量 |
| P0     | Target 定义             | 训练时实际执行的 label 代码                |
| P0     | Timeframe               | 实际 OANDA granularity                     |
| P0     | Nov 5–13 部署记录      | Model load、stale check、retraining、save  |
| P1     | Runtime dependencies    | pandas-ta、sklearn、XGBoost 实际版本       |
| P1     | 部署 artifact 身份      | 本地与生产模型的 hash                      |

特别注意一个细节：

`train_lookback_bars=5000` 不等于实际训练一定用了 5000 根 K 线。

必须区分：

- Requested bars
- Returned bars
- Closed bars
- Valid feature rows
- Final training samples

这几个数量可能不同。

另外，Nov 5 的 Git checkpoint 时间晚于 artifact 时间，只能证明 checkpoint 晚于文件时间，不能证明 artifact 是由该 checkpoint 对应的代码产生的。

### 第二优先级：Numerical Parity Experiment

这里我想对 Phase 2 原来的实验设计做一个细化。

不是 37 个 feature 都同样容易受到 lookback 影响。

根据 Phase 1 的特征定义，可以先分成两组：

| 特征类别                 | 主要特征                                                               | 对历史长度的预期敏感性                    |
| ------------------------ | ---------------------------------------------------------------------- | ----------------------------------------- |
| 固定窗口特征             | Returns、Volatility、High/Low Distance、Candle Geometry、Time Features | 如果最后一段共同 K 线完全相同，通常应一致 |
| 历史递推或初始化敏感特征 | ATR、RSI、MACD，以及其派生指标                                         | 可能受到输入历史长度和初始化方式影响      |
| 需要确认实现细节         | ADX、Volume Trend、Volume Ratio                                        | 取决于实际计算公式及窗口实现              |

例如，`dist_high_96` 如果只使用最近 96 根 K 线，那么输入 200 根还是 5,000 根，在最后 96 根完全相同的前提下，最终值理论上应一致。

但 RSI、MACD 等递推指标，可能因为更早的历史数据影响初始化而产生差异。

所以真正值得关注的是：

1. 哪些 feature 理论上必须相等？
2. 哪些 feature 允许出现初始化差异？
3. 实际差异有多大？
4. 这些差异是否影响模型的 `P_UP`？

这会让实验更有诊断价值，而不只是机械地比较 37 个数字。

## 3. 目前我对 v685 模型的判断

当前模型的证据状态

模型文件结构完整性

部分确认

37 维 Model / Manifest 已确认，Scaler 实际维度和同源性未确认。

训练来源

未确认

5,000 bars 指向 auto-training，但缺少训练事件证据。

Feature numerical parity

未验证

缺少匹配历史 K 线，无法做数值比较。

Prediction impact

未验证

尚不知道输入差异是否改变概率或交易决策。

生产决策可信度

证据不足

这不代表模型已经被证明无效，而是目前无法证明它的训练与推理条件一致。

## 4. 建议下一项任务

我建议先不要启动 Phase 3 的代码修复，而是做一个范围更小的：

Phase 2.1 — Model Provenance Forensics

只调查 Nov 5 模型的生成过程，不做数值实验，不修改代码。

任务的最终目标是回答：

> Can we identify the exact training pipeline and effective training configuration that produced the November 5 model artifacts?

如果无法回答，也要精确列出缺失的证据，以及哪些证据还有可能从 Git、shell history、cron、日志、部署目录和 artifact metadata 中恢复。

这是当前最值得花时间的一步。因为一旦训练身份明确，我们才知道下一轮 parity 实验究竟应该以 500、1,500 还是 5,000 bars 作为训练基准。

我的原则：先确认我们正在审计哪一个模型，再判断这个模型是否一致，最后才讨论是否值得修改或重新训练。
