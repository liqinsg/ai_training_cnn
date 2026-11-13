
这份 Phase 1 审计很有价值。我先说结论：

v685 的 Training / Inference 共用 FeatureEngine，但这不等于训练时模型看到的特征，与实盘预测时模型看到的特征完全一致。

Claude（或这份审计）的核心发现是正确的，而且它发现的问题不只是 ATR、MACD 的数值差异。

我认为这里有一个更重要的风险：

我们可能并不清楚当前生产模型究竟是用什么标签、什么数据历史、什么依赖环境训练出来的。

这意味着，即使模型能够正常加载、输入维度也是 37，仍然不能证明它的预测有可靠的训练基础。

## 一、先看问题的严重程度

P1 — 训练与推理的语义一致性

高优先级

- Explicit training：未来收益超过 0.05% 才标记 UP。
- Auto-training：未来收益只要大于 0 就标记 UP。
- Training timeframe：固定 M15。
- Inference timeframe：允许 M15、H1、H4。

这意味着同一个模型体系可能存在不同的训练目标和输入时间尺度。

P1 — 特征数值一致性

高优先级

- Training：500 candles。
- Inference：200 candles。
- Auto-training：配置为 1500 candles。
- ATR fallback 与 pandas_ta 算法不同。

相同公式不代表相同数值。

P2 — 模型资产完整性

中高优先级

- Model、Scaler、Feature Manifest 分开保存。
- 没有共同 Run ID 或 Hash。
- 只检查维度，不检查特征语义。

37 个输入维度一致，不代表它们属于同一次训练。

## 二、我最关注的四个发现

### 1. 两套训练路线实际上训练的是不同定义的模型

这是我认为最重要的发现。

| 项目         | Explicit retraining | Production auto-training   |
| ------------ | ------------------- | -------------------------- |
| 未来预测周期 | 6 根 M15            | 6 根 M15（需核实实际配置） |
| UP 标签      | Return > 0.0005     | Return > 0                 |
| Lookback     | 500                 | 1500                       |
| 数据组织     | Per-pair split      | 多 Pair 合并               |
| Scaler       | 训练集拟合          | 全数据拟合                 |
| Validation   | 时间顺序 80/20      | TimeSeriesSplit            |

特别是标签：

- Explicit：未来收益必须超过 0.05% 才算 UP。
- Auto：未来收益只要大于零就算 UP。

这不是微小参数差异，而是模型学习目标发生变化。

例如：

| 未来收益 | Explicit | Auto |
| -------- | -------- | ---- |
| +0.02%   | DOWN     | UP   |
| +0.04%   | DOWN     | UP   |
| +0.06%   | UP       | UP   |
| -0.02%   | DOWN     | DOWN |

这里的 DOWN 是标签定义，不代表市场实际下跌。

所以，即使两个模型使用完全相同的 37 个 Feature，它们也可能学习出不同的决策边界。

我不建议在没有确定唯一训练目标之前，继续进行模型 retraining。

### 2. 500、200、1500 根 K 线不是可以忽略的区别

这点容易被低估。

ATR、RSI、MACD 都有历史依赖。

特别是 EMA 类计算，起始历史数据会影响最终结果。

例如：

- 用 500 根 K 线计算最后一根 MACD。
- 用 200 根 K 线计算同一根 K 线的 MACD。

即使最后一根 OHLC 完全相同，数值也不保证相同。

这不是说 500 一定比 200 正确，而是训练与推理应该有明确、可验证的历史窗口契约。

我建议后续不要只检查公式，而要直接比较：

\\[ \Delta Feature = Feature\_{500}-Feature\_{200} \\]

逐个 Feature 输出：

- Absolute Difference
- Relative Difference
- Maximum Difference
- Median Difference
- 是否改变模型预测概率

这样才知道差异有没有实际影响。

### 3. ATR fallback 是真正的算法分叉

这里需要特别注意。

正常路径：

`pandas_ta.atr()`

Fallback：

`rolling(period, min_periods=1).mean()`

两者不是同一个算法。

因此即使 Training 和 Inference 使用相同的 FeatureEngine，也可能因为运行环境不同而得到不同结果。

你之前已经遇到过：

```
ta.atr failed
MACD failed
```

所以这不是纯理论问题，而是必须结合实际运行记录调查的风险。

另外，MACD 没有 fallback：

- 已有模型要求 MACD，但计算失败：预测失败。
- Auto-training 时 MACD 缺失：可能生成不包含 MACD 的新模型。

这会造成模型 Feature Manifest 发生变化。

### 4. 37 个 Feature 不等于 37 个正确的 Feature

这一点是模型资产管理的问题。

当前：

- Model：37 features。
- Manifest：37 names。
- Scaler：37 dimensions。

维度一致只能证明形状匹配。

不能证明：

- Scaler 属于这个 Model。
- Manifest 属于这个 Model。
- Feature 公式与训练时一致。
- 训练时使用的是同一套 Configuration。

我认为未来应该建立一个完整的 Model Bundle Identity：

```
MODEL_BUNDLE
├── model.json
├── scaler.joblib
├── features.json
├── config.json
└── metadata.json
    ├── training_run_id
    ├── training_route
    ├── target_definition
    ├── timeframe
    ├── lookback_bars
    ├── feature_version
    ├── dependency_versions
    └── artifact_hashes
```

这不是要求现在就重构，而是应该作为后续工程设计目标。

## 三、我建议的 Phase 2 顺序

不要马上修改 FeatureEngine，也不要马上重新训练。

我会按以下顺序：

P0

确认当前模型的真实来源

查明 Nov 5 的模型究竟来自 Explicit retraining 还是 Auto-training。

同时确认实际运行的 timeframe、lookback、target definition，以及 Nov 13 是否触发了 auto-training。

P0

Training / Inference Numerical Parity Test

使用完全相同的历史 K 线，分别运行 200、500、1500 bars。

比较 ATR、RSI、MACD 和全部 37 个 Feature 的数值差异。

P1

Dependency Branch Verification

分别验证 pandas_ta 正常路径和 fallback 路径。

确认生产环境实际使用哪个实现，以及失败时是否产生静默的模型行为变化。

P1

Prediction Impact Test

将不同历史窗口、不同 ATR 实现产生的 Feature 输入同一个现有模型。

比较 P_UP 的变化，而不是只看 Feature 差异。

P2

Model Artifact Integrity

检查模型、Scaler、Manifest、Config 是否属于同一次训练，并设计版本绑定机制。

## 四、一个特别重要的判断

我不希望这次审计最后变成：

「发现 5 个问题，修复 5 个问题，然后继续跑 Bot。」

因为我们真正需要回答的是：

当前 XGB 模型的预测概率，到底有没有资格被当成交易决策的依据？

至少要建立三个证据：

1. Training 与 Inference 的数值输入一致性。
2. Model 与 Scaler、Feature Manifest 的资产一致性。
3. 训练标签与实际交易目标的一致性。

这三个证据没有建立之前，模型输出的 P_UP 只能视为一个未经充分验证的统计输出，不能因为它能正常运行就赋予它预测能力。

另外，Nov 5 的模型到 Nov 13 已经超过默认七天 retrain interval。审计报告也明确说了，正常调用 `ensure_model()` 时会考虑重新训练，但尚未确认实际发生。这一点应该优先查清，避免我们分析的是一套已经被自动替换的模型。

我的建议：下一阶段只做 Phase 2 的静态溯源和数值一致性实验，不改交易逻辑、不触碰 OANDA、不触发生产 retraining。

这次审计最值得追求的不是让 FeatureEngine 看起来统一，而是拿出数据证明训练时与推理时模型实际看到的是同一种东西。

如果你准备继续，我可以把上述内容整理成一份给 Claude / TRAE 的英文 `Phase 2 Strict Audit Specification`，带明确的测试输入、输出和 Acceptance Criteria。
