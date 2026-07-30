import json
from datetime import datetime

SIGNAL_FILE = "signal.json"
MAP = {"B":"BUY", "S":"SELL"}

def send(c):
    with open(SIGNAL_FILE,"w") as f:
        json.dump({"signal":MAP[c]},f)
    print("SENT")

def close_all():
    print("CLOSED")
    try:
        from config import OANDA_ACCOUNT_ID_1,OANDA_ENV,OANDA_API_TOKEN
        import oandapyV20
        from oandapyV20.endpoints import trades,orders
        api=oandapyV20.API(access_token=OANDA_API_TOKEN,environment=OANDA_ENV)
        [api.request(trades.TradeClose(OANDA_ACCOUNT_ID_1,tradeID=t["id"])) for t in api.request(trades.TradesList(OANDA_ACCOUNT_ID_1,params={"state":"OPEN"})).get("trades",[])]
        [api.request(orders.OrderCancel(OANDA_ACCOUNT_ID_1,orderID=o["id"])) for o in api.request(orders.OrderList(OANDA_ACCOUNT_ID_1,params={"state":"PENDING"})).get("orders",[])]
    except:pass

print("B=BUY S=SELL C=CLOSE Q=QUIT")
while True:
    cmd=input("> ").strip().upper()
    if cmd=="Q":break
    if cmd=="C":close_all();continue
    if cmd in MAP:send(cmd)