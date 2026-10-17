#!/usr/bin/env python3
"""Read-only OANDA audit (DEMO_2): closed trades in last N hours -> close reasons."""

import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

from oandapyV20.endpoints.trades import TradesList
from oandapyV20.endpoints.transactions import TransactionDetails
from config_oanda import api, OANDA_ACCOUNT_ID_DEMO_2 as ACCOUNT

HOURS = float(sys.argv[1]) if len(sys.argv) > 1 else 72
COUNT = 500


def parse_time(s):
    # OANDA gives nanoseconds ("...06.123456789Z"); keep 6 digits for Python.
    base, _, frac = s.rstrip("Z").partition(".")
    return datetime.fromisoformat(f"{base}.{frac[:6] or '0'}").replace(tzinfo=timezone.utc)


def classify(tx):
    if tx.get("type") != "ORDER_FILL":
        return "NON_ORDER_FILL"
    r = tx.get("reason", "")
    if r == "TAKE_PROFIT_ORDER":
        return "TP"
    if "STOP_LOSS" in r:
        return "SL"
    if r.startswith("MARKET_ORDER"):
        return "NON_TP_CLOSE"
    return "UNKNOWN"


now = datetime.now(timezone.utc)
cutoff = now - timedelta(hours=HOURS)
print(f"Account: {ACCOUNT} | Window UTC: {cutoff:%Y-%m-%d %H:%M} -> {now:%Y-%m-%d %H:%M} | READ ONLY")

trades = api.request(TradesList(ACCOUNT, params={"state": "CLOSED", "count": COUNT}))["trades"]
recent = [t for t in trades if t.get("closeTime") and parse_time(t["closeTime"]) >= cutoff]

totals = Counter()
print("\n=== TRADES ===")
for t in recent:
    for tx_id in t.get("closingTransactionIDs", []):
        tx = api.request(TransactionDetails(ACCOUNT, str(tx_id)))["transaction"]
        c = classify(tx)
        totals[c] += 1
        print(f"{t['id']} {t['instrument']} closed={t['closeTime'][:19]} "
              f"tx={tx_id} reason={tx.get('reason')} -> {c}")

print("\n=== SUMMARY ===")
print(f"Fetched: {len(trades)} | In window: {len(recent)}")
for k in ("TP", "SL", "NON_TP_CLOSE", "UNKNOWN", "NON_ORDER_FILL"):
    print(f"{k}: {totals[k]}")
if len(trades) >= COUNT:
    print("WARNING: hit count limit, result may be incomplete.")