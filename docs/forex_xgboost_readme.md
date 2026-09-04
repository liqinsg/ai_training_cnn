Raw OHLCV Data
      ↓
[Feature Engineer] → 50+ technical indicators
      ↓
[Regime Detector] → "Long" or "Short" trend
      ↓
[Label Generator] → "Would this bar have been a winner?"
      ↓
[Walk-Forward XGBoost] → Trained model
      ↓
[Live Data] → Features computed → Model predicts probability
      ↓
Probability ≥ 0.6? → YES → [Risk Manager] → Execute Trade
                     NO  → Wait for next bar
