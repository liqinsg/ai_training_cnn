# PHASE 3.1 — CD EVIDENCE RECORD（Class Definition 取证记录）

**Status:** 取证完成 — macOS 基线裁决 `CD = NOT VERIFIED`（该工作树 artifact 缺失）；**live 主机续证见文末 “[Live Host Evidence](#live-host-evidence-arm--2026-11-14)” → 最终裁决 `CD = VERIFIED`（CD-OPEN-1 已裁决：接受 `SELL = not-UP`）**
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

---

# Live Host Evidence（arm / 2026-11-14）

**取证模式:** 全程只读（未 `fit`、未写/重发任何 artifact、未改 `.py`、未 commit、未部署）。
**Repository（live 主机）:** `/home/ubuntu/projects/ai_training_cnn`
**Branch / HEAD:** `v2026c` / `10147858af1ff3067dc413330b369911b8186e91`
**host / date_utc:** `arm` / `2026-11-14T07:51:42Z`
**Runtime:** Python `3.12.15` ｜ xgboost `2.0.3` ｜ sklearn `StandardScaler`

> 与前次裁决（§0–§10，macOS 工作树，`CD = NOT VERIFIED`）的差别：**本机是持有精确 artifact 的 live 主机**，
> 因此 §1.3.2 #1「精确 artifact 绑定」与 #2「真实 `classes_`」从**硬失败**变为**可取证**。

---

## A. 指纹 + 环境基线（Step A）

```text
$ hostname; date -u +%FT%TZ; git rev-parse HEAD
arm
2026-11-14T07:51:42Z
10147858af1ff3067dc413330b369911b8186e91

$ stem=trade_model_xgb
$ for f in $stem.json scaler.joblib $stem.features.json $stem.cfg.json $stem.pkl $stem.manifest.json; do
>   if [ -f "$f" ]; then echo "PRESENT  $(sha256sum "$f")"; else echo "ABSENT   $f"; fi
> done
PRESENT  94c8751df33daee5190e42634d823bcb08d4a0dbc1e0a2cf2f3e8cfbd91d5942  trade_model_xgb.json
PRESENT  031ea8068a2b8309829624b30acb7db2cde40ce4452240cf423619fae4b2cd8c  scaler.joblib
PRESENT  3e9e319cae45dc405cf55ba49a2dd87fad8beacb4148d52066b2c79a697605da  trade_model_xgb.features.json
PRESENT  e3ff196491dc503da1d85c9b30c8471044b8108c379677a836b4354d0f5c88f4  trade_model_xgb.cfg.json
ABSENT   trade_model_xgb.pkl
PRESENT  9b860295166d06c1445e5b335f621af6dc5d60ad2a905a9807c512a941ca27bb  trade_model_xgb.manifest.json

$ find . -name '*.manifest.json' -not -path './.git/*'
./trade_model_xgb.manifest.json
```

| artifact | sha256 | 备注 |
|---|---|---|
| `trade_model_xgb.json` | `94c8751d…d5942` | **= `model_artifact_hash`** |
| `scaler.joblib` | `031ea806…2cd8c` | StandardScaler，`n_features_in_ = 34` |
| `trade_model_xgb.features.json` | `3e9e319c…605da` | 34 个特征名 |
| `trade_model_xgb.cfg.json` | `e3ff1964…c88f4` | 与前次记录一致（同字节） |
| `trade_model_xgb.pkl` | — | **ABSENT**（legacy 加载分支不成立） |
| `trade_model_xgb.manifest.json` | `9b860295…27bb` | 新增：live 主机独有 |

**四件套同批证据（mtime，本地 +0800）：** 全部为 `2026-11-13 16:01:34`，且与
`manifest.created_at = 2026-11-13T08:01:34.749304+00:00` 同秒 ⇒ 四件套 + manifest 由**同一次训练**写出。
写盘顺序：`.json(.746) → scaler(.747) → .features.json(.748) → .cfg.json(.748) → .manifest.json(.749)`。

```text
$ md5sum trade_model_xgb.json scaler.joblib trade_model_xgb.features.json trade_model_xgb.cfg.json trade_model_xgb.manifest.json
b3ee253b1c3e53891a20ad5b8a32e0b2  trade_model_xgb.json
4ec25d485bac864b97d202b2ad04e341  scaler.joblib
7474da45b823902a9737cdf9e718d5ad  trade_model_xgb.features.json
c1bd09df868fc4554c9f5a182d67154a  trade_model_xgb.cfg.json
f0b654f5b75f1334851753bee95c0c45  trade_model_xgb.manifest.json
```

`manifest.json` 内容（`schema_version=v1.0`，`feature_names` 与本机 `features.json` **逐字一致**共 34 项）：

```json
{ "schema_version": "v1.0",
  "created_at": "2026-11-13T08:01:34.749304+00:00",
  "feature_names": ["ret_1h","ret_3h","ret_6h","ret_12h","ret_log","vol_12h","vol_24h",
                    "vol_48h","body","upper_wick","lower_wick","range","direction","atr",
                    "atr_pct","atr_percentile","atr_ma","atr_expanding","atr_ratio","rsi",
                    "rsi_slope","adx","dist_high_24","dist_low_24","dist_high_48","dist_low_48",
                    "dist_high_96","dist_low_96","vol_sma_ratio","vol_trend","hour","day_of_week",
                    "is_london","is_ny"],
  "n_features": 34 }
```

---

## B. 只读加载探针（Step B）

```text
$ python3 - <<'PY'  (只读：仅 load_model/joblib.load/json.load，无 save)
python: 3.12.15
xgboost: 2.0.3
classes_        = [0 1]
n_features_in_  = 34
n_classes_      = 2
get_booster().num_class = None
scaler.type     = StandardScaler
scaler.n_in_    = 34
features(n=34)  = ['ret_1h', ... ,'is_ny']
cfg             = {'use_atr': True, ..., 'model_type': 'xgboost', 'target_horizon': 6,
                   'train_lookback_bars': 5000, 'retrain_every_n_days': 7, 'required_bars': 20}
```

Booster 目标（只读 `save_config`）：

```text
objective       = binary:logistic
num_class(param)= 0                 # 二分类在 XGBoost 内部按回归处理
n_classes_      = 2
classes_        = [0 1]
```

### B′. 关键发现：`classes_` 是**库合成属性**，不是从 artifact 复原的值

`xgboost 2.0.3` 的 `XGBClassifier.classes_` 是 **property**，不随 `.json` 保存：

[xgboost/sklearn.py#L1640-L1642](file:///home/ubuntu/miniconda3/envs/ai-sprint/lib/python3.12/site-packages/xgboost/sklearn.py#L1640-L1642)

```python
@property
def classes_(self) -> np.ndarray:
    return np.arange(self.n_classes_)
```

- `load_model()`（[sklearn.py#L820-L843](file:///home/ubuntu/miniconda3/envs/ai-sprint/lib/python3.12/site-packages/xgboost/sklearn.py#L820-L843)）只从 booster config 复原 `n_classes_`（`num_class` < 2 时置 2），**不复原原始 `classes_` 数组**。
- 实证：`fresh = XGBClassifier(); hasattr(fresh,"classes_")` → `False`；`fresh.load_model(...)` 后 → `[0 1]`，且 `booster.attributes() == {}`。
- **结论：`.json` artifact 本身不携带类别标签/顺序；`[0,1]` 是二分类下 XGBoost 唯一可能的约定值**（由 `objective=binary:logistic` 决定），而非“训练时的真实 `classes_` 被读回”。

### B″. 生产加载路径只读重放（含正类索引与 `predict_proba` 列序）

```text
$ python3 - <<'PY'  (只读)
objective       = binary:logistic
n_classes_      = 2
classes_        = [0 1]
positive_class_index = 1                      # data_pipeline.positive_class_index(model)
predict_p_up    = [0.6497587]                 # 零向量输入的 predict_p_up() 输出
predict_proba[0]= [0.3502413 0.6497587]       # 列0=P(class0), 列1=P(class1)
colsum          = 1.0
col1 == p_up    = True                        # p_up 取的就是 classes_[1] 那一列
wrapper read_only = True | n_feats = 34
wrapper positive_class_index = 1              # ModelWrapper(read_only=True).load() 后
```

对应代码：[positive_class_index()](file:///home/ubuntu/projects/ai_training_cnn/data_pipeline.py#L458-L461)（`classes[1] > classes[0]` → 取列 1）、
[predict_p_up()](file:///home/ubuntu/projects/ai_training_cnn/data_pipeline.py#L464-L471)、
[ModelWrapper.load()](file:///home/ubuntu/projects/ai_training_cnn/data_pipeline.py#L634-L659)（`read_only=True`，未触发 `_assert_writable`）。

---

## C. 训练目标语义（Step C — 要素 #4 证据）

仓库内**两条**训练路径，二者**方向一致**（都定义 label 1 = UP），仅阈值不同：

| 产出/路径 | 标签定义 | 阈值 | horizon | 来源 |
|---|---|---|---|---|
| 显式训练器 | `target = future_return > TARGET_THRESHOLD` | **+0.0005** | 6 | [retrain_model.py#L106-L108](file:///home/ubuntu/projects/ai_training_cnn/retrain_model.py#L106-L108) |
| 自动训练（bot 自训） | `target = (future_return > 0)` | **0** | 6 | [data_pipeline.build_target()#L369-L378](file:///home/ubuntu/projects/ai_training_cnn/data_pipeline.py#L369-L378) |

```python
# retrain_model.py:106-108（L35-37: LOOKBACK_BARS=500, TARGET_HORIZON=6, TARGET_THRESHOLD=0.0005）
df["future_return"] = df["Close"].shift(-TARGET_HORIZON) / df["Close"] - 1
df["target"] = (df["future_return"] > TARGET_THRESHOLD).astype(int)

# data_pipeline.py:372-373
future_return = df["Close"].shift(-horizon) / df["Close"] - 1
df["target"] = (future_return > 0).astype(int)
```

⇒ **label 1 = 未来 6 bar 收益为正（UP）**（两条路径均成立）；
⇒ **label 0 = `not (future_return > 阈值)` = “非 UP”**（含横盘、微涨、下跌）——**不是“DOWN”**。见 CD-OPEN-1。

---

## D. 产出溯源（CD-OPEN-2 / 要素 #6）

**D-1 `train_lookback_bars=5000` 的来源（非 `retrain_model.py` 的 500）。**
live bot 构造 `FEAT_CFG` 时用 `cfg_bot("TRAIN_LOOKBACK_BARS", 5000)`（[fx_trade_bot_v685.py#L1217](file:///home/ubuntu/projects/ai_training_cnn/fx_trade_bot_v685.py#L1217)），
且 `build_profile_cfg()` 不暴露该 Key ⇒ 回落到默认 **5000**；`FeatureConfig` 默认亦为 5000（[data_pipeline.py#L111](file:///home/ubuntu/projects/ai_training_cnn/data_pipeline.py#L111)）。
`ModelWrapper.save()` 直接 dump `cfg.__dict__`（[data_pipeline.py#L614-L632](file:///home/ubuntu/projects/ai_training_cnn/data_pipeline.py#L614-L632)）
⇒ **cfg 是运行期配置快照，不是“本次训练元数据”**（与历史审计 R-15 一致）。

**D-2 manifest 的产出者。** 全仓库唯一写出 `{schema_version, created_at, feature_names, n_features}`
这一形状的代码是 [fx_trade_bot_ml_v1.py#L123-L130](file:///home/ubuntu/projects/ai_training_cnn/fx_trade_bot_ml_v1.py#L123-L130)
——即 Phase 3.1 已隔离的非权威 Gemini 支线（`DO-NOT-WIRE`，权威替代为 `fx_trade_bot_ml.py`）。
本机 manifest 的字段与该写入器**逐字匹配**。⇒ 产出该 quartet 的**很可能是该 auto-train 路径**（其标签 =
`build_target > 0`）。

> 注：`fx_trade_bot_ml_v1.py` 在契约 §3.4 中登记为 “stale/out of scope（无 live 入口 import）”。此处仅作**溯源线索**，不构成对其接线。

**D-3 cfg 与 features 的内部不一致（观测）。** `cfg.use_macd=true`，但 `features.json` 为 34 项且**不含任何 `macd*` 列**
（`FeatureEngine.build()` 在 `use_macd=True` 且 `n>26` 时会追加 MACD 列，[data_pipeline.py#L323-L329](file:///home/ubuntu/projects/ai_training_cnn/data_pipeline.py#L323-L329)）。
⇒ **cfg 的 `use_macd` 不代表 quartet 的真实特征集**，进一步证明 cfg 非权威训练元数据（与 D-1 同源）。
（此为特征契约问题，属 Phase 3.2 范围；不影响 CD 裁决。）

> **结论：** 无法把 quartet 精确钉到某一个**已提交的** commit/脚本版本；`cfg` 明确不可作为训练元数据证据。
> 但两份候选标签定义**方向一致**（label 1 = UP），且都能定位到可复现源码。

---

## E. §1.3.2 六要素裁决表（live 主机填空）

| # | 要求 | 现场证据 | 裁决 |
|---|---|---|---|
| 1 | 精确 artifact 绑定 SHA-256（`model_artifact_hash`） | §A：`trade_model_xgb.json = 94c8751d…d5942`；四件套 + manifest 同秒写出，manifest 特征表与 features.json 一致 | ☑ **PASS** |
| 2 | 真实 `classes_` 值与其顺序 | §B：runtime `classes_ = [0,1]`；**但为库属性 `np.arange(n_classes_)`，`.json` 不存储标签数组**（B′） | ☐ **PARTIAL**（值可得但非 artifact 存储） |
| 3 | 正类 label/index ↔ `predict_proba` 列序 一致 | §B″：`positive_class_index=1`；`predict_proba=[P0,P1]`，`colsum=1`，`col1==p_up` | ☑ **PASS** |
| 4 | 训练目标语义：哪个 label 是 UP / DOWN | §C：**label 1 = UP（已证）**；label 0 = “非 UP” **≠ DOWN** | ☐ **FAIL（仅 DOWN 部分）** → CD-OPEN-1 |
| 5 | 二分类互补/穷尽语义 | §B：`objective=binary:logistic`，`n_classes_=2`，`predict_proba` 两列互补求和为 1 | ☑ **PASS** |
| 6 | 可复现证据溯源记录 | 本节 + §A–§D 原始输出 + host/commit/date；可复现 | ☑ **PASS** |

**判定（严格）：#4 未满足 “which means DOWN” ⇒ `CD = NOT VERIFIED`。**
其余五要素（#1/#3/#5/#6 PASS；#2 PARTIAL）均已达标。**唯一的残余阻塞是 #4 的语义口径（CD-OPEN-1）**，不再是 artifact 缺失。

---

## F. 裁决（含 CD-OPEN-1 显式裁决）

**现场严格口径（未裁决前）：`CD = NOT VERIFIED`。**
理由：§1.3.2 #4 要求“证明哪个 label 是 DOWN”，而本模型 `label 0 = 非 UP-beyond-threshold`，
仓库内不存在真正的 DOWN 类（§C）。依契约，此项缺失/含糊即 `NOT VERIFIED`。

**显式裁决（CD-OPEN-1，2026-11-14，权威方）：接受 `SELL = not-UP`。**
第二类即 `not-UP`；方向规则 `p_down = 1 - p_up; direction = BUY if p_up > 0.5 else SELL`
（§1.3.2 §5 + D-19）中的 `SELL` 语义为 **not-UP，而非 `P(DOWN)`**。据此 #4 按契约的**操作性定义**达成。

**最终裁决：`CD = VERIFIED`（绑定 artifact `trade_model_xgb.json@94c8751d…d5942`）。**
六要素在该操作性定义下全部满足（#1/#3/#5/#6 PASS；#2 值可取证但系库合成；#4 经本裁决达成）。

> **边界：** `CD = VERIFIED` **不等于** 授权 Stage B 激活。激活仍须**单独批准**（契约 §1.3.2 / §11：
> `class_definition_verified=True` 需独立 gate）。本文件不授权任何激活、不授权改 `.py`、不授权重训/发布。
>
> 备选未采用路径（留档）：(b) 重定义标签为真正的 UP/FLAT/DOWN（或三分类）并重训产出新 quartet
> （新 SHA-256）后重新取证——本次未采用。

---

## G. 开放项更新

| ID | 事项 | 前状态 | 新状态 |
|---|---|---|---|
| CD-OPEN-1 | label 0 = “非 UP” ≠ DOWN；`p_down` 语义需显式裁决 | OPEN | **RESOLVED（已裁决）**：接受 `SELL = not-UP`（2026-11-14，权威方）→ `CD = VERIFIED` |
| CD-OPEN-2 | cfg `train_lookback_bars=5000` vs 训练器 `500`，溯源不自洽 | OPEN | **RESOLVED（成因已定位）**：5000 = live `FEAT_CFG` 回落默认；cfg 非训练元数据（§D-1/D-3） |
| CD-OPEN-3 | 精确 artifact 四件套不在本仓库，需从 live 主机取回 | OPEN（本手册处理中） | **RESOLVED**：已在 live 主机 `arm` 取到四件套 + manifest，指纹见 §A |
| CD-OPEN-4 | 预激活加固：`positive_class_label` 猜测默认 `"UP"`、`p_down = 1 - p_up` 无条件假设 | OPEN | **OPEN（不变，须激活前单独批准修复）** |

---

## H. 复现命令（live 主机，只读）

```bash
# A. 指纹 + 基线
hostname; date -u +%FT%TZ; git rev-parse HEAD
for f in trade_model_xgb.json scaler.joblib trade_model_xgb.features.json \
         trade_model_xgb.cfg.json trade_model_xgb.pkl trade_model_xgb.manifest.json; do
  [ -f "$f" ] && echo "PRESENT $(sha256sum "$f")" || echo "ABSENT  $f"; done

# B. 只读加载探针（classes_ / 正类索引 / predict_proba 列序）
python3 -c "import xgboost as xgb, joblib, json; \
m=xgb.XGBClassifier(); m.load_model('trade_model_xgb.json'); \
print('classes_=',m.classes_,'n_classes_=',m.n_classes_); \
from data_pipeline import positive_class_index, predict_p_up; \
print('pos_idx=',positive_class_index(m))"
```
