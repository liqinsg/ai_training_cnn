import argparse
import json
import math
import sys
import numpy as np
import yfinance as yf

np.random.seed(42)  # Reproducible results

# --------------------------
# Exact sanitize logic from your yhfin.py
# --------------------------
def _sanitize(obj):
    """Recursively replace NaN/Infinity with None and coerce numpy scalars to native types."""
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return obj

# --------------------------
# Command line arguments
# --------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="FX Monte Carlo simulation using real yfinance market data"
    )
    parser.add_argument(
        "symbols", nargs="+", default=["EURUSD=X"],
        help="One or more FX tickers (e.g. EURUSD=X USDJPY=X GBPUSD=X)"
    )
    parser.add_argument("--period", default="60d", help="History lookback period")
    parser.add_argument("--interval", default="1d", help="Data interval")
    parser.add_argument("--sim", type=int, default=10000, help="Number of simulations")
    parser.add_argument("--horizon", type=int, default=22, help="Forecast horizon (trading days)")
    return parser.parse_args()

# --------------------------
# Core logic
# --------------------------
def run_montecarlo(ticker: str, period: str, interval: str, n_sim: int, t_days: int):
    # Fetch real price data
    df = yf.download(ticker, period=period, interval=interval, progress=False)
    if df.empty or "Close" not in df.columns:
        return {"error": "No valid data returned", "symbol": ticker}

    closes = df["Close"].dropna()
    S0 = float(closes.iloc[-1])

    # Calibrate volatility & drift from real history
    log_ret = np.log(closes / closes.shift(1)).dropna()
    ann_vol = float(log_ret.std() * np.sqrt(252))
    ann_drift = float(log_ret.mean() * 252)
    dt = 1 / 252

    # Define scenarios
    scenarios = {
        "Base Case":     {"vol_mult": 1.0, "drift_add": 0.00},
        "High Volatility": {"vol_mult": 1.5, "drift_add": 0.00},
        "Strong USD":    {"vol_mult": 1.0, "drift_add": -0.02},
    }

    scenario_results = []
    for name, s in scenarios.items():
        sigma = ann_vol * s["vol_mult"]
        mu = ann_drift + s["drift_add"]

        # Daily path simulation
        Z = np.random.normal(0, 1, (n_sim, t_days))
        log_returns = (mu - 0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * Z
        price_paths = S0 * np.exp(np.cumsum(log_returns, axis=1))
        S_T = price_paths[:, -1]

        # Calculate risk metrics
        prob_down = float(np.mean(S_T < S0 * 0.98))
        prob_up = float(np.mean(S_T > S0 * 1.02))

        scenario_results.append({
            "scenario": name,
            "mean": round(float(np.mean(S_T)), 5),
            "median": round(float(np.median(S_T)), 5),
            "p5_percentile": round(float(np.percentile(S_T, 5)), 5),
            "p95_percentile": round(float(np.percentile(S_T, 95)), 5),
            "prob_below_-2pct": f"{prob_down:.1%}",
            "prob_above_+2pct": f"{prob_up:.1%}",
        })

    return {
        "symbol": ticker,
        "lookback_period": period,
        "calibration": {
            "current_spot": round(S0, 5),
            "annualized_volatility": round(ann_vol, 4),
            "annualized_drift": round(ann_drift, 4),
        },
        "forecast_horizon_days": t_days,
        "simulations": n_sim,
        "scenario_results": scenario_results
    }

# --------------------------
# Entry point
# --------------------------
if __name__ == "__main__":
    args = parse_args()
    all_output = []

    for sym in args.symbols:
        try:
            res = run_montecarlo(
                sym, args.period, args.interval,
                args.sim, args.horizon
            )
            all_output.append(res)
        except Exception as e:
            all_output.append({
                "symbol": sym,
                "error": str(e)
            })

    # Clean and print final JSON
    clean_output = _sanitize(all_output if len(all_output) > 1 else all_output[0])
    print(json.dumps(clean_output, indent=2, ensure_ascii=False))
