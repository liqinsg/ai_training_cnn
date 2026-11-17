# 下一步开发计划 · 2026-11-17

> 主题：**退出风险治理（Exit Risk）** —— 把 SL 的损失降到最低，并解决宽幅震荡两头打 SL。
> 纪律：一切新逻辑**先影子（只记录、不改决策）**，用真实数据验证后再转正；只做结构性、可解释的改动，拒绝网格搜索式局部最优。

---

## 0. 背景：今天实测到的三件事

### 0.1 近 7 天运行情况（Demo 4 账户，OANDA 实平仓）

| 平仓类型 | 笔数 | 合计 P&L | 均值 |
|---|---|---|---|
| TP（止盈） | 60 | +1828.24 | +30.47 |
| 主动平仓（时间到期 / 方向翻转） | 31 | +1037.48 | +33.47 |
| **SL（止损）** | **17** | **-670.80** | **-39.46** |
| 合计 | 108 | +2194.92 | +20.3 |

实盘 4 账户：37 笔平仓，净 ≈ +4.2（地板仓，忽略不计）。

**⚠️ 别高兴太早**：最近是强趋势行情，重胜率掩盖了尾部风险。真正的难点是**宽幅震荡**（见 §3）。

### 0.2 根因：SL/TP 风险报酬倒挂（结构问题，非单笔问题）

从 1207 条开仓记录实测几何：

| 指标 | 中位 | 均值 | p90 | 最大 |
|---|---|---|---|---|
| TP 距离(pips) | 30.0 | 30.0 | 30.0 | 30.0（恒定）|
| SL 距离(pips) | **54.6** | 64.2 | 121.8 | 299.7 |
| SL/TP 比值 | **1.82** | 2.14 | | |

- 代码事实：TP = `_TREND_TP_CONFIG["base_tp_pips"] = 30`（MC 强信号才 ×2=60）；
  SL = `compute_sl_zone()` 结构分层 / `ATR × 2.0`（min 25 / 35）。
- 设计文档 `Bot_Workflow.md` 声称 R:R = 1:1.5（ATR_TP 3.0 / ATR_SL 2.0），**实际是 1:0.55**。日元对最糟（USDJPY 2.68、AUDJPY 2.87）。
- **尾部才是大头**：17 笔 SL 中 4 笔打出 -125 ~ -141 pips，合计 **-383.89 = 全部 SL 亏损的 57%**；其中 3 笔 USD_JPY 在 `2026-11-10T14:52` 同一时刻被扫（相关性事件）。

### 0.3 盲点：bot 日志不落盘券商侧 SL/TP 平仓

`logs/profile_pf-*.jsonl` 只记录了 **`TIME_EXPIRY` / `DIRECTION_FLIP`** 两种自平仓，券商侧 `STOP_LOSS_ORDER` / `TAKE_PROFIT_ORDER` 平仓**完全不落盘**。

**你记得没错——能力其实早就有**，只是没落盘：

- `check_and_record_tp_cooldown()`（`fx_trade_bot_utils_v1.py`）：已读 CLOSED trades、按 `clientExtensions` tag 归因、查 closing transaction 的 `reason`。
- `refresh_tp_cooldown_from_recent_tx()`：已批量扫 `TransactionsSinceID` 找 `reason == TAKE_PROFIT_ORDER`。
- **但它们只用来刷 TP 冷却，没有持久化成日志** → SL 打了多少、亏多少，在日志里查不到。
- 而**完整的 drop-in 记录器在另一个项目 `gemini_ai`** 那边（见 §1）。

---

## 1. P0 · 退出可观测性（先修盲点，零决策风险）

**目标**：让"SL 打了几次 / 亏多少 / 什么价位打的"在日志里直接可见，且与 OANDA 对账一致。

**参考实现（另一个项目 `gemini_ai`，直接移植）**：

| 关注点 | gemini_ai 参考文件 |
|---|---|
| 券商即账本（只读、不落本地 state） | `utils/oanda_state.py`（`get_closed_trades` / `build_post_exit_context` / `parse_oanda_time`） |
| 策略归因（tag 匹配） | `oanda_state.is_strategy_record()` + `clientExtensions.tag`（本项目已有，见下） |
| 只读上下文、绝不抛异常 | `utils/post_exit_context.py`（`PostExitTracker.get_context`） |
| 平仓原因 → 分层 | `utils/post_exit_gate.py`（`CLOSE_REASON_TIER_MAP`: TP→tier1 / STOP_LOSS→tier3 / SWEEP→tier3 / STRATEGY_INVALIDATION→tier3） |
| 影子日志 | `logs/post_exit_gate_shadow.jsonl`（字段含 `exit_reason ∈ {ACTIVE, SL, TP}`） |
| 报告 | `utils/analyze_post_exit.py`（平仓原因分布 SL/TP/ACTIVE） |
| 逐笔台账 CSV | `utils/daily_results_profile*/YYYYMMDD_trade_log.csv`（列：`entry_price, sl_price, tp_price, pips, profit_usd, exit_reason, exit_time`） |

**落地方式（本项目）**：

1. 在 `fx_trade_bot_utils_v1.py` 复用已有的 `clientExtensions` tag（`list_open_trades` 已返回 `client_ext_tag`），新增**只读**函数：拉取 CLOSED trades → 按 tag 归因 → 取 closing tx `reason` → 分类为 `TP / SL / ACTIVE`。
2. 输出两样（**先影子**，不参与任何决策）：
   - `logs/exit_audit_YYYYMMDD.jsonl`：逐笔平仓审计（pair, direction, entry, exit, pips, realized_pl, exit_reason, closeTime）。
   - 每日 `trade_log.csv`：与 gemini_ai 同构的列，便于复用分析脚本。
3. 失败一律降级为中性（照抄 `post_exit_context` 的"never raises"契约），**绝不允许**影响交易循环。

**验收标准**：连跑 1 天后，日志中 SL/TP/ACTIVE 计数与 P&L 分解，可与 OANDA 手工对账一致。

---

## 2. P1 · SL 损失最小化（三条杠杆，逐条影子验证）

| 杠杆 | 内容 | 预期效果 | 风险 |
|---|---|---|---|
| **L1 重连 SL↔TP** | SL 上限定在 ≤ 1.0–1.5×TP，或恢复随波动放大的 ATR-TP | 直接压缩单笔亏损 + 尾部"一把回吐一周" | 止损更紧 → 可能被洗，胜率下降（需 A/B） |
| **L2 风险定额仓位** | `units ∝ 风险预算 / SL_pips`，让每笔 SL 的美元亏损大致恒定 | 消除"宽止损=大亏"，与已上线的 prob overlay（只缩不放大）天然互补 | 低（只动 size） |
| **L3 更早保本 + 分批止盈 / HWM 锁盈** | 机制已有（BREAKEVEN 实测有效，2 笔落在 +1p）；扩展覆盖面 + 参考 `gemini_ai/tracking_stop_loss.md` 的 #1（阶梯分批）与 #2（高水位回吐锁） | 把"浮盈回吐变亏损"转成"落袋" | 中（可能过早离场） |

**验收标准**：固定单量下，SL 单笔均值与 p95 尾部下降，且胜率/期望值不显著恶化（用 §1 的审计数据对比）。

---

## 3. P1 · 宽幅震荡识别与降档（最难的一环）

**观察（用户）**：窄幅震荡尚可探测（MC 提示 consolidation、ATR 指标也有），但**宽幅震荡两头打 SL 最难**。

**思路**：关键不是"有没有区间"，而是**区间的宽度**。需要区分 narrow-range（可探测、可交易）与 wide-range（双向扫损、应回避）。

**候选特征**：
- MC `distribution.range_90` 宽度 / `prob_bands` 展宽；
- ATR 的分位（相对自身历史）；
- 布林带宽度 / 近期高低点振幅；
- 与 §14 概率路线 `W = (q95-q05)/price` 已算出的 `risk_cap` 天然衔接。

**处置策略**（择一或组合，先影子）：
- wide-range → 降仓 / 放宽 TP / 直接 skip；
- 与 §14 的 `regime` 定仓合流（参考 gemini_ai `MC_REGIME_MULTIPLIER["CONSOLIDATION"]` 的分档思路）。

**验收标准**：影子标记出的 "wide-range 时段"，其 SL 命中率显著高于其他时段 → 证明判别有效，再做处置。

---

## 4. P2 · 趋势追顶（entry timing）

**观察（用户）**：趋势来了、进场、好家伙正好到顶。

**思路**：用 MC 分布中的**相对分位位置**（当前价在 `q05..q95` 中的位置）判断是否已过度延伸，作为追价过滤。

**验收标准**：影子记录 "进场分位 vs 后续 MFE/MAE"，验证高位进场是否系统性吃亏。

---

## 5. 明天（D+1）具体安排

1. **P0 交接**：移植 gemini_ai 的只读平仓审计到本项目，先影子输出 jsonl + csv，跑满一天。
2. **出第一份报告**：复用 `analyze_post_exit.py` 思路，产出 SL/TP/ACTIVE 分解 + 逐 pair 尾部统计。
3. **L1 / L2 方案设计文档**（只出方案、不动代码）：给出 SL↔TP 重连与风险定额仓位的具体口径、开关、影子验证计划。
4. **§3 特征调研**：盘点可用的 range-width 特征（MC/ATR/BB），定出 wide-range 的初步判别阈值（影子）。
5. **不改任何决策逻辑**；今日已上线的 prob overlay（`VERDICT_MODE=soft`）与 cron（MC 6h 伦敦基准）保持观察。

---

## 6. 待决问题（需 Owner 拍板）

- L1 的 SL 上限取 **1.0×TP** 还是 **1.5×TP**？（越紧 → 单笔损失越小但洗损越多）
- §3 的 wide-range 处置首选 **降仓** 还是 **skip**？
- §1 审计日志是否需要同时覆盖**实盘腿**（读实盘账户 closed trades）？
