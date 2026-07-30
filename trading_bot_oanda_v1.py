import json
import time
import os
from config import OANDA_ACCOUNT_ID_1, OANDA_ENV, OANDA_API_TOKEN, DEMO_MODE
import oandapyV20
from oandapyV20.endpoints import orders, trades
from oandapyV20.endpoints.instruments import InstrumentsCandles

SIGNAL_FILE = "signal.json"
PAIR = "EUR_USD"
RISK_PIPS = 15
CHECK_INTERVAL = 0.5

api = oandapyV20.API(access_token=OANDA_API_TOKEN, environment=OANDA_ENV)


def get_pos():
    try:
        t = api.request(trades.TradesList(OANDA_ACCOUNT_ID_1, params={"state": "OPEN", "instrument": PAIR})).get("trades", [])
        return (True, "BUY") if t and int(t[0]["currentUnits"]) > 0 else (True, "SELL") if t else (False, "NONE")
    except Exception as e:
        print(f"POS ERR:{str(e)[:50]}")
        return (False, "NONE")


def close_pos():
    try:
        for t in api.request(trades.TradesList(OANDA_ACCOUNT_ID_1, params={"state": "OPEN", "instrument": PAIR})).get("trades", []):
            api.request(trades.TradeClose(OANDA_ACCOUNT_ID_1, tradeID=t["id"]))
        return True
    except Exception as e:
        print(f"CLOSE ERR:{str(e)[:50]}")
        return False


def get_price():
    try:
        return float(api.request(InstrumentsCandles(PAIR, params={"count": 1, "granularity": "M1", "price": "M"}))["candles"][0]["mid"]["c"])
    except Exception as e:
        print(f"PRICE ERR:{str(e)[:50]}")
        return None


def send_order(act, p):
    dec = 5
    sl = p - RISK_PIPS * 0.0001 if act == "BUY" else p + RISK_PIPS * 0.0001
    tp = p + RISK_PIPS * 0.0001 if act == "BUY" else p - RISK_PIPS * 0.0001
    units = 10000 if act == "BUY" else -10000
    payload = {
        "order": {
            "type": "MARKET",
            "instrument": PAIR,
            "units": str(units),
            "timeInForce": "FOK",
            "stopLossOnFill": {"price": f"{sl:.{dec}f}", "timeInForce": "GTC"},
            "takeProfitOnFill": {"price": f"{tp:.{dec}f}", "timeInForce": "GTC"}
        }
    }
    if DEMO_MODE:
        print(f"DEMO {act} OK")
        return True
    try:
        api.request(orders.OrderCreate(OANDA_ACCOUNT_ID_1, data=payload))
        print(f"{act} OK")
        return True
    except Exception as e:
        print(f"ORDER ERR:{str(e)[:80]}")
        return False


def clear():
    if os.path.exists(SIGNAL_FILE):
        try:
            os.remove(SIGNAL_FILE)
        except:
            pass


clear()
has, side = get_pos()
print(f"🤖 BOT READY | POS:{side} | Waiting for signals...")

while True:
    try:
        if not os.path.exists(SIGNAL_FILE):
            time.sleep(CHECK_INTERVAL)
            continue

        # Safe read: handle atomic write + new JSON format
        cur = None
        for _ in range(5):
            try:
                with open(SIGNAL_FILE) as f:
                    data = json.load(f)
                    cur = data.get("signal")
                    conf = data.get("confidence", 0)
                    sym = data.get("symbol", "")
                break
            except:
                time.sleep(0.15)
        clear()

        if not cur or cur == "WAIT":
            time.sleep(CHECK_INTERVAL)
            continue

        print(f"\n📩 NEW SIGNAL: {cur} | {sym} | Conf:{conf:.1%}")
        has, side = get_pos()
        p = get_price()
        if not p:
            print("⚠️ No price, skip")
            continue

        # --- YOUR EXACT ENFORCEMENT LOGIC ---
        if cur == "BUY":
            if not has:
                print("→ No position → Open BUY")
                send_order("BUY", p)
            elif side == "SELL":
                print("→ Holding SELL → Close → Open BUY")
                close_pos()
                time.sleep(0.4)
                p2 = get_price()
                if p2:
                    send_order("BUY", p2)
            else:
                print("→ Already BUY → Keep")

        elif cur == "SELL":
            if not has:
                print("→ No position → Open SELL")
                send_order("SELL", p)
            elif side == "BUY":
                print("→ Holding BUY → Close → Open SELL")
                close_pos()
                time.sleep(0.4)
                p2 = get_price()
                if p2:
                    send_order("SELL", p2)
            else:
                print("→ Already SELL → Keep")

        # Verify final state
        time.sleep(0.4)
        _, new = get_pos()
        print(f"✅ FINAL POS:{new}")

    except Exception as e:
        print(f"SKIP:{str(e)[:50]}")
        time.sleep(0.5)
