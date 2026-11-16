# Phase 3.2 — Document 03: Experiment Authorization and Acceptance Criteria

**Date:** 2026-11-15  
**Status:** L2-A APPROVED (owner, 2026-11-15) — protocol + bounded execution authorization recorded  
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
| Approve fixed 200/300/500/800 sequence | APPROVED (owner, 2026-11-15) |
| Approve per-feature tolerance | APPROVED — `atol = 1e-10`, `rtol = 1e-8` |
| Approve two-pair convergence rule | APPROVED — both `300 vs 500` and `500 vs 800` required per feature |
| Approve ADX break/reseed fixture | APPROVED — §6 fixture |
| Approve experiment execution scope | APPROVED — bounded offline fixed-fixture runs only; no production code, training or artifact changes |

**Execution note (2026-11-15):** the bounded Step 4 offline convergence run and the ADX break/reseed unit check were executed as a read-only implementation check under the owner's "go directly to experiment/code" instruction, before this authorization was recorded. Its report is `experiments/phase3_2_feature_convergence/REPORT.md`. This protocol is recorded as approved for that bounded scope; any extension needs a protocol amendment.

## 9. Stop conditions

Stop the affected experiment if:
- Inputs do not match the preregistered fixture.
- Runtime/dependency identity differs from the approved environment.
- A result requires changing the formula or tolerance.
- A feature emits missing/partial output contrary to its definition.
- A hidden fallback or data repair is detected.
- Any production artifact or trading behavior would be changed.

A stop is a result, not permission to improvise a repair.

---

## 10. P1/P2 Train–Inference Parity Preregistration (appended 2026-11-16)

**Experiment ID:** `PARITY-P1P2-01`
**Preregistration timestamp:** 2026-11-16 (written before any run; no result was inspected first).
**Authorization:** owner "全部授权" = L2-B + L3 (Revision Plan §14.1). Bounded **offline / no-network / read-only** only. It does **not** authorize training, artifact writes, deployment, READY activation or trading-behaviour changes.

### 10.1 Objective

Under the new Feature Contract, demonstrate that the **training path** and the **inference path** produce, from identical raw OHLCV:

- **P1 — raw input consistency:** identical accept/reject on identical invalid fixtures; and
- **P2 — raw feature-output consistency:** identical pre-scaling feature row — names / order / dtype / missingness exact; floats within `|A − B| ≤ atol + rtol·|B|` (`atol = 1e-10`, `rtol = 1e-8`).

P1 and P2 are reported **separately**; neither substitutes for the other. P3–P5 stay `NOT VERIFIED`.

### 10.2 Fixtures (frozen; must not be replaced after seeing results)

**Valid fixtures:** the five deterministic fixtures already preregistered for Step 4, reused verbatim from `experiments/phase3_2_feature_convergence/convergence_experiment.py::fixture_ohlc` — `up`, `down`, `varying`, `alternating`, `adx_break`; 800 M15 bars; fixed UTC index starting `2026-01-05 00:00`; each identified by `sha256(OHLC)`.

**Invalid fixtures** (derived deterministically from a valid base; each identified by a name + base sha256):

| # | Case |
|---|---|
| 1 | duplicate timestamp (final row appended again) |
| 2 | non-monotonic index (reversed) |
| 3 | missing required column (`High`) |
| 4 | non-finite `Inf` in `High` |
| 5 | non-finite `NaN` in `Close` |
| 6 | non-positive price (`Low = 0`) |
| 7 | `High < Low` |
| 8 | `High/Low` not bounding `Open/Close` |
| 9 | naive (tz-less) index |
| 10 | too few bars (1 row) |
| 11 | empty batch |

### 10.3 Two path entries

- **Training entry:** `retrain_model._build_pair_features(raw, feat_engine)` with switch `USE_FEATURE_CONTRACT_V2` ON (env `OPT_USE_FEATURE_CONTRACT_V2`; default OFF). Wired in this session under the same default-OFF, revertible, fail-closed pattern as the bots.
- **Inference entry:** `fx_trade_bot.py` / `fx_trade_bot_v685.py::_build_pair_features` with `USE_FEATURE_CONTRACT_V2` ON. Those modules are **not importable offline** (module-level config/engine construction plus a possible outbound cooldown refresh), so the harness (a) **statically asserts** each bot ON-branch source is exactly `from ml.feature_contract import build_features as _contract_build` + `return _contract_build(raw)` with no other transform, and (b) invokes `ml.feature_contract.build_features(raw)` to obtain the inference-side output. Recorded as an **explicit deviation** (source-verified, not imported).
- Both ON-branches call the single shared implementation `ml/feature_contract.build_features`; parity therefore reduces to (i) routing identity and (ii) determinism of that function.

### 10.4 Comparison and acceptance

- **P1:** for each invalid fixture both entries must yield the **same outcome** (both reject with `InputContractError`, or both accept). Divergence = FAIL.
- **P2:** for each valid fixture compare raw contract frames: `list(columns)` exact, `dtypes` exact, per-cell missingness exact, and for every finite pair the float tolerance. Report **per feature, per fixture** — no aggregate may hide a failure. Any schema/missingness mismatch or tolerance breach = FAIL.
- **Secondary (supporting, not substituting P2):** confirm both endpoints apply the same post-build cleaning chain (`replace([inf,-inf],nan) → ffill → bfill → fillna(0)`).
- Tolerances are frozen here and **must not be relaxed** after results.

### 10.5 Recorded identity

Record git commit + dirty/clean (and the files touched), Python / numpy / pandas / xgboost / tzdata / pytz versions, `zoneinfo.TZPATH`, every fixture `sha256`, and this preregistration timestamp.

### 10.6 Verdict rules

P1 PASS iff all invalid fixtures agree. P2 PASS iff all valid fixtures × all features pass schema + tolerance. `FULL_PARITY_STATUS` **remains `NOT VERIFIED`** because P3–P5 are unverifiable without an active model / scaler / `.features.json` bundle; P3–P5 must not be marked pass/waived/`NOT REQUIRED`.
