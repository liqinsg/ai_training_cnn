```markdown
# Forex Trading Bot — 统一术语表

> **核心原则：三者永不混用**
> - **Order** = 指令 / 请求 → 发送给平台的申请，尚未成交
> - **Position** = 持仓 / 仓位 → Order 成交后持有，当前状态
> - **Trade** = 成交记录 → 历史归档，用于对账/复盘

---

## 1. Order（订单 / 指令）
**定义：** 发送给交易平台（OANDA）的交易请求。**未成交、可成功可失败。**

### Order 类型
| 术语 | 含义 | 推荐方法名 |
|---|---|---|
| **Open Order** | 开仓指令 | `place_open_order()` |
| **Close Order** | 平仓指令 | `place_close_order()` |
| **Pending Order** | 挂单（Limit/Stop） | `place_pending_order()` |
| **Cancel Order** | 取消挂单 | `cancel_order()` |

### ✅ 日志 / 文案规范
```
✅ Open order submitted
✅ Close order submitted
✅ Pending order created
✅ Order rejected (reason: ...)

❌ Trade opened       ← 应写: Position opened
❌ Position order opened ← 应写: Open order submitted
```

---

## 2. Position（持仓 / 仓位）
**定义：** Open Order **成交后** 形成的当前持仓。**是状态、有盈亏、可改 SL/TP、可平仓。**

### Position 属性
- `position_direction` → **LONG / SHORT**
- `position_size` → 持仓量
- `position_units` → 交易单位数
- `position_pnl` → 浮动盈亏

### Position 操作
| 操作 | 推荐方法名 | 说明 |
|---|---|---|
| 查询当前持仓 | `get_open_positions()` | ❌ 禁止写 `get_open_orders()` |
| 修改止损 | `update_position_sl()` | 改的是持仓，不是 Order |
| 修改止盈 | `update_position_tp()` | 改的是持仓，不是 Order |
| 平仓（精准） | `close_my_position(instrument)` | 只平 TAG 匹配的持仓 |
| 平仓（全量） | `close_all_positions(instrument)` | ⚠️ 全部持仓，谨慎使用 |

### ✅ 日志 / 文案规范
```
✅ Position opened
✅ Position updated — SL=... TP=...
✅ Position closed — PnL=+xx.xx USD
✅ Position detected — LONG 1000 units
⚠️ No position found
```

---

## 3. Trade（成交记录 / 历史）
**定义：** 一次成交的**历史记录**。用于对账、CSV、复盘。
> ⚠️ **Position ≠ Trade**：一次开仓可能由多笔 Trade 组成（加仓/部分成交）。

### 关系示意
```
Order (申请)
  ↓ 成交
Position (当前持有 — 1个)
  ├─ Trade #1 (历史成交)
  ├─ Trade #2 (加仓成交)
  └─ Trade #3 (加仓成交)
  ↓ 平仓
Trade History (全部归档)
```

### Trade 常用项
- `trade_id` → 成交单号（OANDA 返回）
- `trade_log` → CSV 日志字段
- `trade_history` → 历史查询

### ✅ 日志 / 文案规范
```
✅ Trade executed — TradeID=xxx
✅ Trade closed — recorded to trade_log.csv
✅ Trade history updated
```

---

## 4. TAG / 归属识别（项目特有 ⚠️）
```
Order → stamped with TAG: FXBOT-AUTO-P2/P3/P4
Position → identified by TAG
  ✅ TAG match → operate safely
  ⚠️ No TAG + default → SAFE STOP, do NOT touch
  ⚡ No TAG + no_tag_fallback=True → take FIRST trade
```

---

## 5. 完整生命周期（标准文案）
```
place_open_order()   →  ✅ Open order submitted
          ↓ 成交
get_open_positions() →  ✅ Position opened
update_position_sl() →  ✅ Position updated — SL=...
          ↓ 持有
close_my_position()  →  ✅ Position closed — PnL=...
          ↓ 归档
get_trade_history()  →  ✅ Trade history updated
```

---

## 6. 命名红黑榜 ⚠️

| ❌ 禁止（易混淆） | ✅ 统一标准 |
|---|---|
| `open_trade()` | `place_open_order()` |
| `close_trade()` | `place_close_order()` / `close_my_position()` |
| `get_open_orders()` | `get_open_positions()` |
| `modify_order()` | `update_position_sl/tp()` |
| `order_position()` | 分两步: Order → Position |
| `trade_position()` | Position → Trade |

---

## 7. Telegram / 通知文案模板

### ✅ 开仓成功
```
✅ Position Opened
Instrument : EUR/USD
Direction  : LONG
Entry Price: 1.1750
SL         : 1.1700
TP         : 1.1850
TAG        : FXBOT-AUTO-P2
```

### ✅ 平仓成功
```
✅ Position Closed
Instrument : EUR/USD
PnL        : +18.50 USD
Reason     : CLIENT_CLOSE
```

### ✅ 修改 SL/TP
```
✅ Position Updated
Instrument : USD/JPY
New SL     : 144.90
New TP     : 145.60
```

---

## 一句话总结
> **Order = 申请 → 成交变 Position（持仓管理）→ 平仓变 Trade（历史归档）。三者永不混用！**
```

---

### ✅ 我的微小修改说明
1. **保留你全部核心定义** — 完全不变 ✅
2. **补充 TAG 归属规则** — 咱们项目的安全核心，写进去以后不用再反复解释 ✅
3. **区分精准/全量平仓** — `close_my_position()` vs `close_all_positions()` ✅
4. **生命周期流程图** — Order → Position → Trade，一眼看懂 ✅
5. **修正几处方法名** — 和你我最终定的代码完全对齐，以后复制粘贴不翻车 ✅

