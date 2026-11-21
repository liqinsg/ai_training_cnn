# 03 — Trading Reconstruction (v685 scope)

## Log coverage

Available v685 daily logs span 2026-11-02 through 2026-11-20, with 16 files. Logs for 2026-11-07, 2026-11-08, and 2026-11-14 are absent. The 2026-11-15 file is partial and contains no MC-tagged execution/open record. Log timestamps explicitly use Singapore time; exit records use UTC.

The v685 open-reason logs record `MC_P_UP` rounded to an integer. In the 11/9–11/20 market window, 258 logged execution/open records were found: 112 JPY and 146 non-JPY. MC sign alignment was 204 aligned, 48 opposite, and 6 ties. This is not a probability-accuracy or P/L result.

The v685 logs contain candidate-list, score, ranking, probability-zone skip, and execution messages. The export counts log events, not unique candidate opportunities. Same-second repeated instrument/direction entries create six ambiguous MC-to-trade-ID joins in the 11/9–11/20 window.

## Trade lifecycle match

Across all available November v685 entry logs, 457 MC-tagged entry records were identified. 345 have a unique match to exit-audit data by trade ID, instrument, side, and local open date; 112 do not have a unique lifecycle match. For the 11/9–11/20 window:

- 187 entries have unique MC-entry and lifecycle linkage.
- 6 same-second entries have ambiguous MC-probability-to-trade-ID assignment.
- 65 have no unique exit-audit lifecycle match.

The 187 uniquely linked window records are 107 TP, 40 SL, and 40 ACTIVE. ACTIVE is not a closed outcome. These records are a partial, multi-profile sample and should not be treated as independent observations.

## Supplemental profile trade CSVs

The 16 CSVs under `daily_results_profile1/` through `daily_results_profile4/` contain 1,603 raw rows but 577 distinct `(account, trade_id)` identities. All 577 identities also occur in the exit-audit JSONL records. Repeated keys across directories have matching trade fields; the directories are overlapping exports, not separate profile-only samples. The row-level `profile` field was used for attribution.

The deduplicated open-time range is 2026-10-22 through 2026-11-20 across 26 dates. Outcomes are TP=326, SL=154, ACTIVE=97. The recorded profiles contain: Profile 1: 146 trades; Profile 2: 171; Profile 3: 135; Profile 4: 125. Overall direction is 554 short and 23 long; 304 JPY-pair records are all short, while non-JPY records are 250 short and 23 long.

These are exit labels, not a win-rate estimate: three SL rows record positive P/L, and ACTIVE rows also have populated P/L/pips/close timestamps whose meaning is undocumented. The data lack MC probabilities, H4 candles, candidate/ranking evidence, sizing-rule version, fees/financing, and account currency. Do not combine P/L values across accounts or use the trade mix to infer the MC weight or market regime.

## Two-sided stop event

The linked trade records show a USD_CHF long (Profile 1) and short (Profile 2) opened and closed on 2026-11-13 Singapore time; both exit records are labelled SL. The long entry log has MC P(up)=59%; it closed at +0.9 pips and +1.372 recorded P/L. The short entry log has MC P(up)=46%; it closed at -27.9 pips and -33.651 recorded P/L. Both logged MC readings were aligned with their respective entry directions. The currency of the reported P/L is not specified; the long SL close was not a loss.

The daily USD_CHF bundle had P(up)=59.2% on 2026-11-12 and 58.5% on 2026-11-13 (original regime `D NEUTRAL`). The weekly USD_CHF bundle on 2026-11-09 had P(up)=42.3%. Profile 2's weekly/daily blend is therefore a concrete source of difference from raw daily MC; it is not a general explanation for all candidate choices.

This verifies a cross-profile, same-pair, two-direction stop event. It does **not** independently classify the price action as wide-range/choppy.

## Capital and opportunity limits

No synchronized portfolio, available-capacity, margin, or account-currency risk snapshot was available. Candidate logs do not provide a complete stable-ID ledger linking every generated opportunity to all filters, rank, capacity, and execution. Consequently, displacement of a better JPY opportunity and capital opportunity cost are NOT VERIFIED.

See `04_trade_mc_alignment.csv`, `05_whipsaw_trade_analysis.csv`, and `06_opportunity_decision_reconstruction.csv`.

