import numpy as np
import pandas as pd
import yfinance as yf
import json
from datetime import datetime
from pathlib import Path
from lightgbm import LGBMClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, roc_auc_score
import pandas_ta as ta

# --------------------------
# Settings — match your workflow
# --------------------------
PAIR = "EURUSD=X"
PERIOD = "5y"
INTERVAL = "1d"
FORECAST_HORIZON = 3
JSON_FILE = Path.home() / "ai_training_cnn" / "daily_results" / f"fx_daily_{datetime.utcnow().strftime('%Y%m%d')}.json"

# --------------------------
# 1. Load Monte Carlo data from saved JSON
# --------------------------
mc_features = {}
if JSON_FILE.exists():
    try:
        with open(JSON_FILE) as f:
            mc_data = json.load(f)
        # Handle list or single entry
        entry = mc_data[0] if isinstance(mc_data, list) else mc_data
        if entry.get("symbol") == PAIR:
            mc_features["ann_vol"] = entry["ann_vol"]
            mc_features["ann_drift"] = entry["ann_drift"]
            mc_features["range_low"] = entry["range_90"][0]
            mc_features["range_high"] = entry["range_90"][1]
            print(f"✅ Loaded Monte Carlo data from: {JSON_FILE.name}")
    except Exception as e:
        print(f"⚠️ Could not load JSON: {e} — running without MC features")
else:
    print(f"⚠️ No JSON found at {JSON_FILE.name} — run fx_daily_view.py first")

# --------------------------
# 2. Get price data + build standard features
# --------------------------
df = yf.download(PAIR, period=PERIOD, interval=INTERVAL, progress=False)
df.columns = [col[0] for col in df.columns]
df = df[["Open", "High", "Low", "Close", "Volume"]].copy()

# Target: 1=UP, 0=DOWN
future_return = df["Close"].shift(-FORECAST_HORIZON) / df["Close"] - 1
df["target"] = np.where(future_return > 0, 1, 0)

# Technical features
df["return"] = df["Close"].pct_change()
df["sma_20"] = ta.sma(df["Close"], length=20)
df["sma_50"] = ta.sma(df["Close"], length=50)
df["rsi"] = ta.rsi(df["Close"], length=14)
macd = ta.macd(df["Close"])
df = pd.concat([df, macd], axis=1)
bb = ta.bbands(df["Close"])
df = pd.concat([df, bb], axis=1)
df["vol_20"] = df["return"].rolling(20).std() * np.sqrt(252)
df["high_low"] = (df["High"] - df["Low"]) / df["Close"]
df["close_open"] = (df["Close"] - df["Open"]) / df["Open"]

# --------------------------
# 3. Add Monte Carlo derived features
# --------------------------
if mc_features:
    # Static MC values applied to all rows
    df["mc_vol"] = mc_features["ann_vol"]
    df["mc_drift"] = mc_features["ann_drift"]
    # Where is price relative to today's 90% range?
    rng = mc_features["range_high"] - mc_features["range_low"]
    df["mc_range_pos"] = (df["Close"] - mc_features["range_low"]) / rng

# --------------------------
# 4. Clean & prepare
# --------------------------
df = df.dropna()
print(f"✅ Valid samples: {len(df)}")

features = [c for c in df.columns if c not in ["Open","High","Low","Close","Volume","target"]]
print(f"🔧 Total features: {len(features)} ({' + '.join(features)})")

# --------------------------
# 5. Train model
# --------------------------
X = df[features]
y = df["target"].astype(int)

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, shuffle=False
)

model = LGBMClassifier(
    n_estimators=200,
    max_depth=3,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.8,
    objective="binary",
    random_state=42,
    verbose=-1
)
model.fit(X_train, y_train)

# --------------------------
# 6. Evaluate
# --------------------------
preds = model.predict(X_test)
probs = model.predict_proba(X_test)[:, 1]
print(f"\n📊 Accuracy: {accuracy_score(y_test, preds):.1%}")
print(f"📊 ROC‑AUC:  {roc_auc_score(y_test, probs):.3f}")
print("\n🔝 Top Features:")
fi = pd.Series(model.feature_importances_, index=features).sort_values(ascending=False)
print(fi.head(10).to_string())

# --------------------------
# 7. Final signal
# --------------------------
latest = X.iloc[-1:]
p_up = model.predict_proba(latest)[0, 1]
p_down = 1 - p_up
print(f"\n🚀 {PAIR} | {FORECAST_HORIZON}d outlook:")
print(f"   Prob UP:   {p_up:.1%}")
print(f"   Prob DOWN: {p_down:.1%}")
print(f"   Signal:    {'🟢 BIAS UP' if p_up > 0.6 else '🔴 BIAS DOWN' if p_down > 0.6 else '⚪ NEUTRAL'}")
