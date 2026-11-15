# Phase 3.2 — Document 04: Runtime Configuration Decisions

**Date:** 2026-11-15  
**Status:** L2 APPROVED (owner, 2026-11-15) — RC-01, RC-03..RC-11 recorded; RC-02 remains NOT YET APPROVED (pending Step 4 evidence / L2-B)  
**Scope:** Runtime settings that must be decided separately from feature formulas and experiments.

## 1. Purpose

Separate runtime operating choices from technical feature definitions. These settings must not be inferred from trainer defaults, historical artifacts, or the experiment sequence.

## 2. Decision register

| ID | Runtime decision | Current status | Required evidence/decision |
|---|---|---|---|
| RC-01 | Production timeframe | APPROVED — M15 | Explicit owner choice; M15 remains a candidate |
| RC-02 | Production history length | NOT YET APPROVED | Explicit bar count and warm-up sufficiency evidence (Step 4 report) — L2-B |
| RC-03 | Timestamp convention | APPROVED (direction) — same as Doc 01 IC-02; concrete value pending source evidence | Candle-open or candle-close timestamp |
| RC-04 | Incomplete-candle handling | APPROVED — same shared exclusion rule as Doc 01 IC-04 | Exact shared exclusion rule |
| RC-05 | Calendar/session gap policy | APPROVED — references the Calendar Contract (`PHASE3_2_CALENDAR_CONTRACT.md`) | Pinned calendar and permitted exceptions |
| RC-06 | Volume source | APPROVED — NOT APPLICABLE (FD-07 = EXCLUDE for the new contract) | Tick volume vs exchange-traded volume, per instrument/feed |
| RC-07 | Volume comparability | APPROVED — NOT APPLICABLE (FD-07 = EXCLUDE for the new contract) | Whether values are comparable across supported instruments |
| RC-08 | Volume invalidity | APPROVED — NOT APPLICABLE (FD-07 = EXCLUDE for the new contract) | Missing, zero, negative and unavailable handling |
| RC-09 | London session | APPROVED — IANA `Europe/London`; boundaries/DST per FD-08; FAIL CLOSED | Local start/end, endpoint inclusivity, weekends/holidays |
| RC-10 | New York session | APPROVED — IANA `America/New_York`; boundaries/DST per FD-08; FAIL CLOSED | Local start/end, endpoint inclusivity, weekends/holidays |
| RC-11 | IANA timezone data | APPROVED (requirement) — pin tz database source + version, DST rules, FAIL CLOSED; concrete version pin pending | Pinned timezone database identity/version |

## 3. Production history length rules

- `200 → 300 → 500 → 800` is an experiment sequence only.
- It is not a production history setting.
- Production history length must be approved separately.
- A production length outside the tested sequence requires a preregistered same-final-candle comparison against the 800-bar baseline, but only for features that passed convergence through 800.
- A feature that failed convergence through 800 remains `NOT ESTABLISHED`; do not claim production warm-up sufficiency.

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
- IANA zone (`Europe/London` / `America/New_York`) and pinned tz database identity.
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
| RC-02 | NOT YET APPROVED (pending Step 4 evidence; L2-B) | — | — |
| RC-03 | Same as Doc 01 IC-02; concrete value pending source evidence | owner | 2026-11-15 |
| RC-04 | Same shared exclusion rule as Doc 01 IC-04 | owner | 2026-11-15 |
| RC-05 | Reference the Calendar Contract (`PHASE3_2_CALENDAR_CONTRACT.md`) | owner | 2026-11-15 |
| RC-06 | NOT APPLICABLE (FD-07 = EXCLUDE) | owner | 2026-11-15 |
| RC-07 | NOT APPLICABLE (FD-07 = EXCLUDE) | owner | 2026-11-15 |
| RC-08 | NOT APPLICABLE (FD-07 = EXCLUDE) | owner | 2026-11-15 |
| RC-09 | IANA `Europe/London`; FAIL CLOSED | owner | 2026-11-15 |
| RC-10 | IANA `America/New_York`; FAIL CLOSED | owner | 2026-11-15 |
| RC-11 | Pin tz database source + version, DST rules, FAIL CLOSED; concrete version pin pending | owner | 2026-11-15 |

## 8. Authorization boundary

This document does not authorize changes to runtime configuration, production code, model artifacts, deployment or trading behavior. Each runtime change requires explicit owner approval and an implementation task with acceptance criteria.
