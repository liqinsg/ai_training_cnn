# tests/test_ema100_regression.py
# Focused regression test for evaluate_trend_and_tp() EMA100 semantics.
#
# Exercises three cases:
#   1. week_ema100_filter_enabled=False  -> skip entire EMA100 layer
#   2. week_ema100_filter_enabled=True   -> EMA100 zone + TP-floor active
#   3. week_ema100_filter_enabled=True, weekly_ema100=None -> fail-open preserved
#
# Imports the actual production function by AST-extracting it from
# fx_trade_bot_v71.py, avoiding that module's heavy side effects.

import ast
import io
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "fx_trade_bot_v71.py"


def calculate_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()


def _extract_function_source(module_path: str, fn_name: str) -> str:
    tree = ast.parse(Path(module_path).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == fn_name:
            return ast.get_source_segment(Path(module_path).read_text(encoding="utf-8"), node)
    raise RuntimeError(f"Function {fn_name!r} not found in {module_path}")


def _load_evaluate_trend_and_tp():
    source = _extract_function_source(str(SRC), "evaluate_trend_and_tp")
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    log = logging.getLogger("test_ema100")
    log.handlers = [handler]
    log.setLevel(logging.INFO)
    ns = {
        "calculate_ema": calculate_ema,
        "logger": log,
        "np": np,
        "pd": pd,
    }
    exec(source, ns)
    return ns["evaluate_trend_and_tp"], buf, log


def _make_df(n=105, trend="up"):
    rng = np.random.default_rng(42)
    prices = 1.1000 + np.cumsum(rng.normal(0, 0.0001, n))
    if trend == "up":
        prices = 1.1000 + np.linspace(0, 0.01, n) + rng.normal(0, 0.00005, n)
    elif trend == "down":
        prices = 1.1100 - np.linspace(0, 0.01, n) + rng.normal(0, 0.00005, n)
    else:
        prices = 1.1050 + rng.normal(0, 0.00005, n)
    return pd.DataFrame({"Close": prices})


def _call(fn, **overrides):
    base = dict(
        profile_name="profile3",
        direction="BUY",
        mc_pct_up=70.0,
        entry_price=1.1100,
        pip_value=0.0001,
        df=_make_df(trend="up"),
        weekly_ema100=1.1050,
        ema_cross_filter=True,
        fast_period=40,
        slow_period=80,
        base_tp_pips=50,
        mc_strong_threshold=0.55,
        tp_mult=2.0,
        tp_strong_mult=2.5,
        ema100_buffer_pips=30,
        ema100_tp_floor_pips=30,
        week_ema100_filter_enabled=True,
        timeframe="15m",
    )
    base.update(overrides)
    return fn(**base)


@pytest.fixture(scope="module")
def fn_and_log():
    fn, buf, log = _load_evaluate_trend_and_tp()
    yield fn, buf, log
    log.handlers.clear()


class TestEma100WeeklyFilterGate:
    """Case 1: week_ema100_filter_enabled=False skips the entire EMA100 layer."""

    def test_skip_returns_default_multipliers(self, fn_and_log):
        fn, _, _ = fn_and_log
        ok, tp, reason, lot_mult, tp_mult = _call(
            fn, week_ema100_filter_enabled=False, weekly_ema100=1.0500
        )
        assert ok is True
        assert lot_mult == 1.0
        assert tp_mult == 1.0

    def test_skip_reason(self, fn_and_log):
        fn, _, _ = fn_and_log
        _, _, reason, _, _ = _call(fn, week_ema100_filter_enabled=False)
        assert reason == "OK: WEEKLY_EMA_SKIPPED"

    def test_skip_respects_pre_ema_tp_calc(self, fn_and_log):
        fn, _, _ = fn_and_log
        _, tp_pips, _, _, _ = _call(
            fn, week_ema100_filter_enabled=False, mc_pct_up=60.0
        )
        expected_tp = 50 * 2.5
        assert abs(tp_pips - expected_tp) < 1e-6

    def test_skip_strong_momentum_tp(self, fn_and_log):
        fn, _, _ = fn_and_log
        _, tp_pips, _, _, _ = _call(
            fn, week_ema100_filter_enabled=False, mc_pct_up=70.0
        )
        expected_tp = 50 * 2.5
        assert abs(tp_pips - expected_tp) < 1e-6

    def test_skip_even_with_valid_ema100_in_buffer(self, fn_and_log):
        """Ema100 is in the BUFFER zone (within 30 pips), but filter disabled
        must NOT apply lot/TP reduction."""
        fn, _, _ = fn_and_log
        ok, tp, reason, lot_mult, tp_mult = _call(
            fn,
            week_ema100_filter_enabled=False,
            weekly_ema100=1.1100,
            entry_price=1.1105,
            pip_value=0.0001,
        )
        assert ok is True
        assert lot_mult == 1.0
        assert tp_mult == 1.0
        assert "WEEKLY_EMA_SKIPPED" in reason

    def test_skip_never_blocks_entry_wait(self, fn_and_log):
        """Filter disabled -> even if BUY below weekly EMA100 (a WAIT case),
        entry is NOT blocked."""
        fn, _, _ = fn_and_log
        ok, _, _, _, _ = _call(
            fn,
            week_ema100_filter_enabled=False,
            weekly_ema100=1.1200,
            entry_price=1.1190,
            pip_value=0.0001,
            direction="BUY",
        )
        assert ok is True


class TestEma100ActiveZoneLogic:
    """Case 2: week_ema100_filter_enabled=True -> zone + TP-floor active."""

    def test_safe_zone_no_reduction(self, fn_and_log):
        fn, _, _ = fn_and_log
        ok, tp_pips, reason, lot_mult, tp_mult = _call(
            fn,
            weekly_ema100=1.1200,
            entry_price=1.1100,
            pip_value=0.0001,
            ema100_buffer_pips=30,
        )
        dist_pips = abs(1.1100 - 1.1200) / 0.0001
        assert abs(dist_pips - 100.0) < 1e-6
        assert ok is True
        assert lot_mult == 1.0
        assert tp_mult == 1.0
        assert "TP=" in reason

    def test_buffer_zone_applies_reduction(self, fn_and_log):
        fn, _, _ = fn_and_log
        ok, tp_pips, reason, lot_mult, tp_mult = _call(
            fn,
            weekly_ema100=1.1100,
            entry_price=1.1105,
            pip_value=0.0001,
            ema100_buffer_pips=30,
        )
        dist_pips = abs(1.1105 - 1.1100) / 0.0001
        assert abs(dist_pips - 5.0) < 1e-6
        assert ok is True
        assert lot_mult == 0.5
        assert tp_mult == 0.8
        expected_base_tp = 50 * 2.5
        assert abs(tp_pips - expected_base_tp * 0.8) < 1e-6

    def test_wait_blocks_buy_below_ema(self, fn_and_log):
        fn, _, _ = fn_and_log
        ok, tp, reason, lot_mult, tp_mult = _call(
            fn,
            direction="BUY",
            weekly_ema100=1.1120,
            entry_price=1.1100,
            pip_value=0.0001,
            ema100_buffer_pips=30,
        )
        assert ok is False
        assert "WAIT_ABOVE_WEEKLY_EMA100" in reason
        assert lot_mult == 1.0
        assert tp_mult == 1.0

    def test_wait_blocks_sell_above_ema(self, fn_and_log):
        fn, _, _ = fn_and_log
        ok, tp, reason, lot_mult, tp_mult = _call(
            fn,
            direction="SELL",
            weekly_ema100=1.1100,
            entry_price=1.1120,
            pip_value=0.0001,
            ema100_buffer_pips=30,
            df=_make_df(trend="down"),
            ema_cross_filter=False,
        )
        assert ok is False
        assert "WAIT_BELOW_WEEKLY_EMA100" in reason

    def test_tp_floor_uses_tp_floor_pips_separate_from_buffer(self, fn_and_log):
        """TP-floor must respect ema100_tp_floor_pips independently of
        ema100_buffer_pips."""
        fn, _, _ = fn_and_log
        _, tp_loose_buf, _, _, _ = _call(
            fn,
            weekly_ema100=1.1200,
            entry_price=1.1100,
            pip_value=0.0001,
            ema100_buffer_pips=30,
            ema100_tp_floor_pips=100,
            mc_pct_up=60.0,
            direction="BUY",
        )
        _, tp_tight_buf, _, _, _ = _call(
            fn,
            weekly_ema100=1.1200,
            entry_price=1.1100,
            pip_value=0.0001,
            ema100_buffer_pips=10,
            ema100_tp_floor_pips=30,
            mc_pct_up=60.0,
            direction="BUY",
        )
        assert tp_loose_buf > tp_tight_buf
        assert tp_loose_buf >= 100.0

    def test_buffer_pips_drives_zone_not_tp_floor(self, fn_and_log):
        """ema100_buffer_pips must influence ZONE classification (SAFE/BUFFER/WAIT),
        NOT the TP-floor threshold."""
        fn, _, _ = fn_and_log
        ok_buf, _, _, lot_buf, _ = _call(
            fn,
            weekly_ema100=1.1100,
            entry_price=1.1103,
            pip_value=0.0001,
            ema100_buffer_pips=5,
            ema100_tp_floor_pips=50,
        )
        assert ok_buf is True
        assert lot_buf == 0.5

        ok_safe, _, _, lot_safe, _ = _call(
            fn,
            weekly_ema100=1.1100,
            entry_price=1.1103,
            pip_value=0.0001,
            ema100_buffer_pips=1,
            ema100_tp_floor_pips=50,
        )
        assert ok_safe is True
        assert lot_safe == 1.0


class TestEma100FailOpen:
    """Case 3: week_ema100_filter_enabled=True, weekly_ema100=None.
    Preserve fail-open — do NOT reject merely because EMA100 unavailable."""

    def test_none_ema100_allows_entry(self, fn_and_log):
        fn, _, _ = fn_and_log
        ok, tp_pips, reason, lot_mult, tp_mult = _call(
            fn,
            weekly_ema100=None,
            week_ema100_filter_enabled=True,
        )
        assert ok is True

    def test_none_ema100_default_multipliers(self, fn_and_log):
        fn, _, _ = fn_and_log
        _, _, _, lot_mult, tp_mult = _call(
            fn,
            weekly_ema100=None,
            week_ema100_filter_enabled=True,
        )
        assert lot_mult == 1.0
        assert tp_mult == 1.0

    def test_none_ema100_no_tp_floor_applied(self, fn_and_log):
        """TP must be the pre-EMA calculated value (base_tp_pips * mult),
        NOT inflated by any floor."""
        fn, _, _ = fn_and_log
        _, tp_pips, _, _, _ = _call(
            fn,
            weekly_ema100=None,
            week_ema100_filter_enabled=True,
            mc_pct_up=70.0,
        )
        expected = 50 * 2.5
        assert abs(tp_pips - expected) < 1e-6

    def test_none_ema100_no_zone_reduction(self, fn_and_log):
        fn, _, _ = fn_and_log
        _, _, _, lot_mult, tp_mult = _call(
            fn,
            weekly_ema100=None,
            week_ema100_filter_enabled=True,
            mc_pct_up=70.0,
        )
        assert lot_mult == 1.0
        assert tp_mult == 1.0


class TestEma100FailClosedGateNotImplemented:
    """Safety net: confirm we did NOT accidentally implement fail-closed.

    The task explicitly forbids fail-closed behavior for this patch.
    These tests document that contract and will alert if someone later
    adds fail-closed logic.
    """

    def test_disabled_does_not_turn_into_fail_closed(self, fn_and_log):
        fn, _, _ = fn_and_log
        ok, _, _, _, _ = _call(
            fn,
            week_ema100_filter_enabled=False,
            weekly_ema100=1.1100,
            pip_value=0.0001,
        )
        assert ok is True

    def test_enabled_with_none_does_not_fail_closed(self, fn_and_log):
        fn, _, _ = fn_and_log
        ok, _, _, _, _ = _call(
            fn,
            week_ema100_filter_enabled=True,
            weekly_ema100=None,
        )
        assert ok is True