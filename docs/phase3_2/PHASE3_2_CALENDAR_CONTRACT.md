# Phase 3.2 — OANDA Candle Availability Calendar Contract

**Version:** 0.1  
**Date:** 2026-11-15  
**Status:** DRAFT — PENDING L2-A OWNER APPROVAL. **No actual calendar/schedule value is approved by this draft.**  
**Owner:** (unassigned)  
**Scope:** Availability, time labelling and adjacent-candle gap interpretation for the **OANDA-provided candle feed** used by this repository. This is **not** a general FX market trading-hours table and **not** the local London/New York session definition used by `is_london`/`is_ny`.

> Per Revision Plan §5: this contract is the **single calendar source** for IC-05 / IC-07, RC-05 and every experiment that depends on candle gaps. Those documents reference this contract's ID/version only and must not copy a schedule.
>
> The repo-side facts below are recorded as **evidence gathered from the current working tree**; they are not yet approved schedule values. Anything not backed by a traceable source is marked `UNRESOLVED` and must not be treated as a normal gap.

---

## 1. Contract identity

| Field | Value |
|---|---|
| Contract ID | `PHASE3_2_CALENDAR_CONTRACT` |
| Version | 0.1 (DRAFT) |
| Status | PENDING L2-A OWNER APPROVAL |
| Owner | UNASSIGNED |
| Approval date | PENDING |
| Change history | 0.1 (2026-11-15) — initial draft, source-evidence inventory + rule structure |
| Versioning rule | Any change to source identity, coverage, allowed-gap rules or timezone identity bumps the version and requires re-approval of the referencing IC/RC/experiment clauses |

## 2. OANDA source identity

Evidence: `data_pipeline.py::DataFetcher` (current working tree).

| Field | Recorded value | Evidence |
|---|---|---|
| Product / API | OANDA REST v20, Instruments Candles endpoint, via `oandapyV20.endpoints.instruments.InstrumentsCandles` | `data_pipeline.py` L731–738 |
| Environment | `practice` by default; `live` when the live toggle is set | `config.py` L16 (`OANDA_ENV = "practice"`); `fx_trade_bot_v685.py` L1055 |
| Endpoint params used | `{"count": count, "granularity": g}` — **no explicit `price` parameter** | `data_pipeline.py` L736 |
| Price convention implied | code reads `c["mid"]` (o/h/l/c), consistent with the OANDA default `price=M`; **to be confirmed against the OANDA docs** | `data_pipeline.py` L742–752 |
| Granularity | `M15` default (`oanda_granularity: str = "M15"`) | `data_pipeline.py` L709 |
| Instrument range | whatever `instrument` the caller passes; per-instrument coverage not yet enumerated here | `data_pipeline.py` L729, L733 |
| Non-OANDA fallback | `_from_yfinance` exists for the same `fetch()` call — it is **not** the OANDA feed and must not be governed by this calendar | `data_pipeline.py` L774–807 |
| Repo provenance | branch `v2026c`, HEAD `bd7a77527b97adca4e93b80de3ab787f1799d136` | `git rev-parse` (2026-11-15) |

## 3. Source provenance (to be completed before approval)

| Field | Value |
|---|---|
| OANDA official documentation name | UNRESOLVED — only an in-code link is present |
| Documentation version / release date | UNRESOLVED |
| Retrieval date | UNRESOLVED |
| Link present in repo | `https://developer.oanda.com/rest-live-v20/instrument-datatypes/#Granularity` (`data_guard.py` L265) |
| Additional authoritative holiday/closure source | NONE RECORDED — if later added, its priority and version must be listed per item |
| Source hash / snapshot | NOT CAPTURED (no local snapshot of the OANDA docs) |

## 4. Timestamp / completion semantics

Linked to Doc 01 IC-02 / IC-03 / IC-04.

| Field | Recorded value | Evidence / status |
|---|---|---|
| Timestamp field | `c["time"]` parsed with `pd.to_datetime(...)` | `data_pipeline.py` L748 |
| Timestamp timezone | OANDA returns RFC3339 UTC (`...Z`); parsing yields a tz-aware UTC value | `data_pipeline.py` L748 (behaviour to be confirmed against the OANDA docs) |
| Open vs close labelling | **NOT explicitly verified.** The current completion rule is a *time-elapsed* rule that behaves as if `time` is the **candle-open** timestamp | `data_guard.py` L281–310 |
| Completion signal | **Time-elapsed heuristic only.** The code does **not** read the OANDA candle `complete` field | `data_guard.py` L298–310 (`is_latest_candle_closed`), `data_pipeline.py` L741–755 |
| Completion tolerance | `CANDLE_CLOSE_TOLERANCE_SECONDS = 30` | `data_guard.py` L274 |
| Incomplete-candle action | drop the latest row | `data_guard.py` L313–339 (`trim_to_closed_candles`) |

> This is the concrete blocker behind Doc 01 IC-02 and RC-03: the current code **assumes** candle-open timestamps but never verifies it against OANDA's `complete` field or the documented `time` semantics. Approval of this contract must either (a) confirm candle-open from OANDA docs, or (b) switch to the `complete` field, with the conversion layer to UTC recorded explicitly.

## 5. Expected cadence

- Applies only once IC-01/IC-05 are approved as M15.
- Normal contiguous segment: adjacent timestamps are exactly 15 minutes apart.
- `M15` maps to 15 minutes (`data_guard.py` L268 `GRANULARITY_MINUTES`).
- Edge conventions at a contiguous segment boundary (is the last candle before a gap included) are **UNRESOLVED** until §6 is approved.

## 6. OANDA availability schedule (UNRESOLVED)

No repo evidence or cited OANDA source establishes any of the following. They must be filled from a traceable OANDA source before this contract can be approved; until then they are `UNRESOLVED` and gaps matching them are **not** auto-accepted.

| Item | Status |
|---|---|
| Weekly open / close (e.g. Sunday open, Friday close) | UNRESOLVED |
| Weekend gap rule | UNRESOLVED |
| Daily maintenance / pause window(s) | UNRESOLVED |
| Per-instrument or per-feed differences | UNRESOLVED |
| Whether "market open" differs from "OANDA feed provides candles" | UNRESOLVED — the two must be distinguished |

## 7. Holidays / exceptional closures (UNRESOLVED)

- Authoritative source: NONE RECORDED.
- Coverage, update frequency and expiry handling: UNRESOLVED.
- Feed outages / temporary suspensions: UNRESOLVED.
- Any item that cannot be established from an authoritative source must stay `UNRESOLVED`; no guessed time may be entered.

## 8. DST

- Session features use IANA zones (`Europe/London`, `America/New_York`); the availability calendar must not mix session hours into OANDA feed availability (Revision Plan §5.2).
- tz database source: `pytz` (via pandas) is used implicitly; explicit source/version is **UNRESOLVED** (Doc 04 RC-11).
- Conversion boundaries must be verified with UTC instants; DST rules: **UNRESOLVED**.
- Required behaviour: **FAIL CLOSED** when the tz identity is unavailable or ambiguous (Revision Plan §11-4).

## 9. Gap classifier

- Only gaps matching an **approved** §6/§7 rule are `EXPLAINED`.
- Every other gap is `UNEXPLAINED` and rejects the whole batch (Doc 01 IC-06 / IC-07).
- No default-to-normal: an unresolved rule never makes a gap acceptable.

## 10. Failure / update policy

- No source, stale source, conflicting sources or an unexplained gap ⇒ **fail closed**.
- This contract is re-reviewed and re-versioned whenever any source/version/coverage or schedule rule changes; referencing IC/RC/experiment clauses must be re-approved.

## 11. Acceptance fixtures (design only — no values approved)

| Fixture | Expected result |
|---|---|
| Adjacent M15 candles (15 min apart) | accepted (contiguous segment) |
| Weekend boundary gap (once §6 approved) | accepted only if it exactly matches the approved rule |
| Daily maintenance/pause gap (once §6 approved) | accepted only if it exactly matches the approved rule |
| Holiday closure (once §7 approved) | accepted only if it exactly matches the approved rule |
| Anomalous gap not in any approved rule | whole batch rejected (`UNEXPLAINED`) |
| Source stale / unavailable | fail closed |
| Conflicting sources | fail closed |

## 12. Authorization boundary

This DRAFT does not approve any calendar value, does not modify production code, and does not authorize training, artifact writes, deployment, READY activation or trading behaviour changes. Approving the actual OANDA schedule is an L2-A decision.
