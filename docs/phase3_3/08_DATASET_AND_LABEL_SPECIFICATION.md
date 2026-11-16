# Phase 3.3 — Dataset & Label Specification

**Document ID:** `PHASE3_3_DATASET_AND_LABEL_SPECIFICATION`
**Date:** 2026-11-16
**Status:** `DRAFT` — baseline definitional parameters **FROZEN** (`OPEN-01`–`OPEN-04`, `OPEN-04b`, Owner 2026-11-16); dataset-bound items marked `[PENDING DATA PROFILING SCAN]`.
**Nature:** Defines **what data the research uses, how labels are produced, and which samples are eligible**. It does **not** define the experiment design (that is Doc 09) and does **not** authorize production training, artifact publication, or live wiring.
**Upstream:** `00`–`07`; frozen freeze record `docs/phase3_2/05_TECHNICALLY_ELIGIBLE_CANDIDATE_FREEZE.md` §5.

---

## 1. Purpose and scope

Doc 08 answers: *what dataset do we use, what does each row represent, and what is the correct answer the model must predict?* It defines **input ↔ label** coupling and sample eligibility so that time-travel, ambiguous labels, and invalid samples cannot enter the research set.

**In scope:** prediction target (`OPEN-01`), horizon (`OPEN-02`), label formula (`OPEN-03`), sample eligibility (`OPEN-04`), and the initial support baseline (`OPEN-04b`).
**Out of scope (Doc 09):** time-series splitting, purge/embargo, cross-pair evaluation policy, primary metric, experiment protocol, costs.

## 2. Inherited frozen constraints (must not be altered)

| Item | Value |
|---|---|
| Feature Contract Identity | `FCV2-bffdb0005083f95e` (sha256 `bffdb0005083f95e2030df7ec912af2e87ec930fdd3672f0b1a0d5530e9a0a8c`) |
| Feature set | the frozen 33-column `ORDERED_FEATURES` (`ml/feature_contract.py`) — order and definitions unchanged |
| Timeframe | M15 (one row = 15 minutes) |
| Excluded (2) | `vol_sma_ratio`, `vol_trend` (FD-07) |
| Deferred (2) | `is_london`, `is_ny` (session interval not defined) |
| Upstream parity | P1 PASS · P2 PASS · P3–P5 `NOT VERIFIED`; `FULL_PARITY_STATUS = NOT VERIFIED` |
| Warm-up behaviour | FD-09: warm-up feature outputs stay `NaN`, never imputed |

This document **redefines no frozen feature** and **does not modify the FCID**.

## 3. `OPEN-01` — Prediction Target (FROZEN)

**Binary classification.** Label `1` = **UP**, label `0` = **NON-UP**.

- Positive class = UP. Negative class = NON-UP (the complement; not a separate "down" class).
- Legacy note: the legacy path used a `future_return > 0.0005` threshold; the Phase 3.3 baseline uses a **zero threshold** (see §5) — these are different definitions.

## 4. `OPEN-02` — Prediction Horizon (FROZEN)

**6 completed M15 consecutive bars** (≈ 90 nominal minutes) forward from the decision bar `t`.

- "Completed" = closed candles only (no in-progress candle; the fetch path drops the unclosed last candle).
- "Consecutive" = the 6 forward bars must be contiguous at a 15-minute step; any calendar gap (weekend/holiday/halt) invalidates the sample (see §6).

## 5. `OPEN-03` — Label Construction (FROZEN)

Zero-threshold forward return ratio:

```
R_{t,6} = Close_{t+6} / Close_t - 1
label_t = 1  if R_{t,6} > 0
        = 0  otherwise
```

- `Close_t` is the close of the decision bar; `Close_{t+6}` is the close 6 completed bars later.
- **Information-overlap window = 6 bars** (the label at `t` uses information up to `t+6`). This is the value that Doc 09's purge/embargo must cover; it is **not** a Doc 08 decision.
- Ties (`R == 0`) map to `0` (NON-UP), consistent with a strict `> 0` rule.
- No final label *implementation* code lives in this document; the executable reference is `phase3_3_baseline.py`.

## 6. `OPEN-04` — Sample Eligibility (FROZEN, strict)

A row qualifies as a research sample **only if all** of the following hold:

1. **Warm-up complete** — none of the 33 features is `NaN`. Warm-up rows are **dropped row-wise**; **no interpolation**, **no `ffill`/`bfill`**, **no `fillna(0)`**, **no forward-fill of missing bars**.
2. **Label available** — the horizon target exists (`t+6` present).
3. **Forward window contiguous** — the 6 forward bars are consecutive M15 steps (no gap introduced by market closure or data loss).
4. **Finite values** — inputs and label are finite.

Feature warm-up output itself remains `NaN` (FD-09 is untouched); eligibility **excludes those rows downstream** without modifying the frozen feature definitions or outputs.

## 7. `OPEN-04b` — Initial Support Baseline (FROZEN)

For the **first data-profiling pass**:

- **Minimum support:** ≥ **1,000 samples per class** (both UP and NON-UP) in the eligible dataset.
- **Maximum class imbalance:** the majority class share must not exceed **70%** (i.e., imbalance not worse than 70:30).

These are **initial profiling gates**, reported by the baseline script; exceeding them is a signal to revisit the dataset source/universe, not to relax the gate silently.

## 8. Dataset construction pipeline (executable reference: `phase3_3_baseline.py`)

1. **Ingest** — fetch M15 candles per instrument via OANDA (`config_oanda` is the only module reading env); the unclosed last candle is dropped.
2. **Validate** — apply the frozen input contract (`ml.feature_contract.validate_candles`): DatetimeIndex UTC, strictly increasing, OHLC consistent, positive prices, finite.
3. **Features** — `ml.feature_contract.build_features` → exactly the 33 ordered columns (warm-up = `NaN`).
4. **Label** — apply §5 with `H = 6`.
5. **Eligibility** — apply §6; record exclusion accounting (§9).
6. **Assemble** — pooled research frame `(timestamp, instrument, 33 features, label)`; no scaling here (scaling is fold-local, Doc 09).

## 9. Exclusion accounting (required outputs)

Every run must report, overall and per instrument:

| Stage | Count |
|---|---|
| Raw bars ingested | n_raw |
| Dropped: unclosed last candle | n |
| Dropped: warm-up `NaN` rows | n |
| Dropped: label unavailable / forward window non-contiguous | n |
| **Eligible samples** | n |
| Eligible per class (UP / NON-UP) | n / n |

## 10. `[PENDING DATA PROFILING SCAN]`

The following are **not yet decided** and must be resolved by an Owner-approved data-profiling scan before they are frozen:

- Final **instrument whitelist** (`[PENDING DATA PROFILING SCAN]`) — currently uses `config.DEFAULT_PAIRS` for profiling only.
- Multi-pair **training view** (pooled vs per-pair) — also depends on `OPEN-07` (Doc 09).
- Meeting `OPEN-04b` support across the chosen universe/period (`[PENDING DATA PROFILING SCAN]`).
- Dataset **identity fingerprint** (source, period, final candle, input `sha256`) (`[PENDING DATA PROFILING SCAN]`).
- `is_london` / `is_ny` session definitions remain **DEFER** (out of Doc 08).

## 11. Boundary (non-authorization)

- Doc 08 does **not** authorize experiments (Doc 09), and does **not** authorize production training, artifact write/overwrite/publish, `USE_FEATURE_CONTRACT_V2` default-ON, READY/live-hook wiring, deployment, or trading-behavior change.
- The baseline script writes **only** under `experiments/phase3_3_baseline/` (research location) and **never** touches production artifact paths.
- `OPEN-05`–`OPEN-09` remain `OPEN` in `07_OWNER_DECISION_REGISTER.md`.

## 12. Status

- `OPEN-01`–`OPEN-04`, `OPEN-04b`: **FROZEN** (Owner 2026-11-16).
- `OPEN-05`–`OPEN-09`: **OPEN** (Doc 09 / `07`).
- Dataset-bound items: `[PENDING DATA PROFILING SCAN]`.
