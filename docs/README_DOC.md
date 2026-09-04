
# 🤖 FX Trading Bot v6.8 — System Architecture & Strategy Documentation

---

## 📑 Table of Contents

1. [System Overview](#1-system-overview)
2. [Directory &amp; File Structure](#2-directory--file-structure)
3. [Configuration Layer](#3-configuration-layer)
4. [Data Pipeline](#4-data-pipeline)
5. [Strategy Engine — 5 Signal Modules](#5-strategy-engine--5-signal-modules)
6. [Weighted Scoring &amp; Consensus Logic](#6-weighted-scoring--consensus-logic)
7. [Entry Conditions Workflow](#7-entry-conditions-workflow)
8. [Exit &amp; Risk Management](#8-exit--risk-management)
9. [Execution &amp; Safety Guards](#9-execution--safety-guards)
10. [Tuning Guide &amp; Cheat Sheet](#10-tuning-guide--cheat-sheet)

---

## 1. System Overview

### Philosophy

> **Currency Strength First → Confirm with Indicators → ML & MC Filter → Consensus Vote → Weighted Score → Hierarchical Exit**

The bot combines **fundamental relative strength** (primary driver, 50% weight) with **technical indicators**, **XGBoost machine learning**, and **Monte Carlo probabilistic forecasting** into a unified, transparent scoring system. Decisions require **direction consensus** and **minimum conviction score** before execution.

### Core Design Principles

- ✅ **Modular & Configurable** — all knobs in `config_bot.py`
- ✅ **Weighted Transparency** — every component contributes to a traceable FINAL score
- ✅ **Defensive by Default** — multiple thresholds, position limits, duplicate protection
- ✅ **Multi-Source Validation** — ≥2 of 3 signals must agree before trading
- ✅ **OANDA-Native Execution** — SL/TP attached at order creation

---

## 2. Directory & File Structure

```
ai_training_cnn/
├── fx_trade_bot_v6.8.1.py      ← 🚀 MAIN BOT — orchestrates everything
├── config_bot.py                ← ⚙️ STRATEGY CONFIG — ALL settings + validation
├── config_oanda.py              ← 🔑 OANDA API credentials (separated)
├── config.py                    ← Legacy fallbacks
├── data_pipeline.py             ← 📊 Data fetching + Feature Engineering + ATR
├── strategy_decision.py         ← 🧠 StrategyEngine, Direction, FilterMode
├── fx_trade_bot_utils.py        ← 🛠️ Shared helpers: cooldown, positions, orders, SL/TP
├── utils/
│   ├── trading_core.py          ← Market hours, position checks
│   └── strategy_helpers.py      ← Strength matrix, formatting
├── telegram_message.py          ← ✉️ Telegram alerts
├── trade_model_xgb.pkl          ← 🤖 Pre-trained XGBoost model
├── close_all.py                 ← 🧹 Emergency close utility
├── check_order_details.py       ← 📈 P&L reporting utility
└── logs/
    └── fx_trade_bot_v6.8.log    ← Runtime log
```

---

## 3. Configuration Layer (`config_bot.py`)

### Centralized Settings Groups

| Group               | Purpose                                   |
| ------------------- | ----------------------------------------- |
| Feature & ATR       | RSI/ADX enable, ATR periods & multipliers |
| ML Model            | XGBoost horizon, lookback bars            |
| Strategy Thresholds | Score, conviction, edge                   |
| Data Sources        | Yahoo/OANDA intervals, periods            |
| Monte Carlo         | Simulations, confidence, forecast bands   |
| Risk & Execution    | Lot size, max positions, pairs list       |
| Dynamic TP          | Trailing, breakeven trigger levels        |
| Consensus           | Direction agreement rules                 |
| Weights             | S/R/A/X/M contribution percentages        |
| Portfolio Balance   | Long/Short ratio enforcement              |
| Hierarchical SL     | Multi-timeframe stop-loss zones           |
| Validation          | Auto-checks on import                     |

### ✅ Built-In Validation

- Weight sum must = **1.00 ± 0.005**
- All thresholds within sane ranges
- Warnings on unusual values
- **Halts execution** on critical errors

---

## 4. Data Pipeline

### Sources & Intervals

```
Primary: Yahoo Finance 15m bars  ← matched to bot timeframe
Fallback: OANDA API
Lookback: 200 bars per pair
```

### Feature Engineering (`data_pipeline.py`)

- **ATR(14)** — volatility normalization
- **RSI(14)** — overbought/oversold
- **ADX(14) + DI+/DI-** — trend strength detection
- **MACD** — momentum confirmation
- Normalization → 0–100 scale for consistent weighting

---

## 5. Strategy Engine — 5 Signal Modules

### 🟢 S — Currency Strength (50% Weight) — PRIMARY DRIVER

```
Logic: Rank all 7 currencies → find strongest vs weakest
Gap = Strongest.Strength − Weakest.Strength
BUY if gap ≥ +MIN_STRENGTH_GAP  (Strong Base / Weak Quote)
SELL if gap ≤ −MIN_STRENGTH_GAP
Score = normalize(gap) × 100
```

> **Why 50%?** Relative strength = fundamental flow — most reliable edge.

### 🔵 R — RSI (15% Weight)

```
Logic: RSI aligned with direction
BUY: RSI < 50 (bullish momentum)
SELL: RSI > 50 (bearish momentum)
Score = 100 − |RSI − 50|  (higher = more aligned)
```

### 🟣 A — ADX Trend Strength (15% Weight)

```
Logic: ADX = trend magnitude
ADX ≥ 25 = trending
ADX ≥ 30 = strong trend
Floor: min(ADX, 20)  ← prevents zero-score crush
Boost: ADX ≥ 30 → +10 points
Score = ADX × 2.0  ← scaled contribution
```

### 🟠 X — XGBoost ML Prediction (12% Weight)

```
Logic: Pre-trained model predicts next 6 bars
BUY if prob ≥ 0.55
SELL if prob < 0.55
Score = prob × 100
```

### 🎲 M — Monte Carlo Forecast (8% Weight)

```
Logic: 5,000 simulations → P_UP %
BUY if P_UP ≥ 55%
SELL if P_UP < 55%
Regime: STRONG MOMENTUM / NEUTRAL
Score = P_UP %
```

---

## 6. Weighted Scoring & Consensus Logic

### ⚖️ The Formula

```
FINAL = (S × 0.50) + (R × 0.15) + (A × 0.15) + (X × 0.12) + (M × 0.08)
         ↑           ↑           ↑           ↑           ↑
    Strength      RSI         ADX       XGBoost    Monte Carlo
```

### 🗳️ Direction Consensus (≥ 2 of 3)

```
Voters: Strength  |  XGBoost  |  Monte Carlo
        (BUY/SELL)  (BUY/SELL)   (BUY/SELL)

✅ TRADE only if ≥ 2 agree
❌ SKIP if split 1–1–1
```

> RSI & ADX are **scoring components only** — they boost/reduce confidence but do NOT vote on direction.

### ✅ Passing Criteria

```
FINAL Score ≥ THRESHOLD_SCORE (30)
AND Consensus ≥ 2/3
AND Strength Gap ≥ MIN_STRENGTH_GAP (0.25)
```

---

## 7. Entry Conditions Workflow

```
START
  │
  ▼
STEP 1: Currency Strength Ranking
  ├─ Rank 7 currencies
  ├─ Calculate pairwise gaps
  └─ Filter pairs with gap < MIN_GAP → SKIP
  │
  ▼
STEP 2: Technical Indicators (RSI / ADX / ATR)
  ├─ Fetch 200 bars
  ├─ Compute RSI(14), ADX(14), ATR(14)
  └─ Score alignment with direction
  │
  ▼
STEP 3: Monte Carlo Forecast
  ├─ 5,000 sims → P_UP %
  ├─ Classify regime
  └─ Score
  │
  ▼
STEP 4: XGBoost Prediction
  ├─ Load model
  ├─ Generate features
  └─ Predict bullish probability → Score
  │
  ▼
STEP 5: Consensus Vote (Strength + XGB + MC)
  ├─ ✅ ≥ 2 agree → proceed
  └─ ❌ Split → SKIP
  │
  ▼
STEP 6: Weighted FINAL Score Calculation
  ├─ S×0.50 + R×0.15 + A×0.15 + X×0.12 + M×0.08
  └─ Score < THRESHOLD (30) → SKIP
  │
  ▼
STEP 7: Position & Cooldown Check
  ├─ Already open → SKIP
  ├─ In cooldown → SKIP
  └─ MAX_OPEN reached → SKIP
  │
  ▼
STEP 8: Rank → Select Top N → EXECUTE ✅
END
```

---

## 8. Exit & Risk Management

### 🛡️ Hierarchical Stop-Loss (Priority Order)

```
1. H4 Zone Lookback  ← Higher timeframe support/resistance
2. H8 Lookback Fallback
3. Daily Lookback Fallback
4. ATR × 2.0  ← Final volatility-based
5. Fixed 35 pips absolute minimum
└─ Buffer: ±25 pips from zone | Min distance: ≥20 pips
```

### 🎯 Take-Profit

```
ATR × 3.0  ← Fixed multiple by default
TRAILING_TP = True → activates breakeven + trail
  ├─ BE Trigger: ATR × 1.5
  └─ Trail Trigger: ATR × 2.5 | Trail distance: ATR × 1.5
```

### 📊 Portfolio Balance (Optional)

```
ENFORCE_LONGS_SHORTS = True
  ├─ MIN_PER_SIDE = 1         ← At least 1 LONG + 1 SHORT
  └─ MAX_RATIO = 0.75         ← No more than 75% one side
```

---

## 9. Execution & Safety Guards

| Guard                 | Rule                            | Purpose               |
| --------------------- | ------------------------------- | --------------------- |
| Duplicate Protection  | Skip if position exists         | No double entry       |
| MAX_OPEN Limit        | Never exceed 4 positions        | Cap exposure          |
| Cooldown              | Skip recently traded pairs      | Prevent overtrading   |
| Order ID Verification | Verify SL/TP attached correctly | OANDA order integrity |
| Test Mode             | `--test-trade` = no orders    | Safe iteration        |
| Position Check        | Query OANDA before every run    | Sync state            |
| Telegram Logging      | All trades + P&L reported       | Audit trail           |

---

## 10. Tuning Guide & Cheat Sheet

### ⚙️ Quick Knobs — `config_bot.py`

| Want More Trades | Want Fewer Trades | Setting                     |
| ---------------- | ----------------- | --------------------------- |
| ↓ 0.20          | ↑ 0.40+          | `MIN_STRENGTH_GAP`        |
| ↓ 25            | ↑ 35+            | `THRESHOLD_SCORE`         |
| False            | True              | `REQUIRE_STRONG_MOMENTUM` |
| ↑ 0.60          | ↓ 0.40           | `WEIGHT_STRENGTH`         |

### 📊 Weight Matrix

| Component         | Symbol      | Weight        | Purpose                |
| ----------------- | ----------- | ------------- | ---------------------- |
| Currency Strength | **S** | **50%** | Primary driver         |
| RSI               | R           | 15%           | Momentum alignment     |
| ADX               | A           | 15%           | Trend confirmation     |
| XGBoost           | X           | 12%           | ML prediction          |
| Monte Carlo       | M           | 8%            | Probabilistic forecast |

### 🧪 How to Test Safely

```bash
# Dry run — no orders sent
python fx_trade_bot_v6.8.1.py --timeframe 15m --test-trade

# Live — sends real orders
python fx_trade_bot_v6.8.1.py --timeframe 15m --no-test-trade

# Emergency stop
python close_all.py --yes
```

---

## ✅ Summary

> **Architecture:** Modular pipeline → Rank → Score → Vote → Execute
>
> **Primary Edge:** Currency Strength (50%) → trades strongest vs weakest
>
> **Confirmation:** RSI + ADX + XGBoost + Monte Carlo → filter noise
>
> **Safety:** Consensus ≥2/3 + Score ≥30 + Hierarchical SL + Position Limits
>
> **Philosophy:** Conservative by design — trades only when multiple independent signals align → patience over frequency

---

Would you like me to save this as a proper PDF-ready Markdown file (`README_v6.8.md`) in your project directory? 📄
