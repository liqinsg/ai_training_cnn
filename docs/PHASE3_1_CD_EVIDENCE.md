# PHASE 3.1 — CD EVIDENCE RECORD（Class Definition 取证记录）

**Status:** 取证完成 — 裁决 `CD = NOT VERIFIED`（当前环境证据不足）
**Phase:** 3.1 — Prediction Contract & Abstention Semantics
**Stage:** CD Evidence Task（契约 §9 Deferred Work：“CD evidence acquisition/verification；must precede READY activation”）
**Repository:** `/Users/liqin/projects/ai_training_cnn`
**Branch:** `v2026c`
**Baseline HEAD:** `cd3b072`（phase3.1 / A.2 deployed）
**Authority:** `docs/PHASE3_1_CONTRACT.md` §1.3.2 / §1.3.4 / §4.5 / §9
**Scope:** 仅取证与裁决 — 未修改任何 `.py`，未改变实盘行为，未激活 `READY`。

---

## 0. 一句话结论

CD 仍为 **NOT VERIFIED**。直接原因是 §1.3.2 的**要求 #1（绑定精确 artifact 的 SHA-256）在本工作树不成立**：模型 artifact 四件套缺失，`model_hash` 必然为 `None`。在补齐精确 artifact 之前，任何 `READY` 断言都是非法的。

---

## 1. 依据

`docs/PHASE3_1_CONTRACT.md` §1.3.2 规定 CD 只有在以下**六项全部成立**时才可标记 `VERIFIED`：

1. 绑定到精确 artifact 的 SHA-256（`model_artifact_hash`）
2. 从已加载 artifact 捕获真实 `classes_` 及其顺序
3. 正类 label/index 被显式确定，并证明 `predict_proba()` 列与 `classes_` 同序
4. 训练目标/label 定义证明哪个标签是 UP、哪个是 DOWN
5. 二分类互补/穷尽语义成立（才允许 `p_down = 1 - p_up`）
6. 可复现的证据溯源记录

§9 明确：**CD 取证必须先于 READY 激活。**

---

## 2. 环境与 artifact 清单（实测，2026-11-14）

| artifact | 路径 | 状态 | SHA-256 |
|---|---|---|---|
| model | `trade_model_xgb.json` | **ABSENT** | — |
| scaler | `scaler.joblib` | **ABSENT** | — |
| features | `trade_model_xgb.features.json` | **ABSENT** | — |
| cfg | `trade_model_xgb.cfg.json` | PRESENT | `e3ff196491dc503da1d85c9b30c8471044b8108c379677a836b4354d0f5c88f4` |
| legacy | `trade_model_xgb.pkl` | **ABSENT** | — |
| manifest | `trade_model_xgb.manifest.json` | **ABSENT** | — |

- 全仓库不存在任何 `.manifest.json`。
- `.gitignore`（L12–L21）排除 `trade_model_xgb.json` / `scaler.joblib` / `*.joblib` / `*.pkl`，故这些 artifact **只存在于 live 主机**；“本工作树缺失”≠“生产缺失”，但**用于 CD 验证的精确字节不在本仓库**。

**后果链条（实测可复现）：**
[fx_trade_bot.py#L1242](file:///Users/liqin/projects/ai_training_cnn/fx_trade_bot.py#L1242) `MODEL_PATH="trade_model_xgb.pkl"`
→ [resolve_artifact_paths()](file:///Users/liqin/projects/ai_training_cnn/fx_trade_bot_ml.py#L120-L131)（去后缀得到 stem）
→ [split_ok=False](file:///Users/liqin/projects/ai_training_cnn/fx_trade_bot_ml.py#L213-L224)
→ `ensure_model()` 返回 `UNAVAILABLE / MODEL_MISSING`，`model_hash = None`。

---

## 3. 六要素逐条裁决

| # | 要求 | 裁决 | 证据 |
|---|---|---|---|
| 1 | 绑定精确 artifact SHA-256 | ❌ **失败** | §2：model/scaler/features 全缺失；`model_hash=None` |
| 2 | 捕获真实 `classes_` | ❌ **失败** | 无 artifact 可加载 |
| 3 | 正类索引 ↔ `predict_proba` 列序 | ⚠️ 仅代码层 | [positive_class_index()](file:///Users/liqin/projects/ai_training_cnn/data_pipeline.py#L458-L461)：`classes[1] > classes[0]` 时取列 1 |
| 4 | 训练目标语义（哪个标签是 UP/DOWN） | ⚠️ 部分 | §4：UP 明确；DOWN 不明确（见 §5） |
| 5 | 二分类互补/穷尽语义 | ⚠️ 仅代码层 | `{0,1}` 目标 + XGB 二分类 ⇒ `predict_proba` 两列互补 |
| 6 | 可复现证据记录 | ✅ 本文档 | §8 复现步骤 |

**任一要素缺失 ⇒ CD 保持 `NOT VERIFIED`。** 上表 #1、#2 为硬失败。

---

## 4. 正面证据：训练目标语义（需求 #4，未绑定 artifact）

生产训练器 [retrain_model.py#L106-L108](file:///Users/liqin/projects/ai_training_cnn/retrain_model.py#L106-L108)：

```python
# ── Build TARGET: Did price go UP > threshold in N bars?
df["future_return"] = df["Close"].shift(-TARGET_HORIZON) / df["Close"] - 1
df["target"] = (df["future_return"] > TARGET_THRESHOLD).astype(int)
```

配置（[L32-L38](file:///Users/liqin/projects/ai_training_cnn/retrain_model.py#L32-L38)）：`TIMEFRAME="15m"`、`TARGET_HORIZON=6`、`TARGET_THRESHOLD=0.0005`、`model_type="xgboost"`、`use_macd=True`。

据此：

- **label 1 = 未来 6 根 bar 收益 `> +0.0005`（UP，语义明确）**
- **label 0 = “不高于 +0.0005”**

> 非生产 demo 说明：[fx_model_xgb.py#L60-L62](file:///Users/liqin/projects/ai_training_cnn/fx_model_xgb.py#L60-L62)（LightGBM + yfinance + `EURUSD=X 1d`，horizon 3）虽同样定义 `1=UP`，但其输出与 live 四件套无关，**不得作为 CD 证据**。

---

## 5. 关键发现：label 0 语义不对称（OPEN）

`p_down = 1 - p_up` 得到的是 **“非 UP-beyond-threshold”** 的概率，**不是“下跌”的概率**。契约 §1.3.2 #4 要求证明“哪个标签是 DOWN”，此点**未满足**：UP 类无歧义，DOWN 解释属过度声称。

影响：[live_prediction_engine.py#L179-L181](file:///Users/liqin/projects/ai_training_cnn/ml/live_prediction_engine.py#L179-L181) 的 `p_down = 1 - p_up` / `direction = BUY if p_up > 0.5 else SELL` 复制的是既有 legacy 战术（`strategy_decision.py:158`），在契约语汇下应显式表述为 **`SELL = not-UP`**，而非 `SELL = DOWN`。

---

## 6. 次要发现：cfg 溯源不自洽（OPEN）

磁盘 `trade_model_xgb.cfg.json` 的 `train_lookback_bars = 5000`，而当前训练器 [retrain_model.py#L55](file:///Users/liqin/projects/ai_training_cnn/retrain_model.py#L55) 将 `FEAT_CFG.train_lookback_bars` 设为 `LOOKBACK_BARS = 500`，且 [ModelWrapper.save()](file:///Users/liqin/projects/ai_training_cnn/data_pipeline.py#L626-L631) 直接 dump `FeatureConfig.__dict__`。

⇒ **现存 cfg 并非由当前 `retrain_model.py` 产出**（其对应 `FeatureConfig` 默认值 `train_lookback_bars=5000`）。这削弱了 quartet 的可复现溯源（关联 §1.3.2 #6），登记为待查项。

---

## 7. 裁决与系统影响

**裁决：`CD = NOT VERIFIED`。**

对本阶段系统行为的影响（无需改代码，且与契约完全一致）：

- `ensure_model()` → `UNAVAILABLE / MODEL_MISSING`
- `LivePredictionEngine.predict_live()` → `UNAVAILABLE / MODEL_NOT_USABLE`
- §4.1.1 guard（[integration_hook.py](file:///Users/liqin/projects/ai_training_cnn/ml/integration_hook.py)）恒 `return False`
- 新引擎完全惰性；`READY` 不可达；**这不是缺陷，是设计**

---

## 8. 复现步骤

```bash
# 1. artifact 清单 + 指纹
cd /Users/liqin/projects/ai_training_cnn
for f in trade_model_xgb.json scaler.joblib trade_model_xgb.features.json \
         trade_model_xgb.cfg.json trade_model_xgb.pkl; do
  if [ -f "$f" ]; then echo "PRESENT  $(shasum -a 256 "$f")"; else echo "ABSENT   $f"; fi
done

# 2. 确认无 manifest
find . -name '*.manifest.json'   # 期望：空

# 3. 版本基线
git rev-parse HEAD               # 期望：cd3b072
```

---

## 9. 完成 CD 验证所需输入

1. 从 live 主机取回精确的 `trade_model_xgb.json` + `scaler.joblib` + `trade_model_xgb.features.json`（建议含 `.pkl` / manifest）。
2. 加载后记录 `model.classes_` 实际取值与顺序，计算 `model_artifact_hash`（§1.3.4：hash 是溯源指纹，非逻辑身份）。
3. 在**同一台主机**上执行并留存可复现记录（§1.3.2 #6）。
4. 就 §5 的语义不对称做出显式裁决：接受 `SELL = not-UP`，或重新定义标签。

---

## 10. 开放项登记

| ID | 事项 | 状态 |
|---|---|---|
| CD-OPEN-1 | label 0 = “非 UP-beyond-threshold” ≠ DOWN；`p_down` 语义需显式裁决 | OPEN |
| CD-OPEN-2 | 磁盘 cfg 的 `train_lookback_bars=5000` 与当前训练器 `500` 不自洽 | OPEN |
| CD-OPEN-3 | 精确 artifact 四件套不在本仓库，需从 live 主机取回 | OPEN |
| CD-OPEN-4 | 预激活加固：`positive_class_label` 使用猜测默认值 `"UP"`、`p_down = 1 - p_up` 无条件假设 | OPEN（须在激活前单独批准修复） |

> CD-OPEN-4 属 Phase 3.6 激活前置项，当前冻结期不处理。
