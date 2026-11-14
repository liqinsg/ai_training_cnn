# FX Trading Bot v6.6 — Workflow & Strategy Documentation

## 📋 Overview

**Bot Version**: v6.6 (Centralized Config from `config_bot.py`)
**Timeframe**: 15m / H4 / Daily (configurable)
**Data Source**: OANDA Real-Time + Yahoo Finance
**Model**: XGBoost Machine Learning + Technical Indicators + Monte Carlo Simulation
**Execution**: OANDA API → Dynamic SL/TP + Telegram Alerts

---

## 🔁 Full Workflow Pipeline

```
START BOT RUN
│
├─► ① PRE-CHECKS
│   ├─ Check forex market status → skip if closed
│   ├─ Load/retrain XGBoost model (if missing)
│   └─ Load config from config_bot.py → fallbacks to config.py
│
├─► ② CURRENCY STRENGTH ANALYSIS
│   ├─ Calculate strength scores for 7 major currencies
│   ├─ Rank: strongest → weakest
│   └─ Compute gap between base & quote currency per pair
│
├─► ③ FETCH & PREPARE DATA
│   ├─ Pull 200 latest candles from OANDA per pair
│   ├─ Build features: ATR, MACD, RSI, ADX
│   ├─ Clean: inf/NaN → forward-fill → zero-fill
│   └─ Store ATR value per pair for SL/TP calculation
│
├─► ④ MONTE CARLO FORECAST
│   ├─ 5,000 simulations per pair
│   ├─ Output: regime (MOMENTUM/NEUTRAL/REVERSAL), 90% price range, P_up %
│   ├─ Send MC summary to Telegram
│   └─ Skip or load cached if SKIP_MC = True
│
├─► ⑤ MULTI-TIMEFRAME CONFLUENCE (Optional)
│   ├─ Check signal alignment across 15m / 1H / H4
│   └─ Require ≥2 agreeing timeframes to pass
│
├─► ⑥ POSITION MANAGEMENT
│   ├─ Scan all open positions
│   ├─ Update Dynamic TP / Trailing SL
│   └─ Close positions by strength signal or trailing trigger
│
├─► ⑦ SIGNAL GENERATION & FILTERING
│   ├─ Check cooldown → skip if active
│   ├─ Skip if position already open
│   ├─ Generate signal: XGBoost score + rules
│   ├─ Apply STRENGTH GAP FILTER
│   │   ├─ SELL blocked if base strong > threshold
│   │   └─ BUY blocked if quote strong > threshold
│   ├─ Apply confluence filter (if enabled)
│   └─ Check MAX_SIMULTANEOUS_TRADES limit
│
├─► ⑧ RISK CALCULATION
│   ├─ ATR × Multiplier → SL distance
│   ├─ Enforce MIN_SL_PIPS (25) / MIN_SL_PIPS_JPY (35)
│   ├─ TP = SL × (ATR_TP_MULT ÷ ATR_SL_MULT)
│   └─ Attach SL/TP to order
│
├─► ⑨ EXECUTION
│   ├─ TEST MODE → log only
│   └─ LIVE MODE → send order to OANDA → create SL & TP orders
│
└─► ⑩ REPORT
    ├─ Telegram: MC + Trade signals
    ├─ Update cooldown state
    └─ Log complete → END RUN
```

---

## 🧠 Strategy Components

### 1. Currency Strength Ranking

> **Core directional filter** — trades follow strength momentum

- Calculates relative strength index for: **AUD, EUR, GBP, NZD, CHF, USD, JPY**
- Each pair's **gap = base_strength − quote_strength**
- **SELL** blocked if `gap > STRENGTH_SIGNAL_BLOCK_THRESHOLD (1.0)` → base too strong to sell
- **BUY** blocked if `−gap > 1.0` → quote too strong to buy
- **Goal**: avoid fighting the dominant strength trend

### 2. XGBoost ML Model

> **Confidence scoring engine**

- **Features**: ATR, MACD, RSI, ADX + derived transforms
- **Target**: Price direction TARGET_HORIZON (6) bars ahead
- **Output**: Conviction Score (0–100) + Probability %
- **Threshold**: MIN_CONVICTION_SCORE ≥ 40.0 (LEVEL10 mode)
- **Model file**: `trade_model_xgb.pkl` auto-retrained if missing

### 3. Monte Carlo Simulation

> **Volatility & regime confirmation**

- **Simulations**: 5,000 per pair
- **Confidence**: 90% price envelope
- **Regime detection**: STRONG MOMENTUM / NEUTRAL / REVERSAL
- **P_up**: Probability price rises
- **Used as**: penalty factor in signal scoring (FilterMode.PENALIZE)

### 4. Technical Indicators

> **Feature inputs + ATR risk basis**

| Indicator | Setting   | Purpose                            |
| --------- | --------- | ---------------------------------- |
| ATR       | Period 14 | Volatility measure → SL/TP sizing |
| MACD      | Standard  | Trend strength                     |
| RSI       | Standard  | Overbought/Oversold                |
| ADX       | Standard  | Trend strength filter              |

### 5. ATR-Based Dynamic SL/TP

> **Volatility-adaptive risk sizing**

```
SL Distance = MAX( ATR × 2.0 , MIN_SL_PIPS )
TP Distance = SL × (3.0 ÷ 2.0) = SL × 1.5
```

- **ATR_SL_MULT = 2.0**, **ATR_TP_MULT = 3.0** → **Risk:Reward = 1 : 1.5**
- **Minimum SL enforced**: 25 pips (non-JPY), 35 pips (JPY pairs) → avoids noise stop-outs

### 6. Dynamic TP / Trailing Management

> **In-progress trade optimization**

- **Break-even trigger**: Price moves 1.5× ATR in favor → move SL to entry
- **Trailing trigger**: Price moves 2.5× ATR → activate trailing SL
- **Trailing step**: SL trails price by 1.5× ATR
- **TP raise**: Every 15 pips gained → raise TP target
- **Max hold**: Auto-close after 12 bars without hitting TP/SL

### 7. Multi-Timeframe Confluence (Optional)

> **Higher-confidence filter**

- Require signals to align across ≥2 timeframes (15m / 1H / H4)
- Reduces false signals → fewer but higher-quality entries

### 8. Cooldown Filter

> **Avoid over-trading after closed positions**

- After a pair closes → skip for N runs
- Resets automatically when cooldown expires

### 9. Position Limit Enforcement

> **Risk cap**

- **MAX_SIMULTANEOUS_TRADES = 5** → never exceed 5 open positions
- Prevents correlated over-exposure

---

## ⚙️ Strategy Configuration Reference (`config_bot.py`)

| Category                  | Parameter                              | Value                 |
| ------------------------- | -------------------------------------- | --------------------- |
| **Mode**            | MODE                                   | LEVEL10               |
| **Conviction**      | MIN_CONVICTION_SCORE                   | 40.0                  |
| **ATR**             | ATR_SL_MULT / ATR_TP_MULT              | 2.0 / 3.0             |
| **Min SL**          | MIN_SL_PIPS / MIN_SL_PIPS_JPY          | 25 / 35               |
| **Strength Filter** | STRENGTH_SIGNAL_BLOCK_THRESHOLD        | 1.0                   |
| **Limits**          | MAX_SIMULTANEOUS_TRADES                | 5                     |
| **MC**              | SIMULATIONS / CONFIDENCE               | 5,000 / 90%           |
| **Dynamic TP**      | BE_TRIGGER / TRAIL_TRIGGER / TRAIL_ATR | 1.5× / 2.5× / 1.5× |
| **Lot Size**        | DEFAULT_LOT_SIZE                       | 10,000 units          |

---

## ✅ Signal Acceptance Checklist

A trade is ONLY opened when ALL pass:

1. ✅ Market is open
2. ✅ Not in cooldown period
3. ✅ No existing open position
4. ✅ XGBoost conviction ≥ 40.0
5. ✅ Strength gap ≤ 1.0 (direction consistent)
6. ✅ Confluence requirement met (if enabled)
7. ✅ < 5 open positions currently
8. ✅ SL distance ≥ minimum pips

---

## 📝 Example Signal Log Interpretation

```
📈 SIGNAL USDJPY=X | SELL | Score=84.9 | Prob=0.0% | SL=159.441 | TP=158.566
✅ OANDA accepted order — TradeID=5220 @ 159.094
```

- **Score 84.9** → high conviction
- **SELL** → aligned with JPY being weakest currency
- **SL/TP** → calculated from ATR 0.0747 × 2.0 = 0.1494 → capped to 35 JPY pips
- **TradeID 5220** → reference for tracking
