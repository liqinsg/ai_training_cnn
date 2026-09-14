"""
Minimal Open Trade Ownership Test
---------------------------------
Purpose:
    Directly inspect ONE currently-open OANDA trade by Trade ID.

This test does NOT:
    - open a new trade
    - close a trade
    - modify SL/TP
    - infer ownership from OpenPositions.tradeIDs[0]

It directly calls:
    TradeDetails(account_id, TRADE_ID)

Goal:
    Verify whether clientExtensions.tag/comment persisted
    on the actual OPEN trade.
"""

import pprint

import config_oanda
from oandapyV20.endpoints.trades import TradeDetails


ACCOUNT_ID = config_oanda.OANDA_ACCOUNT_ID_2
TRADE_ID = "7197"


print("=" * 70)
print("OPEN TRADE DIRECT INSPECTION")
print("=" * 70)
print(f"ENVIRONMENT : {config_oanda.OANDA_ENV}")
print(f"ACCOUNT     : {ACCOUNT_ID}")
print(f"TRADE ID    : {TRADE_ID}")
print()


try:
    response = config_oanda.api.request(
        TradeDetails(
            accountID=ACCOUNT_ID,
            tradeID=TRADE_ID,
        )
    )

    trade = response.get("trade", {})

    print("RAW TRADE RESPONSE:")
    pprint.pp(response, width=160)

    print()
    print("-" * 70)
    print("OWNERSHIP FIELDS")
    print("-" * 70)

    print("trade.id              :", trade.get("id"))
    print("trade.instrument      :", trade.get("instrument"))
    print("trade.currentUnits    :", trade.get("currentUnits"))
    print("trade.price           :", trade.get("price"))
    print("trade.state           :", trade.get("state"))

    ext = trade.get("clientExtensions")

    print()
    print("trade.clientExtensions:", ext)

    if ext:
        print()
        print("TAG                  :", ext.get("tag"))
        print("COMMENT              :", ext.get("comment"))
        print("ID                   :", ext.get("id"))

        print()
        print("RESULT:")
        if ext.get("tag") == "TAG-TEST-20260914":
            print("PASS: TAG persisted on OPEN TRADE")
        else:
            print("FAIL: TAG missing or different")

        if ext.get("comment") == "COMMENT-TEST-20260914":
            print("PASS: COMMENT persisted on OPEN TRADE")
        else:
            print("FAIL: COMMENT missing or different")
    else:
        print()
        print("RESULT:")
        print("FAIL: OPEN TRADE has no clientExtensions")

except Exception as e:
    print()
    print("ERROR:")
    print(type(e).__name__, str(e))