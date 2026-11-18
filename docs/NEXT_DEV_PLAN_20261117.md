# Exit Risk Development Plan v1.0

> 文件名保留 `NEXT_DEV_PLAN_20261117.md`（既有代码注释引用本文件 §2.1 / §3.1，改名会失效）。
> 版本：**v1.0**（2026-11-18 定稿；基线 = 2026-11-17 草案 + 2026-11-18 Owner 裁定与两轮评审修正）。
> 主题：**退出风险治理（Exit Risk）** —— 治理 SL 尾部损失、宽幅震荡连续扫损、仓位风险不均衡。
> 纪律：一切新逻辑**先影子（只记录、不改决策）**，用真实数据验证后再转正；只做结构性、可解释的改动，拒绝网格搜索式局部最优。
> **影子 ≠ 被动等待**：每个影子实验必须写明①反事实算法 ②有效性指标 ③失败条件 ④下一步处置；没有这四项的不算影子实验。
> **本轮边界（Owner 2026-11-18）**：本文件为**开发基线**；下一步只拆任务单，**暂不写交易代码、不改任何现有决策逻辑**。

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

### 0.5 架构总纲：三层分离（不要混成一个综合评分）

本课题拆成**三个正交层次**，各自回答一个独立问题，**不允许合并成单一评分/权重池**：

| 层次 | 核心问题 | 作用 | 本计划落点 |
|---|---|---|---|
| **Market Risk** | 当前市场是否值得交易？ | 识别宽幅震荡 / 连续扫损环境 | §3（P1-B） |
| **Position Risk** | 这笔交易应该承担多少风险？ | 风险定额仓位 | §2.1（P1-A，L2） |
| **Exit Risk** | 交易进入后如何控制损失？ | SL / 保本 / 分批止盈 | §7（P3，暂缓） |

理由：三层若混成一个综合乘数，将来会不断叠加"乘数 / 阈值 / 过滤器"，最终无法解释到底是谁改变了交易行为。**每一层单独可观测、单独可回滚、单独有验收指标。**

> 注：§14 prob overlay 的 `size_scale = min(conv, risk_cap, regime_mult)` 属 Position Risk 层的**存量**实现；L2 是**新增的第二个 Position Risk 变量**（交易轴），两者相乘互补（§2.1）。

### 0.6 优先级裁定（Owner 2026-11-18，v1.0）

| 项目 | 裁定 | 优先级 |
|---|---|---|
| P0 退出审计（Exit Audit Foundation） | **必须先完成**，是后续所有实验的数据基础 | **P0** |
| L2 风险定额仓位（两阶段 A→B） | 当前最值得推进的**决策变量** | **P1-A** |
| §3 宽幅震荡识别与损失聚集研究 | 战略价值高，**独立设计** | **P1-B** |
| L1 SL↔TP 几何重构 | **暂缓**，不抢先修改（实际 SL/TP 中位 = 1.01，非主要矛盾） | P2 |
| L3 保本 / 分批止盈 | **暂缓**（跟踪止损已关闭） | P2 |
| §4 趋势追顶（entry timing） | **暂缓** | P3 |

**明确赞成 L1 降级**：实际触发的中位 SL/TP = 1.01（30.4 vs 30.0 pips）。继续在"SL 与 TP 的比例"上投入，很可能是在优化一个**并非主要矛盾**的指标。

### 0.7 Exit Risk Development Roadmap（v1.0 执行顺序）

1. **P0 — Exit Audit Foundation**：建立 OANDA 平仓事实台账、归因、去重、部分平仓规则、对账与分析报告。**必须先完成**。
2. **P1-A — L2 风险定额仓位**：先算反事实仓位，评估尾部损失削减 vs 盈利同步缩小的代价（两阶段 A→B，见 §2.1/§2.2）。
3. **P1-B — Wide-range Regime**：建立宽幅震荡判别，研究**连续双向扫损与交易频率**（见 §3/§3.2）。
4. **P2 — L1 SL/TP 几何重构**：等 L2 与市场状态分析完成，再决定是否调整止损结构。
5. **P3 — Exit Management**：重新评估分批止盈、高水位锁盈等机制。**跟踪止损保持关闭。**

---

## 1. P0 · Exit Audit Foundation（先修盲点，零决策风险）

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

### 1.1 数据完整性契约（唯一平仓事实口径 · v1.0 新增）

**第一原则：OANDA 是唯一账本（single ledger）。本地日志不得成为第二套账本。** 本地 `exit_audit` 只是 OANDA 事实的**只读投影**，任何字段都必须可回溯到 OANDA 原始对象。

**每笔平仓最少必备字段**（缺任一 → 该笔标记 `incomplete`，不计入统计分母）：

| 字段 | 来源 | 说明 |
|---|---|---|
| `trade_id` | OANDA trade | 主键 |
| `closing_transaction_id` | closing tx | 平仓交易 ID（去重用） |
| `instrument` | trade | |
| `direction` | trade（long/short） | |
| `entry_price` / `exit_price` | trade / tx | |
| `initial_sl` / `initial_tp` | trade `stopLossOnFill` / `takeProfitOnFill` | 开仓时挂单值 |
| `realized_pl` | trade | |
| `close_reason` | closing tx `reason` | 映射到 `TP / SL / ACTIVE` |
| `close_time` | trade `closeTime`（UTC） | |
| `client_ext_tag` | trade `clientExtensions.tag` | 归因用 |
| `attribution_status` | 计算 | 见下 |

**归因必须三态，且禁止把"无法归因"默认为 ACTIVE**：

1. `OWNED` —— 已确认归属于本策略（tag 命中本 profile）。
2. `FOREIGN` —— 已确认**不属于**本策略（tag 存在但不匹配，或他账户/他人挂单）。
3. `UNKNOWN` —— **无法归因**（无 `clientExtensions`、tx 缺失、字段不完整）。

> 现状问题（`fx_trade_bot_utils_v1.py::audit_owned_closed_trades`）：分类只有 `TP / SL / ACTIVE`，**没有 `UNKNOWN` 态** → 无法归因的笔数会被并入 `ACTIVE`，污染"净 P&L"与连续性统计。**必须在 P0 任务单中补齐三态。**

**去重与累计规则**（P0 任务单必须显式实现）：

- **主键 = `(trade_id, closing_transaction_id)`**；同一 `trade_id` 多次出现 → 视为**部分平仓**。
- **部分平仓**：同一 `trade_id` 的多条 closing tx → ①各条单独成行（保留 `partial_index`）②另出一行**聚合口径**（`realized_pl` 累计、`exit_price` 取最后一次）。
- **重复扫描**：以 `closing_transaction_id` 去重，避免 `TradesList` 跨窗口重复计入。
- **P&L 口径统一**：统计一律用**聚合口径**，避免部分平仓被重复计权。

**对账**：每日输出 `Σ realized_pl`（本地投影）必须等于 OANDA 账户该窗口已实现 P&L（容差 0），否则报 `reconciliation_mismatch`。

**失败降级**：任何 OANDA 读取/解析失败 → 中性降级（`never raises`），跳过该笔并记 `fetch_error`，**绝不影响交易循环**。

**当前状态**：只读审计（jsonl + 台账 CSV）已落地并在跑；**上表字段中的 `initial_sl/initial_tp`、三态归因、部分平仓聚合、对账校验尚未实现** → 全部纳入 §8.1 任务单。

---

## 2. P1 · SL 损失最小化（三条杠杆，逐条影子验证）

| 杠杆 | 内容 | 预期效果 | 风险 | v1.0 裁定 |
|---|---|---|---|---|
| **L1 重连 SL↔TP** | SL 上限定在 ≤ 1.0–1.5×TP，或恢复随波动放大的 ATR-TP | 直接压缩单笔亏损 + 尾部"一把回吐一周" | 止损更紧 → 可能被洗，胜率下降（需 A/B） | **P2 · 暂缓**（实际 SL/TP=1.01，非主要矛盾） |
| **L2 风险定额仓位** | `units ∝ 风险预算 / SL_pips`，让每笔 SL 的美元亏损大致恒定 | 消除"宽止损=大亏"，与已上线的 prob overlay（只缩不放大）天然互补 | 低（只动 size） | **P1-A · 主攻**（两阶段 A→B） |
| **L3 更早保本 + 分批止盈 / HWM 锁盈** | 机制已有（BREAKEVEN 实测有效，2 笔落在 +1p）；扩展覆盖面 + 参考 `gemini_ai/tracking_stop_loss.md` 的 #1（阶梯分批）与 #2（高水位回吐锁） | 把"浮盈回吐变亏损"转成"落袋" | 中（可能过早离场） | **P2 · 暂缓**（跟踪止损保持关闭） |

**验收标准**：固定单量下，SL 单笔均值与 p95 尾部下降，且胜率/期望值不显著恶化（用 §1 的审计数据对比）。

### 2.1 L2 · 风险定额仓位（设计稿 · 先影子，不改决策）

**问题**：`size_units = DEFAULT_LOT_SIZE × size_scale`（概率覆盖层输出），**与 SL 距离无关**。SL 距离 p50=54.6 / p90=121.8 / max=299.7 pips → 每笔 SL 的美元亏损极不均衡，"宽止损 = 大亏"直接制造 §0.4 的尾部。

**口径（只缩不放大，与 prob overlay 相乘互补）**：

```text
rp_ref_pips = intended_sl_pips                        # ATR 口径的"应然"止损距离
sl_pips_act = |current − sl_price| / pip              # 实际下单 SL
rp_mult     = clamp(rp_ref_pips / sl_pips_act, RP_F_LO, 1.0)
units_raw   = round(size_units_prob × rp_mult)        # 未兜底的真实计算值
```

- `intended_sl_pips = max(min_sl_pips_jpy|std, round(atr_val / pip × ATR_SL_MULT, 1))`
  —— 与 `fx_trade_bot_v685.py` L3128–3131 的 ATR fallback **同式**，**无需新增全局常数**（自参照）。
- `sl_pips_act ≤ ref → rp_mult = 1.0`（不动）；**仅当结构 SL 比 ATR 应然更宽时按比例缩量** → 正好削 p90 / max 尾档。
- `RP_F_LO` 默认 `0.25`（与 §14 `F_LO` 同量级），是单笔最大缩量下限。
- **互补性**：prob overlay 按方向确信度 / regime / MC 区间宽度（**市场轴**）缩，L2 按 SL 几何（**交易轴**）缩，两者相乘 → 双轴封顶。

**⚠️ MIN_LOT 风险边界（v1.0 修正 · 必须是硬约束）**：

原式 `units_l2 = max(MIN_LOT, round(size_units_prob × rp_mult))` **是错的**：若风险计算要求 500 units 而 `MIN_LOT=1000`，强行抬到 1000 会**突破风险预算**。正确规则：

| `units_raw` vs `MIN_LOT` | 处置 |
|---|---|
| `units_raw ≥ MIN_LOT` | 正常执行 |
| `units_raw < MIN_LOT` | **拒绝该候选**（`would_reject = True`），**不允许抬到 MIN_LOT** |

- 影子阶段只**记录** `units_raw / MIN_LOT / would_reject`，不影响下单（`applied=False`）。
- 转正（L2-B）时：`would_reject = True` → **真正拒绝该候选**，而非下注 MIN_LOT。
- 等价表述：`units_l2 = units_raw if units_raw ≥ MIN_LOT else None`（`None` = 不下单）。

**Hook 点**：`fx_trade_bot_v685.py` —— `sl_price` 已算出、`tp_price` 之后、`all_candidates.append` 之前；`size_units` / `sl_price` / `current` / `atr_val` / `pip_cache[pair]` 均在作用域内（现状已落地，见 §2.3）。

**开关**：`OPT_RISK_PARITY_SIZING`（沿用 `_opt()` 约定：env `OPT_RISK_PARITY_SIZING` > config > default）。

- `off`（默认）= **影子**：不改下单 `size_units`，只额外计算 `units_raw` 并落盘。
- `on` = 生效：`size_units = units_l2`（`would_reject` 时拒绝候选）。

**影子产物**：`logs/sizing_shadow_YYYYMMDD.jsonl`，逐候选一行：
`pair / direction / entry / sl_price / tp_price / sl_pips_act / ref_pips / pip_value_usd / units_prob / units_raw / units_l2 / rp_mult / below_min / applied`。
配套分析器（`utils/analyze_sizing_shadow.py`）做反事实估算：
`SL_USD_l2 = units_l2 × sl_pips_act × pip_value_usd` vs 实际 → 给出尾档（p90 / max）下降幅度。

**验收标准（v1.0 修正）**：

> ⚠️ 原文「`rp_mult` 预期 p50 ≈ 1.0、p90 < 0.6」**在数学上不可能同时成立** —— 分位数必须单调 `P10 ≤ P50 ≤ P90`。**不得预设一个尚未被数据支持的分布目标**，改为**只观察不预设**：

1. **分布观察**：报 `rp_mult` 的 **p10**（极端缩量程度）/ **p50**（一般缩量比例）/ **p90**（多数交易是否未受明显影响），以及 **`rp_mult < 1.0` 的比例 = 触发率**。
2. **反事实**：SL 亏损 USD 的 **p90 / max 下降**，最深 25% 占比下降。
3. **EV 不显著恶化**：只缩不放大 → 宽 SL 笔的**盈利也同步缩小**，须核对净期望（**这是 L2 的唯一风险点**）。

**相关性敞口（v1.0 新增）**：L2 只治**单笔**尾部，治不了**同向货币共振**（§0.4 的 `2026-11-03 19:12` 同分钟 5 笔 JPY 系扫损）。影子行**顺带记录**当前已持仓的共同 base / quote 净敞口（如 `JPY_net_units`），供后续评估是否需要**组合级风险预算上限**（不在本轮范围）。

**边界**：与 L1 正交（L1 改 SL 距离、L2 改 size，`ref` 恒取 ATR 口径，不受 L1 影响）；与 §3 正交（§3 是"要不要交易"、L2 是"交易多少"）。属 §0.5 的 **Position Risk** 层。

### 2.2 L2 分阶段与转正门槛（v1.0 · Owner 拍板「两阶段 A→B」）

**L2-A · 几何缩量验证（先做）**

- 公式：`rp_mult = min(1, SL_ref / SL_act)`，**pip 口径**。
- 目标：验证「**宽 SL 是否确实造成尾部风险**」。
- 交付：`sizing_shadow` + `analyze_sizing_shadow` 反事实报告（SL 尾部 + EV）。
- **失败条件**（写死，避免无限观察）：反事实 SL `p90/max` 无明显下降，**或** EV 显著恶化 → **停止 L2**，回头查 §3。

**L2-B · USD 风险定额（L2-A 有效后再做）**

- 公式：`units = clamp(round(R_usd / (sl_pips_act × pip_value_usd) × size_scale_prob), 下限=MIN_LOT 规则, 上限=size_units_prob)`，**只缩不放大**。
- 目标：消除跨**报价币种**（`XXX/JPY` vs `XXX/USD`）的隐性风险敞口偏差 —— §0.4 中亏损前二的 `EUR_JPY(−914)` / `GBP_JPY(−860)` 正是 JPY 报价。
- 前置：`pip_value_usd` 逐笔可得且可信。
- 转正门槛：L2-B 反事实（USD 口径）尾部下降 **≥** L2-A，且 EV 不恶化。

> **为什么分两阶段**（Owner 2026-11-18）：避免把「几何」与「币种换算」两个变量混在一个实验里。Gemini 建议直接上 USD 定额；本计划采纳「一次只变一个变量」。

### 2.3 L2 当前实现状态（2026-11-18）

- **已落地**：`utils/risk_parity_sizing.py`（`compute_risk_parity` / `log_sizing_shadow`）+ `utils/analyze_sizing_shadow.py`；bot 侧开关 `RISK_PARITY_SIZING = _opt("RISK_PARITY_SIZING", False)`（默认影子）、hook 已接线。
- **待改（纳入 §8.2 任务单，本轮不改代码）**：
  1. `units_l2 = max(base, …)` → 改为 `units_raw` + `would_reject`，**不再抬到 MIN_LOT**；
  2. 影子行补 `pip_value_usd` / `units_raw` / `below_min` / 相关性净敞口字段；
  3. 分析器补 `rp_mult` p10/p50/p90 + 触发率 + 尾部分位（对齐 §2.1 修正后的验收）。

---

## 3. P1-B · 宽幅震荡：交易行为与损失聚集研究（最难的一环）

**观察（用户）**：窄幅震荡尚可探测（MC 提示 consolidation、ATR 指标也有），但**宽幅震荡两头打 SL 最难**。

**核心升级（v1.0）**：宽幅震荡的危险**不是**"普通的 SL 命中率高"，而是 ——

- 多空方向**反复切换**；
- 两侧进场**都可能**遭遇不利波动；
- 趋势指标不断产生方向信号；
- **单笔交易看起来合理，连续交易却持续亏损**（损失**聚集**）。

→ 因此**不能只统计 `wide_range → SL_hit_rate`**。§3 研究的是**市场状态 × 交易行为 × 损失聚集**的关系，而非再加一个 ATR 阈值。研究指标见 §3.2。

**思路**：关键不是"有没有区间"，而是**区间的宽度** + **在该区间里的交易频率与方向切换**。区分 narrow-range（可探测、可交易）与 wide-range（双向扫损、应回避）。

**候选特征**：
- MC `distribution.range_90` 宽度 / `prob_bands` 展宽；
- ATR 的分位（相对自身历史）；
- 布林带宽度 / 近期高低点振幅；
- 与 §14 概率路线 `W = (q95-q05)/price` 已算出的 `risk_cap` 天然衔接。

**验收标准（v1.0 升级 · 不再是单一 SL 命中率）**：影子标记出的 "wide-range 时段"，必须在 §3.2 的**多项**指标上显著区别于常态 —— 尤其**连续 SL 次数**、**双向 SL 事件**、**交易频率** —— 才证明判别有效，再做处置（§3.3）。

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

### 3.2 研究指标：宽幅震荡下的交易行为与损失聚集（v1.0 核心）

判别量 `ATR_pct` 只是**输入**；真正要回答的是「这个市场状态是否在制造**损失聚集**」。至少统计以下 6 项（对照 §1 `exit_audit` 事实台账，按 `tier` group-by）：

| 指标 | 要回答的问题 | 计算口径 |
|---|---|---|
| **SL 命中率** | 是否更容易止损？ | `n(SL) / n(OWNED)`，按 tier 分组 |
| **连续 SL 次数** | 是否形成连续扫损？ | 同一 profile 按 `close_time` 排序，统计连续 SL **游程长度**分布（max run / mean run） |
| **双向 SL 事件** | 同一区间是否先后打掉多空？ | 同一 pair 在时间窗 T 内先 BUY 后 SELL（或反之）且**均** SL → 计 1 次「双向扫损」 |
| **净 P&L** | 是否真的造成账户损失？ | `Σ realized_pl`（**聚合口径**）按 tier 分组 |
| **MFE / MAE** | 是方向判断错，还是进场时机不合适？ | 每笔 MFE / MAE（pips）分布；MFE 小且 MAE 大 → 时机问题 |
| **交易频率** | 是否存在过度交易？ | 单位时间开仓笔数 / 每 pair 每日笔数，按 tier 分组 |

> **最后一项（交易频率）是关键洞察**：宽幅震荡可能**不是每一笔都很差**，而是**交易次数太多**。若 wide tier 的交易频率显著高于 normal，处置重点应从"单笔过滤"转向"频率抑制 / 冷却"。

### 3.3 处置策略（Owner 2026-11-18 裁定 = 阶梯降仓 · 档位待影子数据）

| 方案 | 适用 | 理由 |
|---|---|---|
| **阶梯降仓（已裁定）** | 一般 wide | 宽幅震荡常是**趋势突破的前夜** → 直接 `skip` 易错过真突破的第一波（叠加 §4 追顶顾虑：区间内不轻仓试探，突破后更难进）。降到 `0.25x–0.5x`：把"两头打 SL"的亏损控制进预算，同时保留底仓。 |
| **放宽 TP / 移动目标** | wide + 已确认区间 | 避免在区间上沿被"假突破"打掉 TP 后再反向。 |
| **直接 skip（仅极端）** | `ATR_pct` 极端高（如 ≥ 1.8）或已出现连续双向扫损 | 只在最坏情形兜底，**不作为默认**。 |
| **频率抑制 / 冷却** | 交易频率指标异常 | 若 §3.2 证实"过度交易"为主因，则优先**缩频**而非动仓位。 |

- 与 §14 的 `regime` 定仓合流（参考 `gemini_ai` `MC_REGIME_MULTIPLIER["CONSOLIDATION"]` 的分档思路）。
- **Owner 裁定（2026-11-18）= 阶梯降仓**：`wide` tier 默认降到 `0.25x–0.5x`，**不跳单** —— 宽幅震荡常是趋势突破前夜，保留底仓以免错过真突破第一波（叠加 §4 追顶顾虑）。
- `skip` **仅极端兜底**（`ATR_pct ≥ 1.8` 或已出现连续双向扫损），**不作为默认**。

---

## 4. P3 · 趋势追顶（entry timing · 暂缓）

**观察（用户）**：趋势来了、进场、好家伙正好到顶。

**思路**：用 MC 分布中的**相对分位位置**（当前价在 `q05..q95` 中的位置）判断是否已过度延伸，作为追价过滤。

**验收标准**：影子记录 "进场分位 vs 后续 MFE/MAE"，验证高位进场是否系统性吃亏。

---

## 5. D+1 具体安排（对齐 §0.7 Roadmap）

> 本节的"明天"= 计划定稿后的**第一个执行日**；顺序严格服从 §0.7，**不跳步**。

1. **P0 先行**：完成 §8.1 任务单（Exit Audit Foundation 数据完整性契约）—— 三态归因、`initial_sl/tp`、部分平仓聚合、对账校验、同分钟扫损聚类、Clean Baseline 切分。**P0 未完成前，L2 / §3 的反事实分析一律不得作为结论。**
2. **P1-A · L2**：按 §8.2 任务单修正现有影子实现（`units_raw` + `would_reject`、补字段、补分位分析），跑满观察周期后出反事实报告。
3. **P1-B · §3**：按 §8.3 任务单把 `wide_range_shadow` 与 `exit_audit` **按 `tier` 对齐**，统计 §3.2 六项指标。
4. **不改任何决策逻辑**：prob overlay（`VERDICT_MODE=soft`）与 MC cron（6h 伦敦基准）保持观察；`REVISE_OWNED_POSITION` 保持关闭（§7）。
5. **本轮边界**：只落任务单与影子代码，**不上线任何影响下单/拒绝的逻辑**（`applied` 恒 `False`）。

---

## 6. 待决问题（需 Owner 拍板 · v1.0 重排）

| # | 待决项 | v1.0 状态 | 备注 |
|---|---|---|---|
| 1 | **§3 wide-range 处置**：降仓 vs skip | **已裁定 = 阶梯降仓**（`0.25x–0.5x`，见 §3.3） | 保留底仓、不跳单；`skip` 仅极端兜底 |
| 2 | L2 `rp_ref_pips` 口径：ATR 自参照 vs 固定常数 `SL_REF_PIPS` | **已裁定 = ATR 自参照** | 品种/波动率自适应；固定常数会惩罚高波品种 |
| 3 | L2 是否允许放大（结构 SL < ATR 应然） | **已裁定 = 否（只缩不放大）** | 保持"风险预算封顶器"单一职责；避免滑点/跳空暴击 |
| 4 | **L1 SL 上限取值**（1.0×TP vs 1.5×TP） | **暂缓**（L1 已降级 P2） | 实际 SL/TP=1.01，非主要矛盾；等 L2/§3 完成再重估 |
| 5 | §1 审计是否覆盖实盘腿 | **已解决 = 自动覆盖** | 各 profile 各账户各自只读拉取 |
| 6 | L2 两阶段口径（一次性 USD vs A→B） | **已裁定 = 两阶段 A→B** | "一次只变一个变量"（§2.2） |

---

## 7. 跟踪止损 · 另行课题（P3 · Owner 2026-11-18 裁定）

**裁定**：**暂时取消"跟着止损"** —— 整个 `_revise_owned_position`（`fx_trade_bot_v685.py` L2672 起，每周期对每个持仓改写 SL / TP）**已关闭**，开关 `REVISE_OWNED_POSITION = _opt("REVISE_OWNED_POSITION", False)`（可逆：env `OPT_REVISE_OWNED_POSITION=1` 或 config `OPT_REVISE_OWNED_POSITION=true`）。

**理由**：硬抗（固定 SL/TP + 时间到期 / 方向翻转）更能**抵御区间震荡**；跟踪止损"是个大课题"，本次不考虑，**以后另立课题评估**。

**现状（已核实）**：`config_profile.json` 的 `tp_trailing.{DYNAMIC_TP,TRAILING_TP,TRAILING_SL}` 均为 `false`，`DynamicPositionManager` 未传 `enabled`（默认 `False`）→ `_revise_owned_position` 是**唯一在跑**的持仓期改写路径，现已关。

**Roadmap 位置**：属 §0.5 的 **Exit Risk** 层，与 **L3 保本 / 分批止盈**同属 **P3 · Exit Management**，**本轮不动**。

**未来课题范围**：参考 `gemini_ai/tracking_stop_loss.md` 的 #1 阶梯分批止盈 / #2 高水位回吐锁；与 L3 合并评估。

---

## 8. 任务单（本轮唯一交付物 · 只拆单，不写交易代码）

> **纪律**：以下三张单子在本轮**只产出"任务单"本身**（口径、字段、验收、失败条件、不做清单）。**暂不写交易代码、不改任何现有决策逻辑。** 每张单子的影子实验必须满足头部纪律的**四要素**（反事实算法 / 有效性指标 / 失败条件 / 下一步处置）。

### 8.1 P0 · Exit Audit Foundation 任务单

**目标**：把 §1.1 的数据完整性契约落成"OANDA = 唯一账本"的**只读投影**，让 SL 尾部 / 连续扫损 / 相关性扫损在日志里可对账、可追溯。

**输入**：OANDA `TradesList`(CLOSED) + `Transaction`(closing tx) + `clientExtensions.tag`。**输出**：`logs/exit_audit_YYYYMMDD.jsonl`（逐笔）+ 每日 `trade_log.csv`（gemini_ai 同构列）。

**必做项（对照 §1.1）**：

| # | 事项 | 验收 |
|---|---|---|
| 1 | **三态归因** `attribution_status ∈ {OWNED, FOREIGN, UNKNOWN}`；**禁止 UNKNOWN 默认成 ACTIVE** | 统计分母只含 `OWNED`；`UNKNOWN` 单独可见 |
| 2 | 补 `initial_sl` / `initial_tp`（来自 trade `stopLossOnFill`/`takeProfitOnFill`） | 每笔可回溯开仓意图几何 |
| 3 | **去重主键 = `(trade_id, closing_transaction_id)`**；部分平仓 → 单条 + 聚合双口径 | 重复扫描不产生重复行；`Σ` 用聚合口径 |
| 4 | **对账**：`Σ realized_pl`（本地投影）== OANDA 窗口已实现 P&L（容差 0） | 不一致 → 报 `reconciliation_mismatch` |
| 5 | **同分钟扫损聚类（Correlation Cluster）**：`closeTime` 相差 ≤ 60s 且同为 `SL` → 归为一个相关性事件 | 能区分"零星止损"与"宏观事件批量扫损" |
| 6 | **Clean Baseline 切分**：`2026-11-18`（`_revise_owned_position` 关闭）**之后**的数据单独切出，不与关闭前混算 | 便于 L2 反事实有干净对照 |
| 7 | `never raises`：任何读取/解析失败 → 跳过该笔记 `fetch_error`，**绝不影响交易循环** | 影子失败不影响主循环 |

**失败条件**：连续两天对账不一致 或 `UNKNOWN` 占比 > 20% → 暂停下游（L2/§3）分析，先修审计。

**不做**：不参与任何决策、不落"第二套账本"、不写任何 state 文件。

### 8.2 L2 · 风险定额仓位设计任务单（两阶段 A→B）

**目标**：在**只缩不放大**前提下，验证"宽 SL = 尾部大亏"，并量化削尾 vs 盈利同步缩小的代价。

**现状**：`utils/risk_parity_sizing.py` + `utils/analyze_sizing_shadow.py` 已落地影子（默认 `OPT_RISK_PARITY_SIZING=off`）；**当前仍为旧口径** `units_l2 = max(base, …)`。

**必做项（对照 §2.1 / §2.3）**：

| # | 事项 | 验收 |
|---|---|---|
| 1 | **修 MIN_LOT 边界**：`units_raw = round(size_units_prob × rp_mult)`；`units_raw < MIN_LOT → would_reject=True`，**不抬到 MIN_LOT**；等价 `units_l2 = units_raw if units_raw ≥ MIN_LOT else None` | 影子行含 `units_raw / below_min / would_reject` |
| 2 | 影子行补 `pip_value_usd` / 相关性净敞口（如 `JPY_net_units`） | 供 L2-B 与组合级风险预算前置评估 |
| 3 | 分析器补 `rp_mult` **p10 / p50 / p90** + **触发率**（`rp_mult<1.0` 占比）+ 反事实尾部分位（SL USD p90/max、最深 25% 占比） | **禁止预设分布目标**（废弃 p50≈1.0 & p90<0.6） |
| 4 | **L2-A** 先做：pip 口径 `rp_mult = min(1, SL_ref/SL_act)`，验证宽 SL 是否致尾损 | 反事实 SL p90/max 下降；EV 不显著恶化 |
| 5 | **L2-B** 后做（L2-A 有效后）：USD 定额 `units = clamp(round(R_usd/(sl_pips_act×pip_value_usd)×size_scale_prob), MIN_LOT 规则, size_units_prob)` | 尾部下降 ≥ L2-A；消除 JPY 报价偏差 |

**失败条件**：L2-A 反事实 SL `p90/max` 无明显下降 **或** EV 显著恶化 → **停止 L2**，回头查 §3。

**不做**：不对"结构 SL < ATR 应然"放大；不与 §3 的"要不要交易"合并；不引入新全局常数（`ref` 取 ATR 自参照）。

### 8.3 §3 · Wide-range 损失聚集研究任务单

**目标**：把 §3 从"宽幅识别"升级为"**市场状态 × 交易行为 × 损失聚集**"研究，回答"宽幅震荡危险的是单笔、还是频率"。

**现状**：影子层已实现（`utils/wide_range_sizing.py` + `WIDE_RANGE_SHADOW` hook，`applied=False`），判别量 `ATR_pct = 当日 ATR / 近 20 日 ATR 中位`，阈值 `narrow<0.8 / normal 0.8–1.3 / wide≥1.3`。

**必做项（对照 §3.2 / §3.3）**：

| # | 事项 | 验收 |
|---|---|---|
| 1 | 把 `wide_range_shadow`（按 `pair/day` 的 `tier`）与 `exit_audit`（按 `OWNED` 逐笔）**按时间/pair 对齐 join** | 每笔平仓可标注其开仓时 `tier` |
| 2 | 统计 §3.2 **六项指标**：SL 命中率 / 连续 SL 游程 / 双向 SL 事件 / 净 P&L（聚合口径）/ MFE-MAE / **交易频率** | `wide` 在**多项**（尤其连续 SL、双向 SL、频率）显著区别于 `normal` |
| 3 | **交易频率**单列：单位时间开仓笔数 / 每 pair 每日笔数，按 `tier` 分组 | 判定"过度交易"是否为主因 |
| 4 | 处置方案对比（**先影子、不改决策**）：阶梯降仓 `0.25x–0.5x` vs 频率抑制/冷却 vs 极端 `skip` | 给出反事实 P&L，供 §6 第 1 问拍板 |

**失败条件**：`wide` 时段在六项指标上与 `normal` 无显著差异 → 判别量（`ATR_pct`）无效，回退改特征（已实现波动分位 / BB 宽度分位）。

**不做**：**不**只验证 SL 命中率；**不**默认 `skip`（倾向阶梯降仓）；**不**与 L2/Exit 层合并成单一评分。

---

## 附：v1.0 变更摘要（相对 2026-11-17 草案）

1. **新增 §0.5 三层分离架构 / §0.6 优先级裁定 / §0.7 Roadmap**；L1 由主攻降级为 P2。
2. **§1 → Exit Audit Foundation**，新增 §1.1 **数据完整性契约**（唯一账本 / 三态归因 / 去重 / 部分平仓 / 对账 / never raises）。
3. **§2.1 修正**：MIN_LOT **硬边界**（不再抬到 MIN_LOT）；验收**废弃数学矛盾的 p50/p90 预设**，改为 p10/p50/p90 观察 + 触发率；补相关性敞口。
4. **新增 §2.2 L2 两阶段 A→B**、**§2.3 L2 当前实现状态**。
5. **§3 升级**为宽幅震荡**损失聚集研究**：新增 §3.2 六指标、§3.3 处置策略。
6. **§5 对齐 Roadmap**；**§6 待决问题重排**并标注 v1.0 裁定；**§7 归入 P3**。
7. **新增 §8 三张任务单**（P0 / L2 / Wide-range）—— 本轮唯一交付物。
