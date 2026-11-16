# Phase 3.3 — P3–P5 Legacy Bundle Negative Validation

**Document ID:** `P3_P5_LEGACY_BUNDLE_NEGATIVE_VALIDATION`
**Date:** 2026-11-16
**Status:** EXECUTED — read-only negative validation. **Not** a parity pass.
**Boundary:** read-only. No training, no artifact write/overwrite, no deployment, no READY activation, no trading-behavior change.

---

## 1. Purpose and limits

Phase 3.2 has no active bundle aligned to the frozen 33-column contract, which is why P3–P5 are `NOT VERIFIED`. The repository does hold a **legacy** runtime bundle. This validation answers **one** question:

> Is the legacy bundle **correctly rejected** as incompatible with the frozen contract, before any scaler or model computation?

It **cannot** and **does not** verify P3, P4 or P5 for the new contract. Producing an aligned bundle requires training / artifact writes and a new authorization.

## 2. Expected result (preregistered)

```
Legacy bundle: schema = 34-column legacy schema
New contract:  schema = 33-column FCV2
Expected:
  INCOMPATIBLE
  Fail closed
  No scaler inference
  No model inference
  No artifact writes
  No runtime activation
```

## 3. Whether it can be done now

| Check | Doable read-only | Evidence type |
|---|---|---|
| Legacy bundle feature-schema vs. contract | yes | negative / contract validation |
| Feature name + order check | yes | contract validation |
| Scaler input-column / dimension check | yes | read-only |
| Scaler output-dimension check | yes | read-only |
| Model file load | yes (read-only) | load validation |
| Schema mismatch rejected before model compute | yes | fail-closed validation |
| New 33-column P3/P4/P5 parity | **no** | no aligned artifact exists |

## 4. Exact command executed (read-only)

```bash
python - <<'PY'
import hashlib, json, sys, platform
from pathlib import Path
BUNDLE = ["trade_model_xgb.json","scaler.joblib","trade_model_xgb.features.json",
          "trade_model_xgb.cfg.json","trade_model_xgb.manifest.json"]
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()[:16]
before = {p: sha(p) for p in BUNDLE if Path(p).exists()}          # hashes before
legacy = json.loads(Path("trade_model_xgb.features.json").read_text())
sys.path.insert(0, ".")
from ml import feature_contract as fc
new = list(fc.ORDERED_FEATURES)
print("legacy", len(legacy), "| contract", len(new),
      "| order_identical", legacy == new,
      "| verdict", "INCOMPATIBLE" if set(legacy) != set(new) else "COMPATIBLE")
import joblib; scaler = joblib.load("scaler.joblib")
print("scaler n_features_in_ =", scaler.n_features_in_)
import xgboost as xgb; m = xgb.XGBClassifier(); m.load_model("trade_model_xgb.json")
print("model n_features_in_ =", m.n_features_in_, "| classes_ =", list(m.classes_))
import numpy as np, pandas as pd, data_pipeline as dp
idx = pd.date_range("2026-01-05 00:00", periods=800, freq="15min", tz="UTC")
b = 1.10 + np.cumsum(np.random.default_rng(7).normal(0, 0.0003, 800))
raw = pd.DataFrame({"Open":b,"High":b+2e-4,"Low":b-2e-4,"Close":b+1e-4}, index=idx)
row = fc.build_features(raw).iloc[[-1]]                            # 33-col contract row
for label, X in (("DataFrame", row), ("ndarray", row.to_numpy(dtype=float))):
    try: dp._build_matrix(X, legacy, scaler); print(label, "NO ERROR -> FAIL-OPEN")
    except Exception as e: print(label, "raised", type(e).__name__)
after = {p: sha(p) for p in BUNDLE if Path(p).exists()}            # hashes after
print("no-write check:", "PASS" if before == after else "FAIL")
PY
```

## 5. Recorded identity

| Item | Value |
|---|---|
| Python / numpy / pandas / xgboost | 3.12.15 / 1.26.4 / 2.2.3 / 2.0.3 |
| New contract 33-col FCID (recomputed) | `sha256 = bffdb0005083f95e2030df7ec912af2e87ec930fdd3672f0b1a0d5530e9a0a8c` (matches `FCV2-bffdb0005083f95e`) |

**Bundle sha256 (first 16 hex) — before and after:**

| File | sha256[:16] before | sha256[:16] after |
|---|---|---|
| `trade_model_xgb.json` | `ead2f7b9ed254e81` | `ead2f7b9ed254e81` |
| `scaler.joblib` | `8fe9d8b47e3e2695` | `8fe9d8b47e3e2695` |
| `trade_model_xgb.features.json` | `3e9e319cae45dc40` | `3e9e319cae45dc40` |
| `trade_model_xgb.cfg.json` | `e051f228fbdf4841` | `e051f228fbdf4841` |
| `trade_model_xgb.manifest.json` | `9b860295166d06c1` | `9b860295166d06c1` |

## 6. Results

### 6.1 Schema comparison

| Metric | Value |
|---|---|
| Legacy features | 34 |
| Contract features | 33 |
| Shared names | 11 |
| Only in legacy | 23 (`ret_1h, ret_3h, ret_6h, ret_12h, ret_log, vol_12h, vol_24h, vol_48h, atr_percentile, atr_expanding, dist_high_24, dist_low_24, dist_high_48, dist_low_48, dist_high_96, dist_low_96, vol_sma_ratio, vol_trend, hour, day_of_week, is_london, is_ny, rsi_slope`) |
| Only in contract | 22 (`atr_above_sma14, atr_ecdf_50bar, dist_high_6h, dist_low_6h, dist_high_12h, dist_low_12h, dist_high_24h, dist_low_24h, horizon_vol_3h, horizon_vol_6h, horizon_vol_12h, log_return_15m, macd, macd_signal, macd_hist, return_15m, return_45m, return_90m, return_3h, rsi_slope_45m, utc_hour, utc_day_of_week`) |
| Order identical | `False` |
| **Verdict** | **INCOMPATIBLE** |

### 6.2 Read-only artifact load

| Artifact | Result |
|---|---|
| `scaler.joblib` | loaded (read-only); type `StandardScaler`; `n_features_in_ = 34` |
| `trade_model_xgb.json` | loaded (read-only); `n_features_in_ = 34`; `classes_ = [0, 1]` |

### 6.3 Fail-closed guard (mismatch rejected before model compute)

| Input form | Result |
|---|---|
| Contract frame as DataFrame (33 cols) vs. legacy list (34) | raised `InferenceFeatureError: Missing required features: [...]` |
| Contract frame as ndarray (33 cols) | raised `InferenceFeatureError: Input dimension mismatch: 33 vs 34` |

Guard: `data_pipeline._build_matrix` raises **before** `scaler.transform` and before any model call ("fails loudly, never zero-fills").

### 6.4 No-write check

`before == after` for all five files → **PASS** (no artifact written or overwritten; no inference executed).

## 7. Verdict

| Question | Result |
|---|---|
| Legacy bundle vs. frozen contract | **INCOMPATIBLE** |
| Fail closed on mismatch | **PASS** |
| Scaler inference executed | **NO** |
| Model inference executed | **NO** |
| Artifact writes | **NONE** |
| Runtime activation | **NONE** |

## 8. What this closes — and what it does not

- **Closes:** "the legacy bundle is correctly identified as incompatible with the frozen 33-column contract and is rejected fail-closed." This is a **negative validation**.
- **Does NOT close:** P3 (scaler), P4 (model tensor), P5 (prediction output) for the new contract. A scaler that *can* transform is **not** evidence it is *contract-correct*.
- Producing P3–P5 evidence still requires an **aligned bundle**, i.e. training / artifact writes → **new authorization** (see `04_AUTHORIZATION_BOUNDARY.md`).
