# MC Audit Package — Data Dictionary

## Reproduction

From the repository root, run:

```bash
python docs/MC_AUDIT_PACKAGE/generate_audit_exports.py
```

The script reads the v685 November logs, matching exit/shadow logs, and the MC archive at `~/projects/fx_monte_carlo/mc_results/`. Alternate paths may be supplied with `--mc-dir`, `--logs-dir`, and `--out-dir`. It writes only to the selected output directory; source files are read-only.

The source archive is outside this repository. The CSVs are auditable exports, not original file copies. `SHA256SUMS.txt` records hashes for source files, generated CSVs, and the generator.

## Export definitions

| CSV | Definition |
|---|---|
| `01_mc_snapshot_history.csv` | Every result record from all matched D/W bundle files, including original P(up), P(down), regime, bundle/record generation times, source filename, checksum, validity, and duplicate status. Publication time is blank because it is not recorded. |
| `02_market_regime_timeline.csv` | Per-instrument snapshot sequence with probability/regime changes and the next archived reference-price change. Next-observation returns are retrospective and irregular-gap observations, not fixed-horizon labels. |
| `03_currency_consensus_timeline.csv` | Currency-relative signed MC edge. Base/quote orientation is applied. Reverse instrument orientations for the same unordered currency pair are averaged and counted once; related pairs remain correlated. |
| `04_trade_mc_alignment.csv` | v685 `EXECUTED`/`OPEN` pairs keyed by log timestamp, instrument, and direction. Entry P(up) is the logged rounded integer, not the original full-precision snapshot value. A bundle filename/regime is not uniquely linked per trade. Exit status/P&L is populated only for unique trade-ID/pair/side/date matches. |
| `05_whipsaw_trade_analysis.csv` | Trade records uniquely linked to v685 entry logs and the exit audit. Includes an indicator for same-pair, same-UTC-day opposite-direction SL records. P/L currency is not specified. |
| `06_opportunity_decision_reconstruction.csv` | Per-log counts of candidate-list, rejected-list, ranking, and MC-tagged execution messages. These are log-message counts, not counts of unique candidate opportunities. |
| `07_risk_budget_utilization.csv` | Per-day/profile shadow-record counts and tiers. Position capacity, margin, and account-currency risk are explicitly unavailable. |
| `08_data_quality_and_gaps.csv` | Missing, incomplete, or conflicting evidence and impact. |
| `09_statistical_evidence_summary.csv` | Supported descriptive facts and explicit non-calculations for unsupported forecast metrics. |

## Interpretation rules

- Original regime labels are copied, not redefined.
- MC direction alignment in the trade export means only whether the logged P(up) sign agrees with BUY/SELL; it is not realized directional accuracy.
- The 50–55 probability bucket is exploratory only.
- `ACTIVE` is not a closed trade outcome.
- A logged `SL` is not assumed to be a loss.
- No file in this package authorizes strategy or live-trading changes.

