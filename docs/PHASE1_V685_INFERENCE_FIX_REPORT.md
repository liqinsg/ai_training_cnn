# PHASE 1 — v685 推理路径一致性修复报告（1-A / 1-C / 1-D）

- 范围：只修**推理路径一致性**（同一 scaler 实例、同一特征顺序、同一 P(UP) 列、契约违约时**大声失败**）。
- **没有**训练模型、**没有**覆盖工件、**没有**改阈值 / 仓位 / 执行逻辑 / 配置文件。
- 日期：2026-10-22 · 复现环境：Python 3.12.13 / numpy 2.2.6 / pandas 3.0.6 / xgboost 3.3.0 / scikit-learn 1.9.1 / pandas_ta 0.4.71b0

---

## 0. 结论（TL;DR）

| 编号 | 检查项 | 结果 |
|---|---|---|
| 1-A | 工件一致性（model / scaler / features 维度 + `use_macd` + MACD 列） | **PASS** — 37 / 37 / 37，`use_macd=true`，MACD 三列都在且有非零 gain |
| 1-C | 单元测试 + 真实工件 parity | **PASS** — 16/16 新测试通过；真实工件上 wrapper 与 engine 概率**逐位相同**（diff = 0.0） |
| 1-C | 工件只读性 | **PASS** — 4 个工件的 (mtime_ns, size) 前后完全一致 |
| 1-D | MACD triage（定位 + 根因，**不修**） | **DONE** — 两个机制被复现：`n < 34` 时 `ta.macd` 返回 `None`；`Close` 单个 NaN 会**毒化整段** MACD，随后被 `fillna(0)` 变成恒零（残余风险，见 §6） |

**结论：READY FOR PHASE 2**（不是 BLOCKED：工件维度自洽、无契约冲突；但 §6 的“零填充”残余风险必须在 Phase 2 处理）。

---

## 1. 问题回顾（修复前）

```
v685 运行期（修复前）
raw M15 ─▶ FeatureEngine.build() ─▶ df（43 列，含 vol_regime 字符串列）
                                      │
                                      ├─▶ StrategyEngine._predict(df.iloc[-1])
                                      │      row = {f: latest.get(f, 0.0) for f in features}   ← 缺列静默补 0
                                      │      X   = pd.DataFrame([row]).values                 ← 无 scaler.transform
                                      │      p   = model.predict_proba(X)[0, 1]                ← 硬编码列 1
                                      │
                                      └─▶ ModelWrapper.predict_proba(df)
                                             df[feature_names] 缺失列 = 0.0 → 直接喂模型       ← 同样不做缩放
```

三重不一致：① 训练用 `scaler.transform(X)`、推理**完全不缩放**；② 缺列/改名一律按 `0.0` 填充；③ `[0, 1]` 假设正类永远在第 1 列。

## 2. 修复后的单一推理核心

```
                              ┌──────────────────────────────┐
df / Series / dict / ndarray ─▶│ prepare_inference_matrix()   │
                              │  · names = .features.json 顺序│
                              │  · 缺列 / object / NaN / inf  │──▶ InferenceFeatureError
                              │  · scaler 未注入/未 fit        │──▶ ScalerMissingError
                              │  · scaler.transform(values)   │
                              └──────────────┬───────────────┘
                                             ▼
                              ┌──────────────────────────────┐
                              │ predict_p_up()               │
                              │  · model.predict_proba(scaled)│
                              │  · positive_class_index()     │──▶ P(UP) 由 model.classes_ 决定
                              └──────────────┬───────────────┘
                                             │
                    ┌────────────────────────┴────────────────────────┐
                    ▼                                                 ▼
     StrategyEngine._predict()                        ModelWrapper.predict_proba()
     （scaler 由 ensure_model 注入 =                       （同一 model / scaler /
       model_wrapper.scaler 同一实例）                        feature_names 实例）
```

两个入口现在调用**同一个函数**，一致性由构造保证，而不是靠两边“写法一致”来维持。

---

## 3. 变更清单（`git diff --stat`）

```
 data_pipeline.py     | 202 +++++++++++++++++++++++++++++++++++++++++++++++++--
 fx_trade_bot_ml.py   |  13 ++++
 strategy_decision.py |  33 +++++++--
 3 files changed, 236 insertions(+), 12 deletions(-)
   (numstat: data_pipeline +196/-6, fx_trade_bot_ml +13/-0, strategy_decision +27/-6)
 tests/test_inference_consistency_v685.py  (新增，16 个测试)
```

### 3.1 `data_pipeline.py`

| 新增 / 修改 | 作用 |
|---|---|
| `class InferenceFeatureError(ValueError)` | 推理行与训练特征契约不符（缺列 / 非数值 / NaN / inf / 维度不符） |
| `class ScalerMissingError(RuntimeError)` | 没有训练 scaler（未注入或未 fit）就试图预测 |
| `positive_class_index(model, n_classes)` | 从 `model.classes_` 里找 `1` 的下标；无 `classes_` 时仅允许二分类回退到列 1，否则报错 |
| `prepare_inference_matrix(X, feature_names, scaler)` | 唯一对齐 + 缩放实现：按 `.features.json` 顺序取列、拒绝缺列、拒绝 object/NaN/inf、`scaler.transform` |
| `predict_p_up(model, scaler, feature_names, X)` | 唯一推理入口：`prepare_inference_matrix` → `predict_proba` → 取 P(UP) 列 |
| `ModelWrapper.predict_proba()` | 改为 `predict_proba(prepare_inference_matrix(...))`，不再 `get(f, 0.0)` |
| `ModelWrapper._validate_loaded_artifacts()` | `load()` 的两条分支（split 工件 / legacy pkl）都调用；`model.n_features_in_ == scaler.n_features_in_ == len(features.json)` 否则抛错 |

Series 输入的处理是本轮最关键的一处修正：

```python
if isinstance(X, pd.Series):
    # Build each column from its scalar so pandas infers a *per-column* dtype.
    # Series.to_frame().T collapses a mixed int/float row (the normal
    # `df.iloc[-1]` case) into object and would reject every column.
    X = pd.DataFrame({c: [X[c]] for c in names if c in X.index})
```

> 为什么必须这么写：生产路径是 `latest = df.iloc[-1]`，特征帧里 `hour / day_of_week / is_ny` 是 int/bool、
> 其余是 float，**行 Series 的 dtype 是 `object`**。若用 `Series.to_frame().T`，整行仍是 object，
> 严格校验会把 37 列全部判成“非数值”而拒绝预测（真实工件 1-C 首轮运行就是这样暴露出来的）。
> 逐列构造 DataFrame 后每列单独推断 dtype，既保持严格，又不误杀生产输入。

### 3.2 `strategy_decision.py`

```diff
-from data_pipeline import ...                      # 新增
+from data_pipeline import ScalerMissingError, predict_p_up

-    def __init__(self, config: StrategyConfig, model, feature_list: List[str]):
+    def __init__(self, config, model, feature_list: List[str], scaler=None):
         ...
         self.features = feature_list
+        self.scaler = scaler          # 由 ensure_model() 注入，本类永不自行 load/refit

     def _predict(self, latest: pd.Series) -> float:
-        row = {f: latest.get(f, 0.0) for f in self.features}
-        X = pd.DataFrame([row])
-        return float(self.model.predict_proba(X.values)[0, 1])
+        if self.scaler is None:
+            raise ScalerMissingError(...)
+        return float(predict_p_up(self.model, self.scaler, self.features, latest)[0])
```

`scaler=None` 是**可选关键字参数**，现有 3 个位置参数的调用（`fx_trade_bot_v685.py:1184`）保持不变。

### 3.3 `fx_trade_bot_ml.py`（`ensure_model`）

```diff
     strat_engine.model = model_wrapper.model
+    strat_engine.scaler = model_wrapper.scaler      # 同一实例，不重新 load
     strat_engine.features = model_wrapper.feature_names
+    logger.info("Inference wiring: model_n_features=%s scaler_n_features=%s "
+                "features=%s use_macd=%s", ...)
```

`fx_trade_bot_v685.py` **不需要改动**：它已经通过 `ensure_model(...)` 拿到 `(model_wrapper, strat_engine)`，
注入点在 `ensure_model` 内部完成。

### 3.4 `tests/test_inference_consistency_v685.py`（新增）

16 个测试，全部基于**内存中的** xgboost 模型 + `StandardScaler`（合成数据，不读、不写仓库工件、不联网）：

| # | 测试 | 断言 |
|---|---|---|
| 1 | `test_engine_matches_wrapper_exactly` | engine `_predict` 与 wrapper `predict_proba` 概率差 = 0（abs 1e-12） |
| 2 | `test_mixed_dtype_series_row_matches_dataframe` | **object dtype 行 Series（`df.iloc[-1]` 真实形态）仍可用且与 DataFrame 路径一致** |
| 3 | `test_feature_order_follows_features_json_not_dataframe` | DataFrame 列顺序反转后结果不变 |
| 4 | `test_predict_p_up_accepts_series_dataframe_and_array` | Series / DataFrame / ndarray 三种输入一致 |
| 5 | `test_probability_always_in_unit_interval` | 20 行全部 ∈ [0,1] 且非常数 |
| 6 | `test_p_up_is_positive_class_probability` / `test_positive_class_index_follows_classes_order` | P(UP) 由 `classes_.index(1)` 决定；`classes_=[1,0]` 时仍取到 P(UP)=0.70 |
| 7 | `test_missing_scaler_raises` / `test_unfitted_scaler_raises` | 缺 scaler / scaler 未 fit → `ScalerMissingError` |
| 8 | `test_feature_scaler_dimension_mismatch_raises` / `test_wrapper_dimension_mismatch_raises` / `test_loaded_artifact_dimension_mismatch_raises` | 5 名 vs 6 维、6 名 vs 7 维、`_validate_loaded_artifacts()` → `InferenceFeatureError` |
| 9 | `test_missing_feature_column_raises_instead_of_zero_fill` | 缺 1 列 → 报错，不再补 0 |
| 10 | `test_nan_and_inf_raise` | NaN / inf → `Non-finite` 报错 |
| 11 | `test_object_dtype_raises` | `.astype(object)` 且含字符串 → `Non-numeric` 报错 |
| 12 | `test_ensure_model_injects_same_scaler_instance` | `ensure_model` 后 `strat_engine.scaler is model_wrapper.scaler`（不重新 load），且概率与 wrapper 一致 |

> 注：#2 是本轮新增的回归测试，来自 1-C 真实工件运行暴露的 `object` dtype 问题（§5.2）。
>
> 注：仓库 `.gitignore:32` 有 `test_*.py` 规则，因此**所有** `tests/test_*.py`（包括本文件）都不会出现在
> `git status` 里 —— 这与仓库既有约定一致，不是遗漏。

---

## 4. 兼容性表

| 接口 / 行为 | 修复前 | 修复后 | 兼容性 |
|---|---|---|---|
| `StrategyEngine(config, model, feature_list)` | 3 参数 | 3 参数 + 可选 `scaler=None` | ✅ 位置参数调用不变（`fx_trade_bot_v685.py:1184`） |
| `StrategyEngine._predict(series)` 返回 | P(UP)，未缩放、缺列补 0 | P(UP)，缩放 + 严格契约 | ⚠️ **数值会变**（这是本次修复的目的）；缺列时由“假预测”变为 `InferenceFeatureError` |
| `StrategyEngine._predict` 异常语义 | 几乎不抛（补 0 兜底） | 契约违约抛错 → `generate_signal()` 记 `[XGB-MISS]` 并 `return None` | ✅ 上层已有 `try/except`（`generate_signal` L139-147、`should_close` L106-109） |
| `ModelWrapper.predict_proba(df)` | 缺列补 0、不缩放 | 严格对齐 + 缩放，返回 `(n, 2)` 概率矩阵 | ✅ 返回类型/形状不变，仅数值更正确 |
| `ModelWrapper.load()` | 只读工件 | 只读 + `_validate_loaded_artifacts()` 维度校验 | ⚠️ 维度不一致时**从静默改为抛错**（预期行为） |
| `ModelWrapper.fit()` / `save()` / 训练流程 | — | **未改动** | ✅ |
| 工件文件（`.json/.joblib/.features.json/.cfg.json`） | — | **未写、未改、未迁移** | ✅ mtime/size 前后一致（§5.3） |
| 阈值 / 仓位 / 执行 / 配置文件 | — | **未改动** | ✅ |
| `utils/ml_confirmation.py` 自有 predict 路径 | 独立 sklearn Pipeline、失败回退 0.5 | 未改动（与本工件无关，不共享 scaler） | ✅ 出本阶段范围 |

## 5. 1-A / 1-C 证据

### 5.1 1-A：工件一致性矩阵（只读）

`/tmp/phase1a.log`：

```
=== trade_model_xgb.cfg.json ===
{ "use_macd": true, "model_type": "xgboost", "target_horizon": 6,
  "train_lookback_bars": 5000, "required_bars": 20, ... }

=== .features.json === 37 features
['ret_1h','ret_3h','ret_6h','ret_12h','ret_log','vol_12h','vol_24h','vol_48h','body',
 'upper_wick','lower_wick','range','direction','atr','atr_pct','atr_percentile','atr_ma',
 'atr_expanding','atr_ratio','rsi','rsi_slope','adx','MACD_12_26_9','MACDh_12_26_9',
 'MACDs_12_26_9','dist_high_24',...,'is_london','is_ny']

cfg.use_macd          : True
MACD cols in features : ['MACD_12_26_9', 'MACDh_12_26_9', 'MACDs_12_26_9']
build(use_macd=True):  43 cols; MACD present: [MACD_12_26_9, MACDh_12_26_9, MACDs_12_26_9]
build(use_macd=False): 40 cols; MACD present: []

features.json missing from build(use_macd=True) : []
features.json missing from build(use_macd=False): [MACD_12_26_9, MACDh_12_26_9, MACDs_12_26_9]

wrapper.cfg.use_macd (after .cfg.json override): True
wrapper.feature_names == features.json        : True
model / scaler / features dims                : 37 37 37

MACD gains in trained model: {'MACD_12_26_9': 14.737, 'MACDh_12_26_9': 12.806, 'MACDs_12_26_9': 14.749}
features with no split/gain: []
```

| 检查 | 期望 | 实测 | 判定 |
|---|---|---|---|
| `model.n_features_in_` | 37 | 37 | ✅ |
| `scaler.n_features_in_` | 37 | 37 | ✅ |
| `len(.features.json)` | 37 | 37 | ✅ |
| `.features.json` 与 `build(use_macd=True)` 列集 | 子集 | 37/37 全部覆盖，缺 0 列 | ✅ |
| `.cfg.json.use_macd` vs 特征集中的 MACD | 一致 | `true` 且三列都在 | ✅（审计 F-05 的“跨批次矛盾”在当前工件上**已不存在**） |
| 运行期 `USE_MACD` | true | `config_profile.json:13`、`run.env:37`、`FeatureConfig(use_macd=cfg_bot("USE_MACD", True))` 均为 true | ✅ |
| MACD 是否被模型实际使用 | 非零 gain | 14.737 / 12.806 / 14.749，且无零增益特征 | ✅ |

> 注意：`data_pipeline.FeatureConfig` 的默认值是 `use_macd: bool = False`（`data_pipeline.py:82`），
> 而 v685 显式传入 `cfg_bot("USE_MACD", True)`。当前配置下一致，但**默认值仍是一个陷阱**（见 §6.3）。

### 5.2 1-C：真实工件上的 wrapper ↔ engine parity（只读）

`/tmp/phase1c_real_artifacts.py` → `/tmp/phase1c_real.log`：用真实 4 个工件 + 合成 M15 行情，
对同一批行分别调用 `ModelWrapper.predict_proba()` 与 `StrategyEngine._predict()`。

```
loaded features: 37
model n_features_in_: 37
scaler n_features_in_: 37
classes_: [np.int64(0), np.int64(1)]
missing declared features: []

row  wrapper_p_up  engine_p_up  diff
 10  0.516551434994  0.516551434994  0.000e+00
100  0.507501304150  0.507501304150  0.000e+00
250  0.496997863054  0.496997863054  0.000e+00
399  0.508087098598  0.508087098598  0.000e+00

legacy (unscaled, zero-fill) p_up = 0.456062
fixed  (scaled, strict)      p_up = 0.508087
delta                          = +0.052025
```

- 两条路径概率**逐位相同**（diff 恒为 0.0）—— 因为它们是同一个 `predict_p_up()`。
- 旧路径（不缩放 + 缺列按 0）与修复路径在同一行上的差值为 **+5.20 个百分点**，
  足以跨越 `base_min_edge=0.50` / `0.51` 这类阈值 —— 即 F-01 会实际改变“发不发单”的结论。
- `missing declared features: []`：在干净行情上，`.features.json` 声明的 37 列全部存在。

> 这一轮曾暴露一个真实的实现缺陷：`df.iloc[-1]` 的 `object` dtype 行会被
> 旧版 `Series.to_frame().T` 转换判成“全部非数值”。已修复（§3.1）并加回归测试 #2。

### 5.3 1-C：工件只读性

脚本在运行前后对 4 个工件取 `(st_mtime_ns, st_size)` 快照并断言未变：

```
artifacts unchanged: True
  trade_model_xgb.json: (1792633081519448609, 797005) -> (1792633081519448609, 797005)  OK
  scaler.joblib: (1792633081521035096, 1455) -> (1792633081521035096, 1455)  OK
  trade_model_xgb.features.json: (1792633081521657902, 540) -> (1792633081521657902, 540)  OK
  trade_model_xgb.cfg.json: (1792633081523297064, 455) -> (1792633081523297064, 455)  OK
```

即：**没有重训、没有覆盖模型、没有触发 legacy pkl → save() 的再导出**。
（当前仓库里已无 `trade_model_xgb.pkl`，`load()` 只走 split 工件分支，该分支不写盘。）

### 5.4 测试记录

```
$ python3 -m pytest tests/test_inference_consistency_v685.py tests/test_rsi_fallback.py -q
.....................                                                    [100%]
21 passed, 1 warning in 3.23s          # 16 个新测试 + 5 个 RSI 回退测试
```

单文件：

```
$ python3 -m pytest tests/test_inference_consistency_v685.py -q -s
...............                [100%]
15 passed ... (修复前)
16 passed in 2.65s             (加入 mixed-dtype 回归测试后)
```

静态检查：

```
$ python3 -m py_compile data_pipeline.py strategy_decision.py fx_trade_bot_ml.py tests/test_inference_consistency_v685.py
EXIT=0
$ python3 -m flake8 --max-line-length=100 tests/test_inference_consistency_v685.py
EXIT=0                                     # 新文件干净
$ python3 -m flake8 --max-line-length=100 data_pipeline.py
F401 typing.Dict / datetime.datetime / datetime.timezone (L11-13)   ← 既有
E402 module level import (L31-33)                                   ← 既有
F841 pip (L167) / W292 EOF newline (L842)                           ← 既有
（本次新增代码无 flake8 告警）
```

> **全量 `pytest tests/` 仍然收集失败（与本次改动无关，属既有问题）**：
> `tests/test_fx_trade_bot_data.py`（`import fx_trade_bot` 时 `parser.parse_args()` 读 `sys.argv`）、
> `tests/test_account.py`（文件内容是一条 shell 命令）、`tests/integration/test_oanda_roundtrip.py`（缺 `from unittest.mock import patch`）、
> `tests/test_market_open.py` / `test_oanda_functions.py`（`utils.oanda_execution.forex_market_closed` 已不存在）、
> `tests/test_trading_core.py`（`check_order_status` 已不存在）、`tests/test_min_slope_ladder.py`（引用已删除的 `fx_trade_bot_v683.py`）。

---

## 6. 1-D：MACD triage（只定位、只根因，不修）

脚本：`/tmp/phase1d_macd.py` → `/tmp/phase1d.log`，`/tmp/phase1d_macd2.py` → `/tmp/phase1d2.log`（均为只读）。

### 6.1 机制 A —— `n < 34` 时 `ta.macd()` 返回 `None`，列**静默缺失**

```
n=20..33 : None
n=34    : ok      ← 门槛 = slow(26) + signal(9) - 1
```

而 `FeatureEngine.build()` 的门槛是 `if self.cfg.use_macd and n > 26:`（`data_pipeline.py:300`），
于是 `n ∈ [27, 33]` 这段区间里 MACD 三列**根本不会生成**，也没有任何日志：

```python
macd = ta.macd(df["Close"])
if macd is not None and not macd.empty:     # None → 直接跳过，无 warning
    df = pd.concat([df, macd], axis=1)
```

对照 `required_bars = 20`（`.cfg.json`）与 `has_min_bars(df, 5)`（`generate_signal`），
**“最少 20 根 K 线”与“MACD 需要 ≥34 根”是矛盾的**。

- 修复前：缺 3 列 → `latest.get(f, 0.0)` → 恒零 → 假预测。
- 修复后：缺 3 列 → `InferenceFeatureError: Missing 3 trained feature column(s)` →
  `generate_signal()` 记 `[XGB-MISS] ... model predict failed` 并 `return None`（**大声失败，不发假单**）。

### 6.2 机制 B —— `Close` 的**单个 NaN 会毒化整段 MACD**（复现 F-03 的“恒零 3 维”）

`pandas_ta` 的 MACD 用 `ewm(adjust=False)`，NaN 会向后传播：

```
NaN at index   0 -> NaN fraction: {MACD: 0.113, MACDh: 0.113, MACDs: 0.113}
NaN at index   5 -> NaN fraction: {MACD: 1.000, MACDh: 1.000, MACDs: 1.000}   ← 整段全 NaN
NaN at index 150 -> NaN fraction: {MACD: 0.610, MACDh: 0.610, MACDs: 0.610}
NaN at index 298 -> NaN fraction: {MACD: 0.117, ...}
```

端到端（真实模型 + `fx_trade_bot_v685` 的后处理 `.replace(inf,NaN).ffill().bfill().fillna(0)`）：

```
MACD after build(), NaN count per column: {MACD_12_26_9: 300, MACDh_12_26_9: 300, MACDs_12_26_9: 300}
MACD after bot post-processing:            {MACD_12_26_9: 0.0, MACDh_12_26_9: 0.0, MACDs_12_26_9: 0.0}

p_up healthy  = 0.428511
p_up poisoned = 0.439582  (delta +0.011072)      ← 3/37 维恒零后概率偏移 1.11pp
exactly-zero feature values in poisoned row: 5/37
```

> 这与审计 F-03 描述的症状（“3/37 维恒零，模型输出落在训练分布外”）**完全一致**，
> 但触发机制不是“`ta.macd` 抛异常被吞”，而是 **NaN 传播 + 下游 `fillna(0)`**。
> 在当前环境（pandas 3.0.6 / pandas_ta 0.4.71b0）`ta.macd` 对 float / object / 常数序列都能正常返回，
> **无法复现“抛异常”那条路径**；可复现的是机制 A（返回 None）与机制 B（NaN 毒化）。

### 6.3 残余风险（**Phase 1 无法覆盖，必须留给 Phase 2**）

| # | 风险 | 为什么严格推理抓不到 | Phase 2 建议方向 |
|---|---|---|---|
| R1 | MACD 被 NaN 毒化 → 下游 `fillna(0)` → 3 维恒零 | 推理入口看到的已经是**有限值 0.0**，不是 NaN/缺列；契约层面“合法” | 在 `build()` 内用 `Close.ffill()` 或 `ewm(ignore_na=True)` 计算 MACD；或在推理前检测“训练期非零、推理期恒零”的特征并告警 |
| R2 | K 线不足 34 根时 MACD 整块缺失 | **能**抓到（缺列报错），但会导致该 pair **完全不出信号** | 把 `required_bars` 提到 ≥ 34（`use_macd=True` 时），或对 `n < 34` 显式跳过并记录原因 |
| R3 | `FeatureConfig.use_macd` 默认 `False` | 若某条调用链忘了显式传值，特征集会静默变成 34 维 → 现在会**报错**（好事），但属于“配置陷阱” | 让 `FeatureConfig` 默认值与训练工件一致，或在 `build()/ensure_model()` 里交叉校验 `use_macd == ("MACD_*" in features.json)` |
| R4 | `.cfg.json` 反向覆盖调用方 `FeatureConfig`（审计 F-07） | 语义层问题，非推理契约 | Phase 2 决定“谁是配置权威”，并让 `ensure_model` 的 `split_ok` 校验 cfg 一致性 |
| R5 | `should_close()` / `select_signals()` 在 v685 中未被调用（F-11） | 不影响本次推理路径 | Phase 2 单独处理 |

---

## 7. 判定与下一步

| 阶段 | 状态 |
|---|---|
| 1-A 工件一致性 | ✅ 通过（37/37/37，`use_macd=true`，MACD 有非零 gain） |
| 1-B 代码修复（单一推理核心） | ✅ 完成（`prepare_inference_matrix` / `predict_p_up` / 严格校验 / 依赖注入） |
| 1-C 验证（单测 + 真实工件 parity + 只读性） | ✅ 通过（16 测试全绿；parity diff = 0.0；工件 mtime/size 不变） |
| 1-D MACD triage | ✅ 完成（机制 A/B 已复现并定位；修复推迟） |
| 总体 | **READY FOR PHASE 2**（未 BLOCKED：工件自洽、无维度冲突、无工件写入） |

**Phase 2 建议优先级**：R1（NaN 毒化 → 恒零）> R2（`required_bars` 与 MACD 门槛）> R3/R4（配置权威）> R5。

---

## 8. 复现方式

```bash
cd /home/qili/projects/ai_training_cnn

# 1) 单测（不联网、不写工件）
python3 -m pytest tests/test_inference_consistency_v685.py -q -s

# 2) 真实工件 parity（只读，运行前后比对 mtime/size）
python3 /tmp/phase1c_real_artifacts.py      # → /tmp/phase1c_real.log

# 3) 工件 × 特征配置矩阵（只读）
python3 /tmp/phase1a_verify.py              # → /tmp/phase1a.log

# 4) MACD triage（只读）
python3 /tmp/phase1d_macd.py                # → /tmp/phase1d.log
python3 /tmp/phase1d_macd2.py               # → /tmp/phase1d2.log
```

> `/tmp/*.py` 是本次的**只读验证脚本**，不属于仓库代码；如需长期保留，Phase 2 可把 1-A 检查固化成
> `tools/verify_inference_contract.py`。



