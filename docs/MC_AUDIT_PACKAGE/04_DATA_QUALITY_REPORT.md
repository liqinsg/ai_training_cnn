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
| Trade lifecycle | PARTIAL | 345/457 November entry records uniquely matched; 112 have no unique lifecycle match. In the focus window, 187 are uniquely linked, 6 joins are ambiguous, and 65 lack a unique lifecycle record. |
| Fees/financing/account currency | DATA NOT AVAILABLE | P/L currency is not identified and costs are not separately recorded in the matched trade rows. |
| Portfolio/risk budget | DATA NOT AVAILABLE | No synchronized position count, margin, available capacity, or currency-exposure snapshot. Shadow sizing rows are not actual risk utilization. |
| Demo baseline independence | NOT VERIFIED | Shadow records exist and are unapplied; active baseline runtime was not inspected. |
| Calibration and out-of-sample tests | NOT CALCULATED | No valid fixed-horizon realized-price series; Brier, log loss, and calibration would be unsupported. |

`02_market_regime_timeline.csv` records the next archived reference-price observation with its irregular timestamp gap. It explicitly labels this as retrospective and does not substitute it for the requested fixed horizons.

