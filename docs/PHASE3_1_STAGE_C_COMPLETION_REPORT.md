# Phase 3.1 — Stage C 完成报告（Consumer Transparency Migration）

**Version:** 1.1
**Date:** 2026-11-15
**Status:** 复核收尾（review closure）已在工作树落地，**尚未提交**、**尚未验收**。
首轮实现 = `c8bf4b9`；补充测试 + C-5 语义还原 = `a5e916f`。本版在 `a5e916f` 之上追加
**SC-02 路径 A（真绑定 production load）** 与 **C-4 显式 provenance** 两个收尾修复，
以及本文档的偏差记录。Stage C **暂不正式验收**，等待复核。
**Contract:** `docs/PHASE3_1_CONTRACT.md` v1.3（SHA-256 `49975ef4…de7b`）
**Spec:** `docs/PHASE3_1_STAGE_B_STRICT_SPEC.md` v3（Stage B 已验收）
**Task order:** `docs/PHASE3_1_STAGE_C_IMPLEMENTATION_TASK.md`（SC-01…SC-06）
**Authorization:** 用户批准 Stage C；裁定 `ml/prediction_adapter.py` 为**唯一权威**
`PredictionResult` 生产者，A.2 旧版退役（不删代码）；本次**仅改** `fx_trade_bot_v685.py`
（`fx_trade_bot.py` 为其拷贝，不动）。

---

## 0. 冻结边界（契约 §4.1）

> **ML state transparency is in scope; trading behaviour is frozen.**

本次交付**只增加透明化**，**未**改动 Step 7 打分、fallback 行为、票数、权重或
Entry Authorization。所有新增代码 **additive + fail-open**：异常一律吞掉并记日志，
不改变返回值/控制流。**未删任何代码**（退役 = 加 superseded 标注）。

---

## 1. 交付内容（SC-01…SC-06）

### SC-01 — 退役 A.2 seam（零风险）

| 文件 | 变更 |
| --- | --- |
| `ml/live_prediction_engine.py` | 文件头加 `[SUPERSEDED — DO NOT WIRE]` 横幅（L1-14），指向 `ml/prediction_adapter.py`；**正文一字未改** |
| `ml/integration_hook.py` | 文件头加 `[SUPERSEDED — DO NOT WIRE]` 横幅（L1-9）；`evaluate_prediction_guard()` / `guarded_live_polling_hook()` 逻辑原样保留 |

### SC-02 — production loader 身份（**路径 A：真绑定 production load**）

复核裁定：初版（`c8bf4b9`/`a5e916f`）的身份捕获发生在**生产加载完成之后**——它由
`load_model_with_identity()` 二次读取文件字节并**新建**实例，因此 `loaded_identity` 是
「第二次读取的文件字节身份」，**不是**实际接线模型的实例 provenance。这会留下一个
**A/B 文件替换窗口**：加载 A → 接线 → 磁盘被换成 B → 身份探针读 B → B 的 hash 在 CD
registry 命中 VERIFIED，消费者就可能把运行中的 A 误当作已验证的 B（证据错配）。

路径 A 修复：让 **同一份已读字节** 既用于构造**实际接线**的实例，又用于生成
`LoadedModelIdentity`——哈希与实际模型实例来自**同一次加载**。

| 位置 | 变更 |
| --- | --- |
| `fx_trade_bot_ml.py:185-191` | 新增 `_read_artifact_bytes(path)`：**单次**读取文件字节，返回 `(bytes, None)` 或 `(None, detail)`；异常吞掉 |
| `fx_trade_bot_ml.py:194-241` | 新增 `_bind_wired_identity(...)`：校验 `_loaded_from_bytes`（loader 确实用传入字节构造了接线实例）后，惰性导入 `bind_loaded_identity` 并绑定**预读字节 ↔ 接线实例**；双层 try/except，**fail-open**。`_loaded_from_bytes=False`（磁盘回落）时 **withhold** 身份并给出 `identity_detail` |
| `fx_trade_bot_ml.py:297-308` | hash 块改为**单次读**：`model_bytes/scaler_bytes` 同时用于 `sha256(...)` 与下方 `load(...)`（消除二次读窗口） |
| `fx_trade_bot_ml.py:338-344` | load 调用改为 `model_wrapper.load(model_bytes=..., scaler_bytes=...)`（字节可用时），否则维持原 `load()` 磁盘路径 |
| `fx_trade_bot_ml.py:399-423` | 接线之后，用**同一 bytes + `model_wrapper.model/.scaler`（即 `strat_engine` 已接线实例）** 生成身份；`[ML-IDENTITY]` 日志新增 `instance_provenance=%s` |
| `data_pipeline.py:634-670` | `ModelWrapper.load(model_bytes=None, scaler_bytes=None)`：xgb pickle 路径与默认磁盘路径**不变**；仅当卖家字节可用且库支持内存构造时，用 `bytearray(model_bytes)` 构建模型、`io.BytesIO(scaler_bytes)` 构建 scaler，并置 `_loaded_from_bytes=True` |
| `ml/prediction_adapter.py:351-390` | 新增 `bind_loaded_identity(*, model_bytes, scaler_bytes, model_instance, scaler_instance, clock, source_path=None, load_method="BYTES")`：**不 I/O、不构造**，仅把预读字节的 SHA-256 绑定到已接线实例。原 `load_model_with_identity()` 保留（未被生产 loader 调用） |

- 失败/不可用时字段保持 `None`，**不影响既有 load 结果与控制流**。
- 结果：`loaded_identity.model_instance` **就是** `strat_engine.model`（同一实例），
  `artifact_sha256` 覆盖的就是产出该运行实例的字节——**loaded-instance provenance**，
  非 post-load 文件身份。A/B 替换窗口被消除（见 `test_sc02_single_read_is_immune_to_a_later_file_swap`）。

### SC-03 — C-2 / C-3 透明化（`fx_trade_bot_v685.py`）

| 位置 | 变更 |
| --- | --- |
| `fx_trade_bot_v685.py:2601-2616` | C-2：Step 7 之后**追加** `[ML-STATE]` 日志，区分 `prediction=AVAILABLE`（`source=legacy Signal.model_p_up`）与 `prediction=NOT_AVAILABLE`（`scoring_input=SYNTHESIZED_NEUTRAL`），并标注 `legacy scoring behaviour` |
| `fx_trade_bot_v685.py:2762-2770` | C-3：`_open_reasons` 中合成值标 `(SYNTHETIC)`（`XGB_SCORE=0.00(SYNTHETIC)` vs `XGB_SCORE=0.42`） |

- **`prob_raw` 的取值与传入 `calc_weighted_score` 的路径逐字不变**（C-2 冻结）。
- `xgb_score` 语义不变（缺失时仍为 `0.0`）；`_open_reasons` 仅用于日志/Telegram 富文本。

### SC-04 — C-1 透明化（`fx_trade_bot_v685.py:2175-2184`）

- CONFLUENCE 之后追加 `[ML-STATE] CONFLUENCE` 日志：明示票数来自
  legacy Decision 层 `signal.action`、**非**已验证 PredictionResult，
  `ml_votes_invented=0`；**未新增票、未改票数**。

### SC-05 — C-4 / C-5 attribution（`attribution_v2/`）

**C-4（复核后：显式 provenance，取代「非空 ⇒ READY」代理）**

复核裁定：初版把 `sig.model_p_up is not None` 当作 READY 等价条件，**误称**——
legacy `Signal`（契约 §4.1.1.6 C-2 known exception）根本**不是** PredictionResult 消费者，
字段非空并不等于「已由 READY PredictionResult 确认」。

| 位置 | 变更 |
| --- | --- |
| `strategy_decision.py:74-75,93-95,277` | 新增常量 `MODEL_P_UP_SOURCE_READY="MODEL_READY"` / `MODEL_P_UP_SOURCE_UNSET="UNSET"`；`Signal` 新增字段 `model_p_up_source: str = MODEL_P_UP_SOURCE_UNSET`；**唯一生产者** `generate_signal` 显式置 `MODEL_P_UP_SOURCE_READY` |
| `attribution_v2/live_hook.py:140,143-173` | `derive_xgb_p_up` 要求 `getattr(sig,"model_p_up_source",None) == "MODEL_READY"` 方消费；无值 / 未标记 legacy Signal / 非 READY 来源 → `None`（下游记 `degraded`）。观测层**刻意不导入交易模块**，故本地镜像该标记，任何不一致 fail-SAFE |

- 同时保留 C-4 的原有禁令：**移除** `w["X"]/100` 与 `raw_prob` **合成**路径。
- 证据：新增 `test_c4_value_without_ready_provenance_is_rejected`（值存在但未标记 → None）
  与 `test_c4_unmarked_value_propagates_to_degraded_profile_record`（未标记值端到端 degraded）。

**C-5（复核：通过）**

| 位置 | 变更 |
| --- | --- |
| `attribution_v2/data_bridge.py:211-257` | 新增 `_pick_prob()`（返回 `(value, source_key)`，优先级与旧内联链**逐字一致**）与 `_prob_clip_with_unit()`（返回 `(value, unit)`）；`_prob_clip()` 行为不变，改为复用 |
| `attribution_v2/data_bridge.py:102-125` | `from_bot_candidate` 记录 `self.last_prob_provenance`（来源字段 + 检测单位）并落 INFO 日志——**消除静默单位重解释** |
| `attribution_v2/live_hook.py:265-267` | 观测记录 `source.prob_provenance` 持久化该来源/单位 |

- `_pick_prob` 使用 `if key in bot_candidate: return ...`，**保留**旧 `.get(key, default)`
  链的 present-key-wins 语义（含主键存在但值为 `None` 的边界），由
  `test_c5_*` 锁定。复核结论：**通过**。

- `attribution_v2` 为**纯观测层**（不提交订单、不阻断候选、fail-open），且当前**未被 v685 接线**
  （`fx_trade_bot_v685.py` 无 `attribution_v2` / `AttributionObserver` 引用），故 C-4/C-5 不触及交易行为。

### SC-06 — 验证与报告
本文件即 SC-06 产物；证据见 §3。

---

## 2. 变更文件清单

**已提交（`c8bf4b9` + `a5e916f`，range `c8bf4b9~1..HEAD`）：**

```
 attribution_v2/data_bridge.py                     |  93 +++++++++---
 attribution_v2/live_hook.py                       |  49 +++---
 attribution_v2/tests/test_stage_c_transparency.py | 173 ++++++++++++++++++++++
 docs/PHASE3_1_STAGE_C_COMPLETION_REPORT.md        | 172 +++++++++++++++++++++
 docs/PHASE3_1_STAGE_C_IMPLEMENTATION_TASK.md      | 106 +++++++++++++
 fx_trade_bot_ml.py                                |  53 ++++++-
 fx_trade_bot_v685.py                              |  37 ++++-
 ml/integration_hook.py                            |   9 ++
 ml/live_prediction_engine.py                      |  14 ++
 tests/test_phase3_runtime_containment.py          | 136 +++++++++++++++++
 10 files changed, 790 insertions(+), 52 deletions(-)
```

**工作树中未提交（复核收尾，`git diff --stat` vs HEAD；含本报告自身的改动）：**

```
 attribution_v2/live_hook.py                       |  33 ++--
 attribution_v2/tests/test_stage_c_transparency.py |  69 ++++++--
 data_pipeline.py                                  |  26 ++-
 docs/PHASE3_1_STAGE_C_COMPLETION_REPORT.md        | 185 +++++++++++++++-------
 fx_trade_bot_ml.py                                | 112 +++++++++----
 ml/prediction_adapter.py                          |  43 +++++
 strategy_decision.py                              |  16 ++
 tests/test_phase3_runtime_containment.py          | 146 ++++++++++-------
 tests/test_prediction_adapter.py                  | 105 ++++++++++++
 9 files changed, 571 insertions(+), 164 deletions(-)
```

---

## 3. 验证证据

| # | 命令 | 结果 |
| --- | --- | --- |
| V1 | `python -m py_compile`（全部被改文件 + 新增测试） | **COMPILE_OK** |
| V2 | `pytest tests/test_prediction_adapter.py tests/test_phase3_runtime_containment.py -q` | **157 passed**（适配器 112 + 运行时遏制 45） |
| V3 | `pytest tests -q`（cwd=`attribution_v2`） | **83 passed** |
| V4 | C-4/C-5 行为烟测 | `_prob_clip_with_unit(70)=(0.7,'0-100')`、`(0.4)=(0.4,'0-1')`、`(None)=(None,'none')`；`_prob_clip(70)=0.7`（行为不变）；`_pick_prob` 正确解析来源；`derive_xgb_p_up`：READY-marker→`0.42`、有值但**未标记**→`None`、非 READY→`None`、`sig=None`→`None` |
| V5 | 预存在失败隔离 | `git stash` 我的改动后重跑同一命令，结果**逐字相同**，证明**无新增失败** |
| V6 | `git diff` 全量审阅 | 仅日志 / 标签 / 新字段 / 辅助函数 / 单次读重构；无 Step 7 打分 / 票数 / 权重 / Entry Authorization 逻辑变更 |
| V7 | **SC-02 路径 A 自动化测试**（`tests/test_phase3_runtime_containment.py`） | 成功路径：`ident.model_instance is strategy.model is wrapper.model`、`wrapper.loaded_model_bytes == 磁盘字节`、`ident.artifact_sha256 == sha256(磁盘字节)`、`load_method=="BYTES"`、`result.model_hash==ident.artifact_sha256`；**单次读免疫**（读后立即替换磁盘文件，身份仍绑定旧字节）；**withhold**（loader 未消费字节 → `loaded_identity is None` 且 detail 含 `no instance provenance`）；适配器异常 / 模块不可导入 fail-open；字段 additive 且不进 `as_log_fields()` |
| V8 | **C-4 / C-5 自动化测试**（`attribution_v2/tests/test_stage_c_transparency.py`，34） | C-4：READY-marker 用 `model_p_up`、钳位、非 READY 绝不从 `X`/`raw_prob` 合成、`None`/不可解析→`None`、**有值但未标记→`None`（显式 provenance 拒绝）**、`None`/未标记值经 `process_candidate` 落到 `decision.degraded=True` 且 `missing_factors` 含 `xgb`（端到端）。C-5：`_prob_clip` 行为逐值不变、单位标签、来源优先级、**present-but-None 语义**、`last_prob_provenance` 来源+单位 |
| V9 | **`bind_loaded_identity` 专属测试**（`tests/test_prediction_adapter.py`，+10） | hash 覆盖**预读字节**、`model_instance/scaler_instance` 为**同一对象**（`is`）、clock 时间戳、`source_path` 归一为 `str`、`load_method` 透传、`bytearray` 接受、非 bytes → `PredictionAdapterContractError`、缺 clock → `PredictionAdapterContractError`、**无 I/O**（`builtins.open` 被禁用仍成功） |

**关于全套收集错误（非本次引入）：**
`python -m pytest tests` 在全仓库范围内有**预存在**的收集错误——
`tests/test_fx_trade_bot_data.py` 顶层 `from fx_trade_bot import ...`，而 `fx_trade_bot.py`
在 import 时执行 `parser.parse_args()` → `SystemExit(2)`；另有若干依赖缺失配置/凭据的模块。
`git stash` 基线复跑结果与本次**完全一致**，确认与 Stage C 改动无关。
故回归以**与改动相关的定向套件**（V2/V3）为准。

---

## 4. 验收矩阵（任务单 §4）

| ID | 标准 | 结果 |
| --- | --- | --- |
| SC-A1 | 被改文件 `py_compile` 通过 | ✅ V1 |
| SC-A2 | 相关 pytest 套件无新增失败 | ✅ V2/V3/V5/V7/V8/V9 |
| SC-A3 | `git diff` 无 Step 7 打分 / 票数 / 权重 / Entry Authorization 逻辑变更 | ✅ V6 |
| SC-A4 | 新增代码异常时 fail-open，返回值不变 | ✅ SC-02 双层 try/except + withhold；SC-05 默认/降级语义；v685 仅日志 |
| SC-A5 | A.2 seam 有 superseded 标注且未被删除 | ✅ SC-01（正文未删一字） |

**复核项结论（对应用户复核意见）：**

| 项目 | 结论 |
| --- | --- |
| SC-01 | 暂时认可 |
| SC-02 | **路径 A 已实现**（真绑定 production load；含单次读免疫测试 + `bind_loaded_identity` 专属测试）；待复核 |
| SC-03 / SC-04 | 暂时认可（未改） |
| C-4 | **显式 provenance 已实现**（`Signal.model_p_up_source` + `derive_xgb_p_up` 校验）；待复核 |
| C-5 | **通过** |

---

## 5. 明确未做（超出 Stage C，需另批）

- 未接线 ML Vote；未改 Step 7 打分 / 权重；未改 Entry Authorization。
- 未移除 legacy fallback 的交易影响（§4.1.1.4，需另开 Phase 3.6 门槛）。
- 未把 `READY` 接到任何执行路径。
- 未动 `fx_trade_bot.py`（拷贝件）。
- **未部署、未重训。**
- **未提交本轮复核收尾改动**（保留在工作树，等待复核后再决定）。

---

## 6. 残余说明（供审阅关注）

1. **`bind_loaded_identity` 的无 I/O 前提**：它信任调用方已把**同一份字节**交给
   `model_wrapper.load(...)`。这一前提由 `fx_trade_bot_ml.py` 的**单次读**重构 +
   `_loaded_from_bytes` guard 保证；若 loader 回落磁盘（`_loaded_from_bytes=False`），
   身份被 **withhold**（`loaded_identity=None` + detail），不透支未背书的 provenance。
2. **SC-02 身份现为「实例 provenance」**：`loaded_identity.model_instance` **就是**
   `strat_engine.model`（同一对象），哈希覆盖产出该运行实例的字节。初版残余「新建实例 ≠
   接线实例」问题已消除。
3. **C-4 provenance 是显式标记而非推断**：`derive_xgb_p_up` 现在要求 `model_p_up_source
   == "MODEL_READY"`。该标记的**唯一生产者**是 `StrategyEngine.generate_signal`；观测层
   本地镜像该字符串（不导入交易模块），任何漂移 fail-SAFE。若存在其他能看到 `Signal` 的
   构造/序列化路径而绕过 `generate_signal`，其 `model_p_up` 将被判为未标记 → degraded。
4. **C-5 已还原为严格行为一致**：复核发现初版 `_pick_prob` 用 `is not None` 判断，
   在「主键存在但值为 `None`」时会继续尝试别名，而旧内联链 `.get(key, default)` 会
   停在 `None`。已改为 `if key in bot_candidate`，语义**逐字一致**。

---

## 7. Git 流程偏差（如实记录）

任务单 §0 明确写着「**本次不 commit、不部署、不重训**」。实际出现了两次提交：

- `c8bf4b9` — `phase31 stage C implementation`（首轮实现）
- `a5e916f` — `phase31 stage C implementation 2`（补充测试 + C-5 修正）

这属于**明确的授权边界偏差**。它不意味着应撤销代码，也不意味着代码质量因此变差，但需在此
如实记录。当前分支 `v2026c`；`git status` 显示 9 个文件为工作树**未提交**改动（见 §2）。
本轮复核收尾**严格遵守**「不再提交新 commit」——所有修复保留在工作树。

---

## 8. 状态

- 首轮实现 + 初版报告 = `c8bf4b9`；补充测试 + C-5 还原 = `a5e916f`（**均在工作树之外**）。
- 本轮复核收尾（SC-02 路径 A、C-4 显式 provenance、`bind_loaded_identity` 测试、本文档）
  在**工作树中，尚未提交**。
- **Stage C 暂不正式验收。** 待用户/ChatGPT 复核 SC-02 路径 A 与 C-4 provenance 证据后，
  再决定提交、部署、重训与正式关闭。
