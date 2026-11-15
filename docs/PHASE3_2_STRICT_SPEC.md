
# 【Strict Spec】Phase 3.2 — Feature / Inference Consistency

**Version:** 0.1
**Date:** 2026-11-15
**Status:** DRAFT — PENDING OWNER APPROVAL
**Repository:** `ai_training_cnn`
**Baseline:** User-uploaded `ai_training_cnn.zip`
**Implementation Authorization:** NOT GRANTED
**Priority:** P0 / P1

---

## 1. Objective

建立一套可验证、确定性、可复现的训练与实时推理特征契约。

本阶段必须回答：

1. 训练和推理是否使用相同的原始数据定义？
2. 相同输入是否产生相同的特征名称、顺序、类型和数值？
3. 指标计算是否受第三方库版本或 fallback 路径影响？
4. 最低有效 lookback 应该是多少？
5. 缺失值和预热期如何处理，是否存在未来数据填补？
6. 模型是否只能在其训练 timeframe 和 feature contract 下运行？
7. artifact 是否能够静默改变运行时特征配置？

**最终目标：同一份原始 OHLCV 输入，在相同契约下，训练与推理必须产生一致的特征向量。**

## 2. Scope

### 2.1 P0 — Canonical Feature Contract

- 确定唯一权威 Feature Engine。
- 明确全部特征的名称、顺序、数据类型、单位、公式和参数。
- 固定指标计算 backend。
- 明确第三方库依赖及版本。
- 禁止未验证的 fallback 静默改变特征语义。
- 建立 feature contract identity。

### 2.2 P0 — Training / Inference Parity

覆盖：

- 原始 OHLCV 输入。
- FeatureEngine 调用。
- 指标计算。
- 缺失值处理。
- 特征列选择和排序。
- Scaler 输入。
- 最终模型输入。

必须验证相同数据输入下的特征向量一致性。

### 2.3 P0 — Lookback / Warm-up

- 依据完整特征依赖图计算最低输入长度。
- 验证所有特征列是否存在。
- 验证 warm-up 期间的 NaN / Inf。
- 验证训练与实时推理的最低有效数据量。
- 禁止仅凭 `required_bars=20` 或 `has_min_bars(..., 5)` 认定输入有效。

### 2.4 P1 — Timeframe / Candle Integrity

- 固定训练 timeframe。
- 验证实时 timeframe 与模型兼容性。
- 统一 UTC 时间戳语义。
- 验证 K 线完整性。
- 验证重复、乱序和缺失 K 线。
- 验证未完成 K 线的排除规则。

### 2.5 P1 — Configuration Authority

- 明确 runtime configuration 的权威来源。
- artifact config 只作为兼容性验证依据。
- 不允许 artifact 静默覆盖运行配置。
- 对不兼容的 feature configuration 提供明确错误原因。

### 2.6 P1 — Cross-host Determinism

同一份原始输入、同一份 feature contract、同一组依赖版本，在不同运行环境中必须产生可接受的一致结果。

---

## 3. Current Source Findings

以下是本次 ZIP 源码中已经确认的事实，不等于所有问题均已证明影响当前生产预测。

### F32-01 — Feature Backend

**Status: CONFIRMED**

当前实际 FeatureEngine：

`data_pipeline.py::FeatureEngine`

`ml/features.py` 文件头明确标记为：

`NON-AUTHORITATIVE — DO NOT WIRE`

本阶段不得把 `ml/features.py` 接入生产路径，也不得因为文件名或历史注释将它误认为权威实现。

**Required action:** 保留 `data_pipeline.FeatureEngine` 为现状基线，先定义目标契约，再决定是否需要替换或重构计算实现。

### F32-02 — Indicator Backend Variance

**Status: CONFIRMED**

当前 ATR、RSI、MACD 存在第三方库依赖或 fallback：

- ATR：`pandas_ta` 与手工 True Range 路径。
- RSI：`pandas_ta` 与手工 Wilder RSI 路径。
- MACD：依赖 `pandas_ta`，失败时仅记录 warning，可能不生成列。
- ADX：使用本地实现。

**Required action:** 逐项建立固定输入测试，比较不同计算路径的结果。未证明等价的 fallback 不得被视为等价实现。

### F32-03 — Training / Runtime Cleaning

**Status: PARTIALLY VERIFIED**

`retrain_model.py::fetch_all_data()`：

- `FeatureEngine.build(raw)`
- `replace([inf, -inf], nan)`
- `ffill()`
- `bfill()`
- `fillna(0)`

`fx_trade_bot.py` 主行情路径也执行了相同清洗步骤。

但多周期 Confluence 路径直接调用 `feat_engine.build(raw_tf)`，没有执行同样的清洗流程。

**Required action:** 明确所有消费者是否应该共用同一个输入验证与预处理入口，并单独验证 `bfill()` 对训练样本的影响。

### F32-04 — Lookback Guard Mismatch

**Status: CONFIRMED**

当前存在多套长度条件：

- `FeatureConfig.required_bars = 20`
- `StrategyEngine.generate_signal()` 最低检查 5 根。
- `data_guard.MIN_REQUIRED_BARS` 默认 200。
- `retrain_model.py` 要求至少 200 根原始数据。
- 主交易路径请求 200 根，但实际返回数量可能少于请求数量。

FeatureEngine 中存在 `dist_high_96` / `dist_low_96` 等条件生成的特征。

**Required action:** 根据完整依赖图定义唯一的有效输入规则。不能把 API 请求数量当成实际数据保证。

### F32-05 — Timeframe Compatibility

**Status: CONFIRMED GAP**

训练脚本固定：

`retrain_model.py::TIMEFRAME = "15m"`

实时 CLI 支持：

- `15m`
- `1H`
- `H4`

当前模型保存的 `.cfg.json` 来自 `FeatureConfig`，没有明确保存训练使用的 OANDA granularity。

当前加载路径也没有证明模型训练 timeframe 与实时 timeframe 一致。

**Required action:** 定义 artifact timeframe metadata 和 runtime compatibility check。缺少可信 metadata 时，不得猜测兼容。

### F32-06 — Artifact Configuration Mutation

**Status: CONFIRMED**

`data_pipeline.py::ModelWrapper.load()` 读取 `.cfg.json` 后，通过 `setattr(self.cfg, ...)` 修改运行配置。

`FeatureEngine` 与 `ModelWrapper` 持有同一个 `FEAT_CFG` 对象。

另外，`FeatureEngine` 初始化时已经构造 `ATRModule(period=cfg.atr_period)`。后续修改 `cfg.atr_period` 不会自动重新初始化该模块。

**Required action:** 将 artifact config 改为只读兼容性输入；runtime config 不应被 artifact 静默覆盖。

### F32-07 — Artifact Evidence

**Status: NOT VERIFIED**

本次 ZIP 不包含：

- `.git` 元数据
- `docs/Development_plan.md`
- `trade_model_xgb.json`
- `scaler.joblib`
- `trade_model_xgb.features.json`
- `trade_model_xgb.cfg.json`

因此，本轮不能确认实际生产 artifact 的 feature list、训练配置及具体兼容性。

---

## 4. Proposed Feature Contract

每个特征至少定义：

| Field              | Requirement            |
| ------------------ | ---------------------- |
| `name`           | 唯一、稳定的列名       |
| `dtype`          | 明确数据类型           |
| `unit`           | 明确数值单位           |
| `formula`        | 完整计算公式           |
| `parameters`     | period、window 等      |
| `backend`        | 唯一计算实现           |
| `warmup`         | 有效预热要求           |
| `missing_policy` | 缺失值处理             |
| `timeframe`      | 输入 K 线周期          |
| `ordering`       | 在模型输入中的固定位置 |

Feature contract identity 应由规范化后的契约内容确定，至少覆盖：

- feature names and ordering
- formulas and parameters
- backend identity/version
- dtype and units
- timeframe
- warm-up policy
- missing-value policy

模型 artifact 的完整发布身份和不可变发布管理属于 Phase 3.4，不在本阶段提前实现。

---

## 5. Missing-value and Warm-up Policy

本阶段需要验证并确定以下原则：

1. 不允许未来方向的数据填补过去的特征值。
2. 训练样本必须满足完整的特征有效性条件。
3. 最新实时输入不满足特征契约时，不应生成伪造的模型输入。
4. NaN、Inf、缺失列、错误 dtype 和错误顺序必须被明确识别。
5. 不允许通过无条件 `fillna(0)` 把无效特征伪装成有效特征。
6. 预热长度必须由实际计算依赖和数值收敛实验确定。

`bfill()` 是否应彻底移除，以及最终采用 drop、显式缺失标记或其他处理策略，需要通过固定样本实验和模型输入兼容性分析确定，不能在没有验证的情况下直接替换生产逻辑。

---

## 6. Timeframe and Candle Contract

训练与推理必须声明相同的 timeframe。

必须验证：

- 原始时间戳为 UTC 或经过明确的 UTC 标准化。
- K 线按时间严格递增。
- 不存在重复时间戳。
- 对预期 K 线缺口有明确检测规则。
- 最新未完成 K 线被一致排除。
- 训练与推理采用相同的 candle completeness policy。

当前 `trim_to_closed_candles()` 主要处理最新一根 K 线，不应把它视为已经完成全部时间序列完整性验证。

---

## 7. Work Stages

### Stage A — Contract and Source Reconciliation

**目标：锁定当前真实行为与目标契约。**

交付：

- Current Feature Inventory
- Training / Inference Call Graph
- Feature Dependency Graph
- Configuration Authority Table
- Timeframe Compatibility Matrix
- Missing-value / Warm-up Matrix
- NOT VERIFIED Register

验收：

- 每个模型输入特征均有明确来源。
- 每条实际消费者路径均有记录。
- 所有现有 fallback 均有归属。
- 不以历史文档代替当前源码证据。

### Stage B — Deterministic Parity Test Design

**目标：建立可重复的验证系统。**

测试样本：

- 单调上涨数据
- 单调下跌数据
- 横盘数据
- 高波动数据
- Gap 数据
- 零成交量
- 缺失数据
- 非有限数值
- 重复及乱序时间戳
- 不同 lookback 长度
- 不同 timeframe
- 不同计算 backend

验收：

- 特征名称和顺序完全一致。
- dtype 一致。
- 数值差异满足明确、经批准的容差。
- 所有失败均能给出明确原因。
- 不依赖真实 OANDA 账户。

### Stage C — Canonical Implementation

**目标：实现经批准的唯一特征计算与验证入口。**

实施前提：

- Stage A、B 已验收。
- Canonical backend 已明确。
- Missing-value / warm-up policy 已批准。
- 旧 artifact 兼容策略已明确。

实施要求：

- 训练和推理使用相同计算定义。
- 统一预处理和输入验证。
- 固定 feature ordering。
- 固定 timeframe metadata。
- runtime config 与 artifact config 分离。
- 不允许未经批准的生产路径切换。

验收：

- 固定样本通过训练/推理 parity tests。
- fallback 等价性有测试证据。
- 不兼容输入能够明确拒绝。
- 旧 artifact 的兼容状态有明确分类。

---

## 8. Explicit Non-Goals

Phase 3.2 不包括：

- 重新设计 target / label。
- 重新设计训练集和验证集切分。
- Cross-instrument temporal leakage 修复。
- Purge / embargo / final holdout 重构。
- Model calibration。
- Threshold optimization。
- ML Vote 接入。
- Entry Authorization 修改。
- 交易评分、仓位、订单和退出逻辑修改。
- 生产模型重训。
- 生产部署。
- Phase 3.5 Shadow Evaluation。
- Phase 3.6 Controlled Activation。

这些工作继续由各自阶段负责。

---

## 9. Acceptance Criteria

| ID      | Acceptance criterion                             | Priority |
| ------- | ------------------------------------------------ | -------- |
| P32-A01 | 唯一权威 Feature Engine 已明确                   | P0       |
| P32-A02 | 所有模型特征均有完整定义                         | P0       |
| P32-A03 | Feature ordering 固定且可验证                    | P0       |
| P32-A04 | Indicator backend 确定且 fallback 等价性得到证明 | P0       |
| P32-A05 | Training / inference 使用统一预处理规则          | P0       |
| P32-A06 | 不存在未定义的未来方向特征填补                   | P0       |
| P32-A07 | Lookback / warm-up 有直接测试                    | P0       |
| P32-A08 | NaN / Inf / missing column 被明确处理            | P0       |
| P32-A09 | Timeframe metadata 和兼容性规则明确              | P1       |
| P32-A10 | Candle completeness / timestamp policy 明确      | P1       |
| P32-A11 | Artifact 不再静默修改 runtime config             | P1       |
| P32-A12 | Cross-host parity 有固定测试样本                 | P1       |
| P32-A13 | 旧 artifact 兼容状态可识别                       | P1       |
| P32-A14 | 不改变交易执行行为                               | P0       |

---

## 10. Stop Conditions

遇到以下情况必须停止对应实施，不得猜测：

- 当前模型 artifact 无法取得。
- Feature list 与模型实际维度不一致。
- 无法确认训练 timeframe。
- 指标 fallback 无法证明等价。
- 不能确定实际消费者调用路径。
- 旧 artifact 与新 feature contract 不兼容，但迁移策略尚未批准。
- 需要修改交易决策或执行路径才能完成测试。

停止后只报告具体证据缺口、影响和最小解决方案，不扩大成无限审计。

---

## 11. Authorization Boundary

当前批准：

- Phase 3.2 规格设计。
- 基于当前源码的只读分析。
- 固定样本测试设计。
- 现有特征计算行为的离线实验。

当前未批准：

- 修改 `.py` 文件。
- 修改生产 FeatureEngine。
- 修改模型加载行为。
- 生成或覆盖模型 artifact。
- 重训模型。
- 部署。
- 接通 PredictionResult READY。
- 修改任何交易行为。

**Stage C 实施必须取得单独批准。**

---

## 12. Final Deliverables

Phase 3.2 完成时必须交付：

1. `docs/PHASE3_2_FEATURE_CONTRACT.md`
2. `docs/PHASE3_2_TRAIN_INFERENCE_PARITY_REPORT.md`
3. `docs/PHASE3_2_IMPLEMENTATION_REPORT.md`
4. 固定输入测试数据及预期输出。
5. 自动化 parity test suite。
6. Feature Contract Compatibility Matrix。
7. 明确的 Phase 3.2 Closure Decision。

`docs/Development_plan.md` 仍是最高层生命周期参考；其内容必须在最终规格冻结前完成对照，不得由本任务单擅自覆盖。

**Phase 3.2 Status: DRAFT — PENDING APPROVAL**
