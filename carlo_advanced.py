# carlo_advanced.py
"""
Advanced Monte Carlo Simulation for Forex Pairs
- Pulls live price from OANDA
- Calculates drift, volatility, 90% range
- Fixed percentile: strictly 0.0–100.0%
- Outputs clean JSON for fx_trade_bot.py
"""
import numpy as np
import pandas as pd
import json
from datetime import datetime, timezone
from pathlib import Path
from utils.oanda_execution import api
from utils import oanda_client
import oandapyV20.endpoints.instruments as instruments

# --------------------------
# YOUR EXISTING CANDLE FETCH — UNCHANGED
# --------------------------
def get_candles(instrument: str, granularity: str, count: int) -> list:
    params = {"count": count, "granularity": granularity}
    try:
        req = instruments.InstrumentsCandles(instrument=instrument, params=params)
        oanda_client.request(req)
        return [c for c in req.response.get("candles", []) if c["complete"]]
    except Exception as e:
        print(f"  [HELPERS] Candle fetch failed {instrument} {granularity}: {e}")
        return []

# --------------------------
# MAIN MC CALCULATION — FULLY FIXED
# --------------------------

def run_monte_carlo(pair: str, period: str = "60d", sims: int = 5000):
    """
    Run MC for a forex pair — auto‑converts Yahoo → OANDA format
    """
    # ✅ SYMBOL MAPPING — SAME AS IN fx_trade_bot.py
    YAHOO_TO_OANDA = {
        "EURUSD=X": "EUR_USD",
        "GBPUSD=X": "GBP_USD",
        "EURJPY=X": "EUR_JPY",
        "GBPJPY=X": "GBP_JPY",
        "AUDUSD=X": "AUD_USD",
        "USDJPY=X": "USD_JPY",
        "GBPAUD=X": "GBP_AUD",
        "USDCHF=X": "USD_CHF"
    }
    # Convert to OANDA format
    oanda_pair = YAHOO_TO_OANDA.get(pair, pair)

    # Convert period → days
    lookback_days = int(period.replace("d", ""))
    sim_count = sims

    # --- rest of code stays exactly the same ---
    granularity = "D"
    count = lookback_days
    candles = get_candles(oanda_pair, granularity, count)    

    if not candles or len(candles) < 30:
        raise ValueError(f"Not enough data for {oanda_pair} — need ≥30 days")

    # 2. Extract prices
    closes = np.array([float(c["mid"]["c"]) for c in candles])
    latest_close = closes[-1]
    log_returns = np.diff(np.log(closes))
    
    # 3. Calculate stats
    ann_drift = float(np.mean(log_returns) * 252 * 100)  # %
    ann_vol = float(np.std(log_returns) * np.sqrt(252) * 100)  # %

    # 4. Monte Carlo simulation
    dt = 1 / 252
    drift_daily = np.mean(log_returns)
    vol_daily = np.std(log_returns)
    np.random.seed(42)  # Reproducible

    paths = np.exp(
        (drift_daily - 0.5 * vol_daily**2) * dt
        + vol_daily * np.sqrt(dt) * np.random.normal(0, 1, (sim_count, 1))
    ).cumprod(axis=1) * latest_close

    # 5. 90% expected range
    all_final = paths[:, -1]
    range_90_low = float(np.percentile(all_final, 5))
    range_90_high = float(np.percentile(all_final, 95))

    # ==============================================
    # ✅ PERCENTILE CALCULATION — FULLY FIXED
    # ==============================================
    if range_90_high == range_90_low:
        percentile_rank = 50.0  # Flat market — neutral
    else:
        percentile_rank = round(
            ((latest_close - range_90_low) / (range_90_high - range_90_low)) * 100,
            1
        )
    # Hard clamp — NEVER outside 0–100%
    percentile_rank = max(0.0, min(100.0, percentile_rank))

    # 6. Probabilities & Regime
    p_up = float(np.mean(all_final > latest_close)) * 100
    p_down = 100 - p_up

    if percentile_rank < 10:
        regime = "🔻 OVERSOLD"
    elif percentile_rank > 90:
        regime = "⚠️ OVERBOUGHT"
    elif ann_drift > 0.1:
        regime = "📈 Uptrend"
    elif ann_drift < -0.1:
        regime = "📉 Downtrend"
    else:
        regime = "➡️ Sideways"

    # 7. Final output — clean JSON‑ready
    return {
        "ann_drift": round(ann_drift, 2),
        "ann_vol": round(ann_vol, 2),
        "range_90": [round(range_90_low, 5), round(range_90_high, 5)],
        "percentile_rank": percentile_rank,
        "p_up": round(p_up, 1),
        "p_down": round(p_down, 1),
        "regime": regime
    }

def build_telegram_report(results: list) -> str:
    """Format MC results for Telegram — safe against missing keys"""
    lines = [
        f"📊 FX DAILY MC — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "🔹 Period: 60d | Simulations: 5000 | Pairs: 8",
        ""
    ]
    for r in results:
        # Skip empty/invalid entries
        if not isinstance(r, dict) or "pair" not in r:
            continue
        pair = r["pair"]
        if "error" in r:
            lines.append(f"❌ {pair}: {r['error']}")
        else:
            lines.append(
                f"✅ {pair} | Drift: {r.get('ann_drift', 0):.1f}% | Vol: {r.get('ann_vol', 0):.1f}% | "
                f"Range: {r.get('range_90', [0,0])[0]:.5f}–{r.get('range_90', [0,0])[1]:.5f} | "
                f"Percentile: {r.get('percentile_rank', 0):.1f}% | {r.get('regime', 'N/A')}"
            )
    return "\n".join(lines)

# --------------------------
# RUN WHEN CALLED
# --------------------------
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python carlo_advanced.py EUR_USD")
        sys.exit(1)
    pair = sys.argv[1]
    result = run_monte_carlo(pair)
    print(json.dumps(result, indent=2))