"""
Unified profile registry (v6.8.4) — config_bot.py merges config_bot_profile2/3.py.

Guards the two things this merge could silently break:
  1. the PROFILES contract (weights / whitelist / limits / D-GATE)
  2. byte-identical resolution of every value the old profile modules supplied,
     so scoring, filters and position limits do not drift.

Also a regression guard for the "2H1" → 2 confirm-bar parse: joining all digits
turns it into 21, which silently changes D-GATE semantics (seen as Tail(21)).

No network, no OANDA calls, no orders.

Run:  python -m pytest tests/test_unified_profiles.py -q
"""

import importlib
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
BOT = BASE_DIR / "fx_trade_bot_v683.py"


@pytest.fixture(scope="module")
def cb():
    return importlib.import_module("config_bot")


# ── 1) PROFILES contract ─────────────────────────────────────────────────────

def test_profiles_keys(cb):
    assert sorted(cb.PROFILES) == [2, 3]
    required = {
        "NAME", "WEIGHTS", "WHITELIST", "MAX_OPEN", "MAX_ENTRIES_THIS_RUN",
        "MIN_CONVICTION", "MIN_GAP", "D_GATE_ENABLED", "D_GATE_BUFFER_PCT",
        "D_GATE_SHADOW", "D_GATE_CONFIRM",
    }
    for pid in (2, 3):
        assert required <= set(cb.PROFILES[pid]), f"profile {pid} missing keys"


def test_d_gate_policy_per_profile(cb):
    """Spec: P2 gate fully off, P3 active @ 0.15% buffer in shadow mode."""
    assert cb.PROFILES[2]["D_GATE_ENABLED"] is False
    assert cb.PROFILES[3]["D_GATE_ENABLED"] is True
    for pid in (2, 3):
        p = cb.PROFILES[pid]
        assert p["D_GATE_BUFFER_PCT"] == 0.15
        assert p["D_GATE_SHADOW"] is True
        assert p["D_GATE_CONFIRM"] == "2H1"


def test_weights_and_limits(cb):
    for pid in (2, 3):
        p = cb.PROFILES[pid]
        assert p["WEIGHTS"] == {"S": 0.40, "R": 0.15, "A": 0.15, "X": 0.20, "M": 0.10}
        assert abs(sum(p["WEIGHTS"].values()) - 1.0) < 1e-9
        assert p["MAX_OPEN"] == 3
        assert p["MAX_ENTRIES_THIS_RUN"] == 3
        assert p["MIN_CONVICTION"] == 45.0
        assert p["MIN_GAP"] == 0.25


def test_get_profile_validation(cb):
    assert cb.get_profile(2)["NAME"] == "Profile2"
    assert cb.get_profile("3")["NAME"] == "Profile3"
    with pytest.raises(ValueError):
        cb.get_profile(9)


def test_weights_base_is_the_banner_basis_not_the_scoring_weights(cb):
    """config_bot's own defaults stay 0.50/0.15/0.15/0.12/0.08 (validation banner),
    while scoring uses PROFILES weights — the two must remain distinct."""
    assert cb.WEIGHTS_BASE == {"S": 0.50, "R": 0.15, "A": 0.15, "X": 0.12, "M": 0.08}
    assert abs(sum(cb.WEIGHTS_BASE.values()) - 1.0) < 1e-9
    assert cb.WEIGHTS_BASE != cb.PROFILES[2]["WEIGHTS"]

# ── 2) Preserved runtime values (formerly in the profile modules) ─────────────

@pytest.mark.parametrize("pid", [2, 3])
def test_shared_profile_values_preserved(cb, pid):
    cfg = cb.build_profile_cfg(pid)
    assert cfg.MAX_OPEN_POSITIONS == 3
    assert cfg.MIN_CONVICTION_SCORE == 45.0
    assert cfg.MIN_STRENGTH_GAP == 0.25
    assert cfg.USE_TOP_PAIRS_ONLY is True
    assert cfg.TOP_N_CURRENCIES == 3
    assert cfg.TOP_PAIRS_MIN_GAP == 0.50
    assert cfg.TRAIL_ATR_MULT == 2.0
    assert cfg.MAX_HOLD_BARS == 48
    assert cfg.YF_INTERVAL == "4h"
    assert cfg.WEIGHT_STRENGTH == 0.40
    assert cfg.WEIGHT_RSI == 0.15
    assert cfg.WEIGHT_ADX == 0.15
    assert cfg.WEIGHT_XGB == 0.20
    assert cfg.WEIGHT_MC == 0.10
    assert cfg.WEIGHT_XGBOOST == cfg.WEIGHT_XGB     # legacy alias stays in sync
    assert cfg.OANDA_ACCOUNT_ID


@pytest.mark.parametrize("pid", [2, 3])
def test_whitelists_stay_disjoint_and_cover_all_eight(cb, pid):
    mine = set(cb.PROFILES[pid]["WHITELIST"])
    other = set(cb.PROFILES[3 if pid == 2 else 2]["WHITELIST"])
    assert not (mine & other), f"overlap {sorted(mine & other)} trips the safety lock"
    assert len(mine | other) == 8


def test_profile_specific_behaviour_switches(cb):
    p2 = cb.build_profile_cfg(2)
    p3 = cb.build_profile_cfg(3)
    # Profile2 only
    assert p2.SL_PAIR_FLOOR_OVERRIDES == {"GBPJPY=X": 50}
    assert p2.TREND_FILTER_ENABLED is False
    assert not hasattr(p2, "SLOPE_DIAG")            # → cfg_bot default False
    # Profile3 only
    assert p3.SL_PAIR_FLOOR_OVERRIDES == {}
    assert p3.SLOPE_DIAG is True
    assert p3.TREND_FILTER_ENABLED is True          # inherits config_bot


# ── 3) D-GATE confirm-bar parsing (regression) ───────────────────────────────

@pytest.mark.parametrize("pid", [2, 3])
def test_d_gate_confirm_bars_parses_to_two_not_twenty_one(cb, pid):
    cfg = cb.build_profile_cfg(pid)
    assert cfg.D_GATE_CONFIRM_BARS == 2, (
        "join-all-digits turns '2H1' into 21 → D-GATE would require 21 confirming "
        "H1 bars instead of 2 (surfaced as Tail(21) in the DIAG line)"
    )
    assert cfg.D_GATE_MIN_BUFFER_PCT == 0.0015      # 0.15%


# ── 4) Bot wiring ────────────────────────────────────────────────────────────

def _src():
    return BOT.read_text(encoding="utf-8")


def test_bot_no_longer_imports_the_old_profile_modules():
    src = _src()
    assert "PROFILE_MODULE" not in src
    assert "importlib.import_module(PROFILE_MODULE)" not in src
    for needle in ("import config_bot_profile2", "import config_bot_profile3"):
        assert needle not in src


def test_bot_uses_unified_loader_and_disabled_gate():
    src = _src()
    assert "config_bot.get_profile(profile_id)" in src
    assert "config_bot.build_profile_cfg(profile_id)" in src
    assert "D-GATE: DISABLED — skipped entirely per profile config" in src
    assert "SKIP_DGATE = not D_GATE_ENABLED" in src

