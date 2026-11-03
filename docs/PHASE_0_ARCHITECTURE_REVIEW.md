# PHASE 0 — ARCHITECTURE & DATA CONTRACT REVIEW

**Project:** `fx_monte_carlo`  
**Date:** 2026-11-03  
**Reviewer:** Forensic Architecture Review (Read-Only)  
**Source of Truth:** Master_Blueprint_v1.0.md, Master_Blueprint_v1.0_phase0.md

---

## 1. EXECUTIVE SUMMARY

### Overall Verdict: **CONDITIONALLY APPROVED — MINOR DECISIONS REQUIRED**

Phase 0 审查发现 **3 个 BLOCKING 级问题**、**5 个 HIGH 级问题**、**12 个 MEDIUM 级问题**。架构方向与 Master Blueprint 高度一致，但存在以下必须在 Phase 1 开始前解决的硬约束：

### Critical Findings (Blocking)

| # | Finding | Severity | Evidence |
|---|---------|----------|----------|
| B-1 | `build_api.py` 无 Fib 过滤，会将 Fib 文件注入公开 API | CRITICAL | `build_api.py:52-64` 无任何 `_fib` 过滤逻辑 |
| B-2 | `fib_mc_segment.py::locate_zone()` 边界约定违反半开区间规范，且不处理超出范围价格 | HIGH | 实测：pos=0.236 返回 zone 1 而非 zone 0；pos=-10→zone 0；pos=150→zone 5 |
| B-3 | `fib_mc_segment.py` 输出包含交易指令标签（`BUY_ZONE`/`SELL_ZONE`/`SELL_LIMIT`/`BUY_LIMIT`），违反"纯描述性"规范 | HIGH | `fib_mc_segment.py:60-67 fib_bias_action()` 生成的 `action` 字段写入 JSON |
| B-4 | metadata.total_pairs 报告 35 但实际成功生成 29 对 | MEDIUM | `mc_data.yml` 35 条目含 6 个重复，`fx_monte_carlo.py` 静默去重但元数据未更新 |
| B-5 | 无 `batch_id`/`schema_version`/`algorithm_version`/`configuration_fingerprint`/`source_data_timestamp` | CRITICAL | 所有 47 个现有 JSON 文件的 metadata 均只有 6 个字段 |
| B-6 | 两个独立 MC 引擎：`fx_monte_carlo/` 用 Student-t(df=5)，`ai_training_cnn/` 用 Normal | HIGH | 数学上不同分布，但 Blueprint 未明确哪个是主引擎 |
| B-7 | `mc_loader_local.py` 不存在，`log_mc_observation` / `resolve_pending_mc_observations` 均为 None | MEDIUM | `fx_monte_carlo.py:39-46` ImportError fallback |
| B-8 | ai_training_cnn 存在 `blend_metric()` 混合 D+W，违反 Blueprint D/W 隔离 | MEDIUM | `fx_trade_bot_utils.py` blend 相关逻辑 |
| B-9 | 非原子写入：直接 `Path.write_text()` | MEDIUM | `fx_monte_carlo.py` 和 `fib_mc_segment.py` |
| B-10 | `range_90` 端点四舍五入到 6 位小数，元数据未记录 confidence=0.90 | MEDIUM | `fib_mc_segment.py:83-85 round(edge[a], 6)` |
| B-11 | pair 身份未一致化：YAML 用 `EURUSD`，输出 JSON 用 `EURUSD=X` | LOW | `fx_monte_carlo.py:202` 追加 `=X`，但 YAML 未统一 |
| B-12 | 确定性种子 np.random.seed(42) 硬编码，未记录 | LOW | `fx_monte_carlo.py:237` |

### Phase 1 Readiness

**Conditional:** 3 个 CRITICAL 问题必须在 Phase 1 开始前通过架构决策或契约修正来处理；5 个 HIGH 问题建议在 Phase 1 一并解决。其余 MEDIUM/LOW 问题可在 Phase 2/3 修复。

---

## 2. ACTUAL SYSTEM ARCHITECTURE

### 2.1 Discovered File Map

**主项目（fx_monte_carlo）**：
```
/home/qili/projects/fx_monte_carlo/
├── fx_monte_carlo.py          ← MC 引擎 (Student-t df=5, D+W, 种子42)
├── fib_mc_segment.py          ← Fib 注解 (与 ai_training_cnn 版本 IDENTICAL)
├── build_api.py               ← 公开 API 构建 (扫描 mc_results/*.json)
├── mc_data.yml                ← YAML 配置 (35 pair 条目 / 29 唯一)
├── run_fx_mc.sh               ← 调度脚本 (每日 D, 周一额外 W)
├── mc_results/                ← 单一输出目录 (47 文件)
│   ├── mc_D_all_pairs_*.json  (34 个原始 D 文件)
│   ├── mc_W_all_pairs_*.json  (11 个原始 W 文件)
│   ├── mc_D_all_pairs_20261103_fib.json  ← Fib 标注版本
│   └── mc_W_all_pairs_20261103_fib.json  ← Fib 标注版本
├── api/                       ← build_api 输出目录
└── get_mc_data.py             ← CLI 消费者
```

**相关项目（ai_training_cnn）**：
```
/home/qili/projects/ai_training_cnn/
├── fx_monte_carlo.py          ← 不同的 MC 引擎 (Normal, D+H4)
├── fib_mc_segment.py          ← 与 fx_monte_carlo 版本 IDENTICAL
├── fx_trade_bot_utils.py      ← load_mc_bundle + blend_metric
├── mc_bundle_loader.py        ← 混合 D+W 概率
└── tests/                     ← 存在但未被 Blueprint 涵盖
```

**缺失文件：**
- `utils/mc_loader_local.py` — 被 `fx_monte_carlo.py` 导入但不存在
- 任何 batch_id 生成器
- 任何 Shadow Observation 模块
- 任何 Outcome Resolver 模块
- 任何 Statistical Validation 模块
- 任何配置指纹生成器

### 2.2 Actual Execution Flow

```
run_fx_mc.sh
  │
  ├─> fx_monte_carlo.py D          (每日)
  │     │
  │     ├─ 加载 mc_data.yml
  │     ├─ yfinance 拉取历史价格
  │     ├─ Student-t Monte Carlo (5000 sims, seed=42)
  │     ├─ write mc_results/mc_D_all_pairs_YYYYMMDD_HHMM.json  ← 非原子
  │     ├─ log_mc_observation(data)        ← None (module missing)
  │     └─ resolve_pending_mc_observations(current_prices)  ← None (module missing)
  │
  ├─> fx_monte_carlo.py W          (仅周一)
  │     │
  │     └─ 同上但 weekly_* 参数
  │
  └─> fib_mc_segment.py YYYYMMDD   (手动或未调度)
        │
        ├─ 选择该日最早 MC 文件
        ├─ 对每对执行 segment_pair()
        │     ├─ locate_zone(current_price, range_90[0], range_90[1])
        │     └─ 生成 labels.action = "SELL_LIMIT" / "BUY_ZONE" ...
        └─ write mc_results/mc_TF_all_pairs_YYYYMMDD_fib.json

  [独立]
  build_api.py
    ├─ glob("mc_results/*.json")   ← 不排除 _fib.json!
    ├─ 按 tf 过滤: name.startswith("mc_"+tf+"_")
    ├─ 按 pair 聚合, 取 latest generated_utc
    └─ 写入 api/{daily,weekly}/latest/{pair}.json
```

### 2.3 Key Runtime Evidence

**文件统计（2026-11-03）：**
- MC 原始文件：34 D + 11 W = **45 个**
- Fib 标注文件：2 个（D 和 W 各一）
- 总计：**47 个 JSON 文件**

**pair 去重：**
- mc_data.yml: `35` 条目（6 个重复：EURUSD×2, GBPUSD×2, NZDUSD×2, USDCAD×2, USDCHF×2, USDJPY×2）
- 实际运行时：Python dict 自动去重 → **29 个唯一 pair**
- 但 `metadata.total_pairs` 仍报告 `35`（虚假计数）

**两个引擎的数学差异：**

| 属性 | fx_monte_carlo/ | ai_training_cnn/ |
|------|-----------------|-------------------|
| 分布 | Student-t df=5 | Normal (高斯) |
| 周期 | D + W | D + H4 |
| 种子 | 42 | 42 |
| 配置 | YAML | 硬编码 |
| Fib 相同 | 是 | 是 |

---

## 3. MASTER BLUEPRINT TRACEABILITY MATRIX

### 3.1 Core Requirements

| ID | Blueprint Requirement | Actual Evidence | Status | Gap | Recommendation |
|----|----------------------|-----------------|--------|-----|----------------|
| R-1 | Monte Carlo 为统计模拟引擎 | `fx_monte_carlo.py` Student-t MC，5000 sims | ✅ IMPLEMENTED | 两个引擎数学不同 | 主引擎明确为 `fx_monte_carlo/` Student-t 版本 |
| R-2 | Fib 为描述性价格位置层 | `fib_mc_segment.py` 对 range_90 划分 | ✅ IMPLEMENTED | 含交易指令标签 | 移除 action 字段或改为 PURELY_DESCRIPTIVE |
| R-3 | Shadow Observation 记录不影响交易 | 无模块存在 | ❌ NOT IMPLEMENTED | 完全缺失 | Phase 2 实现 |
| R-4 | 统计验证收集可测量价值 | 无模块存在 | ❌ NOT IMPLEMENTED | 完全缺失 | Phase 4 实现 |
| R-5 | 组件不得影响交易决策 | 当前 MC/Fib 不直接接入 | ⚠️ PARTIAL | ai_training_cnn blend_metric 混合 D+W | 禁止 blend 逻辑 |
| R-6 | 概率有明确术语语义 | `p_up`/`p_down` 已定义为终端价格概率 | ✅ IMPLEMENTED | 未区分 terminal vs path-touch | 添加字段注释 |
| R-7 | 边界用半开区间 [a,b) | `locate_zone()` 用双侧包含 `a<=pos<=b` | ❌ NOT IMPLEMENTED | 违反规范 | 修正为 pos<b 归入上区 |
| R-8 | 超出范围价格 → BELOW_RANGE/ABOVE_RANGE | pos=-10→zone 0, pos=150→zone 5 | ❌ NOT IMPLEMENTED | 静默映射到内部区间 | 添加 range_status 字段 |
| R-9 | range_90 为 90% 置信区间 | `mc_data.yml confidence: 0.90`，无元数据 | ⚠️ PARTIAL | 元数据无 confidence 字段 | 添加 `confidence: 0.90` 到 metadata |
| R-10 | D1/W1 独立存储/独立分析 | 文件名含 D/W 前缀 | ✅ IMPLEMENTED | 共享 mc_results 目录 | Phase 1 前保持现状，文档明确 |
| R-11 | 单一输出目录 | mc_results/ 为单一目录 | ✅ IMPLEMENTED | Fib 文件也写入同目录 | Phase 1 增加过滤 |
| R-12 | 可复现历史 MC 运行 | seed=42 硬编码 | ⚠️ PARTIAL | 无 batch_id/algorithm_version/config_fingerprint | Phase 1 添加 provenance 元数据 |
| R-13 | API 与交易消费者隔离 | `load_mc_bundle` 用严格 regex 过滤 Fib ✅ | ✅ IMPLEMENTED | `build_api` 无 Fib 过滤 ❌ | build_api 必须过滤 _fib.json |
| R-14 | 原子写入 | 直接 Path.write_text() | ❌ NOT IMPLEMENTED | 写一半崩溃会损坏 | tmp+rename 模式 |
| R-15 | Pair identity 一致 | YAML: EURUSD, JSON: EURUSD=X | ⚠️ PARTIAL | 两种表示共存 | YAML 统一为 EURUSD=X 或添加映射 |
| R-16 | Deduplication 显式 | Python dict 隐式去重 | ⚠️ PARTIAL | metadata.total_pairs 虚假计数 | 记录 requested vs unique vs successful |
| R-17 | 零宽 range 明确 | hi<=lo 返回 zone 3 | ⚠️ PARTIAL | 应标记为 INVALID_RANGE | 添加 range_status=ZERO_WIDTH |
| R-18 | mc_loader_local.py 存在 | ImportError fallback | ❌ NOT IMPLEMENTED | log_mc_observation=None | 创建此模块（Phase 2） |
| R-19 | batch_id 存在 | 完全缺失 | ❌ NOT IMPLEMENTED | 无批次身份 | Phase 1 添加 |
| R-20 | schema_version / algorithm_version | 完全缺失 | ❌ NOT IMPLEMENTED | 无版本追溯 | Phase 1 添加 |

### 3.2 Summary Statistics

| Status | Count |
|--------|-------|
| ✅ IMPLEMENTED | 6 |
| ⚠️ PARTIAL | 5 |
| ❌ NOT IMPLEMENTED | 7 |
| CONTRADICTORY | 0 |
| NOT VERIFIED | 0 |

---

## 4. ACTUAL MODULE DEPENDENCY ANALYSIS

### 4.1 Actual Dependency Graph

```
                  mc_data.yml  ←── fx_monte_carlo.py  ──┐
                                                       │
                                         yfinance API   │
                                                       │
                                    mc_results/*.json   │
                                              │         │
                              ┌───────────────┼─────────┤
                              ▼               ▼         │
                    fib_mc_segment.py  build_api.py     │
                              │               │         │
                              ▼               ▼         │
                    mc_results/*_fib.json   api/        │
                              │                         │
                              │   ai_training_cnn/       │
                              │   fx_trade_bot_utils.py  │
                              │   load_mc_bundle()      │
                              │   (strict regex 过滤)    │
                              │                         │
                              │   mc_bundle_loader.py    │
                              │   blend_metric()  ──────┘ ← 违反 D/W 隔离
                              │
   ✗ utils/mc_loader_local.py 不存在 (log_mc_observation / resolve_pending 均 None)
   ✗ Shadow Observation 不存在
   ✗ Outcome Resolver 不存在
   ✗ Statistical Validator 不存在
```

### 4.2 Dependency Violations

| Violation | Evidence | Severity |
|-----------|----------|----------|
| build_api 未过滤 Fib 文件 | `build_api.py:52-64` glob 不过滤 | CRITICAL |
| ai_training_cnn blend_metric 混合 D+W | 引入概率合并 | MEDIUM |
| build_api 和 fx_monte_carlo 无循环依赖 | ✅ | — |
| fx_trade_bot_utils::load_mc_bundle 正确过滤 Fib | regex `_(\d{4})` 不匹配 `_fib` | ✅ |

### 4.3 Independent Modules (No Dependencies)

- `mc_data.yml` — 纯配置
- `run_fx_mc.sh` — 调度器
- Fib 文件 — 独立输出，build_api 错误摄入

---

## 5. PROPOSED MODULE BOUNDARIES

### 5.1 Target Architecture (No Phase 1 Implementation Required — Contract Only)

```
┌──────────────────────────────────────────────────────────┐
│                  PHASE 1 (Base)                           │
│                                                           │
│  MC Engine ──► Validation ──► MC Batch JSON                │
│  (Student-t)    (basic)     (batch_id, schema_version,    │
│                              config_fingerprint,          │
│                              confidence, source_data_ts)   │
│                                                           │
│  build_api  ──► api/   [EXCLUDES _fib.json]               │
│                                                           │
└──────────────────────────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────┐
│                  PHASE 2 (Research)                       │
│                                                           │
│  MC Batch ──► Fib Annotator ──► Fib JSON (separate file)  │
│  (validated)                      (no action labels)      │
│                                                           │
│  MC + Fib ──► Shadow Observation ──► observation store   │
│                                                           │
└──────────────────────────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────┐
│                  PHASE 3                                  │
│                                                           │
│  Future Market Data ──► Outcome Resolver                  │
│                                                           │
└──────────────────────────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────┐
│                  PHASE 4                                  │
│                                                           │
│  Resolved Observations ──► Statistical Validation         │
│                                                           │
└──────────────────────────────────────────────────────────┘

Constraints:
  1. MC Engine ──✗── Fib       (MC 不依赖 Fib)
  2. Fib  ──► validated MC     (Fib 依赖已验证的 MC)
  3. Shadow ──► validated MC + Fib
  4. Outcome ──► stored observations + future market data
  5. Validator ──► resolved observations
  6. 无研究组件 ──► 交易决策
```

### 5.2 Dependency Contract Enforcement Mechanisms

| Mechanism | Description |
|-----------|-------------|
| Fib 输出写入 `mc_results_fib/` 而非 `mc_results/` | 物理隔离，build_api 无法触及 |
| build_api 增加硬编码排除：`if '_fib' in path.name: continue` | 双保险 |
| ai_training_cnn blend_metric 禁止 | 代码审查门控 |
| 所有新模块放入独立研究包 | 命名空间隔离 |

---

## 6. DATA CONTRACTS

### 6.1 MC Batch Data Contract

#### Current State

现有 metadata（6 字段）：
```json
{
  "timeframe": "D",
  "generated_utc": "2026-11-03T05:04:47.824019+00:00",
  "total_pairs": 35,
  "simulations": 5000,
  "lookback": 90,
  "forecast": 5
}
```

#### Proposed Contract (v2 — PHASE 1 TARGET)

| Field | Type | Required | Current | Description |
|-------|------|----------|---------|-------------|
| `batch_id` | string (uuid7) | ✅ | ❌ | 唯一批次身份，格式：`mc_{tf}_{YYYYMMDD}_{HHMMSS}_{shortuuid}` |
| `schema_version` | string semver | ✅ | ❌ | 输出 JSON schema 版本，初始 "2.0.0" |
| `algorithm_version` | string | ✅ | ❌ | MC 算法身份，如 "student_t_d5_v1" |
| `generated_utc` | string ISO8601 | ✅ | ✅ | 现有 |
| `source_data_timestamp` | string ISO8601 | ✅ | ❌ | yfinance 数据拉取时间（市场时间对齐） |
| `timeframe` | string "D"\|"W"\|"H4" | ✅ | ✅ | 现有 |
| `configuration_fingerprint` | string sha256 hex | ✅ | ❌ | 对 mc_data.yml 关键字段哈希 |
| `configuration` | object | ✅ | ❌ | 配置快照完整副本（用于审计） |
| `requested_pairs` | integer | ✅ | ❌ | YAML 中请求的 pair 数（35） |
| `unique_pairs` | integer | ✅ | ❌ | 去重后的唯一 pair 数（29） |
| `successful_pairs` | integer | ✅ | ❌ | 成功生成的 pair 数（29） |
| `failed_pairs` | list of strings | ✅ | ❌ | 拉取失败的 pair 列表 |
| `batch_status` | enum | ✅ | ❌ | "COMPLETE" / "PARTIAL" / "FAILED" |
| `confidence` | float | ✅ | ❌ | `mc_data.yml confidence`，当前 0.90 |
| `student_t_df` | integer | ✅ | ❌ | `mc_data.yml student_t_df`，当前 5 |
| `results` | object | ✅ | ✅ | 现有，value 为 Pair Result Contract |

#### Configuration Fingerprint Determinism Recommendation

由于 `mc_data.yml` 配置简单（标量值 + 列表），建议：
```
canonical_yaml = yaml.safe_dump(cfg, sort_keys=True, default_flow_style=True)
fingerprint = hashlib.sha256(canonical_yaml.encode()).hexdigest()[:16]
```
**不**需要包含 `pairs` 列表在 hash 中（太冗长），但必须包含 `simulations`、`confidence`、`student_t_df`、`daily_*`、`weekly_*`。

### 6.2 MC Pair Result Data Contract

#### Current State

现有 pair 字段（21 个）：
```
pair, timeframe, current_price, ann_drift_pct, ann_vol_pct,
range_90, percentile_rank, p_up, p_down, p_up_pct, p_down_pct,
touch_upper_pct, touch_lower_pct, var_95, cvar_95, expected_price,
regime, lookback, forecast, simulations, generated_utc
```

#### Proposed Contract

所有现有字段保持不变（向后兼容）。补充：

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `batch_id` | string | ✅ | 引用父 batch |
| `algorithm_version` | string | ✅ | 引用算法身份 |
| `confidence` | float | ✅ | 冗余但必需，独立消费者无需回溯 metadata |
| `source_data_timestamp` | string ISO8601 | ❌ | 可选，当前价格的时间戳 |
| `calculation_precision` | integer | ❌ | 6（range_90 端点四舍五入精度） |
| `result_status` | enum | ✅ | "VALID" / "ZERO_VOLATILITY" / "ZERO_WIDTH_RANGE" / "OUTLIER" |

#### Critical Semantic Distinctions (Do NOT Conflate)

| Concept | Field | Definition |
|---------|-------|------------|
| **Terminal-price p_up** | `p_up` (或 `p_up_pct`) | 预测期结束时价格高于 current_price 的概率 |
| **Path-touch upper** | `touch_upper_pct` | 预测期内任何时刻价格触达 range_90[1] 的概率 |
| **Terminal-price CI** | `range_90` | 预测期结束时价格的 90% 置信区间 |
| **Realized outcome** | Future data | 未来实际市场价格（不在 MC 输出中） |

**⚠️ p_up 不是"盈利概率"** — 它只是方向概率，没有考虑交易成本、止盈止损等。

### 6.3 Confidence Interval Contract

#### Current State Analysis

| 属性 | 实际值 |
|------|--------|
| confidence 配置来源 | `mc_data.yml: confidence: 0.90` |
| 端点计算 | numpy 分位数 |
| 端点精度 | Fib 注解时 `round(edge[a], 6)` → 6 位小数 |
| 元数据记录 confidence | ❌ 未记录 |
| 元数据记录端点精度 | ❌ 未记录 |
| 消费者字段名 | `range_90`（不可配置） |

#### Backward-Compatibility Migration Strategy

**Phase 1 增量策略：**
1. 保留字段名 `range_90` 不变
2. 在 metadata 添加 `confidence: 0.90`
3. 在 pair 结果添加冗余 `confidence: 0.90`
4. 新增可选字段 `range_{0.90}` 作为别名（未来方向）
5. 所有现有消费者继续工作

**Phase 2 可选策略：**
- 如果未来需要 95% CI，新增 `range_95` 字段
- 新 schema_version `"2.0.0"` 可同时包含多个 range 字段
- **旧文件永远不重写**（不可变历史）

### 6.4 Fib Annotation Data Contract

#### Critical Bug Fix Before Phase 1

**`locate_zone()` 边界约定必须改为半开区间 [a, b)：**
```python
# 当前: 双侧包含 (违反规范)
if a <= pos <= b: return i

# 应改为: 半开区间 (pos<b 归入当前区间；pos>=b 归入下一区间)
if a <= pos < b: return i
```

**超出范围价格必须显式标记：**
```python
if pos < 0.0:
    return "range_status": "BELOW_RANGE"
if pos > 1.0:
    return "range_status": "ABOVE_RANGE"
```

#### Proposed Fib Schema (Purely Descriptive — NO ACTION LABELS)

```jsonc
{
  "fib_algorithm_version": "Fibonacci_grid_v1",
  "source_batch_id": "mc_D_20261103_041842_a1b2c3",
  "source_pair": "EURUSD=X",
  "source_range": [1.10707, 1.12888],
  "source_confidence": 0.90,
  "ratios": [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0],
  "levels": {
    "fib_0": 1.10707,
    "fib_23.6": 1.11222,
    "fib_38.2": 1.11542,
    "fib_50": 1.11797,
    "fib_61.8": 1.12052,
    "fib_78.6": 1.12428,
    "fib_100": 1.12888
  },
  "zones": [
    { "tag": "F0",    "label": "Deep Discount",    "ratio": [0.0, 0.236],   "price": [...] },
    { "tag": "F236",  "label": "Discount",          "ratio": [0.236, 0.382], "price": [...] },
    { "tag": "F382",  "label": "Below Equilibrium", "ratio": [0.382, 0.5],   "price": [...] },
    { "tag": "F5",    "label": "Above Equilibrium", "ratio": [0.5, 0.618],   "price": [...] },
    { "tag": "F618",  "label": "Premium",           "ratio": [0.618, 0.786], "price": [...] },
    { "tag": "F786",  "label": "Deep Premium",      "ratio": [0.786, 1.0],   "price": [...] }
  ],
  "current_zone": {
    "tag": "F5",
    "label": "Above Equilibrium",
    "zone_index": 3,
    "position_in_zone_pct": 52.0,
    "ratio_position": [0.5, 0.618],
    "price_position": [1.11797, 1.12052]
  },
  "range_status": "IN_RANGE",  // or BELOW_RANGE / ABOVE_RANGE / ZERO_WIDTH / INVALID
  "calculation_precision": 6,
  "labels": {
    "fib_zone": "FIB F5 | Above Equilibrium",
    "fib_position": "FIB 4/6 52% in F5"
    // action 字段 REMOVED — 纯描述性
  }
}
```

**禁止字段（Phase 1 立即移除）：**
- `labels.action` — 包含 BUY_ZONE/SELL_ZONE/BUY_LIMIT/SELL_LIMIT 交易指令

### 6.5 Shadow Observation Data Contract

#### Proposed Schema (Immutable Snapshot)

```jsonc
{
  "observation_id": "obs_{batch_id}_{pair}_{timestamp}",
  "observation_schema_version": "1.0.0",
  "source_batch_id": "mc_D_20261103_041842_a1b2c3",
  "source_pair": "EURUSD=X",
  "timeframe": "D",
  "observation_utc": "2026-11-03T04:18:42Z",
  "current_price": 1.11932,
  "mc_snapshot": {
    "p_up": 42.1,
    "p_down": 57.9,
    "range_90": [1.10707, 1.12888],
    "confidence": 0.90,
    "expected_price": 1.11797,
    "ann_vol_pct": 4.32
  },
  "fib_snapshot": {
    "zone_tag": "F5",
    "zone_index": 3,
    "position_in_zone_pct": 52.0,
    "range_status": "IN_RANGE"
  },
  "validation_status": "PENDING",   // PENDING / RESOLVED / EXPIRED
  "resolution_status": "UNRESOLVED"  // UNRESOLVED / RESOLVED / MISSING_DATA
}
```

**不可变 vs 可引用的决策：**

| 值 | 复制到 observation？ | 理由 |
|----|---------------------|------|
| current_price | ✅ 复制 | 核心快照值 |
| mc_snapshot | ✅ 复制 | 独立于源 batch（MC 可能重跑） |
| fib_snapshot | ✅ 复制 | 独立于源 batch |
| source_batch_id | ✅ 存储 | 溯源 |
| source_pair | ✅ 存储 | 溯源 |

### 6.6 Outcome Record Data Contract

```jsonc
{
  "outcome_id": "out_{observation_id}_{horizon}",
  "observation_id": "obs_mc_D_20261103_...",
  "horizon": 5,                      // forecast days
  "target_utc": "2026-11-08T00:00:00Z",
  "actual_utc": "2026-11-08T23:59:59Z",  // 实际获取到未来数据的时间
  "future_close": 1.12000,           //  Horizon 结束时价格
  "return_pct": 0.059,               //  (future_close - current_price) / current_price * 100
  "direction": "UP",                 //  UP / DOWN / FLAT
  "max_favourable_excursion_pct": 1.2,
  "max_adverse_excursion_pct": -0.8,
  "mc_range_covered": true,          //  终端价格是否在 range_90 内
  "path_touched_upper": true,
  "path_touched_lower": false,
  "resolution_status": "RESOLVED",   // RESOLVED / MISSING_DATA / CORRECTED_DATA
  "market_data_source": "yfinance"
}
```

**关键约束：**
- Outcome 数据绝不修改 Observation 历史值
- Corrected market data 创建新 outcome 记录，旧 outcome 保留但标记为 SUPERSEDED
- 同一 observation + horizon 可有多 outcome，但仅一个为 ACTIVE

---

## 7. FIVE ARCHITECTURAL DECISIONS

### Decision 1 — API and Consumer Isolation

#### Question

`build_api.py` 扫描 `mc_results/*.json`，不过滤 Fib 文件。当前有 2 个 Fib 文件会被摄入。`_group_latest()` 会选择 Fib 版本（因为 generated_utc 更新）覆盖 MC 版本。

但 `fx_trade_bot_utils::load_mc_bundle` 使用严格 regex `_(\d{4})` 匹配，**不会**摄入 Fib 文件。

#### Option A: build_api 排除 Fib 输出

```python
# build_api.py _load_results() 中
if '_fib' in path.name: continue
```

**优点：** 最小改动，fib 文件留在 mc_results/ 但被跳过
**缺点：** Fib 文件仍在同一目录，技术上可能被其他消费者扫描

#### Option B: Fib 输出到独立目录

```
mc_results/           ← 纯 MC 原始输出
mc_results_fib/       ← Fib 标注输出
```

**优点：** 物理隔离，零误摄入风险
**缺点：** 稍有变更成本

#### Option C: 版本化数据源 + 显式选择

build_api 改为从 MC 引擎直接获取，不扫描文件系统。

**优点：** 架构清晰
**缺点：** 架构大改，Phase 1 不可行

#### Recommendation: **Option B (Primary) + Option A (Defense-in-Depth)**

1. Fib 文件输出到 `mc_results_fib/`（物理隔离）
2. build_api 额外加 `_fib` 排除（防御性编程）
3. 研究 API 独立读取 `mc_results_fib/`

### Decision 2 — D1/W1 Observation Schedule

#### Current State

| 组件 | 调度 | 市场时间假设 |
|------|------|-------------|
| D1 MC | `run_fx_mc.sh` 每日 | 脚本调用时（假设 D1 bar 已关闭） |
| W1 MC | 周一执行 | 假设周一 W1 bar 已关闭（矛盾！W1 bar 周一刚开） |
| D1 fib_mc_segment | 手动 | 无 |

#### Critical Issue: W1 的周一执行矛盾

```
周一 00:00 UTC: W1 bar 刚开始
周一 04:30 UTC: run_fx_mc.sh 执行 python fx_monte_carlo.py W
               → yfinance 拉取 W1 数据 → 仅含周一部分数据
               → W1 MC 实际上是"半周"数据
```

`fx_trade_bot_utils::load_mc_bundle` 对 W 使用"本周一以来的文件"（`d >= monday_str`），确认了这种半周语义是**有意设计**。

#### Recommendation

**1. D1 观察触发：D1 bar 关闭后 1 小时 UTC（约周五 22:00 UTC）**
- 不假设脚本在正确时间执行，改为检查 yfinance 最新可用 D1 bar 的时间戳
- 如果脚本执行时间早于 D1 bar 关闭时间 → 跳过该次运行

**2. W1 观察触发：W1 bar 关闭后 1 小时 UTC（周日约 22:00 UTC）**
- 或者，保持"半周 MC"作为设计决策并显式记录为 `semantics: HALF_WEEK_PROGRESSION`
- **关键：必须在 metadata 中记录 W1 的实际覆盖时间范围**

**3. D1 和 W1 独立调度：**
- D1 每次 D1 bar 关闭时独立记录一个 observation
- W1 每次 W1 bar 关闭时独立记录一个 observation
- 两者各自保留自己的 batch_id 和 source_timestamp
- **绝不混合**

**4. 所有内部时间戳强制 UTC，外部消费者看到 UTC。**

### Decision 3 — Reproducibility

#### Current Status Per Component

| Aspect | Value | Sufficient for Reproducibility? |
|--------|-------|--------------------------------|
| Random seed | `np.random.seed(42)` | ✅ 但硬编码 |
| Input price history | yfinance API 实时拉取 | ❌ yfinance 历史数据可能修正/变更 |
| Algorithm version | Student-t df=5 | ⚠️ 未记录到输出 JSON |
| Simulation count | 5000 | ✅ 在 metadata 中 |
| Configuration | 散落在 YAML | ❌ 无快照/指纹 |
| Numerical precision | numpy float64 | ❌ 未记录 |
| External dependency | yfinance API | ❌ 未记录 source timestamp |

#### Recommendation: Three Tiers

**Tier 1 — Configuration Reproducibility（Phase 1）**
```
batch_id, schema_version, algorithm_version, configuration_fingerprint
configuration (完整 YAML 快照), simulation_count, seed (硬编码 42), 
source_data_timestamp, student_t_df
```
→ 足以知道"在什么配置下什么时间跑了什么"，但不保证数值完全可复现

**Tier 2 — Simulation Reproducibility（Phase 2+）**
```
input_price_history_snapshot (或 source URL + timestamp + yfinance ticker version)
numpy version, yfinance version
```
→ 足以保证数值可复现（yfinance 可能提供不同历史值）

**Tier 3 — Full Historical Data Reproducibility（Phase 4+）**
```
每对的完整 yfinance close 序列（lookback 90/104 天）
```
→ 足以重跑并得到 bit-identical 结果（除 API 变数据的情况）

**当前 Tier 1 不足（缺少 algorithm_version 和 config_snapshot）**，Tier 2/3 尚未开始。

### Decision 4 — Baseline and Candidate Storage

| Option | Backward Compat | Consumer Isolation | Complexity | Traceability | Rollback | Historical Compare | Accidental Ingest |
|--------|----------------|-------------------|------------|--------------|----------|-------------------|------------------|
| A. Separate dirs | ✅ MC 不受影响 | ✅ 物理隔离 | Low | ✅ 天然 | ✅ 切回 | ✅ 跨目录对比 | ✅ 不可能 |
| B. Versioned files in same dir | ⚠️ 新文件名 | ⚠️ build_api 可能摄入 | Low | ⚠️ 按文件名 | ⚠️ 手动排除 | ✅ 直接 | ❌ build_api 需过滤 |
| C. Separate research dataset | ✅ MC 不受影响 | ✅ 天然隔离 | Medium | ✅ | ✅ | ✅ 跨系统 | ✅ 不可能 |

#### Recommendation: **Option C — 独立研究数据集 + 不可变源引用**

```
mc_results/                 ← 原始 MC 输出（baseline），永远不改动
mc_results_fib/             ← Fib 标注输出（Phase 2）
observations/               ← Shadow Observation 记录（Phase 2）
outcomes/                   ← Outcome 解析结果（Phase 3）
```

**理由：**
- Baseline MC 输出保持完全可恢复（物理隔离）
- 历史文件不可变，新数据集只增不改
- 研究组件的意外操作不会影响 baseline
- Rollback 等于"停止写新数据集"

### Decision 5 — `range_90` Compatibility

#### Current Consumers

| Consumer | 位置 | 匹配模式 | Fib 摄入？ |
|----------|------|----------|-----------|
| build_api | fx_monte_carlo/ | glob("*.json") + startswith("mc_{tf}_") | ❌ 无显式过滤（会摄入） |
| load_mc_bundle | ai_training_cnn/ | regex `_(\d{4})` | ✅ 正确排除 `_fib` |
| get_mc_data.py | fx_monte_carlo/ | CLI，可指定文件 | 取决于用户选择 |

#### Recommendation: **增量增强 + 语义保护**

**Phase 1 — 零破坏性：**
1. 保留 `range_90` 字段名和计算不变
2. 在 metadata 和 pair 级别添加 `confidence: 0.90`
3. 消费者可以（但不必须）开始读取 confidence 元数据
4. 旧消费者完全不受影响

**Phase 2 — 可选多置信度：**
1. 新 schema_version `"2.0.0"` 可同时包含 `range_90` 和 `range_95`
2. 用 schema_version 区分新旧文件
3. **旧文件永不重写**（不可变历史原则）

**Phase 3 — 新消费者强制使用 confidence：**
- 新 API 消费者必须检查 confidence 字段
- 旧消费者继续只读 `range_90`

---

## 8. D1/W1 ARCHITECTURAL SEPARATION VERIFICATION

### Current State

| 约束 | Status | Evidence |
|------|--------|----------|
| D1 和 W1 是独立 MC 运行 | ✅ 是 | 不同配置参数 (lookback=90 vs 104)，不同 simulation seed |
| D1 和 W1 概率不共享 | ✅ 是（输出层面） | 独立 JSON 文件 |
| D1 和 W1 Fib 不共享 | ✅ 是 | 独立标注 |
| ai_training_cnn blend_metric 混合 | ❌ 违反 | ai_training_cnn/mc_bundle_loader.py blend 逻辑 |
| D1/W1 互相覆盖 | ✅ 不覆盖 | 各自 pair JSON 独立 |
| D1/W1 自动 veto | ✅ 不 veto | 各自独立 |

### Recommended Comparison Method

**必须不合并底层统计人口：**
```python
# 正确方法：对比独立观察
d1_obs = load_observation(pair, "D", date)
w1_obs = load_observation(pair, "W", date)

# 报告：D1 range_90 vs W1 range_90，各自独立
# 不做概率合并，不做 Fib 合并
# 可以做相关性分析（D1 p_up vs W1 p_up 的时间序列相关系数）
```

**严禁方法：**
```python
# 错误：blend 后的概率不是任何真实统计人口
blended_p_up = w1_weight * w1.p_up + d1_weight * d1.p_up
```

---

## 9. SHADOW OBSERVATION DESIGN — ELIGIBILITY AND LIFECYCLE

### Eligibility Criteria

Observation 仅在以下条件满足时创建：
1. MC batch 存在且 status = COMPLETE 或 PARTIAL（无 CRITICAL failures）
2. Pair result 存在且 result_status = VALID
3. `range_90[0] < current_price < range_90[1]`（或允许 OUT_OF_RANGE 状态但标记 range_status）
4. Fib segmentation 完成且不产生 INVALID_RANGE

### Uniqueness

Observation identity = `observation_id = hash(source_batch_id + source_pair + timeframe + current_price_precision)`
→ 同一 pair 在同一 batch 中只能产生一个 observation

### Idempotent Lifecycle

| Event | Action | Idempotency |
|-------|--------|-------------|
| 处理同一 batch 两次 | 检查 observation_id 是否存在，存在则跳过 | ✅ |
| 源 batch 不完整 | 创建 observation 但标记 `validation_status: PENDING_SOURCE` | N/A |
| 当前价格超出 MC range | 创建 observation，标记 `fib_snapshot.range_status: BELOW_RANGE` / `ABOVE_RANGE` | ✅ |
| Fib 分段无效 | 创建 observation，标记 `fib_snapshot.range_status: INVALID_RANGE` | ✅ |
| 等待未来数据 | Pending — 无操作 | ✅ |
| 未来数据到达 | 检查 outcome_id 是否已存在，存在则跳过 | ✅ |
| 未来数据缺失（市场关闭） | 标记 `resolution_status: MISSING_DATA` | N/A |
| 历史市场数据修正 | 创建新 outcome（SUPERSEDES 旧 outcome），不修改 observation | ✅ |
| outcome 已解析 | 绝不二次解析（除非 CORRECTED_DATA） | ✅ |

### Pending Outcome Tracking

```
pending_outcomes/
  ├─ 2026-11-08.json  ← 每个目标日期一个文件
  │     { "target_utc": "...", "observation_ids": ["obs_001", "obs_002", ...] }
```

---

## 10. STATISTICAL METHODOLOGY REVIEW

### Blueprint 方法论评估

| Methodology | Soundness | Issue |
|-------------|-----------|-------|
| 概率校准曲线 | ✅ | — |
| Brier Score | ✅ | — |
| MC interval coverage | ⚠️ | Terminal-price CI vs Path-touch CI 不可混淆 |
| Fib 条件回报分布 | ⚠️ | Zone 样本量小（约 170 obs / zone 假设 29 pairs × 6 years） |
| 样本独立性 | ❌ | 连续每日观察**不独立**（价格有自相关，MC sims 有重叠） |
| 重叠观察期 | ⚠️ | D1 每天跑 forecast=5 → 观察期重叠 |
| Serial correlation | ❌ | 必须在验证模型中显式建模 |
| Pair 依赖性 | ⚠️ | EURUSD/GBPUSD 共享 USD 因子，独立假设失败 |
| Multiple testing | ⚠️ | 29 pairs × 6 zones × 2 directions = 348 tests — Bonferroni/BH 校正 |
| Regime dependence | ⚠️ | 牛市/熊市/震荡市分开评估 |

### Five Critical Statistical Pitfalls

**Pitfall 1 — 连续观察不独立**
```
错误: p-value < 0.05 → 有预测价值
正确: p-value 必须基于 clustered standard errors 或 block bootstrap
      （因为 D1 观察有 serial correlation）
```

**Pitfall 2 — p_up 不是交易盈利概率**
```
p_up = P(terminal_price > current_price)
     ≠ P(trade is profitable)
     
profit depends on: entry, stop-loss, take-profit, spread, commission
                   这些都不在 MC 模型中
```

**Pitfall 3 — MC interval coverage 不能用 path-touch 概率评估**
```
range_90 是终端价格区间 → 应比较 terminal_price 是否在 [lo, hi] 内
                    而不是路径上是否触达边界
```

**Pitfall 4 — Fib zone 平均回报差 ≠ Fib 有预测价值**
```
Zone A 平均回报 0.3%, Zone B 平均回报 -0.1%
→ 可能只是 MC p_up 的函数（zone 由 range_90 内位置决定）
→ 必须控制 MC p_up 后看 Fib 是否还有增量解释力
```

**Pitfall 5 — 滚动样本重叠**
```
每天一个 D1 MC（forecast=5）
Day T 的 outcome period: [T, T+5]
Day T+1 的 outcome period: [T+1, T+6] → 与 Day T 重叠 4 天
→ 不能把每个 outcome 当作独立样本
→ 推荐：每 5 天取一次 observation（或只看 terminal outcome）
```

### Recommendations for Phase 4 Validation

1. **主要指标：Brier Score + 校准曲线**（对 terminal direction 预测）
2. **MC interval coverage 必须与 terminal price 比较**（不是 path-touch）
3. **块 bootstrap（block=5天）** 来估计标准误差
4. **控制变量法**：Fib zone vs 仅 MC p_up 的增量 R²
5. **分 regime 评估**：用 rolling 60-day 波动率分类为 LOW/MED/HIGH vol
6. **多重比较校正**：Benjamini-Hochberg 控制 FDR
7. **Pair-level 聚合**：29 pairs × 6 zones，每个 zone 至少要有 200+ 观察才能做独立测试

---

## 11. PHASE 1 READINESS CHECKLIST

| # | Item | Status | Condition |
|---|------|--------|-----------|
| P1-1 | MC Batch Contract schema 冻结 | ✅ READY | 上文 §6.1 已定义 |
| P1-2 | Pair Result Contract schema 冻结 | ✅ READY | 上文 §6.2 已定义 |
| P1-3 | Fib Bug: locate_zone 边界修正 | ⚠️ BLOCKED | `_fib` 注释仍说 "双侧包含"，需改为半开 |
| P1-4 | Fib Bug: 超出范围标记 | ⚠️ BLOCKED | 需添加 range_status 字段 |
| P1-5 | Fib Bug: 移除交易指令标签 | ⚠️ BLOCKED | action 字段必须删除 |
| P1-6 | build_api Fib 排除 | ⚠️ BLOCKED | 或 Fib 输出到独立目录 |
| P1-7 | batch_id 生成器 | ✅ READY | uuid7 或时间戳+shortuuid |
| P1-8 | configuration_fingerprint | ✅ READY | 上文 §6.1 已定义 |
| P1-9 | metadata confidence/student_t_df | ✅ READY | 从 YAML 读取并记录 |
| P1-10 | total_pairs → requested/unique/successful | ✅ READY | 明确三步计数 |
| P1-11 | 原子写入 | ✅ READY | tmp+rename 模式 |
| P1-12 | mc_results_fib/ 独立目录 | ⚠️ REQUIRES DECISION | Option B vs A |
| P1-13 | W1 调度语义（半周 vs 完整周） | ⚠️ REQUIRES DECISION | 保持现状还是改到周日 |
| P1-14 | 算法版本标识 | ✅ READY | "student_t_df5_v1" |
| P1-15 | ai_training_cnn blend_metric 处理 | ⚠️ REQUIRES DECISION | 是否在 Phase 1 禁止 |
| P1-16 | Shadow Observation schema 冻结 | ✅ READY（Phase 2） | Phase 1 不实现，但 contract 已定 |
| P1-17 | 测试 fixtures | ⚠️ REQUIRES EVIDENCE | 检查 tests/ 下有什么 |
| P1-18 | 历史数据不可变原则文档化 | ✅ READY | Contract 已明确 |

---

## 12. UNRESOLVED DECISIONS

| ID | Question | Owner | Deadline | Impact if Delayed |
|----|----------|-------|----------|------------------|
| U-1 | Fib 文件输出目录：`mc_results_fib/` 还是留在 `mc_results/` + build_api 过滤 | User | Phase 1 开始前 | 延迟 Phase 1 |
| U-2 | W1 调度：保持周一半周还是改为周日完整周 | User | Phase 1 开始前 | 影响所有 W1 数据语义 |
| U-3 | ai_training_cnn blend_metric 是否在 Phase 1 禁止 | User | Phase 1 开始前 | 交易层可能继续混合 D+W |
| U-4 | 两个 MC 引擎：ai_training_cnn 是否应该改用 Student-t | User | Phase 2 | 否则两个引擎数学不同无法直接对比 |
| U-5 | pair identity 统一：YAML 用 `EURUSD` vs `EURUSD=X` | User | Phase 1 | metadata.pairs 字段格式 |

---

## 13. FINAL PHASE 0 VERDICT

**CONDITIONALLY APPROVED — 5 USER DECISIONS REQUIRED**

### What is Ready for Phase 1

- MC Batch Contract schema 已完整定义
- Pair Result Contract schema 已完整定义（向后兼容）
- range_90 兼容策略已完整定义
- D/W 隔离原则已明确
- 依赖边界已明确
- 统计方法论陷阱已识别

### What Must Be Resolved Before Phase 1

| Item | Severity | Action |
|------|----------|--------|
| build_api 摄入 Fib 文件 | CRITICAL | Phase 1 必须先修复（Option A + B 组合） |
| locate_zone 边界 bug | CRITICAL | Fib 输出仍在用双侧包含，Phase 1 必须修正 |
| action 交易指令标签 | CRITICAL | Phase 1 必须移除或改为纯描述性 |
| User Decision U-1 | HIGH | Fib 输出目录 |
| User Decision U-2 | HIGH | W1 调度语义 |
| User Decision U-4 | MEDIUM | 两个 MC 引擎统一 |

### Phase 1 Scope Boundary

Phase 1 应限于：
1. MC Engine 元数据增强（batch_id, schema_version, algorithm_version, config_fingerprint, confidence, student_t_df, requested/unique/successful_pairs, configuration 快照）
2. 原子写入实现
3. 修复 locate_zone 边界约定和超出范围标记
4. 移除 action 标签或改为纯描述性
5. build_api 添加 Fib 过滤
6. （待 User Decision）Fib 输出目录

Phase 1 **不应**包含：
- Shadow Observation 实现
- Outcome Resolver 实现
- Statistical Validation 实现
- blend_metric 重构（待 U-3）
- ai_training_cnn 引擎修改（待 U-4）

---

## 14. EVIDENCE APPENDIX

### File Existence Verification

| File | Location | Exists? |
|------|----------|---------|
| fx_monte_carlo.py | /home/qili/projects/fx_monte_carlo/ | ✅ |
| mc_data.yml | /home/qili/projects/fx_monte_carlo/ | ✅ |
| fib_mc_segment.py | /home/qili/projects/fx_monte_carlo/ | ✅ |
| build_api.py | /home/qili/projects/fx_monte_carlo/ | ✅ |
| get_mc_data.py | /home/qili/projects/fx_monte_carlo/ | ✅ |
| run_fx_mc.sh | /home/qili/projects/fx_monte_carlo/ | ✅ |
| utils/mc_loader_local.py | /home/qili/projects/fx_monte_carlo/ | ❌ |
| MC_FIB_SHADOW_SYSTEM_BLUEPRINT.md | — | ❌ |
| Master_Blueprint_v1.0.md | ai_training_cnn/ | ✅ |
| Master_Blueprint_v1.0_phase0.md | ai_training_cnn/ | ✅ |
| ai_training_cnn/fib_mc_segment.py | ai_training_cnn/ | ✅ (identical) |
| ai_training_cnn/fx_monte_carlo.py | ai_training_cnn/ | ✅ (different engine) |

### JSON File Sample (2026-11-03)

**原始 MC D 文件：**
```
Metadata keys: ['timeframe', 'generated_utc', 'total_pairs', 'simulations', 'lookback', 'forecast']
Pair count: 29 (YAML 有 35 条目)
metadata.total_pairs: 35 ← 虚假计数
Seed: 42 (Student-t df=5, 5000 sims, forecast=5)
```

**Fib 标注 D 文件：**
```
Metadata keys: [...基础 6 个..., fib_segmentation]
Fib fib_segmentation keys: ['method', 'ratios', 'zones', 'source_file', 'date']
Fib pair keys: [...MC 21 个..., fib]
Fib.labels.action = "SELL_LIMIT" ← 交易指令
Fib has range_status = False ← 超出范围未标记
```

### locate_zone Boundary Test Results

| pos | 期望 zone | 实际 zone | 状态 |
|-----|----------|----------|------|
| 0.0 | 0 (F0) | 0 | ✅ |
| 23.6 | 0 (F0/F236 边界，应归入 F236 或单独处理) | 1 | ⚠️ 双侧包含导致归入下区间 |
| 38.2 | 1 (F236/F382 边界) | 1 | ⚠️ |
| 100.0 | 5 (F786) | 5 | ✅ |
| -10.0 | "BELOW_RANGE" | 0 | ❌ 静默映射 |
| 150.0 | "ABOVE_RANGE" | 5 | ❌ 静默映射 |
| hi<=lo | "ZERO_WIDTH" | 3 | ❌ 静默映射 |

### build_api Fib Ingestion Simulation

```
Total JSON in mc_results/: 47
MC files: 45
Fib files: 2 (mc_D_..._fib.json, mc_W_..._fib.json)

build_api._load_results() glob("*.json") 会摄入 Fib 文件
→ _group_latest() 按 generated_utc 选择最新版本
→ Fib 文件的 generated_utc 早于 MC 文件（因为选择"最早 MC 文件"标注）
→ 实际上可能 MC 版本胜出 (时间更新的那个)
→ 但如果 Fib 文件在 MC 之后运行 → Fib 版本胜出
→ Fib 版本含 .fib_labels.action → 进入 API → 下游消费者可见交易指令
```

### ai_training_cnn vs fx_monte_carlo

| 属性 | ai_training_cnn/fx_monte_carlo.py | fx_monte_carlo/fx_monte_carlo.py |
|------|-----------------------------------|----------------------------------|
| 种子 | `np.random.seed(42)` | `np.random.seed(42)` |
| 分布 | `np.random.normal(0, 1, SIMULATIONS)` | `np.random.standard_t(STUDENT_T_DF, ...)` |
| df | N/A | 5 (Student-t) |
| 周期 | D + H4 | D + W |
| Fib 相同 | 是 | 是 |
| mc_data.yml | 硬编码 pairs | YAML 配置 |

---

**END OF PHASE 0 REVIEW**