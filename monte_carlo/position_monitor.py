# monte_carlo/position_monitor.py
"""
===============================================================================
MONTE CARLO POSITION MONITOR & RISK CIRCUIT BREAKER
===============================================================================

PURPOSE:
--------
Acts as an active, automated risk management layer (circuit breaker) for open 
OANDA trading positions. It regularly evaluates live active trades against the 
latest Kalman-filtered Monte Carlo (MC) probabilistic forecasts (H4 timeframe).

HOW IT WORKS:
-------------
1. Fetches current open positions from OANDA (`get_open_positions_formatted`).
2. Matches each trade's currency instrument with today's latest generated MC 
    JSON forecast file (`daily_results/h4_mc_<PAIR>_<DATE>_*.json`).
3. Evaluates directional win-rate probabilities (`p_up` / `p_down`) and volatility:
    - LONG positions require `p_up >= 45.0%`.
    - SHORT positions require `p_down >= 45.0%`.

AUTOMATED ACTIONS (NOT JUST PASSIVE MONITORING):
------------------------------------------------
- REVERSAL / DECAY EXIT:
    If a trade's directional win probability drops below 45.0% (edge loss/reversal),
    it IMMEDIATELY calls `close_position(instrument)` to pull the plug early and 
    sends an automated Telegram alert notification.

- VOLATILITY NOTIFICATION:
    Logs low volatility conditions (`ann_vol < 3.5%`) to signal tight consolidation/TP.

EXECUTION MODES:
----------------
- Standalone via Cron: Scheduled (e.g., every 15 mins) as an independent risk monitor.
- Integrated Pipeline: Called directly inside `fx_trade_bot` before scanning for entries.

===============================================================================
"""
import sys
import json
from pathlib import Path
from datetime import datetime, timezone

# Ensure project base directory and utility modules are added to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.extend([str(BASE_DIR), str(BASE_DIR / "utils")])

from utils.trading_core import get_positions, close_position  #get_open_positions_formatted, 
from telegram_message import send_telegram_message

RESULTS_DIR = BASE_DIR / "daily_results"


def normalize_symbol(symbol: str) -> str:
    """
    Standardize currency pair tickers across different providers/APIs.
    Example: 'EUR_USD' -> 'EURUSD', 'EURUSD=X' -> 'EURUSD'
    """
    if not symbol:
        return ""
    return symbol.replace("=X", "").replace("=", "_").replace("_", "").upper()


def load_latest_mc(pair: str, tf: str = "h4"):
    """
    Locates and loads the most recent Monte Carlo JSON cache file for a given pair.
    """
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    norm_pair = normalize_symbol(pair)

    # Search for today's generated MC JSON cache files
    matches = sorted(
        RESULTS_DIR.glob(f"{tf.lower()}_mc_*_{date_str}_*.json"),
        key=lambda x: x.stat().st_mtime,
        reverse=True
    )

    for file_path in matches:
        # Extract currency ticker from filename (e.g., h4_mc_EURUSD_20260807_120000.json)
        parts = file_path.stem.split("_")
        if len(parts) >= 3 and normalize_symbol(parts[2]) == norm_pair:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠️ Failed to read MC JSON cache [{file_path.name}]: {e}")
                return None
    return None


def position_monitor():
    # Fetch formatted open positions (includes direction, open_time_utc, and trade_id)
    open_positions = get_positions()
    # open_positions_formated = get_open_positions_formatted()
    pos_summary = ", ".join([p.get("instrument", "") for p in open_positions]) if open_positions else "None"
    print(f"🔍 Open positions: {pos_summary}")

    if not open_positions:
        print("🔍 No active positions to monitor.")
        return

    print(f"🔄 Monitoring {len(open_positions)} active positions via MC updates...\n")

    closed_instruments = set()  # Prevent duplicate closure calls for the same instrument in one cycle

    for position in open_positions:
        instrument = position.get("instrument")

        trade_id = str(position.get("id") or position.get("trade_id") or position.get("tradeId") or "N/A")

        open_time = position.get("open_time_utc", "N/A")

        # Determine direction safely
        if "direction" in position:
            direction = str(position["direction"]).upper()
        else:
            long_units = float(position.get("long", {}).get("units", 0) or 0)
            direction = "LONG" if long_units > 0 else "SHORT"

        if not instrument or instrument in closed_instruments:
            continue

        mc = load_latest_mc(instrument, tf="h4")
        if not mc:
            print(f"⚠️ [{instrument}] No recent MC JSON cache found. Skipping...")
            continue

        # Safely extract numerical values with fallback defaults
        p_up = float(mc.get("p_up") if mc.get("p_up") is not None else 50.0)
        p_down = float(mc.get("p_down") if mc.get("p_down") is not None else 50.0)
        ann_vol = float(mc.get("ann_vol_pct") if mc.get("ann_vol_pct") is not None else 5.0)

        print(f"📌 Trade #{trade_id} [{instrument}] | Direction: {direction} | Open Time: {open_time}")
        print(f"   └── MC Win Rates: UP {p_up}% / DOWN {p_down}% | Volatility: {ann_vol}%")

        # 1. Win-rate decay and reversal exit logic
        if direction == "LONG" and p_up < 45.0:
            msg = f"⚠️ Trade #{trade_id} {instrument} (LONG): MC UP probability decayed to {p_up}% < 45% -> Triggering early reversal exit!"
            print(f"   └── {msg}")
            close_position(instrument)
            closed_instruments.add(instrument)
            send_telegram_message(msg)

        elif direction == "SHORT" and p_down < 45.0:
            msg = f"⚠️ Trade #{trade_id} {instrument} (SHORT): MC DOWN probability decayed to {p_down}% < 45% -> Triggering early reversal exit!"
            print(f"   └── {msg}")
            close_position(instrument)
            closed_instruments.add(instrument)
            send_telegram_message(msg)

        # 2. Low volatility state notice
        if ann_vol < 3.5:
            print(f"   └── 📏 Low volatility detected (Vol={ann_vol}%). Maintaining tight take-profit bounds.")

        print("-" * 50)


if __name__ == "__main__":
    position_monitor()