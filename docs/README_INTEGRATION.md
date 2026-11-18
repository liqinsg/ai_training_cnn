# 集成说明 · Exit Risk 影子模块（2026-11-18）
> 基线：`docs/NEXT_DEV_PLAN_20261117.md` v1.0 + `TASK_BRIEF_FINAL_20261118.md`
> **全部为影子模式（applied=False），不改任何下单/决策逻辑，never raises。**

---

## 文件清单与放置位置
| 文件 | 放到项目 | 作用 |
|------|----------|------|
| `exit_audit_foundation.py` | `utils/` | P0 只读平仓审计（三态归因/去重/部分平仓/聚类/对账） |
| `analyze_exit_audit.py` | `utils/` | P0 对账与分析报告 |
| `risk_parity_sizing.py` | `utils/`（替换/覆盖现有） | P1-A L2 风险定额（修正 MIN_LOT 硬边界） |
| `analyze_sizing_shadow.py` | `utils/` | P1-A L2 反事实分析（p10/p50/p90+触发率+尾部） |
| `wide_range_sizing.py` | `utils/`（替换/覆盖现有） | P1-B Wide-range（补 trade_id 桥 + D_skew） |
| `analyze_wide_range.py` | `utils/` | P1-B 六项指标分析（SL命中率/连续SL/双向SL/频率等） |

---

## 集成点（主循环加调用，不改决策）

### 1. P0 Exit Audit（每周期调用一次）
```python
# fx_trade_bot_v685.py 主循环末尾（或独立 cron）
from utils.exit_audit_foundation import run_exit_audit
run_exit_audit(oanda_api, profile_tag="YOUR_CLIENT_EXT_TAG")  # never raises，失败自动降级
```
输出：`logs/exit_audit_YYYYMMDD.jsonl` + `daily_results_profile*/YYYY-MM-DD_trade_log.csv`

### 2. P1-A L2 风险定额（Hook：sl_price 已算出、tp_price 之后、all_candidates.append 之前）
```python
from utils.risk_parity_sizing import compute_risk_parity, log_sizing_shadow, apply_if_enabled
result = compute_risk_parity(
    pair=pair, direction=direction, size_units_prob=size_units,
    sl_price=sl_price, current_price=current, atr_val=atr_val,
    pip=pip_cache[pair], min_lot=MIN_LOT,
    pip_value_usd=pip_value_usd,  # 可选，供 L2-B
    jpy_net_units=jpy_net_units,  # 可选，相关性敞口
)
log_sizing_shadow(result)  # 影子：不改 size_units
# 转正（OPT_RISK_PARITY_SIZING=on）时才启用：
# decision = apply_if_enabled(result, enabled=OPT_RISK_PARITY_SIZING)
# if decision["rejected"]: 跳过该候选
# else: size_units = decision["size_units"]
```
输出：`logs/sizing_shadow_YYYYMMDD.jsonl`

### 3. P1-B Wide-range（Hook：L2 之后、候选入选前，逐候选写影子）
```python
from utils.wide_range_sizing import compute_atr_ratio, classify_tier, compute_d_skew, log_wide_range_shadow, WideRangeShadow
atr_info = compute_atr_ratio(daily_candles_complete)  # 仅 complete 已收线日线
tier = classify_tier(atr_info["atr_pct"])
d_skew = compute_d_skew(mc_snapshot, current_price)  # 可选，仅前向
record = WideRangeShadow(
    profile=profile, pair=pair, oanda=account, direction=direction,
    atr_pct=atr_info["atr_pct"], atr_current=atr_info["atr_current"],
    atr_median=atr_info["atr_median"], tier=tier, n_points=atr_info["n_points"],
    d_skew=d_skew, d_skew_available=(d_skew is not None),
    client_order_id=client_order_id,  # 下单后回填 trade_id 用
)
log_wide_range_shadow(record)  # 影子：applied=False，不改决策
# 下单返回后：update_trade_id("logs", client_order_id, trade_id)
```
输出：`logs/wide_range_shadow_YYYYMMDD.jsonl`

---

## 开关（沿用 _opt() 约定：env > config > default，默认影子/关闭）
| 开关 | 默认 | 说明 |
|------|------|------|
| `OPT_RISK_PARITY_SIZING` | off（影子） | on = 生效（would_reject 时拒绝候选） |
| `OPT_WIDE_RANGE_SHADOW` | on（仅落盘） | 0 = 关闭影子 |
| `REVISE_OWNED_POSITION` | **保持关闭** | 跟踪止损（P3，本轮不动） |

---

## 分析报告生成（影子数据积累后）
```bash
# P0 对账报告
python utils/analyze_exit_audit.py --log-dir logs --out reports/exit_audit.json

# P1-A L2 反事实（rp_mult p10/p50/p90 + 触发率 + 尾部削减）
python utils/analyze_sizing_shadow.py --log-dir logs --out reports/l2_counterfactual.json

# P1-B Wide-range 六项指标（需 P0 先产出 exit_audit）
python utils/analyze_wide_range.py --log-dir logs --out reports/wide_range.json
```

---

## 验收流程（严格按顺序）
1. **P0 先行**：连跑 ≥1 天，`analyze_exit_audit` 显示 UNKNOWN≤20%、incomplete≤5%、对账无 mismatch → 验收通过。
2. **P0 未通过前，L2 / Wide-range 反事实分析不得作为结论。**
3. P1-A：积累 sizing_shadow 数据，`analyze_sizing_shadow` 输出 p90 下降 >10% 且 EV 不恶化 → L2-A 有效，进 L2-B；否则停止 L2，回头查 Wide-range。
4. P1-B：`analyze_wide_range` 显示 wide tier 在连续 SL/双向 SL/交易频率上显著区别于 normal → 判别有效，提交 Owner 评审阶梯降仓上线；否则回退改特征。

---

## 注意事项
- 所有模块 `never raises`：任何失败 → 中性降级 + 记 error，**绝不影响交易循环**。
- 只做**追加**（新增字段/文件），不做**覆盖/删除**现有日志与代码。
- 不新增全局常数；能自参照（ATR）就自参照。
- L1（SL/TP 几何）/ L3（保本/分批止盈）/ §4（趋势追顶）均为 P2/P3 **暂缓**，本轮不碰。
- 三层分离：Market Risk（wide_range）/ Position Risk（L2）/ Exit Risk（P3）各自独立，**禁止合并成单一评分**。
