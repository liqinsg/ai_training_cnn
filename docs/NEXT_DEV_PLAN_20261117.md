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

### 0.4 审计口径修正（P0 实测 · 2026-11-18）

§0.2 的 SL/TP 倒挂（1.82）是**开仓意图口径**（含大量从未触发的宽 SL）。P0 审计（`logs/exit_audit_20261117.jsonl`，495 笔，窗口 2026-10-22 ~ 11-17）显示**实际触发的 SL 几何与 TP 基本 1:1**：

| 平仓类型 | 笔数 | 合计 P&L | 均值 | 中位 pips |
|---|---|---|---|---|
| TP | 272 | +7369.59 | +27.09 | +30.00 |
| SL | 140 | −5128.98 | −36.64 | −30.40 |
| ACTIVE（时间到期 / 方向翻转） | 83 | +168.22 | +2.03 | +3.60 |

- 实际 \|pips\| 中位：TP **30.00** vs SL **30.40** → **SL/TP = 1.01**（非 1.82）。
- 真问题是**尾部**：SL 亏损幅度 USD p50=28.89 / p90=70.93 / p95=89.66 / max=127.66；pips p50=30.4 / p90=95.4 / max=182.4；**最深 25% 的笔数占了全部 SL 亏损的 50%**。
- 逐 pair（SL 亏损）：EUR_JPY −914 / GBP_JPY −860 / GBP_USD −662 / USD_JPY −624（**SL 命中率 45% 最高**）…
- 相关扫损：`2026-11-03 19:12` 同分钟 5 笔（USD_JPY / EUR_JPY 系）。
- **Owner 裁定（2026-11-18）**：不深究口径差异，**按审计口径为准** → L1（重连 SL↔TP）**降级**，P1 主攻 **L2**。

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
| 逐笔台账 CSV | `daily_results_profile*/YYYY-MM-DD_trade_log.csv`（列：`entry_price, sl_price, tp_price, pips, profit_usd, exit_reason, exit_time`） |

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

### 2.1 L2 · 风险定额仓位（设计稿 · 先影子，不改决策）

**问题**：`size_units = DEFAULT_LOT_SIZE × size_scale`（概率覆盖层输出），**与 SL 距离无关**。SL 距离 p50=54.6 / p90=121.8 / max=299.7 pips → 每笔 SL 的美元亏损极不均衡，"宽止损 = 大亏"直接制造 §0.4 的尾部。

**口径（只缩不放大，与 prob overlay 相乘互补）**：

```text
rp_ref_pips = intended_sl_pips                        # ATR 口径的"应然"止损距离
sl_pips_act = |current − sl_price| / pip              # 实际下单 SL
rp_mult     = clamp(rp_ref_pips / sl_pips_act, RP_F_LO, 1.0)
units_l2    = max(MIN_LOT, round(size_units_prob × rp_mult))
```

- `intended_sl_pips = max(min_sl_pips_jpy|std, round(atr_val / pip × ATR_SL_MULT, 1))`
  —— 与 `fx_trade_bot_v685.py` L3128–3131 的 ATR fallback **同式**，**无需新增全局常数**（自参照）。
- `sl_pips_act ≤ ref → rp_mult = 1.0`（不动）；**仅当结构 SL 比 ATR 应然更宽时按比例缩量** → 正好削 p90 / max 尾档。
- `RP_F_LO` 默认 `0.25`（与 §14 `F_LO` 同量级），是单笔最大缩量下限。
- **互补性**：prob overlay 按方向确信度 / regime / MC 区间宽度（**市场轴**）缩，L2 按 SL 几何（**交易轴**）缩，两者相乘 → 双轴封顶，MIN_LOT 兜底。

**Hook 点**：`fx_trade_bot_v685.py` L3118–3143 —— `sl_price` 已算出（L3123–3136）、`tp_price` 之后、`all_candidates.append`（L3163）之前。此处 `size_units`(L3119) / `sl_price` / `current` / `atr_val` / `pip_cache[pair]` 均在作用域内。

**开关**：`OPT_RISK_PARITY_SIZING`（沿用 `_opt()` 约定：env `OPT_RISK_PARITY_SIZING` > config > default）。

- `off`（默认）= **影子**：不改下单 `size_units`，只额外计算 `units_l2` 并落盘。
- `on` = 生效：`size_units = units_l2`。

**影子产物**：`logs/sizing_shadow_YYYYMMDD.jsonl`，逐候选一行：
`pair / direction / entry / sl_price / tp_price / sl_pips_act / ref_pips / units_prob / units_l2 / rp_mult / pip_value_usd`。
配套分析器（对齐 `utils/analyze_exit_audit.py`）做反事实估算：
`SL_USD_l2 = units_l2 × sl_pips_act × pip_value_usd` vs 实际 → 给出尾档（p90 / max）下降幅度。

**验收标准**（影子 ≥ 1 天后）：

1. `rp_mult` 分布合理（预期 p50 ≈ 1.0、p90 < 0.6）；
2. 反事实：SL 亏损 USD p90 / max **下降**，最深 25% 占比下降；
3. **EV 不显著恶化**：只缩不放大 → 宽 SL 笔的**盈利也同步缩小**，须核对净期望（**这是 L2 的唯一风险点**）。

**Caveat（必须记录）**：`pip 定额 ≠ USD 定额`。跨 quote ccy（`XXX/JPY` vs `XXX/USD`）1 pip 的美元价值不同。影子阶段记录 `pip_value_usd`，报告按 USD 复核；若偏差显著，转正时升级为 USD 定额：`units ∝ budget_usd / (sl_pips × pip_value_usd)`。

**边界**：与 L1 正交（L1 改 SL 距离、L2 改 size，`ref` 恒取 ATR 口径，不受 L1 影响）；与 §3 正交（§3 是"要不要交易"、L2 是"交易多少"）。

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

### 3.1 特征调研结果（§5.4 交付 · 实测 2026-11-18）

**盘点（现状代码）**：

| 候选特征 | 现状 | 可用性 |
|---|---|---|
| MC `range_90` 宽度 `W=(q95−q05)/price` | **已在算**（`prob_zone_sizing._width_pct`），经 `risk_cap=clamp(R_REF/W, C_LO, 1.0)` 已软处置 | ✅ 现成（但见下） |
| MC `distribution.quantiles` / `prob_bands` | 快照已含；目前仅 q05/q95 被消费 | ✅ |
| ATR（`atr_val`） | bot 有**绝对值**（ATRModule），**无分位** | ⚠️ 需补 rolling 分位 |
| 布林带宽度 | **live bot 无**（仅 `fx_model_xgb.py` 训练侧用 `ta.bbands`） | ❌ 需新增 |
| 近 N 日已实现波动 | 无显式 | ❌ 需新增 |

**关键实测（否定结论）—— `W` 不是时序判别器**：

- 100 个 D 快照 / 2828 样本 / 39 个交易日：全体 `W%` p05=1.54 / p50=2.46 / p90=3.41 / p99=3.70 / max=3.78；
- **逐日中位 `W%` 几乎不动**：39 天里只在 **2.38 ~ 2.58%** 之间（相对波动 ≈±4%）；
- 变化只在**跨 pair**（1.54 ~ 3.78%）→ 现有 `risk_cap` 实质是"按币种波动微调 + 常数 ~0.8 削"，**不构成宽幅震荡闸门**。

→ **需要一个时序敏感特征**（ATR 分位 / 已实现波动分位 / BB 宽度分位）；`W` 只能作辅助（跨币种维度）。

**初步判别阈值（影子，待验）**：以 `ATR_pct = 当日 ATR / 该 pair 近 N 日 ATR 的 rolling 中位` 为判别量：

- 窄幅 `ATR_pct < 0.8`（可交易）；
- 常态 `0.8 ≤ ATR_pct < 1.3`；
- **宽幅 `ATR_pct ≥ 1.3`**（双向扫损风险 ↑）→ 影子标记。

先只落盘 `logs/wide_range_shadow_*.jsonl`（`pair / day / atr_pct / tier`），**不改决策**；验收 = 被标为 wide 的时段，其 SL 命中率显著高于常态（对照 §1 审计）。

**顺带发现（属 L1 口径，另议）**：`R_REF=2.0` **低于**实测 `W` 中位 2.46 → `risk_cap` 对**多数**交易都在约束（≈0.78）；若希望该轴只在"真实宽幅"时发力，`R_REF` 需按 `W` 分位重标。

**落地（2026-11-18 · 影子层已实现）**：

- 新模块 `utils/wide_range_sizing.py`：`compute_atr_ratio(oanda)` 只读日线（`utils.trading_core.get_candles`，仅 `complete` 已收线日线）→ `ATR_pct = 当日 ATR / 近 20 日 ATR 中位`；`ATR_PERIOD=14 / LOOKBACK_DAYS=20 / THRESH_NARROW=0.8 / THRESH_WIDE=1.3` 为模块常量；`classify_tier()` 分档；`log_wide_range_shadow()` 落盘。纯函数 + 永不抛异常。
- `fx_trade_bot_v685.py`：开关 `WIDE_RANGE_SHADOW = _opt("WIDE_RANGE_SHADOW", True)`（默认**开**，仅落盘；env `OPT_WIDE_RANGE_SHADOW=0` 可关）；hook 在 L2 之后、候选入选前，逐候选写 `logs/wide_range_shadow_YYYYMMDD.jsonl`（字段：`profile / pair / oanda / direction / atr_pct / atr_current / atr_median / tier / n_points / applied=False`）。
- **不改任何决策**（`applied` 恒 `False`）。验收：`tier=="wide"` 的时段 SL 命中率应显著高于 `normal`（对照 `logs/exit_audit_*.jsonl`）。
- 实测（2026-11-18）：`EUR_USD 1.127 / USD_JPY 1.041 / GBP_JPY 1.004`（均 `normal`，`n_points≈24`）。

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
4. **§3 特征调研**：盘点可用的 range-width 特征（MC/ATR/BB），定出 wide-range 的初步判别阈值（影子）。→ **已成**（§3.1：`W` 非时序判别器 → 改用 `ATR_pct`，阈值 0.8 / 1.3）。
5. **不改任何决策逻辑**；今日已上线的 prob overlay（`VERDICT_MODE=soft`）与 cron（MC 6h 伦敦基准）保持观察。

---

## 6. 待决问题（需 Owner 拍板）

- L1 的 SL 上限取 **1.0×TP** 还是 **1.5×TP**？（越紧 → 单笔损失越小但洗损越多）
- §3 的 wide-range 处置首选 **降仓** 还是 **skip**？
- §1 审计日志是否需要同时覆盖**实盘腿**（读实盘账户 closed trades）？→ **已自动覆盖**（各 profile 各账户各自只读拉取）。
- L2 的 `rp_ref_pips` 口径：**ATR 自参照（推荐）** vs 固定常数 `SL_REF_PIPS`（如 55 = 实测中位）？
- L2 是否允许对"结构 SL < ATR 应然"的笔数**放大**？（建议**否** —— 保持"只缩不放大"单一性，否则须重新论证加仓风险。）

---

## 7. 跟踪止损 · 另行课题（Owner 2026-11-18 裁定）

**裁定**：**暂时取消"跟着止损"** —— 整个 `_revise_owned_position`（`fx_trade_bot_v685.py` L2672 起，每周期对每个持仓改写 SL / TP）**已关闭**，开关 `REVISE_OWNED_POSITION = _opt("REVISE_OWNED_POSITION", False)`（可逆：env `OPT_REVISE_OWNED_POSITION=1` 或 config `OPT_REVISE_OWNED_POSITION=true`）。

**理由**：硬抗（固定 SL/TP + 时间到期 / 方向翻转）更能**抵御区间震荡**；跟踪止损"是个大课题"，本次不考虑，**以后另立课题评估**。

**现状（已核实）**：`config_profile.json` 的 `tp_trailing.{DYNAMIC_TP,TRAILING_TP,TRAILING_SL}` 均为 `false`，`DynamicPositionManager` 未传 `enabled`（默认 `False`）→ `_revise_owned_position` 是**唯一在跑**的持仓期改写路径，现已关。

**未来课题范围**：参考 `gemini_ai/tracking_stop_loss.md` 的 #1 阶梯分批止盈 / #2 高水位回吐锁；与 L3 合并评估。
