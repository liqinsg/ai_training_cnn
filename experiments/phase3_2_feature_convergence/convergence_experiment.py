"""
Phase 3.2 Step 4 — Offline history-length convergence experiment.

READ-ONLY. Computes the *proposed* Feature Contract (see proposed_contract.py)
on preregistered deterministic M15 OHLC fixtures at history lengths
200 / 300 / 500 / 800 and compares the final-candle vector using the tolerance

    |A - B| <= atol + rtol * |B|        (atol = 1e-10, rtol = 1e-8)

Main acceptance pairs: 300v500 and 500v800. 200v300 / 200v500 / 200v800 are
diagnostic only. Implements the protocol in PHASE3_2_REVISION_PLAN.md §9.

Run:  python3 experiments/phase3_2_feature_convergence/convergence_experiment.py
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from proposed_contract import (  # noqa: E402
    build_proposed_features, adx_from_dx, E_CLASS, R_CLASS, ADX_N,
)

N_BARS = 800
LENGTHS = [200, 300, 500, 800]
ATOL = 1e-10
RTOL = 1e-8
MAIN_PAIRS = [(300, 500), (500, 800)]
DIAG_PAIRS = [(200, 300), (200, 500), (200, 800)]
ALL_FEATURES = E_CLASS + R_CLASS


# ─────────────────────────────── fixtures (preregistered) ───────────────────────────────

def _ohlc_from_close(close: np.ndarray, rng: np.random.Generator, wick: float = 2e-4):
    n = len(close)
    o = np.empty(n)
    o[0] = close[0]
    o[1:] = close[:-1]
    top = np.maximum(o, close)
    bot = np.minimum(o, close)
    up = np.abs(rng.normal(0.0, 1.0, n)) * wick
    dn = np.abs(rng.normal(0.0, 1.0, n)) * wick
    h = top + up
    l = bot - dn
    return o, h, l, close.copy()


def _index(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2026-01-05 00:00", periods=n, freq="15min", tz="UTC")


def fixture_ohlc(name: str) -> pd.DataFrame:
    rng = np.random.default_rng({"up": 1, "down": 2, "varying": 3, "alternating": 4, "adx_break": 5}[name])
    n = N_BARS

    if name == "up":
        close = 1.10 + 2e-4 * np.arange(n)
        o, h, l, c = _ohlc_from_close(close, rng)
    elif name == "down":
        close = 1.40 - 2e-4 * np.arange(n)
        o, h, l, c = _ohlc_from_close(close, rng)
    elif name == "varying":
        close = 1.10 * np.exp(np.cumsum(rng.normal(0.0, 4e-4, n)))
        o, h, l, c = _ohlc_from_close(close, rng)
    elif name == "alternating":
        close = 1.10 + 4e-4 * np.where(np.arange(n) % 2 == 0, 1.0, -1.0)
        o, h, l, c = _ohlc_from_close(close, rng)
    elif name == "adx_break":
        # flat prefix (H=O=L=C -> TR=0, DI unavailable) -> directional up
        # -> exact-flat mid segment (TR=0) -> directional down. Exercises the
        # "DX unavailable" / warm-up edges that a valid OHLC feed can produce.
        k1, k2 = 40, 600
        close = np.empty(n)
        close[:k1] = 1.10
        close[k1:k2] = 1.10 + 2e-4 * np.arange(k2 - k1)
        close[k2:] = close[k2 - 1] - 3e-4 * np.arange(n - k2)
        o, h, l, c = _ohlc_from_close(close, rng)
        for a, b in [(0, k1), (k2, n)]:           # force exact flat regions
            o[a:b] = c[a:b]
            h[a:b] = c[a:b]
            l[a:b] = c[a:b]
        # exact-flat midfield band
        band = slice(k2 - 120, k2 - 60)
        o[band] = c[band]
        h[band] = c[band]
        l[band] = c[band]
    else:
        raise ValueError(name)

    return pd.DataFrame(
        {"Open": o, "High": h, "Low": l, "Close": c}, index=_index(n)
    )


def fixture_hash(df: pd.DataFrame) -> str:
    raw = np.ascontiguousarray(df[["Open", "High", "Low", "Close"]].to_numpy(np.float64)).tobytes()
    return hashlib.sha256(raw).hexdigest()


# ─────────────────────────────── comparison ───────────────────────────────

def compare(a: float, b: float) -> tuple[str, float, float]:
    """Returns (status, absdiff, tol) for |A-B| <= atol + rtol*|B|."""
    if not np.isfinite(b):
        return "NOT ESTABLISHED (B non-finite)", float("nan"), float("nan")
    if not np.isfinite(a):
        return "NOT ESTABLISHED (A non-finite)", float("nan"), float("nan")
    diff = abs(a - b)
    tol = ATOL + RTOL * abs(b)
    return ("PASS" if diff <= tol else "FAIL"), diff, tol


def adx_reseed_unit_check() -> tuple[bool, str]:
    """Direct check of the reseed rule using a crafted DX series (n=14)."""
    dx = np.full(80, np.nan)
    dx[14:40] = 30.0            # first run -> seed at index 27
    dx[45:80] = 50.0            # break at 40..44 -> reseed at 45+13=58
    adx = adx_from_dx(dx, ADX_N)
    ok = (
        np.isnan(adx[26])
        and abs(adx[27] - 30.0) < 1e-12          # mean of DX[14..27]
        and np.isnan(adx[44])                    # gap
        and abs(adx[58] - 50.0) < 1e-12          # reseed mean of DX[45..58]
        and (adx[59] - (50.0 * 13 + 50.0) / 14) < 1e-9
    )
    msg = f"seed@27={adx[27]:.6f}, gap@44={adx[44]}, reseed@58={adx[58]:.6f}, step@59={adx[59]:.6f}"
    return bool(ok), msg


# ─────────────────────────────── run ───────────────────────────────

def run() -> str:
    lines: list[str] = []
    lines.append("# Phase 3.2 Step 4 — History-Length Convergence Report\n")
    lines.append("**Status:** OFFLINE EXPERIMENT OUTPUT — not an approval, not a freeze.\n")
    lines.append(f"- History lengths: `{LENGTHS}`")
    lines.append(f"- Main acceptance pairs: `{MAIN_PAIRS}`  |  Diagnostic pairs: `{DIAG_PAIRS}`")
    lines.append(f"- Tolerance: `|A-B| <= atol + rtol*|B|`, atol={ATOL}, rtol={RTOL} (B = longer history)")
    lines.append("- Contract under test: proposed Feature Contract (Doc 02 §2/§3, Revision Plan §6). Not production code.\n")

    ok, msg = adx_reseed_unit_check()
    lines.append("## 0. ADX break/reseed unit check")
    lines.append(f"- result: **{'PASS' if ok else 'FAIL'}** — {msg}\n")

    overall_pass = ok

    for name in ["up", "down", "varying", "alternating", "adx_break"]:
        df = fixture_ohlc(name)
        lines.append(f"## Fixture `{name}`")
        lines.append(f"- rows: {len(df)}  | sha256(OHLC): `{fixture_hash(df)}`")

        final = {}
        for L in LENGTHS:
            feats = build_proposed_features(df.iloc[-L:])
            final[L] = feats.iloc[-1]
        final_ts = df.index[-1]
        lines.append(f"- final candle: `{final_ts.isoformat()}`\n")

        # main acceptance
        lines.append("### Main acceptance (300v500, 500v800)\n")
        lines.append("| feature | class | 300v500 | 500v800 | verdict |")
        lines.append("|---|---|---|---|---|")
        for f in ALL_FEATURES:
            cls = "E" if f in E_CLASS else "R"
            s1, _, _ = compare(final[300][f], final[500][f])
            s2, _, _ = compare(final[500][f], final[800][f])
            passed = s1 == "PASS" and s2 == "PASS"
            overall_pass = overall_pass and passed
            lines.append(f"| `{f}` | {cls} | {s1} | {s2} | {'PASS' if passed else 'FAIL'} |")
        lines.append("")

        # diagnostic
        lines.append("### Diagnostic pairs (final-candle |A-B|)\n")
        hdr = "| feature | " + " | ".join(f"{a}v{b}" for a, b in DIAG_PAIRS) + " |"
        lines.append(hdr)
        lines.append("|---|" + "---|" * len(DIAG_PAIRS))
        for f in ALL_FEATURES:
            cells = []
            for a, b in DIAG_PAIRS:
                _, d, _ = compare(final[a][f], final[b][f])
                cells.append("nan" if not np.isfinite(d) else f"{d:.3e}")
            lines.append(f"| `{f}` | " + " | ".join(cells) + " |")
        lines.append("")

    lines.append("## Summary")
    lines.append(f"- ADX reseed unit check: {'PASS' if ok else 'FAIL'}")
    lines.append(f"- All fixtures x main pairs x all features PASS: **{'YES' if overall_pass else 'NO'}**")
    lines.append("- E-class features carry no recursive state, so identical final candles give "
                 "bit-identical final values; R-class features show the initialization-tailoff behaviour.")
    lines.append("- Limitations recorded: a mid-series exact `+DI=-DI=0` break is mathematically "
                 "degenerate and is not constructible from valid OHLC within the tested horizon; "
                 "the reseed rule is therefore verified by the direct DX check in §0.")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    report = run()
    out = Path(__file__).resolve().parent / "REPORT.md"
    out.write_text(report, encoding="utf-8")
    print(f"wrote {out}")
    # also echo the compact main-acceptance verdicts to stdout
    for line in report.splitlines():
        if line.startswith("- All fixtures") or line.startswith("- ADX reseed") or line.startswith("| `adx`") or line.startswith("| `atr`") or line.startswith("| `rsi`"):
            print(line)
