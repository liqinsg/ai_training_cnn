# Phase 3.2 — Document 04: Runtime Configuration Decisions

**Date:** 2026-11-15  
**Status:** L2-A + L2-B APPROVED (owner, 2026-11-15) — RC-01, RC-03..RC-11 recorded; RC-02 APPROVED under L2-B (production history length = 800; evidence = Step 4 convergence report)  
**Scope:** Runtime settings that must be decided separately from feature formulas and experiments.

## 1. Purpose

Separate runtime operating choices from technical feature definitions. These settings must not be inferred from trainer defaults, historical artifacts, or the experiment sequence.

## 2. Decision register

| ID | Runtime decision | Current status | Required evidence/decision |
|---|---|---|---|
| RC-01 | Production timeframe | APPROVED — M15 | Explicit owner choice; M15 remains a candidate |
| RC-02 | Production history length | APPROVED (L2-B) — 800 bars | Explicit bar count and warm-up sufficiency evidence (Step 4 report); 800 is the longest tested length and passes main acceptance at that length |
| RC-03 | Timestamp convention | APPROVED — candle-OPEN (start) timestamp; same as Doc 01 IC-02 | Evidenced from OANDA REST-V20 Instrument Definitions (`time` = "The start time of the candlestick") |
| RC-04 | Incomplete-candle handling | APPROVED — same shared exclusion rule as Doc 01 IC-04 | Exact shared exclusion rule |
| RC-05 | Calendar/session gap policy | APPROVED — references the Calendar Contract (`PHASE3_2_CALENDAR_CONTRACT.md`) | Pinned calendar and permitted exceptions |
| RC-06 | Volume source | APPROVED — NOT APPLICABLE (FD-07 = EXCLUDE for the new contract) | Tick volume vs exchange-traded volume, per instrument/feed |
| RC-07 | Volume comparability | APPROVED — NOT APPLICABLE (FD-07 = EXCLUDE for the new contract) | Whether values are comparable across supported instruments |
| RC-08 | Volume invalidity | APPROVED — NOT APPLICABLE (FD-07 = EXCLUDE for the new contract) | Missing, zero, negative and unavailable handling |
| RC-09 | London session | APPROVED — IANA `Europe/London`; boundaries/DST per FD-08; FAIL CLOSED | Local start/end, endpoint inclusivity, weekends/holidays |
| RC-10 | New York session | APPROVED — IANA `America/New_York`; boundaries/DST per FD-08; FAIL CLOSED | Local start/end, endpoint inclusivity, weekends/holidays |
| RC-11 | IANA timezone data | APPROVED — pin tz database source + version, DST rules, FAIL CLOSED; `tzdata==2026.5`, `pytz==2026.1` | Pinned timezone database identity/version |

## 3. Production history length rules

- `200 → 300 → 500 → 800` is an experiment sequence only.
- It is not a production history setting.
- Production history length must be approved separately.
- A production length outside the tested sequence requires a preregistered same-final-candle comparison against the 800-bar baseline, but only for features that passed convergence through 800.
- A feature that failed convergence through 800 remains `NOT ESTABLISHED`; do not claim production warm-up sufficiency.

**Approved value (RC-02, L2-B, 2026-11-15): 800 bars.** Rationale, grounded in the Step 4 report (`experiments/phase3_2_feature_convergence/REPORT.md`):

- 800 is the longest tested length; at 800 the main acceptance pairs `300v500` and `500v800` pass for every candidate on every fixture.
- The only observed length-sensitivity is on the degenerate `adx_break` fixture, where `atr_ecdf_50bar` shifts by 0.92 between length 200 and 300 and is then stable (0.02) for 300/500/800. Choosing 800 therefore sits well inside the stable region rather than at the 200-bar boundary.
- The recursive R-class features (ATR/RSI/ADX/MACD family) reach their settled tail-off within the tested horizon at 800; 800 gives the largest margin against the initialization tail at the final candle.
- This is a runtime length, not a formula parameter; it does not change any frozen feature definition.

## 4. Volume policy

Until source semantics are established:
- `vol_sma_ratio` remains DEFER.
- `vol_trend` remains DEFER.
- Do not switch between real/tick volume and synthetic proxies.
- Do not infer missing volume as zero.
- Do not use whole-input-dependent source selection.
- Record feed and instrument coverage before deciding cross-instrument comparability.

## 5. Session policy

Before session features become eligible, specify:
- Local start and end times.
- Whether start/end are inclusive or exclusive.
- Weekends and holidays.
- Whether the feature means local clock window or actual market-open session.
- IANA zone (`Europe/London` / `America/New_York`) and pinned tz database identity (`tzdata==2026.5`, `pytz==2026.1`; FAIL CLOSED when unavailable).
- DST behavior, tested using UTC instants converted into the local zone.

## 6. Runtime authority and configuration discipline

- Runtime configuration is the authority for runtime settings.
- Model/artifact metadata is read-only compatibility evidence; it must not silently override runtime settings.
- Training and inference must consume the same approved semantic configuration.
- Any change to timeframe, history length, source, timezone, session or missing-value policy is a semantic change requiring a new contract identity once one exists.

## 7. Owner approval register

| ID | Owner-approved value | Approver | Date |
|---|---|---|---|
| RC-01 | M15 | owner | 2026-11-15 |
| RC-02 | 800 bars (production history length) | owner (L2-B) | 2026-11-15 |
| RC-03 | candle-OPEN (start) timestamp — same as Doc 01 IC-02 | owner | 2026-11-15 |
| RC-04 | Same shared exclusion rule as Doc 01 IC-04 | owner | 2026-11-15 |
| RC-05 | Reference the Calendar Contract (`PHASE3_2_CALENDAR_CONTRACT.md`) | owner | 2026-11-15 |
| RC-06 | NOT APPLICABLE (FD-07 = EXCLUDE) | owner | 2026-11-15 |
| RC-07 | NOT APPLICABLE (FD-07 = EXCLUDE) | owner | 2026-11-15 |
| RC-08 | NOT APPLICABLE (FD-07 = EXCLUDE) | owner | 2026-11-15 |
| RC-09 | IANA `Europe/London`; FAIL CLOSED | owner | 2026-11-15 |
| RC-10 | IANA `America/New_York`; FAIL CLOSED | owner | 2026-11-15 |
| RC-11 | Pin `tzdata==2026.5` + `pytz==2026.1` (env `ai-sprint` `share/zoneinfo`); FAIL CLOSED | owner | 2026-11-15 |

## 8. Authorization boundary

This document does not authorize changes to runtime configuration, production code, model artifacts, deployment or trading behavior. Each runtime change requires explicit owner approval and an implementation task with acceptance criteria.
