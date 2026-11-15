"""
Phase 3.2 — Proposed Feature Contract (offline experiment implementation).

Standalone, READ-ONLY implementation of the *proposed* Feature Contract defined in
docs/phase3_2/02_FEATURE_TECHNICAL_DEFINITIONS_AND_ELIGIBILITY.md (§2 candidate
inventory, §3 proposed ADX) together with the computation semantics recorded in
docs/phase3_2/PHASE3_2_REVISION_PLAN.md (§6 FD-03..FD-06).

This module deliberately does NOT import or modify data_pipeline.py or
ml/features.py. It exists only to evaluate the proposed definitions in the
Step 4 offline convergence experiment. It is not wired to production.

Timeframe: M15 (one row == 15 minutes).
Input frame: index = timezone-aware UTC DatetimeIndex; columns Open/High/Low/Close.
Volume is intentionally absent (FD-07 proposed EXCLUDE).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

ATR_N = 14
RSI_N = 14
ADX_N = 14
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9

# §9.5 classification: E = exact fixed-window / row-wise deterministic,
# R = recursive or depends on recursive input.
E_CLASS = [
    "return_15m", "return_45m", "return_90m", "return_3h", "log_return_15m",
    "horizon_vol_3h", "horizon_vol_6h", "horizon_vol_12h",
    "body", "upper_wick", "lower_wick", "range", "direction",
    "dist_high_6h", "dist_low_6h", "dist_high_12h", "dist_low_12h",
    "dist_high_24h", "dist_low_24h",
    "utc_hour", "utc_day_of_week",
]
R_CLASS = [
    "atr", "atr_pct", "atr_ecdf_50bar", "atr_ma", "atr_above_sma14", "atr_ratio",
    "rsi", "rsi_slope_45m",
    "macd", "macd_signal", "macd_hist",
    "adx",
]


# ─────────────────────────────── primitives ───────────────────────────────

def _lag_return(close: np.ndarray, k: int) -> np.ndarray:
    out = np.full(len(close), np.nan)
    if len(close) > k:
        out[k:] = close[k:] / close[:-k] - 1.0
    return out


def _true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    n = len(close)
    tr = np.empty(n)
    tr[0] = high[0] - low[0]                       # candle 0 has no prior close
    if n > 1:
        prev_close = close[:-1]
        tr[1:] = np.maximum.reduce([
            high[1:] - low[1:],
            np.abs(high[1:] - prev_close),
            np.abs(low[1:] - prev_close),
        ])
    return tr


def _wilder_sum(x: np.ndarray, n: int, seed_from: int = 1) -> np.ndarray:
    """Wilder smoothed sum: S[n] = sum(x[seed_from..n]); S[t]=S[t-1]-S[t-1]/n+x[t]."""
    out = np.full(len(x), np.nan)
    if len(x) <= n:
        return out
    out[n] = np.nansum(x[seed_from:n + 1])
    for t in range(n + 1, len(x)):
        out[t] = out[t - 1] - out[t - 1] / n + x[t]
    return out


def _wilder_mean(x: np.ndarray, n: int, seed_from: int = 1) -> np.ndarray:
    """Wilder smoothed average: mean[n] = mean(x[seed_from..n]); mean[t]=(mean[t-1]*(n-1)+x[t])/n."""
    out = np.full(len(x), np.nan)
    if len(x) <= n:
        return out
    out[n] = np.nansum(x[seed_from:n + 1]) / n
    for t in range(n + 1, len(x)):
        out[t] = (out[t - 1] * (n - 1) + x[t]) / n
    return out


def _ema(x: np.ndarray, span: int) -> np.ndarray:
    """EMA with alpha = 2/(span+1), adjust=False, seeded with the first value."""
    a = 2.0 / (span + 1.0)
    out = np.empty(len(x))
    out[0] = x[0]
    for t in range(1, len(x)):
        out[t] = (1.0 - a) * out[t - 1] + a * x[t]
    return out


def _atr_ecdf_50(atr: np.ndarray, w: int = 50) -> np.ndarray:
    """Empirical rank of the current ATR within the trailing w valid ATR values."""
    out = np.full(len(atr), np.nan)
    valid = np.where(~np.isnan(atr))[0]
    for k, i in enumerate(valid):
        if k + 1 < w:
            continue
        window = atr[valid[k + 1 - w:k + 1]]
        out[i] = float(np.sum(window <= atr[i])) / w
    return out


# ─────────────────────────────── ADX (Wilder) ───────────────────────────────

def adx_wilder(high: np.ndarray, low: np.ndarray, close: np.ndarray, n: int = ADX_N) -> np.ndarray:
    """Doc02 §3: Wilder DI/DX with seed at t=n, first ADX seed at t=2n-1, break/reseed."""
    N = len(high)
    adx_out = np.full(N, np.nan)
    if N <= n:
        return adx_out

    tr = _true_range(high, low, close)
    plus_dm = np.zeros(N)
    minus_dm = np.zeros(N)
    up = high[1:] - high[:-1]
    down = low[:-1] - low[1:]
    pm = np.where((up > down) & (up > 0), up, 0.0)
    mm = np.where((down > up) & (down > 0), down, 0.0)
    plus_dm[1:] = pm
    minus_dm[1:] = mm

    str_ = _wilder_sum(tr, n, seed_from=1)
    sp = _wilder_sum(plus_dm, n, seed_from=1)
    sm = _wilder_sum(minus_dm, n, seed_from=1)

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


def adx_from_dx(dx: np.ndarray, n: int = ADX_N) -> np.ndarray:
    """ADX Wilder recurrence over a DX series: seed at first run of n valid DX, reseed after gaps."""
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


# ─────────────────────────────── main builder ───────────────────────────────

def build_proposed_features(df: pd.DataFrame) -> pd.DataFrame:
    o = df["Open"].to_numpy(float)
    h = df["High"].to_numpy(float)
    l = df["Low"].to_numpy(float)
    c = df["Close"].to_numpy(float)
    n = len(df)
    out = pd.DataFrame(index=df.index)

    # 1. Returns
    out["return_15m"] = _lag_return(c, 1)
    out["return_45m"] = _lag_return(c, 3)
    out["return_90m"] = _lag_return(c, 6)
    out["return_3h"] = _lag_return(c, 12)
    log_ret = np.full(n, np.nan)
    if n > 1:
        log_ret[1:] = np.log(c[1:] / c[:-1])
    out["log_return_15m"] = log_ret

    # 2. Realized volatility — proposed new scale sqrt(window)
    rets = pd.Series(c).pct_change()
    out["horizon_vol_3h"] = (rets.rolling(12, min_periods=12).std(ddof=1) * np.sqrt(12)).to_numpy()
    out["horizon_vol_6h"] = (rets.rolling(24, min_periods=24).std(ddof=1) * np.sqrt(24)).to_numpy()
    out["horizon_vol_12h"] = (rets.rolling(48, min_periods=48).std(ddof=1) * np.sqrt(48)).to_numpy()

    # 3. Candle microstructure
    out["body"] = np.abs(c - o) / o
    out["upper_wick"] = (h - np.maximum(o, c)) / o
    out["lower_wick"] = (np.minimum(o, c) - l) / o
    out["range"] = (h - l) / o
    out["direction"] = np.where(c > o, 1.0, np.where(c == o, 0.0, -1.0))

    # 4. ATR (Wilder) + derived
    tr = _true_range(h, l, c)
    str_ = _wilder_sum(tr, ATR_N, seed_from=1)
    atr = str_ / ATR_N
    atr_s = pd.Series(atr)
    out["atr"] = atr
    out["atr_pct"] = atr / c
    out["atr_ecdf_50bar"] = _atr_ecdf_50(atr, 50)
    atr_ma = atr_s.rolling(ATR_N, min_periods=ATR_N).mean().to_numpy()
    out["atr_ma"] = atr_ma
    with np.errstate(invalid="ignore"):
        out["atr_above_sma14"] = np.where(np.isnan(atr_ma), np.nan, (atr > atr_ma).astype(float))
    atr_hist_mean = atr_s.rolling(2 * ATR_N, min_periods=2 * ATR_N).mean().to_numpy()
    out["atr_ratio"] = atr / atr_hist_mean

    # 5. RSI (Wilder) + slope
    delta = np.diff(c, prepend=np.nan)
    gain = np.clip(delta, 0.0, None)
    loss = np.clip(-delta, 0.0, None)
    ag = _wilder_mean(gain, RSI_N, seed_from=1)
    al = _wilder_mean(loss, RSI_N, seed_from=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        rs = ag / al
        rsi = 100.0 - 100.0 / (1.0 + rs)
        rsi = np.where(al == 0, 100.0, rsi)
        rsi = np.where((ag == 0) & (al == 0), 50.0, rsi)
    rsi = np.where(np.isnan(ag) | np.isnan(al), np.nan, rsi)
    out["rsi"] = rsi
    out["rsi_slope_45m"] = pd.Series(rsi).diff(3).to_numpy()

    # 6. ADX (Wilder, break/reseed)
    out["adx"] = adx_wilder(h, l, c, ADX_N)

    # 7. MACD 12/26/9 (EMA, adjust=False)
    ema_fast = _ema(c, MACD_FAST)
    ema_slow = _ema(c, MACD_SLOW)
    macd = ema_fast - ema_slow
    signal = _ema(macd, MACD_SIGNAL)
    out["macd"] = macd
    out["macd_signal"] = signal
    out["macd_hist"] = macd - signal

    # 8. Distance from extremes (full window, includes current bar)
    for name_h, name_l, w in [
        ("dist_high_6h", "dist_low_6h", 24),
        ("dist_high_12h", "dist_low_12h", 48),
        ("dist_high_24h", "dist_low_24h", 96),
    ]:
        hh = pd.Series(h).rolling(w, min_periods=w).max().to_numpy()
        ll = pd.Series(l).rolling(w, min_periods=w).min().to_numpy()
        out[name_h] = (c - hh) / c
        out[name_l] = (c - ll) / c

    # 9. Time features from the validated UTC index
    if isinstance(df.index, pd.DatetimeIndex):
        out["utc_hour"] = df.index.hour.astype(float)
        out["utc_day_of_week"] = df.index.dayofweek.astype(float)
    else:
        out["utc_hour"] = 0.0
        out["utc_day_of_week"] = 0.0

    return out
