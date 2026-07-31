from utils.oanda_execution import api, open_oanda_order, has_open_position, get_oanda_candles, is_forex_market_open
from utils.calculate_currency_strength import calculate_currency_strength
from utils.strategy_helpers import build_strength_matrix, format_strength_ranking
from telegram_message import send_telegram_message
import numpy as np
import pandas as pd
import yfinance as yf
import json
import joblib
import sys
from datetime import datetime, timezone
from pathlib import Path
import pandas_ta as ta
import config

# Exit immediately if market is closed
if not is_forex_market_open():
    print("⏸️ Market is closed — skipping run")
    raise SystemExit(0)

# --------------------------
# 🧩 CONFIG — ONE SOURCE OF TRUTH
# --------------------------


def cfg(name, default):
    return getattr(config, name, default)


# ✅ SET YOUR DATA SOURCE HERE
USE_OANDA_DATA = cfg("USE_OANDA_DATA", True)   # True = OANDA, False = yfinance
USE_YFINANCE_DATA = not USE_OANDA_DATA

OANDA_ACCOUNT_ID = cfg("OANDA_ACCOUNT_ID", "")
assert OANDA_ACCOUNT_ID.strip(), "OANDA_ACCOUNT_ID is empty. Set it in your .env / environment."

# --- Auto‑set all parameters from MODE ---
MODE = cfg("MODE", "TESTING")
if MODE == "TESTING":
    MIN_PROB = cfg("MIN_PROB", 0.50)
    TREND_THRESHOLD = cfg("TREND_THRESHOLD", 20)
    MAX_TOTAL_TRADES = cfg("MAX_TOTAL_TRADES", 3)
    MAX_PER_USD_GROUP = cfg("MAX_PER_USD_GROUP", 3)
    MAX_PER_JPY_GROUP = cfg("MAX_PER_JPY_GROUP", 3)
else:
    MIN_PROB = cfg("MIN_PROB", 0.52)
    TREND_THRESHOLD = cfg("TREND_THRESHOLD", 25)
    MAX_TOTAL_TRADES = cfg("MAX_TOTAL_TRADES", 2)
    MAX_PER_USD_GROUP = cfg("MAX_PER_USD_GROUP", 2)
    MAX_PER_JPY_GROUP = cfg("MAX_PER_JPY_GROUP", 2)

DEFAULT_PAIRS = cfg("DEFAULT_PAIRS", [
    "EURUSD=X", "GBPUSD=X", "EURJPY=X", "GBPJPY=X", "AUDUSD=X", "USDJPY=X", "GBPAUD=X",
    "USDCHF=X"
])
YAHOO_TO_OANDA = cfg("YAHOO_TO_OANDA", {
    "EURUSD=X": "EUR_USD", "GBPUSD=X": "GBP_USD", "EURJPY=X": "EUR_JPY",
    "GBPJPY=X": "GBP_JPY", "AUDUSD=X": "AUD_USD", "USDJPY=X": "USD_JPY",
    "GBPAUD=X": "GBP_AUD", "USDCHF=X": "USD_CHF"
})
TIMEFRAME = cfg("TIMEFRAME", "15m")
MC_MAX_AGE_HOURS = cfg("MC_MAX_AGE_HOURS", 24)
CHECK_INTERVAL_MINUTES = cfg("CHECK_INTERVAL_MINUTES", 15)

# --- Pivot Settings ---
ENABLE_PIVOTS = cfg("ENABLE_PIVOTS", True)
PIVOT_METHOD = cfg("PIVOT_METHOD", "Classic")
PIVOT_TIMEFRAME = cfg("PIVOT_TIMEFRAME", "D")
PIVOT_BIAS_CHECK = cfg("PIVOT_BIAS_CHECK", True)

TELEBOT_PATH = Path.home() / "ai_training_cnn"
sys.path.append(str(TELEBOT_PATH))
sys.path.append(str(Path(__file__).parent / "utils"))
BASE_DIR = Path(__file__).resolve().parent


def resample_ohlc(df: pd.DataFrame, rule: str = "D") -> pd.DataFrame:
    """Resample OHLCV to higher timeframe — returns clean OHLC"""
    return df.resample(rule).agg({
        "Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"
    })


def calculate_pivots(prev_high: float, prev_low: float, prev_close: float, pivot_type: str = "Classic") -> dict:
    """Standard pivot calculation — Classic / Fibonacci / Camarilla / Woodie"""
    high, low, close = float(prev_high), float(prev_low), float(prev_close)
    rng = high - low
    if pivot_type == "Classic":
        p = (high + low + close) / 3
        return {
            "R3": round(p + 2 * rng, 3), "R2": round(p + rng, 3), "R1": round(2 * p - low, 3),
            "P": round(p, 3), "S1": round(2 * p - high, 3), "S2": round(p - rng, 3), "S3": round(p - 2 * rng, 3)
        }
    elif pivot_type == "Fibonacci":
        p = (high + low + close) / 3
        return {
            "R3": round(p + rng * 1.000, 3), "R2": round(p + rng * 0.618, 3), "R1": round(p + rng * 0.382, 3),
            "P": round(p, 3), "S1": round(p - rng * 0.382, 3), "S2": round(p - rng * 0.618, 3), "S3": round(p - rng * 1.000, 3)
        }
    elif pivot_type == "Camarilla":
        h4 = close + (high - low) * 1.1 / 4
        h3 = close + (high - low) * 1.1 / 6
        h2 = close + (high - low) * 1.1 / 12
        h1 = close + (high - low) * 1.1 / 24
        l1 = close - (high - low) * 1.1 / 24
        l2 = close - (high - low) * 1.1 / 12
        l3 = close - (high - low) * 1.1 / 6
        l4 = close - (high - low) * 1.1 / 4
        return {
            "R3": round(h3, 3), "R2": round(h2, 3), "R1": round(h1, 3),
            "P": round((high + low + close) / 3, 3),
            "S1": round(l1, 3), "S2": round(l2, 3), "S3": round(l3, 3)
        }
    elif pivot_type == "Woodie":
        p = (2 * close + high + low) / 4
        return {
            "R3": round(p + rng * 2, 3), "R2": round(p + rng, 3), "R1": round(2 * p - low, 3),
            "P": round(p, 3), "S1": round(2 * p - high, 3), "S2": round(p - rng, 3), "S3": round(p - rng * 2, 3)
        }
    return None


def is_market_open():
    try:
        from oandapyV20.endpoints.instruments import InstrumentsCandles
        r = InstrumentsCandles(instrument="EUR_USD", params={"count": 1, "granularity": "M1"})
        return bool(api.request(r).get("candles"))
    except:
        return False


def get_open_position(instrument: str):
    if not has_open_position(instrument):
        return None
    try:
        from oandapyV20.endpoints.positions import PositionDetails
        pos = api.request(PositionDetails(accountID=OANDA_ACCOUNT_ID, instrument=instrument)).get("position", {})
        if pos.get("long", {}).get("units", "0") != "0":
            return {"units": int(pos["long"]["units"])}
        if pos.get("short", {}).get("units", "0") != "0":
            return {"units": -int(pos["short"]["units"])}
        return None
    except Exception as e:
        print(f"ℹ️ Position check: {instrument} — skipping new entry")
        return {"units": 1}


def close_position(instrument: str):
    try:
        from oandapyV20.endpoints.positions import PositionDetails
        from oandapyV20.endpoints.orders import OrderCreate
        pos = api.request(PositionDetails(accountID=OANDA_ACCOUNT_ID, instrument=instrument)).get("position", {})
        if pos.get("long", {}).get("units", "0") != "0":
            units = -int(pos["long"]["units"])
        elif pos.get("short", {}).get("units", "0") != "0":
            units = abs(int(pos["short"]["units"]))
        else:
            print(f"ℹ️ No open position on {instrument}")
            return
        data = {"order": {"type": "MARKET", "instrument": instrument, "units": str(units), "positionFill": "REDUCE_ONLY"}}
        api.request(OrderCreate(accountID=OANDA_ACCOUNT_ID, data=data))
        print(f"✅ Closed {instrument} — units: {abs(units)}")
        send_telegram_message(f"🔄 AUTO‑CLOSE EXECUTED: {instrument} — Trend reversed")
    except Exception as e:
        print(f"❌ Close failed: {e}")


def build_features(df):
    df = df.copy()
    df["return"] = df["Close"].pct_change()
    for p in [5, 10, 20, 50]:
        df[f"sma_{p}"] = ta.sma(df["Close"], p)
        df[f"ema_{p}"] = ta.ema(df["Close"], p)
        df[f"dist_sma_{p}"] = (df["Close"] - df[f"sma_{p}"]) / df[f"sma_{p}"]
    df["rsi"] = ta.rsi(df["Close"], 14)
    df = pd.concat([df, ta.macd(df["Close"]), ta.adx(df["High"], df["Low"], df["Close"], 14)], axis=1)
    df["atr14"] = ta.atr(df["High"], df["Low"], df["Close"], 14)
    df["vol_20"] = df["return"].rolling(20).std() * np.sqrt(252 * 24)
    df["body"] = abs(df["Close"] - df["Open"]) / df["Open"]
    return df


def load_mc(pair):
    safe = pair.replace("=X", "").replace("=", "_")
    f = BASE_DIR / "daily_results" / f"fx_daily_{safe}_{datetime.now(timezone.utc).strftime('%Y%m%d')}.json"
    if not f.exists():
        print(f"⚠️ MC missing for {pair}")
        return None, False
    age = (datetime.now(timezone.utc) - datetime.fromtimestamp(f.stat().st_mtime, timezone.utc)).total_seconds() / 3600
    if age > MC_MAX_AGE_HOURS:
        print(f"⚠️ MC stale for {pair}")
        return None, False
    with open(f) as j:
        return json.load(j), True


# --------------------------
# 🧠 LOAD MODEL
# --------------------------
model = joblib.load(BASE_DIR / "trade_model.pkl")
with open(BASE_DIR / "features_list.json") as f:
    features = json.load(f)


# --------------------------
# 🚀 MAIN LOGIC
# --------------------------
def main():
    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    print(f"\n🤖 MULTI‑PAIR RUN — {now} | MODE={MODE} | DATA={'OANDA' if USE_OANDA_DATA else 'YFINANCE'} | {DEFAULT_PAIRS}")

    if not is_market_open():
        print("⏳ Market closed")
        return

    # --- Helper: Get data from selected source ---
    def get_data(pair, oanda_sym, count=200):
        if USE_OANDA_DATA:
            print(f"📥 Fetching OANDA data: {oanda_sym}")
            return get_oanda_candles(oanda_sym, TIMEFRAME, count)
        else:
            print(f"📥 Fetching yfinance data: {pair}")
            df = yf.download(pair, period="5d", interval=TIMEFRAME, progress=False)
            df.columns = [c[0] for c in df.columns]
            return df[["Open", "High", "Low", "Close", "Volume"]]

    # Step 1: Auto‑close reversed trends
    for pair in DEFAULT_PAIRS:
        oanda = YAHOO_TO_OANDA[pair]
        pos = get_open_position(oanda)
        if not pos:
            continue

        df = get_data(pair, oanda, count=200)
        df = build_features(df).dropna()
        if len(df) < 5:
            continue
        latest = df.iloc[-1]
        p_up = model.predict_proba(pd.DataFrame([latest[features]]))[0, 1]
        p_down = 1 - p_up

        if pos["units"] > 0 and p_down > p_up and max(p_up, p_down) >= MIN_PROB:
            print(f"🔄 AUTO‑CLOSE LONG {pair} — DOWN {p_down:.1%}")
            close_position(oanda)
        if pos["units"] < 0 and p_up > p_down and max(p_up, p_down) >= MIN_PROB:
            print(f"🔄 AUTO‑CLOSE SHORT {pair} — UP {p_up:.1%}")
            close_position(oanda)

    # Step 2: Scan for new signals
    candidates = []
    for pair in DEFAULT_PAIRS:
        oanda = YAHOO_TO_OANDA[pair]
        if get_open_position(oanda):
            print(f"⏭️ {pair}: already open — skip")
            continue

        df = get_data(pair, oanda, count=200)
        df = build_features(df).dropna()
        if len(df) < 20:
            continue
        latest = df.iloc[-1]

        # --- Monte Carlo Alignment ---
        mc_data, mc_ok = load_mc(pair)
        align = True
        if mc_ok:
            pos_rel = (latest["Close"] - mc_data["range_90"][0]) / (mc_data["range_90"][1] - mc_data["range_90"][0])
            if mc_data["ann_drift"] > 0.1 and pos_rel > 0.90:
                align = False
            if mc_data["ann_drift"] < -0.1 and pos_rel < 0.10:
                align = False
            if mc_data["ann_drift"] < -0.1 and latest["Close"] > mc_data["range_90"][0] * 1.08:
                align = False
            if mc_data["ann_drift"] > 0.1 and latest["Close"] < mc_data["range_90"][1] * 0.92:
                align = False

        # --- ML + Trend + Direction ---
        p_up = model.predict_proba(pd.DataFrame([latest[features]]))[0, 1]
        p_down = 1 - p_up
        adx = latest["ADX_14"]
        best_p = max(p_up, p_down)
        best_dir = "BUY" if p_up > p_down else "SELL"

        # --- Pivot Calculation + SMART ENTRY / SL / TP ---
        pivots = None
        pivot_ok = True
        entry_ok = False
        target_sl = None
        target_tp = None

        # ✅ YOUR SAFETY RULES
        PIP_BUFFER = 25       # Extra room: 20–30 pips
        SPREAD_ALLOWANCE = 0  # Fallback only

        if ENABLE_PIVOTS:
            daily = resample_ohlc(df, rule=PIVOT_TIMEFRAME).dropna()
            if len(daily) >= 2:
                prev = daily.iloc[-2]
                pivots = calculate_pivots(prev["High"], prev["Low"], prev["Close"], PIVOT_METHOD)
                curr = latest["Close"]

                # --- Pivot Bias Check ---
                if PIVOT_BIAS_CHECK and pivots:
                    if best_dir == "SELL" and curr > pivots["P"]:
                        pivot_ok = False
                    if best_dir == "BUY" and curr < pivots["P"]:
                        pivot_ok = False

                # --- ✅ GET LIVE SPREAD FROM OANDA ---
                live_spread_pips = SPREAD_ALLOWANCE
                try:
                    from oandapyV20.endpoints.instruments import InstrumentsCandles
                    spread_resp = api.request(InstrumentsCandles(
                        instrument=oanda,
                        params={"count": 1, "granularity": "M1", "price": "BA"}
                    ))
                    tick = spread_resp["candles"][0]
                    ask = float(tick["ask"]["c"])
                    bid = float(tick["bid"]["c"])
                    spread_raw = ask - bid
                    live_spread_pips = abs(spread_raw / 0.01) if "JPY" in oanda else abs(spread_raw / 0.0001)
                    print(f"📊 {pair} Live Spread: {live_spread_pips:.1f} pips")
                except Exception as e:
                    print(f"⚠️ {pair} Using fallback spread: {SPREAD_ALLOWANCE} pips")

                # --- ✅ ONLY ENTER AT VALID LEVELS + PIP-BASED SL ---
                if pivots and pivot_ok:
                    decimals = 3 if "JPY" in pair else 5
                    if best_dir == "SELL":
                        near_r = abs(curr - pivots["R1"]) / curr < 0.0015 or abs(curr - pivots["P"]) / curr < 0.0015
                        if near_r:
                            entry_ok = True
                            sl_base = max(pivots["R1"], pivots["P"])
                            total_buffer = live_spread_pips + PIP_BUFFER
                            pip_size = 0.01 if "JPY" in pair else 0.0001
                            target_sl = round(sl_base + total_buffer * pip_size, decimals)
                            target_tp = round(pivots["S1"], decimals)

                    if best_dir == "BUY":
                        near_s = abs(curr - pivots["S1"]) / curr < 0.0015 or abs(curr - pivots["P"]) / curr < 0.0015
                        if near_s:
                            entry_ok = True
                            sl_base = min(pivots["S1"], pivots["P"])
                            total_buffer = live_spread_pips + PIP_BUFFER
                            pip_size = 0.01 if "JPY" in pair else 0.0001
                            target_sl = round(sl_base - total_buffer * pip_size, decimals)
                            target_tp = round(pivots["R1"], decimals)

        # --- Debug Log ---
        pivot_text = f" | PIVOT={pivots['P']:.3f}" if pivots else ""
        print(f"🔍 CHECK: {pair:12} | P_UP={p_up:.1%} | P_DOWN={p_down:.1%} | ADX={adx:5.1f} | ALIGN={align} | PIVOT_OK={pivot_ok}{pivot_text} | ENTRY_OK={entry_ok} | DIR={best_dir} | PROB={best_p:.1%}")

        # --- All Filters Combined ---
        if best_p >= MIN_PROB and adx >= TREND_THRESHOLD and align and pivot_ok and entry_ok:
            candidates.append({
                "pair": pair, "oanda": oanda, "dir": best_dir,
                "prob": best_p, "sl": target_sl, "tp": target_tp
            })

    # Step 3: Apply correlation & limits
    winners = []
    usd = jpy = 0
    candidates.sort(key=lambda x: x["prob"], reverse=True)
    for c in candidates:
        if "USD=X" in c["pair"] and c["pair"] != "USDJPY=X":
            if usd >= MAX_PER_USD_GROUP:
                continue
            usd += 1
        if "JPY" in c["pair"]:
            if jpy >= MAX_PER_JPY_GROUP:
                continue
            jpy += 1
        if len(winners) >= MAX_TOTAL_TRADES:
            break
        winners.append(c)

    # Step 4: Execute
    lines = [f"🤖 MULTI‑PAIR UPDATE — {now}"]
    if not winners:
        lines.append("➡️ No high‑probability setups found")
    else:
        for w in winners:
            res = open_oanda_order({
                "pair": w["oanda"],
                "action": w["dir"],
                "stop_loss": w["sl"],
                "take_profit": w["tp"]
            }, tag=f"FX_{w['dir']}_{w['pair'].replace('=X', '')}_15m")
            print(f"📤 Order result: {res}")
            lines.append(f"✅ {w['pair']} | {w['dir']} | Prob: {w['prob']:.1%} | SL={w['sl']} | TP={w['tp']}")

    msg = "\n".join(lines)
    print(msg)
    send_telegram_message(msg)
    print("✅ Run complete")


def currency_strength():
    scores = build_strength_matrix()
    strength_report = format_strength_ranking(scores)
    print(strength_report)


if __name__ == "__main__":
    print("[STRATEGY] Step 1 — Building currency strength matrix...")
    currency_strength()
    try:
        main()
    except Exception as e:
        err = f"❌ Error: {e}"
        print(err)
        send_telegram_message(err)
