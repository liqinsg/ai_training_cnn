# Phase 3.1 — Stage C 完成报告（Consumer Transparency Migration）

**Version:** 1.0
**Date:** 2026-11-15
**Status:** Implementation complete — **NOT committed, NOT deployed** (awaiting review)
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

### SC-02 — production loader 身份（additive，独立增量）

| 位置 | 变更 |
| --- | --- |
| `fx_trade_bot_ml.py:105-114` | `ModelInitResult` **新增**可选字段 `loaded_identity: Optional[Any] = None`、`identity_detail: Optional[str] = None`（默认 None；不进 `as_log_fields()`、不影响 `status`/`reason`/`ok`） |
| `fx_trade_bot_ml.py:183-205` | 新增 `_capture_loaded_identity(paths)`：**惰性**导入 `ml.prediction_adapter` → `load_model_with_identity(...)`，双层 try/except，**fail-open**，返回 `(identity, None)` 或 `(None, detail)` |
| `fx_trade_bot_ml.py:352-365` | READY 分支**接线之后**追加：尽力填充身份 + 一条 `[ML-IDENTITY]` INFO 日志 |

- 失败/不可用时字段保持 `None`，**不影响既有 load 结果与控制流**。
- 模块头「仅 stdlib+pandas」的意图得以保留（重模块为惰性导入）。
- 目的：使 Stage C 消费者可在生产侧拿到**单次读字节绑定**的 artifact/scaler 身份（spec §3.4）。

### SC-03 — C-2 / C-3 透明化（`fx_trade_bot_v685.py`）

| 位置 | 变更 |
| --- | --- |
| `fx_trade_bot_v685.py:2601-2616` | C-2：Step 7 之后**追加** `[ML-STATE]` 日志，区分 `prediction=AVAILABLE`（`source=legacy Signal.model_p_up`）与 `prediction=NOT_AVAILABLE`（`scoring_input=SYNTHESIZED_NEUTRAL`），并标注 `legacy scoring behaviour` |
| `fx_trade_bot_v685.py:2762-2770` | C-3：`_open_reasons` 中合成值标 `(SYNTHETIC)`（`XGB_SCORE=0.00(SYNTHETIC)` vs `XGB_SCORE=0.42`） |

- **`prob_raw` 的取值与传入 `calc_weighted_score` 的路径逐字不变**（C-2 冻结）。
- `xgb_score` 语义不变（缺失时仍为 `0.0`）；`_open_reasons` 仅用于日志/Telegram 富文本（`:2838/:2881`）。

### SC-04 — C-1 透明化（`fx_trade_bot_v685.py:2175-2184`）

- CONFLUENCE 之后追加 `[ML-STATE] CONFLUENCE` 日志：明示票数来自
  legacy Decision 层 `signal.action`、**非**已验证 PredictionResult，
  `ml_votes_invented=0`；**未新增票、未改票数**。

### SC-05 — C-4 / C-5 attribution（`attribution_v2/`）

| 位置 | 变更 |
| --- | --- |
| `attribution_v2/live_hook.py:137-160` | C-4：`derive_xgb_p_up` 重写为**仅在 READY 等价态**（`sig.model_p_up` 非 None）消费解释后的 P(up)；否则返回 `None`（下游记 `degraded`）。**移除** `w["X"]/100` 与 `raw_prob` **合成**路径 |
| `attribution_v2/data_bridge.py:211-257` | C-5：新增 `_pick_prob()`（返回 `(value, source_key)`，优先级与旧内联链**逐字一致**）与 `_prob_clip_with_unit()`（返回 `(value, unit)`）；`_prob_clip()` 行为不变，改为复用 |
| `attribution_v2/data_bridge.py:102-125` | `from_bot_candidate` 记录 `self.last_prob_provenance`（来源字段 + 检测单位）并落 INFO 日志——**消除静默单位重解释** |
| `attribution_v2/live_hook.py:265-267` | 观测记录 `source.prob_provenance` 持久化该来源/单位 |

- `attribution_v2` 为**纯观测层**（不提交订单、不阻断候选、fail-open），且当前**未被 v685 接线**
  （`fx_trade_bot_v685.py` 无 `attribution_v2` / `AttributionObserver` 引用），故 C-4/C-5 不触及交易行为。

### SC-06 — 验证与报告
本文件即 SC-06 产物；证据见 §3。

---

## 2. 变更文件清单

```
 attribution_v2/data_bridge.py | 91 +++++++++++++++++++++++++++-----------
 attribution_v2/live_hook.py   | 49 +++++++++++------------
 fx_trade_bot_ml.py            | 53 +++++++++++++++++++++++-
 fx_trade_bot_v685.py          | 37 +++++++++++++++++-
 ml/integration_hook.py        |  9 +++++
 ml/live_prediction_engine.py  | 14 +++++++
 6 files changed, 201 insertions(+), 52 deletions(-)
```

新文件（未跟踪）：`docs/PHASE3_1_STAGE_C_IMPLEMENTATION_TASK.md`（任务单）、本报告。

---

## 3. 验证证据

| # | 命令 | 结果 |
| --- | --- | --- |
| V1 | `python -m py_compile`（全部 6 个被改文件） | **COMPILE_OK** |
| V2 | `pytest tests/test_prediction_adapter.py tests/test_phase3_runtime_containment.py -q` | **140 passed**（Stage B 适配器 102 + 运行时遏制 38） |
| V3 | `pytest tests -q`（cwd=`attribution_v2`） | **49 passed** |
| V4 | C-4/C-5 行为烟测 | `_prob_clip_with_unit(70)=(0.7,'0-100')`、`(0.4)=(0.4,'0-1')`、`(None)=(None,'none')`；`_prob_clip(70)=0.7`（行为不变）；`_pick_prob` 正确解析来源；`derive_xgb_p_up`：READY→`0.42`、非 READY（有 `X`/`raw_prob`）→`None`、`sig=None`→`None` |
| V5 | 预存在失败隔离 | `git stash` 我的改动后重跑同一命令，结果**逐字相同**（见 §4 说明），证明**无新增失败** |
| V6 | `git diff` 全量审阅（6 文件） | 仅日志 / 标签 / 新字段 / 辅助函数；无 Step 7 打分 / 票数 / 权重 / Entry Authorization 逻辑变更 |

**关于全套收集错误（非本次引入）：**
`python -m pytest tests` 在全仓库范围内有**预存在**的收集错误——
`tests/test_fx_trade_bot_data.py` 顶层 `from fx_trade_bot import ...`，而 `fx_trade_bot.py`
在 import 时执行 `parser.parse_args()` → `SystemExit(2)`；另有若干依赖缺失配置/凭据的模块
（`test_oanda_*`、`test_account`、`test_market_open`、`test_trading_core` 等）。
`git stash` 基线复跑结果与本次**完全一致**（2 errors），确认与 Stage C 改动无关。
故回归以**与改动相关的定向套件**（V2/V3）为准。

---

## 4. 验收矩阵（任务单 §4）

| ID | 标准 | 结果 |
| --- | --- | --- |
| SC-A1 | 被改文件 `py_compile` 通过 | ✅ V1 |
| SC-A2 | 相关 pytest 套件无新增失败 | ✅ V2/V3/V5 |
| SC-A3 | `git diff` 无 Step 7 打分 / 票数 / 权重 / Entry Authorization 逻辑变更 | ✅ V6 |
| SC-A4 | 新增代码异常时 fail-open，返回值不变 | ✅ SC-02 双层 try/except；SC-05 默认/降级语义；v685 仅日志 |
| SC-A5 | A.2 seam 有 superseded 标注且未被删除 | ✅ SC-01（正文未删一字） |

---

## 5. 明确未做（超出 Stage C，需另批）

- 未接线 ML Vote；未改 Step 7 打分 / 权重；未改 Entry Authorization。
- 未移除 legacy fallback 的交易影响（§4.1.1.4，需另开 Phase 3.6 门槛）。
- 未把 `READY` 接到任何执行路径。
- 未动 `fx_trade_bot.py`（拷贝件）。
- 未 commit、未部署、未重训。

---

## 6. 残余说明（供审阅关注）

1. **SC-02 的身份是「字节身份」，非「同一实例」**：`loaded_identity.model_instance` 是
   由同一内存字节**新建**的实例，未替换 `strat_engine` 已接线实例（替换属执行路径改动，超出 Stage C）。
   它提供的是 artifact/scaler **字节级 SHA-256 绑定**（spec §3.4 所要求的身份面）。
2. **SC-02 会在每次 READY 时多读一次 artifact 并重构造一次模型**（一次/启动，fail-open）。
   如需避免重复构造，可后续另议（不在本阶段）。
3. **C-4 为观测层语义收紧**：`derive_xgb_p_up` 不再从 `X`/`raw_prob` 合成。
   由于真实 `Signal` 总带 `model_p_up`，实际数据损失可忽略；且 `attribution_v2` 未被
   v685 接线，不触及交易行为。若后续认为 `raw_prob`（同一模型输出、按方向还原）亦属
   READY 等价来源，可再批一次微调。

---

## 7. 状态

- 交付完成，**未提交**。工作树状态见 `git status`。
- 等待用户复核后再决定 commit / 部署。
