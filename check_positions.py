#!/usr/bin/env python3
"""
Reusable position/order checker — works standalone OR imported
"""
import sys
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from utils.oanda_execution import api, OANDA_ACCOUNT_ID
from oandapyV20.endpoints.positions import OpenPositions
from oandapyV20.endpoints.orders import OrderList

def _get_position_summary() -> str:
    """Return formatted text summary for Telegram"""
    lines = []
    lines.append("\n📋 **CURRENT POSITIONS**")
    try:
        pos = api.request(OpenPositions(accountID=OANDA_ACCOUNT_ID)).get("positions", [])
        if not pos:
            lines.append("✅ No open positions")
        else:
            total_pl = 0.0
            for p in pos:
                inst = p["instrument"]
                if p["long"].get("units", "0") != "0":
                    u = int(p["long"]["units"])
                    pl = float(p["long"]["unrealizedPL"])
                    lines.append(f"  📈 {inst} | LONG {u} | P&L {pl:.2f}")
                    total_pl += pl
                if p["short"].get("units", "0") != "0":
                    u = abs(int(p["short"]["units"]))
                    pl = float(p["short"]["unrealizedPL"])
                    lines.append(f"  📉 {inst} | SHORT {u} | P&L {pl:.2f}")
                    total_pl += pl
            lines.append(f"  🧾 TOTAL UNREALIZED P&L: **{total_pl:.2f}**")

        orders = api.request(OrderList(accountID=OANDA_ACCOUNT_ID)).get("orders", [])
        if orders:
            lines.append("\n🛡️ **ATTACHED SL / TP**")
            for o in orders:
                inst = o.get("instrument") or o.get("instrumentName") or "—"
                lines.append(f"  {inst} | {o.get('type','?')} @ {o.get('price','-')}")
        else:
            lines.append("\n✅ No active SL/TP orders")
    except Exception as e:
        lines.append(f"  ⚠️ Check failed: {e}")
    
    return "\n".join(lines)

def get_position_summary() -> str:
    lines = []
    lines.append("\n📋 **CURRENT POSITIONS**")
    try:
        pos_resp = api.request(OpenPositions(accountID=OANDA_ACCOUNT_ID))
        positions = pos_resp.get("positions", [])
        pos_map = {}  # instrument → attached SL/TP prices
        if not positions:
            lines.append("✅ No open positions")
        else:
            total_pl = 0.0
            for p in positions:
                inst = p["instrument"]
                pos_map[inst] = {}
                if p["long"].get("units", "0") != "0":
                    u = int(p["long"]["units"])
                    pl = float(p["long"]["unrealizedPL"])
                    lines.append(f"  📈 {inst} | LONG {u} | P&L {pl:.2f}")
                    total_pl += pl
                if p["short"].get("units", "0") != "0":
                    u = abs(int(p["short"]["units"]))
                    pl = float(p["short"]["unrealizedPL"])
                    lines.append(f"  📉 {inst} | SHORT {u} | P&L {pl:.2f}")
                    total_pl += pl
            lines.append(f"  🧾 TOTAL UNREALIZED P&L: **{total_pl:.2f}**")

        # 🛡️ Show SL/TP grouped by instrument
        ord_resp = api.request(OrderList(accountID=OANDA_ACCOUNT_ID))
        orders = ord_resp.get("orders", [])
        if orders:
            lines.append("\n🛡️ **ATTACHED SL / TP**")
            # Group by instrument we already know from positions
            for inst in pos_map:
                sl_price = "—"
                tp_price = "—"
                for o in orders:
                    o_type = o.get("type", "")
                    o_price = o.get("price", "")
                    trade_id = o.get("tradeID", "")
                    # Match SL/TP to instrument via trade context
                    if o_type == "STOP_LOSS":
                        sl_price = o_price
                    if o_type == "TAKE_PROFIT":
                        tp_price = o_price
                lines.append(f"  {inst} | SL @ {sl_price} | TP @ {tp_price}")

    except Exception as e:
        lines.append(f"  ⚠️ Check failed: {e}")
    return "\n".join(lines)

# Allow running standalone
if __name__ == "__main__":
    print("=" * 60)
    print("📊 OANDA OPEN POSITIONS & ACTIVE ORDERS")
    print(f"🕒 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)
    print(get_position_summary())
    print("=" * 60)