# Phase 3.2 Feature Contract — Decision Record

**Version:** 0.2-decision
**Source spec:** `docs/PHASE3_2_STRICT_SPEC.md` v0.3
**Evidence:** `docs/PHASE3_2_STAGE_A_SOURCE_RECONCILIATION.md`; `docs/PHASE3_2_TRAIN_INFERENCE_PARITY_REPORT.md`; `docs/PHASE3_2_ARTIFACT_EVIDENCE_RECOVERY.md`
**Status:** PARTIAL — contract authority and legacy disposition decided; technical Feature Contract Identity not issued; Phase 3.2 remains OPEN

## 1. Authority and scope

- The current source authority remains `data_pipeline.FeatureEngine`.
- `ml/features.py` is not a production feature source.
- For future controlled training and inference, the versioned Feature Contract in this record is the sole authority for ordered names, calculations, backend, preprocessing, timeframe, and history/warm-up policy. Training and runtime implementations must conform to the same issued contract identity; source code or an artifact manifest cannot silently override it.
- Historical artifacts without a verifiable binding to an issued contract are not compatible by inference and must not enter a new controlled activation path.
- This document defines the target contract only. It does not authorize implementation, model training, artifact writes, deployment, READY wiring, or trading behavior changes.
- Feature Contract Identity is **NOT ISSUED** until ordered feature names and calculations, backend identity/version, timeframe, data/preprocessing rules, and lookback/warm-up policy are resolved together.

## 2. Input and candle requirements

The model feature input is OHLCV indexed by candle time. A contract-conforming input must:

- represent one declared instrument and one declared timeframe;
- use timezone-aware UTC timestamps;
- be strictly increasing, unique, and validated against the timeframe's expected candle interval;
- exclude the latest incomplete candle under one shared training/inference rule;
- reject or explicitly account for gaps and invalid OHLCV values before feature calculation.

The current OANDA fetch path trims a possibly incomplete last candle. The inspected feature/fetch path does not enforce sorted unique timestamps or a candle-gap policy; these are target requirements, not claims about current behavior.

## 3. Feature schema

The model input must use an explicit ordered feature list stored with the model bundle. Runtime code must not discover the model schema by selecting whatever numeric columns happen to exist.

With the current configuration (`use_macd=True`) and successful pandas-ta calls, the source generates 37 numeric candidates in this order:

```text
ret_1h, ret_3h, ret_6h, ret_12h, ret_log,
vol_12h, vol_24h, vol_48h,
body, upper_wick, lower_wick, range, direction,
atr, atr_pct, atr_percentile, atr_ma, atr_expanding, atr_ratio,
rsi, rsi_slope, adx,
MACD_12_26_9, MACDh_12_26_9, MACDs_12_26_9,
dist_high_24, dist_low_24, dist_high_48, dist_low_48,
dist_high_96, dist_low_96, vol_sma_ratio, vol_trend,
hour, day_of_week, is_london, is_ny
```

This is a **source-derived candidate**, not a frozen model schema. The historical host record describes a 34-feature bundle, while the local October model and feature-list backups have 37 features; there is no evidence that either is the current active bundle, and the recorded historical bundle has no trustworthy timeframe binding. Do not use either set to infer the new contract. Resolve and explicitly approve the ordered schema and calculations from source and Stage B evidence before issuing a contract identity or starting a new training run.

## 4. Numerical backend and failure policy

- Backend identity and version are part of the contract and must match across training and inference.
- ATR: the current manual rolling-mean TR fallback is not equivalent to installed pandas-ta on tested variable-range fixtures. It must not silently substitute for the canonical backend.
- RSI: the current manual Wilder EWM fallback matched pandas-ta on tested fixtures, but universal equivalence is not established. It must not silently substitute until broader evidence and owner approval establish equivalence.
- MACD: there is no fallback. Missing MACD output must be a contract error when MACD is in the ordered feature list; no silent column omission.
- ADX remains the local implementation; its exact formula and numeric behavior must be included in the eventual contract identity.

The observed environment (NumPy 2.2.6, pandas 3.1.1, pandas-ta 0.4.71b0, pandas-ta-classic 0.6.52, scikit-learn 1.9.1, XGBoost 3.3.0) is recorded in the Stage A report. XGBoost cannot load on this host because `libomp.dylib` is missing.

## 5. Lookback, warm-up, and missing values

- At least 97 rows are needed for the current configured source to produce all 37 numeric candidate columns. This is a schema-presence threshold only; it is not a numerical-convergence guarantee.
- Training and inference must use the same declared history-length and warm-up policy. The tested 200-bar and 500-bar latest vectors differ beyond the preregistered tolerance in RSI, RSI slope, ATR percentile, and all three MACD columns.
- No future-to-past filling is permitted. Training samples with invalid warm-up features must be excluded or handled by an explicitly versioned policy; inference must reject invalid vectors.
- NaN, Inf, absent columns, dtype mismatch, and unexpected order must be detected explicitly. Unconditional `fillna(0)` must not turn an invalid model vector into a valid one.
- The exact history length and recursive-indicator convergence requirement remain unresolved; do not select 500 bars solely because that is the current trainer request.

## 6. Timeframe and configuration compatibility

- The inspected `retrain_model.py` source declares M15, but that declaration is not bound to the recovered historical bundle. Runtime accepts M15, H1, and H4. A model bundle must declare its training timeframe; missing timeframe metadata is `UNVERIFIABLE`, and a runtime mismatch must be rejected unless an explicit compatibility rule is approved.
- Runtime configuration is authoritative. Artifact configuration may be read for compatibility checking but must not silently mutate runtime configuration.
- The current artifact loader mutates the shared config object; the live FeatureEngine and ModelWrapper share `FEAT_CFG`. This remains a confirmed implementation gap, not a claim that runtime behavior has been changed.

## 7. Compatibility disposition

| Item | Current evidence | Disposition |
| --- | --- | --- |
| `trade_model_xgb.manifest.json` | Declares 34 feature names | Metadata only; not proof of model/scaler dimensions |
| `trade_model_xgb.cfg.json` | Present; enables MACD | Inspectable config, but not tied to a verified active bundle |
| Historical host bundle (2026-11-14 record) | 34-dimension model and scaler; ordered 34-name list; recorded same-second writes | `HISTORICALLY RECORDED / NOT INDEPENDENTLY VERIFIED`; does not establish current activity, source feature semantics, or timeframe |
| Current active model / scaler / ordered `.features.json` | Not present in this workspace or independently re-established | `NOT ESTABLISHED`; current compatibility `NOT VERIFIED` |
| October 37-feature backups | Model and names present; scaler association and shared provenance unproven | `UNVERIFIABLE`; excluded from controlled activation |
| 34 versus 37 feature schema | Historical record, local backups, and current source do not establish one current model schema | No compatibility claim; determine and issue a new contract before future training |
| Training timeframe | Not bound to historical bundle or local backups | `UNVERIFIABLE`; must be declared and source-bound for each future bundle |

## 8. Stage C decision

### 8.1 Accepted governance decisions

1. **New-contract authority:** Before any future model training, the owner must approve and issue one versioned Feature Contract defining the ordered feature schema, formulas, canonical backend and versions, candle/timeframe rules, target and preprocessing rules, and history/warm-up policy. Training and inference must bind to that same identity. A candidate list in this document is not itself an issued identity.
2. **Legacy disposition:** The historical 34-feature bundle is `HISTORICALLY RECORDED / NOT INDEPENDENTLY VERIFIED`; the current active bundle is `NOT ESTABLISHED`; October 37-feature backups are `UNVERIFIABLE`; training timeframe is `UNVERIFIABLE`. No legacy artifact lacking a verifiable contract binding may be loaded into a new controlled activation path. These labels do not assert that any historical production behavior has changed.
3. **Minimum evidence for a future training output:** Before a run is accepted as a contract-conforming bundle, record a common run identity and provenance binding the model, scaler, ordered feature list, and metadata to the same output. Capture and verify each file's SHA-256; model/scaler dimensions and ordered feature names; Feature Contract identity; instrument and training timeframe with a trustworthy source; training code revision; target, lookback, warm-up, missing-value and scaling rules; and exact relevant dependency/backend versions. Reject incomplete, mismatched, or unbound outputs. Formal immutable release-manifest and publication lifecycle remains Phase 3.4 scope.

Behavioral requirements are established, and Stage B has shown that parity is currently not established. Artifact Evidence Recovery is **UNSUCCESSFUL / CLOSED — EVIDENCE NOT RECOVERED**; its bounded old-artifact search is complete. Stage A and Stage B remain **ACCEPTED**. Stage C remains **BLOCKED** because the technical contract identity has not been issued and active-bundle compatibility is not established. Phase 3.2 therefore remains **OPEN**. This decision authorizes no retraining, production implementation, artifact write, deployment, READY wiring, or trading-path change.
