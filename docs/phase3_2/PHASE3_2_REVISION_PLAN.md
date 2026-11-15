# Phase 3.2 — 修改计划书（Revision Plan）

**Version:** 0.3 — 完整性修订稿
**Date:** 2026-11-15
**Status:** DRAFT — 待 owner 批准；批准后仅 **L1 流程**生效，**L2 技术取值**仍需逐项批准
**Scope:** Phase 3.2 决策包（01–05）、Calendar Contract 的治理、修订与推进顺序

> v0.3 变更：拆分 L2-A / L2-B；规定 Calendar Contract 的独立交付形式及 OANDA 来源要求；保留旧决策历史并先做引用审计；细化 candle-close 定义；固定 FD-02 矩阵版本/hash；校正 RSI slope 与矩阵的一致性；明确 parity 不降级、实验参考值和历史窗口判定范围。**本版本不修改 01–05，也不批准任何技术取值。**

---

## 0. 如何使用本文件

- 本文件是**修订底稿**，不是 owner 决策记录，也不是实现授权。
- 每个决策表中的 **「你的决定」** 列由 owner 填写；**未填即维持 PENDING**，下游不得当作已批准值。
- L1 仅批准流程、文档目录治理方式和逐项决策顺序；**不批准任何建议技术值**。M15、ADX `n=14`、Volume `EXCLUDE`、任何 backend/session/calendar 值均不得因 L1 生效。
- L2 分为 **L2-A**（Step1–3：输入/日历/特征定义/实验协议）和 **L2-B**（Step5：依赖实验结果的运行配置）。每项由 owner 单独记录；空白仍为 `PENDING`。
- 在对应 L2 项批准前，不把决策写成已生效的 01–05 值；未批准 Doc03 前不运行或查看新实验结果；不改代码。
- L1 后可按 Step0.1 编写 Calendar Contract 草案并做只读引用盘点；其日历值在 L2-A 批准前不生效。

---

## 1. 背景与目标

- 输入：`docs/phase3_2/` 决策包 [01](01_INPUT_CONTRACT_OWNER_DECISION.md) / [02](02_FEATURE_TECHNICAL_DEFINITIONS_AND_ELIGIBILITY.md) / [03](03_EXPERIMENT_AUTHORIZATION_AND_ACCEPTANCE.md) / [04](04_RUNTIME_CONFIGURATION_DECISIONS.md) / [05](05_TECHNICALLY_ELIGIBLE_CANDIDATE_FREEZE.md)，及支撑文档 [DEV_TASK_PLAN](PHASE3_2_DEV_TASK_PLAN.md)、[STRICT_SPEC](PHASE3_2_STRICT_SPEC.md)、[决策矩阵](PHASE3_2_TECHNICAL_FEATURE_DECISION_MATRIX_v0.1.md)、[FEATURE_CONTRACT](PHASE3_2_FEATURE_CONTRACT.md)、[TFC 设计](PHASE3_2_Tech_Feature_Contract_v1.0_Design.md)、[Stage A](PHASE3_2_STAGE_A_SOURCE_RECONCILIATION.md)、[Stage B/Parity](PHASE3_2_TRAIN_INFERENCE_PARITY_REPORT.md)、[Artifact Recovery](PHASE3_2_ARTIFACT_EVIDENCE_RECOVERY.md)。
- 治理链路：Step0 → Step0.1 → Step1..Step3（L2-A）→ Step4 → Step5（L2-B）→ Step6–7；**Step8–9 实现另行 L3 授权**。
- **本 Phase 的目标**：建立一套**新的、可复现、可验证的 Feature Contract**，而**不是**修复旧模型兼容性。旧模型的历史包袱可以正式结束，但其**证据链与状态记录不得被抹除**。
- 本文件批准后是**新契约决策流程**的权威入口；它不追溯覆盖旧 Feature Contract 的历史决定。`PHASE3_2_DEV_TASK_PLAN.md` 是执行细化稿，L1 后需与本文件的 L2-A/L2-B、Calendar 和 legacy 规则核对；冲突时以本文件及各已批准决策记录为准。

---

## 2. 现状快照（2026-11-15）

| 项 | 现状 |
|---|---|
| 分支 / HEAD | `v2026c` / `720fe34`（快照检查时） |
| 工作树 | `git status --porcelain=v1` 为空；`mc_results/` 被忽略，不等于已审阅其内容 |
| 决策包 01–04 | 全部 `PENDING`（0 项落地） |
| 文档 05 | 37 项模板均未冻结；无 `TECHNICALLY ELIGIBLE` 项 |
| Stage A / B | `ACCEPTED` |
| Artifact Evidence Recovery | `UNSUCCESSFUL / CLOSED — EVIDENCE NOT RECOVERED` |
| Stage C / Phase 3.2 | Feature Contract 记录 Stage C `PARTIAL / BLOCKED`；Artifact Recovery 记录 Stage C `BLOCKED — ARTIFACT EVIDENCE`；Phase 3.2 `OPEN` |
| 候选分布 | 37 = 4 `ACCEPTABLE AS-IS` + 19 `REDEFINE` + 14 `DEFER` + 0 `EXCLUDE` |
| Calendar Contract | 尚未创建；不得假设任何周末/维护/节假日值 |
| Owner decisions | 01–04 决策寄存表待填；05 未冻结 |

01–05 同名副本在 `docs/` 与 `docs/phase3_2/` 经 `cmp` 确认为逐字节相同；仓库级引用盘点尚未完成。当前建议 `docs/phase3_2/` 为 canonical 目录，仍须经 L1 接受 A2 流程后才能执行引用/副本治理。删除或改写副本前必须先完成引用扫描并获 A2 具体批准。

**A2 更新记录（2026-11-15，仅追加，不改上文）：** 上文「逐字节相同」在 2026-11-15 将 L2 决定写入 `docs/phase3_2/` 后不再成立（五对全部 DIFF）。仓库级引用扫描已完成，结论见 `PHASE3_2_A2_REFERENCE_SCAN.md`（全仓库无任何引用指向根目录副本）。Owner 已接受 A2 方案 A：canonical 定为 `docs/phase3_2/`，根目录 `docs/01–05` 五个副本已删除；其原始内容由归档 `phase3_2_owner_decision_pack.zip` 与 git 历史（提交 `334cc00` 之前的版本）保留。

---

## 3. 授权模型（三层分离）— 对应 P0-1

**接受计划书 ≠ 接受全部技术建议。** L1 只批准流程；L2-A/L2-B 分批批准技术与运行决定；L3 才是实现授权。任何一层都不能被相邻层的批准自动替代。

| 层级 | 名称 | 授权内容 | 不授权 |
|---|---|---|---|
| **L1** | 流程批准 | 批准本文件中的决策顺序、Calendar Contract 交付形式、A1/A2 治理方式 | M15、ADX `n=14`、Volume `EXCLUDE`、backend、timezone/calendar、session、其他技术/运行取值；实验；实现 |
| **L2-A** | 输入/特征/实验协议批准 | Step1–3：逐项批准 IC、Calendar Contract、FD 及 Doc03 实验方案与明确实验授权 | Step4 以外的实验；L2-B 运行配置；实现/接线 |
| **L2-B** | 证据后运行配置批准 | Step5：根据 Step4 证据逐项批准 RC，尤其 production history length；必要时批准额外预注册比较 | 实现/接线 |
| **L3** | 实现授权 | Step8–9 的具体文件范围、实现/集成任务及验收 | 未写入该授权的训练、artifact、部署、READY 或交易行为变更 |

规则：

1. L1 通过后，只允许 §12 Step0.1 的治理工作：只读引用盘点、按已批准路径治理重复副本、建立并填充 Calendar Contract **草案**及其来源证据；日历值在 L2-A 批准前不生效。
2. L2-A 按 Step1→Step2→Step3 逐项审批：先输入/Calendar，再特征定义，再实验协议。三步全部批准后才可开始 Step4；Doc03 必须明确批准实验范围。
3. L2-B 只在 Step4 报告验收后发生。RC-01/03/04 等若与已批准 IC 相同，只作一致性引用；RC-02 等依赖证据的值不得在 Step4 前批准为最终值。
4. **A3（legacy 处置）必须等 §11 分歧点 2 明确批准后才能执行**，且只能追加新的 owner 决定记录，不得改写旧历史状态。
5. 01–05 的决策字段仅在对应 L2 项批准后落地；L1 不得填写或默认其建议列。
6. L3 不得因 Step7 完成、候选冻结或 L2 批准而**自动**获得。

---

## 4. 修改范围

### 4.1 A 层 — 治理/一致性（纯文档编辑）

| ID | 修改项 | 说明 | 门槛 |
|---|---|---|---|
| A1 | 声明新旧治理关系 | 新 pack 经批准后，成为**新 Feature Contract** 的权威决策入口；旧 `PHASE3_2_FEATURE_CONTRACT.md` 与 Stage A/B/C 记录保留其原始内容、日期和历史状态，不追溯改写。新旧契约不得混用，也不据此声称旧 artifact 兼容。 | L1 流程批准；具体 legacy scope 另需 L2 |
| A2 | 确定唯一权威目录并治理副本 | 推荐 `docs/phase3_2/` 为 canonical。已验证根目录与子目录 01–05 五对副本逐字节相同；先做全仓库引用扫描并列出引用目标，再提交具体重定向/指针方案。未完成扫描与 owner 对具体 diff 的批准前，不删除、不覆盖副本。 | L1 批准流程；具体文件改动按扫描结果逐项接受 |
| A3 | legacy recovery scope decision 记录 | 仅在 §11 分歧点 2 获得 L2 决定后追加新的 owner 决定记录；不修改旧合同、Strict Spec、Artifact Evidence Recovery 或既有报告。 | **L2（依赖 §11 分歧点 2）** |

**A1 的历史保护规则：**“supersede”只表示新 pack 获批后支配未来的新契约决策，不表示旧决策记录失效或被擦除。若 owner 选择停止旧 artifact recovery，只关闭该 recovery work item，并记录 `CLOSED BY OWNER SCOPE DECISION / NOT APPLICABLE TO NEW CONTRACT`；Stage C 原记录仍为 `PARTIAL / BLOCKED`，Artifact Evidence Recovery 仍为 `UNSUCCESSFUL / CLOSED — EVIDENCE NOT RECOVERED`。不得改写成 Stage C 已完成、Stage C accepted 或 artifact evidence recovered。

### 4.2 B 层 — 决策登记（我的建议取值，全部待 L2 批准）

**B1. 输入契约（Doc 01 · IC‑01..08）**

| ID | 决策 | 我的建议 | 你的决定 |
|---|---|---|---|
| IC‑01 | 目标周期 | M15 | |
| IC‑02 | 时间戳约定 | 来源端时间戳语义必须查明并明确选 candle-open 或 candle-close；不能仅依据 `time` 字段名推断 | |
| IC‑03 | 时区 | timezone-aware UTC | |
| IC‑04 | 未完成 K 线 | 一致排除最新未完成根 | |
| IC‑05 | 节奏 | 15 分钟，配套 **Calendar Contract**（§5） | |
| IC‑06 | 非法批次 | 整批拒绝，不删行/不插补/不部分输出 | |
| IC‑07 | 会话缺口 | 仅接受 **Calendar Contract** 解释的缺口（§5） | |
| IC‑08 | 训练/推理 parity | 相同校验实现与失效语义（分层见 §8） | |

IC‑02/03/04 的 owner decision 必须共同回答：①源时间戳标记开盘还是收盘；②以什么来源信号判定 candle 已完成（优先核实 OANDA candle `complete` 等源字段；没有源字段时须审批并验证替代判据）；③原始时间戳在哪一层转换/规范化到 UTC，且验证与特征只读取规范化值；④最新未完成 candle 如何识别并排除；⑤历史训练与实时推理使用完全相同规则。以上均不得由本计划的建议自动选定。

**B2. 特征定义（Doc 02 · FD‑01..09）**

| ID | 决策 | 我的建议 | 你的决定 |
|---|---|---|---|
| FD‑01 | 目标周期与输入语义 | 同 IC‑01/04 | |
| FD‑02 | ACCEPTABLE/REDEFINE 公式与命名 | 以矩阵 `PHASE3_2_TECHNICAL_FEATURE_DECISION_MATRIX_v0.1.md` 为审批基线；SHA‑256 `808bdcbdbb7b95a9322183686c9440746df0fc703184475369eb9990044c0453` | |
| FD‑03 | ATR 完整计算定义 | 见 §6（backend/输入/初始化/warm‑up/失效/派生） | |
| FD‑04 | RSI 完整计算定义 | 见 §6（backend/平滑/零分母/warm‑up） | |
| FD‑05 | MACD 完整计算定义 | 见 §6（EMA 递归/初始化/三列/有效区间） | |
| FD‑06 | ADX 完整计算定义 | 见 §6（Wilder/零分母/中断/重新 seed） | |
| FD‑07 | Volume 语义 | `EXCLUDE` 是建议，仅在 L2 明确批准后才对新契约生效；未批准前保持 `DEFER` | |
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
| RC‑06/07/08 | Volume 源/可比性/非法值 | 仅在 L2 批准 FD‑07=`EXCLUDE` 后记录为不适用；否则保持 `DEFER` 并明确源语义、覆盖、可比性、missing/zero/negative policy | |
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

## 5. Calendar Contract（独立、版本化权威契约）— 对应 P0-4

L1 后建立独立文件 **`docs/phase3_2/PHASE3_2_CALENDAR_CONTRACT.md`**。初版为 `v0.1 DRAFT — PENDING L2-A OWNER APPROVAL`；草案必须包含可追溯来源和可执行的规则结构，不能只是空白待填清单。**写草案不批准任何实际交易日历值。**

此 Calendar Contract 的范围是 **OANDA 所提供 candle data 的可用性、时间标签与相邻 candle 缺口解释**，不是泛化的外汇市场交易时间表，也不是 London/NY 特征的本地 session 定义。不能用抽象的“Forex 周日开盘/周五收盘”代替 OANDA feed 的实证/文档规则。

### 5.1 必需字段与证据

| 字段 | Calendar Contract 必须记录 |
|---|---|
| Contract identity | 独立版本、状态、owner、批准日期、变更历史；任何 schedule 语义改变升版本 |
| OANDA source identity | 实际使用的 OANDA 产品/API、环境（practice/live）、endpoint 或 feed、granularity、适用 instrument 范围；以仓库实际调用和获批运行路径为准，不臆测 |
| Source provenance | OANDA 官方 API/产品文档或可追溯的 OANDA 提供 schedule/availability source 的名称、版本/发布日期、获取日期、链接/文件 hash；若结合其他权威节假日源，逐项标明优先级和版本 |
| Timestamp/completion | OANDA 返回时间戳的语义（open/close）、时区、candle completion 字段/规则；必须与 IC-02/03/04 一致 |
| Expected cadence | M15 只有在 IC-01/05 获批后适用；定义普通连续时段的预期相邻 timestamp 和边界约定 |
| OANDA availability schedule | 有证据支持的每周开闭、周末、每日 maintenance/暂停窗口，按 instrument/feed 有差异时分别列出 |
| Holidays / exceptional closures | 节假日、临时停市、feed outage 的可用来源、覆盖范围、更新频率、过期处理；无法从权威来源确定的项目标 `UNRESOLVED`，不填猜测时间 |
| DST | 日历使用的 timezone/IANA zone、tz database 来源与固定版本；转换边界以 UTC instants 验证 |
| Gap classifier | 对每类允许缺口明确可匹配的时间规则及证据；超出获批例外的 gap 一律 `UNEXPLAINED` |
| Failure/update policy | 无来源、来源过期、来源冲突或缺口无法解释时 fail closed；契约如何复核/升版本 |
| Acceptance fixtures | 正常相邻 M15 candle、周末/每日维护/节假日边界（仅在有 OANDA 证据时）、异常 gap、source stale/conflict fixtures 及预期结果 |

如果 OANDA 没有发布足以解释某类间隔的正式 schedule，Contract 必须说明需要的独立权威来源或将该 gap 规则保持 `UNRESOLVED`；未解决的 gap 不得默认为正常。必须分辨“底层市场开放”与“OANDA 服务/API 实际提供 candle”两件事。

### 5.2 唯一引用规则与批准门槛

- Calendar Contract 是 IC‑05/IC‑07、RC‑05 及所有依赖 candle gap 的实验的**唯一日历定义来源**。这些文档只引用 contract ID/version，不复制交易日历时间表。
- London/NY 本地 session 特征仍由 FD/RC session 决策定义；它们可引用同一 IANA tz database identity，但不能把 session hours 混入 OANDA candle availability calendar。
- Calendar Contract 必须在 Step1 作为 L2-A 的一部分获批；未批准前不允许运行依赖缺口判断的实验。
- 任一来源/version/覆盖范围或 schedule 变化需出新版本并重新批准相关 IC/RC/实验引用。

---

## 6. 特征计算语义与失效规则补全 — 对应 P0-7

> 仅确定"公式名称"不够；必须确定**每个特征的完整状态转换与失效语义**。以下为建议定义，全部待 L2 批准。

### FD‑03 · ATR
- backend：唯一 canonical 实现；“pandas‑ta 系”只是候选，L2 必须固定具体 distribution/package、精确版本、函数/API、参数和代码身份；禁止手工 fallback 静默替代
- 输入：High/Low/Close（未完成 K 线已排除）
- 平滑建议：Wilder RMA（alpha = 1/n），n = 14；period、seed 与 first-valid row 均待 L2 明确批准
- 初始化 / warm‑up：不能只写“前 n−1 根无值”；必须写出 seed 数据区间、seed 方程、首个有效 timestamp 和 reset/invalidity 行为
- 失效：窗口内任一输入不可得 → 该点无值
- 派生：`atr_ma` / `atr_expanding` / `atr_ratio` / `atr_pct` 的窗口与除零规则显式定义

### FD‑04 · RSI
- backend：单一 canonical 实现；包、版本、具体 API/参数待 L2 冻结，不得静默切换 fallback
- 平滑建议：Wilder RMA（alpha = 1/n），n = 14；period、初始化 seed 与 first-valid row 待 L2 决定
- 零分母行为：`avg_loss == 0 → RSI = 100`；`avg_gain == avg_loss == 0`（完全静止）→ **提案 50**（连续、不引入额外 NaN）
- warm‑up：前 n 根无值
- `rsi_slope`：与决策矩阵对齐，候选名 `rsi_slope_45m`，公式 `RSI[t] - RSI[t-3]`（M15 下为三根间隔 / 45 分钟差分），需要 4 个有效 RSI 值；不得写成一阶差分。该重命名/公式仍待 L2 批准。

### FD‑05 · MACD
- 建议递归：EMA alpha=`2/(n+1)`，等价 `adjust=False` 递推；L2 必须批准精确递推定义
- 初始化：若选择首个输入值作 EMA seed，须明确 fast/slow 两条 EMA 的 seed index、signal EMA 的首个输入 index 和首个有效输出 index
- 周期候选：12 / 26 / 9，全部待 L2 批准
- 输出三列：候选名 `macd` / `macd_signal` / `macd_hist`，其中 `hist=macd-signal`；三列必须同批生成、同一有效区间，缺任一列即失败
- 有效区间、非有限输入处理、backend/package/version 或稳定代码身份必须显式冻结；不允许静默缺列

### FD‑06 · ADX（Wilder；period 候选 n = 14，待 L2 批准）
完整 break/reseed 规则写入 FD‑06，不留讨论记录：

1. 无效 K 线：按输入契约**拒绝**。
2. 有效 K 线但 DI/DX 分母为零：**中断 ADX 链**（该点 DX 无效）。
3. **保留** Wilder TR/DM 平滑状态（不重置）。
4. 累积新的**连续有效** DX。
5. 达到 n 个有效 DX 后**重新 seed**。
6. **不沿用**中断前的 ADX 状态。
7. 首次 seed 位置：index = 2n−1（仅当 L2 批准 n=14 时为 index 27）。

---

## 7. Legacy 结束与证据保全 — 对应 P0-2

**放弃 legacy recovery ≠ Stage C 自动解除或完成。** 若 §11 分歧点 2 批准停止旧 artifact recovery，则只对新治理记录追加 owner scope decision；不得回写下列既有历史记录：

| 项目 | 应有处理 |
|---|---|
| 历史 Stage A / B | 原记录保持 `ACCEPTED`；只描述原授权范围与时间点 |
| Stage C | 历史状态保持 `PARTIAL / BLOCKED`（原记录具体 blocker 原样保留）；不能改称 `ACCEPTED` 或“已完成” |
| Artifact Evidence Recovery | 历史状态保持 `UNSUCCESSFUL / CLOSED — EVIDENCE NOT RECOVERED`；停止继续追踪只关闭该 recovery work item，不表示证据取得 |
| Owner scope decision | 新增 `CLOSED BY OWNER SCOPE DECISION / NOT APPLICABLE TO NEW CONTRACT`，只针对是否继续追旧 artifact recovery |
| 新契约/新模型 | 独立建立；不得引用旧 artifact 作为兼容证明，不得将旧、新契约或 feature schema 混用 |

规则：
- 旧 `PHASE3_2_FEATURE_CONTRACT.md`、Strict Spec、Stage A/B/C 报告、Artifact Evidence Recovery 和 implementation report 保留原文/原日期/原 SHA（若已记录）；不追溯替换或改写。
- 禁止把“未取得 artifact”描述为“Stage C 已完成”，或把 Stage C 历史状态当成新契约的验证证据。
- 若 owner 选择继续 recovery，当前已关闭的 bounded recovery 不自动重开；须另批新的范围和授权。
- Legacy 决策不会自动变更或删除模型、scaler、manifest 或 runtime 行为。

---

## 8. Train / Inference Parity 分层 — 对应 P0-6

| 层级 | 验证内容 | 状态 |
|---|---|---|
| P1 | 原始 OHLCV 输入一致性 | 必须 |
| P2 | Feature Engineering 输出一致性 | 必须 |
| P3 | Scaler 输入/输出一致性 | 当前 `NOT VERIFIED / NOT RUN`（active bundle 不可用） |
| P4 | 模型输入张量一致性 | 当前 `NOT VERIFIED / NOT RUN`（active bundle 不可用） |
| P5 | 模型预测输出一致性 | 当前 `NOT VERIFIED / NOT RUN`（active bundle/host capability 不足） |

规则：
- P1 与 P2 是技术候选冻结的**硬性验收**；必须分别报告原始输入验证 parity 与原始 feature 输出 parity，不能以一项代替另一项。
- P3–P5 不得标成 pass、waived 或 `NOT REQUIRED`。当前没有可验证 active model/scaler bundle；XGBoost `libomp.dylib` 问题是当前 host 能力限制，不是理论架构限制。
- 记录 **`FULL_PARITY_STATUS = NOT VERIFIED`**。P3–P5 未验证时，不得宣称 full train/inference/model parity、Phase 3.2 end-to-end parity 或 activation-ready；任何新 scope 改变须另行 owner 决策。
- 若 L2 选择只冻结 feature-level contract，必须明示该边界：P1/P2 已通过、P3–P5 仍为未验证的后续兼容/激活 blocker；不能降低 P1/P2 的验收门槛。

---

## 9. 离线实验设计与验收标准 — 对应 P0-5

本节是 **Doc03 的待批准 protocol 设计输入**，不是实验授权。所有技术值/实验口径在 L2-A 的 Doc03 决定记录中逐项批准后，才可运行。

### 9.1 固定 fixture、历史序列与比较对象

至少 preregister 独立的**有效、连续、固定 M15** OHLC fixtures：单调上涨、单调下跌、变动区间/波动、交替方向；另设 `有效 directional → 有效平盘/零 DX 分母 → 再次有效 directional` 连续 fixture 验证 ADX 数学中断与 reseed。单一全平盘 fixture 可验证零分母行为，但本身不能证明恢复。拒绝类 candle（重复/乱序/invalid OHLC/unexplained gap）用于整批拒绝测试，不进入收敛值计算。所有有效 fixtures 必须有固定最终 candle、确定 OHLC 生成规则、唯一 fixture identity/hash；不得在看结果后替换 fixture。

**固定 history sequence：`200 → 300 → 500 → 800` bars。** 每个长度来自同一 fixture 的同一底层序列、以相同最终已完成 candle 结束；较短序列必须是较长序列的精确后缀。200 是诊断点；主收敛判定为 300v500 与 500v800。比较最新最终 candle 上的每项原始候选特征值。全共同区间的 timestamp-aligned 差异可以输出为诊断材料，**不代替也不改变最终向量验收**。

| 长度 | 角色 |
|---|---|
| 200 | **诊断基准**（表征 warm‑up 敏感性）；**不参与验收** |
| 300 | 验收对成员 |
| 500 | 验收对成员 |
| 800 | 验收对成员 |

### 9.2 比较矩阵与 reference

| 比较对 | 作用 | 是否验收 |
|---|---|---|
| 200v300 | 诊断（"200 是否足够"） | 否 |
| **300v500** | 主验收对 1 | **是** |
| **500v800** | 主验收对 2 | **是** |
| 200v500 | 诊断（全距趋势） | 否 |
| 200v800 | 诊断（全距趋势） | 否 |

对每个 pair，`A` 是较短历史结果、`B` 是较长历史结果，因此：200v300 的 reference=`300`；300v500 的 reference=`500`；500v800 的 reference=`800`。特征只有**同时**通过 300v500 与 500v800 才能标记 `CONVERGENCE PASSED ON PREREGISTERED FIXTURES/RANGE`。200v300 是诊断，不作为通过条件。

### 9.3 容差公式

统一写成：

```
|A − B| ≤ atol + rtol × |B|
```

其中 `atol = 1e-10`，`rtol = 1e-8`；`B` 始终是本 pair 中**较长 history 的值**。每个 feature、每个 fixture、每个主验收 pair 独立判定，不使用总体平均误差。相同输入的实现 correctness/parity 仍另行报告；它不能替代本收敛实验，反之亦然。

### 9.4 对齐、有效值和失败判定（需写入 Doc03）

- **主要对齐单位：**同一 fixture 的同一最终 candle timestamp；每个 run 输出该最终 candle 的 raw feature vector。
- **输入关系：**每个短 history 必须是对应长 history 的精确后缀；fixture、最终 candle、feature config、代码与 dependency/backend identity 固定。
- **候选集合：**仅对 L2 已批准且参与该实验的候选项作数值判定。仍为 `DEFER` 的特征不记作 PASS；L2 决定 `EXCLUDE` 的特征标记 `NOT APPLICABLE`，不得伪装为 PASS。
- **有效性先于数值：**预期在该长度有效的特征，若任一长度为 NaN/Inf/缺列/错误 dtype，则该 feature/pair FAIL 或 `NOT ESTABLISHED`，不得通过“NaN 等于 NaN”判 pass。若按已批准 warm‑up 规则该点确实尚未有效，记 `NOT APPLICABLE — WARM-UP`，且不能据此证明收敛或冻结该 feature。
- **数值判定：**仅两值均有限且按批准定义有效时，应用 §9.3 tolerance；记录 `A`、`B`、绝对差、容差和判定。
- **失败定位：**输出 fixture、feature、最终 timestamp、history pair、A、B、差值、reference、tolerance、有效性状态与失败原因。
- **共同区间行级比较：**可作额外诊断并按 timestamp 对齐，但不作为主收敛判据；不能将不同 initialization 历史造成的早期行差异混入最终状态，也不能用其通过替代固定最终 candle 检验。

### 9.5 特征类与各自的验收判据

> 历史长度稳定性测试**不是**简单数值比较，而是验证特征定义是否具备**预期的收敛性质**。不同特征必须有自己的验收标准。

| 类 | 特征 | 期望性质 | 验收 |
|---|---|---|---|
| **E 类**（纯精确定窗/逐行确定） | `return_*`、`log_return_*`、body/wick/range/direction、`dist_*`、`horizon_vol_*`、UTC time 数值 | 相同最终 candle 与相同完整依赖后缀应在 history 长度变化时保持不变 | 每个有效 fixture 的主验收 pair 都满足 §9.3 容差；任何不一致按 feature-specific 定义排查 |
| **R 类**（递归或依赖递归输入） | ATR 及其派生（包括 `atr_ecdf_50bar`）、RSI/`rsi_slope_45m`、MACD 三列、ADX | 初始化影响随历史长度变化；比较每 feature 的固定最终值 | 对每个有效 fixture 分别要求 300v500 与 500v800 通过 §9.3。记录三组 delta 趋势作诊断；单调下降**不作为额外通过条件**，除非 owner 在 L2-A 明确批准 |

规则：`atr_ecdf_50bar` 本身是有限 50-bar ECDF，但输入 ATR 是递归值，所以归为 R 类依赖特征，不能误列为纯 E 类。收敛 PASS 只说明该 feature 在**预注册 fixtures 和测试长度范围**内通过，不能外推为所有市场、instrument、backend、history length 的普遍稳定证明。Production history length 单独审批；非 200/300/500/800 时按 §4 的额外比较规则执行。

---

## 10. Volume 处置与 vol 缩放登记 — 对应附加项 1 & 2

### 10.1 Volume（EXCLUDE 是待审批建议）
- 对**新模型契约**，建议将 `vol_sma_ratio`、`vol_trend` 标记为 `EXCLUDE`，因为 source volume 语义/跨 instrument 可比性未确定。
- 这只是建议；L1 后仍为 `PENDING`，须由 L2 对 FD‑07 与 RC‑06/07/08 明确批准。批准前维持 `DEFER`，不按 EXCLUDE 改写 02/04/05，不因本计划跳过实验/兼容检查。
- 若批准 EXCLUDE，仅作用于新契约；**不代表**历史模型的输入定义已获验证，也不授权改动旧 artifact。
- Volume 的排除不得顺带改变其他特征的输入、值或顺序；若实现后获 L3 授权，须用同一 OHLC fixture 验证非 Volume 特征输出不变。

### 10.2 vol 缩放改变（须单独登记）

| | 公式 | 说明 |
|---|---|---|
| 旧 | `rolling(n).std(ddof=1) * sqrt(n*4)` | 当前源码语义（如 n=12 → `sqrt(48)`） |
| 新 | `rolling(n).std(ddof=1) * sqrt(n)` | 候选新契约公式（如 n=12 → `sqrt(12)`）；M15 名称候选 `horizon_vol_3h/6h/12h` 对应 n=12/24/48 |

规则：
- 明确新旧公式、`ddof=1`、window 与 timeframe mapping，并登记为**特征语义改变**，**不是** bugfix；由 L2 批准后方可作为新定义。
- 不声称旧模型兼容该新语义；实际旧模型 schema/compatibility 仍按 `UNVERIFIABLE` 等历史证据状态表述，不据此推测已部署 bundle 的具体输入。
- **禁止**旧模型通过修改 metadata 冒充兼容；本建议不授权改写旧 metadata。

---

## 11. 待 owner 拍板的分歧点

下表六项均为 L2 技术/范围决定；“我的推荐”仅供讨论。L1 流程批准不填充任何“你的决定”栏，也不使 Volume `EXCLUDE`、M15 或其他推荐值生效。

| # | 分歧点 | 我的推荐 | 你的决定 |
|---|---|---|---|
| 1 | 目标周期 | M15 | |
| 2 | 是否停止旧 artifact recovery 并转向独立新契约（不改写 Stage C 历史状态） | 停止旧 recovery work item；新契约单独建立；保留旧证据和状态 | |
| 3 | Volume 两特征 | `EXCLUDE`（§10） | |
| 4 | Session timezone/definition | IANA zone；pin tzdb source/version；明确 DST、session boundaries 和数据不可用时 fail closed；禁止退化为固定 UTC offset。Session 与 candle-availability Calendar 分开定义 | |
| 5 | Parity scope/disposition | P1/P2 为候选冻结硬门槛；P3–P5 不通过豁免降低，保持 `NOT VERIFIED`/blocker；`FULL_PARITY_STATUS = NOT VERIFIED` | |
| 6 | OANDA candle availability calendar | 先批准独立 OANDA-specific Calendar Contract，再由 IC/RC 引用其 ID/version 并判定 gap | |

以上不是全部逐 feature 决定的替代物；FD、RC 和 Doc03 的各项寄存表仍须分别批准。

---

## 12. 执行顺序

| 步骤 | 动作 | 产出 | 授权前提 |
|---|---|---|---|
| Step0 | **Revision Plan L1 批准**：仅接受流程/治理顺序；任何建议值仍 PENDING | 批准的流程版本 | Owner 明确记录 L1；不等同 L2 或 L3 |
| Step0.1 | **治理与 Calendar 草案**：只读仓库级引用扫描；确认 canonical dir；经批准后做安全指针治理；创建独立 Calendar Contract v0.1 草案并登记 OANDA source evidence；A3 仅在分歧点2 L2 决定后追加记录 | A1/A2 记录、引用清单、Calendar Contract DRAFT；不改 01–05 技术值 | L1 仅流程；具体路径/文件操作依 A2 审查；Calendar 值待 L2-A |
| Step1 | **Input Contract + Calendar**：逐项决定 IC‑01..08；独立批准 Calendar Contract；锁定时间戳开/收语义、completion signal、UTC 转换层、OANDA gap/calendar 数据来源 | 批准的 Doc01 + Calendar Contract ID/version | **L2-A**；前置 Step0.1；所有日历/IC 值明确签署 |
| Step2 | **Feature Definition**：逐项决定 FD‑01..09，公式/backend/warm-up/invalidity完整；FD‑02 锁定矩阵版本+SHA；建议值不自动生效 | 批准的 Doc02 决策记录/矩阵引用 | **L2-A**；前置 Step1；Volume/session unresolved 可以继续 DEFER |
| Step3 | **Experiment Authorization**：将固定 fixture、scope、code/dependency identity、alignment、tolerance/reference、验收和stop conditions逐条写入 Doc03 | 明确批准的 Doc03 protocol + execution authorization | **L2-A**；前置 Step1–2 和 Calendar Contract；无授权不得运行/查看结果 |
| Step4 | **Offline Experiments**：只运行 Doc03 已批准的离线/固定 fixture实验；不改生产代码/训练/artifact | 每 fixture、feature、pair 独立报告及 PASS/FAIL/NOT RUN/BLOCKED | Doc03 L2-A 批准已完成；任何扩项须先 protocol amendment approval |
| Step5 | **Runtime Configuration**：基于已接受实验决定 RC‑01..11；尤其审批 production history length。若 history length 不在已测序列，先批准额外比较 protocol，再执行并审阅 | 批准的 Doc04；history support evidence；必要的额外实验附录 | **L2-B**；前置 Step4；RC-01/03/04 必须与已批 IC 一致 |
| Step6 | **Candidate Freeze**：逐项登记 37 项最终技术资格、证据与 DEFER/EXCLUDE理由 | 经 owner 签署的 Doc05 freeze record | L2；前置 Step1–5；Doc05 production-length prerequisite和 P1/P2 parity 均通过；P3–P5不得虚报 |
| Step7 | **Phase 3.3 Handover**：仅交接技术合格候选，预测价值独立决定 | 交接包及认可记录 | L2/Phase3.3 owner接受；不冻结预测 schema、不签发身份、不授权实现 |

> **Step 8–9（Implementation / Integration）另行授权；不得因 Step 7 完成而自动获得授权。**

---

## 13. 边界（本文件不做的事）

- 不改任何 `.py` 文件、不改生产 FeatureEngine / 模型加载行为。
- 不训练模型、不写入或覆盖 model artifact、不改依赖或主机环境。
- 不部署、不接 `PredictionResult` READY、不改任何交易行为。
- L1 不使任何 B 层推荐取值生效。对应 L2 批准前，不将技术/运行值写成已批准值；Doc03 批准前不运行或查看新实验结果。
- 01–05 的决策内容只在对应 L2 项批准后更新。L1 后的 A1/A2 文档治理也不得改写任何决策内容或历史记录；具体副本重定向/指针改动须先完成引用扫描并获得 A2 对具体 diff 的接受。
- 不创建或批准 OANDA 交易日历时间值；L1 后只可起草独立 Calendar Contract 和记录来源证据，所有实际日历值须经 L2-A。

---

## 14. 修订记录

| 版本 | 日期 | 修改人 | 变更摘要 |
|---|---|---|---|
| 0.1 | 2026-11-15 | assistant | 初稿：现状快照、修改范围 A/B/C、6 个分歧点、执行顺序 |
| 0.2 | 2026-11-15 | assistant | 处理 P0‑1..P0‑7：三层授权分离、legacy 证据保全、会话保留 IANA tz+FAIL CLOSED、Calendar Contract、实验比较矩阵+容差+分类验收、parity 分层+FULL_PARITY_STATUS；新增 Volume EXCLUDE 与 vol 缩放登记；执行顺序加入 Step0.1；明确本版本不改 01–05 |
| 0.3 | 2026-11-15 | assistant | L2 拆为 L2-A/L2-B 并纳入 Doc03 授权；OANDA-specific 独立 Calendar Contract；legacy 历史不可变与引用审计；明确 timestamp/completion/UTC；FD-02 矩阵 SHA 锁定；统一 RSI slope 3-bar；限定 parity 和 convergence 结论；规范 Volume EXCLUDE 及 Step0–7 顺序 |
