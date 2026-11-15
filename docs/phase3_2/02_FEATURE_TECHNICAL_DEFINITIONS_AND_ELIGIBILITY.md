# Phase 3.2 — Document 02: Feature Technical Definitions and Eligibility

**Date:** 2026-11-15  
**Status:** L1 + L2-A APPROVED (owner, 2026-11-15) — FD-01..09 recorded below  
**Scope:** Technical definitions for the 37 source-derived feature candidates. Predictive value is out of scope.

## 1. Purpose and boundary

This document consolidates the candidate dispositions from `PHASE3_2_TECHNICAL_FEATURE_DECISION_MATRIX_v0.1.md`. It does not create a final ordered model schema and does not issue a Feature Contract Identity.

A feature is technically eligible only if its formula, inputs, timeframe mapping, implementation/backend, warm-up, invalidity behavior, determinism, no-future-data property, and training/inference parity are all specified.

## 2. Candidate disposition inventory

The current matrix classifies 37 candidates as:
- 4 `ACCEPTABLE AS-IS`
- 19 `REDEFINE`
- 14 `DEFER`
- 0 `EXCLUDE`

These dispositions were proposed by the matrix; under FD-02 (below) they are now the approved *definition* baseline, but they are still not final eligibility findings.

**FD-02 (approved, 2026-11-15):** the matrix `PHASE3_2_TECHNICAL_FEATURE_DECISION_MATRIX_v0.1.md` is adopted as the approval baseline for the ACCEPTABLE/REDEFINE formulas and names, pinned at SHA-256 `808bdcbdbb7b95a9322183686c9440746df0fc703184475369eb9990044c0453`. It fixes the *technical definition baseline* only; candidate eligibility/freeze remains a Doc 05 (Step 6) outcome.

| # | Source candidate | Proposed disposition | Proposed definition / blocker |
|---:|---|---|---|
| 1 | `ret_1h` | REDEFINE | `return_15m = Close[t]/Close[t-1]-1`; exact prior M15 timestamp only |
| 2 | `ret_3h` | REDEFINE | `return_45m = Close[t]/Close[t-3]-1`; exact 45-minute lag |
| 3 | `ret_6h` | REDEFINE | `return_90m = Close[t]/Close[t-6]-1`; exact 90-minute lag |
| 4 | `ret_12h` | REDEFINE | `return_3h = Close[t]/Close[t-12]-1`; exact 3-hour lag |
| 5 | `ret_log` | REDEFINE | `log_return_15m = ln(Close[t]/Close[t-1])`; positive finite closes |
| 6 | `vol_12h` | REDEFINE | `horizon_vol_3h = sqrt(12) * sample_std(last 12 one-bar returns, ddof=1)` |
| 7 | `vol_24h` | REDEFINE | `horizon_vol_6h = sqrt(24) * sample_std(last 24 one-bar returns, ddof=1)` |
| 8 | `vol_48h` | REDEFINE | `horizon_vol_12h = sqrt(48) * sample_std(last 48 one-bar returns, ddof=1)` |
| 9 | `body` | ACCEPTABLE AS-IS | `abs(Close-Open)/Open`; finite valid OHLC; Open > 0 |
| 10 | `upper_wick` | ACCEPTABLE AS-IS | `(High-max(Open,Close))/Open`; finite valid OHLC; Open > 0 |
| 11 | `lower_wick` | ACCEPTABLE AS-IS | `(min(Open,Close)-Low)/Open`; finite valid OHLC; Open > 0 |
| 12 | `range` | ACCEPTABLE AS-IS | `(High-Low)/Open`; finite valid OHLC; Open > 0 |
| 13 | `direction` | REDEFINE | 1 if Close>Open, 0 if equal, -1 if Close<Open |
| 14 | `atr` | DEFER | Canonical formula, seed, smoothing, period, backend/version and warm-up unresolved |
| 15 | `atr_pct` | DEFER | `ATR/Close`; depends on canonical ATR; positive finite Close |
| 16 | `atr_percentile` | REDEFINE | `atr_ecdf_50bar`: count of ATR values <= current over trailing 50 valid ATR values, divided by 50; depends on canonical ATR |
| 17 | `atr_ma` | DEFER | Candidate trailing SMA of 14 ATR values including current; ATR unresolved |
| 18 | `atr_expanding` | DEFER | Proposed rename `atr_above_sma14`; strict ATR>SMA14; ATR unresolved |
| 19 | `atr_ratio` | DEFER | Candidate ATR/current divided by mean of 28 ATR values; no fill-to-1; ATR unresolved |
| 20 | `rsi` | DEFER | Canonical calculation, seed, smoothing, zero-gain/loss behavior, backend/version and warm-up unresolved |
| 21 | `rsi_slope` | DEFER | Candidate `RSI[t]-RSI[t-3]`; depends on canonical RSI; name must express 45-minute lag under M15 |
| 22 | `adx` | REDEFINE | Replace local rolling-mean ADX and NaN-to-zero with Wilder definition in §3 |
| 23 | `MACD_12_26_9` | DEFER | Explicit periods, EMA seed/recurrence, input, backend and warm-up unresolved |
| 24 | `MACDh_12_26_9` | DEFER | Same MACD decision; all outputs required together |
| 25 | `MACDs_12_26_9` | DEFER | Same MACD decision; no partial output set |
| 26 | `dist_high_24` | REDEFINE | `dist_high_6h=(Close-max(High[t-23:t]))/Close`; full 24 bars |
| 27 | `dist_low_24` | REDEFINE | `dist_low_6h=(Close-min(Low[t-23:t]))/Close`; full 24 bars |
| 28 | `dist_high_48` | REDEFINE | `dist_high_12h=(Close-max(High[t-47:t]))/Close`; full 48 bars |
| 29 | `dist_low_48` | REDEFINE | `dist_low_12h=(Close-min(Low[t-47:t]))/Close`; full 48 bars |
| 30 | `dist_high_96` | REDEFINE | `dist_high_24h=(Close-max(High[t-95:t]))/Close`; full 96 bars |
| 31 | `dist_low_96` | REDEFINE | `dist_low_24h=(Close-min(Low[t-95:t]))/Close`; full 96 bars |
| 32 | `vol_sma_ratio` | DEFER | Volume meaning/source, availability, comparability and invalid-value policy unresolved |
| 33 | `vol_trend` | DEFER | Same volume-source blockers; if retained use explicit three-state or other approved semantics |
| 34 | `hour` | REDEFINE | Rename `utc_hour`; derive from validated UTC timestamp, integer 0–23 |
| 35 | `day_of_week` | REDEFINE | Rename `utc_day_of_week`; UTC weekday, Monday=0 through Sunday=6 |
| 36 | `is_london` | DEFER | Define local interval/boundaries/calendar; use `Europe/London` IANA timezone |
| 37 | `is_ny` | DEFER | Define local interval/boundaries/calendar; use `America/New_York` IANA timezone |

## 3. ADX definition — APPROVED (FD-06)

Period `n=14` bars: **APPROVED (FD-06, 2026-11-15)**. The definition below is the approved ADX definition.

1. For `t>0`: `up=High[t]-High[t-1]`; `down=Low[t-1]-Low[t]`.
2. `+DM[t]=up` iff `up>down` and `up>0`, else zero. `-DM[t]=down` iff `down>up` and `down>0`, else zero. Ties set both to zero.
3. `TR[t]=max(High[t]-Low[t], abs(High[t]-Close[t-1]), abs(Low[t]-Close[t-1]))`. Candle zero has no prior-close transition.
4. At `t=n`, seed smoothed sums from transitions `1..n`. For later rows: `S[t]=S[t-1]-S[t-1]/n+x[t]`.
5. `+DI=100*S+DM/STR`; `-DI=100*S-DM/STR`. If `STR=0`, DI/DX unavailable.
6. Let `D=+DI+(-DI)`. If `D=0`, DX unavailable; otherwise `DX=100*abs(+DI-(-DI))/D`.
7. First ADX seed at `t=2n-1`: arithmetic mean of `DX[n..2n-1]`. Thereafter use Wilder recurrence while DX remains valid and contiguous.
8. If input candle validation fails, reject the whole batch.
9. If candles are valid but a DI/DX denominator is zero, DX and ADX are unavailable at that point and the ADX smoothing chain breaks. Retain Wilder TR/+DM/-DM states. Starting at the next valid DX, collect `n` consecutive valid DX values, seed from their arithmetic mean, then resume recurrence. Never carry pre-break ADX across the break.
10. For `n=14`, if DX breaks at index 40 and valid DX resumes at index 41, the next seed is at index 54 using `DX[41..54]`.

This is a proposed definition, not a claim of equivalence to any third-party library.

## 3.1 `atr_ecdf_50bar` tie-handling — approved addendum (2026-11-15)

Definition frozen as: `atr_ecdf_50bar[t] = (count of ATR values in the trailing 50 valid ATR values that are <= ATR[t]) / 50` (inclusive rank / ECDF at the sample point). It is deterministic for a fixed input history.

This inclusive-rank form is tie-sensitive by construction: on a (near-)degenerate window where many ATR values are exactly equal, a minute shift of the reference ATR can step the count across many equal samples at once. This was observed exactly once, on the synthetic degenerate `adx_break` fixture (Step 4 report, fixture `adx_break`): the final-candle `|A-B|` for `atr_ecdf_50bar` is **0.92** between history 200 and 300, then stable (0.02) for 300/500/800. Both main acceptance pairs (300v500, 500v800) pass on all fixtures.

Owner decision: keep the inclusive-rank definition (it is the frozen, reproducible semantic) and treat tie-sensitivity as an inherent R-class behaviour, not a defect. The approved production history length (RC-02 = 800, Doc 04) sits in the stable region, so the frozen production configuration is unaffected. No formula change → the preregistered convergence protocol is not re-opened. Any future tie-robust variant (e.g. mid-rank `(count(<) + 0.5*count(==))/w`) would be a **new contract identity**, not a silent change.

## 4. Shared eligibility gate

All nine conditions are mandatory:
1. Complete unambiguous formula.
2. Explicit input columns and data meaning.
3. Explicit timeframe and row-to-time mapping.
4. Fixed canonical backend/implementation and version where applicable.
5. Explicit warm-up and first-valid-row behavior.
6. Explicit missing, invalid and non-finite behavior.
7. No future data.
8. Repeatable output for identical declared input.
9. Identical training/inference calculation and validity semantics.

Failure of any condition means `DEFER`.

## 5. Cross-feature rules

- No unapproved backend fallback.
- No `bfill`, blanket `fillna(0)`, or plausible numeric sentinel for unavailable values.
- No silent partial MACD outputs.
- Any change to formula, name, window, seed, input source, scale, timezone or missing behavior changes contract semantics.
- Candle validation precedes all feature calculation.
- Training and inference share the same validity rules.
- Technical eligibility does not establish predictive value or final schema inclusion.

## 6. Owner decision register

| Decision ID | Required decision | Status |
|---|---|---|
| FD-01 | Approve target timeframe and timestamp/input semantics | APPROVED — M15; input/timestamp semantics per Doc 01 IC-01..08 (IC-02 value pending source evidence) |
| FD-02 | Approve proposed formulas/names for ACCEPTABLE/REDEFINE candidates | APPROVED — matrix `PHASE3_2_TECHNICAL_FEATURE_DECISION_MATRIX_v0.1.md` as baseline; SHA-256 `808bdcbdbb7b95a9322183686c9440746df0fc703184475369eb9990044c0453` |
| FD-03 | Choose canonical ATR definition/backend/period | APPROVED — Revision Plan §6 FD-03: Wilder RMA (alpha = 1/n), n = 14; one canonical implementation, no silent fallback; derived `atr_ma`/`atr_pct`/`atr_ecdf_50bar`/`atr_ratio` windows as in §6 |
| FD-04 | Choose canonical RSI definition/backend/period | APPROVED — Revision Plan §6 FD-04: Wilder RMA (alpha = 1/n), n = 14; `avg_loss == 0 → 100`; fully flat → `50`; `rsi_slope_45m = RSI[t]-RSI[t-3]` |
| FD-05 | Choose canonical MACD definition/backend/periods | APPROVED — Revision Plan §6 FD-05: EMA alpha = 2/(n+1), `adjust=False`, first-value seed; periods 12 / 26 / 9; `macd`/`macd_signal`/`macd_hist` produced together in one shared valid range |
| FD-06 | Approve ADX Wilder definition and period 14 | APPROVED — §3 above; n = 14; full break/reseed rules; first seed at index 2n-1 |
| FD-07 | Resolve volume source semantics and invalid-value policy | APPROVED — `vol_sma_ratio` and `vol_trend` = `EXCLUDE` for the new contract (Revision Plan §10.1); does not alter any other feature |
| FD-08 | Resolve London/New York sessions and calendar rules | APPROVED — sessions keep IANA zones (`Europe/London`, `America/New_York`); candle-availability calendar governed by the Calendar Contract |
| FD-09 | Approve feature-specific warm-up and invalidity behavior | APPROVED — Revision Plan §6: warm-up rows stay `NaN` (never filled); per-feature first-valid rows as defined there |

## 7. Authorization boundary

Owner approval of technical definitions does not itself authorize implementation, training, artifact writes, deployment or trading behavior changes. The final ordered schema is not frozen here. Phase 3.3 evaluates predictive value after technical eligibility and required experiments are established.
