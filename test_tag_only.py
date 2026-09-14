"""
Minimal OANDA TAG test

1. Use API / environment / token from config_oanda.py
2. Open ONE MARKET GBP_JPY trade with clientExtensions.tag/comment
3. Print the raw OANDA response
4. DO NOT close the trade

Practice/demo only.
"""

import sys
import pprint

import config_oanda
import oandapyV20.endpoints.orders as oanda_orders
from oandapyV20.exceptions import V20Error


# ─────────────────────────────────────────────
# Config — everything from config_oanda.py
# ─────────────────────────────────────────────

OANDA_ENV = config_oanda.OANDA_ENV
API = config_oanda.api

# Profile 2 — same account used in the previous E2E test
ACCOUNT_ID = config_oanda.OANDA_ACCOUNT_ID_2


# ─────────────────────────────────────────────
# Safety
# ─────────────────────────────────────────────

if OANDA_ENV in ("live", "real"):
    print("❌ ABORT — LIVE ENVIRONMENT DETECTED.")
    sys.exit(1)

if OANDA_ENV not in ("practice", "demo"):
    print(f"❌ ABORT — INVALID OANDA_ENV={OANDA_ENV}")
    sys.exit(1)


if not ACCOUNT_ID:
    print("❌ ABORT — OANDA_ACCOUNT_ID_2 is empty.")
    sys.exit(1)


# ─────────────────────────────────────────────
# Test parameters
# ─────────────────────────────────────────────

INSTRUMENT = "GBP_JPY"
UNITS = 10000

SL = "204.80"
TP = "213.30"

TAG = "TAG-TEST-20260914"
COMMENT = "COMMENT-TEST-20260914"


# ─────────────────────────────────────────────
# Display
# ─────────────────────────────────────────────

print("=" * 70)
print("🧪 MINIMAL OANDA TAG TEST")
print("=" * 70)

print(f"ENVIRONMENT : {OANDA_ENV}")
print(f"ACCOUNT     : {ACCOUNT_ID}")
print(f"INSTRUMENT  : {INSTRUMENT}")
print(f"UNITS       : {UNITS}")
print(f"TAG         : {TAG}")
print(f"COMMENT     : {COMMENT}")
print("=" * 70)


# ─────────────────────────────────────────────
# Order
# ─────────────────────────────────────────────

order = {
    "order": {
        "type": "MARKET",
        "instrument": INSTRUMENT,
        "units": str(UNITS),
        "positionFill": "DEFAULT",

        "clientExtensions": {
            "tag": TAG,
            "comment": COMMENT,
        },

        "stopLossOnFill": {
            "price": SL,
            "timeInForce": "GTC",
        },

        "takeProfitOnFill": {
            "price": TP,
            "timeInForce": "GTC",
        },
    }
}


print("\n🔵 Sending MARKET order...")

print("\nREQUEST:")
pprint.pp(order, width=140)


# ─────────────────────────────────────────────
# Execute
# ─────────────────────────────────────────────

try:
    resp = API.request(
        oanda_orders.OrderCreate(
            ACCOUNT_ID,
            data=order,
        )
    )

    print("\n✅ ORDER ACCEPTED / FILLED")
    print("=" * 70)
    print("RAW OANDA RESPONSE")
    print("=" * 70)

    pprint.pp(resp, width=160)

    # ─────────────────────────────────────────
    # Extract trade
    # ─────────────────────────────────────────

    fill = resp.get("orderFillTransaction", {})
    trade_opened = fill.get("tradeOpened", {})

    trade_id = trade_opened.get("tradeID")

    print("\n" + "=" * 70)
    print("🔎 RESULT")
    print("=" * 70)

    print(f"Trade ID : {trade_id}")

    print("\nclientExtensions returned by tradeOpened:")
    pprint.pp(
        trade_opened.get("clientExtensions"),
        width=140,
    )

    print("\n" + "=" * 70)
    print("⚠️ TRADE IS LEFT OPEN")
    print("=" * 70)

    print("\nNow run:")
    print("    python check_order_details.py")

    print("\nExpected values to check:")
    print(f"    TAG     = {TAG}")
    print(f"    COMMENT = {COMMENT}")

    print("=" * 70)


except V20Error as e:
    print("\n❌ OANDA REJECTED ORDER")
    print(str(e))
    sys.exit(1)

except Exception as e:
    print("\n❌ UNEXPECTED ERROR")
    print(repr(e))
    sys.exit(1)