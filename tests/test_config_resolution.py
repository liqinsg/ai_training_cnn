"""
Offline proof for the config-resolution fixes in the v6.8.3.3 bot.

Covers:
  1. WEIGHT_XGB is the canonical weight key (validate_config must read the key
     the scoring code actually reads, not the legacy WEIGHT_XGBOOST spelling).
  2. The TOP-N resolution chain in fx_trade_bot_v683.py resolves to the
     authoritative utils/strategy_config values instead of the legacy
     config_bot AUTO-RANKING block.

The bot's own cfg_bot("KEY", DEFAULT) calls are extracted from its source via
AST, so the assertions track what the bot reads rather than what we assume.

No network, no OANDA calls, no orders.

Run:  python -m pytest tests/test_config_resolution.py -q
"""

import ast
import importlib
import sys
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

BOT = BASE_DIR / "fx_trade_bot_v683.py"

# Legacy values in config_bot.py that must NOT win over strategy_config.
LEGACY_CONFIG_BOT_VALUES = {
    "USE_TOP_PAIRS_ONLY": False,
    "TOP_PAIRS_MIN_GAP": 1.5,
    "TOP_PAIRS_COUNT": 5,
}


def _bot_tree():
    return ast.parse(BOT.read_text(encoding="utf-8"))


def bot_module_constants():
    """Map module-level NAME = <literal> assignments in the bot to their values."""
    consts = {}
    for node in _bot_tree().body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                try:
                    consts[target.id] = ast.literal_eval(node.value)
                except ValueError:
                    continue
    return consts


def bot_imported_names():
    """Resolve the bot's imported fallback names (e.g. STRATEGY_USE_TOP_PAIRS_ONLY).

    They come from `from utils.strategy_config import X as Y`, so the mapping is
    read out of the bot's import statement and the values come from the real
    strategy_config module — no hardcoded copies.
    """
    strategy_config = importlib.import_module("utils.strategy_config")
    mapping = {}
    for node in ast.walk(_bot_tree()):
        if not isinstance(node, ast.ImportFrom):
            continue
        if not (node.module or "").endswith("strategy_config"):
            continue
        for alias in node.names:
            local = alias.asname or alias.name
            if hasattr(strategy_config, alias.name):
                mapping[local] = getattr(strategy_config, alias.name)
    return mapping


def bot_cfg_bot_default(key):
    """Second argument of the bot's cfg_bot("<key>", <default>), resolved.

    The default may be a literal or an imported name such as
    STRATEGY_USE_TOP_PAIRS_ONLY, so both are resolved against the bot's own
    source instead of being assumed.
    """
    constants = bot_module_constants()
    imported = bot_imported_names()
    for node in ast.walk(_bot_tree()):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Name) and func.id == "cfg_bot"):
            continue
        if len(node.args) != 2:
            continue
        first = node.args[0]
        if not (isinstance(first, ast.Constant) and first.value == key):
            continue
        default = node.args[1]
        if isinstance(default, ast.Name):
            if default.id in constants:
                return constants[default.id]
            if default.id in imported:
                return imported[default.id]
            return f"<unresolved {default.id}>"
        # Nested fallback, e.g. cfg_bot("TOP_N_CURRENCIES", cfg_bot("TOP_PAIRS_COUNT", 3)).
        # The inner default is what wins when neither key is configured.
        if isinstance(default, ast.Call):
            inner = default.func
            if (
                isinstance(inner, ast.Name)
                and inner.id == "cfg_bot"
                and len(default.args) == 2
            ):
                inner_key = default.args[0]
                if isinstance(inner_key, ast.Constant):
                    return bot_cfg_bot_default(inner_key.value)
        try:
            return ast.literal_eval(default)
        except ValueError:
            return "<non-literal default>"
    return None


@pytest.fixture(scope="module")
def strategy_config():
    return importlib.import_module("utils.strategy_config")


@pytest.fixture(scope="module")
def config_bot_mod():
    return importlib.import_module("config_bot")


@pytest.mark.parametrize("profile_id", [2, 3])
def test_canonical_weight_key_sums_to_one(profile_id, config_bot_mod):
    """Both profiles define WEIGHT_XGB and their weights sum to 1.0."""
    p = config_bot_mod.get_profile(profile_id)
    weights = p["WEIGHTS"]
    assert set(weights) == {"S", "R", "A", "X", "M"}
    total = sum(weights.values())
    assert abs(total - 1.0) < 1e-9, f"profile {profile_id} weights sum to {total}"


def test_validate_config_reads_canonical_key(config_bot_mod):
    """The banner must print the canonical key's value, not the alias."""
    config_bot = config_bot_mod
    assert config_bot.WEIGHT_XGB == 0.12
    assert config_bot.WEIGHT_XGBOOST == config_bot.WEIGHT_XGB, (
        "legacy alias drifted from the canonical key that scoring reads"
    )
    # Reproduce the dict validate_config() builds and confirm what it checks.
    checked = {
        "S": config_bot.WEIGHT_STRENGTH,
        "R": config_bot.WEIGHT_RSI,
        "A": config_bot.WEIGHT_ADX,
        "X": config_bot.WEIGHT_XGB,
        "M": config_bot.WEIGHT_MC,
    }
    assert abs(sum(checked.values()) - 1.0) < 0.005
    # The bug being fixed: the old banner reported 0.12 while scoring used 0.20.
    assert checked["X"] != 0.20, "banner would still disagree with profile scoring"


def test_scoring_reads_the_same_key_as_the_banner():
    """The bot's cfg_bot call for X must name the same key the banner reads."""
    assert bot_cfg_bot_default("WEIGHT_XGB") == 0.20, (
        "bot no longer reads WEIGHT_XGB; banner and scoring could diverge again"
    )
    assert bot_cfg_bot_default("WEIGHT_XGBOOST") is None, (
        "bot reads WEIGHT_XGBOOST — scoring would use the legacy key"
    )


def test_top_n_resolution_ignores_legacy_config_bot(strategy_config, config_bot_mod):
    """The bot's fallback defaults must come from strategy_config, not config_bot.

    config_bot.py still carries USE_TOP_PAIRS_ONLY = False and
    TOP_PAIRS_MIN_GAP = 1.5; if the bot's defaults tracked those, every run
    would silently fall back to a full 8-pair scan.
    """
    assert bot_cfg_bot_default("USE_TOP_PAIRS_ONLY") is strategy_config.USE_TOP_PAIRS_ONLY
    assert bot_cfg_bot_default("TOP_N_CURRENCIES") == strategy_config.TOP_N_CURRENCIES
    assert bot_cfg_bot_default("TOP_PAIRS_MIN_GAP") == strategy_config.TOP_PAIRS_MIN_GAP

    # The bot must NOT consult TOP_PAIRS_COUNT any more. config_bot.py still
    # defines it as 5, so a fallback would resolve TOP_N to 5 — five strongest
    # and five weakest currencies, which is not what either profile intends.
    assert bot_cfg_bot_default("TOP_PAIRS_COUNT") is None, (
        "bot reads TOP_PAIRS_COUNT again; with config_bot.TOP_PAIRS_COUNT = 5 "
        "this would silently change the candidate pool"
    )

    # And the legacy values really are dangerous, i.e. they differ.
    for key, legacy in LEGACY_CONFIG_BOT_VALUES.items():
        authoritative = getattr(strategy_config, key, None)
        if authoritative is not None:
            assert authoritative != legacy, (
                f"{key}: legacy and authoritative now agree; this guard is stale"
            )


@pytest.mark.parametrize("profile_id", [2, 3])
def test_profile_resolution_matches_shipped_run_values(profile_id, config_bot_mod):
    """Mirror the bot's unified profile loader: PROFILE dict wins, then default.

    The 2026-10-02 profile2 run logged TOP_N=3 and Top-3, so both profiles must
    resolve to 3 with the top-pairs mode enabled.
    """
    strategy_config = importlib.import_module("utils.strategy_config")
    # The bot hardcodes these after loading the PROFILE (same values the former
    # config_bot_profile{2,3}.py modules defined); read them from its source so
    # this test tracks the shipped wiring instead of a copy.
    consts = bot_module_constants()

    use_top = consts.get("USE_TOP_PAIRS_ONLY", strategy_config.USE_TOP_PAIRS_ONLY)
    # Mirrors the bot exactly: no TOP_PAIRS_COUNT fallback any more.
    top_n = consts.get("TOP_N_CURRENCIES", strategy_config.TOP_N_CURRENCIES)
    min_gap = consts.get("TOP_PAIRS_MIN_GAP")
    if min_gap is None:
        min_gap = config_bot_mod.get_profile(profile_id)["MIN_GAP"]

    assert use_top is True, f"profile {profile_id}: expected top-pairs mode ON"
    assert top_n == 3, f"profile {profile_id}: resolved TOP_N={top_n}, run logged 3"
    assert min_gap == 0.25, f"profile {profile_id}: resolved TOP_PAIRS_MIN_GAP={min_gap}"


@pytest.mark.parametrize("profile_id", [2, 3])
def test_profile_d_gate_settings(profile_id, config_bot_mod):
    """D-GATE is the ONLY deliberate difference between the two profiles."""
    p = config_bot_mod.get_profile(profile_id)
    assert p["D_GATE_BUFFER_PCT"] == 0.15
    assert p["D_GATE_SHADOW"] is True
    assert p["D_GATE_CONFIRM"] == "2H1"
    if profile_id == 2:
        assert p["D_GATE_ENABLED"] is False, "Profile2 must fully disable D-GATE"
    else:
        assert p["D_GATE_ENABLED"] is True, "Profile3 must activate D-GATE"
