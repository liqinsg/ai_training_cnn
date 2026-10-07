"""
DRY_RUN write-suppression contract (v6.8.3.6).

Original design contract for dry-run:
  1) run the FULL pipeline end-to-end (reads + all evaluations), and
  2) skip every mutating OANDA op — open / close / SL update / TP update,
  3) while read-only get-info calls keep working.

Before the fix only the ENTRY path was gated (and on the wrong flag,
LIVE_MODE); close_position was called without dry_run and
DynamicPositionManager issued TradeCRCDO writes unconditionally — so a
"--live --dry-run observer" run could still close real positions and move
real stops.

Part 1 unit-tests the functions with a FakeAPI that records every endpoint,
so any write attempt fails the assertion instead of reaching the network.
Part 2 checks the shipped fx_trade_bot_v683.py wiring via AST (same style as
tests/test_scoring_log_guard.py): the gate flag must reach every call site.

Run:  python -m pytest tests/test_dry_run_gate.py -q
"""

import ast
from pathlib import Path

from fx_trade_bot_utils import (
    DynamicPositionManager,
    close_position,
    update_order_tp,
)

BASE_DIR = Path(__file__).resolve().parent.parent
BOT = BASE_DIR / "fx_trade_bot_v683.py"

OPEN_POSITION = {"position": {"long": {"units": "1000"}, "short": {"units": "0"}}}
EMPTY_POSITION = {"position": {"long": {"units": "0"}, "short": {"units": "0"}}}


class FakeAPI:
    """Records endpoint class names; returns canned responses, never network."""

    def __init__(self, position=OPEN_POSITION):
        self.position = position
        self.calls: list[str] = []

    def request(self, endpoint):
        name = type(endpoint).__name__
        self.calls.append(name)
        if name == "PositionDetails":
            return self.position
        if name == "OrderCreate":
            return {"orderFillTransaction": {"price": "1.10000", "id": "1"}}
        if name == "TradeCRCDO":
            return {"takeProfitOrderTransaction": {"id": "2"}}
        raise AssertionError(f"unexpected endpoint: {name}")


# ── 1) close_position ──────────────────────────────────────────────────────

def test_close_position_dry_run_is_read_only():
    api = FakeAPI()
    assert close_position(api, "ACC", "EURJPY=X", dry_run=True) is True
    assert api.calls == ["PositionDetails"]  # read allowed, no OrderCreate


def test_close_position_dry_run_with_no_position_still_read_only():
    api = FakeAPI(position=EMPTY_POSITION)
    assert close_position(api, "ACC", "EURJPY=X", dry_run=True) is True
    assert api.calls == ["PositionDetails"]


def test_close_position_live_sends_ordercreate():
    api = FakeAPI()
    assert close_position(api, "ACC", "EURJPY=X", dry_run=False) is True
    assert "OrderCreate" in api.calls


# ── 2) DynamicPositionManager — BE / Trailing SL writes ────────────────────

def test_sl_update_dry_run_short_circuits():
    api = FakeAPI()
    mgr = DynamicPositionManager(api, "ACC", "15m", dry_run=True)
    # returns True (logical "handled") so the caller reports with DRY-RUN wording
    assert mgr._update_trade_sl("123", 110.123, 3) is True
    assert api.calls == []


def test_sl_update_live_sends_write():
    api = FakeAPI()
    mgr = DynamicPositionManager(api, "ACC", "15m", dry_run=False)
    assert mgr._update_trade_sl("123", 110.123, 3) is True
    assert api.calls == ["TradeCRCDO"]


def test_dynamic_manager_defaults_to_live_behaviour():
    # backward compat: no dry_run kwarg → writes still happen (old callers)
    api = FakeAPI()
    mgr = DynamicPositionManager(api, "ACC", "15m")
    assert mgr.dry_run is False
    mgr._update_trade_sl("123", 110.123, 3)
    assert api.calls == ["TradeCRCDO"]

# ── 3) update_order_tp — dynamic TP writes ─────────────────────────────────

def test_tp_update_dry_run_short_circuits():
    api = FakeAPI()
    res = update_order_tp(api, "ACC", "123", "EURUSD=X", 1.12345, dry_run=True)
    assert res["status"] == "DRY_RUN"
    assert res["ok"] is True
    assert api.calls == []


def test_tp_update_live_sends_write():
    api = FakeAPI()
    res = update_order_tp(api, "ACC", "123", "EURUSD=X", 1.12345, dry_run=False)
    assert res["ok"] is True
    assert api.calls == ["TradeCRCDO"]


# ── 4) Wiring in the shipped bot (AST — guards against regression) ─────────

def _tree():
    return ast.parse(BOT.read_text(encoding="utf-8"))


def _calls(tree, func_name):
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            name = node.func.attr
        else:
            continue
        if name == func_name:
            out.append(node)
    return out


def _kw(call, key):
    for kw in call.keywords:
        if kw.arg == key:
            return kw.value
    return None


def test_entry_call_wires_dry_run_mode():
    calls = _calls(_tree(), "open_oanda_order")
    assert calls, "open_oanda_order call site not found"
    for call in calls:
        val = _kw(call, "dry_run")
        assert val is not None, "open_oanda_order missing dry_run kwarg"
        assert isinstance(val, ast.Name) and val.id == "DRY_RUN_MODE"


def test_close_wrap_wires_dry_run_mode():
    calls = _calls(_tree(), "close_position")
    assert calls, "close_position call site not found"
    for call in calls:
        val = _kw(call, "dry_run")
        assert val is not None, "close_position missing dry_run kwarg"
        assert isinstance(val, ast.Name) and val.id == "DRY_RUN_MODE"


def test_dynamic_position_manager_wires_dry_run_mode():
    calls = _calls(_tree(), "DynamicPositionManager")
    assert calls, "DynamicPositionManager call site not found"
    for call in calls:
        val = _kw(call, "dry_run")
        assert val is not None, "DynamicPositionManager missing dry_run kwarg"
        assert isinstance(val, ast.Name) and val.id == "DRY_RUN_MODE"


def test_entry_gate_tested_on_dry_run_mode_not_live_mode():
    """The [DRY-RUN] SIGNAL branch must be guarded by DRY_RUN_MODE.

    v6.8.3.6 regression guard: it used to be `if not LIVE_MODE:`, which
    silently ignored run.env DRY_RUN entirely."""
    tree = _tree()
    found = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        body_src = " ".join(
            n.value
            for n in ast.walk(node)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        )
        if "[DRY-RUN] SIGNAL" in body_src:
            found = True
            test_src = ast.dump(node.test)
            assert "DRY_RUN_MODE" in test_src, "entry gate must test DRY_RUN_MODE"
            assert "LIVE_MODE" not in test_src, "entry gate must not test LIVE_MODE"
    assert found, "[DRY-RUN] SIGNAL branch not found"

