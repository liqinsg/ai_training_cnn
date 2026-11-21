# 04 — Data Quality and Evidence Gaps

| Issue | Status | Impact |
|---|---|---|
| Runtime version, effective config, and deployed commit | NOT VERIFIED | Checked-in service/crontab do not establish the running v685 process. |
| MC snapshot generation time | Available | `generated_utc` and bundle filename timestamps are present. |
| MC publication time | DATA NOT AVAILABLE | No separate publish timestamp; a later bot load time is not a publish time. |
| Strategy consumption | PARTIAL | Logs contain MC bundle names and rounded entry P(up), but not a unique archive filename/profile/run ID on each entry record. |
| MC instrument coverage | INCONSISTENT COUNTS | Bundles have 28/29 result rows; metadata commonly says 35; archive has two reverse orientations of the same currency relationship. |
| Historical price candles | DATA NOT AVAILABLE | No candle time series to verify realized volatility, regime transitions, or 1H/4H/8H/1D outcomes. |
| Historical MC coverage | GAPS | Daily archive has a 19-day gap from 2026-09-24 through 2026-10-12; weekly archive also has missing intervals. |
| v685 log coverage | GAPS | 2026-11-07, 11-08, and 11-14 absent; 11-15 is partial. |
| Candidate history | INCOMPLETE_CANDIDATE_EVIDENCE | Logs contain event text but no complete candidate ledger with stable IDs and per-stage outcomes. |
| Trade lifecycle | PARTIAL | Profile CSVs contain 577 distinct `(account, trade_id)` identities matching the 577 exit-audit records, over open times 2026-10-22..11-20. Separately, only 345/457 November MC-tagged entry rows uniquely link to those lifecycle records; 112 entry-to-lifecycle links remain unresolved. In the focus window, 187 link uniquely, 6 MC-to-trade joins are ambiguous, and 65 entry rows lack a unique lifecycle link. |
| Profile CSV duplication/attribution | OVERLAPPING EXPORTS | 1,603 raw rows reduce to 577 distinct identities; repeated business fields agree. 1,026 raw rows have a `profile` value different from the containing directory suffix, so attribution uses the row's `profile` field. |
| Fees/financing/account currency | DATA NOT AVAILABLE | P/L currency is not identified and costs are not separately recorded; do not aggregate P/L across the six account IDs. |
| Trade export outcome semantics | PARTIAL/AMBIGUOUS | Three `SL` rows have positive P/L; `ACTIVE` rows still contain close-time, pips, and P/L fields. Do not equate exit labels to wins/losses or treat ACTIVE values as realized without source semantics. |
| Position-sizing rule history | DATA NOT AVAILABLE | Units and SL/TP prices are present, but no sizing-rule/version, Fibonacci/probability input, or change timestamp is recorded. |
| Market regime / OHLC | DATA NOT AVAILABLE IN THESE CSVs | Trade exports contain no H4 candles or regime labels; they cannot reconstruct wide-ranging H4 movement or JPY-strength onset. |
| Portfolio/risk budget | DATA NOT AVAILABLE | No synchronized position count, margin, available capacity, or currency-exposure snapshot. Shadow sizing rows are not actual risk utilization. |
| Demo baseline independence | NOT VERIFIED | Shadow records exist and are unapplied; active baseline runtime was not inspected. |
| Calibration and out-of-sample tests | NOT CALCULATED | No valid fixed-horizon realized-price series; Brier, log loss, and calibration would be unsupported. |

`02_market_regime_timeline.csv` records the next archived reference-price observation with its irregular timestamp gap. It explicitly labels this as retrospective and does not substitute it for the requested fixed horizons.

