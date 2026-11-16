# Phase 3.3 — Feature Candidate Register

**Document ID:** `PHASE3_3_FEATURE_CANDIDATE_REGISTER`
**Date:** 2026-11-16
**Source of truth:** `docs/phase3_2/05_TECHNICALLY_ELIGIBLE_CANDIDATE_FREEZE.md` §3 (owner-signed 2026-11-16)
**Rule:** This register preserves the candidates' **original order and technical identity**. Phase 3.3 must not alter any definition, parameter, or the Feature Contract Identity.

---

## 1. Identity

| Field | Value |
|---|---|
| Feature Contract Identity | `FCV2-bffdb0005083f95e` (sha256 `bffdb0005083f95e2030df7ec912af2e87ec930fdd3672f0b1a0d5530e9a0a8c`) |
| Evidence bundle identity | `3a6ea118b5520dba` |
| Canonical implementation | `ml/feature_contract.py` (single backend; no silent fallback) |
| Timeframe / timestamp | M15 / candle-OPEN (IC-02, RC-03) |
| Production history length | 800 bars (RC-02) |
| Frozen parameters | `ATR_N=14, RSI_N=14, ADX_N=14, MACD=12/26/9, ECDF_WINDOW=50, ATR_SMA_N=14, ATR_RATIO_N=28` |

## 2. Eligible candidates (33) — canonical `ORDERED_FEATURES` order

Legend: **Formula** = owner decision ID(s); **Backend** = `feature_contract.py`; **Warm-up** = FD-09; **Parity** = P1/P2 (`PARITY_P1P2_REPORT.md`); **Conv** = convergence (`REPORT.md`); **Prod** = production-length support (RC-02). All rows: `Final status = TECHNICALLY ELIGIBLE (feature-level)`.

| # | Feature | Matrix disposition | Formula | Warm-up | Parity | Conv | Prod |
|--:|---|---|---|---|---|---|---|
| 1 | `return_15m` | REDEFINE | FD-02 | FD-09 | P1/P2 PASS | PASS | 800 |
| 2 | `return_45m` | REDEFINE | FD-02 | FD-09 | P1/P2 PASS | PASS | 800 |
| 3 | `return_90m` | REDEFINE | FD-02 | FD-09 | P1/P2 PASS | PASS | 800 |
| 4 | `return_3h` | REDEFINE | FD-02 | FD-09 | P1/P2 PASS | PASS | 800 |
| 5 | `log_return_15m` | REDEFINE | FD-02 | FD-09 | P1/P2 PASS | PASS | 800 |
| 6 | `horizon_vol_3h` | REDEFINE | FD-02 | FD-09 | P1/P2 PASS | PASS | 800 |
| 7 | `horizon_vol_6h` | REDEFINE | FD-02 | FD-09 | P1/P2 PASS | PASS | 800 |
| 8 | `horizon_vol_12h` | REDEFINE | FD-02 | FD-09 | P1/P2 PASS | PASS | 800 |
| 9 | `body` | ACCEPTABLE AS-IS | FD-02 | FD-09 | P1/P2 PASS | PASS | 800 |
| 10 | `upper_wick` | ACCEPTABLE AS-IS | FD-02 | FD-09 | P1/P2 PASS | PASS | 800 |
| 11 | `lower_wick` | ACCEPTABLE AS-IS | FD-02 | FD-09 | P1/P2 PASS | PASS | 800 |
| 12 | `range` | ACCEPTABLE AS-IS | FD-02 | FD-09 | P1/P2 PASS | PASS | 800 |
| 13 | `direction` | REDEFINE | FD-02 | FD-09 | P1/P2 PASS | PASS | 800 |
| 14 | `atr` | DEFER→DEFINED | FD-02 + FD-03 | FD-09 | P1/P2 PASS | PASS | 800 |
| 15 | `atr_pct` | DEFER→DEFINED | FD-02 + FD-03 | FD-09 | P1/P2 PASS | PASS | 800 |
| 16 | `atr_ecdf_50bar` | REDEFINE | FD-03 §3.1 | FD-09 | P1/P2 PASS | PASS * | 800 |
| 17 | `atr_ma` | DEFER→DEFINED | FD-02 + FD-03 | FD-09 | P1/P2 PASS | PASS | 800 |
| 18 | `atr_above_sma14` | DEFER→DEFINED | FD-02 + FD-03 | FD-09 | P1/P2 PASS | PASS | 800 |
| 19 | `atr_ratio` | DEFER→DEFINED | FD-02 + FD-03 | FD-09 | P1/P2 PASS | PASS | 800 |
| 20 | `rsi` | DEFER→DEFINED | FD-02 + FD-04 | FD-09 | P1/P2 PASS | PASS | 800 |
| 21 | `rsi_slope_45m` | DEFER→DEFINED | FD-02 + FD-04 | FD-09 | P1/P2 PASS | PASS | 800 |
| 22 | `adx` | REDEFINE | FD-02 + FD-06 | FD-09 | P1/P2 PASS | PASS | 800 |
| 23 | `macd` | DEFER→DEFINED | FD-02 + FD-05 | FD-09 | P1/P2 PASS | PASS | 800 |
| 24 | `macd_signal` | DEFER→DEFINED | FD-02 + FD-05 | FD-09 | P1/P2 PASS | PASS | 800 |
| 25 | `macd_hist` | DEFER→DEFINED | FD-02 + FD-05 | FD-09 | P1/P2 PASS | PASS | 800 |
| 26 | `dist_high_6h` | REDEFINE | FD-02 | FD-09 | P1/P2 PASS | PASS | 800 |
| 27 | `dist_low_6h` | REDEFINE | FD-02 | FD-09 | P1/P2 PASS | PASS | 800 |
| 28 | `dist_high_12h` | REDEFINE | FD-02 | FD-09 | P1/P2 PASS | PASS | 800 |
| 29 | `dist_low_12h` | REDEFINE | FD-02 | FD-09 | P1/P2 PASS | PASS | 800 |
| 30 | `dist_high_24h` | REDEFINE | FD-02 | FD-09 | P1/P2 PASS | PASS | 800 |
| 31 | `dist_low_24h` | REDEFINE | FD-02 | FD-09 | P1/P2 PASS | PASS | 800 |
| 32 | `utc_hour` | REDEFINE | FD-02 | FD-09 | P1/P2 PASS | PASS | 800 |
| 33 | `utc_day_of_week` | REDEFINE | FD-02 | FD-09 | P1/P2 PASS | PASS | 800 |

\* `atr_ecdf_50bar`: convergence PASS on the main acceptance pairs; the documented `adx_break` Δ=0.92 exception is an R-class tie-sensitivity behaviour (Doc 02 §3.1), not an open blocker.

## 3. Excluded candidates (2) — closed

| Feature | Final status | Reason | Evidence |
|---|---|---|---|
| `vol_sma_ratio` | EXCLUDE | volume semantics unreliable for the new contract | FD-07 |
| `vol_trend` | EXCLUDE | same | FD-07 |

## 4. Deferred candidates (2) — not eligible, must not enter Phase 3.3

| Feature | Final status | Blocker | Evidence |
|---|---|---|---|
| `is_london` | DEFER | session interval / boundaries not owner-defined | Calendar Contract §7 (status), §9; Revision Plan §5.2 |
| `is_ny` | DEFER | same | same |

> `is_london` / `is_ny` remain out of the Phase 3.3 candidate set until the session definition is owner-approved and the features are re-adjudicated. They do **not** auto-recover on entering Phase 3.3.

## 5. Notes

- All rows draw formula/backend/warm-up decisions from Doc 02 (FD-01..FD-09) and Doc 05 §3; parity from `experiments/phase3_2_feature_convergence/PARITY_P1P2_REPORT.md`; convergence from `experiments/phase3_2_feature_convergence/REPORT.md`.
- `TECHNICALLY ELIGIBLE` = passed technical definition + eligibility; **not** a predictive-value claim.
- The final ordered **model** schema is not complete: it requires both Phase 3.2 technical eligibility **and** Phase 3.3 predictive-value decisions.
