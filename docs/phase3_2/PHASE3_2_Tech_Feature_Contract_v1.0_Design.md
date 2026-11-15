# 【Technical Design】Phase 3.2 — Technical Feature Contract v1.0

**Version:** 0.1 — Initial Technical Design  
**Date:** 2026-11-15  
**Status:** DRAFT — PENDING OWNER APPROVAL  
**Source:** Phase 3.2 Strict Spec v0.3 / Feature Contract Decision Record v0.2-decision  
**Authority:** `data_pipeline.FeatureEngine` (current source baseline)  
**Implementation Authorization:** NOT GRANTED

---

## 1. Design Objective

建立一个版本化、可验证、不可被 artifact 或运行时配置静默改变的 Feature Contract。

该契约是未来模型训练和实时推理共同遵守的唯一特征定义。

核心原则：

1. Feature Contract 定义模型输入，而不是模型 artifact 定义输入。
2. Training 与 Inference 必须使用相同的特征计算语义。
3. 特征名称、顺序、公式、参数、backend、数据处理和 timeframe 必须明确。
4. 未验证的 fallback 不得静默替代 canonical backend。
5. 无效特征输入必须明确拒绝，不能伪装成有效模型向量。
6. 旧 artifact 不得仅凭维度相同而认定兼容。

**本设计不授权生产实现、模型训练、artifact 写入、部署或交易行为变更。**

## 2. Contract Architecture

未来采用以下逻辑结构：

`Raw Candle Data`
→ `Candle Validation`
→ `Feature Calculation`
→ `Warm-up Validation`
→ `Missing-value Validation`
→ `Ordered Feature Projection`
→ `Model Input`

Training 与 Inference 共用同一套逻辑定义。

两个路径可以有不同的工程入口，但不得有不同的特征语义。

### 2.1 Authority hierarchy

| Layer | Authority |
|---|---|
| Feature Contract | 特征定义、顺序、计算语义和输入要求 |
| Training Contract | Target、Label、训练样本和评价定义；属于 Phase 3.3 |
| Runtime Configuration | 当前运行环境和运行参数 |
| Artifact Metadata | 声明并证明 artifact 与 Contract 的兼容关系 |
| Release Manifest | 不可变发布身份和生命周期；属于 Phase 3.4 |

Artifact metadata 不得覆盖 Feature Contract 或 runtime configuration。

## 3. Feature Schema Design

### 3.1 Current candidate inventory

当前源码在 `use_macd=True` 且指标计算成功时生成 37 个数值候选特征。

这 37 个候选项仅作为待审查清单，不代表已批准的最终模型输入。

| Group | Candidate features | Decision |
|---|---|---|
| Returns | `ret_1h`, `ret_3h`, `ret_6h`, `ret_12h`, `ret_log` | PENDING |
| Volatility | `vol_12h`, `vol_24h`, `vol_48h` | PENDING |
| Candle geometry | `body`, `upper_wick`, `lower_wick`, `range`, `direction` | PENDING |
| ATR | `atr`, `atr_pct`, `atr_percentile`, `atr_ma`, `atr_expanding`, `atr_ratio` | PENDING |
| Momentum | `rsi`, `rsi_slope`, `adx` | PENDING |
| MACD | `MACD_12_26_9`, `MACDh_12_26_9`, `MACDs_12_26_9` | PENDING |
| Price location | `dist_high_24`, `dist_low_24`, `dist_high_48`, `dist_low_48`, `dist_high_96`, `dist_low_96` | PENDING |
| Volume | `vol_sma_ratio`, `vol_trend` | PENDING |
| Time | `hour`, `day_of_week`, `is_london`, `is_ny` | PENDING |

### 3.2 Per-feature specification

每个最终保留的特征必须定义：

- Stable feature name
- Position in ordered feature list
- Output dtype
- Unit and scale
- Exact formula
- Formula parameters
- Input columns
- Lookback dependency
- Warm-up behavior
- Missing-value behavior
- Canonical backend and version
- Timeframe interpretation
- Numerical comparison tolerance

不得使用“与当前代码相同”“默认参数”或“pandas-ta 标准实现”代替精确的定义。

### 3.3 Feature selection rule

每个候选特征必须明确分类：

- INCLUDE：进入最终模型输入
- EXCLUDE：不进入最终模型输入
- DEFER：缺少证据，暂不决定

每个 INCLUDE / EXCLUDE 决定必须记录技术依据。

任何特征不得仅因当前 FeatureEngine 会生成它而自动纳入契约。

### 3.4 Ordered schema

最终模型输入必须使用显式有序列表。

禁止通过动态选择所有 numeric columns 的方式决定模型输入。

禁止根据 DataFrame 当前列顺序推断模型输入顺序。

Contract Identity 必须覆盖完整有序列表。

## 4. Canonical Numerical Backend

### 4.1 ATR

当前手工 rolling-mean True Range fallback 与 pandas-ta 在可变波动样本上不等价。

设计决定：

- pandas-ta 是当前 canonical backend 的候选。
- 不允许手工 fallback 静默替代。
- backend 不可用或计算失败时，特征计算必须明确失败。
- 最终 period、初始化规则、输出定义和版本必须写入契约。

### 4.2 RSI

当前手工 Wilder EWM fallback 在已测试固定样本中与 pandas-ta 结果一致，但尚未证明普遍等价。

设计决定：

- 暂不批准 fallback。
- 必须扩大固定样本验证范围。
- 在获得明确等价证据和 owner approval 前，使用唯一 canonical backend。
- RSI 初始化和历史长度依赖必须纳入 warm-up 实验。

### 4.3 MACD

设计决定：

- 若最终 schema INCLUDE MACD，三个 MACD 列必须同时存在。
- 任意必要 MACD 输出缺失，必须报告 contract error。
- 不允许静默删除列或用零值替代。
- 若决定 EXCLUDE MACD，则必须从有序 schema 和相关输入要求中整体移除。

### 4.4 ADX

ADX 当前使用本地实现。

最终契约必须记录：

- 精确公式
- 平滑方式
- 初始化方式
- period
- NaN / warm-up 规则
- 实现版本或稳定代码身份

不能只记录“local ADX”。

### 4.5 Backend failure policy

默认采用 fail-closed：

- Required backend missing → REJECT
- Indicator calculation failure → REJECT
- Required output column missing → REJECT
- Non-finite required feature → REJECT
- Unapproved fallback → REJECT

不得在 backend 失败后静默生成替代数值。

## 5. Lookback and Warm-up Policy

### 5.1 Known structural threshold

当前配置下：

- 97 rows 是生成全部 37 个候选数值特征的结构性列生成门槛。
- 97 rows 不代表所有指标已经数值收敛。
- 200 与 500 bars 的最新特征向量存在六个超出预注册容差的特征差异。

### 5.2 Required experiments

需要针对以下候选历史长度进行可重复测试：

- 97 bars：结构性边界测试
- 128 bars：短历史候选
- 200 bars：当前主交易请求长度
- 300 bars：中间历史候选
- 500 bars：当前训练请求长度
- 更长历史：仅在递归指标仍未达到稳定条件时使用

这些长度是实验候选，不是已批准的最终配置。

### 5.3 Comparison method

固定：

- Instrument
- Timeframe
- 最后一根已完成 K 线
- OHLCV 数据来源
- FeatureEngine 版本
- Backend 和 dependency versions
- Runtime feature configuration

比较每个候选历史长度下最后一根 K 线的特征向量。

记录：

- Absolute difference
- Relative difference
- Missing / non-finite values
- Feature-specific convergence behavior
- Differences attributable to initialization or calculation backend

### 5.4 Acceptance principle

最终历史长度必须满足：

1. 所有 INCLUDE 特征均存在。
2. 不存在未处理的 NaN / Inf。
3. 递归指标达到事先批准的稳定标准。
4. Training 与 Inference 使用相同历史长度策略。
5. 容差和比较规则在实验前确定，不得事后放宽。

不得仅因为 500 bars 是当前训练请求长度，就直接将其设为最终 warm-up policy。

## 6. Missing-value Policy

设计原则：

- 禁止 future-to-past filling。
- 禁止无条件 `bfill()`。
- 禁止无条件 `fillna(0)` 伪装无效特征。
- Training 的 warm-up 无效样本必须被排除，或按明确批准的版本化策略处理。
- Inference 的无效特征向量必须被拒绝。
- 缺失列、错误 dtype、Inf、NaN 和错误顺序必须提供独立错误原因。

最终策略必须区分：

- Structural missing columns
- Indicator warm-up NaN
- Raw OHLCV invalidity
- Unexpected runtime calculation failure

不得把这些问题统一转换成零值。

## 7. Timeframe and Candle Contract

### 7.1 Timeframe identity

每个 Feature Contract 必须声明一个具体 timeframe。

例如 M15、H1 或 H4。

不得使用未限定的 `ANY` timeframe。

Training 与 Inference 默认要求精确 timeframe match。

不同 timeframe 之间的兼容性必须有单独实验和 owner approval，不得根据特征列数量相同推断兼容。

### 7.2 Candle integrity

输入必须满足：

- Timezone-aware UTC timestamps
- Strictly increasing timestamps
- Unique timestamps
- Expected candle interval validation
- OHLCV validity checks
- Shared incomplete-candle exclusion policy

Gap handling 必须考虑外汇市场的周末和交易时段，不得将所有时间间隔大于 timeframe 的情况直接视为数据损坏。

未被已批准交易日历或 session policy 解释的缺口必须明确报告。

## 8. Configuration Authority

- Runtime configuration 是运行时参数的权威来源。
- Feature Contract 是特征语义的权威来源。
- Artifact config 只用于兼容性验证。
- Artifact config 不得静默修改 runtime configuration。
- 任何契约不兼容都必须在进入模型推理前明确拒绝。

FeatureEngine 和 ModelWrapper 不得通过共享可变配置对象，使 artifact load 改变已经初始化的特征计算行为。

此项是目标架构要求，不代表当前代码已经实现。

## 9. Feature Contract Identity

Contract Identity 只有在所有必需定义确定后才能签发。

Identity 至少覆盖：

- Contract version
- Ordered feature names
- Formula definitions and parameters
- Dtype and units
- Backend identity and version
- Timeframe
- Candle integrity policy
- Lookback and warm-up policy
- Missing-value policy
- Preprocessing rules

建议使用规范化契约内容计算稳定 SHA-256 identity。

任何影响上述语义的变化都必须产生新的 Contract Identity。

训练 Target / Label 定义属于 Phase 3.3 的 Training Contract，不能混入本阶段 Feature Contract Identity。

未来模型产物必须同时绑定：

- Feature Contract Identity
- Training / Target Contract Identity

正式不可变发布管理仍由 Phase 3.4 负责。

## 10. Required Technical Decisions

以下事项仍需 Stage C 技术定稿：

| ID | Decision | Current status |
|---|---|---|
| TFC-01 | 37 个候选特征最终取舍 | PENDING |
| TFC-02 | 所有 INCLUDE 特征的完整公式及参数 | PENDING |
| TFC-03 | ATR canonical backend | PENDING OWNER APPROVAL |
| TFC-04 | RSI canonical backend 与 fallback disposition | PENDING |
| TFC-05 | MACD 是否进入最终 schema | PENDING |
| TFC-06 | ADX 精确公式与初始化规则 | PENDING |
| TFC-07 | 最终 lookback / warm-up | PENDING |
| TFC-08 | Missing-value policy | DESIGN PRINCIPLE ESTABLISHED |
| TFC-09 | 默认 timeframe 与兼容规则 | PENDING |
| TFC-10 | Candle gap / session policy | PENDING |
| TFC-11 | Feature Contract Identity serialization | PENDING |

## 11. Acceptance Criteria

Technical Feature Contract v1.0 必须满足：

1. 所有 INCLUDE 特征有完整、可实现的定义。
2. 所有 EXCLUDE 特征有明确记录。
3. Ordered schema 固定。
4. Canonical backend 和版本固定。
5. 所有 backend failure behavior 明确。
6. Lookback 和 warm-up 有直接实验依据。
7. Training / Inference missing-value policy 一致。
8. Timeframe 和 candle integrity policy 明确。
9. Runtime configuration 与 artifact config 分离。
10. Contract Identity 可稳定计算。
11. 不依赖历史 UNVERIFIABLE artifact 推断新契约。
12. 不改变现有交易行为。

## 12. Non-Goals

本设计不包括：

- Target / Label redesign
- Train / validation split redesign
- Purge / embargo
- Model calibration
- Threshold optimization
- Production FeatureEngine implementation
- Production model loading changes
- Model retraining
- Artifact writing
- Deployment
- PredictionResult READY activation
- Shadow Evaluation
- Controlled Activation
- Trading decision / execution changes
- Phase 3.4 release-management implementation

## 13. Authorization Boundary

当前请求允许：

- Technical Feature Contract 设计
- 基于已有 Stage A / B 证据整理决策
- 明确待批准事项
- 准备后续实现规格和验收标准

当前不允许：

- 修改生产 `.py` 文件
- 修改依赖或主机环境
- 训练模型
- 写入或覆盖模型 artifact
- 部署
- READY wiring
- 修改交易行为

**Final status: DRAFT — PENDING OWNER APPROVAL**
