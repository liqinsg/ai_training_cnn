#!/usr/bin/env python3
"""
FX H4 INTRADAY MONTE CARLO ENGINE
✅ Runs every 4 hours
✅ Lookback: 90 H4 | Forecast: 8 H4 | Sims: 5000
✅ Market‑closed skip
✅ Outputs JSON + clean Telegram report
"""
import sys
import json
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import config
from config_oanda import OANDA_API_TOKEN, OANDA_ACCOUNT_ID, OANDA_ENV
from telegram_message import send_telegram_message
import oandapyV20

api = oandapyV20.API(access_token=OANDA_API_TOKEN, environment=OANDA_ENV)

# ==========================================
# ⚙️ CONFIG
# ==========================================
def cfg(name, default):
    return getattr(config, name, default)

PAIRS = cfg("DEFAULT_PAIRS", [
    "EURUSD=X", "GBPUSD=X", "EURJPY=X", "GBPJPY=X",
    "AUDUSD=X", "USDJPY=X", "GBPAUD=X", "USDCHF=X"
])
LOOKBACK_H4 = cfg("H4_LOOKBACK", 90)
FORECAST_H4 = cfg("H4_FORECAST", 8)
SIMULATIONS = cfg("MC_SIMULATIONS", 5000)
CONFIDENCE = cfg("MC_CONFIDENCE", 0.90)
OANDA_GRANULARITY = "H4"
RESULTS_DIR = BASE_DIR / "daily_results"
RESULTS_DIR.mkdir(exist_ok=True)

# ==========================================
# 🛡️ MARKET STATUS CHECK
# ==========================================
def forex_market_closed():
    try:
        from oandapyV20.endpoints.instruments import InstrumentsCandles
        resp = api.request(InstrumentsCandles(
            instrument="EUR_USD", params={"count": 1, "granularity": OANDA_GRANULARITY}
        ))
        return not bool(resp.get("candles"))
    except Exception:
        return False

if forex_market_closed():
    print("⏸️ Market closed — skipping H4 MC run")
    send_telegram_message("⏸️ FX H4 MC: Market closed — skipped")
    raise SystemExit(0)

# ==========================================
# 📥 DATA FETCH — H4 / AUTO‑RESAMPLE
# ==========================================
def fetch_h4_data(pair: str) -> pd.DataFrame:
    try:
        df = yf.download(pair, period="30d", interval="4h", progress=False)
        if len(df) >= LOOKBACK_H4:
            return df[["Open","High","Low","Close"]].dropna()
    except Exception:
        pass
    try:
        df = yf.download(pair, period="60d", interval="1h", progress=False)
        if df.empty:
            return pd.DataFrame()
        return df[["Open","High","Low","Close"]].resample("4h").agg({
            "Open":"first", "High":"max", "Low":"min", "Close":"last"
        }).dropna()
    except Exception as e:
        print(f"❌ Data failed {pair}: {e}")
        return pd.DataFrame()

# ==========================================
# 🧠 H4 PROBABILITY ENGINE
# ==========================================
def run_h4_mc(pair: str):
    df = fetch_h4_data(pair)
    if len(df) < LOOKBACK_H4:
        return None, False

    closes = df["Close"].values[-LOOKBACK_H4:]
    current = float(closes[-1])
    log_returns = np.log(closes[1:] / closes[:-1])

    periods_year = 252 * 6
    drift = float(np.mean(log_returns) * periods_year)
    vol = float(np.std(log_returns) * np.sqrt(periods_year))
    dt = 1 / periods_year * 6

    np.random.seed(42)
    paths = np.zeros((SIMULATIONS, FORECAST_H4 + 1))
    paths[:, 0] = current
    for t in range(1, FORECAST_H4 + 1):
        z = np.random.normal(0, 1, SIMULATIONS)
        paths[:, t] = paths[:, t-1] * np.exp(
            (drift/periods_year - 0.5 * (vol**2)/periods_year) + (vol * np.sqrt(dt)) * z
        )

    final = paths[:, -1]
    lower = float(np.percentile(final, (1 - CONFIDENCE)/2 * 100))
    upper = float(np.percentile(final, (1 + CONFIDENCE)/2 * 100))

    percentile = round((np.sum(final <= current) / SIMULATIONS) * 100, 1)
    p_up = round((np.sum(final > current) / SIMULATIONS) * 100, 1)
    p_down = round(100 - p_up, 1)
    touch_upper = round((np.any(paths >= upper, axis=1).sum() / SIMULATIONS) * 100, 1)
    touch_lower = round((np.any(paths <= lower, axis=1).sum() / SIMULATIONS) * 100, 1)

    if percentile >= 85 and p_down > 55:
        regime = "🔴 H4 OVERBOUGHT | Mean‑Reversion Risk"
    elif percentile <= 15 and p_up > 55:
        regime = "🟢 H4 OVERSOLD | Bullish Reversal Chance"
    elif abs(drift) > vol * 0.7 and max(p_up, p_down) > 60:
        regime = "⚡ H4 STRONG MOMENTUM"
    elif abs(p_up - p_down) < 4 and abs(drift) < vol * 0.3:
        regime = "⏳ H4 CONSOLIDATION RANGE"
    else:
        regime = "🔹 H4 NEUTRAL"

    dec = 3 if "JPY" in pair else 5
    return {
        "pair": pair,
        "current_price": round(current, dec),
        "ann_drift_pct": round(drift * 100, 2),
        "ann_vol_pct": round(vol * 100, 2),
        "range_90": [round(lower, dec), round(upper, dec)],
        "percentile_rank": percentile,
        "p_up_pct": p_up,
        "p_down_pct": p_down,
        "touch_upper_pct": touch_upper,
        "touch_lower_pct": touch_lower,
        "regime": regime,
        "lookback_h4": LOOKBACK_H4,
        "forecast_h4": FORECAST_H4,
        "simulations": SIMULATIONS,
        "generated_utc": datetime.now(timezone.utc).isoformat()
    }, True

# ==========================================
# 📤 TELEGRAM REPORT
# ==========================================
def build_h4_telegram(results: list) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"📊 **FX H4 MONTE CARLO UPDATE**",
        f"📅 Generated: {now}",
        f"🔹 Lookback: {LOOKBACK_H4} H4 | Forecast: {FORECAST_H4} H4 | Sims: {SIMULATIONS}", ""
    ]
    for r in results:
        dec = 3 if "JPY" in r["pair"] else 5
        lo, hi = r["range_90"]
        lines.extend([
            f"🔹 **{r['pair']}**",
            f"   💵 Last H4 Close: `{r['current_price']}`",
            f"   📊 Percentile: `{r['percentile_rank']}%`",
            f"   🎯 UP: `{r['p_up_pct']}%` | DOWN: `{r['p_down_pct']}%`",
            f"   📏 90% Band: `{lo}` – `{hi}`",
            f"   🔍 Touch: Low `{r['touch_lower_pct']}%` | High `{r['touch_upper_pct']}%`",
            f"   {r['regime']}", ""
        ])
    return "\n".join(lines)

# ==========================================
# 🚀 MAIN RUN
# ==========================================
def main():
    now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    all_results = []
    print(f"🔬 H4 MC RUN — {now_str} UTC | Pairs: {len(PAIRS)}")
    for pair in PAIRS:
        print(f"🔄 Processing: {pair}")
        data, ok = run_h4_mc(pair)
        if not ok:
            print(f"⚠️ Skipped {pair}")
            continue
        all_results.append(data)
        safe = pair.replace("=X","").replace("=","_")
        with open(RESULTS_DIR / f"h4_mc_{safe}_{now_str}.json", "w") as f:
            json.dump(data, f, indent=2)
        print(f"✅ Saved → h4_mc_{safe}_{now_str}.json")
    if all_results:
        send_telegram_message(build_h4_telegram(all_results))
        print("✅ Telegram report sent")
    print("✅ Run complete")

if __name__ == "__main__":
    try: main()
    except Exception as e:
        err = f"❌ H4 MC Error: {e}"
        print(err)
        send_telegram_message(err)