from .trading_core import api, OANDA_ACCOUNT_ID
from oandapyV20.endpoints.trades import TradesList
from oandapyV20.endpoints.positions import PositionDetails
from datetime import datetime, timezone

def get_last_trade_info(instrument):
    """
    Returns: (entry_price, open_time, direction) or (None, None, None)
    Works for all account types (hedge/net)
    """
    try:
        # 1. Get all open trades for this instrument
        resp = api.request(TradesList(
            accountID=OANDA_ACCOUNT_ID,
            params={"instrument": instrument, "state": "OPEN"}
        ))
        trades = resp.get("trades", [])
        if not trades:
            return (None, None, None)

        # 2. Pick the most recently opened one
        latest = sorted(trades, key=lambda x: x["openTime"], reverse=True)[0]
        entry_price = float(latest["price"])
        open_time_str = latest["openTime"]  # ISO 8601 e.g. "2026-08-06T03:15:22.000000000Z"
        direction = "LONG" if float(latest["currentUnits"]) > 0 else "SHORT"

        # Convert to datetime object if needed
        open_time = datetime.fromisoformat(open_time_str.replace("Z", "+00:00"))
        return (entry_price, open_time, direction)

    except Exception as e:
        print(f"⚠️ get_last_trade_info({instrument}): {repr(e)[:80]}")
        return (None, None, None)

# Convenience wrappers you asked for:
def get_last_entry_price(instrument):
    p, _, _ = get_last_trade_info(instrument)
    return p

def get_last_open_time(instrument):
    _, t, _ = get_last_trade_info(instrument)
    return t

def get_last_closed_trade_info(instrument):
    """
    Returns: (exit_price, close_time, direction, reason) or (None, None, None, None)
    Only looks at CLOSED trades — perfect for post‑TP/SL cooldown
    """
    try:
        resp = api.request(TradesList(
            accountID=OANDA_ACCOUNT_ID,
            params={"instrument": instrument, "state": "CLOSED", "count": 10}
        ))
        trades = resp.get("trades", [])
        if not trades:
            return (None, None, None, None)

        # ✅ SAFE SORT: skip trades with no closeTime
        valid_trades = [t for t in trades if t.get("closeTime")]
        if not valid_trades:
            return (None, None, None, None)

        # Sort by closeTime — newest first
        latest = sorted(valid_trades, key=lambda x: x["closeTime"], reverse=True)[0]

        exit_price = float(latest["price"])
        close_time = datetime.fromisoformat(latest["closeTime"].replace("Z", "+00:00"))
        direction = "LONG" if float(latest["initialUnits"]) > 0 else "SHORT"
        reason = latest.get("exitReason", "UNKNOWN")

        return (exit_price, close_time, direction, reason)

    except Exception as e:
        print(f"⚠️ closed trade fetch {instrument}: {repr(e)[:60]}")
        return (None, None, None, None)

    
# Wrapper for quick cooldown check
def minutes_since_last_close(instrument):
    _, close_time, _, _ = get_last_closed_trade_info(instrument)
    if not close_time:
        return 9999  # no closed trades → OK
    return (datetime.now(timezone.utc) - close_time).total_seconds() / 60

def get_recent_exit_status(instrument, cooldown_mins=60):
    """
    Unified check for re‑entry rules:
    1. No open position on this pair
    2. How long since last closed trade
    3. Whether still inside cooldown window

    Returns:
        (no_open: bool, mins_since_exit: float, in_cooldown: bool, last_exit_dir: str|None)
    """
    # Step 1: Check open position
    open_price, _, open_dir = get_last_trade_info(instrument)
    no_open = open_price is None

    # Step 2: Get last closed trade
    exit_price, close_time, exit_dir, reason = get_last_closed_trade_info(instrument)
    if not close_time:
        # No closed trades ever
        return (no_open, 9999.0, False, None)

    # Step 3: Calculate elapsed time
    mins_since_exit = (datetime.now(timezone.utc) - close_time).total_seconds() / 60
    in_cooldown = mins_since_exit < cooldown_mins

    return (no_open, round(mins_since_exit, 1), in_cooldown, exit_dir)

def check_recent_closed_no_open(instrument, cooldown_mins=60):
    """
    Returns:
        (has_no_open: bool, in_cooldown: bool, mins_since: float, last_dir: str|None)
    Logic:
    1. has_no_open = True only if NO open position exists
    2. in_cooldown = True if last closed < cooldown_mins ago
    """
    open_price, _, _ = get_last_trade_info(instrument)
    has_no_open = open_price is None

    _, close_time, last_dir, _ = get_last_closed_trade_info(instrument)
    if not close_time:
        return (has_no_open, False, 9999.0, None)

    mins_since = (datetime.now(timezone.utc) - close_time).total_seconds() / 60
    in_cooldown = mins_since < cooldown_mins

    return (has_no_open, in_cooldown, round(mins_since,1), last_dir)

if __name__ == "__main__":
    # Example usage:
    instrument = "EUR_USD"
    price, open_time, direction = get_last_trade_info(instrument)
    print(f"Last trade for {instrument}: Price={price}, OpenTime={open_time}, Direction={direction}")
    exit_price, close_time, close_direction, reason = get_last_closed_trade_info(instrument)
    print(f"Last closed for {instrument}: Price={exit_price}, CloseTime={close_time}, Direction={close_direction}, Reason={reason}")

    no_order  = get_last_entry_price(instrument) is None
    no_open   = get_last_trade_info(instrument)[0] is None
    print(f"Is it a latest closed no open order: {no_order}, {no_open}")
    # print(f"Is it a latest closed no open order: {get_last_entry_price(instrument)}")
    # print(f"Last closed trade for {instrument}: {get_last_closed_trade_info(instrument)}")
    # print(f"Last closed trade for {instrument}: {get_last_closed_trade_info(instrument)}")
    
    has_no_open, in_cooldown, mins_since, last_dir = check_recent_closed_no_open(instrument)
    print(f"Check recent closed no open: has_no_open={has_no_open}, in_cooldown={in_cooldown}, mins_since={mins_since}, last_dir={last_dir}")
    # get_last_closed_trade_info(instrument)
# Before opening a new order:
# last_price = get_last_entry_price(oanda_sym)
# last_open = get_last_open_time(oanda_sym)

# if last_price and last_open:
#     # 1. Price distance check
#     pips_diff = abs(current_price - last_price) / pip_size
#     if pips_diff < 5:
#         print(f"⏭️ SKIP — {oanda_sym} only {pips_diff:.1f} pips from last entry")
#         continue

#     # 2. Cooldown check
#     mins_since = (datetime.now(timezone.utc) - last_open).total_seconds() / 60
#     if mins_since < 60:
#         print(f"⏭️ SKIP — {oanda_sym} opened {mins_since:.0f}min ago (cooldown)")
#         continue

#     # 3. Direction check
#     _, _, last_dir = get_last_trade_info(oanda_sym)
#     if last_dir == signal_direction:
#         print(f"⏭️ SKIP — {oanda_sym} already {last_dir} — no duplicate")
#         continue