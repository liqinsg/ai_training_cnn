#!/usr/bin/env python3
"""Phase 3.3 — Baseline dataset build + XGBoost baseline sanity run.

Executable reference for Doc 08 (`docs/phase3_3/08_DATASET_AND_LABEL_SPECIFICATION.md`).
Implements only the FROZEN dataset/label decisions (Owner 2026-11-16):

  OPEN-01  target          : binary classification, 1 = UP, 0 = NON-UP
  OPEN-02  horizon         : 6 completed M15 consecutive bars
  OPEN-03  label formula   : R_{t,6} = Close_{t+6}/Close_t - 1 ; 1 if R > 0 else 0
  OPEN-04  eligibility     : strict — drop warm-up NaN rows row-wise (no
                             interpolation / ffill / bfill / fillna(0) / gap pad);
                             label must exist; the 6 forward bars must be
                             contiguous M15 steps
  OPEN-04b support baseline: >= 1,000 samples per class; majority share <= 70%

Stages
------
1. Ingestion & alignment  — OANDA M15 candles (env only via ``config_oanda``);
                            the unclosed last candle is trimmed by the canonical
                            ``DataFetcher`` path.
2. Feature & label        — the frozen 33-column Feature Contract
                            (``ml.feature_contract.build_features``) + OPEN-02/03.
3. Strict eligibility     — OPEN-04, with exclusion accounting.
4. Baseline training      — XGBoost + time-ordered CV, reporting
                            Accuracy / Precision / Recall / confusion matrix.

Boundaries (Doc 08 §11)
-----------------------
* Research baseline only — NOT the Doc 09 experiment protocol. The split / CV
  below is a leakage-safe *sanity* default (fold-local scaling, no shuffle); the
  purge/embargo design remains Doc 09.
* No production training, no artifact write/overwrite, no live wiring.
  Outputs land **only** under ``experiments/phase3_3_baseline/``.

Run:  python3 phase3_3_baseline.py [--count 5000] [--pairs EUR_USD,USD_JPY]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import xgboost as xgb  # noqa: E402
from sklearn.metrics import (  # noqa: E402
    accuracy_score,
    confusion_matrix,
    precision_score,
    recall_score,
)
from sklearn.model_selection import TimeSeriesSplit  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

import config  # noqa: E402
from config_oanda import get_oanda_profile  # noqa: E402
from data_pipeline import DataFetcher  # noqa: E402
from ml.feature_contract import (  # noqa: E402
    ORDERED_FEATURES,
    build_features,
    validate_candles,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("phase3_3_baseline")

# ── FROZEN baseline parameters (OPEN-01..OPEN-04b, Owner 2026-11-16) ──────────
HORIZON_BARS = 6               # OPEN-02
LABEL_THRESHOLD = 0.0          # OPEN-03 (zero-threshold)
BAR_MINUTES = 15               # M15
MIN_SUPPORT_PER_CLASS = 1000   # OPEN-04b
MAX_MAJORITY_SHARE = 0.70      # OPEN-04b
GRANULARITY = "M15"

# ── Baseline run defaults (research only) ────────────────────────────────────
DEFAULT_COUNT = 5000           # OANDA v20 InstrumentsCandles hard maximum
TRAIN_FRACTION = 0.80          # simple chronological split (Doc 09 owns purge/embargo)
CV_SPLITS = 5
RANDOM_STATE = 42

OUT_DIR = BASE_DIR / "experiments" / "phase3_3_baseline"


# ─────────────────────────────── ingestion ───────────────────────────────

class _CountingAPI:
    """Proxy around the OANDA client that records how many candles the last
    InstrumentsCandles response contained.

    ``DataFetcher`` trims the unclosed last candle internally, so the raw count
    is otherwise invisible; capturing it here keeps the canonical fetch path
    untouched while making the exclusion accounting exact.
    """

    def __init__(self, api):
        self._api = api
        self.last_raw_count = 0

    def request(self, endpoint):
        resp = self._api.request(endpoint)
        if isinstance(resp, dict) and "candles" in resp:
            self.last_raw_count = len(resp["candles"])
        return resp


def ingest_pair(fetcher: DataFetcher, proxy: _CountingAPI, instrument: str, count: int) -> Tuple[pd.DataFrame, int, int]:
    """Fetch one instrument's M15 history. Returns (closed_candles, n_raw, n_unclosed)."""
    df = fetcher.fetch(instrument, instrument, count=count, granularity=GRANULARITY)
    n_raw = proxy.last_raw_count
    n_closed = len(df)
    n_unclosed = max(n_raw - n_closed, 0)
    return df, n_raw, n_unclosed


# ─────────────────────────────── features & labels ───────────────────────────────

def build_pair_dataset(
    df: pd.DataFrame, instrument: str, n_raw: int, n_unclosed: int
) -> Tuple[pd.DataFrame, Dict[str, int]]:
    """Features (33 frozen columns) + OPEN-02/03 label + OPEN-04 eligibility.

    Returns the eligible frame and this instrument's exclusion accounting.
    """
    n_closed = len(df)
    if n_closed == 0:
        raise ValueError(f"{instrument}: no closed candles")

    validate_candles(df)                      # explicit input-contract alignment
    feats = build_features(df)                # exactly ORDERED_FEATURES, warm-up = NaN

    close = df["Close"].astype(float)
    forward_return = close.shift(-HORIZON_BARS) / close - 1.0     # R_{t,6}
    label = pd.Series(
        np.where(forward_return > LABEL_THRESHOLD, 1.0, 0.0), index=df.index
    )
    label[forward_return.isna()] = np.nan    # horizon target unavailable

    # Forward-window contiguity: each of the 6 forward bars is an exact M15 step.
    idx = df.index
    minutes = np.full(n_closed, np.nan)
    if n_closed > 1:
        minutes[1:] = np.diff(idx.asi8) / (60.0 * 1e9)
    step_ok = np.isclose(minutes, BAR_MINUTES, atol=1e-9)          # minutes[0] -> False
    forward_ok = np.ones(n_closed, dtype=bool)
    for k in range(1, HORIZON_BARS + 1):
        shifted = np.zeros(n_closed, dtype=bool)
        if n_closed > k:
            shifted[: n_closed - k] = step_ok[k:]
        forward_ok &= shifted

    warmup_nan = feats.isna().any(axis=1).to_numpy()               # any of the 33 is NaN
    no_label = label.isna().to_numpy()
    label_or_gap = no_label | (~forward_ok)

    eligible_mask = (~warmup_nan) & (~label_or_gap)

    accounting = {
        "n_raw": int(n_raw),
        "n_dropped_unclosed": int(n_unclosed),
        "n_closed": int(n_closed),
        "n_dropped_warmup_nan": int(warmup_nan.sum()),
        "n_dropped_label_or_gap": int((~warmup_nan & label_or_gap).sum()),
        "n_eligible": int(eligible_mask.sum()),
        "n_up": int((label.to_numpy()[eligible_mask] == 1).sum()),
        "n_non_up": int((label.to_numpy()[eligible_mask] == 0).sum()),
    }

    elig = feats.loc[eligible_mask].copy()
    elig.insert(0, "timestamp", idx[eligible_mask])
    elig.insert(1, "instrument", instrument)
    elig["label"] = label.to_numpy()[eligible_mask].astype(int)
    return elig, accounting


# ─────────────────────────────── fingerprint ───────────────────────────────

def dataset_fingerprint(pooled: pd.DataFrame) -> str:
    """SHA-256 over the ordered (timestamp, instrument, 33 features, label) block."""
    h = hashlib.sha256()
    ts = pooled["timestamp"].astype("int64").to_numpy()
    h.update(np.ascontiguousarray(ts).tobytes())
    h.update("\n".join(pooled["instrument"].astype(str)).encode("utf-8"))
    h.update(np.ascontiguousarray(pooled[ORDERED_FEATURES].to_numpy(float)).tobytes())
    h.update(np.ascontiguousarray(pooled["label"].to_numpy(int)).tobytes())
    return h.hexdigest()


# ─────────────────────────────── baseline model ───────────────────────────────

def _make_model() -> "xgb.XGBClassifier":
    return xgb.XGBClassifier(
        n_estimators=200,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=RANDOM_STATE,
        eval_metric="logloss",
    )


def _metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, object]:
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, pos_label=1, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, pos_label=1, zero_division=0)),
        "tn": int(cm[0, 0]),
        "fp": int(cm[0, 1]),
        "fn": int(cm[1, 0]),
        "tp": int(cm[1, 1]),
        "n": int(len(y_true)),
    }


def run_baseline(pooled: pd.DataFrame) -> Dict[str, object]:
    """Time-ordered 80/20 holdout + time-ordered CV on the training portion.

    Scaling is fold-local (fit on fold-train only) — the leakage-safe default;
    purge/embargo is out of scope here (Doc 09).
    """
    ordered = pooled.sort_values(["timestamp", "instrument"], kind="mergesort").reset_index(drop=True)
    X = ordered[ORDERED_FEATURES].to_numpy(float)
    y = ordered["label"].to_numpy(int)
    n = len(ordered)
    split = int(n * TRAIN_FRACTION)
    X_tr, y_tr = X[:split], y[:split]
    X_te, y_te = X[split:], y[split:]

    folds: List[Dict[str, object]] = []
    tscv = TimeSeriesSplit(n_splits=CV_SPLITS)
    for tr_idx, va_idx in tscv.split(X_tr):
        scaler = StandardScaler().fit(X_tr[tr_idx])
        model = _make_model().fit(scaler.transform(X_tr[tr_idx]), y_tr[tr_idx])
        pred = model.predict(scaler.transform(X_tr[va_idx]))
        folds.append(_metrics(y_tr[va_idx], pred))

    scaler = StandardScaler().fit(X_tr)
    model = _make_model().fit(scaler.transform(X_tr), y_tr)
    holdout = _metrics(y_te, model.predict(scaler.transform(X_te)))

    importances = sorted(
        zip(ORDERED_FEATURES, model.feature_importances_.tolist()),
        key=lambda kv: kv[1],
        reverse=True,
    )

    return {
        "n_total": n,
        "n_train": int(len(y_tr)),
        "n_test": int(len(y_te)),
        "train_up_share": float(y_tr.mean()),
        "test_up_share": float(y_te.mean()),
        "cv_folds": folds,
        "holdout": holdout,
        "importances": importances,
        "split_timestamp": str(ordered["timestamp"].iloc[split]) if 0 < split < n else None,
    }


# ─────────────────────────────── reporting ───────────────────────────────

def _env_identity() -> List[str]:
    lines = [
        f"- Python: {sys.version.split()[0]}",
        f"- numpy: {np.__version__} | pandas: {pd.__version__}",
        f"- xgboost: {xgb.__version__}",
    ]
    try:
        import sklearn

        lines.append(f"- scikit-learn: {sklearn.__version__}")
    except Exception:  # noqa: BLE001
        lines.append("- scikit-learn: <not importable>")
    return lines


def _fmt_pct(x: float) -> str:
    return f"{x * 100:.2f}%"


def log_exclusion_accounting(per_pair: List[Tuple[str, Dict[str, int]]], total: Dict[str, int]) -> None:
    logger.info("")
    logger.info("=" * 78)
    logger.info("EXCLUSION ACCOUNTING (raw → eligible)")
    logger.info("=" * 78)
    header = f"{'instrument':<10} {'raw':>6} {'-open':>6} {'warmup':>7} {'lbl/gap':>8} {'elig':>7} {'UP':>6} {'NONUP':>6}"
    logger.info(header)
    logger.info("-" * len(header))
    for name, a in per_pair:
        logger.info(
            f"{name:<10} {a['n_raw']:>6} {a['n_dropped_unclosed']:>6} "
            f"{a['n_dropped_warmup_nan']:>7} {a['n_dropped_label_or_gap']:>8} "
            f"{a['n_eligible']:>7} {a['n_up']:>6} {a['n_non_up']:>6}"
        )
    logger.info("-" * len(header))
    logger.info(
        f"{'TOTAL':<10} {total['n_raw']:>6} {total['n_dropped_unclosed']:>6} "
        f"{total['n_dropped_warmup_nan']:>7} {total['n_dropped_label_or_gap']:>8} "
        f"{total['n_eligible']:>7} {total['n_up']:>6} {total['n_non_up']:>6}"
    )
    logger.info("=" * 78)


def _support_verdict(total: Dict[str, int]) -> Dict[str, object]:
    up, non_up = total["n_up"], total["n_non_up"]
    n = up + non_up
    minority = min(up, non_up)
    majority_share = (max(up, non_up) / n) if n else float("nan")
    return {
        "min_class_count": minority,
        "majority_share": majority_share,
        "support_ok": minority >= MIN_SUPPORT_PER_CLASS,
        "imbalance_ok": (majority_share <= MAX_MAJORITY_SHARE) if n else False,
    }


def write_report(
    per_pair: List[Tuple[str, Dict[str, int]]],
    total: Dict[str, int],
    fingerprint: str,
    baseline: Dict[str, object],
    pairs: List[str],
    count: int,
) -> Path:
    support = _support_verdict(total)
    L: List[str] = []
    L.append("# Phase 3.3 — Baseline Dataset & Model Report")
    L.append("")
    L.append("**Document:** `docs/phase3_3/08_DATASET_AND_LABEL_SPECIFICATION.md` (DRAFT, `OPEN-01`–`OPEN-04b` FROZEN)")
    L.append("**Nature:** research baseline sanity run — **not** the Doc 09 experiment protocol; not an approval; no artifact written.")
    L.append("")
    L.append("## 0. Run identity")
    L.extend(_env_identity())
    L.append(f"- instruments: `{', '.join(pairs)}`")
    L.append(f"- requested bars per instrument: {count} | granularity: {GRANULARITY}")
    L.append(f"- label fingerprint (sha256): `{fingerprint}`")
    L.append("")
    L.append("## 1. Frozen parameters in force")
    L.append("")
    L.append("| Decision | Value |")
    L.append("|---|---|")
    L.append("| `OPEN-01` target | binary, 1 = UP / 0 = NON-UP |")
    L.append(f"| `OPEN-02` horizon | {HORIZON_BARS} completed M15 bars |")
    L.append(f"| `OPEN-03` label | `Close_(t+{HORIZON_BARS})/Close_t - 1 > {LABEL_THRESHOLD}` |")
    L.append("| `OPEN-04` eligibility | drop warm-up NaN rows; label present; 6 forward bars contiguous (no interpolation / ffill / bfill / fillna0 / gap pad) |")
    L.append(f"| `OPEN-04b` support | >= {MIN_SUPPORT_PER_CLASS} per class; majority share <= {_fmt_pct(MAX_MAJORITY_SHARE)} |")
    L.append("| Feature Contract | frozen 33 `ORDERED_FEATURES`; FCID `FCV2-bffdb0005083f95e` |")
    L.append("")
    L.append("## 2. Exclusion accounting (raw → eligible)")
    L.append("")
    L.append("| instrument | raw | −unclosed | −warm-up NaN | −label/gap | eligible | UP | NON-UP |")
    L.append("|---|---|---|---|---|---|---|---|")
    for name, a in per_pair:
        L.append(
            f"| {name} | {a['n_raw']} | {a['n_dropped_unclosed']} | {a['n_dropped_warmup_nan']} | "
            f"{a['n_dropped_label_or_gap']} | {a['n_eligible']} | {a['n_up']} | {a['n_non_up']} |"
        )
    L.append(
        f"| **TOTAL** | **{total['n_raw']}** | **{total['n_dropped_unclosed']}** | **{total['n_dropped_warmup_nan']}** | "
        f"**{total['n_dropped_label_or_gap']}** | **{total['n_eligible']}** | **{total['n_up']}** | **{total['n_non_up']}** |"
    )
    L.append("")
    L.append("Bucket priority: warm-up NaN first, then label-unavailable / non-contiguous; buckets are disjoint.")
    L.append("")
    L.append("## 3. `OPEN-04b` support baseline")
    L.append("")
    L.append(f"- smallest class: **{support['min_class_count']}** (threshold {MIN_SUPPORT_PER_CLASS}) → "
             f"**{'PASS' if support['support_ok'] else 'FAIL'}**")
    share = support["majority_share"]
    share_s = "n/a" if not np.isfinite(share) else _fmt_pct(share)
    L.append(f"- majority-class share: **{share_s}** (cap {_fmt_pct(MAX_MAJORITY_SHARE)}) → "
             f"**{'PASS' if support['imbalance_ok'] else 'FAIL'}**")
    L.append("")
    L.append("## 4. Baseline model (XGBoost) — sanity run only")
    L.append("")
    L.append(f"- ordered 80/20 chronological holdout; CV = `TimeSeriesSplit(n_splits={CV_SPLITS})` on the training portion.")
    L.append("- scaler is fit **fold-locally** (leakage-safe default); purge/embargo is Doc 09.")
    L.append(f"- total {baseline['n_total']} | train {baseline['n_train']} | test {baseline['n_test']} "
             f"| split at {baseline['split_timestamp']}")
    L.append(f"- UP share — train {_fmt_pct(baseline['train_up_share'])} | test {_fmt_pct(baseline['test_up_share'])}")
    L.append("")
    L.append("### Cross-validation (mean ± std over folds)")
    L.append("")
    L.append("| metric | mean | std |")
    L.append("|---|---|---|")
    for key in ("accuracy", "precision", "recall"):
        vals = np.array([f[key] for f in baseline["cv_folds"]], dtype=float)
        L.append(f"| {key} | {vals.mean():.4f} | {vals.std():.4f} |")
    L.append("")
    L.append("| fold | n | accuracy | precision | recall |")
    L.append("|---|---|---|---|---|")
    for i, f in enumerate(baseline["cv_folds"], 1):
        L.append(f"| {i} | {f['n']} | {f['accuracy']:.4f} | {f['precision']:.4f} | {f['recall']:.4f} |")
    L.append("")
    L.append("### Holdout")
    L.append("")
    h = baseline["holdout"]
    L.append(f"- Accuracy: **{h['accuracy']:.4f}** | Precision (UP): **{h['precision']:.4f}** | Recall (UP): **{h['recall']:.4f}**")
    L.append("")
    L.append("| | predicted NON-UP | predicted UP |")
    L.append("|---|---|---|")
    L.append(f"| **actual NON-UP** | {h['tn']} | {h['fp']} |")
    L.append(f"| **actual UP** | {h['fn']} | {h['tp']} |")
    L.append("")
    L.append("### Top 10 features by importance")
    L.append("")
    L.append("| feature | importance |")
    L.append("|---|---|")
    for name, imp in baseline["importances"][:10]:
        L.append(f"| `{name}` | {imp:.4f} |")
    L.append("")
    L.append("## 5. Boundary")
    L.append("")
    L.append("- Baseline sanity run only; no Doc 09 experiment protocol, no purge/embargo, no artifact, no live wiring.")
    L.append("- Outputs written only under `experiments/phase3_3_baseline/`.")
    L.append("- Instrument whitelist / pooled-vs-per-pair / dataset fingerprint remain `[PENDING DATA PROFILING SCAN]`.")
    L.append("")
    out = OUT_DIR / "BASELINE_REPORT.md"
    out.write_text("\n".join(L), encoding="utf-8")
    return out


def write_accounting_csv(per_pair: List[Tuple[str, Dict[str, int]]], total: Dict[str, int]) -> Path:
    rows = [{"instrument": name, **a} for name, a in per_pair]
    rows.append({"instrument": "TOTAL", **total})
    out = OUT_DIR / "exclusion_accounting.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    return out


# ─────────────────────────────── main ───────────────────────────────

def _parse_args(argv: Optional[List[str]]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Phase 3.3 baseline dataset & model run (research only).")
    p.add_argument("--count", type=int, default=DEFAULT_COUNT,
                   help=f"bars per instrument (OANDA max 5000; default {DEFAULT_COUNT})")
    p.add_argument("--pairs", type=str, default=None,
                   help="comma-separated instrument whitelist (default: config.DEFAULT_PAIRS)")
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    pairs = (
        [p.strip().upper() for p in args.pairs.split(",") if p.strip()]
        if args.pairs
        else list(config.DEFAULT_PAIRS)
    )
    if args.count > 5000:
        raise SystemExit("--count exceeds the OANDA v20 maximum of 5000 candles")

    profile = get_oanda_profile()
    api = profile["api"]
    if api is None:
        raise SystemExit("OANDA API client unavailable — check config_oanda credentials")

    logger.info(f"Phase 3.3 baseline | env={profile['env']} | pairs={pairs} | count={args.count}")
    proxy = _CountingAPI(api)
    fetcher = DataFetcher(use_oanda=True, oanda_api=proxy, oanda_granularity=GRANULARITY)

    per_pair: List[Tuple[str, Dict[str, int]]] = []
    frames: List[pd.DataFrame] = []
    min_bars = HORIZON_BARS + 1
    for instrument in pairs:
        try:
            df, n_raw, n_unclosed = ingest_pair(fetcher, proxy, instrument, args.count)
            if len(df) < min_bars:
                logger.warning(f"  ⚠️ {instrument}: only {len(df)} closed bars → skipped")
                continue
            elig, accounting = build_pair_dataset(df, instrument, n_raw, n_unclosed)
            per_pair.append((instrument, accounting))
            logger.info(
                f"  ✅ {instrument}: raw={accounting['n_raw']} eligible={accounting['n_eligible']} "
                f"(UP={accounting['n_up']} / NON-UP={accounting['n_non_up']})"
            )
            if accounting["n_eligible"] > 0:
                frames.append(elig)
        except Exception as exc:  # noqa: BLE001 — log and continue to next instrument
            logger.error(f"  ❌ {instrument} failed: {type(exc).__name__}: {exc}")

    if not frames:
        raise SystemExit("No eligible samples produced — nothing to report.")

    total = {k: sum(a[k] for _, a in per_pair) for k in per_pair[0][1]}
    log_exclusion_accounting(per_pair, total)

    pooled = pd.concat(frames, ignore_index=True)
    pooled = pooled.sort_values(["timestamp", "instrument"], kind="mergesort").reset_index(drop=True)
    fingerprint = dataset_fingerprint(pooled)

    support = _support_verdict(total)
    logger.info("")
    logger.info(f"OPEN-04b support: smallest class={support['min_class_count']} "
                f"({'PASS' if support['support_ok'] else 'FAIL'}) | "
                f"majority share={_fmt_pct(support['majority_share'])} "
                f"({'PASS' if support['imbalance_ok'] else 'FAIL'})")
    logger.info(f"dataset fingerprint (sha256): {fingerprint}")

    baseline = run_baseline(pooled)
    h = baseline["holdout"]
    logger.info("")
    logger.info("BASELINE HOLD OUT — Accuracy %.4f | Precision(UP) %.4f | Recall(UP) %.4f",
                h["accuracy"], h["precision"], h["recall"])
    cv = baseline["cv_folds"]
    logger.info("BASELINE CV — Accuracy %.4f±%.4f | Precision %.4f±%.4f | Recall %.4f±%.4f",
                np.mean([f["accuracy"] for f in cv]), np.std([f["accuracy"] for f in cv]),
                np.mean([f["precision"] for f in cv]), np.std([f["precision"] for f in cv]),
                np.mean([f["recall"] for f in cv]), np.std([f["recall"] for f in cv]))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = write_report(per_pair, total, fingerprint, baseline, pairs, args.count)
    csv_path = write_accounting_csv(per_pair, total)
    (OUT_DIR / "run_identity.json").write_text(
        json.dumps(
            {
                "fingerprint": fingerprint,
                "count_requested": args.count,
                "pairs": pairs,
                "total": total,
                "support": support,
                "holdout": h,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    logger.info(f"wrote {report}")
    logger.info(f"wrote {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
