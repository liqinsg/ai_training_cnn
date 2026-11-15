# Phase 3.2 — Document 05: Technically Eligible Candidate Freeze

**Date:** 2026-11-15  
**Status:** TEMPLATE — NOT FROZEN; OWNER APPROVAL AND EVIDENCE REQUIRED  
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

**Status note (2026-11-15):** the L2-A definition decisions (Doc 01 IC-*, Doc 02 FD-*) were recorded on 2026-11-15, which satisfies the definition-level prerequisites 1–5 for the `REDEFINE`/`ACCEPTABLE AS-IS` candidates that are not blocked. **No candidate is frozen**: prerequisites 8 (train/inference parity — P1/P2 not run), 9 (convergence — offline only) and 10 (production history length — RC-02 not approved) remain unmet, and the `atr_ecdf_50bar` tie-sensitivity finding is an open blocker. All `Final status` values below therefore remain `NOT FROZEN` or `DEFER`.

## 3. Candidate freeze register

| Candidate | Proposed name | Matrix disposition | Formula decision | Backend decision | Warm-up decision | Correctness/parity | Convergence | Production-length support | Final status |
|---|---|---|---|---|---|---|---|---|---|
| ret_1h | return_15m | REDEFINE | PENDING | PENDING | PENDING | NOT RUN | N/A / PENDING | NOT ESTABLISHED | NOT FROZEN |
| ret_3h | return_45m | REDEFINE | PENDING | PENDING | PENDING | NOT RUN | N/A / PENDING | NOT ESTABLISHED | NOT FROZEN |
| ret_6h | return_90m | REDEFINE | PENDING | PENDING | PENDING | NOT RUN | N/A / PENDING | NOT ESTABLISHED | NOT FROZEN |
| ret_12h | return_3h | REDEFINE | PENDING | PENDING | PENDING | NOT RUN | N/A / PENDING | NOT ESTABLISHED | NOT FROZEN |
| ret_log | log_return_15m | REDEFINE | PENDING | PENDING | PENDING | NOT RUN | N/A / PENDING | NOT ESTABLISHED | NOT FROZEN |
| vol_12h | horizon_vol_3h | REDEFINE | PENDING | PENDING | PENDING | NOT RUN | NOT ESTABLISHED | NOT ESTABLISHED | NOT FROZEN |
| vol_24h | horizon_vol_6h | REDEFINE | PENDING | PENDING | PENDING | NOT RUN | NOT ESTABLISHED | NOT ESTABLISHED | NOT FROZEN |
| vol_48h | horizon_vol_12h | REDEFINE | PENDING | PENDING | PENDING | NOT RUN | NOT ESTABLISHED | NOT ESTABLISHED | NOT FROZEN |
| body | body | ACCEPTABLE AS-IS | PENDING | PENDING | PENDING | NOT RUN | N/A / PENDING | NOT ESTABLISHED | NOT FROZEN |
| upper_wick | upper_wick | ACCEPTABLE AS-IS | PENDING | PENDING | PENDING | NOT RUN | N/A / PENDING | NOT ESTABLISHED | NOT FROZEN |
| lower_wick | lower_wick | ACCEPTABLE AS-IS | PENDING | PENDING | PENDING | NOT RUN | N/A / PENDING | NOT ESTABLISHED | NOT FROZEN |
| range | range | ACCEPTABLE AS-IS | PENDING | PENDING | PENDING | NOT RUN | N/A / PENDING | NOT ESTABLISHED | NOT FROZEN |
| direction | direction | REDEFINE | PENDING | PENDING | PENDING | NOT RUN | N/A / PENDING | NOT ESTABLISHED | NOT FROZEN |
| atr | atr | DEFER | BLOCKED | BLOCKED | BLOCKED | NOT RUN | NOT ESTABLISHED | NOT ESTABLISHED | DEFER |
| atr_pct | atr_pct | DEFER | BLOCKED | BLOCKED | BLOCKED | NOT RUN | NOT ESTABLISHED | NOT ESTABLISHED | DEFER |
| atr_percentile | atr_ecdf_50bar | REDEFINE | BLOCKED: ATR | BLOCKED: ATR | BLOCKED: ATR | NOT RUN | NOT ESTABLISHED | NOT ESTABLISHED | DEFER |
| atr_ma | atr_ma | DEFER | BLOCKED: ATR | BLOCKED: ATR | BLOCKED: ATR | NOT RUN | NOT ESTABLISHED | NOT ESTABLISHED | DEFER |
| atr_expanding | atr_above_sma14 | DEFER | BLOCKED: ATR | BLOCKED: ATR | BLOCKED: ATR | NOT RUN | NOT ESTABLISHED | NOT ESTABLISHED | DEFER |
| atr_ratio | atr_ratio | DEFER | BLOCKED: ATR | BLOCKED: ATR | BLOCKED: ATR | NOT RUN | NOT ESTABLISHED | NOT ESTABLISHED | DEFER |
| rsi | rsi | DEFER | BLOCKED | BLOCKED | BLOCKED | NOT RUN | NOT ESTABLISHED | NOT ESTABLISHED | DEFER |
| rsi_slope | rsi_slope_45m | DEFER | BLOCKED: RSI | BLOCKED: RSI | BLOCKED: RSI | NOT RUN | NOT ESTABLISHED | NOT ESTABLISHED | DEFER |
| adx | adx | REDEFINE | PENDING | PENDING | PENDING | NOT RUN | NOT ESTABLISHED | NOT ESTABLISHED | NOT FROZEN |
| MACD_12_26_9 | macd | DEFER | BLOCKED | BLOCKED | BLOCKED | NOT RUN | NOT ESTABLISHED | NOT ESTABLISHED | DEFER |
| MACDh_12_26_9 | macd_hist | DEFER | BLOCKED: MACD | BLOCKED: MACD | BLOCKED: MACD | NOT RUN | NOT ESTABLISHED | NOT ESTABLISHED | DEFER |
| MACDs_12_26_9 | macd_signal | DEFER | BLOCKED: MACD | BLOCKED: MACD | BLOCKED: MACD | NOT RUN | NOT ESTABLISHED | NOT ESTABLISHED | DEFER |
| dist_high_24 | dist_high_6h | REDEFINE | PENDING | PENDING | PENDING | NOT RUN | N/A / PENDING | NOT ESTABLISHED | NOT FROZEN |
| dist_low_24 | dist_low_6h | REDEFINE | PENDING | PENDING | PENDING | NOT RUN | N/A / PENDING | NOT ESTABLISHED | NOT FROZEN |
| dist_high_48 | dist_high_12h | REDEFINE | PENDING | PENDING | PENDING | NOT RUN | N/A / PENDING | NOT ESTABLISHED | NOT FROZEN |
| dist_low_48 | dist_low_12h | REDEFINE | PENDING | PENDING | PENDING | NOT RUN | N/A / PENDING | NOT ESTABLISHED | NOT FROZEN |
| dist_high_96 | dist_high_24h | REDEFINE | PENDING | PENDING | PENDING | NOT RUN | N/A / PENDING | NOT ESTABLISHED | NOT FROZEN |
| dist_low_96 | dist_low_24h | REDEFINE | PENDING | PENDING | PENDING | NOT RUN | N/A / PENDING | NOT ESTABLISHED | NOT FROZEN |
| vol_sma_ratio | vol_sma_ratio | DEFER | BLOCKED: volume semantics | BLOCKED | BLOCKED | NOT RUN | NOT ESTABLISHED | NOT ESTABLISHED | DEFER |
| vol_trend | vol_trend | DEFER | BLOCKED: volume semantics | BLOCKED | BLOCKED | NOT RUN | NOT ESTABLISHED | NOT ESTABLISHED | DEFER |
| hour | utc_hour | REDEFINE | PENDING | PENDING | PENDING | NOT RUN | N/A / PENDING | NOT ESTABLISHED | NOT FROZEN |
| day_of_week | utc_day_of_week | REDEFINE | PENDING | PENDING | PENDING | NOT RUN | N/A / PENDING | NOT ESTABLISHED | NOT FROZEN |
| is_london | is_london | DEFER | BLOCKED: session definition | BLOCKED | BLOCKED | NOT RUN | NOT ESTABLISHED | NOT ESTABLISHED | DEFER |
| is_ny | is_ny | DEFER | BLOCKED: session definition | BLOCKED | BLOCKED | NOT RUN | NOT ESTABLISHED | NOT ESTABLISHED | DEFER |

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

| Field | Value |
|---|---|
| Eligible candidate list | NOT FROZEN |
| Ordered model input schema | NOT FROZEN; Phase 3.3 not complete |
| Feature Contract Identity | NOT ISSUED |
| Evidence bundle identity/hash | NOT ISSUED |
| Owner approver | PENDING |
| Approval date | PENDING |

## 6. Phase 3.3 handoff

Only candidates marked `TECHNICALLY ELIGIBLE` may be handed to Phase 3.3 for predictive-value evaluation. Phase 3.3 may select or reject candidates for predictive reasons, but must not silently alter their technical definitions.

The final ordered model schema requires both:
- Phase 3.2 technical eligibility; and
- Phase 3.3 predictive-value decisions.

## 7. Authorization boundary

This freeze template does not authorize production code changes, model training, artifact writes, deployment, READY activation or trading behavior changes. A later implementation task must cite the approved decisions and carry its own scope and acceptance criteria.
