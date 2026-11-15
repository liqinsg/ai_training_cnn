# Phase 3.2 — 修改计划书（Revision Plan）

**Version:** 0.2 — 修订底稿
**Date:** 2026-11-15
**Status:** DRAFT — 待 owner 批准；批准后仅 **L1 流程**生效，**L2 技术取值**仍需逐项批准
**Scope:** Phase 3.2 决策包（01–05）的修订与推进顺序

> v0.2 变更：处理 7 个 P0 问题 + Volume/缩放/历史兼容性规则 + Calendar Contract + 实验验收标准 + 三层授权分离。**本版本不修改 01–05。**

---

## 0. 如何使用本文件

- 本文件是**修订底稿**，不是 owner 决策记录，也不是实现授权。
- 每个决策表中的 **「你的决定」** 列由 owner 填写；**未填即维持 PENDING**，下游不得当作已批准值。
- 本文件先修订到**完整、自洽**；随后**一次性批准**，再集中把结论落地到 01–05。
- **在 L2 批准前，不修改 01–05、不运行实验、不改任何代码。**

---

## 1. 背景与目标

- 输入：`docs/phase3_2/` 决策包 [01](01_INPUT_CONTRACT_OWNER_DECISION.md) / [02](02_FEATURE_TECHNICAL_DEFINITIONS_AND_ELIGIBILITY.md) / [03](03_EXPERIMENT_AUTHORIZATION_AND_ACCEPTANCE.md) / [04](04_RUNTIME_CONFIGURATION_DECISIONS.md) / [05](05_TECHNICALLY_ELIGIBLE_CANDIDATE_FREEZE.md)，及支撑文档 [DEV_TASK_PLAN](PHASE3_2_DEV_TASK_PLAN.md)、[STRICT_SPEC](PHASE3_2_STRICT_SPEC.md)、[决策矩阵](PHASE3_2_TECHNICAL_FEATURE_DECISION_MATRIX_v0.1.md)、[FEATURE_CONTRACT](PHASE3_2_FEATURE_CONTRACT.md)、[TFC 设计](PHASE3_2_Tech_Feature_Contract_v1.0_Design.md)、[Stage A](PHASE3_2_STAGE_A_SOURCE_RECONCILIATION.md)、[Stage B/Parity](PHASE3_2_TRAIN_INFERENCE_PARITY_REPORT.md)、[Artifact Recovery](PHASE3_2_ARTIFACT_EVIDENCE_RECOVERY.md)。
- 治理链路：Step0 → Step0.1 → Step1..Step7；**Step8–9 实现另行授权**。
- **本 Phase 的目标**：建立一套**新的、可复现、可验证的 Feature Contract**，而**不是**修复旧模型兼容性。旧模型的历史包袱可以正式结束，但其**证据链与状态记录不得被抹除**。

---

## 2. 现状快照（2026-11-15）

| 项 | 现状 |
|---|---|
| 分支 / HEAD | `v2026c` / `334cc00` |
| 工作树 | 干净（仅未跟踪 `mc_results`） |
| 决策包 01–04 | 全部 `PENDING`（0 项落地） |
| 文档 05 | 空模板，37 行全 `NOT FROZEN` / `DEFER` |
| Stage A / B | `ACCEPTED` |
| Stage C | `BLOCKED`（active artifact 未取得） |
| Phase 3.2 | `OPEN` |
| 候选分布 | 37 = 4 `ACCEPTABLE AS-IS` + 19 `REDEFINE` + 14 `DEFER` + 0 `EXCLUDE` |

---

## 3. 授权模型（三层分离）— 对应 P0-1

**接受计划书 ≠ 接受全部技术建议。** 三个层次必须分开记录、分别批准。

| 层级 | 名称 | 授权内容 | 不授权 |
|---|---|---|---|
| **L1** | 流程批准 | 批准修订流程与治理方式（即批准本文件） | 任何技术取值 |
| **L2** | 技术决策批准 | **逐项**批准 IC‑01..08、FD‑01..09、RC‑01..11 及 §11 分歧点 | 实现 / 接线 |
| **L3** | 实现授权 | Step8–9（实现、接线、部署） | —— |

规则：

1. L1 通过后，仅允许执行 §12 中的 **Step0.1 治理清理（A1/A2）**。
2. **A3（legacy 处置）必须等 §11 分歧点 2 明确批准后才能执行。**
3. 01–05 的落地写入，仅在对应条目获得 L2 批准后进行。
4. L3 不得因 Step7 完成而**自动**获得。

---

## 4. 修改范围

### 4.1 A 层 — 治理/一致性（纯文档编辑）

| ID | 修改项 | 说明 | 门槛 |
|---|---|---|---|
| A1 | 声明取代关系 | 明确新 pack(01–05) 与旧 `PHASE3_2_FEATURE_CONTRACT.md`(v0.2-decision) 的关系：新 pack supersede 旧治理决策 | L1 |
| A2 | 消除重复副本 | `docs/01..05` 与 `docs/phase3_2/01..05` 完全相同；指定唯一权威目录，另一份删除或改为指针 | L1 |
| A3 | legacy 处置落地 | 按 §7 处理表写入 03/05 | **L2（依赖 §11 分歧点 2）** |

### 4.2 B 层 — 决策登记（我的建议取值，全部待 L2 批准）

**B1. 输入契约（Doc 01 · IC‑01..08）**

| ID | 决策 | 我的建议 | 你的决定 |
|---|---|---|---|
| IC‑01 | 目标周期 | M15 | |
| IC‑02 | 时间戳约定 | candle-close（若无反证） | |
| IC‑03 | 时区 | timezone-aware UTC | |
| IC‑04 | 未完成 K 线 | 一致排除最新未完成根 | |
| IC‑05 | 节奏 | 15 分钟，配套 **Calendar Contract**（§5） | |
| IC‑06 | 非法批次 | 整批拒绝，不删行/不插补/不部分输出 | |
| IC‑07 | 会话缺口 | 仅接受 **Calendar Contract** 解释的缺口（§5） | |
| IC‑08 | 训练/推理 parity | 相同校验实现与失效语义（分层见 §8） | |

**B2. 特征定义（Doc 02 · FD‑01..09）**

| ID | 决策 | 我的建议 | 你的决定 |
|---|---|---|---|
| FD‑01 | 目标周期与输入语义 | 同 IC‑01/04 | |
| FD‑02 | ACCEPTABLE/REDEFINE 公式与命名 | 沿用[决策矩阵](PHASE3_2_TECHNICAL_FEATURE_DECISION_MATRIX_v0.1.md) | |
| FD‑03 | ATR 完整计算定义 | 见 §6（backend/输入/初始化/warm‑up/失效/派生） | |
| FD‑04 | RSI 完整计算定义 | 见 §6（backend/平滑/零分母/warm‑up） | |
| FD‑05 | MACD 完整计算定义 | 见 §6（EMA 递归/初始化/三列/有效区间） | |
| FD‑06 | ADX 完整计算定义 | 见 §6（Wilder/零分母/中断/重新 seed） | |
| FD‑07 | Volume 语义 | `EXCLUDE`（见 §10） | |
| FD‑08 | 会话与日历 | 会话保留 IANA tz（§11‑4）；日历见 §5 | |
| FD‑09 | warm‑up / 失效行为 | 逐特征显式（§6） | |

**B3. 运行配置（Doc 04 · RC‑01..11）**

| ID | 决策 | 我的建议 | 你的决定 |
|---|---|---|---|
| RC‑01 | 生产周期 | M15 | |
| RC‑02 | 生产历史长度 | **NOT YET APPROVED**，待 Step4 证据 | |
| RC‑03 | 时间戳约定 | 同 IC‑02 | |
| RC‑04 | 未完成 K 线处理 | 同 IC‑04 | |
| RC‑05 | 日历/会话缺口 | 引用 **Calendar Contract**（§5） | |
| RC‑06/07/08 | Volume 源/可比性/非法值 | 随 FD‑07 一并 `EXCLUDE`（§10） | |
| RC‑09/10 | London / New York 会话 | 保留 IANA tz 语义（§11‑4） | |
| RC‑11 | IANA tz 数据库身份 | 钉死版本与来源 + DST 规则 + **FAIL CLOSED**（§11‑4） | |

### 4.3 C 层 — 技术自洽性

| ID | 问题 | 处理 |
|---|---|---|
| C1 | `vol_*` 缩放变更 | 单独登记，见 §10（非 bugfix，属语义改变） |
| C2 | 週末/交易时段缺口 | 由独立 **Calendar Contract** 解决（§5） |
| C3 | parity 范围受限 | 分层记录，禁用"NOT REQUIRED"（§8） |
| C4 | 新契约面向新模型 | legacy 正式结束，但证据/状态保留（§7） |

---

## 5. Calendar Contract（独立权威契约）— 对应 P0-4

**必须先把交易日历定义成一份独立契约，再定义缺口校验。**
`Calendar Contract` 是 **IC 与 RC 共同引用的唯一权威定义**，不允许两份文档各自解释；也不允许把所有 >15 分钟间隔直接判为非法——必须先判断该间隔是否被批准的日历解释。

**至少需定义：**

| # | 条目 | 待定内容 |
|---|---|---|
| 1 | 正常交易周开放时间 | |
| 2 | 周末关闭时间 | |
| 3 | 每周开市 / 收市边界 | |
| 4 | 节假日规则及数据来源 | |
| 5 | DST 转换规则 | |
| 6 | 非正常停市处理 | |
| 7 | 合法缺口 vs 非法缺口 的判定 | |
| 8 | 无法解释缺口的处理 | |

---

## 6. 特征计算语义与失效规则补全 — 对应 P0-7

> 仅确定"公式名称"不够；必须确定**每个特征的完整状态转换与失效语义**。以下为建议定义，全部待 L2 批准。

### FD‑03 · ATR
- backend：单一 canonical 实现（pandas‑ta 系）；禁止手工 fallback 静默替代
- 输入：High/Low/Close（未完成 K 线已排除）
- 平滑：Wilder RMA（alpha = 1/n），n = 14
- 初始化 / warm‑up：前 n−1 根无值；首个有效值语义需固定
- 失效：窗口内任一输入不可得 → 该点无值
- 派生：`atr_ma` / `atr_expanding` / `atr_ratio` / `atr_pct` 的窗口与除零规则显式定义

### FD‑04 · RSI
- backend：单一 canonical 实现（pandas‑ta 系）
- 平滑：Wilder RMA（alpha = 1/n），n = 14
- 零分母行为：`avg_loss == 0 → RSI = 100`；**`avg_gain == avg_loss == 0` 的取值待你定**（50 或 NaN）
- warm‑up：前 n 根无值
- `rsi_slope`：RSI 一阶差分，窗口 1

### FD‑05 · MACD
- EMA 递归：alpha = 2/(n+1)，`adjust=False`
- 初始化：首值语义（EMA seed = 首值）显式
- 周期：12 / 26 / 9
- 输出三列：`macd` / `macd_signal` / `macd_hist`（hist = macd − signal）
- 有效区间与失效语义显式

### FD‑06 · ADX（Wilder，n = 14）
完整 break/reseed 规则写入 FD‑06，不留讨论记录：

1. 无效 K 线：按输入契约**拒绝**。
2. 有效 K 线但 DI/DX 分母为零：**中断 ADX 链**（该点 DX 无效）。
3. **保留** Wilder TR/DM 平滑状态（不重置）。
4. 累积新的**连续有效** DX。
5. 达到 n 个有效 DX 后**重新 seed**。
6. **不沿用**中断前的 ADX 状态。
7. 首次 seed 位置：index = 2n−1（n=14 → 27）。

---

## 7. Legacy 结束与证据保全 — 对应 P0-2

**"放弃 legacy" ≠ "Stage C 自动解除"。** 若 §11 分歧点 2 批准放弃 legacy，则按下列处理：

| 项目 | 应有处理 |
|---|---|
| 旧 artifact 追踪 | **STOP** |
| Stage C 原定任务 | `CLOSED BY SCOPE CHANGE / NOT APPLICABLE` |
| Artifact blocker | `CLOSED BY OWNER DECISION`（**不是**"证据已取得"） |
| 新契约 | 独立建立 |
| 新模型验证 | 纳入新 Phase 的后续流程 |

规则：
- **禁止**把"未取得 artifact"描述为"Stage C 已完成"。
- 禁止后续把 Stage C 的 `ACCEPTED` 当作新契约的验证证据。
- 既有证据链与状态记录**保留**，不抹除。

---

## 8. Train / Inference Parity 分层 — 对应 P0-6

| 层级 | 验证内容 | 状态 |
|---|---|---|
| P1 | 原始 OHLCV 输入一致性 | 必须 |
| P2 | Feature Engineering 输出一致性 | 必须 |
| P3 | Scaler 输入/输出一致性 | 暂不具备 |
| P4 | 模型输入张量一致性 | 暂不具备 |
| P5 | 模型预测输出一致性 | 暂不具备 |

规则：
- 记录 **`FULL_PARITY_STATUS = NOT VERIFIED`**；**禁止**写成 `FULL_PARITY = NOT REQUIRED`。
- 缺 `libomp.dylib` 是**当前机器环境限制**，**不是**理论上的架构限制，不得固化。

---

## 9. 离线实验设计与验收标准 — 对应 P0-5

### 9.1 历史长度序列与角色

| 长度 | 角色 |
|---|---|
| 200 | **诊断基准**（表征 warm‑up 敏感性）；**不参与验收** |
| 300 | 验收对成员 |
| 500 | 验收对成员 |
| 800 | 验收对成员 |

### 9.2 比较矩阵

| 比较对 | 作用 | 是否验收 |
|---|---|---|
| 200v300 | 诊断（"200 是否足够"） | 否 |
| **300v500** | 主验收对 1 | **是** |
| **500v800** | 主验收对 2 | **是** |
| 200v500 | 诊断（全距趋势） | 否 |
| 200v800 | 诊断（全距趋势） | 否 |

> 特征只有**同时**通过 300v500 与 500v800，才判定为"通过历史长度收敛"。

### 9.3 容差公式

统一写成：

```
|A − B| ≤ atol + rtol × |B|
```

其中 `atol = 1e-10`，`rtol = 1e-8`（A、B 为该位置的两次取值）。

### 9.4 验收细则（需在 Doc 03 中逐条固定）

- **比较对象与列集合**：同一品种、同一时间轴上的候选特征列；DEFER / EXCLUDE 项按各自规则排除并声明。
- **索引对齐**：以 timestamp 对齐；两 run 长度不同，取**共同重叠区间**比较。
- **NaN 规则**：`NaN == NaN` 视为相等；`NaN` vs 数值 = 失败；warm‑up 区间的 NaN 不计入。
- **行数与索引**：行数允许不同（因长度不同）；只比较**重叠且非 warm‑up** 区域。
- **每特征是否允许差异**：按 §9.5 特征类判定。
- **失败定位**：输出首个超差的 `(特征, timestamp, A, B, diff, tol)`，并给出该特征最大超差条数与分布。

### 9.5 特征类与各自的验收判据

> 历史长度稳定性测试**不是**简单数值比较，而是验证特征定义是否具备**预期的收敛性质**。不同特征必须有自己的验收标准。

| 类 | 特征 | 期望性质 | 验收 |
|---|---|---|---|
| **E 类**（精确定窗） | `return_*`、body/wick/range、`dist_*`、`horizon_vol_*`、`atr_percentile`(ECDF)、time 数值 | 给定同一窗口应逐位一致（差异仅来自 warm‑up 边界） | 直接套用 §9.3 容差 |
| **R 类**（递归/初始化敏感） | `atr*`、`rsi`、`rsi_slope`、MACD 三列、`adx` | \|Δ\| 随历史增长**单调下降**，并在验收对落入容差 | 收敛对容差通过 |

规则：**禁止**把 R 类初始化收敛问题类推到 E 类（ECDF 窗口语义 ≠ EMA 初始化语义）。

---

## 10. Volume 处置与 vol 缩放登记 — 对应附加项 1 & 2

### 10.1 Volume（支持 EXCLUDE）
- 对**新模型契约**：`vol_sma_ratio`、`vol_trend` 两特征 `EXCLUDE`。
- `EXCLUDE` 仅针对新契约；**不代表**历史模型的输入定义已获验证。
- 删除 Volume **不得**顺带改变其他特征的计算语义（静默语义漂移）。

### 10.2 vol 缩放改变（须单独登记）

| | 公式 | 说明 |
|---|---|---|
| 旧 | `rolling(n).std() * sqrt(n*4)` | 源码语义（如 n=12 → `sqrt(48)`） |
| 新 | `rolling(n).std() * sqrt(n)` | 新契约语义（如 n=12 → `sqrt(12)`） |

规则：
- 明确新旧公式并登记为**特征语义改变**，**不是** bugfix。
- 旧模型**不兼容**；新契约固定新公式。
- **禁止**旧模型通过修改 metadata 冒充兼容。

---

## 11. 待 owner 拍板的分歧点

| # | 分歧点 | 我的推荐 | 你的决定 |
|---|---|---|---|
| 1 | 目标周期 | M15 | |
| 2 | legacy 是否正式放弃（据此按 §7 处理表关闭 Stage C blocker） | 放弃，另起新契约 | |
| 3 | Volume 两特征 | `EXCLUDE`（§10） | |
| 4 | 会话时区 | **保留 IANA tz**；钉死 tz 数据库版本与来源；明确 DST 切换日规则；环境无 tz 数据时 **FAIL CLOSED**；**禁止静默退化为固定 UTC 偏移** | |
| 5 | parity 范围 | 接受 §8 分层：P1/P2 必须，P3–P5 暂不具备；记录 `FULL_PARITY_STATUS = NOT VERIFIED` | |
| 6 | 交易日历 | 先定 §5 Calendar Contract，再定缺口校验 | |

---

## 12. 执行顺序

| 步骤 | 动作 | 产出 | 授权前提 |
|---|---|---|---|
| Step0 | **Revision Plan 批准**（仅 L1：批准流程，不代表批准技术取值） | 批准的修订流程 | owner 认可本文件 |
| Step0.1 | **治理清理**：A1 / A2；A3 待分歧点 2 | 治理说明 | L1 |
| Step1 | **Input Contract**：IC‑01..08（含 **Calendar Contract**） | 输入契约决策记录 | L2 |
| Step2 | **Feature Definition**：FD‑01..09（公式/backend/warm‑up/失效语义完整） | 特征定义决策记录 | L2 |
| Step3 | **Experiment Authorization**：范围/数据/比较矩阵/容差/验收 | 实验授权记录 | L2 |
| Step4 | **Offline Experiments**（200/300/500/800 稳定性与一致性报告） | 逐特征证据报告 | L2 |
| Step5 | **Runtime Configuration**：依实验结果填 RC‑01..11 | 运行配置决策记录 | L2 |
| Step6 | **Candidate Freeze**：逐项登记 37 候选最终状态与证据 | 技术合格候选清单 | L2 |
| Step7 | **Phase 3.3 Handover** | 交接包 | L2 |

> **Step 8–9（Implementation / Integration）另行授权；不得因 Step 7 完成而自动获得授权。**

---

## 13. 边界（本文件不做的事）

- 不改任何 `.py` 文件、不改生产 FeatureEngine / 模型加载行为。
- 不训练模型、不写入或覆盖 model artifact、不改依赖或主机环境。
- 不部署、不接 `PredictionResult` READY、不改任何交易行为。
- 在 L2 批准前：不修改 01–05、不落地任何决策、不运行实验。

---

## 14. 修订记录

| 版本 | 日期 | 修改人 | 变更摘要 |
|---|---|---|---|
| 0.1 | 2026-11-15 | assistant | 初稿：现状快照、修改范围 A/B/C、6 个分歧点、执行顺序 |
| 0.2 | 2026-11-15 | assistant | 处理 P0‑1..P0‑7：三层授权分离、legacy 证据保全、会话保留 IANA tz+FAIL CLOSED、Calendar Contract、实验比较矩阵+容差+分类验收、parity 分层+FULL_PARITY_STATUS；新增 Volume EXCLUDE 与 vol 缩放登记；执行顺序加入 Step0.1；明确本版本不改 01–05 |
| | | | |
