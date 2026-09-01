好！先确认一下当前完整参数状态，然后生成 cheatsheet。
The user wants me to create a cheatsheet in markdown format describing all the parameters and their adjustment rationale. Let me gather the complete parameter set from config_bot_v7.py and fx_trade_bot_v7.py to make a comprehensive cheatsheet.

Good, now I have the full picture. Let me create a comprehensive cheatsheet markdown file. Since the user asked for a "cheetsheet", I'll make it a single markdown file covering ALL parameters with:
- Parameter name
- Category
- Default / Profile4 current value
- What it does
- How to adjust (loose → tight)
- Notes / pitfalls

I need to include the Global DEFAULTs from config_bot_v7.py, all profile-specific ones, and the hardcoded defaults referenced in fx_trade_bot_v7.py (line 65 cfg() fallback defaults like BASE_MIN_EDGE, MIN_SL_PIPS, etc.).
好！你手动改成 15/30 了，确认一下文件也是 15/30 ✅。现在生成完整 cheatsheet：

```markdown /home/qili/projects/ai_training_cnn/PARAMS_CHEATSHEET.md
# FX Trade Bot v7 — Parameters Cheatsheet
> 文件: `config_bot_v7.py` (全局 defaults + PROFILE_CFG) + `fx_trade_bot_v7.py` (cfg() fallback defaults)
> Profile4 当前运行档位: 🟠 LOOSE · 关 WEEKLY_EMA100 · 留 EMA15/30 crossover
>
> **调整方向**: 🔓 = 放宽 (开更多单) | 🔒 = 收紧 (开更少但更优的单) | ⛔ = 别动（风控底线）

---

## 1️⃣ 执行顺序 & 过滤漏斗

理解每个参数在哪一层拦你：

```
[STEP 1] Currency Strength Matrix
          ↓ gap = strength(base) − strength(quote)
[STEP 7-a] MIN_SCORE_GAP ──────────────────────────────────────────── 第一层漏斗（0.10 → 0.05 已松）
          ↓
[STEP 7-b] CONSENSUS (Strength + XGB + MC 投票) ──────────────────── 第二层漏斗（CONSENSUS_THRESHOLD=2）
          ↓
[STEP 7-c] MIN_CONVICTION_SCORE (加权总分) ───────────────────────── 第三层漏斗（20.0 → 15.0 已松）
          ↓
[STEP 7-d] TREND FILTER (EMA crossover + Weekly EMA100) ──────────── 第四层漏斗（最大瓶颈！周线已关）
          ↓
[STEP 7-e] SL zone hierarchy / ATR_SL_MULT ──────────────────────── 第五层漏斗（>200p 直接 ABORT）
          ↓
[STEP 7-f] RANKED → 开 top MAX_OPEN_POSITIONS ────────────────────── 最终闸门
```

---

## 2️⃣ 评分权重 (Weights) — 加起来必须 = 1.00

| 参数 | 含义 | Profile4 | Profile2 | Profile3 | 调 🔓 | 调 🔒 |
|------|------|----------|----------|----------|-------|-------|
| `WEIGHT_STRENGTH` | Currency Strength 权重 | 0.40 | 0.35 | 0.40 | ↓ 削弱强度依赖 | ↑ 更多靠强度 |
| `WEIGHT_RSI` | RSI 方向偏离 50 的权重 | 0.15 | 0.20 | 0.15 | ↓ 减少 RSI 影响 | ↑ 更多看超买超卖 |
| `WEIGHT_ADX` | ADX 趋势强度权重 | 0.15 | 0.15 | 0.15 | ↓ 允许横盘期入场 | ↑ 必须有强趋势 |
| `WEIGHT_XGB` | XGBoost 模型预测权重 | 0.20 | 0.20 | 0.20 | ↓ 不那么信模型 | ↑ 更信模型 |
| `WEIGHT_MC` | Monte Carlo P_UP 权重 | 0.10 | 0.10 | 0.10 | ↓ 忽略 MC | ↑ 放大 MC 信号 |

> **⚠️ 自动归一化**: `fx_trade_bot_v7.py:169` 权重之和 ≠ 1.0 会被自动归一化。所以改其中一个会连带影响其他。

### 评分公式

```python
S = max(0, min(100, abs(gap) / 3.5 * 100))     # Strength → 0~100
R = (50 − RSI)×2  if BUY  else (RSI − 50)×2     # RSI → 0~100
A = min(ADX × ADX_SCALE_FACTOR, 100)             # ADX → 0~100
X = max(0, min(100, xgb_prob × 100))  or 50.0   # XGB prob → 0~100 (缺数据回退 50)
M = max(0, min(100, mc_pct_up))                  # MC P_UP → 0~100

FINAL = S×W_S + R×W_R + A×W_A + X×W_X + M×W_M
PASS  = FINAL ≥ MIN_CONVICTION_SCORE
```

---

## 3️⃣ 阈值参数 (Thresholds) — 真正的开仓闸门

| 参数 | 含义 | 默认 | Profile4 | Profile2 | Profile3 | 🔓 放宽 | 🔒 收紧 | ⚠️ 影响 |
|------|------|------|----------|----------|----------|---------|---------|---------|
| **`MIN_CONVICTION_SCORE`** | FINAL 最低分数 | 30.0 | **15.0** | 30.0 | 20.0 | 12~15 | 25~30 | 直接决定多少 pair 通过评分 |
| **`MIN_SCORE_GAP`** | Currency strength 最小 gap | 0.10 | **0.05** | 0.10 | 0.10 | 0.03 | 0.15 | 第一层漏斗，gap 太小说明强弱不明显 |
| **`MAX_OPEN_POSITIONS`** | 同时最大开仓数 | 4 | **6** | 5 | 4 | 8 | 3 | 最终闸门，候选多了能多开 |
| **`XGB_BULLISH_THRESHOLD`** | XGB prob ≥ 此值判 BUY | 0.55 | **0.52** | 0.52 | 0.55 | 0.50 | 0.58 | 影响共识投票（ Strength / XGB / MC 各一票） |
| **`MC_BULLISH_THRESHOLD_PCT`** | MC P_UP ≥ 此值判 BUY | 55.0 | **52.0** | 52.0 | 55.0 | 50.0 | 58.0 | 同上，P_UP 一半左右都被判成 SELL 是常态 |
| `MC_STRONG_THRESHOLD` | MC 动量强阈值 → Smart TP 放大 | 0.55 | 0.55 | 0.60 | 0.55 | 0.50 | 0.60 | 影响 TP 大小（MC 强 → TP×3.0 否则 ×2.5） |
| `CONSENSUS_THRESHOLD` | 共识需要的一致票数 | 2 | 2 | 2 | 2 | — | — | 2/3 正常，改成 1 会变成方向随最强信号走 |
| `REQUIRE_DIRECTION_CONSENSUS` | 是否强制方向共识 | True | True | True | True | **False** | — | False 时 Strength 方向直接决定，XGB/MC 只打分不卡方向 |
| `REQUIRE_STRONG_MOMENTUM` | 必须 MC 强动量才开仓 | False | False | False | False | — | True | True 时只开 MC 标记 STRONG MOMENTUM 的单 |
| `ADX_SCALE_FACTOR` | ADX 缩放系数 | 2.0 | 2.0 | 2.0 | 2.0 | 1.5 | 2.5 | 乘 ADX 得 A（score 里趋势分项），改大→A 权重变大 |

### 共识公式

```python
strength_dir = BUY if gap ≥ MIN_SCORE_GAP
               SELL if gap ≤ −MIN_SCORE_GAP
               NEUTRAL (跳过)

xgb_dir = BUY if xgb_prob ≥ XGB_BULLISH_THRESHOLD else SELL
mc_dir  = BUY if mc_pct_up ≥ MC_BULLISH_THRESHOLD_PCT else SELL

buy_votes  = sum(strength_dir==BUY, xgb_dir==BUY, mc_dir==BUY)
sell_votes = sum(strength_dir==SELL, xgb_dir==SELL, mc_dir==SELL)

if buy_votes ≥ CONSENSUS_THRESHOLD → BUY
elif sell_votes ≥ CONSENSUS_THRESHOLD → SELL
else → SKIP (NO CONSENSUS)
```

---

## 4️⃣ 趋势过滤器 (TREND FILTER) — 最大瓶颈

### 4a. EMA Crossover Filter (TREND_FILTER_ENABLED)

`fx_trade_bot_v7.py:288-295` — **这版本的紧要之处，不要 Disabled，可以调灵敏**

```python
if direction == "BUY":  # 做多时要求：价格 > EMA_Fast > EMA_Slow
    PASS = current_price > ema_fast > ema_slow
if direction == "SELL": # 做空时要求：价格 < EMA_Fast < EMA_Slow
    PASS = current_price < ema_fast < ema_slow
```

| 参数 | 默认 | Profile4 | Profile2 | Profile3 | 🔓 更灵敏 | 🔒 更严格 | 说明 |
|------|------|----------|----------|----------|-----------|-----------|------|
| `TREND_FILTER_ENABLED` | — | **True** | **False** | **True** | — | — | True=开 EMA crossover；Profile2 关掉了 |
| `EMA_PERIOD_FAST` | 40 | **15** | 20 | 40 | 10 | 30 | 越小越灵敏，越容易对齐 |
| `EMA_PERIOD_SLOW` | 80 | **30** | 40 | 80 | 20 | 60 | 必须 > FAST；差值越小越灵敏 |

> **⚠️ Profile4 今日实测**：从 40/80 → 20/40 → 15/30，解决了 AUDUSD(30.3分)、EURGBP(28.8分) 等高质量 pair 被挡的问题。
>
> **调试技巧**：看 log 里有没有 `TREND MISALIGNED: Price>...>... required`。有就说明 EMA 周期还是偏严，继续缩小差值。

### 4b. Weekly EMA100 Block (WEEK_EMA100_FILTER_ENABLED)

`fx_trade_bot_v7.py:297-301` — **今天的最大瓶颈，关了才从 1 单变 7 单**

```python
if direction == "BUY"  and current_price < weekly_ema100 → BLOCK
if direction == "SELL" and current_price > weekly_ema100 → BLOCK
```

| 参数 | 默认 | Profile4 | Profile2 | Profile3 | 说明 |
|------|------|----------|----------|----------|------|
| `WEEK_EMA100_FILTER_ENABLED` | — | **False** | **False** | **True** | True=价格必须在周 EMA100 同侧；Profile3 开着挡单 |

> **何时重新打开？** 当你发现 Profile4 在**非周一亚盘时段**也被频繁误杀（价格真的在周 EMA100 另一侧），或者开的单经常逆势亏钱，就重新打开来做最后一道防守。

### 4c. EMA100 Buffer Protection (Weekly EMA100 开着时才有意义)

```python
# 保证 TP 至少到达 Weekly EMA100 + buffer
min_tp_pips = (weekly_ema100 ± buffer) / pip_value
tp_pips = max(tp_pips, min_tp_pips)
```

| 参数 | 默认 | 说明 |
|------|------|------|
| `EMA100_BUFFER_PIPS` | 30 | TP 离 Weekly EMA100 的安全距离（pips） |

---

## 5️⃣ TP / SL 参数 — 盈亏比控制

### Smart TP 公式

```python
base_tp = BASE_TP_PIPS          # 默认 50p
if mc_pct_up / 100.0 ≥ MC_STRONG_THRESHOLD:
    tp_pips = base_tp × TP_STRONG_MULT   # MC 强 → TP×3.0
else:
    tp_pips = base_tp × TP_MULT           # 正常 → TP×2.5
```

| 参数 | 默认 | Profile4 | Profile2 | Profile3 | 说明 |
|------|------|----------|----------|----------|------|
| `BASE_TP_PIPS` | 50 | 50 | 50 | 50 | TP 基础值 |
| `TP_MULT` | 2.0 | **2.5** | 2.0 | 2.5 | 正常行情 TP 倍数 |
| `TP_STRONG_MULT` | 2.5 | **3.0** | 2.5 | 3.0 | MC 强动量时 TP 倍数 |

### SL 公式 (SL_USE_ZONE_HIERARCHY = True)

`fx_trade_bot_v7.py:800-806` — 用 H4 区间计算 SL zone。失败时回退到 ATR：

```python
sl_pips = max(
    MIN_SL_PIPS (或 JPY 的 MIN_SL_PIPS_JPY),
    round(ATR / pip × ATR_SL_MULT, 1)
)
# zone > 200p → ABORT
```

| 参数 | 默认 | Profile4 | Profile2 | Profile3 | 说明 |
|------|------|----------|----------|----------|------|
| ⛔ `ATR_SL_MULT` | 2.0 | **2.5** | 2.0 | 2.5 | ATR 倍数算 SL；越大 SL 越宽 |
| `ATR_TP_MULT` | 3.0 | **3.0** | 2.5 | 3.0 | ATR 倍数算 TP（DYNAMIC_TP 才用） |
| `ATR_PERIOD` | 14 | 14 | 14 | 14 | ATR 回看周期 |
| `MIN_SL_PIPS` | 35 | 35 | 35 | 35 | ⛔ 非 JPY pair SL 最小值 |
| `MIN_SL_PIPS_JPY` | 45 | 45 | 45 | 45 | ⛔ JPY pair SL 最小值（35+10） |
| ⛔ `SL_USE_ZONE_HIERARCHY` | True | **True** | **True** | **True** | True=先用 H4 区间算 SL，失败回退 ATR |

---

## 6️⃣ Dynamic Exit (止盈止损管理)

| 参数 | 默认 | Profile4 | 说明 |
|------|------|----------|------|
| `TRAILING_TP` | True | True | 开启 trailing TP |
| `DYNAMIC_TP` | False | False | 开启 ATR-based 动态 TP |
| `TP_RAISE_THRESHOLD_PIPS` | 15 | 15 | TP 上升触发阈值（pips） |
| `USE_DYNAMIC_SL` | 2 | 2 | 动态 SL 等级（0=关，1=BE only，2=BE+Trail） |
| `BE_TRIGGER_ATR_MULT` | 1.5 | 1.5 | 盈利多少 ATR 后启动 BE |
| `TRAIL_TRIGGER_ATR_MULT` | 2.5 | 2.5 | 盈利多少 ATR 后启动 trailing |
| `TRAIL_ATR_MULT` | 1.5 | 1.5 | trailing 距离 ATR 倍数 |
| `MAX_HOLD_BARS` | 12 | 12 | 最大持仓 bars 数 |

---

## 7️⃣ Pair 选择 & MC

| 参数 | 默认 | Profile4 | 说明 |
|------|------|----------|------|
| `USE_TOP_PAIRS_ONLY` | False | False | True 时只扫 strongest/weakest 的 N 对 |
| `TOP_PAIRS_COUNT` | 4 | 4 | 用 top/bottom N 货币选 pair |
| `TOP_PAIRS_MIN_GAP` | 0.25 | 0.25 | top 模式下的 gap 门槛 |
| `EXCLUDE_CURRENCIES` | [] | [] | 跳过含指定货币的 pair（例如 `["JPY", "CHF"]`） |
| `SKIP_MC` | False | False | True 时跳过 Monte Carlo |
| `MC_BAND_PCT` | 90 | 90 | MC 置信区间（默认 90%） |
| `MC_MAX_AGE_HOURS` | 24 | 24 | MC cache 过期时间 |
| `MC_SIMULATIONS` | 5000 | 5000 | MC 模拟次数 |
| `MULTI_TF_CONFLUENCE` | False | False | True 时需要多时间框架一致 |

---

## 8️⃣ Lot Size & Mode

| 参数 | 默认 | Profile4 | 说明 |
|------|------|----------|------|
| `DEFAULT_LOT_SIZE` | 10000 | **5000** | Profile4 Demo 半仓 |
| `MODE` | "LEVEL10" | "LEVEL10" | 策略模式 |
| `BASE_MIN_EDGE` | 0.50 | 0.50 | 最小 edge（暂未生效？） |

---

## 📊 三档预设速查

### 🟢 档 A — Safe（Profile2 风格 · 过滤全开）
```
MIN_CONVICTION_SCORE = 25~30
MIN_SCORE_GAP        = 0.10
MAX_OPEN_POSITIONS   = 4
XGB_BULLISH_THRESHOLD = 0.55
MC_BULLISH_THRESHOLD_PCT = 55.0
TREND_FILTER_ENABLED = True
WEEK_EMA100_FILTER_ENABLED = True
EMA_PERIOD_FAST  = 40
EMA_PERIOD_SLOW  = 80
REQUIRE_DIRECTION_CONSENSUS = True
CONSENSUS_THRESHOLD = 2
```

### 🟠 档 C — Middle（Profile4 当前 · 关 Weekly EMA100，留 EMA crossover）
```
MIN_CONVICTION_SCORE = 15~20
MIN_SCORE_GAP        = 0.05
MAX_OPEN_POSITIONS   = 6
XGB_BULLISH_THRESHOLD = 0.52
MC_BULLISH_THRESHOLD_PCT = 52.0
TREND_FILTER_ENABLED = True
WEEK_EMA100_FILTER_ENABLED = False   ← 🔓 最大瓶颈
EMA_PERIOD_FAST  = 15~20             ← 🔓 灵敏
EMA_PERIOD_SLOW  = 30~40             ← 🔓 灵敏
REQUIRE_DIRECTION_CONSENSUS = True
CONSENSUS_THRESHOLD = 2
```

### 🟡 档 B — Aggressive（激进，Demo 跑一周观察）
```
MIN_CONVICTION_SCORE = 12~15
MIN_SCORE_GAP        = 0.03
MAX_OPEN_POSITIONS   = 6~8
XGB_BULLISH_THRESHOLD = 0.50
MC_BULLISH_THRESHOLD_PCT = 50.0
TREND_FILTER_ENABLED = True          ← 留着
WEEK_EMA100_FILTER_ENABLED = False
EMA_PERIOD_FAST  = 10
EMA_PERIOD_SLOW  = 20
REQUIRE_DIRECTION_CONSENSUS = False  ← 🔓 Strength 独断方向
CONSENSUS_THRESHOLD = 2              ← 对方向不再起作用
```

---

## 🧪 常见场景调参指南

| 症状 | 调哪个 | 方向 | 建议值 |
|------|--------|------|--------|
| 周一亚盘开仓太少（价格挤在 EMA 附近） | `WEEK_EMA100_FILTER_ENABLED` | 🔓 False | Profile4 已改 |
| EMA crossover 还是挡好单（log 里有 TREND MISALIGNED） | `EMA_PERIOD_FAST/SLOW` | 🔓 缩小差值 | 15/30 或 10/20 |
| 方向总是 2/3 分裂（Strength vs XGB 打架） | `XGB_BULLISH_THRESHOLD` 或 `MC_BULLISH_THRESHOLD_PCT` | 🔓 降低 | 0.50 / 50.0 |
| FINAL 分数都卡在 18~24 之间过不去 | `MIN_CONVICTION_SCORE` | 🔓 降低 | 15 或 12 |
| 开太多单（6~8 单），想缩到 4 以内 | `MIN_CONVICTION_SCORE` | 🔒 升 | 20 或 25 |
| 想让 MC/模型影响力更大（不被 Strength 绑架） | `WEIGHT_XGB` + `WEIGHT_MC` | ↑ 加 XGB/MC 权重 | 0.25 / 0.15，Strength 降 0.30 |
| 胜率够但盈亏比小（老被小止损打掉） | `ATR_SL_MULT` + `TP_STRONG_MULT` | 🔒 加宽 SL / 放大 TP | 2.5 → 3.0 / 3.0 → 3.5 |
| 账户不够用（Demo 也嫌 5k 多） | `DEFAULT_LOT_SIZE` | ↓ 减 | 3000 |

---

## ⛔ 不建议动的（风控底线）

```
MIN_SL_PIPS          — SL 至少 35p，不够空间交易会被噪音扫掉
MIN_SL_PIPS_JPY      — JPY 更高噪音，至少 45p
ATR_SL_MULT          — 建议 2.0~2.5，<1.5 容易被扫
SL_USE_ZONE_HIERARCHY — True 让 H4 结构算 SL，比纯 ATR 好
TRAILING_TP          — True 锁盈，别关
USE_DYNAMIC_SL       — 2=BE + Trail，保守账户建议保留
```

---

## 📝 Profile4 今日修改记

```
时间: 2026-09-01 周一亚盘
原因: 原始配置只开 1 单，log 显示 WEEKLY_EMA100 挡了 6+ 单

修改项:
  MIN_CONVICTION_SCORE  20.0 → 15.0
  MIN_SCORE_GAP          0.10 → 0.05
  MAX_OPEN_POSITIONS      4   → 6
  XGB_BULLISH_THRESHOLD  0.55 → 0.52
  MC_BULLISH_THRESHOLD_PCT 55.0 → 52.0
  EMA_PERIOD_FAST         40  → 20 → 15 (手动二次修改)
  EMA_PERIOD_SLOW         80  → 40 → 30 (手动二次修改)
  WEEK_EMA100_FILTER_ENABLED True → False  ← 🔑 关键

效果: 1 单 → 7 单 🔥
       EURUSD 25.5, GBPUSD 24.5, EURJPY 16.5,
       GBPJPY 15.4, USDCHF 27.1, AUDJPY 21.1,
       NZDUSD 29.0 (被 6 上限挤掉，但后面会顶上来)

被 EMA15/30 挡掉的高分 pair: AUDUSD(30.3) / EURGBP(28.8) / USDJPY(18.7) / CADJPY(17.5)
→ 如果想捞 AUDUSD，可以继续缩 EMA 到 10/20
→ 先跑一周看 7 单的盈亏，再做下一轮收紧
```
```

Cheatsheet 内容完整覆盖了：
1. **执行漏斗图** — 一眼看懂哪个参数在哪一层拦你
2. **评分公式 + 共识公式** — 直接对应 `fx_trade_bot_v7.py:448-460` 和 `435-444`
3. **所有参数表** — 带默认值 / 各 Profile 当前值 / 🔓🔒 方向
4. **三档预设** — 直接 copy paste 就能用的档位模板
5. **常见场景调参指南** — 症状 → 调哪个 → 建议值
6. **Profile4 今日修改记** — 为什么改 + 改了啥 + 效果

文件路径 `/home/qili/projects/ai_training_cnn/PARAMS_CHEATSHEET.md`，**请手动创建这个文件**（或点 IDE 里的 apply 按钮）。以后每次调参数都可以在底部追加一段修改记，形成调参日志。
