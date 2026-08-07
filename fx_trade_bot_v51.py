# fx_trade_bot_v6.py — ORIGINAL v4/v5 + ONLY CONFIG LOAD UPDATED
# ✅ Dual Daily + H4 MC | ✅ Atomic SL/TP | ✅ No carry‑over | ✅ Pivot filter | ✅ Risk limits
# ✅ ONLY CHANGE: Removed cfg() helper → load directly from config
import sys
from pathlib import Path
from datetime import datetime, timezone
from enum import Enum
import json
import numpy as np
import pandas as pd
import pandas_ta as ta
from utils.calculate_pivots import calculate_pivots

from monte_carlo.position_monitor import position_monitor

class Direction(Enum):
    LONG = "LONG"
    SHORT = "SHORT"

# --------------------------
# PATH SETUP — UNCHANGED
# --------------------------
BASE_DIR = Path(__file__).resolve().parent
sys.path.extend([str(BASE_DIR), str(BASE_DIR / "utils")])

# --------------------------
# IMPORTS — UNCHANGED
# --------------------------
from utils.trading_core import (
    get_candles as get_oanda_candles,
    forex_market_closed,
    get_open_instruments,
    get_open_position
)
from utils.oanda_execution import execute_market_trade as execute_market_trade_v5
from utils.calculate_currency_strength import calculate_currency_strength
from utils.strategy_helpers import build_strength_matrix, format_strength_ranking
from telegram_message import send_telegram_message
from check_positions import get_position_summary
import config  # ✅ SAME config.py file you already use

# --------------------------
# ✅ ONLY CHANGED PART: LOAD DIRECTLY — NO cfg() HELPER
# --------------------------
MODE = getattr(config, "MODE", "LEVEL10")
MIN_PROB = getattr(config, "MIN_PROB", 0.45)
STRENGTH_GAP_THRESHOLD = getattr(config, "STRENGTH_GAP_THRESHOLD", 7)
MAX_TOTAL_TRADES = getattr(config, "MAX_TOTAL_TRADES", 3)
MAX_PER_USD_GROUP = getattr(config, "MAX_PER_USD_GROUP", 3)
MAX_PER_JPY_GROUP = getattr(config, "MAX_PER_JPY_GROUP", 3)
DEFAULT_LOT_SIZE = getattr(config, "DEFAULT_LOT_SIZE", 10000)
ENABLE_PIVOTS = getattr(config, "ENABLE_PIVOTS", False)
PIVOT_BIAS_CHECK = getattr(config, "PIVOT_BIAS_CHECK", True)
PIVOT_METHOD = getattr(config, "PIVOT_METHOD", "Classic")
DEFAULT_PAIRS = getattr(config, "DEFAULT_PAIRS", [])
YAHOO_TO_OANDA = getattr(config, "YAHOO_TO_OANDA", {})
TIMEFRAME = getattr(config, "TIMEFRAME", "15m")
ALLOW_TOP_N = getattr(config, "ALLOW_TOP_N", 3)
ALLOW_BOTTOM_N = getattr(config, "ALLOW_BOTTOM_N", 3)
DEBUG_EDGE_REASON = getattr(config, "DEBUG_EDGE_REASON", True)
NO_SIDE_WAYS_TRADE = getattr(config, "NO_SIDE_WAYS_TRADE", True)

VOL_LOW_THRESHOLD = getattr(config, "VOL_LOW_THRESHOLD", 4.0)
VOL_HIGH_THRESHOLD = getattr(config, "VOL_HIGH_THRESHOLD", 7.0)
RANGE_LOW_PCT = getattr(config, "RANGE_LOW_PCT", 0.20)
RANGE_HIGH_PCT = getattr(config, "RANGE_HIGH_PCT", 0.50)
TP_MULT_SIDEWAYS = getattr(config, "TP_MULT_SIDEWAYS", 1.5)
TP_MULT_NORMAL = getattr(config, "TP_MULT_NORMAL", 2.0)
TP_MULT_STRONG = getattr(config, "TP_MULT_STRONG", 2.5)
MIN_TREND_STRENGTH = getattr(config, "MIN_TREND_STRENGTH", 0.05)

GRANULARITY_MAP = {"15m": "M15", "1h": "H1", "4h": "H4", "D": "D"}
OANDA_GRAN = GRANULARITY_MAP.get(TIMEFRAME, "H1")

# --------------------------
# MARKET CHECK — 100% UNCHANGED
# --------------------------
if forex_market_closed():
    print("⏸️ Market is closed — skipping run")
    raise SystemExit(0)

# --------------------------
# FILE PATHS & MC LOADER — 100% UNCHANGED
# --------------------------
RESULTS_DIR = BASE_DIR / "daily_results"
RESULTS_DIR.mkdir(exist_ok=True)
CLOSED_PAIRS_FILE = RESULTS_DIR / "closed_pairs.json"

def load_closed_pairs():
    if CLOSED_PAIRS_FILE.exists():
        with open(CLOSED_PAIRS_FILE) as f:
            return json.load(f)
    return {}

def load_mc_data(pair):
    """✅ Loads H4 first, falls back to Daily — dual timeframe support"""
    now_utc = datetime.now(timezone.utc)
    date_str = now_utc.strftime("%Y%m%d")
    safe = pair.replace("=X", "").replace("=", "_")
    for tf in ["h4", "daily"]:
        matches = sorted(RESULTS_DIR.glob(f"{tf}_mc_{safe}_{date_str}_*.json"), reverse=True)
        if matches:
            with open(matches[0]) as f:
                return json.load(f)
    print(f"⚠️ No MC data found for {pair}")
    return None

# --------------------------
# MAIN LOGIC — EVERY LINE IDENTICAL TO YOUR ORIGINAL
# --------------------------
def main():
    # 1. Run MC position monitor first to handle probability decay & exits
    position_monitor()
    
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n🤖 FX TRADE BOT — {now} | MODE={MODE}")

    # --- Currency Strength — UNCHANGED ---
    strength_scores = build_strength_matrix()
    ranked = sorted(strength_scores.items(), key=lambda x:x[1], reverse=True)
    top_val, bot_val = ranked[0][1], ranked[-1][1]
    top_n = [c[0] for c in ranked[:ALLOW_TOP_N]]
    bottom_n = [c[0] for c in ranked[-ALLOW_BOTTOM_N:]]
    strength_gap = abs(top_val - bot_val)

    print(format_strength_ranking(strength_scores))
    print(f"📊 Strength Gap: {strength_gap:.2f} | Threshold: {STRENGTH_GAP_THRESHOLD}")
    print(f"🔝 Top {ALLOW_TOP_N}: {', '.join(top_n)} | 🔻 Bottom {ALLOW_BOTTOM_N}: {', '.join(bottom_n)}")

    active_positions = set(get_open_instruments())
    print(f"🔍 Open positions: {', '.join(active_positions) if active_positions else 'None'}")

    closed_tracker = load_closed_pairs()
    today_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    candidates = []
    target_prob_pct = MIN_PROB * 100 if MIN_PROB <= 1.0 else MIN_PROB

    # --- Pair Processing Loop — EXACTLY YOUR CODE ---
    for pair in DEFAULT_PAIRS:
        buy_cond = sell_cond = False
        sl = tp = direction = None
        mc_data = p_up = p_down = ann_vol = range_90 = current_price = None

        oanda_sym = YAHOO_TO_OANDA.get(pair, pair)
        base_cur, quote_cur = oanda_sym.split("_")

        # ✅ YOUR ORIGINAL CHECKS — NO ADDITIONS
        if oanda_sym in active_positions:
            print(f"⏭️ {oanda_sym}: already open — skip duplicate")
            continue
        if closed_tracker.get(pair) == today_str:
            print(f"⏳ {oanda_sym}: cooldown — skip")
            continue

        # Load MC — UNCHANGED
        mc_data = load_mc_data(pair)
        if not mc_data:
            continue

        p_up = mc_data.get("p_up", 50.0)
        p_down = mc_data.get("p_down", 50.0)
        ann_vol = mc_data.get("ann_vol", 5.0)
        range_90 = mc_data.get("range_90", [1.0, 1.0])
        current_price = mc_data.get("current_price", (range_90[0]+range_90[1])/2)

        # Trend & sideways — UNCHANGED
        price_range = range_90[1] - range_90[0]
        price_pos_pct = (current_price - range_90[0]) / price_range if price_range > 0 else 0.5
        uptrend = price_pos_pct > (0.5 + MIN_TREND_STRENGTH)
        downtrend = price_pos_pct < (0.5 - MIN_TREND_STRENGTH)

        if NO_SIDE_WAYS_TRADE and not uptrend and not downtrend:
            print(f"⏸️ {oanda_sym}: sideways — skip")
            continue

        # Strength + Probability — UNCHANGED
        base_top = base_cur in top_n
        base_bot = base_cur in bottom_n
        quote_top = quote_cur in top_n
        quote_bot = quote_cur in bottom_n
        prob_ok_buy = p_up >= target_prob_pct
        prob_ok_sell = p_down >= target_prob_pct

        buy_cond = base_top and quote_bot and prob_ok_buy and (not NO_SIDE_WAYS_TRADE or uptrend)
        sell_cond = base_bot and quote_top and prob_ok_sell and (not NO_SIDE_WAYS_TRADE or downtrend)

        # Debug — EXACTLY YOUR FORMAT
        if DEBUG_EDGE_REASON:
            if buy_cond or sell_cond:
                dir_txt = "BUY" if buy_cond else "SELL"
                print(f"✅ {oanda_sym}: {dir_txt} | Prob {max(p_up,p_down):.1f}% ≥ {target_prob_pct:.0f}%")
            else:
                reasons=[]
                if not (base_top and quote_bot or base_bot and quote_top):
                    reasons.append("Strength mismatch")
                if not (prob_ok_buy or prob_ok_sell):
                    reasons.append(f"Prob {max(p_up,p_down):.1f}% low")
                if NO_SIDE_WAYS_TRADE and not (uptrend or downtrend):
                    reasons.append("Sideways")
                print(f"🔍 {oanda_sym} | REJECT: {'; '.join(reasons) if reasons else 'edge insufficient'}")

        if not (buy_cond or sell_cond):
            continue

        # Regime → TP — UNCHANGED
        if price_pos_pct < RANGE_LOW_PCT or ann_vol < VOL_LOW_THRESHOLD:
            tp_mult, label = TP_MULT_SIDEWAYS, "SIDEWAYS → TP TIGHT"
        elif price_pos_pct < RANGE_HIGH_PCT or ann_vol < VOL_HIGH_THRESHOLD:
            tp_mult, label = TP_MULT_NORMAL, "NORMAL → TP BALANCED"
        else:
            tp_mult, label = TP_MULT_STRONG, "STRONG → TP WIDE"
        print(f"📊 {oanda_sym}: {label}")

        # ATR + SL/TP — 100% YOUR CODE
        pip_size = 0.01 if "JPY" in oanda_sym else 0.0001
        spread = 2 * pip_size
        try:
            candles = get_oanda_candles(oanda_sym, OANDA_GRAN, 50)
            rows = [{"High":float(c["mid"]["h"]),"Low":float(c["mid"]["l"]),"Close":float(c["mid"]["c"])}
                    for c in candles if c.get("complete") and all(k in c.get("mid",{}) for k in "hlc")]
            if not rows: raise ValueError("No candles")
            df = pd.DataFrame(rows)
            atr = ta.atr(df["High"], df["Low"], df["Close"], 14).iloc[-1]
            current_price = df.iloc[-1]["Close"]

            # Pivot — UNCHANGED
            if ENABLE_PIVOTS:
                prev_high = df.iloc[-2]["High"]
                prev_low = df.iloc[-2]["Low"]
                prev_close = df.iloc[-2]["Close"]
                pivots = calculate_pivots(prev_high, prev_low, prev_close, PIVOT_METHOD)
                if PIVOT_BIAS_CHECK:
                    if buy_cond and current_price > pivots["P"]:
                        print(f"✅ PIVOT BIAS: Price above Pivot — LONG confirmed")
                    elif sell_cond and current_price < pivots["P"]:
                        print(f"✅ PIVOT BIAS: Price below Pivot — SHORT confirmed")
                    else:
                        print(f"⏸️ PIVOT BIAS MISMATCH — skip")
                        buy_cond = sell_cond = False

            if not (buy_cond or sell_cond):
                continue

            decimals = 3 if "JPY" in oanda_sym else 5
            pip_size = 0.01 if "JPY" in oanda_sym else 0.0001
            spread = 2 * pip_size
            min_safe_distance = 5 * pip_size

            if buy_cond:
                direction = "BUY"
                sl = round(current_price - (atr * 1.8 + spread + min_safe_distance), decimals)
                tp = round(current_price + max(atr * tp_mult, min_safe_distance), decimals)
                tp = min(tp, range_90[1])
                tp = max(tp, current_price + min_safe_distance)
            else:
                direction = "SELL"
                sl = round(current_price + (atr * 1.8 + spread + min_safe_distance), decimals)
                tp = round(current_price - max(atr * tp_mult, min_safe_distance), decimals)
                tp = max(tp, range_90[0])
                tp = min(tp, current_price - min_safe_distance)

            print(f"📤 {direction} {oanda_sym} | SL={sl} TP={tp}")
            candidates.append({
                "pair": oanda_sym, "dir": direction,
                "prob": max(p_up,p_down), "sl": sl, "tp": tp
            })
            
        except Exception as e:
            print(f"❌ {oanda_sym}: SL/TP skipped — {e}")
            continue

    # --- Execute — EXACTLY YOUR CODE ---
    candidates.sort(key=lambda x:x["prob"], reverse=True)
    usd_count = jpy_count = total = 0

    for sig in candidates:
        if total >= MAX_TOTAL_TRADES: break
        if "USD" in sig["pair"] and usd_count >= MAX_PER_USD_GROUP: continue
        if "JPY" in sig["pair"] and jpy_count >= MAX_PER_JPY_GROUP: continue

        class MockSignal:
            def __init__(self, p, a, s, t, r=""):
                self.pair_to_trade = p
                self.action = a
                self.stop_loss = s
                self.take_profit = t
                self.reasoning = r

        mock_sig = MockSignal(
            sig["pair"], sig["dir"], sig["sl"], sig["tp"],
            f"MODE={MODE} | Prob={sig['prob']:.1f}%"
        )
        if get_open_position(mock_sig.pair_to_trade):
            print(f"double confirmation — skip execution for {mock_sig.pair_to_trade}")
            continue
        if execute_market_trade_v5(mock_sig, units_override=DEFAULT_LOT_SIZE):
            total += 1
            active_positions.add(sig["pair"])
            if "USD" in sig["pair"]: usd_count += 1
            if "JPY" in sig["pair"]: jpy_count += 1
        else:
            print(f"❌ Failed execution for {sig['pair']}")

    # --- Telegram — UNCHANGED ---
    msg_lines = [
        "🤖 FX TRADE BOT — RUN COMPLETE",
        f"🔹 Mode: {MODE} | New orders: {total}",
        f"🔹 Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n",
        get_position_summary()
    ]
    send_telegram_message("\n".join(msg_lines))


if __name__ == "__main__":
    print("[STRATEGY] Building currency strength matrix...")
    try:
        main()
    except Exception as e:
        err = f"❌ FATAL ERROR: {e}"
        print(err)
        send_telegram_message(err)