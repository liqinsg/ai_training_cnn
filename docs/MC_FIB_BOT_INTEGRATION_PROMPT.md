# MC Fib Zone 执行层 — 接入 Prompt（供 ai_training_cnn 使用）

> 本文件是需要**原样粘贴到 `ai_training_cnn` 项目**的 prompt。
> 目标项目：`/home/ubuntu/projects/ai_training_cnn`
> 数据来源：`/home/ubuntu/projects/fx_monte_carlo`（经 symlink `mc_results/`）
> 日期：2026-11-05

---

## 前置说明（给粘贴者看，不要粘进 prompt）

- 已核实：`interface.py` / `interface.md` 已拷贝到 `ai_training_cnn` 根目录。
- 已核实：`mc_results` 是指向 `../fx_monte_carlo/mc_results/` 的 symlink。
- 已核实：老快照（如 `mc_D_all_pairs_20260913_0503.json`）**没有 fib 块**（无 `schema_version` / `fib_segmentation`），fib 为 schema 1.1.0 引入。
- 已核实：今日 28 个 pair 的 `zone_index` 分布为 `2:12 / 3:15 / 4:1`，0/1/5 为 0。仓位阶梯现阶段极少触发，实际主要影响 TP。
- 已核实：bot 中 SL/TP 计算循环与下单循环是**分开的两个循环**，`smart_tp_pips` 已作为候选元组第 10 个元素在两循环间传递。
- 已知限制（**本次不做**）：`interface.get_latest_fib_mc_data` 按「日期精确匹配」取文件；W timeframe 的文件名日期为周一，非周一当天直接调用会取不到。将来接 W 时需先补一个「本周一」日期解析器。

---

## ↓↓↓ 以下是粘贴到 ai_training_cnn 的 prompt ↓↓↓

【任务】为 **fx_trade_bot version 685** 增加 "Fib Zone 执行层"（仅影响仓位与 TP，不影响信号方向）

## 数据接入（重要：必须走 interface.py）

`interface.py` 与 `interface.md` 已在项目根目录。bot 必须通过它取数，
禁止直接读 `mc_results/` 目录、禁止直接读 `mc_cache[pair]["fib"]`。

```python
import interface as mc_iface

# 每次运行开始时加载一次（不要每个 pair 重读文件）
_day = datetime.now().strftime("%Y%m%d")
_tf  = args.timeframe or "D"
_bundle = mc_iface.get_latest_fib_mc_data(_day, _tf)
fib_index = (_bundle or {}).get("results", {})
# 之后按 pair 取：
rec = fib_index.get(pair)
```

说明：

- `interface.py` 里 `example_calculate_position_multiplier()` 只是参考示例。
  它 `Data not found → multiplier_k=1.0` 是 fail-open，且 K 与方向无关（对称）。
  **禁止直接复用**，须按本文档自研。
- 不要逐 pair 调用 `get_pair_analytics()`，其内部每次都会重读 JSON，造成 N 次文件 IO。

## 背景事实（已用真实数据核实，不必再验证）

- schema 1.1.0 起 pair 记录才带 fib 块；更老的快照没有 fib。
- 交易只使用**当天**数据；老数据不参与交易。
- 实测今日 28 个 pair：`zone_index` 分布为 2:12 / 3:15 / 4:1。
  即：仓位阶梯现阶段极少触发，实际主要影响 TP。这是预期内，**不要为此调整阈值**。

## 已确认的设计决策（不得偏离）

1. 中心满仓：`zone_index ∈ {2,3}` → size_scale = 1.0
2. 单笔递减，**方向感知**：1.0 / 0.5 / 0.25
3. SL 完全不动，保持 `compute_sl_zone` 结构式结果
4. TP **只缩不放大**（阶段一禁止任何 TP 放大）
5. 直接以 filter 模式上线，跑 demo 小仓位
6. units 直接沿用 `run.env` 的 `DEFAULT_LOT_SIZE`，不做 lot 换算

## 核心算法（方向感知，中心为基线）

```
late = max(0, CENTER_LO - zone_index)   if direction == "SHORT"   # 价格跌到中心以下算"晚了"
     = max(0, zone_index - CENTER_HI)   if direction == "BUY"     # 价格涨到中心以上算"晚了"

size_scale = SIZE_LADDER[min(late, len(SIZE_LADDER)-1)]   # [1.0, 0.5, 0.25]

room     = ratio_pos if direction == "SHORT" else (1.0 - ratio_pos)
tp_scale = min(TP_SCALE_MAX, max(TP_SCALE_MIN, room / TP_ROOM_REF))
tp_pips  = max(MIN_TP_PIPS, round(base_tp_pips * tp_scale, 1))
```

## 边界处理（fail-closed 优先）

- fib 缺失（老快照 / 分段未跑）        → 回退标准手数 + TP 不变 + WARNING 日志，**不 skip**
- `zone_index` / `ratio_pos` 缺失或非法 → 同上（按缺失处理）
- `fib.degenerate == True`              → **skip 该 pair 开仓**，记录 SKIP 原因，不得满仓
- `fib.breakout == True`                → 默认不 skip，仅记录日志（由 `FIB_ZONE_SKIP_BREAKOUT` 控制）
- `size_units` 下限 `max(1, ...)`，**绝不返回 0**

## 新增模块（纯函数、无 I/O、可单测）

新增 `utils/fib_zone_sizing.py`，暴露：

```python
def compute_zone_plan(rec: dict, direction: str, cfg: dict,
                      base_lot: int, base_tp_pips: float) -> dict:
    ...
```

返回字段：
`skip(bool), reason(str), zone_index, ratio_pos, late_distance, size_scale, size_units, tp_scale, tp_pips`

约束：该模块内**禁止**调用 OANDA、读写文件、读环境变量、`import interface`。
`cfg` 由调用方以普通 dict 传入（便于单测）。

## 配置（追加到 config_profile.json 的 global，并支持 profiles.N 覆盖）

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

在 `config_bot.py` 按现有 `get_global("a.b")` 模式暴露对应键（前缀 `FIB_ZONE_`）。
默认值必须与上面一致；配置缺失时也必须能正常运行。

## 接入点（已核实行号，最小改动）

### 1) TP 缩放 —— 在「候选计算循环」内完成

位置：`fx_trade_bot_v685.py` 约 L2340-L2406。
`evaluate_trend_and_tp()` 返回 `smart_tp_pips` 后、计算 `tp_price` 之前：

```python
# fib zone plan（README 见上）
fib_rec = fib_index.get(pair, {})
plan = compute_zone_plan(fib_rec, direction, FIB_ZONE_CFG, DEFAULT_LOT_SIZE, smart_tp_pips)
if plan.get("skip"):
    log.info(f"⏭️ {pair}: FIB-ZONE SKIP ({plan.get('reason')})")
    continue

tp_pips_eff = plan["tp_pips"]      # 用它替代 smart_tp_pips 计算 tp_price
tp_price = (
    round(current + tp_pips_eff * pip_cache[pair], dec)
    if direction == "BUY"
    else round(current - tp_pips_eff * pip_cache[pair], dec)
)
```

### 2) 把 size_units 传给下单循环 —— 搭现有元组第 11 位

现有候选元组（L2415 附近）：
`(-w["FINAL"], w["FINAL"], pair, oanda, direction, current, sl_price, tp_price, dec, smart_tp_pips)`
在末尾追加 `plan["size_units"]`，并把第 10 位改成 `tp_pips_eff`（便于排名日志审计）。

需同步更新**两处**显式解包：

- 排名日志循环（L2472 附近）：补一个 `_`
- 下单循环（L2490 附近）：`for (_, FINAL, pair, oanda, direction, current, sl_price, tp_price, dec, _, size_units) in all_candidates:`

（冲突检测循环用 `*_rest`，无需改动。）

### 3) 下单处用 per-pair size 替换全局手数

位置：`fx_trade_bot_v685.py` 的 L2506 / L2516 / L2531 / L2550 / L2559 / L2568 / L2585。
把 `DEFAULT_LOT_SIZE` 全部替换为 `size_units`，包括：

- `open_oanda_order(..., size_units, sl_price, tp_price, ...)`
- `json_log.bot_open(units=size_units, ...)`
- 所有 `lots={DEFAULT_LOT_SIZE}` 的日志 / telegram 文案 → 改为打印实际 `size_units`

`DEFAULT_LOT_SIZE` 仍作为 `base_lot` 传入，**保留其解析逻辑不动**。

## 日志（必须可审计）

每次开仓 / 跳过打印一行结构化日志，含：
`pair, direction, zone_index, ratio_pos, late_distance, size_scale, units(base→final), tp_scale, base_tp→final_tp, reason`

## 测试（必须新增并通过）

新增 `tests/test_fib_zone_sizing.py`，纯 dict 夹具，覆盖：

- zone 2/3 两个方向 → `size_scale == 1.0`
- SHORT zone=1 → 0.5；zone=0 → 0.25
- BUY  zone=4 → 0.5；zone=5 → 0.25
- `degenerate == True` → `skip == True`
- fib 缺失 / `zone_index` 缺失 → 回退 1.0，**不** skip
- `tp_scale` 恒 ∈ `[TP_SCALE_MIN, TP_SCALE_MAX]`
- `size_units` 永不为 0

运行：`python -m pytest tests/test_fib_zone_sizing.py -q`
并确保现有 `tests/` 未被破坏。

## 明确不做（范围内禁止）

- 不修改打分权重（S/R/G/A/X/M）与 `calc_weighted_score`
- 不修改信号方向、不修改 MC 融合逻辑
- 不修改 SL 逻辑、不实现 SL 缩放
- 不实现多笔阶梯挂单、不触碰 `MAX_OPEN` / 净敞口核算
- 不做任何 TP 冷却相关改动
- 不修改 `interface.py` / `interface.md` / `mc_bundle_loader` / `load_mc_bundle`
- 不修改 `mc_results/` 下任何文件

## 交付要求

1) **先**给出改动文件清单（含行号）与最小 diff 方案，等待确认
2) 确认后实施，运行 `python -m py_compile` + `pytest` 并给出真实输出
