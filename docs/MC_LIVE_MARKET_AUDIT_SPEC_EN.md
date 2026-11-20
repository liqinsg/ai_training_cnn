# [Permanent Spec] MC Live Market Audit & Strategy Utilization

**Version:** 1.0  
**Date:** 2026-11-20  
**Status:** PROPOSED — Pending Owner Approval  
**Priority:** P0  
**Document Type:** Permanent Research and Audit Specification  
**Scope:** MC Historical Data / Live Trading Reconstruction / Market Regime / Capital Allocation / Demo Validation

---

# 0. Document Authority

## 0.1 Purpose

This document defines a systematic audit of Monte Carlo (MC) probability data and its actual utilization by the trading strategy.

The primary objective is not merely to determine whether MC can predict price movements.

The objective is to answer:

**Does the trading system effectively use MC probability information to identify market conditions worth participating in and allocate its limited trading capital to opportunities with measurable statistical advantages?**

The audit must investigate:

1. How market conditions evolved over time.
2. Whether MC can distinguish directional markets from unclear or unstable markets.
3. Whether MC probabilities contain measurable statistical information.
4. Whether the strategy actually reads and uses that information.
5. Why the strategy enters trades when directional advantage is unclear.
6. Whether less attractive opportunities occupy capital that could have been allocated to clearer opportunities.
7. How audit findings can be translated into independently testable strategy improvements.

## 0.2 Authority Boundary

This document is a research and audit specification. It is not a trading authorization.

This document does NOT authorize:

- Changes to production strategy logic.
- Changes to the existing MC algorithm.
- Changes to order-submission logic.
- Changes to position sizing or risk parameters.
- Changes to SL/TP behavior.
- Activation of new trading filters.
- Submission of new live orders.

Any behavior-changing modification requires separate technical review and explicit Owner approval.

## 0.3 Core Principles

- There is no Holy Grail. We investigate probability advantages.
- The system should participate only in market conditions it can identify and evaluate.
- The system is not required to participate in every market movement.
- Capital and risk budgets are limited resources. Opportunity cost matters.
- Statistical association is not causation.
- Calculation is not execution confirmation.
- Logging does not mean the strategy has consumed or acted on the information.
- Missing data must be explicitly identified. Do not fabricate or infer unavailable evidence.
- Do not selectively use data to make the strategy appear successful.

---

# 1. Research Questions

The project must address four primary research questions.

## RQ-01: Can MC Identify Directional Advantage?

Investigate whether MC probabilities can distinguish:

- Markets with clear directional advantage.
- Markets with weak directional advantage.
- Markets with unclear direction.
- Markets with frequent probability-direction changes.
- Markets undergoing volatility or regime transitions.

Do not evaluate MC solely by checking whether P(up) is above or below 50%.

Investigate:

- Probability edge magnitude.
- Probability persistence.
- Probability change rate.
- Directional consistency across multiple observations.
- Cross-pair consistency.
- Subsequent realized market behavior under different market conditions.

Preserve the original definitions of MC classifications such as Strong, Neutral, and Consolidation.

Do not redefine these classifications inside the audit script without documenting and separately approving the methodology.

## RQ-02: Does the Strategy Actually Use MC Information?

Compare:

- What MC actually produced at the time.
- What information the strategy actually read.
- Which trade candidates the strategy generated.
- Which candidates passed or failed filters.
- Which candidates were eventually executed.
- Which candidates were not executed and why.

Investigate the following possibilities:

1. MC showed directional advantage, but the strategy did not exploit it.
2. MC showed unclear direction, but the strategy still traded.
3. The executed trade direction conflicted with MC.
4. The strategy consumed only selected MC fields rather than the complete probability information.
5. MC data existed, but the decision chain did not consume it.
6. Other strategy conditions prevented an MC-supported opportunity from being selected.

Do not infer what the strategy knew from executed trades alone.

## RQ-03: Was Capital Allocated to Low-Quality Opportunities?

Investigate:

- Directional clarity at actual entry time.
- Other available trade candidates at the same time.
- Actual positions and risk budgets.
- Correlated currency exposure.
- Opportunity ranking.
- Available capital and position capacity.
- Trade selection and execution sequence.

A central question is:

**Why did the strategy continue opening numerous non-JPY positions when JPY directional strength had already been observable for some time?**

Investigate, without presuming the answer, whether:

- No JPY candidates were generated.
- JPY candidates failed other technical conditions.
- JPY candidates were excluded by ranking or position limits.
- The strategy failed to recognize the common JPY direction.
- MC information did not enter the decision chain.
- Non-JPY trades had their own independent advantages.
- Available logs are insufficient to determine the reason.

Do not assume any explanation before examining evidence.

## RQ-04: Can MC Help Identify Market Conditions Worth Participating In?

The ultimate research objective is to identify:

- Which market conditions are more attractive for participation.
- Which market conditions warrant reduced participation.
- Which directional movements demonstrate persistence.
- Which movements are temporary fluctuations.
- Which conditions are associated with stop-outs in both directions.
- Which market conditions are more likely to develop into sustained trends.

The objective is not to increase trade frequency.

The objective is to improve opportunity selection.

---

# 2. Mandatory Historical Market Timeline

## 2.1 Why a Timeline Is Mandatory

The audit must not be limited to a single day's MC snapshot.

The MC Daily Update on 2026-11-20 is one observation point. It does not establish when the preceding market conditions began.

The audit must reconstruct the evolution of market conditions using all available historical data.

Two actual trading observations require particular attention.

### Event A: Wide-Range / Choppy Market

The Owner observed:

- A wide-range, choppy market during the previous week.
- Both LONG and SHORT positions experienced stop-loss exits.
- Individual losses were relatively small, approximately SGD 1 each.
- Nevertheless, the same market environment appeared to penalize both trading directions.

Investigate:

1. When did the wide-range conditions first become observable?
2. Did MC already indicate weak or unclear directional advantage?
3. Did P(up) frequently change direction across observations?
4. Did probability changes lead or lag actual price movements?
5. What were the actual price ranges, volatility levels, and durations?
6. Did LONG and SHORT stop-outs occur on the same instrument, within the same market theme, or across unrelated instruments?
7. Did the strategy repeatedly participate without sufficient directional persistence?
8. Did MC contain information that could have helped identify these conditions?

Do not classify a market as wide-range or choppy merely because both LONG and SHORT trades experienced stop losses.

Validate the classification using actual price and trade-timing data.

### Event B: Established JPY Strength

The Owner observed:

- JPY strength did not begin on 2026-11-20.
- JPY strength had already been observable for some time before the latest MC Daily Update.
- During this period, the strategy continued opening numerous non-JPY positions.
- Some of those non-JPY opportunities appeared to have unclear directional advantage.

Investigate:

1. When did JPY strength first become observable in historical MC data?
2. How did cross-pair JPY directional consistency develop?
3. How many JPY pairs consistently indicated the same direction?
4. How did the proportions of Strong and Neutral classifications change?
5. How long did the directional consistency persist?
6. Were there temporary reversals or disagreements?
7. Did the strategy identify and consume this common directional information?
8. Why did actual trading remain heavily distributed across non-JPY instruments?

### Event C: Regime Transition

Event A and Event B must be placed on the same historical timeline.

Do not assume they were entirely independent market events.

Investigate:

- Whether wide-range conditions gradually contracted or ended.
- Whether the market transitioned from unclear direction to a clearer directional condition.
- Whether JPY strength developed during that transition.
- Whether MC provided useful information during the transition.
- Whether the strategy adapted its participation behavior accordingly.

If the available evidence cannot establish a regime transition, explicitly state that limitation.

## 2.2 Historical Coverage

Collect all available historical MC data from the server and accessible archives.

Do not arbitrarily restrict the historical period to one day or a few recent days.

Priority:

- Collect the complete available historical archive.
- Include the previous week's wide-range event.
- Include the period preceding and covering the development of JPY strength.
- Collect corresponding price candles and actual trade records.
- Collect MC generation, publication, and actual consumption timestamps.

If historical MC snapshots are no longer available:

- Inspect log rotation archives.
- Inspect backup directories.
- Inspect historical output files.
- Inspect other accessible server archives.
- Inspect historical database records.

If historical MC is recalculated from historical prices, it must be classified separately as:

`RETROSPECTIVE_RECALCULATION`

Recalculated historical MC must never be represented as the actual MC output available to the strategy at that historical time.

---

# 3. Phase 1 — Runtime Fact Finding

**Priority:** P0  
**Mode:** READ ONLY  
**Execution:** Server-side inspection, where access is available

The assigned LLM or technical agent must inspect the actual runtime environment, source code, logs, and data files if it has authorized access.

The assigned agent must explicitly state which resources it can and cannot access.

If it cannot access the server, it must produce a precise collection checklist and executable commands for an authorized operator. It must not claim to have completed server-side verification.

## 3.1 Runtime Inventory

Investigate:

| Category | Required Investigation |
|---|---|
| MC Generation | Actual MC generation entry point and execution frequency |
| MC Output | Output files, databases, logs, historical archives |
| MC Timeframes | Actual D1, W1, or other available timeframes |
| MC Fields | P(up), P(down), regime, price, timestamps |
| Strategy Consumer | Modules that read MC |
| Decision Chain | How MC enters candidate generation, filtering, Advisor, and execution |
| Trade Records | Actual entries, exits, SL, TP, fees |
| Candidate Records | Available candidate opportunities and filter outcomes |
| Portfolio State | Actual positions, exposure, and capacity at the time |
| Demo Runtime | Current Demo version and data-collection behavior |

Confirm:

- The actual production runner.
- The actual production strategy file.
- The effective runtime configuration.
- The actual MC data source.
- File timestamps and server timezone.
- Production runtime version and Git commit.

The existence of a feature in source code does not prove that the feature was active in production.

## 3.2 Historical MC Data Inventory

Determine:

1. Number of historical MC files.
2. Earliest recoverable date.
3. Latest recoverable date.
4. Generation timestamp of each file.
5. Instruments included in each file.
6. Duplicate records.
7. Missing dates.
8. Conflicting records for the same instrument at different prices or timestamps.
9. Availability of different MC timeframes.
10. Whether historical outputs were overwritten.

A single date may contain multiple MC updates.

Do not merge records from different generation times into one daily record without preserving the original timestamps.

## 3.3 Trade Reconstruction

Reconstruct actual trade timelines.

Collect, where available:

- Trade ID.
- Instrument.
- Direction.
- Open Time.
- Close Time.
- Entry Price.
- Exit Price.
- Units.
- SL / TP.
- Close Reason.
- Realized P/L.
- Commission / Financing.
- Account Currency.
- Positions and risk exposure at the relevant time.

Distinguish between:

- An order.
- A trade object.
- A trade lifecycle.
- Multiple partial fills or partial closures within one lifecycle.

Do not treat these as interchangeable entities.

## 3.4 Strategy Decision Reconstruction

Reconstruct the available decision chain:

`Market Data → MC → Candidate → Filter → Ranking → Advisor → Execution`

For every available stage, determine:

- Input.
- Output.
- Timestamp.
- Pass/fail status.
- Rejection reason.
- Corresponding log evidence.

If the strategy records only executed trades and does not retain rejected candidates, explicitly report:

`CANDIDATE_HISTORY_NOT_AVAILABLE`

Do not reverse-engineer nonexistent candidate opportunities from final trade records.

## 3.5 Required Phase 1 Deliverables

Submit:

| File | Purpose |
|---|---|
| `01_RUNTIME_FACTS.md` | Actual runtime environment and version facts |
| `02_MC_DATA_INVENTORY.md` | Historical MC data inventory |
| `03_TRADING_RECONSTRUCTION.md` | Actual trade reconstruction |
| `04_DATA_QUALITY_REPORT.md` | Data quality and missing-data report |
| `05_EVIDENCE_REGISTER.md` | Evidence sources and fact register |
| `06_PHASE1_ACCEPTANCE.md` | Phase 1 acceptance report |
| `MC_AUDIT_PACKAGE/` | Exported source data package |

The data package must include:

- Original files or auditable exports.
- File manifest.
- SHA256 checksums.
- Data coverage period.
- Timezone information.
- Data dictionary.
- Source locations.
- Missing-data report.
- Duplicate-record report.

Original data must remain unchanged and read-only.

---

# 4. Phase 2 — Offline MC Audit

**Priority:** P0  
**Execution:** ChatGPT / Python Offline Analysis  
**Prerequisite:** Phase 1 data package and data dictionary

The offline audit script will be developed after the actual data structures have been inspected.

The script must be based on real files and fields.

Do not assume filenames, directory structures, or field names before inspecting the supplied data.

## 4.1 Main Analysis Outputs

The following are target analytical deliverables.

Actual fields must be adjusted according to the available source data.

If a required field is unavailable, report it explicitly. Do not fabricate values.

### CSV 01 — MC Snapshot History

Suggested filename:

`01_mc_snapshot_history.csv`

Purpose: Create a unified historical record of MC snapshots.

Suggested fields:

- Snapshot ID.
- Generated Time.
- Published Time.
- Instrument.
- Timeframe.
- Reference Price.
- P(up).
- P(down).
- Original Regime.
- Data Source.
- Validity Status.
- Duplicate Status.

Preserve original probabilities and classifications.

### CSV 02 — Market Regime Timeline

Suggested filename:

`02_market_regime_timeline.csv`

Purpose: Reconstruct market-condition changes for each instrument.

Investigate:

- Current probability.
- Previous probability.
- Probability change.
- Direction change.
- Regime change.
- Duration.
- Subsequent price movement.
- Subsequent volatility.

Calculate forward outcomes over explicitly defined horizons, where data permits:

- 1H.
- 4H.
- 8H.
- 1D.

Select appropriate horizons based on actual data frequency.

Never use future prices as information available to the strategy at the original decision time.

### CSV 03 — Currency Consensus Timeline

Suggested filename:

`03_currency_consensus_timeline.csv`

Purpose: Investigate common currency direction across multiple instruments.

Focus on:

- JPY.
- USD.
- EUR.
- GBP.
- AUD.
- CAD.
- CHF.
- NZD.

Correctly account for base/quote orientation.

For example:

`USDJPY P(up) < 50%`

indicates a higher probability of USDJPY moving down, which is consistent with relative JPY strength.

For each timestamp, provide where possible:

- Currency.
- Observation Time.
- Distinct Pair Count.
- Bullish Pair Count.
- Bearish Pair Count.
- Directional Consensus.
- Consensus Strength.
- Component Pairs.
- Data Quality.

Important:

Repeated records for the same pair must not count as independent confirmation.

Multiple pairs containing the same currency are statistically related.

Do not treat them as independent samples without qualification.

### CSV 04 — Trade MC Alignment

Suggested filename:

`04_trade_mc_alignment.csv`

Purpose: Match actual trades with MC information available at entry time.

Suggested fields:

- Trade ID.
- Instrument.
- Trade Direction.
- Open Time.
- Matching MC Snapshot Time.
- P(up).
- P(down).
- Original Regime.
- MC Direction.
- Trade Alignment.
- Realized P/L.
- Close Reason.

Use an as-of matching approach.

Only match MC data that had already been generated and was actually available at the trade entry time.

Do not use MC snapshots generated after entry to explain the original entry decision.

If MC generation time, publication time, or strategy consumption time is uncertain, explicitly flag the timestamp-alignment uncertainty.

### CSV 05 — Whipsaw / Wide-Range Trade Analysis

Suggested filename:

`05_whipsaw_trade_analysis.csv`

Purpose: Specifically investigate the observed two-sided stop-loss events.

Suggested fields:

- Trade ID.
- Instrument.
- Direction.
- Open Time.
- Close Time.
- Exit Reason.
- Realized P/L.
- Contemporaneous MC.
- Price Range.
- Realized Volatility.
- Directional Persistence.
- Opposite Direction Trade Exists.
- Same Instrument / Same Theme.
- Evidence Quality.

Distinguish:

- Opposite-direction trades on the same instrument.
- Related trades across different instruments.
- Independent trades at different times.

Do not classify a market as wide-range or choppy solely because LONG and SHORT positions both experienced stop losses.

### CSV 06 — Opportunity and Decision Reconstruction

Suggested filename:

`06_opportunity_decision_reconstruction.csv`

Purpose: Investigate why the strategy selected actual trades instead of other potential opportunities.

Suggested fields:

- Decision Time.
- Instrument.
- Candidate Direction.
- MC Direction.
- MC Probability.
- Candidate Eligibility.
- Filter Result.
- Rejection Reason.
- Ranking.
- Selected Status.
- Execution Status.

This file depends heavily on candidate-generation and decision logs.

If candidate records are incomplete, report:

`INCOMPLETE_CANDIDATE_EVIDENCE`

Do not invent unexecuted opportunities from trade records.

### CSV 07 — Risk Budget and Capital Utilization

Suggested filename:

`07_risk_budget_utilization.csv`

Purpose: Investigate actual capital and risk-budget utilization.

Suggested fields:

- Timestamp.
- Open Trade Count.
- Available Capacity.
- Instrument.
- Currency Exposure.
- Units.
- Notional Exposure.
- Account Currency Exposure.
- Estimated Risk Exposure.
- MC Directional Consensus.
- Position Allocation.

Distinguish between:

- Nominal trade size.
- Notional exposure.
- Actual margin usage.
- Potential loss based on SL distance.
- Risk amount in account currency.

Do not label nominal trade size as risk amount without a valid risk calculation.

If reliable risk exposure cannot be calculated, flag it explicitly.

### CSV 08 — Data Quality and Evidence Gaps

Suggested filename:

`08_data_quality_and_gaps.csv`

Purpose: Record all data limitations.

Include:

- Missing Data.
- Duplicate Data.
- Timestamp Conflict.
- Invalid Probability.
- Missing Timeframe.
- Incomplete Trade History.
- Missing Candidate History.
- Missing Portfolio Snapshot.
- Missing Price History.
- Timezone Uncertainty.

For each issue, record:

- Affected file.
- Affected time.
- Affected field.
- Scope of impact.
- Whether statistical results are affected.
- Whether the issue can be repaired.
- Repair method or reason it cannot be repaired.

### CSV 09 — Statistical Evidence Summary

Suggested filename:

`09_statistical_evidence_summary.csv`

Purpose: Consolidate analytical results.

Include where supported:

- Sample Count.
- Date Range.
- Probability Distribution.
- Directional Accuracy.
- Brier Score.
- Log Loss.
- Calibration.
- Forward Return.
- Return Distribution.
- Market Regime Breakdown.
- Trade Outcome Breakdown.
- Confidence Interval.

Calculate a metric only when its data and definitions are valid.

Do not silently substitute a different metric when the requested metric cannot be calculated.

---

# 5. Statistical Methodology

## 5.1 Probability Evaluation

MC is a probability system.

Therefore, evaluation must not be limited to whether the predicted direction was correct.

Investigate at least:

1. Brier Score.
2. Log Loss.
3. Probability Calibration.
4. Directional Accuracy.
5. Probability Bucket Performance.
6. Forward Return Distribution.

The key question:

When MC assigns a higher probability to a direction, does the subsequent outcome show corresponding statistical behavior?

For exploratory analysis, probability buckets may include:

- 50%–55%.
- 55%–60%.
- 60%–65%.
- 65%–70%.
- Above 70%.

These are analytical buckets, not approved strategy thresholds.

Do not repeatedly optimize thresholds on the same sample and present the best result as independent validation.

## 5.2 Probability Persistence

Investigate whether MC directional probabilities persist over time.

Measure:

- Duration of consecutive directional agreement.
- Probability changes.
- Direction reversal frequency.
- Regime transition frequency.
- Subsequent performance across different persistence durations.

Distinguish:

- Persistence of probability direction.
- Persistence of price direction.
- Persistence of profitable trades.

These are not equivalent.

## 5.3 Currency Consensus

Currency-strength analysis must not simply count every pair as an independent vote.

Account for:

- Base/quote orientation.
- Repeated currency exposure.
- Correlation between instruments.
- Missing observations.
- Number of valid observations at each timestamp.

JPY is a priority research subject, but the same methodology should also be applied to other currencies.

Do not selectively validate only the currency that currently appears strongest.

## 5.4 Time-Series Validation

All statistical analysis must respect chronological order.

Where sample size permits, separate:

- Discovery Period.
- Validation Period.
- Out-of-Sample Period.

Do not randomly shuffle time-series observations and use an ordinary random train/test split as evidence of live trading performance.

If the historical sample is insufficient for independent validation, state this explicitly.

## 5.5 Statistical Uncertainty

For every important statistical result, report where possible:

- Sample size.
- Time range.
- Mean or median.
- Distribution.
- Confidence interval.
- Missing-data impact.

Do not report only a single attractive percentage.

Statistical significance must not automatically be interpreted as practical trading value.

---

# 6. Phase 3 — Parallel Demo Operation

**Priority:** P0  
**Execution:** In parallel with Phases 1 and 2

The audit and Demo data collection must proceed simultaneously.

Do not wait until the entire audit is finished before collecting new Demo evidence.

## 6.1 Demo Baseline

Preserve the current Demo baseline.

Record:

- Current code version.
- Current strategy configuration.
- Current MC data.
- Current trade decisions.
- Actual executions.
- Current positions and risk exposure.
- Actual trade outcomes.

Do not change baseline strategy behavior for the purpose of the audit.

## 6.2 Shadow Data Collection

Where technically possible, record the following without changing trade decisions:

- Original MC probabilities.
- Currency consensus.
- Market regime.
- Trade candidates.
- Candidate ranking.
- Rejection reasons.
- Actual trades.
- Capital utilization.
- Trade lifecycle.

Shadow records must remain separate from actual execution records.

`SHADOW_RESULT` must never be represented as an actual executed trade.

## 6.3 Demo Comparison

Subsequently compare:

| Dimension | Baseline | Shadow / Candidate |
|---|---|---|
| Candidate Count | Actual baseline | Shadow proposal |
| Selected Trades | Actual baseline | Shadow proposal |
| MC Alignment | Actual baseline | Shadow proposal |
| Trade Distribution | Actual baseline | Shadow proposal |
| Currency Exposure | Actual baseline | Shadow proposal |
| Risk Utilization | Actual baseline | Shadow proposal |
| Realized P/L | Actual executions | Only actual executions |
| Counterfactual P/L | Not applicable | Separately estimated and labelled |

If a shadow proposal was not actually executed, its theoretical return must not be reported as realized profit.

## 6.4 Demo Acceptance

Ensure that:

- Baseline operation is not contaminated by shadow logic.
- Shadow data is distinguishable from actual execution data.
- Records can be matched by timestamp.
- Every shadow decision has an explicit reason.
- No unauthorized order submission occurs.

---

# 7. Phase 4 — Independent Branch Preparation

**Priority:** P1  
**Prerequisite:** Phase 1 acceptance and initial audit findings

After Phase 1 is completed, prepare an independent development branch based on the verified production baseline.

Record:

- Base Branch.
- Base Commit.
- Working Branch.
- Changed Files.
- Configuration Changes.
- New Shadow Components.
- Test Results.

## 7.1 Development Objective

The independent branch will investigate:

**Can better utilization of MC probabilities, currency consensus, and market-regime information improve opportunity selection and capital allocation?**

Potential research directions include:

- MC Directional Clarity.
- Multi-Pair Currency Consensus.
- Probability Persistence.
- Market Regime Classification.
- Opportunity Ranking.
- Capital Allocation Priority.
- Wide-Range / Choppy Market Detection.

These are research directions, not approved strategy definitions.

## 7.2 Live Shadow Boundary

The independent branch may be prepared for observation in the Live environment, subject to separate technical and operational approval.

It must remain under the following restrictions:

- No new order submission.
- No modification of existing positions.
- No SL / TP modification.
- No change to existing strategy decisions.
- No change to existing production execution permissions.
- No interference with the original production runner.

Live Shadow is intended to validate:

- Real-time data integrity.
- Correct MC consumption.
- Stability of shadow assessments.
- Explainability of decision outputs.
- Matching between shadow decisions and actual trades.

**Live Shadow is not Live Trading Authorization.**

Any real trading behavior requires separate, explicit Owner approval.

---

# 8. Evidence Classification

All reports must distinguish the following evidence levels.

| Level | Classification | Meaning |
|---|---|---|
| E0 | Missing | Insufficient evidence |
| E1 | Observed Fact | Directly confirmed by actual files or logs |
| E2 | Statistical Evidence | Statistical association or pattern supported by data |
| E3 | Out-of-Sample Evidence | Independently validated using a separate chronological sample |
| E4 | Strategy Impact Evidence | Evidence that a strategy behavior change produced actual improvement |

Important:

E2 does not automatically qualify as E3.

E3 does not automatically qualify as E4.

The absence of E4 evidence does not invalidate useful information already established at E1 or E2.

Likewise, an observed market pattern does not prove that a particular strategy modification will necessarily improve performance.

---

# 9. Strict Data and Analysis Rules

The following rules are mandatory.

## 9.1 No Lookahead Bias

A trading decision may only use information available at the time.

MC snapshots generated after trade entry must not be used to explain the original entry decision.

## 9.2 No False Historical Reconstruction

Recalculated historical MC must remain separate from actual historical MC.

Never mix the two in the same statistical population without explicit labelling and justification.

## 9.3 No Duplicate Inflation

Identify duplicate snapshots, duplicate instruments, and duplicate trade records.

Do not inflate consensus by counting duplicate observations.

## 9.4 No Selective Sampling

Do not select only successful instruments, periods, or trades.

Report the complete available sample and all exclusion reasons.

## 9.5 No Unsupported Opportunity Claims

Without complete candidate history, do not claim that an unexecuted opportunity definitely existed at a particular time.

## 9.6 No Confusion Between Probability and Profit

Probability advantage does not guarantee that every trade will be profitable.

Analyze separately:

- Probability quality.
- Price behavior.
- Strategy selection.
- Trading costs.
- Realized P/L.

## 9.7 No Unapproved Strategy Changes

Phases 1 and 2 are audit activities.

They must not change production trading behavior.

All strategy modifications require separate review and approval.

---

# 10. Acceptance Criteria

## Phase 1 — Runtime Fact Finding

- [ ] Actual production runtime version confirmed.
- [ ] Actual MC data sources confirmed.
- [ ] Available multi-day historical MC data collected.
- [ ] Earliest recoverable MC timestamp identified.
- [ ] Historical data gaps identified.
- [ ] Target-period trades reconstructed.
- [ ] Wide-range two-sided stop-loss events investigated.
- [ ] Historical development of JPY strength investigated.
- [ ] Strategy MC consumption chain inspected.
- [ ] Candidate and rejection-reason logging coverage inspected.
- [ ] Data dictionary produced.
- [ ] Evidence register produced.
- [ ] Data package and SHA256 manifest produced.
- [ ] No production code or trading behavior modified.

## Phase 2 — Offline Audit

- [ ] Offline script is based on actual data structures.
- [ ] Analysis is reproducible.
- [ ] Original data remains unchanged.
- [ ] No future-data leakage in timestamp matching.
- [ ] Duplicate records are handled.
- [ ] Market-regime timeline produced.
- [ ] JPY consensus timeline produced.
- [ ] Actual trades matched with MC data.
- [ ] Wide-range event independently analyzed.
- [ ] Non-JPY trade selection investigated.
- [ ] Capital utilization analyzed, or data limitations explicitly documented.
- [ ] All core analyses have CSV outputs.
- [ ] Statistical results include sample counts and date ranges.
- [ ] Facts, associations, and hypotheses are clearly separated.

## Phase 3 — Demo

- [ ] Baseline Demo remains independent.
- [ ] Shadow records do not affect trading decisions.
- [ ] Shadow and actual executions are distinguishable.
- [ ] Timestamp matching is possible.
- [ ] MC and candidate opportunities can be recorded.
- [ ] Capital and risk exposure can be recorded.
- [ ] No unauthorized order submission.

## Phase 4 — Independent Branch

- [ ] Exact baseline commit recorded.
- [ ] Independent branch created.
- [ ] Scope of changes reviewed.
- [ ] Shadow behavior fully recorded.
- [ ] Original production runner unaffected.
- [ ] No unauthorized live order submission.

---

# 11. Instructions for Any Assigned LLM or Technical Agent

This specification is tool-agnostic.

The assigned agent may be Claude, DeepSeek, Microsoft Copilot, TRAE, or another authorized development assistant.

The agent must first declare:

- Which repository and files it can access.
- Whether it can access the server.
- Whether it can inspect runtime logs.
- Whether it can inspect historical MC data.
- Whether it can execute read-only commands.
- Whether it can export data packages.

Never claim to have inspected inaccessible resources.

Follow this execution order.

### Step 1 — Read-Only Inspection

Inspect the actual runtime environment and historical data.

Do not write code first.

Do not begin with strategy improvement proposals.

Do not modify configurations.

### Step 2 — Data Inventory

Identify actual data files, fields, time ranges, missing records, and duplicates.

Prioritize exporting original data.

### Step 3 — Trade Reconstruction

Reconstruct LONG and SHORT stop-loss events during the wide-range period.

Reconstruct actual trades during the development of JPY strength.

Investigate the selection process behind non-JPY trades.

### Step 4 — Evidence Report

Produce factual reports.

Every conclusion must identify its evidence source.

If a fact cannot be confirmed, use:

`NOT VERIFIED`

If the required data is unavailable, use:

`DATA NOT AVAILABLE`

### Step 5 — Audit Package

Organize all source data and reports.

Generate SHA256 checksums.

Ensure that the package can be downloaded and analyzed offline.

### Step 6 — Parallel Demo

Continue baseline Demo operation and Shadow data collection.

Do not wait for the entire offline audit to finish before collecting new runtime evidence.

### Step 7 — Stop and Submit

Submit all Phase 1 deliverables for review.

Do not independently proceed to production strategy modification.

---

# 12. Final Expected Outcome

The project must ultimately answer:

1. When did the wide-range market conditions first appear, and how long did they last?
2. Did MC indicate weak or unclear directional advantage at the time?
3. Could MC identify this two-sided risk environment?
4. When did JPY strength first become observable?
5. Was JPY strength persistent and consistent across multiple pairs?
6. Did the strategy identify and use the common JPY direction?
7. Why did the strategy continue opening numerous non-JPY trades?
8. Did those non-JPY trades have independent statistical advantages?
9. Was capital occupied by opportunities with unclear directional advantage?
10. Can MC help the strategy select major market opportunities more effectively?
11. Which findings have statistical evidence?
12. Which questions still require more data or Demo validation?

The final objective is not to prove that MC is always correct.

The objective is to build a trading system that can use probability information, identify market conditions, select opportunities, and allocate its limited risk budget more effectively.

**We do not aim to participate in every market movement.**

**We aim to participate only in market conditions that we can identify, evaluate, and support with measurable statistical evidence.**

---

**Document Status:** PROPOSED — Pending Owner Approval  
**Implementation Authorization:** NOT GRANTED  
**Production Strategy Change:** NOT AUTHORIZED  
**Live Order Submission:** NOT AUTHORIZED