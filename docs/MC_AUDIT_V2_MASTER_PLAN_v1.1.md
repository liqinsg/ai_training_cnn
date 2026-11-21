# MC Audit V2 — Historical Market Reconstruction and MC Probability Audit

- **Version:** 1.1
- **Date:** 2026-11-22
- **Status:** DRAFT — pending Owner review
- **Scope:** v685 / v685-2 evidence and explicitly identified historical sources
- **Immediate authorization requested:** Phase 0 read-only reconciliation only
**Trading authorization:** NONE

## 1. Purpose and review of the proposed next steps

This revision retains the V1.0 research goals but changes the execution order. It is a supplemental audit, not a rerun of the first audit and not permission to change trading behavior.

The proposed direction is sound: reconcile prior work, find actual historical prices, then define analysis against the available evidence. The following refinements are required before handing work to an IDE Agent:

1. **Phase 0 must reuse and validate the existing audit package.** Do not regenerate equivalent MC and log CSVs merely to create more deliverables. Reproduce an existing export only when needed to verify a discrepancy or its provenance.
2. **The existing `02_market_regime_timeline.csv` is not an H4 market-regime reconstruction.** It is an MC snapshot transition/next-archived-reference-price view with irregular observation intervals. Keep the prior file intact, document its actual meaning, and use distinct names for future MC-transition and OHLC-derived market-regime outputs.
3. **Keep two JPY dates separate:** (a) the earliest archived MC observation indicating JPY strength and (b) the first market-price evidence of JPY strength. The current archive supports the former only from 2026-09-13; it does not establish the latter.
4. **Do not invent historical opportunities.** Candidate ranking or counterfactual replay is allowed only when the historical candidate set, inputs, filters, and capacity can be linked. Otherwise report `NOT_RECONSTRUCTABLE`; analysis of current code is not historical replay.
5. **Treat file provenance and hashes as an evidence chain, not a checksum claim.** Identify which source files are present for independent verification and which hashes refer to external/unavailable files. Use portable relative paths within a delivered package wherever possible.
6. **Cross-index the trade datasets; do not add their row counts.** The daily profile exports and v685 entry logs overlap with exit-audit data. Match by stable trade identity and validate pair, side, and open time; ambiguous links remain ambiguous.
7. **Separate code existence from runtime use.** The prior audit noted discrepancies among local v685 source, config, checked-in service/crontab, and v685-tagged logs. Recheck current worktree and runtime facts, never infer deployed state from repository files alone, and never overwrite a user change.
8. **Do not start a Demo shadow process as part of Phase 0.** Existing shadow files do not establish baseline independence. Starting or changing a process requires a separate approval after an isolation review.

## 2. Carry-forward evidence and known limitations

These are findings in the local audit package and the supplemental CSV review. Phase 0 must verify their files and provenance; do not present them as independently verified against a remote production host.

### 2.1 Existing MC and log package

- The accessible MC archive contains 100 Daily and 16 Weekly bundles, 3,287 result rows total. The Daily archive has a 19-day gap from 2026-09-24 through 2026-10-12; the earliest accessible Daily bundle is 2026-09-13.
- All seven JPY pairs in each of the 100 archived Daily snapshots point toward JPY strength after pair orientation is applied. These are repeated, correlated MC observations—not independent price-outcome tests.
- Available v685-tagged logs contain 457 MC-tagged entry records. 345 have a unique lifecycle link; six focus-window same-second joins are ambiguous. This must not be added to the 577 lifecycle identities as a count of distinct trades.
- Existing candidate/ranking log text is incomplete and lacks a full stable-ID opportunity ledger.
- Existing shadow logs are marked unapplied; Demo baseline/shadow independence and deployed runtime are not verified.
- The previous package’s `02_market_regime_timeline.csv` is not evidence of H4 ranges, swings, or trends. Its irregular next-archived-reference-price observations are not fixed-horizon outcomes.

See the [first audit completion report](MC_LIVE_MARKET_AUDIT_COMPLETION_REPORT.md) and [MC_AUDIT_PACKAGE](MC_AUDIT_PACKAGE/) for details and source references.

### 2.2 Supplemental profile trade exports

The local `daily_results_profile1/` through `daily_results_profile4/` directories contain 16 CSVs:

| Measure | Verified local result |
|---|---:|
| Raw rows | 1,603 |
| Distinct `(account, trade_id)` identities | 577 |
| Duplicate rows beyond those identities | 1,026 |
| Identities repeated in multiple profile directories | 477 |
| Identities present in all four directories | 201 |
| Open-time range | 2026-10-22 through 2026-11-20 |
| Distinct open dates | 26 |
| Unique identities matching exit-audit JSONL | 577 / 577 |

Repeated business fields for the same identity agree in the current files. Directories are overlapping exports, not disjoint samples: in 1,026 rows, the row `profile` differs from the directory suffix. Attribute profile from the row field, not the folder name. If a future source has differing snapshots/statuses, retain every source row and establish version order from an explicit observation/export time; do not silently keep one.

After deduplication by `(account, trade_id)`, the row profile counts are Profile 1: 146; Profile 2: 171; Profile 3: 135; Profile 4: 125. Exit labels are TP=326, SL=154, ACTIVE=97. Direction is 554 short and 23 long; 304 JPY-pair records are short, and the 273 non-JPY records include 250 short and 23 long.

These are trade facts, not an explanation of candidate weighting or market regime. Three SL rows have positive recorded P/L; ACTIVE rows also have populated P/L, pips, and close-time fields. Account currency and those ACTIVE-field semantics are unspecified. Do not equate exit labels to wins/losses or aggregate P/L across accounts. The CSVs contain no MC probability, H4 OHLC, candidate rank/rejection, or sizing-rule version.

## 3. Research questions and evidence discipline

The V2 audit should ultimately answer:

1. What did actual H4 market prices do, including the user-identified wide oscillations, subsequent contraction, and transitions?
2. When did market-price evidence—not merely the MC archive—first show JPY strength, and how did it evolve across JPY pairs?
3. Given the event definition and horizon MC actually predicted, how did saved Daily and Weekly probability outputs compare with later realized outcomes?
4. What evidence explains non-JPY selection: within-pair MC contribution, global currency consensus, candidate filters/ranking, or portfolio capacity?
5. When were the old sizing approach, Fibonacci sizing, and probability sizing actually calculated, enabled, and applied?
6. Which conclusions are observed facts, associations, retrospective reconstructions, counterfactuals, or unresolved?

### Evidence classes

Every dataset and result must be labelled:

- `ACTUAL_ARCHIVED`: MC output saved at the time.
- `ACTUAL_MARKET`: historical price/OHLC observations.
- `ACTUAL_TRADE`: order, fill, position, or lifecycle evidence.
- `ACTUAL_RUNTIME`: verified process, code version, and effective configuration.
- `RETROSPECTIVE`: output recomputed after the event; never represented as saved historical MC.
- `COUNTERFACTUAL`: hypothetical ranking, weight, or sizing scenario.
- `SHADOW`: observation computed without execution.

Do not treat overlapping currency pairs, repeated snapshots, or repeated exports as independent samples. Distinguish:

- observed market prices from market-regime labels;
- MC forecast probability from strategy BUY/SELL and sizing rules;
- calculation from selection, authorization, order submission, fill, and application;
- SL/TP exit labels from actual P/L signs;
- market evidence from user-provided observations that still need price-based review.

## 4. Phase 0 — Reconcile prior work and inventory missing evidence

**Priority:** P0
**Mode:** Read-only
**This is the only immediately actionable phase in this specification.** Later phases require data review and Owner approval.

### 4.1 Goals

1. Verify the prior package’s files, definitions, counts, generator, and manifest against the files actually present.
2. Inventory available OHLC/backtest sources, especially H4, and determine their time coverage and provenance.
3. Reconcile trade CSVs, exit-audit records, and MC-tagged entry logs without counting overlapping records as new trades.
4. Locate evidence for MC output semantics and sizing-rule history.
5. Report runtime/Demo facts only where directly verifiable; explicitly identify inaccessible facts.
6. State which V2 studies are feasible, blocked, or need an Owner decision.

### 4.2 Required inventory

Search the current repository and authorized local data directories for:

- prior `docs/MC_AUDIT_PACKAGE/` sources, exports, generator, and manifest;
- Daily/Weekly MC archives, including source filenames, timestamps, pair coverage, and gaps;
- H4/D1/W1 OHLC and Backtest data, with timezone, timestamp convention, price fields, and coverage;
- `daily_results_profile1/` through `daily_results_profile4/`, and `daily_results_profile.tar` only if it exists;
- trade, order, fill, candidate, sizing, risk, margin, and position records;
- local Git history/configuration evidence relevant to sizing and candidate weighting;
- current local runtime/service artifacts and Demo/shadow logs.

Do not access remote servers, brokers, or external data services unless separately authorized. Do not assume the checked-in workspace is the deployed runtime. Do not extract an archive over existing files.

### 4.3 Trade identity and provenance rules

- Initial trade identity: `(account, trade_id)`. Verify key uniqueness and collisions; retain instrument, direction, and open time as consistency checks and cross-source join fields.
- Preserve `source_file`, `source_row`, raw values, and source hash in any normalized mapping.
- Keep each repeated export row in the provenance map. Deduplicate only for trade-level summaries.
- If duplicate records disagree, compare explicit observation/export timestamps and lifecycle state. If ordering cannot be established, mark `AMBIGUOUS_STATE`; do not choose a convenient row.
- Cross-source join key should include identity plus instrument, normalized direction, and normalized open time. Record join cardinality (`1:1`, `1:many`, `many:1`, `unmatched`) and timezone transformations.
- Do not add the 457 v685 entry-log rows to 577 lifecycle identities. Report unique lifecycle identities, entry-log rows, and successful/ambiguous/unmatched links separately.

### 4.4 Hash and package rules

Create a portable manifest with relative paths for files included in the Phase 0 package. Each entry must state size, SHA256, source class, and whether the file is included and independently verifiable.

For source files outside the package or unavailable to the reviewer:

- record the original source path and hash as `EXTERNAL_ORIGIN_ONLY`;
- do not claim independent verification unless the source bytes are available;
- record the exact verification command and its result separately from the manifest.

Hash source inputs before analysis and confirm they were unchanged afterward. Do not modify the prior package solely to normalize its outputs; document any actual discrepancy.

### 4.5 Phase 0 deliverables

Use `docs/MC_AUDIT_V2/phase0/` for the new reconciliation outputs:

1. `01_PHASE0_RECONCILIATION.md` — prior package verification, dataset inventory summary, V2 feasibility, and open decisions.
2. `02_MC_ARCHIVE_INVENTORY.csv` — existing snapshots and provenance; no duplicate export unless required for verification.
3. `03_OHLC_DATA_INVENTORY.csv` — discovered OHLC sources, timeframe, date coverage, gaps, timezone, and quality.
4. `04_TRADE_DATA_INVENTORY.csv` — source rows, unique trade identities, date range, profile/account fields, statuses, and duplicate mapping reference.
5. `05_BACKTEST_DATA_INVENTORY.csv` — actual backtest inputs/outputs and whether it contains market prices, saved MC, candidate history, and trades.
6. `06_CODE_CONFIG_TIMELINE.md` — local code/config change evidence for MC weights and sizing eras; introduced/available/applied/deployed must be separate states.
7. `07_RUNTIME_AND_DEMO_STATUS.md` — verified facts and `NOT_VERIFIED` items; do not start or stop processes.
8. `08_DATA_GAPS.csv` — each gap, affected research question, impact, and potential authorized source.
9. `09_PHASE0_ACCEPTANCE.md` — checklist, validation commands, hashes, unresolved items, and recommendation for the next gate.

If a data class is absent, produce an inventory row and gap statement; do not fabricate an empty-looking analysis dataset or pretend the analysis was performed.

### 4.6 Phase 0 acceptance gate

Phase 0 passes only when:

- the existing package has been checked for definitions and provenance, without unnecessarily duplicating exports;
- local OHLC/Backtest coverage and gaps are stated, including whether H4 exists;
- all trade sources are reconciled by validated identity and row-level provenance;
- profile attribution uses the row `profile` field;
- MC forecast event/horizon/version/availability facts are confirmed or explicitly unknown;
- sizing-era introduction, configuration, and actual application dates are proven or marked unknown;
- runtime, Demo baseline, and Shadow independence are verified or marked `NOT_VERIFIED`;
- source hashes can be independently checked where bytes are included, and external-only hashes are clearly labelled;
- no trading code/configuration, order, position, or running process was changed.

After Phase 0, stop and present the acceptance report. Owner review is required before implementing analysis scripts or proceeding to a research phase.

## 5. Conditional research phases

These phases are research design and deliverable requirements, not current execution authorization. At each gate, use only data available and approved for that phase.

### Phase 1 — H4 market-structure reconstruction

**Prerequisite:** Usable, timestamped historical OHLC; Owner approves the descriptive feature set and review windows.

- Use actual prices as the source of market facts. H4 is primary; D1/W1 are context.
- Validate missing/duplicate bars, timezone/session conventions, price anomalies, and instrument orientation.
- Preserve raw continuous features (swing highs/lows, range, range expansion/contraction, reversal count, directional persistence, duration) before proposing categorical labels.
- Keep `UNKNOWN`, `TRANSITION`, `MIXED`, and insufficient-data states. Do not let a single indicator or current strategy decide the ground truth.
- Treat the user-described prior-week H4 swings as a review window to locate and verify from actual timestamps, not as a pre-labelled outcome.
- Keep human annotations separate from computed features and record reviewer, timestamp, and rationale.

Potential outputs: `h4_market_structure.csv`, `market_regime_timeline.csv`, `market_transition_events.csv`, `market_regime_statistics.csv`, `manual_review_windows.csv`, and a methodology report. `market_regime_timeline.csv` in V2 must be derived from OHLC, not from MC snapshots.

### Phase 2 — JPY strength reconstruction

**Prerequisite:** Phase 1 data-quality review or a separately approved price-only method.

- Report earliest MC evidence and earliest price evidence separately.
- Normalize price and MC direction by base/quote orientation.
- Examine individual JPY pairs, cross-pair consensus, persistence, weakening/recovery, and timeframe.
- Preserve the MC archive’s 2026-09-24..2026-10-12 gap; do not interpolate missing forecasts.
- Account for shared JPY exposure, correlated pairs, and temporal dependence.

Potential outputs: JPY price-strength timeline, cross-pair consensus, phase changes, MC-vs-market comparison, and a report that distinguishes actual saved MC from retrospective calculations.

### Phase 3 — MC probability-quality audit

**Prerequisite:** Confirm MC event definition, forecast horizon, prediction timestamp, price field, model version, and when each forecast became available. Owner approves label and horizon definitions before scoring.

- Do not score direction using Bot BUY/SELL logic.
- Evaluate P(up) only for the event/horizon it actually represents. If the contract cannot be established, report the probability-quality analysis as blocked rather than selecting a convenient horizon.
- If only aggregate P(up) is saved, limit claims to binary-event calibration/quality. Do not claim full simulated-distribution validation without the underlying distribution/sample.
- Keep Daily and Weekly forecasts separate; include sensible non-lookahead baselines, sample sizes, uncertainty intervals, missingness, and dependence limitations.
- Calculate Brier/log loss/calibration only when labels and time alignment are valid. No unsupported significance claims.

Potential outputs: probability/outcome links, calibration by bucket/instrument, D/W comparison, regime-stratified results only if regime labels were approved, uncertainty estimates, and a report.

### Phase 4 — MC weights, candidates, and opportunity allocation

**Prerequisite:** Source-code path review and historical candidate records with stable IDs, decision-time inputs, filters/ranks, capacity, and execution links.

- Separate within-pair MC influence from cross-pair JPY consensus and global ranking.
- Attribute observed choices only to logs/code facts that are linked to that decision.
- If historical candidate records are incomplete, mark historical ranking `NOT_RECONSTRUCTABLE`; do not backfill candidates with current logic and call them historical.
- A counterfactual replay must be separately labelled `COUNTERFACTUAL`, preserve actual historical candidates and available inputs, state substitutions, and evaluate subsequent outcomes without lookahead.
- Trade counts alone cannot establish that light MC weighting caused non-JPY selections.

Potential outputs: weight-path evidence, candidate/decision reconstruction where linkable, rejection reasons, actual-vs-counterfactual comparison, and limitations.

### Phase 5 — Position-management evolution

**Prerequisite:** Evidence for rule introduction, configuration, calculation, and actual application.

Use three candidate eras, with boundaries proven rather than assumed:

1. prior sizing behavior;
2. Fibonacci allocation;
3. probability-based allocation.

For each, distinguish code present, configured, calculated, authorized, applied, and reflected in filled units. Git commit time alone does not establish deployment. Report profile/time differences and actual units; calculate currency exposure or account-currency risk only when conversion, SL, account currency, and synchronized portfolio context are available.

Potential outputs: era timeline, rule-input reconstruction, calculated-vs-filled units, exposure/risk limitations, and a report.

### Phase 6 — Unified market/MC/decision/trade timeline

**Prerequisite:** Relevant price and saved-MC data plus source records linkable by stable IDs and availability times.

Align actual market, saved MC, decision/candidate, sizing, order/fill, and lifecycle events. Store UTC plus original timestamps/timezone. Never use a forecast generated or made available after the decision to explain that decision. Preserve ambiguous/unmatched joins.

Potential outputs: unified event timeline, trade/regime alignment, whipsaw sequences, JPY/non-JPY opportunity review, and a report.

### Phase 7 — P2 recording specification and implementation

**Design owner:** ChatGPT / Owner review.
**Implementation:** IDE Agent only after an approved strict specification.

First deliver a schema proposal covering market snapshot, MC snapshot, consensus, decision cycle, candidate, sizing, order, and lifecycle events. Specify stable IDs, types, units, timestamps/availability, source/version, missing semantics, idempotency, privacy, retention, validation, and failure handling.

No P2 code is authorized by this plan. After Owner approval, implementation is observation-only and must not alter decisions, weights, filters, candidate order, sizing, SL/TP, orders, or positions. Shadow execution requires a separate isolation approval.

## 6. Demo baseline and shadow guard

The existing audit records do not verify an independent Demo baseline. Phase 0 may inspect process/config/log evidence read-only, but must not launch, restart, or change any process.

Before any later Shadow launch, separately prove that it:

- cannot submit orders or change positions;
- has separate state, output paths, and logs;
- cannot influence baseline decisions or shared mutable state;
- has a failure mode that cannot interrupt the baseline;
- records `execution_authorized=false`.

If isolation cannot be verified, do not start Shadow. Existing `applied=false` shadow files are not proof that a process is currently running or isolated.

## 7. Data and output naming

Keep the first audit package immutable as historical evidence. In V2:

- call the prior `02_market_regime_timeline.csv` an **MC snapshot transition timeline** in documentation; do not interpret it as OHLC regime labels;
- if a V2 MC transition extract is needed, name it `mc_snapshot_transition_timeline.csv`;
- reserve `market_regime_timeline.csv` for explicitly documented, OHLC-derived market analysis;
- include a data dictionary, source classification, join/key definition, missingness, and methodology with each deliverable set;
- avoid producing a file if its underlying data are absent; record the blocker in the inventory instead.

The phase-specific output names in V1.0 may be retained when they remain appropriate. Deliverables are conditional on evidence and gate approval, not a requirement to create empty CSVs.

## 8. Execution order and approvals

| Order | Work | Approval gate |
|---|---|---|
| 0 | Read-only prior-work reconciliation, local data inventory, data-source/hash verification | Owner approves this V1.1 Phase 0 task |
| 1 | Review Phase 0 report and decide whether OHLC/Backtest data are sufficient | Owner review |
| 2 | Approve market feature definitions and review windows; reconstruct H4 market structure | Separate phase approval |
| 3 | Reconstruct JPY market strength | Phase 1/data review |
| 4 | Agree MC event/horizon/label contract, then evaluate probability quality | Explicit methodology approval |
| 5 | Reconstruct weights/candidates only to extent historical evidence permits | Explicit approval; no fabricated candidates |
| 6 | Establish sizing eras and actual-application evidence | Explicit phase review |
| 7 | Build unified timeline from linkable data | Explicit phase review |
| 8 | Draft P2 event/data contract; implement only after Owner approval | Strict Spec approval required |
| Parallel | Demo/Shadow inspection or launch | Inspection read-only; launch needs separate isolation and Owner approval |

If OHLC or historical saved MC cannot be found, report which research questions are blocked and identify authorized data-acquisition options. Do not silently substitute current/recomputed data for actual historical observations.

## 9. IDE Agent operating rules

### Phase 0 permitted

- Read files, code, logs, local Git history, and approved data directories.
- Inspect the audit package and re-run a prior export only to validate a specific discrepancy.
- Produce inventory, reconciliation, provenance, hashes, and gap reports.

### Prohibited without separate written approval

- Strategy, MC weight, direction, ranking, filtering, sizing, SL/TP, configuration, or production changes.
- Order submission, position changes, broker/server actions, Demo restart, or starting a Shadow process.
- Creating historical candidates or MC predictions with the current algorithm and labelling them as actual historical data.
- Deleting, rewriting, normalizing in place, or cleaning original data.
- Committing, pushing, resetting, checking out, or overwriting user changes.

Report branch, HEAD, worktree status, generated files, and any source changes observed. Do not clean unrelated files. Stop at the Phase 0 gate and await Owner review.

## 10. Phase 0 handoff task — current agent assignment

> **Do only this task after Owner approval. Do not implement Phases 1–7.**

1. Inventory the existing `docs/MC_AUDIT_PACKAGE/` and completion report. Confirm the meaning of each export from its header, generator, and source; specifically mark the old MC `02_market_regime_timeline.csv` as not an OHLC regime dataset.
2. Verify the source CSVs in `daily_results_profile1/`–`daily_results_profile4/`, if still present, and the 577 trade identities against exit-audit records. Do not require `daily_results_profile.tar` if the unpacked files are available; record it only if present.
3. Search authorized local project/data locations for H4/D1/W1 OHLC and Backtest files. Report exact path, size, source, timeframe, timezone, min/max timestamps, gaps, duplicate bars, and whether historical saved MC/candidates/trades accompany them.
4. Inventory MC files using existing exports as a starting point. Verify earliest/latest available timestamps and gaps; do not recreate every existing CSV.
5. Cross-index v685 entry logs, lifecycle records, and profile CSV identities. Report one-to-one, ambiguous, and unmatched links separately; do not infer missing candidate decisions.
6. Search local Git/config/log evidence for sizing and MC-weight chronology. Report introduced/configured/calculated/applied/deployed evidence separately; do not modify config or infer deployment from commit time.
7. Inspect local runtime/Demo artifacts only. If production runtime or Demo independence cannot be verified without remote access, mark `NOT_VERIFIED` and stop short of accessing it.
8. Create only the Phase 0 deliverables in §4.5. Include a portable manifest and distinguish included/verified files from external-origin-only hashes.
9. Run validation on the inventory output and hashes. Report Git status and confirm no trading code/config, process, order, or source data was changed.
10. Stop and provide a gate recommendation. Do not begin H4 labeling, MC scoring, candidate replay, sizing experiments, or P2 implementation.

## 11. Phase 0 completion response

The handoff report must answer:

1. What prior outputs were re-used and verified?
2. What actual market-price/backtest sources exist, and what periods/timeframes do they cover?
3. What historical MC sources exist, and are event/horizon/availability semantics known?
4. What trade identities and lifecycle links are validated, ambiguous, or unmatched?
5. What evidence exists for MC weights and sizing eras?
6. Which V2 phases are feasible, blocked, or need an Owner decision?
7. Were any files, code, config, processes, orders, or positions changed?
8. What is the branch/HEAD/worktree state?
9. What is the recommended next gate and exact evidence needed?

**End of V1.1.**
**Immediate next action:** Owner review/approval of this Phase 0-only task.
**Implementation authorization:** Phase 0 read-only only, after approval.
**Trading authorization:** NONE.
