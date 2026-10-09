
# 🚀 Step-by-Step Task Guide — TRAE Execution Order

## RULE: Complete → Verify → Next Step. DO NOT skip.

---

## STEP 1 — Build Core Engine

**File:** `attribution_core.py`
**Test file:** `tests/test_core.py`

Implement pure functions:

1. candidate_relative(raw_score, direction)
2. classify_score(relative_score, neutral_band=0.10)
3. weighted_calc(factors, weights)
4. decision_from_score(rel_score, thresholds)
5. counterfactuals_full(factors, weights, thresholds)
6. build_jsonl(...)

✅ **Verify:** All unit tests pass; `decision_from_score(-0.72)` returns REJECT

---

## STEP 2 — Define 4 Profiles

**File:** `profiles/attribution_profiles.py`
**Test file:** `tests/test_profiles.py`

Define PROFILES dict: PF-A / PF-B / PF-C / PF-D
Include: weights, thresholds, neutral_band

✅ **Verify:** Each profile weights sum = 1.0; all thresholds valid

---

## STEP 3 — Profile Runner

**File:** `profile_runner.py`
**Test file:** `tests/test_runner.py`

Class ProfileAttribution(process_candidate(...))
Function run_all_profiles(...)

✅ **Verify:** Same input → 4 independent outputs; no shared state

---

## STEP 4 — Logger

**File:** `profile_logger.py`
**Test file:** `tests/test_logger.py`

Class ProfileLogger.write(record)
Method write_all(records_dict)

✅ **Verify:** 4 separate directories; each profile writes independently

---

## STEP 5 — Full Validation

Run all tests in `tests/`

✅ **Verify:** All 17 tests pass

---

## STEP 6 — Dry Run Demo

**File:** `examples/demo_single_candidate.py`

Mock one candidate → run all 4 profiles → print results → write logs

✅ **Verify:** Output readable; 4 JSONL lines written to logs/

---

**⚠️ FINAL RULE: This entire directory is self-contained. Nothing outside here is modified.**
