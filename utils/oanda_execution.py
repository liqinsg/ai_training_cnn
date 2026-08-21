# utils/oanda_execution.py — 100% MATCHES YOUR OUTPUT
import time
from oandapyV20.endpoints.orders import OrderCreate
import oandapyV20
from config_oanda import OANDA_ACCOUNT_ID, OANDA_ENV, OANDA_API_TOKEN
from oandapyV20.endpoints.accounts import AccountSummary

api = oandapyV20.API(access_token=OANDA_API_TOKEN, environment=OANDA_ENV)

def check_oanda_account(account_id: str = None):
    try:
        r = AccountSummary(account_id)
        resp = api.request(r)
        print('✅ ACCOUNT OK:', resp['account']['id'], '—', resp['account']['currency'])
    except Exception as e:
        print('❌ FORBIDDEN / MISMATCH:', e)

# ==================================================
def execute_market_trade(signal, units_override=None):
    instrument = signal.pair_to_trade
    units = units_override if units_override is not None else 10000
    if signal.action == "SELL":
        units = -abs(units)

    decimals = 3 if "JPY" in instrument else 5

    # ✅ ALL IN ONE ORDER: MARKET + SL + TP
    entry_data = {
        "order": {
            "type": "MARKET",
            "instrument": instrument,
            "units": str(units),
            "stopLossOnFill": {
                "price": str(round(signal.stop_loss, decimals)),
                "triggerCondition": "DEFAULT"
            } if signal.stop_loss else None,
            "takeProfitOnFill": {
                "price": str(round(signal.take_profit, decimals)),
                "triggerCondition": "DEFAULT"
            } if signal.take_profit else None
        }
    }

    try:
        entry_resp = api.request(OrderCreate(accountID=OANDA_ACCOUNT_ID, data=entry_data))
        fill_tx = entry_resp.get("orderFillTransaction", {})
        filled_price = float(fill_tx.get("price", 0))
        print(f"🔹 FILLED: {signal.action} {instrument} @ {filled_price}")
        print(f"🔹 SL ATTACHED: {signal.stop_loss}")
        print(f"🔹 TP ATTACHED: {signal.take_profit}")
        return True

    except Exception as e:
        print(f"❌ FAILED {instrument}: {repr(e)[:120]}")
        return False