#!/usr/bin/env python3
"""
    check_order_details.py — Open Positions + SL/TP + P&L Reporter
    Usage:
        python check_order_details.py                    # → uses default OANDA_ACCOUNT_ID
        python check_order_details.py ACCT_ID1           # → single account
        python check_order_details.py ID1,ID2,ID3        # → comma-separated list
        python check_order_details.py ID1 ID2 ID3        # → space-separated list
"""

import sys
import argparse
from datetime import datetime, timezone

# ─── PATH ADJUSTMENT ───
# sys.path.insert(0, "/home/nie/projects/ai_training_cnn/utils")

from utils.oanda_execution import api, OANDA_ACCOUNT_ID as DEFAULT_ACCOUNT
from oandapyV20.endpoints.positions import OpenPositions
from oandapyV20.endpoints.trades import TradeDetails
from oandapyV20.endpoints.orders import OrderList
from telegram_message import send_telegram_message


def get_position_win_loss_message(account_id: str) -> str:
    """Generate detailed position report for ONE account"""
    resp = api.request(OpenPositions(account_id))

    # Fetch ALL pending orders once
    all_orders_resp = api.request(OrderList(account_id, params={"state": "PENDING"}))
    all_orders = all_orders_resp.get("orders", [])

    # Build lookup: tradeID → {sl_price, sl_id, tp_price, tp_id}
    trade_orders = {}
    for ord in all_orders:
        tid = ord.get("tradeID")
        if not tid:
            continue
        otype = ord.get("type")
        price = ord.get("price")
        oid = ord.get("id")
        if tid not in trade_orders:
            trade_orders[tid] = {
                "sl_price": "NONE", "sl_id": "NONE",
                "tp_price": "NONE", "tp_id": "NONE",
            }
        if otype == "STOP_LOSS":
            trade_orders[tid]["sl_price"] = price
            trade_orders[tid]["sl_id"] = oid
        elif otype == "TAKE_PROFIT":
            trade_orders[tid]["tp_price"] = price
            trade_orders[tid]["tp_id"] = oid

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = []
    lines.append("=" * 120)
    lines.append(f"📊 OANDA OPEN POSITIONS — Account: {account_id}")
    lines.append(f"🕒 {now}")
    lines.append("=" * 120)

    grand_unrealized = 0.0
    positions_count = 0

    for pos in resp.get("positions", []):
        instr = pos["instrument"]

        for side in ("long", "short"):
            units = float(pos[side]["units"])
            if units == 0:
                continue

            positions_count += 1
            unrealized_pl = float(pos[side].get("unrealizedPL", 0.0))
            grand_unrealized += unrealized_pl

            trade_ids = pos[side].get("tradeIDs", [])
            if not trade_ids:
                lines.append(f"\n➡️ {instr} {side.upper()} — No tradeIDs found!")
                continue

            tid = trade_ids[0]
            trade = api.request(TradeDetails(account_id, tid))["trade"]

            entry_price = trade.get("price", "NONE")
            sl = trade.get("stopLossOrder", {}).get("price", "NONE")
            tp = trade.get("takeProfitOrder", {}).get("price", "NONE")

            # Override with pending order details if available
            orders_info = trade_orders.get(tid, {})
            sl_id = orders_info.get("sl_id", "NONE")
            tp_id = orders_info.get("tp_id", "NONE")
            sl = orders_info.get("sl_price", sl)
            tp = orders_info.get("tp_price", tp)

            # Client Extensions (bot tag/tracking)
            ext = trade.get("clientExtensions", {})
            ext_tag = ext.get("tag", "-")
            ext_id = ext.get("id", "-")
            ext_comment = ext.get("comment", "-")

            side_label = "LONG" if side == "long" else "SHORT"

            lines.append(f"\n➡️ {instr} {side_label}")
            lines.append(f"   Units (abs): {abs(int(units))}")
            lines.append(f"   TradeID: {tid}")
            lines.append(f"   Entry: {entry_price}")
            lines.append(f"   SL: {sl}  (orderID: {sl_id})")
            lines.append(f"   TP: {tp}  (orderID: {tp_id})")
            lines.append(f"   Unrealized P&L: {unrealized_pl:.2f}")
            lines.append(f"   🏷️ Tag: {ext_tag}  |  ID: {ext_id}")
            lines.append(f"   💬 Comment: {ext_comment}")

    lines.append("\n" + "=" * 120)
    lines.append(f"Summary: Positions = {positions_count}")
    lines.append(f"Grand TOTAL Unrealized P&L: {grand_unrealized:.2f}")
    lines.append("=" * 120)

    return "\n".join(lines)


def parse_account_ids(args_list):
    """Accept comma-separated OR space-separated IDs"""
    ids = []
    for arg in args_list:
        ids.extend([aid.strip() for aid in arg.split(",") if aid.strip()])
    return ids if ids else [DEFAULT_ACCOUNT]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Check OANDA open positions + SL/TP + P&L",
        epilog="Examples:\n  python check_order_details.py\n  python check_order_details.py ACCT_ID\n  python check_order_details.py ID1,ID2\n  python check_order_details.py ID1 ID2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "accounts",
        nargs="*",
        help="One or more OANDA Account IDs (comma or space separated)",
    )
    args = parser.parse_args()

    account_ids = parse_account_ids(args.accounts)
    full_report = []

    for acct in account_ids:
        report = get_position_win_loss_message(acct)
        full_report.append(report)
        print("\n" + report)
        print("\n" + "━" * 120 + "\n")

    # Send combined report via Telegram
    combined = "\n\n" + "📋 " + "=" * 30 + " MULTI-ACCOUNT REPORT " + "=" * 30 + "\n\n".join(full_report)
    send_telegram_message(combined.strip())