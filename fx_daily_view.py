"""
FX Daily Monte Carlo Calculator
Runs simulation for a single forex pair, outputs summary or clean JSON.
"""
import argparse
import json
import numpy as np
import pandas as pd
import yfinance as yf
from telegram_message import send_telegram_message
from config import USE_OANDA_DATA
from utils.oanda_execution import get_oanda_candles
from utils.oanda_execution import is_forex_market_open

# Exit immediately if market is closed
if not is_forex_market_open():
    print("⏸️ Market is closed — skipping run")
    raise SystemExit(0)

parser = argparse.ArgumentParser()
parser.add_argument("pair", help="e.g. EURUSD=X")
parser.add_argument("--period", default="60d", help="Lookback period")
parser.add_argument("--account-risk", type=float, default=0.01, help="Max risk per trade")
parser.add_argument("--sim", type=int, default=5000, help="Number of simulations")
parser.add_argument("--json-out", action="store_true", help="Output only JSON data")
args = parser.parse_args()

YAHOO_TO_OANDA = {
    "EURUSD=X": "EUR_USD", "GBPUSD=X": "GBP_USD", "EURJPY=X": "EUR_JPY",
    "GBPJPY=X": "GBP_JPY", "AUDUSD=X": "AUD_USD", "USDJPY=X": "USD_JPY",
    "GBPAUD=X": "GBP_AUD", "USDCHF=X": "USD_CHF"
}
oanda_sym = YAHOO_TO_OANDA.get(args.pair, args.pair.replace("=X", ""))

print(f"📊 Fetching {args.pair} data — {args.period}...") if not args.json_out else None

df = None
if USE_OANDA_DATA:
    try:
        df = get_oanda_candles(oanda_sym, "D", count=200)
    except Exception as e:
        if not args.json_out:
            print(f"⚠️ OANDA failed: {e} → using yfinance")

if df is None or len(df) < 30:
    df = yf.download(args.pair, period=args.period, interval="1d", progress=False)
    df.columns = [c[0] for c in df.columns]

if "Close" not in df.columns or len(df.dropna()) < 30:
    if not args.json_out:
        print("❌ Not enough data")
    raise SystemExit(1)

close = df["Close"].dropna()
returns = close.pct_change().dropna()
ann_drift = returns.mean() * 252 * 100
ann_vol = returns.std() * np.sqrt(252) * 100

last_price = close.iloc[-1]
n_days = 20
simulations = []
np.random.seed(42)
for _ in range(args.sim):
    path = [last_price]
    for _ in range(n_days):
        shock = np.random.normal(returns.mean(), returns.std())
        path.append(path[-1] * (1 + shock))
    simulations.append(path[-1])

range_low = np.percentile(simulations, 5)
range_high = np.percentile(simulations, 95)

if args.json_out:
    print(json.dumps({
        "ann_drift": round(ann_drift, 2),
        "ann_vol": round(ann_vol, 2),
        "range_90": [round(range_low, 5), round(range_high, 5)]
    }))
    raise SystemExit(0)

msg = f"""📊 FX DAILY — {args.pair}
📅 Period: {args.period} | Simulations: {args.sim}
📈 Annual Drift: {ann_drift:+.2f}%
📊 Annual Volatility: {ann_vol:.2f}%
🔵 90% Expected Range: {range_low:.5f} – {range_high:.5f}
💵 Current Price: {last_price:.5f}
⚠️ Risk Per Trade: {args.account_risk:.1%}
"""
print(msg)
send_telegram_message(msg)