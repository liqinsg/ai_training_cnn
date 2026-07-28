import argparse
import json
import math
import sys
import numpy as np
import yfinance as yf

np.random.seed(42)

def _sanitize(obj):
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

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FX Monte Carlo — Normal / Fat‑Tails / Jump Risk")
    parser.add_argument("symbols", nargs="+", help="FX tickers: EURUSD=X USDJPY=X GBPUSD=X")
    parser.add_argument("--period", default="60d")
    parser.add_argument("--interval", default="1d")
    parser.add_argument("--sim", type=int, default=10000)
    parser.add_argument("--horizon", type=int, default=22)
    parser.add_argument("--fat-tails", action="store_true", dest="fat_tails",
                        help="Use Student's t-distribution instead of Normal")
    parser.add_argument("--df", type=int, default=5,
                        help="t-distribution degrees of freedom (smaller = fatter tails)")
    parser.add_argument("--jumps", action="store_true",
                        help="Add Poisson jump risk for news/events")
    parser.add_argument("--jump-prob", type=float, default=0.05,
                        help="Daily probability of a jump (default 5%)")
    parser.add_argument("--jump-vol", type=float, default=0.003,
                        help="Jump volatility (default 0.3% daily)")
    return parser.parse_args()

def run_montecarlo(ticker, period, interval, n_sim, t_days,
                   fat_tails, df, jumps, jump_prob, jump_vol):
    try:
        df_data = yf.download(ticker, period=period, interval=interval, progress=False)
        if df_data.empty or "Close" not in df_data.columns:
            return {"symbol": ticker, "error": "No data returned"}

        closes = df_data["Close"].dropna()
        S0 = float(closes.iloc[-1].item())

        log_ret = np.log(closes / closes.shift(1)).dropna()
        ann_vol = float((log_ret.std() * np.sqrt(252)).item())
        ann_drift = float((log_ret.mean() * 252).item())
        dt = 1 / 252

        scenarios = {
            "Base Case":        {"vol_mult": 1.0, "drift_add": 0.00},
            "High Volatility":  {"vol_mult": 1.5, "drift_add": 0.00},
            "Strong USD":       {"vol_mult": 1.0, "drift_add": -0.02},
        }

        results = []
        for name, s in scenarios.items():
            sigma = ann_vol * s["vol_mult"]
            mu = ann_drift + s["drift_add"]

            # Base daily innovations
            if fat_tails:
                Z = np.random.standard_t(df, size=(n_sim, t_days))
                Z = Z / np.sqrt(df / (df - 2))  # match variance
            else:
                Z = np.random.normal(0, 1, (n_sim, t_days))

            log_r = (mu - 0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * Z

            # Add jump component if enabled
            if jumps:
                # Poisson: 1 if jump occurs that day
                jump_occur = np.random.binomial(1, jump_prob, size=(n_sim, t_days))
                # Jump size: normal around zero with given daily vol
                jump_size = np.random.normal(0, jump_vol, size=(n_sim, t_days))
                log_r += jump_occur * jump_size

            paths = S0 * np.exp(np.cumsum(log_r, axis=1))
            ST = paths[:, -1]

            results.append({
                "scenario": name,
                "mean": round(float(np.mean(ST)), 5),
                "median": round(float(np.median(ST)), 5),
                "p5": round(float(np.percentile(ST, 5)), 5),
                "p95": round(float(np.percentile(ST, 95)), 5),
                "prob_below_2pct": f"{np.mean(ST < S0*0.98):.1%}",
                "prob_above_2pct": f"{np.mean(ST > S0*1.02):.1%}",
            })

        return {
            "symbol": ticker,
            "calibration": {
                "spot": round(S0, 5),
                "ann_vol": round(ann_vol, 4),
                "ann_drift": round(ann_drift, 4),
                "distribution": "Student's t" if fat_tails else "Normal",
                "jump_risk_enabled": jumps,
            },
            "scenarios": results
        }

    except Exception as e:
        return {"symbol": ticker, "error": str(e)}

if __name__ == "__main__":
    args = parse_args()
    output = [
        run_montecarlo(
            s, args.period, args.interval, args.sim, args.horizon,
            args.fat_tails, args.df, args.jumps, args.jump_prob, args.jump_vol
        )
        for s in args.symbols
    ]
    print(json.dumps(_sanitize(output), indent=2))