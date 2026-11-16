# Phase 3.3 — Blocker and Deferred Items

**Document ID:** `PHASE3_3_BLOCKER_AND_DEFERRED`
**Date:** 2026-11-16
**Purpose:** Carry forward, unchanged and un-waived, every item that blocks full parity, activation, or feature admission, plus the risks registered by the external review of 2026-11-16.

Nothing in this document is waived, downgraded, or marked `NOT REQUIRED`.

---

## 1. Parity blockers (P3–P5)

| Layer | Meaning | Status | Root cause | Next action |
|---|---|---|---|---|
| **P3** | Scaler input/output consistency | `NOT VERIFIED` | no scaler aligned to the 33-column contract | requires a new **aligned bundle** → new authorization |
| **P4** | Model input-tensor consistency | `NOT VERIFIED` | no model input contract aligned to the contract | same |
| **P5** | Model prediction-output consistency | `NOT VERIFIED` | no aligned model + reference outputs | same |
| **`FULL_PARITY_STATUS`** | overall | **`NOT VERIFIED`** | P3–P5 unverified | do not claim full/e2e/activation-ready until closed |

- P1 (raw input) and P2 (feature output) are **PASS** (see `docs/phase3_2/05_…FREEZE.md` §2 and `PARITY_P1P2_REPORT.md`).
- P1/P2 PASS is **not** a substitute for P3–P5 and must not be described as end-to-end production-path parity.
- Producing an aligned bundle requires **training and/or artifact writes**, which are outside the current red lines (see `04_AUTHORIZATION_BOUNDARY.md`).
- **Read-only partial validation is done and recorded** (legacy bundle correct-rejection): see `05_P3_P5_LEGACY_BUNDLE_NEGATIVE_VALIDATION.md`. It closes **only** "legacy bundle correctly identified as incompatible" — it does **not** close P3, P4, or P5.

## 2. Session features (`is_london` / `is_ny`) — `DEFER`

| Item | Status | Why | Owner / next action |
|---|---|---|---|
| `is_london` | DEFER | session interval / boundaries not owner-defined | **owner** defines trading semantics; Calendar Contract formalizes; feature consumes |
| `is_ny` | DEFER | same | same |

Split of responsibility (must not be collapsed):

1. **Owner** decides the trading semantics (which local times; inclusive/exclusive ends; overlap; holidays; DST).
2. **Calendar Contract** formalizes it as the single authority (`session_id`, `timezone`, `start_local_time`, `end_local_time`, inclusivity, `calendar_version`, `dst_policy`, `holiday_policy`). Field structure is a proposal — **no session value is approved** here.
3. **Feature Contract** consumes only an approved Calendar Contract.

Fail-closed rule: if the time definition is missing, unparseable, DST-ambiguous, or version-mismatched, the feature must stay unresolved. `0 = not in session` and `UNKNOWN = cannot determine` are **different states** and must not be conflated.

Current recommendation carried forward: keep both features DEFER and out of the Phase 3.3 candidate set until the Calendar Contract is revised and re-approved.

## 3. Legacy artifact mismatch

- The repository's runtime bundle (`trade_model_xgb.json`, `trade_model_xgb.features.json`, `scaler.joblib`) uses the **legacy 34-feature schema**, which is incompatible with the frozen 33-column contract.
- Verified read-only: `INCOMPATIBLE`, fails closed, no artifact writes. Evidence in `05_P3_P5_LEGACY_BUNDLE_NEGATIVE_VALIDATION.md`.

## 4. Closed items (for completeness)

| Item | Status |
|---|---|
| `vol_sma_ratio`, `vol_trend` | **EXCLUDE** (FD-07) — closed, no action |
| Phase 3.2 DEFER limbo (ATR/RSI/MACD families) | closed → `REDEFINE` (Doc 05 §8) |

## 5. Registered risks

Registered by the external review (2026-11-16); ownership and disposition are for the owner to accept.

| ID | Risk | Level | Note / next action |
|---|---|---|---|
| **R1** | Feature Contract Identity scope | High | FCID covers feature order + 9 frozen params; it does **not by itself** prove code, dependency, tzdb or data-source identity. Keep FCID **and** the evidence bundle **and** env pin; do not over-interpret FCID as full production-environment identity. |
| **R2** | Evidence bundle vs. current repo state | Medium | Bundle baseline is commit `7868a50`; HEAD has since advanced to `d6db32c`. Confirm whether later commits touch any bundled file. |
| **R3** | Data leakage in Phase 3.3 | High | Controlled by `02_FEATURE_VALUE_EVALUATION_PROTOCOL.md` §4–§5 (purge/embargo, fold-local preprocessing, untouched holdout, cross-instrument isolation). |
| **R4** | Multiple-comparison / selection bias | Medium | Controlled by `02_…PROTOCOL.md` §9 (trial budget, FDR/Bonferroni, holdout re-confirmation). |
| **R5** | "Default-OFF" ≠ zero side effect | Medium | The `USE_FEATURE_CONTRACT_V2` switch is default OFF, but import/init/file-read/config-load on the legacy path has **not** been proven unchanged. **Open item** — verify before any activation discussion. |

## 6. Open-item summary

| Open item | Blocking what | Owner action needed |
|---|---|---|
| P3–P5 | full parity, activation | new authorization (aligned bundle) |
| `is_london` / `is_ny` | 2 feature admissions | owner defines session semantics |
| R5 (legacy-path side-effect check) | activation safety | verification task |
| R2 (bundle-vs-HEAD drift) | evidence validity | confirm no bundled file changed after `7868a50` |
