# Phase 3.2 — Document 01: Input Contract Owner Decision

**Date:** 2026-11-15  
**Status:** DRAFT — OWNER DECISION REQUIRED  
**Scope:** Input data, timeframe, timestamps, candle completeness, validation and batch failure policy.

## 1. Purpose

Freeze the common input boundary used by both training and inference before feature calculations are implemented. This document is a decision record proposal, not implementation authorization.

## 2. Decisions required

| ID | Decision | Current proposal | Owner decision |
|---|---|---|---|
| IC-01 | Target timeframe | M15 | PENDING |
| IC-02 | Timestamp convention | One explicit convention: candle-open timestamp or candle-close timestamp | PENDING |
| IC-03 | Timestamp timezone | Timezone-aware UTC before validation/features | PENDING |
| IC-04 | Incomplete candle | Exclude the latest incomplete candle using one shared rule | PENDING |
| IC-05 | Candle cadence | Expected 15-minute intervals, subject to an approved market/session calendar | PENDING |
| IC-06 | Invalid batch policy | Reject the entire input batch; no row deletion, imputation, substitution or partial feature output | PENDING |
| IC-07 | Session gaps | Accept only gaps explicitly explained by an approved calendar; otherwise reject | PENDING |
| IC-08 | Training/inference parity | Identical validation and failure semantics | PENDING |

## 3. Proposed v1 input contract

1. Input represents one instrument and one declared timeframe per batch.
2. Candle timestamps must be timezone-aware and normalized to UTC before feature calculation.
3. Timestamps must be strictly increasing and unique.
4. Every adjacent timestamp must match the expected cadence or an explicitly approved calendar exception.
5. Every candle must contain finite OHLC values.
6. OHLC constraints:
   - `Open > 0` and `Close > 0` wherever used as denominator or logarithm input.
   - `High >= max(Open, Close)`.
   - `Low <= min(Open, Close)`.
   - `High >= Low`.
7. Any duplicate, unordered timestamp, unexplained gap, or invalid OHLC rejects the entire batch.
8. Invalid rows must not be silently removed, repaired, imputed, or replaced with older candles.
9. Training and inference must use the same validation implementation and validity definition.
10. No feature calculation may begin until the batch passes validation.

## 4. Important distinctions

- M15 is a proposed evaluation baseline, not historical artifact provenance.
- Timestamp convention (open-time versus close-time) is not implied by the label M15.
- The incomplete-candle exclusion rule must be explicit and identical in training and inference.
- The calendar policy is not approved merely because a gap appears to coincide with a weekend or session closure.

## 5. Acceptance criteria

- Valid M15 fixtures pass.
- Duplicate timestamps fail the whole batch.
- Unordered timestamps fail the whole batch.
- Invalid OHLC fails the whole batch.
- Unexplained missing intervals fail the whole batch.
- An explained calendar gap passes only when the exact calendar rule is approved and pinned.
- Training and inference return equivalent validation outcomes for every fixture.
- No partial feature output is emitted for a rejected batch.

## 6. Owner approval record

| Decision | Owner choice / value | Approved by | Date |
|---|---|---|---|
| IC-01 Target timeframe |  |  |  |
| IC-02 Timestamp convention |  |  |  |
| IC-03 UTC normalization |  |  |  |
| IC-04 Incomplete-candle rule |  |  |  |
| IC-05 Cadence/calendar |  |  |  |
| IC-06 Whole-batch rejection |  |  |  |
| IC-07 Explained gaps |  |  |  |
| IC-08 Train/inference parity |  |  |  |

## 7. Authorization boundary

Approval of this document freezes the proposed input semantics only. It does **not** authorize production code changes, model training, artifact writes, deployment, READY wiring, or trading behavior changes. Those require separate explicit authorization.
