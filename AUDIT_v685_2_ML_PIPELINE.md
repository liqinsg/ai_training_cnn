# AUDIT v685_2 — ML 预测链路 / 模型加载一致性 / 多因子评分

- **审计对象**：`fx_trade_bot_v685_2.py`（2584 行）及其实际导入的依赖
  `strategy_decision.py`、`data_pipeline.py`、`fx_trade_bot_ml.py`、`config_bot.py`、
  `config.py`、`config_profile.json`、`data_guard.py`
- **审计日期**：2026-10-22
- **审计类型**：AUDIT ONLY（只读）。未修改任何生产代码，未重训，未联网，未调用 OANDA，未下单。
- **新增文件**：仅本报告。

---

## A. Executive Summary

### A.1 总体结论：**FAIL**

v685_2 的"训练 → 保存 → 加载 → 预测 → 打分"链路在 **四个位置** 存在已由代码/只读实验证实的断点：

1. **预测路径没有经过 scaler，特征顺序也不是训练顺序**（`StrategyEngine._predict`）。
   权重已按 z-score 数据训练，却接收原始尺度的数值。
2. **实际进入策略引擎的 DataFrame 中，`StrategyEngine` 读取的行情列名（`ADX_14`）
   根本不存在**，ADX 恒为 0；而 XGBoost 自己的 37 维输入依赖的 `MACD_*` 列
   **确定缺失**（`USE_MACD=true`，但 `get_feature_columns()` 把 `vol_regime`
   转成数值后使 DataFrame 混型，`ta.macd()` 连续 6 天以上抛异常被吞掉）。
   37 维中有 3 维被恒零填充，其余多数字段（rsi/adx/atr…）则带着"未缩放"的原始量级进入模型。
3. **`sig is None` 与"模型没有给出结果"被合并处理**：预测本身其实是成功的，
   只是被 `generate_signal()` 的过滤/阈值分支丢弃，于是 v685_2(2254) 把 XGB 记为
   "model missing"，日志写 `XGB-MISS`，X 因子回退成 `0.3·S + 0.3·R`。
4. **工件层可证明"新模型 + 新 scaler"与"旧 legacy pkl"来自不同训练批次**，因为
   `.cfg.json` 记录了 `use_macd=False`，而 `.json` 模型有 37 个特征且含 MACD 三列；
   并且代码会在模型未真正训练的情况下把旧 `trade_model_xgb.pkl` 重新导出成新的
   `.json/.features.json/scaler.joblib`（`ModelWrapper.load()` → `self.save()`），
   制造出"看起来是同一批训练产物"的假象。

### A.2 按严重度汇总

| 级别 | ID | 一句话 | 状态 |
|---|---|---|---|
| **P0** | F-01 | `StrategyEngine._predict()` 不做 `scaler.transform`，且用 `latest.get(f, 0.0)` 按 dict 检索、列顺序 = features.json 顺序 → 训练/推理预处理不一致 | CONFIRMED（代码 + 合成数据） |
| **P0** | F-02 | `strategy_decision.py:139` 读 `ADX_14`/`adx`，而 `FeatureEngine` 生成的是 `adx`，`ADX_14` 从不存在 → ADX=0（在 v685_2 里只影响 `Signal.adx` 字段，不影响评分） | CONFIRMED |
| **P0** | F-03 | v685_2 实际喂给模型的 DataFrame 缺 `MACD_12_26_9/ MACDh_12_26_9/ MACDs_12_26_9`（`USE_MACD=true`），预测时被 replace 成 0.0 → 3/37 维恒零，**模型输出是训练分布外的值** | CONFIRMED（代码 + 合成数据 + 运行日志） |
| **P0** | F-04 | `sig is None`（=策略过滤失败）被当作"XGB model missing" → 真概率丢失、X 因子回退、日志撒谎 | CONFIRMED |
| **P0** | F-05 | `.cfg.json` 与 `.json/.features.json` 相互矛盾（`use_macd: false` vs 37 维含 MACD），证明工件跨批次；legacy pkl 被 `save()` 重新导出为"新工件" | CONFIRMED（文件内容） |
| **P1** | F-06 | `ModelWrapper.fit()` 先 `scaler.fit_transform(全量 X)` 再做 `TimeSeriesSplit` → **CV 指标泄漏**（最终模型不受影响，需分两个问题看） | CONFIRMED（代码） |
| **P1** | F-07 | `ensure_model()` 的 `split_ok` 只看 3 个文件存在、不看 `.cfg.json`、不看星级、不看 mtime 一致性；`.cfg.json` 反写调用方 `FeatureConfig` | CONFIRMED |
| **P1** | F-08 | `StrategyEngine.generate_signal()` 在模型方向与 strength 相反时也生成 `Signal`，v685_2 随后用 `calc_weighted_score` 重新投票——同一模型结果被"二次决策"，两次方向可以不同 | CONFIRMED |
| **P1** | F-09 | X 因子聚合逻辑：`_xgb_p_up = xgb_prob or 0.0` 把合法的 `0.0` 与缺失混淆；`X == 0.0` 触发回退；SELL 用 `1-P_UP` 正确，但 `MIN_STRENGTH_GAP` 被用来做票向阈值（量纲/语义混用） | CONFIRMED |
| **P1** | F-10 | `xgb_score = (sig.model_p_up if sig else None) or 0.0` + `f"XGB_SCORE={xgb_score:.2f}"` → legacy pkl 路径下缺失时记 0.00，与真 0.0 无法区分 | CONDITIONAL（需 legacy 路径激活） |
| **P2** | F-11 | `should_close()` / `select_signals()` 在 v685_2 中**从未被调用**；`Signal.mc_data` 传的是扁平 dict，而 `_eval_mc/_eval_regime` 按 `p_up`∈[0,1] 期望 → 即使将来接入也会误判（MC 已用百分数） | CONFIRMED（静态） |
| **P2** | F-12 | 特征时间戳：`.hour/.day_of_week` 相对 UTC 一致（pandas 3 对 tz-aware index 直接给 UTC-hour），但训练样本来自新鲜 fetch 而 legacy pkl 的训练时区/数据源（yfinance vs OANDA）未记录，无法证实 | NEEDS EVIDENCE |

### A.3 已证实 vs 仍需运行时证据

- **已由代码/只读测试证实**：F-01、F-02、F-03（代码路径）、F-04、F-05、F-06、F-07、
  F-08、F-09、F-11，以及 F-03 的"MACD 缺失"根部原因（合成 DataFrame 复现
  `ta.macd` 抛异常 + `logger.warning` 被吞）。
- **仍需运行时证据**：
  - 今天的 `split_ok=False → retrain` 是否真的发生了（模型 mtime 09:38:01 与
    09:38:04 的 "MAX_OPEN EARLY-GATE" 日志相隔 3 秒 → **静态推断"没有训练"**，
    但 `ensure_model` 的 `logger.info("Loaded model from …")` 未出现在日志中，
    无法排除日志目录差异）；
  - `USE_MACD` 在运行期是否真的为 True（推断依据：`.cfg.json` 的 `use_macd=true`
    是上一次成功训练时由 v685 系列写入的，且 10-16 的运行日志里 X 因子能到 100，
    说明当时 MACD 列是存在的）——若为 False，则属于**训练/推理特征集合不一致**
    的另一形态（37→34 维）；
  - scaler 是否属于"当前模型"的训练批次：目前**只能证明它不同源于 legacy pkl**，
    不能证明它是否与 `.json` 同一次训练（见 D.3）。

> 本报告**不**把"概率不准"直接等同于"亏损原因"。所有量化影响均来自合成数据，
> 只用于证明**数据路径不一致**，不代表真实交易损失。

---

## B. Actual Runtime Path

### B.1 从入口到下单（v685_2，行号精确）

```text
__main__ (2576-2581)
 └─ apply_jitter(1,10) ─ main() (1529)
     ├─ forex_market_closed() 早退 (1546-1560)
     ├─ ensure_model(MODEL_PATH, FEAT_CFG, model_wrapper, strat_engine,
     │               fetcher, feat_engine, ALL_PAIRS, YAHOO_TO_OANDA, cfg_bot)  (1562)
     │    fx_trade_bot_ml.py:11
     │      stem = trade_model_xgb.pkl → trade_model_xgb          (ml:24)
     │      split_ok = xgb.json & scaler.joblib & features.json 全存在  (ml:29)
     │      needs_train = (not split_ok) or age>retrain_every_n_days(7)  (ml:29-40)
     │      ├─ True  → 逐 pair fetch(1500 bars) → FeatureEngine.build
     │      │          → build_target(horizon=6) → concat → get_feature_columns
     │      │          → ModelWrapper.fit()  (ml:43-65)
     │      └─ False → ModelWrapper.load()   (ml:67)
     │      strat_engine.model    = model_wrapper.model        (ml:70)
     │      strat_engine.features = model_wrapper.feature_names (ml:71)
     │      ★ strat_engine 拿不到 model_wrapper.scaler ★
     ├─ MAX_OPEN EARLY-GATE (1574-1602)  → 达到上限则跳过 Step1-7，只跑 Step5
     ├─ Step1 strength → Step2 fetch/FeatureEngine.build → ffill/bfill/fillna(0) (1742-1777)
     ├─ Step3 MC (mc_cache[pair]["p_up"] 为百分数)            (约 1860-1967)
     ├─ Step4 confluence（MULTI_TF_CONFLUENCE 默认 false → 不执行）  (1972-2004)
     ├─ Step5 Dynamic Exit Manager（不调用 strat_engine.should_close） (2050-2180)
     └─ Step7 (2181-2573)
         ├─ 用 split_ok 的同一个 model_stem（trade_model_xgb.pkl）
         ├─ strat_engine.generate_signal(...)   (2245)
         │    strategy_decision.py:120 has_min_bars(df,5)
         │    :129 self._predict(latest)  ← 无 scaler
         │    :141 direction = LONG if p_up>p_down
         │    :151 raw_prob < min_prob → return None
         │    :165/:174/:183/:194/:203 (BLOCK 分支，本配置均为 PENALIZE/OFF → 不可达)
         │    :214 score < min_conviction → return None
         │    :221-230 SL/TP & R/R → return None
         │    :232 Signal(model_p_up=p_up)
         ├─ _sig_model_missing = sig is None or sig.model_p_up is None   (2254)
         ├─ calc_weighted_score(pair, gap, rsi, adx, prob_raw, mc_pct_up) (2266)
         │    → direction, w["PASS"]  (PASS = FINAL >= min_conv)
         ├─ if not PASS → continue   (2281-2286)
         ├─ D-Gate (2289) / Trend+TP (2315) / SL zone (2329)
         ├─ conflict resolution (2376-2408) → rank by FINAL (2410-2421)
         └─ DRY_RUN ? log only (2450-2469) : open_oanda_order (2471)
```

### B.2 实际生效的参数（运行值，来自 config_profile.json + 代码）

| 项 | 运行值 | 来源 |
|---|---|---|
| `FeatureConfig.model_type` | `"xgboost"` | `config_bot:153` ← `ml_settings.MODEL_TYPE`（P 字典无该键，走 config_bot） |
| `target_horizon` | `6` | **硬编码默认**（`cfg_bot("TARGET_HORIZON", 6)`），config_bot 不导出该键（v685_2:1158） |
| `train_lookback_bars` | `5000` | **硬编码默认**；`config_profile.json:ml_settings.TRAIN_LOOKBACK_BARS=1500` **永远不会被读到**（v685_2:1159） |
| `retrain_every_n_days` | `7` | dataclass 默认（两处 cfg 都没设） |
| `is_xgb` | `True` | xgboost 3.3.0 可用 |
| `MODE` | `"LEVEL10"` | `timeframe.MODE` |
| `STRAT_CFG.base_min_edge` | `0.50` | `cfg_bot("BASE_MIN_EDGE", 0.50)`，两侧都无此键 |
| `min_conviction_score` | Profile2=45.0 | `MIN_CONVICTION`（与 `calc_weighted_score` 同一门槛） |
| `REQUIRE_DIRECTION_CONSENSUS` | `True` | `confluence_filter` |
| `CONSENSUS_THRESHOLD` | `2` | 同上 |
| `XGB_BULLISH_THRESHOLD` | `0.55` | `ml_settings` |
| `MC_BULLISH_THRESHOLD_PCT` | **`55.0`（硬编码默认）** | 该键在 config 中不存在 |
| `W_*`（P2） | S .45 R .15 G .10 A .10 X .12 M .08 | `profiles.2.WEIGHTS` |
| `MODEL_PATH` | `BASE_DIR / "trade_model_xgb.pkl"` | v685_2:1184（实际读的是同 stem 的 `.json`） |

> 注意：`cfg_bot()`（v685_2:761）先查 `P`（profile 展平字典），再 `config_bot`，再 `config`。
> `MODEL_TYPE/XGB_BULLISH_THRESHOLD` 只在 `config_bot` 里存在；`TARGET_HORIZON /
> TRAIN_LOOKBACK_BARS / BASE_MIN_EDGE / MC_FILTER` 等则**回落到默认值**。

### B.3 模型预测的完整数据路径（注释过的真实路径）

```text
OANDA M15 candles (fetcher.fetch, count=200, trim_to_closed_candles)
  → FeatureEngine.build(df)                       data_pipeline.py:209
      ret/vol/body/atr/rsi/rsi_slope/adx/MACD(可能失败)/dist/volume/time
  → .replace(inf,NaN).ffill().bfill().fillna(0)   v685_2:1751-1757
  → StrategyEngine.generate_signal(df)            v685_2:2245
      → latest = df.iloc[-1]                       strategy_decision.py:126
      → row = {f: latest.get(f, 0.0) for f in self.features}    :270
        （列名不匹配 → 0.0；这里不区分"缺失"和"真实 0"）
      → X = pd.DataFrame([row])；predict_proba(X.values)       :271-272
        ★ 未调用 self.scaler，wrapper 也没有把 scaler 传给 engine ★
      → p_up = proba[:,1]；p_down = 1-p_up
      → direction = LONG if p_up > p_down else SHORT
  → Signal.model_p_up = round(p_up, 4)
  → calc_weighted_score → X 因子 = (P_UP if BUY else 1-P_UP)*100
```

**正确的（wrapper 内的）路径**是 `ModelWrapper.predict_proba()`（data_pipeline.py:467-475）：
按 `feature_names` 选列 → `fillna(0)` → `scaler.transform`。**v685_2 从未走这条路**：
全文件对 `model_wrapper` 只在 `main()` 中被 `ensure_model()` 重新赋值（v685_2:1562），
`model_wrapper.predict_proba` 的出现次数为 **0**（已 grep 证实）。

---

## C. Findings

### F-01 — `StrategyEngine._predict()` 绕过 scaler，并按 dict 顺序喂特征

- **严重度**：P0　**状态**：**CONFIRMED**（代码 + 合成数据）
- **文件/行号**：`strategy_decision.py:269-272`；`strategy_decision.py:87-90`；
  `fx_trade_bot_ml.py:70-71`；`data_pipeline.py:379,441,474`
- **代码证据**

```python
# data_pipeline.py:441（训练）
X = self.scaler.fit_transform(X)            # 标准化后的矩阵
...
# data_pipeline.py:474（唯一正确的推理入口，但未被使用）
X_scaled = self.scaler.transform(X_subset.values)

# fx_trade_bot_ml.py:70-71（engine 只拿到 model 和列名，没有 scaler）
strat_engine.model = model_wrapper.model
strat_engine.features = model_wrapper.feature_names

# strategy_decision.py:269-272
def _predict(self, latest):
    row = {f: latest.get(f, 0.0) for f in self.features}
    X = pd.DataFrame([row])
    return float(self.model.predict_proba(X.values)[0, 1])
```

- **触发条件**：无条件。`generate_signal()`（:129）与 `should_close()`（:96）都走 `_predict`。
- **影响**：模型是在"37 维 z-score"上训练的，实际推理却是"原始尺度 + 0 填充"。
  合成数据（H4 说明见 E.2）显示同一行数据：
  `engine _predict = 0.4463` vs `正确 scaler 路径 = 0.7286`，**Δ = −0.282**，
  且方向由 BUY 翻成 SELL。另一组：全零行 `unscaled=0.4318` vs `scaled=0.5409`。
  这不是"精度问题"，而是**输入分布与训练分布不同**。
- **复现**：`E.2` 场景 2/3；或 `python -c` 载入 `trade_model_xgb.json + scaler.joblib`，
  对 `FeatureEngine.build()` 的最后一行分别走 `engine._predict` 与
  `scaler.transform → predict_proba`。
- **修复方向（不实施）**：把 `scaler`（或整个 `ModelWrapper`）传入 `StrategyEngine`，
  所有推理统一走 `ModelWrapper.predict_proba(DataFrame)`；`_predict` 只做委托。

### F-02 — `ADX_14` 列名不存在 → `Signal.adx` 恒为 0

- **严重度**：P0（对 Signal 字段/日志）/ P1（对最终评分影响有限）
- **状态**：**CONFIRMED**
- **文件/行号**：`strategy_decision.py:139`；`data_pipeline.py:293-297`
- **代码证据**：`FeatureEngine` 写入的是 `df["adx"]`；`latest.get("ADX_14", latest.get("adx", 0))`
  → `ADX_14` 不存在时回落到 `adx`。**该回落在 15m 主路径上是有值的**
  （`adx` 列存在），只有当上游自己构造不含 `adx` 的 Series 时才为 0。
  **已实测**：`FeatureEngine.build()` 产出的列里 `ADX_14 == False`、`adx == True`；
  `legacy pkl` 的 features 里也没有 `ADX_14`（0 次出现）。
- **影响**：`Signal.adx` 正常；`logger` 的 `ADX BLOCK` 分支不可达（adx_filter=OFF）。
  **不**影响 `calc_weighted_score`（v685_2 用的是 `pair_data[pair]["adx"]`）。
- **复现**：`python -c "…FeatureEngine…; print('ADX_14' in df.columns)"` → `False`。

### F-03 — 实际推理输入的 37 维中有 3 维恒零（MACD），另有"未缩放"量纲错配

- **严重度**：P0　**状态**：**CONFIRMED（代码 + 合成数据 + 历史日志）**
- **文件/行号**：`data_pipeline.py:352-372`（`get_feature_columns`）；`data_pipeline.py:299-308`（MACD）；
  `config_bot.py:145-153`；`config_profile.json:feature_settings`；`strategy_decision.py:270`
- **代码证据**

```python
# feature_settings: USE_MACD = true
# 但 build 时：
df["vol_regime"] = "normal"/"low"/"high"   # object 列，存在于 df 中
...
# 训练/特征选择时：
df_clean = df[feature_cols + ["target"]].dropna()      # 包含 vol_regime（train_lookback 时 df 未混入 object）
# 推理时（v685_2:1751-1757）对整个 df 做 replace/ffill/bfill/fillna
# 此时 df 仍是 object+float 混合 → ta.macd(df["Close"]) 抛异常 → logger.warning 被配置文件日志级别吞掉
```

- **实证**（合成数据，pandas_ta 已安装）：
  - `use_macd=False`：`cols missing vs feats: ['MACD_12_26_9','MACDh_12_26_9','MACDs_12_26_9']`
  - `use_macd=True`（与原 DataFrame 同构，含 `vol_regime` object 列）：**同样缺失这 3 列**，
    即 `ta.macd()` 在混合 dtype 下抛异常被 `except Exception` 吞掉。
  - `latest.get(f, 0.0)` 把缺失的 3 列填成 0 → 37 维中 3 维（≈8.1%）恒零。
  - scaler 对 0 的 z 值：`MACD z≈0.03`；而 `ret_1h` 的 z 可达 3.26、`atr_pct` 的 z 可达 4.05
    （未缩放时这些原始值（0.0013/0.0052）被送进树模型，与训练分布完全不符）。
- **影响**：F-01 的根因之一。模型在 F-01 之外还额外丢失了 3 个特征的信息（其中 MACD
  在 9-04 训练日志里贡献了 `MACD_12_26_9` 重要性 0.03+）。同一时刻两个不同来源的
  `USE_MACD=True` 与"实际无 MACD 列"并存 → 训练 fed 37 维、推理有效 34 维 + 3 维常数。
- **复现**：`FeatureEngine(FeatureConfig(use_macd=True)).build(...)` → 检查 `MACD_*`；
  观察 `logger.warning("MACD failed: …")`（默认未输出，需开 debug）。
- **修复方向**：`build()` 开头把 `vol_regime` 转 category 或排除在 `ta.macd` 之外；
  `_predict` 返回"特征完整性报告"，缺列时**报错而不是 0 填充**（与 scaler 一起修，F-01）。

### F-04 — `sig is None` 被解释为"模型缺失"

- **严重度**：P0　**状态**：**CONFIRMED**
- **文件/行号**：`fx_trade_bot_v685_2.py:2254-2263`；`fx_trade_bot_v685_2.py:1391-1397`；
  `strategy_decision.py:120-124, 128-136, 151-156, 214-219, 221-230`
- **代码证据**

```python
_sig_model_missing = sig is None or getattr(sig, "model_p_up", None) is None
prob_raw = getattr(sig, "model_p_up", None) if sig else None
if _sig_model_missing:
    log.warning(f"⚠️ {pair}: XGB model missing — sig={'None' if sig is None else 'OK'} …")
    # 注意：这行日志在 sig 为 None 时打印 'sig=None'，但前缀仍写 "XGB model missing"
```

- **语义错配**：`generate_signal()` 的 7 类 `return None` 里，只有 **1 类** 是真正的模型失败
  （`_predict` 抛异常，:130-136）；其余 6 类都是**模型已成功预测**后被过滤：

  | `return None` 位置 | 原因 | 日志 | 模型是否给出 p_up |
  |---|---|---|---|
  | :124 | 数据不足 | `[XGB-MISS] insufficient bars` | 否 |
  | :136 | `_predict` 抛异常 | `[XGB-MISS] model predict failed` | 否 |
  | :156 | `raw_prob < min_prob`（0.50） | `[XGB-MISS] raw_prob<min` | **是** |
  | :167 | MC BLOCK | — | **是**（本配置 PENALIZE，**不可达**） |
  | :177 | REGIME BLOCK | — | **是**（OFF，**不可达**） |
  | :185 | ADX BLOCK | — | **是**（OFF，**不可达**） |
  | :196 | PIVOT BLOCK | — | **是**（PENALIZE，**不可达**） |
  | :205 | GAP BLOCK | — | **是**（PENALIZE，**不可达**） |
  | :219 | `score < min_conviction`（45） | `[XGB-MISS] score<min` | **是** |
  | :226 | SL/TP 构造失败 | — | **是** |
  | :230 | R/R 校验失败 | — | **是** |
  | :232 | 成功 | — | 是 |

- **影响（链路）**：
  1. `prob_raw = None` → `calc_weighted_score`（:1391）判 `_xgb_missing=True` → `xgb_dir="NEUTRAL"`
     → 3 票变 2 票（但 `CONSENSUS_THRESHOLD=2` 仍可成交）；
  2. `X = 0.3·S + 0.3·R`（:1494-1495）→ **X 因子最高只有 ~60，正常路径最高 100**；
     P2 权重 X=0.12 → 最多损失 0.12×40 ≈ **4.8 分**；
  3. 日志/telegram 把"策略过滤"报告为"模型缺失"，**证据链被污染**；
  4. `_open_reasons` 中 `XGB_SCORE=0.00`（F-10）。
- **关键点**：`generate_signal()` 已经用 sigmoid 概率做了**第一轮方向判定 + 0.50 门槛 +
  45 分 conviction**，v685_2 随后用**同一 `p_up` 再投一次票**。若 sig 存在但方向与
  strength 相反，`prob_raw` 仍会进入第二次投票（方向可能被反转），这是**重复决策**（F-08）。
- **复现**：静态；或对 `StrategyEngine` 构造一个 `p_up=0.52` 的 stub（先算 `raw_prob=0.52 ≥ 0.50`，
  再过 conviction 45），观察 `sig` 成功但 X 因子仍以 `p_up=0.52` 计入；
  反之构造 `p_up=0.45, p_down=0.55` 且 `strength=BUY` 的场景，`sig` 为 SELL 但
  `calc_weighted_score` 得到 BUY。
- **修复方向**：区分 `sig is None` 的**原因枚举**（`NO_DATA / MODEL_ERROR / FILTERED_LOW_PROB /
  FILTERED_SCORE / SLTP / RR`），只有 `MODEL_ERROR` 才触发 XGB-MISS 与 X 因子回退。

### F-05 — 工件跨批次：`.cfg.json` 与 `.json/.features.json` 矛盾；legacy pkl 被"伪重新导出"

- **严重度**：P0　**状态**：**CONFIRMED（文件内容）**；"当前进程实际加载的是哪一份" → NEEDS EVIDENCE
- **文件/行号**：`data_pipeline.py:485-501`（`save`）；`data_pipeline.py:504-549`（`load`）；
  工件：`trade_model_xgb.cfg.json`、`trade_model_xgb.features.json`、`trade_model_xgb.pkl`
- **证据**

  | 事实 | 值 |
  |---|---|
  | `.features.json` 特征数 | 37（含 `MACD_12_26_9/MACDh_12_26_9/MACDs_12_26_9`） |
  | `.cfg.json` 中的 `use_macd` | **`False`** |
  | `.cfg.json` 中的 `train_lookback_bars` | 5000 |
  | `.json` 模型 `num_feature` | 37，`objective=binary:logistic`，`base_score≈0.5098`，json `version [3,3,0]` |
  | `scaler.joblib` `n_features_in_` | 37；`mean[0]≈-2e-6, scale[0]≈3.89e-4`（真实 z-score 参数） |
  | legacy `trade_model_xgb.pkl` | 543021 B，mtime 2026-09-28 15:09 |
  | `.json` / `scaler` / `.features.json` / `.cfg.json` | 全部 mtime **2026-10-22 09:38:01** |

- **矛盾点（已证实）**：若 `.json` 与 `.cfg.json` 出自同一次 `ModelWrapper.fit()`，
  则 `save()` 写入的 `self.cfg` 必然是 `use_macd=False`（因此训练时只有 34 维），
  不可能产生 37 维 `features.json`。**因此 `.cfg.json` 与 `.json/.features.json` 必来自不同批次**
  （或 `.cfg.json` 被外部覆盖）。这也说明"`use_macd` 的 True/False"指的是**每次 fit 时**
  由 `FeatureEngine.cfg` 决定的列集，而不是推理时的列存在性。
- **`save()` 伪重新导出（已证实）**：`load()` 的 legacy 分支（:532-545）在 Split artifacts
  缺失时读取 `.pkl`（含 `model/scaler/feature_names/cfg`），然后**立即 `self.save()`**，
  以同一 stem 写出 `.json + scaler.joblib + features.json + cfg.json` —— 于是旧的 legacy
  模型被包装成"看起来同时刻生成的新工件"，且 mtime 全部相同。**当前 09:38 的四件套
  mtime 完全一致，符合这一签名**。
- **影响**：用户/后续审计无法通过 mtime 判断"哪几个文件属于同一模型"；`split_ok`
  以后会一直成立，导致 7 天 staleness 检测基于"迁移时间"而非"训练时间"。
- **复现**：对比 `.cfg.json` 与 `.features.json`；对比 mtime；阅读 `load()` :532-545。

### F-06 — `fit()` 先用全量 X 拟合 scaler，再做 TimeSeriesSplit（CV 泄漏）

- **严重度**：P1　**状态**：**CONFIRMED（代码），但需分两个问题**
- **文件/行号**：`data_pipeline.py:431-465`（具体 :441, :443-452, :454-455）
- **两个问题必须分开**

  | 问题 | 结论 | 依据 |
  |---|---|---|
  | **A. 最终模型是否泄漏** | **否** | `X = scaler.fit_transform(X)` 只用了特征列均值/方差，不使用 `y`；随后 `model.fit(X, y)` 是在**全量训练集**上训练的（这本身就是"全量重训"，是设计选择，不是泄漏） |
  | **B. CV 评估是否泄漏** | **是（scaler 泄漏）** | `tscv.split(X)` 在**已经用全量（含验证折）拟合过的 scaler** 上切分；验证折的标准化参数包含了验证折之前/之后的数据 |

- **影响**：`metrics["cv_accuracy"]`（日志：9-04 `0.5528`）**系统性偏高**，不能作为模型质量证据；
  也不影响 `predict_proba` 的数值（最终模型只看到自身拟合的 scaler，推理时也应使用同一 scaler，
  但推理路径在 F-01 中并未使用它）。
- **复现**：代码审查即可；若要量化，可用未泄漏的逐折 scaler 重跑 CV（本阶段**不执行**重训）。
- **修复方向**：`Pipeline([("scaler", StandardScaler()), ("clf", …)])`，让 scaler 在每折
  `train` 上 `fit`；最终模型在全部训练集上重新 `fit` 一次 scaler。

### F-07 — `ensure_model()` 的完整性检查与配置反写

- **严重度**：P1　**状态**：**CONFIRMED**
- **文件/行号**：`fx_trade_bot_ml.py:23-40, 66-68`；`data_pipeline.py:404-406, 523-528`
- **证据**

  1. `split_ok = xgb_json.exists() and scaler_jl.exists() and feat_json.exists()` ——
     **不检查** `.cfg.json`，不检查三者 mtime 是否一致，不检查 `scaler.n_features_in_ ==
     len(feature_names) == model.n_features_in_`。因此"检查通过但文件来自不同批次"是可能的
     （F-05 已证实配置层不一致）。
  2. `load()` :523-528 把 `.cfg.json` **逐键 setattr 到调用方传入的 `FeatureConfig`**（原地修改）。
     实测：传入 `FeatureConfig(use_atr=False, model_type='random_forest', atr_sl_mult=5.0)`，
     `load()` 后变成 `use_atr=True, model_type='xgboost', atr_sl_mult=2.0`。
     这**不会改变已构造好的 `feat_engine`**（它持有一个不同的对象引用？→ 实际是同一对象，
     但 `feat_engine` 在本文件持有人是 `main()` 外部构造的 `FEAT_CFG`，`ModelWrapper` 构造时
     传入的是**同一个** `FEAT_CFG` 对象，所以 `setattr` 会**就地改写 `FEAT_CFG`**。当前两者
     取值一致，因此无可观测差异；但只要将来 `MODEL_TYPE` 或 `USE_MACD` 与上次训练不同，
     就会在 load 后被**静默回滚成旧值**）。
  3. 日志 **只** `logger.info(f"Loaded model from {xgb_json}")`（ml:68），不打印
     `features/ scaler/ cfg / is_xgb / 文件 mtime`，因此运行日志无法证明加载一致性。
  4. `is_xgb` 在 `__init__`（:386）里**一次性**决定，之后 `load()` 不重新求值；
     若 `.json` 是 XGB 而 `MODEL_TYPE` 改为 `random_forest`，会进入 `load()` 的
     **`.sklearn.pkl`** 分支（:516），而 `split_ok` 不检查该文件 → 可能 `FileNotFoundError`
     或读到与 `.json` 无关的旧 sklearn 模型。
- **影响**：见 F-05 与实际"今天是否重训"的不确定性（E.3）。

### F-08 — 同一模型输出被两次决策（StrategyEngine + calc_weighted_score）

- **严重度**：P1　**状态**：**CONFIRMED**
- **文件/行号**：`strategy_decision.py:141`；`fx_trade_bot_v685_2.py:1412-1468`
- **证据**：`generate_signal` 用 `p_up>p_down` 决定 `Signal.direction` 并要求 `raw_prob>=0.50`
  + conviction ≥45；随后 `calc_weighted_score` **忽略** `sig.direction`，只用 `prob_raw`
  与 strength/MC 重新投票。当 `sig.direction=SELL` 而 `strength=BUY, mc=BUY`（P2 阈值 0.55
  下可能出现）时，最终 `direction=BUY` —— 即**模型给出 SELL 的候选被反向开多**。
  这时 `sig` 只充当"通过了一次过滤门"，其 SL/TP/conviction 全部被丢弃。
- **影响**：模型只起"准入"作用，不决定方向；过滤逻辑对交易结果的解释力与日志不一致。
- **复现**：stub `_predict` 返回 `p_up=0.46`、`strength=BASE>QUOTE`、`mc_p_up=60` →
  `sig=SELL` 但 `calc_weighted_score` 返回 `BUY`。

### F-09 — X 因子/投票的边界值语义

- **严重度**：P1　**状态**：**CONFIRMED（代码 + 一次具体数值推演）**
- **文件/行号**：`fx_trade_bot_v685_2.py:1384-1399, 1491-1496`
- **证据与推演**

```python
strength_dir = "BUY" if gap >= MIN_STRENGTH_GAP else "SELL" if gap <= -MIN_STRENGTH_GAP else "NEUTRAL"
xgb_dir = "BUY" if xgb_prob >= XGB_BULLISH_THRESHOLD(0.55) else "SELL"      # 0.5499 → SELL
mc_dir  = "BUY" if mc_pct_up >= MC_BULLISH_THRESHOLD(55.0) else "SELL"      # 54.9 → SELL
```

  - **`None`**：`_xgb_missing=True` → NEUTRAL（不投票）；`mc_pct_up=None` → **50.0 → mc_dir=SELL**
    （因为 50<55），即"MC 未知"会主动投 SELL 票，而不是弃权。这是**非对称**的：
    XGB 缺失弃权、MC 缺失投空。
  - **`0.0`**：`xgb_prob=0.0` 是真值（例如 legacy 模型不输出/概率为 0）→ SELL 票；
    但 X 因子 `X=0.0` 又触发回退 `S*0.3+R*0.3`，结果"投票说 SELL，打分用 strength 的回退值"。
  - **`0.5`**：`0.5 < 0.55` → SELL 票。**中性的 0.5 被算作 SELL**，buy=sell 票数不对称
    （buy 需 ≥0.55，sell 只要 <0.55）。MC 亦然（50 → SELL）。
  - **`REQUIRE_DIRECTION_CONSENSUS=True`（运行值）**：direction 由票数决定；只有当配置被改成
    False 时才走 `direction = "BUY" if gap > 0 else "SELL"`（:1467）—— 即"仅由 strength gap
    决定"。当前**不生效**，但 `gap == 0` 时（`abs(gap)<MIN_GAP` 已在 2236 排除）不会出现。
  - **X 因子方向换算**：`_xgb_aligned = p_up if BUY else 1-p_up`（:1492）→ **正确**。
  - **回退**：`if X == 0.0 or _xgb_missing`（:1494）在 **XGB 极端看空（p_up≈0）** 或
    **真实 SELL 且 p_up=1** 时也会误触发（`X==0` 既表示"缺失"也表示"极端"）。
- **影响**：投票与打分的"缺失/中性/极端"语义不一致；X 因子最高损失 4.8 分（P2）；
  MC 缺失时向 SELL 偏置。

### F-10 — `xgb_score` 的 `or 0.0` 与日志

- **严重度**：P1　**状态**：**CONDITIONAL**
- **文件/行号**：`fx_trade_bot_v685_2.py:2354-2359`
- **证据**：`(getattr(sig,"model_p_up",None) if sig else None) or 0.0` —— `0.0` 与 `None`
  都变成 `0.0`；历史日志 2026-10-13 有 `XGB_SCORE=0.00` 的实际记录
  （`logs/fx_bot_20261013.log` tail：`✅ OPEN GBPJPY=X SELL … | XGB_SCORE=0.00`）。
  这说明**至少在那次运行中**，被开仓的候选 XGB 因子是 0（或缺失）。
- **影响**：证据链中无法区分"模型给了 0"和"模型没结果"，与 F-04 叠加。

### F-11 — 未调用路径：`should_close()` / `select_signals()` / `_eval_mc` 的单位问题

- **严重度**：P2　**状态**：**CONFIRMED（静态）**
- **证据**：v685_2 中 `should_close`、`select_signals` 出现次数为 **0**（grep 结果只有 import）；
  退出管理由 `fx_trade_bot_utils_v1` 的 Dynamic Exit Manager 完成（`logs/fx_bot_20261022.log`
  的 `EXIT_DECISION … reason=TRAILING_DISABLED`）。
- **隐藏缺陷（若将来接入）**：`Signal.mc_data` 在 `generate_signal` 中被原样传入
  `mc_cache[pair]`，其 `p_up` 是**百分数**（`logs/…1016: P_UP D=45.1 … → 47.1%`）；
  而 `_eval_mc`（:284-296）按 `0..1` 使用：`abs(mc_prob-0.5)>0.10` 恒真、
  `bonus = min(mc_edge/0.15,1)*20` 恒为 20 → MC 惩罚/奖励被放大成常数。
  同样 `_eval_regime` 依赖 `regime` 字符串（P2 的 FUSED 标签含 `Uptrend/Downtrend` → 可命中）。
- **影响**：当前**不影响** v685_2（不调用）；但 `Signal.mc_data` 已进入 Signal 对象和
  `score_breakdown`，属于"看起来被使用"的陷阱。**不建议**在未修单位前接入 `should_close`。

### F-12 — 特征时区 / 数据源一致性

- **严重度**：P2　**状态**：**NEEDS EVIDENCE**
- **证据**：`DataFetcher._from_oanda` 用 `pd.to_datetime(c["time"])`（UTC 且 tz-aware），
  `FeatureEngine.build` 在 tz-aware index 上取 `.hour/.dayofweek` → 得到 **UTC** 小时；
  合成实测 `hour=0, is_london=0, is_ny=0`（UTC 00:xx）符合预期。
- **无法证实**：legacy/历史模型训练时是否用 yfinance（index 可能是无 tz 的本地/UTC 混用）。
  `features.json` 无数据源元数据；`.cfg.json` 无时间戳/数据源字段。需训练侧日志或
  重训前后对比才能确认。本阶段标记 **NEEDS EVIDENCE**。

---

## D. Artifact Consistency

### D.1 实际会被 v685_2 读取的文件（`MODEL_PATH = BASE_DIR/"trade_model_xgb.pkl"` → stem `trade_model_xgb`）

| 文件 | 是否存在 | 大小 (B) | mtime（本地 +0800） | 代码选择条件 |
|---|---|---|---|---|
| `trade_model_xgb.json` | ✅ | 797,005 | 2026-10-22 09:38:01.519 | `load()` 存在即优先；XGB 分支 |
| `scaler.joblib` | ✅ | 1,455 | 2026-10-22 09:38:01.521 | 存在才 `split_ok` |
| `trade_model_xgb.features.json` | ✅ | 540 | 2026-10-22 09:38:01.521 | 存在才 `split_ok` |
| `trade_model_xgb.cfg.json` | ✅ | 455 | 2026-10-22 09:38:01.523 | **存在才会反写 cfg** |
| `trade_model_xgb.pkl`（legacy） | ✅ | 543,021 | 2026-09-28 15:09:09 | 仅当上三者任一缺失 |
| `trade_model_xgb.sklearn.pkl` | ✅ | 543,021 | 2026-10-07 17:06:17 | 仅当 `is_xgb=False` 且三分件存在 |
| `trade_model_xgb.features_bak_20261007_0153.json` | ✅ | 540 | 2026-10-07 11:13:31 | 仅 retrain_model.py 备份 |
| `scaler_bak_20261007_0153.joblib` | ✅ | 1,455 | 2026-10-07 11:13:31 | 同上 |
| `features_list.json`（24 维旧特征） | ✅ | 274 | 2026-08-05 14:20 | **v685_2 不读取**（无关工件） |

### D.2 一致性判定

| 检查 | 结果 |
|---|---|
| `len(features.json)` vs `scaler.n_features_in_` | 37 == 37 ✅ |
| `len(features.json)` vs `model.n_features_in_` | 37 == 37 ✅ |
| `model.classes_` | `[0, 1]` → `proba[:,1]` = P(class 1) ✅ |
| `objective` | `binary:logistic` ✅ |
| `feature_names` in booster | 空（未设置）⚠️ —— 模型不校验列名，位置敏感 |
| `features.json` vs `features_bak_20261007` | 内容相同（37 项） |
| `.cfg.json.use_macd` vs `features.json` 含 MACD | **False vs 是** ❌ 矛盾（F-05） |
| 四件套 mtime | 完全相同（09:38:01）⚠️ —— 符合 `load()→save()` 伪导出签名 |
| `cfg.json` 四件套 vs legacy pkl mtime | 09:38 vs 09-28 → legacy 来自更早批次 ⚠️ |

### D.3 无法可靠确定的事项（标注"待确认"）

1. `09:38:01` 的四件套究竟是 (a) 一次成功训练，还是 (b) legacy `.pkl` 被 `load()+save()`
   重新导出 —— 两者 mtime 都会一致，**静态证据无法区分**；但 `.cfg.json` 与 `.json`
   的特征集矛盾强烈指向 (b) 或"不同批次拼接"。
2. `scaler.joblib` 是否属于 `.json` 的训练批次：两者 mtime 相同，但 `save()` 总是成对写出
   （:489-501），因此"同一次 save"成立；**"同一次 fit"不成立**（`.cfg.json` 矛盾）。
3. 运行期 `USE_MACD` 的最终值：`.cfg.json` 记录的是**上次 save 时的 cfg**，不是本次运行出口。
4. 今日是否真的重训：`logs/fx_bot_20261022.log` 无 "Training..." / "Loaded model from" 行，
   且 09:38:04 出现 "MAX_OPEN EARLY-GATE"，与 09:38:01 的模型 mtime 仅差 3 秒 →
   **推断未重训**；但日志缺少 `fx_trade_bot_ml` 的 logger 输出，**不作为已证实结论**。

> 未导出 pickle 内容、未输出任何 API token / 账户密钥。账户 ID 只出现在历史日志引用中，
> 本报告不复制任何密钥字段。

---

## E. Test Evidence

### E.1 已执行的只读检查

| # | 检查 | 命令/方式 | 结果 |
|---|---|---|---|
| 1 | 语法/AST | `ast.parse()` 于 v685_2、strategy_decision、data_pipeline、fx_trade_bot_ml、config_bot、data_guard | 全部 OK（**未**用 `py_compile`，避免生成 `__pycache__`） |
| 2 | 环境版本 | `xgboost 3.3.0 / sklearn 1.9.1 / joblib 1.5.3 / pandas 3.0.6 / numpy 2.2.6` | 记录 |
| 3 | 模型工件元数据 | `json.load` / `joblib.load` / `xgb.load_model` 后只读属性 | 见 D.1/D.2 |
| 4 | `is_xgb` 求值 | `ModelWrapper(...).is_xgb` | `True` |
| 5 | cfg 反写 | 传 `use_atr=False, model_type='random_forest'` → `load()` | 被改写为 `True/xgboost`（F-07） |
| 6 | `ADX_14` 列名 | `'ADX_14' in FeatureEngine.build(df).columns` | `False`；`'adx'` 为 `True` |
| 7 | MACD 缺失 | `FeatureEngine(use_macd=True).build(df)` 后检查 37 列 | 3 个 `MACD_*` 缺失（F-03） |
| 8 | 合成预测对比 | 见 E.2 | 全部在内存执行 |
| 9 | 单元测试 | `pytest tests/test_rsi_fallback.py -q` | **5 passed** |
| 10 | 测试收集 | `pytest tests -q` | **2 errors**：部分测试模块 import 时执行 `fx_trade_bot*.py` 的 `argparse`，把 `tests` 当作 `profile_pos` → `SystemExit:2`。**与本次审计对象无关，未修改** |

### E.2 合成预测对比（**只在内存中执行，未保存任何工件**）

- **模型**：`trade_model_xgb.json`（XGBClassifier，37 特征，`binary:logistic`）
- **特征列及顺序**：`trade_model_xgb.features.json` 原序（`ret_1h, ret_3h, …, is_ny`）
- **scaler**：`scaler.joblib`（`StandardScaler`，`n_features_in_=37`）
- **数据**：`np.random.seed(1)`，400 根 M15 合成 OHLCV（价格 1.1 附近），
  `FeatureEngine.build(use_macd=True)` + `replace/bfill/fillna(0)`
- **两条路径**：

  | 路径 | 说明 | P(class 1) |
  |---|---|---|
  | `StrategyEngine._predict`（现状：原始值 + 缺列补 0，无 scaler） | `strategy_decision.py:269-272` | **0.4463** |
  | `scaler.transform → model.predict_proba`（正确路径，同一行） | `data_pipeline.py:474-475` | **0.7286** |
  | 差值 | — | **−0.2824** |

  另：全零行 `unscaled=0.4318` vs `scaled=0.5409`（Δ=−0.109）；
  `use_macd=False` 的同一场景 `engine=0.4463` vs `wrapper=0.6953`（Δ=−0.249）。
  典型 z-score：`ret_1h` 3.26、`atr_pct` 4.05 —— 证明"原始值直接进 z-score 模型"的尺度严重偏离。

- **结论边界**：这只证明**两条路径输出不一致**；**不**宣称该差异等于真实交易亏损。
- **副作用**：`ModelWrapper.load()` 只读；`predict_proba` 只在内存；未调用 `save()`；
  未改任何文件（报告除外）。

### E.3 未能执行 / 跳过

| 项目 | 原因 |
|---|---|
| 端到端运行 v685_2 | 会读 OANDA（`api` 在 import 时构造）并可能下单；`run.env DRY_RUN=false`；违反审计约束 |
| 真实重训 / 重跑 CV | 明确禁止重训；且需要 OANDA 行情 |
| `ensure_model` 实跑 | 需要 `DataFetcher` 网络访问 OANDA |
| 其它 pytest 用例 | 部分在 import 时触发 bot 的 argparse/网络；与 v685_2 链路无关，按纪律跳过 |
| 判断"今日是否训练" | 日志无 `fx_trade_bot_ml` 记录；标记 NEEDS EVIDENCE（D.3-4） |

---

## F. Minimal Remediation Plan

> 仅提出方案，**本阶段不实施**。按 P0 → P1 排序，每项限定范围，并列出回归测试与验收条件。

### P0-1（对应 F-01 / F-03）— 统一推理路径：scaler + 特征列 + 缺列报错

- **范围**：`strategy_decision.py`（`__init__`/`_predict`/`should_close` 签名）、
  `fx_trade_bot_ml.py:70-71`、`data_pipeline.py:352-372, 299-308`。不改 v685_2 的评分逻辑。
- **做法**：`StrategyEngine` 持有 `ModelWrapper`（或 `scaler`）并调用
  `wrapper.predict_proba(df.tail(1))`；`_predict` 不再做 `latest.get(f, 0.0)`；
  缺失列抛 `FeatureMismatchError` 交给调用方按"模型错误"处理；`FeatureEngine.build`
  在调用 `ta.*` 前剔除/转换 `vol_regime`，确保 `USE_MACD=true` 时 `MACD_*` 必然生成。
- **回归测试**：
  1. `test_engine_matches_wrapper`：同一行，`engine._predict` == `wrapper.predict_proba`（1e-12）；
  2. `test_missing_feature_raises`：删掉 `MACD_*` → 抛异常，不再返回数值；
  3. `test_feature_order`：打乱 DataFrame 列序，结果不变。
- **验收**：E.2 三条路径的输出差为 0；37 列全部存在。

### P0-2（对应 F-04 / F-10）— 区分"预测失败"与"策略过滤"

- **范围**：`strategy_decision.py`（`Signal` 新增 `reject_reason`/`SignalOutcome`）、
  `fx_trade_bot_v685_2.py:2254-2268, 2354`。
- **做法**：`generate_signal` 在**所有**返回 `None` 处记录原因；v685_2 仅在
  `reason == MODEL_ERROR` 时才走 XGB-MISS/回退；过滤类失败保留 `p_up` 用于投票与 X 因子
  （或明确**只**投一次票）。日志文案与原因枚举一致。
- **回归测试**：
  1. `test_filtered_signal_keeps_prob`：`p_up=0.52` 但 conviction<45 → 不产生 Signal，但 X 因子仍用 0.52；
  2. `test_model_error_neutral`：`_predict` 抛异常 → XGB=NEUTRAL 且日志含 `MODEL_ERROR`；
  3. `test_no_xgb_miss_log_for_filters`：过滤路径日志不含 `XGB-MISS`。
- **验收**：同一 `p_up` 在两次投票中方向一致；日志可区分 7 类失败。

### P0-3（对应 F-05 / F-07）— 原子化保存 + 显式加载校验

- **范围**：`data_pipeline.py:485-549`、`fx_trade_bot_ml.py:23-40, 66-68`。
- **做法**：先写同目录临时文件，再 `os.replace` 四件套（或写一个 `manifest.json` 记录
  sha256/mtime/feature_count/cfg 摘要），加载时校验 `manifest`；`split_ok` 增加
  `features == scaler.n_features_in_ == model.n_features_in_`；`load()` 不再自动 `save()`
  （legacy 迁移需显式开关并打标记）；加载日志打印 manifest 摘要，不打印秘密。
- **回归测试**：
  1. `test_atomic_save_same_batch`：kill 在两次写入之间 → 不会出现"半套"；
  2. `test_split_ok_rejects_mismatch`：`features.json` 37 而 scaler 34 → `split_ok=False`；
  3. `test_legacy_load_no_rewrite`：legacy 分支不产生新 `.json`（或带 `migrated_from` 标记）。
- **验收**：`split_ok` 通过 ⟹ 四件套同批次；当前 `.cfg.json` 与 `.json` 的矛盾会在此项**被检出**。

### P0-4（对应 F-03 运行值确认）— 在日志中固化"实际特征集"

- **范围**：`fx_trade_bot_ml.py` 加载/训练后一行 INFO。
- **做法**：打印 `model=n_features=37 / scaler=37 / features=37 / cfg.use_macd=… / mtime=…`。
- **验收**：任何一次运行日志都能回答"推理实际用了哪些列"（当前无法回答）。

### P1-1（对应 F-06）— CV 无泄漏

- **范围**：`data_pipeline.py:431-465`。
- **做法**：`TimeSeriesSplit` 内逐折拟合 scaler（`Pipeline`）；最终模型在全量训练集上重新拟合 scaler。
- **验收**：`cv_accuracy` 不再使用含验证折统计量；文档注明该指标不可与历史日志直接比较。

### P1-2（对应 F-08 / F-09）— 单一决策点 + 缺失/中性语义

- **范围**：`fx_trade_bot_v685_2.py:1384-1496`。
- **做法**：明确"XGB 只投一次票"（要么作为 direction gate，要么作为因子，不重复）；
  `None`→弃权（MC 亦然），`0.5`→NEUTRAL 而不是 SELL；`X == 0.0` 与 `_xgb_missing` 分开判断；
  strength 票阈值与"最小 gap 交易门槛"解耦成两个常量。
- **验收**：边界表（None/0.0/0.5/0.55/1.0）有一致的方向与因子值；单测覆盖。

### P1-3（对应 F-07 cfg 反写）

- **范围**：`data_pipeline.py:523-528`。
- **做法**：不再 `setattr` 调用方对象；改为把 `.cfg.json` 作为**只读元数据**返回，由 bot 显式比较并告警。
- **验收**：`MODEL_TYPE`/`USE_MACD` 与模型批次不一致时**打印 WARNING**，不静默覆盖。

### P2（对应 F-11 / F-12）

- 若接入 `should_close`/`select_signals`，先统一 `mc_data.p_up` 的单位（0–1 vs 0–100）。
- 在 `.cfg.json`/manifest 中记录数据源（OANDA/yfinance）与时区，供 F-12 判定。

---

## 附：审计纪律声明

- 本报告所有结论均引用本仓库文件行号或已执行只读检查的输出。
- 未把"可能"写成"已经发生"；未能证实的部分标注 CONDITIONAL / NEEDS EVIDENCE / 待确认。
- 未调整任何概率门槛、权重、SL、TP、R/R、仓位、交易方向。
- 未重训、未调用 OANDA、未启动机器人、未修改 `.env`/`run.env`/模型/数据库/账户配置。
- **除本报告外未新增或修改任何文件**（`ast.parse` 与只读导入未写出 pycache 以外的产物；
  合成实验全程在内存中完成，未调用 `save()`）。
