"""动态 MAX_OPEN（波动率档驱动）回归测试。"""

import pytest

from utils import wide_range_sizing as wrs


@pytest.mark.parametrize(
    ("base", "tier", "expected"),
    [
        (6, "wide", 4),
        (6, "extreme", 4),
        (6, "normal", 6),
        (6, "narrow", 6),
        (6, "unknown", 6),
        (3, "wide", 1),   # base - 2 = 1 → 地板 1（MIN_OPEN=1）
        (2, "wide", 1),   # 地板保护
        (1, "wide", 1),   # 上限本身为 1
        (8, "wide", 6),
    ],
)
def test_dynamic_max_open_matrix(base, tier, expected):
    assert wrs.dynamic_max_open(base, tier) == expected


def test_portfolio_volatility_tier_uses_median(monkeypatch):
    values = {"A": 0.5, "B": 0.6, "C": 1.4, "D": 1.5, "E": 1.6}
    monkeypatch.setattr(
        wrs, "compute_atr_ratio", lambda inst: {"atr_pct": values.get(inst)}
    )
    rec = wrs.portfolio_volatility_tier(list(values))
    # 中位数 1.4 → wide
    assert rec["tier"] == "wide"
    assert rec["atr_pct"] == 1.4
    assert rec["n_instruments"] == 5


def test_portfolio_volatility_tier_failclosed_when_too_few(monkeypatch):
    monkeypatch.setattr(wrs, "compute_atr_ratio", lambda inst: {"atr_pct": None})
    rec = wrs.portfolio_volatility_tier(["A", "B"])
    assert rec["tier"] == "unknown"
    assert rec["atr_pct"] is None
    assert rec["n_instruments"] == 0


def test_dynamic_max_open_failclosed_unknown_keeps_base():
    assert wrs.dynamic_max_open(6, "unknown") == 6
