"""
Proof and regression guard for the RSI scoring term (R) in fx_trade_bot_v683.py.

Old form, per direction:
    BUY : R = max(0, min(100, (50 - rsi) * 2))
    SELL: R = max(0, min(100, (rsi - 50) * 2))
That is not a measurement of RSI, it is a hard gate at the 50 midline: any short
with RSI <= 50 scored exactly 0 and any long with RSI >= 50 scored exactly 0, so
the configured 15% RSI weight disappeared for roughly half of all candidates
purely because the reading landed on the wrong side of 50.

New form:
    R = max(0, min(100, |rsi - 50| * 2))

Both forms are computed here on the RSI values from the 2026-10-02 07:21 UTC
profile3 run so the change is measurable rather than asserted.

No network, no OANDA calls, no orders.

Run:  python -m pytest tests/test_rsi_score_symmetry.py -q
"""

import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
BOT = BASE_DIR / "fx_trade_bot_v683.py"


def old_R(rsi, direction):
    if direction == "BUY":
        return max(0.0, min(100.0, (50.0 - rsi) * 2.0))
    return max(0.0, min(100.0, (rsi - 50.0) * 2.0))


def new_R(rsi, direction=None):
    return max(0.0, min(100.0, abs(rsi - 50.0) * 2.0))


def test_shipped_formula_is_the_symmetric_one():
    src = BOT.read_text(encoding="utf-8")
    assert "R = max(0.0, min(100.0, abs(rsi - 50.0) * 2.0))" in src, (
        "R is no longer |rsi - 50| * 2 — the 50 midline gate may be back"
    )
    # The old per-direction branch must be gone.
    assert "(50.0 - rsi) * 2.0" not in src, "direction-dependent R formula still present"
    assert "(rsi - 50.0) * 2.0)" not in src.replace(
        "abs(rsi - 50.0) * 2.0", ""
    ), "old SELL-only R formula still present"


def test_midline_is_zero_in_both_directions():
    for direction in ("BUY", "SELL"):
        assert new_R(50.0, direction) == 0.0
        assert old_R(50.0, direction) == 0.0


def test_new_formula_has_no_discontinuity_at_50():
    """A reading just either side of 50 must score nearly the same."""
    below = new_R(49.9)
    above = new_R(50.1)
    print(f"   new R: rsi=49.9 -> {below:.2f}   rsi=50.1 -> {above:.2f}")
    assert abs(below - above) < 1.0, "new formula still has a step at the midline"

    old_below = old_R(49.9, "SELL")
    old_above = old_R(50.1, "SELL")
    print(f"   old R: rsi=49.9 -> {old_below:.2f}   rsi=50.1 -> {old_above:.2f}")
    assert old_below == 0.0 and old_above > 0.0


def test_extremes_keep_the_same_scale():
    """100 must stay the ceiling so total scores stay comparable."""
    assert new_R(100.0) == 100.0, "overbought no longer reaches 100"
    assert new_R(0.0) == 100.0, "oversold no longer reaches 100"
    assert new_R(75.0) == 50.0


def test_real_run_candidates_change_measurably():
    """Apply both forms to the RSI values logged in the 07:21 profile3 run.

    Both candidates were SELLs. The old form zeroed USDJPY's RSI contribution
    entirely (RSI 47.5) while AUDUSD scored normally (RSI 63.5).
    """
    run_candidates = {
        # (rsi, R factor as printed in the 07:21 run's breakdown line)
        "AUDUSD=X SELL": (63.5, 26.9),
        "USDJPY=X SELL": (47.5, 0.0),
    }
    weight = 0.15
    print(
        f"\n   {'candidate':16} {'rsi':>5}  {'old R':>7} {'new R':>7}  "
        f"{'old pts':>7} {'new pts':>7}"
    )
    for label, (rsi, logged_old_R) in run_candidates.items():
        old_r = old_R(rsi, "SELL")
        new_r = new_R(rsi, "SELL")
        # The logged R factor must match the old formula, which confirms the
        # model of what was running before this change.
        assert abs(old_r - logged_old_R) < 1.0, (
            f"{label}: modelled old R={old_r:.1f} disagrees with logged {logged_old_R}"
        )
        print(
            f"   {label:16} {rsi:5.1f}  {old_r:7.1f} {new_r:7.1f}  "
            f"{old_r * weight:7.2f} {new_r * weight:7.2f}"
        )

    # The whole point: the sub-50 short is no longer zeroed.
    assert new_R(47.5, "SELL") > 0.0, "RSI 47.5 still scores zero for a short"
    assert old_R(47.5, "SELL") == 0.0
    assert new_R(47.5) == 5.0

    # And the direction no longer matters, which is the asymmetry being fixed.
    for rsi in (10.0, 30.0, 47.5, 50.0, 63.5, 80.0, 95.0):
        assert new_R(rsi, "BUY") == new_R(rsi, "SELL"), f"asymmetric at rsi={rsi}"
    print("   symmetry: R identical for BUY and SELL at every tested rsi")


def test_weighted_impact_is_bounded_and_documented():
    """Quantify the swing for the two candidates from the real run."""
    weight = 0.15
    aud_delta = (new_R(63.5) - old_R(63.5, "SELL")) * weight
    jpy_delta = (new_R(47.5) - old_R(47.5, "SELL")) * weight
    print(f"\n   AUDUSD delta={aud_delta:+.2f} pts   USDJPY delta={jpy_delta:+.2f} pts")
    # AUDUSD was overbought for a short, so both forms already credited it.
    assert abs(aud_delta) < 0.6
    # USDJPY was below the midline and previously got nothing.
    assert jpy_delta > 0.5
