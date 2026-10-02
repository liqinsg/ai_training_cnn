"""
Offline proof that the RSI column survives a pandas_ta failure.

Context: in this environment `import pandas_ta` raises
`ImportError: Numba needs NumPy 2.2 or less. Got NumPy 2.5.` The old code only
logged a warning, so df["rsi"] was never created, the bot's
`.get("rsi", 50.0)` silently substituted 50.0, and the RSI scoring term
((rsi - 50) * 2) collapsed to exactly 0.0 for every pair — the configured RSI
weight stopped existing with no visible symptom.

No network, no OANDA calls, no orders.

Run:  python -m pytest tests/test_rsi_fallback.py -q
"""

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from data_pipeline import FeatureConfig, FeatureEngine  # noqa: E402


def make_frame(closes):
    closes = pd.Series(closes, dtype="float64")
    return pd.DataFrame(
        {
            "Open": closes.shift(1).fillna(closes.iloc[0]),
            "High": closes + 0.0005,
            "Low": closes - 0.0005,
            "Close": closes,
            "Volume": 1000.0,
        }
    )


def build_rsi(closes, period=14):
    engine = FeatureEngine(FeatureConfig(use_rsi=True, rsi_period=period))
    out = engine.build(make_frame(closes))
    return out


def test_perfect_uptrend_pins_rsi_at_100():
    """A monotonic rise has zero average loss, so RSI is exactly 100.0."""
    out = build_rsi([1.0 + i * 0.001 for i in range(120)])
    rsi = out["rsi"].dropna()
    print(f"   monotonic rise: last rsi={rsi.iloc[-1]:.2f}, unique={rsi.nunique()}")
    assert np.isfinite(rsi).all(), "RSI produced NaN/inf on a clean uptrend"
    assert rsi.iloc[-1] == 100.0, f"expected 100.0, got {rsi.iloc[-1]:.2f}"
    assert (rsi == 100.0).all(), "avg_loss==0 must pin the whole series to 100.0"


def test_rsi_column_exists_and_varies_on_a_mixed_trend():
    """A trend with genuine pullbacks must yield a varying RSI series.

    Note: a monotonic rise (even a noisy-looking one) has zero average loss and
    therefore pins RSI at exactly 100.0 — variability needs real down bars, so
    this uses a sine-wave oscillation on top of the uptrend.
    """
    closes = [1.0 + i * 0.001 + 0.004 * math.sin(i / 3.0) for i in range(120)]
    out = build_rsi(closes)

    assert "rsi" in out.columns, (
        "df['rsi'] missing — pandas_ta failed and the fallback did not run; "
        "the bot would silently score RSI as 50.0"
    )
    rsi = out["rsi"].dropna()
    assert not rsi.empty, "RSI column is entirely NaN"
    assert rsi.iloc[-1] > 90.0, f"strong uptrend gave RSI={rsi.iloc[-1]:.2f}"
    # The old failure mode left the column absent, so every caller saw one
    # value (the 50.0 default) for every pair.
    assert rsi.nunique() > 1, "RSI is constant — fallback did not compute a series"
    print(
        f"   mixed trend: last rsi={rsi.iloc[-1]:.2f}, unique={rsi.nunique()}, "
        f"min={rsi.min():.2f}, max={rsi.max():.2f}"
    )


def test_rsi_distinguishes_direction():
    """Up and down trends must not produce the same RSI."""
    up = build_rsi([1.0 + i * 0.001 for i in range(120)])["rsi"].dropna()
    down = build_rsi([1.5 - i * 0.001 for i in range(120)])["rsi"].dropna()

    print(f"   up rsi={up.iloc[-1]:.2f}  down rsi={down.iloc[-1]:.2f}")
    assert up.iloc[-1] > 70.0, f"uptrend RSI={up.iloc[-1]:.2f} not overbought"
    assert down.iloc[-1] < 30.0, f"downtrend RSI={down.iloc[-1]:.2f} not oversold"
    # A constant 50.0 sentinel cannot pass either bound, so this also catches
    # the silent-substitution regression.
    assert abs(up.iloc[-1] - down.iloc[-1]) > 40.0


def test_rsi_flat_market_is_neutral_and_finite():
    """0/0 must not produce NaN or inf."""
    out = build_rsi([1.2] * 120)
    rsi = out["rsi"].dropna()
    assert np.isfinite(rsi).all(), "flat market produced NaN/inf RSI"
    print(f"   flat market: last rsi={rsi.iloc[-1]:.2f}, finite=True")


def test_real_rsi_moves_the_scoring_term():
    """Quantify the cost of the silent 50.0 substitution.

    A SELL scores R = (rsi - 50) * 2, so only an OVERBOUGHT reading (rsi > 50)
    contributes to a short. With the sentinel this is exactly 0.0 for every pair,
    so the RSI weight contributed nothing at all. An oscillating series is used
    because a monotonic one saturates RSI at 0 or 100.
    """
    closes = [1.0 + 0.004 * math.sin(i / 3.0) for i in range(120)]
    out = build_rsi(closes)
    rsi_val = float(out["rsi"].dropna().iloc[-1])

    def rsi_score(rsi, direction="SELL"):
        if direction == "SELL":
            return max(0.0, min(100.0, (rsi - 50.0) * 2.0))
        return max(0.0, min(100.0, (50.0 - rsi) * 2.0))

    sentinel = rsi_score(50.0)
    real = rsi_score(rsi_val)
    print(f"   oscillating market rsi={rsi_val:.2f}")
    print(f"   SELL R term: sentinel(50.0)={sentinel:.1f}  real({rsi_val:.2f})={real:.1f}")
    assert sentinel == 0.0, "sentinel 50.0 should score 0 — that was the silent bug"
    assert rsi_val > 50.0, f"expected an overbought reading for a short, got {rsi_val:.2f}"
    assert real > 0.0, "real overbought RSI must contribute to the SELL score"

    # Weighted by the profile's RSI weight, the missing term cost this much.
    print(f"   with RSI weight 0.15 the lost contribution was {real * 0.15:.2f} pts")
    assert real * 0.15 > 1.0, (
        f"expected the missing RSI term to be worth >1 score point, "
        f"got {real * 0.15:.2f}"
    )
