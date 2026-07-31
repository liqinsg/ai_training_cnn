import json, time, os
from config import OANDA_ACCOUNT_ID, OANDA_ENV, OANDA_API_TOKEN, DEMO_MODE
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
        t = api.request(trades.TradesList(OANDA_ACCOUNT_ID, params={"state":"OPEN","instrument":PAIR})).get("trades",[])
        return (True,"BUY") if t and int(t[0]["currentUnits"])>0 else (True,"SELL") if t else (False,"NONE")
    except: return (False,"NONE")

def close_pos():
    try:
        [api.request(trades.TradeClose(OANDA_ACCOUNT_ID, tradeID=x["id"])) for x in api.request(trades.TradesList(OANDA_ACCOUNT_ID, params={"state":"OPEN","instrument":PAIR})).get("trades",[])]
        return True
    except: return False

def get_price():
    try: return float(api.request(InstrumentsCandles(PAIR, params={"count":1,"granularity":"M1","price":"M"}))["candles"][0]["mid"]["c"])
    except: return None

def send_order(act, p):
    dec = 5
    sl = p - RISK_PIPS*0.0001 if act=="BUY" else p + RISK_PIPS*0.0001
    tp = p + RISK_PIPS*0.0001 if act=="BUY" else p - RISK_PIPS*0.0001
    units = 10000 if act=="BUY" else -10000
    payload = {"order":{"type":"MARKET","instrument":PAIR,"units":str(units),"timeInForce":"FOK",
                "stopLossOnFill":{"price":f"{sl:.{dec}f}","timeInForce":"GTC"},
                "takeProfitOnFill":{"price":f"{tp:.{dec}f}","timeInForce":"GTC"}}}
    if DEMO_MODE: print(f"{act} OK");return True
    try: api.request(orders.OrderCreate(OANDA_ACCOUNT_ID,data=payload));print(f"{act} OK");return True
    except Exception as e: print(f"ERR:{str(e)[:60]}");return False

def clear(): os.path.exists(SIGNAL_FILE) and os.remove(SIGNAL_FILE)

clear()
has, side = get_pos()
print(f"POS:{side} | READY")

while True:
    try:
        if not os.path.exists(SIGNAL_FILE):
            time.sleep(CHECK_INTERVAL)
            continue
        cur = None
        for _ in range(5):
            try:
                with open(SIGNAL_FILE) as f: cur = json.load(f).get("signal")
                break
            except: time.sleep(0.15)
        clear()
        if not cur: continue

        has, side = get_pos()
        p = get_price()
        if not p: continue

        # --- EXACT LOGIC YOU WANT ---
        if cur == "BUY":
            # ALWAYS END WITH BUY
            if not has:
                send_order("BUY", p)
            elif side == "SELL":
                close_pos()
                time.sleep(0.3)
                p2 = get_price()
                if p2: send_order("BUY", p2)
            # Already BUY → keep, do nothing

        elif cur == "SELL":
            # ALWAYS END WITH SELL
            if not has:
                send_order("SELL", p)
            elif side == "BUY":
                close_pos()
                time.sleep(0.3)
                p2 = get_price()
                if p2: send_order("SELL", p2)
            # Already SELL → keep, do nothing

        time.sleep(0.3)
        _, new = get_pos()
        print(f"NOW POS:{new}")

    except Exception as e:
        print(f"SKIP:{e}")
        time.sleep(0.5)