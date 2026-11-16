#!/usr/bin/env python3
"""Phase 3.3 — Doc 09 experiment harness (research / Demo preparation only).

Implements the FROZEN protocol in
``docs/phase3_3/09_EXPERIMENT_EXECUTION_PLAN.md`` (Revision R4, Owner-accepted
2026-11-16). This is the executable translation of that document — *not* the
``phase3_3_baseline.py`` sanity run (see Doc 09 §13).

What it implements (Doc 09 section in brackets)
----------------------------------------------
* Module 1 — load & filter (§4.7, §5): pairs = ``mc_data.yml`` ``pairs`` ∩
  ``config_bot`` whitelist, OANDA-native; strict Doc 08 eligibility reused.
* Module 2 — walk-forward splitter on the *unique timestamp grid* (§4.1–§4.6):
  holdout = last 20% of unique timestamps; dev = the rest; ``seed_len`` = 30% of
  dev; K = 5 deterministic folds; **purge = H = 6 bars (trailing)**; embargo = 0;
  the last H development timestamps are dropped from dev evaluation.
* Module 3 — baseline / model sandbox (§6, §6.0, §7): B0a (majority constant),
  B0b (deterministic persistence), B1 (reference set ``R``), B2 (``R ∪ {c}``),
  B3 (all − c), B4 (all), plus per-candidate ``{c}`` and per-group models.
  Learner = logistic regression with a **fold-local** ``StandardScaler``; the
  learner is already probabilistic, so per ``PRIOR-C1`` **no** post-hoc
  calibrator is applied.
* Inference (§8): moving-block bootstrap on the timestamp grid, blocks
  **synchronized across instruments**, ``B`` replicates, block-length
  sensitivity {6,12,24,48}; BH-FDR per family F1/F2/F3. All significance output
  is tagged ``NOT VERIFIED — provisional`` (``L_b`` is an unvalidated prior).

Boundaries (Doc 09 §14)
-----------------------
* Research only. **No** production training, **no** write to the production
  bundle, **no** live/READY wiring, **no** trading-behaviour change.
* Outputs land only under ``experiments/phase3_3_demo/<run_id>/``.
* Running this harness (fetching OANDA data, in-fold training, writing research
  outputs) requires a **separate explicit Owner execution authorization**; the
  Doc 09 freeze enables building the harness only.

Run:
  python3 phase3_3_demo.py --self-test          # offline, no OANDA, no network
  python3 phase3_3_demo.py --count 5000 --profile 2
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import yaml

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

from ml.feature_contract import ORDERED_FEATURES  # noqa: E402
from phase3_3_baseline import (  # noqa: E402
    _CountingAPI,
    build_pair_dataset,
    dataset_fingerprint,
    ingest_pair,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("phase3_3_demo")

# ── FROZEN protocol parameters (Doc 09 §2–§8) ────────────────────────────────
H = 6                      # OPEN-02 horizon / label span (bars)
PURGE_BARS = 6             # §4.3 = H (trailing, one-sided)
EMBARGO_BARS = 0           # §4.4
HOLDOUT_FRACTION = 0.20    # §12 OPEN-05
N_FOLDS = 5                # §4.2
INITIAL_TRAIN_FRACTION = 0.30   # §4.2 seed_len
REFERENCE_FEATURES: Tuple[str, ...] = ("return_15m",)   # §6.1 PRIOR-R1
LABEL_THRESHOLD = 0.0      # OPEN-03
BAR_MINUTES = 15           # M15
GRANULARITY = "M15"
DEFAULT_COUNT = 5000       # OANDA v20 max candles per request
ENV_COUNT_KEY = "PHASE33_DEMO_COUNT"   # run.env override (loaded via config_oanda)

# ── PRIOR (Agent-proposed, §8.3 / §12) ───────────────────────────────────────
BOOTSTRAP_B = 2000
BLOCK_LENGTHS: Tuple[int, ...] = (6, 12, 24, 48)
BH_Q = 0.05
RANDOM_STATE = 42

PRIMARY = "roc_auc"
PROVISIONAL = "NOT VERIFIED — provisional"

OUT_ROOT = BASE_DIR / "experiments" / "phase3_3_demo"

FEATURE_GROUPS: Dict[str, Tuple[str, ...]] = {
    "return": ("return_15m", "return_45m", "return_90m", "return_3h", "log_return_15m"),
    "horizon_vol": ("horizon_vol_3h", "horizon_vol_6h", "horizon_vol_12h"),
    "candle": ("body", "upper_wick", "lower_wick", "range", "direction"),
    "atr": ("atr", "atr_pct", "atr_ecdf_50bar", "atr_ma", "atr_above_sma14", "atr_ratio"),
    "rsi": ("rsi", "rsi_slope_45m"),
    "adx": ("adx",),
    "macd": ("macd", "macd_signal", "macd_hist"),
    "distance": ("dist_high_6h", "dist_low_6h", "dist_high_12h", "dist_low_12h",
                 "dist_high_24h", "dist_low_24h"),
    "time": ("utc_hour", "utc_day_of_week"),
}


# ══════════════════════════════ Module 1 — load & filter ══════════════════════

def _to_oanda_native(symbol: str) -> str:
    """`EURUSD` → `EUR_USD`; already-native names pass through unchanged."""
    s = str(symbol).strip().upper()
    if "_" in s:
        return s
    if len(s) == 6:
        return f"{s[:3]}_{s[3:]}"
    return s


def _whitelist_sources() -> Tuple[List[str], Dict[str, List[str]], str]:
    """Return (DEFAULT_PAIRS, WHITELIST, source). Prefers `config_bot`, falls
    back to reading `forex_pairs.json` (the file `config_bot` loads)."""
    try:
        import config_bot  # noqa: PLC0415 — optional, avoids import cost when unused

        default_pairs = list(getattr(config_bot, "DEFAULT_PAIRS", []) or [])
        whitelist = {str(k): list(v) for k, v in (getattr(config_bot, "WHITELIST", {}) or {}).items()}
        if default_pairs or whitelist:
            return default_pairs, whitelist, "config_bot"
    except Exception as exc:  # noqa: BLE001 — fall back to the raw file
        logger.warning("config_bot import unavailable (%s) — reading forex_pairs.json", exc)
    fp = json.loads((BASE_DIR / "forex_pairs.json").read_text(encoding="utf-8"))
    return list(fp.get("DEFAULT_PAIRS", [])), dict(fp.get("WHITELIST", {})), "forex_pairs.json"


def resolve_universe(profile: Optional[int]) -> Dict[str, object]:
    """Universe = (mc_data.yml pairs) ∩ (config_bot whitelist), OANDA-native."""
    md = yaml.safe_load((BASE_DIR / "mc_data.yml").read_text(encoding="utf-8")) or {}
    md_native = sorted({_to_oanda_native(p) for p in (md.get("pairs") or [])})

    default_pairs, whitelist, source = _whitelist_sources()
    if profile is not None:
        allowed = {str(p).upper() for p in whitelist.get(str(profile), default_pairs)}
    else:
        allowed = {str(p).upper() for p in default_pairs}
        for bucket in whitelist.values():
            allowed.update(str(p).upper() for p in bucket)

    universe = sorted(set(md_native) & allowed)
    return {
        "source": source,
        "profile": profile,
        "mc_data_pairs": md_native,
        "whitelist": sorted(allowed),
        "universe": universe,
        "excluded_by_whitelist": sorted(set(md_native) - allowed),
        "whitelist_only": sorted(allowed - set(md_native)),
    }


# ══════════════════════════════ Module 2 — splitter ═══════════════════════════

@dataclass
class Fold:
    index: int
    train_lo: int          # position in T (inclusive)
    train_hi: int          # position in T (exclusive)
    test_lo: int
    test_hi: int
    purge_bars: int

    def as_dict(self) -> Dict[str, int]:
        return {
            "fold": self.index,
            "train_lo": self.train_lo, "train_hi": self.train_hi,
            "test_lo": self.test_lo, "test_hi": self.test_hi,
            "purge_bars": self.purge_bars,
        }


@dataclass
class SplitPlan:
    n_T: int
    n_holdout: int
    n_dev: int
    seed_len: int
    edges: List[int]
    folds: List[Fold] = field(default_factory=list)

    def as_dict(self) -> Dict[str, object]:
        return {
            "n_T": self.n_T,
            "n_holdout": self.n_holdout,
            "n_dev": self.n_dev,
            "seed_len": self.seed_len,
            "edges": self.edges,
            "purge_bars": PURGE_BARS,
            "embargo_bars": EMBARGO_BARS,
            "folds": [f.as_dict() for f in self.folds],
        }


def _linspace_int(a: int, b: int, n: int) -> List[int]:
    """`n` integer points from `a` to `b` inclusive (endpoints exact)."""
    raw = np.linspace(a, b, n)
    edges = np.rint(raw).astype(int).tolist()
    edges[0], edges[-1] = int(a), int(b)
    return edges


def compute_split_plan(n_T: int) -> SplitPlan:
    """Deterministic walk-forward plan over the unique-timestamp grid (§4.2)."""
    if n_T < N_FOLDS + 2:
        raise ValueError(f"timestamp grid too small (n_T={n_T}) for K={N_FOLDS} folds")
    n_holdout = int(math.floor(HOLDOUT_FRACTION * n_T))
    n_dev = n_T - n_holdout
    seed_len = int(math.floor(INITIAL_TRAIN_FRACTION * n_dev))
    edges = _linspace_int(seed_len, n_dev, N_FOLDS + 1)

    folds: List[Fold] = []
    for k in range(1, N_FOLDS + 1):
        test_lo, test_hi = edges[k - 1], edges[k]
        if k == N_FOLDS:                      # §4.3 dev/holdout boundary purge
            test_hi -= PURGE_BARS
        train_hi = max(edges[k - 1] - PURGE_BARS, 0)
        folds.append(Fold(index=k, train_lo=0, train_hi=train_hi,
                          test_lo=test_lo, test_hi=test_hi, purge_bars=PURGE_BARS))

    plan = SplitPlan(n_T=n_T, n_holdout=n_holdout, n_dev=n_dev,
                     seed_len=seed_len, edges=edges, folds=folds)
    _assert_split(plan)
    return plan


def _assert_split(plan: SplitPlan) -> None:
    """Doc 09 §4.5 reproducibility assertions (fail closed)."""
    e = plan.edges
    assert e[0] == plan.seed_len and e[-1] == plan.n_dev, "edges must start at seed_len, end at n_dev"
    assert all(e[i] < e[i + 1] for i in range(len(e) - 1)), "edges must be strictly increasing"
    for k in range(1, len(e)):
        assert e[k] > e[k - 1], "empty test window"
    # folds are contiguous, disjoint, and (with the final purge) cover dev[seed_len:dev)
    for i, f in enumerate(plan.folds):
        if i > 0:
            assert f.test_lo == plan.folds[i - 1].test_hi or plan.folds[i - 1].index == N_FOLDS, \
                "test windows must be contiguous and non-overlapping"
        assert f.train_hi <= f.test_lo, "train must not extend into the test window"
        assert f.test_lo - f.train_hi >= PURGE_BARS, "purge gap violated"
        assert f.test_hi > f.test_lo, "empty test window"


def window_mask(T: np.ndarray, lo: int, hi: Optional[int], pooled_ts: np.ndarray) -> np.ndarray:
    """Rows whose timestamp lies in `[T[lo], T[hi])` (half-open, `hi=None` → open)."""
    lo_v = T[lo]
    if hi is None:
        return pooled_ts >= lo_v
    return (pooled_ts >= lo_v) & (pooled_ts < T[hi])


# ══════════════════════════════ Module 3 — models & metrics ═══════════════════

@dataclass
class ModelSpec:
    key: str
    kind: str                  # "b0a" | "b0b" | "lr"
    features: Tuple[str, ...]
    role: str                  # B0a/B0b/B1/B2/B3/B4/standalone/group
    candidate: Optional[str] = None


def build_model_specs(candidates: Sequence[str], groups: Sequence[str]) -> List[ModelSpec]:
    allf = tuple(ORDERED_FEATURES)
    specs: List[ModelSpec] = [
        ModelSpec("B0a", "b0a", (), "B0a"),
        ModelSpec("B0b", "b0b", (), "B0b"),
        ModelSpec("B1", "lr", tuple(REFERENCE_FEATURES), "B1"),
        ModelSpec("B4", "lr", allf, "B4"),
    ]
    for c in candidates:
        specs.append(ModelSpec(f"B2:{c}", "lr", tuple(REFERENCE_FEATURES) + (c,), "B2", c))
        specs.append(ModelSpec(f"B3:{c}", "lr", tuple(f for f in allf if f != c), "B3", c))
        specs.append(ModelSpec(f"S:{c}", "lr", (c,), "standalone", c))
    for g in groups:
        specs.append(ModelSpec(f"G:{g}", "lr", tuple(FEATURE_GROUPS[g]), "group"))
    return specs


def _make_learner() -> LogisticRegression:
    return LogisticRegression(max_iter=1000, random_state=RANDOM_STATE)


def safe_auc(y: np.ndarray, s: np.ndarray) -> float:
    y = np.asarray(y)
    s = np.asarray(s, dtype=float)
    if y.size == 0 or np.unique(y).size < 2:
        return float("nan")
    if np.all(s == s[0]):          # constant score ⇒ no discrimination (B0a)
        return 0.5
    return float(roc_auc_score(y, s))


def safe_logloss(y: np.ndarray, p: np.ndarray) -> float:
    y = np.asarray(y)
    if y.size == 0 or np.unique(y).size < 2:
        return float("nan")
    return float(log_loss(y, np.clip(np.asarray(p, float), 1e-12, 1 - 1e-12), labels=[0, 1]))


def safe_brier(y: np.ndarray, p: np.ndarray) -> float:
    y = np.asarray(y)
    if y.size == 0:
        return float("nan")
    return float(brier_score_loss(y, np.clip(np.asarray(p, float), 0.0, 1.0)))


# ─────────────────────────── experiment core ───────────────────────────

@dataclass
class ExperimentData:
    pooled: pd.DataFrame
    X: np.ndarray                 # (n_rows, 33)
    y: np.ndarray                 # (n_rows,)
    ts_int: np.ndarray            # (n_rows,) int64 timestamps
    T: np.ndarray                 # unique sorted int64 timestamps
    split: SplitPlan
    pairs: List[str]


def prepare_pooled(pooled: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    pooled = pooled.reset_index(drop=True)
    X = pooled[ORDERED_FEATURES].to_numpy(float)
    y = pooled["label"].to_numpy(int)
    ts_int = pooled["timestamp"].astype("int64").to_numpy()
    return X, y, ts_int


def fit_fold_models(
    data: ExperimentData, specs: List[ModelSpec], fold: Fold
) -> Tuple[Dict[str, np.ndarray], np.ndarray, np.ndarray]:
    """Fit `specs` on fold `k`'s train window; return (preds, test_idx, y_test).

    `preds[key]` is a full-length array (NaN outside the test window).
    """
    T, ts_int, X, y = data.T, data.ts_int, data.X, data.y
    tr_mask = window_mask(T, fold.train_lo, fold.train_hi, ts_int)
    te_mask = window_mask(T, fold.test_lo, fold.test_hi, ts_int)
    tr_idx = np.flatnonzero(tr_mask)
    te_idx = np.flatnonzero(te_mask)

    preds: Dict[str, np.ndarray] = {}
    if tr_idx.size == 0 or te_idx.size == 0:
        for s in specs:
            preds[s.key] = np.full(len(y), np.nan)
        return preds, te_idx, y[te_idx]

    X_tr, y_tr = X[tr_idx], y[tr_idx]
    b0a_value = float(np.bincount(y_tr, minlength=2).argmax())
    b0b_col = data.pooled["b0b_up"].to_numpy(float) if "b0b_up" in data.pooled else None

    for s in specs:
        out = np.full(len(y), np.nan)
        if s.kind == "b0a":
            out[te_idx] = b0a_value
        elif s.kind == "b0b":
            if b0b_col is None:
                raise ValueError("B0b requires the 'b0b_up' column")
            out[te_idx] = b0b_col[te_idx]
        else:
            # each spec gets its own fold-local scaler (fit on train rows only)
            cols = [ORDERED_FEATURES.index(f) for f in s.features]
            sc = StandardScaler().fit(X_tr[:, cols])
            Xs_tr = sc.transform(X_tr[:, cols])
            Xs_te = sc.transform(X[te_idx][:, cols])
            model = _make_learner().fit(Xs_tr, y_tr)
            out[te_idx] = model.predict_proba(Xs_te)[:, 1]
        preds[s.key] = out
    return preds, te_idx, y[te_idx]


def fold_metrics(preds: Dict[str, np.ndarray], keys: Sequence[str],
                 te_idx: np.ndarray, y_te: np.ndarray) -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {}
    for k in keys:
        p = preds[k][te_idx]
        out[k] = {
            "roc_auc": safe_auc(y_te, p),
            "log_loss": safe_logloss(y_te, p),
            "brier": safe_brier(y_te, p),
        }
    return out


def per_pair_auc(pooled: pd.DataFrame, preds: Dict[str, np.ndarray], keys: Sequence[str],
                 te_idx: np.ndarray, y_te: np.ndarray) -> Dict[str, Dict[str, float]]:
    instr = pooled["instrument"].to_numpy()[te_idx]
    res: Dict[str, Dict[str, float]] = {}
    for k in keys:
        row: Dict[str, float] = {}
        for ins in sorted(set(instr)):
            m = instr == ins
            row[ins] = safe_auc(y_te[m], preds[k][te_idx][m])
        res[k] = row
    return res


# ─────────────────────────── inference (§8.3) ───────────────────────────

def moving_block_positions(n: int, L: int, rng: np.random.Generator) -> np.ndarray:
    if n <= 0:
        return np.array([], dtype=int)
    L = min(L, n)
    n_blocks = int(math.ceil(n / L))
    starts = rng.integers(0, n - L + 1, size=n_blocks)
    idx = np.concatenate([np.arange(s, s + L) for s in starts])[:n]
    return idx


def build_position_matrix(pooled: pd.DataFrame, ts_int: np.ndarray, instr_pos: Dict[str, int],
                          te_idx: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Matrix [n_ts, n_instr] of pooled row positions (−1 = absent)."""
    uniq, inv = np.unique(ts_int[te_idx], return_inverse=True)
    n_instr = len(instr_pos)
    M = np.full((len(uniq), n_instr), -1, dtype=np.int64)
    cols = np.array([instr_pos[i] for i in pooled["instrument"].to_numpy()[te_idx]], dtype=np.int64)
    M[inv, cols] = te_idx
    return M, uniq


def bh_fdr(pvals: Sequence[float]) -> np.ndarray:
    p = np.asarray(list(pvals), dtype=float)
    m = p.size
    if m == 0:
        return p
    order = np.argsort(p, kind="mergesort")
    ranked = p[order]
    adj = ranked * m / (np.arange(m) + 1.0)
    adj = np.minimum.accumulate(adj[::-1])[::-1]
    out = np.empty(m)
    out[order] = np.clip(adj, 0.0, 1.0)
    return out


# ══════════════════════════════ experiment driver ═════════════════════════════

def run_experiment(data: ExperimentData, specs: List[ModelSpec], contrasts: List[Tuple[str, str, str, str]],
                   boot_B: int, block_lengths: Sequence[int], evaluate_holdout: bool,
                   seed: int = RANDOM_STATE) -> Dict[str, object]:
    keys = [s.key for s in specs]
    n_folds = len(data.split.folds)

    # ── pass 1: fit every fold, store out-of-fold predictions per model ──
    preds: Dict[str, np.ndarray] = {k: np.full(len(data.y), np.nan) for k in keys}
    fold_preds: List[Dict[str, np.ndarray]] = []
    fold_metrics_all: List[Dict[str, Dict[str, float]]] = []
    fold_per_pair: List[Dict[str, Dict[str, float]]] = []
    fold_ts: List[np.ndarray] = []
    for fold in data.split.folds:
        fp, te_idx, y_te = fit_fold_models(data, specs, fold)
        for k in keys:
            preds[k][te_idx] = fp[k][te_idx]
        fold_preds.append(fp)
        fold_ts.append(np.unique(data.ts_int[te_idx]))
        fold_metrics_all.append(fold_metrics(fp, keys, te_idx, y_te))
        fold_per_pair.append(per_pair_auc(data.pooled, fp, keys, te_idx, y_te))
        logger.info("  fold %d/%d fitted (%d test rows)", fold.index, n_folds, te_idx.size)

    point = _aggregate(fold_metrics_all, keys)
    per_pair = _aggregate_per_pair(fold_per_pair, keys)

    # ── pass 2: synchronized moving-block bootstrap over folds ──
    inference: Dict[str, object] = {}
    if boot_B > 0 and contrasts:
        inference = _bootstrap(
            data, preds, contrasts, boot_B, block_lengths, seed,
        )

    holdout: Optional[Dict[str, object]] = None
    if evaluate_holdout:
        holdout = _evaluate_holdout_once(data, specs)

    return {
        "point": point,
        "per_pair": per_pair,
        "fold_metrics": fold_metrics_all,
        "fold_timestamps": fold_ts,
        "inference": inference,
        "holdout": holdout,
        "n_models": len(specs),
        "n_folds": n_folds,
    }


def _aggregate(fold_metrics_all: List[Dict[str, Dict[str, float]]],
               keys: Sequence[str]) -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {}
    for k in keys:
        row: Dict[str, float] = {}
        for metric in ("roc_auc", "log_loss", "brier"):
            vals = np.array([f[k][metric] for f in fold_metrics_all], dtype=float)
            vals = vals[np.isfinite(vals)]
            row[f"{metric}_mean"] = float(vals.mean()) if vals.size else float("nan")
            row[f"{metric}_std"] = float(vals.std()) if vals.size else float("nan")
        out[k] = row
    return out


def _aggregate_per_pair(fold_per_pair: List[Dict[str, Dict[str, float]]],
                        keys: Sequence[str]) -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {}
    for k in keys:
        row: Dict[str, float] = {}
        all_pairs = sorted({p for f in fold_per_pair for p in f[k]})
        for p in all_pairs:
            vals = np.array([f[k].get(p, float("nan")) for f in fold_per_pair], dtype=float)
            vals = vals[np.isfinite(vals)]
            row[p] = float(vals.mean()) if vals.size else float("nan")
        out[k] = row
    return out


def _bootstrap(data: ExperimentData, preds: Dict[str, np.ndarray],
               contrasts: List[Tuple[str, str, str, str]], boot_B: int,
               block_lengths: Sequence[int], seed: int) -> Dict[str, object]:
    instr_pos = {ins: i for i, ins in enumerate(data.pairs)}
    y = data.y
    folds = data.split.folds

    # precompute per-fold (position matrix, test index) once
    prepared = []
    for fold in folds:
        te_idx = np.flatnonzero(window_mask(data.T, fold.test_lo, fold.test_hi, data.ts_int))
        M, uniq = build_position_matrix(data.pooled, data.ts_int, instr_pos, te_idx)
        prepared.append({"M": M, "n_ts": M.shape[0], "te_idx": te_idx, "uniq": uniq})

    needed = sorted({m for _, _, a, b in contrasts for m in (a, b)})
    results: Dict[str, Dict[str, object]] = {}
    per_L: Dict[int, Dict[str, np.ndarray]] = {}

    for L in block_lengths:
        rng = np.random.default_rng(seed + L)
        acc = {name: np.empty(boot_B, dtype=float) for _, name, _, _ in contrasts}
        for b in range(boot_B):
            fold_delta: Dict[str, List[float]] = {name: [] for _, name, _, _ in contrasts}
            for prep in prepared:
                idx = moving_block_positions(prep["n_ts"], L, rng)
                rows = prep["M"][idx].ravel()
                rows = rows[rows >= 0]
                if rows.size == 0:
                    continue
                yk = y[rows]
                auc = {m: safe_auc(yk, preds[m][rows]) for m in needed}
                for _, name, a, bkey in contrasts:
                    av, bv = auc.get(a, float("nan")), auc.get(bkey, float("nan"))
                    if np.isfinite(av) and np.isfinite(bv):
                        fold_delta[name].append(av - bv)
            for _, name, _, _ in contrasts:
                vals = fold_delta[name]
                acc[name][b] = float(np.mean(vals)) if vals else float("nan")
            if (b + 1) % 200 == 0:
                logger.info("    bootstrap L_b=%d: %d/%d", L, b + 1, boot_B)
        per_L[L] = acc

    for _, name, a, bkey in contrasts:
        obs = _contrast_point(data, preds, a, bkey)
        entry: Dict[str, object] = {"contrast": f"{a} − {bkey}", "observed_delta": obs,
                                    "status": PROVISIONAL}
        for L in block_lengths:
            d = per_L[L][name]
            d = d[np.isfinite(d)]
            if d.size == 0:
                continue
            p_raw = float((d <= 0.0).mean())
            p_raw = max(p_raw, 1.0 / d.size)
            entry[f"p_raw_L{L}"] = p_raw
            entry[f"ci95_L{L}"] = [float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))]
            entry[f"delta_mean_L{L}"] = float(d.mean())
            entry[f"delta_std_L{L}"] = float(d.std())
        results[name] = entry

    return {
        "block_lengths": list(block_lengths),
        "B": boot_B,
        "primary_L_b": 2 * H,
        "results": results,
        "per_L_distributions": per_L,
        "caveat": PROVISIONAL,
    }


def _contrast_point(data: ExperimentData, preds: Dict[str, np.ndarray], a: str, b: str) -> float:
    """Point ΔAUC = mean over folds of (AUC_a − AUC_b) on stored OOF predictions."""
    vals = []
    for fold in data.split.folds:
        te_idx = np.flatnonzero(window_mask(data.T, fold.test_lo, fold.test_hi, data.ts_int))
        y = data.y[te_idx]
        av, bv = safe_auc(y, preds[a][te_idx]), safe_auc(y, preds[b][te_idx])
        if np.isfinite(av) and np.isfinite(bv):
            vals.append(av - bv)
    return float(np.mean(vals)) if vals else float("nan")


def _evaluate_holdout_once(data: ExperimentData, specs: List[ModelSpec]) -> Dict[str, object]:
    """Single, isolated holdout evaluation (§4.6). Never used for selection."""
    T = data.T
    mask = window_mask(T, data.split.n_dev, None, data.ts_int)
    te_idx = np.flatnonzero(mask)
    if te_idx.size == 0:
        return {"status": "EMPTY"}
    tr_mask = window_mask(T, 0, data.split.n_dev - PURGE_BARS, data.ts_int)
    tr_idx = np.flatnonzero(tr_mask)
    X_tr, y_tr = data.X[tr_idx], data.y[tr_idx]
    out: Dict[str, float] = {}
    b0a_value = float(np.bincount(y_tr, minlength=2).argmax())
    b0b_col = data.pooled["b0b_up"].to_numpy(float)
    for s in specs:
        if s.kind == "b0a":
            out[s.key] = safe_auc(data.y[te_idx], np.full(te_idx.size, b0a_value))
        elif s.kind == "b0b":
            out[s.key] = safe_auc(data.y[te_idx], b0b_col[te_idx])
        else:
            cols = [ORDERED_FEATURES.index(f) for f in s.features]
            sc = StandardScaler().fit(X_tr[:, cols])
            model = _make_learner().fit(sc.transform(X_tr[:, cols]), y_tr)
            p = model.predict_proba(sc.transform(data.X[te_idx][:, cols]))[:, 1]
            out[s.key] = safe_auc(data.y[te_idx], p)
    return {"status": "EVALUATED_ONCE", "roc_auc": out, "n": int(te_idx.size)}


# ══════════════════════════════ reporting ═════════════════════════════════════

def _git_identity() -> Dict[str, str]:
    def run(*a: str) -> str:
        try:
            return subprocess.run(["git", *a], cwd=BASE_DIR, capture_output=True,
                                  text=True, check=False).stdout.strip()
        except Exception:  # noqa: BLE001
            return ""

    return {
        "commit": run("rev-parse", "HEAD"),
        "branch": run("rev-parse", "--abbrev-ref", "HEAD"),
        "dirty": "dirty" if run("status", "--porcelain") else "clean",
    }


def _env_identity() -> Dict[str, str]:
    import sklearn  # noqa: PLC0415

    return {
        "python": sys.version.split()[0],
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scikit-learn": sklearn.__version__,
        "pyyaml": yaml.__version__,
    }


def _fmt(x: float) -> str:
    return "n/a" if x is None or not np.isfinite(x) else f"{x:.4f}"


def write_outputs(run_dir: Path, univ: Dict[str, object], data: ExperimentData,
                  fingerprint: str, results: Dict[str, object], contrasts: List[Tuple[str, str, str, str]],
                  command: str) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "RUN_IDENTITY.json").write_text(json.dumps({
        "git": _git_identity(), "env": _env_identity(),
        "dataset_fingerprint_sha256": fingerprint,
        "universe": univ,
        "protocol": "docs/phase3_3/09_EXPERIMENT_EXECUTION_PLAN.md R4 (FROZEN, Owner-accepted 2026-11-16)",
        "fcid": "FCV2-bffdb0005083f95e",
        "command": command,
    }, indent=2), encoding="utf-8")
    (run_dir / "SPLIT_PLAN.json").write_text(json.dumps(data.split.as_dict(), indent=2), encoding="utf-8")

    # baseline metrics table
    rows = []
    for k, m in results["point"].items():
        rows.append({"model": k, "roc_auc_mean": m["roc_auc_mean"], "roc_auc_std": m["roc_auc_std"],
                     "log_loss_mean": m["log_loss_mean"], "brier_mean": m["brier_mean"]})
    pd.DataFrame(rows).to_csv(run_dir / "MODEL_METRICS.csv", index=False)

    # inference table
    inf = results.get("inference") or {}
    if inf:
        fam_rows = []
        for _, name, a, b in contrasts:
            e = inf["results"].get(name)
            if not e:
                continue
            fam_rows.append({
                "contrast": name, "definition": e["contrast"],
                "observed_delta": e["observed_delta"],
                "p_raw_L6": e.get("p_raw_L6"), "p_raw_L12": e.get("p_raw_L12"),
                "p_raw_L24": e.get("p_raw_L24"), "p_raw_L48": e.get("p_raw_L48"),
                "status": PROVISIONAL,
            })
        pd.DataFrame(fam_rows).to_csv(run_dir / "CONTRASTS.csv", index=False)

    md: List[str] = ["# Phase 3.3 — Demo run (Doc 09 protocol)", ""]
    md.append(f"- protocol: `docs/phase3_3/09_EXPERIMENT_EXECUTION_PLAN.md` **R4 FROZEN**")
    md.append(f"- dataset fingerprint (sha256): `{fingerprint}`")
    md.append(f"- universe: {len(univ['universe'])} pairs — `{', '.join(univ['universe'])}`")
    md.append(f"- excluded by whitelist: `{', '.join(univ['excluded_by_whitelist']) or '—'}`")
    md.append(f"- models: {results['n_models']} | folds: {results['n_folds']}")
    md.append("")
    md.append("## Baseline / reference metrics (fold mean)")
    md.append("")
    md.append("| model | ROC-AUC | ±std | log-loss | Brier |")
    md.append("|---|---|---|---|---|")
    for k in ("B0a", "B0b", "B1", "B4"):
        m = results["point"].get(k, {})
        md.append(f"| `{k}` | {_fmt(m.get('roc_auc_mean', float('nan')))} | {_fmt(m.get('roc_auc_std', float('nan')))} "
                  f"| {_fmt(m.get('log_loss_mean', float('nan')))} | {_fmt(m.get('brier_mean', float('nan')))} |")
    md.append("")
    if inf:
        md.append("## Statistical inference — `NOT VERIFIED — provisional`")
        md.append("")
        md.append(f"Moving-block bootstrap, blocks synchronized across instruments, `B = {inf['B']}`, "
                  f"primary `L_b = {inf['primary_L_b']}`, sensitivity {inf['block_lengths']}.")
        md.append("Significance is **not** claimed: `L_b` is an unvalidated prior (Doc 09 §8.3).")
        md.append("")
        md.append("| contrast | ΔAUC (obs) | p (L_b=12) | 95% CI (L_b=12) | status |")
        md.append("|---|---|---|---|---|")
        for _, name, _, _ in contrasts:
            e = inf["results"].get(name)
            if not e:
                continue
            ci = e.get("ci95_L12")
            ci_s = f"[{ci[0]:.4f}, {ci[1]:.4f}]" if ci else "n/a"
            p12 = e.get("p_raw_L12")
            md.append(f"| `{name}` | {_fmt(e['observed_delta'])} | {_fmt(p12) if p12 is not None else 'n/a'} "
                      f"| {ci_s} | `{PROVISIONAL}` |")
        md.append("")
    md.append("## Holdout")
    ho = results.get("holdout")
    md.append("")
    md.append("`HOLDOUT: NOT EVALUATED` (default — Doc 09 §4.6 discipline; use `--evaluate-holdout` only after freeze)."
              if not ho else f"`HOLDOUT: {ho.get('status')}` — n={ho.get('n')}")
    md.append("")
    md.append("## Boundary")
    md.append("")
    md.append("- Research Demo only. No production training, no artifact write to the production "
              "bundle, no READY / live wiring.")
    md.append("- Significance output is **`NOT VERIFIED — provisional`** until the inference "
              "procedure is validated (Doc 09 §8.3).")
    md.append("")
    report = run_dir / "DEMO_REPORT.md"
    report.write_text("\n".join(md), encoding="utf-8")
    return report


# ══════════════════════════════ CLI ═══════════════════════════════════════════

def _contrasts_for(candidates: Sequence[str], groups: Sequence[str]) -> List[Tuple[str, str, str, str]]:
    out: List[Tuple[str, str, str, str]] = []
    for c in candidates:
        if c not in REFERENCE_FEATURES:
            out.append(("F1", f"incremental:{c}", f"B2:{c}", "B1"))
        out.append(("F1", f"marginal:{c}", "B4", f"B3:{c}"))
    for g in groups:
        out.append(("F2", f"group:{g}", f"G:{g}", "B0a"))
    return out


def _build_experiment_data(pooled: pd.DataFrame, pairs: List[str]) -> ExperimentData:
    pooled = pooled.reset_index(drop=True)
    X, y, ts_int = prepare_pooled(pooled)
    T = np.sort(np.unique(ts_int))
    split = compute_split_plan(len(T))
    return ExperimentData(pooled=pooled, X=X, y=y, ts_int=ts_int, T=T, split=split, pairs=pairs)


def _fetch_pooled(pairs: List[str], count: int) -> pd.DataFrame:
    from config_oanda import get_oanda_profile  # noqa: PLC0415

    profile = get_oanda_profile()
    api = profile["api"]
    if api is None:
        raise SystemExit("OANDA API client unavailable — check config_oanda credentials")
    logger.info("OANDA env=%s | pairs=%d | bars=%d", profile["env"], len(pairs), count)
    proxy = _CountingAPI(api)
    from data_pipeline import DataFetcher  # noqa: PLC0415

    fetcher = DataFetcher(use_oanda=True, oanda_api=proxy, oanda_granularity=GRANULARITY)

    frames: List[pd.DataFrame] = []
    for instrument in pairs:
        try:
            df, n_raw, n_unclosed = ingest_pair(fetcher, proxy, instrument, count)
            if len(df) < H + 1:
                logger.warning("  %s: only %d closed bars — skipped", instrument, len(df))
                continue
            elig, acc = build_pair_dataset(df, instrument, n_raw, n_unclosed)
            if acc["n_eligible"] == 0:
                logger.warning("  %s: no eligible rows", instrument)
                continue
            close = df["Close"].astype(float)
            lag = close.shift(PURGE_BARS)
            b0b = ((close / lag - 1.0) > 0.0).where(lag.notna(), other=False)
            elig["b0b_up"] = elig["timestamp"].map(b0b).astype(float)
            frames.append(elig)
            logger.info("  %s: eligible=%d (UP=%d / NON-UP=%d)",
                        instrument, acc["n_eligible"], acc["n_up"], acc["n_non_up"])
        except Exception as exc:  # noqa: BLE001
            logger.error("  %s failed: %s: %s", instrument, type(exc).__name__, exc)
    if not frames:
        raise SystemExit("No eligible samples produced — nothing to run.")
    return pd.concat(frames, ignore_index=True)


def _self_test() -> int:
    """Offline check of the splitter, metrics, and bootstrap math (no OANDA)."""
    logger.info("SELF-TEST — synthetic data, no network")
    rng = np.random.default_rng(0)
    n_ts, pairs = 400, ["EUR_USD", "USD_JPY", "GBP_USD"]
    ts = np.arange(n_ts, dtype="int64") * 15 * 60 * 1_000_000_000
    rows = []
    for ins in pairs:
        X = rng.normal(size=(n_ts, len(ORDERED_FEATURES)))
        y = (X[:, 0] * 1.5 + rng.normal(scale=1.0, size=n_ts) > 0).astype(int)
        b0b = (X[:, 0] > 0).astype(float)
        d = {f: X[:, i] for i, f in enumerate(ORDERED_FEATURES)}
        d["timestamp"] = pd.to_datetime(ts)
        d["instrument"] = ins
        d["label"] = y
        d["b0b_up"] = b0b
        rows.append(pd.DataFrame(d))
    pooled = pd.concat(rows, ignore_index=True)

    data = _build_experiment_data(pooled, pairs)
    plan = data.split
    assert plan.edges[0] == plan.seed_len and plan.edges[-1] == plan.n_dev
    assert plan.folds[-1].test_hi == plan.n_dev - PURGE_BARS, "final dev tail must be purged"
    logger.info("  split OK: n_T=%d dev=%d holdout=%d edges=%s", plan.n_T, plan.n_dev, plan.n_holdout, plan.edges)

    cands = list(REFERENCE_FEATURES) + ["atr", "rsi"]
    groups = ["return", "atr"]
    specs = build_model_specs(cands, groups)
    contrasts = _contrasts_for(cands, groups)
    res = run_experiment(data, specs, contrasts, boot_B=40, block_lengths=(6, 12),
                         evaluate_holdout=False)
    auc_b1 = res["point"]["B1"]["roc_auc_mean"]
    logger.info("  model matrix OK: %d models, B1 mean AUC=%.4f", res["n_models"], auc_b1)
    inf = res["inference"]["results"]
    assert all("p_raw_L6" in e for e in inf.values()), "bootstrap produced no p-values"
    logger.info("  bootstrap OK: %d contrasts, e.g. %s p(L6)=%.4f",
                len(inf), "marginal:atr", inf["marginal:atr"]["p_raw_L6"])
    logger.info("SELF-TEST PASSED")
    return 0


def _env_default_count() -> int:
    """`--count` fallback from run.env (via config_oanda) then DEFAULT_COUNT."""
    try:
        import config_oanda  # noqa: F401,PLC0415 — loads .env + run.env via dotenv
    except Exception as exc:  # noqa: BLE001
        logger.debug("config_oanda unavailable for env count (%s)", exc)
    raw = os.environ.get(ENV_COUNT_KEY, "").strip()
    if not raw:
        return DEFAULT_COUNT
    try:
        return int(raw)
    except ValueError:
        logger.warning("%s=%r is not an int — using %d", ENV_COUNT_KEY, raw, DEFAULT_COUNT)
        return DEFAULT_COUNT


def _parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Phase 3.3 Doc 09 experiment harness (research/Demo only).")
    p.add_argument("--self-test", action="store_true", help="offline synthetic check; no OANDA/network")
    p.add_argument("--count", type=int, default=None,
                   help=f"bars per instrument (max 5000; default: run.env {ENV_COUNT_KEY} else {DEFAULT_COUNT})")
    p.add_argument("--profile", type=int, default=None, help="config_bot profile id to narrow the whitelist (default: union)")
    p.add_argument("--pairs", type=str, default=None, help="comma-separated OANDA-native instrument override")
    p.add_argument("--candidates", type=str, default=None, help="comma-separated candidate subset (default: all 33)")
    p.add_argument("--boot-B", type=int, default=BOOTSTRAP_B, help=f"bootstrap replicates (default {BOOTSTRAP_B})")
    p.add_argument("--block-lengths", type=str, default=",".join(map(str, BLOCK_LENGTHS)),
                   help=f"bootstrap block lengths (default {BLOCK_LENGTHS})")
    p.add_argument("--evaluate-holdout", action="store_true", help="run the single isolated holdout evaluation")
    p.add_argument("--skip-inference", action="store_true", help="skip the bootstrap (fast protocol check)")
    return p.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    if args.self_test:
        return _self_test()
    count = args.count if args.count is not None else _env_default_count()
    if count > DEFAULT_COUNT:
        raise SystemExit(f"--count exceeds the OANDA v20 maximum of {DEFAULT_COUNT}")
    logger.info("count=%d bars/instrument (CLI=%s, run.env[%s]=%s)",
                count, args.count, ENV_COUNT_KEY, os.environ.get(ENV_COUNT_KEY, "unset"))

    univ = resolve_universe(args.profile)
    pairs = ([p.strip().upper() for p in args.pairs.split(",") if p.strip()]
             if args.pairs else list(univ["universe"]))
    if not pairs:
        raise SystemExit("Empty universe — check mc_data.yml / config_bot whitelist")
    logger.info("universe=%d pairs (profile=%s, source=%s): %s",
                len(pairs), univ["profile"], univ["source"], ", ".join(pairs))
    if univ["excluded_by_whitelist"]:
        logger.info("excluded by whitelist: %s", ", ".join(univ["excluded_by_whitelist"]))

    pooled = _fetch_pooled(pairs, count)
    fingerprint = dataset_fingerprint(pooled)
    logger.info("dataset fingerprint (sha256): %s", fingerprint)

    data = _build_experiment_data(pooled, pairs)
    logger.info("split: n_T=%d dev=%d holdout=%d seed_len=%d edges=%s",
                data.split.n_T, data.split.n_dev, data.split.n_holdout,
                data.split.seed_len, data.split.edges)

    candidates = ([c.strip() for c in args.candidates.split(",") if c.strip()]
                  if args.candidates else list(ORDERED_FEATURES))
    groups = list(FEATURE_GROUPS)
    specs = build_model_specs(candidates, groups)
    contrasts = _contrasts_for(candidates, groups)
    block_lengths = tuple(int(x) for x in args.block_lengths.split(",") if x.strip())
    boot_B = 0 if args.skip_inference else args.boot_B

    logger.info("models=%d | contrasts=%d | bootstrap B=%d | L_b=%s",
                len(specs), len(contrasts), boot_B, block_lengths)
    results = run_experiment(data, specs, contrasts, boot_B=boot_B,
                             block_lengths=block_lengths, evaluate_holdout=args.evaluate_holdout)

    run_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{fingerprint[:12]}"
    run_dir = OUT_ROOT / run_id
    command = "python3 " + " ".join(sys.argv)
    report = write_outputs(run_dir, univ, data, fingerprint, results, contrasts, command)

    for k in ("B0a", "B0b", "B1", "B4"):
        m = results["point"][k]
        logger.info("%-4s ROC-AUC %.4f ± %.4f | log-loss %.4f",
                    k, m["roc_auc_mean"], m["roc_auc_std"], m["log_loss_mean"])
    logger.info("wrote %s", report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
