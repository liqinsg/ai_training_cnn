"""
Phase 3.2 — Feature Contract implementation tests (ml/feature_contract.py).

Covers the *proposed* Phase 3.2 Feature Contract implementation:
  * input contract (IC-06): whole-batch rejection semantics
  * deterministic, ordered schema (33 features)
  * warm-up indexing of the recursive primitives
  * Wilder/EMA primitives and the ADX break/reseed rule
  * fail-closed build (no silent fallback, NaN never filled)

This module is wired into the production runtime only behind the default-OFF
switch ``USE_FEATURE_CONTRACT_V2`` (L3, 2026-11-15); with the switch off the
shipped path is unchanged. These tests are offline and use no network, no OANDA
calls, and write nothing to production paths.

Run:  python -m pytest tests/test_feature_contract.py -q
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from ml import feature_contract as fc  # noqa: E402


# ── fixtures / helpers ──────────────────────────────────────────────────────

def _index(n):
    return pd.date_range("2026-01-05 00:00", periods=n, freq="15min", tz="UTC")


def _frame(n=80, seed=7):
    """A valid M15 candle batch: tz-aware UTC, positive, OHLC-consistent."""
    rng = np.random.default_rng(seed)
    close = 1.10 + np.cumsum(rng.normal(0.0, 0.0004, n))
    open_ = close.copy()
    open_[1:] = close[:-1]                       # open == previous close
    high = np.maximum(open_, close) + 0.0005
    low = np.minimum(open_, close) - 0.0005
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close},
        index=_index(n),
    )


def _assert_invalid(df):
    with pytest.raises(fc.InputContractError):
        fc.validate_candles(df)


# ── schema ──────────────────────────────────────────────────────────────────

def test_ordered_features_count_and_no_duplicates():
    assert len(fc.ORDERED_FEATURES) == 33
    assert len(set(fc.ORDERED_FEATURES)) == 33


def test_ordered_features_exact_sequence():
    expected = [
        "return_15m", "return_45m", "return_90m", "return_3h", "log_return_15m",
        "horizon_vol_3h", "horizon_vol_6h", "horizon_vol_12h",
        "body", "upper_wick", "lower_wick", "range", "direction",
        "atr", "atr_pct", "atr_ecdf_50bar", "atr_ma", "atr_above_sma14", "atr_ratio",
        "rsi", "rsi_slope_45m",
        "adx",
        "macd", "macd_signal", "macd_hist",
        "dist_high_6h", "dist_low_6h", "dist_high_12h", "dist_low_12h",
        "dist_high_24h", "dist_low_24h",
        "utc_hour", "utc_day_of_week",
    ]
    assert fc.ORDERED_FEATURES == expected


def test_get_feature_columns_is_a_copy():
    cols = fc.get_feature_columns()
    assert cols == fc.ORDERED_FEATURES
    cols.append("mutated")
    assert fc.ORDERED_FEATURES == list(fc.ORDERED_FEATURES)
    assert "mutated" not in fc.ORDERED_FEATURES


# ── input contract (IC-06) ──────────────────────────────────────────────────

def test_validate_accepts_valid_frame_and_returns_copy():
    df = _frame()
    out = fc.validate_candles(df)
    assert isinstance(out, pd.DataFrame)
    assert out is not df
    pd.testing.assert_frame_equal(out, df)
    # defensive copy: mutating the result must not touch the source
    out.iloc[0, out.columns.get_loc("Close")] = 999.0
    assert df["Close"].iloc[0] != 999.0


def test_validate_rejects_non_dataframe():
    _assert_invalid([1, 2, 3])


def test_validate_rejects_empty():
    _assert_invalid(pd.DataFrame(
        {"Open": [], "High": [], "Low": [], "Close": []},
        index=pd.DatetimeIndex([], tz="UTC"),
    ))


def test_validate_rejects_too_few_bars():
    _assert_invalid(_frame().iloc[:1])


def test_validate_rejects_missing_column():
    _assert_invalid(_frame().drop(columns=["High"]))


def test_validate_rejects_non_datetime_index():
    _assert_invalid(_frame().reset_index(drop=True))


def test_validate_rejects_naive_index():
    df = _frame()
    df.index = df.index.tz_localize(None)
    _assert_invalid(df)


def test_validate_rejects_duplicate_timestamps():
    df = _frame()
    dup = pd.concat([df, df.iloc[[-1]]])
    _assert_invalid(dup)


def test_validate_rejects_non_monotonic_index():
    _assert_invalid(_frame().iloc[::-1])


def test_validate_rejects_non_finite():
    df = _frame()
    df.iloc[3, df.columns.get_loc("High")] = np.inf
    _assert_invalid(df)
    df = _frame()
    df.iloc[4, df.columns.get_loc("Close")] = np.nan
    _assert_invalid(df)


def test_validate_rejects_non_positive_price():
    df = _frame()
    df.iloc[2, df.columns.get_loc("Low")] = 0.0
    _assert_invalid(df)


def test_validate_rejects_high_below_low():
    df = _frame()
    df.iloc[1, df.columns.get_loc("High")] = df["Low"].iloc[1] - 0.001
    _assert_invalid(df)


def test_validate_rejects_high_low_not_bounding_open_close():
    df = _frame()
    # High below max(Open, Close), still >= Low and > 0
    df.iloc[1, df.columns.get_loc("High")] = df["Low"].iloc[1] + 1e-6
    _assert_invalid(df)

    df = _frame()
    # Low above min(Open, Close), still <= High
    df.iloc[0, df.columns.get_loc("Low")] = df["Open"].iloc[0] + 1e-6
    _assert_invalid(df)


def test_build_features_rejects_invalid_batch():
    df = _frame()
    df = df.drop(columns=["Open"])
    with pytest.raises(fc.InputContractError):
        fc.build_features(df)


# ── primitives ──────────────────────────────────────────────────────────────

def test_lag_return_warmup_and_values():
    close = np.array([1.0, 2.0, 4.0, 8.0])
    out = fc._lag_return(close, 1)
    assert np.isnan(out[0])
    np.testing.assert_allclose(out[1:], [1.0, 1.0, 1.0])
    out3 = fc._lag_return(close, 3)
    assert np.isnan(out3[:3]).all()
    assert out3[3] == pytest.approx(7.0)


def test_true_range_first_candle_is_high_minus_low():
    high = np.array([1.10, 1.12, 1.11])
    low = np.array([1.00, 1.05, 1.02])
    close = np.array([1.05, 1.11, 1.03])
    tr = fc.true_range(high, low, close)
    assert tr[0] == pytest.approx(0.10)
    # row 1: max(H-L, |H-prevC|, |L-prevC|) = max(0.07, 0.07, 0.0) = 0.07
    assert tr[1] == pytest.approx(0.07)


def test_wilder_sum_and_mean_seed_location():
    x = np.array([np.nan, 1.0, 2.0, 3.0, 4.0, 5.0])
    s = fc.wilder_sum(x, 2, seed_from=1)
    assert np.isnan(s[1])
    assert s[2] == pytest.approx(3.0)          # 1 + 2
    assert s[3] == pytest.approx(3.0 - 3.0 / 2 + 3.0)
    m = fc.wilder_mean(x, 2, seed_from=1)
    assert m[2] == pytest.approx(1.5)
    assert m[3] == pytest.approx((1.5 * 1 + 3.0) / 2)


def test_wilder_short_series_is_all_nan():
    x = np.array([np.nan, 1.0, 2.0])
    assert np.isnan(fc.wilder_sum(x, 5)).all()
    assert np.isnan(fc.wilder_mean(x, 5)).all()


def test_ema_seed_and_adjust_false_recurrence():
    x = np.array([1.0, 2.0, 3.0])
    out = fc.ema(x, 3)                          # alpha = 0.5
    assert out[0] == pytest.approx(1.0)         # seeded with first value
    assert out[1] == pytest.approx(0.5 * 1.0 + 0.5 * 2.0)
    assert out[2] == pytest.approx(0.5 * out[1] + 0.5 * 3.0)


def test_atr_ecdf_constant_series_rank_one():
    atr = np.full(70, 0.5)
    ecdf = fc.atr_ecdf_50(atr, 50)
    assert np.isnan(ecdf[:49]).all()            # needs 50 valid values
    assert ecdf[49] == pytest.approx(1.0)
    assert np.allclose(ecdf[49:], 1.0)


def test_rsi_wilder_monotonic_up_is_100():
    close = 1.0 + np.arange(40) * 0.001
    rsi = fc.rsi_wilder(close, 14)
    assert np.isnan(rsi[:14]).all()
    assert np.allclose(rsi[14:], 100.0)


def test_rsi_wilder_flat_is_50():
    close = np.full(40, 1.1)
    rsi = fc.rsi_wilder(close, 14)
    assert np.isnan(rsi[:14]).all()
    assert np.allclose(rsi[14:], 50.0)


def test_adx_from_dx_break_and_reseed():
    dx = np.full(60, np.nan)
    dx[14:44] = 30.0                            # first run of 14 valid
    dx[44] = np.nan                             # break
    dx[45:60] = 50.0                            # reseed run
    adx = fc.adx_from_dx(dx, 14)
    assert np.isnan(adx[:27]).all()
    assert adx[27] == pytest.approx(30.0)       # seed == mean(first 14)
    assert adx[28] == pytest.approx(30.0)       # carried while valid
    assert adx[43] == pytest.approx(30.0)
    assert np.isnan(adx[44])                    # break => no value
    assert adx[58] == pytest.approx(50.0)       # reseed, not carried from 30
    assert adx[59] == pytest.approx(50.0)


def test_adx_wilder_first_valid_is_2n_minus_1():
    df = _frame(n=80)
    adx = fc.adx_wilder(df["High"].to_numpy(), df["Low"].to_numpy(),
                        df["Close"].to_numpy(), 14)
    assert np.isnan(adx[:27]).all()             # first ADX seed at t = 2n-1
    assert np.isfinite(adx[27])
    assert np.all((adx[27:] >= 0.0) & (adx[27:] <= 100.0))


def test_adx_wilder_flat_series_is_nan_not_fabricated():
    # No directional movement => DX is 0/0 undefined, so ADX stays NaN rather
    # than being fabricated as 0.0 (fail-closed, no silent default).
    n = 80
    flat = np.full(n, 1.1)
    adx = fc.adx_wilder(flat, flat, flat, 14)
    assert np.isnan(adx).all()


# ── contract builder ────────────────────────────────────────────────────────

def test_build_features_columns_and_index():
    df = _frame()
    out = fc.build_features(df)
    assert list(out.columns) == fc.ORDERED_FEATURES
    assert out.index.equals(df.index)
    assert len(out) == len(df)


def test_build_features_does_not_mutate_input():
    df = _frame()
    before = df.copy()
    fc.build_features(df)
    pd.testing.assert_frame_equal(df, before)


def test_build_features_is_deterministic():
    df = _frame()
    a = fc.build_features(df)
    b = fc.build_features(df)
    pd.testing.assert_frame_equal(a, b)


def test_build_features_warmup_is_nan_not_filled():
    out = fc.build_features(_frame(n=90))
    # leading rows stay NaN — no fillna/bfill/ffill fallback
    for col in ("return_15m", "atr", "rsi", "adx", "horizon_vol_3h", "atr_ma"):
        assert np.isnan(out[col].iloc[0]), col
    # direction is a strict sign column, never a fabricated default
    assert set(np.unique(out["direction"].dropna())).issubset({-1.0, 0.0, 1.0})


def test_build_features_first_valid_rows():
    out = fc.build_features(_frame(n=90))
    # exact-window / recursive warm-up boundaries
    assert not np.isnan(out["macd"].iloc[0])            # EMA seeds at row 0
    assert np.isnan(out["return_15m"].iloc[0])
    assert not np.isnan(out["return_15m"].iloc[1])
    assert np.isnan(out["horizon_vol_3h"].iloc[11])
    assert not np.isnan(out["horizon_vol_3h"].iloc[12])
    assert np.isnan(out["atr"].iloc[13])
    assert not np.isnan(out["atr"].iloc[14])            # Wilder seed at t = n
    assert np.isnan(out["rsi"].iloc[13])
    assert not np.isnan(out["rsi"].iloc[14])
    assert np.isnan(out["rsi_slope_45m"].iloc[16])      # rsi first valid + 3
    assert not np.isnan(out["rsi_slope_45m"].iloc[17])
    assert np.isnan(out["atr_ma"].iloc[26])
    assert not np.isnan(out["atr_ma"].iloc[27])         # 14 valid ATR bars
    assert np.isnan(out["atr_ecdf_50bar"].iloc[62])
    assert not np.isnan(out["atr_ecdf_50bar"].iloc[63])  # 50 valid ATR bars
    assert np.isnan(out["dist_high_6h"].iloc[22])
    assert not np.isnan(out["dist_high_6h"].iloc[23])    # 24-bar window
    assert np.isnan(out["adx"].iloc[26])
    assert not np.isnan(out["adx"].iloc[27])


def test_build_features_time_columns():
    df = _frame()
    out = fc.build_features(df)
    assert np.allclose(out["utc_hour"], df.index.hour.astype(float))
    assert np.allclose(out["utc_day_of_week"], df.index.dayofweek.astype(float))


def test_horizon_vol_uses_sqrt_window_scale():
    df = _frame()
    out = fc.build_features(df)
    rets = df["Close"].pct_change()
    expected = (rets.rolling(24, min_periods=24).std(ddof=1) * np.sqrt(24)).to_numpy()
    np.testing.assert_allclose(out["horizon_vol_6h"].to_numpy(), expected, equal_nan=True)


def test_module_stays_unwired():
    """The contract must not pull in the legacy engine or a silent fill path."""
    import ast

    src = Path(fc.__file__).read_text()
    tree = ast.parse(src)
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module)
    assert not any(m == "data_pipeline" or m.startswith("ml.features") or m == "features"
                   for m in mods), mods

    # executable source with the module docstring stripped
    end = src.index('"""', src.index('"""') + 3) + 3
    body = src[end:]
    assert ".bfill(" not in body
    assert ".ffill(" not in body
    assert "fillna(" not in body


# ── L3 runtime wiring (reversible, default-OFF) ──────────────────────────────

_LIVE_BOTS = [BASE_DIR / "fx_trade_bot.py", BASE_DIR / "fx_trade_bot_v685.py"]
_RETRAIN = BASE_DIR / "retrain_model.py"


@pytest.mark.parametrize("bot", _LIVE_BOTS, ids=lambda p: p.name)
def test_bot_exposes_default_off_v2_switch(bot):
    """L3: the contract is reachable only behind a default-OFF runtime switch."""
    src = bot.read_text(encoding="utf-8")
    assert 'USE_FEATURE_CONTRACT_V2 = _opt("USE_FEATURE_CONTRACT_V2", False)' in src


@pytest.mark.parametrize("bot", _LIVE_BOTS, ids=lambda p: p.name)
def test_bot_feature_builds_are_routed_through_helper(bot):
    """Every per-pair build goes through _build_pair_features; the only direct
    FeatureEngine.build call left is the legacy branch inside the helper."""
    src = bot.read_text(encoding="utf-8")
    assert src.count("feat_engine.build(") == 1
    assert src.count("_build_pair_features(") == 5  # 1 def + 4 call sites
    assert "return feat_engine.build(raw)" in src


@pytest.mark.parametrize("bot", _LIVE_BOTS, ids=lambda p: p.name)
def test_helper_contract_branch_is_lazy_and_fail_closed(bot):
    """The contract import is lazy (inside the switch branch) and the build is
    not wrapped in a swallowing try/except."""
    src = bot.read_text(encoding="utf-8")
    start = src.index("def _build_pair_features(raw):")
    body = src[start:src.index("last_closed = {}", start)]
    assert "if USE_FEATURE_CONTRACT_V2:" in body
    assert "from ml.feature_contract import build_features" in body
    assert "try:" not in body
    assert "except" not in body


# ── L3 training-path wiring (reversible, default-OFF) ────────────────────────

def test_retrain_exposes_default_off_v2_switch():
    """P1/P2 parity: the training path carries the same default-OFF switch."""
    src = _RETRAIN.read_text(encoding="utf-8")
    assert 'USE_FEATURE_CONTRACT_V2 = _opt("USE_FEATURE_CONTRACT_V2", False)' in src


def test_retrain_feature_builds_are_routed_through_helper():
    """The single per-pair build goes through _build_pair_features; the only
    direct FeatureEngine.build call left is the legacy branch inside it."""
    src = _RETRAIN.read_text(encoding="utf-8")
    assert src.count("feat_engine.build(") == 1
    assert src.count("_build_pair_features(") == 2  # 1 def + 1 call site
    assert "return feat_engine.build(raw)" in src


def test_retrain_helper_contract_branch_is_lazy_and_fail_closed():
    """The contract import is lazy (inside the switch branch) and the build is
    not wrapped in a swallowing try/except."""
    src = _RETRAIN.read_text(encoding="utf-8")
    start = src.index("def _build_pair_features(raw, feat_engine):")
    body = src[start:src.index("MODEL_STEM = BASE_DIR", start)]
    assert "if USE_FEATURE_CONTRACT_V2:" in body
    assert "from ml.feature_contract import build_features" in body
    assert "try:" not in body
    assert "except" not in body
