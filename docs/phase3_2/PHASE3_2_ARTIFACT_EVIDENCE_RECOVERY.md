# Phase 3.2 — Artifact Evidence Recovery

**Scope:** bounded read-only inventory of model, scaler, ordered feature names, timeframe, and bundle provenance. No production code, training, deployment, trading behavior, dependencies, or host environment were changed.

**Status:** `CLOSED — EVIDENCE NOT RECOVERED`

## Findings

### Historical host bundle recorded on 2026-11-14

[`PHASE3_1_CD_EVIDENCE.md`](PHASE3_1_CD_EVIDENCE.md#live-host-evidence-arm--2026-11-14) records a read-only inventory from host `arm` at `2026-11-14T07:51:42Z`. That snapshot reports:

| Evidence | Recorded result | What it establishes |
|---|---|---|
| `trade_model_xgb.json` | SHA-256 `94c8751df33daee5190e42634d823bcb08d4a0dbc1e0a2cf2f3e8cfbd91d5942`; XGBoost `n_features_in_ = 34` | Model identity and input dimension at snapshot time |
| `scaler.joblib` | SHA-256 `031ea8068a2b8309829624b30acb7db2cde40ce4452240cf423619fae4b2cd8c`; `StandardScaler`, `n_features_in_ = 34` | Scaler identity and dimension at snapshot time |
| `trade_model_xgb.features.json` | SHA-256 `3e9e319cae45dc405cf55ba49a2dd87fad8beacb4148d52066b2c79a697605da`; 34 ordered names | Ordered names at snapshot time |
| `trade_model_xgb.manifest.json` | SHA-256 `9b860295166d06c1445e5b335f621af6dc5d60ad2a905a9807c512a941ca27bb`; `created_at=2026-11-13T08:01:34.749304Z`; names match `.features.json` | Manifest metadata at snapshot time |
| Four files' mtimes | All recorded in the same second as manifest creation; write order was model, scaler, feature list, config, manifest | Strong evidence those recorded files were emitted together |

This is useful historical bundle evidence and proves its recorded dimensions were mutually consistent at capture time. The model/scaler/ordered feature bytes themselves are not present in this workspace, so their hashes and probe results cannot be independently rechecked here. The recorded config enables MACD while the feature list has 34 names and omits MACD; the same evidence report says config is a runtime snapshot, not reliable training metadata. Bundle provenance also points only to a likely, explicitly non-authoritative auto-training path, not a confirmed source revision.

### Timeframe evidence

- `retrain_model.py` declares `TIMEFRAME = "15m"` / OANDA `M15`, but there is no evidence binding that script execution to the historical 34-feature bundle above.
- The likely manifest-writing path in `fx_trade_bot_ml_v1.py` does not declare a timeframe in its manifest. Its source comment marks that path non-authoritative; its fetch call's effective granularity is not captured in the bundle evidence.
- The manifest and config contain no training timeframe.

**Result:** timeframe compatibility for the historical bundle is `UNVERIFIABLE`.

### Files currently in this workspace

| File | Observation | Classification |
|---|---|---|
| `trade_model_xgb_bak_20261007_0153.json` | Embedded XGBoost JSON declares `num_feature = 37`; local SHA-256 `682824abdb928f5d263b4110c976c062f76ab3f20c44460c542af573515a8165` | Old backup; not the 34-feature model hash in the historical host record |
| `trade_model_xgb.features_bak_20261007_0153.json` | 37 ordered names, including three MACD columns; local SHA-256 `a4d38adb0f7054d44dd7f432fbf9e216ee10f7dd226ec5b3dba6566deaa168cd` | Old backup; not the 34-name ordered list in the historical host record |
| `scaler_bak_20261007_0153.joblib` | Local SHA-256 `01a05031df9a235b0472f8838f18f9e8e03cd885dff7139596384935a875382b`; could not inspect because `joblib` is unavailable in the current Python environment | Old backup; no proven association with either model candidate |
| `trade_model_xgb.manifest.json` | 34 names; local SHA-256 `9b860295166d06c1445e5b335f621af6dc5d60ad2a905a9807c512a941ca27bb` | Metadata only; does not bind the local 37-feature backups to a bundle |
| `trade_model_xgb.cfg.json` | Enables MACD; SHA-256 matches the historical host record | Config snapshot only; not training-timeframe or feature-order evidence |

The current workspace has no active `trade_model_xgb.json`, `scaler.joblib`, or `trade_model_xgb.features.json`. The differently named October backups have no matching bundle manifest or verifiable shared provenance. **Classify those local legacy backups as `UNVERIFIABLE`; do not combine them with the 34-feature manifest or infer that either set is active.**

## Decision and bounded follow-up

- Artifact Evidence Recovery: `UNSUCCESSFUL` / `CLOSED — EVIDENCE NOT RECOVERED`.
- Stage A: `ACCEPT`.
- Stage B: `ACCEPT`.
- Stage C: `BLOCKED — ARTIFACT EVIDENCE`.
- Phase 3.2: `OPEN`.
- Historical 34-feature bundle: `HISTORICALLY RECORDED / NOT INDEPENDENTLY VERIFIED`.
- Current active bundle: `NOT ESTABLISHED`.
- October 37-feature backups: `UNVERIFIABLE`.
- Training timeframe: `UNVERIFIABLE`.
- Feature Contract Identity: `NOT ISSUED`.

The historical record establishes that a mutually dimension-consistent 34-feature bundle was recorded on `arm` on 2026-11-14, but does not establish its training timeframe or that it remains the active bundle. This bounded recovery task is closed without establishing current active-bundle identity. Do not continue open-ended searches or combine the historical record with the October backups.

The XGBoost `libomp.dylib` import issue remains a separate host-environment blocker. No dependency or environment changes were made as part of this evidence recovery.
