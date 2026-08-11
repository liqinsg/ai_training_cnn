import pandas as pd
import numpy as np
import yfinance as yf
import joblib
import json
import time
from datetime import datetime

# ========== CONFIG ==========
SYMBOL = "EURUSD=X"
INTERVAL = "1m"
LOOKBACK = 300
MODEL_PATH = "final_trading_model.pkl"
THRESHOLD = 0.52
SIGNAL_FILE = "signal.json"

# --- NEW TEST VARIABLES ---
TEST_MODE = True       # Set False for real live signals
MOCK_SIGNAL = 'BUY'       # Use 'BUY' / 'WAIT' / 'SELL' to test logic
MOCK_CONFIDENCE = 0.75    # Fixed confidence for testing

# ========== FEATURE LIST (EXACTLY SAME AS TRAINING) ==========
FEATURES = [
    'volume_sma_20', 'hl_position_50', 'volatility_20', 'roc_50',
    'close_dist_ema_50', 'volatility_5', 'hl_position_20', 'atr_14'
]

# ========== HELPER: CALCULATE FEATURES SAFELY ==========
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

# ========== MAIN LOOP ==========
print("🔄 Signal Generator Starting...")
print(f"🧪 TEST MODE: {'ON' if TEST_MODE else 'OFF'}")
if TEST_MODE:
    print(f"📤 MOCK SIGNAL: {MOCK_SIGNAL} | Conf: {MOCK_CONFIDENCE:.1%}")
else:
    model = joblib.load(MODEL_PATH)
    print(f"✅ Model loaded | Threshold: {THRESHOLD}")
print("="*60)

while True:
    try:
        # --------------------------
        # TEST MODE: Send fixed mock signal
        # --------------------------
        if TEST_MODE:
            signal = MOCK_SIGNAL
            prob = MOCK_CONFIDENCE
        
        # --------------------------
        # LIVE MODE: Real data + model
        # --------------------------
        else:
            ticker = yf.Ticker(SYMBOL)
            df = ticker.history(interval=INTERVAL, period="5d", prepost=True)
            
            if df.empty or len(df) < 100:
                print("⚠️ Not enough data, retrying...")
                time.sleep(15)
                continue

            df = add_features(df)
            if len(df) < 50:
                print("⚠️ Not enough data after feature calc, retrying...")
                time.sleep(15)
                continue

            latest = df.iloc[-1]
            X = pd.DataFrame([latest[FEATURES].values], columns=FEATURES)
            prob = float(model.predict_proba(X)[0, 1])
            signal = "BUY" if prob >= THRESHOLD else "WAIT"

        # --------------------------
        # Write signal (same format for both modes)
        # --------------------------
        output = {
            "timestamp": datetime.now().isoformat(),
            "symbol": SYMBOL,
            "signal": signal,
            "confidence": round(prob, 4),
            "threshold": THRESHOLD if not TEST_MODE else "TEST"
        }
        with open(SIGNAL_FILE, "w") as f:
            json.dump(output, f)

        print(f"[{output['timestamp']}] {'[TEST]' if TEST_MODE else '[LIVE]'} {SYMBOL} | Signal: {signal} | Conf: {prob:.1%}")

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()

    time.sleep(30)