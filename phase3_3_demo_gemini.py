#!/usr/bin/env python3
"""
phase3_3_demo.py — Doc 09 (R4 FROZEN) Experiment Harness
=======================================================
Governance Boundary:
- Authorized: Offline preparation, dataset alignment, walk-forward splitting,
  in-fold constrained training, LOPO evaluation, and synchronized block bootstrap.
- NOT Authorized: Production model deployment, live/paper order routing, or
  modifying upstream production configs.
- Output Tag: All statistical outputs carry `NOT VERIFIED — provisional` until
  Owner sign-off on execution results.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.preprocessing import StandardScaler

# ---------------------------------------------------------------------------
# Frozen Protocol Constants (Doc 09 R4)
# ---------------------------------------------------------------------------
PROTOCOL_ID = "DOC09-R4-FROZEN-20261116"
PROVISIONAL_TAG = "NOT VERIFIED — provisional"
HORIZON_BARS = 6
PURGE_BARS = 6
HOLDOUT_FRAC = 0.20
SEED_FRAC = 0.30
N_FOLDS = 5
BOOTSTRAP_B = 2000
BLOCK_LENGTHS = (6, 12, 24, 48)
DEFAULT_COUNT = 5000
RANDOM_SEED = 42


@dataclass(frozen=True)
class FoldWindow:
    fold_id: int
    train_start_idx: int
    train_end_idx: int  # exclusive
    test_start_idx: int
    test_end_idx: int   # exclusive
    train_start_ts: str
    train_end_ts: str
    test_start_ts: str
    test_end_ts: str


# ===========================================================================
# MODULE 1: Data Loader & Universe Filter
# ===========================================================================
def normalize_to_oanda(symbol: str) -> str:
    """Convert clean 6-char symbol (e.g. 'EURUSD') to OANDA native ('EUR_USD')."""
    s = symbol.strip().upper()
    if "_" in s:
        return s
    if len(s) == 6:
        return f"{s[:3]}_{s[3:]}"
    raise ValueError(f"Unsupported FX symbol format: {symbol!r}")


def _parse_mc_data_pairs(mc_yaml_path: Path) -> List[str]:
    """Load pairs from mc_data.yml using PyYAML if available, else regex fallback."""
    text = mc_yaml_path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore
        doc = yaml.safe_load(text) or {}
        raw_pairs = doc.get("pairs", [])
        return [normalize_to_oanda(p) for p in raw_pairs]
    except ImportError:
        in_pairs = False
        out: List[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("pairs:"):
                in_pairs = True
                continue
            if in_pairs:
                if stripped.startswith("-"):
                    item = stripped.lstrip("-").strip().strip("'\"")
                    if item:
                        out.append(normalize_to_oanda(item))
                elif stripped and not stripped.startswith("#"):
                    break
        return out


def _load_whitelist_from_repo(repo_root: Path, profile_id: Optional[str] = None) -> List[str]:
    """Resolve whitelist via config_bot.py / forex_pairs.json without mutating state."""
    pairs_json = repo_root / "forex_pairs.json"
    if pairs_json.exists():
        data = json.loads(pairs_json.read_text(encoding="utf-8"))
        default_pairs = [normalize_to_oanda(p) for p in data.get("DEFAULT_PAIRS", [])]
        wl_map: Dict[str, List[str]] = data.get("WHITELIST", {})
        if profile_id is not None:
            bucket = wl_map.get(str(profile_id), default_pairs)
            return sorted({normalize_to_oanda(p) for p in bucket})
        union_set = set(default_pairs)
        for bucket in wl_map.values():
            union_set.update(normalize_to_oanda(p) for p in bucket)
        return sorted(union_set)

    # Fallback: attempt import of config_bot if present
    sys.path.insert(0, str(repo_root))
    import config_bot  # type: ignore
    if profile_id is not None:
        cfg = config_bot.build_profile_cfg(int(profile_id))
        return sorted({normalize_to_oanda(p) for p in cfg.get("WHITELIST", [])})
    union_set = {normalize_to_oanda(p) for p in getattr(config_bot, "DEFAULT_PAIRS", [])}
    for bucket in getattr(config_bot, "WHITELIST", {}).values():
        union_set.update(normalize_to_oanda(p) for p in bucket)
    return sorted(union_set)


def resolve_universe(
    repo_root: Path,
    profile_id: Optional[str] = None,
    override_pairs: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Compute mc_data.yml pairs intersected with config_bot.py whitelist."""
    mc_path = repo_root / "mc_data.yml"
    mc_pairs = sorted(set(_parse_mc_data_pairs(mc_path)))
    wl_pairs = _load_whitelist_from_repo(repo_root, profile_id=profile_id)

    universe = sorted(set(mc_pairs).intersection(wl_pairs))
    excluded_from_mc = sorted(set(mc_pairs) - set(wl_pairs))

    if override_pairs:
        req = {normalize_to_oanda(p) for p in override_pairs}
        universe = sorted(set(universe).intersection(req))

    return {
        "mc_data_count": len(mc_pairs),
        "whitelist_count": len(wl_pairs),
        "resolved_pairs": universe,
        "excluded_mc_pairs": excluded_from_mc,
        "profile_filter": profile_id if profile_id is not None else "UNION_ALL_PROFILES",
    }


# ===========================================================================
# MODULE 2: Global Timestamp-Grid Walk-Forward Splitter
# ===========================================================================
def _ts_ns(series: pd.Series) -> np.ndarray:
    """Normalize timestamps to UTC int64 nanoseconds for tz-safe comparisons."""
    return pd.to_datetime(series, utc=True).astype("datetime64[ns, UTC]").astype("int64").to_numpy()


def build_timestamp_grid(df: pd.DataFrame) -> np.ndarray:
    """Return sorted unique UTC nanosecond timestamps across all instruments."""
    return np.unique(_ts_ns(df["timestamp"]))


def compute_folds(
    timestamps: np.ndarray,
    holdout_frac: float = HOLDOUT_FRAC,
    seed_frac: float = SEED_FRAC,
    n_folds: int = N_FOLDS,
    purge_bars: int = PURGE_BARS,
) -> Tuple[List[FoldWindow], Tuple[int, int]]:
    """
    Construct expanding walk-forward folds on the global timestamp grid T
    with strict purge gaps and a sealed tail holdout window.
    """
    n_t = len(timestamps)
    n_holdout = int(math.floor(holdout_frac * n_t))
    dev_len = n_t - n_holdout
    if dev_len <= 0:
        raise ValueError("Insufficient timestamps for development split.")

    seed_len = int(math.floor(seed_frac * dev_len))
    edges = np.rint(np.linspace(seed_len, dev_len, n_folds + 1)).astype(int)

    folds: List[FoldWindow] = []
    for k in range(1, n_folds + 1):
        test_start = int(edges[k - 1])
        test_end = int(edges[k])
        if k == n_folds:
            # Enforce purge gap before sealed holdout block
            test_end = max(test_start, test_end - purge_bars)
        train_start = 0
        train_end = max(0, test_start - purge_bars)
        if train_end <= train_start or test_end <= test_start:
            raise ValueError(f"Degenerate window on fold {k}: train=({train_start},{train_end}), test=({test_start},{test_end})")

        folds.append(
            FoldWindow(
                fold_id=k,
                train_start_idx=train_start,
                train_end_idx=train_end,
                test_start_idx=test_start,
                test_end_idx=test_end,
                train_start_ts=pd.Timestamp(timestamps[train_start], unit="ns", tz="UTC").isoformat(),
                train_end_ts=pd.Timestamp(timestamps[train_end - 1], unit="ns", tz="UTC").isoformat(),
                test_start_ts=pd.Timestamp(timestamps[test_start], unit="ns", tz="UTC").isoformat(),
                test_end_ts=pd.Timestamp(timestamps[test_end - 1], unit="ns", tz="UTC").isoformat(),
            )
        )

    holdout_span = (dev_len, n_t)
    return folds, holdout_span


# ===========================================================================
# MODULE 3: In-Fold Constrained Runner, LOPO & Block Bootstrap
# ===========================================================================
def define_feature_subsets(all_features: Sequence[str]) -> Dict[str, List[str]]:
    """
    Partition the 33-feature contract into nested ablation sets:
    - B1: Price/Return & Volatility core
    - B2: B1 + Regime / ECDF / Distributional features
    - B3: Cross-pair / Session / Microstructure core
    - B4: Full feature contract (all 33 features)
    """
    feats = list(all_features)
    ecdf_regime = [f for f in feats if any(k in f.lower() for k in ("ecdf", "regime", "zscore", "rank", "vol_ratio", "hurst"))]
    cross_sess = [f for f in feats if any(k in f.lower() for k in ("session", "hour", "dow", "corr", "spread", "usd_", "jpy_"))]
    core = [f for f in feats if f not in set(ecdf_regime) | set(cross_sess)]
    if not core:
        core = feats[: max(1, len(feats) // 3)]

    b1 = core
    b2 = sorted(set(b1) | set(ecdf_regime), key=feats.index)
    b3 = sorted(set(b1) | set(cross_sess), key=feats.index)
    b4 = feats
    return {"B1": b1, "B2": b2, "B3": b3, "B4": b4}


def _fit_predict_fold(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_test: np.ndarray,
    calibrate: bool = False,
) -> np.ndarray:
    """In-fold fold-local StandardScaler + LogisticRegression (no global grid search)."""
    scaler = StandardScaler()
    X_tr_s = scaler.fit_transform(X_train)
    X_te_s = scaler.transform(X_test)

    base_clf = LogisticRegression(C=1.0, penalty="l2", solver="lbfgs", max_iter=1000, random_state=RANDOM_SEED)
    if calibrate:
        clf = CalibratedClassifierCV(estimator=base_clf, method="sigmoid", cv=3)
    else:
        clf = base_clf
    clf.fit(X_tr_s, y_train)
    return clf.predict_proba(X_te_s)[:, 1]


def _safe_metrics(y_true: np.ndarray, y_prob: np.ndarray) -> Dict[str, float]:
    y_prob_clip = np.clip(y_prob, 1e-6, 1.0 - 1e-6)
    auc = float(roc_auc_score(y_true, y_prob_clip)) if len(np.unique(y_true)) > 1 else 0.5
    ll = float(log_loss(y_true, y_prob_clip, labels=[0, 1]))
    brier = float(brier_score_loss(y_true, y_prob_clip))
    return {"roc_auc": auc, "log_loss": ll, "brier": brier, "n": int(len(y_true))}


def run_walk_forward(
    df: pd.DataFrame,
    timestamps: np.ndarray,
    folds: List[FoldWindow],
    feature_sets: Dict[str, List[str]],
    calibrate: bool = False,
) -> Tuple[Dict[str, Any], pd.DataFrame]:
    """Execute B0a, B0b, and B1..B4 across expanding walk-forward folds."""
    ts_col = _ts_ns(df["timestamp"])
    records: List[Dict[str, Any]] = []
    oof_rows: List[pd.DataFrame] = []

    for fw in folds:
        tr_mask = (ts_col >= timestamps[fw.train_start_idx]) & (ts_col <= timestamps[fw.train_end_idx - 1])
        te_mask = (ts_col >= timestamps[fw.test_start_idx]) & (ts_col <= timestamps[fw.test_end_idx - 1])

        df_tr = df.loc[tr_mask]
        df_te = df.loc[te_mask].copy()
        y_tr = df_tr["label"].to_numpy(dtype=int)
        y_te = df_te["label"].to_numpy(dtype=int)

        # B0a: Majority class prior
        pos_rate = float(np.mean(y_tr))
        p_b0a = np.full(len(y_te), pos_rate, dtype=float)

        # B0b: 6-bar realized return persistence
        ret6 = (df_te["close_now"].to_numpy(dtype=float) / df_te["close_lag6"].to_numpy(dtype=float)) - 1.0
        p_b0b = 1.0 / (1.0 + np.exp(-np.clip(ret6 * 500.0, -20.0, 20.0)))

        preds_fold: Dict[str, np.ndarray] = {"B0a": p_b0a, "B0b": p_b0b}
        for model_name, cols in feature_sets.items():
            preds_fold[model_name] = _fit_predict_fold(
                df_tr[cols].to_numpy(dtype=float),
                y_tr,
                df_te[cols].to_numpy(dtype=float),
                calibrate=calibrate,
            )

        for model_name, probs in preds_fold.items():
            m_pooled = _safe_metrics(y_te, probs)
            records.append({"fold": fw.fold_id, "model": model_name, "scope": "POOLED", **m_pooled})
            for inst, grp_idx in df_te.groupby("instrument").groups.items():
                pos = df_te.index.get_indexer(grp_idx)
                m_pair = _safe_metrics(y_te[pos], probs[pos])
                records.append({"fold": fw.fold_id, "model": model_name, "scope": str(inst), **m_pair})

        oof_slice = df_te[["timestamp", "instrument", "label"]].copy()
        for model_name, probs in preds_fold.items():
            oof_slice[f"prob_{model_name}"] = probs
        oof_slice["fold"] = fw.fold_id
        oof_rows.append(oof_slice)

    oof_df = pd.concat(oof_rows, ignore_index=True)
    summary_df = pd.DataFrame(records)
    agg = (
        summary_df[summary_df["scope"] == "POOLED"]
        .groupby("model")[["roc_auc", "log_loss", "brier"]]
        .mean()
        .to_dict(orient="index")
    )
    return {"pooled_mean": agg, "fold_details": records}, oof_df


def run_lopo(
    df: pd.DataFrame,
    timestamps: np.ndarray,
    holdout_start_idx: int,
    features: List[str],
    calibrate: bool = False,
) -> Dict[str, Any]:
    """Leave-One-Pair-Out generalization across the development window."""
    ts_col = _ts_ns(df["timestamp"])
    dev_df = df.loc[ts_col < timestamps[holdout_start_idx]]
    lopo_res: Dict[str, Any] = {}
    for held_out in sorted(dev_df["instrument"].unique()):
        tr = dev_df[dev_df["instrument"] != held_out]
        te = dev_df[dev_df["instrument"] == held_out]
        probs = _fit_predict_fold(
            tr[features].to_numpy(dtype=float),
            tr["label"].to_numpy(dtype=int),
            te[features].to_numpy(dtype=float),
            calibrate=calibrate,
        )
        lopo_res[held_out] = _safe_metrics(te["label"].to_numpy(dtype=int), probs)
    return lopo_res


def bh_fdr(p_values: Sequence[float]) -> List[float]:
    """Benjamini-Hochberg FDR adjusted q-values."""
    m = len(p_values)
    if m == 0:
        return []
    order = np.argsort(p_values)
    ranked = np.asarray(p_values, dtype=float)[order]
    q = np.empty(m, dtype=float)
    prev = 1.0
    for i in range(m - 1, -1, -1):
        val = ranked[i] * m / (i + 1)
        prev = min(prev, val)
        q[i] = prev
    out = np.empty(m, dtype=float)
    out[order] = np.clip(q, 0.0, 1.0)
    return out.tolist()


def block_bootstrap_delta_auc(
    oof_df: pd.DataFrame,
    comparisons: Sequence[Tuple[str, str]] = (("B2", "B1"), ("B4", "B3"), ("B4", "B1")),
    block_lengths: Sequence[int] = BLOCK_LENGTHS,
    n_boot: int = BOOTSTRAP_B,
    seed: int = RANDOM_SEED,
) -> Dict[str, Any]:
    """
    Synchronized cross-instrument Moving-Block Bootstrap over unique OOF timestamps.
    Resamples timestamp blocks simultaneously across all pairs to preserve
    contemporaneous cross-currency correlation.
    """
    rng = np.random.default_rng(seed)
    unique_ts = np.sort(pd.to_datetime(oof_df["timestamp"], utc=True).unique())
    n_ts = len(unique_ts)
    ts_to_rows = {
        t: idx.to_numpy()
        for t, idx in oof_df.groupby(pd.to_datetime(oof_df["timestamp"], utc=True)).groups.items()
    }
    row_groups = [ts_to_rows[t] for t in unique_ts]

    y_all = oof_df["label"].to_numpy(dtype=int)
    probs_map = {
        col.replace("prob_", ""): oof_df[col].to_numpy(dtype=float)
        for col in oof_df.columns
        if col.startswith("prob_")
    }

    results_by_lb: Dict[str, Any] = {}
    for lb in block_lengths:
        n_blocks = int(math.ceil(n_ts / lb))
        max_start = max(1, n_ts - lb + 1)
        comp_stats: Dict[str, Any] = {}
        raw_pvals: List[float] = []
        comp_keys: List[str] = []

        for m_cand, m_ref in comparisons:
            obs_delta = float(
                roc_auc_score(y_all, probs_map[m_cand]) - roc_auc_score(y_all, probs_map[m_ref])
            )
            deltas = np.empty(n_boot, dtype=float)
            for b in range(n_boot):
                starts = rng.integers(0, max_start, size=n_blocks)
                sampled_ts_idx = np.concatenate([np.arange(s, min(n_ts, s + lb)) for s in starts])[:n_ts]
                sampled_rows = np.concatenate([row_groups[i] for i in sampled_ts_idx])
                yb = y_all[sampled_rows]
                if len(np.unique(yb)) < 2:
                    deltas[b] = 0.0
                else:
                    deltas[b] = roc_auc_score(yb, probs_map[m_cand][sampled_rows]) - roc_auc_score(
                        yb, probs_map[m_ref][sampled_rows]
                    )

            # One-sided p-value: P(delta <= 0)
            p_val = float((np.sum(deltas <= 0.0) + 1.0) / (n_boot + 1.0))
            ci_low, ci_high = float(np.percentile(deltas, 2.5)), float(np.percentile(deltas, 97.5))
            key = f"{m_cand}_vs_{m_ref}"
            comp_keys.append(key)
            raw_pvals.append(p_val)
            comp_stats[key] = {
                "obs_delta_auc": obs_delta,
                "boot_mean_delta_auc": float(np.mean(deltas)),
                "ci95": [ci_low, ci_high],
                "p_one_sided": p_val,
            }

        q_vals = bh_fdr(raw_pvals)
        for key, qv in zip(comp_keys, q_vals):
            comp_stats[key]["bh_fdr_q"] = qv
            comp_stats[key]["status_tag"] = PROVISIONAL_TAG

        results_by_lb[f"Lb_{lb}"] = comp_stats

    return {
        "status_tag": PROVISIONAL_TAG,
        "bootstrap_B": n_boot,
        "block_lengths": list(block_lengths),
        "results": results_by_lb,
    }


# ===========================================================================
# Synthetic Offline Self-Test & CLI Entrypoint
# ===========================================================================
def generate_synthetic_dataset(pairs: Sequence[str], n_bars: int = 800) -> Tuple[pd.DataFrame, List[str]]:
    """Generate deterministic multi-pair synthetic dataset for offline verification."""
    rng = np.random.default_rng(RANDOM_SEED)
    n_features = 33
    feat_names = [
        "ret_1", "ret_3", "ret_6", "vol_12", "vol_48", "atr_14",
        "ecdf_ret_1", "ecdf_vol_12", "regime_vol_ratio", "hurst_32", "zscore_close",
        "session_asia", "session_london", "session_ny", "hour_sin", "hour_cos",
        "usd_factor", "jpy_factor", "spread_norm", "corr_eurusd", "dow_sin",
    ] + [f"feat_{i}" for i in range(21, n_features)]

    ts_grid = pd.date_range("2026-01-01", periods=n_bars, freq="15min", tz="UTC")
    common_shock = rng.normal(0.0, 1.0, size=n_bars)
    frames: List[pd.DataFrame] = []

    for p in pairs:
        X = rng.normal(0.0, 1.0, size=(n_bars, n_features))
        X[:, 0] += 0.35 * common_shock
        close = 1.1000 * np.exp(np.cumsum(0.0005 * X[:, 0]))
        close_lag6 = np.roll(close, HORIZON_BARS)
        close_lag6[:HORIZON_BARS] = close[:HORIZON_BARS]
        logit = 0.25 * X[:, 0] - 0.15 * X[:, 6] + rng.normal(0.0, 0.8, size=n_bars)
        y = (logit > 0.0).astype(int)

        part = pd.DataFrame(X, columns=feat_names)
        part.insert(0, "instrument", p)
        part.insert(0, "timestamp", ts_grid)
        part["close_now"] = close
        part["close_lag6"] = close_lag6
        part["label"] = y
        frames.append(part.iloc[HORIZON_BARS:].reset_index(drop=True))

    return pd.concat(frames, ignore_index=True), feat_names

def main() -> int:
    parser = argparse.ArgumentParser(description="Doc 09 (R4 FROZEN) Phase 3.3 Experiment Harness")
    parser.add_argument("--repo-root", type=Path, default=Path("."), help="Repository root containing mc_data.yml and forex_pairs.json")
    parser.add_argument("--profile", type=str, default=None, help="Optional profile ID to narrow whitelist (default: union of all whitelists)")
    parser.add_argument("--pairs", nargs="*", default=None, help="Optional explicit subset of pairs")
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT, help=f"Candles per instrument (OANDA max 5000; default {DEFAULT_COUNT})")
    parser.add_argument("--calibrate", action="store_true", help="Enable internal 3-fold sigmoid probability calibration")
    parser.add_argument("--bootstrap-b", type=int, default=BOOTSTRAP_B, help="Number of moving-block bootstrap replicates")
    parser.add_argument("--self-test", action="store_true", help="Run offline synthetic verification without OANDA network access")
    parser.add_argument("--output-dir", type=Path, default=Path("experiments/phase3_3_demo"), help="Base output directory")
    args = parser.parse_args()

    if args.count > 5000:
        raise SystemExit("--count exceeds the OANDA v20 maximum of 5000 candles")

    run_id = datetime.now(timezone.utc).strftime("run_%Y%m%dT%H%M%SZ")
    out_dir = args.output_dir / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.self_test:
        pairs = ["EUR_USD", "GBP_USD", "USD_JPY", "AUD_JPY"]
        universe_info = {"mode": "SELF_TEST_SYNTHETIC", "resolved_pairs": pairs}
        df, feat_names = generate_synthetic_dataset(pairs, n_bars=600)
    else:
        universe_info = resolve_universe(args.repo_root, profile_id=args.profile, override_pairs=args.pairs)
        pairs = universe_info["resolved_pairs"]
        if not pairs:
            raise RuntimeError("Resolved universe is empty after intersecting mc_data.yml and whitelist.")

        repo_str = str(args.repo_root.resolve())
        if repo_str not in sys.path:
            sys.path.insert(0, repo_str)

        from config_oanda import get_oanda_profile  # type: ignore
        from data_pipeline import DataFetcher  # type: ignore
        from ml.feature_contract import ORDERED_FEATURES  # type: ignore
        from phase3_3_baseline import GRANULARITY, _CountingAPI, build_pair_dataset, ingest_pair  # type: ignore

        profile = get_oanda_profile()
        api = profile["api"]
        if api is None:
            raise SystemExit("OANDA API client unavailable — check config_oanda credentials")

        proxy = _CountingAPI(api)
        fetcher = DataFetcher(use_oanda=True, oanda_api=proxy, oanda_granularity=GRANULARITY)

        feat_names = list(ORDERED_FEATURES)
        frames = []
        for p in pairs:
            raw_df, n_raw, n_unclosed = ingest_pair(fetcher, proxy, p, count=args.count)
            if len(raw_df) < HORIZON_BARS + 1:
                continue
            ds, accounting = build_pair_dataset(raw_df, p, n_raw, n_unclosed)
            if accounting["n_eligible"] == 0:
                continue
            close_s = raw_df["Close"].astype(float)
            ds["close_now"] = ds["timestamp"].map(close_s)
            ds["close_lag6"] = ds["timestamp"].map(close_s.shift(HORIZON_BARS))
            ds = ds.dropna(subset=["close_now", "close_lag6"]).reset_index(drop=True)
            frames.append(ds)

        if not frames:
            raise RuntimeError("No eligible samples produced across resolved pairs.")
        df = pd.concat(frames, ignore_index=True)

    timestamps = build_timestamp_grid(df)
    folds, holdout_span = compute_folds(timestamps)
    feature_sets = define_feature_subsets(feat_names)

    wf_results, oof_df = run_walk_forward(df, timestamps, folds, feature_sets, calibrate=args.calibrate)
    lopo_results = run_lopo(df, timestamps, holdout_span[0], feature_sets["B4"], calibrate=args.calibrate)
    boot_results = block_bootstrap_delta_auc(oof_df, n_boot=args.bootstrap_b)

    data_hash = hashlib.sha256(
        pd.util.hash_pandas_object(df[["timestamp", "instrument", "label"]], index=False).values.tobytes()
    ).hexdigest()

    evidence_record = {
        "protocol_id": PROTOCOL_ID,
        "status_tag": PROVISIONAL_TAG,
        "run_id": run_id,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "cpu_count": os.cpu_count(),
        },
        "universe": universe_info,
        "dataset_fingerprint": {
            "rows": int(len(df)),
            "unique_timestamps": int(len(timestamps)),
            "sha256": data_hash,
        },
        "splits": {
            "holdout_span_idx": list(holdout_span),
            "holdout_sealed": True,
            "folds": [asdict(f) for f in folds],
        },
        "walk_forward": wf_results,
        "lopo_dev": lopo_results,
        "block_bootstrap": boot_results,
    }

    (out_dir / "evidence_record.json").write_text(json.dumps(evidence_record, indent=2), encoding="utf-8")
    oof_df.to_csv(out_dir / "oof_predictions.csv", index=False)
    print(f"[{PROTOCOL_ID}] Completed ({PROVISIONAL_TAG}) -> {out_dir}")
    return 0

def _main() -> int:
    parser = argparse.ArgumentParser(description="Doc 09 (R4 FROZEN) Phase 3.3 Experiment Harness")
    parser.add_argument("--repo-root", type=Path, default=Path("."), help="Repository root containing mc_data.yml and forex_pairs.json")
    parser.add_argument("--profile", type=str, default=None, help="Optional profile ID to narrow whitelist (default: union of all whitelists)")
    parser.add_argument("--pairs", nargs="*", default=None, help="Optional explicit subset of pairs")
    parser.add_argument("--calibrate", action="store_true", help="Enable internal 3-fold sigmoid probability calibration")
    parser.add_argument("--bootstrap-b", type=int, default=BOOTSTRAP_B, help="Number of moving-block bootstrap replicates")
    parser.add_argument("--self-test", action="store_true", help="Run offline synthetic verification without OANDA network access")
    parser.add_argument("--output-dir", type=Path, default=Path("experiments/phase3_3_demo"), help="Base output directory")
    args = parser.parse_args()

    run_id = datetime.now(timezone.utc).strftime("run_%Y%m%dT%H%M%SZ")
    out_dir = args.output_dir / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.self_test:
        pairs = ["EUR_USD", "GBP_USD", "USD_JPY", "AUD_JPY"]
        universe_info = {"mode": "SELF_TEST_SYNTHETIC", "resolved_pairs": pairs}
        df, feat_names = generate_synthetic_dataset(pairs, n_bars=600)
    else:
        universe_info = resolve_universe(args.repo_root, profile_id=args.profile, override_pairs=args.pairs)
        pairs = universe_info["resolved_pairs"]
        if not pairs:
            raise RuntimeError("Resolved universe is empty after intersecting mc_data.yml and whitelist.")
        # Reuse repo ingestion + feature contract builder when executed in repo
        sys.path.insert(0, str(args.repo_root))
        from phase3_3_baseline import _CountingAPI, build_pair_dataset, ingest_pair  # type: ignore
        from ml.feature_contract import REQUIRED_COLUMNS as FEATURE_COLUMNS

        feat_names = list(FEATURE_COLUMNS)
        api = _CountingAPI()
        frames = []
        for p in pairs:
            raw_df = ingest_pair(api, p, count=DEFAULT_COUNT)
            ds = build_pair_dataset(raw_df, p)
            close_s = raw_df.set_index("timestamp")["close"]
            ds["close_now"] = ds["timestamp"].map(close_s)
            ds["close_lag6"] = ds["timestamp"].map(close_s.shift(HORIZON_BARS))
            ds = ds.dropna(subset=["close_now", "close_lag6"]).reset_index(drop=True)
            frames.append(ds)
        df = pd.concat(frames, ignore_index=True)

    timestamps = build_timestamp_grid(df)
    folds, holdout_span = compute_folds(timestamps)
    feature_sets = define_feature_subsets(feat_names)

    wf_results, oof_df = run_walk_forward(df, timestamps, folds, feature_sets, calibrate=args.calibrate)
    lopo_results = run_lopo(df, timestamps, holdout_span[0], feature_sets["B4"], calibrate=args.calibrate)
    boot_results = block_bootstrap_delta_auc(oof_df, n_boot=args.bootstrap_b)

    data_hash = hashlib.sha256(
        pd.util.hash_pandas_object(df[["timestamp", "instrument", "label"]], index=False).values.tobytes()
    ).hexdigest()

    evidence_record = {
        "protocol_id": PROTOCOL_ID,
        "status_tag": PROVISIONAL_TAG,
        "run_id": run_id,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "cpu_count": os.cpu_count(),
        },
        "universe": universe_info,
        "dataset_fingerprint": {
            "rows": int(len(df)),
            "unique_timestamps": int(len(timestamps)),
            "sha256": data_hash,
        },
        "splits": {
            "holdout_span_idx": list(holdout_span),
            "holdout_sealed": True,
            "folds": [asdict(f) for f in folds],
        },
        "walk_forward": wf_results,
        "lopo_dev": lopo_results,
        "block_bootstrap": boot_results,
    }

    (out_dir / "evidence_record.json").write_text(json.dumps(evidence_record, indent=2), encoding="utf-8")
    oof_df.to_csv(out_dir / "oof_predictions.csv", index=False)
    print(f"[{PROTOCOL_ID}] Completed ({PROVISIONAL_TAG}) -> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
