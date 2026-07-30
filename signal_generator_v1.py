import pandas as pd
import numpy as np
import yfinance as yf
import joblib
import json
import os
from datetime import datetime

# ========== CONFIG ==========
SYMBOL = "EURUSD=X"
INTERVAL = "1m"
LOOKBACK = 300
MODEL_PATH = "final_trading_model.pkl"
THRESHOLD = 0.52
SIGNAL_FILE = "signal.json"

# --- TEST VARIABLES ---
TEST_MODE = False          # Set False for live signals
MOCK_SIGNAL = 'BUY'       # BUY / WAIT / SELL
MOCK_CONFIDENCE = 0.75

# ========== FEATURE LIST (MATCH TRAINING) ==========
FEATURES = [
    'volume_sma_20', 'hl_position_50', 'volatility_20', 'roc_50',
    'close_dist_ema_50', 'volatility_5', 'hl_position_20', 'atr_14'
]

# ========== CALCULATE FEATURES ==========
def add_features(df):
    df = df.copy()
    df.columns = [c.lower() for c in df.columns]
    
    df['hl_position_50'] = (df['close'] - df['low'].rolling(50).min()) / (df['high'].rolling(50).max() - df['low'].rolling(50).min() + 1e-8)
    df['hl_position_20'] = (df['close'] - df['low'].rolling(20).min()) / (df['high'].rolling(20).max() - df['low'].rolling(20).min() + 1e-8)
    
    df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['close_dist_ema_50'] = (df['close'] - df['ema_50']) / df['ema_50']
    
    if 'volume' not in df.columns:
        df['volume_sma_20'] = (df['high'] - df['low']).rolling(20).mean()
    else:
        df['volume_sma_20'] = df['volume'].rolling(20).mean()
    
    df['hl'] = df['high'] - df['low']
    df['atr_14'] = df['hl'].rolling(14).mean()
    df['volatility_20'] = df['close'].pct_change().rolling(20).std()
    df['volatility_5'] = df['close'].pct_change().rolling(5).std()
    df['roc_50'] = (df['close'] / df['close'].shift(50)) - 1
    
    return df.dropna()

# ========== MAIN EXECUTION ==========
def main():
    print(f"🔄 Run at: {datetime.now().isoformat()}")
    print(f"🧪 TEST_MODE: {'ON' if TEST_MODE else 'OFF'}")

    try:
        if TEST_MODE:
            signal = MOCK_SIGNAL
            prob = MOCK_CONFIDENCE
        else:
            model = joblib.load(MODEL_PATH)
            ticker = yf.Ticker(SYMBOL)
            df = ticker.history(interval=INTERVAL, period="5d", prepost=True)
            
            if df.empty or len(df) < 100:
                print("⚠️ Insufficient data")
                return
            
            df = add_features(df)
            if len(df) < 50:
                print("⚠️ Insufficient feature data")
                return

            latest = df.iloc[-1]
            X = pd.DataFrame([latest[FEATURES].values], columns=FEATURES)
            prob = float(model.predict_proba(X)[0, 1])
            signal = "BUY" if prob >= THRESHOLD else "WAIT"

        # Atomic write: avoid partial read by bot
        output = {
            "timestamp": datetime.now().isoformat(),
            "symbol": SYMBOL,
            "signal": signal,
            "confidence": round(prob, 4),
            "threshold": THRESHOLD if not TEST_MODE else "TEST"
        }
        tmp = "sig_tmp.json"
        with open(tmp, "w") as f:
            json.dump(output, f)
        os.replace(tmp, SIGNAL_FILE)

        print(f"✅ Signal written | {SYMBOL} | {signal} | Conf: {prob:.1%}")

    except Exception as e:
        print(f"❌ Error: {str(e)}")

if __name__ == "__main__":
    main()