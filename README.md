
# 📘 FX Trading Bot — Full System Documentation

**Version**: v3.0 | **Updated**: 2026-08-05 | **Environment**: OANDA Demo / Live Ready

---

## 🎯 Overview

This is a rule‑based automated forex trading system that combines **currency strength analysis**, **Monte Carlo probability forecasting**, **technical pivot levels**, and **strict risk management**. It runs on a schedule, only enters high‑probability setups, and automatically attaches SL/TP to every trade.

**Core Philosophy**:

> Better miss a trade than take a bad one. Discipline over action.

---

## 🧩 System Components

| File / Module            | Purpose                                                           |
| ------------------------ | ----------------------------------------------------------------- |
| `fx_trade_bot_v3.py`   | Main engine — signals, filters, execution, reporting             |
| `fx_monte_carlo_v1.py` | Daily + H4 Monte Carlo simulation — probability & range forecast |
| `check_positions.py`   | Reusable position/order status checker                            |
| `config.py`            | Central settings — risk modes, thresholds, parameters            |
| `utils/`               | OANDA API, candle fetch, math & strategy helpers                  |
| `logs/`                | All run logs, MC reports, bot activity                            |
| `.git`                 | Version control — all changes tracked & backed up                |

---

## ⚙️ How It Works — Step by Step

### 1. Currency Strength Analysis

- Calculates relative strength across 7 majors: `JPY, AUD, EUR, NZD, CHF, GBP, USD`
- Ranks from strongest to weakest
- **Primary rule**: Only trades the **strongest currency vs weakest currency** pair
- **Strength Gap filter**: If top‑vs‑bottom gap < threshold → **no trade** (avoids ranging markets)

### 2. Monte Carlo Probability Check

- Runs **Daily (D)** and **4‑Hour (H4)** simulations (5,000 paths each)
- Outputs:
  - `p_up` / `p_down`: Probability of upward/downward move
  - `percentile_rank`: Price position within recent range
  - `90% band`: Expected high/low range
  - **Market regime**: `TREND` / `CONSOLIDATION` / `NEUTRAL`
- **Rule**: Only proceeds if edge is clear or timeframes align

### 3. Entry Filters — ALL Must Pass

- ✅ Currency strength gap ≥ configured threshold
- ✅ Up‑probability ≥ minimum required edge
- ✅ No existing position for that instrument
- ✅ Market is open
- ✅ Total open positions ≤ maximum allowed
- ✅ Per‑currency exposure limits respected

### 4. Execution & Risk Management

- **Order type**: Market order with `FOK` (Fill‑Or‑Kill)
- **SL/TP**: Calculated from pivot levels + spread buffer; **always attached**
- **Dynamic TP**: Scaled based on volatility & market regime
- **Position sizing**: Fixed per trade — no martingale, no averaging down
- **Duplicate protection**: Skips pairs already open

### 5. Reporting & Logging

- One merged Telegram message per run:
  - Mode, timestamp, orders executed
  - Full currency strength ranking
  - Pass/reject reasons for all pairs
  - Live positions + unrealized P&L
  - All attached SL/TP grouped by instrument
- Logs auto‑rotated daily to prevent disk bloat

---

## 🎚️ Risk Modes

Fully configurable in `config.py` — **no code changes required**:

| Mode              | Style        | Min Probability | Min Strength Gap | Max Open Trades |
| ----------------- | ------------ | --------------- | ---------------- | --------------- |
| **NORMAL**  | Conservative | 52%             | 7                | 2               |
| **LEVEL10** | Aggressive   | 50%             | 10               | 3               |

---

## 🕒 Scheduled Jobs

```
0 8 * * *       → Daily Monte Carlo (D timeframe)
0 */4 * * *     → Intraday Monte Carlo (H4 timeframe)
*/15 * * * *    → Trading bot full run
5 0 * * *       → Daily log rotation
```

---

## 🛡️ Safety Features

- ✅ No order if any filter fails
- ✅ SL/TP mandatory — **no unprotected trades**
- ✅ No duplicate entries
- ✅ Fails gracefully — errors logged, no crash
- ✅ All parameters centralized
- ✅ Full audit trail in Telegram + logs
- ✅ Version controlled via Git

---

## 📊 Example — Why No Trades Today

```
Strength gap = 2.41 < threshold 7
All MC probabilities within ±5%
All percentiles 45–55% → NEUTRAL / RANGE
→ No new trades — correct discipline
```

> System waits patiently until market shows a clear edge.

---

## 🚀 Usage

```bash
# Full bot run
python fx_trade_bot_v3.py

# Check positions only
python check_positions.py

# Adjust settings
nano config.py → edit → save → git commit
```

---

## 📌 Core Principles

1. **Strength first**: Always Strongest vs Weakest
2. **Probability second**: Only bet when odds favour you
3. **Filters protect**: Better miss than force
4. **SL always on**: Never enter without exit levels
5. **Consistency > frequency**: Discipline over activity

---

## ✅ Deployment Status

- ✅ Strategy logic complete & tested
- ✅ OANDA API fully compliant
- ✅ Telegram reporting integrated
- ✅ Log rotation configured
- ✅ Git backed up
- ✅ Running live on demo account

---

---

### 📁 Save this as `README.md`

```bash
# Write the file
nano README.md

# Add & commit
git add README.md
git commit -m "Add full system documentation"
git push
```

Done — now anyone (or future you) can open this file and understand exactly how the whole system works! 😊
