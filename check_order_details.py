# check_order_details.py
import sys
sys.path.insert(0, '/home/qili/ai_training_cnn/utils')
from utils.oanda_execution import api
from config import OANDA_ACCOUNT_ID_1
import oandapyV20.endpoints.trades as trades
import oandapyV20.endpoints.orders as orders

TRADE_ID = "552"

# 1. Get full trade details
r = trades.TradeDetails(OANDA_ACCOUNT_ID_1, tradeID=TRADE_ID)
trade = api.request(r)["trade"]

print("=== TRADE #552 FULL DETAILS ===")
print(f"Instrument: {trade['instrument']}")
print(f"Units: {trade['currentUnits']}")
print(f"Entry: {trade['price']}")
print(f"Tag/ID: {trade.get('clientExtensions', {}).get('id', 'NONE')}")
print(f"Comment: {trade.get('clientExtensions', {}).get('comment', 'NONE')}")
print(f"Stop Loss Order ID: {trade.get('stopLossOrderID', 'NOT_ATTACHED')}")
print(f"Take Profit Order ID: {trade.get('takeProfitOrderID', 'NOT_ATTACHED')}")

# 2. List all open orders to confirm SL/TP exist
print("\n=== ALL OPEN ORDERS ===")
r = orders.OrderList(OANDA_ACCOUNT_ID_1, params={"state": "OPEN"})
all_orders = api.request(r)["orders"]
for o in all_orders:
    if o.get("tradeID") == TRADE_ID or o.get("clientExtensions",{}).get("comment","").startswith(("SL_","TP_")):
        print(f"→ {o['type']} | Price: {o['price']} | Comment: {o.get('clientExtensions',{}).get('comment','NONE')}")