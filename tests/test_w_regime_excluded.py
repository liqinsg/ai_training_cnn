import ast
from pathlib import Path

from utils import prob_zone_sizing


ROOT = Path(__file__).resolve().parents[1]
BOT_PATH = ROOT / "fx_trade_bot_v685.py"


def test_w_regime_does_not_change_sizing_multiplier_but_d_regime_still_does():
    assert prob_zone_sizing._regime_mult(
        "STRONG MOMENTUM", 0.25
    ) == 1.0
    assert prob_zone_sizing._regime_mult(
        "NEUTRAL", 0.25
    ) == 0.25


def test_decision_regime_uses_d_label_and_never_falls_back_to_fused_w_label():
    select_d_regime = getattr(prob_zone_sizing, "d_regime_for_decision", None)
    assert callable(select_d_regime)

    assert select_d_regime(
        {
            "regime": "FUSED | D:NEUTRAL W:STRONG MOMENTUM",
            "regime_D": "NEUTRAL",
            "regime_W": "STRONG MOMENTUM",
        }
    ) == "NEUTRAL"
    assert select_d_regime(
        {
            "regime": "FUSED | D:STRONG MOMENTUM W:NEUTRAL",
            "regime_W": "NEUTRAL",
            "blend_complete": True,
        },
        fallback="FUSED | D:STRONG MOMENTUM W:NEUTRAL",
    ) == ""
    assert select_d_regime({"regime": "NEUTRAL"}) == "NEUTRAL"


def test_bot_uses_d_only_regime_for_scoring_and_momentum_bonus():
    tree = ast.parse(BOT_PATH.read_text(encoding="utf-8"))
    main = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "main"
    )
    assignments = {}
    for node in ast.walk(main):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assignments[target.id] = node.value

    assert "d_regime_for_decision" in ast.unparse(assignments["_regime_str"])
    d_label_source = ast.unparse(assignments["_d_label"])
    assert "d_regime_for_decision" in d_label_source
    assert "regime_W" not in d_label_source


def _load_fusion_sync():
    tree = ast.parse(BOT_PATH.read_text(encoding="utf-8"))
    names = {
        "_fuse_num",
        "_fuse_pair2",
        "_fuse_w_range",
        "_fuse_normalize",
        "_fuse_sync_derived_blocks",
    }
    body = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    body.extend(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name)
            and target.id in {
                "_FUSE_STATES",
                "_FUSE_PRIOR_GAMMA",
                "_FUSE_THRESHOLD_TAU",
                "_FUSE_MIN_WIDTH_PCT_GATE",
                "_FUSE_DEFAULT_W_RANGE",
                "_FUSE_W_RANGE_MAP",
            }
            for target in node.targets
        )
    )
    namespace = {}
    exec(compile(ast.Module(body=body, type_ignores=[]), str(BOT_PATH), "exec"), namespace)
    return namespace["_fuse_sync_derived_blocks"]


def _fusion_record(w_regime):
    return {
        "pair": "AUD_JPY",
        "regime": f"FUSED | D:STRONG MOMENTUM W:{w_regime}",
        "regime_D": "STRONG MOMENTUM",
        "regime_W": w_regime,
        "current_price": 100.0,
        "distribution": {
            "quantiles": {"0.05": 95.0, "0.50": 100.0, "0.95": 105.0},
            "min": 90.0,
            "max": 110.0,
            "mean": 100.0,
            "std": 3.0,
            "degenerate": False,
        },
        "prob_bands": {
            "bands": [
                {"price_lo": 90.0, "price_hi": 100.0},
                {"price_lo": 100.0, "price_hi": 110.0},
            ],
            "current": {"price_lo": 90.0, "price_hi": 100.0},
            "shape": {"quantiles": {"0.05": 95.0, "0.50": 100.0, "0.95": 105.0}},
            "degenerate": False,
        },
        "belief": {"threshold_tau": 0.55},
    }


def test_fused_belief_is_invariant_to_w_regime_when_d_regime_is_fixed():
    sync = _load_fusion_sync()
    neutral_w = _fusion_record("NEUTRAL")
    momentum_w = _fusion_record("STRONG MOMENTUM")

    assert sync(neutral_w, 50.0, 50.0, [90.0, 110.0], [92.0, 108.0])
    assert sync(momentum_w, 50.0, 50.0, [90.0, 110.0], [92.0, 108.0])
    assert neutral_w["belief"]["posterior"] == momentum_w["belief"]["posterior"]
