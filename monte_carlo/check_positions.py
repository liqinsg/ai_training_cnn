# check_positions.py
# ==========================================
# 🧩 ACCURATE POSITION CHECK — NO BOGUS VALUES
# ==========================================
from utils.oanda_execution import api, OANDA_ACCOUNT_ID
from oandapyV20.endpoints.positions import OpenPositions
from oandapyV20.endpoints.trades import TradeDetails
from oandapyV20.endpoints.trades import OpenTrades
import datetime
from utils.utils import format_oanda_time
from datetime import datetime, timezone

def get_open_trades():
    resp = api.request(OpenTrades(OANDA_ACCOUNT_ID))
    return [{"id": trade["id"], "instrument": trade["instrument"], "units": trade["currentUnits"], "open_time": format_oanda_time(trade["openTime"])} for trade in resp["trades"]]

def get_position_summary() -> str:
    """✅ Returns formatted position text for Telegram — importable"""
    resp = api.request(OpenPositions(OANDA_ACCOUNT_ID))
    lines = []
    lines.append("="*60)
    lines.append("📊 OANDA OPEN POSITIONS & ACTIVE ORDERS")
    lines.append(f"🕒 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("="*60)
    lines.append("")

    total_pnl = 0.0
    lines.append("📋 **CURRENT POSITIONS**")
    for pos in resp.get("positions", []):
        instr = pos["instrument"]
        for side in ("long", "short"):
            units = float(pos[side]["units"])
            if units == 0:
                continue
            side_label = "📈 LONG" if units > 0 else "📉 SHORT"
            pnl = float(pos[side]["unrealizedPL"])
            total_pnl += pnl
            tid = pos[side]["tradeIDs"][0]

            # Fetch real SL/TP directly from OANDA
            trade = api.request(TradeDetails(OANDA_ACCOUNT_ID, tid))["trade"]
            sl = trade.get("stopLossOrder", {}).get("price", "NONE")
            tp = trade.get("takeProfitOrder", {}).get("price", "NONE")

            lines.append(f"  {side_label} {instr} | {abs(int(units))} units | P&L {pnl:.2f}")
            lines.append(f"  🛡️  SL @ {sl} | TP @ {tp}\n")

    lines.append(f"🧾 TOTAL UNREALIZED P&L: **{total_pnl:.2f}**")
    lines.append("="*60)
    return "\n".join(lines)


# ✅ RUN WHEN CALLED DIRECTLY
if __name__ == "__main__":
    print("🔍 Fetching open positions from OANDA...")
    print("Position========================================")
    open_positions = get_open_trades()
    for pos in open_positions:
        print(pos)
    # print("\n")
    # print("Summary========================================")
    # print(get_position_summary())