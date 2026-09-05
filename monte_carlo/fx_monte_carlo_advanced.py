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


def fetch_price_data(symbol: str, period: str):
    """Download & clean adjusted close prices"""
    df = yf.download(symbol, period=period, interval="1d", progress=False)
    df.columns = [c[0] for c in df.columns]
    close = df["Close"].dropna()
    if len(close) < 30:
        raise ValueError("Insufficient historical data")
    return close


def compute_stats(close: pd.Series):
    """Calculate drift, volatility, last price"""
    last_price = float(close.iloc[-1])
    returns = close.pct_change().dropna()
    ann_drift = returns.mean() * 252 * 100
    ann_vol = returns.std() * np.sqrt(252) * 100
    return last_price, returns, ann_drift, ann_vol


def simulate_paths(last_price: float, returns: pd.Series, sims: int, horizon: int = 20):
    """Run Monte Carlo price paths"""
    np.random.seed(42)
    paths = np.zeros((sims, horizon + 1))
    paths[:, 0] = last_price
    daily_drift = returns.mean()
    daily_vol = returns.std()
    for t in range(1, horizon + 1):
        shocks = np.random.normal(daily_drift, daily_vol, sims)
        paths[:, t] = paths[:, t - 1] * (1 + shocks)
    return paths


def detect_regime(percentile: float, drift: float, vol: float):
    """Auto market condition label"""
    if percentile >= 80:
        return "⚠️ OVERBOUGHT | Strong Uptrend — Mean‑Reversion Risk High" if drift > 0 else "⚠️ OVERBOUGHT | Weak Trend — Reversal Likely"
    elif percentile <= 20:
        return "🔻 OVERSOLD | Strong Downtrend — Mean‑Reversion Risk High" if drift < 0 else "🔻 OVERSOLD | Weak Trend — Bounce Likely"
    elif abs(drift) > 10 and vol < 8:
        return "📈 STRONG UPTREND | Low Vol — Trend Continuation" if drift > 0 else "📉 STRONG DOWNTREND | Low Vol — Trend Continuation"
    elif abs(drift) < 5 and vol > 12:
        return "↔️ RANGE‑BOUND | High Vol — Mean‑Revert Trade"
    else:
        return "⚖️ NEUTRAL | Balanced Risk — Await Breakout"


def run_monte_carlo(symbol: str, period: str = DEFAULT_PERIOD, sims: int = DEFAULT_SIMS):
    """Full MC simulation — returns all statistics"""
    print(f"📊 Fetching data: {symbol} | Period: {period}")
    close = fetch_price_data(symbol, period)
    last_price, returns, ann_drift, ann_vol = compute_stats(close)
    paths = simulate_paths(last_price, returns, sims)
    final_prices = paths[:, -1]
    all_prices = paths.flatten()

    # Core bounds
    lower_90 = np.percentile(final_prices, 5)
    upper_90 = np.percentile(final_prices, 95)

    # Probability metrics (fixed 0–100% percentile)
    sorted_prices = np.sort(all_prices)
    pos = np.searchsorted(sorted_prices, last_price)

    # percentile_rank = float((pos / len(sorted_prices)) * 100)


    current_price = float(latest_close)
    range_90_low = float(range_90[0])
    range_90_high = float(range_90[1])

    percentile_rank = round(
        ((current_price - range_90_low) / (range_90_high - range_90_low)) * 100,
        1
    )
    # Hard guarantee — never goes outside 0–100%
    percentile_rank = max(0.0, min(100.0, percentile_rank))

    # ✅ CORRECT — always outputs 0.0–100.0%
    percentile_rank = round(
        ((current_price - range_90_low) / (range_90_high - range_90_low)) * 100,
        1
    )
    # Safety clamp — guarantees no out‑of‑range values ever
    percentile_rank = max(0.0, min(100.0, percentile_rank))


    p_up = float(np.mean(final_prices > last_price) * 100)
    p_down = float(np.mean(final_prices < last_price) * 100)
    touch_lower = float(np.mean(np.any(paths <= lower_90, axis=1)) * 100)
    touch_upper = float(np.mean(np.any(paths >= upper_90, axis=1)) * 100)

    # Regime
    regime = detect_regime(percentile_rank, ann_drift, ann_vol)

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
            out_path = Path(__file__).parent / "daily_results" / f"fx_mc_{pair.replace('=X', '')}_{datetime.now().strftime('%Y%m%d')}.json"
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
