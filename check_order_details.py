# check_order_details.py
import sys
sys.path.insert(0, "/home/qili/ai_training_cnn/utils")

from datetime import datetime, timezone

from utils.oanda_execution import api, OANDA_ACCOUNT_ID
from oandapyV20.endpoints.positions import OpenPositions
from oandapyV20.endpoints.trades import TradeDetails

# def win_loss_status(unrealized_pl: float) -> str:
#     if unrealized_pl > 0:
#         return "✅ WIN (in profit)"
#     if unrealized_pl < 0:
#         return "❌ LOSS (in drawdown)"
#     return "➖ FLAT (breakeven)"

def get_position_win_loss_message() -> str:
    resp = api.request(OpenPositions(OANDA_ACCOUNT_ID))

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = []
    lines.append("=" * 120)
    lines.append(f"📊 OANDA OPEN POSITIONS — DETAILED WIN/LOSS (UNREALIZED P&L) for OANDA A/C {OANDA_ACCOUNT_ID}")
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
                lines.append(f"\n➡️ {instr} {side.upper()} has no tradeIDs!")
                continue

            tid = trade_ids[0]
            trade = api.request(TradeDetails(OANDA_ACCOUNT_ID, tid))["trade"]

            entry_price = trade.get("price", "NONE")
            sl = trade.get("stopLossOrder", {}).get("price", "NONE")
            tp = trade.get("takeProfitOrder", {}).get("price", "NONE")
            sl_id = trade.get("stopLossOrderID", "NONE")
            tp_id = trade.get("takeProfitOrderID", "NONE")

            side_label = "LONG" if side == "long" else "SHORT"

            lines.append(f"\n➡️ {instr} {side_label}")
            lines.append(f"   Units (abs): {abs(int(units))} | signed: {units}")
            lines.append(f"   TradeID: {tid}")
            lines.append(f"   Entry: {entry_price}")
            lines.append(f"   SL: {sl}  (orderID: {sl_id})")
            lines.append(f"   TP: {tp}  (orderID: {tp_id})")
            lines.append(f"   Unrealized P&L: {unrealized_pl:.2f}")
            # lines.append(f"   Status: {win_loss_status(unrealized_pl)}")

    lines.append("\n" + "=" * 120)
    lines.append(f"Summary: positions counted = {positions_count}")
    lines.append(f"Grand TOTAL unrealized P&L: {grand_unrealized:.2f}")
    lines.append("=" * 120)

    return "\n".join(lines)

if __name__ == "__main__":
    from telegram_message import send_telegram_message
    msg = get_position_win_loss_message()
    print(msg)  # keep console output
    send_telegram_message(msg)