# 为 fx_trade_bot v685 增加 Fib Zone 执行层（仅影响仓位与 TP，不影响信号方向）

## 数据接入（重要：必须走 interface.py）

**interface.py 与 interface.md 已在项目根目录。**

**Bot 必须通过 interface 取数。**

**禁止：**

- 直接读取 `mc_results/`
- 直接读取 `mc_cache[pair]["fib"]`
- 在 Fib Zone 模块内自行读取 JSON

**示例：**

```python
import interface as mc_iface

# 每次运行开始时加载一次（不要每个 pair 重读文件）
_day = datetime.now().strftime("%Y%m%d")
_tf  = args.timeframe or "D"

_bundle = mc_iface.get_latest_fib_mc_data(_day, _tf)
fib_index = (_bundle or {}).get("results", {})

# 之后按 pair 取
rec = fib_index.get(pair)
```

**说明：**

1. `interface.py` 中 `example_calculate_position_multiplier()` 仅为参考示例。

   它存在：

   ```
   Data not found
   → multiplier_k = 1.0
   ```

   的 fail-open 行为。

   禁止直接复用。

   必须按本需求实现新的逻辑。

2. 禁止逐 pair 调用：

   ```python
   get_pair_analytics()
   ```

   因为其内部会重复读取 JSON 文件。

   必须：

   ```
   启动时加载一次 bundle
   → 内存索引
   → 所有 pair 复用
   ```

---

## Pair Key 对齐要求

实现前必须确认：

```
pair
```

与：

```
fib_index.keys()
```

格式完全一致。

例如：

```
EUR_USD
EURUSD
EURUSD=X
```

可能同时存在。

若格式不同：

必须实现统一映射函数。

禁止在业务流程中到处：

```python
replace()
split()
upper()
```

临时处理。

最终目标：

```python
rec = fib_index.get(mapped_pair)
```

能够稳定命中。

---

## 背景事实

1. schema 1.1.0 起：

   ```
   pair["fib"]
   ```

   才存在。

   更老快照没有 fib。

2. 交易仅采用：

   ```
   当天数据
   ```

   老数据不参与交易。

3. 当前实测：

   ```python
   zone 2 = 12
   zone 3 = 15
   zone 4 = 1
   ```

   现阶段：

   ```
   仓位缩放极少触发
   主要影响 TP
   ```

   这是预期行为。

   禁止调整 zone 阈值。

---

## 已确认设计决策（不得偏离）

1. 中心区满仓：

   ```python
   zone_index in {2, 3}
   ```

   ↓

   ```python
   size_scale = 1.0
   ```

2. 方向感知仓位：

   ```python
   1.0
   0.5
   0.25
   ```

3. SL 完全不变：

   继续沿用：

   ```python
   compute_sl_zone()
   ```

4. TP：

   仅允许缩小

   禁止放大

5. 直接以 Filter 模式上线

   先跑 Demo，标准仓位取决于命令行参数和 `run.env` 配置

6. units 继续沿用：

   ```python
   DEFAULT_LOT_SIZE
   ```

   不进行 lot 换算

---

## 核心算法

```python
late = (
    max(0, CENTER_LO - zone_index)
    if direction == "SHORT"
    else max(0, zone_index - CENTER_HI)
)

size_scale = SIZE_LADDER[
    min(late, len(SIZE_LADDER) - 1)
]

room = (
    ratio_pos
    if direction == "SHORT"
    else (1.0 - ratio_pos)
)

tp_scale = min(
    TP_SCALE_MAX,
    max(TP_SCALE_MIN, room / TP_ROOM_REF)
)

tp_pips = max(
    MIN_TP_PIPS,
    round(base_tp_pips * tp_scale, 1)
)
```

---

## 边界处理（Fail-Closed 优先）

### 缺失 Fib

情况：

```shell
fib 缺失
老快照
分段未运行
```

处理：

```shell
回退标准仓位
TP 保持原值
记录 WARNING
继续交易
```

不得 Skip。

---

### 非法 Fib 数据

包括：

```python
zone_index is None
ratio_pos < 0
ratio_pos > 1
ratio_pos = NaN
类型错误
```

全部按：

```python
fib_missing
```

处理。

禁止参与计算。

---

### Degenerate

```python
fib.degenerate == True
```

↓

```python
skip = True
```

记录原因：

```python
fib_degenerate
```

不得满仓放行。

---

### Breakout

```python
fib.breakout == True
```

默认：

```
不 Skip
```

仅记录日志。

由：

```python
FIB_ZONE_SKIP_BREAKOUT
```

控制。

---

### 优先级

必须按以下顺序处理：

```python
invalid data
    ↓
degenerate
    ↓
breakout
    ↓
normal
```

其中：

```python
degenerate
```

优先级高于：

```
breakout
```

即使两者同时出现：

```python
degenerate == True
breakout == True
```

也必须：

```python
skip = True
```

`size_units` 下限：

禁止返回：

```
0
```

---

## 新增模块

新增：

```
utils/fib_zone_sizing.py
```

暴露：

```python
def compute_zone_plan(
    rec: dict,
    direction: str,
    cfg: dict,
    base_lot: int,
    base_tp_pips: float,
) -> dict:
    ...
```

### 返回契约（新增要求）

无论任何情况：

```python
compute_zone_plan()
```

必须返回完整 dict。

禁止：

```python
{}
```

或者：

```python
{"skip": False}
```

最少返回：

```python
{
    "skip": False,
    "reason": "...",
    "zone_index": None,
    "ratio_pos": None,
    "late_distance": 0,
    "size_scale": 1.0,
    "size_units": base_lot,
    "tp_scale": 1.0,
    "tp_pips": base_tp_pips
}
```

即：

- 永远返回完整结构
- 永远不抛异常

### 实现约束

该模块内禁止：

```python
import interface
```

禁止：

```
OANDA API
```

禁止：

```
文件 IO
```

禁止：

```
环境变量读取
```

只接受：

```python
cfg
```

作为普通 dict 输入。

### size_units 计算规则（新增）

统一采用：

```python
size_units = max(
    1,
    round(base_lot * size_scale)
)
```

禁止：

```python
int()
floor()
ceil()
```

等不同实现。

必须保证结果一致。

---

## 配置

追加到：

```
config_profile.json
```

```json
"fib_zone": {
  "ENABLED": true,
  "MODE": "filter",
  "CENTER_LO": 2,
  "CENTER_HI": 3,
  "SIZE_LADDER": [1.0, 0.5, 0.25],
  "TP_ROOM_REF": 0.5,
  "TP_SCALE_MIN": 0.5,
  "TP_SCALE_MAX": 1.0,
  "MIN_TP_PIPS": 10,
  "SKIP_WHEN_DEGENERATE": true,
  "SKIP_BREAKOUT": false
}
```

并在：

```
config_bot.py
```

通过：

```python
FIB_ZONE_*
```

导出。

配置缺失时必须使用同样默认值。

---

## 接入点

### 1. TP 缩放

位置：

```
fx_trade_bot_v685.py
L2340-L2406
```

在：

```python
evaluate_trend_and_tp()
```

得到：

```python
smart_tp_pips
```

之后、

计算：

```python
tp_price
```

之前执行。

（后续代码保持原设计要求）

### 2. Candidate Tuple

现有 tuple 末尾追加：

```python
plan["size_units"]
```

并把 TP 字段改成：

```python
tp_pips_eff
```

同步修改：

- 排名日志解包
- 下单循环解包

### 3. 下单使用实际仓位

将：

```python
DEFAULT_LOT_SIZE
```

替换为：

```python
size_units
```

包括：

- `open_oanda_order()`
- `json_log.bot_open()`
- `telegram`
- 日志

---

## 审计日志（增强）

每次：

- 开仓
- 跳过

均记录：

| 字段 | 说明 |
| --- | --- |
| `pair` | 交易对 |
| `direction` | 方向 |
| `zone_index` | Fib zone 索引 |
| `ratio_pos` | 位置比例 |
| `room` | 剩余空间 |
| `late_distance` | 偏离中心区距离 |
| `size_scale` | 仓位缩放系数 |
| `units` | 仓位（base → final） |
| `tp_scale` | TP 缩放系数 |
| `tp` | TP（base → final） |
| `reason` | 原因 |

---

## 测试（必须新增）

新增：

```
tests/test_fib_zone_sizing.py
```

覆盖：

- zone 2/3，双方向：

  ```python
  size_scale == 1.0
  ```

- SHORT，zone=1：

  ```
  ↓ 0.5
  ```

- SHORT，zone=0：

  ```
  ↓ 0.25
  ```

- BUY，zone=4：

  ```
  ↓ 0.5
  ```

- BUY，zone=5：

  ```
  ↓ 0.25
  ```

- `degenerate=True`：

  ```
  ↓ skip=True
  ```

- fib missing / zone missing / ratio invalid：

  ```
  ↓ fallback
  不 skip
  ```

- `tp_scale` 始终：

  ```python
  TP_SCALE_MIN <= tp_scale <= TP_SCALE_MAX
  ```

- `size_units > 0` 永远成立。

---

## Implementation Guardrails（新增）

必须满足：

1. `compute_zone_plan()` 永远不抛异常。
2. `compute_zone_plan()` 永远返回完整 dict。
3. 非法 Fib 数据按 `fib_missing` 统一处理。
4. `ratio_pos` 必须验证在 `[0.0, 1.0]`。
5. `size_units` 必须按：

   ```python
   max(1, round(base_lot * size_scale))
   ```

   计算。

6. degenerate 的处理优先级高于 breakout。
7. 集成前必须验证 pair key 映射。
8. Fib Zone 层任何异常都必须优雅降级到 v685 现有行为（除显式 skip 情况外）。

---

## 明确不做（禁止范围蔓延）

禁止修改：

- S/R/G/A/X/M 权重体系
- `calc_weighted_score`
- 信号方向
- MC 融合逻辑
- SL 逻辑
- SL 缩放
- 多笔阶梯挂单
- `MAX_OPEN`
- 敞口核算
- TP 冷却机制
- `interface.py`
- `interface.md`
- `mc_bundle_loader`
- `load_mc_bundle`
- `mc_results/` 下任何文件

---

## 交付要求

完成后提供：

1. 修改文件清单
2. `compute_zone_plan` 完整源码
3. 所有关键 diff
4. pytest 结果
5. 示例日志输出

在未满足上述约束前，不得自行扩展需求范围。
