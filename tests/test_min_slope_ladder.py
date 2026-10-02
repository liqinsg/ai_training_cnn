"""
Tests for the min_slope tightening ladder in fx_trade_bot_v683.py.

The ladder lets an operator advance the EMA-slope threshold by editing one
config value only:
    profile3.min_slope_rung: 0.0003 -> 0.0005 -> 0.0007 -> 0.001
These tests cover the guardrails, because a typo there would silently widen the
trend filter beyond the agreed floor — the one failure mode this knob must not
have.

The bot module is NOT imported: its module level runs argparse against
sys.argv, which collides with pytest's own arguments. Everything is extracted
from the source with AST instead, which also means these tests exercise the
shipped text rather than a re-implementation.

No network, no OANDA calls, no orders.

Run:  python -m pytest tests/test_min_slope_ladder.py -q
"""

import ast
import logging
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
BOT = BASE_DIR / "fx_trade_bot_v683.py"


def _tree():
    return ast.parse(BOT.read_text(encoding="utf-8"))


def _module_literal(tree, name):
    return ast.literal_eval(
        next(
            n.value
            for n in tree.body
            if isinstance(n, ast.Assign)
            and getattr(n.targets[0], "id", None) == name
        )
    )


def _load():
    """Extract MIN_SLOPE_LADDER, _TREND_TP_CONFIG and resolve_min_slope."""
    tree = _tree()
    fn = next(
        (
            n
            for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name == "resolve_min_slope"
        ),
        None,
    )
    assert fn is not None, "resolve_min_slope not found in the bot source"

    ns = {
        "logger": logging.getLogger("ladder-test"),
        # resolve_min_slope() reads this module-level constant.
        "MIN_SLOPE_LADDER": _module_literal(tree, "MIN_SLOPE_LADDER"),
    }
    exec(
        compile(ast.Module(body=[fn], type_ignores=[]), str(BOT), "exec"),
        ns,
    )
    return {
        "ladder": _module_literal(tree, "MIN_SLOPE_LADDER"),
        "profiles": _module_literal(tree, "_TREND_TP_CONFIG"),
        "resolve": ns["resolve_min_slope"],
        "tree": tree,
    }


L = _load()
LADDER = L["ladder"]
PROFILES = L["profiles"]
resolve_min_slope = L["resolve"]


def test_ladder_is_widest_first_and_ends_at_the_original_value():
    assert LADDER == tuple(sorted(LADDER)), (
        "ladder is not ascending, so 'advance a rung' would not mean 'tighten'"
    )
    assert len(set(LADDER)) == len(LADDER), "duplicate rungs"
    assert LADDER[0] == 0.0003, "widest rung should be the relaxation"
    assert LADDER[-1] == 0.001, (
        "last rung must be the original strictest value so completing the "
        "ladder equals reverting the relaxation"
    )


@pytest.mark.parametrize("rung", LADDER)
def test_every_ladder_rung_resolves_to_itself(rung):
    assert resolve_min_slope({"min_slope_rung": rung}, "profile3") == rung


def test_invalid_rung_is_refused_and_falls_back_to_strictest():
    """A typo must fail closed (strictest), never open (widest)."""
    for bad in (0.0004, 0.0, 0.002, -0.001, "0.0005"):
        got = resolve_min_slope({"min_slope_rung": bad}, "profile3")
        assert got == LADDER[-1], (
            f"rung {bad!r} resolved to {got}; expected the strictest {LADDER[-1]}"
        )
        assert got != LADDER[0], f"rung {bad!r} widened the filter"


def test_missing_rung_falls_back_to_legacy_min_slope():
    """Profiles without the ladder knob keep working unchanged."""
    assert resolve_min_slope({"min_slope": 0.001}, "profile2") == 0.001
    assert resolve_min_slope({"min_slope": 0.002}, "x") == 0.002


def test_shipped_profiles_resolve_as_expected():
    p2 = resolve_min_slope(PROFILES["profile2"], "profile2")
    p3 = resolve_min_slope(PROFILES["profile3"], "profile3")
    print(f"   profile2 -> {p2}   profile3 -> {p3}")
    assert p2 == 0.001, "profile2 was never relaxed and must stay strict"
    assert p3 == LADDER[0], "profile3 should start at the widest rung"
    assert "min_slope_rung" not in PROFILES["profile2"], (
        "profile2 should not carry a ladder knob"
    )


def test_advancing_a_rung_needs_no_code_change():
    """The whole point: editing the config value alone moves the threshold."""
    observed = [
        resolve_min_slope({"min_slope_rung": r}, "profile3") for r in LADDER
    ]
    print(f"   ladder walk: {observed}")
    assert observed == list(LADDER)
    # Strictly tightening, with no repeats from a silent clamp.
    assert all(b > a for a, b in zip(observed, observed[1:]))


def test_filter_reads_the_resolved_rung_not_a_hardcoded_value():
    """evaluate_trend_and_tp must call resolve_min_slope, not index min_slope."""
    fn = next(
        n
        for n in ast.walk(L["tree"])
        if isinstance(n, ast.FunctionDef) and n.name == "evaluate_trend_and_tp"
    )
    body = ast.unparse(fn)
    assert "resolve_min_slope(cfg, profile_name)" in body, (
        "the filter no longer resolves min_slope through the ladder"
    )
    assert 'cfg["min_slope"]' not in body, (
        "the filter still indexes min_slope directly, bypassing the ladder"
    )


def test_module_level_startup_logs_the_active_rung():
    """The run banner must show which rung is live, for post-hoc attribution."""
    src = BOT.read_text(encoding="utf-8")
    assert "MIN_SLOPE LADDER: active rung=" in src, (
        "no startup line reporting the active rung"
    )
