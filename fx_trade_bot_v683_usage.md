# FX Trade Bot v6.8.3.4 — 使用文档（备查，Gemini 审订版 Policy Document）

> Version: v6.8.3.4 (v6.8.3.3 → v6.8.3.4 → Gemini-audit policy lock-in)
> Update: 2026-10-03
> Code refs: fx_trade_bot_v683.py · fx_trade_bot_utils.py · sl_zone_hierarchy.py · config_bot_profile2.py · config_bot_profile3.py

---

## 0. 状态标签规范（Gemini 审计强制要求：四类标签，不准模糊）

> Core principle（权威规范）：
> **Broker state authoritative（券商端真实状态为唯一事实依据）**。
> 任何行为变更必须按以下四类显式标注 — 禁止将实际改变实盘分布的代码改动说成“不影响行为”。

| 标签 | 颜色 | 含义 |
|------|:----:|------|
| ✅ **LIVE / VERIFIED** | GREEN | 已在实盘或 dry-run 中真实验证过的、稳定的行为/机制 |
| 🟡 **LIVE BEHAVIOR CHANGED** | YELLOW | **本次上线实际改变了实盘 exit / entry 分布的行为变更**（必须披露！） |
| 🔵 **SHADOW ONLY** | BLUE | Phase-0 影子模式：**只打诊断日志，完全不改变任何交易决策或手数** |
| ⚪ **DESIGN ONLY** | GREY | 路线图、规划、未来架构想法。**代码库里没有任何实现，当前版本零影响** |

### ⚠️ 🔒 MC STRONG THRESHOLD — Authoritative Lock-in（杜绝 62.5% vs 75% 再口误）

代码（实盘逻辑）和文档（所有叙述）统一锁定为 **62.5%**：
- 代码配置：`_TREND_TP_CONFIG["mc_strong_threshold"] = 0.625`
- 数学定义：`mc_pct_up ≥ 62.5%` 即 `|P_up - 0.50| ≥ 12.5%`（MC 单边偏置超过 1/8） → STRONG ×2 TP
- **禁止任何文档、注释、交付总结再出现「75%」字样，出现即视为文档和代码偏离，必须立刻修正。**

---

## 1. 本次会话（2026-10-02/03）修复 & 新增总览

### Bug 修复（✅ LIVE / VERIFIED，已全部在 LIVE 实盘验证通过）

| # | 问题 | 根因 | 修复 |
|---|------|------|------|
| B1 | `tuple indices must be integers or slices, not str` 扫持仓必崩 | `get_open_position()` 返回 `(PositionStatus, dict)` 被直接当 dict 访问 | 正确解包 `status, pos = get_open_position(...)`，用 `status == PositionStatus.OPEN` 判断 |
| B2 | 下单后 TradeID 永远显示 `TradeID=?` | 主循环去取不存在的 `resp["orderFillTransaction"]["id"]`，实际路径是 `resp["trade_id"]` | 按 status 分支读取，仅 `status=="OK"` 才打印 `trade_id` |
| B3 | 被拒的订单日志显示 `✅ OANDA accepted order`（假成功），还占 MAX_OPEN 坑 | utils 中判拒前就打成功日志；主循环不管 status 一律 `✅ EXECUTED` 并 `entries_this_run++` | utils 先判 `orderRejectTransaction / orderCancel` 后判成功；主循环仅当 `status ∈ {OK, DRY_RUN}` 才占坑；REJECTED/CANCELLED/REDUCED/ERROR 打原因后 continue，不占坑，允许候补替补 |
| B4 | crontab 激活行缺少 `--live`，永远 DRY-RUN 不开仓 | `LIVE_MODE = args.live` 默认 False；开仓门控绑在 `LIVE_MODE` 上，cron 行没加 `--live` 就永远不发单；`run.env` 的 `DRY_RUN` 从未被读取 | v6.8.3.6：开仓门控改读 `DRY_RUN`（CLI `--dry-run/--no-dry-run` > `run.env DRY_RUN` > 默认 true），`--live` 只管账户环境；新增 `🚦 EXECUTION GATE` 启动日志 |

### 新增 & 改进特性（v6.8.3.4 Gemini-audit locked）

| # | 功能 | 状态标签 | 说明 | 代码位置 |
|---|------|:--------:|------|----------|
| F1 | Pair Whitelist 互斥品种池（Universe Buckets, 4:4） | ✅ LIVE / VERIFIED | **P2 = JPY 纯交叉桶 4 对**（AUDJPY / EURJPY / GBPJPY / USDJPY）；**P3 = G8 Majors 桶 4 对**（AUDUSD / EURUSD / GBPUSD / USDCHF）；并集=8 对全覆盖，交集=空，杜绝「两账户同向双倍仓位」 | [ALLOWED_PAIRS (P2)](file:///home/qili/projects/ai_training_cnn/config_bot_profile2.py#L69-L82) / [ALLOWED_PAIRS (P3)](file:///home/qili/projects/ai_training_cnn/config_bot_profile3.py#L69-L82) + [主循环过滤](file:///home/qili/projects/ai_training_cnn/fx_trade_bot_v683.py#L986-L989) |
| F2 | Whitelist Overlap 安全锁（Level-0 Universe Safety Guard） | ✅ LIVE / VERIFIED | 启动时自动导入另一 profile 的 ALLOWED_PAIRS，若交集非空立刻 ERROR 打 `🚨 WHITELIST OVERLAP` | [fx_trade_bot_v683.py#L490-L535](file:///home/qili/projects/ai_training_cnn/fx_trade_bot_v683.py#L490-L535) |
| F3 | D-Gate 日线方向闸门（A/A/A） | ✅ LIVE / VERIFIED（Phase-0 SHADOW ONLY 子模式） | D-EMA20 × D-EMA50 交叉定 LONG/SHORT/BOTH；2D 确认 + 0.2% 缓冲防 whipsaw；**当前 SHADOW 只打 would_block 日志不拦截** | [fx_trade_bot_v683.py#L216-L331](file:///home/qili/projects/ai_training_cnn/fx_trade_bot_v683.py#L216-L331) |
| F4 | Per-Pair SL Floor Override（GBPJPY） | 🟡 **LIVE BEHAVIOR CHANGED 1** | GBPJPY（120-150p/d 高 ATR）单独把 SL floor 从 20/35p → **50p**，直接改变 GBPJPY 的开仓 SL 距离分布，防止自然摆动被意外扫 | [override 机制](file:///home/qili/projects/ai_training_cnn/sl_zone_hierarchy.py#L7-L28) + [P2 配置](file:///home/qili/projects/ai_training_cnn/config_bot_profile2.py#L84-L91) |
| F5 | P3 Smart TP 从静态 ×1.2 改为与 P2 完全一致的 MC 自适应 | 🟡 **LIVE BEHAVIOR CHANGED 2** | 原 P3 固定 TP ×1.2 ≈ 36p；现统一为 **MC 62.5% 切换阈值：NORMAL 30p(×1) / STRONG 60p(×2)**。直接改变 P3 的 exit 分布，目的是保持 A/B 测试基准一致（策略参数统一 → PnL 差异只能来自 Universe） | [_TREND_TP_CONFIG 🔒locked](file:///home/qili/projects/ai_training_cnn/fx_trade_bot_v683.py#L109-L146) + [TP 分支统一](file:///home/qili/projects/ai_training_cnn/fx_trade_bot_v683.py#L427-L446) |
| F6 | 2:1 Dynamic Sizing Phase-0（含 Disagreed Voter 精确归因） | 🔵 **SHADOW ONLY** | 3:0 unanimous → 满手数；2:1 分票 → 打诊断日志 `would_halve=True`，**附带异议投票人（Strength / XGB / MC）精确归因**，不真改手数。攒 20+ 样本后再判定 | [诊断插入点](file:///home/qili/projects/ai_training_cnn/fx_trade_bot_v683.py#L847-L883) |
| F7 | Portfolio Observer（只读）规划 | ⚪ **DESIGN ONLY** | 规划中、未实现；未来**只读 OANDA API 真实持仓**做组合层诊断，永远不做 Execution Gate（禁止引入 portfolio_state.json 文件锁 / race condition） | 见 §13 |
| F8 | Level-1 Allocation Controller（跨账户 TOTAL_MAX_OPEN 动态额度） | ⚪ **DESIGN ONLY** | 规划中、未实现；先靠 §4 Crontab 的方案 B（CLI --max-entries 2+2）做物理限制 | 见 §13 |
| F9 | Level-2 Portfolio Intel（主题聚类 / 相关性感知） | ⚪ **DESIGN ONLY** | 远期规划，无代码 | 见 §13 |

---

## 2. 快速启动

### CLI 常用命令

```bash
# 0) Demo 账户真实开仓（run.env: DRY_RUN=false，无需 --live；启动看 🚦 EXECUTION GATE 确认来源）
python fx_trade_bot_v683.py --profile2 -p 3

# 1) Dry-run 安全验证（每次改完先跑这个，确认白名单/overlap 锁/D-Gate banner）
python fx_trade_bot_v683.py --profile2 --dry-run
python fx_trade_bot_v683.py --profile3 --dry-run

# 2) LIVE 实盘（小仓位测试档）
python fx_trade_bot_v683.py --profile2 --live --lots 1 --max-entries 1

# 3) 标准运行（1 单 = 1000 units ≈ $0.1/pip；本轮最多开 3 单）
python fx_trade_bot_v683.py --profile2 --live --lots 1000 --max-entries 3
```

### CLI 参数一览

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--profile2 / --profile3` | — | 选其一，决定 **Universe Bucket**（P2=JPY 桶 / P3=Majors 桶）+ **OANDA 账户（-002 / -003）** + 独立 cooldown/results |
| `--live` | False | 只决定**连哪个账户环境**（False=Practice/Demo，True=LIVE 实盘）；**不再控制是否发单**（v6.8.3.6 起） |
| `--dry-run / --no-dry-run` | 不加 = 读 `run.env` 的 `DRY_RUN`（默认 true） | 执行门控。优先级：CLI > `run.env DRY_RUN` > 默认 true。`--dry-run` 强制不发单，`--no-dry-run` 强制发单。启动时看 `🚦 EXECUTION GATE` 行确认来源 |
| `--lots N` | `DEFAULT_LOT_SIZE=10000` | **OANDA 的 1 lot = 1 USD 名义价值（和 MT4 标准手完全不同！）**。对照见 §4 表 |
| `--max-entries N` | unlimited（within MAX_OPEN） | 本轮运行最多新开几单（和 `MAX_OPEN_POSITIONS`「总持仓上限」并行）。**§4 方案 B 用这个把两桶并发上限压到 2+2=4** |
| `--timeframe` | 15m | 15m / H1 / H4 / D |
| `--mc-only` | off | 只跑 MC 不交易（开发用） |
| `--skip-mc` | off | 跳过蒙特卡洛，加载 24h 内旧缓存（仅当缓存存在时） |

---

## 3. 安全参数（Conservative 档，P2/P3 完全一致）

> **优先级链（硬约定）**：`args.*`（CLI）> `config_bot_profile{2,3}.py` > `config_bot.py` default

| 参数 | Conservative 档值 | 调整原因（Conservative vs 旧档） |
|------|------------------|--------------------------------|
| `MIN_CONVICTION_SCORE` | **45.0**（旧 30） | 砍掉尾部 20% 低确信度噪声信号（Sharpe 提升最有效手段，Gemini 评为「极其正确」） |
| `MIN_SCORE_GAP / TOP_PAIRS_MIN_GAP` | **0.50**（旧 0.25） | 币种强弱差门槛翻倍；横盘无方向时不开仓，减少区间震荡中的 whipsaw |
| `MAX_OPEN_POSITIONS` | **3**（旧 4） | 单 bucket 内最多 3 单，降低同向集中风险（两桶并发上限靠 §4 Crontab 方案 B 做 2+2=4 物理限制） |
| `TRAIL_ATR_MULT` | **2.0**（旧 1.5） | 外汇 15m 噪声极大，1.5×ATR 追踪容易「扫了之后行情继续」；2.0 给盈利单足够呼吸空间（Gemini：非常贴合外汇特性） |
| `MAX_HOLD_BARS`（15m 下） | **48 根 = 12h**（旧 12 根 = 3h） | 严格遵循用户哲学：「宁愿被 SL 扫也不要频频被自己扫出局」；12h 覆盖日内趋势的典型寿命 |

**保持不变（不参与调参）**：
- `ATR_SL_MULT = 2.0`（开仓 ATR SL 倍数）
- `SL_BUFFER_PIPS = 25`（Zone SL 极值点缓冲）
- `SL_MIN_DISTANCE_PIPS = 20` / `SL_FALLBACK_FIXED_PIPS = 35`（默认全局 floor；高波动品种用 §6 F4 单品种 override 机制）

---

## 4. Crontab（OracleVM 生产配置：`crontab -e`）

### 架构背景（Gemini 澄清）

- **Execution-Safe（执行安全）** ✅：白名单彻底隔离，不可能出现同一 pair 双倍下注
- **Portfolio-Safe（组合安全）** ⚠️：P2 MAX_OPEN=3 + P3 MAX_OPEN=3 = **理论极限 6 单 > 全局 4 单风险上限**，所以提供两套方案

```cron
# ──────────────────────────────────────────────────────────────────────────
# FX BOT v6.8.3.4 — Top-N Strength + Universe Buckets(4:4) + D-Gate(SHADOW)
# ──────────────────────────────────────────────────────────────────────────
# P2  (Account 002) = JPY Bucket     (4 pairs: AUDJPY, EURJPY, GBPJPY, USDJPY)
# P3  (Account 003) = Majors Bucket  (4 pairs: AUDUSD, EURUSD, GBPUSD, USDCHF)
# ──────────────────────────────────────────────────────────────────────────
# 时间错峰：P2 每 15m 整 ±8 分抖动；P3 比 P2 偏 5 分钟 ±9 分抖动
# ──────────────────────────────────────────────────────────────────────────
#
# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  SCHEME A (推荐下周先跑): P2 ONLY — 最稳健                           ║
# ║  只开 P2，先集中收集 JPY Bucket 的 D-Gate + Sizing 证据链              ║
# ║  Portfolio-Safe: P2 上限 3 单，不突破全局 4 ceiling                   ║
# ╚══════════════════════════════════════════════════════════════════════════╝
*/15 * * * 1-5 cd $HOME/projects/ai_training_cnn && /usr/local/bin/jitter-run.sh -m 8 -- /home/ubuntu/miniconda3/envs/ai-sprint/bin/python fx_trade_bot_v683.py --profile2 --live --lots 1 --max-entries 2 >> logs/bot_profile2.log 2>&1

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  SCHEME B: P2 + P3 A/B TEST（要同时跑时启用）                          ║
# ║  CLI --max-entries 2 + 2 = 4 物理 enforce 全局 4 ceiling               ║
# ║  （Level-1 总控还没做，先用这个做物理限制）                              ║
# ╚══════════════════════════════════════════════════════════════════════════╝
# Scheme B-P2（取消下一行注释时注释掉 Scheme A 的 P2 行）：
#*/15 * * * 1-5 cd $HOME/projects/ai_training_cnn && /usr/local/bin/jitter-run.sh -m 8 -- /home/ubuntu/miniconda3/envs/ai-sprint/bin/python fx_trade_bot_v683.py --profile2 --live --lots 1 --max-entries 2 >> logs/bot_profile2.log 2>&1
# Scheme B-P3（取消注释即启用）：
#*/15 * * * 1-5 cd $HOME/projects/ai_training_cnn && /usr/local/bin/jitter-run.sh -m 9 -- /home/ubuntu/miniconda3/envs/ai-sprint/bin/python fx_trade_bot_v683.py --profile3 --live --lots 1 --max-entries 2 >> logs/bot_profile3.log 2>&1
```

### OANDA 手数对照表（核心认知：1 lot = 1 USD 名义价值）

| `--lots` | 每 pip 盈亏（直盘约） | 档位 |
|-----------|--------------------|------|
| 1 | ≈ $0.0001 | 测试档（安全白给） |
| 100 | ≈ $0.01 | 微型 |
| 1000 | ≈ $0.10 | 小仓（日常推荐） |
| 10000 | ≈ $1.00 | 常规迷你（≈MT4 0.01 手） |
| 100000 | ≈ $10.00 | ≈ MT4 0.1 标准手 |

---

## 5. Profile2 vs Profile3 差异对比（v6.8.3.4 — Gemini 澄清版 Uniformity）

> **架构定义一句话（ChatGPT P0 推荐 + Gemini 审订确认）**：
> **P2/P3 不是两个互相竞争的独立策略，而是两个拥有独立品种池（Universe Bucket）和 OANDA 账户的「执行单元 (Execution Unit)」。**
>
> Gemini 精确措辞（避免“100% 统一”的夸大）：
> **Core strategy parameters are identical across P2/P3; pair-specific risk overrides may exist where justified by instrument volatility.**
> （核心策略逻辑、预测模型、过滤器、TP 完全一致；允许针对特定品种波动率存在个别风控兜底覆盖，如 GBPJPY 50p floor — 这属于 pair-specific risk cap，不算「策略分歧」。）

| 维度 | Profile2 (Bucket: JPY Crosses) | Profile3 (Bucket: G8 Majors) | 是否差异 |
|------|:-----------------------------:|:---------------------------:|:--------:|
| **Universe（所有权，硬不变量）** | AUDJPY、EURJPY、**GBPJPY**、USDJPY（4 对，全部含 JPY） | AUDUSD、EURUSD、GBPUSD、USDCHF（4 对，纯 Major vs USD） | ✅ **唯一真正差异** |
| OANDA 账户 | -002 (Live/Practice) | -003 (Live/Practice) | ✅ 真独立 |
| 冷却文件 / 结果目录 | `cooldown_profile2.json` / `daily_results_profile2/` | `cooldown_profile3.json` / `daily_results_profile3/` | ✅ 真独立 |
| **权重 S=0.40 R=0.15 A=0.15 X=0.20 M=0.10** | ✅ 一致 | ✅ 一致 | ❌ 相同 |
| Conservative 安全参数（5 项） | ✅ 一致 | ✅ 一致 | ❌ 相同 |
| **Smart TP（🔒 MC 62.5% 阈值统一切换）** | NORMAL MC<62.5% → ×1（30p）；STRONG MC≥62.5% → ×2（60p） | （原静态 ×1.2 → 现与 P2 完全相同：NORMAL 30p / STRONG 60p，🔒62.5% 阈值） | ❌ **现已相同**（🟡 LIVE BEHAVIOR CHANGED 2） |
| D-Gate（Phase-0 SHADOW + A/A/A） | ✅ 一致 | ✅ 一致 | ❌ 相同 |
| TOP_N / MAX_OPEN / MAX_HOLD_BARS | TOP3 / MAX3 / 48bars | TOP3 / MAX3 / 48bars | ❌ 相同 |
| Per-Pair SL Override（🟡 LIVE BEHAVIOR CHANGED 1） | `GBPJPY=X → 50p`（GBPJPY 大波动补偿，实盘 SL 分布已改变） | `{}`（空 dict，波动率匹配默认 20/35p floor） | ⚠️ 小差异（pair-specific risk cap，跟随 universe，不属于策略分歧） |

---

## 6. Pair Whitelist 系统（Universe Ownership Layer）

### 设计动机（为什么从 5:3 → 4:4，用户明确指令 + ChatGPT 架构评审）

```
旧划分 5:3（P2=AUD+JPY 5 对 / P3=欧系 3 对）的问题：
  AUDUSD 在 P2，AUDJPY 也在 P2 → P2 暴露了 AUD 单币 + JPY 双主题，
  而 P3 只有 EUR/GBP/CHF 3 个 Major，两桶主题不对称。

新划分 4:4（用户指令）：
  P2 = 所有 JPY 交叉盘（主题纯粹 = 「押注 JPY 的强弱」）
  P3 = 所有 G8 Major 直盘对 USD（主题纯粹 = 「押注各 Major 独立 vs USD」）
  → 两桶主题对称，4 对 vs 4 对，容量/地位均等，更利于 Portfolio-level 分配。
```

### 配置（所有权硬不变量）

P2 (JPY Bucket) — [config_bot_profile2.py#L69-L82](file:///home/qili/projects/ai_training_cnn/config_bot_profile2.py#L69-L82)：
```python
ALLOWED_PAIRS = ["AUDJPY=X","EURJPY=X","GBPJPY=X","USDJPY=X"]
```

P3 (Majors Bucket) — [config_bot_profile3.py#L69-L82](file:///home/qili/projects/ai_training_cnn/config_bot_profile3.py#L69-L82)：
```python
ALLOWED_PAIRS = ["AUDUSD=X","EURUSD=X","GBPUSD=X","USDCHF=X"]
```

### 启动时 Overlap 安全锁（Level-0 Universe Safety Guard）

[fx_trade_bot_v683.py#L490-L535](file:///home/qili/projects/ai_training_cnn/fx_trade_bot_v683.py#L490-L535)

启动时自动 import 另一 profile module，取它的 `ALLOWED_PAIRS` 求交集：

- 交集非空 → **ERROR 级 `🚨 WHITELIST OVERLAP`**（例如有人未来把 GBPUSD 同时加到 P2，立刻发现）。
- 交集为空 → INFO 级 `🔐 WHITELIST disjoint ✅ | overlap=0 | union covers 8 pairs vs 8 total available`。

**启动 dry-run 必须看到 disjoint ✅ 行，否则不要开 LIVE！**

### 运行时日志（grep 用）

不在白名单的 pair 会被主循环硬跳过：
```
🔒 GBPUSD=X: not in PROFILE2 ALLOWED_PAIRS — SKIP
```

---

## 7. Per-Pair SL Floor Override（F4，🟡 LIVE BEHAVIOR CHANGED 1）

### 背景问题

全局统一 `SL_MIN_DISTANCE_PIPS=20`（Zone floor）+ `SL_FALLBACK_FIXED_PIPS=35`（硬兜底）对不同波动率的 pair **是错配的**：
- AUDUSD / USDCHF 日均 ATR 50-70p → 35p 兜底 ≈ 0.5ATR ✓ 合理
- **GBPJPY 日均 ATR 120-150p** → 35p 兜底仅 ≈ 0.25ATR → ❌ 常规日内回摆就被意外扫 SL

### 解决机制（通用 per-pair dict，方便未来扩展）

在 `compute_sl_zone()` 里读取 `SL_PAIR_FLOOR_OVERRIDES: dict[str, int]`（profile 级配置）：
- 如果 pair 在 dict 里 → 用配置值同时覆盖 `MIN_DIST_PIPS`（Zone floor）和 `FIXED_PIPS`（硬兜底最后防线）。
- 打一行 `📏 PAIR-SPECIFIC FLOOR: GBPJPY=X → MIN_DIST_PIPS=50 (vol-matched override applied)` 可审计。

**当前生效 override（v6.8.3.4）**：

| Pair | 覆盖值 | 原因 | 配置位置 |
|------|:------:|------|---------|
| GBPJPY=X | **50 pips**（默认 20→50 Zone floor / 35→50 Fixed） | 波动率 2× 于 AUDUSD，给自然波动留空间 | [config_bot_profile2.py#L84-L91](file:///home/qili/projects/ai_training_cnn/config_bot_profile2.py#L84-L91) |

未来要加新 pair 很简单：比如 EURJPY 也想 45p，就把 P2 的 dict 加 `"EURJPY=X": 45`。

---

## 8. D-Gate（D-Timeframe Direction Gate，日线方向闸门）

### 解决的问题

根治「几小时前卖 → 现在又买」的 15m flip-flop：用 **D 级别** EMA 交叉锁定大方向，15m 信号只能顺着日线方向开仓（逆日线哪怕 15m 再强也拦）。

### 参数（A/A/A 方案，已 Phase-0 SHADOW 落地）

| 参数 | 值 | 说明 |
|------|----|------|
| EMA 交叉组合 | **EMA20 × EMA50**（经典双均线，D 级别） | 标准趋势跟踪 |
| `D_GATE_CONFIRM_BARS` | **2 根 D 级别 K 线** | 翻转缓冲：方向变化必须连续 2 根 D 收盘同时满足 gap%，防假突破 |
| `D_GATE_MIN_BUFFER_PCT` | **0.2%**（= 0.002） | 两根 EMA 的归一化差值 `|(EMA20−EMA50)/EMA50|` 必须 ≥ 0.2%，窄幅震荡内不锁方向 |

### 三态输出（每 pair 独立）

| 态 | 判定条件 | 放行动作 |
|---|---------|---------|
| **LONG** | 连续 2 根 D-K 线 `(EMA20−EMA50)/EMA50 ≥ 0.002` | 只允许 BUY 信号通过；SELL → 拦 |
| **SHORT** | 连续 2 根 D-K 线 `差值 ≤ −0.002` | 只允许 SELL 信号通过；BUY → 拦 |
| **BOTH**（中性） | 缓冲带内 / 数据不足 / 混合符号 | 双向放行（= 闸门不介入） |

### Phase 工作流（用户「记录≠执行」铁律）

| 阶段 | `D_GATE_ENABLED` | `D_GATE_SHADOW` | 行为 |
|------|:---:|:---:|------|
| **Phase 0 观测（当前）** | ✅ True | ✅ True | 逆向信号打 **`🧭 D-GATE SHADOW DIAG … would_block=YES`**，**仍然照常放行**，让你事后统计「这些被影子拦下的单」真实盈亏；目标攒 ≥20 条样本 |
| **Phase 1 执行（晋升）** | ✅ True | ❌ False | 真正执行拦截：`🚫 D-GATE ENFORCED: EURUSD BUY BLOCKED (D-dir=SHORT)`，逆日线单被 `continue` 掉 |

**Gemini 评审建议 Phase 0 达标后立刻转 Phase 1**：「日线强空头时 15m 反弹 BUY 绝大多数是诱多，拦下它们可显著降低 MDD」。

### grep 关键词速查（证据链收集用）

| 关键字 | 位置 | 含义 |
|--------|------|------|
| `🧭 D-GATE: SHADOW (log-only) \| EMA20×EMA50 \| confirm=2D \| buffer=0.20%` | 启动 banner | 确认当前处于 Phase-0 观测 |
| `STEP 2.5 D-GATE — Daily Direction Locks` | 每轮 main 启动 | 每轮重算所有 pair 的 D 方向锁 |
| `🧭 D-GATE SUMMARY: LONG=x SHORT=y BOTH=z` | Step 2.5 末尾 | 全局 D 方向统计（市场环境速览） |
| `AUDUSD=X: LONG` / `GBPUSD=X: SHORT` / `USDCHF=X: BOTH` | Step 2.5 明细 | 每对独立方向 |
| `🧭 D-GATE: AUDUSD BUY ALLOWED (D-dir=LONG)` | 评分后放行 | 15m 方向符合 D 闸门 |
| **`🧭 D-GATE SHADOW DIAG EURUSD: D-dir=SHORT 但 15m-wants BUY — would_block=YES`** | 评分后逆向 | **Phase-0 证据链核心行**：统计这些单后来 hit SL 还是 TP 的比例 |
| `🚫 D-GATE ENFORCED: … BLOCKED` | Phase 1 启用后 | 真实拦截（未来才会出现） |

---

## 9. 3 票制开仓方向 + Dynamic Sizing Phase-0（🔵 SHADOW ONLY，F6 升级含 Disagreed Voter）

### 方向投票（3 独立投票人，同方向 ≥2 票 PASS）

| 投票人（权重相等，非加权，硬 2/3 阈值） | 判定规则 |
|----------------------------|---------|
| 1️⃣ **Strength Gap（主导）** | `base_strength − quote_strength`；gap ≥ `MIN_SCORE_GAP(0.50)` → BUY；≤ −0.50 → SELL |
| 2️⃣ **XGB 模型预测** | `P_up` ≥ 0.55 → BUY；否则 SELL |
| 3️⃣ **MC 蒙特卡洛（15m horizon）** | `P_UP`（15m 末涨概率）≥ 55% → BUY；否则 SELL |

**2:1 例子为什么合理？**：
`Strength Gap = BUY（强动能）+ XGB = SELL + MC = SELL` → 2:1 通过 SELL。
Gemini 指出：这代表「**中短期动能（Strength）与预测模型/概率模拟严重背离**」，可能是潜在低质量信号。

### Gemini P1 改进：Dynamic Position Sizing（v6.8.3.4 只做 Phase-0 诊断，不真执行）

为了验证「2:1 信号比 3:0 全票信号质量明显差」这个假设，v6.8.3.4 在 3 票判定后插了诊断日志：

- **3:0 unanimous**（三票一致）→ 不打特殊诊断
- **2:1 split**（Strength 背离 XGB/MC，或任何 1 票背离）→ **Gemini 升级：精确标明 Disagreed Voter 到底是 Strength / XGB / MC 中哪一个在唱反调**：

```
📊 VOTE SIZE DIAG [GBPJPY=X]: 2:1 split consensus (BUY=2, SELL=1) | Disagreed: MC (Strength=BUY, XGB=BUY, MC=SELL (vs winner BUY)) -> would_halve=True (Phase0: log-only; actual lot unchanged)
```

**Phase-0 证据链收集命令**：
```bash
# 1) 先统计样本数
grep "VOTE SIZE DIAG" logs/bot_profile*.log | wc -l
# 2) 分类：异议到底是谁
grep "Disagreed: MC"       logs/bot_profile*.log | wc -l   # MC 唱反调多少条
grep "Disagreed: Strength" logs/bot_profile*.log | wc -l   # Strength 唱反调多少条
grep "Disagreed: XGB"      logs/bot_profile*.log | wc -l   # XGB 唱反调多少条
# 3) ≥ 20 条 would_halve 样本后
#    → 对比 2:1 vs 3:0 的 hit-SL-rate / PnL
#    → 如果 2:1 胜率比 3:0 低 ≥ 20%，且 MC 异议占比最高 → 才考虑真 0.5x 开仓
```

---

## 10. Smart TP（v6.8.3.4 策略统一版：P2=P3 MC 自适应，🔒 62.5% 阈值）

### 从「P2 自适应 / P3 固定 ×1.2」→「统一 MC 自适应」

ChatGPT P0 评审建议：**P2/P3 策略参数必须完全一致，否则未来 PnL 差异不知道是来自 bucket 还是 TP 调参**。v6.8.3.4 起 P3 不再是固定 ×1.2，和 P2 统一为：

| 情形 | MC 动量（🔒 LOCKED：mc_pct_up ≥ **62.5%** 即 ≥ STRONG） | TP pips |
|------|:---:|---|
| **STRONG MOMENTUM** | ≥ 62.5%（也就是 MC 单边 ≥ 62.5%，偏置 12.5%+） | 30p × **2.0** = **60p**（让强趋势充分跑） |
| **NORMAL** | < 62.5% | 30p × **1.0** = **30p**（常规环境快速落袋） |

两种情形都会在 evaluate_trend_and_tp 末尾打可审计的 INFO 行：
```
✅ STRONG MOMENTUM ×2.0 — MC=82.1% (≥62.5% 🔒locked) → TP=60.0p (PROFILE2)
✅ NORMAL ×1.0 — MC=57.4% (<62.5%) → TP=30.0p (PROFILE3)
```

### 原「P3 静态 ×1.2 (36p)」为什么不保留？（Gemini 审订澄清）

- 静态 ×1.2 在 GBPUSD/EURUSD 强趋势时**过早 TP，限制盈利上限（Gemini 建议至少 ×1.5）**；而 MC 自适应能在强趋势（MC≥62.5%）自动吃到 60p。
- 静态 36p 比 NORMAL 30p 宽、比 STRONG 60p 窄，处于「两不靠」的模糊地带，对审计归因没有帮助。
- 统一后 P2/P3 的 Universe 差异变成唯一变量，符合科学方法。
- **🟡 LIVE BEHAVIOR CHANGED 2 标记**：这个改动实际上改变了 P3 的 exit 分布，必须显式披露。

---

## 11. 均线过滤器（默认关闭，随时可以启用）

### 两道 15m Trend Filter 门

| 道门 | BUY 条件 | SELL 条件 | 备注（关于 P2 min_slope 过严的 Gemini 建议） |
|------|---------|----------|------------------------------------------|
| ① 价格门 | `现价 > EMA10` | `现价 < EMA10` | P2/P3 完全一致（EMA10） |
| ② 斜率门（5 根 K 线相对涨跌幅） | 涨幅 ≥ `min_slope` | 跌幅 ≥ `min_slope` | **Gemini 指出 P2 原本 `min_slope=0.001`（=0.1% / 5bar）对 AUDUSD / USDJPY 过于严格**，目前 P3 已经用 `min_slope_rung = 0.0003` 放宽阶梯（配合 SLOPE_DIAG 证据链）。建议未来 P2 也降到 `min_slope_rung = 0.0005`（中间档）配合 SLOPE_DIAG 收集 `would_flip` 样本后再逐步收紧。 |

### 周线 EMA100 反趋势拦截
> 周线大级别反趋势（BUY 单价格 < Weekly EMA100 / SELL 单价格 > Weekly EMA100）一律拦截，缓冲 30p。

### 启用方法
```python
# 对应 profile 配置里改：
TREND_FILTER_ENABLED = True            # 打开 15m 双门
WEEK_EMA100_FILTER_ENABLED = True      # 打开周线大级别反趋势保护
SLOPE_DIAG = True                      # 打开 min_slope 收紧阶梯诊断（P3 默认已开）
```

---

## 12. Position Management（开仓 SL + 持仓移动 SL）

### 开仓初始 SL（默认走 Zone-based，`SL_USE_ZONE_HIERARCHY=True`）

[compute_sl_zone](file:///home/qili/projects/ai_training_cnn/sl_zone_hierarchy.py#L7-L80)

优先级阶梯：
```
① H4 Zone（最近 6 根 H4 的 swing low/high ± SL_BUFFER_PIPS=25）
  → dist >= MIN_DIST_PIPS（默认 20，可被 §7 SL_PAIR_FLOOR_OVERRIDES 覆盖，如 GBPJPY=50）✓ OK
  → 太窄 ② H8 Zone（4 根 H8）太窄 → ③ Daily Zone（2 根 D）太窄
  → ④ ATR-2.0x（6-14 根 True Range 的均值 ×2）
  → ⑤ SL_FALLBACK_FIXED_PIPS=35p（可被 §7 覆盖，如 GBPJPY=50）—— 最后防线
```
每一步都会打 `📏 SL {H4/H8/DAILY/ATR/FIXED}` 的 INFO 行，方便审计 SL 的来源。

### 持仓后移动 SL（DynamicPositionManager，P2/P3 完全相同）

统一逻辑：
- **BE 保本触发**：利润 ≥ `1.5 × ATR` → 把 SL 拉到 entry_price + 0（保本）。
- **追踪止损触发**：利润 ≥ `2.5 × ATR` → 开始用 `2.0 × ATR` 的追踪宽度从最高点/最低点追着走（Conservative 档从 1.5 放宽到 2.0，防 whipsaw）。

---

## 13. Portfolio Controller 总控架构三阶段（Gemini 审订重写版：禁止文件锁 / race condition）

> **Gemini 审计强制修订**（2026-10-03，取代之前的 Level-1/2 方案）：
> 1.  **绝对禁止引入 `portfolio_state.json` / `allocation.json` 之类的本地并发状态文件锁**（会有 race condition、死锁、且本地状态 ≠ 券商端真实状态，违反 broker-state-authoritative 原则）。
> 2.  降级 Level-1 为 **DESIGN ONLY**，不承诺实现时间；未来总控第一版命名为 **Portfolio Observer（只读）**，只做：读取 OANDA 两账户真实持仓 → 打组合层诊断日志，永远不作为 Execution Gate。
> 3.  目前 Level-0 Universe Safety Guard（Whitelist Overlap 锁）是唯一真正的组合层硬门禁。

### 总设计一句话（ChatGPT 原架构 + Gemini 修订）

```
P2/P3 ≠ 两个互相竞争的独立 Bot
P2/P3 = 两个拥有固定 Universe Bucket + OANDA 独立账户的「执行单元」

Master（Portfolio Observer，只读）= 只看 OANDA API 真实持仓做组合层诊断，
  绝对不碰 OANDA Order API，绝对不写本地状态锁。
  只输出 Evidence-chain 诊断，不做 Execution Gate。

Execution Boundary（必须守住，Gemini 明确反对 Master 直接下单）：
  Master 不碰 OANDA Order API，Master 只输出 allocation policy 诊断；
  P2/P3 仍全权负责自己的 entry/SL/TP/position。
```

### 三阶段落地路线图（按优先级 P0→P3）

| 阶段 | 控制对象 | 功能 | v6.8.3.4 状态 | 何时晋级 |
|------|---------|------|:------------:|---------|
| **Level-0 Universe Safety Guard** | 启动时硬不变量 | ① Whitelist overlap 检查；② 参数合法性（ATR_TP_MULT 范围） | ✅ **GREEN — LIVE / VERIFIED 已完成** | — |
| **Portfolio Observer（只读，P1 最高优先级）** | 跨账户只读诊断（⛔ 不写入任何文件锁，⛔ 不拦截任何执行） | ① 每 15m 同时读 OANDA P2 + P3 真实持仓；② 打 `📊 PORTFOLIO OBSERVER: total_open=3 / JPY_net=LONG_2 / USD_net=SHORT_1 …` 之类诊断日志；③ Currency / Theme 暴露统计（例：JPY 主题目前 3 LONG，应注意集中度） | ⚪ **DESIGN ONLY 规划中**（代码未写） | 等当前 v6.8.3.4 跑 2-4 周，积累了 30+ 笔成交后再写一个 **只读** 的 observer.py（单独脚本，不插入主循环） |
| **Level-1 Allocation Gate（跨账户 TOTAL_MAX_OPEN 硬拦截）** | 跨账户总风险预算 | ① 真正 enforce `PORTFOLIO_MAX_OPEN = 4`；② 动态分配 P2 vs P3 本轮额度；③ Theme 暴露硬上限 | ⚪ **DESIGN ONLY 规划中**（**Gemini 降级**：暂不写，等 Portfolio Observer 跑 2 个月有组合层数据后再评估是否需要） | Portfolio Observer 稳定运行 2 个月且确实经常发生「P2 3 单 + P3 2 单 = 5 单 > 4 ceiling」场景 → 再决定要不要真做 Gate |
| **Level-2 Portfolio Intel** | 组合层「聪明度」 | ① 收集 P2/P3 所有 pair 的 MC/Strength，做「主题聚类」；② Correlation-aware 分配；③ Portfolio 级别的 MC 大方向判断（不是重做 MC，是 pair-level MC 的汇总） | ⚪ **DESIGN ONLY 远期规划**，无代码 | Level-1 稳定运行 ≥ 2 个月后再考虑 |
| **Master 自己生成交易 Signal（P3 ❌ 不建议）** | 交易信号 | — | 🚫 **不做** | 会变成第三套策略，与 P2/P3 互相打架，执行所有权混乱 |
| **Master 直接调用 OANDA Order API（P3 ❌ 不建议）** | 订单执行 | — | 🚫 **不做** | 破坏 ownership 边界，回滚和审计都困难，且违反 broker-state-authoritative 原则 |

### 替代 Level-1 的临时方案（已写在 §4 Crontab）

在 Level-1 真正实现前，用 **CLI 物理参数限制** 实现组合上限：

| 方案 | 具体做法 | Portfolio Safe |
|------|---------|:--------------:|
| **Scheme A（推荐下周）** | 只开 P2 单账户，`--max-entries 2` | ✅ P2 上限 2 < 4 |
| **Scheme B（要同时跑 A/B 测试时）** | P2 `--max-entries 2` + P3 `--max-entries 2` = **合计 4**，物理卡死 | ✅ 合计 4 = 全局 ceiling |

---

## 14. 下周（实盘观测期）证据链采集清单（5 天后汇总用）

下周系统维持当前代码**不追加任何硬编码执行逻辑**，全力收集真实市场反馈，下周末用数据说话。

### 4 条核心 grep + 分析目标

| # | 诊断项 | grep 命令 | 分析问题 |
|---|--------|-----------|---------|
| 1 | **D-Gate 拦单有效性（Phase-0 证据链）** | `grep "would_block=YES" logs/bot_profile*.log \| wc -l` | 被 D-Gate 影子记录为「该拦」的那些单：如果真的不拦，最终是 hit SL 还是 hit TP？如果 ≥60% 最终亏损，立刻转 Phase 1 ENFORCED |
| 2 | **2:1 分票异议方精确归因（F6 升级）** | `grep "VOTE SIZE DIAG" logs/bot_profile*.log` → 按 `Disagreed: {Strength/XGB/MC}` 三类切开统计 | 到底谁唱反调最伤 PnL？MC 异议 vs Strength 异议 vs XGB 异议，哪一类 2:1 单 hit-SL-rate 显著高？ |
| 3 | **GBPJPY 50p SL 呼吸空间验证（🟡 LIVE CHANGED 1）** | `grep "📏 PAIR-SPECIFIC FLOOR" logs/bot_profile2.log` → 看所有 GBPJPY 成交单的实际入场 SL 距离，对照后续是否出现「如果 35p 就被扫、50p 能活到反弹」的案例 | 验证 50p 给的呼吸空间是不是真的在「35p~50p 区间内有反弹盈利」案例 |
| 4 | **P3 MC 自适应 TP 重构验证（🟡 LIVE CHANGED 2）** | `grep -E "STRONG MOMENTUM|NORMAL.*MC=" logs/bot_profile3.log` → 统计 NORMAL(30p) 与 STRONG(60p) 的实际触及率及盈亏比 | 对比原固定 36p 的假设行为：新的 30p 快速落袋 + 60p 强趋势吃满，整体 RR 是否优于静态 ×1.2 |

### 观测期运行方案选择（§4 Crontab）

- **下周推荐 Scheme A（最稳健）**：只开 P2 单账户 `--max-entries 2`，先集中收集 JPY Bucket 干净样本，P3 注释不动。
- **想同时跑 A/B 测试**：用 Scheme B，P2 `--max-entries 2` + P3 `--max-entries 2`，CLI 物理卡死 4 单 ceiling。

---

## 15. 诊断 grep 命令速查（日志分析必备）

| 要分析什么 | grep 命令 / 关键词 |
|-----------|-------------------|
| D-Gate Phase-0 影子拦下了多少条（证据链核心） | `grep "would_block=YES" logs/bot_profile2.log \| wc -l` |
| 2:1 分票（含 Disagreed Voter，未来 Dynamic Sizing 证据链） | `grep "📊 VOTE SIZE DIAG" logs/bot_profile{2,3}.log` |
| 白名单被 SKIP 了多少对 | `grep "not in.*ALLOWED_PAIRS — SKIP" logs/bot_profile2.log` |
| 订单状态成功/失败分类 | `grep -E "✅ EXECUTED\|❌ ORDER FAILED\|REJECTED\|CANCELLED\|REDUCED" logs/*.log` |
| Pair-specific SL Floor 生效 | `grep "📏 PAIR-SPECIFIC FLOOR" logs/bot_profile2.log`（看 GBPJPY 打出来 50p） |
| Smart TP 用的是 ×1 还是 ×2（NORMAL/STRONG） | `grep -E "STRONG MOMENTUM|NORMAL.*MC=.*→ TP" logs/bot_profile{2,3}.log`（所有 MC 阈值均按 🔒62.5% 打印） |
| SL 最终来自哪一层（H4 Zone / ATR / FIXED） | `grep -E "📏 SL|🔁 SL ATR|🚨 SL FIXED" logs/bot_profile*.log` |
| 最近一次运行的 Summary（入口方便） | `grep "Run Complete\|run_summary\|entries_executed\|MAX_OPEN" logs/bot_profile2.log \| tail -n 10` |
| Whitelist disjoint 检查（启动必须看到） | `grep -E "WHITELIST disjoint\|OVERLAP" logs/bot_profile*.log` |
| Overlap 警报（绝对不应该出现） | `grep "🚨 WHITELIST OVERLAP" logs/bot_profile*.log`（有返回立刻停！） |
| D-Gate SUMMARY 看当前市场大环境 | `grep "D-GATE SUMMARY:" logs/bot_profile2.log \| tail -n 1` |

---

## 16. 同步 OracleVM 文件命令备忘

```bash
# 本机（开发机）→ OracleVM（生产）：
cd ~/projects/ai_training_cnn && rsync -av \
  fx_trade_bot_v683.py \
  fx_trade_bot_utils.py \
  sl_zone_hierarchy.py \
  config_bot_profile2.py \
  config_bot_profile3.py \
  fx_trade_bot_v683_usage.md \
  ubuntu@oraclevm:~/projects/ai_training_cnn/
```

**每次同步后，OracleVM 上先跑这两步再开 LIVE / 启用 cron：**
```bash
# Step 1: Syntax OK
ssh ubuntu@oraclevm "cd ~/projects/ai_training_cnn && \
  python -m py_compile fx_trade_bot_v683.py sl_zone_hierarchy.py config_bot_profile2.py config_bot_profile3.py && echo '✅ All syntax OK'"

# Step 2: Dry-run P2 + P3，必须看到 disjoint ✅（无 OVERLAP）
ssh ubuntu@oraclevm "cd ~/projects/ai_training_cnn && \
  python fx_trade_bot_v683.py --profile2 --dry-run 2>&1 | grep -E 'WHITELIST.*disjoint|D-GATE: SHADOW|OVERLAP' && \
  python fx_trade_bot_v683.py --profile3 --dry-run 2>&1 | grep -E 'WHITELIST.*disjoint|D-GATE: SHADOW|OVERLAP'"
# 必须看到两行：WHITELIST disjoint ✅ overlap=0 + 🧭 D-GATE: SHADOW
# OVERLAP 有任何返回 → 立刻停，不要开 LIVE
```

---

## 17. 「下一步做什么」按优先级+前提条件排序（给未来自己看）

| 序号 | 事项 | 前提条件（必须满足） | 收益 |
|------|------|:---:|------|
| 1 | D-Gate 从 SHADOW 转 ENFORCED | 20 条 `would_block=YES` 且 ≥60% 这些单实际亏损 | 显著砍逆日线大趋势回撤（MDD 大幅下降） |
| 2 | **写 Portfolio Observer（只读脚本）**（§13） | 当前 P2（Scheme A）跑 ≥ 2 周、20+ 笔成交样本 | 组合层 JPY Theme 集中度、净暴露的只读诊断，不做任何 Gate |
| 3 | 2:1 分票真的开 0.5x 手数 | 20 条 would_halve 样本 → 2:1 胜率比 3:0 低 ≥ 20%；并识别出具体是哪一类异议（MC/Strength/XGB）最伤 | 动能背离场景降风险，避免低质量信号满仓 |
| 4 | Trend Filter 开启 + P2 min_slope 也走放宽阶梯 | 先跑 2 周 SLOPE_DIAG 看 P2 的 would_flip 分布 | 减少无趋势 15m 横盘假突破 |
| 5 | 新增更多 Per-Pair SL Override（例 EURJPY 也提到 45p？） | 观察 EURJPY 被 SL 扫前的距离分布，确认 35p 真不够 | 其他高波动交叉盘留足呼吸空间 |
| 6 | Level-1 Allocation Gate（真的跨账户 enforce 4 ceiling） | Portfolio Observer 跑 2 个月，且真的常出现 P2 2-3 单 + P3 2 单 = 5 单突破 ceiling 的场景 | 真的组合层硬风控（在 Scheme B 的物理 2+2 不够灵活时才值得做） |
| 7 | Level-2 Portfolio Intel（主题/相关性） | Level-1 稳定 2 个月，且有 ≥80 笔成交样本做相关性分析 | 把「GBPJPY LONG + EURJPY LONG + USDJPY LONG = 同一 JPY 主题」识别成 1 个独立 bet，而非 3 个 |
