# PHASE 3.1 — CD 验证 · Live 主机续接手册（HANDOFF / RESUME PLAYBOOK）

**用途:** 在具备 artifact 的 live 主机上，按本文件即可无缝续接 Phase 3.1 的 CD 取证与验证。
**作者:** TRAE ｜ **生成日期:** 2026-11-14
**权威契约:** [`docs/PHASE3_1_CONTRACT.md`](./PHASE3_1_CONTRACT.md)（§1.3.2 六要素 / §4.1.1 隔离 / §9 Deferred Work）
**上一份裁决:** [`docs/PHASE3_1_CD_EVIDENCE.md`](./PHASE3_1_CD_EVIDENCE.md) → `CD = NOT VERIFIED`（因 artifact 缺失）

---

## 1. 可粘贴的「续接 Prompt」（给服务器上的 AI Agent）

> 你是 Phase 3.1 的 CD 取证代理。仓库 `ai_training_cnn`，分支 `v2026c`。
>
> **铁律（违反即停止）：**
> 1. 全程**只读**。严禁训练（`fit`）、严禁写/重发任何 artifact（`.json`/`.joblib`/`.pkl`）、严禁 `ModelWrapper` 非只读加载。Phase 3.0 规定 live runtime 不得发布 artifact。
> 2. 不得修改任何 `.py`，不得提交，不得部署。
> 3. 不得伪造/推断 `classes_`。拿不到就如实写 `NOT CAPTURED`。
>
> **任务：** 按 `docs/PHASE3_1_CONTRACT.md` §1.3.2 的六要素，完成 CD 取证，并对 `CD = VERIFIED | NOT VERIFIED` 给出裁决。
> **产出：** 在 `docs/PHASE3_1_CD_EVIDENCE.md` 追加一节 “Live Host Evidence（<hostname> / <date>）”，含全部原始输出，并更新开放项 CD-OPEN-1…4 的状态。
> **首先执行** 本文件 §4 的三步取证，把原始输出原样记录。

---

## 2. 当前状态快照（本机，2026-11-14）

| 项 | 值 |
|---|---|
| 分支 | `v2026c` |
| HEAD | `3ae3f68` `phase3.1 / quarantine non-authoritative Gemini track (DO-NOT-WIRE)` |
| 同步 | 与 `origin/v2026c` 一致，工作树干净 |
| 契约 | `docs/PHASE3_1_CONTRACT.md`（已提交 `cd3b072`，决策 D-1…D-22） |
| Stage B | 已上线：`ml/live_prediction_engine.py`、`ml/integration_hook.py`（未接线，additive seam） |
| CD 状态 | `NOT VERIFIED` |

**已提交链：** `3ae3f68` ← `657c733` ← `cd3b072` ← `0a7e212`

### 2.1 本机 artifact 清单（实测）

| artifact | 状态 | SHA-256 |
|---|---|---|
| `trade_model_xgb.json` | **ABSENT** | — |
| `scaler.joblib` | **ABSENT** | — |
| `trade_model_xgb.features.json` | **ABSENT** | — |
| `trade_model_xgb.cfg.json` | PRESENT | `e3ff196491dc503da1d85c9b30c8471044b8108c379677a836b4354d0f5c88f4` |
| `trade_model_xgb.pkl` | **ABSENT** | — |
| `trade_model_xgb.manifest.json` | **ABSENT** | — |

> `.gitignore` 排除了 `*.json`(model)/`scaler.joblib`/`*.pkl`，故这些 artifact **只存在于 live 主机**。

---

## 3. 唯一阻塞与只读铁律

**阻塞 = CD-OPEN-3：** 精确的 artifact 四件套不在本仓库，需从 live 主机取回。
**没有它们，§1.3.2 的要素 #1（SHA-256 绑定）与 #2（真实 `classes_`）硬失败，`READY` 不可达。**

**只读铁律（Phase 3.0 §5）：**
- 加载模型必须**只读**：不得 `fit`、不得 `save_model`、不得任何 re-publish。
- 若用生产 `ModelWrapper`，必须以 `read_only=True` 构造，并确认 `_assert_writable` 未被触发。
- 任何写操作都是红线。

---

## 4. 取证步骤（在 live 主机、repo 目录下执行）

### 步骤 A — 指纹 + 环境基线

```bash
hostname; uname -a; date -u +%FT%TZ; git rev-parse HEAD
stem=trade_model_xgb
for f in $stem.json scaler.joblib $stem.features.json $stem.cfg.json $stem.pkl $stem.manifest.json; do
  if [ -f "$f" ]; then echo "PRESENT  $(shasum -a 256 "$f")"; else echo "ABSENT   $f"; fi
done
find . -name '*.manifest.json'    # 期望：列出 manifest（若有）
```

### 步骤 B — 只读加载探针（捕获 `classes_` 与列序）

```bash
python3 - <<'PY'
import json, pathlib
import xgboost as xgb, joblib

# 只读加载，绝不 save
m = xgb.XGBClassifier()
m.load_model("trade_model_xgb.json")
print("classes_        =", getattr(m, "classes_", None))     # 关键：可能是 None（见下注）
print("n_features_in_  =", getattr(m, "n_features_in_", None))

sc = joblib.load("scaler.joblib")                            # 只读
print("scaler.n_in_    =", getattr(sc, "n_features_in_", None))

feats = json.loads(pathlib.Path("trade_model_xgb.features.json").read_text())
print("features(n=%d)  =" % len(feats), feats)

cfg = json.loads(pathlib.Path("trade_model_xgb.cfg.json").read_text())
print("cfg             =", cfg)
PY
```

> **关键预警：** xgboost 的 sklearn `.json` 只存 booster，**`classes_` 通常不随 `load_model` 复原**。
> - 若 `classes_` 为 `None` → **正类顺序无法仅凭 `.json` 证明**，这本身就是 CD 结论的一部分。
> - 此时改从 `.pkl`（若存在）或 manifest 取证；若两者皆无 → `CD = NOT VERIFIED`（要素 #2/#3 无法满足）。

**（可选，更忠实）生产加载路径取证：** 用仓库真实加载器只读重放，捕获线上实际使用的 `positive_class_index` 与概率列：

```bash
python3 - <<'PY'
# 参考 data_pipeline.py: positive_class_index() / predict_p_up() / ModelWrapper(read_only=True)
# 目标：打印线上真实使用的正类索引，以及 predict_proba 输出与该索引列的对应关系。
# 注意：只读，不得触发任何 save。
PY
```

### 步骤 C — 训练目标语义（要素 #4 的证据）

记录**产出当前 artifact 的训练器版本与其标签定义**。当前仓库生产训练器
[`retrain_model.py`](../retrain_model.py) 定义为：

```python
df["future_return"] = df["Close"].shift(-TARGET_HORIZON) / df["Close"] - 1
df["target"] = (df["future_return"] > TARGET_THRESHOLD).astype(int)
# TARGET_HORIZON=6, TARGET_THRESHOLD=0.0005  → label 1 = 未来6根bar收益 > +0.0005 (UP)
```

> 必须确认 live 主机上**实际产出该 artifact 的脚本/commit** 与此一致；若不一致，记录实际版本（这是要素 #6 溯源要求）。

---

## 5. §1.3.2 六要素裁决表（现场填空）

| # | 要求 | 现场证据 | 裁决 |
|---|---|---|---|
| 1 | 精确 artifact 绑定 SHA-256（`model_artifact_hash`） | 步骤 A 输出 | ☐ PASS / ☐ FAIL |
| 2 | 真实 `classes_` 值与其顺序 | 步骤 B `classes_=` | ☐ PASS / ☐ FAIL |
| 3 | 正类 label/index ↔ `predict_proba` 列序 一致 | 步骤 B + 生产加载器 | ☐ PASS / ☐ FAIL |
| 4 | 训练目标语义：哪个 label 是 UP / DOWN | 步骤 C | ☐ PASS / ☐ FAIL |
| 5 | 二分类互补/穷尽语义（才允许 `p_down = 1 - p_up`） | 步骤 B `classes_` 是否为 `[0,1]` | ☐ PASS / ☐ FAIL |
| 6 | 可复现证据溯源记录 | 本表 + 原始输出 + host/commit/date | ☐ PASS / ☐ FAIL |

**判定：六项全部 PASS ⇒ `CD = VERIFIED`；任一 FAIL/缺失 ⇒ `CD = NOT VERIFIED`。**

---

## 6. 判据决策树

- `classes_` 拿到且为 `[0, 1]`，且训练目标证明 `1 = UP`：
  - 若所有六要素 PASS → **CD = VERIFIED**。可解除 `READY` 禁令，但**仍需单独批准**才能进入 Stage B 激活（`class_definition_verified=True`）。
  - 若要素 #4 证明 label 0 ≠ DOWN（即 label 0 = “非UP-beyond-threshold”）→ 触发 **CD-OPEN-1 显式裁决**：接受 `SELL = not-UP`，或回 ChatGPT 重定义标签。
- `classes_` 为 `None`（`.json` 不含）→ 找 `.pkl`/manifest；仍无 → **NOT VERIFIED**。
- cfg `train_lookback_bars=5000` 与训练器 `500` 不一致（CD-OPEN-2）→ 记录产出该 artifact 的真实 commit，判定 quartet 溯源是否自洽。

---

## 7. 回传模板（把这段贴回本机，我即刻做裁决）

```text
[LIVE HOST EVIDENCE]
host      = <hostname>
date_utc  = <ISO8601>
git_head  = <rev-parse HEAD>

[step A]
<逐行粘贴 PRESENT/ABSENT + sha256 输出>

[step B]
classes_       = <...>
n_features_in_ = <...>
scaler.n_in_   = <...>
features       = <...>
<生产加载器输出：positive_class_index=...>

[step C]
producing_script = <retrain_model.py @ commit X | 其他>
target_def       = <label 1 = ? ; label 0 = ?>
```

---

## 8. 开放项与冻结边界

### 开放项
| ID | 事项 | 状态 |
|---|---|---|
| CD-OPEN-1 | label 0 = “非 UP-beyond-threshold” ≠ DOWN；`p_down` 语义需显式裁决 | OPEN |
| CD-OPEN-2 | cfg `train_lookback_bars=5000` vs 训练器 `500`，溯源不自洽 | OPEN |
| CD-OPEN-3 | 精确 artifact 四件套不在本仓库，需从 live 主机取回 | **本手册处理中** |
| CD-OPEN-4 | 预激活加固：`positive_class_label` 猜测默认 `"UP"`、`p_down = 1 - p_up` 无条件假设 | OPEN（须激活前单独批准修复） |

### 冻结边界（本阶段严禁触碰）
- **Entry Authorization 不变且未解决**（契约 §11）。
- Step 7 scoring / legacy fallback 行为不变（§4.1.1，C-2 为注册 Known Exception）。
- 禁止 live 训练 / artifact 写入 / 重新发布（Phase 3.0 §5）。
- 不得把本手册当作「已批准激活」；本文件只做 CD 取证，不授权 Stage B 激活。
- 代码侧现状（已与契约一致，勿改）：方向平局规则 `p_up > 0.5`（D-19）；`PredictionResult` 自描述字段齐备（D-20）。

---

## 9. 权威文件索引

| 文件 | 角色 |
|---|---|
| [`docs/PHASE3_1_CONTRACT.md`](./PHASE3_1_CONTRACT.md) | 权威契约（D-1…D-22） |
| [`docs/PHASE3_1_CD_EVIDENCE.md`](./PHASE3_1_CD_EVIDENCE.md) | CD 取证记录（当前裁决 NOT VERIFIED） |
| `ml/live_prediction_engine.py` | Stage B 预测引擎（含 `PredictionStatus/Reason/Result`） |
| `ml/integration_hook.py` | §4.1.1 隔离护栏 seam（未接线） |
| `retrain_model.py` | 生产训练器（标签定义来源） |
| `data_pipeline.py` | 生产特征引擎 / `ModelWrapper` / `positive_class_index()` |
| `fx_trade_bot_ml.py` | Phase 3.0 `ModelInitResult` / `ensure_model()` |
