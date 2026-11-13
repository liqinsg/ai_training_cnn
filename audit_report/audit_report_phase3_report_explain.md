这份 Phase 3 报告的价值很高。我认为它已经完成了一个重要转变：从怀疑 ML 的基础架构有问题，转向识别真正影响交易决策的缺陷。

而且，它基本推翻了之前 Phase 3 中几个过于激进的重构方向。

我的总体判断是：

REPAIR 优于 REPLACE

暂不进入全面实施

但我不建议原样批准第 8 节的实施顺序。报告本身还有几个需要进一步明确的架构问题。

# 一、真正重要的发现：问题的严重程度重新排序了

我把这些发现分成三个层次。

## P0：直接影响交易方向和决策正确性

N1 — XGB 投票被伪造

Critical

这是我认为整个报告最重要的发现。

`generate_signal() == None` 并不意味着模型不存在，也不意味着模型没有预测能力。

它可能意味着：

- 数据不足
- 其他策略过滤器未通过
- SL/TP 构建失败
- 分数不足
- 预测异常

但决策层把这些全部转换成模型缺席，然后重新计算：

\\[ X=S\times0.3+R\times0.3 \\]

这不是中性投票，而是人为制造了一张 XGB 投票。

N9 — Strength Gap 方向性错误

Critical

这个发现尤其严重。

EUR_USD 被错误解析为：

- Base: EUR
- Quote: \_US

Quote 取不到真实强度，回退到 50。

结果：

| 方向  | Strength Gap |
| ----- | ------------ |
| LONG  | -5           |
| SHORT | +10          |

每一笔交易都天然存在 15 分的 SHORT 优势。

这不是参数调优问题，而是评分函数的输入语义错误。

N10 + N11 — MC 单位与评分尺度错误

High

N10 把百分数当作小数，导致 MC 分数几乎总是饱和。

N11 又把这个已经失真的 Engine Score 与 Profile 的 MIN_CONVICTION 直接比较。

两者叠加，意味着当前评分系统可能并没有按照设计的权重工作。

我的结论：

在修复 N1、N9、N10、N11 之前，当前三票共识机制的统计表现不能被当作有效的策略证据。

尤其不能根据现有 BUY/SELL 数量来推断模型方向偏好。

## P1：模型本身是否真的具备可用预测能力

这里最重要的是 F2。

当前使用了 `TimeSeriesSplit`，但这并不自动意味着时间序列验证正确。

假设数据组织如下：

```
EURUSD: Oct 01 ... Nov 13
GBPUSD: Oct 01 ... Nov 13
USDJPY: Oct 01 ... Nov 13
AUDUSD: Oct 01 ... Nov 13
```

直接 concat 后再进行 TimeSeriesSplit：

```
训练集：EURUSD 的全部 + GBPUSD 的部分
验证集：GBPUSD 的剩余 + 后续货币对
```

这会造成两个问题：

1. 验证集中的某个时间段，其他货币对相同时间的数据可能已经进入训练集。
2. 模型可能学习到跨货币对的同期市场信息，而不是未来预测能力。

另外，Scaler 在 CV 之前拟合，也构成数据泄漏。

因此：

F2 必须解决

但我还要补充一个设计问题：

Walk-forward 究竟应该按时间统一切分，还是按货币对分别切分？

我倾向于：

- 所有货币对先统一时间轴。
- 相同时间戳的样本必须进入同一个训练或验证区间。
- 按时间进行 walk-forward。
- 6-bar label horizon 设置至少 6 根 bar 的 purge/embargo。
- Scaler 必须在每个训练 fold 内单独拟合。

这样才能避免不同货币对在同一时期的信息泄漏。

F3 也值得保留，但不要立即归一化或删除特征。首先用特征重要性、SHAP（如果已有相应基础设施）以及分组验证确认它是否真的形成了货币对识别捷径。

## P2：工程与部署可靠性

这里我认为 N3、F4、F7、N12 应该作为一个整体处理。

当前结构的问题是：

```
Profile 1 ─┐
Profile 2 ─┼── Shared Model
Profile 3 ─┤
Profile 4 ─┘
```

任何一个 Profile 都可能触发重新训练并覆盖所有 Profile 使用的模型。

而且：

- 没有训练数据快照。
- 没有模型版本和来源记录。
- 没有环境依赖记录。
- 多文件非原子写入。
- 多个进程可能同时训练和写入。
- 不同主机可能生成不同特征。

这意味着即使模型在某次运行中表现良好，也未必能复现。

我支持将训练和交易运行彻底分离。

但这里还有一个关键设计选择：

四个 Profile 究竟应该共享一个模型，还是拥有独立模型？

不能仅仅因为当前四个 Profile 使用同一份模型，就默认应该继续共享。

应该先确定训练目标、交易货币对集合、特征分布和预测任务是否一致。

# 二、我认为报告还漏掉了三个重要问题

这三个问题值得加入 Phase 3 的最终设计。

### 1. ML Prediction 和 Strategy Eligibility 必须彻底分离

N1 暴露的不只是一个异常处理 Bug，而是两个职责混在一起。

应该设计成：

Market Data / Feature Validation

数据有效性、完整性、特征契约

ML Advisor

P(UP), P(DOWN), confidence, abstain

Strategy Engine

Entry eligibility, risk, score

Decision / Consensus

明确区分预测结果与交易许可

例如：

| ML 状态 | Strategy 状态 | 结果             |
| ------- | ------------- | ---------------- |
| BUY     | Eligible      | 可以参与决策     |
| BUY     | Ineligible    | 不交易           |
| SELL    | Eligible      | 可以参与决策     |
| ABSTAIN | Eligible      | 不得伪造 ML 投票 |
| ABSTAIN | Ineligible    | 不交易           |

ML 不应该因为 SL/TP 构建失败而失去独立预测记录。

反过来，ML 预测成功也不代表允许交易。

### 2. Shadow Mode 不应该只是一个日志开关

报告的 S1、T6 方向是对的。

但是我认为 Shadow Mode 应该同时记录：

- 旧决策路径的投票和分数。
- 新决策路径的投票和分数。
- 两者之间的差异。
- 哪些交易因为新旧逻辑而改变方向。
- 哪些交易因为新逻辑而从交易变成拒绝。
- 哪些交易因为新逻辑而从拒绝变成允许。

否则，Shadow Mode 只能证明程序运行了，不能证明新旧逻辑的差异。

尤其要保证：

`Shadow computation ≠ Execution authorization`

### 3. 需要区分模型质量与交易系统质量

这是一个非常重要的评估架构问题。

当前报告有 Accuracy、CV、模型预测等内容，但我们还需要独立评估：

| 评估层           | 要回答的问题               |
| ---------------- | -------------------------- |
| Data Quality     | 输入数据是否正确？         |
| Feature Quality  | 特征是否一致、可复现？     |
| Model Quality    | 模型是否真正具有预测能力？ |
| Calibration      | 预测概率是否可信？         |
| Decision Quality | 投票和评分是否正确？       |
| Trading Quality  | 最终交易是否产生实际价值？ |

例如，一个模型可能有不错的 AUC，但在交易成本、点差和六根 K 线的预测期限下，没有任何实际交易优势。

反过来，交易系统亏损也不意味着 ML 模型本身没有预测能力。

这两个结论必须分开。

# 三、对原实施顺序的修改建议

我不建议直接照搬 S0-S5。

我的建议是重新组织为下面六个阶段。

1. P0 — Runtime Risk Containment

   先处理 N3 的并发训练覆盖风险，以及 D1 的 TP 自动修改风险。

   确认当前是否正在发生。必要时通过独立开关禁止 live retraining，但不擅自改变其他交易逻辑。
2. P1 — Decision Logic Repair

   N1、N2、N9、N10、N11。

   先建立明确的预测状态、投票契约和评分单位。不能直接把旧逻辑替换成新逻辑。
3. P2 — Feature & Runtime Consistency

   F4、F5、F6、N5、N6、N7、N12。

   明确特征定义、NaN 政策、后端公式、时间周期和窗口契约。
4. P3 — Model Evaluation Redesign

   F2、F3、F10、F11。

   重新建立真正的时间序列验证、purge/embargo、baseline、概率校准及最终 holdout。
5. P4 — Artifact & Training Architecture

   F7、F8、N3。

   建立不可变训练产物、manifest、原子发布、离线训练及显式 promotion。
6. P5 — Shadow Validation & Controlled Rollout

   旧逻辑与新逻辑并行计算，比较结果，完成验收后再逐项启用。

注意：这里的顺序是工程依赖顺序，不意味着每个阶段都要等待几天。能通过确定性测试验证的，就不应该靠等待市场行情来验证。

# 四、目前我不会批准的三个决定

| 决定                             | 我的意见                            |
| -------------------------------- | ----------------------------------- |
| 直接启用 `OPT_XGB_DIRECT_VOTE` | 暂缓，先定义 Advisor 的独立预测契约 |
| 立即修改 Engine Score 公式       | 暂缓，先确定评分量纲及方向对称性    |
| 立即删除或归一化 ATR/MACD        | 暂缓，先完成特征诊断和对照实验      |

还有一个细节：S0 所说的至少 20 行数据，只能作为运行冒烟测试，不能作为任何统计判断的充分样本。

# 五、下一步最值得做什么？

我建议现在不要再开一个无限延伸的 Audit Phase 3.1。

这份报告已经足以进入设计阶段。

但进入实施之前，有三个决定必须先确定：

1. Model Architecture：四个 Profile 共享模型，还是按 Profile / 交易任务拆分？
2. Prediction Contract：ML Advisor 是否完全独立于 Strategy Engine 的交易资格判断？
3. Evaluation Contract：以什么样的时间切分、预测期限、成本和评价指标认定模型有效？

这三个决定会影响后面几乎所有工程实现。

我的最终判断：

这份报告不支持重写 ML 系统。它支持保留现有 FeatureEngine 和 XGBoost 框架，修复决策逻辑、重新建立评估体系，并重构模型训练与发布生命周期。

我建议下一份正式文件直接写成：

`PHASE3_REDESIGN.md`

以这份 Audit 为证据基础，形成最终架构、明确的技术决策、依赖关系、实施任务和验收标准。

不要再让 AI 对整个仓库重新做一遍审计。现在最有价值的是把已经找到的问题变成可验证、可实施的工程设计。
