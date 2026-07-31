import json, time, os
from config import OANDA_ACCOUNT_ID,OANDA_ENV,OANDA_API_TOKEN,DEMO_MODE
import oandapyV20
from oandapyV20.endpoints import orders,trades
from oandapyV20.endpoints.instruments import InstrumentsCandles

SIGNAL_FILE="signal.json"
PAIR="EUR_USD"
RISK_PIPS=15
CHECK_INTERVAL=5
last="WAIT"

api=oandapyV20.API(access_token=OANDA_API_TOKEN,environment=OANDA_ENV)

def get_pos():
    try:
        t=api.request(trades.TradesList(OANDA_ACCOUNT_ID,params={"state":"OPEN","instrument":PAIR})).get("trades",[])
        return (True,"BUY") if t and int(t[0]["currentUnits"])>0 else (True,"SELL") if t else (False,"NONE")
    except:return (False,"NONE")

def close_pos():
    try:
        [api.request(trades.TradeClose(OANDA_ACCOUNT_ID,tradeID=t["id"])) for t in api.request(trades.TradesList(OANDA_ACCOUNT_ID,params={"state":"OPEN","instrument":PAIR})).get("trades",[])]
        return True
    except:return False

def get_price():
    try:
        return float(api.request(InstrumentsCandles(PAIR,params={"count":1,"granularity":"M1","price":"M"}))["candles"][0]["mid"]["c"])
    except:return None

def do_order(act,p):
    dec=3 if "JPY" in PAIR else 5
    sl=p-RISK_PIPS*0.0001; tp=p+RISK_PIPS*0.0001
    u=10000 if act=="BUY" else -10000
    pay={"order":{"type":"MARKET","instrument":PAIR,"units":str(u),"timeInForce":"FOK","stopLossOnFill":{"price":str(round(sl,dec)),"timeInForce":"GTC"},"takeProfitOnFill":{"price":str(round(tp,dec)),"timeInForce":"GTC"}}}
    if DEMO_MODE:print("OK");return True
    try:api.request(orders.OrderCreate(OANDA_ACCOUNT_ID,data=pay));print("OK");return True
    except:print("ERR");return False

def clear():os.path.exists(SIGNAL_FILE)and os.remove(SIGNAL_FILE)

clear()
has,side=get_pos()
print(f"POS:{side} | BOT READY")

while True:
    try:
        if not os.path.exists(SIGNAL_FILE):time.sleep(CHECK_INTERVAL);continue
        cur=json.load(open(SIGNAL_FILE))["signal"]
        clear()
        if cur==last:time.sleep(CHECK_INTERVAL);continue
        has,side=get_pos()
        if cur=="BUY":
            if not has:get_price() and do_order("BUY",get_price())
            elif side=="SELL":close_pos() and time.sleep(1) and get_price() and do_order("BUY",get_price())
        elif cur=="SELL":
            if not has:get_price() and do_order("SELL",get_price())
            elif side=="BUY":close_pos() and time.sleep(1) and get_price() and do_order("SELL",get_price())
        last=cur
    except:pass
    time.sleep(CHECK_INTERVAL)