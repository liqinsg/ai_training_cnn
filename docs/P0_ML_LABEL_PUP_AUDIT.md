# P0 只读审计报告 — ML 模型质量：标签不平衡、P(UP) 与交易价值

- **项目**：`/home/qili/projects/ai_training_cnn`（branch `HEAD 100a5e8`）
- **审计类型**：**只读（READ-ONLY）**。未修改任何源码/配置/`.env`/`run.env`/cron/模型文件；未重训；未调用任何 OANDA 交易 API；未安装依赖。
- **审计时间**：2026-10-23
- **离线工作目录**：`/tmp/p0_audit/`（所有脚本与输出均在此，可复现，见 §2.6）
- **Python 解释器**：`~/miniconda3/envs/ai-sprint/bin/python`（xgboost 3.3.0 / sklearn 1.9.1 / pandas 3.0.6 / numpy 2.2.6）

---

## 1. 执行摘要

| # | 问题 | 结论 | 证据等级 |
|---|---|---|---|
| A | 能否确认"模型几乎不预测 UP"？ | **不能。已证实为相反**：对 37 维标准正态输入（训练同分布），当前 `trade_model_xgb.json` 的 P(UP) 均值 **0.5084**、中位数 **0.5093**、<0.5 占比 **45.9%**；对真实特征过 scaler 后均值 **0.4933**。日志里的 `prob_buy=0.000` 不是该模型的输出（该模型在分布内概率下界是 0.163）。 | `已证实` |
| B | 当前主要问题是标签不平衡、分类阈值、模型学习、概率校准，还是证据不足？ | **主因是"证据不足"+"模型本身低信噪比"，并且 `0.002` 阈值这个前提在仓库里找不到任何代码证据**；标签不平衡是事实但**不是**造成"不预测 UP"的原因；分类阈值（0.55 / 0.50）不是主因（概率本来就集中在 0.45–0.57）。 | `部分证实`（每项见 §4 分级） |
| C | 生产 X 因子是否存在可证实的语义不一致？ | **存在，已证实**。`X = 100·P(aligned)` 把"90 分钟内涨超阈值"的事件概率（基准率≈0.34）直接当成 0–100 分——一个中性/无信息预测天然只有 ≈50 分，X 满分 100 只有在该事件近乎确定时才出现；同时 `sig is None` 被误报成"XGB model missing"，X 回退成 `0.3S+0.3R`。 | `已证实` |
| D | 样本外预测价值是否得到验证？ | **未验证**。无法重算任何指标：仓库里不存在可复现的验证集，也没有重训日志文件（`logs/bot_cron.log` 不存在）。 | `未证实` |
| E | 交易价值是否得到验证？ | **未验证**。退出记录中**没有任何 P&L / 平仓结果字段**，`trade_data/` 为空，`profile_pf-b_balanced.jsonl` 只有 5 条 BOT_OPEN、0 条关闭。 | `未证实` |

**一句话结论**：现在**没有任何证据支持**"模型几乎不预测 UP / 需要下调阈值到 0.0005"。相反，有两条独立证据表明"0.002 版"这个前提本身就不成立：① `git log -p` 显示 `retrain_model.py` **历史上从来没有出现过 0.002**；② 两个模型工件的 XGBoost `base_score` 反推出的训练正样本率是 **33.8% / 33.9%**，与 `0.002` 阈值下应有的 ≈1.7–1.9% 相差一个数量级。

---

## 2. 证据清单

### 2.1 P0-A：实际生产链路与模型身份

#### A-1 重训入口与调度

| 事实 | 证据 |
|---|---|
| 重训入口脚本 | `retrain_model.py`（254 行）|
| 仓库内 cron 定义 | `crontab.20261022:24` → `0 0 * * 1-5 cd $HOME/projects/ai_training_cnn && /home/ubuntu/miniconda3/envs/ai-sprint/bin/python retrain_model.py >> logs/bot_cron.log 2>&1`（UTC 00:00 = 新加坡 08:00，周一至周五）|
| 机器上**当前生效**的 crontab | `crontab -l` → 只有 2 行**被注释掉**的条目，**没有任何 `retrain_model.py`**。→ **无法确认**这台机器就是生产机 |
| `logs/bot_cron.log` | **不存在**（`ls` 报 No such file）。→ 重训运行日志在本地**不可获得** |
| 用户所述"Train 1.9% / Val 1.7% / Acc 100% / AUC 0.8953" | **本地无任何文件包含这些数字**（`grep -rn "ROC-AUC\|UP ratio"` 无结果）。只能作为外部输入，无法核对 |

#### A-2 模型加载入口（真实生产文件是 v685）

- `fx_trade_bot_v685.py:1186` `MODEL_PATH = BASE_DIR / "trade_model_xgb.pkl"` → `:1187` `ModelWrapper(FEAT_CFG, model_path=MODEL_PATH)`
- `fx_trade_bot_v685.py:1568-1578` `ensure_model(...)` → `fx_trade_bot_ml.py:23-68`
- `ModelWrapper.load()`（`data_pipeline.py:601-648`）加载优先级：
  1. `trade_model_xgb.json` + `scaler.joblib` + `trade_model_xgb.features.json` 三者同时存在 → **走这一支**（`:608-628`，还会把 `trade_model_xgb.cfg.json` 的内容**覆盖**到内存里的 `FeatureConfig`，`:620-625`）
  2. 否则退回 `trade_model_xgb.pkl` 并 `save()` 重新导出（`:630-644`）
  3. 都没有 → `FileNotFoundError`
- **`trade_model_xgb.pkl` 在当前目录不存在**（`ls` 无此文件），所以只可能走第 1 支。
- 依赖注入：`fx_trade_bot_ml.py:74-76` 把**同一个** `model / scaler / feature_names` 实例交给 `StrategyEngine`。

> 注意：`crontab.20261022` 调用的是 `fx_trade_bot_v685_1.py`，该文件在 `archives/` 下，**不在仓库根目录**；根目录实际运行的是 `fx_trade_bot_v685.py`（见 `logs/fx_bot_20261022.log` 的 `fx_bot.__main__` logger 名与 traceback 行号）。→ 调度文件、工作区、日志三者的版本对应关系 **无法完全确认**。

#### A-3 四件套一致性（已证实：维度一致，但 cfg 与数据统计口径不一致）

| 检查 | 结果 |
|---|---|
| `trade_model_xgb.features.json` | 37 个特征名 |
| `trade_model_xgb.json` | `n_features_in_ = 37`，`classes_ = [0 1]`，`num_boosted_rounds = 200`，`max_depth = 5` |
| `scaler.joblib` | `StandardScaler`，`n_features_in_ = 37` |
| 推理端 `FeatureEngine(use_macd=True)` 实际产出 | 37 个，缺失 0、多余 0（离线实测，§2.6 `feature_contract.py`）|
| `trade_model_xgb.cfg.json` | `use_macd=true` ✓、`target_horizon=6` ✓、但 `train_lookback_bars=5000` |
| `retrain_model.py:37` | `LOOKBACK_BARS = 500` ❌ **与 cfg 不一致** |
| `retrain_model.py:39` | `TARGET_THRESHOLD = 0.0005` ❌ **不是 0.002** |

**已知问题（历史报告中已记录、本次代码仍然存在）**：`data_pipeline.py:520-544` `ModelWrapper.fit()` 会把 `cfg.__dict__`（含 `train_lookback_bars`）写进 `.cfg.json`；而 `.cfg.json` 在加载时又**覆盖**运行时的 `FEAT_CFG`。= **5000 是历史遗留值，不是本次训练真实使用值。** 这证明"cfg 文件不能作为训练元数据证据"。

#### A-4 训练目标 vs 推理目标

| 位置 | 目标定义 | 阈值 |
|---|---|---|
| `retrain_model.py:109-110` | `future_return = Close.shift(-6)/Close - 1`；`target = (future_return > TARGET_THRESHOLD)` | **0.0005** |
| `data_pipeline.py:359-368` `build_target()` | `future_return > 0` | **0** |
| `fx_trade_bot_ml.py:52`（bot 自训路径）| `feat_engine.build_target(horizon=6)` | **0** |
| `utils/ml_confirmation.py:206-210` | `pct_change(3).shift(-3) > 0`（另一套、3 根） | **0**，horizon=3 |

→ **仓库内同时存在 3 套不同的标签定义**。生产加载的是哪个 `.json`，就决定了 P(UP) 指的是哪一件事——而 `.json` 本身**不携带标签定义**。这是本次审计最大的语义风险来源（见 §4 R-01）。

#### A-5 Notebook / 服务器 / 生产模型是否同一份

| 对象 | md5 | mtime |
|---|---|---|
| `trade_model_xgb.json`（当前生产候选）| `64967221793ac538b5e6ef8f3523f45e` | 2026-10-22 09:38:01 |
| `trade_model_xgb_bak_20261007_0153.json` | `1616d66701ee62085541df0c1ddacbae` | 2026-10-07 01:53 |
| `scaler.joblib` | `ada53d608cef9c5ca85b32ff42861e52` | 2026-10-22 09:38:01 |
| `scaler_bak_20261007_0153.joblib` | `fdd9d3cc1fcc091f8684c0f1b70f6cc3` | 2026-10-07 01:53 |

- 两者 **n_features 都是 37**、都 `classes_=[0,1]`、都 200 棵树/深度 5；
- `scaler` 的 `mean_/scale_` **不相等**（`mean equal? False`）→ 是**两次不同批次**的训练产物；
- Jupyter notebook（`jupyterlab/*.ipynb`）为年 8 月的教学 playbook，特征名（`close_dist_ema_50` 等）与本模型无关 → **不是同一份模型**。
- 服务器与本机：本机 crontab 无重训项 → **无法确认**。

#### A-6 cron 是否会覆盖生产模型

`retrain_model.py:220-234` `save_model()`：
1. 对 5 个目标文件（`.json/.joblib/.features.json/.cfg.json/.pkl`）逐个 `shutil.copy2` 生成 `*_bak_<YYYYmmdd_HHMM><suffix>`；
2. 再用 `ModelWrapper.save()` **原地覆盖** `trade_model_xgb.json / scaler.joblib / trade_model_xgb.features.json / trade_model_xgb.cfg.json`。

→ 若生产机 cron 真的执行，会在 **UTC 00:00（新加坡 08:00）** 覆盖这 4 个文件。**本机 cron 没有该条目，因此无法确认它是否真的发生**。`ls` 中当前只存在 **一份** `_bak_20261007_0153` 备份，与"每日重训"不符 → 更强的反证。

#### A-7 实际调用链

```
[cron crontab.20261022:24]  retrain_model.py  (UTC 00:00, 周一~五)
        │  fetch_all_data()      → OANDA M15 × 7 pairs × 500 bars
        │  FeatureEngine.build() → 37 维
        │  target = future_return > TARGET_THRESHOLD (0.0005)
        │  StandardScaler().fit(X_train)
        └─ ModelWrapper.save() ──► trade_model_xgb.json
                                   scaler.joblib
                                   trade_model_xgb.features.json
                                   trade_model_xgb.cfg.json   ← cfg 里是 5000，非本次 500
        ↓
[fx_trade_bot_v685.py:1186-1187]  MODEL_PATH = trade_model_xgb.pkl
        ↓  main():1568  ensure_model()
[fx_trade_bot_ml.py:29-40]  split_ok? age>7d?
        │  否 →  model_wrapper.load()  (data_pipeline.py:601)
        │           └─ json+scaler+features 都在 → 载入 + cfg 覆盖(:620-625)
        │  是 →  自己抓 1500 bars 自训 build_target(>0) 并 save()  ★第二套标签
        ↓
[fx_trade_bot_ml.py:74-76]  strat_engine.model / .scaler / .features  ← 同实例注入
        ↓
[v685:2251]  strat_engine.generate_signal(...)
[    :140]       p_up = StrategyEngine._predict(latest)
[    :299]           → data_pipeline.predict_p_up() → _build_matrix(严格列序+scaler) → proba[:, pos_idx]
[    :155]       p_down = 1 - p_up
[    :158]       direction = LONG if p_up > p_down else SHORT        ← 0.50 就是方向分界
[    :161]       edge = |raw_prob - 0.5|
[    :168]       if raw_prob < 0.50 → return None                    ← 硬门槛
[    :175-236]   score = 25 + edge_pts + MC + pivot + gap
[    :231]       if score < min_conviction → return None
        ↓  (sig 返回后)
[v685:2260-2269]  sig is None  ⇒  日志写 “XGB model missing”         ← 误报
[v685:2272-2274]  calc_weighted_score(pair, gap, rsi, adx, prob_raw, mc_pct_up)
[v685:1393-1405]  xgb_dir = BUY if prob>=0.55 else SELL; 三票表决
[v685:1493-1497]  X = 100·P(aligned);  若 X==0 或 xgb_prob is None → X = 0.3S + 0.3R
[v685:1520]       FINAL = S·W_S + R·W_R + G·W_G + A·W_A + X·W_X + M·W_M
[v685:1529]       PASS = FINAL >= MIN_CONVICTION
        ↓
[v685:2287]  if not (direction and w and w["PASS"]): continue
[v685:2295-2315] D-Gate → [v685:2321] evaluate_trend_and_tp → 下单
```

---

### 2.2 P0-B：标签与数据分布

| 项目 | 结论 | 证据 |
|---|---|---|
| `TARGET_HORIZON` 运行值 | 训练端 `6`（`retrain_model.py:38`）；推理端 `target_horizon` **只用于 cfg 元数据**，推理时不用它 | 代码 |
| `future_return` 公式 | `Close[t+6] / Close[t] - 1`（简单收益率，**非**对数、**非** ATR 归一） | `retrain_model.py:109` |
| `target` 定义 | `(future_return > TARGET_THRESHOLD).astype(int)`，**严格大于** | `:110` |
| `NaN` / 尾部处理 | 每个 pair 内算完再 concat；`train_model` 里又 `X[:-6], y[:-6]` —— 这 6 行是**跨 pair 拼接后的最后 6 行**（只属于最后一个 pair），**其余 6 个 pair 各泄漏 6 行带 NaN 标签的样本**（`future_return` NaN → `> t` 为 `False` → 被静默打成 **target=0**） | `:156-161`、`:110` |
| 样本过滤 | **无**。`df.ffill().bfill().fillna(0)` 之前未 dropna | `:106` |
| 缺失特征填零 | `fillna(0)` 用在 `future_return` 之前，标签列不受影响；但特征被 0 填充 | `:106` |
| 时间切分 | `train_test_split(shuffle=False)`，`test_size=0.20` | `:164-166` |
| **切分泄漏** | 拼接顺序是 **pair-major**（每个 pair 的 500 根 bar 首尾相接）。`shuffle=False` 后，验证集 = **末尾 ~1.4 个 pair 的整段数据**，而不是"所有 pair 的最后 20% 时间"。实测：train = `['AUDUSD','EURJPY','EURUSD','GBPJPY','GBPUSD','USDJPY']`，val = `['USDCHF','USDJPY'(尾)]` | `:119`、离线 `label_repro.py` |
| **标签跨越切分** | 拼接点处 `cut-1` 的训练样本，其标签用到 `cut+5` 的价格 → **6 行跨边** | 离线实测 |
| scaler 拟合 | 只在 `X_train` 上 fit，`X_val` transform ✅ | `:177-179` |
| 特征泄漏 | `FeatureEngine.build()` 全部为因果滚动量（`pct_change/rolling/shift`），**未发现未来数据**；`vol_regime` 被 `exclude` 且为字符串 | `data_pipeline.py:222-357` |

#### B-1 `0.002` 没有源码证据（已证实）

```
$ git log -p --follow -- retrain_model.py | grep -E "^[+-].*(TARGET_THRESHOLD|LOOKBACK_BARS)"
+TARGET_THRESHOLD = 0.0005        ← 该行自首次加入起就是 0.0005
```

**`0.002` 在整个 git 历史里从未出现在 `retrain_model.py` 中**，当前工作区的 `TARGET_THRESHOLD = 0.0005` 也**不是**未提交改动（`git diff retrain_model.py` 只有第 1 行注释）。

#### B-2 `1.7%–1.9%` 与 `0.002` 的数量级冲突（已证实）

XGBoost `binary:logistic` + `boost_from_average=1` 时，`base_score = p/(1-p)`（margin）。直接读模型工件：

| 工件 | `base_score`（margin） | 反推训练集 P(UP) |
|---|---|---|
| `trade_model_xgb.json`（当前）| 0.509755 | **33.76 %** |
| `trade_model_xgb_bak_20261007_0153.json` | 0.513883 | **33.94 %** |

即：**生成当前 `.json` 的训练集正样本率约 34%，不是 1.7–1.9%**。两者不可能来自同一个标签阈值（差一个数量级，AUC 0.8953 也无法覆盖）。

> 这说明用户引用的那段"Train 1.9% / Val 1.7%"日志**几乎不可能来自当前这份 `.json`**（除非该 `.json` 不是那次训练的产物）。`无法确认` 它对应哪个文件。

#### B-3 各阈值下正样本率的理论值（零漂移高斯近似 + 日志实测 ATR）

日志 `logs/fx_bot_20261022.log:208-214` 给出 20:00 的 M15 ATR 与收盘价：

| 品种 | ATR(M15)/Close | 隐含 σ_bar | P(>0.05 %) over 6 bar | P(>0.075 %) | P(>0.10 %) | P(>0.20 %) |
|---|---|---|---|---|---|---|
| AUDCHF | 0.115 % | ≈9.6 bp | 40.8 % | 37.4 % | 33.6 % | **19.8 %** |
| USDCHF | 0.090 % | ≈7.5 bp | 40.0 % | 32.6 % | 29.4 % | **13.9 %** |
| GBPAUD | 0.076 % | ≈6.3 bp | 39.1 % | 29.6 % | 25.8 % | **9.7 %** |
| EURCHF | 0.065 % | ≈5.5 bp | 38.5 % | 26.9 % | 22.7 % | **6.7 %** |
| GBPUSD | 0.053 % | ≈4.4 bp | 37.7 % | 21.4 % | 17.6 % | **3.1 %** |
| EURUSD | 0.022 % | ≈1.9 bp | 34.0 % | 4.9 % | 1.4 % | **≈0.0 %** |

**解读**（这是本次审计能给出的最硬的一条量化结论）：

- 对**低波动品种**（EURUSD/GBPUSD），`0.002 / 90min` 确实**几乎不可能发生**（0–3 %）→ 标签在该子集上退化成"全是 0"。
- 对**高波动品种**（AUDCHF/USDCHF），`0.002` 仍有 14–20 % → 标签是有效的。
- 所以 `1.9 %` **只在"全部品种混合 + 低波动时段"下才成立**。这不是"标签定义错误"，而是"**固定绝对阈值 × 跨品种混合 = 各品种标签难度差 20 倍**"。
- 反过来，`0.002` 断言的是一次 **0.2 % 的确定性方向移动**，而代码对**所有**品种（含 EURUSD）都输出同一个 P(UP)——这与 §2.4 的 X 因子语义问题叠加。

#### B-4 用真实代码 + 合成行情复现标签（`label_repro.py`）

用 `FeatureEngine.build()` 真实路径 + 7 对 × 500 根零漂移随机游走：

| threshold | UP_all | UP_train | UP_val |
|---|---|---|---|
| 0.0 | 46.9 % | 46.9 % | 51.3 % |
| 0.0002 | 38.4 % | 38.4 % | 41.5 % |
| 0.0005 | 26.8 % | 26.8 % | 28.1 % |
| 0.001 | 11.9 % | 11.9 % | 13.5 % |
| **0.002** | **1.6 %** | **1.6 %** | **2.6 %** |

→ `0.002` 在 4 bp/bar 的合成波动率下确实给出 ~1.6 %，**与用户日志的 1.9 %/1.7 % 同一量级**。这说明：**"1.9 % 正样本率"这个事实是真的、且能解释；但它与"当前 `.json` 的训练集 34 %"矛盾。**

---

### 2.3 P0-C：模型是否真的几乎不预测 UP？

**无法复现用户给出的 Val Accuracy 98.14 % / ROC-AUC 0.8953** —— 缺少：验证集（`trade_data/` 为空、`data/train/` 只有一张图）、重训日志（`logs/bot_cron.log` 不存在）、以及生成该 `.json` 的训练脚本版本与数据快照。

能做到的是**用真实工件直接探测模型行为**（`pup_probe.py`，20000 条 / 3500 条）：

#### C-1 三组概率分布

| 场景 | 均值 | Std | P1 | P5 | P25 | P50 | P75 | P95 | P99 | P(≥0.50) | P(≥0.55) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **A. 训练同分布**（37 维标准正态） | **0.5084** | 0.0916 | 0.2958 | 0.3568 | 0.4462 | **0.5093** | 0.5712 | 0.6569 | 0.7206 | **54.08 %** | **32.84 %** |
| **B. 真实特征，未过 scaler**（v685_2 历史 bug 形态） | 0.4842 | 0.0484 | 0.3800 | 0.4173 | 0.4467 | 0.4749 | 0.5346 | 0.5581 | 0.5634 | 35.60 % | 16.83 % |
| **C. 真实特征，过 scaler（契约正确）** | 0.4933 | 0.0823 | 0.2652 | 0.3485 | 0.4480 | 0.4934 | 0.5473 | 0.6270 | 0.6719 | 46.54 % | 24.00 % |

**关键读数**：
- 场景 A 的概率**下界是 0.1629**，`count(P<1e-3) = 0`。→ 日志里 `prob_buy=0.000` **不可能是这个模型的合法输出**（见 C-3）。
- 场景 A 的 `P(≥0.55)=32.8%`。若阈值是 0.55，模型在**中立输入**上就会给出 33 % 的 BUY 票 → **阈值本身不是"UP 被压死"的原因**。
- 概率集中在 0.44–0.57（judiciously 窄），这是**信号弱**的表现，不是"被阈值卡住"。

#### C-2 混淆矩阵 / Precision / Recall / PR-AUC

**无法计算。** 缺少真实标签 + 真实预测概率的配对数据。任何数字都是编造，故不填。

#### C-3 日志中的 `prob_buy=0.000` 是"占位值"而非模型输出（已证实）

`logs/fx_bot_20261022.log:1520`：
```
🤝 EURUSD=X: Strength=SELL | XGB=NEUTRAL (prob_buy=0.000, thr=0.55) | MC=SELL (P_UP=49.4%) | BUY=0/3
```
同一对同一时刻 `:1528`：
```
✅ SCORE EURUSD=X SELL | S=100.0×0.45=45.0 ... X= 44.5×0.12= 5.3  M= 49.4×0.08= 4.0 | FINAL=71.60
```
- 若 `prob_buy` 真的是 0，SELL 对齐概率 `1-0 = 1.0` → `X` 应 = **100.0**，而不是 44.5；
- `0.3·S + 0.3·R = 0.3×100 + 0.3×48.2 = **44.46 ≈ 44.5**` → **`X` 正是 `calc_weighted_score:1496-1497` 的 fallback 分支**；
- 触发 fallback 的条件是 `X == 0.0 or _xgb_missing`，而 `_xgb_missing` 仅在 `xgb_prob is None` 时为真（`:1393`）。

→ **结论**：那一轮 `xgb_prob` 是 `None`（`sig is None`），日志里的 `prob_buy=0.000` 是 `calc_weighted_score:1394` 把 `None → 0.0` 后的格式化结果。**这正是历史审计报告 F-04 记录的问题，至今未修**。

#### C-4 分类阈值来源（以代码为证）

| 阈值 | 位置 | 值 | 用途 |
|---|---|---|---|
| 方向分界 | `strategy_decision.py:158` | **0.50**（`p_up > p_down`） | 决定 BUY/SELL |
| `base_min_edge` | `strategy_decision.py:40` / `fx_trade_bot_v685.py:1158-1173` | 0.50（`MODE="LEVEL10"`）| `raw_prob < 0.50 → return None` |
| 三票表决 XGB 票 | `fx_trade_bot_v685.py:828` | **0.55**（`XGB_BULLISH_THRESHOLD`）| `BUY if prob≥0.55 else SELL` |
| sklearn 内部 | XGB 内部 | 0.50 | 仅用于 `retrain_model.py:197-198` 的 Accuracy |
| MC 票 | `fx_trade_bot_v685.py:829` | 55.0 % | — |

→ `Accuracy 98.14 %` 对应的阈值是 **sklearn 默认 0.5**，而 0.5 在 `retrain_model.py` 里**没有任何配置项支撑**，也不是生产用的 0.55。

---

### 2.4 P0-D：P(UP) → X 因子 → 评分的语义一致性

#### D-1 `P(UP)` 实际表示什么？`无法确认`

- **代码层面**：`data_pipeline.py:448-461` `predict_p_up()` 返回 `proba[:, positive_class_index]`，即 `classes_[1] == 1` 那一列概率。`classes_ = [0 1]`（工件实测）。→ **数学上是"该工件训练时 `target==1` 的概率"**。
- **业务层面**：`target==1` 到底是 `>0` 还是 `>0.002` 还是 `>0.0005`，**工件里不含标签定义**；仓库内同时有 3 种定义（§2.1 A-4）。→ **`无法确认` 生产 P(UP) 是"90 分钟涨超 0.2 %"还是"一般上涨"。**

#### D-2 `P(UP)` 是否被反向 / 阈值化 / 归一化 / 裁剪

| 变换 | 位置 | 说明 |
|---|---|---|
| 反向 | `strategy_decision.py:155`、`fx_trade_bot_v685.py:1494` | `p_down = 1-p_up`；`SELL → X = 100·(1-P(UP))` ✅ 语义正确 |
| 硬阈值 | `strategy_decision.py:168` | `raw_prob < 0.50 → return None`（**整个信号被丢弃**，而非降权）|
| 硬阈值 | `fx_trade_bot_v685.py:1399` | `prob ≥ 0.55 → BUY` |
| **无**平滑/校准 | — | 未发现 isotonic / Platt / rolling calibration |
| 裁剪 | `fx_trade_bot_v685.py:1495` | `max(0,min(100, ...))` |
| **回退** | `fx_trade_bot_v685.py:1496-1497` | `X == 0 or None → X = 0.3S + 0.3R` |

#### D-3 X 因子的实际公式

```python
# fx_trade_bot_v685.py:1493-1497
_xgb_p_up   = xgb_prob or 0.0                        # None 和 0.0 都变 0.0  ★
_xgb_aligned = _xgb_p_up if direction == "BUY" else (1.0 - _xgb_p_up)
X = max(0.0, min(100.0, _xgb_aligned * 100.0))
if X == 0.0 or _xgb_missing:
    X = max(0.0, min(100.0, S * 0.3 + R * 0.3))
```

#### D-4 `X` 的输入范围与权重

| 项 | 满分 | 典型值 | 语义 |
|---|---|---|---|
| S | 100（`min(|gap|/3.5,1)·100`）| 100 | 强度差 |
| R | 100（`|rsi-50|·2`）| 48 | RSI 偏离 |
| A | 100（`min(adx·2,100)`，地板 20）| 100 | ADX |
| **X** | **100**（`P(aligned)·100`）| **≈50** | **模型对齐概率** |
| M | 100（MC `p_up` 已是百分数！）| 50 | 蒙特卡洛 |

> ⚠️ `strategy_decision.py:311-316` 假设 `mc_data["p_up"] ∈ [0,1]`（`abs(mc_prob-0.5)/0.15`），但 `mc_cache` 里的 `p_up` 是 **0–100**（`daily_results/h4_mc_*.json: "p_up": 42.0`）。→ `_eval_mc` 在本链路会恒给满/恒定分。该方法在 v685 中**未被调用**（`grep should_close` 无命中），属**潜在**缺陷。

#### D-5 BUY / SELL 是否用同一概率？是。

`fx_trade_bot_v685.py:1493-1494` + `strategy_decision.py:160`：BUY 用 `P(UP)`，SELL 用 `1-P(UP)`，**同一个二分类模型、互补概率**。因此：**任何关于"下跌"的信息只能通过"非 UP"间接表达**——而 `target=0` 同时混入了「下跌」「横盘」「未达阈值的微涨」（§P0-B）。→ **把 `1-P(UP)` 当作 `P(DOWN)` 是语义错误**，这是 `已证实` 的代码事实。

#### D-6 是否存在"把低置信度当明确方向"？

`strategy_decision.py:158` `direction = LONG if p_up > p_down else SHORT`：`p_up = 0.5001` 即判 LONG。但同一函数 `:168` 要求 `raw_prob ≥ 0.50`，只挡掉 `≤0.5`；`0.501` 可通过。→ **存在**（`部分证实`：`generate_signal` 后续还有 `score ≥ min_conviction` 的二道闸，但 `calc_weighted_score` 路径的 `xgb_dir` 在 `prob<0.55` 时**直接投 SELL**，即 `0.501` 与 `0.001` 在票向上完全等价）。

#### D-7 dtype / 特征顺序 / 缺失特征 / 概率列索引 / 类别编码

| 检查项 | 结果 |
|---|---|
| 特征顺序 | ✅ `data_pipeline._build_matrix:411-425` 按 `.features.json` 顺序取列 |
| 缺失特征 | ✅ 抛 `InferenceFeatureError`，**不再静默填 0**（`:412-413`）|
| 非有限值 | ✅ 抛 `InferenceFeatureError`（`:442-443`）|
| dtype | ✅ `to_numpy(dtype=float)` |
| 概率列索引 | ✅ `positive_class_index()` 跟随 `classes_`（`:448-451`）|
| scaler 维度 | ✅ 三方 37/37/37，`_validate_loaded_artifacts` 校验（`:563-572`）|
| **scaler 是否真的被应用** | ✅ v685 走 `StrategyEngine._predict → predict_p_up → _build_matrix`（`strategy_decision.py:286-299`）|
| **XGB 产物忘了 set_feature_names** | ⚠️ `booster.feature_names is None` → 模型内部用 `f0..f36`，与外部顺序**只能靠调用方保证**；一旦顺序错，**不会报错**（`已证实`）|
| **scaler 与模型的训练批次** | ⚠️ `scaler.joblib` 与 `_bak_20261007` 的 `mean_/scale_` 不同；无法证明 `.json` 与 `scaler.joblib` 是**同一次** fit 的（两者 mtime 同秒，只能说明同时写盘）|

#### D-8 "模型几乎不输出 UP" 对 X 因子的理论影响

- **（若为真）** `P(UP)→0` ⇒ SELL 方向 `X→100`，即**永远给 SELL 满分 12 分**；BUY 方向 `X→0` 触发 fallback。→ 单边偏置。
- **（实测）** 不成立：A 场景 `P<0.5` 占 45.9 %，双向都有。
- **静态代码推断**：`X` 满分需要 `P(aligned)=1.0`，而 **34 % 基准率的事件的概率永远到不了 100 %**。`X` 的真实区间约 **18–86**（场景 A 的 P0–P100），典型 ≈ 50。→ **`X` 的有效动态范围只有理论的一半**，权重 0.12 → 实际贡献 2–10 分（满分 12），而 S 满分 45 分。这是**已观察到的实际运行证据**（`:1528` X=44.5、`:1536` X=49.9、`:1557` X=29.1）。

---

### 2.5 P0-E：样本外与交易价值

| 需要的证据 | 现状 |
|---|---|
| 独立测试集 | **不存在**（`trade_data/` 空，`data/train/` 只有 `iscsi.png`）|
| 训练/验证日志 | **不存在**（`logs/bot_cron.log` 缺失）|
| 按品种/时间段的样本外表现 | **无法计算** |
| PR-AUC vs 正样本基准 | **无法计算** |
| 概率校准曲线 | **无法计算**（且工件只有概率下界 0.163，集中于 0.44–0.57）|
| 历史信号 + 成交 | `logs/profile_pf-b_balanced.jsonl`：**5 条 `BOT_OPEN`**，`score_final` ∈ {58.1, 62.1, 59.8, 71.6, 69.5}，**无平仓/P&L 字段** |
| 成本 / 出场 / 收益 | `trade_data/` 空；`fx_daily_report*.py` 未在本地产生输出；`logs/` 无 `CLOSED`/`pnl` 记录 |
| 与简单基线比较 | **无法计算** |
| 与 `X` 无关的对照组 | v685 有 `VOTE SIZE DIAG`（6 条），但**样本量 6** |

**结论**：**没有任何样本外或交易价值证据**。`已证实` 的是"证据不存在"，`未证实` 的是"模型有效"和"模型无效"两个方向。

---

## 3. 核心指标表

| 指标 | 值 | 来源 | 备注 |
|---|---|---|---|
| UP 比例（用户日志） | Train 1.9 % / Val 1.7 % | 用户输入 | ⚠️ 本地无文件佐证 |
| UP 比例（模型工件反推） | **33.76 % / 33.94 %** | `base_score` + `p=b/(1+b)` | 与上一行**矛盾** |
| UP 比例（0.002 理论，4–10 bp/bar） | 0.0 %（EURUSD）–19.8 %（AUDCHF） | §2.2 B-3 | 品种间差 20× |
| UP 比例（0.0005 理论，同条件） | ≈34 %（EURUSD 34.0 %）– 40.8 %（AUDCHF） | 同上 | 与工件 33.8 % **吻合** |
| 训练集行数 | 3500 − 末 6 行（≈3494，含 6×7 条 NaN→0 伪负样本） | `retrain_model.py:160` | 7 pairs × 500 |
| 验证集行数 | ≈700（= 末尾 pair 片段） | `test_size=0.20` + pair-major | 非时间切分 |
| 验证集品种覆盖 | 2 / 7 个（USDCHF、USDJPY 尾部） | 离线实测 | 跨品种泛化**未被验证** |
| P(UP) 分布（训练同分布，n=20000） | mean 0.5084 / std 0.0916 / P1 0.2958 / P50 0.5093 / P99 0.7206 / min 0.1629 | `pup_probe.py` | 双向都有 |
| P(UP) 分布（真实特征 × scaler，n=3500） | mean 0.4933 / std 0.0823 / P50 0.4934 / min 0.1925 / max 0.7589 | `pup_probe.py` | — |
| 预测 UP 比例 @0.50（训练同分布） | 54.08 % | 同上 | — |
| 预测 UP 比例 @0.55（训练同分布） | 32.84 % | 同上 | 生产 XGB 票阈值 |
| 混淆矩阵 TP/FP/TN/FN | **无法计算** | — | 无验证集 |
| Precision / Recall / F1 | **无法计算** | — | 无验证集 |
| PR-AUC | **无法计算** | — | 无验证集 |
| ROC-AUC | **无法计算**（用户称 0.8953，本地无证据） | — | — |
| Accuracy | **无法计算**（用户称 98.14 % / 100 %） | — | — |
| 全 0 基线 Accuracy | 若正样本率 = 1.7 % → **98.3 %** | 算术 | **98.14 % 低于该基线** |
| 全 0 基线 Accuracy（若按工件 34 %） | 66.2 % | 算术 | — |
| 分类阈值 | 0.50（方向 + `min_edge`）、0.55（XGB 票）、0.50（sklearn Accuracy） | 代码 | 三处不同 |
| 预测 UP 比例（生产日志，2026-10-22 20:01） | 5 条合格对：2 条 NEUTRAL(占位 0.000)、3 条 0.501/0.501/0.524 → **0 条 ≥0.55 → 0 张 BUY 票** | `logs/fx_bot_20261022.log:1520-1560` | 但 5 条全是 SELL 候选 |
| 模型概率下界 | **0.1629** | 工件实测 | `prob_buy=0.000` 非模型输出 |

---

## 4. 风险分级

### P0 — 可能影响生产决策 / 存在严重验证问题

| ID | 风险 | 证据 | 影响范围 |
|---|---|---|---|
| **R-01** | **标签语义未固化在工件里**：同一仓库 3 套标签（`>0.0005` / `>0` / `>0 @h=3`），`.json/.features.json/.cfg.json` **都不记录阈值**；`ModelWrapper.load()` 还会用 `.cfg.json` 覆盖运行时 `FEAT_CFG` | §2.1 A-4、`data_pipeline.py:620-625` | 无法证明生产 P(UP) 指代的是哪一件事；任何"下调阈值"的方案都可能改错目标 |
| **R-02** | **"0.002 版"这个前提在代码里不存在**：git 全历史无 `0.002`；当前值 0.0005；工件反推 33.8 % 正样本率 | §2.2 B-1、B-2 | 若按"1.9 %→改阈值"决策，**基线与结论都建立在错误前提上** |
| **R-03** | **`sig is None` 被误报为 "XGB model missing"**，`None → 0.0` 后再格式化成 `prob_buy=0.000`，X 回退 `0.3S+0.3R` | `fx_trade_bot_v685.py:1393-1397, 1496-1497, 2260-2269`；`2026-10-22 20:01:42` 日志算术验证 X=44.5 | **证据链被污染**：观察 P(UP) 的日志本身不可信；X 因子实际未使用模型 |
| **R-04** | **`validate_split` 非时间、非品种分层**：`shuffle=False` + pair-major concat → 验证集 = 末尾 1.4 个 pair | `retrain_model.py:119, 164-166` | 98.14 %/0.8953 只证明"对 USDCHF/USDJPY 拟合好"，**不构成样本外证据** |
| **R-05** | **无独立测试集、无重训日志、无 P&L 记录** | §2.5 | 无法做出"改/不改"的决策 |
| **R-06** | **同日 20:01:42 实际向 OANDA 提交了 2 笔订单**（`TradeID=11003/11007`），其中 EURUSD 的 X 因子是 **fallback 值**而非模型输出 | `logs/fx_bot_20261022.log:1581-1596`、`logs/profile_pf-b_balanced.jsonl` | 生产决策因子与模型脱钩 |

### P1 — 模型质量与评估风险

| ID | 风险 | 证据 |
|---|---|---|
| **R-07** | **Accuracy 指标选择错误**：`retrain_model.py:197-205` 只报 Accuracy/ROC-AUC，不报 PR-AUC/Precision/Recall/校准；且在 1.7 % 正样本率下 `全0 = 98.3 % > 98.14 %` | `全0 基线 98.3 %` 算术 |
| **R-08** | **`X = 100·P(aligned)` 量纲错配**：34 % 基准率事件的概率被当作 0–100 分，`X` 实际动态范围 ≈18–86、典型 ≈50，满分 100 只在事件近乎确定时出现 | §2.4 D-3/D-4；日志 X=44.5/49.9/29.1 |
| **R-09** | **`1-P(UP)` 被当 `P(DOWN)`**：`target=0` 含「下跌/横盘/微涨」，SELL 方向 `X=100·(1-P(UP))` 在语义上是"不是大涨"而非"会跌" | `strategy_decision.py:155`、`fx_trade_bot_v685.py:1494` |
| **R-10** | **无概率校准**；概率集中在 0.44–0.57（std 0.09），`0.501` 与 `0.001` 在票向上等价 | §2.3 C-1、`fx_trade_bot_v685.py:1399` |
| **R-11** | **标签窗口跨越切分**：6 行训练样本的标签用到验证集价格 | §2.2 |
| **R-12** | **6 个 pair 各泄漏 6 行 NaN 标签 → 被静默打成 target=0** | `retrain_model.py:110, 160-161` |
| **R-13** | **固定绝对阈值 × 跨品种 = 标签难度差 20 倍**（EURUSD 0 % vs AUDCHF 19.8 %） | §2.2 B-3 |
| **R-14** | **booster 未保存 feature_names**，特征顺序错误不会报错 | 工件实测 `feature_names is None` |
| **R-15** | **cfg 记录 `train_lookback_bars=5000` 而实际用 500** → cfg 不能作为训练元数据证据 | `retrain_model.py:37` vs `trade_model_xgb.cfg.json:18` |
| **R-16** | bot 自查路径 `fx_trade_bot_ml.py:52 → data_pipeline.py:363` 用的是 **`>0` 标签**，与 `retrain_model.py` 的 `>0.0005` **不一致**；一旦模型"过期 7 天"触发自训，会**静默换掉标签定义** | `retrain_model.py:110` vs `data_pipeline.py:363` |

### P2 — 进一步研究项

| ID | 项目 |
|---|---|
| **R-17** | `strategy_decision._eval_mc` 假设 `p_up∈[0,1]`，实际传 0–100（当前死代码） |
| **R-18** | `strategy_decision.should_close()`（0.55 反转平仓）在 v685 **从未被调用** |
| **R-19** | 训练只用 **500 根 bar × 7 对 = 3500 行**（≈52 天 M15），`n_estimators=200, max_depth=5` → 3500 行配 200 棵深树，过拟合风险高；与实际"整族品种 × 数周"样本量不匹配 |
| **R-20** | `crontab.20261022` 指向 `archives/fx_trade_bot_v685_1.py`；本机 crontab 无重训项 → 调度/工作区/生产版本三方一致性问题 |
| **R-21** | `XGB_BULLISH_THRESHOLD=0.55` 在 `config_profile.json:22` 与代码默认一致；但 `config_bot.get_global` 只从 `global` 段读，profile 级覆盖 `:131-228` 不生效（需另验） |
| **R-22** | `OPEN` 日志把 `score_final` 直接当交易质量代理，与 `Signal.conviction_score` 并不同源 |

---

## 5. 后续建议（只分析，不实施、不预设胜者）

> 所有选项的共同前置条件：**先补 §6 里列出的缺失证据**。没有这些，任何方案都无法被验证。

### 5.1 保持 `TARGET_THRESHOLD` 不变，只修评估方式

- **预期收益**：零模型风险；立刻获得可比的 PR-AUC / Precision@K / 校准曲线；暴露 R-03（`sig is None` 污染日志）和 R-04（切分）两个真 bug，且这两个 bug 与标签无关。
- **代价**：低（改评估脚本 + 日志字段，不动模型）。
- **风险**：如果真实目标是"提高交易质量"，单纯的评估改良不会改变 P(UP) 的基准率；且 `X` 因子的量纲问题（R-08）仍在。
- **验证方法**：以现有 `.json` 在**按时间切分、按品种分层**的独立集上算 PR-AUC / Brier / 校准斜率；对比"全 0 基线"和"仅用 `P(UP)` 排序 + 固定分位选前 K"的收益。

### 5.2 比较不同**固定**收益阈值（0.0005 / 0.001 / 0.002…）

- **预期收益**：`0.0005` 会把基准率抬到 ≈34 %（与当前工件反推一致），使 `X` 因子的动态范围回到≈30–70；`0.002` 在高波动品种保留 14–20 %、在 EURUSD 归零。
- **代价**：每换一个阈值都必须**重训 + 重新校准 + 重新评估 PR-AUC**；标签语义必须写进工件元数据（否则 R-01 复发）。
- **风险**：**固定绝对阈值仍不解决跨品种波动率差异（R-13）**；且 `0.0005` ≈ 0.05 %，在点差 1–2 pip（≈0.01–0.02 %）之上但很薄，交易成本对标签的侵蚀需单独量化。
- **验证方法**：同一时间窗、同一特征集，**只在标签上做 A/B**；对每个阈值输出 PR-AUC、正样本率、按品种拆分的 `P(>阈值)`、以及"标签命中 → 实际可达 TP/SL 比例"。

### 5.3 使用 **ATR 归一化**阈值（`future_return > k · ATR%`）

- **预期收益**：直接消除 R-13（品种间 20× 难度差），让标签变成"相对波动幅度的方向性移动"，与 SL/TP 的 ATR 倍数（`atr_sl_mult=2.0 / atr_tp_mult=3.0`）**同量纲**；正样本率跨品种稳定，`X` 因子分布也更可比。
- **代价**：标签需要每个 pair 的 `atr[t]`（已有，`FeatureEngine` 输出 `atr` / `atr_pct`）；阈值 `k` 增加一个自由度，需在验证集上固定并冻结。
- **风险**：`atr` 本身是回看量，**用 `atr[t]` 做分母不引入未来信息**（✅ 因果），但需确认 `atr` 在尾部 NaN 的处理；另外 `atr_pct` 在低波动时数值小、放大会放大噪声。
- **验证方法**：同 5.2，但先固定 `k ∈ {0.5, 1.0, 1.5}`，检查各品种正样本率是否落在 20–35 %，再比 PR-AUC。

### 5.4 使用**分位数**标签（每个品种每个滚动窗口取 top-q%）

- **预期收益**：正样本率**恒定为 q**，彻底摆脱"固定阈值 × 波动率"问题；`X` 因子天然可比，阈值语义清晰（"该品种前 q% 的上涨"）。
- **代价**：标签依赖**滚动窗口长度**与 `q`；标签定义随窗口变化，**必须写进工件元数据**；实时推理时不需要标签，所以不影响部署。
- **风险**：分位数标签的"正样本"是**相对**的；在趋势性行情中会把"小涨"也标成 UP，与"能否覆盖成本"脱钩；窗口边界会产生标签不稳定。**最大风险**：容易把"分类难度"误当成"可交易性"。
- **验证方法**：固定 `q=20 %`，检查跨品种正样本率恒定性（应 ≈20 %）；再用"标签命中 → 实际净收益 > 成本"的比例检验经济意义。

### 5.5 研究**双向 / 三分类**标签

- **预期收益**：直接消除 R-09（`1-P(UP) ≠ P(DOWN)`）。三分类（`UP / FLAT / DOWN`，中间带用 ATR 或分位数定义）能把"横盘"单独建模，`P(DOWN)` 变成真实输出，SELL 方向不再依赖"非 UP"。
- **代价**：最高。需要改 `retrain_model.py`（`objective=multi:softprob`）、改 `predict_p_up`（取列）、改 `X` 因子（BUY 取 P(UP)、SELL 取 P(DOWN)，两者**不再互补**）、改 `XGB_BULLISH_THRESHOLD` 语义、重训、重评。改动面横跨 §2.1 A-7 全链路。
- **风险**：改动面最大，回归风险最高；中间带的比例本身又是一个需要选定的超参；在样本量只有 3500 行（R-19）时，三分类每类样本更少，**统计功效进一步下降**。
- **验证方法**：先在离线脚本里用现有 7 对数据做三分类的**交叉验证**（不落盘、不覆盖生产），只比较 `P(UP|DOWN)` 的区分度（PR-AUC per class）与"BUY/SELL 对称性"，再决定是否进入实施。

---

## 6. 明确的最终结论

### 6.1 当前证据**不足以**决定是否修改 `0.002`

原因不是"证据倾向于不改"，而是**"`0.002` 这个基线本身没有被证实"**：

1. `git log -p` 证明 `retrain_model.py` **从未**使用 `0.002`（§2.2 B-1）；
2. 当前 `.json` 的 `base_score` 反推训练正样本率 **33.8 %**，与 `0.002` 应有的 1.7–1.9 % 相差一个数量级（§2.2 B-2）；
3. 用户引用的重训日志在本地**不存在**，无法核对它对应哪个脚本版本、哪个模型文件（§2.1 A-1）；
4. 生产链路里 `sig is None` 被写进日志成 `prob_buy=0.000`，**日志本身不能证明模型"不预测 UP"**（§2.3 C-3）。

### 6.2 作出决定前仍缺少的关键证据

| # | 缺什么 | 怎么补（只读） |
|---|---|---|
| **E-1** | **真实重训日志原文**：`logs/bot_cron.log` 中最近一次 `🚀 XGBOOST MODEL RETRAINING` 到 `🎉 RETRAINING COMPLETE` 的完整段落（含 `Features:` 行、`UP ratio — Train/Val`、`top features`） | 从**生产机**取回该文件；对比其中的 `Features: N` 与 §2.1 A-3 的 37 |
| **E-2** | **该次训练所用 `retrain_model.py` 的实际内容**（md5 + `TARGET_THRESHOLD` 行） | 生产机上 `md5sum retrain_model.py` + `sed -n '33,40p'` |
| **E-3** | **该次训练产物与生产加载文件的同一性** | 生产机上 `md5sum trade_model_xgb.json scaler.joblib trade_model_xgb.features.json`，与 §2.1 A-5 比对；并读 `base_score` 看是否仍是 ~0.51（→≈34 % 正样本率） |
| **E-4** | **验证集本身**：切分后的 `X_val`、`y_val`（或能重算它们的数据快照） | 需要训练时的 3500 行原始 OHLC 快照；当前 `trade_data/` 为空 |
| **E-5** | **真实的 P(UP) 观测序列**（不是 `prob_buy`，而是 `Signal.raw_prob` / `Signal.model_p_up`） | 需在 `fx_trade_bot_v685.py:2251` 之后**只加日志**（不改逻辑）记录 `sig.model_p_up`，并修 R-03 的误报；这是唯一能回答"是否几乎不输出 UP"的现场证据 |
| **E-6** | **独立测试集 + 成本模型** | 至少一段**与训练期不重叠**的 M15 数据（同 7 对），以及点差/滑点数值，才能算"标签命中 → 净收益" |
| **E-7** | **每笔交易的平仓结果** | `BOT_OPEN` 需配对 `BOT_CLOSE` + `pnl` + `exit_reason`；当前 jsonl 无此字段 |
| **E-8** | **生产机 cron 实际内容** | 生产机 `crontab -l`（本机没有重训条目） |

### 6.3 可以**现在**就确定的三件事（不涉及改阈值）

1. **`prob_buy=0.000` 不是模型输出**（模型概率下界 0.163），而是 `None → 0.0` 的占位；这是**已证实**的日志/评分链路缺陷（R-03）。
2. **X 因子把 34 % 基准率的事件概率当 0–100 分用**，动态范围被压缩一半（R-08）；`SELL` 用 `1-P(UP)` 而非 `P(DOWN)`（R-09）。这两条与阈值无关，改阈值**不会**修复它们。
3. **当前验证集不是样本外**（pair-major + shuffle=False），98.14 % / 0.8953 **不能**作为"模型有效"或"模型需要改标签"的依据（R-04）。

> 最终判断：**先取回 E-1/E-2/E-3/E-8 四份证据，再决定是否动 `TARGET_THRESHOLD`。** 在这四份证据到手之前，任何"下调到 0.0005"或"维持 0.002"的结论都建立在未经证实的基线上。

---

## 附录 A：本次审计执行的只读命令

```bash
# 产出物一致性
md5sum trade_model_xgb.json scaler.joblib trade_model_xgb.features.json trade_model_xgb.cfg.json
stat -c '%n %s %y' trade_model_xgb.json scaler.joblib
git log -p --follow -- retrain_model.py | grep -E "^[+-].*(TARGET_THRESHOLD|LOOKBACK_BARS)"
git ls-files | grep -E "^(retrain_model|trade_model_xgb|scaler)"
crontab -l

# 生产链路
grep -n "MODEL_PATH\|ModelWrapper(\|ensure_model(" fx_trade_bot_v685.py fx_trade_bot_ml.py
grep -n "prob_buy=\|XGB_SCORE=\|XGB model missing" logs/fx_bot_20261022.log

# 离线（全部在 /tmp/p0_audit 下，未写入仓库）
~/miniconda3/envs/ai-sprint/bin/python model_identity.py      # 工件身份 + base_score
~/miniconda3/envs/ai-sprint/bin/python feature_contract.py    # 37/37/37 + MACD 契约
~/miniconda3/envs/ai-sprint/bin/python label_repro.py         # 标签阈值 × 切分泄漏
~/miniconda3/envs/ai-sprint/bin/python label_theory.py        # base_score → 正样本率
~/miniconda3/envs/ai-sprint/bin/python pup_probe.py           # P(UP) 三分位 + 分布
~/miniconda3/envs/ai-sprint/bin/python zero_prob_check.py     # prob_buy=0.000 反证
```

## 附录 B：未做 / 做不到的事（明确声明）

- ❌ 未重训、未调参、未替换任何模型/scaler/cfg/备份；
- ❌ 未运行 `retrain_model.py`（会联网抓 OANDA 并覆盖生产工件）；
- ❌ 未调用任何 OANDA 交易 API；
- ❌ 未安装/升级依赖；
- ❌ **未能**计算 Precision / Recall / F1 / PR-AUC / 混淆矩阵 —— 无验证集，**没有编造**；
- ❌ **未能**确认 P(UP) 的业务语义（`>0` / `>0.0005` / `>0.002`）—— 工件不含标签定义；
- ❌ **未能**确认本机 == 生产机（本机 crontab 无重训项、无 `bot_cron.log`）。
