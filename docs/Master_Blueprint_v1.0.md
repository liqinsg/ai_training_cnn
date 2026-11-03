
这份文件是整个 MC + Fib Shadow Intelligence System 的总设计规范。后续 Phase 1、2、3 的开发 Prompt 都必须遵守它，避免每个阶段各自做局部优化，最后接口无法衔接。

原则：不推翻已经运行的 Monte Carlo 基线，不急着优化预测能力，先建立可信、可追溯、可验证的数据系统。

# MC + Fibonacci Shadow Intelligence System

# Master System Blueprint v1.0

**Project:** `fx_monte_carlo`
**Related Fib Generator:** `ai_training_cnn/fib_mc_segment.py`
**Primary Output:** `fx_monte_carlo/mc_results`
**Document Type:** Master Architecture & Development Specification
**Status:** Proposed — Pending Implementation
**Version:** 1.0
**Date:** 2026-11-03

---

# 1. Executive Vision

## 1.1 Mission

Build a reliable, reproducible, statistically auditable Monte Carlo and Fibonacci Shadow Observation system for Forex markets.

The system must evolve through controlled development phases:

1. Monte Carlo Data Integrity
2. Fibonacci Segmentation Integrity
3. Shadow Observation
4. Statistical Validation
5. Decision Support Evaluation

The objective is not to produce more trading signals.

The objective is to determine, using real market observations and statistical evidence, whether Monte Carlo probability distributions and Fibonacci-based price-location segmentation provide useful information about future market behaviour.

## 1.2 Fundamental Philosophy

The system follows five principles:

**Principle A — Statistical Thinking**

Financial markets cannot be predicted with certainty. Probability distributions, uncertainty measurements, and repeated observations are more appropriate than deterministic claims.

**Principle B — Preserve the Baseline**

The existing Monte Carlo simulation methodology is the baseline. Do not modify its core mathematical assumptions merely to make outputs look better.

**Principle C — Evidence Before Optimization**

Do not optimize parameters based on a small number of observations. Accumulate sufficient data and evaluate out-of-sample performance.

**Principle D — Shadow Before Trading**

All new Fib functionality remains outside the trading decision and execution path.

**Principle E — Reproducibility and Auditability**

Every observation must be traceable to its source data, configuration, generation time, and algorithm version.

---

# 2. System Architecture

## 2.1 Logical Architecture

The system consists of six logical layers.

```
                  MARKET DATA
                       |
                       v
            MONTE CARLO ENGINE
                       |
                       v
             MC DATA VALIDATION
                       |
                       v
              MC BATCH OUTPUT
                       |
                       v
          FIBONACCI SEGMENTATION
                       |
                       v
             SHADOW OBSERVATION
                       |
                       v
           OUTCOME RESOLUTION
                       |
                       v
          STATISTICAL VALIDATION
                       |
                       v
          DECISION SUPPORT REVIEW
```

The layers must remain logically independent.

A downstream component must not silently modify upstream results.

## 2.2 Module Responsibilities

| Module                | Responsibility                           | Must Not                            |
| --------------------- | ---------------------------------------- | ----------------------------------- |
| MC Engine             | Generate Monte Carlo distributions       | Generate Fib trading signals        |
| MC Validator          | Validate data completeness and integrity | Modify simulation results           |
| Fib Segmenter         | Calculate price-location zones           | Modify MC probabilities             |
| Shadow Observer       | Record point-in-time observations        | Influence live trading              |
| Outcome Resolver      | Attach future realized outcomes          | Use future data at observation time |
| Statistical Validator | Evaluate observed performance            | Automatically optimize parameters   |

## 2.3 Existing Project Mapping

Known existing components:

| Existing Component                    | Intended Responsibility                |
| ------------------------------------- | -------------------------------------- |
| `fx_monte_carlo.py`                 | MC simulation and batch generation     |
| `mc_data.yml`                       | Central MC configuration               |
| `mc_results/`                       | MC and Fib JSON artifacts              |
| `ai_training_cnn/fib_mc_segment.py` | Existing Fib annotation implementation |
| `build_api.py`                      | Potential API ingestion path           |
| `get_mc_data.py`                    | Existing local MC data reader          |

The exact import relationships, runtime invocation, and external consumers must be verified before implementation.

Do not assume that a file is part of the live trading path merely because it exists.

---

# 3. Global Data Contract

All subsequent phases must follow a consistent data identity and lineage model.

## 3.1 Core Identity

Every MC batch must have:

- `batch_id`
- `schema_version`
- `algorithm_version`
- `timeframe`
- `generated_utc`
- `source_data_timestamp`
- `configuration_fingerprint`

Every pair result must have:

- `pair`
- `timeframe`
- `batch_id`
- `current_price`
- `p_up`
- `p_down`
- MC interval information
- calculation metadata
- validation status

Every Fib annotation must retain:

- Original MC result identity
- Source MC batch identity
- Fib algorithm version
- Fib levels
- Fib zone
- Range status

Every Shadow Observation must have a unique immutable `observation_id`.

## 3.2 Currency Pair Identity

Pair identity must be normalized before simulation.

Example:

```
EURUSD
GBPUSD
USDJPY
EURJPY
```

Requirements:

1. Remove accidental duplicate entries.
2. Preserve deterministic ordering.
3. Do not silently overwrite repeated results.
4. Record requested, unique, successful, and failed pair counts separately.
5. Preserve the original configured pair list in audit metadata when useful.

Required batch accounting:

```
{
  "requested_pairs": 35,
  "unique_pairs": 29,
  "successful_pairs": 29,
  "failed_pairs": 0
}
```

These numbers are illustrative. Actual counts must come from execution.

## 3.3 Timeframe Identity

Supported primary timeframes:

- D — Daily
- W — Weekly

D and W are separate statistical populations.

Do not merge their:

- MC probabilities
- MC intervals
- Fib ranges
- Observation horizons
- Outcome records

Each must retain its own source timestamp.

## 3.4 Timestamp Rules

Use UTC internally.

Each dataset must distinguish:

- `generated_utc`: when the MC result was generated.
- `source_data_timestamp`: timestamp of the last market data point used.
- `observation_utc`: when the shadow snapshot was recorded.
- `resolved_utc`: when the future outcome was calculated.

File modification time must never substitute for source or generation timestamps.

---

# 4. Monte Carlo Data Integrity Specification

## 4.1 Baseline Preservation

The current Student-t Monte Carlo methodology is the baseline.

Current known configuration:

- Simulations: 5,000
- Confidence: 0.90
- Student-t degrees of freedom: 5
- Daily lookback: 90
- Weekly lookback: 104
- Forecast horizon: 5

These values are recorded as the current baseline, not permanent mandatory values.

Do not change them during Phase 1 unless a separate, explicitly approved defect correction requires it.

## 4.2 Required Validations

Each pair result must be checked for:

- Valid pair identity
- Valid timeframe
- Valid current price
- Finite probability values
- Probability bounds
- Probability consistency
- Valid interval endpoints
- Strictly increasing MC interval
- Finite expected price
- Valid simulation count
- Valid source timestamp

Probability checks:

[
0 \leq p\_{up} \leq 100
]

[
0 \leq p\_{down} \leq 100
]

[
p\_{up}+p\_{down}\approx100
]

The acceptable numerical tolerance must be documented.

Important: these probabilities describe the simulated terminal-price distribution. They are not automatically calibrated real-world probabilities or trade win rates.

## 4.3 Confidence Interval Semantics

The interval field must accurately describe its configured confidence.

A fixed field name such as `range_90` must not silently represent another confidence level.

The output must record:

- Confidence level
- Lower quantile
- Upper quantile
- Interval calculation method
- Endpoint precision

The existing `range_90` schema may be preserved for backward compatibility during migration.

Any schema change must be versioned.

## 4.4 Batch Failure Isolation

A failure in one currency pair must not silently corrupt other results.

The batch must distinguish:

- Successful pairs
- Failed pairs
- Invalid results
- Missing market data

A batch may be marked PARTIAL rather than COMPLETE.

Consumers must be able to distinguish a valid complete batch from a partial batch.

## 4.5 Reproducibility

Record sufficient information to identify the simulation configuration:

- Simulation count
- Distribution family
- Degrees of freedom
- Lookback
- Forecast horizon
- Confidence
- Random seed policy
- Algorithm version
- Source data identity

Do not claim deterministic reproducibility if the historical market input data cannot be reconstructed.

---

# 5. Fibonacci Segmentation Specification

## 5.1 Role of Fibonacci

Fib is a descriptive price-location segmentation layer applied to the MC interval.

It does not generate an independent market direction.

It does not modify:

- `p_up`
- `p_down`
- MC expected price
- MC range
- Simulation parameters

## 5.2 Standard Ratios

The initial ratio set is:

```
0.000
0.236
0.382
0.500
0.618
0.786
1.000
```

For a valid interval:

[
L(r)=MC\_{low}+r(MC\_{high}-MC\_{low})
]

This creates six zones:

| Zone | Ratio Interval | Descriptive Label |
| ---- | -------------- | ----------------- |
| F0   | 0.000–0.236   | Deep Discount     |
| F236 | 0.236–0.382   | Discount          |
| F382 | 0.382–0.500   | Below Equilibrium |
| F5   | 0.500–0.618   | Above Equilibrium |
| F618 | 0.618–0.786   | Premium           |
| F786 | 0.786–1.000   | Deep Premium      |

These labels are descriptive names only.

They must not imply that a price is objectively cheap, expensive, supported, or resistant.

## 5.3 Boundary Convention

Adopt a documented half-open convention:

- Lower boundary inclusive.
- Upper boundary exclusive.
- Final zone includes the global upper boundary.

Formally:

[
Z_i=[r_i,r\_{i+1})
]

For the final zone:

[
Z\_{last}=[r\_{last},1]
]

Every valid in-range price must map to exactly one zone.

## 5.4 Range Status

Every Fib observation must have an explicit range status.

Allowed values:

```
BELOW_RANGE
WITHIN_RANGE
ABOVE_RANGE
INVALID_RANGE
MISSING_DATA
```

Rules:

- BELOW_RANGE: current price is below the MC lower bound.
- WITHIN_RANGE: current price is inside the valid MC interval.
- ABOVE_RANGE: current price is above the MC upper bound.
- INVALID_RANGE: interval is malformed, non-finite, reversed, or has zero width.
- MISSING_DATA: required source data is absent.

Outside-range prices must not be assigned to F0 or F786.

Invalid data must not be assigned to any internal zone.

## 5.5 Action Label Policy

The following labels are prohibited as operational outputs:

- BUY_ZONE
- SELL_ZONE
- BUY_LIMIT
- SELL_LIMIT
- REVERSAL_WATCH_LONG
- REVERSAL_WATCH_SHORT

Fib output must remain descriptive.

Any future decision-support interpretation requires separate statistical validation and explicit approval.

---

# 6. Shadow Observation Engine

## 6.1 Objective

The Shadow Observation Engine records the state of the market and its MC/Fib measurements at a specific point in time.

It must not participate in live trading decisions.

## 6.2 Observation Lifecycle

```
MC BATCH CREATED
       |
       v
MC VALIDATED
       |
       v
FIB ANNOTATED
       |
       v
OBSERVATION CREATED
       |
       v
WAIT FOR FUTURE DATA
       |
       v
OUTCOME RESOLUTION
       |
       v
STATISTICAL ANALYSIS
```

Each stage must have a traceable status.

## 6.3 Observation Immutability

Once created, an observation is an immutable historical snapshot.

Future outcomes may be attached as separate records.

Do not rewrite historical MC probabilities or Fib zones using future information.

## 6.4 Observation Dimensions

Minimum dimensions:

- Pair
- Timeframe
- Observation timestamp
- MC batch identity
- Current price
- MC interval
- MC probability
- Fib zone
- Range status
- Source lineage
- Algorithm versions

## 6.5 Observation Frequency

The initial system should use a clearly defined observation policy.

Do not create uncontrolled repeated observations every time a script happens to run.

Define:

- Daily observation schedule
- Weekly observation schedule
- Duplicate detection
- Re-run behaviour
- Missing batch behaviour

The same source batch and pair should not produce accidental duplicate observations.

---

# 7. Outcome Resolution Engine

## 7.1 Purpose

The Outcome Resolver measures what actually happened after an observation.

It must not use future information when constructing the original observation.

## 7.2 Initial Horizons

For D:

- 1 trading day
- 3 trading days
- 5 trading days

For W:

- 1 completed week
- 3 completed weeks
- 5 completed weeks

These are initial research horizons and must be configurable without changing historical observation definitions.

## 7.3 Required Outcomes

For each horizon, record:

- Future closing price
- Absolute price change
- Percentage return
- Direction
- Maximum favourable excursion
- Maximum adverse excursion
- Whether price remained within the original MC interval
- Whether price crossed either MC boundary

For currency pairs, returns should be normalized consistently.

Do not compare raw pip values across pairs without accounting for pip conventions and price scales.

## 7.4 Incomplete Outcomes

If required future market data is unavailable:

- Mark outcome PENDING or UNAVAILABLE.
- Do not substitute an invented value.
- Do not treat an incomplete outcome as a zero return.
- Preserve the reason for non-resolution.

---

# 8. Statistical Validation Framework

This is the core research stage.

The purpose is to determine whether the observed data supports any meaningful conclusion.

## 8.1 MC Probability Calibration

Evaluate whether predicted probabilities correspond to realized frequencies.

Suggested metrics:

- Brier Score
- Calibration Curve
- Reliability Diagram
- Log Loss where appropriate
- Probability bucket analysis

Do not confuse terminal-price probability with directional trade success.

## 8.2 MC Range Coverage

Measure how frequently future realized prices fall within the original simulated interval.

Evaluate separately by:

- Timeframe
- Currency pair
- Confidence level
- Market volatility regime
- Historical period

Compare observed coverage against nominal confidence.

A nominal 90% interval should not be assumed to achieve 90% empirical coverage.

## 8.3 Fib Zone Behaviour

For each zone, measure:

- Sample count
- Mean future return
- Median future return
- Return distribution
- Positive-return frequency
- Negative-return frequency
- Volatility
- Maximum favourable excursion
- Maximum adverse excursion
- Confidence intervals

Do not rank zones solely by average return.

## 8.4 Baseline Comparison

At minimum, compare:

1. MC-only observations.
2. MC + Fib observations.
3. Simple unconditional market baseline.

This helps establish whether Fib adds information beyond the underlying MC measurements.

## 8.5 Statistical Robustness

Validation must address:

- Sample size
- Overlapping observation windows
- Serial correlation
- Currency-pair dependence
- Multiple hypothesis testing
- Market regime changes
- Out-of-sample validation
- Parameter sensitivity

Use time-ordered validation rather than random shuffling of observations.

Do not claim predictive improvement from an in-sample result alone.

## 8.6 Minimum Evidence Policy

Do not establish arbitrary sample thresholds as proof of validity.

For each reported result, provide:

- Actual sample count
- Effective independent sample considerations
- Uncertainty interval
- Period covered
- Number of currency pairs
- Relevant exclusions

If evidence is insufficient, report INCONCLUSIVE.

---

# 9. Baseline and Candidate Architecture

## 9.1 Two-Track Principle

Maintain two distinguishable data paths.

**Baseline**

Represents the existing MC implementation and its established behaviour.

**Candidate**

Represents the improved implementation with validated data integrity and Fib annotations.

The Candidate must not silently replace the Baseline.

## 9.2 Comparison Requirements

For every implementation change, compare:

- Pair coverage
- Simulation count
- Current prices
- Probability values
- MC interval values
- Source timestamps
- Fib levels
- Fib zones
- Invalid data counts
- Output completeness

If the underlying MC calculation is unchanged, any unexpected change in MC values must be investigated.

## 9.3 Rollback

Every phase must define:

- Files changed
- Schema changes
- Backward compatibility impact
- Rollback method
- Recovery procedure

Original source artifacts must remain recoverable.

---

# 10. API and Consumer Isolation

The MC/Fib research system must not accidentally change existing consumers.

Before changing shared output formats:

1. Identify all direct consumers.
2. Identify filename patterns they accept.
3. Identify whether they read unknown JSON fields.
4. Identify whether they choose latest records by timestamp or filename.
5. Identify whether Fib files can enter existing API datasets.
6. Identify whether any trading process reads these fields.

Do not introduce Fib fields into trading decisions.

If necessary, create a dedicated Shadow output directory or a versioned research dataset.

No production consumer should receive an unexpected schema change.

---

# 11. Operational Safety

All batch processes should follow a consistent operational pattern:

1. Load configuration.
2. Validate configuration.
3. Identify input data.
4. Execute calculations.
5. Validate results.
6. Write temporary output.
7. Verify written output.
8. Atomically publish completed output.
9. Record execution metadata.
10. Report success, partial success, or failure.

No incomplete result should be presented as a successful complete batch.

No silent fallback should conceal an invalid source.

No stale output should be mistaken for a new result.

---

# 12. Development Roadmap and Phase Gates

## Phase 0 — Architecture and Contract

Deliverables:

- Approved architecture.
- Data schema definitions.
- Module boundaries.
- Status and error definitions.
- Compatibility assessment.
- Test and acceptance matrix.

Acceptance:

- All required data objects are defined.
- All module responsibilities are clear.
- No unresolved critical interface ambiguity.
- No source code changes required in this phase.

## Phase 1 — Monte Carlo Data Integrity

Deliverables:

- Pair deduplication.
- Accurate pair accounting.
- Input and output validation.
- Confidence metadata.
- Batch completeness status.
- Atomic output verification.
- Regression tests.

Acceptance:

- No duplicate pair overwrite.
- Accurate success/failure counts.
- Invalid numerical data is detected.
- Existing baseline simulation logic is preserved.
- Historical output remains readable.
- Baseline/candidate comparison passes.

## Phase 2 — Fib Segmentation Integrity

Deliverables:

- Validated Fib calculation.
- Explicit range status.
- Documented boundary convention.
- Removal of operational action labels.
- Source lineage.
- Atomic output.
- Mathematical and edge-case tests.

Acceptance:

- Every valid in-range price maps to exactly one zone.
- Outside-range values have no internal zone.
- Invalid data is not silently classified.
- Original MC data is preserved.
- D/W remain independent.
- No trading logic is affected.

## Phase 3 — Shadow Observation

Deliverables:

- Observation identity.
- Immutable observation records.
- Duplicate prevention.
- D/W scheduling policy.
- Outcome resolution.
- Pending and unavailable status.
- Historical data integrity.

Acceptance:

- No look-ahead bias.
- Re-running an existing batch does not create accidental duplicate observations.
- Historical observations remain immutable.
- Outcome records can be traced to the original observation.
- No live trading integration.

## Phase 4 — Statistical Validation

Deliverables:

- MC probability calibration.
- MC interval coverage.
- Fib zone conditional statistics.
- Baseline comparisons.
- Out-of-sample analysis.
- Statistical limitations report.

Acceptance:

- Sample counts and uncertainty are disclosed.
- No unsupported predictive claims.
- Time leakage and overlapping samples are addressed.
- Inconclusive results are allowed.
- Any claimed improvement is supported by out-of-sample evidence.

## Phase 5 — Decision Support Evaluation

Deliverables:

- Research findings.
- Utility assessment.
- Risk assessment.
- Integration proposal, if justified.

Acceptance:

- No automatic trading enablement.
- No automatic parameter optimization.
- No changes to the existing trading architecture without separate approval.
- A negative or inconclusive result is an acceptable outcome.

---

# 13. Global Testing Requirements

Every implementation phase must include:

## Unit Tests

Validate individual calculations and functions.

## Integration Tests

Validate interfaces between modules.

## Regression Tests

Ensure existing baseline behaviour has not changed unexpectedly.

## Data Integrity Tests

Validate actual JSON files and schema compatibility.

## Failure Injection Tests

Test:

- Missing fields
- Duplicate pairs
- Empty input
- Malformed JSON
- NaN and Infinity
- Reversed interval
- Zero-width interval
- Missing timestamps
- Partial pair failures
- Interrupted output writing

## Real Demo / Shadow Validation

Use actual market data and actual generated outputs.

Synthetic tests alone are insufficient for final acceptance.

---

# 14. Non-Negotiable Development Rules

1. Do not rewrite the entire MC engine.
2. Do not change Student-t simulation methodology without a separate research proposal.
3. Do not change MC probabilities merely to align with Fib labels.
4. Do not merge D1 and W1 probabilities.
5. Do not allow Fib to generate independent trading direction.
6. Do not connect Fib to OANDA execution.
7. Do not silently discard failed pairs.
8. Do not silently accept invalid numerical values.
9. Do not use future market data in historical observations.
10. Do not overwrite historical observations.
11. Do not claim statistical validity without sufficient evidence.
12. Do not optimize based on a small sample.
13. Do not modify unrelated projects.
14. Do not expand scope without documenting the reason.
15. Every phase must produce an auditable report.

---

# 15. Required Project Documentation

The following documents should be maintained as the project evolves:

| Document                              | Purpose                                   |
| ------------------------------------- | ----------------------------------------- |
| `MC_FIB_SHADOW_SYSTEM_BLUEPRINT.md` | Master architecture                       |
| `MC_DATA_CONTRACT.md`               | MC schema and data rules                  |
| `FIB_SEGMENTATION_SPEC.md`          | Fib mathematics and status rules          |
| `SHADOW_OBSERVATION_SPEC.md`        | Observation and outcome contract          |
| `STATISTICAL_VALIDATION_SPEC.md`    | Research and validation methodology       |
| `PHASE_1_IMPLEMENTATION_REPORT.md`  | Phase 1 implementation evidence           |
| `PHASE_2_IMPLEMENTATION_REPORT.md`  | Phase 2 implementation evidence           |
| `PHASE_3_IMPLEMENTATION_REPORT.md`  | Phase 3 implementation evidence           |
| `PHASE_4_VALIDATION_REPORT.md`      | Statistical findings                      |
| `CHANGELOG.md`                      | Versioned changes and compatibility notes |

These documents should be created when their corresponding phase is ready. Do not create empty placeholder files.

---

# 16. Final Architectural Position

The system is a research and statistical observation platform.

It is not a trading strategy.

Its primary responsibility is to produce trustworthy, reproducible, and measurable information.

The development sequence is:

```
TRUST THE DATA
      |
      v
TRUST THE SEGMENTATION
      |
      v
OBSERVE THE MARKET
      |
      v
MEASURE THE OUTCOMES
      |
      v
VALIDATE THE STATISTICS
      |
      v
EVALUATE PRACTICAL VALUE
```

No phase may bypass the preceding acceptance gate.

A statistically inconclusive result is better than a misleading positive result.

A system that discovers a method has no measurable value has still produced a useful research outcome.

**Final principle: Build for evidence, not for confirmation of an existing hypothesis.**

## 我的建议：先不要让 IDE 直接开发

Blueprint 已经建立，但有一个关键步骤：先让 IDE 做一次 Blueprint Consistency Review。

因为我们目前仍有几个需要在实施前确认的事项：

1. `build_api.py` 是否应该排除 Fib 文件，还是把 Shadow 数据独立输出？
2. D1/W1 的 Observation Schedule 应该以哪个已完成的市场 K 线为准？
3. MC 的随机种子和输入历史数据，是否足以支持真正的可重复实验？
4. Baseline 与 Candidate 应该采用双目录，还是版本化文件？
5. `range_90` 的向后兼容应该保留多久？

这些问题不必全部现在由我们猜答案。让 IDE 根据实际代码和文件结构逐项核实，然后再冻结 Phase 0。

下一步建议：先做 Phase 0 — Architecture & Data Contract Review，不改任何代码。 通过之后，我们再正式下达 Phase 1 实施任务。
