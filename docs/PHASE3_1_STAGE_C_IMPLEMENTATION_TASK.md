# Phase 3.1 — Stage C 实施任务单（Consumer Transparency Migration）

**Version:** 1.0
**Date:** 2026-11-15
**Authorization:** 用户于 2026-11-15 明确批准 Stage C；并裁定 `ml/prediction_adapter.py`
为**唯一权威** `PredictionResult` 生产者，A.2 旧版（`ml/live_prediction_engine.py` +
`ml/integration_hook.py`）退役（不删代码）。
**Contract:** `docs/PHASE3_1_CONTRACT.md` v1.3（SHA-256 `49975ef4…de7b`）
**Spec:** `docs/PHASE3_1_STAGE_B_STRICT_SPEC.md` v3（Stage B 已验收）
**Scope target:** `fx_trade_bot_v685.py`（本次唯一被修改的脚本；`fx_trade_bot.py` 为其拷贝，不动）

---

## 0. 不可越界（契约 §4.1 / §4.1.1 / §4.2）

- **ML 状态透明化在范围内；交易行为冻结。**
- **禁止**：改 Step 7 打分、fallback 行为、票数、权重、Entry Authorization。
- **C-2（Step 7）是已登记的 known exception**（§4.1.1.6）：只做**透明化记录**，
  其 `prob_raw` 仍照旧喂给 `calc_weighted_score`，交易影响不得改变。
- 所有新增代码必须 **additive + fail-open**：任何异常一律吞掉并记日志，
  绝不改变返回值/控制流。
- **不删代码**：退役 = 加 superseded 标注。
- 本次**不 commit**、不部署、不重训。

---

## 1. 已核实的调用点

| 消费者 | 位置 | 现状 | 契约要求 |
| --- | --- | --- | --- |
| C-1 Step 4 汇合 | `fx_trade_bot_v685.py:2156` | `sig.action` 直接计票 | 独立读 PredictionResult 状态；**不得**为非 READY 造票 |
| C-2 Step 7 打分 | `fx_trade_bot_v685.py:2572-2594` | `prob_raw = sig.model_p_up` 喂 `calc_weighted_score`；缺省走 NEUTRAL | 独立记录真实 ML 状态；与 legacy fallback 区分；fallback 标注 `legacy scoring behaviour` |
| C-3 开仓理由日志 | `fx_trade_bot_v685.py:2736-2741` | `xgb_score = … or 0.0`，合成 0.0 与真实概率无法区分 | 状态与分数并记；区分 missing/default；**不得**把合成 `0.0` 当真实概率 |
| C-4 attribution p_up | `attribution_v2/live_hook.py:137-160` `derive_xgb_p_up` | 从 `X/100`、`raw_prob` **合成** p_up | 仅在 READY 时消费 p_up；不得从非 READY 合成 |
| C-5 attribution 单位 | `attribution_v2/data_bridge.py:94-110` `_prob_clip` | 静默 0–1 / 0–100 重解释 | 保留 scale-aware 行为并**记录来源/单位** |
| loader 身份 | `fx_trade_bot_ml.py:173-232` `ensure_model` | hash 由 `file_sha256` **单独读**，非单次读字节绑定 | 生产运行时提供 `LoadedModelIdentity`（§3.4） |

补充事实：实时模型对象是 `xgb.XGBClassifier`（`data_pipeline.py:530`，具备 `.classes_` /
`.predict_proba`），故 `ml/prediction_adapter.py` 可直接消费；`_open_reasons`（`:2737`）
仅用于日志与 Telegram 富文本（`:2838/:2881`），改动属纯透明化。

---

## 2. 任务

### SC-01 退役 A.2 seam（零风险）

- `ml/live_prediction_engine.py`：文件头加 superseded 横幅，指向 `ml/prediction_adapter.py`。
- `ml/integration_hook.py`：文件头加 superseded 横幅。
- **不删任何代码、不改任何行为。**

### SC-02 production loader 身份（additive，独立增量）

- 在 `fx_trade_bot_ml.py` 的 `ModelInitResult` 上**新增**可选字段（默认 `None`），
  由 `load_model_with_identity(...)` 以 **try/except 尽力**填充。
- 失败/不可用 → 字段保持 `None`，**不得**影响既有 load 结果与控制流。
- 目的：使 Stage C 消费者能在生产侧拿到**单次读字节绑定**的 artifact/scaler 身份。

### SC-03 C-2 / C-3 透明化（`fx_trade_bot_v685.py`）

- C-2：在 Step 7 之后**追加**一条审计日志，区分：
  - `true model output`（`sig.model_p_up` 非 None），
  - `legacy XGB NEUTRAL / synthesized X`（缺失）。
  并在缺失分支明确标注 `legacy scoring behaviour`。
- C-3：`_open_reasons` 中区分真实概率与合成值，例如
  `XGB_SCORE=0.00(SYNTHETIC)` vs `XGB_SCORE=0.42`。
- **`prob_raw` 的取值与传入 `calc_weighted_score` 的路径逐字不变。**

### SC-04 C-1 透明化（`fx_trade_bot_v685.py:2156`）

- 记录每个 TF 的 ML 状态；**不新增票、不改票数**。
- 非 READY 一律记为「非 ML 方向票」。

### SC-05 C-4 / C-5 attribution（`attribution_v2/`）

- C-4：`derive_xgb_p_up` 仅在 READY 语义下消费；否则记为缺失（`degraded`），
  **不再**从 `X/100`、`raw_prob` 合成。
- C-5：`data_bridge` 记录概率**来源与单位**，消除静默重解释。

### SC-06 验证与报告

- `python -m py_compile` 全部被改文件；
- 相关既有 pytest 套件回归（不得新增失败）；
- 逐文件 `git diff` 证明「仅透明化、无行为变更」；
- 产出 Stage C 完成报告。

---

## 3. 明确不做（超出 Stage C）

- 不接线 ML Vote、不改 Step 7 打分/权重、不改 Entry Authorization。
- 不移除 legacy fallback 的交易影响（§4.1.1.4，需另开 Phase 3.6 门槛）。
- 不把 `READY` 接到任何执行路径。
- 不动 `fx_trade_bot.py`（拷贝件）。

---

## 4. 验收标准

| ID | 标准 |
| --- | --- |
| SC-A1 | 被改文件 `py_compile` 通过 |
| SC-A2 | 相关 pytest 套件无新增失败 |
| SC-A3 | `git diff` 中无任何 Step 7 打分 / 票数 / 权重 / Entry Authorization 逻辑变更 |
| SC-A4 | 所有新增代码在异常时 fail-open，返回值不变 |
| SC-A5 | A.2 seam 有 superseded 标注且未被删除 |
