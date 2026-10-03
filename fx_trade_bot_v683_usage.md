# FX Trade Bot v6.8.3.3 — 使用文档（备查）

> Version: v6.8.3.3 PROFILE2 / PROFILE3 dual-account architecture
> Last updated: 2026-10-03
> Code refs: fx_trade_bot_v683.py · fx_trade_bot_utils.py · config_bot_profile{,_profile2.py · config_bot_profile3.py

---

## 0. 本次会话（2026-10-02）修复 & 新增总览

### Bug 修复（P0 级，已全部在 LIVE 实盘验证通过）

| # | 问题 | 根因 | 修复 |
|---|------|------|------|
| B1 | `tuple indices must be integers or slices, not str` 扫持仓必崩 | `get_open_position()` 返回 `(PositionStatus, dict)` 被直接当 dict 访问 | 正确解包 `status, pos = get_open_position(...)`，用 `status == PositionStatus.OPEN` 判断 |
| B2 | 下单后 TradeID 永远显示 `TradeID=?` | 主循环去取不存在的 `resp["orderFillTransaction"]["id"]，实际路径是 `resp["trade_id"]` | 按 status 分支读取 `status=="OK"` 才打印 `trade_id` |
| B3 | 被拒的订单日志显示 `✅ OANDA accepted order`（假成功），还占 MAX_OPEN 坑 | utils 中判拒前就打成功日志；主循环不管 status 一律 `✅ EXECUTED` 并 `entries_this_run++` | utils 先判 `orderRejectTransaction / orderCancel` 后判成功；主循环按 `status ∈ {OK, DRY_RUN} 才占坑；REDUCED / REJECTED / CANCELLED / ERROR 打原因附` → continue，不占坑 |
| B4 | crontab 激活行缺少 `--live`，永远 DRY-RUN 不开仓 | `LIVE_MODE = args.live`，默认 False；cron 行没加 `--live` 就永远不发单 | 手动修复 crontab（详见 §3 |

### 新增特性（P1 级，按 CONSERVATIVE 档 + 品种池差异化）

| # | 功能 | 说明 | 代码位置 |
|---|------|------|----------|
| F1 | **Pair Whitelist 互斥品种池（Ownership Tag） | P2 独占 AUD+JPY 组 5 对；P3 独占 EUR+GBP+CHF 组 3 对；并集=全部 8 对，交集=空，彻底杜绝「两账户同向双倍仓位 | `ALLOWED_PAIRS` in profile configs + fx_trade_bot_v683.py 评分循环 L986-L989 |
| F2 | **Whitelist Overlap 安全锁 | 启动时自动导入另一 profile 的 ALLOWED_PAIRS，若交集非空立刻 `logger.error` 打 `🚨 WHITELIST OVERLAP` | fx_trade_bot_v683.py#L490-L535 |
| F3 | **D-Gate 日线方向闸门（A/A/A） | D-EMA20 × D-EMA50 交叉定 LONG/SHORT/BOTH；2D 确认 + 0.2% 缓冲防 whipsaw；Phase 0 Shadow Mode（D_GATE_SHADOW=True 先观测 | fx_trade_bot_v683.py#L216-L331 |

---

## 1. 快速启动

### CLI 常用命令

```bash
# 1) Dry-run 安全验证（永远先跑这个）
python fx_trade_bot_v683.py --profile2 --dry-run
python fx_trade_bot_v683.py --profile3 --dry-run

# 2) LIVE 实盘（小仓位测试）
python fx_trade_bot_v683.py --profile2 --live --lots 1 --max-entries 1

# 3) 标准运行（1 单开 0.01 迷你手 + 本轮最多开 3 单
python fx_trade_bot_v683.py --profile2 --live --lots 1000 --max-entries 3
```

### CLI 参数一览

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--profile2 / --profile3` | — | 选其一，决定账户 / 账户 002 vs 账户 003 |
| `--live` | False | **不加这个永远 DRY-RUN （不会发单 |
| `--dry-run` | False | `--live 和 `--dry-run` 同给时 `--live` 胜，提示警告） |
| `--lots N` | `DEFAULT_LOT_SIZE=10000 | **OANDA 的 1 lot = 1 USD 名义价值（和 MT4 标准手）| 示例：--lots 1 ≈ $0.0001/pip；--lots 1000 ≈ $0.1/pip；--lots 10000 ≈ $1/pip |
| `--max-entries N` | unlimited（within MAX_OPEN） | 本轮运行最多开几单新单（和 MAX_OPEN 是总持仓限制并行） |
| `--timeframe` | 15m | 15m / H1 / H4 / D |
| `--confluence N` | off | 多周期共振层数（仅当 N=1 |
| `--mc-only` | off | 只做 MC 就退出，不交易） |
| `--skip-mc` | off | 跳过蒙特卡洛（加载上次24h 内旧缓存（开发/缓存不存在时加载，否则跳过所有需要最新结果 |

---

## 2. 安全参数（已统一 CONSERVATIVE 档，P2/P3 同步一致）

> 优先级：`args.*` CLI` → profile config → config_bot.py default`

| 参数 | 值（Conservative 档值 | 说明 |
|------|-------------------|------|
| `MIN_CONVICTION_SCORE` | 分以下 | 30 → **45.0** | 砍掉尾部边缘（排名最后的 20% 低分信号；评分门槛 |
| `MIN_SCORE_GAP` / `TOP_PAIRS_MIN_GAP | 0.25 → **0.50** | 币种强弱差距门槛；横盘强弱差距 0.50 才开仓，避免横盘反复被扫 SL |
| `MAX_OPEN_POSITIONS` | 4 → **3** | 最多同时持 3 单；降低同向集中风险 |
| `TRAIL_ATR_MULT`（动态追踪止损距离 | 1.5 → **2.0** | 强趋势下反对收紧 0.9x，主动放宽到 2.0，防 whipsaw |
| `MAX_HOLD_BARS`（15m 下） | 12（=3 小时）→ **48（=12 小时）** | 严格符合「持仓不足 3h 不要主动平仓」「宁挨 SL 扫不自己扫」哲学 |

**未变（保持默认）**：
- `ATR_SL_MULT = 2.0`（开仓 SL 最小 pips 下限：JPY=35p，其它=25p，不动）
- `SL_ZONE_BUFFER_PIPS = 25`（H4 Zone SL 缓冲不动）
- `DEFAULT_LOT_SIZE = 10000`（CLI --lots 覆盖建议 CLI

---

## 3. Crontab（OracleVM 生产配置：`crontab -e`）

```cron
# ──────────────────────────────────────────────────────────────────────────
# FX BOT v6.8.3 — Top-N Strength + 白名单互斥池 + D-Gate(观测
# ──────────────────────────────────────────────────────────────────────────
# P2（Account 002）亚系 AUD+JPY 组（5 对，Profile3（Account 003）欧系 EUR/镑系 CHF 组（3 对
# 注意：每次运行同一时刻，白名单不重叠。两 profile 的 `--lots` 可独立设置手数
# ──────────────────────────────────────────────────────────────────────────
# Profile2: minute=0,15,30,45 分 ±8 分抖动；--lots 1（$1 名义价值，按需要×10
# Profile3: minute=5,20,35,50 分 ±9 分抖动（与 P2 偏 5 分钟减少重叠低重叠
# ──────────────────────────────────────────────────────────────────────────
*/15 * * * 1-5 cd $HOME/projects/ai_training_cnn && /usr/local/bin/jitter-run.sh -m 8 -- /home/ubuntu/miniconda3/envs/ai-sprint/bin/python fx_trade_bot_v683.py --profile2 --live --lots 1 >> logs/bot_profile2.log 2>&1
#*/15 * * * 1-5 cd $HOME/projects/ai_training_cnn && /usr/local/bin/jitter-run.sh -m 9 -- /home/ubuntu/miniconda3/envs/ai-sprint/bin/python fx_trade_bot_v683.py --profile3 --live --lots 1 >> logs/bot_profile3.log 2>&1
```

**OANDA 手数对照（1 lot = 1 USD 名义价值）：

| `--lots` | 每 pip 盈亏（直盘约） |档位|
|-----------|--------------------|---|
| 1 | ≈ $0.0001 | 测试|
| 100 | ≈ $0.01 | 微|
| 1000 | ≈ $0.10 | 小仓|
| 10000 | ≈ $1.00 | 常规迷你|
| 100000 | ≈ $10.00 | 1 标准手|

---

## 4. Profile2 vs 4.3 差异对比

| 维度 | Profile2（Account 002）亚系 | Profile3（Account 003）欧系/镑系 | 是否真的 → 实 |
|------|---------------------------|----------------------------------|---------|
| OANDA 账号 | `OANDA_ACCOUNT_ID_2_LIVE` - 002） | `OANDA_ACCOUNT_ID_3_LIVE`（-003） | ✅ 真独立 |
| cooldown 文件 | `cooldown_profile2.json | `cooldown_profile3.json` | ✅ 独立 |
| results 目录 | `daily_results_profile2/` | `daily_results_profile3/` | ✅ 独立 |
| **白名单**（`ALLOWED_PAIRS） | **AUDUSD=X，AUDJPY=X，EURJPY=X，GBPJPY=X，USDJPY=X（5 对 亚系 | EURUSD=X，GBPUSD=X，USDCHF=X（3 对 | ✅ 完全互斥无重叠交集空）
| Smart TP 策略 | 2档自适应：MC≥75% →×2.0（否则 ×1.0（30p/60p | 固定 ×1.2（≈36p | ⚠️ 差异较小差异，但不足以 justify 双开 |
| 15m Trend Filter min_slope | 严格 0.001 | 宽松 0.0003（SLOPE_DIAG=True 开诊断） | ❌ 暂未生效（`TREND_FILTER_ENABLED=False） |
| `SLOPE_DIAG` 诊断 | 关 | 开 | 关 | 日志诊断仅日志 |
| 其余安全参数 | 完全一致 | 完全一致 | 权重 / 4 分 / 4 分 / 4 分 / 4 分
| 权重 | S=0.40 R=0.15 A=0.15 X=0.20 M=0.10 | 相同 | ✅ |
| TOP_N = 3，MAX_OPEN=3，完全一致相同 一致 | | ✅
| D-GATE 配置 | ENABLED=True+ SHADOW=True（Phase 观测 | 相同 ✅ 相同 |
| 权重 |

---

## 5. Pair Whitelist 系统（Ownership Tag）

### 设计目标

**为什么要它：

```P2/P3 同时跑同一时刻不因为同样信号各开 1 单 = 双双倍仓位不翻倍 + 双份保证金占 2 份保证完全白名单完全互斥的白名单从源头保证同一信号，确保任何货币同时开仓

### 配置

`config_bot_profile2.py L61-L71
```python
ALLOWED_PAIRS = ["AUDUSD=X，AUDJPY=X，EURJPY=X，GBPJPY=X，USDJPY=X"]
```

`config_bot_profile3.py L61-L69
```python
ALLOWED_PAIRS = ["EURUSD=X"，GBPUSD=X，USDCHF=X"]
```

### 安全锁（启动时自动检查）

fx_trade_bot_v683.py#L510-L531
启动时自动导入另一 profile 的 ALLOWED_PAIRS 交集 → 若交集非空立刻打 ERROR：
```
🚨 WHITELIST OVERLAP with config_bot_profile3! Shared pairs = ['EURUSD=X'] — doubles exposure. Fix ALLOWED_PAIRS.
```
如果交集为则成功功打印：
```
🔐 WHITELIST disjoint ✅ | overlap=0 | union covers 8 pairs vs 8 total available
```

### 运行时日志

放行：不在白名单时，主循环会跳过这一行：
```
🔒 GBPUSD=X：not in PROFILE2 ALLOWED_PAIRS — SKIP
```

---

## 6. D-Gate（D-Timeframe Direction 日线方向闸门

### 目的

根绝「几小时前卖 → 现在又买」flip-flop 问题：用 D 级EMAslow 交叉定方向，15m 只能顺着 D 方向开；反方向哪怕 15m 哪怕再强都 BLOCK。

### 参数（A/A/A 方案）

| 参数 | 值 | 说明 |
|------|----|------|
| EMA_FAST × EMA_SLOW | 20 × 50 | 经典双均线交叉（D 级别） | 标准趋势跟踪 |
| CONFIRM_BARS | 2 | 翻转缓冲：翻转需要连续 2 根 D 级别K 线 gap%） | 防一日游假突破 |
| MIN_BUFFER_PCT | 0.2% | 两根 EMA gap ≥0.2% 才算交叉幅度，窄幅震荡） | 防窄幅震荡内不锁方向 |

### 三态输出

| 态 | 意义 | 放行动 |
|---|---|---|
| `LONG` | 连续 2 根 D-K 线 `（EMA20 - EMA50)/EMA50 ≥ 都 ≥ 0.2% → 上升趋势 | 只允许 BUY 通过；SELL → 被拦下 |
| `SHORT` | 连续 2 根 < -0.2% → 下降趋势 | 只允许 SELL；BUY → 拦 |
| `BOTH` | 中性（缓冲带内 / 数据不够 / 混合 sign 不足 / 数据不足）→ 不锁方向 | 双向都放行（=不做） |

### Phase 工作流（记录≠执行→先证据链

| 阶段 | `D_GATE_ENABLED` `D_GATE_SHADOW` | 行为 |
|------|:-:|:-:|---|
| **Phase 0 观测（当前） | ✅ True | ✅ True | **反方向时打 SHADOW DIAG `would_block=YES`，**照常放行 → 统计 结果；**至少积累 20 条被记录实盘实际结果：**如果 ≥ 60% 被拦下的单都都** → ✅ 晋级 |
| **Phase 1 执行 | True | False | 真 `🚫 D-GATE ENFORCED BLOCK **方向反方向单 BLOCK，方向 | 真正拦 下 |

### 关键日志 grep 关键词

| 关键词 | 位置 | 含义 |
|--------|------|------|
| `🧭 D-GATE: SHADOW (log-only) | 启动时 | D-Gate 配置模式和 |
| `STEP 2.5 D-GATE — Daily Locks | main 启动 | D-GATE SUMMARY: LONG=0 SHORT=0 BOTH=8 | 每轮所有 8 对 D 方向统计 |
| `AUDUSD=X：LONG | Step2.5 打印每对方向明细 |
| `🧭 D-GATE: AUDUSD BUY ALLOWED (D-dir=LONG) | 评分后 | 15m 方向符合 D 闸门，通过 |
| **🧭 D-GATE SHADOW DIAG EURUSD: D-dir=SHORT 但 15m-wants BUY — would_block=YES | 评分后（**最关键的证据链行 | **Phase 0 阶段积累被 Shadow（**下这些单在真实结果真实

### 如何晋级（晋升 ENFORCED

```
# config_bot_profile2.py 改这一行：
D_GATE_SHADOW = False
```

---

## 7. 均线过滤器（默认关闭，随时可以启用

### 两道门

两道门过滤器 15m/H1 双门（1 门 EMA10 价格门 2 门 EMA10 斜率门

| 道门 | BUY 条件 | SELL 条件 | 配置 |
|------|---------|----------|------|
| 1 价格门 | `现价 > EMA10 | 现价 < EMA10 | P2 严格 min_slope=0.001（slope_lookback=5 根
| 2 斜率门 | EMA10 5 根K线相对涨幅 ≥ 0.1% | 跌幅 ≥ 0.1% | P3 宽松 min_slope=0.0003（诊断模式 SLOPE_DIAG 开） |

### Weekly EMA100 反趋势拦截

- 开仓价格在周线 EMA100 以下不追多；上方不追空。需要 `ema100_buffer_pips=30p 缓冲带

### 如何启用方法

```
# config_bot_profile2.py：
TREND_FILTER_ENABLED = True              # 开 15m 双门
WEEK_EMA100_FILTER_ENABLED = True        # 开周线大级别反趋势拦截
```

---

## 8. 开仓方向决策（3 票制）

3 个独立投票人同方向，≥2 票才放行，否则 SKIP。

| 投票人 | 怎么投票 |
|--------|---------|
| 1️⃣ Strength Gap（主导方向） | gap = `base Strength - quote Strength | gap ≥ MIN_STRENGTH_GAP(0.50 → BUY | gap ≤ -0.50 → SELL
| 2️⃣ XGB 模型 | `P_up概率 ≥ 0.55 → BUY；否则 SELL
| 3️⃣ MC 蒙特卡洛 15m | P_UP ≥ 55% → BUY；否则 SELL

**结果**

**所以 `XGB+MC22 都 SELL，哪怕 Strength=BUY，依然 2:1 → BUY（你日志里每对都显示 `XGB=SELL 但 2:1 依然通过）。

---

## 9. Position Management 持仓后 SL 管理

### 开仓 SL（初始止损）

默认走 Zone-based（）**SL_USE_ZONE_HIERARCHY=True）
1. H4 级别找最近 swing low/high swing high low 区间极值 ±25p 缓冲 → SL。如果过小触发
2. floor 跌破 floor（JPY 35p 其它 25p）SL if ＜ floor ）

### 持仓后移动 SL（DynamicPositionManager，所有 profile 相同统一逻辑一样统一：
- BE_TRIGGER_ATR_MULT=1.5 → 利润达 1.5×ATR 上到 BE+0 → `BE 保本
- 之后 TRAIL_TRIGGER_ATR_MULT=2.5 → 利润达 2.5×ATR → 开始 1.5×ATR 追踪（放宽到 2.0×ATR 安全档）

---

## 10. Evidence Chain 诊断命令速查

| 要分析 | 目的 | grep /grep 关键字
|--------|------|--------|
| 确认 D-Gate 有多少信号拦了多少单 | `grep "would_block=YES" logs/bot_profile2.log \| wc -l`
| |查看有被拦下的都 hit/miss 率
| 白名单有多少非池中 | grep "not in.*ALLOWED_PAIRS — SKIP" | log 数一下哪些被拦了多少非白名单 | grep "🔒.*ALLOWED_PAIRS.*SKIP"
| 开仓失败详细 | `grep "✅ EXECUTED\|❌ ORDER FAILED\|REJECTED"` | 订单状态成功/失败
| 最近一次运行 summary | 每次结束打 run_summary 日志文件.log "v6.8.3.3.*Run Complete
| WL 有多少持仓 | grep "📊 Open positions.*MAX_OPEN"

---

## 11. 同步 OracleVM 同步文件命令备忘

```bash
# 本机 → OracleVM：
# 本机（每次改完 4 个文件同步
rsync -av fx_trade_bot_v683.py \
  fx_trade_bot_utils.py \
  config_bot_profile2.py \
  config_bot_profile3.py \
  ubuntu@oraclevm:~/projects/ai_training_cnn/
```