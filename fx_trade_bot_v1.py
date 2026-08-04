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
MC_TP_MAX_BAND_PCT = cfg("MC_TP_MAX_BAND_PCT", 0.7)

# Trading pairs & mappings
DEFAULT_PAIRS = cfg(
    "DEFAULT_PAIRS",
    ["EURUSD=X", "GBPUSD=X", "EURJPY=X", "GBPJPY=X", "AUDUSD=X", "USDJPY=X", "GBPAUD=X", "USDCHF=X"],
)
YAHOO_TO_OANDA = cfg(
    "YAHOO_TO_OANDA",
    {
        "EURUSD=X": "EUR_USD", "GBPUSD=X": "GBP_USD", "EURJPY=X": "EUR_JPY",
        "GBPJPY=X": "GBP_JPY", "AUDUSD=X": "AUD_USD", "USDJPY=X": "USD_JPY",
        "GBPAUD=X": "GBP_AUD", "USDCHF=X": "USD_CHF",
    },
)

# Timeframes
TIMEFRAME = cfg("TIMEFRAME", "15m")
OANDA_GRANULARITY_MAP = {"1m": "M1", "5m": "M5", "15m": "M15", "30m": "M30", "1h": "H1", "4h": "H4", "1d": "D"}
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

# Close / Reopen rules
CLOSE_THRESHOLD = 55.0
REOPEN_DELAY_RUNS = 2
CLOSED_STATE_FILE = RESULTS_DIR / "last_closed_state.json"  # ✅ Persist cooldown across cron runs


# --------------------------
# 🧩 PERSISTENT COOLDOWN STATE
# --------------------------
def load_closed_state():
    if CLOSED_STATE_FILE.exists():
        try:
            with open(CLOSED_STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_closed_state(state):
    with open(CLOSED_STATE_FILE, "w") as f:
        json.dump(state, f)


# --------------------------
# 🧩 LOAD BOTH DAILY + H4 MC
# --------------------------
def load_both_mc(pair):
    safe = pair.replace("=X", "").replace("=", "_")
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    daily_path = RESULTS_DIR / f"fx_daily_{safe}_{today}.json"
    daily_data = json.load(open(daily_path)) if daily_path.exists() else None
    h4_files = sorted(RESULTS_DIR.glob(f"h4_mc_{safe}_*.json"), reverse=True)
    h4_data = json.load(open(h4_files[0])) if h4_files else None
    return daily_data, h4_data


# --------------------------
# 🧩 COMBINED EDGE CHECK
# --------------------------
def combined_edge_ok(daily, h4, best_dir, MIN_EDGE, MODE):
    if not daily and not h4:
        return True, "NO_MC"
    scores = []
    if daily: scores.append(daily["p_up" if best_dir == "BUY" else "p_down"])
    if h4: scores.append(h4["p_up_pct" if best_dir == "BUY" else "p_down_pct"])
    avg_score = sum(scores) / len(scores)
    passes = all(s >= MIN_EDGE for s in scores) if MODE != "LEVEL10" else avg_score >= MIN_EDGE
    label = f"DAILY+H4 AVG: {avg_score:.1f}%" if len(scores) == 2 else ("DAILY ONLY" if daily else "H4 ONLY")
    return passes, label


# --------------------------
# 🛡️ MARKET STATUS CHECK
# --------------------------
def forex_market_closed():
    try:
        from oandapyV20.endpoints.instruments import InstrumentsCandles
        resp = api.request(InstrumentsCandles(instrument="EUR_USD", params={"count":1, "granularity":OANDA_GRANULARITY}))
        return not bool(resp.get("candles"))
    except Exception:
        return False

if forex_market_closed():
    print("⏸️ Market closed — skipping run")
    send_telegram_message("⏸️ FX BOT: Market closed")
    raise SystemExit(0)


# --------------------------
# 🧩 HELPER FUNCTIONS
# --------------------------
def resample_ohlc(df: pd.DataFrame, rule: str = "D") -> pd.DataFrame:
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("Need DatetimeIndex for resample")
    return df.resample(rule).agg({"Open":"first", "High":"max", "Low":"min", "Close":"last", "Volume":"sum"}).dropna()

def calculate_pivots(prev_high, prev_low, prev_close, pivot_type="Classic") -> dict:
    h,l,c = float(prev_high), float(prev_low), float(prev_close)
    rng = h - l
    p = (h + l + c) / 3
    if pivot_type == "Classic":
        return {"R3":round(p+2*rng,3),"R2":round(p+rng,3),"R1":round(2*p-l,3),"P":round(p,3),"S1":round(2*p-h,3),"S2":round(p-rng,3),"S3":round(p-2*rng,3)}
    elif pivot_type == "Fibonacci":
        return {"R3":round(p+rng*1.0,3),"R2":round(p+rng*0.618,3),"R1":round(p+rng*0.382,3),"P":round(p,3),"S1":round(p-rng*0.382,3),"S2":round(p-rng*0.618,3),"S3":round(p-rng*1.0,3)}
    elif pivot_type == "Camarilla":
        h3,h2,h1 = c+rng*1.1/6, c+rng*1.1/12, c+rng*1.1/24
        l1,l2,l3 = c-rng*1.1/24, c-rng*1.1/12, c-rng*1.1/6
        return {"R3":round(h3,3),"R2":round(h2,3),"R1":round(h1,3),"P":round(p,3),"S1":round(l1,3),"S2":round(l2,3),"S3":round(l3,3)}
    elif pivot_type == "Woodie":
        p = (2*c + h + l) / 4
        return {"R3":round(p+2*rng,3),"R2":round(p+rng,3),"R1":round(2*p-l,3),"P":round(p,3),"S1":round(2*p-h,3),"S2":round(p-rng,3),"S3":round(p-2*rng,3)}

def get_open_position(instrument: str):
    try:
        from oandapyV20.endpoints.positions import PositionDetails
        pos = api.request(PositionDetails(accountID=OANDA_ACCOUNT_ID, instrument=instrument)).get("position", {})
        if pos.get("long",{}).get("units","0")!="0": return {"units":int(pos["long"]["units"])}
        if pos.get("short",{}).get("units","0")!="0": return {"units":-int(pos["short"]["units"])}
        return None
    except Exception:
        return None

def close_position(instrument: str):
    try:
        from oandapyV20.endpoints.positions import PositionDetails
        from oandapyV20.endpoints.orders import OrderCreate
        pos = api.request(PositionDetails(accountID=OANDA_ACCOUNT_ID, instrument=instrument)).get("position",{})
        if pos.get("long",{}).get("units","0")!="0": units = -int(pos["long"]["units"])
        elif pos.get("short",{}).get("units","0")!="0": units = abs(int(pos["short"]["units"]))
        else: return
        api.request(OrderCreate(accountID=OANDA_ACCOUNT_ID, data={"order":{"type":"MARKET","instrument":instrument,"units":str(units),"positionFill":"REDUCE_ONLY"}}))
        print(f"✅ Closed {instrument}")
        send_telegram_message(f"🔄 AUTO‑CLOSE: {instrument}")
    except Exception as e:
        print(f"❌ Close failed: {e}")

def normalize_ohlc_data(data):
    if isinstance(data, pd.DataFrame): return data.copy()
    rows = []
    for c in data:
        mid = c.get("mid",{})
        if not mid: continue
        rows.append({"time":pd.to_datetime(c["time"]),"Open":float(mid["o"]),"High":float(mid["h"]),"Low":float(mid["l"]),"Close":float(mid["c"]),"Volume":float(c.get("volume",0))})
    df = pd.DataFrame(rows).set_index("time")
    return df.astype({"Open":float,"High":float,"Low":float,"Close":float,"Volume":float})

def build_features(df):
    df = df.copy()
    df["return"] = df["Close"].pct_change()
    for p in [5,10,20,50]:
        df[f"sma_{p}"] = ta.sma(df["Close"],p)
        df[f"ema_{p}"] = ta.ema(df["Close"],p)
        df[f"dist_sma_{p}"] = (df["Close"] - df[f"sma_{p}"]) / df[f"sma_{p}"]
    df["rsi"] = ta.rsi(df["Close"],14)
    df = pd.concat([df, ta.macd(df["Close"]), ta.adx(df["High"],df["Low"],df["Close"],14)], axis=1)
    if "ADXR_14" in df.columns and "ADXR_14_2" not in df.columns: df = df.rename(columns={"ADXR_14":"ADXR_14_2"})
    df["atr14"] = ta.atr(df["High"],df["Low"],df["Close"],14)
    df["vol_20"] = df["return"].rolling(20).std() * np.sqrt(252*24)
    df["body"] = abs(df["Close"] - df["Open"]) / df["Open"]
    return df

def open_oanda_order(signal: dict, units: float | None = None) -> dict:
    pair_raw, action = signal["pair"], signal["action"]
    units = int(units or 10000) if action=="BUY" else -int(units or 10000)
    sl, tp = signal["stop_loss"], signal["take_profit"]
    decimals = 3 if "JPY" in pair_raw else 5
    if sl is None or tp is None: return {"status":"ERROR","message":"SL/TP missing"}
    order = {"order":{"type":"MARKET","instrument":pair_raw,"units":str(units),"timeInForce":"FOK","positionFill":"DEFAULT",
            "stopLossOnFill":{"price":str(round(float(sl),decimals)),"timeInForce":"GTC"},
            "takeProfitOnFill":{"price":str(round(float(tp),decimals)),"timeInForce":"GTC"}}}
    try:
        from oandapyV20.endpoints.orders import OrderCreate
        api.request(OrderCreate(accountID=OANDA_ACCOUNT_ID, data=order))
        return {"status":"OK"}
    except Exception as e:
        return {"status":"ERROR","message":str(e)}


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
    now = datetime.now(timezone.utc).strftime("%Y‑%m‑%d %H:%M UTC")
    print(f"\n🤖 RUN — {now} | MODE={MODE} | DATA={'OANDA' if USE_OANDA_DATA else 'YFINANCE'}")

    def get_data(pair, oanda_sym, count=200):
        if USE_OANDA_DATA:
            return normalize_ohlc_data(get_oanda_candles(oanda_sym, OANDA_GRANULARITY, count))
        df = yf.download(pair, period="5d", interval=TIMEFRAME, progress=False)
        df.columns = [c[0] for c in df.columns]
        return df[["Open","High","Low","Close","Volume"]]

    strength_scores = build_strength_matrix()
    sorted_str = sorted(strength_scores.values(), reverse=True)
    score_gap = abs(sorted_str[0] - sorted_str[-1])
    print(f"📊 Strength gap: {score_gap:.2f} | Threshold: {STRENGTH_GAP_THRESHOLD}")

    last_closed = load_closed_state()

    # 1. CLOSE CHECK
    for pair in DEFAULT_PAIRS:
        oanda = YAHOO_TO_OANDA[pair]
        if not get_open_position(oanda): continue
        df = build_features(get_data(pair, oanda, 200)).dropna()
        if len(df) < 50: continue
        latest = df.iloc[-1]
        p_up = model.predict_proba(pd.DataFrame([latest[features]]))[0,1]
        p_down = 1 - p_up
        pos = get_open_position(oanda)
        if pos["units"] > 0 and p_down >= CLOSE_THRESHOLD:
            close_position(oanda)
            last_closed[pair] = [Direction.LONG.name, REOPEN_DELAY_RUNS]
            save_closed_state(last_closed)
        if pos["units"] < 0 and p_up >= CLOSE_THRESHOLD:
            close_position(oanda)
            last_closed[pair] = [Direction.SHORT.name, REOPEN_DELAY_RUNS]
            save_closed_state(last_closed)

    # 2. NEW ENTRIES
    # ==========================================
    # 2. NEW ENTRIES — NOW FULLY SCOPE‑SAFE
    # ==========================================
    candidates = []
    for pair in DEFAULT_PAIRS:
        mc_pass = True
        pivot_ok = True       # ✅ PRE‑INIT: no crash if ENABLE_PIVOTS=False
        entry_ok = True       # ✅ PRE‑INIT: always defined
        lo = hi = band_width = None

        # Cooldown logic — unchanged
        if pair in last_closed:
            dir_closed, runs_left = last_closed[pair]
            if runs_left > 0:
                last_closed[pair] = [dir_closed, runs_left - 1]
                save_closed_state(last_closed)
                print(f"⏳ COOLDOWN: {pair} — {runs_left-1} runs left")
                continue
            del last_closed[pair]; save_closed_state(last_closed)

        oanda = YAHOO_TO_OANDA[pair]
        if get_open_position(oanda):
            print(f"⏭️ {pair}: open — skip"); continue

        df = build_features(get_data(pair, oanda, 200)).dropna()
        if len(df) < 50:
            print(f"⚠️ {pair}: insufficient data — skip"); continue

        latest = df.iloc[-1]
        p_up = model.predict_proba(pd.DataFrame([latest[features]]))[0,1]
        p_down = 1 - p_up
        adx = latest["ADX_14"]
        best_p = max(p_up, p_down)
        best_dir = "BUY" if p_up > p_down else "SELL"

        daily_mc, h4_mc = load_both_mc(pair)
        MIN_EDGE = RELAXED_MIN_PROB if MODE=="LEVEL10" else NORMAL_MIN_PROB

        if daily_mc or h4_mc:
            lo = max(daily_mc["range_90"][0], h4_mc["range_90"][0]) if (daily_mc and h4_mc) else (daily_mc["range_90"][0] if daily_mc else h4_mc["range_90"][0])
            hi = min(daily_mc["range_90"][1], h4_mc["range_90"][1]) if (daily_mc and h4_mc) else (daily_mc["range_90"][1] if daily_mc else h4_mc["range_90"][1])
            band_width = hi - lo
            if daily_mc: print(f"📊 DAILY MC {pair}: P={daily_mc['percentile_rank']:.1f}% UP={daily_mc['p_up']:.1f}% DOWN={daily_mc['p_down']:.1f}% {daily_mc['regime']}")
            if h4_mc: print(f"📊 H4 MC {pair}: P={h4_mc['percentile_rank']:.1f}% UP={h4_mc['p_up_pct']:.1f}% DOWN={h4_mc['p_down_pct']:.1f}% {h4_mc['regime']}")
            if score_gap >= STRENGTH_GAP_THRESHOLD: MIN_EDGE = min(MIN_EDGE, RELAXED_MIN_PROB)
            mc_pass, label = combined_edge_ok(daily_mc, h4_mc, best_dir, MIN_EDGE, MODE)
            if not mc_pass: print(f"⏸️ {pair} failed {label} — skip"); continue
            if MODE != "LEVEL10":
                for mc in [daily_mc, h4_mc]:
                    if not mc: continue
                    if "Uptrend" in mc["regime"] and best_dir=="SELL": mc_pass=False
                    if "Downtrend" in mc["regime"] and best_dir=="BUY": mc_pass=False
            else:
                for mc in [daily_mc, h4_mc]:
                    if not mc: continue
                    if "Uptrend" in mc["regime"] and best_dir=="SELL": print(f"⚠️ {pair} UPTREND vs SELL — PROCEED")
                    if "Downtrend" in mc["regime"] and best_dir=="BUY": print(f"⚠️ {pair} DOWNTREND vs BUY — PROCEED")
        if not mc_pass: continue

        target_sl = target_tp = None
        if ENABLE_PIVOTS:
            entry_ok = (MODE == "LEVEL10")  # Only override if pivots ON
            daily = resample_ohlc(df, PIVOT_TIMEFRAME).dropna()
            if len(daily)>=2:
                pivots = calculate_pivots(daily.iloc[-2]["High"], daily.iloc[-2]["Low"], daily.iloc[-2]["Close"], PIVOT_METHOD)
                curr = latest["Close"]
                if MODE != "LEVEL10":
                    if PIVOT_BIAS_CHECK:
                        if best_dir=="SELL" and curr>pivots["P"]: pivot_ok=False
                        if best_dir=="BUY" and curr<pivots["P"]: pivot_ok=False
                    if best_dir=="SELL" and (abs(curr-pivots["R1"])/curr<0.0015 or abs(curr-pivots["P"])/curr<0.0015): entry_ok=True
                    if best_dir=="BUY" and (abs(curr-pivots["S1"])/curr<0.0015 or abs(curr-pivots["P"])/curr<0.0015): entry_ok=True
                try:
                    from oandapyV20.endpoints.instruments import InstrumentsCandles
                    tick = api.request(InstrumentsCandles(instrument=oanda, params={"count":1,"granularity":"M1","price":"BA"}))["candles"][0]
                    spread_pips = abs(float(tick["ask"]["c"])-float(tick["bid"]["c"])) / (0.01 if "JPY" in pair else 0.0001)
                except: spread_pips = 1.0
                buffer = spread_pips + 30
                pip_size = 0.01 if "JPY" in pair else 0.0001  # ✅ Extend if adding XAU/HKD etc.
                decimals = 3 if "JPY" in pair else 5
                if best_dir=="SELL":
                    target_sl = round(max(pivots["R1"],pivots["P"]) + buffer*pip_size, decimals)
                    target_tp = round(min(pivots["S1"],pivots["P"]) - buffer*pip_size, decimals)
                if best_dir=="BUY":
                    target_sl = round(min(pivots["S1"],pivots["P"]) - buffer*pip_size, decimals)
                    target_tp = round(max(pivots["R1"],pivots["P"]) + buffer*pip_size, decimals)
                if daily_mc and h4_mc and lo and hi and band_width:
                    if best_dir=="SELL": target_tp = max(target_tp, lo + (band_width*(1-MC_TP_MAX_BAND_PCT)))
                    if best_dir=="BUY": target_tp = min(target_tp, hi - (band_width*(1-MC_TP_MAX_BAND_PCT)))
                    target_tp = round(target_tp, decimals)

        # ATR fallback — always active
        if target_sl is None or target_tp is None:
            decimals = 3 if "JPY" in pair else 5
            atr = latest["atr14"]
            mul = 1.8
            if best_dir=="BUY":
                target_sl = round(latest["Close"] - mul*atr, decimals)
                target_tp = round(latest["Close"] + mul*atr, decimals)
            else:
                target_sl = round(latest["Close"] + mul*atr, decimals)
                target_tp = round(latest["Close"] - mul*atr, decimals)
            print(f"⚠️ {pair}: ATR SL/TP fallback used")

        adx_ok = adx >= TREND_THRESHOLD if MODE!="LEVEL10" else True
        if best_p >= MIN_PROB and adx_ok and mc_pass and pivot_ok and entry_ok:
            candidates.append({"pair":pair,"oanda":oanda,"dir":best_dir,"prob":best_p,"sl":target_sl,"tp":target_tp})

    # 3. EXECUTE
    winners = []; usd=jpy=0
    candidates.sort(key=lambda x:x["prob"], reverse=True)
    for c in candidates:
        if "USD=X" in c["pair"] and c["pair"]!="USDJPY=X" and usd>=MAX_PER_USD_GROUP: continue
        if "JPY" in c["pair"] and jpy>=MAX_PER_JPY_GROUP: continue
        if len(winners)>=MAX_TOTAL_TRADES: break
        if "USD=X" in c["pair"] and c["pair"]!="USDJPY=X": usd+=1
        if "JPY" in c["pair"]: jpy+=1
        winners.append(c)

    lines = [f"🤖 UPDATE — {now}"]
    if not winners: lines.append("➡️ No high‑prob setups")
    else:
        for w in winners:
            res = open_oanda_order({"pair":w["oanda"],"action":w["dir"],"stop_loss":w["sl"],"take_profit":w["tp"]})
            lines.append(f"✅ {w['pair']} {w['dir']} {w['prob']:.1%} SL={w['sl']} TP={w['tp']} | {res['status']}")

    msg = "\n".join(lines); print(msg); send_telegram_message(msg); print("✅ Done")


if __name__ == "__main__":
    print("[STRATEGY] Currency Strength...")
    print(format_strength_ranking(build_strength_matrix()))
    try: main()
    except Exception as e:
        err = f"❌ Error: {e}"; print(err); send_telegram_message(err)