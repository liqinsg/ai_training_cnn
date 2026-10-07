"""
data_guard.py — 数据边界保护单元测试。

覆盖：
  * MIN_REQUIRED_BARS 常量与可配置性
  * 标准日志格式「数据不足：需要 N 根，实际只有 M 根 → 跳过」
  * get_safe_series 的 None / 缺列 / 全空 / 正常 四条分支
  * safe_last / safe_iloc / safe_tail / safe_last_row 的越界不抛异常
  * 典型崩溃场景：`.iloc[-1]` 空表、`.iloc[-2]` 只有 1 行、`.iloc[-lookback]` 超长回退

无网络、无 OANDA 调用、不下单。
Run:  python -m pytest tests/test_data_guard.py -q
"""

import ast
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import data_guard
from data_guard import (
    DEFAULT_MIN_REQUIRED_BARS,
    MIN_REQUIRED_BARS,
    get_safe_series,
    has_min_bars,
    insufficient_bars,
    safe_iloc,
    safe_last,
    safe_last_row,
    safe_tail,
    to_float,
)


def _df(n, col="Close"):
    return pd.DataFrame({col: np.arange(float(n))})


# ── 1) 常量 ──────────────────────────────────────────────────────────────────

def test_default_min_required_bars_is_200():
    assert DEFAULT_MIN_REQUIRED_BARS == 200


def test_effective_min_required_bars_is_configurable_and_valid():
    # 运行环境可用 MIN_REQUIRED_BARS 覆盖，但必须是 ≥1 的整数
    assert isinstance(MIN_REQUIRED_BARS, int)
    assert MIN_REQUIRED_BARS >= 1


def test_env_int_parsing():
    assert data_guard._env_int("DEFINITELY_NOT_SET_XYZ", 200) == 200
    import os
    os.environ["MIN_REQUIRED_BARS_TEST"] = "150"
    assert data_guard._env_int("MIN_REQUIRED_BARS_TEST", 200) == 150
    os.environ["MIN_REQUIRED_BARS_TEST"] = "not-a-number"
    assert data_guard._env_int("MIN_REQUIRED_BARS_TEST", 200) == 200
    os.environ["MIN_REQUIRED_BARS_TEST"] = "0"
    assert data_guard._env_int("MIN_REQUIRED_BARS_TEST", 200) == 200
    del os.environ["MIN_REQUIRED_BARS_TEST"]


# ── 2) 标准日志格式 ──────────────────────────────────────────────────────────

def test_insufficient_bars_logs_required_format(caplog):
    with caplog.at_level(logging.WARNING, logger="data_guard"):
        hit = insufficient_bars(200, 10, "EURJPY=X")
    assert hit is True
    assert "数据不足：需要 200 根，实际只有 10 根 → 跳过" in caplog.text
    assert "EURJPY=X" in caplog.text


def test_insufficient_bars_silent_when_enough(caplog):
    with caplog.at_level(logging.WARNING, logger="data_guard"):
        assert insufficient_bars(200, 200) is False
    assert "数据不足" not in caplog.text


def test_has_min_bars_handles_none(caplog):
    with caplog.at_level(logging.WARNING, logger="data_guard"):
        assert has_min_bars(None) is False
    assert "数据不足：需要 200 根，实际只有 0 根 → 跳过" in caplog.text


# ── 3) get_safe_series ───────────────────────────────────────────────────────

def test_get_safe_series_returns_none_when_too_short(caplog):
    with caplog.at_level(logging.WARNING, logger="data_guard"):
        out = get_safe_series(_df(10), "Close")
    assert out is None
    assert "数据不足：需要 200 根，实际只有 10 根 → 跳过" in caplog.text


def test_get_safe_series_none_dataframe():
    assert get_safe_series(None, "Close") is None


def test_get_safe_series_missing_column(caplog):
    with caplog.at_level(logging.WARNING, logger="data_guard"):
        assert get_safe_series(_df(300), "Volume") is None
    assert "字段缺失" in caplog.text


def test_get_safe_series_all_nan_returns_none():
    df = _df(300)
    df["Close"] = np.nan
    assert get_safe_series(df, "Close") is None


def test_get_safe_series_returns_series_when_healthy():
    out = get_safe_series(_df(300), "Close")
    assert isinstance(out, pd.Series)
    assert len(out) == 300


def test_get_safe_series_min_bars_override():
    # min_bars 参数允许调用点使用比 MIN_REQUIRED_BARS 更紧的阈值
    assert get_safe_series(_df(10), "Close", min_bars=5) is not None
    assert get_safe_series(_df(10), "Close", min_bars=50) is None


def test_get_safe_series_multiindex_columns():
    cols = pd.MultiIndex.from_product([["Close", "High"], ["EURUSD=X"]])
    df = pd.DataFrame(np.arange(600.0).reshape(300, 2), columns=cols)
    out = get_safe_series(df, "Close")
    assert isinstance(out, pd.Series)
    assert len(out) == 300

# ── 4) 安全取值封装（越界不抛异常） ──────────────────────────────────────────

def test_safe_last_on_empty_series_returns_default(caplog):
    empty = pd.Series(dtype=float)
    with caplog.at_level(logging.WARNING, logger="data_guard"):
        assert safe_last(empty, "DEFAULT") == "DEFAULT"
    assert "数据不足：需要 1 根，实际只有 0 根 → 跳过" in caplog.text


def test_safe_last_returns_value_when_present():
    s = pd.Series([1.1, 2.2, 3.3])
    assert safe_last(s) == 3.3


def test_safe_last_on_none():
    assert safe_last(None, -1) == -1


def test_safe_iloc_returns_default_when_lookback_out_of_range(caplog):
    """`series.iloc[-50]` 只有 3 根 → 不崩溃、不静默换值，返回 default。"""
    s = pd.Series([10.0, 20.0, 30.0])
    with caplog.at_level(logging.WARNING, logger="data_guard"):
        assert safe_iloc(s, -50, "DEF") == "DEF"
    assert "数据不足：需要 50 根，实际只有 3 根 → 跳过" in caplog.text
    # 数据充足时行为与原实现完全一致
    assert safe_iloc(s, -2) == 20.0
    assert safe_iloc(s, -1) == 30.0


def test_safe_iloc_on_empty_returns_default():
    assert safe_iloc(pd.Series(dtype=float), -5, "DEF") == "DEF"


def test_safe_iloc_positive_out_of_range_returns_default():
    s = pd.Series([1.0, 2.0])
    assert safe_iloc(s, 99, "DEF") == "DEF"
    assert safe_iloc(s, 1) == 2.0


def test_safe_tail_clamps_to_available_length():
    """经典错误：`series.iloc[-50:]` 范围硬写 —— 切片虽不抛错，但会静默给错长度。"""
    s = pd.Series(range(8))
    assert len(safe_tail(s, 50)) == 8
    assert len(safe_tail(s, 3)) == 3
    assert len(safe_tail(s, 1)) == 1


def test_safe_tail_on_empty_does_not_raise(caplog):
    empty = pd.Series(dtype=float)
    with caplog.at_level(logging.WARNING, logger="data_guard"):
        out = safe_tail(empty, 5)
    assert len(out) == 0


def test_safe_last_row_on_empty_dataframe():
    empty = pd.DataFrame({"Close": []})
    assert safe_last_row(empty, "DEF") == "DEF"


def test_safe_last_row_returns_row_when_present():
    df = _df(5)
    row = safe_last_row(df)
    assert row["Close"] == 4.0


def test_classic_single_positional_indexer_crash_is_gone():
    """重现原始报错：空 DataFrame 上 `.iloc[-1]`。"""
    empty = pd.DataFrame({"Close": []})
    with pytest.raises(IndexError):
        empty.iloc[-1]                     # 原始代码确实会崩
    assert safe_last_row(empty, None) is None          # 加保护后不崩


def test_classic_iloc_minus_two_on_single_row():
    """重现原始报错：只有 1 行时 `.iloc[-2]`（indicator_provider 的 previous_high）。"""
    one = pd.Series([1.0])
    with pytest.raises(IndexError):
        one.iloc[-2]
    assert safe_iloc(one, -2, "DEF") == "DEF"


# ── 5) 数值兜底 ──────────────────────────────────────────────────────────────

def test_to_float_never_raises():
    assert to_float(None, 0.0) == 0.0
    assert to_float(float("nan"), -1.0) == -1.0
    assert to_float("1.25") == 1.25
    assert to_float("abc", 0.0) == 0.0
    assert to_float(3, 0.0) == 3.0


# ── 7) 业务接入点行为（AST 抽取，与 tests_offline 同套路，避免 import 整个 bot） ──

def _extract_bot_functions(*names):
    """从 fx_trade_bot_v683.py 抽取指定函数，用最小桩执行。"""
    bot = Path(__file__).resolve().parent.parent / "fx_trade_bot_v683.py"
    tree = ast.parse(bot.read_text(encoding="utf-8"))
    mod = ast.Module(
        body=[
            n
            for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name in set(names)
        ],
        type_ignores=[],
    )
    ns = {"pd": pd, "np": np, "logger": logging.getLogger("data-guard-test")}
    exec(compile(mod, str(bot), "exec"), ns)
    return ns


def test_calculate_ema_slope_survives_empty_and_short_series():
    ns = _extract_bot_functions("calculate_ema_slope")
    fn = ns["calculate_ema_slope"]
    # ① 空序列 —— 原实现 `ema_series.iloc[-1]` 直接 IndexError
    assert fn(pd.Series(dtype=float), 5) == (None, None)
    # ② 比 lookback 短 —— 原实现 `series.iloc[-50]` 越界
    slope, ema = fn(pd.Series([1.0, 2.0]), 50)
    assert ema == 2.0
    assert slope is not None
    # ③ 数据充足时结果与原实现逐位一致（lookback=2 → 取倒数第 2 根）
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    slope, ema = fn(s, 2)
    assert ema == 5.0
    assert slope == pytest.approx((5.0 - 4.0) / 4.0)     # 原实现：iloc[-1] 与 iloc[-2]


def test_evaluate_trend_and_tp_returns_gracefully_on_thin_data():
    """数据不足 → 返回 (False, 0.0, 原因)，不抛异常、不中断整轮。"""
    ns = _extract_bot_functions(
        "evaluate_trend_and_tp", "calculate_ema", "calculate_ema_slope",
        "resolve_min_slope",
    )
    ns["TREND_TP_CONFIG"] = {
        "base_tp_pips": 30,
        "mc_strong_threshold": 0.75,
        "profile2": {"ema_period": 10, "slope_lookback": 5, "min_slope": 0.001},
    }
    ns["cfg_bot"] = lambda name, default: {"TREND_FILTER_ENABLED": True}.get(name, default)
    ns["SLOPE_DIAG"] = False
    ns["SLOPE_DIAG_BASELINE"] = 0.001
    ns["PROFILE_NAME"] = "profile2"
    ns["PROFILE_LABEL"] = "PROFILE2"
    ns["MIN_REQUIRED_BARS"] = MIN_REQUIRED_BARS
    ns["get_safe_series"] = get_safe_series

    fn = ns["evaluate_trend_and_tp"]
    # 需要 max(10, 5) + 1 = 16 根，这里只有 3 根
    thin = pd.DataFrame({"Close": [1.0] * 3})
    ok, tp_pips, reason = fn(
        "profile2", "BUY", 50.0, 1.0, 0.0001, thin, None, timeframe="15m"
    )
    assert ok is False
    assert tp_pips == 0.0
    assert "数据不足" in reason

    # 数据充足时不再被保护层拦截（会继续走到趋势/TP 判定）
    good = pd.DataFrame({"Close": np.linspace(1.2, 1.19, 120)})
    ok2, tp2, reason2 = fn(
        "profile2", "SELL", 50.0, 1.195, 0.0001, good, None, timeframe="15m"
    )
    assert "数据不足" not in reason2


# ── 6) 关键接入点：模块确实被业务代码引用 ────────────────────────────────────

def test_bot_wires_data_guard():
    from pathlib import Path
    bot = Path(__file__).resolve().parent.parent / "fx_trade_bot_v683.py"
    src = bot.read_text(encoding="utf-8")
    assert "from data_guard import" in src
    assert "MIN_REQUIRED_BARS" in src

