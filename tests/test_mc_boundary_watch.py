"""MC 概率带内部边界观察层回归测试（只观察 · 不改仓位）。"""

import json

import pandas as pd
import pytest

from utils import mc_boundary_watch as mbw


def _bands_5():
    """AUD/JPY 形态的 5 带样本（内部边界 Q20/Q40/Q60/Q80）。"""
    edges = [100.728, 104.040, 104.730, 105.348, 106.066, 124.251]
    tags = ["Q0-20", "Q20-40", "Q40-60", "Q60-80", "Q80-100"]
    return {
        "bands": [
            {"index": i, "tag": tags[i], "price_lo": edges[i], "price_hi": edges[i + 1]}
            for i in range(5)
        ],
        # 故意设置一个“错误”的静态 current，验证观察层不读取它
        "current": {"index": 0, "tag": "Q0-20", "price_lo": 0.0, "price_hi": 1.0},
    }


def test_extract_internal_boundaries_returns_four_shared_edges():
    bounds = mbw.extract_internal_boundaries(_bands_5())
    assert [label for label, _ in bounds] == ["Q20", "Q40", "Q60", "Q80"]
    assert [round(v, 3) for _, v in bounds] == [104.040, 104.730, 105.348, 106.066]


def test_band_tag_uses_bands_not_static_current():
    pb = _bands_5()
    # 105.496 落在 Q60-80，而非被静态 current 指向的 Q0-20
    assert mbw.band_tag_for_price(pb, 105.496) == "Q60-80"
    assert mbw.band_tag_for_price(pb, 99.0) == "OUT_OF_RANGE"
    assert mbw.band_tag_for_price(pb, None) == "UNKNOWN"


def test_detect_touch_and_cross_directions():
    boundaries = [("Q60", 105.348)]
    bars = [
        {"open_time": "t0", "high": 105.70, "low": 105.40, "close": 105.60},
        # 前收在边界上方、影线触及后收回 → touch / from_above
        {"open_time": "t1", "high": 105.70, "low": 105.10, "close": 105.60},
        # 前收在上方、收盘向下越界 → cross_down / from_above
        {"open_time": "t2", "high": 105.60, "low": 105.00, "close": 105.05},
        # 前收在下方、影线触及后收回 → touch / from_below
        {"open_time": "t3", "high": 105.50, "low": 105.00, "close": 105.10},
    ]
    events = mbw.detect_boundary_events(bars, boundaries)
    kinds = [(e["open_time"], e["kind"], e["direction"]) for e in events]
    assert kinds == [
        ("t1", "touch", "from_above"),
        ("t2", "cross_down", "from_above"),
        ("t3", "touch", "from_below"),
    ]


def test_detect_cross_up():
    boundaries = [("Q40", 104.730)]
    bars = [
        {"open_time": "t0", "high": 104.70, "low": 104.50, "close": 104.60},
        {"open_time": "t1", "high": 104.90, "low": 104.60, "close": 104.85},
    ]
    events = mbw.detect_boundary_events(bars, boundaries)
    assert len(events) == 1
    assert events[0]["kind"] == "cross_up"
    assert events[0]["direction"] == "from_below"


def test_first_bar_skipped_without_prev_close():
    boundaries = [("Q40", 104.730)]
    bars = [{"open_time": "t0", "high": 105.0, "low": 104.0, "close": 104.8}]
    assert mbw.detect_boundary_events(bars, boundaries) == []


def test_watch_dedupes_across_runs(tmp_path):
    pb = _bands_5()
    bars = [
        {"open_time": "2026-11-26T00:00:00+00:00", "high": 105.40, "low": 105.20, "close": 105.30},
        {"open_time": "2026-11-26T00:15:00+00:00", "high": 105.50, "low": 105.10, "close": 105.20},
    ]
    first = mbw.watch_mc_boundaries(
        "AUD_JPY", pb, bars, "batchA", current=105.496, logs_dir=tmp_path
    )
    assert first["current_band"] == "Q60-80"
    assert first["n_new"] == 1
    # 同一批次 / 同一根 K 线再跑 → 0 新增
    second = mbw.watch_mc_boundaries(
        "AUD_JPY", pb, bars, "batchA", current=105.496, logs_dir=tmp_path
    )
    assert second["n_new"] == 0
    # 新批次 → 视为新观察
    third = mbw.watch_mc_boundaries(
        "AUD_JPY", pb, bars, "batchB", current=105.496, logs_dir=tmp_path
    )
    assert third["n_new"] == 1

    files = list(tmp_path.glob("mc_boundary_watch_*.jsonl"))
    assert len(files) == 1
    rows = [json.loads(line) for line in files[0].read_text().splitlines() if line.strip()]
    assert len(rows) == 2
    assert all(row["applied"] is False for row in rows)
    assert all(row["boundary"] == "Q60" for row in rows)


def test_bars_from_dataframe_uses_closed_ohlc():
    idx = pd.DatetimeIndex(
        ["2026-11-26T00:00:00+00:00", "2026-11-26T00:15:00+00:00"]
    )
    df = pd.DataFrame(
        {"Open": [1.0, 1.1], "High": [1.2, 1.3], "Low": [0.9, 1.0], "Close": [1.1, 1.2]},
        index=idx,
    )
    bars = mbw.bars_from_dataframe(df)
    assert [b["high"] for b in bars] == [1.2, 1.3]
    assert bars[0]["open_time"].startswith("2026-11-26T00:00:00")


@pytest.mark.parametrize(
    ("prob_bands", "bars", "batch"),
    [
        (None, None, None),
        ({}, [], {}),
        ({"bands": "bad"}, [{"open_time": "t", "high": 1, "low": 0, "close": 0.5}], "b"),
    ],
)
def test_never_raises_on_bad_input(prob_bands, bars, batch):
    result = mbw.watch_mc_boundaries(
        "X_Y", prob_bands, bars or [], batch, current=1.0
    )
    assert isinstance(result, dict)
    assert "current_band" in result and "n_new" in result
