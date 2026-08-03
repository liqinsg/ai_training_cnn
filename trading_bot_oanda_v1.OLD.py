import time
import pandas as pd
import numpy as np
import yfinance as yf
import joblib
from datetime import datetime
from config import OANDA_ACCOUNT_ID_3, OANDA_ENV, OANDA_API_TOKEN, DEMO_MODE
import oandapyV20
from oandapyV20.endpoints import orders, trades
from oandapyV20.endpoints.instruments import InstrumentsCandles
from utils.oanda_execution import is_forex_market_open

# Exit immediately if market is closed
forex_market_open = is_forex_market_open
print(forex_market_open)
if not is_forex_market_open():
    print("⏸️ Market is closed — skipping run")
    raise SystemExit(0)

# ========== CONFIG ==========
SYMBOL = "EURUSD=X"
PAIR = "EUR_USD"
INTERVAL = "1m"
MODEL_PATH = "final_trading_model.pkl"
THRESHOLD = 0.52
RISK_PIPS = 15
MONTE_CARLO_RUNS = 50

FEATURES = [
    'volume_sma_20', 'hl_position_50', 'volatility_20', 'roc_50',
    'close_dist_ema_50', 'volatility_5', 'hl_position_20', 'atr_14'
]

TEST_MODE = False
MOCK_SIGNAL = "BUY"
MOCK_CONFIDENCE = 0.75

# ========== INIT ==========
api = oandapyV20.API(access_token=OANDA_API_TOKEN, environment=OANDA_ENV)
last_executed = None
model = None if TEST_MODE else joblib.load(MODEL_PATH)
print(f"🤖 SINGLE-RUN BOT | MC_RUNS:{MONTE_CARLO_RUNS}")

# ========== HELPERS ==========
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

def get_pos():
    try:
        t = api.request(trades.TradesList(OANDA_ACCOUNT_ID_3, params={"state":"OPEN","instrument":PAIR})).get("trades",[])
        return (True,"BUY") if t and int(t[0]["currentUnits"])>0 else (True,"SELL") if t else (False,"NONE")
    except Exception as e:
        print(f"POS ERR:{str(e)[:50]}")
        return (False,"NONE")

def close_pos():
    try:
        for t in api.request(trades.TradesList(OANDA_ACCOUNT_ID_3, params={"state":"OPEN","instrument":PAIR})).get("trades",[]):
            api.request(trades.TradeClose(OANDA_ACCOUNT_ID_3, tradeID=t["id"]))
        return True
    except Exception as e:
        print(f"CLOSE ERR:{str(e)[:50]}")
        return False

def get_price():
    try:
        return float(api.request(InstrumentsCandles(PAIR, params={"count":1,"granularity":"M1","price":"M"}))["candles"][0]["mid"]["c"])
    except Exception as e:
        print(f"PRICE ERR:{str(e)[:50]}")
        return None

def send_order(act, p):
    dec = 5
    sl = p - RISK_PIPS*0.0001 if act=="BUY" else p + RISK_PIPS*0.0001
    tp = p + RISK_PIPS*0.0001 if act=="BUY" else p - RISK_PIPS*0.0001
    units = 10000 if act=="BUY" else -10000
    payload = {"order":{"type":"MARKET","instrument":PAIR,"units":str(units),"timeInForce":"FOK",
                "stopLossOnFill":{"price":f"{sl:.{dec}f}","timeInForce":"GTC"},
                "takeProfitOnFill":{"price":f"{tp:.{dec}f}","timeInForce":"GTC"}}}
    if DEMO_MODE: print(f"DEMO {act} OK");return True
    try: api.request(orders.OrderCreate(OANDA_ACCOUNT_ID_3,data=payload));print(f"{act} OK");return True
    except Exception as e: print(f"ORDER ERR:{str(e)[:80]}");return False

# ========== RUN ONCE & EXIT ==========
def main():
    cur_signal = None
    mean_prob = 0.0
    mc_min = mc_max = 0.0

    try:
        print(f"\n🔄 RUN @ {datetime.now().strftime('%H:%M:%S')}")

        if TEST_MODE:
            cur_signal = MOCK_SIGNAL
            mean_prob = MOCK_CONFIDENCE
            mc_min = mc_max = mean_prob
        else:
            df = yf.Ticker(SYMBOL).history(interval=INTERVAL, period="5d", prepost=True)
            if df.empty or len(df) < 100:
                print("⚠️ Not enough data")
                return
            df = add_features(df)
            if len(df) < 50:
                print("⚠️ Not enough features")
                return
            X = pd.DataFrame([df.iloc[-1][FEATURES].values], columns=FEATURES)
            probs = [float(model.predict_proba(X)[0,1]) for _ in range(MONTE_CARLO_RUNS)]
            mean_prob = float(np.mean(probs))
            mc_min, mc_max = float(np.min(probs)), float(np.max(probs))
            cur_signal = "BUY" if mean_prob >= THRESHOLD else "WAIT"

        print(f"📊 SIGNAL: {cur_signal} | MEAN_CONF:{mean_prob:.1%} | MC_RANGE:{mc_min:.1%}–{mc_max:.1%}")

        if not cur_signal or cur_signal == "WAIT":
            print("⏸ No action needed")
            return

        print(f"\n⚡ EXECUTE: {cur_signal}")
        has, side = get_pos()
        p = get_price()
        if not p:
            print("⚠️ No price")
            return

        if cur_signal == "BUY":
            if not has:
                print("→ Open BUY")
                send_order("BUY", p)
            elif side == "SELL":
                print("→ Close SELL → Open BUY")
                close_pos()
                time.sleep(0.4)
                p2 = get_price()
                if p2: send_order("BUY", p2)
            else:
                print("→ Already BUY — keep")

        elif cur_signal == "SELL":
            if not has:
                print("→ Open SELL")
                send_order("SELL", p)
            elif side == "BUY":
                print("→ Close BUY → Open SELL")
                close_pos()
                time.sleep(0.4)
                p2 = get_price()
                if p2: send_order("SELL", p2)
            else:
                print("→ Already SELL — keep")

        time.sleep(0.4)
        _, new = get_pos()
        print(f"✅ DONE | FINAL POS:{new}\n" + "="*60)

    except Exception as e:
        print(f"❌ ERR:{str(e)[:60]}")

if __name__ == "__main__":
    main()