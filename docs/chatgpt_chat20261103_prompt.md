
我赞成。我们应该拒绝局部最优，但也不能为了追求 complete system 而一次性修改太多，最后无法判断问题来自哪里。

我的建议是：

先制定一份完整的 Master Development Blueprint，再按 Phase 1、Phase 2、Phase 3 逐步实施。

这不是把系统拆成互不相关的小修补，而是先设计好完整目标、数据契约和验收标准，再分阶段交付。

我建议把这项工作定位为：

# MC + Fibonacci Shadow Intelligence System

Development Blueprint v1.0 · Proposed Architecture

## 一、最终目标架构

我们要建立的不是一个简单的 Fib Calculator，而是一个独立的统计观察系统。

Phase 0 — Architecture & Data Contract

统一数据结构、接口、规则和验收标准

Phase 1 — Monte Carlo Data Integrity

数据生成、Pair 去重、概率、区间、时间戳、输出完整性

Phase 2 — Fibonacci Segmentation Integrity

Fib 数学、边界、异常状态、数据来源、原子写入

Phase 3 — Shadow Observation Engine

观察记录、未来价格追踪、D1/W1 独立统计

Phase 4 — Statistical Validation

样本量、置信区间、校准、基准比较、稳健性测试

Phase 5 — Decision Support Evaluation

评估是否值得提供交易决策上下文，仍不自动下单

这里有一个重要原则：Phase 5 不代表一定要接入交易系统。统计结果没有证明价值，就停留在 Shadow 层。

## 二、每个 Phase 应该完成什么？

### Phase 0 — Architecture & Data Contract

先设计，不改代码

这是整个工程最重要的基础。

先统一以下概念：

| 数据对象           | 责任                        |
| ------------------ | --------------------------- |
| MC Batch           | 一次完整的 Monte Carlo 运算 |
| MC Pair Result     | 一个货币对的模拟结果        |
| Fib Annotation     | MC Range 上的价格位置分段   |
| Shadow Observation | 某个时间点的观察快照        |
| Outcome Record     | 未来实际市场结果            |
| Validation Report  | 统计验证结果                |

必须定义：

- 唯一 Pair Identity。
- D1/W1 Timeframe Identity。
- Source Timestamp。
- Generation Timestamp。
- Schema Version。
- Confidence Level。
- Observation ID。
- 数据有效性状态。
- 数据版本和来源追踪。

核心要求：下游任何统计结果，都必须能追溯到原始 MC Batch。

### Phase 1 — Monte Carlo Data Integrity

目标：确保 Monte Carlo 产生的数据真实、完整、可重复审计。

主要工作：

1. Currency Pair 去重。
2. requested / unique / successful / failed 计数。
3. 单个 Pair 失败时的隔离机制。
4. 严格检查 NaN、Infinity、无效价格。
5. `range_90` 与实际 confidence 配置一致。
6. 保存生成时间、参数、数据来源。
7. 保持原有 Student-t Monte Carlo 算法。
8. Atomic JSON output。
9. 检查所有结果的 schema consistency。

不在这一阶段优化模拟算法。

我们先确保当前算法产生的数据可以被信任。

### Phase 2 — Fibonacci Segmentation Integrity

目标：Fib 成为可靠的独立数据注释层。

主要工作：

1. 明确 Fibonacci Ratio 和 Zone 定义。
2. 统一 Half-open Boundary Convention。
3. 增加 BELOW_RANGE、WITHIN_RANGE、ABOVE_RANGE。
4. 增加 INVALID_RANGE、MISSING_DATA。
5. 移除 BUY_LIMIT、SELL_LIMIT 等交易指令式标签。
6. 保留原始 MC 数据，不修改 MC Probability。
7. D1/W1 分别处理，不交叉融合。
8. Atomic Fib JSON output。
9. Fib 输出与 MC Source 建立明确 lineage。

这里不需要重新设计 Fibonacci 数学。重点是让它在各种输入情况下都表现明确。

### Phase 3 — Shadow Observation Engine

目标：让系统开始积累真实市场观察数据。

每个观察记录都应该有唯一 ID。

例如：

```
{
  "observation_id": "EURUSD_D_20261103_0418",
  "pair": "EURUSD",
  "timeframe": "D",
  "source_mc_file": "mc_D_all_pairs_20261103_0418.json",
  "current_price": 1.11932,
  "mc_probability": {
    "p_up": 42.1,
    "p_down": 57.9
  },
  "fib": {
    "zone": "F5",
    "range_status": "WITHIN_RANGE"
  },
  "outcomes": {
    "1_period": null,
    "3_period": null,
    "5_period": null
  }
}
```

这只是结构示意，实际字段和价格精度要在 Phase 0 定义。

重点是：

- 观察时不读取未来数据。
- 未来数据只在对应 horizon 到期后填入。
- 已完成的历史观察不可静默覆盖。
- D1 和 W1 使用各自的 outcome horizon。
- 对缺失 K 线、市场休市和重复观察有明确处理规则。

### Phase 4 — Statistical Validation

这是系统真正开始产生研究价值的阶段。

我建议至少验证：

| 研究维度                | 方法                                 |
| ----------------------- | ------------------------------------ |
| MC Range Reliability    | 实际价格覆盖率                       |
| Probability Calibration | Brier Score、Calibration Curve       |
| Fib Zone Behaviour      | Zone Conditional Return Distribution |
| Time Horizon            | 1、3、5 Period                       |
| Regime Dependency       | 不同波动率环境分组                   |
| Robustness              | 不同时间段和货币对                   |
| Baseline Comparison     | 不使用 Fib 的对照组                  |

特别强调：

不能只看某个 Zone 的平均收益。

还要看：

- 样本量。
- 分布形状。
- 置信区间。
- 极端行情。
- 交易成本影响（若以后评估交易价值）。
- Out-of-sample 表现。

### Phase 5 — Decision Support Evaluation

只有 Phase 4 通过统计验证，才考虑这一阶段。

Fib 最合理的潜在用途是：

Entry Location Context，而不是 Direction Generator。

D1 仍然是 Primary Decision。

W1 仍然是 Market Context。

H1 如果未来加入，仍然只承担 Entry Gate。

不允许 Fib：

- 自己产生 BUY/SELL。
- 改写 MC Probability。
- 改写 Monte Carlo 参数。
- 自动否决 D1。
- 直接触发 OANDA 下单。

## 三、全工程必须遵守的原则

我建议把这些原则写进 Master Blueprint，作为所有后续开发 Prompt 的共同约束。

| 原则                      | 具体要求                           |
| ------------------------- | ---------------------------------- |
| Baseline Preservation     | 不随意改变现有 MC 模拟算法         |
| Data Lineage              | 所有结果必须可追溯原始数据         |
| Reproducibility           | 相同输入和配置可以重现结果         |
| No Silent Failure         | 不允许失败后悄悄输出看似正常的数据 |
| Time Integrity            | 不允许 Look-ahead Bias             |
| D1/W1 Separation          | 两个周期独立观察                   |
| Shadow First              | 先观察，再验证，最后才评估用途     |
| No Premature Optimization | 不因少量结果改变参数               |
| Statistical Honesty       | 不把 MC 概率当成交易胜率           |
| Auditability              | 每次运行都能解释、追踪和复核       |

## 四、如何推进开发？

我建议不要现在就让 IDE 一次性完成全部六个 Phase。

我们应该采用以下交付模式：

1. Master Blueprint

   先生成完整设计规范、模块边界、数据契约、状态定义、验收矩阵。
2. Phase Implementation Prompt

   每次只授权一个 Phase，明确允许修改哪些文件、禁止修改哪些文件。
3. Implementation Audit

   IDE 完成后，独立审计代码变更和测试结果。
4. Demo / Shadow Validation

   使用真实市场数据验证，而不是只依赖模拟测试。
5. Phase Gate

   通过验收才进入下一阶段。未通过则修复，不跳过问题。

## 五、我建议增加一个很重要的设计：Baseline vs Candidate

每次修改都保留两条数据路径：

- Baseline：当前已经存在的 MC 结果和算法。
- Candidate：经过数据完整性及 Fib 改进后的版本。

这样未来我们可以比较：

- 数据有没有丢失？
- Probability 有没有意外变化？
- Fib Zone 有没有变化？
- 统计结果有没有变化？
- 改进是否真的带来价值？

如果 Candidate 只让代码更复杂，却没有带来更好的数据质量或统计证据，就没有理由采用。

## 六、接下来第一份正式文件

我建议先制作：

MC_FIB_SHADOW_SYSTEM_BLUEPRINT.md

建议作为总规范

版本：v1.0

内容：

1. System Objectives
2. Architecture & Module Boundaries
3. Data Contracts & JSON Schemas
4. MC Data Integrity Requirements
5. Fib Segmentation Specification
6. Shadow Observation Data Model
7. Outcome Resolution Rules
8. Statistical Validation Framework
9. Baseline / Candidate Comparison
10. Phase Implementation Plan
11. Testing & Acceptance Criteria
12. Rollback & Operational Safety

我的建议：先完成 Blueprint，不急着写 Phase 1 的修改 Prompt。

因为我们现在已经知道 MC、Fib 和 API Builder 之间存在潜在接口问题。先把数据契约和模块边界确定下来，Phase 1、2 才不会各自修好，却在接口处产生新的问题。

下一步我可以直接帮你制定这份完整的 Master Blueprint v1.0，作为 IDE 后续所有开发工作的唯一设计基准。
