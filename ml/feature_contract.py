"""
Phase 3.2 — Feature Contract implementation (PROPOSED / NOT WIRED).

Authoritative, self-contained implementation of the *proposed* Phase 3.2 Feature
Contract. Source of truth:
  * docs/phase3_2/02_FEATURE_TECHNICAL_DEFINITIONS_AND_ELIGIBILITY.md  (§2, §3)
  * docs/phase3_2/PHASE3_2_REVISION_PLAN.md                            (§6, §10)

Status / boundaries
-------------------
* This module is the *single* implementation of the new contract. It does NOT
  import, call, or modify ``data_pipeline.py`` or ``ml/features.py``; the live
  runtime call paths are unchanged until an explicit L3 implementation decision
  wires them.
* No silent fallback, no ``bfill``, no blanket ``fillna(0)``. Warm-up rows stay
  ``NaN``; invalid candles reject the whole batch (IC-06).
* Timeframe is M15 (one row == 15 minutes). Every window below is a bar count.

Implemented numeric features (33)
---------------------------------
returns:      return_15m, return_45m, return_90m, return_3h, log_return_15m
horizon_vol:  horizon_vol_3h, horizon_vol_6h, horizon_vol_12h   (std(ddof=1)*sqrt(window))
candle:       body, upper_wick, lower_wick, range, direction
atr:          atr, atr_pct, atr_ecdf_50bar, atr_ma, atr_above_sma14, atr_ratio
rsi:          rsi, rsi_slope_45m
adx:          adx
macd:         macd, macd_signal, macd_hist
distance:     dist_high_6h, dist_low_6h, dist_high_12h, dist_low_12h, dist_high_24h, dist_low_24h
time:         utc_hour, utc_day_of_week

Dispositions not implemented here
---------------------------------
DEFER / proposed-EXCLUDE (4): vol_sma_ratio, vol_trend, is_london, is_ny.
See :data:`DISPOSITIONS`.
"""

from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

# ── frozen parameters (FD-03..FD-06 owner-approved values) ──
ATR_N = 14
RSI_N = 14
ADX_N = 14
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
ECDF_WINDOW = 50
ATR_SMA_N = 14
ATR_RATIO_N = 28

MIN_BARS = 2

REQUIRED_COLUMNS = ["Open", "High", "Low", "Close"]

ORDERED_FEATURES: List[str] = [
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

DISPOSITIONS: Dict[str, str] = {
    **{f: "REDEFINE" for f in (
        "return_15m", "return_45m", "return_90m", "return_3h", "log_return_15m",
        "horizon_vol_3h", "horizon_vol_6h", "horizon_vol_12h", "direction",
        "atr_ecdf_50bar", "adx", "dist_high_6h", "dist_low_6h", "dist_high_12h",
        "dist_low_12h", "dist_high_24h", "dist_low_24h", "utc_hour", "utc_day_of_week")},
    **{f: "ACCEPTABLE AS-IS" for f in ("body", "upper_wick", "lower_wick", "range")},
    **{f: "DEFER->DEFINED" for f in (
        "atr", "atr_pct", "atr_ma", "atr_above_sma14", "atr_ratio",
        "rsi", "rsi_slope_45m", "macd", "macd_signal", "macd_hist")},
    "vol_sma_ratio": "DEFER (proposed EXCLUDE)",
    "vol_trend": "DEFER (proposed EXCLUDE)",
    "is_london": "DEFER",
    "is_ny": "DEFER",
}


class InputContractError(ValueError):
    """Raised when the input candle batch violates the Input Contract (IC)."""


class FeatureContractError(RuntimeError):
    """Raised when the contract cannot be honoured (never silently degraded)."""


# ─────────────────────────────── input validation ───────────────────────────────

def validate_candles(df: pd.DataFrame) -> pd.DataFrame:
    """Validate and return a defensive copy of the candle batch.

    Rejects the whole batch (IC-06) on any violation. Candle validation precedes
    all feature calculation (Doc02 §5).
    """
    if not isinstance(df, pd.DataFrame):
        raise InputContractError(f"expected DataFrame, got {type(df).__name__}")
    if df.empty:
        raise InputContractError("empty candle batch")
    if len(df) < MIN_BARS:
        raise InputContractError(f"need >= {MIN_BARS} candles, got {len(df)}")

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise InputContractError(f"missing required columns: {missing}")

    if not isinstance(df.index, pd.DatetimeIndex):
        raise InputContractError("index must be a DatetimeIndex (validated UTC timestamps)")
    if df.index.tz is None:
        raise InputContractError("index must be timezone-aware (UTC)")
    if not df.index.is_monotonic_increasing or df.index.has_duplicates:
        raise InputContractError("index must be strictly increasing with no duplicate timestamps")

    out = df.copy()
    for c in REQUIRED_COLUMNS:
        out[c] = pd.to_numeric(out[c], errors="coerce").astype(float)

    arr = out[REQUIRED_COLUMNS].to_numpy(float)
    if not np.isfinite(arr).all():
        raise InputContractError("non-finite value in OHLC")

    o, h, l, c = (out[c].to_numpy(float) for c in REQUIRED_COLUMNS)
    if np.any(o <= 0) or np.any(h <= 0) or np.any(l <= 0) or np.any(c <= 0):
        raise InputContractError("OHLC prices must be strictly positive")
    if np.any(h < l):
        raise InputContractError("High < Low in at least one candle")
    if np.any(h < np.maximum(o, c)) or np.any(l > np.minimum(o, c)):
        raise InputContractError("OHLC inconsistent: High/Low do not bound Open/Close")

    return out


# ─────────────────────────────── primitives ───────────────────────────────

def _lag_return(close: np.ndarray, k: int) -> np.ndarray:
    out = np.full(len(close), np.nan)
    if len(close) > k:
        out[k:] = close[k:] / close[:-k] - 1.0
    return out


def true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    n = len(close)
    tr = np.empty(n)
    tr[0] = high[0] - low[0]                      # candle 0 has no prior close
    if n > 1:
        prev_close = close[:-1]
        tr[1:] = np.maximum.reduce([
            high[1:] - low[1:],
            np.abs(high[1:] - prev_close),
            np.abs(low[1:] - prev_close),
        ])
    return tr


def wilder_sum(x: np.ndarray, n: int, seed_from: int = 1) -> np.ndarray:
    """S[n] = sum(x[seed_from..n]); S[t] = S[t-1] - S[t-1]/n + x[t]."""
    out = np.full(len(x), np.nan)
    if len(x) <= n:
        return out
    out[n] = np.nansum(x[seed_from:n + 1])
    for t in range(n + 1, len(x)):
        out[t] = out[t - 1] - out[t - 1] / n + x[t]
    return out


def wilder_mean(x: np.ndarray, n: int, seed_from: int = 1) -> np.ndarray:
    """mean[n] = mean(x[seed_from..n]); mean[t] = (mean[t-1]*(n-1) + x[t]) / n."""
    out = np.full(len(x), np.nan)
    if len(x) <= n:
        return out
    out[n] = np.nansum(x[seed_from:n + 1]) / n
    for t in range(n + 1, len(x)):
        out[t] = (out[t - 1] * (n - 1) + x[t]) / n
    return out


def ema(x: np.ndarray, span: int) -> np.ndarray:
    """EMA, alpha = 2/(span+1), adjust=False, seeded with the first value."""
    a = 2.0 / (span + 1.0)
    out = np.empty(len(x))
    out[0] = x[0]
    for t in range(1, len(x)):
        out[t] = (1.0 - a) * out[t - 1] + a * x[t]
    return out


def atr_ecdf_50(atr: np.ndarray, w: int = ECDF_WINDOW) -> np.ndarray:
    """Empirical rank of the current ATR within the trailing w valid ATR values."""
    out = np.full(len(atr), np.nan)
    valid = np.where(~np.isnan(atr))[0]
    for k, i in enumerate(valid):
        if k + 1 < w:
            continue
        window = atr[valid[k + 1 - w:k + 1]]
        out[i] = float(np.sum(window <= atr[i])) / w
    return out


def rsi_wilder(close: np.ndarray, n: int = RSI_N) -> np.ndarray:
    """Wilder RSI. avg_loss==0 -> 100 ; avg_gain==avg_loss==0 (flat) -> 50."""
    delta = np.diff(close, prepend=np.nan)
    gain = np.clip(delta, 0.0, None)
    loss = np.clip(-delta, 0.0, None)
    ag = wilder_mean(gain, n, seed_from=1)
    al = wilder_mean(loss, n, seed_from=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        rs = ag / al
        rsi = 100.0 - 100.0 / (1.0 + rs)
        rsi = np.where(al == 0, 100.0, rsi)
        rsi = np.where((ag == 0) & (al == 0), 50.0, rsi)
    return np.where(np.isnan(ag) | np.isnan(al), np.nan, rsi)


def adx_from_dx(dx: np.ndarray, n: int = ADX_N) -> np.ndarray:
    """ADX Wilder recurrence over a DX series: seed at the first run of n valid
    DX values, reseed after a gap, never carry pre-break ADX across the gap."""
    N = len(dx)
    adx_out = np.full(N, np.nan)
    i = 0
    while i < N:
        while i < N and np.isnan(dx[i]):
            i += 1
        if i >= N:
            break
        end = i + n - 1
        if end >= N:
            break
        seg = dx[i:end + 1]
        if np.isnan(seg).any():
            i += 1
            continue
        prev = float(np.mean(seg))
        adx_out[end] = prev
        j = end + 1
        while j < N and not np.isnan(dx[j]):
            prev = (prev * (n - 1) + dx[j]) / n
            adx_out[j] = prev
            j += 1
        i = j
    return adx_out


def adx_wilder(high: np.ndarray, low: np.ndarray, close: np.ndarray, n: int = ADX_N) -> np.ndarray:
    """Doc02 §3: Wilder DI/DX, seed at t=n, first ADX seed at t=2n-1, break/reseed."""
    N = len(high)
    if N <= n:
        return np.full(N, np.nan)

    tr = true_range(high, low, close)
    up = high[1:] - high[:-1]
    down = low[:-1] - low[1:]
    plus_dm = np.zeros(N)
    minus_dm = np.zeros(N)
    plus_dm[1:] = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm[1:] = np.where((down > up) & (down > 0), down, 0.0)

    str_ = wilder_sum(tr, n, seed_from=1)
    sp = wilder_sum(plus_dm, n, seed_from=1)
    sm = wilder_sum(minus_dm, n, seed_from=1)

    dx = np.full(N, np.nan)
    for t in range(n, N):
        if np.isnan(str_[t]) or str_[t] == 0:
            continue
        pdi = 100.0 * sp[t] / str_[t]
        mdi = 100.0 * sm[t] / str_[t]
        d = pdi + mdi
        if d == 0:
            continue
        dx[t] = 100.0 * abs(pdi - mdi) / d
    return adx_from_dx(dx, n)


# ─────────────────────────────── contract ───────────────────────────────

def get_feature_columns() -> List[str]:
    """Deterministic, ordered feature schema."""
    return list(ORDERED_FEATURES)


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute the ordered Feature Contract frame for a validated M15 candle batch.

    Returns a new frame indexed like the input with exactly :data:`ORDERED_FEATURES`
    columns. Warm-up rows are ``NaN`` — never filled.
    """
    d = validate_candles(df)
    o = d["Open"].to_numpy(float)
    h = d["High"].to_numpy(float)
    l = d["Low"].to_numpy(float)
    c = d["Close"].to_numpy(float)
    n = len(d)

    cols: Dict[str, np.ndarray] = {}

    # 1. returns
    cols["return_15m"] = _lag_return(c, 1)
    cols["return_45m"] = _lag_return(c, 3)
    cols["return_90m"] = _lag_return(c, 6)
    cols["return_3h"] = _lag_return(c, 12)
    log_ret = np.full(n, np.nan)
    log_ret[1:] = np.log(c[1:] / c[:-1])
    cols["log_return_15m"] = log_ret

    # 2. horizon volatility — proposed scale sqrt(window), sample std (ddof=1)
    rets = pd.Series(c).pct_change()
    for name, w in (("horizon_vol_3h", 12), ("horizon_vol_6h", 24), ("horizon_vol_12h", 48)):
        cols[name] = (rets.rolling(w, min_periods=w).std(ddof=1) * np.sqrt(w)).to_numpy()

    # 3. candle microstructure
    cols["body"] = np.abs(c - o) / o
    cols["upper_wick"] = (h - np.maximum(o, c)) / o
    cols["lower_wick"] = (np.minimum(o, c) - l) / o
    cols["range"] = (h - l) / o
    cols["direction"] = np.where(c > o, 1.0, np.where(c == o, 0.0, -1.0))

    # 4. ATR (Wilder) + derived
    tr = true_range(h, l, c)
    atr = wilder_sum(tr, ATR_N, seed_from=1) / ATR_N
    atr_s = pd.Series(atr)
    cols["atr"] = atr
    cols["atr_pct"] = atr / c
    cols["atr_ecdf_50bar"] = atr_ecdf_50(atr, ECDF_WINDOW)
    atr_ma = atr_s.rolling(ATR_SMA_N, min_periods=ATR_SMA_N).mean().to_numpy()
    cols["atr_ma"] = atr_ma
    with np.errstate(invalid="ignore"):
        cols["atr_above_sma14"] = np.where(np.isnan(atr_ma), np.nan, (atr > atr_ma).astype(float))
    atr_ratio_den = atr_s.rolling(ATR_RATIO_N, min_periods=ATR_RATIO_N).mean().to_numpy()
    cols["atr_ratio"] = atr / atr_ratio_den

    # 5. RSI (Wilder) + slope
    rsi = rsi_wilder(c, RSI_N)
    cols["rsi"] = rsi
    cols["rsi_slope_45m"] = pd.Series(rsi).diff(3).to_numpy()

    # 6. ADX (Wilder, break/reseed)
    cols["adx"] = adx_wilder(h, l, c, ADX_N)

    # 7. MACD 12/26/9 (EMA, adjust=False)
    macd = ema(c, MACD_FAST) - ema(c, MACD_SLOW)
    signal = ema(macd, MACD_SIGNAL)
    cols["macd"] = macd
    cols["macd_signal"] = signal
    cols["macd_hist"] = macd - signal

    # 8. distance from extremes (full window, includes current bar)
    for name_h, name_l, w in (
        ("dist_high_6h", "dist_low_6h", 24),
        ("dist_high_12h", "dist_low_12h", 48),
        ("dist_high_24h", "dist_low_24h", 96),
    ):
        hh = pd.Series(h).rolling(w, min_periods=w).max().to_numpy()
        ll = pd.Series(l).rolling(w, min_periods=w).min().to_numpy()
        cols[name_h] = (c - hh) / c
        cols[name_l] = (c - ll) / c

    # 9. time features from the validated UTC index
    cols["utc_hour"] = d.index.hour.astype(float)
    cols["utc_day_of_week"] = d.index.dayofweek.astype(float)

    return pd.DataFrame({name: cols[name] for name in ORDERED_FEATURES}, index=d.index)
