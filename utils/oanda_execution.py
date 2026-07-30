from config import OANDA_ACCOUNT_ID_1, OANDA_ENV, OANDA_API_TOKEN, DEMO_MODE
from typing import Dict, Optional, List
from oandapyV20.exceptions import V20Error
import oandapyV20.endpoints.positions as positions
from oandapyV20.endpoints.instruments import InstrumentsCandles
import pandas as pd 
# import oandapyV20.endpoints.trades as trades
# import oandapyV20.endpoints.orders as orders
import yfinance as yf
from oandapyV20.endpoints import orders, trades
import oandapyV20
import sys
import os
import datetime

# Add project root to import path so config.py is found
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

api = oandapyV20.API(
    access_token=OANDA_API_TOKEN,
    environment=OANDA_ENV
)

# --------------------------
# NEW: Helper — Check Open Trades & Recent Orders
# --------------------------


def check_order_status(instrument: Optional[str] = None) -> Dict:
    """
    Show all open trades + last 10 orders.
    Filter by pair if given.
    """
    output = {"open_trades": [], "recent_orders": [], "summary": {}}

    # Open Trades
    try:
        r = trades.TradesList(OANDA_ACCOUNT_ID_1, params={"state": "OPEN"})
        resp = api.request(r)
        open_trades = resp.get("trades", [])
        if instrument:
            open_trades = [t for t in open_trades if t["instrument"] == instrument]
        output["open_trades"] = open_trades
        output["summary"]["open_count"] = len(open_trades)
    except Exception as e:
        output["summary"]["open_error"] = str(e)

    # Recent Orders (last 10)
    try:
        r = orders.OrderList(OANDA_ACCOUNT_ID_1, params={"count": 10})
        resp = api.request(r)
        orders_list = resp.get("orders", [])
        if instrument:
            orders_list = [o for o in orders_list if o["instrument"] == instrument]
        output["recent_orders"] = orders_list
        output["summary"]["order_count"] = len(orders_list)
    except Exception as e:
        output["summary"]["order_error"] = str(e)

    return output


def has_open_position(instrument: str) -> bool:
    """Return True if we already have an open trade for this pair."""
    try:
        r = trades.TradesList(OANDA_ACCOUNT_ID_1, params={"state": "OPEN", "instrument": instrument})
        resp = api.request(r)
        return len(resp.get("trades", [])) > 0
    except:
        return False


def _open_oanda_order(signal: Dict, units: Optional[float] = None, tag: str = "FX_BOT_15m") -> Dict:
    """
    Open a market order on OANDA — with custom tag/comment.
    Expected keys: pair, action, stop_loss, take_profit
    """
    if not OANDA_ACCOUNT_ID_1 or not OANDA_API_TOKEN:
        return {"status": "ERROR", "message": "Missing OANDA credentials"}

    pair_raw = signal.get("pair")
    if not pair_raw:
        return {"status": "ERROR", "message": "Signal missing 'pair'"}

    pair = pair_raw.replace("_", "/")
    action = signal.get("action")
    if action not in {"BUY", "SELL"}:
        return {"status": "ERROR", "message": "Signal 'action' must be BUY or SELL"}

    sl_raw = signal.get("stop_loss")
    tp_raw = signal.get("take_profit")
    if sl_raw is None or tp_raw is None:
        return {"status": "ERROR", "message": "Signal missing stop_loss or take_profit"}

    try:
        sl = float(sl_raw)
        tp = float(tp_raw)
    except (TypeError, ValueError):
        return {"status": "ERROR", "message": "stop_loss/take_profit must be numeric"}

    default_units = 10000
    position_units = default_units if units is None else units
    position_units = float(position_units)
    if action == "SELL":
        position_units = -abs(position_units)

    # ✅ Added clientExtensions for TAG/COMMENT
    order_payload = {
        "order": {
            "type": "MARKET",
            "instrument": pair,
            "units": str(int(position_units)),
            "timeInForce": "FOK",
            "positionFill": "DEFAULT",
            # ✅ Correct field names OANDA expects
            "clientExtensions": {
                "id": tag,
                "comment": tag
            },
            "stopLossOnFill": {
                "price": str(round(sl, 5)),
                "timeInForce": "GTC",
                "clientExtensions": {"comment": f"SL_{tag}"}
            },
            "takeProfitOnFill": {
                "price": str(round(tp, 5)),
                "timeInForce": "GTC",
                "clientExtensions": {"comment": f"TP_{tag}"}
            },
        }
    }
    try:
        print(f"\n[OANDA EXEC] [{tag}] Sending {action} order for {pair}...")
        print(f"  Units: {abs(int(position_units))} | SL: {sl:.5f} | TP: {tp:.5f}")

        request = orders.OrderCreate(OANDA_ACCOUNT_ID_1, data=order_payload)
        response = api.request(request)

        fill = response["orderFillTransaction"]
        result = {
            "status": "SUCCESS",
            "order_id": fill.get("id", "unknown"),
            "filled_price": fill.get("price", "unknown"),
            "instrument": fill.get("instrument", pair),
            "units": fill.get("units", str(int(position_units))),
            "tag": tag,
            "sl_set": fill.get("stopLossOnFill", {}).get("price", "NOT_SET"),
            "tp_set": fill.get("takeProfitOnFill", {}).get("price", "NOT_SET"),
            "time": fill.get("time", "unknown"),
        }

        print(f"[OANDA EXEC] ✅ [{tag}] Filled: {result['order_id']} @ {result['filled_price']}")
        return result

    except V20Error as e:
        error_msg = f"OANDA API Error: {e}"
        print(f"[OANDA EXEC] ❌ {error_msg}")
        return {"status": "ERROR", "message": error_msg, "tag": tag}
    except Exception as e:
        print(f"[OANDA EXEC] ⚠️ Parsing error — checking if order filled anyway...")
        try:
            trades_resp = api.request(trades.TradesList(OANDA_ACCOUNT_ID_1))
            recent = [t for t in trades_resp.get("trades", []) if t["instrument"] == pair]
            if recent:
                print(f"[OANDA EXEC] ✅ [{tag}] Found trade {recent[0]['id']}")
                return {
                    "status": "SUCCESS",
                    "order_id": recent[0]["id"],
                    "filled_price": recent[0]["price"],
                    "instrument": recent[0]["instrument"],
                    "units": recent[0]["currentUnits"],
                    "tag": tag,
                    "sl_set": "CHECK_API",
                    "tp_set": "CHECK_API",
                    "time": recent[0]["time"],
                }
        except:
            pass
        error_msg = f"Unexpected Error: {str(e)}"
        print(f"[OANDA EXEC] ❌ {error_msg}")
        return {"status": "ERROR", "message": error_msg, "tag": tag}


def open_oanda_order(signal: Dict, units: Optional[float] = None, tag: str = "FX_BOT_15m") -> Dict:
    """
    Open a market order on OANDA — with custom tag/comment & pivot‑based SL/TP.
    Expected keys: pair, action, stop_loss, take_profit
    Automatically uses correct decimal precision for JPY vs non‑JPY pairs.
    """
    if not OANDA_ACCOUNT_ID_1 or not OANDA_API_TOKEN:
        return {"status": "ERROR", "message": "Missing OANDA credentials"}

    pair_raw = signal.get("pair")
    if not pair_raw:
        return {"status": "ERROR", "message": "Signal missing 'pair'"}

    # Keep OANDA native format (no underscore swap needed)
    pair = pair_raw
    action = signal.get("action")
    if action not in {"BUY", "SELL"}:
        return {"status": "ERROR", "message": "Signal 'action' must be BUY or SELL"}

    sl_raw = signal.get("stop_loss")
    tp_raw = signal.get("take_profit")
    if sl_raw is None or tp_raw is None:
        return {"status": "ERROR", "message": "Signal missing stop_loss or take_profit"}

    try:
        sl = float(sl_raw)
        tp = float(tp_raw)
    except (TypeError, ValueError):
        return {"status": "ERROR", "message": "stop_loss/take_profit must be numeric"}

    # Auto‑detect precision: 3 decimals for JPY, 5 for all others
    decimals = 3 if "JPY" in pair else 5

    default_units = 10000
    position_units = default_units if units is None else units
    position_units = float(position_units)
    if action == "SELL":
        position_units = -abs(position_units)

    # ✅ Correct OANDA payload with proper rounding
    order_payload = {
        "order": {
            "type": "MARKET",
            "instrument": pair,
            "units": str(int(position_units)),
            "timeInForce": "FOK",
            "positionFill": "DEFAULT",
            "clientExtensions": {
                "id": tag,
                "comment": tag
            },
            "stopLossOnFill": {
                "price": str(round(sl, decimals)),
                "timeInForce": "GTC",
                "clientExtensions": {"comment": f"SL_{tag}"}
            },
            "takeProfitOnFill": {
                "price": str(round(tp, decimals)),
                "timeInForce": "GTC",
                "clientExtensions": {"comment": f"TP_{tag}"}
            },
        }
    }

    try:
        print(f"\n[OANDA EXEC] [{tag}] Sending {action} order for {pair}...")
        print(f"  Units: {abs(int(position_units))} | SL: {sl:.{decimals}f} | TP: {tp:.{decimals}f}")

        request = orders.OrderCreate(OANDA_ACCOUNT_ID_1, data=order_payload)
        response = api.request(request)

        fill = response["orderFillTransaction"]
        # result = {
        #     "status": "SUCCESS",
        #     "order_id": fill.get("id", "unknown"),
        #     "filled_price": fill.get("price", "unknown"),
        #     "instrument": fill.get("instrument", pair),
        #     "units": fill.get("units", str(int(position_units))),
        #     "tag": tag,
        #     "sl_set": fill.get("stopLossOnFill", {}).get("price", "NOT_SET"),
        #     "tp_set": fill.get("takeProfitOnFill", {}).get("price", "NOT_SET"),
        #     "time": fill.get("time", "unknown"),
        # }
        result = {
            "status": "SUCCESS",
            "order_id": fill.get("id", "unknown"),
            "filled_price": fill.get("price", "unknown"),
            "instrument": fill.get("instrument", pair),
            "units": fill.get("units", str(int(position_units))),
            "tag": tag,
            "sl_set": f"{round(sl, decimals)} ✅",
            "tp_set": f"{round(tp, decimals)} ✅",
            "time": fill.get("time", "unknown"),
        }

        print(f"[OANDA EXEC] ✅ [{tag}] Filled: {result['order_id']} @ {result['filled_price']}")
        return result

    except V20Error as e:
        error_msg = f"OANDA API Error: {e}"
        print(f"[OANDA EXEC] ❌ {error_msg}")
        return {"status": "ERROR", "message": error_msg, "tag": tag}

    except Exception as e:
        print(f"[OANDA EXEC] ⚠️ Parsing error — checking if order filled anyway...")
        try:
            trades_resp = api.request(trades.TradesList(OANDA_ACCOUNT_ID_1))
            recent = [t for t in trades_resp.get("trades", []) if t["instrument"] == pair]
            if recent:
                print(f"[OANDA EXEC] ✅ [{tag}] Found trade {recent[0]['id']}")
                return {
                    "status": "SUCCESS",
                    "order_id": recent[0]["id"],
                    "filled_price": recent[0]["price"],
                    "instrument": recent[0]["instrument"],
                    "units": recent[0]["currentUnits"],
                    "tag": tag,
                    "sl_set": recent[0].get("stopLossOrderID", "CHECK_API"),
                    "tp_set": recent[0].get("takeProfitOrderID", "CHECK_API"),
                    "time": recent[0]["time"],
                }
        except Exception as e2:
            print(f"[OANDA EXEC] ❌ Fallback check also failed: {e2}")

        error_msg = f"Unexpected Error: {str(e)}"
        print(f"[OANDA EXEC] ❌ {error_msg}")
        return {"status": "ERROR", "message": error_msg, "tag": tag}


def close_all_trades() -> Dict:
    """Helper: Close all open trades on your account"""
    try:
        request = trades.TradesList(OANDA_ACCOUNT_ID_1)
        open_trades = api.request(request).get("trades", [])
        if not open_trades:
            return {"status": "INFO", "message": "No open trades found"}

        results = []
        for trade in open_trades:
            req = trades.TradeClose(OANDA_ACCOUNT_ID_1, tradeID=trade["id"])
            api.request(req)
            results.append({"trade_id": trade["id"], "closed": True})
            print(f"[CLEANUP] Closed trade ID: {trade['id']}")

        return {"status": "SUCCESS", "closed_trades": results}

    except Exception as e:
        return {"status": "ERROR", "message": str(e)}


def get_oanda_candles(instrument, timeframe, count=500):
    """Fetch historical candles directly from OANDA — matches your execution prices exactly"""
    TF_MAP = {
        "1m": "M1", "5m": "M5", "15m": "M15", "30m": "M30",
        "1h": "H1", "4h": "H4", "D": "D", "1d": "D"
    }
    oanda_tf = TF_MAP.get(timeframe, timeframe)

    try:
        resp = api.request(InstrumentsCandles(
            instrument=instrument,
            params={"count": count, "granularity": oanda_tf, "price": "M"}
        ))
        rows = []
        times = []
        for c in resp["candles"]:
            times.append(pd.to_datetime(c["time"]))
            rows.append({
                "Open": float(c["mid"]["o"]),
                "High": float(c["mid"]["h"]),
                "Low": float(c["mid"]["l"]),
                "Close": float(c["mid"]["c"]),
                "Volume": 0  # ✅ Add dummy volume — OANDA doesn't provide it
            })
        df = pd.DataFrame(rows, index=times)
        df.index = df.index.tz_convert(None)
        return df

    except Exception as e:
        print(f"⚠️ OANDA data failed for {instrument}: {str(e)} — falling back to yfinance")
        try:
            yf_symbol = instrument.replace("_", "") + "=X"
            df = yf.download(yf_symbol, period="30d", interval=timeframe, progress=False)
            df.columns = [c[0] for c in df.columns]
            return df[["Open", "High", "Low", "Close", "Volume"]]
        except Exception as e2:
            print(f"❌ Fallback also failed for {instrument}: {str(e2)}")
            return pd.DataFrame()


# --------------------------
# MARKET OPEN CHECK
# --------------------------
def is_forex_market_open():
    """Check if Forex market is open (UTC time)
    Open: Mon 00:00 → Sat 21:00 UTC
    Closed: Sat 21:00 → Mon 00:00 UTC
    """
    now = datetime.datetime.utcnow()
    weekday = now.weekday()  # 0=Mon, 4=Fri, 5=Sat, 6=Sun
    hour = now.hour

    # Weekend closed
    if weekday == 6:  # Sunday all day
        return False
    if weekday == 5 and hour >= 21:  # Saturday after 21:00 UTC
        return False
    if weekday == 0 and hour < 0:  # Monday before 00:00 UTC
        return False

    return True

# Exit immediately if market is closed
if not is_forex_market_open():
    print("⏸️ Market is closed — skipping run")
    raise SystemExit(0)


# --------------------------
# 🧪 TEST — Order + Status Check
# --------------------------
if __name__ == "__main__":
    print("=" * 60)
    print("🧪 TEST: TAG + STATUS CHECK")
    print("=" * 60)

    # 1. Check status FIRST
    print("\n📋 CURRENT STATUS:")
    status = check_order_status("EUR_USD")
    print(f"Open trades: {status['summary']['open_count']}")
    print(f"Recent orders: {status['summary']['order_count']}")

    # 2. Test order WITH TAG
    test_signal = {
        "pair": "EUR_USD",
        "action": "SELL",
        "stop_loss": 1.1450,
        "take_profit": 1.1350
    }
    print("\n📤 Sending test order with tag...")
    res = open_oanda_order(test_signal, tag="FX_BOT_SHORT_15m")
    print(f"Result: {res}")

    # 3. Check again
    print("\n📋 STATUS AFTER ORDER:")
    status2 = check_order_status("EUR_USD")
    print(f"Open trades: {status2['summary']['open_count']}")
    if status2["open_trades"]:
        print(f"Trade tag: {status2['open_trades'][0].get('clientExtensions', {}).get('comment', 'NONE')}")
