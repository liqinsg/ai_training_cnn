
---
# 📋 **STRATEGY FRAMEWORK — DYNAMIC ENTRY + AUTO COOLDOWN (NO ARTIFICIAL WAIT)**

## 🎯 **CORE PHILOSOPHY**
> **Don't force a fixed waiting period.** Let the market tell you when to rest:
> - ✅ **Trend still alive → keep adding / hold positions**
> - ⏸️ **Momentum fading / TP hit → pause naturally**
> - 🔄 **New setup appears → enter again immediately**
> 
> *"Cool down when the market cools down, not because the clock says so."*
---
## 📊 **FULL STRATEGY LOGIC — IN PLAIN ENGLISH**

### **1. ENTRY CONDITIONS (Must ALL be true)**

- ✅ Currency strength: **Strong currency vs Weak currency** (TopN × BottomN)
- ✅ Probability edge: **MC p_up or p_down ≥ threshold** (45%–50%)
- ✅ Trend alignment: **Price direction matches trade direction** (Uptrend=BUY, Downtrend=SELL)
- ✅ Market regime: **NOT sideways** — price must be moving clearly
- ✅ No existing position on **same pair + same direction** → prevent duplicates
- ✅ Within daily/global trade limits (`MAX_TOTAL_TRADES`, group limits)

---

### **2. DYNAMIC TP & REGIME DETECTION**

| Market State                   | How detected              | TP Multiplier             | Action                       |
| ------------------------------ | ------------------------- | ------------------------- | ---------------------------- |
| 📏**Sideways / Low Vol** | Price flat + Vol < 4%     | **1.5× ATR**       | Take profit quickly → pause |
| 📈**Normal Trend**       | Price moving + Vol 4–7%  | **2.0× ATR**       | Standard target → hold      |
| 🚀**Strong Trend**       | Price trending + Vol > 7% | **2.5× ATR**       | Let profits run → can add   |
| 🛡️**MC Safety Cap**    | Always                    | Never exceed MC 90% range | Realistic targets            |

---

### **3. THE "SMART COOLDOWN" — NO FIXED WAIT TIME**

**Instead of "wait X hours after TP", use market-based rules:**

#### ✅ **→ ALLOW RE-ENTRY IMMEDIATELY IF:**

- Trend direction **unchanged AND still strong**
- Price has **pulled back to a better entry zone**
- MC probability still **≥ threshold**
- Strength gap still **qualifies**
- → *"Trend not done yet — keep riding"*

#### ⏸️ → PAUSE / COOL DOWN AUTOMATICALLY IF:

- Price hits TP **AND** momentum **reverses**
- Market shifts to **sideways / choppy**
- Probability edge **disappears** (p_up/p_down < threshold)
- Strength gap **narrows below threshold**
- Price reaches **MC range boundary** (no more room)
- → *"Story's over — wait for new setup"*

#### 🧭 **→ RE-ENTRY ALLOWED WHEN:**

- New trend forms **in same direction**
- Currency strength **re-aligns**
- MC probability **recovers**
- → *"New story begins — trade again"*

---

### **4. POSITION MANAGEMENT RULES**

| Rule                                          | Purpose                       |
| --------------------------------------------- | ----------------------------- |
| **One position per pair per direction** | No martingale duplicates      |
| **Different pairs allowed**             | Diversify across currencies   |
| **Trend fading = no new entries**       | Don't add into weakness       |
| **TP hit + trend gone = close & pause** | Lock profit, wait             |
| **TP hit + trend strong = re-evaluate** | Consider re-entry on pullback |

---

### **5. WHAT REPLACES THE OLD "COOLDOWN"**

| Old Way (Fixed Wait)       | New Way (Dynamic — Market Decides)     |
| -------------------------- | --------------------------------------- |
| "Wait 4 hours after TP"    | "Wait until trend + probability return" |
| Misses continuation trends | ✅ Catches strong trend extensions      |
| Trades dead markets        | ✅ Stays out of chop automatically      |
| Arbitrary & rigid          | ✅ Adaptive & aligned with price action |

---

## 📝 **STRATEGY SUMMARY**

```
Currency Strength
        ↓
Monte Carlo Probability
        ↓
Trend Confirmation ← Sideways? → SKIP
        ↓
Dynamic TP based on regime
  ├─ Sideways → TP tight → take profit → pause
  ├─ Normal   → TP standard → hold → re-evaluate
  └─ Strong   → TP wider   → can add → let run
        ↓
TP Hit?
  ├─ Trend still strong → pullback → RE-ENTER
  └─ Trend gone / sideways / edge lost → PAUSE
        ↓
New trend + new edge → RESTART
```

---

### 💡 **IN ONE SENTENCE**

> **Trade when the market gives you a reason. Stop when the reason disappears. Re-enter when the market gives you a new reason. No arbitrary waiting — just follow price, follow strength, follow probability.**

---

Does this framework match what you had in mind? Once you're happy with the logic, I can turn this into code whenever you're ready. 😊
