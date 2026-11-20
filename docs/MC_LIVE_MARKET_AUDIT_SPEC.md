# 【Permanent Spec】MC Live Market Audit & Strategy Utilization

**Version:** 1.0  
**Date:** 2026-11-20  
**Status:** PROPOSED — Pending Owner Approval  
**Priority:** P0  
**Document Type:** Permanent Research & Audit Specification  
**Scope:** MC Historical Data / Live Trading Reconstruction / Market Regime / Capital Allocation / Demo Validation

---

## 0. Document Authority

### 0.1 Purpose

本文件定义 MC（Monte Carlo）概率数据与实际交易行为之间的系统性审计任务。

核心目的不是单纯验证 MC 能否预测价格，而是回答：

**机器人是否有效利用了 MC 提供的概率信息，识别值得参与的市场行情，并把有限的交易资金分配给具有统计优势的机会？**

本审计将研究：

1. 市场状态在时间轴上如何演变。
2. MC 是否识别了方向明确与方向不明确的市场。
3. MC 概率是否具有可测量的统计价值。
4. 策略是否读取并有效使用了 MC 信息。
5. 为什么策略在方向优势不明确时仍然选择某些交易。
6. 是否存在更清晰的交易机会，却被其他交易占用了资金或仓位。
7. 如何将审计发现转化为可验证、可独立运行的策略改进。

### 0.2 Authority Boundary

本文件是研究与审计规范，不是交易策略授权书。

本文件不授权：

- 修改现有生产策略。
- 修改现有 MC 算法。
- 修改下单逻辑。
- 修改仓位管理或风险参数。
- 修改 SL / TP 行为。
- 直接启用新的交易过滤器。
- 在实盘环境提交新订单。

任何行为变化必须经过独立的技术审议和 Owner 明确批准。

### 0.3 Core Principles

- 没有圣杯，只能研究概率优势。
- 只参与自己能够识别和评估的行情。
- 不要求机器人参与每一次市场波动。
- 资金和风险预算是有限资源，必须考虑机会成本。
- 统计关联不等于因果关系。
- 计算结果不等于执行确认。
- 记录不等于策略已经使用。
- 没有数据必须明确标记为缺失，不允许推测补齐。
- 不允许为了证明策略正确而选择性使用数据。

---

# 1. Research Questions

本项目必须围绕以下四个研究问题展开。

## RQ-01：MC 是否能够识别市场方向优势？

研究 MC 概率是否能够区分：

- 方向优势明显的市场。
- 方向优势较弱的市场。
- 方向不明确的市场。
- 概率方向持续变化的市场。
- 市场方向与波动状态发生转换的市场。

不能仅仅检查 P(up) 是否大于 50%。

需要研究：

- 概率优势幅度。
- 概率持续性。
- 概率变化速度。
- 多时间点方向一致性。
- 多货币对之间的相互印证。
- 不同市场状态下的实际后续表现。

MC 的 Strong、Neutral、Consolidation 等分类必须保留原始定义，不允许在审计脚本中擅自重新解释。

## RQ-02：策略是否有效使用 MC 信息？

需要比较：

- MC 当时实际输出了什么。
- 策略当时实际读取了什么。
- 策略当时生成了哪些候选交易。
- 哪些候选交易通过或未通过筛选。
- 哪些交易最终被执行。
- 哪些交易最终没有执行，以及是否有明确原因。

重点识别以下情况：

1. MC 已显示方向优势，但策略没有利用。
2. MC 显示方向不明确，但策略仍然交易。
3. MC 与策略交易方向存在冲突。
4. 策略只使用 MC 的部分字段，没有使用完整概率信息。
5. MC 数据存在，但策略执行链没有消费这些数据。
6. 策略因其他过滤条件而放弃 MC 所指示的机会。

不能仅凭成交记录推断策略当时看到了哪些机会。

## RQ-03：资金是否被低质量机会占用？

需要研究：

- 实际开仓时的市场方向清晰度。
- 同一时间存在的其他候选机会。
- 实际仓位与风险预算。
- 相关货币敞口。
- 交易机会的优先级。
- 可用资金与仓位容量。
- 交易执行顺序。

特别关注：

**当 JPY 方向优势已经持续出现时，策略为什么仍然开出大量非 JPY 交易？**

必须区分以下可能性：

- 当时没有生成 JPY 候选交易。
- JPY 候选交易未通过其他技术条件。
- JPY 候选交易被排名或仓位限制排除。
- 策略没有正确识别 JPY 共同方向。
- MC 信息没有进入决策链。
- 非 JPY 交易本身具有其他独立的有效优势。
- 现有日志不足以确定原因。

不得提前认定任何一种原因。

## RQ-04：MC 是否有助于识别值得参与的大行情？

最终研究重点是识别：

- 哪些市场状态更值得参与。
- 哪些市场状态应该降低参与意愿。
- 哪些方向具有持续性。
- 哪些方向只是短暂波动。
- 哪些市场状态容易出现双向止损。
- 哪些行情具有较好的持续发展特征。

本项目不以增加交易数量为目标。

研究目标是提高机会选择质量，而不是让机器人在更多行情中交易。

---

# 2. Mandatory Historical Market Timeline

## 2.1 Why Timeline Is Mandatory

本项目不能只分析某一天的 MC 快照。

2026-11-20 的 MC Daily Update 只是一个时间点，不能代表此前市场状态的开始时间。

必须尽可能向前追溯历史数据，重建市场状态演变过程。

尤其需要调查两个实际交易现象。

### Event A：Wide-Range / Choppy Market

用户观察到：

- 上周市场出现宽幅震荡。
- LONG 和 SHORT 两个方向的交易都出现 SL。
- 单笔损失较小，约 SGD 1 左右。
- 但同一市场环境对两个方向都造成了损失。

需要研究：

1. 宽幅震荡最早何时出现？
2. 当时 MC 是否已经显示方向优势不明确？
3. P(up) 是否在不同方向之间频繁变化？
4. 概率变化是否早于或晚于实际价格变化？
5. 当时的价格区间、波动幅度和持续时间如何？
6. LONG 与 SHORT 止损是否发生在同一货币对、同一市场主题或不同货币对？
7. 策略是否在缺乏持续方向优势时反复参与？
8. MC 是否提供了可用于识别该类行情的信息？

不得仅凭两笔反向交易都发生 SL，就直接定义为宽幅震荡。

必须使用实际价格和交易时间数据验证。

### Event B：Established JPY Strength

用户观察到：

- JPY 强势并不是 2026-11-20 才出现。
- 在最新 MC Daily Update 之前，JPY 强势已经存在一段时间。
- 期间策略仍然开出不少非 JPY 交易。
- 部分非 JPY 交易的方向优势并不明确。

需要研究：

1. JPY 强势最早何时能够从历史 MC 数据中观察到？
2. JPY 方向一致性如何逐步形成？
3. 有多少 JPY 货币对持续显示相同方向？
4. Strong 与 Neutral 的比例如何变化？
5. 这种一致性持续了多久？
6. 是否存在短暂反转或方向分歧？
7. 策略是否识别到这种共同方向？
8. 为什么实际交易仍然大量分布在非 JPY 货币对？

### Event C：Regime Transition

必须把 Event A 与 Event B 放到同一条时间轴上。

不能预先假定两者是完全独立的市场事件。

需要判断：

- 宽幅震荡是否逐渐收缩或结束。
- 市场是否由方向不明确转向某种更清晰的方向。
- JPY 强势是否在该过程中逐步形成。
- MC 是否能够在转换过程中提供有用信息。
- 策略是否及时改变参与行为。

如果数据不足以证明存在市场状态转换，必须明确写明。

## 2.2 Historical Coverage

优先收集服务器上所有可用历史 MC 数据。

不得人为将历史范围限制为最近一天或最近几天。

建议：

- 优先收集完整历史存档。
- 至少覆盖上周宽幅震荡事件。
- 尽可能覆盖 JPY 强势开始前及持续期间。
- 收集对应的价格 K 线和实际交易记录。
- 收集 MC 生成时间、发布时间及实际读取时间。

如果历史 MC 快照已经不存在：

- 检查日志轮转。
- 检查备份目录。
- 检查历史输出文件。
- 检查服务器其他可访问的归档。
- 检查是否存在历史数据库记录。

如果只能通过历史价格重新计算 MC：

必须单独标记为：

`RETROSPECTIVE_RECALCULATION`

不得把重新计算的历史 MC 冒充当时真实生成的 MC 数据。

---

# 3. Phase 1 — TRAE Runtime Fact Finding

**Priority:** P0  
**Mode:** READ ONLY  
**Execution:** Server-side inspection

TRAE IDE 可以访问服务器代码、运行日志和实际数据文件。

第一阶段由 TRAE 完成现场事实调查。

ChatGPT 不假设能够直接访问服务器。

## 3.1 Runtime Inventory

调查以下内容：

| Category | Required Investigation |
|---|---|
| MC Generation | MC 实际生成入口、运行频率、生成时间 |
| MC Output | 输出文件、数据库、日志、历史存档 |
| MC Timeframes | 实际存在的 D1、W1 或其他周期 |
| MC Fields | P(up)、P(down)、regime、价格、时间等 |
| Strategy Consumer | 哪些模块读取 MC |
| Decision Chain | MC 如何进入候选、过滤、Advisor 和执行链 |
| Trade Records | 实际开仓、平仓、SL、TP、费用 |
| Candidate Records | 所有候选机会及筛选结果 |
| Portfolio State | 当时的实际持仓、敞口及容量 |
| Demo Runtime | 当前 Demo 的运行版本和数据记录方式 |

必须确认：

- 当前实际运行的 runner。
- 当前实际运行的策略文件。
- 当前实际使用的配置。
- 当前实际使用的 MC 文件。
- 文件时间戳与服务器时区。
- 生产运行版本与 Git commit。

不能只根据代码中存在某个功能，就认定生产运行时确实使用了该功能。

## 3.2 Historical MC Data Inventory

必须查明：

1. 历史 MC 文件数量。
2. 最早可追溯日期。
3. 最晚可追溯日期。
4. 每个文件的生成时间。
5. 每个文件包含的货币对。
6. 是否存在重复记录。
7. 是否存在缺失日期。
8. 是否存在同一货币对不同价格或不同时间的记录。
9. 是否存在不同周期的 MC 数据。
10. 是否存在历史输出被覆盖的情况。

特别注意：

同一天可能有多次 MC 更新。

不得将不同生成时间的记录简单合并成一条每日记录。

## 3.3 Trade Reconstruction

必须重建真实交易时间线。

至少调查：

- Trade ID。
- Instrument。
- Direction。
- Open Time。
- Close Time。
- Entry Price。
- Exit Price。
- Units。
- SL / TP。
- Close Reason。
- Realized P/L。
- Commission / Financing（如有）。
- Account Currency。
- 当时的持仓和风险敞口（如可获得）。

需要区分：

- 一笔订单。
- 一个交易对象。
- 一次交易生命周期。
- 一个交易周期内的多个部分成交或平仓记录。

不得将不同概念混为一谈。

## 3.4 Strategy Decision Reconstruction

尽可能收集完整决策链：

`Market Data → MC → Candidate → Filter → Ranking → Advisor → Execution`

对于每一个阶段，查明：

- 输入是什么。
- 输出是什么。
- 时间是什么。
- 是否通过。
- 未通过的原因是什么。
- 是否有对应日志。

如果策略只记录最终成交，而没有记录被拒绝的候选机会，必须明确报告：

`CANDIDATE_HISTORY_NOT_AVAILABLE`

不能用最终成交反推全部候选机会。

## 3.5 Required Phase 1 Deliverables

TRAE 必须提交：

| File | Purpose |
|---|---|
| `01_RUNTIME_FACTS.md` | 实际运行环境与版本事实 |
| `02_MC_DATA_INVENTORY.md` | MC 历史数据清单 |
| `03_TRADING_RECONSTRUCTION.md` | 实际交易重建 |
| `04_DATA_QUALITY_REPORT.md` | 数据质量与缺失情况 |
| `05_EVIDENCE_REGISTER.md` | 证据来源与事实登记 |
| `06_PHASE1_ACCEPTANCE.md` | 第一阶段验收报告 |
| `MC_AUDIT_PACKAGE/` | 原始数据导出包 |

数据包必须包含：

- 原始文件或可审计导出。
- 文件清单。
- SHA256。
- 数据时间范围。
- 时区说明。
- 数据字段说明。
- 文件来源。
- 数据缺失说明。
- 重复记录说明。

原始数据必须保持只读，不得为了方便分析而覆盖或修改。

---

# 4. Phase 2 — Offline MC Audit

**Priority:** P0  
**Execution:** ChatGPT / Python Offline Analysis  
**Prerequisite:** Phase 1 data package and data dictionary

ChatGPT 在获得真实数据后编写离线 Python 审计脚本。

脚本必须根据实际文件结构编写。

不得在没有检查真实数据前假设字段名、文件名或目录结构。

## 4.1 Main Analysis Outputs

以下为目标分析成果。

具体字段以 Phase 1 实际数据为准。

如果某项数据不存在，必须报告缺失，不允许生成虚构数据。

### CSV 01 — MC Snapshot History

建议文件：

`01_mc_snapshot_history.csv`

用途：建立所有历史 MC 快照的统一记录。

建议内容：

- Snapshot ID。
- Generated Time。
- Published Time。
- Instrument。
- Timeframe。
- Reference Price。
- P(up)。
- P(down)。
- Original Regime。
- Data Source。
- Validity Status。
- Duplicate Status。

要求：

保留原始概率，不允许擅自重新计算或修改原始分类。

### CSV 02 — Market Regime Timeline

建议文件：

`02_market_regime_timeline.csv`

用途：重建每个货币对的市场状态变化。

研究：

- 当前概率。
- 前一次概率。
- 概率变化幅度。
- 方向变化。
- Regime 变化。
- 持续时间。
- 后续价格变化。
- 后续波动幅度。

后续收益必须按明确时间窗口计算，例如：

- 1H。
- 4H。
- 8H。
- 1D。

具体周期根据实际数据频率决定。

严禁使用未来价格参与当时的决策信息计算。

### CSV 03 — Currency Consensus Timeline

建议文件：

`03_currency_consensus_timeline.csv`

用途：研究各货币在多个货币对之间的共同方向。

特别研究：

- JPY。
- USD。
- EUR。
- GBP。
- AUD。
- CAD。
- CHF。
- NZD。

必须处理货币对方向。

例如：

`USDJPY P(up) < 50%`

意味着 USDJPY 下跌方向的概率较高，不能误认为 USD 强势。

对于每个时间点，应尽可能提供：

- Currency。
- Observation Time。
- Distinct Pair Count。
- Bullish Pair Count。
- Bearish Pair Count。
- Directional Consensus。
- Consensus Strength。
- Component Pairs。
- Data Quality。

重要约束：

同一货币对的重复记录不能被当成独立确认。

同一货币参与多个货币对，数据之间存在相关性。

不能简单将多个货币对视为独立样本。

### CSV 04 — Trade MC Alignment

建议文件：

`04_trade_mc_alignment.csv`

用途：将实际交易与开仓时可获得的 MC 数据进行匹配。

建议内容：

- Trade ID。
- Instrument。
- Trade Direction。
- Open Time。
- Matching MC Snapshot Time。
- P(up)。
- P(down)。
- Original Regime。
- MC Direction。
- Trade Alignment。
- Realized P/L。
- Close Reason。

必须采用 as-of matching：

只允许匹配交易开仓时已经生成并且实际可获得的 MC 数据。

不得使用开仓之后生成的 MC 数据解释开仓决策。

如果 MC 生成时间、发布时间或策略读取时间不明确，必须标记时间对齐不确定性。

### CSV 05 — Whipsaw / Wide-Range Trade Analysis

建议文件：

`05_whipsaw_trade_analysis.csv`

用途：专门研究宽幅震荡期间的双向止损现象。

建议内容：

- Trade ID。
- Instrument。
- Direction。
- Open Time。
- Close Time。
- Exit Reason。
- Realized P/L。
- Contemporaneous MC。
- Price Range。
- Realized Volatility。
- Directional Persistence。
- Opposite Direction Trade Exists。
- Same Instrument / Same Theme。
- Evidence Quality。

必须区分：

- 同一货币对的双向交易。
- 不同货币对的相关交易。
- 不同时间发生的独立交易。

不得仅因 LONG 和 SHORT 都发生 SL，就直接认定市场处于宽幅震荡。

### CSV 06 — Opportunity and Decision Reconstruction

建议文件：

`06_opportunity_decision_reconstruction.csv`

用途：调查策略为什么选择实际交易，而没有选择其他可能机会。

建议内容：

- Decision Time。
- Instrument。
- Candidate Direction。
- MC Direction。
- MC Probability。
- Candidate Eligibility。
- Filter Result。
- Rejection Reason。
- Ranking。
- Selected Status。
- Execution Status。

本文件高度依赖候选交易日志。

如果候选交易记录不完整，必须标记：

`INCOMPLETE_CANDIDATE_EVIDENCE`

不能从成交记录反向虚构未成交机会。

### CSV 07 — Risk Budget and Capital Utilization

建议文件：

`07_risk_budget_utilization.csv`

用途：研究实际资金和风险预算的使用情况。

建议内容：

- Timestamp。
- Open Trade Count。
- Available Capacity。
- Instrument。
- Currency Exposure。
- Units。
- Notional Exposure。
- Account Currency Exposure。
- Estimated Risk Exposure。
- MC Directional Consensus。
- Position Allocation。

必须区分：

- 名义交易量。
- 名义敞口。
- 实际保证金占用。
- SL 对应的潜在风险。
- 账户币种下的风险金额。

没有 SL 距离或其他有效风险依据时，不允许把名义交易量直接称为风险金额。

如果无法可靠计算风险敞口，必须单独标记。

### CSV 08 — Data Quality and Evidence Gaps

建议文件：

`08_data_quality_and_gaps.csv`

用途：记录所有数据限制。

包括：

- Missing Data。
- Duplicate Data。
- Timestamp Conflict。
- Invalid Probability。
- Missing Timeframe。
- Incomplete Trade History。
- Missing Candidate History。
- Missing Portfolio Snapshot。
- Missing Price History。
- Timezone Uncertainty。

每个问题必须记录：

- 涉及文件。
- 涉及时间。
- 涉及字段。
- 影响范围。
- 是否影响统计结果。
- 是否可以修复。
- 修复方式或无法修复的原因。

### CSV 09 — Statistical Evidence Summary

建议文件：

`09_statistical_evidence_summary.csv`

用途：集中展示各项统计结果。

包括：

- Sample Count。
- Date Range。
- Probability Distribution。
- Directional Accuracy。
- Brier Score。
- Log Loss。
- Calibration。
- Forward Return。
- Return Distribution。
- Market Regime Breakdown。
- Trade Outcome Breakdown。
- Confidence Interval。

指标只能在样本和数据定义满足要求时计算。

不能因为某个指标无法计算，就用另一个看起来相似的指标代替。

---

# 5. Statistical Methodology

## 5.1 Probability Evaluation

MC 是概率系统。

因此不能只看预测方向是否正确。

至少需要研究：

1. Brier Score。
2. Log Loss。
3. Probability Calibration。
4. Directional Accuracy。
5. Probability Bucket Performance。
6. Forward Return Distribution。

重点问题：

当 MC 给出较高方向概率时，实际结果是否具有相应的统计表现？

例如：

- 50%–55%。
- 55%–60%。
- 60%–65%。
- 65%–70%。
- 70% 以上。

分桶边界是分析工具，不是策略阈值。

不得根据同一批样本反复选择最有利的阈值，再将结果当作独立验证。

## 5.2 Probability Persistence

研究 MC 概率是否持续。

需要测量：

- 连续方向一致的时间。
- 概率变化幅度。
- 方向反转次数。
- Regime 切换次数。
- 不同持续时间对应的后续表现。

必须区分：

- 概率方向持续。
- 价格方向持续。
- 交易盈利持续。

三者不是同一概念。

## 5.3 Currency Consensus

货币强弱研究不能简单地对所有货币对进行计数。

必须考虑：

- Base / Quote 方向。
- 同一货币的重复暴露。
- 货币对之间的相关性。
- 数据缺失。
- 不同时间点的有效样本数量。

JPY 是重点研究对象，但不能因为当前观察到 JPY 强势，就只保留 JPY 数据。

其他货币也应使用相同方法分析，避免选择性验证。

## 5.4 Time-Series Validation

所有统计分析必须尊重时间顺序。

至少区分：

- Discovery Period。
- Validation Period。
- Out-of-Sample Period。

不能随机打乱时间序列后进行普通随机训练/测试拆分，再声称结果能够代表实盘表现。

如果历史样本不足以完成独立验证，必须明确说明。

## 5.5 Statistical Uncertainty

每项核心统计结果应尽可能报告：

- 样本量。
- 时间范围。
- 均值或中位数。
- 分布。
- 置信区间。
- 缺失情况。

不能只报告一个漂亮的百分比。

不能把统计显著性直接解释为实际交易价值。

---

# 6. Phase 3 — Demo Parallel Operation

**Priority:** P0  
**Execution:** Parallel with Phase 1 and Phase 2

审计与 Demo 运行必须同时进行。

不能等全部审计完成才开始收集新的 Demo 数据。

## 6.1 Demo Baseline

保留当前 Demo 基线。

记录：

- 当前代码版本。
- 当前策略配置。
- 当前 MC 数据。
- 当前交易决策。
- 当前实际成交。
- 当前仓位和风险敞口。
- 当前交易结果。

不得为了审计而改变基线策略行为。

## 6.2 Shadow Data Collection

在不改变交易决策的前提下，尽可能记录：

- MC 原始概率。
- 货币共识。
- 市场状态。
- 候选交易。
- 候选排名。
- 被拒绝原因。
- 实际交易。
- 资金占用。
- 交易生命周期。

Shadow 记录必须与实际执行结果分开。

`SHADOW_RESULT` 不得被当成实际成交。

## 6.3 Demo Comparison

后续需要比较：

| Dimension | Baseline | Shadow / Candidate |
|---|---|---|
| Candidate Count | 实际基线 | 影子方案 |
| Selected Trades | 实际基线 | 影子方案 |
| MC Alignment | 实际基线 | 影子方案 |
| Trade Distribution | 实际基线 | 影子方案 |
| Currency Exposure | 实际基线 | 影子方案 |
| Risk Utilization | 实际基线 | 影子方案 |
| Realized P/L | 实际成交 | 仅实际执行的结果 |
| Counterfactual P/L | 不适用 | 独立估算并标记 |

影子方案没有实际成交时，不能将理论收益写成实际收益。

## 6.4 Demo Acceptance

必须保证：

- 基线运行没有被影子逻辑污染。
- 影子数据与真实执行数据可以区分。
- 同一时间点的数据可以匹配。
- 所有影子决策都有明确原因。
- 不存在未经批准的下单行为。

---

# 7. Phase 4 — Independent Branch Preparation

**Priority:** P1  
**Prerequisite:** Phase 1 acceptance and initial audit findings

第一阶段完成后，根据实际审计结果，准备独立开发分支。

分支必须基于已经核实的生产代码版本。

必须记录：

- Base Branch。
- Base Commit。
- Working Branch。
- Changed Files。
- Configuration Changes。
- New Shadow Components。
- Test Results。

## 7.1 Development Objective

独立分支的目标是验证：

**如果策略更有效地使用 MC 概率、市场方向共识和市场状态信息，机会选择与资金分配是否得到改善？**

候选研究方向包括：

- MC Directional Clarity。
- Multi-Pair Currency Consensus。
- Probability Persistence。
- Market Regime Classification。
- Opportunity Ranking。
- Capital Allocation Priority。
- Wide-Range / Choppy Market Detection。

这些只是研究方向，不是已经批准的策略定义。

## 7.2 Live Shadow Boundary

独立分支可以准备在 Live 环境运行观察，但必须保持：

- 不提交新订单。
- 不修改现有持仓。
- 不修改 SL / TP。
- 不改变现有策略决策。
- 不改变现有生产执行权限。
- 不影响原有生产 runner。

Live Shadow 的用途是验证：

- 实时数据是否正确。
- MC 是否正确读取。
- 影子判断是否稳定。
- 决策原因是否可解释。
- 影子结果是否能够与实际交易匹配。

**Live Shadow 不等于 Live Trading Authorization。**

任何真实交易行为必须另行获得 Owner 明确批准。

---

# 8. Evidence Classification

所有报告必须区分以下证据等级。

| Level | Classification | Meaning |
|---|---|---|
| E0 | Missing | 没有足够数据 |
| E1 | Observed Fact | 可以从实际文件或日志直接确认 |
| E2 | Statistical Evidence | 有统计结果支持的关联或规律 |
| E3 | Out-of-Sample Evidence | 在独立时间样本中得到验证 |
| E4 | Strategy Impact Evidence | 能够证明策略行为变化带来实际改善 |

特别注意：

E2 不自动等于 E3。

E3 不自动等于 E4。

不能因为尚未达到 E4，就否定 E1 或 E2 已经发现的有价值信息。

同样，不能因为观察到某个市场现象，就直接认定某项策略改动必然有效。

---

# 9. Strict Data and Analysis Rules

以下规则具有强制性。

## 9.1 No Lookahead Bias

任何交易决策只能使用当时已经可获得的数据。

交易开仓之后生成的 MC 快照，不得用于解释该交易的原始决策。

## 9.2 No False Historical Reconstruction

历史重算 MC 必须与真实历史 MC 分开。

不得混合统计。

## 9.3 No Duplicate Inflation

重复快照、重复货币对和重复交易记录必须识别。

不得通过重复计数人为放大共识。

## 9.4 No Selective Sampling

不能只选择表现好的货币对、时间段或交易。

必须报告完整样本范围和排除原因。

## 9.5 No Unsupported Opportunity Claims

没有完整候选交易日志时，不能宣称某个未成交机会当时一定存在。

## 9.6 No Confusion Between Probability and Profit

概率优势不等于每笔交易盈利。

必须分别分析：

- 概率质量。
- 价格表现。
- 策略选择。
- 交易成本。
- 实际盈亏。

## 9.7 No Unapproved Strategy Changes

第一阶段和第二阶段的审计工作不得改变生产交易行为。

所有策略改动必须单独提交审议。

---

# 10. Acceptance Criteria

## Phase 1 — Runtime Fact Finding

必须满足：

- [ ] 已确认实际生产运行版本。
- [ ] 已确认实际 MC 数据来源。
- [ ] 已收集可获得的多日历史 MC 数据。
- [ ] 已确认最早可追溯 MC 时间。
- [ ] 已确认历史数据缺失情况。
- [ ] 已重建目标时间段的实际交易。
- [ ] 已调查宽幅震荡期间的双向止损。
- [ ] 已调查 JPY 强势的历史形成过程。
- [ ] 已检查策略 MC 消费链。
- [ ] 已检查候选交易和拒绝原因的日志覆盖。
- [ ] 已生成数据字典。
- [ ] 已生成证据登记表。
- [ ] 已生成完整数据包及 SHA256。
- [ ] 没有修改生产代码或交易行为。

## Phase 2 — Offline Audit

必须满足：

- [ ] 离线脚本基于真实数据结构编写。
- [ ] 能够重复运行。
- [ ] 原始数据不被修改。
- [ ] 时间匹配没有未来数据泄漏。
- [ ] 重复记录得到处理。
- [ ] 市场状态时间轴已经建立。
- [ ] JPY 共识时间轴已经建立。
- [ ] 实际交易与 MC 已进行时间匹配。
- [ ] 宽幅震荡事件已经独立分析。
- [ ] 非 JPY 交易选择情况已经调查。
- [ ] 资金使用情况已经分析，或明确说明数据不足。
- [ ] 所有核心分析都有 CSV 输出。
- [ ] 统计结果附带样本数量和时间范围。
- [ ] 事实、统计关联和假设明确分开。

## Phase 3 — Demo

必须满足：

- [ ] 基线 Demo 保持独立。
- [ ] Shadow 记录不影响交易决策。
- [ ] Shadow 与真实成交可以区分。
- [ ] 能够进行时间匹配。
- [ ] 能够记录 MC 与候选机会。
- [ ] 能够记录资金及风险敞口。
- [ ] 没有未经批准的下单行为。

## Phase 4 — Independent Branch

必须满足：

- [ ] 已记录准确的基准 commit。
- [ ] 已建立独立分支。
- [ ] 改动范围已经审议。
- [ ] Shadow 行为有完整记录。
- [ ] 不影响原有生产 runner。
- [ ] 没有未经授权的真实订单提交。

---

# 11. TRAE Task Execution Instructions

TRAE 必须严格遵循以下顺序：

### Step 1 — Read Only Inspection

先调查实际运行环境和历史数据。

不要先写代码。

不要先提出策略改进。

不要修改配置。

### Step 2 — Data Inventory

确认真实数据文件、字段、时间范围、缺失和重复情况。

优先导出真实原始数据。

### Step 3 — Trade Reconstruction

重建宽幅震荡期间的 LONG / SHORT 止损事件。

重建 JPY 强势形成期间的实际交易。

检查非 JPY 交易的实际选择过程。

### Step 4 — Evidence Report

形成事实报告。

每项结论都必须有证据来源。

如果无法确认，明确写入：

`NOT VERIFIED`

如果没有数据，明确写入：

`DATA NOT AVAILABLE`

### Step 5 — Audit Package

整理所有原始数据和报告。

生成 SHA256 清单。

确保数据包可以下载并在离线环境中重复分析。

### Step 6 — Parallel Demo

继续基线 Demo 和 Shadow 数据收集。

不得等待离线审计全部完成才开始记录新的运行数据。

### Step 7 — Stop and Submit

提交 Phase 1 全部交付物，等待审议。

不得擅自进入生产策略修改。

---

# 12. Final Expected Outcome

本项目最终必须回答以下问题：

1. 宽幅震荡最早何时开始，持续了多久？
2. MC 当时是否显示方向优势不明确？
3. MC 是否能够识别这种双向风险环境？
4. JPY 强势最早何时出现？
5. JPY 强势是否具有持续性和跨货币对一致性？
6. 策略是否识别并使用了 JPY 共同方向？
7. 为什么策略仍然大量参与非 JPY 交易？
8. 非 JPY 交易是否具有独立的统计优势？
9. 是否存在资金被方向优势不明确的机会占用？
10. MC 是否能够帮助策略更有效地选择值得参与的大行情？
11. 哪些发现已经有统计证据？
12. 哪些问题仍然缺少数据或需要 Demo 验证？

最终目标不是证明 MC 永远正确。

最终目标是建立一个能够利用概率信息、识别市场状态、选择交易机会并合理分配有限风险预算的交易系统。

**我们不追求参与所有行情。**

**我们追求只参与自己能够识别、能够评估、具有统计优势的行情。**

---

**Document Status:** PROPOSED — Pending Owner Approval  
**Implementation Authorization:** NOT GRANTED  
**Production Strategy Change:** NOT AUTHORIZED  
**Live Order Submission:** NOT AUTHORIZED  
