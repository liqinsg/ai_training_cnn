# fx_trade_bot_v3.py
import sys
from pathlib import Path
from datetime import datetime, timezone
from enum import Enum

class Direction(Enum):
    LONG = "LONG"
    SHORT = "SHORT"

# --------------------------
# CONSOLIDATED PATH SETUP
# --------------------------
BASE_DIR = Path(__file__).resolve().parent
TELEBOT_PATH = Path.home() / "ai_training_cnn"
sys.path.extend([str(TELEBOT_PATH), str(BASE_DIR), str(BASE_DIR / "utils")])

# --------------------------
# IMPORTS
# --------------------------
from utils.trading_core import get_candles as get_oanda_candles, open_oanda_order, forex_market_closed, get_open_instruments
from utils.calculate_currency_strength import calculate_currency_strength
from utils.strategy_helpers import build_strength_matrix, format_strength_ranking
from telegram_message import send_telegram_message
import numpy as np
import pandas as pd
import yfinance as yf
import json
import pandas_ta as ta
import config
import contextlib
# --------------------------
# CONFIG HELPER
# --------------------------
def cfg(name, default):
    return getattr(config, name, default)

# --------------------------
# LOAD ALL PARAMS FROM CONFIG
# --------------------------
MODE = cfg("MODE", "LEVEL10")
MIN_PROB = cfg("MIN_PROB", 0.45)
NORMAL_MIN_PROB = cfg("NORMAL_MIN_PROB", 51.0)
RELAXED_MIN_PROB = cfg("RELAXED_MIN_PROB", 50.0)
STRENGTH_GAP_THRESHOLD = cfg("STRENGTH_GAP_THRESHOLD", 7)
TREND_THRESHOLD = cfg("TREND_THRESHOLD", 20)
MAX_TOTAL_TRADES = cfg("MAX_TOTAL_TRADES", 3)
MAX_PER_USD_GROUP = cfg("MAX_PER_USD_GROUP", 3)
MAX_PER_JPY_GROUP = cfg("MAX_PER_JPY_GROUP", 3)
DEFAULT_LOT_SIZE = cfg("DEFAULT_LOT_SIZE", 10000)
ENABLE_PIVOTS = cfg("ENABLE_PIVOTS", True)
PIVOT_METHOD = cfg("PIVOT_METHOD", "Classic")
PIVOT_TIMEFRAME = cfg("PIVOT_TIMEFRAME", "D")
PIVOT_BIAS_CHECK = cfg("PIVOT_BIAS_CHECK", True)
DEFAULT_PAIRS = cfg("DEFAULT_PAIRS", [])
YAHOO_TO_OANDA = cfg("YAHOO_TO_OANDA", {})
TIMEFRAME = cfg("TIMEFRAME", "15m")
ALLOW_TOP_N = cfg("ALLOW_TOP_N", 3)
ALLOW_BOTTOM_N = cfg("ALLOW_BOTTOM_N", 3)
DEBUG_EDGE_REASON = cfg("DEBUG_EDGE_REASON", False)

# Dynamic TP / Regime settings
VOL_LOW_THRESHOLD = cfg("VOL_LOW_THRESHOLD", 4.0)
VOL_HIGH_THRESHOLD = cfg("VOL_HIGH_THRESHOLD", 7.0)
RANGE_LOW_PCT = cfg("RANGE_LOW_PCT", 0.20)
RANGE_HIGH_PCT = cfg("RANGE_HIGH_PCT", 0.50)
TP_MULT_SIDEWAYS = cfg("TP_MULT_SIDEWAYS", 1.5)
TP_MULT_NORMAL = cfg("TP_MULT_NORMAL", 2.0)
TP_MULT_STRONG = cfg("TP_MULT_STRONG", 2.5)
MIN_TREND_STRENGTH = cfg("MIN_TREND_STRENGTH", 0.05)

# OANDA standard granularity codes
GRANULARITY_MAP = {
    "15m": "M15",
    "1h": "H1",
    "4h": "H4",
    "D": "D",
}
OANDA_GRAN = GRANULARITY_MAP.get(TIMEFRAME, "H1")

# --------------------------
# MARKET OPEN CHECK
# --------------------------
if forex_market_closed():
    print("⏸️ Market is closed — skipping run")
    raise SystemExit(0)
    
# --------------------------
# PERSISTENT COOLDOWN STORAGE
# --------------------------
RESULTS_DIR = BASE_DIR / "daily_results"
RESULTS_DIR.mkdir(exist_ok=True)
CLOSED_PAIRS_FILE = RESULTS_DIR / "closed_pairs.json"

def load_closed_pairs():
    if CLOSED_PAIRS_FILE.exists():
        with open(CLOSED_PAIRS_FILE) as f:
            return json.load(f)
    return {}

# --------------------------
# ✅ FIXED MC LOADER — MATCHES YOUR ACTUAL FILENAMES
# --------------------------
def load_mc_data(pair):
    now_utc = datetime.now(timezone.utc)
    date_str = now_utc.strftime("%Y%m%d")
    time_str = now_utc.strftime("%H%M")
    safe = pair.replace("=X", "").replace("=", "_")
    # Try exact timestamp first, then any file for today
    for tf in ["h4", "daily"]:
        mc_path = RESULTS_DIR / f"{tf}_mc_{safe}_{date_str}_{time_str}.json"
        if mc_path.exists():
            with open(mc_path) as f:
                return json.load(f)
    # Fallback: find latest file for this pair today
    for tf in ["h4", "daily"]:
        matches = sorted(RESULTS_DIR.glob(f"{tf}_mc_{safe}_{date_str}_*.json"), reverse=True)
        if matches:
            with open(matches[0]) as f:
                return json.load(f)
    print(f"⚠️ No MC data found for {pair}")
    return None

# --------------------------
# CALC PIVOTS
# --------------------------
def calculate_pivots(df):
    last = df.iloc[-1]
    h, l, c = last["High"], last["Low"], last["Close"]
    rng = h - l
    if PIVOT_METHOD == "Classic":
        return {
            "P": (h + l + c) / 3,
            "R1": 2 * (h + l + c) / 3 - l,
            "S1": 2 * (h + l + c) / 3 - h,
            "R2": (h + l + c) / 3 + rng,
            "S2": (h + l + c) / 3 - rng,
        }
    return {"P": (h + l + c) / 3}

# --------------------------
# MAIN EXECUTION
# --------------------------
def main():
    now = datetime.now(timezone.utc).strftime("%Y‑%m‑%d %H:%M UTC")
    print(f"\n🤖 FX TRADE BOT — {now} | MODE={MODE}")

    strength_scores = build_strength_matrix()
    ranked = sorted(strength_scores.items(), key=lambda x: x[1], reverse=True)

    top_strength, top_val = ranked[0]
    bot_strength, bot_val = ranked[-1]
    top_n = [c[0] for c in ranked[:ALLOW_TOP_N]]
    bottom_n = [c[0] for c in ranked[-ALLOW_BOTTOM_N:]]
    strength_gap = abs(top_val - bot_val)

    print(format_strength_ranking(strength_scores))
    print(f"📊 Strength Gap: {strength_gap:.2f} | Threshold: {STRENGTH_GAP_THRESHOLD}")
    print(f"🔝 Top {ALLOW_TOP_N}: {', '.join(top_n)} | 🔻 Bottom {ALLOW_BOTTOM_N}: {', '.join(bottom_n)}")

    active_positions = get_open_instruments()
    print(f"🔍 Open positions: {', '.join(active_positions) if active_positions else 'None'}")

    closed_tracker = load_closed_pairs()
    today_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    candidates = []

    for pair in DEFAULT_PAIRS:
        oanda_sym = YAHOO_TO_OANDA.get(pair, pair)
        base_cur, quote_cur = oanda_sym.split("_")

        if oanda_sym in active_positions:
            print(f"⏭️ {oanda_sym}: already open — skip duplicate")
            continue
        if closed_tracker.get(pair) == today_str:
            print(f"⏳ {oanda_sym}: cooldown active — skip")
            continue

        mc_data = load_mc_data(pair)
        if not mc_data:
            continue

        p_up = mc_data.get("p_up", 50.0)
        p_down = mc_data.get("p_down", 50.0)
        ann_vol = mc_data.get("ann_vol", 5.0)
        range_90 = mc_data.get("range_90", [1.0, 1.0])
        current_price = mc_data.get("current_price", (range_90[0] + range_90[1]) / 2)

        price_range = range_90[1] - range_90[0]
        price_pos_pct = (current_price - range_90[0]) / price_range if price_range > 0 else 0.5
        price_change_pct = ((current_price - range_90[0]) / range_90[0]) * 100 if range_90[0] != 0 else 0

        uptrend = price_change_pct > MIN_TREND_STRENGTH
        downtrend = price_change_pct < -MIN_TREND_STRENGTH

        if not uptrend and not downtrend:
            print(f"⏸️ {oanda_sym}: sideways market — wait for clear trend, skip")
            continue

        # ── DECISION + FULL DEBUG ──
        base_in_top = base_cur in top_n
        base_in_bot = base_cur in bottom_n
        quote_in_top = quote_cur in top_n
        quote_in_bot = quote_cur in bottom_n
        prob_ok_buy = p_up >= MIN_PROB * 100
        prob_ok_sell = p_down >= MIN_PROB * 100


        buy_cond = base_in_top and quote_in_bot and prob_ok_buy and uptrend
        sell_cond = base_in_bot and quote_in_top and prob_ok_sell and downtrend

        if DEBUG_EDGE_REASON:
            if buy_cond or sell_cond:
                dir_txt = "BUY" if buy_cond else "SELL"
                prob_txt = f"p_up={p_up:.1f}%" if buy_cond else f"p_down={p_down:.1f}%"
                trend_txt = "UP" if uptrend else "DOWN"
                print(f"✅ {oanda_sym}: QUALIFIED → {dir_txt} | {prob_txt} ≥ {MIN_PROB*100:.0f}% | Trend {trend_txt}")
            else:
                reasons = []
                if not (base_in_top and quote_in_bot) and not (base_in_bot and quote_in_top):
                    reasons.append("Strength mismatch")
                if not prob_ok_buy and not prob_ok_sell:
                    reasons.append(f"Probability {max(p_up,p_down):.1f}% < {MIN_PROB*100:.0f}%")
                if not uptrend and not downtrend:
                    reasons.append("Sideways / no clear trend")
                print(f"🔍 {oanda_sym} | REJECT: {'; '.join(reasons) if reasons else 'edge insufficient'}")

        if not (buy_cond or sell_cond):
            print(f"⏸️ {oanda_sym}: edge insufficient — skip")
            continue
        
        # Dynamic TP logic
        if price_pos_pct < RANGE_LOW_PCT or ann_vol < VOL_LOW_THRESHOLD:
            tp_multiplier = TP_MULT_SIDEWAYS
            regime_label = "📏 SIDEWAYS → TP TIGHT"
        elif price_pos_pct < RANGE_HIGH_PCT or ann_vol < VOL_HIGH_THRESHOLD:
            tp_multiplier = TP_MULT_NORMAL
            regime_label = "📈 NORMAL TREND → TP BALANCED"
        else:
            tp_multiplier = TP_MULT_STRONG
            regime_label = "🚀 STRONG TREND → TP WIDE"

        print(f"📊 {oanda_sym} REGIME: {regime_label} | Pos={price_pos_pct:.2f} Vol={ann_vol:.1f}% | TP ×{tp_multiplier}")

        sl, tp = None, None
        pip_size = 0.01 if "JPY" in oanda_sym else 0.0001
        spread = 3 * pip_size

        try:
            candles = get_oanda_candles(oanda_sym, OANDA_GRAN, 50)
            rows = []
            for c in candles:
                if not c.get("complete"):
                    continue
                mid = c.get("mid", {})
                if all(k in mid for k in ("h","l","c")):
                    rows.append({
                        "High": float(mid["h"]),
                        "Low": float(mid["l"]),
                        "Close": float(mid["c"])
                    })
            if not rows:
                raise ValueError("No complete candles")
            df = pd.DataFrame(rows)
            atr = ta.atr(df["High"], df["Low"], df["Close"], 14).iloc[-1]

            if buy_cond:
                sl = round(current_price - (atr * 1.8 + spread), 3 if "JPY" in oanda_sym else 5)
                tp = round(current_price + (atr * tp_multiplier), 3 if "JPY" in oanda_sym else 5)
                tp = min(tp, round(range_90[1], 3 if "JPY" in oanda_sym else 5))
            else:
                sl = round(current_price + (atr * 1.8 + spread), 3 if "JPY" in oanda_sym else 5)
                tp = round(current_price - (atr * tp_multiplier), 3 if "JPY" in oanda_sym else 5)
                tp = max(tp, round(range_90[0], 3 if "JPY" in oanda_sym else 5))

        except Exception as e:
            print(f"❌ {oanda_sym}: SL/TP calc skipped — {e}")
            continue

        direction = "BUY" if buy_cond else "SELL"
        candidates.append({
            "pair": oanda_sym, "dir": direction, "prob": max(p_up, p_down),
            "sl": sl, "tp": tp
        })

    # Execute respecting limits
    candidates.sort(key=lambda x: x["prob"], reverse=True)
    usd_count, jpy_count, total = 0, 0, 0

    for sig in candidates:
        if total >= MAX_TOTAL_TRADES: break
        if "USD" in sig["pair"] and usd_count >= MAX_PER_USD_GROUP: continue
        if "JPY" in sig["pair"] and jpy_count >= MAX_PER_JPY_GROUP: continue

        print(f"📤 ORDER: {sig['dir']} {sig['pair']} | SL={sig['sl']} TP={sig['tp']}")
        res = open_oanda_order(
            signal={
                "pair": sig["pair"],
                "action": sig["dir"],
                "stop_loss": sig["sl"],
                "take_profit": sig["tp"]
            },
            units=DEFAULT_LOT_SIZE if sig["dir"] == "BUY" else -DEFAULT_LOT_SIZE
        )
        if res.get("status") == "OK":
            total += 1
            active_positions.add(sig["pair"])
            if "USD" in sig["pair"]: usd_count +=1
            if "JPY" in sig["pair"]: jpy_count +=1
        else:
            print(f"❌ Order failed: {res.get('message', 'unknown error')}")

    # ──────────────────────────────────────────────────────────
    # 📤 BUILD FULL REPORT — SEND ONCE ONLY
    # ──────────────────────────────────────────────────────────
    msg_lines = []
    msg_lines.append(f"🤖 FX TRADE BOT — RUN COMPLETE")
    msg_lines.append(f"🔹 Mode: {MODE} | New orders: {total}")
    msg_lines.append(f"🔹 Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    msg_lines.append("")


    # === APPEND POSITION SUMMARY (REUSE YOUR MODULE) ===
    from check_positions import get_position_summary
    msg_lines.append(get_position_summary())

    # === SEND ALL IN ONE GO ===
    send_telegram_message("\n".join(msg_lines))
    # send_telegram_message(f"🤖 BOT RUN COMPLETE — {total} ORDERS EXECUTED | MODE={MODE}")
    
    # from check_positions import get_position_summary
    
    # msg_lines = []
    # msg_lines.append(get_position_summary())

    # # Then send as before:
    # send_telegram_message("\n".join(msg_lines))

if __name__ == "__main__":
    print("[STRATEGY] Step 1 — Building currency strength matrix...")
    try:
        main()
    except Exception as e:
        err = f"❌ FATAL: {e}"
        print(err)
        send_telegram_message(err)