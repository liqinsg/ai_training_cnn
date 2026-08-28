# 🤖 FX Trading Bot v6.8.1 — Cheat Sheet

---

## ⚙️ Core Configuration

| Setting                               | Value     | Purpose                                  |
| ------------------------------------- | --------- | ---------------------------------------- |
| **MIN_STRENGTH_GAP**            | `0.35`  | Currency strength difference threshold   |
| **REQUIRE_STRONG_MOMENTUM**     | `False` | Allow NEUTRAL MC pairs (not just STRONG) |
| **MIN_CONVICTION_SCORE**        | `35.0`  | Final score threshold to trade           |
| **MAX_SIMULTANEOUS_TRADES**     | `4`     | Max open positions                       |
| **REQUIRE_DIRECTION_CONSENSUS** | `True`  | Need ≥2 of 3 signals aligned            |
| **CONSENSUS_THRESHOLD**         | `2`     | Buy/Sell votes required                  |

---

## ⚖️ Weighted Scoring Formula

```
FINAL = (S × 0.50) + (R × 0.15) + (A × 0.15) + (X × 0.12) + (M × 0.08)
         ↑           ↑           ↑           ↑           ↑
     Strength      RSI         ADX       XGBoost    Monte Carlo
```

| Component                 | Weight | Raw Range      | Notes                            |
| ------------------------- | ------ | -------------- | -------------------------------- |
| **Strength (S)**    | 50%    | gap/3.5 × 100 | Currency divergence              |
| **RSI (R)**         | 15%    | 0–100         | Overbought/Oversold alignment    |
| **ADX (A)**         | 15%    | raw × 2.0     | Floor=20, Boost @ ADX≥30 → +10 |
| **XGBoost (X)**     | 12%    | prob × 100    | Bullish threshold ≥0.55         |
| **Monte Carlo (M)** | 8%     | P_UP %         | Bullish threshold ≥55%          |

---

## 🗳️ Direction Consensus

```
Strength  → BUY if gap ≥ +0.35 | SELL if gap ≤ -0.35 | NEUTRAL
XGBoost   → BUY if prob ≥ 0.55 | SELL otherwise
Monte Carlo → BUY if P_UP ≥ 55% | SELL otherwise

✅ TRADE if ≥ 2 votes aligned  |  ❌ SKIP if split
```

---

## 🎯 Entry Conditions (ALL Must Pass)

| Check               | Rule                                                     |
| ------------------- | -------------------------------------------------------- |
| Strength Gap        | `abs(gap) ≥ MIN_STRENGTH_GAP (0.35)`                  |
| Direction Consensus | ≥ 2 of 3 agree                                          |
| Final Score         | `FINAL ≥ 35.0`                                        |
| MC Filter           | Any regime allowed (`REQUIRE_STRONG_MOMENTUM = False`) |
| Already Open        | Skip if position exists                                  |
| Cooldown            | Skip if in cooldown window                               |
| Max Open            | Skip if`≥ MAX_SIMULTANEOUS_TRADES (4)`                |

---

## 🛡️ Exit Rules (SL / TP)

| Setting           | Value                             |
| ----------------- | --------------------------------- |
| **SL Mode** | Hierarchical Zone → ATR Fallback |
| SL Buffer         | ±25 pips from zone               |
| SL Min Distance   | ≥ 20 pips                        |
| ATR SL Multiplier | × 2.0                            |
| ATR TP Multiplier | × 3.0                            |
| Trailing TP       | Enabled (`TRAILING_TP = True`)  |
| BE Trigger        | ATR × 1.5                        |
| Trail Trigger     | ATR × 2.5                        |

---

## 🔧 Quick Tuning — Common Knobs

### More Trades → Relax

```python
MIN_STRENGTH_GAP = 0.25        # ↓ from 0.35
MIN_CONVICTION_SCORE = 30       # ↓ from 35
# REQUIRE_STRONG_MOMENTUM already False ✅
```

### Fewer Trades → Tighten

```python
MIN_STRENGTH_GAP = 0.50         # ↑ from 0.35
MIN_CONVICTION_SCORE = 40       # ↑ from 35
REQUIRE_STRONG_MOMENTUM = True  # Only MC STRONG pairs
```

### Change Bias

```python
WEIGHT_STRENGTH = 0.60          # ↑ Strength
WEIGHT_MC = 0.03                # ↓ MC
```

---

## 📋 Run Commands

```bash
# Live Trade
python fx_trade_bot_v6.8.1.py --timeframe 15m --no-test-trade

# Test Mode (no orders, relaxed thresholds)
python fx_trade_bot_v6.8.1.py --timeframe 15m --test-trade

# Close All Positions
python close_all.py --yes

# Check Open Positions
python check_order_details.py
```

---

## 🐛 Common Log Messages & Meaning

| Log Message                       | Meaning              | Action                               |
| --------------------------------- | -------------------- | ------------------------------------ |
| `gap=0.xx < MIN=0.35 — SKIP`   | Divergence too weak  | Lower`MIN_STRENGTH_GAP`            |
| `NO CONSENSUS → SKIP`          | Signals split        | Lower`CONSENSUS_THRESHOLD=1`       |
| `FINAL=xx.x < 35 → FAIL`       | Score too low        | Lower`MIN_CONVICTION_SCORE`        |
| `position already open — SKIP` | Duplicate prevented  | Normal ✅                            |
| `MC regime=NEUTRAL — SKIP`     | Blocked by MC filter | Set`REQUIRE_STRONG_MOMENTUM=False` |

---

## ✅ Config Validation Checklist

```
🔍 CONFIG VALIDATION — v6.8
─────────────────────────────────────
   Weight S: 0.5000
   Weight R: 0.1500
   Weight A: 0.1500
   Weight X: 0.1200
   Weight M: 0.0800
   ── SUM: 1.0000 ✅
─────────────────────────────────────
✅ ALL CHECKS PASSED — Config OK
```

---

Would you like me to turn this into a nicely formatted PDF-ready document or an HTML dashboard reference?
