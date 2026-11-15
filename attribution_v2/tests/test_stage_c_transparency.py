"""
test_stage_c_transparency.py — Phase 3.1 Stage C (C-4 / C-5) regression tests.

Scope (contract §4.1; consumer contract C-4 / C-5):

  * C-4  `derive_xgb_p_up` consumes an interpreted P(up) **only** when the
         producer explicitly marked the value as a genuine legacy model
         inference (a present `model_p_up` value **and**
         `model_p_up_source == "LEGACY_MODEL_INFERENCE_OK"`). Mere field presence
         is not sufficient. It never synthesizes a P(up) from the bot's `X` factor
         or from `raw_prob`, and an unmarked state must reach the profile record
         as `degraded`.
         NOTE: this marker is NOT `PredictionResult.status == READY` — the live
         path is the legacy `predict_p_up` route (contract §4.1.1.6 known
         exception). Binding to the authoritative adapter is deferred to
         Phase 3.6.
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


LEGACY_OK = "LEGACY_MODEL_INFERENCE_OK"  # mirrors strategy_decision.MODEL_P_UP_SOURCE_LEGACY_OK


def _sig(**kw):
    """Minimal Signal stand-in (only the attributes C-4 reads)."""
    return SimpleNamespace(**kw)


# ════════════════════════════════════════════════
# C-4 — the producer's legacy-inference marker gates P(up); everything else yields nothing
# ════════════════════════════════════════════════
def test_c4_marked_value_uses_model_p_up_as_p_up():
    """`sig.model_p_up` IS the model's direction-independent P(UP) (see
    strategy_decision: model_p_up=round(p_up,4), distinct from direction-
    conditional `raw_prob`), so it is consumed verbatim when the producer marked
    the Signal as a genuine legacy model inference."""
    assert derive_xgb_p_up(
        _sig(model_p_up=0.42, model_p_up_source=LEGACY_OK), {"X": 70}
    ) == pytest.approx(0.42)


def test_c4_marked_value_clamped_to_unit_interval():
    assert derive_xgb_p_up(
        _sig(model_p_up=1.5, model_p_up_source=LEGACY_OK), None
    ) == pytest.approx(1.0)
    assert derive_xgb_p_up(
        _sig(model_p_up=-0.2, model_p_up_source=LEGACY_OK), None
    ) == pytest.approx(0.0)


def test_c4_value_without_the_marker_is_rejected():
    """The core C-4 tightening: a *present* value is NOT sufficient evidence of a
    marked inference. An unmarked Signal, or one whose source is not the marker,
    must yield no interpreted P(up)."""
    # field present but no provenance marker at all (legacy / hand-built)
    assert derive_xgb_p_up(_sig(model_p_up=0.42), {"X": 70}) is None
    # explicit non-matching provenance
    assert derive_xgb_p_up(_sig(model_p_up=0.42, model_p_up_source="UNSET"), None) is None
    assert derive_xgb_p_up(_sig(model_p_up=0.42, model_p_up_source="DEGRADED"), None) is None


@pytest.mark.parametrize("x_val", [70, 0.7, None])
def test_c4_missing_value_never_synthesizes_from_X_or_raw_prob(x_val):
    """Pre-Stage-C returned `X/100` (or a `raw_prob`-derived value) here.

    C-4 forbids that: a prediction with no `model_p_up` must yield NO interpreted
    P(up) — regardless of what `X` / `raw_prob` carry, even with the marker set.
    """
    sig = _sig(model_p_up=None, raw_prob=0.8, model_p_up_source=LEGACY_OK)
    w = None if x_val is None else {"X": x_val}
    assert derive_xgb_p_up(sig, w) is None


def test_c4_none_signal_returns_none():
    assert derive_xgb_p_up(None, {"X": 70}) is None


def test_c4_unparseable_model_p_up_returns_none():
    assert derive_xgb_p_up(
        _sig(model_p_up="not-a-number", model_p_up_source=LEGACY_OK), {"X": 70}
    ) is None


def test_c4_missing_value_propagates_to_degraded_profile_record():
    """End-to-end, NOT just the helper's return value: a p_up with no value (None)
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


def test_c4_unmarked_value_propagates_to_degraded_profile_record():
    """A value carried WITHOUT the marker must end up degraded end-to-end —
    proving the provenance check (not just the None case) shapes the record."""
    p_up = derive_xgb_p_up(_sig(model_p_up=0.42), {"X": 70})  # unmarked → rejected
    assert p_up is None

    rec = ProfileAttribution("PF-A").process_candidate(
        symbol="USD/JPY",
        candidate_direction="BUY",
        trend_raw=+1,
        location_raw=+1,
        xgb_p_up=p_up,
        mc_p_up=0.75,
    )
    assert rec["decision"]["degraded"] is True
    assert "xgb" in rec["decision"]["missing_factors"]


def test_c4_marked_record_is_not_degraded_on_the_xgb_axis():
    """Control: a producer-marked p_up keeps `xgb` out of `missing_factors`."""
    p_up = derive_xgb_p_up(_sig(model_p_up=0.42, model_p_up_source=LEGACY_OK), None)
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
