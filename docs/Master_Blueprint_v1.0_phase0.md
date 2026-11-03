
好。这一步我们要特别克制：Phase 0 只负责审查、确认和冻结架构，不写代码，不修 Bug，也不提前启动 Phase 1。

我建议让 IDE 以刚才的 `MC + Fibonacci Shadow Intelligence System — Master Blueprint v1.0` 为审查对象，结合真实代码和 JSON 数据，找出 Blueprint 与实际项目之间的差距。

这次最重要的交付物不是代码，而是一份可以据此批准 Phase 1 的 Architecture Review Report。

下面这份 Prompt 可以直接交给 IDE。

# PHASE 0 — ARCHITECTURE & DATA CONTRACT REVIEW

**Project:** `fx_monte_carlo`
**Related Fib Generator:** `ai_training_cnn/fib_mc_segment.py`
**Master Specification:** `MC_FIB_SHADOW_SYSTEM_BLUEPRINT.md`
**Phase:** 0 — Architecture & Data Contract Review
**Mode:** READ-ONLY / FORENSIC REVIEW
**Objective:** Validate the proposed system architecture against the actual codebase and establish an implementation-ready data contract before Phase 1.

---

# 1. MISSION

Conduct a comprehensive architecture and data contract review before any implementation begins.

The project has an approved architectural direction:

- Monte Carlo remains the primary statistical simulation engine.
- Fibonacci segmentation is a descriptive price-location layer.
- Shadow Observation records real market outcomes without influencing trading.
- Statistical Validation evaluates whether the collected observations have measurable value.
- No new component is permitted to influence live trading decisions during these phases.

The Master Blueprint defines the intended future architecture.

Your task is to determine whether that architecture is:

1. Consistent with the existing codebase.
2. Technically feasible.
3. Internally consistent.
4. Backward-compatible where required.
5. Sufficiently precise to support phased implementation.
6. Free of unresolved critical interface ambiguities.

**Do not implement anything in this phase.**

The result must be an evidence-based architecture review, not a generic design proposal.

---

# 2. STRICT SCOPE

Inspect only the components directly relevant to this system.

Primary project:

`fx_monte_carlo`

Explicitly identified Fib generator:

`ai_training_cnn/fib_mc_segment.py`

Relevant known files may include:

- `fx_monte_carlo.py`
- `mc_data.yml`
- `fib_mc_segment.py` or its explicitly identified copy
- `build_api.py`
- `get_mc_data.py`
- `mc_results/`
- Relevant test files
- Directly related shell scripts and scheduler configuration

Do not perform a general audit of `ai_training_cnn`.

Do not inspect or incorporate unrelated trading bots, CNN models, MC loaders, or other projects.

Do not assume that files discovered elsewhere belong to this pipeline.

If a relevant component is missing, report it as MISSING or NOT VERIFIED.

---

# 3. NON-NEGOTIABLE RULES

1. READ ONLY.
2. Do not modify Python source code.
3. Do not modify configuration files.
4. Do not modify JSON output files.
5. Do not create new modules.
6. Do not install packages.
7. Do not change scheduler settings.
8. Do not run a production or Demo trading process.
9. Do not regenerate MC or Fib data.
10. Do not change the Monte Carlo algorithm.
11. Do not implement any proposed remediation.
12. Do not connect Fib to trading decisions.
13. Do not create empty placeholder specifications.
14. Do not fabricate evidence.

You may create one report file:

`PHASE_0_ARCHITECTURE_REVIEW.md`

No other files may be created or modified.

---

# 4. REVIEW A — MASTER BLUEPRINT CONSISTENCY

Read the complete Master Blueprint.

Check every major requirement against the actual implementation.

Classify each requirement as:

- IMPLEMENTED
- PARTIALLY IMPLEMENTED
- NOT IMPLEMENTED
- NOT APPLICABLE
- NOT VERIFIED
- CONTRADICTORY

Create a requirement traceability matrix.

Required columns:

| ID | Blueprint Requirement | Actual Evidence | Status | Gap | Recommendation |
| -- | --------------------- | --------------- | ------ | --- | -------------- |

Review at least these areas:

- Monte Carlo generation
- Pair identity and deduplication
- Batch metadata
- Probability semantics
- Confidence interval semantics
- Fib segmentation
- Boundary conventions
- Invalid data handling
- D1/W1 separation
- Shadow observation identity
- Outcome resolution
- Statistical validation
- API and consumer isolation
- Atomic output
- Reproducibility
- Rollback

Do not mark a requirement IMPLEMENTED merely because a design document mentions it.

Source code and actual artifacts are the evidence.

---

# 5. REVIEW B — MODULE BOUNDARIES

Determine the actual dependency relationships.

Document:

- Which module generates MC results?
- Which module validates MC results?
- Which module performs Fib annotation?
- Which module builds API output?
- Which module reads local MC results?
- Which module could potentially consume Fib fields?
- Which modules are currently independent?
- Which proposed modules do not yet exist?

Produce an actual dependency diagram.

Then produce a proposed target dependency diagram.

The target architecture must enforce:

1. MC Engine does not depend on Fib.
2. Fib depends on validated MC data.
3. Shadow Observation depends on validated MC and Fib outputs.
4. Outcome Resolver depends on stored observations and future market data.
5. Statistical Validator consumes resolved observations.
6. None of these research components modifies live trading decisions.

Identify any circular dependency or accidental coupling.

---

# 6. REVIEW C — DATA CONTRACT DESIGN

This is the most important part of Phase 0.

Define and evaluate the data contracts between all layers.

Do not implement the schemas. Produce proposed schema definitions and explain their compatibility implications.

## 6.1 MC Batch Contract

Determine the required fields for a complete MC batch.

At minimum evaluate:

- `batch_id`
- `schema_version`
- `algorithm_version`
- `generated_utc`
- `source_data_timestamp`
- `timeframe`
- `configuration`
- `configuration_fingerprint`
- `requested_pairs`
- `unique_pairs`
- `successful_pairs`
- `failed_pairs`
- `batch_status`
- `results`

Determine which fields already exist and which are new.

Do not assume a configuration fingerprint must be a particular hashing algorithm. Recommend a deterministic implementation only after inspecting the existing configuration structure.

## 6.2 MC Pair Result Contract

Define the expected pair-level fields.

Evaluate:

- Pair identity
- Timeframe
- Batch identity
- Current price
- p_up
- p_down
- Expected price
- MC interval
- Drift
- Volatility
- VaR/CVaR
- Simulation count
- Result status
- Source lineage

Clarify the semantics of each field.

In particular, distinguish:

- Terminal-price probability
- Path-touch probability
- Terminal-price confidence interval
- Realized future price outcome

These concepts must not be conflated.

## 6.3 Confidence Interval Contract

Investigate the current `range_90` implementation.

Determine:

- How confidence is configured.
- How quantiles are calculated.
- How endpoints are rounded.
- Whether full precision is retained.
- Whether metadata records confidence.
- Whether consumers rely on the existing field name.

Recommend a backward-compatible migration strategy.

Do not change the current field or calculation.

## 6.4 Fib Annotation Contract

Define a proposed Fib annotation schema.

Evaluate:

- Fib algorithm version
- Source MC batch identity
- Source pair identity
- Source timeframe
- Source range
- Fib ratios
- Fib levels
- Zone tag
- Range status
- Position within zone
- Calculation precision

Ensure Fib cannot overwrite MC probability fields.

Ensure descriptive labels cannot be interpreted as trading instructions.

## 6.5 Shadow Observation Contract

Define the minimum viable immutable observation record.

Determine:

- Observation identity
- Source batch identity
- Pair and timeframe
- Observation timestamp
- Current price
- MC probability snapshot
- MC interval snapshot
- Fib snapshot
- Validation status
- Resolution status
- Observation schema version

Clarify which values must be copied into the observation and which can be referenced through immutable source lineage.

Do not leave this ambiguous.

## 6.6 Outcome Record Contract

Define how future realized market data will be attached.

Evaluate:

- Outcome identity
- Observation identity
- Horizon
- Target timestamp
- Actual market timestamp
- Future closing price
- Return
- Direction
- Maximum favourable excursion
- Maximum adverse excursion
- MC range coverage
- Resolution status

Ensure future data cannot alter historical observation values.

---

# 7. REVIEW D — FIVE ARCHITECTURAL DECISIONS

The following five questions must be explicitly resolved or identified as requiring user approval.

Do not make assumptions where evidence is insufficient.

## Decision 1 — API and Consumer Isolation

The previous audit identified that `build_api.py` may scan JSON files containing nested `results`, potentially including Fib JSON.

Determine:

- Which JSON files are currently accepted?
- Can Fib files enter API aggregation?
- How are duplicate timestamps resolved?
- Does filename ordering influence selection?
- Are unknown fields preserved?
- Could Fib fields reach an existing trading consumer?

Recommend one target architecture:

A. Exclude Fib output from existing API ingestion.

B. Keep Fib in a separate research API.

C. Use a versioned and explicitly selected data source.

Evaluate the compatibility and operational consequences of each.

Do not modify API code.

## Decision 2 — D1/W1 Observation Schedule

Determine the actual available market-data timestamps and existing scheduling conventions.

Recommend an observation trigger based on completed market bars, not arbitrary script execution time.

Address:

- D1 completed candle definition.
- W1 completed candle definition.
- Weekend and market closure handling.
- Holidays.
- Missing candles.
- Duplicate execution.
- Different D1/W1 generation timestamps.
- Whether a daily MC snapshot and weekly MC snapshot should be synchronized or independently recorded.

Do not assume the user's local timezone is the market-data timezone.

All internal timestamps must be UTC.

## Decision 3 — Reproducibility

Determine whether the existing system retains sufficient information to reproduce a historical MC run.

Inspect:

- Random seed policy.
- Input price history.
- Input data timestamps.
- Configuration.
- Algorithm version.
- Simulation count.
- Numerical precision.
- External data source dependencies.

Distinguish:

- Configuration reproducibility
- Simulation reproducibility
- Full historical data reproducibility

Recommend the minimum provenance required for each.

Do not change the seed policy.

## Decision 4 — Baseline and Candidate Storage

Compare possible storage strategies:

A. Separate baseline and candidate directories.

B. Versioned files in the existing output directory.

C. Separate research dataset with immutable source references.

Evaluate:

- Backward compatibility
- Consumer isolation
- Storage complexity
- Traceability
- Rollback
- Historical comparison
- Accidental ingestion risk

Recommend one approach with a clear rationale.

The existing baseline output must remain recoverable.

## Decision 5 — `range_90` Compatibility

Determine how the current field is consumed.

Recommend how to support configurable confidence levels without silently changing existing semantics.

Address:

- Existing `range_90` readers.
- New schema version.
- Confidence metadata.
- Migration period.
- Historical JSON compatibility.
- Whether old files require migration or can remain immutable.

Do not rewrite historical files.

---

# 8. REVIEW E — D1/W1 ARCHITECTURAL SEPARATION

Verify that the target design preserves these responsibilities:

| Timeframe | Responsibility                                          |
| --------- | ------------------------------------------------------- |
| D1        | Primary MC and Fib observation                          |
| W1        | Independent longer-term context                         |
| H1        | Not part of this project's current implementation scope |

D1 and W1 must not:

- Share probability values.
- Share Fib ranges.
- Overwrite each other's results.
- Merge into a single synthetic probability.
- Automatically veto each other.

Each observation must preserve its own batch ID and source timestamp.

Recommend a method for comparing D1 and W1 observations without merging their underlying statistical populations.

---

# 9. REVIEW F — SHADOW OBSERVATION DESIGN

Evaluate whether the proposed Shadow Observation lifecycle is sufficiently precise.

Required lifecycle:

```
MC BATCH
   |
   v
VALIDATION
   |
   v
FIB ANNOTATION
   |
   v
OBSERVATION CREATION
   |
   v
WAIT FOR FUTURE DATA
   |
   v
OUTCOME RESOLUTION
   |
   v
STATISTICAL VALIDATION
```

Clarify:

- What makes an observation eligible?
- What makes an observation unique?
- What happens when the same batch is processed twice?
- What happens when a source batch is incomplete?
- What happens when the current price is outside MC range?
- What happens when Fib segmentation is invalid?
- How are pending outcomes tracked?
- How are missing future candles handled?
- Can an outcome be resolved more than once?
- How are corrected historical market data handled?

Recommend an idempotent observation lifecycle.

No observation database or logger should be implemented in Phase 0.

---

# 10. REVIEW G — STATISTICAL METHODOLOGY READINESS

Review whether the proposed Phase 4 validation methodology is statistically sound.

Evaluate:

- Probability calibration
- Brier Score
- Calibration curves
- MC interval coverage
- Fib conditional return distributions
- Sample independence
- Overlapping observation horizons
- Serial correlation
- Pair dependence
- Multiple testing
- Regime dependence
- Out-of-sample testing
- Baseline comparison

Identify methodological weaknesses in the Master Blueprint.

In particular:

1. Do not treat consecutive daily observations as independent samples.
2. Do not confuse p_up with the probability of a profitable trade.
3. Do not interpret MC interval coverage using only terminal prices if the interval definition is terminal-price based.
4. Do not confuse path-touch probabilities with terminal-price interval coverage.
5. Do not claim Fib adds predictive value merely because different zones have different average returns.

Recommend improvements to the research design without implementing statistical models.

---

# 11. REVIEW H — IMPLEMENTATION READINESS

Determine whether Phase 1 can safely begin after Phase 0.

Identify:

- Missing prerequisites.
- Ambiguous data contracts.
- Backward compatibility risks.
- Required tests.
- Required test fixtures.
- Required migration strategy.
- Potential consumer breakage.
- Unresolved user decisions.

Create a Phase 1 readiness checklist.

Classify each item:

- READY
- BLOCKED
- REQUIRES USER DECISION
- REQUIRES FURTHER EVIDENCE

Do not start Phase 1.

---

# 12. REQUIRED DELIVERABLE

Create exactly one file:

`PHASE_0_ARCHITECTURE_REVIEW.md`

The report must contain:

1. Executive Summary
2. Actual System Architecture
3. Proposed Target Architecture
4. Master Blueprint Traceability Matrix
5. Actual Module Dependency Analysis
6. Proposed Module Boundaries
7. MC Batch Data Contract
8. MC Pair Result Data Contract
9. Fib Annotation Data Contract
10. Shadow Observation Data Contract
11. Outcome Record Data Contract
12. API and Consumer Isolation Decision
13. D1/W1 Observation Schedule Recommendation
14. Reproducibility Assessment
15. Baseline/Candidate Storage Recommendation
16. `range_90` Compatibility Strategy
17. Statistical Methodology Review
18. Phase 1 Readiness Checklist
19. Unresolved Decisions
20. Final Phase 0 Verdict

For every major finding include:

- Finding ID
- Severity
- Evidence
- Actual behaviour
- Architectural implication
- Recommendation

Use exact filenames, functions, line numbers, and real JSON examples wherever possible.

Separate:

- Confirmed Facts
- Design Recommendations
- Assumptions
- Unverified Items
- User Decisions Required

---

# 13. FINAL PHASE 0 VERDICT

Choose exactly one:

- APPROVED — READY FOR PHASE 1
- CONDITIONALLY APPROVED — MINOR DECISIONS REQUIRED
- BLOCKED — DATA CONTRACT ISSUES
- BLOCKED — ARCHITECTURAL CONFLICTS
- NOT VERIFIED — INSUFFICIENT EVIDENCE

A CONDITIONAL approval must identify each remaining condition and its owner.

A BLOCKED result must identify the minimum work required to unblock Phase 1.

Do not give approval merely because the proposed architecture looks reasonable.

The implementation must be feasible against the actual codebase.

---

# 14. FINAL INSTRUCTION

This is an architecture review, not an implementation task.

Do not fix findings.

Do not create code.

Do not modify existing documents.

Do not begin Phase 1.

The objective is to establish a precise, evidence-backed contract so that subsequent implementation phases can proceed without architectural guesswork.

**Deliverable: `PHASE_0_ARCHITECTURE_REVIEW.md` only.**

At completion, provide a concise terminal summary containing:

- Review status
- Number of confirmed findings
- Number of unresolved decisions
- Phase 1 readiness
- Exact report path

Stop after the report is produced.

## 我特别强调的三个设计要求

1. 不让 IDE 自己决定所有架构问题。 对 API 隔离、D1/W1 时间策略、Baseline 存储方式等问题，必须提供证据和推荐方案；缺乏证据时明确标记需要我们决定。
2. 数据契约先于代码。 每个模块必须清楚知道输入、输出、状态和数据来源。
3. Phase 0 不得顺手修复问题。 即使发现明显 Bug，也只登记，不修改。否则我们会失去干净的审计基线。

等 IDE 生成 `PHASE_0_ARCHITECTURE_REVIEW.md`，把报告贴过来。我们先审查它的结论，再冻结数据契约，最后才正式进入 Phase 1。

Phase 0 完成后准备 Phase 1 Prompt
