┌─────────────────────────────────────────────────────────────────────┐
│  🤖 START RUN — 15‑MINUTE INTERVAL                                  │
└──────────────────────────────┬──────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  1️⃣  CURRENCY STRENGTH CALCULATION                                   │
│     → Rank all 8 currencies by relative strength                    │
│     → Strongest vs Weakest = highest‑probability pair candidates     │
└──────────────────────────────┬──────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  2️⃣  AUTO‑CHECK EXISTING POSITIONS                                   │
│     For every open trade:                                            │
│       → Run ML prediction: is trend still valid?                    │
│       → If signal flips + confidence ≥ threshold → AUTO‑CLOSE        │
│       → Send Telegram alert                                         │
└──────────────────────────────┬──────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  3️⃣  SCAN ALL PAIRS — ONE BY ONE                                     │
│     Skip if already open                                            │
│     Download price data → build indicators (SMA/EMA/RSI/MACD/ADX/ATR) │
└──────────────────────────────┬──────────────────────────────────────┘
                               ▼
        ┌───────────────────────┴───────────────────────┐
        ▼                                               ▼
┌───────────────────────┐                     ┌───────────────────────┐
│  🧠 ML PREDICTION     │                     │  📊 PIVOT CALCULATION  │
│  → P_UP %             │                     │  → Get prev day HLC    │
│  → P_DOWN %           │                     │  → Calc P / R1‑3 / S1‑3│
│  → best_dir / best_p  │                     │  → Check price vs Pivot │
└───────────┬───────────┘                     └───────────┬───────────┘
            ▼                                             ▼
┌───────────────────────┐                     ┌───────────────────────┐
│  📈 ADX CHECK         │                     │  🎯 PIVOT BIAS RULE    │
│  → ADX ≥ TREND_THRESHOLD│                    │  SELL only if price < P│
│  (20=TEST / 25=LIVE)  │                     │  BUY only if price > P │
└───────────┬───────────┘                     └───────────┬───────────┘
            ▼                                             ▼
┌───────────────────────┐                     ┌───────────────────────┐
│  🧭 MONTE CARLO ALIGN │                     │  ✅ ALL 4 FILTERS PASS?│
│  → Price position vs  │────────────────────▶  1. Probability ≥ MIN  │
│    forecast range     │                     │  2. ADX ≥ threshold   │
│  → Drift direction    │                     │  3. MC Align = True  │
│  → align = True/False │                     │  4. Pivot Bias = OK   │
└───────────┬───────────┘                     └───────────┬───────────┘
            ▼                                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│  ✅ PASS → Add to CANDIDATES list                                    │
│  ❌ FAIL → Skip this pair                                            │
└──────────────────────────────┬──────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  4️⃣  RANK & LIMIT                                                    │
│     → Sort candidates HIGHEST probability FIRST                      │
│     → Apply group limits: USD group / JPY group                      │
│     → Apply total limit: MAX_TOTAL_TRADES (3=TEST / 2=LIVE)          │
└──────────────────────────────┬──────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  5️⃣  EXECUTE WINNERS                                                 │
│     → Calculate SL/TP using ATR (1.5× risk, 3.0× reward)             │
│     → Send order to OANDA                                            │
│     → Log result + Telegram message                                 │
└──────────────────────────────┬──────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  ✅ RUN COMPLETE — WAIT 15 MINUTES & REPEAT                          │
└─────────────────────────────────────────────────────────────────────┘