"""
Regression guard for the scoring log block in fx_trade_bot_v683.py.

calc_weighted_score() returns (None, None) when there is no direction
consensus (see the `NO CONSENSUS → SKIP` path). The score-breakdown log was
moved ABOVE the `continue`, so it now runs on the no-consensus path too — it
must therefore be protected by a `direction and w` guard before any w["..."]
access, or a no-consensus candidate raises TypeError and aborts the run
mid-scan.

This checks the shipped source via AST, so it fails if the guard is dropped
even though a single happy-path run would still look fine.

No network, no OANDA calls, no orders.

Run:  python -m pytest tests/test_scoring_log_guard.py -q
"""

import ast
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
BOT = BASE_DIR / "fx_trade_bot_v683.py"


def _tree():
    # Parsed once per call: node identity is what lets us find the parent body,
    # so two separate parses would never match.
    return ast.parse(BOT.read_text(encoding="utf-8"))


def _score_call(tree):
    """The `direction, w = calc_weighted_score(...)` assignment in main()."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        targets = [t for t in node.targets if isinstance(t, ast.Tuple)]
        if not targets:
            continue
        names = [elt.id for elt in targets[0].elts if isinstance(elt, ast.Name)]
        if names != ["direction", "w"]:
            continue
        value = node.value
        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "calc_weighted_score"
        ):
            return node
    return None


def test_calc_weighted_score_call_exists():
    assert _score_call(_tree()) is not None, "calc_weighted_score assignment not found"


def test_no_consensus_returns_none_twice():
    """Confirm the (None, None) contract the guard exists to handle."""
    src = BOT.read_text(encoding="utf-8")
    assert "NO CONSENSUS → SKIP" in src
    # The no-consensus branch must return a 2-tuple of None.
    import re

    assert re.search(
        r"return\s+None\s*,\s*None", src
    ), "expected `return None, None` on the no-consensus path"


def test_unguarded_w_access_would_crash():
    """Demonstrate the real failure mode the guard prevents.

    Reproduces the pre-change ordering (breakdown logged before the continue,
    with no guard) against the (None, None) no-consensus return.
    """

    def unguarded(direction, w):
        # Old shape: w["PASS"] accessed unconditionally for the tag.
        tag = "✅" if w["PASS"] else "❌"
        return tag

    def guarded(direction, w):
        # New shape: guarded by `if direction and w:`.
        if direction and w:
            return "✅" if w["PASS"] else "❌"
        return None

    import pytest

    with pytest.raises(TypeError):
        unguarded(None, None)

    assert guarded(None, None) is None


def test_guard_placement_matches_shipped_source():
    """The shipped source must use the guarded form, not the unguarded one."""
    src = BOT.read_text(encoding="utf-8")
    guarded = "if direction and w:"
    assert guarded in src, f"expected `{guarded}` guard in the score log block"


def test_score_log_block_is_guarded_and_covers_both_tags():
    """The breakdown log must sit before the continue AND behind the guard."""
    tree = _tree()
    call = _score_call(tree)
    assert call is not None

    # Find the enclosing body list and the statement following the assignment,
    # using the SAME tree so node identity holds.
    enclosing = None
    for node in ast.walk(tree):
        for field in ("body", "orelse", "finalbody"):
            body = getattr(node, field, None)
            if isinstance(body, list) and any(stmt is call for stmt in body):
                enclosing = body
                break
        if enclosing is not None:
            break

    assert enclosing is not None, "could not locate the assignment's statement list"
    idx = enclosing.index(call)
    after = enclosing[idx + 1 :]
    assert after, "no statements follow calc_weighted_score()"

    guard = after[0]
    assert isinstance(guard, ast.If), (
        f"expected the score log to be guarded by an `if`, got {type(guard).__name__}"
    )

    guard_src = ast.unparse(guard.test)
    assert "direction" in guard_src and "w" in guard_src, (
        f"guard does not test both direction and w: {guard_src!r}"
    )

    # The guard body must emit the breakdown with a pass/fail tag.
    # ast.unparse normalises quote style, so compare tag contents, not quotes.
    guard_text = ast.unparse(guard)
    assert "SCORE" in guard_text, "guarded block no longer logs the breakdown"
    assert "✅" in guard_text and "❌" in guard_text, (
        "breakdown log lost its pass/fail tag"
    )
    assert 'w["PASS"]' in guard_text or "w['PASS']" in guard_text, (
        "tag no longer derives from w['PASS']"
    )

    # And the FINAL display must not round away the distinction.
    assert "FINAL={w['FINAL']:.2f}" in guard_text.replace('"', "'"), (
        "FINAL precision is not .2f — a 29.97 score could print as 30.00"
    )
    print(f"   guard: if {guard_src}")
    print("   tags: ✅/❌  FINAL precision: .2f")


def test_reason_line_still_follows_the_continue_guard():
    """The REASON line must stay on the reject path, after the breakdown."""
    src = BOT.read_text(encoding="utf-8")
    assert "➖ REASON: FINAL {w['FINAL']:.2f} < MIN_CONVICTION={min_conv:.2f}" in src
    # src.index raises if missing, which is itself the assertion.
    score_at = src.index('f"{tag} SCORE {pair} {direction} | "')
    reason_at = src.index("➖ REASON: FINAL")
    assert score_at < reason_at, "breakdown log must precede the REASON line"
    print(f"   breakdown at char {score_at}, REASON at char {reason_at}")
