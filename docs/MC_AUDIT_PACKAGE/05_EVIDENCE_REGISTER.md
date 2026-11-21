# 05 — Evidence Register

| ID | Evidence | Classification | Conclusion supported | Limitation |
|---|---|---|---|---|
| E-01 | `fx_trade_bot_v685.py`, bundle loading, scoring, probability-zone, and ranking paths | E1 | Local v685 source consumes per-pair MC and includes Profile 2 weekly/daily blending. | Does not prove deployed source/commit. |
| E-02 | `logs/fx_bot_202611*.log` | E1 | v685-tagged logs record MC bundle loads, logged MC P(up), decisions, and executions. | Date gaps; open-reason P(up) rounded; some duplicate same-second joins. |
| E-03 | 116 archived `mc_[DW]_all_pairs_*.json` files | E1 | Preserved daily/weekly MC outputs and timestamps exist over a multi-week period. | Large historical gaps; no OHLC candles or publication timestamp. |
| E-04 | 100 daily archived MC snapshots | E2 descriptive | All 100 show seven JPY pairs oriented toward JPY strength; 26/26 snapshots in 11/9–11/20 do so. | Repeated, correlated forecasts; not realized-price validation. |
| E-05 | MC entry log and exit-audit join | E1 | 345 November v685 entries have a unique trade-lifecycle match; 187 focus-window entries also have a unique MC entry join. | Incomplete lifecycle and ambiguous joins; profiles are correlated. |
| E-06 | USD_CHF opposite-direction SL records on 2026-11-13 | E1 | One long and one short, across Profiles 1 and 2, both later show SL. | One is positive P/L; no candle-based regime confirmation; account currency unknown. |
| E-07 | `wide_range_shadow_20261118..20.jsonl` | E1 | 544 shadow observations: 542 normal, 2 unknown; none wide/extreme; all unapplied. | Begins after the 11/13 event and is not actual trade behavior. |
| E-08 | Historical candles, synchronized portfolio/risk snapshots, complete candidate ledger | E0 | No supported conclusion about volatility regime, calibration, opportunity cost, or displacement. | Required source data not available. |
| E-09 | Checked-in service unit and crontab | E1 | Repository configuration artifacts point to a v6 entrypoint/v683 jobs rather than a confirmed v685 runtime. | Files may be stale; active server state not inspected. |
| E-10 | Worktree diff for `config_profile.json` | E1 | `ranking_cooldown.REMOVE_COOLDOWN` is true in the worktree versus false in Git HEAD. | Not made or reverted by this audit; whether this configuration is deployed is unknown. |
| E-11 | `daily_results_profile1..4/*_trade_log.csv` | E1 | 1,603 rows deduplicate to 577 `(account, trade_id)` identities, all matching exit-audit identities; open times span 2026-10-22..11-20. | Directories overlap; use row `profile`, not folder name. No MC, H4 market, candidate-ranking, sizing-rule history, or account-currency fields. `ACTIVE` and SL/TP semantics require caution. |

E2 findings are associations/descriptive patterns only. No E3 out-of-sample or E4 strategy-impact evidence is established.

