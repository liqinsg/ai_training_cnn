
# 🧭 FX-Monte-Carlo Data Access Contract & Example

本模块为外部系统提供标准化的 **Monte Carlo 概率区间 + Fibonacci 空间分割** 纯数据契约。

---

## 1. 核心原则

* **MC提供客观的量化测算结果**（包含模拟概率、统计分位数、Fibonacci 网格区间及当前价格映射）。
* **可自由设计策略绑定**：例如用于仓位控制、网格边界、风控止损或趋势过滤。

---

## 2. API 调用参考

### `get_pair_analytics(pair, day, timeframe="D")`

* **作用**：加载指定日期最新生成的复合 JSON，并返回特定交易对的完整分析数据结构。
* **返回数据结构示例 (JSON Schema)**：

```json
{
  "timeframe": "D",
  "pair": "EURUSD=X",
  "current_price": 1.12575,
  "range_90": [1.11374, 1.13566],
  "percentile_rank": 56.0,
  "p_up": 44.0,
  "fib": {
    "levels": {
      "fib_0": 1.11374,
      "fib_50": 1.1247,
      "fib_100": 1.13566
    },
    "zones": [...],
    "current_zone": {
      "tag": "F5",
      "label": "Above Equilibrium",
      "position_in_zone_pct": 40.6
    },
    "zone_index": 3
  }
}
```

---

## 3. 调用者自由消费示例

调用者只需将 `interface.py` 放到本地，即可按需提取任意指标：

```python
from interface import get_pair_analytics

# 获取某交易对的今日数据
data = get_pair_analytics("EURUSD=X", "20261105")

if data:
    current_price = data["current_price"]
    zone_idx = data["fib"]["zone_index"]
    zone_label = data["fib"]["current_zone"]["label"]
  
    print(f"Price: {current_price} | Fib Zone Index: {zone_idx} ({zone_label})")
  
    # 调用者自行实现个性化逻辑（例如：根据 zone_index 自行决定风控、减仓或挂单）
    if zone_idx >= 4:
        # 开发者自己的高位策略...
        pass
```

---

## 4. ⚠️ 使用须知与已知限制

### 4.1 示例函数请勿直接复用

`interface.py` 中的 `example_calculate_position_multiplier()` 仅为**演示如何消费数据**的参考
实现，**不要直接用于生产策略**，原因有二：

* **Fail-open**：数据缺失时返回 `multiplier_k = 1.0`（满仓）。
  这与"最不确定时应给最小仓位"的安全原则相冲突，是危险默认值。
* **与方向无关**：其 K 系数仅按 `zone_index` 对称分档，未区分 BUY / SELL。
  同一个 zone 对多头与空头的含义并不相同，生产策略必须自行做**方向感知**处理。

调用方请只把该函数当作"如何读取 `fib` 字段"的语法示例，仓位与风控逻辑自行实现。

### 4.2 每次调用都会重新读取文件

`get_pair_analytics()` / `get_latest_fib_mc_data()` 每次调用都会重新读取并解析整个 JSON。
若需处理多个交易对，请**只调用一次**并复用返回的 `results` 字典，避免 N 次重复文件 IO。

### 4.3 时间框架匹配规则

`get_latest_fib_mc_data(day, timeframe)` 按**文件名中的日期做精确匹配**：

* `D`：文件名日期即当日，可正常使用。
* `W`：文件名日期为**当周周一**。非周一调用时必须自行传入该周一的日期，否则取不到数据。

### 4.4 历史快照可能不含 fib

fib 块自 schema `1.1.0` 起才写入。更早生成的快照没有 `schema_version` 与
`fib_segmentation`，其交易对记录中**不存在 `fib` 字段**。
消费方必须处理该字段缺失的情况（降级而非报错）。
