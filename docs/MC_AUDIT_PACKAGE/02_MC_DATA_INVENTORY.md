# 02 — MC Data Inventory

## Archive examined

Source directory: `/home/ubuntu/projects/fx_monte_carlo/mc_results/`, the sibling archive selected by the inspected loader when the repository-local `mc_results/` directory is absent.

| Timeframe | Files | Generated-time range | Result rows |
|---|---:|---|---:|
| Daily | 100 | 2026-09-13 05:03 UTC to 2026-11-20 05:49 UTC | 2,828 |
| Weekly | 16 | 2026-09-13 05:35 UTC to 2026-11-16 06:32 UTC | 459 |
| Total | 116 | 2026-09-13 to 2026-11-20 | 3,287 |

The archive has 42 daily-generation dates and 9 weekly-generation dates. Generated timestamps are unique; no byte-identical bundles were found. Multiple bundles on one date were retained as separate observations.

## Fields and quality

- Each inspected JSON file contains `metadata` and `results`.
- Result records include timeframe, pair, current/reference price, P(up), P(down), original regime, forecast metadata, and generation time.
- All inspected P(up)/P(down) values were in `[0,100]` and complementary within 0.11 percentage points.
- Results contain 28 or 29 instruments per bundle. Across the archive there are 30 raw instrument strings but 28 unordered currency relationships; `CAD_NZD`/`NZD_CAD` and `CHF_NZD`/`NZD_CHF` are reverse orientations and are counted once in consensus.
- The archive metadata reports `total_pairs=35` in 108/116 files, while result objects contain 28/29 rows. This count mismatch is recorded, not silently repaired.
- Daily outputs have a 19-calendar-day gap between 2026-09-23 and 2026-10-13. Weekly outputs are missing several expected weekly intervals, including the weeks beginning 2026-09-28 and 2026-10-05.
- Files do not contain a separate publication timestamp or historical OHLC candle series.

## JPY snapshot result

All 100 archived daily snapshots contain seven JPY pairs. All 700 instrument-level P(up) observations point to relative JPY strength when base/quote orientation is applied. The earliest archived snapshot, 2026-09-13, already has 7/7 agreement; the archive cannot establish when the move began. During 2026-11-09 through 2026-11-20, all 26 daily snapshots have 7/7 agreement, with mean signed probability edge 9.33 percentage points.

These are correlated repeated forecasts, not independent samples and not evidence of realized price accuracy.

## Exports

- Complete archived result rows and source hashes: `01_mc_snapshot_history.csv`.
- Snapshot-to-snapshot descriptive timeline: `02_market_regime_timeline.csv`.
- Orientation-corrected, reverse-pair-deduplicated consensus: `03_currency_consensus_timeline.csv`.
- Input hashes: `SHA256SUMS.txt`.

