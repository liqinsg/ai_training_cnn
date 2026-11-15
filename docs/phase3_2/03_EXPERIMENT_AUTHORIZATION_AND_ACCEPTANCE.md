# Phase 3.2 — Document 03: Experiment Authorization and Acceptance Criteria

**Date:** 2026-11-15  
**Status:** DRAFT — OWNER APPROVAL REQUIRED BEFORE EXECUTION  
**Scope:** Bounded technical experiments only. No production implementation or training authorization.

## 1. Purpose

Authorize a finite, preregistered experiment set to test formula correctness, input validation, backend failure behavior, history-length sensitivity and training/inference parity.

No experiment result may be inspected before its inputs, code identity, tolerances and acceptance rules are frozen.

## 2. Global controls

- Record repository commit, working-tree status, Python version, dependency lock/hash, OS and relevant backend versions.
- Use deterministic fixtures and fixed final candle timestamps.
- Record raw feature outputs before scaling.
- Record each feature independently; no aggregate score may hide a failed feature.
- No model training, artifact writing, deployment, READY activation or trading behavior changes.
- Do not relax tolerances after seeing results.
- Keep implementation correctness/parity (A) separate from history convergence (B).

## 3. Fixed history-length experiment

**Preregistered sequence:** `200 → 300 → 500 → 800` bars.

All runs:
- End at the same final completed candle.
- Come from the same underlying OHLCV series.
- Use exact suffixes.
- Record the final raw value for every candidate feature.

| Pair | Common suffix | Reference |
|---|---:|---:|
| 200 vs 300 | 200 bars | 300-bar result |
| 300 vs 500 | 300 bars | 500-bar result |
| 500 vs 800 | 500 bars | 800-bar result |

For each feature and pair:

`abs(shorter_value - reference) <= 1e-10 + 1e-8 * abs(reference)`

A feature passes convergence only if both `300 vs 500` and `500 vs 800` pass. `200 vs 300` is diagnostic evidence only. If either required pair fails, status is `NOT ESTABLISHED`; do not extend beyond 800 without a new preregistered owner decision.

The 800-bar result is a verified convergence baseline only for a feature that passed both required pairs through 800.

## 4. Production history length

**Status: NOT YET APPROVED.**

The experiment sequence is not a production setting. If the subsequently approved production length is not one of 200, 300, 500 or 800, preregister a same-final-candle comparison between that length and the 800-bar result before inspecting results. Use the longer-history value as reference and the same per-feature tolerance. This comparison is separate and cannot be inferred from the fixed sequence.

If a feature did not pass the required convergence pairs through 800, no production warm-up claim may be made from this baseline.

## 5. Experiment matrix

| Experiment | Method | Acceptance |
|---|---|---|
| Timeframe/input validation | UTC M15 fixtures; inject duplicate, reorder, invalid OHLC and missing interval | Whole batch rejected before feature output for each invalid case; approved calendar exceptions only |
| Formula fixtures | Hand-calculated rising, falling, flat, zero-denominator, boundary and missing-input fixtures | Exact categorical values; float tolerance `1e-10 + 1e-8*abs(reference)` |
| Return/volatility continuity | Verify exact lag timestamps and full consecutive return/close counts | No skipping; exact first-valid position; common candle policy applied |
| Backend identity/failure | Pin dependency/code identity; inject missing dependency, exception, null/empty output, missing columns and non-finite output | Named actionable failures; no fallback, sentinel or partial output |
| History-length sensitivity | Fixed 200/300/500/800 sequence | Both required adjacent comparisons pass independently per feature |
| Warm-up boundary | Sweep immediately below/at/above each declared window/seed | Fixed schema; unavailable before declared first-valid row |
| Volume invariance | Add historical volume before common suffix; test missing/zero/negative/changing values | No source switching; only run once volume semantics are approved |
| Session/DST | UTC instants around boundaries and DST transitions with pinned IANA tz database | Matches approved session rule in both paths; only run once session definition is approved |
| Train/inference parity | Same raw candles/config/dependency identity through both paths | Names/order/types/missingness exact; float tolerance met; same invalid fixtures rejected |

## 6. ADX-specific fixture

Include:
- A valid contiguous DX run that produces the initial seed at index `2n-1`.
- A mathematically undefined DX due to zero denominator on otherwise valid candles.
- Confirmation that ADX is unavailable at the break.
- Confirmation that pre-break ADX is not carried forward.
- Confirmation that Wilder TR/+DM/-DM states continue.
- Confirmation that a fresh run of `n` consecutive valid DX values is required before reseeding.
- For `n=14`, break at index 40 followed by valid DX from 41 must seed at index 54 from `DX[41..54]`.

Invalid candle/timestamp cases are not ADX-local recovery tests; they must reject the entire batch.

## 7. Deliverable for each experiment

Record:
1. Experiment ID and approved protocol version.
2. Git commit and dirty/clean status.
3. Runtime/dependency/backend identity.
4. Exact input fixture identity and final candle.
5. Per-feature expected and actual outputs.
6. Absolute difference and tolerance.
7. PASS / FAIL / NOT RUN / BLOCKED.
8. Failure reason and reproducible evidence.
9. Whether result concerns correctness/parity (A) or convergence (B).

## 8. Owner authorization

| Authorization | Owner decision |
|---|---|
| Approve fixed 200/300/500/800 sequence | PENDING |
| Approve per-feature tolerance | PENDING |
| Approve two-pair convergence rule | PENDING |
| Approve ADX break/reseed fixture | PENDING |
| Approve experiment execution scope | PENDING |

## 9. Stop conditions

Stop the affected experiment if:
- Inputs do not match the preregistered fixture.
- Runtime/dependency identity differs from the approved environment.
- A result requires changing the formula or tolerance.
- A feature emits missing/partial output contrary to its definition.
- A hidden fallback or data repair is detected.
- Any production artifact or trading behavior would be changed.

A stop is a result, not permission to improvise a repair.
