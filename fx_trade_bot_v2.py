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
from utils.oanda_execution import api, open_oanda_order
from utils.trading_core import get_candles as get_oanda_candles
from utils.calculate_currency_strength import calculate_currency_strength
from utils.strategy_helpers import build_strength_matrix, format_strength_ranking
from telegram_message import send_telegram_message
import numpy as np
import pandas as pd
import yfinance as yf
import json
import joblib
import pandas_ta as ta
import config

# --------------------------
# CONFIG HELPER — SINGLE SOURCE
# --------------------------
def cfg(name, default):
    return getattr(config, name, default)

# --------------------------
# LOAD ALL PARAMS FROM CONFIG
# --------------------------
MODE = cfg("MODE", "LEVEL10")
MIN_PROB = cfg("MIN_PROB", 0.50)
NORMAL_MIN_PROB = cfg("NORMAL_MIN_PROB", 51.0)
RELAXED_MIN_PROB = cfg("RELAXED_MIN_PROB", 50.0)
STRENGTH_GAP_THRESHOLD = cfg("STRENGTH_GAP_THRESHOLD", 10)
TREND_THRESHOLD = cfg("TREND_THRESHOLD", 20)
MAX_TOTAL_TRADES = cfg("MAX_TOTAL_TRADES", 3)
MAX_PER_USD_GROUP = cfg("MAX_PER_USD_GROUP", 3)
MAX_PER_JPY_GROUP = cfg("MAX_PER_JPY_GROUP", 3)
MC_TP_MAX_BAND_PCT = cfg("MC_TP_MAX_BAND_PCT", 0.7)
CLOSE_THRESHOLD = cfg("CLOSE_THRESHOLD", 55.0)
REOPEN_DELAY_RUNS = cfg("REOPEN_DELAY_RUNS", 2)
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

# --------------------------
# MARKET OPEN CHECK
# --------------------------
try:
    from utils.oanda_execution import is_forex_market_open
    if not is_forex_market_open():
        print("⏸️ Market is closed — skipping run")
        raise SystemExit(0)
except ImportError:
    pass

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
# LOAD MC RESULTS
# --------------------------
def load_mc_data(pair):
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    safe = pair.replace("=X", "").replace("=", "_")
    mc_path = RESULTS_DIR / f"fx_daily_{safe}_{today}.json"
    if mc_path.exists():
        with open(mc_path) as f:
            return json.load(f)
    return None

# --------------------------
# CORE UTILITIES
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

    closed_tracker = load_closed_pairs()
    today_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    active_positions = set()
    candidates = []

    for pair in DEFAULT_PAIRS:
        oanda_sym = YAHOO_TO_OANDA.get(pair, pair)
        base_cur, quote_cur = oanda_sym.split("_")

        if oanda_sym in active_positions:
            print(f"⏭️ {oanda_sym}: already open — skip")
            continue
        if closed_tracker.get(pair) == today_str:
            print(f"⏳ {oanda_sym}: cooldown active — skip")
            continue

        mc_data = load_mc_data(pair)
        if not mc_data:
            print(f"⚠️ {oanda_sym}: no MC data — skip")
            continue

        p_up = mc_data.get("p_up", 50.0)
        p_down = mc_data.get("p_down", 50.0)
        range_90 = mc_data.get("range_90", [1.0, 1.0])
        current_price = mc_data.get("current_price", (range_90[0] + range_90[1]) / 2)

        # Condition checks
        base_in_top = base_cur in top_n
        base_in_bot = base_cur in bottom_n
        quote_in_top = quote_cur in top_n
        quote_in_bot = quote_cur in bottom_n
        prob_ok_buy = p_up >= MIN_PROB * 100
        prob_ok_sell = p_down >= MIN_PROB * 100

        buy_cond = base_in_top and quote_in_bot and prob_ok_buy
        sell_cond = base_in_bot and quote_in_top and prob_ok_sell

        # 🛠️ DEBUG: show exactly why skipped
        if DEBUG_EDGE_REASON and not (buy_cond or sell_cond):
            reasons = []
            if not (base_in_top and quote_in_bot) and not (base_in_bot and quote_in_top):
                reasons.append("Strength mismatch (not strong vs weak)")
            if not prob_ok_buy and not prob_ok_sell:
                reasons.append(f"Probability too low ({max(p_up,p_down):.1f}% < {MIN_PROB*100:.0f}%)")
            print(f"🔍 {oanda_sym} | Base={base_cur} Quote={quote_cur} | Reason: {', '.join(reasons)}")

        if not (buy_cond or sell_cond):
            print(f"⏸️ {oanda_sym}: edge insufficient — skip")
            continue

        # Pivot & SL/TP logic
        pivot_ok = True
        entry_ok = True
        sl, tp = None, None
        if ENABLE_PIVOTS:
            try:
                candles = get_oanda_candles(oanda_sym, PIVOT_TIMEFRAME, 50)
                df = pd.DataFrame([{
                    "Open": float(c["mid"]["o"]), "High": float(c["mid"]["h"]),
                    "Low": float(c["mid"]["l"]), "Close": float(c["mid"]["c"]),
                    "Volume": c.get("volume", 0)
                } for c in candles if c.get("complete")])
                pivots = calculate_pivots(df)
                entry_ok = (MODE == "LEVEL10")
                if PIVOT_BIAS_CHECK and MODE != "LEVEL10":
                    if buy_cond and current_price < pivots["P"]: pivot_ok = False
                    if sell_cond and current_price > pivots["P"]: pivot_ok = False
                pip_size = 0.01 if "JPY" in pair else 0.0001
                spread = 3 * pip_size
                atr = ta.atr(df["High"], df["Low"], df["Close"], 14).iloc[-1]
                if buy_cond:
                    sl = current_price - (atr * 1.8 + spread)
                    tp = min(current_price + atr * 2.0, range_90[1] * MC_TP_MAX_BAND_PCT + current_price * (1 - MC_TP_MAX_BAND_PCT))
                else:
                    sl = current_price + (atr * 1.8 + spread)
                    tp = max(current_price - atr * 2.0, range_90[0] * MC_TP_MAX_BAND_PCT + current_price * (1 - MC_TP_MAX_BAND_PCT))
            except Exception as e:
                print(f"⚠️ {oanda_sym}: pivot calc failed — use ATR fallback: {e}")

        if sl is None or tp is None:
            try:
                candles = get_oanda_candles(oanda_sym, TIMEFRAME, 50)
                df = pd.DataFrame([{
                    "High": float(c["mid"]["h"]), "Low": float(c["mid"]["l"]), "Close": float(c["mid"]["c"])
                } for c in candles if c.get("complete")])
                atr = ta.atr(df["High"], df["Low"], df["Close"], 14).iloc[-1]
                if buy_cond:
                    sl = current_price - atr * 1.8
                    tp = current_price + atr * 2.0
                else:
                    sl = current_price + atr * 1.8
                    tp = current_price - atr * 2.0
            except:
                print(f"❌ {oanda_sym}: no SL/TP possible — skip")
                continue

        adx_ok = True if MODE == "LEVEL10" else (25 >= TREND_THRESHOLD)
        edge_ok = (p_up >= RELAXED_MIN_PROB or p_down >= RELAXED_MIN_PROB) if strength_gap >= STRENGTH_GAP_THRESHOLD else (p_up >= NORMAL_MIN_PROB or p_down >= NORMAL_MIN_PROB)

        if adx_ok and pivot_ok and entry_ok and edge_ok:
            direction = "BUY" if buy_cond else "SELL"
            candidates.append({
                "pair": oanda_sym, "dir": direction, "prob": max(p_up, p_down),
                "sl": round(sl, 3 if "JPY" in pair else 5),
                "tp": round(tp, 3 if "JPY" in pair else 5)
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
            if "USD" in sig["pair"]: usd_count +=1
            if "JPY" in sig["pair"]: jpy_count +=1
        else:
            print(f"❌ Order failed: {res.get('message', 'unknown error')}")

    send_telegram_message(f"🤖 BOT RUN COMPLETE — {total} ORDERS EXECUTED | MODE={MODE}")

if __name__ == "__main__":
    print("[STRATEGY] Step 1 — Building currency strength matrix...")
    try:
        main()
    except Exception as e:
        err = f"❌ FATAL: {e}"
        print(err)
        send_telegram_message(err)