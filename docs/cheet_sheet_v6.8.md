
# 📋 FX TRADE BOT v6.8 — CHEAT SHEET

> **Last Updated:** 2026-08-18 | **Status:** ✅ LOCKED & PRODUCTION-READY

---

## ⚖️ STRATEGY WEIGHTS (SUM = 1.00)

| Component            | Symbol      | Weight           | Purpose                         |
| -------------------- | ----------- | ---------------- | ------------------------------- |
| Currency Strength    | **S** | **50%** 🪝 | Primary trend / contrast anchor |
| RSI                  | **R** | 15%              | Timing filter — avoid extremes |
| ADX (Normalized ×2) | **A** | 15%              | Trend confirmation — boosted   |
| XGBoost Model        | **X** | 12%              | ML probability signal           |
| Monte Carlo          | **M** | 8%               | Regime / forecast confirmation  |

> **Formula:** `FINAL = (S×0.50) + (R×0.15) + (A×0.15) + (X×0.12) + (M×0.08)`
> **Pass Threshold:** `FINAL ≥ 35.0`

---

## 🎯 DIRECTION CONSENSUS — 2-of-3 RULE

> **REQUIRE_DIRECTION_CONSENSUS = True**
> Need **≥ 2 out of 3** sources AGREEING → TRADE OPENS

| Source      | Bullish Threshold               | How to Read in Log                  |
| ----------- | ------------------------------- | ----------------------------------- |
| Strength    | Auto-passes if gap ≥ 0.8       | `Strength=BUY`                    |
| XGBoost     | **≥ 0.55** probability   | `XGB prob=0.XX` → BUY if ≥ 0.55 |
| Monte Carlo | **≥ 55.0%** up-scenarios | `P_UP=XX.X%` → BUY if ≥ 55.0    |

> **VOTE RULE:** Each source = 1 vote. Need ≥ 2 BUY votes → PASS ✅

---

## 📊 ADX NORMALIZATION SYSTEM

> **ADX_SCALE_FACTOR = 2.0** — Raw ADX is DOUBLED

| Raw ADX         | After ×2       | Bonus System      | Final Score             |
| --------------- | --------------- | ----------------- | ----------------------- |
| 0–10           | 0–20           | 🛡️ FLOOR = 20.0 | **20.0** minimum  |
| 11–29          | 22–58          | No bonus          | Raw × 2                |
| **≥ 30** | **≥ 60** | +10.0 BOOST       | **Raw × 2 + 10** |
| ≥ 50           | ≥ 100          | Capped at 100     | **100.0** max     |

> **Example:** ADX=35 → 35×2=70 → +10 BOOST → **80.0 score**

---

## 🔍 SCORING EXAMPLE — HOW TO READ A RUN LOG

```
⚖️  SCORE USDJPY BUY
  S= 68.9 × 0.50 = 34.5  ← Strength (heaviest)
  R= 21.5 × 0.15 =  3.2  ← RSI timing
  A=100.0 × 0.15 = 15.0  ← ADX boosted to MAX
  X= 27.1 × 0.12 =  3.3  ← XGB (currently bearish)
  M= 69.6 × 0.08 =  5.6  ← MC forecast
─────────────────────────────
  FINAL = 61.5  vs THRESHOLD=35 → ✅ PASS
```

---

## 🚦 DECISION FLOW — STEP BY STEP

```
  ① Currency Strength → Calculate ALL pairs
  ↓
  ② MIN_GAP ≥ 0.8 ? → ❌ SKIP if contrast too weak
  ↓
  ③ Indicators → RSI + ADX (×2 normalized)
  ↓
  ④ Monte Carlo → P_UP % forecast
  ↓
  ⑤ XGBoost → Probability prediction
  ↓
  ⑥ Consensus → Need ≥ 2 BUY votes
  ↓
  ⑦ Weighted Score → FINAL ≥ 35 ?
  ↓
  ⑧ Rank all passed pairs → Highest score FIRST
  ↓
  ⑨ Open Top N → MAX_OPEN = 4
  ↓
  ⑩ ATR Dynamic SL/TP → SL=2×ATR | TP=3×ATR
```

---

## ⚙️ LOCKED CONFIG — DO NOT CHANGE

| Setting               | Value  |
| --------------------- | ------ |
| MIN_STRENGTH_GAP      | 0.8    |
| THRESHOLD_SCORE       | 35.0   |
| MAX_OPEN trades       | 4      |
| CONSENSUS_THRESHOLD   | 2 of 3 |
| XGB_BULLISH_THRESHOLD | 0.55   |
| MC_BULLISH_THRESHOLD  | 55.0   |
| ADX_SCALE_FACTOR      | 2.0    |
| ADX_MIN_SCORE         | 20.0   |
| ADX_BOOST_THRESHOLD   | 30.0   |
| ADX_BOOST_VALUE       | 10.0   |
| ATR_SL_MULT           | 2.0    |
| ATR_TP_MULT           | 3.0    |

---

## 📈 CURRENT BEHAVIOR — WHAT TO WATCH

> ⚠️ **XGBoost is currently CONTRARIAN** — consistently votes SELL on all BUY-strength pairs (prob ~0.20–0.35)
>
> ✅ **2/3 Rule saves the day** — Strength + MC = 2 votes → trades pass
>
> 🎯 **MC is the tie-breaker** — P_UP ≥ 55% required → filters weak forecasts
>
> 📊 **ADX is #2 driver** — high-trend pairs get boosted → higher scores

---

## 🔑 QUICK LOG CHECKLIST

```
[ ] Config Validation: ✅ ALL CHECKS PASSED
[ ] Weights: S=0.50 R=0.15 A=0.15 X=0.12 M=0.08
[ ] MC P_UP ≥ 55% → counts as BUY
[ ] XGB prob ≥ 0.55 → counts as BUY
[ ] Votes: 2/3 minimum
[ ] FINAL score ≥ 35.0
[ ] Top 4 ranked pairs opened
```

---

Would you like me to also generate a **printable PDF version** or a **reference card you can keep open side-by-side while monitoring runs**? Tap **Fast** → **Pro**.
