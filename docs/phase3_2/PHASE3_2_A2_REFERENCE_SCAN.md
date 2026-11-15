# Phase 3.2 — A2 引用扫描记录与副本治理方案

**版本:** 0.1  
**日期:** 2026-11-15  
**状态:** 扫描完成 — 指针/重定向方案**待 owner 逐项接受**（本记录未执行任何删除或覆盖）  
**依据:** `PHASE3_2_REVISION_PLAN.md` §4.1 A2、§2、§12 Step0.1  
**授权边界:** 本文件仅为只读扫描与方案。按 A2 规则，未完成扫描与 owner 对具体 diff 的批准前，**不删除、不覆盖任何副本**。

---

## 1. 方法（只读）

| 项 | 内容 |
|---|---|
| 扫描范围 | 全仓库（含 `docs/`、`docs/phase3_2/`、`ml/`、`experiments/`、`tests/`、脚本、配置、归档） |
| 文件名模式 | `01_INPUT_CONTRACT_OWNER_DECISION`、`02_FEATURE_TECHNICAL_DEFINITIONS_AND_ELIGIBILITY`、`03_EXPERIMENT_AUTHORIZATION_AND_ACCEPTANCE`、`04_RUNTIME_CONFIGURATION_DECISIONS`、`05_TECHNICALLY_ELIGIBLE_CANDIDATE_FREEZE` |
| 路径模式 | `docs/phase3_2`、`docs/0[1-5]_` |
| 来源模式 | `owner_decision_pack` / `phase3_2_owner` |
| 快照 | 分支 `v2026c`，HEAD `bd7a7752`，`git status --porcelain` 干净（2026-11-15 扫描时） |
| 方法限制 | 二进制归档 `phase3_2_owner_decision_pack.zip` 仅记录其清单与哈希，未逐条解压比对；无 CI/Makefile 参与路径解析 |

---

## 2. 副本盘点（5 对）

同名副本位于 `docs/`（根）与 `docs/phase3_2/`（建议 canonical）。`sha256` 取前 16 位。

| 文件 | `docs/`（根） | `docs/phase3_2/` | 现状 |
|---|---|---|---|
| `01_INPUT_CONTRACT_OWNER_DECISION.md` | `d95138f634e4cc15` | `101348e8a449cef2` | **DIFF** |
| `02_FEATURE_TECHNICAL_DEFINITIONS_AND_ELIGIBILITY.md` | `d582973683c9c903` | `ad923eb98e24a6a8` | **DIFF** |
| `03_EXPERIMENT_AUTHORIZATION_AND_ACCEPTANCE.md` | `98dde94b0f370d07` | `0653188d500dbe5b` | **DIFF** |
| `04_RUNTIME_CONFIGURATION_DECISIONS.md` | `c9e5586d58bce40a` | `2b042408e41f3717` | **DIFF** |
| `05_TECHNICALLY_ELIGIBLE_CANDIDATE_FREEZE.md` | `32dc3381a3fc81cf` | `63c5d99cbfdbdf29` | **DIFF** |

- 计划书 §2 曾以 `cmp` 确认五对**逐字节相同**（L2 决定记录之前）。
- 2026-11-15 将 L2 已批准值写入 `docs/phase3_2/` 后，canonical 侧被更新，故当前五对**全部 DIFF**；根副本仍停留在记录前的版本。
- 来源：`PHASE3_2_DEV_TASK_PLAN.md:156` 记载决策包由仓库根归档 `phase3_2_owner_decision_pack.zip`（`sha256` 前 16 = `09d88b6794f63064`，内含正好这 5 个文件）解压到 `docs/phase3_2/`。

**根副本删除记录（2026-11-15，方案 A 执行）：** owner 接受方案 A 后，`docs/` 根目录 5 个副本已删除。删除前完整 `sha256`：

| 文件（原 `docs/` 根） | 删除前 sha256 |
|---|---|
| `01_INPUT_CONTRACT_OWNER_DECISION.md` | `d95138f634e4cc156bfbebbd67cf5bcdd43021fc5381fe9c220883ee7db92bf8` |
| `02_FEATURE_TECHNICAL_DEFINITIONS_AND_ELIGIBILITY.md` | `d582973683c9c9036dc3be4af4366b4bf99eb1158d077b0d2751830c452b00d3` |
| `03_EXPERIMENT_AUTHORIZATION_AND_ACCEPTANCE.md` | `98dde94b0f370d0707e41e7331a82d84a30bb4f73357bf229c8f5850eeb7afdd` |
| `04_RUNTIME_CONFIGURATION_DECISIONS.md` | `c9e5586d58bce40ac317ebf2d46ec39161f0e8b5c3f8a609ebf7ffbe568176c2` |
| `05_TECHNICALLY_ELIGIBLE_CANDIDATE_FREEZE.md` | `32dc3381a3fc81cf2429e6c6521c70654cc1ab52c8b5640877bd40372a09631f` |

恢复来源：git 历史（末次含这些文件的提交 `334cc00`，2026-11-15）与归档 `phase3_2_owner_decision_pack.zip`。删除为 A2 已批准的最小动作，未改写任何 canonical 内容。

---

## 3. 引用清单（全仓库，全部文件类型；共 8 处匹配）

| # | 引用位置 | 行 | 引用形式 | 解析目标 | 判定 |
|---|---|---|---|---|---|
| 1 | `docs/phase3_2/PHASE3_2_DEV_TASK_PLAN.md` | 14–18 | 相对链接 `[01_…](01_…md)` … `[05_…](05_…md)` | 相对自身目录 → `docs/phase3_2/…` | canonical ✔ |
| 2 | `docs/phase3_2/PHASE3_2_REVISION_PLAN.md` | 25 | 相对链接（01–05 共 5 条） | 相对自身目录 → `docs/phase3_2/…` | canonical ✔ |
| 3 | `ml/feature_contract.py` | 6 | 注释 `docs/phase3_2/02_FEATURE_…md` | canonical（显式路径） | canonical ✔ |
| 4 | `experiments/phase3_2_feature_convergence/proposed_contract.py` | 5 | 注释 `docs/phase3_2/02_FEATURE_…md` | canonical（显式路径） | canonical ✔ |

**结论：没有任何引用指向根目录副本。** 全部引用要么是 `docs/phase3_2/` 内的相对链接，要么是显式写 `docs/phase3_2/` 的注释。因此把 canonical 定为 `docs/phase3_2/` 与现有引用**零冲突**。

---

## 4. 反向发现（无依赖）

| 项 | 结果 |
|---|---|
| 以路径读写这 5 个文档的 `.py` / `.json` / `.sh` / CI / Makefile | 无 |
| 引用这 5 个文档的测试 | 无（`tests/` 无相关引用） |
| `docs/` 根目录其余文档与 `docs/phase3_2/` 的同名重复 | 无 —— 重复**仅限** 01–05 这 5 对 |
| `PHASE3_2_TECHNICAL_FEATURE_DECISION_MATRIX_v0.1.md` 等支撑文档 | 仅存在于 `docs/phase3_2/`，无副本 |
| 归档 `phase3_2_owner_decision_pack.zip` | 仍存在于仓库根；是原始来源，非活跃引用 |

---

## 5. 风险

| 风险 | 说明 |
|---|---|
| 双份分叉被误用 | 根副本停留在 L2 记录前状态；若有人按根副本行事，会读到未更新的决策字段 |
| 归档溯源 | `phase3_2_owner_decision_pack.zip` 与 `docs/phase3_2/` 已不再一致（后者含 L2 决定记录）；归档应作为**历史来源**保留，不得当作 current |
| 治理动作本身的风险 | 删除/覆盖前若未确认引用，可能破坏相对链接解析；本扫描已确认无根路径引用，风险低 |

---

## 6. 建议的副本治理方案（待接受，均未执行）

| 方案 | 具体 diff | 优点 | 缺点 |
|---|---|---|---|
| **A（推荐）** 删除根目录 5 个副本 | 删除 `docs/01_…md` … `docs/05_…md`；canonical 保留在 `docs/phase3_2/` | 单一权威源；现有引用零改动 | 根目录不再有入口；依赖归档保留历史 |
| **B** 根目录 5 个副本替换为指针桩 | 将 `docs/01_…md` … 内容替换为 3–5 行说明（“已移至 `docs/phase3_2/`，本文件非权威”） | 保留发现路径 + 明确非权威 | 根目录仍有 5 个文件；需维护桩 |
| **C** 保留双份，仅在根副本头部加 canonical 声明 | 在根副本首行插入“本文件非权威，canonical 见 `docs/phase3_2/`” | 改动最小 | 双份继续分叉，权威性弱 |

附加建议（不属 A2）：`docs/phase3_2/PHASE3_2_REVISION_PLAN.md` §2 的“副本逐字节相同”陈述已过期，应在 A2 接受后按选定方案追加一条**新的**状态记录（不追溯改写旧记录）。

---

## 7. 接受记录

| 项 | 决定 | 接受人 | 日期 |
|---|---|---|---|
| A2 引用扫描结论（canonical = `docs/phase3_2/`） | ACCEPTED | owner | 2026-11-15 |
| A2 副本治理方案（A / B / C） | ACCEPTED — 方案 A（删除根目录 5 副本） | owner | 2026-11-15 |
| 是否允许对根副本执行删除/改写 | ACCEPTED — 允许删除，已执行 | owner | 2026-11-15 |
| 计划书 §2 过期陈述处理 | ACCEPTED — 追加新状态记录，不改旧文 | owner | 2026-11-15 |

**执行结果（2026-11-15）：** 方案 A 已执行（根目录 `docs/01–05` 五副本删除）；计划书 §2 已按「仅追加」方式新增 A2 更新记录。

> 上述决定已由 owner 逐项接受。canonical 目录自此唯一化为 `docs/phase3_2/`。
