import sys
from pathlib import Path
from datetime import datetime, timezone
from enum import Enum


class Direction(Enum):
    LONG = "LONG"
    SHORT = "SHORT"

# --------------------------
# 🧩 CONSOLIDATED PATH SETUP
# --------------------------
BASE_DIR = Path(__file__).resolve().parent
TELEBOT_PATH = Path.home() / "ai_training_cnn"
sys.path.extend([str(TELEBOT_PATH), str(BASE_DIR), str(BASE_DIR / "utils")])

# --------------------------
# 🧩 IMPORTS — NO DUPLICATES
# --------------------------
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
from config_oanda import OANDA_API_TOKEN, OANDA_ACCOUNT_ID, OANDA_ENV
import config_gemini
from utils.find_support_resistence import get_support_resistance
import oandapyV20

api = oandapyV20.API(access_token=OANDA_API_TOKEN, environment=OANDA_ENV)


# --------------------------
# 🧩 CONFIG — ONE SOURCE OF TRUTH
# --------------------------
def cfg(name, default):
    return getattr(config, name, default)


units = cfg("DEFAULT_LOT_SIZE", 10000)

# Data source
USE_OANDA_DATA = True

assert OANDA_ACCOUNT_ID.strip(), "OANDA_ACCOUNT_ID is empty — check .env"

# Mode‑based parameters
MODE = cfg("MODE", "LEVEL10")
MIN_PROB = cfg("MIN_PROB", 0.50)
TREND_THRESHOLD = cfg("TREND_THRESHOLD", 25)
MAX_TOTAL_TRADES = cfg("MAX_TOTAL_TRADES", 2)
MAX_PER_USD_GROUP = cfg("MAX_PER_USD_GROUP", 2)
MAX_PER_JPY_GROUP = cfg("MAX_PER_JPY_GROUP", 2)
NORMAL_MIN_PROB = cfg("MIN_PROB", 51.0)
RELAXED_MIN_PROB = 50.0  # ✅ FORCED 50.0% FOR LEVEL10
STRENGTH_GAP_THRESHOLD = cfg("STRENGTH_GAP_THRESHOLD", 10)

# Trading pairs & mappings
DEFAULT_PAIRS = cfg(
    "DEFAULT_PAIRS",
    [
        "EURUSD=X",
        "GBPUSD=X",
        "EURJPY=X",
        "GBPJPY=X",
        "AUDUSD=X",
        "USDJPY=X",
        "GBPAUD=X",
        "USDCHF=X",
    ],
)
YAHOO_TO_OANDA = cfg(
    "YAHOO_TO_OANDA",
    {
        "EURUSD=X": "EUR_USD",
        "GBPUSD=X": "GBP_USD",
        "EURJPY=X": "EUR_JPY",
        "GBPJPY=X": "GBP_JPY",
        "AUDUSD=X": "AUD_USD",
        "USDJPY=X": "USD_JPY",
        "GBPAUD=X": "GBP_AUD",
        "USDCHF=X": "USD_CHF",
    },
)

# Timeframes
TIMEFRAME = cfg("TIMEFRAME", "15m")
OANDA_GRANULARITY_MAP = {
    "1m": "M1",
    "5m": "M5",
    "15m": "M15",
    "30m": "M30",
    "1h": "H1",
    "4h": "H4",
    "1d": "D",
}
OANDA_GRANULARITY = OANDA_GRANULARITY_MAP.get(TIMEFRAME, "M15")
MC_MAX_AGE_HOURS = cfg("MC_MAX_AGE_HOURS", 24)
CHECK_INTERVAL_MINUTES = cfg("CHECK_INTERVAL_MINUTES", 15)

# Pivot settings
ENABLE_PIVOTS = cfg("ENABLE_PIVOTS", True)
PIVOT_METHOD = cfg("PIVOT_METHOD", "Classic")
PIVOT_TIMEFRAME = cfg("PIVOT_TIMEFRAME", "D")
PIVOT_BIAS_CHECK = cfg("PIVOT_BIAS_CHECK", True)

# File paths
RESULTS_DIR = BASE_DIR / "daily_results"
RESULTS_DIR.mkdir(exist_ok=True)
TODAY_STR = datetime.now(timezone.utc).strftime("%Y%m%d")


CLOSE_THRESHOLD = 55.0  # Need 55%+ flipped prob to close
REOPEN_DELAY_RUNS = 2  # Wait 2 runs before re-opening same pair
last_closed = {}  # Track: {pair: (direction, run_count)}


# --------------------------
# 🛡️ MARKET STATUS CHECK
# --------------------------

if forex_market_closed():
    print("⏸️ Market closed — skipping run")
    send_telegram_message("⏸️ FX BOT: Market closed")
    raise SystemExit(0)


# --------------------------
# 🧩 HELPER FUNCTIONS
# --------------------------
def resample_ohlc(df: pd.DataFrame, rule: str = "D") -> pd.DataFrame:
    """Resample OHLCV safely — requires DatetimeIndex"""
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("DataFrame must have DatetimeIndex for resampling")
    return (
        df.resample(rule)
        .agg(
            {
                "Open": "first",
                "High": "max",
                "Low": "min",
                "Close": "last",
                "Volume": "sum",
            }
        )
        .dropna()
    )


def calculate_pivots(prev_high, prev_low, prev_close, pivot_type="Classic") -> dict:
    high, low, close = float(prev_high), float(prev_low), float(prev_close)
    rng = high - low
    if pivot_type == "Classic":
        p = (high + low + close) / 3
        return {
            "R3": round(p + 2 * rng, 3),
            "R2": round(p + rng, 3),
            "R1": round(2 * p - low, 3),
            "P": round(p, 3),
            "S1": round(2 * p - high, 3),
            "S2": round(p - rng, 3),
            "S3": round(p - 2 * rng, 3),
        }
    elif pivot_type == "Fibonacci":
        p = (high + low + close) / 3
        return {
            "R3": round(p + rng * 1.0, 3),
            "R2": round(p + rng * 0.618, 3),
            "R1": round(p + rng * 0.382, 3),
            "P": round(p, 3),
            "S1": round(p - rng * 0.382, 3),
            "S2": round(p - rng * 0.618, 3),
            "S3": round(p - rng * 1.0, 3),
        }
    elif pivot_type == "Camarilla":
        h3 = close + (high - low) * 1.1 / 6
        h2 = close + (high - low) * 1.1 / 12
        h1 = close + (high - low) * 1.1 / 24
        l1 = close - (high - low) * 1.1 / 24
        l2 = close - (high - low) * 1.1 / 12
        l3 = close - (high - low) * 1.1 / 6
        return {
            "R3": round(h3, 3),
            "R2": round(h2, 3),
            "R1": round(h1, 3),
            "P": round((high + low + close) / 3, 3),
            "S1": round(l1, 3),
            "S2": round(l2, 3),
            "S3": round(l3, 3),
        }
    elif pivot_type == "Woodie":
        p = (2 * close + high + low) / 4
        return {
            "R3": round(p + 2 * rng, 3),
            "R2": round(p + rng, 3),
            "R1": round(2 * p - low, 3),
            "P": round(p, 3),
            "S1": round(2 * p - high, 3),
            "S2": round(p - rng, 3),
            "S3": round(p - 2 * rng, 3),
        }


def get_open_position(instrument: str):
    try:
        from oandapyV20.endpoints.positions import PositionDetails

        pos = api.request(
            PositionDetails(accountID=OANDA_ACCOUNT_ID, instrument=instrument)
        ).get("position", {})
        if pos.get("long", {}).get("units", "0") != "0":
            return {"units": int(pos["long"]["units"])}
        if pos.get("short", {}).get("units", "0") != "0":
            return {"units": -int(pos["short"]["units"])}
        return None
    except Exception:
        print(f"ℹ️ Position check: {instrument} — skip")
        return None


def close_position(instrument: str):
    try:
        from oandapyV20.endpoints.positions import PositionDetails
        from oandapyV20.endpoints.orders import OrderCreate

        pos = api.request(
            PositionDetails(accountID=OANDA_ACCOUNT_ID, instrument=instrument)
        ).get("position", {})
        if pos.get("long", {}).get("units", "0") != "0":
            units = -int(pos["long"]["units"])
        elif pos.get("short", {}).get("units", "0") != "0":
            units = abs(int(pos["short"]["units"]))
        else:
            print(f"ℹ️ No position: {instrument}")
            return
        api.request(
            OrderCreate(
                accountID=OANDA_ACCOUNT_ID,
                data={
                    "order": {
                        "type": "MARKET",
                        "instrument": instrument,
                        "units": str(units),
                        "positionFill": "REDUCE_ONLY",
                    }
                },
            )
        )
        print(f"✅ Closed {instrument} — {abs(units)} units")
        send_telegram_message(f"🔄 AUTO‑CLOSE: {instrument} — trend reversed")
    except Exception as e:
        print(f"❌ Close failed: {e}")


def normalize_ohlc_data(data):
    if isinstance(data, pd.DataFrame):
        df = data.copy()
    elif isinstance(data, list):
        rows = []
        for c in data:
            mid = c.get("mid", {})
            if not mid:
                continue
            try:
                rows.append(
                    {
                        "time": pd.to_datetime(c["time"]),
                        "Open": float(mid["o"]),
                        "High": float(mid["h"]),
                        "Low": float(mid["l"]),
                        "Close": float(mid["c"]),
                        "Volume": float(c.get("volume", 0)),
                    }
                )
            except:
                continue
        df = pd.DataFrame(rows)
        if not df.empty:
            df = df.set_index("time")
    else:
        raise TypeError("Unsupported data type")
    if df.empty:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    return df.astype(
        {"Open": float, "High": float, "Low": float, "Close": float, "Volume": float}
    )


def build_features(df):
    df = df.copy()
    df["return"] = df["Close"].pct_change()

    for p in [5, 10, 20, 50]:
        df[f"sma_{p}"] = ta.sma(df["Close"], p)
        df[f"ema_{p}"] = ta.ema(df["Close"], p)
        df[f"dist_sma_{p}"] = (df["Close"] - df[f"sma_{p}"]) / df[f"sma_{p}"]

    df["rsi"] = ta.rsi(df["Close"], 14)

    macd = ta.macd(df["Close"])
    df = pd.concat([df, macd], axis=1)

    adx = ta.adx(df["High"], df["Low"], df["Close"], length=14)
    df = pd.concat([df, adx], axis=1)
    if "ADXR_14" in df.columns and "ADXR_14_2" not in df.columns:
        df = df.rename(columns={"ADXR_14": "ADXR_14_2"})

    df["atr14"] = ta.atr(df["High"], df["Low"], df["Close"], 14)
    df["vol_20"] = df["return"].rolling(20).std() * np.sqrt(252 * 24)
    df["body"] = abs(df["Close"] - df["Open"]) / df["Open"]

    return df


def load_mc(pair):
    safe = pair.replace("=X", "").replace("=", "_")
    f = RESULTS_DIR / f"fx_daily_{safe}_{TODAY_STR}.json"
    if not f.exists():
        print(f"⚠️ MC missing: {pair}")
        return None, False
    age = (
        datetime.now(timezone.utc)
        - datetime.fromtimestamp(f.stat().st_mtime, timezone.utc)
    ).total_seconds() / 3600
    if age > MC_MAX_AGE_HOURS:
        print(f"⚠️ MC stale: {pair}")
        return None, False
    with open(f) as j:
        return json.load(j), True


def open_oanda_order(signal: dict, units: float | None = None) -> dict:
    """
    Open a market order with Stop Loss & Take Profit — OANDA verified working format.
    Expected keys: pair, action, stop_loss, take_profit
    """
    if not OANDA_ACCOUNT_ID or not OANDA_API_TOKEN:
        return {"status": "ERROR", "message": "Missing OANDA credentials"}

    pair_raw = signal.get("pair")
    if not pair_raw:
        return {"status": "ERROR", "message": "Signal missing 'pair'"}

    action = signal.get("action")
    if action not in {"BUY", "SELL"}:
        return {"status": "ERROR", "message": f"Invalid action: {action}"}

    if units is None:
        units = 10000
    units = int(units) if action == "BUY" else -int(units)

    sl = signal.get("stop_loss")
    tp = signal.get("take_profit")
    print(f"🔍 SENDING SL/TP for {pair_raw}: SL={sl} | TP={tp}")

    if sl is None or tp is None:
        return {"status": "ERROR", "message": f"SL/TP missing! SL={sl}, TP={tp}"}

    decimals = 3 if "JPY" in pair_raw else 5

    # ✅ NO DELETIONS — ALWAYS INCLUDE SL/TP IN CORRECT OANDA FORMAT
    order_payload = {
        "order": {
            "type": "MARKET",
            "instrument": pair_raw,
            "units": str(units),
            "timeInForce": "FOK",
            "positionFill": "DEFAULT",
            "stopLossOnFill": {
                "price": str(round(float(sl), decimals)),
                "timeInForce": "GTC",
            },
            "takeProfitOnFill": {
                "price": str(round(float(tp), decimals)),
                "timeInForce": "GTC",
            },
        }
    }

    try:
        from oandapyV20.endpoints.orders import OrderCreate

        resp = api.request(OrderCreate(accountID=OANDA_ACCOUNT_ID, data=order_payload))
        print("✅ OANDA ACCEPTED — SL/TP ATTACHED")
        return {"status": "OK", "response": resp}
    except Exception as e:
        return {"status": "ERROR", "message": f"OANDA API Error: {e}"}


# --------------------------
# 🧠 LOAD MODEL
# --------------------------
model = joblib.load(BASE_DIR / "trade_model.pkl")
with open(BASE_DIR / "features_list.json") as f:
    features = json.load(f)


# --------------------------
# 🚀 MAIN LOGIC
# --------------------------
# --------------------------
# 🚀 MAIN LOGIC
# --------------------------
def main():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n🤖 MULTI‑PAIR RUN — {now} | MODE={MODE} | DATA={'OANDA' if USE_OANDA_DATA else 'YFINANCE'} | {DEFAULT_PAIRS}")

    def get_data(pair, oanda_sym, count=200):
        if USE_OANDA_DATA:
            print(f"📥 OANDA: {oanda_sym}")
            return normalize_ohlc_data(get_oanda_candles(oanda_sym, OANDA_GRANULARITY, count))
        else:
            print(f"📥 YFINANCE: {pair}")
            df = yf.download(pair, period="5d", interval=TIMEFRAME, progress=False)
            df.columns = [c[0] for c in df.columns]
            return df[["Open","High","Low","Close","Volume"]]

    strength_scores = build_strength_matrix()
    sorted_str = sorted(strength_scores.values(), reverse=True)
    score_gap = abs(sorted_str[0] - sorted_str[-1])
    print(f"📊 Strength gap: {score_gap:.2f} | Threshold: {STRENGTH_GAP_THRESHOLD}")

    # ==========================================
    # 1. CHECK EXISTING POSITIONS — ONLY CLOSE ON ≥55% REVERSAL
    # ==========================================
    for pair in DEFAULT_PAIRS:
        oanda = YAHOO_TO_OANDA[pair]
        pos = get_open_position(oanda)
        if not pos:
            continue

        df = build_features(get_data(pair, oanda, 200)).dropna()
        if len(df) < 5:
            continue
        latest = df.iloc[-1]
        p_up = model.predict_proba(pd.DataFrame([latest[features]]))[0,1]
        p_down = 1 - p_up

        # ✅ ONLY close on REAL reversal ≥ CLOSE_THRESHOLD
        if pos["units"] > 0 and p_down >= CLOSE_THRESHOLD:
            print(f"🔄 CLOSE LONG {pair} — DOWN {p_down:.1%}")
            close_position(oanda)
            last_closed[pair] = (Direction.LONG, REOPEN_DELAY_RUNS)

        if pos["units"] < 0 and p_up >= CLOSE_THRESHOLD:
            print(f"🔄 CLOSE SHORT {pair} — UP {p_up:.1%}")
            close_position(oanda)
            last_closed[pair] = (Direction.SHORT, REOPEN_DELAY_RUNS)

    # ==========================================
    # 2. LOOK FOR NEW ENTRIES — RESPECT COOLDOWN
    # ==========================================
    candidates = []
    for pair in DEFAULT_PAIRS:

        # ✅ Skip pairs in cooldown
        if pair in last_closed:
            dir_closed, runs_left = last_closed[pair]
            if runs_left > 0:
                last_closed[pair] = (dir_closed, runs_left - 1)
                print(f"⏳ COOLDOWN: Skipping {pair} — {runs_left-1} runs remaining")
                continue
            else:
                del last_closed[pair]

        oanda = YAHOO_TO_OANDA[pair]
        if get_open_position(oanda):
            print(f"⏭️ {pair}: open — skip")
            continue

        df = build_features(get_data(pair, oanda, 200)).dropna()
        if len(df) < 20:
            continue
        latest = df.iloc[-1]
        p_up = model.predict_proba(pd.DataFrame([latest[features]]))[0,1]
        p_down = 1 - p_up
        adx = latest["ADX_14"]
        best_p = max(p_up, p_down)
        best_dir = "BUY" if p_up > p_down else "SELL"

        mc_data, mc_ok = load_mc(pair)
        mc_pass = True
        MIN_EDGE = RELAXED_MIN_PROB if MODE == "LEVEL10" else NORMAL_MIN_PROB
        if mc_ok:
            print(f"📊 MC: {pair} | P={mc_data['percentile_rank']:.1f}% | UP={mc_data['p_up']:.1f}% | DOWN={mc_data['p_down']:.1f}% | {mc_data['regime']}")
            if not (1 <= mc_data["percentile_rank"] <= 99):
                print(f"⏸️ {pair} extreme percentile — skip")
                mc_pass = False
            if score_gap >= STRENGTH_GAP_THRESHOLD:
                MIN_EDGE = min(MIN_EDGE, RELAXED_MIN_PROB)
                print(f"⚡ Strong gap → threshold {MIN_EDGE}%")
            if mc_data["p_up"] < MIN_EDGE and mc_data["p_down"] < MIN_EDGE:
                print(f"⏸️ {pair} low edge — skip")
                continue
            if MODE != "LEVEL10":
                if "Uptrend" in mc_data["regime"] and best_dir == "SELL":
                    print(f"⏸️ {pair} UPTREND → no SELL — skip")
                    mc_pass = False
                if "Downtrend" in mc_data["regime"] and best_dir == "BUY":
                    print(f"⏸️ {pair} DOWNTREND → no BUY — skip")
                    mc_pass = False
            else:
                if "Uptrend" in mc_data["regime"] and best_dir == "SELL":
                    print(f"⚠️ {pair} UPTREND vs SELL — PROCEEDING (LEVEL10)")
                if "Downtrend" in mc_data["regime"] and best_dir == "BUY":
                    print(f"⚠️ {pair} DOWNTREND vs BUY — PROCEEDING (LEVEL10)")

        if not mc_pass:
            continue

        pivots = entry_ok = pivot_ok = False
        target_sl = target_tp = None
        if ENABLE_PIVOTS:
            daily = resample_ohlc(df, PIVOT_TIMEFRAME).dropna()
            if len(daily) >= 2:
                pivots = calculate_pivots(daily.iloc[-2]["High"], daily.iloc[-2]["Low"], daily.iloc[-2]["Close"], PIVOT_METHOD)
                curr = latest["Close"]

                if MODE == "LEVEL10":
                    pivot_ok = True
                    entry_ok = True
                else:
                    pivot_ok = True
                    if PIVOT_BIAS_CHECK:
                        if best_dir == "SELL" and curr > pivots["P"]: pivot_ok = False
                        if best_dir == "BUY" and curr < pivots["P"]: pivot_ok = False
                    if best_dir == "SELL" and (abs(curr-pivots["R1"])/curr < 0.0015 or abs(curr-pivots["P"])/curr < 0.0015):
                        entry_ok = True
                    if best_dir == "BUY" and (abs(curr-pivots["S1"])/curr < 0.0015 or abs(curr-pivots["P"])/curr < 0.0015):
                        entry_ok = True
                try:
                    from oandapyV20.endpoints.instruments import InstrumentsCandles
                    tick = api.request(InstrumentsCandles(instrument=oanda, params={"count":1,"granularity":"M1","price":"BA"}))["candles"][0]
                    spread_pips = abs(float(tick["ask"]["c"]) - float(tick["bid"]["c"])) / (0.01 if "JPY" in pair else 0.0001)
                except:
                    spread_pips = 1.0

                # buffer = spread_pips + 25 
                buffer = spread_pips + 30  # Spread + 30 pips buffer — always safe
                pip_size = 0.01 if "JPY" in pair else 0.0001
                decimals = 3 if "JPY" in pair else 5

                if best_dir == "SELL":
                    target_sl = round(max(pivots["R1"], pivots["P"]) + buffer * pip_size, decimals)
                    target_tp = round(pivots["S1"], decimals)
                if best_dir == "BUY":
                    target_sl = round(min(pivots["S1"], pivots["P"]) - buffer * pip_size, decimals)
                    target_tp = round(pivots["R1"], decimals)

        adx_ok = adx >= TREND_THRESHOLD if MODE != "LEVEL10" else True
        if best_p >= MIN_PROB and adx_ok and mc_pass and pivot_ok and entry_ok:
            candidates.append({
                "pair": pair, "oanda": oanda, "dir": best_dir,
                "prob": best_p, "sl": target_sl, "tp": target_tp
            })

    # ==========================================
    # 3. SELECT & EXECUTE BEST SIGNALS
    # ==========================================
    winners = []
    usd_count = jpy_count = 0
    candidates.sort(key=lambda x: x["prob"], reverse=True)
    for c in candidates:
        if "USD=X" in c["pair"] and c["pair"] != "USDJPY=X":
            if usd_count >= MAX_PER_USD_GROUP:
                continue
            usd_count += 1
        if "JPY" in c["pair"]:
            if jpy_count >= MAX_PER_JPY_GROUP:
                continue
            jpy_count += 1
        if len(winners) >= MAX_TOTAL_TRADES:
            break
        winners.append(c)

    lines = [f"🤖 MULTI‑PAIR UPDATE — {now}"]
    if not winners:
        lines.append("➡️ No high‑probability setups found")
    else:
        for w in winners:
            res = open_oanda_order(
                {
                    "pair": w["oanda"],
                    "action": w["dir"],
                    "stop_loss": w["sl"],
                    "take_profit": w["tp"]
                }
            )
            print(f"📤 Order: {res}")
            lines.append(f"✅ {w['pair']} | {w['dir']} | {w['prob']:.1%} | SL={w['sl']} | TP={w['tp']}")

    msg = "\n".join(lines)
    print(msg)
    send_telegram_message(msg)
    print("✅ Run complete")

if __name__ == "__main__":
    print("[STRATEGY] Step 1 — Currency Strength...")
    print(format_strength_ranking(build_strength_matrix()))
    try:
        main()
    except Exception as e:
        err = f"❌ Error: {e}"
        print(err)
        send_telegram_message(err)
