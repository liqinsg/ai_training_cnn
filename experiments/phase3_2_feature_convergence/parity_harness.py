"""
Phase 3.2 — P1/P2 Train–Inference Parity Harness (Doc 03 §10, PARITY-P1P2-01).

OFFLINE / NO-NETWORK / READ-ONLY. Exercises the *new* Feature Contract
(ml/feature_contract.py) through the training path and the inference path on the
same raw OHLCV and reports, per feature and per fixture:

  P1 — raw input consistency : identical accept/reject on invalid fixtures.
  P2 — raw feature output     : identical pre-scaling frame (names / order /
       dtype / missingness exact; floats within |A-B| <= atol + rtol*|B|).

Valid fixtures are reused verbatim from convergence_experiment.py (Step 4,
preregistered) so the same deterministic OHLC series are used.

Two path entries (Doc 03 §10.3):
  * training  : retrain_model._build_pair_features(raw, feat_engine) with
                USE_FEATURE_CONTRACT_V2 ON (env OPT_USE_FEATURE_CONTRACT_V2=1).
  * inference : the bots are NOT importable offline (module-level config/engine
                construction + a possible outbound cooldown refresh), so the
                bot ON-branch is source-verified to be a transform-free call
                into ml.feature_contract.build_features, then invoked directly.

Run:  python3 experiments/phase3_2_feature_convergence/parity_harness.py
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[2]
EXP_DIR = Path(__file__).resolve().parent
for p in (str(BASE_DIR), str(EXP_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

# The training path reads the switch at import time; set it ON before importing.
os.environ["OPT_USE_FEATURE_CONTRACT_V2"] = "1"

import ml.feature_contract as fc  # noqa: E402
import retrain_model as rt  # noqa: E402
from data_pipeline import FeatureEngine  # noqa: E402
import convergence_experiment as ce  # noqa: E402

ATOL = 1e-10
RTOL = 1e-8

VALID_FIXTURES = ["up", "down", "varying", "alternating", "adx_break"]
_BOTS = [BASE_DIR / "fx_trade_bot.py", BASE_DIR / "fx_trade_bot_v685.py"]


# ─────────────────────────────── path entries ───────────────────────────────

def _assert_bot_on_branch_is_transform_free() -> None:
    """Static proof that each bot's ON-branch is exactly the contract call."""
    for bot in _BOTS:
        src = bot.read_text(encoding="utf-8")
        start = src.index("def _build_pair_features(raw):")
        body = src[start:src.index("last_closed = {}", start)]
        assert "if USE_FEATURE_CONTRACT_V2:" in body, bot
        assert "from ml.feature_contract import build_features as _contract_build" in body, bot
        assert "return _contract_build(raw)" in body, bot
        assert "return feat_engine.build(raw)" in body, bot
        # ON-branch performs no other transform: only the two returns appear.
        assert body.count("return ") == 2, bot
        assert ".bfill(" not in body and ".fillna(" not in body, bot


def train_entry(raw: pd.DataFrame, feat_engine: FeatureEngine) -> pd.DataFrame:
    """Training path entry (real module, switch ON)."""
    return rt._build_pair_features(raw, feat_engine)


def infer_entry(raw: pd.DataFrame) -> pd.DataFrame:
    """Inference path entry: the bot ON-branch, source-verified above to be this
    exact transform-free call into the shared contract."""
    return fc.build_features(raw)


# ─────────────────────────────── fixtures ───────────────────────────────

def valid_fixture(name: str) -> pd.DataFrame:
    return ce.fixture_ohlc(name)


def invalid_fixtures(base: pd.DataFrame) -> list[tuple[str, object]]:
    """Deterministic invalid batches (Doc 03 §10.2), built from a valid base."""
    out: list[tuple[str, object]] = []

    dup = pd.concat([base, base.iloc[[-1]]])
    out.append(("duplicate_timestamp", dup))

    out.append(("non_monotonic_index", base.iloc[::-1].copy()))

    out.append(("missing_column", base.drop(columns=["High"]).copy()))

    f = base.copy()
    f.iloc[3, f.columns.get_loc("High")] = np.inf
    out.append(("non_finite_inf", f))

    f = base.copy()
    f.iloc[4, f.columns.get_loc("Close")] = np.nan
    out.append(("non_finite_nan", f))

    f = base.copy()
    f.iloc[2, f.columns.get_loc("Low")] = 0.0
    out.append(("non_positive_price", f))

    f = base.copy()
    f.iloc[1, f.columns.get_loc("High")] = f["Low"].iloc[1] - 0.001
    out.append(("high_below_low", f))

    f = base.copy()
    f.iloc[1, f.columns.get_loc("High")] = f["Low"].iloc[1] + 1e-6
    out.append(("hl_not_bounding", f))

    f = base.copy()
    f.index = f.index.tz_localize(None)
    out.append(("naive_index", f))

    out.append(("too_few_bars", base.iloc[:1].copy()))

    out.append(("empty_batch", base.iloc[:0].copy()))

    return out


# ─────────────────────────────── comparison ───────────────────────────────

def _outcome(entry, raw) -> str:
    try:
        entry(raw)
        return "ACCEPT"
    except fc.InputContractError:
        return "REJECT(InputContractError)"
    except Exception as e:  # noqa: BLE001 — record, never swallow silently
        return f"ERROR({type(e).__name__})"


def compare_frames(a: pd.DataFrame, b: pd.DataFrame) -> tuple[bool, list[tuple[str, str, float, float]]]:
    """Return (all_ok, per-feature rows) where each row is
    (feature, verdict, max_abs_diff, max_allowed_tol)."""
    ok = True
    rows: list[tuple[str, str, float, float]] = []

    if list(a.columns) != list(b.columns):
        return False, [("<schema>", "FAIL: column order differs", float("nan"), float("nan"))]
    for c in a.columns:
        if a[c].dtype != b[c].dtype:
            rows.append((c, "FAIL: dtype differs", float("nan"), float("nan")))
            ok = False
            continue
        na_a = a[c].isna().to_numpy()
        na_b = b[c].isna().to_numpy()
        if not np.array_equal(na_a, na_b):
            rows.append((c, "FAIL: missingness differs", float("nan"), float("nan")))
            ok = False
            continue
        av = a[c].to_numpy(float)
        bv = b[c].to_numpy(float)
        m = ~na_a
        if not m.any():
            rows.append((c, "PASS (all-NaN agree)", 0.0, 0.0))
            continue
        diff = np.abs(av[m] - bv[m])
        tol = ATOL + RTOL * np.abs(bv[m])
        max_diff = float(np.max(diff))
        max_tol = float(np.max(tol))
        passed = bool(np.all(diff <= tol))
        rows.append((c, "PASS" if passed else "FAIL", max_diff, max_tol))
        ok = ok and passed
    return ok, rows


def cleaning_chain_identity() -> tuple[bool, str]:
    """Static check that both endpoints apply the same post-build clean chain."""
    expect = (".replace([np.inf, -np.inf], np.nan)",)
    bot_srcs = [p.read_text(encoding="utf-8") for p in _BOTS]
    rt_src = rt.__file__ and Path(rt.__file__).read_text(encoding="utf-8")
    ok = True
    detail = []
    for name, src in [("retrain_model.py", rt_src)] + [(p.name, s) for p, s in zip(_BOTS, bot_srcs)]:
        has = all(tok in src for tok in expect) and ".ffill()" in src and ".bfill()" in src and ".fillna(0)" in src
        ok = ok and has
        detail.append(f"{name}={'ok' if has else 'MISSING'}")
    return ok, ", ".join(detail)


def _git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=BASE_DIR, capture_output=True, text=True, check=False
        ).stdout.strip()
    except Exception:  # noqa: BLE001
        return "<unavailable>"


def env_identity() -> list[str]:
    import zoneinfo

    lines = [
        f"- git HEAD: `{_git('rev-parse', 'HEAD')}`",
        f"- git status (porcelain): `{_git('status', '--porcelain') or '(clean)'}`",
        f"- Python: {sys.version.split()[0]}",
        f"- numpy: {np.__version__} | pandas: {pd.__version__}",
    ]
    try:
        import xgboost
        lines.append(f"- xgboost: {xgboost.__version__}")
    except Exception as e:  # noqa: BLE001
        lines.append(f"- xgboost: UNAVAILABLE ({type(e).__name__})")
    try:
        import tzdata  # type: ignore
        lines.append(f"- tzdata: {getattr(tzdata, '__version__', '?')}")
    except Exception:  # noqa: BLE001
        lines.append("- tzdata: <not importable>")
    try:
        import pytz
        lines.append(f"- pytz: {pytz.__version__}")
    except Exception:  # noqa: BLE001
        lines.append("- pytz: <not importable>")
    lines.append(f"- zoneinfo.TZPATH: {zoneinfo.TZPATH}")
    return lines


# ─────────────────────────────── run ───────────────────────────────

def run() -> str:
    assert rt.USE_FEATURE_CONTRACT_V2 is True, "training switch did not read ON"
    _assert_bot_on_branch_is_transform_free()

    feat_engine = FeatureEngine(rt.FEAT_CFG)
    L: list[str] = []
    L.append("# Phase 3.2 — P1/P2 Train–Inference Parity Report")
    L.append("")
    L.append("**Experiment ID:** `PARITY-P1P2-01`  |  **Protocol:** Doc 03 §10 (preregistered 2026-11-16)")
    L.append("**Status:** OFFLINE EXPERIMENT OUTPUT — not an approval, not a freeze.")
    L.append("")
    L.append("- Tolerance: `|A-B| <= atol + rtol*|B|`, "
             f"atol={ATOL}, rtol={RTOL} (A = training path, B = inference path)")
    L.append("- P1 and P2 are reported separately; neither substitutes for the other.")
    L.append("- Inference entry representation: bot ON-branch is source-verified to be a "
             "transform-free call into `ml.feature_contract.build_features` (Doc 03 §10.3 deviation).")
    L.append("")
    L.append("## 0. Recorded identity")
    L.extend(env_identity())
    L.append("")

    chain_ok, chain_detail = cleaning_chain_identity()
    L.append(f"- Post-build cleaning chain identity (supporting): "
             f"**{'SAME' if chain_ok else 'DIFFERS'}** — {chain_detail}")
    L.append("")

    # ── P1 ──
    L.append("## P1 — raw OHLCV input consistency (invalid fixtures)")
    L.append("")
    L.append("| # | case | training | inference | parity |")
    L.append("|---|---|---|---|---|")
    base = valid_fixture("varying")
    p1_ok = True
    for i, (name, raw) in enumerate(invalid_fixtures(base), 1):
        t = _outcome(lambda r: train_entry(r, feat_engine), raw)
        n = _outcome(infer_entry, raw)
        same = (t == n)
        p1_ok = p1_ok and same
        L.append(f"| {i} | {name} | {t} | {n} | {'PASS' if same else 'FAIL'} |")
    L.append("")
    L.append(f"- **P1 verdict: {'PASS' if p1_ok else 'FAIL'}** "
             f"(base fixture `varying`, sha256={ce.fixture_hash(base)[:16]}…)")
    L.append("")

    # ── P2 ──
    L.append("## P2 — raw feature-output consistency (valid fixtures, pre-scaling)")
    L.append("")
    L.append("Per feature: full-frame comparison (all 800 rows). `max|A-B|` and "
             "`max allowed` are over the finite cells.")
    L.append("")
    p2_ok = True
    for name in VALID_FIXTURES:
        raw = valid_fixture(name)
        tf = train_entry(raw, feat_engine)
        nf = infer_entry(raw)
        ok, rows = compare_frames(tf, nf)
        p2_ok = p2_ok and ok
        L.append(f"### Fixture `{name}`")
        L.append(f"- rows: {len(raw)}  | sha256(OHLC): `{ce.fixture_hash(raw)}`")
        L.append(f"- columns: {list(tf.columns) == fc.ORDERED_FEATURES} "
                 f"({len(tf.columns)} == {len(fc.ORDERED_FEATURES)})")
        L.append("")
        L.append("| feature | verdict | max|A-B| | max allowed |")
        L.append("|---|---|---|---|")
        for feat, verdict, md, mt in rows:
            md_s = "nan" if not np.isfinite(md) else f"{md:.3e}"
            mt_s = "nan" if not np.isfinite(mt) else f"{mt:.3e}"
            L.append(f"| `{feat}` | {verdict} | {md_s} | {mt_s} |")
        L.append("")

    L.append("## Summary")
    L.append("")
    L.append(f"- P1 (invalid-fixture accept/reject parity): **{'PASS' if p1_ok else 'FAIL'}**")
    L.append(f"- P2 (raw feature-output parity, all fixtures × all features): **{'PASS' if p2_ok else 'FAIL'}**")
    L.append(f"- Post-build cleaning chain identity (supporting): {'SAME' if chain_ok else 'DIFFERS'}")
    L.append("- Both ON-branches resolve to the single shared implementation "
             "`ml/feature_contract.build_features`; parity is therefore a property "
             "of routing identity + determinism of that function.")
    L.append("- **`FULL_PARITY_STATUS` remains `NOT VERIFIED`**: P3–P5 (scaler / tensor / "
             "prediction-output) require an active model / scaler / `.features.json` "
             "bundle that is not in the repository. P3–P5 are not marked pass/waived/"
             "`NOT REQUIRED`.")
    L.append("")
    return "\n".join(L)


if __name__ == "__main__":
    report = run()
    out = EXP_DIR / "PARITY_P1P2_REPORT.md"
    out.write_text(report, encoding="utf-8")
    print(f"wrote {out}")
    for line in report.splitlines():
        if line.startswith("- **P1") or line.startswith("- **P2") or line.startswith("- P1 verdict") or line.startswith("- P2 verdict"):
            print(line)
