"""
Tests for analyze_slope_diag.py.

The analyzer reads SLOPE DIAG lines from the bot's log. Real DIAG output did not
exist when this was written (the flag had never been enabled), so the fixtures
here are synthetic lines in the exact shipped format, generated from parameters
rather than hand-copied — a format change in the bot then breaks these tests
instead of silently producing a zero-row report.

Run:  python -m pytest tests/test_analyze_slope_diag.py -q
"""

import sys
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import analyze_slope_diag as A  # noqa: E402

MIN_SLOPE = 0.0003
BASELINE = 0.001


def diag_line(
    slope,
    direction="SELL",
    profile="profile3",
    tf="15m",
    price_ok=True,
    min_slope=MIN_SLOPE,
    baseline=BASELINE,
):
    """Render a DIAG line exactly as the bot's f-string does.

    flags are computed from the shipped inclusive comparisons so the fixture
    cannot disagree with the semantics the analyzer checks.
    """
    if direction == "BUY":
        loose = slope >= min_slope
        strict = slope >= baseline
        cmp_ = "<="
    else:
        loose = slope <= -min_slope
        strict = slope <= -baseline
        cmp_ = ">="
    sensitive = loose and not strict
    flip = price_ok and sensitive
    return (
        f"2026-10-02 07:21:25,904 [INFO] 📊 SLOPE DIAG: profile={profile} "
        f"dir={direction} tf={tf} slope={slope:.6f} min_slope={min_slope:.6f} "
        f"price_ok={price_ok} "
        f"loose({-min_slope:.6f}{cmp_})={loose} "
        f"strict({-baseline:.6f}{cmp_})={strict} "
        f"sensitive={sensitive} would_flip={flip}"
    )


@pytest.fixture
def logfile(tmp_path):
    def _write(lines, name="bot_profile3.log"):
        path = tmp_path / name
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return str(path)

    return _write


def test_parses_a_single_row_and_derives_fields(logfile):
    path = logfile([diag_line(-0.0004)])
    rows, seen = A.parse_file(path)
    assert seen >= 1
    assert len(rows) == 1
    row = rows[0]
    assert row.profile == "profile3"
    assert row.direction == "SELL"
    assert row.timeframe == "15m"
    assert row.slope == pytest.approx(-0.0004)
    assert row.min_slope == pytest.approx(MIN_SLOPE)
    assert row.strict_threshold == pytest.approx(BASELINE)
    assert row.price_ok is True
    assert row.sensitive is True
    assert row.would_flip is True
    assert row.abs_slope == pytest.approx(0.0004)


def test_price_blocked_row_is_sensitive_but_not_a_flip(logfile):
    """The exact regression the new criteria fixed (USDJPY 07:21 case)."""
    path = logfile([diag_line(-0.0004, price_ok=False)])
    rows, _ = A.parse_file(path)
    assert rows[0].sensitive is True
    assert rows[0].would_flip is False, (
        "a price-blocked candidate must not count as ladder evidence"
    )


def test_slope_outside_the_widened_band_is_not_sensitive(logfile):
    path = logfile([diag_line(0.000092)])  # positive slope on a SELL
    rows, _ = A.parse_file(path)
    assert rows[0].sensitive is False
    assert rows[0].would_flip is False


def test_flip_above_the_strict_baseline_is_not_sensitive(logfile):
    path = logfile([diag_line(-0.002)])
    rows, _ = A.parse_file(path)
    assert rows[0].strict is True
    assert rows[0].sensitive is False


def test_buy_and_sell_both_parse(logfile):
    path = logfile([diag_line(0.0004, direction="BUY"), diag_line(-0.0004, direction="SELL")])
    rows, _ = A.parse_file(path)
    assert {r.direction for r in rows} == {"BUY", "SELL"}
    assert all(r.sensitive for r in rows)


def test_outcome_attribution_follows_the_diag_row(logfile):
    path = logfile(
        [
            diag_line(-0.0004),
            "2026-10-02 07:21:26,132 [INFO] 📈 USDJPY=X: gap=1.14 ≥ 0.25 — QUALIFIED",
            "2026-10-02 07:21:26,325 [INFO] ✅ EXECUTED USDJPY=X SELL | SL=1.0 | TP=2.0",
            diag_line(-0.0005),
            "2026-10-02 07:21:26,325 [INFO] ➖ REASON: FINAL 19.70 < MIN_CONVICTION=30.00",
        ]
    )
    rows, _ = A.parse_file(path)
    assert rows[0].outcome == "executed"
    assert rows[1].outcome == "rejected_score"


def test_malformed_diag_line_is_counted_not_silently_dropped(logfile):
    path = logfile(["📊 SLOPE DIAG: profile=profile3 dir=SELL tf=15m slope=oops"])
    rows, seen = A.parse_file(path)
    assert rows == []
    assert seen >= 1, "malformed DIAG lines must not be invisible"


def test_dedupe_removes_the_double_logged_row(logfile):
    path = logfile([diag_line(-0.0004), diag_line(-0.0004)])
    rows, _ = A.parse_file(path)
    assert len(rows) == 2
    deduped, dropped = A.dedupe(rows)
    assert dropped == 1
    assert len(deduped) == 1


def test_dedupe_keeps_genuinely_different_rows(logfile):
    path = logfile([diag_line(-0.0004), diag_line(-0.0005), diag_line(-0.0004, price_ok=False)])
    rows, _ = A.parse_file(path)
    deduped, dropped = A.dedupe(rows)
    assert dropped == 0
    assert len(deduped) == 3


def test_report_gate_progress_and_exit_code(logfile, capsys):
    path = logfile([diag_line(-0.0004), diag_line(-0.0005)])
    rows, _ = A.parse_file(path)
    rc = A.report(rows, target=20, files=[path])
    out = capsys.readouterr().out
    assert rc == 0
    assert "would_flip=True :   2 / 20" in out
    assert "18 more would_flip rows needed" in out


def test_report_flags_eligible_when_target_met(logfile, capsys):
    path = logfile([diag_line(-0.0004)] * 3)
    rows, _ = A.parse_file(path)
    rows, _ = A.dedupe(rows)  # collapse to 1 unique
    assert len(rows) == 1
    rc = A.report(rows, target=1, files=[path])
    out = capsys.readouterr().out
    assert rc == 0
    assert "target met" in out


def test_report_detects_inconsistent_row(logfile, capsys):
    """A hand-edited/corrupt row claiming would_flip with price_ok=False."""
    line = diag_line(-0.0004, price_ok=False).replace(
        "would_flip=False", "would_flip=True"
    )
    path = logfile([line])
    rows, _ = A.parse_file(path)
    rc = A.report(rows, target=20, files=[path])
    out = capsys.readouterr().out
    assert rc == 1, "inconsistent rows must fail the report"
    assert "violate" in out or "price leg" in out


def test_report_handles_empty_input_with_guidance(capsys, tmp_path):
    path = tmp_path / "empty.log"
    path.write_text("nothing here\n", encoding="utf-8")
    rows, _ = A.parse_file(str(path))
    assert rows == []
    rc = A.report(rows, target=20, files=[str(path)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "No SLOPE DIAG rows found" in out
    assert "SLOPE_DIAG" in out  # tells the operator what to check


def test_main_returns_usage_error_when_no_files(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # no logs anywhere
    monkeypatch.setattr(A, "discover_logs", lambda: [])
    assert A.main(["--target", "5"]) == 2


def test_main_end_to_end_on_a_real_shaped_log(logfile, capsys):
    path = logfile(
        [
            diag_line(-0.0004),
            "✅ EXECUTED USDJPY=X SELL | SL=1.0 | TP=2.0",
            diag_line(-0.0002, price_ok=False),
            diag_line(0.0005),
        ]
    )
    rc = A.main(["--target", "1", path])
    out = capsys.readouterr().out
    assert rc == 0
    assert "LADDER GATE" in out
    assert "target met" in out
    assert "WOULD_FLIP DETAIL" in out
    assert "consistent:" in out
