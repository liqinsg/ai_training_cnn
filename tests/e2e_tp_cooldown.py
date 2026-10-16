#!/usr/bin/env python3
"""Demo-only E2E: open tiny-TP trade -> wait for TP fill -> assert cooldown."""
import sys, time
from pathlib import Path
sys.path.extend([str(Path(__file__).resolve().parent.parent)])

import config_bot as C
from config_oanda import get_oanda_profile
from oandapyV20.endpoints.pricing import PricingInfo
from oandapyV20.endpoints.trades import TradeDetails
from fx_trade_bot_utils_v1 import open_oanda_order_simple as open_order
from utils.cooldown_tp import recent_tp_close_mins

PROFILE, INSTR, UNITS = 2, "EUR_JPY", 1000
TP_PIPS, SL_PIPS, TIMEOUT_MIN, COOLDOWN_H = 6, 30, 60, 0.25
TAG = f"fx_bot_v685_profile{PROFILE}_entry"
EXT_ID = f"fx_bot_v685_profile{PROFILE}_{INSTR}"

prof = get_oanda_profile("practice")
assert prof["env"] == "practice", f"REFUSING: env={prof['env']}"
api = prof["oanda_client"]
acct, src = C.resolve_account_id(PROFILE, False)
print(f"[SETUP] env=practice account={acct} ({src}) pair={INSTR}")

pip = 0.01 if "JPY" in INSTR else 0.0001
dec = 3 if "JPY" in INSTR else 5
p = api.request(PricingInfo(acct, params={"instruments": INSTR}))["prices"][0]
bid, ask = float(p["bids"][0]["price"]), float(p["asks"][0]["price"])
tp = round(ask + TP_PIPS * pip, dec)
sl = round(bid - SL_PIPS * pip, dec)
print(f"[ORDER] BUY {UNITS} bid={bid} ask={ask} TP={tp} SL={sl}")

resp = open_order(api, acct, INSTR, "BUY", UNITS, sl, tp, dry_run=False,
                  tags=["fx_bot", "v685", f"profile{PROFILE}"],
                  comment="cooldown_e2e_test",
                  client_ext={"id": EXT_ID, "tag": TAG})
assert resp.get("status") == "OK", f"order failed: {resp}"
tid = resp["trade_id"]
print(f"[ORDER] opened trade_id={tid}")

deadline = time.time() + TIMEOUT_MIN * 60
while time.time() < deadline:
    t = api.request(TradeDetails(acct, tid))["trade"]
    tp_state = t.get("takeProfitOrder", {}).get("state")
    print(f"[WAIT] state={t['state']} tp_order={tp_state}", flush=True)
    if t["state"] == "CLOSED":
        break
    time.sleep(15)
else:
    sys.exit(f"[TIMEOUT] trade {tid} still open - close manually in demo")

print(f"[PROBE] clientExtensions on closed trade: {t.get('clientExtensions')}")
assert t["takeProfitOrder"]["state"] == "FILLED", "closed by SL/manual, not TP"

mins = recent_tp_close_mins(api, acct, INSTR, TAG)
print(f"[CHECK] minutes since TP fill = {mins}")
assert mins is not None, "tag filter missed it (see PROBE line) or lookup failed"
assert mins < COOLDOWN_H * 60, "should be inside cooldown window"
print("[PASS] cooldown detected after TP")