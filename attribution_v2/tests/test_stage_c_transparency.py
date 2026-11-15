"""
test_stage_c_transparency.py — Phase 3.1 Stage C (C-4 / C-5) regression tests.

Scope (contract §4.1; consumer contract C-4 / C-5):

  * C-4  `derive_xgb_p_up` consumes an interpreted P(up) **only** in the
         READY-equivalent state (`sig.model_p_up is not None`). It never
         synthesizes a P(up) from the bot's `X` factor or from `raw_prob`, and a
         non-READY state must reach the profile record as `degraded`.
  * C-5  `data_bridge` keeps its exact scale-aware `_prob_clip` behaviour while
         now recording the source key + detected unit (no silent reinterpretation).

These pin the Stage C semantics so an accidental change fails CI.

Run (from attribution_v2/):  python -m pytest tests/test_stage_c_transparency.py -q
"""

from types import SimpleNamespace

import pytest

from data_bridge import FactorDataBridge
from live_hook import derive_xgb_p_up
from profile_runner import ProfileAttribution


def _sig(**kw):
    """Minimal Signal stand-in (only the attributes C-4 reads)."""
    return SimpleNamespace(**kw)


# ════════════════════════════════════════════════
# C-4 — READY-equivalent consumes P(up); non-READY yields nothing
# ════════════════════════════════════════════════
def test_c4_ready_uses_model_p_up_as_p_up():
    """`sig.model_p_up` IS the model's direction-independent P(UP) (see
    strategy_decision: model_p_up=round(p_up,4), distinct from direction-
    conditional `raw_prob`), so it is consumed verbatim."""
    assert derive_xgb_p_up(_sig(model_p_up=0.42), {"X": 70}) == pytest.approx(0.42)


def test_c4_ready_value_clamped_to_unit_interval():
    assert derive_xgb_p_up(_sig(model_p_up=1.5), None) == pytest.approx(1.0)
    assert derive_xgb_p_up(_sig(model_p_up=-0.2), None) == pytest.approx(0.0)


@pytest.mark.parametrize("x_val", [70, 0.7, None])
def test_c4_non_ready_never_synthesizes_from_X_or_raw_prob(x_val):
    """Pre-Stage-C returned `X/100` (or a `raw_prob`-derived value) here.

    C-4 forbids that: a non-READY prediction (no `model_p_up`) must yield NO
    interpreted P(up) — regardless of what `X` / `raw_prob` carry.
    """
    sig = _sig(model_p_up=None, raw_prob=0.8)
    w = None if x_val is None else {"X": x_val}
    assert derive_xgb_p_up(sig, w) is None


def test_c4_none_signal_returns_none():
    assert derive_xgb_p_up(None, {"X": 70}) is None


def test_c4_unparseable_model_p_up_returns_none():
    assert derive_xgb_p_up(_sig(model_p_up="not-a-number"), {"X": 70}) is None


def test_c4_non_ready_propagates_to_degraded_profile_record():
    """End-to-end, NOT just the helper's return value: a non-READY p_up (None)
    must flow through `process_candidate` and surface as `degraded=True` with
    `xgb` listed under `missing_factors`."""
    p_up = derive_xgb_p_up(_sig(model_p_up=None, raw_prob=0.8), {"X": 70})
    assert p_up is None

    rec = ProfileAttribution("PF-A").process_candidate(
        symbol="USD/JPY",
        candidate_direction="BUY",
        trend_raw=+1,
        location_raw=+1,
        xgb_p_up=p_up,  # None → degraded
        mc_p_up=0.75,
    )
    assert rec["decision"]["degraded"] is True
    assert "xgb" in rec["decision"]["missing_factors"]


def test_c4_ready_record_is_not_degraded_on_the_xgb_axis():
    """Control: a READY-equivalent p_up keeps `xgb` out of `missing_factors`."""
    p_up = derive_xgb_p_up(_sig(model_p_up=0.42), None)
    rec = ProfileAttribution("PF-A").process_candidate(
        symbol="USD/JPY",
        candidate_direction="BUY",
        trend_raw=+1,
        location_raw=+1,
        xgb_p_up=p_up,
        mc_p_up=0.75,
    )
    assert "xgb" not in rec["decision"]["missing_factors"]


# ════════════════════════════════════════════════
# C-5 — scale-aware clip is unchanged; source + unit are now recorded
# ════════════════════════════════════════════════
@pytest.mark.parametrize(
    "raw,expected",
    [
        (0.4, 0.4), (0.7, 0.7), (1.0, 1.0), (0.0, 0.0),
        (70, 0.7), (100, 1.0), (150, 1.0), (-5, 0.0),
        ("0.6", 0.6), ("70", 0.7),
        (None, None), ("x", None),
    ],
)
def test_c5_prob_clip_behaviour_is_unchanged(raw, expected):
    assert FactorDataBridge._prob_clip(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        (0.4, (0.4, "0-1")), (1.0, (1.0, "0-1")),
        (70, (0.7, "0-100")), (100, (1.0, "0-100")), (150, (1.0, "0-100")),
        (None, (None, "none")), ("x", (None, "unparseable")),
    ],
)
def test_c5_prob_clip_with_unit_labels(raw, expected):
    assert FactorDataBridge._prob_clip_with_unit(raw) == expected


def test_c5_pick_prob_uses_original_priority():
    aliases = ("xgb_prob", "prob_raw", "model_p_up")
    assert FactorDataBridge._pick_prob({"xgb_p_up": 70}, "xgb_p_up", aliases) == (70, "xgb_p_up")
    assert FactorDataBridge._pick_prob({"xgb_prob": 5}, "xgb_p_up", aliases) == (5, "xgb_prob")
    assert FactorDataBridge._pick_prob({"prob_raw": 5}, "xgb_p_up", aliases) == (5, "prob_raw")
    assert FactorDataBridge._pick_prob({"model_p_up": 5}, "xgb_p_up", aliases) == (5, "model_p_up")
    assert FactorDataBridge._pick_prob({}, "xgb_p_up", aliases) == (None, None)


def test_c5_pick_prob_matches_legacy_present_but_none_precedence():
    """Pins the exact legacy semantics: the first key that is PRESENT wins even
    when its value is None (old `.get(key, default)`), proving the refactor is
    behaviour-preserving for every input the old chain could receive."""
    cand = {"xgb_p_up": None, "xgb_prob": 0.7}
    got = FactorDataBridge._pick_prob(cand, "xgb_p_up", ("xgb_prob", "prob_raw", "model_p_up"))
    assert got == (None, "xgb_p_up")


def test_c5_provenance_records_source_and_unit():
    """`from_bot_candidate` stamps where each probability came from and which
    scale was detected — the value is unchanged, only made non-silent."""
    bridge = FactorDataBridge.__new__(FactorDataBridge)  # avoid live config load
    bridge.symbol = "USD/JPY"
    bridge.instrument = "USD_JPY"
    bridge.last_prob_provenance = None

    bridge.from_bot_candidate({"pair": "USD/JPY", "xgb_p_up": 70, "mc_p_up": 0.6})

    assert bridge.last_prob_provenance == {
        "xgb_p_up": {"source": "xgb_p_up", "unit": "0-100"},
        "mc_p_up": {"source": "mc_p_up", "unit": "0-1"},
    }


def test_c5_provenance_for_alias_source():
    bridge = FactorDataBridge.__new__(FactorDataBridge)
    bridge.symbol = "USD/JPY"
    bridge.instrument = "USD_JPY"
    bridge.last_prob_provenance = None

    bridge.from_bot_candidate({"pair": "USD/JPY", "xgb_prob": 0.55, "mc_pct_up": 40})

    assert bridge.last_prob_provenance == {
        "xgb_p_up": {"source": "xgb_prob", "unit": "0-1"},
        "mc_p_up": {"source": "mc_pct_up", "unit": "0-100"},
    }
