"""
Advanced FX Monte Carlo Simulator
✅ Drift, Volatility, 90% Range
✅ Current Price Percentile Rank
✅ P(Up) / P(Down) Win Rate
✅ Boundary Touch Probabilities
✅ Auto Market Regime / Bias
✅ Clean Telegram Output
✅ JSON Export for Trading Bot
"""
import argparse
import json
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timezone
from pathlib import Path
from telegram_message import send_telegram_message

# ==========================================
# CONFIG
# ==========================================
DEFAULT_PERIOD = "60d"
DEFAULT_SIMS = 5000
DEFAULT_RISK = 0.01
FORECAST_DAYS = 20  # Standard MC horizon
SEED = 42

# ==========================================
# SIMULATION ENGINE
# ==========================================
def run_monte_carlo(symbol: str, period: str = DEFAULT_PERIOD, sims: int = DEFAULT_SIMS):
    """Run full MC simulation and return all statistics"""
    print(f"📊 Fetching data: {symbol} | Period: {period}")
    df = yf.download(symbol, period=period, interval="1d", progress=False)
    df.columns = [c[0] for c in df.columns]
    close = df["Close"].dropna()

    if len(close) < 30:
        raise ValueError("Insufficient historical data")

    # Core stats
    last_price = float(close.iloc[-1])
    returns = close.pct_change().dropna()
    ann_drift = returns.mean() * 252 * 100
    ann_vol = returns.std() * np.sqrt(252) * 100

    # Simulate paths
    np.random.seed(SEED)
    paths = np.zeros((sims, FORECAST_DAYS + 1))
    paths[:, 0] = last_price
    daily_drift = returns.mean()
    daily_vol = returns.std()

    for t in range(1, FORECAST_DAYS + 1):
        shocks = np.random.normal(daily_drift, daily_vol, sims)
        paths[:, t] = paths[:, t-1] * (1 + shocks)

    final_prices = paths[:, -1]
    all_prices = paths.flatten()

    # 90% Confidence Range
    lower_90 = np.percentile(final_prices, 5)
    upper_90 = np.percentile(final_prices, 95)

    # 1. Probability Engine Metrics
    percentile_rank = float(np.percentile(all_prices, (last_price - np.min(all_prices)) / (np.max(all_prices) - np.min(all_prices)) * 100))
    p_up = float(np.mean(final_prices > last_price) * 100)
    p_down = float(np.mean(final_prices < last_price) * 100)

    # Boundary touch probabilities
    touch_lower = float(np.mean(np.any(paths <= lower_90, axis=1)) * 100)
    touch_upper = float(np.mean(np.any(paths >= upper_90, axis=1)) * 100)

    # 2. Regime & Bias Detection
    if percentile_rank >= 80:
        if ann_drift > 0:
            regime = "⚠️ OVERBOUGHT | Strong Uptrend — Mean‑Reversion Risk High"
        else:
            regime = "⚠️ OVERBOUGHT | Weak Trend — Reversal Likely"
    elif percentile_rank <= 20:
        if ann_drift < 0:
            regime = "🔻 OVERSOLD | Strong Downtrend — Mean‑Reversion Risk High"
        else:
            regime = "🔻 OVERSOLD | Weak Trend — Bounce Likely"
    elif abs(ann_drift) > 10 and ann_vol < 8:
        regime = "📈 STRONG UPTREND | Low Volatility — Trend Continuation" if ann_drift > 0 else "📉 STRONG DOWNTREND | Low Volatility — Trend Continuation"
    elif abs(ann_drift) < 5 and ann_vol > 12:
        regime = "↔️ RANGE‑BOUND | High Volatility — Mean‑Revert Trade"
    else:
        regime = "⚖️ NEUTRAL | Balanced Risk — Await Breakout"

    return {
        "symbol": symbol,
        "last_price": round(last_price, 5),
        "ann_drift": round(ann_drift, 2),
        "ann_vol": round(ann_vol, 2),
        "range_90": [round(lower_90, 5), round(upper_90, 5)],
        "percentile_rank": round(percentile_rank, 1),
        "p_up": round(p_up, 1),
        "p_down": round(p_down, 1),
        "touch_lower": round(touch_lower, 1),
        "touch_upper": round(touch_upper, 1),
        "regime": regime,
        "period": period,
        "simulations": sims,
        "risk": DEFAULT_RISK
    }

# ==========================================
# REPORT FORMATTING
# ==========================================
def build_telegram_report(results: list) -> str:
    """Format all pair results into clean, actionable Telegram message"""
    header = f"""📊 **FX ADVANCED MONTE CARLO REPORT**
📅 Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
🔹 Period: {DEFAULT_PERIOD} | Simulations: {DEFAULT_SIMS} | Risk: {DEFAULT_RISK:.1%}
"""
    body = ""
    for r in results:
        body += f"""
🔹 **{r['symbol']}**
   💵 Spot: {r['last_price']}
   📈 Drift: {r['ann_drift']:+.2f}% | Vol: {r['ann_vol']:.2f}%
   📏 90% Range: {r['range_90'][0]} – {r['range_90'][1]}
   📊 Percentile: {r['percentile_rank']}%
   🎯 Win Rate: UP {r['p_up']}% | DOWN {r['p_down']}%
   🔍 Touch Prob: Lower {r['touch_lower']}% | Upper {r['touch_upper']}%
   🧭 Bias: {r['regime']}
"""
    return header + body

# ==========================================
# MAIN EXECUTION
# ==========================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pairs", nargs="*", default=["EURUSD=X", "GBPUSD=X", "EURJPY=X", "GBPJPY=X", "AUDUSD=X", "USDJPY=X", "GBPAUD=X", "USDCHF=X"])
    parser.add_argument("--json-out", action="store_true")
    args = parser.parse_args()

    all_results = []
    for pair in args.pairs:
        try:
            res = run_monte_carlo(pair)
            all_results.append(res)
            # Save per‑pair JSON for trading bot
            out_path = Path(__file__).parent / "daily_results" / f"fx_mc_{pair.replace('=X','')}_{datetime.now().strftime('%Y%m%d')}.json"
            out_path.parent.mkdir(exist_ok=True)
            with open(out_path, "w") as f:
                json.dump(res, f, indent=2)
        except Exception as e:
            print(f"❌ Failed {pair}: {e}")

    if args.json_out:
        print(json.dumps(all_results, indent=2))
    else:
        msg = build_telegram_report(all_results)
        print(msg)
        send_telegram_message(msg)