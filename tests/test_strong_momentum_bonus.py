import pytest

from utils.prob_zone_sizing import (
    apply_strong_momentum_bonus,
    below_min_prob_factor,
    is_strong_momentum_regime,
    min_prob_factor_units,
    next_prob_rung_up,
    normalize_to_prob_factor,
    prob_tier_for_units,
)


@pytest.mark.parametrize(
    ("base_units", "minimum", "maximum", "expected"),
    [
        (1, 1, 16, 2),
        (2, 1, 16, 4),
        (1250, 1000, 20000, 2500),
        (10000, 1000, 20000, 20000),
    ],
)
def test_strong_momentum_doubles_positive_position_within_bounds(
    base_units, minimum, maximum, expected
):
    assert apply_strong_momentum_bonus(
        base_units,
        enabled=True,
        min_units=minimum,
        max_units=maximum,
    ) == expected


def test_strong_momentum_bonus_does_not_create_position_or_change_normal_sizes():
    kwargs = {"enabled": True, "min_units": 1000, "max_units": 20000}
    assert apply_strong_momentum_bonus(0, **kwargs) == 0
    assert (
        apply_strong_momentum_bonus(
            1250, enabled=False, min_units=1000, max_units=20000
        )
        == 1250
    )


@pytest.mark.parametrize(
    ("regime", "expected"),
    [
        ("strong_momentum", True),
        ("⚡ 15m STRONG MOMENTUM", True),
        ("MOMENTUM", True),
        ("NEUTRAL", False),
        ("🧬 FUSED | D:MOMENTUM W:NEUTRAL", False),
        (None, False),
    ],
)
def test_strong_momentum_regime_recognition(regime, expected):
    assert is_strong_momentum_regime(regime) is expected


def test_probability_factor_rungs_are_shared_by_normalization_and_pyramiding():
    assert normalize_to_prob_factor(9000, base_lot=10000, min_units=1000) == 5000
    assert normalize_to_prob_factor(2500, base_lot=10000, min_units=1000) == 2500
    assert min_prob_factor_units(10000) == 1250
    assert below_min_prob_factor(1249, 10000)
    assert not below_min_prob_factor(1250, 10000)
    assert next_prob_rung_up(2500, base_lot=10000, min_units=1000) == (5000, 2500)
    assert prob_tier_for_units(1250, 10000) == 1
    assert prob_tier_for_units(1, 4) == 1
