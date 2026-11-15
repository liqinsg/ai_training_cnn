# Phase 3.2 — OANDA Candle Availability Calendar Contract

**Version:** 0.2
**Date:** 2026-11-15
**Status:** v0.2 — **owner-approved (2026-11-15) for the clauses evidenced from OANDA official sources** (§4 timestamp convention; §6 weekly open/close). Clauses marked `UNRESOLVED` (§6 daily maintenance, §6 per-instrument, §7 holidays) are **NOT approved** and **fail closed**.
**Owner:** owner (decision recorded 2026-11-15)
**Scope:** Availability, time labelling and adjacent-candle gap interpretation for the **OANDA-provided candle feed** used by this repository. This is **not** a general FX market trading-hours table and **not** the local London/New York session definition used by `is_london`/`is_ny`.

> Per Revision Plan §5: this contract is the **single calendar source** for IC-05 / IC-07, RC-05 and every experiment that depends on candle gaps. Those documents reference this contract's ID/version only and must not copy a schedule.
>
> v0.2 change (append-only history is preserved in §1): OANDA official documentation was retrieved on 2026-11-15 and the previously-open `UNRESOLVED` items for **timestamp convention** and **weekly open/close** are now `EVIDENCED`. Anything still not backed by a traceable source remains `UNRESOLVED` and must not be treated as a normal gap.

---

## 1. Contract identity

| Field | Value |
|---|---|
| Contract ID | `PHASE3_2_CALENDAR_CONTRACT` |
| Version | 0.2 |
| Status | v0.2 — evidenced clauses owner-approved; `UNRESOLVED` clauses not approved and fail closed |
| Owner | owner (2026-11-15) |
| Approval date | 2026-11-15 |
| Change history | 0.1 (2026-11-15) — initial draft, source-evidence inventory + rule structure. 0.2 (2026-11-15) — OANDA official sources retrieved: **§4 `time` = candle-open / `complete` flag**, **§6 weekly open/close**, REST candle defaults (dailyAlignment/alignmentTimezone/weeklyAlignment), §8 tz pin |
| Versioning rule | Any change to source identity, coverage, allowed-gap rules or timezone identity bumps the version and requires re-approval of the referencing IC/RC/experiment clauses |

## 2. OANDA source identity

Evidence: `data_pipeline.py::DataFetcher` (current working tree).

| Field | Recorded value | Evidence |
|---|---|---|
| Product / API | OANDA REST v20, Instruments Candles endpoint, via `oandapyV20.endpoints.instruments.InstrumentsCandles` | `data_pipeline.py` L731–738 |
| Environment | `practice` by default; `live` when the live toggle is set | `config.py` L16 (`OANDA_ENV = "practice"`) |
| Endpoint params used | `{"count": count, "granularity": g}` — **no explicit `price` parameter** | `data_pipeline.py` L736 |
| Price convention implied | code reads `c["mid"]` (o/h/l/c). OANDA's `CandlestickData` documents `mid` as being returned only when midpoint-based candles are requested; the default when `price` is omitted is the midpoint (`M`). Recorded as **CONSISTENT / inferred from behaviour**, not read from an explicit parameter. | `data_pipeline.py` L742–752; OANDA REST-V20 Instrument Definitions (`CandlestickData`) |
| Granularity | `M15` default (`oanda_granularity: str = "M15"`) | `data_pipeline.py` L709 |
| Instrument range | whatever `instrument` the caller passes; per-instrument coverage not yet enumerated here (see §6 per-instrument row) | `data_pipeline.py` L729, L733 |
| Non-OANDA fallback | `_from_yfinance` exists for the same `fetch()` call — it is **not** the OANDA feed and must not be governed by this calendar | `data_pipeline.py` L774–807 |
| Repo provenance | branch `v2026c`, HEAD `5b11c06fc855c004c11645bed6f54e26be040f2f` | `git rev-parse` (2026-11-15) |

## 3. Source provenance

| Field | Value |
|---|---|
| OANDA official documentation name | (a) OANDA REST-V20 **Instrument Definitions** (`Candlestick`, `CandlestickData`, `CandlestickGranularity`, `WeeklyAlignment`); (b) OANDA **Hours of Operation** — Forex CFDs table |
| Documentation URL(s) | (a) https://developer.oanda.com/rest-live-v20/instrument-df/ ; (b) https://www.oanda.com/uk-en/trading/hours-of-operation/ and https://www.oanda.com/assets/documents/252/Hours_of_Operation.pdf |
| Retrieval date | 2026-11-15 |
| Link present in repo | `https://developer.oanda.com/rest-live-v20/instrument-datatypes/#Granularity` (`data_guard.py` L265) |
| Additional authoritative holiday source | https://www.oanda.com/uk-en/trading/holiday-trading-hours/ — identified, **NOT CAPTURED** (see §7) |
| Source hash / snapshot | NOT CAPTURED — no byte snapshot of the OANDA pages was stored. Quoted wording is reproduced verbatim in §4/§6 for traceability. |

## 4. Timestamp / completion semantics

Linked to Doc 01 IC-02 / IC-03 / IC-04.

| Field | Recorded value | Evidence / status |
|---|---|---|
| Timestamp field | `c["time"]` parsed with `pd.to_datetime(...)` | `data_pipeline.py` L748 |
| Timestamp convention | **EVIDENCED — candle-OPEN (start) timestamp.** OANDA REST-V20: `time` = *"The start time of the candlestick"*. | OANDA REST-V20 Instrument Definitions (`Candlestick`) |
| Open/close field meaning | `o` = *"The first (open) price in the time-range represented by the candlestick"*; `c` = *"The last (closing) price in the time-range represented by the candlestick"*. This confirms `time` is the start of the bar's time-range. | same |
| Timestamp timezone | OANDA returns RFC3339 UTC (`...Z`); parsing yields a tz-aware UTC value | `data_pipeline.py` L748; OANDA `DateTime` primitive |
| Completion signal (correct) | OANDA `complete`: *"A flag indicating if the candlestick is complete. A complete candlestick is one whose ending time is not in the future."* This is the authoritative completion signal. | OANDA REST-V20 Instrument Definitions (`Candlestick`) |
| Completion signal (current code) | **Time-elapsed heuristic only.** The code does **not** read the OANDA `complete` field. | `data_guard.py` L298–310 (`is_latest_candle_closed`), `data_pipeline.py` L741–755 |
| Completion tolerance | `CANDLE_CLOSE_TOLERANCE_SECONDS = 30` | `data_guard.py` L274 |
| Incomplete-candle action | drop the latest row | `data_guard.py` L313–339 (`trim_to_closed_candles`) |

> **Resolution of the IC-02 / RC-03 blocker:** the timestamp convention is now resolved: OANDA `time` is the **candle-open** timestamp. The residual gap is that the live code uses a time-elapsed heuristic instead of OANDA's `complete` flag; it produces the same result for normal operation but is not the authoritative signal. This contract records `complete` as the **correct** signal and flags the heuristic as a deviation to reconcile at implementation time (L3). Until then, IC-02/RC-03 are `CONFIRMED — candle-open`; IC-04's "latest incomplete candle" identification is `CONFIRMED` in rule form but its signal source is `heuristic (deviation logged)`.

## 5. Expected cadence

- Applies only once IC-01/IC-05 are approved as M15.
- Normal contiguous segment: adjacent timestamps are exactly 15 minutes apart.
- `M15` maps to 15 minutes (`data_guard.py` L268 `GRANULARITY_MINUTES`).
- OANDA `M15` is documented as *"15 minute candlesticks, hour alignment"* → M15 bars align to `:00/:15/:30/:45`; the hourly alignment is independent of `alignmentTimezone`.
- Edge conventions at a contiguous segment boundary (is the last candle before a gap included) are **UNRESOLVED** until §6 is approved end-to-end.

## 6. OANDA availability schedule

Retrieved 2026-11-15 from the OANDA **Hours of Operation** page (Forex CFDs table):

> "All FX products (except TRY Pairs) — Timezone of exchange: New York — Trading hours (local exchange time): Sun-Fri: 17:05 - 16:59"
> "Forex instruments open on Sunday at 17:05 and close for the week on Friday 16:59 (New York time). There will be a six minute break between 16:59 - 17:05."
> "There is an additional 6-minute break for NZD pairs starting at 06:59 Auckland time."

OANDA REST candle defaults (Instrument Definitions): `dailyAlignment = 17`, `alignmentTimezone = America/New_York`, `weeklyAlignment = Friday`.

| Item | Status |
|---|---|
| Weekly open | **EVIDENCED** — Sunday 17:05 `America/New_York` (all FX products except TRY pairs) |
| Weekly close | **EVIDENCED** — Friday 16:59 `America/New_York` |
| Weekend gap rule | **EVIDENCED (derived)** — from Friday 16:59 NY to Sunday 17:05 NY the FX feed is closed → the "Friday close → Sunday open" gap is the allowed weekend gap, expressed as UTC instants. A gap is accepted only if it matches this rule exactly; the six-minute re-open offset (17:05 vs 17:00) is part of the rule. |
| Daily maintenance / pause window | **DOCUMENTED, NOT VERIFIED** — a six-minute break 16:59–17:05 New York time each trading day. Whether this removes any M15 candle is not verified against a real feed; **any gap at this boundary stays `UNEXPLAINED` until verified**. |
| Per-instrument differences | **EVIDENCED to exist, coverage UNRESOLVED** — TRY pairs (Mon–Fri 08:00–17:00 Central Europe) and NZD pairs (extra 6-minute break 06:59–07:05 Auckland). The instrument(s) this repo trades are not yet enumerated, so which rule applies is `UNRESOLVED`. |
| "market open" vs "feed provides candles" | **DISTINGUISHED** — the FX rule above is OANDA FX trading hours, which govern the feed. OANDA separately warns that hours are *"subject to change during daylight saving time and certain public holidays"*, so an open market table does not by itself guarantee candles during a holiday closure. |

> The weekly open/close are EVIDENCED, but a full `EXPLAINED` classification additionally requires §7 (holidays) and the daily-maintenance verification. Gap classification therefore remains **fail-closed** until those are resolved.

## 7. Holidays / exceptional closures (UNRESOLVED)

- Authoritative source identified but **NOT CAPTURED**: `https://www.oanda.com/uk-en/trading/holiday-trading-hours/`.
- OANDA explicitly states hours are *"subject to change during daylight saving time and certain public holidays"* → holiday closures are real, but their dates/times are not enumerated in this contract.
- Coverage, update frequency and expiry handling: `UNRESOLVED`.
- Feed outages / temporary suspensions: `UNRESOLVED` (OANDA: *"There may be occasions within market hours when trading may be halted"*).
- Any item that cannot be established from an authoritative source must stay `UNRESOLVED`; no guessed time may be entered. Unresolved gaps are `UNEXPLAINED` → fail closed.

## 8. DST and the timezone database pin (RC-11)

- Session features use IANA zones (`Europe/London`, `America/New_York`); the availability calendar must not mix session hours into OANDA feed availability (Revision Plan §5.2).
- OANDA's FX schedule is expressed in **New York local time**, so the UTC instants of the weekly open/close shift with US DST. The rule is defined in local time; the UTC conversion must be computed from the pinned tz database, never from a fixed offset.
- **Pinned tz identity (RC-11, recorded 2026-11-15, environment evidence):**
  - `tzdata` **2026.5** (the IANA database shipped in the active environment: `zoneinfo.TZPATH = /home/ubuntu/miniconda3/envs/ai-sprint/share/zoneinfo`).
  - `pytz` **2026.1**; `pandas` 2.2.3; Python 3.12.15.
  - IANA zone identity: `Europe/London` (RC-09), `America/New_York` (RC-10).
- Conversion boundaries must be verified with UTC instants; DST rules: applied via the pinned database above.
- Required behaviour: **FAIL CLOSED** when the tz identity is unavailable or ambiguous (Revision Plan §11-4).

## 9. Gap classifier

- Only gaps matching an **approved** §6/§7 rule are `EXPLAINED`.
- Every other gap is `UNEXPLAINED` and rejects the whole batch (Doc 01 IC-06 / IC-07).
- Given §6's daily-maintenance row is `NOT VERIFIED` and §7 is `UNRESOLVED`, **the only currently-approved allowed gap is the weekend gap**; every other gap fails closed.
- No default-to-normal: an unresolved rule never makes a gap acceptable.

## 10. Failure / update policy

- No source, stale source, conflicting sources or an unexplained gap ⇒ **fail closed**.
- This contract is re-reviewed and re-versioned whenever any source/version/coverage or schedule rule changes; referencing IC/RC/experiment clauses must be re-approved.

## 11. Acceptance fixtures

| Fixture | Expected result |
|---|---|
| Adjacent M15 candles (15 min apart) | accepted (contiguous segment) |
| Weekend boundary gap matching Fri 16:59 → Sun 17:05 `America/New_York` exactly | accepted |
| Weekend boundary gap NOT matching that rule | rejected (`UNEXPLAINED`) |
| Daily-maintenance gap (16:59–17:05 NY) | **currently rejected (`UNEXPLAINED`)** — not verified/approved |
| Holiday closure gap | **currently rejected (`UNEXPLAINED`)** — §7 unresolved |
| Anomalous gap not in any approved rule | whole batch rejected (`UNEXPLAINED`) |
| Source stale / unavailable | fail closed |
| Conflicting sources | fail closed |

## 12. Authorization boundary

This contract approves only the clauses evidenced above (§4 timestamp convention, §6 weekly open/close, §8 tz pin, §9 classifier). It does **not** approve any holiday or daily-maintenance value, does **not** modify production code, and does **not** authorize training, artifact writes, deployment, READY activation or trading behaviour changes. Any clause not evidenced here remains `UNRESOLVED` and fails closed.
