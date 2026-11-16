# Phase 3.2 — Document 05: Technically Eligible Candidate Freeze

**Date:** 2026-11-15  
**Status:** FROZEN (feature-level) — OWNER-SIGNED 2026-11-16; P3–P5 recorded as downstream activation blockers (see §2 and §5)  
**Scope:** Final Phase 3.2 technical eligibility handoff to Phase 3.3.

## 1. Purpose

Create one controlled record of which feature candidates have passed technical definition and required experiments. This document is the freeze record template. It does not pre-approve any candidate.

## 2. Freeze prerequisites

A candidate may be marked `TECHNICALLY ELIGIBLE` only when all applicable conditions are satisfied:

1. Target timeframe and input contract are approved.
2. Candidate formula, name, parameters and units are approved.
3. Canonical implementation/backend and dependency identity are fixed.
4. Warm-up and first-valid-row behavior are explicit.
5. Missing, invalid and non-finite behavior is explicit.
6. No-future-data behavior is established.
7. Deterministic fixture tests pass.
8. Training/inference parity passes.
9. History convergence passes where applicable.
10. Production history length is approved and the candidate's warm-up is supported at that length.
11. No unresolved blocker remains for the candidate.

A `DEFER` candidate cannot be frozen as technically eligible.

**Status note (2026-11-15):** the L2-A definition decisions (Doc 01 IC-*, Doc 02 FD-*) were recorded on 2026-11-15, which satisfies the definition-level prerequisites 1–5 for the `REDEFINE`/`ACCEPTABLE AS-IS` candidates that are not blocked. **No candidate is frozen**: prerequisites 8 (train/inference parity — P1/P2 not run) and 9 (convergence — offline only) remain unmet. All `Final status` values below therefore remain `NOT FROZEN` or `DEFER`.

**Status update (2026-11-15, appended — L2-B):** prerequisite 10 is now met — production history length is approved at 800 bars (RC-02, Doc 04, L2-B), supported by the Step 4 convergence report. The `atr_ecdf_50bar` tie-sensitivity finding is resolved as a documented R-class behaviour (Doc 02 §3.1), not an open blocker, and the frozen production length sits in its stable region. Freeze is still withheld because prerequisite 8 (train/inference parity P1/P2) is `NOT VERIFIED`; this is the remaining gating item.

**Status update (2026-11-16, appended — P1/P2 parity):** prerequisite 8 is now met **at the feature level**. Experiment `PARITY-P1P2-01` (protocol preregistered in Doc 03 §10) ran offline on this host and returned **P1 = PASS** (11/11 invalid fixtures → identical accept/reject on both paths) and **P2 = PASS** (5 deterministic fixtures × all 33 features: column names/order/dtype/missingness exact; every finite cell within `1e-10 + 1e-8·|B|`). Report: `experiments/phase3_2_feature_convergence/PARITY_P1P2_REPORT.md`. The training path (`retrain_model.py`) and the inference path (`fx_trade_bot*.py`) both route, under the default-OFF switch `USE_FEATURE_CONTRACT_V2`, into the single implementation `ml/feature_contract.build_features`, so parity follows from routing identity + determinism of that function. This satisfies prerequisite 8 **for the feature contract only**: P3–P5 (scaler / model-tensor / prediction-output) remain `NOT VERIFIED` (no active model / scaler / `.features.json` bundle in the repository), so `FULL_PARITY_STATUS` stays `NOT VERIFIED` and the freeze **remains withheld**. No candidate is frozen by this update.

**Status update (2026-11-16, appended — owner freeze-scope decision):** the owner has adjudicated the freeze scope: **freeze at the feature-contract level only**, recording P3–P5 as downstream activation blockers and **not** waiving, downgrading or marking them `NOT REQUIRED` (Revision Plan §248). Under that scope, prerequisites 1–11 are satisfied for every candidate that is inside the 33-column `ORDERED_FEATURES` contract: definitions (FD-01..09), single canonical backend, warm-up/invalidity semantics, deterministic fixture tests, P1/P2 parity, Step-4 convergence and the 800-bar production length (RC-02) are all recorded. The §3 register is therefore back-filled with the feature-level eligibility finding, and §5 carries the corresponding freeze decision **pending the owner signature**. `is_london` / `is_ny` remain `DEFER` (session interval not defined); `vol_sma_ratio` / `vol_trend` are `EXCLUDE` (FD-07). This update records the finding and scope; it does **not** by itself issue the freeze — that act is the §5 signature.

## 3. Candidate freeze register

| Candidate | Proposed name | Matrix disposition | Formula decision | Backend decision | Warm-up decision | Correctness/parity | Convergence | Production-length support | Final status |
|---|---|---|---|---|---|---|---|---|---|
| ret_1h | return_15m | REDEFINE | RESOLVED (FD-02) | RESOLVED — feature_contract.py | RESOLVED (FD-09) | P1/P2 PASS | PASS | 800 bars (RC-02) | TECHNICALLY ELIGIBLE (feature-level) |
| ret_3h | return_45m | REDEFINE | RESOLVED (FD-02) | RESOLVED — feature_contract.py | RESOLVED (FD-09) | P1/P2 PASS | PASS | 800 bars (RC-02) | TECHNICALLY ELIGIBLE (feature-level) |
| ret_6h | return_90m | REDEFINE | RESOLVED (FD-02) | RESOLVED — feature_contract.py | RESOLVED (FD-09) | P1/P2 PASS | PASS | 800 bars (RC-02) | TECHNICALLY ELIGIBLE (feature-level) |
| ret_12h | return_3h | REDEFINE | RESOLVED (FD-02) | RESOLVED — feature_contract.py | RESOLVED (FD-09) | P1/P2 PASS | PASS | 800 bars (RC-02) | TECHNICALLY ELIGIBLE (feature-level) |
| ret_log | log_return_15m | REDEFINE | RESOLVED (FD-02) | RESOLVED — feature_contract.py | RESOLVED (FD-09) | P1/P2 PASS | PASS | 800 bars (RC-02) | TECHNICALLY ELIGIBLE (feature-level) |
| vol_12h | horizon_vol_3h | REDEFINE | RESOLVED (FD-02) | RESOLVED — feature_contract.py | RESOLVED (FD-09) | P1/P2 PASS | PASS | 800 bars (RC-02) | TECHNICALLY ELIGIBLE (feature-level) |
| vol_24h | horizon_vol_6h | REDEFINE | RESOLVED (FD-02) | RESOLVED — feature_contract.py | RESOLVED (FD-09) | P1/P2 PASS | PASS | 800 bars (RC-02) | TECHNICALLY ELIGIBLE (feature-level) |
| vol_48h | horizon_vol_12h | REDEFINE | RESOLVED (FD-02) | RESOLVED — feature_contract.py | RESOLVED (FD-09) | P1/P2 PASS | PASS | 800 bars (RC-02) | TECHNICALLY ELIGIBLE (feature-level) |
| body | body | ACCEPTABLE AS-IS | RESOLVED (FD-02) | RESOLVED — feature_contract.py | RESOLVED (FD-09) | P1/P2 PASS | PASS | 800 bars (RC-02) | TECHNICALLY ELIGIBLE (feature-level) |
| upper_wick | upper_wick | ACCEPTABLE AS-IS | RESOLVED (FD-02) | RESOLVED — feature_contract.py | RESOLVED (FD-09) | P1/P2 PASS | PASS | 800 bars (RC-02) | TECHNICALLY ELIGIBLE (feature-level) |
| lower_wick | lower_wick | ACCEPTABLE AS-IS | RESOLVED (FD-02) | RESOLVED — feature_contract.py | RESOLVED (FD-09) | P1/P2 PASS | PASS | 800 bars (RC-02) | TECHNICALLY ELIGIBLE (feature-level) |
| range | range | ACCEPTABLE AS-IS | RESOLVED (FD-02) | RESOLVED — feature_contract.py | RESOLVED (FD-09) | P1/P2 PASS | PASS | 800 bars (RC-02) | TECHNICALLY ELIGIBLE (feature-level) |
| direction | direction | REDEFINE | RESOLVED (FD-02) | RESOLVED — feature_contract.py | RESOLVED (FD-09) | P1/P2 PASS | PASS | 800 bars (RC-02) | TECHNICALLY ELIGIBLE (feature-level) |
| atr | atr | REDEFINE | RESOLVED (FD-02 + FD-03) | RESOLVED — feature_contract.py | RESOLVED (FD-09) | P1/P2 PASS | PASS | 800 bars (RC-02) | TECHNICALLY ELIGIBLE (feature-level) |
| atr_pct | atr_pct | REDEFINE | RESOLVED (FD-02 + FD-03) | RESOLVED — feature_contract.py | RESOLVED (FD-09) | P1/P2 PASS | PASS | 800 bars (RC-02) | TECHNICALLY ELIGIBLE (feature-level) |
| atr_percentile | atr_ecdf_50bar | REDEFINE | RESOLVED (FD-03 §3.1) | RESOLVED — feature_contract.py | RESOLVED (FD-09) | P1/P2 PASS | PASS | 800 bars (RC-02) | TECHNICALLY ELIGIBLE (feature-level) |
| atr_ma | atr_ma | REDEFINE | RESOLVED (FD-02 + FD-03) | RESOLVED — feature_contract.py | RESOLVED (FD-09) | P1/P2 PASS | PASS | 800 bars (RC-02) | TECHNICALLY ELIGIBLE (feature-level) |
| atr_expanding | atr_above_sma14 | REDEFINE | RESOLVED (FD-02 + FD-03) | RESOLVED — feature_contract.py | RESOLVED (FD-09) | P1/P2 PASS | PASS | 800 bars (RC-02) | TECHNICALLY ELIGIBLE (feature-level) |
| atr_ratio | atr_ratio | REDEFINE | RESOLVED (FD-02 + FD-03) | RESOLVED — feature_contract.py | RESOLVED (FD-09) | P1/P2 PASS | PASS | 800 bars (RC-02) | TECHNICALLY ELIGIBLE (feature-level) |
| rsi | rsi | REDEFINE | RESOLVED (FD-02 + FD-04) | RESOLVED — feature_contract.py | RESOLVED (FD-09) | P1/P2 PASS | PASS | 800 bars (RC-02) | TECHNICALLY ELIGIBLE (feature-level) |
| rsi_slope | rsi_slope_45m | REDEFINE | RESOLVED (FD-02 + FD-04) | RESOLVED — feature_contract.py | RESOLVED (FD-09) | P1/P2 PASS | PASS | 800 bars (RC-02) | TECHNICALLY ELIGIBLE (feature-level) |
| adx | adx | REDEFINE | RESOLVED (FD-02 + FD-06) | RESOLVED — feature_contract.py | RESOLVED (FD-09) | P1/P2 PASS | PASS | 800 bars (RC-02) | TECHNICALLY ELIGIBLE (feature-level) |
| MACD_12_26_9 | macd | REDEFINE | RESOLVED (FD-02 + FD-05) | RESOLVED — feature_contract.py | RESOLVED (FD-09) | P1/P2 PASS | PASS | 800 bars (RC-02) | TECHNICALLY ELIGIBLE (feature-level) |
| MACDh_12_26_9 | macd_hist | REDEFINE | RESOLVED (FD-02 + FD-05) | RESOLVED — feature_contract.py | RESOLVED (FD-09) | P1/P2 PASS | PASS | 800 bars (RC-02) | TECHNICALLY ELIGIBLE (feature-level) |
| MACDs_12_26_9 | macd_signal | REDEFINE | RESOLVED (FD-02 + FD-05) | RESOLVED — feature_contract.py | RESOLVED (FD-09) | P1/P2 PASS | PASS | 800 bars (RC-02) | TECHNICALLY ELIGIBLE (feature-level) |
| dist_high_24 | dist_high_6h | REDEFINE | RESOLVED (FD-02) | RESOLVED — feature_contract.py | RESOLVED (FD-09) | P1/P2 PASS | PASS | 800 bars (RC-02) | TECHNICALLY ELIGIBLE (feature-level) |
| dist_low_24 | dist_low_6h | REDEFINE | RESOLVED (FD-02) | RESOLVED — feature_contract.py | RESOLVED (FD-09) | P1/P2 PASS | PASS | 800 bars (RC-02) | TECHNICALLY ELIGIBLE (feature-level) |
| dist_high_48 | dist_high_12h | REDEFINE | RESOLVED (FD-02) | RESOLVED — feature_contract.py | RESOLVED (FD-09) | P1/P2 PASS | PASS | 800 bars (RC-02) | TECHNICALLY ELIGIBLE (feature-level) |
| dist_low_48 | dist_low_12h | REDEFINE | RESOLVED (FD-02) | RESOLVED — feature_contract.py | RESOLVED (FD-09) | P1/P2 PASS | PASS | 800 bars (RC-02) | TECHNICALLY ELIGIBLE (feature-level) |
| dist_high_96 | dist_high_24h | REDEFINE | RESOLVED (FD-02) | RESOLVED — feature_contract.py | RESOLVED (FD-09) | P1/P2 PASS | PASS | 800 bars (RC-02) | TECHNICALLY ELIGIBLE (feature-level) |
| dist_low_96 | dist_low_24h | REDEFINE | RESOLVED (FD-02) | RESOLVED — feature_contract.py | RESOLVED (FD-09) | P1/P2 PASS | PASS | 800 bars (RC-02) | TECHNICALLY ELIGIBLE (feature-level) |
| vol_sma_ratio | vol_sma_ratio | EXCLUDE | N/A (FD-07) | N/A (FD-07) | N/A (FD-07) | N/A | N/A | N/A | EXCLUDE |
| vol_trend | vol_trend | EXCLUDE | N/A (FD-07) | N/A (FD-07) | N/A (FD-07) | N/A | N/A | N/A | EXCLUDE |
| hour | utc_hour | REDEFINE | RESOLVED (FD-02) | RESOLVED — feature_contract.py | RESOLVED (FD-09) | P1/P2 PASS | PASS | 800 bars (RC-02) | TECHNICALLY ELIGIBLE (feature-level) |
| day_of_week | utc_day_of_week | REDEFINE | RESOLVED (FD-02) | RESOLVED — feature_contract.py | RESOLVED (FD-09) | P1/P2 PASS | PASS | 800 bars (RC-02) | TECHNICALLY ELIGIBLE (feature-level) |
| is_london | is_london | DEFER | BLOCKED: session interval/boundaries | BLOCKED | BLOCKED | NOT RUN | NOT ESTABLISHED | NOT ESTABLISHED | DEFER |
| is_ny | is_ny | DEFER | BLOCKED: session interval/boundaries | BLOCKED | BLOCKED | NOT RUN | NOT ESTABLISHED | NOT ESTABLISHED | DEFER |

Register notes (2026-11-16 back-fill):
- `Correctness/parity = P1/P2 PASS` cites `experiments/phase3_2_feature_convergence/PARITY_P1P2_REPORT.md` (experiment `PARITY-P1P2-01`, Doc 03 §10).
- `Convergence = PASS` cites `experiments/phase3_2_feature_convergence/REPORT.md` (Step 4; main acceptance pairs `300v500`, `500v800` pass for all fixtures/features).
- `Production-length support = 800 bars (RC-02)` cites Doc 04 §RC-02 and the Step 4 report.
- `Backend decision = RESOLVED — feature_contract.py` = the single canonical implementation (`ml/feature_contract.py`); no silent fallback (FD-03).
- Feature-level eligibility becomes effective on the owner signature in §5; P3–P5 remain `NOT VERIFIED` downstream activation blockers.

## 4. Required evidence package

Attach or reference:
- Approved Document 01 input-contract decision record.
- Approved Document 02 feature decisions.
- Approved Document 03 experiment protocol and per-feature reports.
- Approved Document 04 runtime configuration decisions.
- Source commit and clean/dirty status.
- Dependency/backend lock identity.
- Per-feature formula fixture report.
- Train/inference parity report.
- History convergence report.
- Production history-length approval and support comparison.
- Explicit list of deferred/excluded candidates and reasons.

## 5. Freeze decision

> **SIGNED — feature-level freeze effective 2026-11-16.** The freeze is issued at the feature-contract level under the owner scope decision of 2026-11-16 (Doc 05 §2). P3–P5 (`scaler` / model-tensor / prediction-output parity) remain `NOT VERIFIED` downstream activation blockers and are **not** waived.

| Field | Value |
|---|---|
| Freeze scope | Feature-contract level (33-column `ORDERED_FEATURES`); P3–P5 downstream activation blockers recorded, not waived |
| Eligible candidate list | 33 feature-level candidates (all rows in §3 with `Final status = TECHNICALLY ELIGIBLE (feature-level)`) |
| Excluded candidates | `vol_sma_ratio`, `vol_trend` — `EXCLUDE` (FD-07) |
| Deferred candidates | `is_london`, `is_ny` — `DEFER` (session interval/boundaries not defined; Calendar Contract §7/§9 fail-closed) |
| Ordered model input schema | `ORDERED_FEATURES` (33 cols) as implemented in `ml/feature_contract.py`; final Phase 3.3 predictive-value schema not complete |
| Feature Contract Identity | `FCV2-bffdb0005083f95e` (sha256 `bffdb0005083f95e2030df7ec912af2e87ec930fdd3672f0b1a0d5530e9a0a8c`) |
| Evidence bundle identity/hash | `3a6ea118b5520dba` (sha256 `3a6ea118b5520dba2462e2ca57dd93bd6e98748f21e95239ca8797e6f91a4c88`) |
| Owner approver | owner |
| Approval date | 2026-11-16 |
| `FULL_PARITY_STATUS` | `NOT VERIFIED` (P3–P5 unverified) |

Identity derivation (reproducible):
- **Feature Contract Identity** = `sha256` of `json.dumps({"features": ORDERED_FEATURES, "params": {ATR_N, RSI_N, ADX_N, MACD_FAST, MACD_SLOW, MACD_SIGNAL, ECDF_WINDOW, ATR_SMA_N, ATR_RATIO_N}}, sort_keys=True, separators=(",",":"))` — i.e. the 33-name ordered schema plus the FD-03..FD-06 frozen parameters.
- **Evidence bundle hash** = `sha256` of the newline-joined `<relpath> <sha256>` manifest over this fixed input set: Doc 01, Doc 02, Doc 03, Doc 04, Calendar Contract, `experiments/phase3_2_feature_convergence/REPORT.md`, `experiments/phase3_2_feature_convergence/PARITY_P1P2_REPORT.md`, `ml/feature_contract.py`, `tests/test_feature_contract.py` — at evidence baseline commit `7868a50` (origin/v2026c).

## 6. Phase 3.3 handoff

Only candidates marked `TECHNICALLY ELIGIBLE` may be handed to Phase 3.3 for predictive-value evaluation. Phase 3.3 may select or reject candidates for predictive reasons, but must not silently alter their technical definitions.

The final ordered model schema requires both:
- Phase 3.2 technical eligibility; and
- Phase 3.3 predictive-value decisions.

## 7. Authorization boundary

This freeze template does not authorize production code changes, model training, artifact writes, deployment, READY activation or trading behavior changes. A later implementation task must cite the approved decisions and carry its own scope and acceptance criteria.

## 8. DEFER candidate adjudication (appended 2026-11-16 — closes "DEFER limbo")

Purpose: give every candidate that was left `DEFER` in §3 a **formal disposition** with a stated reason and an evidence citation, so that no candidate remains in limbo. This section performs **attribution adjudication + register update only**; it does **not** alter any already-approved technical definition and it does **not** freeze any candidate.

**Scope note (register reconciliation):** §4 task b of the handover names 15 rows. The register's `DEFER` final-status set is 14 rows; the 15th name (`atr_percentile`) carried the documented internal inconsistency — its *matrix disposition* was `REDEFINE` while its *final status* was `DEFER`. That inconsistency is corrected below: `atr_percentile` is adjudicated with its ATR peers as `REDEFINE`.

### 8.1 Adjudication register

| Candidate | Prior state | Disposition | Reason | Evidence |
|---|---|---|---|---|
| atr | DEFER | **RESOLVE → REDEFINE** | Definition already owner-approved; the former blocker was backend ambiguity (pandas_ta vs manual fallback), which the new single-backend contract removes | Doc 02 FD-03; Doc 03 §10; `PARITY_P1P2_REPORT.md` (P2 PASS) |
| atr_pct | DEFER | **RESOLVE → REDEFINE** | Derived from canonical ATR; same backend-ambiguity removal | Doc 02 FD-03; `PARITY_P1P2_REPORT.md` |
| atr_percentile | DEFER (final) / REDEFINE (matrix) | **RESOLVE → REDEFINE** (inconsistency fixed) | `atr_ecdf_50bar` definition approved (ECDF window 50, inclusive-rank); tie-sensitivity is documented R-class behaviour, not a blocker | Doc 02 FD-03 + §3.1; Doc 03 §10; `PARITY_P1P2_REPORT.md` |
| atr_ma | DEFER | **RESOLVE → REDEFINE** | Derived (SMA-14 of ATR); same backend-ambiguity removal | Doc 02 FD-03; `PARITY_P1P2_REPORT.md` |
| atr_expanding | DEFER | **RESOLVE → REDEFINE** | Resolved as `atr_above_sma14` boolean under approved ATR family | Doc 02 FD-03; `PARITY_P1P2_REPORT.md` |
| atr_ratio | DEFER | **RESOLVE → REDEFINE** | Derived (ATR ratio, window 28); same backend-ambiguity removal | Doc 02 FD-03; `PARITY_P1P2_REPORT.md` |
| rsi | DEFER | **RESOLVE → REDEFINE** | Definition approved (Wilder n=14; flat → 50); backend ambiguity removed | Doc 02 FD-04; `PARITY_P1P2_REPORT.md` |
| rsi_slope | DEFER | **RESOLVE → REDEFINE** | Definition approved (`rsi_slope_45m = RSI[t]-RSI[t-3]`) | Doc 02 FD-04; `PARITY_P1P2_REPORT.md` |
| MACD_12_26_9 | DEFER | **RESOLVE → REDEFINE** | Definition approved (EMA 12/26/9, `adjust=False`, first-value seed) | Doc 02 FD-05; `PARITY_P1P2_REPORT.md` |
| MACDh_12_26_9 | DEFER | **RESOLVE → REDEFINE** | Produced in the same shared valid range as MACD | Doc 02 FD-05; `PARITY_P1P2_REPORT.md` |
| MACDs_12_26_9 | DEFER | **RESOLVE → REDEFINE** | Produced in the same shared valid range as MACD | Doc 02 FD-05; `PARITY_P1P2_REPORT.md` |
| vol_sma_ratio | DEFER / BLOCKED | **EXCLUDE** | FD-07 excludes volume features for the new contract; register no longer says BLOCKED | Doc 02 FD-07; Revision Plan §10.1 |
| vol_trend | DEFER / BLOCKED | **EXCLUDE** | FD-07 excludes volume features for the new contract; register no longer says BLOCKED | Doc 02 FD-07; Revision Plan §10.1 |
| is_london | DEFER | **KEEP DEFER** | Session-window definition for this local feature is not yet owner-approved; the Calendar Contract explicitly does **not** define it, and the adjacent gap classifier remains fail-closed | Calendar Contract §7 (status), §9; Revision Plan §5.2 |
| is_ny | DEFER | **KEEP DEFER** | Same as `is_london` | Calendar Contract §7 (status), §9; Revision Plan §5.2 |

### 8.2 Consequences

- The two volume rows move from `BLOCKED` to `EXCLUDE`; the register (§3) now carries `EXCLUDE` for `vol_sma_ratio`/`vol_trend`.
- The ATR/RSI/MACD families move from `DEFER` to `REDEFINE`, with `Correctness/parity = P1/P2 PASS`, `Convergence = PASS` and `Production-length support = 800 bars (RC-02)` recorded in §3.
- `atr_percentile`'s matrix disposition and final status are now consistent (`REDEFINE`).
- `is_london`/`is_ny` remain `DEFER`; they are **not** eligible and must not enter Phase 3.3 until the session definition is approved and the feature is adjudicated.
- **No candidate is frozen by this adjudication.** A `REDEFINE` disposition is a *definition/direction* decision, not technical eligibility: prerequisites 6, 7, 11 and the P3–P5 parity layers remain to be satisfied, and owner approval is still required before any candidate becomes `TECHNICALLY ELIGIBLE`.
