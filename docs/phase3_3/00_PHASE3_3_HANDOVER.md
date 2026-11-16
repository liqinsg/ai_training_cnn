# Phase 3.3 — Feature Candidate Handover

**Document ID:** `PHASE3_3_HANDOVER`
**Date:** 2026-11-16
**From:** Phase 3.2 — Candidate Freeze (feature level, owner-signed 2026-11-16)
**To:** Phase 3.3 — predictive-value evaluation
**Status:** DRAFT — awaiting Phase 3.3 owner acceptance
**Nature:** Feature **Candidate** handover. **Not** a model-implementation handover.

---

## 1. Purpose

Hand over the **33 technically-eligible feature candidates**, together with their frozen technical identity and evidence, to Phase 3.3 for **predictive-value** evaluation.

This package:

- hands over **candidates and evaluation tasks only**;
- does **not** freeze a prediction schema;
- does **not** issue a model artifact identity;
- does **not** authorize implementation, training, deployment or trading-behavior changes.

Authority: Revision Plan §365 — "Step7: only hand over technically-eligible candidates; predictive value decided independently; **does not freeze the prediction schema, does not issue identity, does not authorize implementation**."

## 2. Source record (upstream, already signed)

| Item | Value |
|---|---|
| Phase 3.2 freeze record | `docs/phase3_2/05_TECHNICALLY_ELIGIBLE_CANDIDATE_FREEZE.md` §5 (SIGNED) |
| Freeze scope | feature-contract level (33-column `ORDERED_FEATURES`) |
| Feature Contract Identity | `FCV2-bffdb0005083f95e` (sha256 `bffdb0005083f95e2030df7ec912af2e87ec930fdd3672f0b1a0d5530e9a0a8c`) |
| Evidence bundle identity | `3a6ea118b5520dba` (sha256 `3a6ea118b5520dba2462e2ca57dd93bd6e98748f21e95239ca8797e6f91a4c88`) |
| Owner approver / date | owner / 2026-11-16 |
| Evidence baseline commit | `7868a50` (origin/v2026c) |
| Upstream parity | P1 PASS · P2 PASS · **P3–P5 `NOT VERIFIED`** |
| `FULL_PARITY_STATUS` | `NOT VERIFIED` |

## 3. What this handover transfers (allowed)

| Content | Notes |
|---|---|
| 33 feature names and their order | canonical `ORDERED_FEATURES` order (see `01_…REGISTER.md`) |
| Each feature's definition + parameters | as frozen by FD-01..FD-09; **not to be altered** |
| Feature Contract Identity | `FCV2-bffdb0005083f95e` |
| Input contract + timestamp semantics | M15, candle-OPEN, whole-batch rejection (IC-02/IC-04/IC-06) |
| Production history length | 800 bars (RC-02) |
| P1/P2 parity results | `PARITY_P1P2_REPORT.md` |
| Convergence results + documented exception | `REPORT.md` (`atr_ecdf_50bar` tie-sensitivity = R-class) |
| The 2 `EXCLUDE` reasons | `vol_sma_ratio`, `vol_trend` (FD-07) |
| The 2 `DEFER` reasons | `is_london`, `is_ny` (session interval not defined) |
| P3–P5 blocking facts | mandatory handover item (see `03_…` and `05_…`) |
| Predictive-value evaluation as a Phase 3.3 **research task** | protocol in `02_…` |

## 4. What is NOT transferred (retained / needs new authorization)

| Content | Restriction |
|---|---|
| Final `PredictionResult` schema | not approved |
| Scaler production configuration | P3 not verified |
| Model input Tensor Contract | P4 not verified |
| Prediction output parity | P5 not verified |
| Model training | new authorization required |
| Artifact write / overwrite / publish | new authorization required |
| `USE_FEATURE_CONTRACT_V2` default ON | not allowed |
| Live-prediction wiring (READY / hook) | not allowed |
| Trading-behavior change | not allowed |

A full statement of the boundary is in `04_AUTHORIZATION_BOUNDARY.md`.

## 5. Upstream status carried forward (not to be overstated)

- Phase 3.2 **Step6** (Candidate Freeze) is **completed and owner-signed at the feature level**. **Step7** (Phase 3.3 handover) is **prepared but remains pending Phase 3.3 owner acceptance**. The 33 feature candidates retain their signed feature-level freeze status: 33 `TECHNICALLY ELIGIBLE (feature-level)`, 2 `EXCLUDE`, 2 `DEFER`.
- `TECHNICALLY ELIGIBLE` means the candidate passed its technical definition and eligibility checks; it is **not** evidence of predictive value.
- No model activation, no prediction-schema freeze, no implementation authorization, no trading-behavior authorization is granted by this handover.

## 6. Package index

| File | Responsibility |
|---|---|
| `00_PHASE3_3_HANDOVER.md` | this file — purpose, source, scope, explicit non-authorizations |
| `01_FEATURE_CANDIDATE_REGISTER.md` | the 33 candidates (+ 2 EXCLUDE + 2 DEFER), preserving original order and identity |
| `02_FEATURE_VALUE_EVALUATION_PROTOCOL.md` | how predictive value is evaluated (baselines, ablation, out-of-time, cost, leakage control, multiple-comparison control) |
| `03_BLOCKER_AND_DEFERRED_ITEMS.md` | P3–P5, session, legacy-artifact mismatch, and registered risks R1–R5 |
| `04_AUTHORIZATION_BOUNDARY.md` | what Phase 3.3 may / may not do; conditions to unlock |
| `05_P3_P5_LEGACY_BUNDLE_NEGATIVE_VALIDATION.md` | read-only negative validation of the legacy bundle — **executed 2026-11-16, with recorded evidence** (not a plan) |

## 7. Acceptance

Phase 3.3 owner acceptance record:

> **Accepted by:** owner
> **Acceptance date:** 2026-11-16
> **Status:** ACCEPTED — **research handover only**
>
> Phase 3.2 completed through the feature-level **Step6** candidate freeze (owner-signed 2026-11-16). **Step7** — the Phase 3.3 handover of the **33 technically-eligible feature candidates**, together with their frozen technical identity and evidence — is **accepted for predictive-value research only**, as scoped in §3.
>
> P1/P2 parity is PASS. P3–P5 remain `NOT VERIFIED`; `FULL_PARITY_STATUS = NOT VERIFIED`. These are retained **un-waived** as downstream activation blockers.
>
> **Not granted by this acceptance:** final `PredictionResult` / prediction schema; model training; artifact write / overwrite / publish; `USE_FEATURE_CONTRACT_V2` default ON; live-prediction (READY / `live_hook`) wiring; deployment; trading-behavior change. Each requires a separate, explicit owner authorization.

> **Governance distinction:** Phase 3.3 Owner Acceptance accepts the **research handover only**. It is **not** owner approval of any future Phase 3.3 implementation action — model training, artifact publication, and inference wiring must each be authorized separately. (The may / may-not boundary is stated in `04_AUTHORIZATION_BOUNDARY.md`.)

## 8. Record discipline

- This package is **append-only**: new state is recorded by appending; approved wording is not rewritten.
- Phase 3.3 may select or reject candidates **for predictive reasons only**; it **must not** silently alter any technical definition or the Feature Contract Identity.
- Predictive rejection or selection in Phase 3.3 shall be recorded as a **downstream disposition** (a Phase 3.3 Candidate Disposition Register). It shall **not** rewrite the signed Phase 3.2 candidate register, alter the frozen feature definitions, or silently change the Feature Contract Identity. (Example: a candidate that is technically eligible but rejected for lack of predictive value is recorded as *eligible / rejected-for-value* — the original 33-column list and `FCV2` are unchanged.)
- Any change to a definition, parameter, or the identity requires returning to the Phase 3.2 owner decision process.
