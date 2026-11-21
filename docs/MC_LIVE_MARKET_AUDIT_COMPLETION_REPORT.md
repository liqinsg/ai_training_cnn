# MC Live Market Audit — Completion Report

**Audit scope:** v685 / v685-2 only  
**Original audit date:** 2026-11-20
**Supplemental profile-CSV review:** 2026-11-22
**Mode:** Read-only source, log, archive, and trade-export analysis
**Overall status:** Local audit complete; full acceptance blocked by missing runtime and market evidence  
**Trading changes:** None

## Executive summary

The accessible v685-tagged records show that the strategy consumed MC information at the instrument level: its inspected entry path loads daily MC, optionally blends weekly MC for Profile 2, uses MC in direction/scoring, logs the probability in order reasons, and applies a probability-zone skip. This is stronger evidence than the mere presence of MC code.

The archived daily MC snapshots show a consistent descriptive JPY signal: all seven JPY pairs pointed toward JPY strength in each of 100 archived daily snapshots from 2026-09-13 through 2026-11-20. In the 26 daily snapshots generated from 2026-11-09 through 2026-11-20, all seven pairs continued to agree; the mean signed edge was 9.33 percentage points. The archive has a 19-day gap from 2026-09-24 through 2026-10-12, so this does not establish uninterrupted market behavior or the true onset of JPY strength.

Across the available v685 logs dated 2026-11-09 through 2026-11-20 (2026-11-14 absent; 2026-11-15 partial), 258 logged executions had an MC probability in the order reason: 112 JPY pairs and 146 non-JPY pairs. The executed direction agreed with the sign of the logged MC probability in 204 cases, disagreed in 48, and tied at 50% in 6. These are execution-input facts, not evidence that MC predicted subsequent price movement or that non-JPY entries had an independent statistical edge.

Across the 457 MC-tagged November entry-log records, 345 link uniquely to a lifecycle record in the 577-record profile-CSV/exit-audit dataset; 112 entry-to-lifecycle links remain unresolved. In the 2026-11-09 through 2026-11-20 focus window, 187 link uniquely to both entry MC and lifecycle data; six same-second entries have ambiguous MC-to-trade assignment, and 65 have no unique lifecycle link.

Supplemental review of the 16 CSVs under `daily_results_profile1/` through `daily_results_profile4/` found 1,603 rows but only 577 distinct `(account, trade_id)` records. The repeated records are identical on the trade fields examined and the 577 unique identities match the 577 exit-audit records. Using each row's `profile` field (not its directory name), the records span 2026-10-22 through 2026-11-20: 326 TP, 154 SL, and 97 ACTIVE. They are overwhelmingly short (554 short, 23 long). These files improve lifecycle coverage, but do not contain historical MC probabilities, candidate rankings, or market-regime labels.

The observed two-sided stop event is specific: on 2026-11-13, v685 logs and exit records show one USD_CHF long and one USD_CHF short, from different profiles, both later labelled SL. The logged MC P(up) at their entries was 59% for the long and 46% for the short. The long closed at +0.9 pips and +1.372 recorded P/L; the short closed at -27.9 pips and -33.651 recorded P/L. The account currency is not identified, and an SL label did not mean both trades lost. Without contemporaneous candle data, this does not establish that the market was wide-range or choppy.

The full research questions cannot be closed. No historical OHLC candle series, synchronized portfolio/margin snapshots, fully linked candidate ledger, or independently confirmed production runtime was available. Brier score, log loss, calibration, fixed-horizon returns, and out-of-sample results were therefore not calculated. No strategy, order, sizing, SL/TP, or production configuration changes were made by this audit. At final status check, [config_profile.json](/home/ubuntu/projects/ai_training_cnn/config_profile.json) had an uncommitted worktree change (`ranking_cooldown.REMOVE_COOLDOWN: false` in Git HEAD, `true` in the worktree). I did not make or revert it; whether it is deployed is unknown.

## Findings by research question

### RQ-01 — MC directional advantage

- **Observed, E1:** The archive contains 100 daily and 16 weekly MC JSON files, generated from 2026-09-13 through 2026-11-20 (daily) and 2026-09-13 through 2026-11-16 (weekly). The 100 daily snapshots all contain seven JPY pairs; all 700 JPY-pair records have P(up) oriented toward JPY strength.
- **Observed, E1:** The 26 daily snapshots from 2026-11-09 through 2026-11-20 all show the same 7/7 JPY direction. This is repeated, correlated evidence—not 182 independent confirmations.
- **Descriptive, E2:** The original per-pair classifications show the JPY-pair mix moving from one Strong / six Neutral on the latest 2026-11-09 snapshot to five Strong / two Neutral on 2026-11-20. Original regime labels were preserved.
- **Not established, E0:** Predictive quality, calibration, or market-regime usefulness. The forecasts have no matched, fixed-horizon realized price labels. The earliest archived snapshot already has the JPY direction; the archive cannot date its onset.

### RQ-02 — Actual MC use by v685

- **Observed, E1:** The inspected v685 entry path loads precomputed daily bundles and weekly bundles; Profile 2 blends weekly and daily P(up). MC contributes to per-pair direction/scoring and a probability-zone gate. v685 logs contain bundle filenames, MC probabilities, candidate/ranking messages, and `MC_P_UP` in order reasons.
- **Observed, E1:** The 2026-11-18 through 2026-11-20 logs contain 283 `PROB-ZONE SKIP` messages. They are log events, not a count of unique independent opportunities.
- **Concrete timeframe divergence, E1:** For USD_CHF, archived daily P(up) was 59.2% on 2026-11-12, while the 2026-11-09 weekly P(up) was 42.3%. Profile 2's short entry log recorded 46%; a later Profile 1 long entry recorded 59%. This illustrates that the blend can differ from raw daily MC; it does not explain portfolio-wide selection.
- **Runtime boundary:** Local v685 source and v685-tagged logs are available, but the currently deployed process/version and the exact code commit it ran are NOT VERIFIED.

### RQ-03 — Non-JPY selection and capital use

- **Observed, E1:** In the available 2026-11-09 through 2026-11-20 entry logs, there were 146 non-JPY and 112 JPY executions across the v685 profiles. The logs show that JPY-pair entries in that window were sells; the non-JPY entries were not all in one direction.
- **Supplemental trade-export fact, E1:** Across the 577 deduplicated profile-CSV records opened 2026-10-22 through 2026-11-20, 304 are JPY pairs (all short) and 273 are non-JPY (250 short, 23 long). This is an executed-trade mix only; these files do not record the MC weights, unselected candidates, or ranking needed to test whether low JPY weighting caused non-JPY selection.
- **Observed, E1:** Among non-JPY entries, 117/146 had logged MC probability in the trade direction, 23 were opposite, and 6 were ties. Of the 146 non-JPY entries, 57 had trade-aligned logged probabilities from 50% up to but not including 55%. These are descriptive probability buckets, not an approved quality threshold.
- **Not established, E0:** Whether a non-JPY entry displaced a better JPY candidate, whether an unexecuted JPY opportunity existed, or whether the non-JPY trades had independent realized advantages. Candidate history is not a complete, stable-ID opportunity ledger; synchronized available-capacity, margin, and currency-exposure snapshots are absent.
- **Source-code observation:** The inspected v685 path scores MC per instrument and ranks generated strength candidates. The reviewed entry path does not log a cross-pair JPY-consensus ranking input. The evidence is insufficient to attribute any particular non-JPY selection to a specific filter, ranking, or capacity decision.

### RQ-04 — Conditions worth participating in

- The archive and logs establish that MC presented a persistent JPY direction in the available snapshots and that v685 consumed MC per pair.
- **Supplemental limitation:** Trade exports show the strategy's recorded positions and outcomes, not H4 market structure. They cannot establish the start or evolution of the user's described wide-ranging H4 swings or date the beginning of JPY strength; those questions still require historical price data.
- The two-sided USD_CHF stop event demonstrates that MC-aligned entry direction did not guarantee a favorable trade outcome.
- The separate wide-range shadow logs contain 544 observations from 2026-11-18 through 2026-11-20: 542 `normal`, 2 `unknown`, 0 `wide`/`extreme`; every record has `applied=false`. This shadow starts after the 2026-11-13 event and cannot classify it.
- The separate sizing shadow contains 546 records; every record is marked `applied=false`, so it is not evidence of actual sizing or portfolio-risk utilization.
- Price regimes, stop-out context, MC calibration, and strategy impact remain unverified. No E3 out-of-sample or E4 strategy-impact evidence is available.

## Phase status

| Phase | Result | Reason |
|---|---|---|
| 1 — Runtime fact finding | **Partial; not accepted overall** | Local source, archives, logs, and checksums were inspected. Production runtime, deployed commit, and complete server evidence were not verifiable. |
| 2 — Offline MC audit | **Partial** | MC snapshots, logs, shadow records, and deduplicated trade lifecycle exports are reviewed. Candle-based outcomes, calibration, out-of-sample validation, and complete candidate/risk reconstruction are unavailable. |
| 3 — Parallel Demo | **Not verified** | Existing wide-range and sizing shadow logs are present and marked unapplied; active Demo baseline independence and runtime behavior were not checked. |
| 4 — Independent branch | **Not started** | Phase 1 acceptance and separate authorization are not present. No branch or behavior change was made. |

Phase 1 item-by-item results are in [06_PHASE1_ACCEPTANCE.md](MC_AUDIT_PACKAGE/06_PHASE1_ACCEPTANCE.md). The data dictionary and reproducibility instructions are in [DATA_DICTIONARY.md](MC_AUDIT_PACKAGE/DATA_DICTIONARY.md); source and export hashes are in [SHA256SUMS.txt](MC_AUDIT_PACKAGE/SHA256SUMS.txt).

## Deliverables

Phase 1 records:

- [01_RUNTIME_FACTS.md](MC_AUDIT_PACKAGE/01_RUNTIME_FACTS.md)
- [02_MC_DATA_INVENTORY.md](MC_AUDIT_PACKAGE/02_MC_DATA_INVENTORY.md)
- [03_TRADING_RECONSTRUCTION.md](MC_AUDIT_PACKAGE/03_TRADING_RECONSTRUCTION.md)
- [04_DATA_QUALITY_REPORT.md](MC_AUDIT_PACKAGE/04_DATA_QUALITY_REPORT.md)
- [05_EVIDENCE_REGISTER.md](MC_AUDIT_PACKAGE/05_EVIDENCE_REGISTER.md)
- [06_PHASE1_ACCEPTANCE.md](MC_AUDIT_PACKAGE/06_PHASE1_ACCEPTANCE.md)

Offline exports:

- [01_mc_snapshot_history.csv](MC_AUDIT_PACKAGE/01_mc_snapshot_history.csv)
- [02_market_regime_timeline.csv](MC_AUDIT_PACKAGE/02_market_regime_timeline.csv)
- [03_currency_consensus_timeline.csv](MC_AUDIT_PACKAGE/03_currency_consensus_timeline.csv)
- [04_trade_mc_alignment.csv](MC_AUDIT_PACKAGE/04_trade_mc_alignment.csv)
- [05_whipsaw_trade_analysis.csv](MC_AUDIT_PACKAGE/05_whipsaw_trade_analysis.csv)
- [06_opportunity_decision_reconstruction.csv](MC_AUDIT_PACKAGE/06_opportunity_decision_reconstruction.csv)
- [07_risk_budget_utilization.csv](MC_AUDIT_PACKAGE/07_risk_budget_utilization.csv)
- [08_data_quality_and_gaps.csv](MC_AUDIT_PACKAGE/08_data_quality_and_gaps.csv)
- [09_statistical_evidence_summary.csv](MC_AUDIT_PACKAGE/09_statistical_evidence_summary.csv)

The exports are auditable extracts, not copies of the original MC archive or full log files. Original evidence was read-only; the manifest records source paths and SHA256 hashes. The generator is [generate_audit_exports.py](MC_AUDIT_PACKAGE/generate_audit_exports.py).

## Required follow-up evidence

To complete the blocked acceptance items, an authorized operator should provide:

1. The actual v685 runtime command, process/service status, effective config, runtime version, and deployed commit.
2. The complete historical OHLC candle archive for the target period, with timezone and source metadata.
3. Per-decision candidate IDs and input/output/rejection/ranking/selection fields, linked to actual execution IDs.
4. Synchronized positions, margin, available capacity, currency exposure, and account-currency risk snapshots.
5. Any order/fill/partial-closure evidence beyond the available per-trade lifecycle rows, plus fees, financing, and account-currency definition.
6. Confirmed Demo baseline and shadow process separation.

Until that evidence is reviewed, do not treat these findings as authorization to change or enable trading behavior.

## Appendix A — Supplemental profile trade CSV review (2026-11-22)

The review read all 16 files in [daily_results_profile1/](../daily_results_profile1/), [daily_results_profile2/](../daily_results_profile2/), [daily_results_profile3/](../daily_results_profile3/), and [daily_results_profile4/](../daily_results_profile4/). It did not modify the source CSVs.

### Deduplication and coverage

| Measure | Result |
|---|---:|
| CSV files / raw rows | 16 / 1,603 |
| Distinct `(account, trade_id)` keys | 577 |
| Repeated rows beyond distinct keys | 1,026 |
| Distinct keys repeated in multiple profile directories | 477 |
| Distinct keys present in all four directories | 201 |
| Trade open-time range | 2026-10-22 through 2026-11-20 |
| Distinct open dates | 26 |
| Unique identities also found in exit-audit JSONL | 577 / 577 |

Repeated keys have identical trade-field values in the CSV copies. The CSV directories are not disjoint samples: 1,026 raw rows have a `profile` value different from the directory suffix. Counts below therefore use the row's `profile` field and deduplicate by `(account, trade_id)`, not the containing directory. The CSVs and exit-audit records are matching representations of the same trade identities, not independent outcome replications.

### Deduplicated outcomes

| Recorded profile | TP | SL | ACTIVE | Total | Long | Short |
|---|---:|---:|---:|---:|---:|---:|
| Profile 1 | 81 | 39 | 26 | 146 | 9 | 137 |
| Profile 2 | 94 | 47 | 30 | 171 | 3 | 168 |
| Profile 3 | 83 | 41 | 11 | 135 | 5 | 130 |
| Profile 4 | 68 | 27 | 30 | 125 | 6 | 119 |
| **Total** | **326** | **154** | **97** | **577** | **23** | **554** |

Among the 480 records labelled TP or SL, 326 are labelled TP and 154 SL. This is an exit-label distribution, not a strategy win rate: 3 of the 154 SL rows have positive recorded P/L. ACTIVE rows also contain populated close-time, pips, and P/L fields, so those fields cannot be assumed to be realized outcomes without a definition of the export semantics. P/L must not be summed across accounts because account-currency metadata is absent.

### What this adds—and what it does not

- It adds an October 22–November 20 trade-lifecycle view and profile-attributed outcome counts, after deduplicating repeated account/trade records.
- It confirms that this trade sample is short-dominated, including all 304 JPY-pair records being short. That describes executed trades only; it does not show the underlying JPY candidate universe or explain the MC weight used in selection.
- The CSV fields are trade/account/profile, direction, units, prices, pips, P/L, exit label, and timestamps. They do not include MC probability, H4 OHLC, market regime, candidate rank/rejection, position-sizing rule/version, commission/financing, or account currency.
- The files cannot independently reconstruct H4 wide-ranging oscillations or test MC probability distributions. Historical price and contemporaneous MC archives remain necessary for those V2 modules.

The 16 source CSVs are now SHA256-listed in [SHA256SUMS.txt](MC_AUDIT_PACKAGE/SHA256SUMS.txt).
