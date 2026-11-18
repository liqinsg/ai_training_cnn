# 任务单（定稿）· Exit Risk 治理（2026-11-18）
> 基线文件：`docs/NEXT_DEV_PLAN_20261117.md`（v1.0，2026-11-18 定稿）
> 执行日期：2026-11-18
> 版本：FINAL（合并 Dola 全量骨架 + TRAE P0 细粒度拆分）
> **最高纪律**：本轮**只产出任务单与影子代码**，**不写交易代码、不改任何现有决策逻辑**（`applied` 恒 `False`）。任何 agent 执行前必须先读本文件。
> **影子四要素**（每张单子必须满足，缺一不可）：①反事实算法 ②有效性指标 ③失败条件 ④下一步处置。
> **三层分离**（§0.5）：Market Risk / Position Risk / Exit Risk 各自独立可观测、可回滚、有验收指标，**禁止合并成单一评分**。

---

## 执行顺序（严格服从 §0.7 Roadmap，不跳步）
1. **TASK-1（P0）** Exit Audit Foundation —— **必须先完成**，是后续所有实验的数据基础。
2. **TASK-2（P1-A）** L2 风险定额仓位影子修正 —— P0 验收通过后启动。
3. **TASK-3（P1-B）** Wide-range 损失聚集研究 —— P0 验收通过后启动，与 TASK-2 并行。
4. **P0 未完成前，TASK-2 / TASK-3 的反事实分析一律不得作为结论。**

---

## TASK-1 · P0 Exit Audit Foundation（数据完整性契约）
**优先级**：P0（阻塞后续）
**目标**：把 §1.1 数据完整性契约落成"OANDA = 唯一账本"的**只读投影**，让 SL 尾部 / 连续扫损 / 相关性扫损在日志里可对账、可追溯。
**输入**：OANDA `TradesList`(CLOSED) + `Transaction`(closing tx) + `clientExtensions.tag`。
**输出**：
- `logs/exit_audit_YYYYMMDD.jsonl`（逐笔平仓审计）
- 每日 `daily_results_profile*/YYYY-MM-DD_trade_log.csv`（与 gemini_ai 同构列：`entry_price, sl_price, tp_price, pips, profit_usd, exit_reason, exit_time`）

### 子任务拆分（细粒度，含文件位置与动作）

#### 子任务 1.1 · 实现核心只读审计函数
- **文件位置**：`fx_trade_bot_utils_v1.py`（新增函数，勿改现有决策路径）
- **动作**：新增**只读**函数（如 `audit_closed_trades_readonly()`），拉取 CLOSED trades → 按 `clientExtensions.tag` 归因 → 取 closing tx `reason` → 分类为 `TP / SL / ACTIVE`。
- **复用已有能力**（勿重写）：`check_and_record_tp_cooldown()` / `refresh_tp_cooldown_from_recent_tx()` 已实现"读 CLOSED trades + tag 归因 + 查 closing tx reason"，**只缺持久化**，直接扩展。
- **参考移植**（gemini_ai 项目）：`utils/oanda_state.py`（`get_closed_trades` / `build_post_exit_context` / `parse_oanda_time`）、`utils/post_exit_context.py`（`PostExitTracker.get_context`，只读、never raises）。

#### 子任务 1.2 · 三态归因（禁止 UNKNOWN 默认成 ACTIVE）
- **文件位置**：`fx_trade_bot_utils_v1.py`（修改现有 `audit_owned_closed_trades` 或在新函数内实现）
- **动作**：`attribution_status ∈ {OWNED, FOREIGN, UNKNOWN}` 三态：
  - `OWNED` = tag 命中本 profile；
  - `FOREIGN` = tag 存在但不匹配（他账户/他人挂单）；
  - `UNKNOWN` = 无 `clientExtensions` / tx 缺失 / 字段不完整。
- **硬要求**：统计分母只含 `OWNED`；`UNKNOWN` 单独计数、单独可见，**严禁并入 ACTIVE**。

#### 子任务 1.3 · 数据完整性契约（必备字段）
- **动作**：每笔平仓记录必须含以下字段，缺任一 → 标记 `incomplete=true`，不计入统计分母：
  `trade_id, closing_transaction_id, instrument, direction, entry_price, exit_price, initial_sl, initial_tp, realized_pl, close_reason(TP/SL/ACTIVE), close_time(UTC), client_ext_tag, attribution_status`
- **`initial_sl / initial_tp` 来源**：trade 对象的 `stopLossOnFill` / `takeProfitOnFill`（开仓时挂单值，反映开仓意图几何）。

#### 子任务 1.4 · 去重主键 + 部分平仓双口径
- **动作**：
  - 主键 = `(trade_id, closing_transaction_id)`，以 `closing_transaction_id` 去重，避免 `TradesList` 跨窗口重复计入。
  - 同一 `trade_id` 多条 closing tx → 视为**部分平仓**：①各条单独成行（保留 `partial_index`）；②另出一行**聚合口径**（`realized_pl` 累计、`exit_price` 取最后一次）。
  - 所有统计 `Σ` 一律用**聚合口径**，避免部分平仓被重复计权。

#### 子任务 1.5 · 影子输出（JSONL + CSV，不参与决策）
- **动作**：
  - `logs/exit_audit_YYYYMMDD.jsonl`：逐笔一行，含子任务 1.3 全部字段 + `partial_index`（可选）+ `cluster_id`（子任务 1.6）+ `clean_baseline`（子任务 1.7）+ `fetch_error`（可选）。
  - 每日 `daily_results_profile*/YYYY-MM-DD_trade_log.csv`：与 gemini_ai 同构列，便于复用分析脚本。
- **硬要求**：纯影子，不参与任何下单/平仓决策。

#### 子任务 1.6 · 同分钟扫损聚类（Correlation Cluster）
- **动作**：`closeTime` 相差 ≤ 60s 且 `close_reason == SL` 的多笔 → 归为一个相关性事件，赋同一 `cluster_id`。
- **目的**：区分"零星止损"与"宏观事件批量扫损"（如 §0.4 的 `2026-11-03 19:12` 同分钟 5 笔 JPY 系扫损）。

#### 子任务 1.7 · Clean Baseline 切分
- **动作**：`closeTime >= 2026-11-18`（`_revise_owned_position` 关闭时点）之后的平仓 → 标记 `clean_baseline=true`；之前的标记 `false`。
- **目的**：L2 / Wide-range 反事实分析必须用 `clean_baseline=true` 的干净对照，不与持仓期改写（已关闭）的历史数据混算。

#### 子任务 1.8 · 对账校验（Reconciliation）
- **动作**：每日/每轮计算 `Σ realized_pl`（本地投影，OWNED + 聚合口径），与 OANDA 账户同窗口已实现 P&L 比对。
- **硬要求**：容差 = 0；不一致 → 记 `reconciliation_mismatch` 错误并告警。

#### 子任务 1.9 · Failure Resilience（"Never Raises"契约）
- **动作**：所有 OANDA 读取/解析逻辑包异常处理；任何失败 → 跳过该笔、记 `fetch_error` / `parse_error`，**绝不抛异常、绝不影响交易循环**。
- **参考**：照抄 `gemini_ai/utils/post_exit_context.py` 的"never raises"契约。

### 验收标准
- 连跑 1 天后，`exit_audit` 日志中 SL/TP/ACTIVE 计数与 P&L 分解，可与 OANDA 手工对账一致（容差 0）。
- `UNKNOWN` 占比 ≤ 20%；`incomplete` 占比 ≤ 5%。
- 部分平仓无重复计权；同分钟扫损可聚类识别；`clean_baseline` 切分正确。

### 影子四要素
- **反事实算法**：无（纯只读投影，不改变任何行为）。
- **有效性指标**：对账一致率 = 100%；`UNKNOWN` 占比 ≤ 20%；`incomplete` 占比 ≤ 5%。
- **失败条件**：连续两天对账不一致 **或** `UNKNOWN` 占比 > 20% → **暂停下游（TASK-2/TASK-3）分析，先修审计**。
- **下一步处置**：验收通过 → 解锁 TASK-2 / TASK-3 反事实分析；失败 → 回查 OANDA 读取与归因逻辑。

### 不做清单
- ❌ 不参与任何决策、不改变下单/平仓行为。
- ❌ 不落"第二套账本"（本地只是 OANDA 只读投影）。
- ❌ 不写任何 state 文件。
- ❌ 不把 `UNKNOWN` 并入 `ACTIVE`。

---

## TASK-2 · P1-A L2 风险定额仓位（两阶段 A→B，影子修正）
**优先级**：P1-A（P0 验收通过后启动）
**目标**：在**只缩不放大**前提下，验证"宽 SL = 尾部大亏"，量化削尾 vs 盈利同步缩小的代价。
**现状**：`utils/risk_parity_sizing.py` + `utils/analyze_sizing_shadow.py` 已落地影子（默认 `OPT_RISK_PARITY_SIZING=off`）；**当前仍为旧口径** `units_l2 = max(base, …)`（错误，会突破风险预算）。
**输入**：开仓候选时的 `size_units_prob` / `sl_price` / `current` / `atr_val` / `pip_cache[pair]` / `MIN_LOT`。
**输出**：`logs/sizing_shadow_YYYYMMDD.jsonl`（逐候选一行，`applied=False`）+ 反事实分析报告。
**Hook 点**：`fx_trade_bot_v685.py` —— `sl_price` 已算出、`tp_price` 之后、`all_candidates.append` 之前；`size_units` / `sl_price` / `current` / `atr_val` / `pip_cache[pair]` 均在作用域内。
**开关**：`OPT_RISK_PARITY_SIZING`（沿用 `_opt()` 约定：env > config > default；`off`=影子，`on`=生效）。

### 必做项（对照 §2.1 / §2.3 / §8.2）
| # | 事项 | 验收标准 |
|---|------|----------|
| 1 | **修 MIN_LOT 硬边界**：`units_raw = round(size_units_prob × rp_mult)`；`units_raw < MIN_LOT → would_reject=True`，**不抬到 MIN_LOT**；等价 `units_l2 = units_raw if units_raw ≥ MIN_LOT else None`（None=不下单） | 影子行含 `units_raw / below_min / would_reject` |
| 2 | 影子行补字段：`pip_value_usd` / 相关性净敞口（如 `JPY_net_units`，当前已持仓共同 base/quote 净敞口） | 供 L2-B 与组合级风险预算前置评估 |
| 3 | 分析器补 `rp_mult` **p10 / p50 / p90** + **触发率**（`rp_mult<1.0` 占比）+ 反事实尾部分位（SL USD p90/max、最深 25% 占比） | **禁止预设分布目标**（废弃原"p50≈1.0 & p90<0.6"，数学矛盾） |
| 4 | **L2-A 先做**：pip 口径 `rp_mult = clamp(rp_ref_pips / sl_pips_act, RP_F_LO=0.25, 1.0)`；`rp_ref_pips` 取 ATR 自参照（与 `fx_trade_bot_v685.py` L3128–3131 同式，**不新增全局常数**） | 反事实 SL p90/max 下降；EV 不显著恶化 |
| 5 | **L2-B 后做**（L2-A 有效后）：USD 定额 `units = clamp(round(R_usd / (sl_pips_act × pip_value_usd) × size_scale_prob), MIN_LOT规则, 上限=size_units_prob)` | 尾部下降 ≥ L2-A；消除 JPY 报价隐性偏差 |

### 影子行字段
`pair / direction / entry / sl_price / tp_price / sl_pips_act / ref_pips / pip_value_usd / units_prob / units_raw / units_l2 / rp_mult / below_min / would_reject / JPY_net_units(或对应) / applied=False`

### 影子四要素
- **反事实算法**：`SL_USD_l2 = units_l2 × sl_pips_act × pip_value_usd` vs 实际 SL 亏损，对比 p90/max/最深25%占比。
- **有效性指标**：①SL 亏损 USD p90/max 下降；②最深 25% 笔数占全部 SL 亏损比例下降；③净 EV 不显著恶化（唯一风险点：宽 SL 笔盈利同步缩小）。
- **失败条件**：L2-A 反事实 SL `p90/max` 无明显下降 **或** EV 显著恶化 → **停止 L2**，回头查 TASK-3（§3 宽幅震荡）。
- **下一步处置**：L2-A 有效 → 进 L2-B（USD 定额）；L2-B 达标 → 提交 Owner 评审是否转正（`OPT_RISK_PARITY_SIZING=on`）。

### 不做清单
- ❌ 不对"结构 SL < ATR 应然"放大（只缩不放大，保持风险预算封顶器单一职责）。
- ❌ 不与 TASK-3"要不要交易"合并（L2 是"交易多少"，属 Position Risk 层）。
- ❌ 不引入新全局常数（`ref` 取 ATR 自参照）。
- ❌ 影子阶段不真正拒绝候选（只记录 `would_reject`，`applied=False`）。

---

## TASK-3 · P1-B Wide-range 损失聚集研究（市场状态 × 交易行为 × 损失聚集）
**优先级**：P1-B（P0 验收通过后启动，与 TASK-2 并行）
**目标**：把 §3 从"宽幅识别"升级为"**市场状态 × 交易行为 × 损失聚集**"研究，回答"宽幅震荡危险的是单笔、还是频率"。
**现状**：影子层已实现（`utils/wide_range_sizing.py` + `WIDE_RANGE_SHADOW` hook，`applied=False`），判别量 `ATR_pct = 当日 ATR / 近 20 日 ATR 中位`，阈值 `narrow<0.8 / normal 0.8–1.3 / wide≥1.3`。**评审复核后**：主轴 `ATR_pct` 保持；`W_norm` **弃用**（实测 ∝1/ATR%、语义反向）；新增第二轴 `D_skew`（仅前向）。
**输入**：`wide_range_shadow`（按 `pair/day` 的 `tier`）+ `exit_audit`（TASK-1 产出的 OWNED 逐笔台账）。
**输出**：按 `tier` 分组的六项指标报告 + 处置方案反事实对比 + `logs/wide_range_shadow_YYYYMMDD.jsonl`（`applied=False`）。

### 必做项（对照 §3.2 / §3.3 / §8.3）
| # | 事项 | 验收标准 |
|---|------|----------|
| 1 | 把 `wide_range_shadow`（`pair/day/tier`）与 `exit_audit`（OWNED 逐笔）**按时间/pair 对齐 join** | 每笔平仓可标注其开仓时 `tier` |
| 2 | 统计 §3.2 **六项指标**（按 `tier` group-by）：①SL 命中率 ②连续 SL 游程（max/mean run）③双向 SL 事件（同 pair 时间窗 T 内先 BUY 后 SELL 均 SL）④净 P&L（聚合口径）⑤MFE/MAE ⑥**交易频率** | `wide` 在**多项**（尤其连续 SL、双向 SL、频率）显著区别于 `normal` |
| 3 | **交易频率**单列：单位时间开仓笔数 / 每 pair 每日笔数，按 `tier` 分组 | 判定"过度交易"是否为主因（若是，处置重点转向频率抑制/冷却而非单笔过滤） |
| 4 | 处置方案对比（**先影子、不改决策**）：阶梯降仓 `0.25x–0.5x`（Owner 已裁定默认）vs 频率抑制/冷却 vs 极端 `skip`（仅 `ATR_pct≥1.8` 或已出现连续双向扫损） | 给出反事实 P&L，供 Owner 拍板 |
| 5 | **第二轴 `D_skew`**（仅前向）：从 `distribution.quantiles["0.50"]` 取 `q50` → `D_skew = |q50 − P0| / (q95 − q05)`，与 `ATR_pct` 组成**双轴**分组；`q50` 仅 schema 1.2.0 起写入，历史不可回测 | `ATR_pct↑ & D_skew↓` 组的双向扫损/连续 SL 显著高于 `ATR_pct↑ & D_skew↑`（区分宽幅震荡 vs 高波单边趋势） |
| 6 | **MFE/MAE 归因**（never-raises · 离线）：按 `openTime→closeTime` 拉 M1/M5 K 线算逐笔 `mfe_pips / mae_pips / mfe_mae_ratio`；`whipsaw_flag` = 打了 SL **且** 平仓后 2h 内价格反向触达原 `tp_price` | `wide`/`D_skew↓` 分箱的 `mae` 放大、`whipsaw` 占比上升 |
| 7 | **`trade_id` 桥**：入场快照（`wide_range_shadow` 行）**必须带 `trade_id`**（下单返回后回填），作为与 `exit_audit`（主键 `(trade_id, closing_transaction_id)`）合并的唯一键 | 每笔特征可无损 join 到平仓事实 |

### 双轴判别（v1.0 复核后确立）
- 主轴 `ATR_pct`（波动率是否抬升）× 第二轴 `D_skew`（抬升后是否单边）：
  - `ATR_pct` 高 **且** `D_skew` 低 → **宽幅震荡（双向扫损）** = 本课题治理对象。
  - `ATR_pct` 高 **且** `D_skew` 高 → 更可能是**高波单边趋势** → 处置不同（不该降仓/不该 skip）。
- 两轴**分别可观测**，共同输入处置；**不合并成单一综合评分**。

### 影子四要素
- **反事实算法**：对 `wide` tier 时段分别模拟"阶梯降仓 0.25x/0.5x"、"频率抑制（冷却）"、"极端 skip"三种处置，对比实际 P&L 与反事实 P&L。
- **有效性指标**：`wide` tier 在六项指标（尤其连续 SL 游程、双向 SL、交易频率）上与 `normal` 有统计显著差异；处置反事实能降低净亏损而不过度牺牲盈利。
- **失败条件**：`wide` 时段在六项指标上与 `normal` 无显著差异 → 判别量（`ATR_pct`）无效，回退改特征（已实现波动分位 / BB 宽度分位）；`D_skew` 双轴无区分度 → 退回单轴 `ATR_pct`。
- **下一步处置**：判别有效 + 处置反事实达标 → 提交 Owner 评审是否上线阶梯降仓（`applied=True`）；判别无效 → 换特征重测。

### 不做清单
- ❌ **不**只验证 SL 命中率（宽幅震荡危险在损失聚集，非单笔命中率）。
- ❌ **不**默认 `skip`（Owner 已裁定 = 阶梯降仓 `0.25x–0.5x`，保留底仓；`skip` 仅极端兜底）。
- ❌ **不**与 L2/Exit 层合并成单一评分（§0.5 三层分离）。
- ❌ **不**采用 `W_norm`（§3.1 已证 ∝1/ATR%、语义反向、常数 3.29 不成立）。
- ❌ 不改任何决策（`applied` 恒 `False`）。

---

## 全局约束（所有 agent 必须遵守）
1. **本轮只落任务单与影子代码**，不上线任何影响下单/拒绝的逻辑（`applied` 恒 `False`）。
2. **P0 未完成前，TASK-2 / TASK-3 的反事实分析一律不得作为结论。**
3. 所有影子模块必须 `never raises`：任何失败 → 中性降级 + 记 error，**绝不影响交易循环**。
4. 所有开关沿用 `_opt()` 约定：env `OPT_XXX` > config > default；默认值必须是"影子/关闭"。
5. 不新增全局常数；能自参照（如 ATR）就自参照。
6. 保留所有原始日志与字段，只做**追加**（新增字段/文件），不做**覆盖/删除**。
7. `REVISE_OWNED_POSITION` 保持关闭；跟踪止损保持关闭（§7，P3 本轮不动）。
8. L1（SL↔TP 几何重构）/ L3（保本/分批止盈）/ §4（趋势追顶）均为 P2/P3 **暂缓**，本轮不碰。

---

## 交付物清单（本轮结束时应存在）
- [ ] TASK-1：`logs/exit_audit_*.jsonl` + 每日 `trade_log.csv` + 对账报告（含 `UNKNOWN` 占比、`reconciliation_mismatch` 计数、`cluster_id` 聚类统计、`clean_baseline` 切分）
- [ ] TASK-2：修正后的 `utils/risk_parity_sizing.py` + `utils/analyze_sizing_shadow.py` + `logs/sizing_shadow_*.jsonl` + L2-A 反事实报告（p10/p50/p90 + 触发率 + 尾部分位）
- [ ] TASK-3：`utils/wide_range_sizing.py`（补 `trade_id` 桥 + `D_skew` 前向采集）+ 六项指标分析报告 + 处置反事实对比
- [ ] 三份报告均标注：数据窗口、样本量、是否 clean_baseline、统计显著性

---

## 审查确认（Owner 签字后启动执行）
- [ ] Owner 确认任务单口径无误
- [ ] Owner 确认执行顺序（P0 先行，阻塞后续）
- [ ] Owner 确认"不写交易代码、不改决策逻辑"边界
- [ ] Owner 确认 P0 子任务拆分（1.1–1.9）无遗漏
