# Phase 3.2 — Document 01: Input Contract Owner Decision

**Date:** 2026-11-15  
**Status:** L1 + L2-A APPROVED (owner, 2026-11-15) — IC decisions recorded below; IC-02/IC-04 source-evidence gap CLOSED (2026-11-15, see §6 addendum)  
**Scope:** Input data, timeframe, timestamps, candle completeness, validation and batch failure policy.

## 1. Purpose

Freeze the common input boundary used by both training and inference before feature calculations are implemented. This document is a decision record proposal, not implementation authorization.

## 2. Decisions required

| ID | Decision | Current proposal | Owner decision |
|---|---|---|---|
| IC-01 | Target timeframe | M15 | APPROVED — M15 |
| IC-02 | Timestamp convention | One explicit convention: candle-open timestamp or candle-close timestamp | APPROVED — **candle-OPEN (start) timestamp**; evidenced from OANDA REST-V20 Instrument Definitions (`time` = "The start time of the candlestick"); not inferred from the field name (see `PHASE3_2_CALENDAR_CONTRACT.md` §4) |
| IC-03 | Timestamp timezone | Timezone-aware UTC before validation/features | APPROVED — timezone-aware UTC before validation/features |
| IC-04 | Incomplete candle | Exclude the latest incomplete candle using one shared rule | APPROVED — exclude the latest incomplete candle with one shared rule; the authoritative signal is the OANDA `complete` field (`complete == True` ⇔ candle ending time is not in the future). Deviation logged: current code uses a time-elapsed heuristic instead of `complete` (see §6 addendum) |
| IC-05 | Candle cadence | Expected 15-minute intervals, subject to an approved market/session calendar | APPROVED — 15-minute intervals governed by the Calendar Contract |
| IC-06 | Invalid batch policy | Reject the entire input batch; no row deletion, imputation, substitution or partial feature output | APPROVED — reject the entire batch; no deletion / imputation / substitution / partial output |
| IC-07 | Session gaps | Accept only gaps explicitly explained by an approved calendar; otherwise reject | APPROVED — accept only gaps explained by the approved Calendar Contract; otherwise reject |
| IC-08 | Training/inference parity | Identical validation and failure semantics | APPROVED — identical validation and failure semantics (layered per Revision Plan §8) |

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
| IC-01 Target timeframe | M15 | owner | 2026-11-15 |
| IC-02 Timestamp convention | candle-OPEN (start) timestamp — evidenced from OANDA REST-V20 Instrument Definitions (`time` = "The start time of the candlestick") | owner | 2026-11-15 |
| IC-03 UTC normalization | Timezone-aware UTC before validation/features | owner | 2026-11-15 |
| IC-04 Incomplete-candle rule | Exclude the latest incomplete candle, one shared rule across training and inference; authoritative signal = OANDA `complete` field | owner | 2026-11-15 |
| IC-05 Cadence/calendar | 15-minute cadence; governed by the Calendar Contract | owner | 2026-11-15 |
| IC-06 Whole-batch rejection | Reject entire batch; no deletion / imputation / substitution / partial output | owner | 2026-11-15 |
| IC-07 Explained gaps | Accept only Calendar-Contract-explained gaps; otherwise reject | owner | 2026-11-15 |
| IC-08 Train/inference parity | Identical validation and failure semantics | owner | 2026-11-15 |

**Open dependency (IC-02 / IC-04): CLOSED 2026-11-15.** The concrete convention is fixed to **candle-open (start) timestamp**, evidenced from OANDA REST-V20 Instrument Definitions (`time` = "The start time of the candlestick"; `complete` = a flag that is true iff the candle's ending time is not in the future). The full source quote, provenance and the completion-signal definition are recorded in `PHASE3_2_CALENDAR_CONTRACT.md` §4. Remaining recorded deviation: current runtime code identifies the incomplete candle via a time-elapsed heuristic rather than the `complete` field; this is a logged deviation (not a re-opening of IC-04), and the contract requires the `complete` signal where the feed provides it.

## 7. Authorization boundary

Approval of this document freezes the proposed input semantics only. It does **not** authorize production code changes, model training, artifact writes, deployment, READY wiring, or trading behavior changes. Those require separate explicit authorization.
