# 【Strict Spec】Phase 3.1 — Stage B v3

# Prediction Adapter Implementation

**Priority:** P0
**Version:** 3.0
**Status:** DRAFT — PENDING STAGE A.3 ACCEPTANCE
**Repository:** `/Users/liqin/projects/ai_training_cnn`
**Expected branch:** `v2026c`
**Prerequisite:** Accepted Stage A.3 Contract Reconciliation
**Implementation authorization:** NOT GRANTED
**Scope:** Additive Prediction Adapter only

---

# 0. Mission and governing principles

## 0.1 Mission

Implement one independent Prediction Adapter that converts a model-inference attempt into a structured, immutable `PredictionResult`.

The implementation must follow the final accepted version of `docs/PHASE3_1_CONTRACT.md`.

Stage B is responsible for the Prediction boundary only. It does not implement Strategy Decision, Entry Authorization, or trading execution.

## 0.2 Governing principles

```text
Model Initialization
        |
        v
Prediction Adapter
        |
        v
PredictionResult
        |
        |  Stage B does not migrate consumers
        v
Strategy Decision
        |
        v
Entry Authorization
        |
        v
Execution
```

1. Prediction ≠ Decision ≠ Authorization.
2. ModelStatus ≠ PredictionStatus.
3. Raw probability ≠ interpreted probability.
4. Numeric class label ≠ semantic class definition.
5. Successful inference ≠ valid directional interpretation.
6. Recorded evidence ≠ execution authorization.
7. A diagnostic value must never override authoritative status.
8. Unknown conditions must fail closed.
9. No fallback direction or fabricated probability.
10. No behaviour change outside the approved Prediction boundary.

## 0.3 Required outcome

After Stage B:

- A prediction attempt produces a structured, immutable `PredictionResult`.
- Every result has one authoritative status and one compatible reason.
- Probability output is validated before interpretation.
- CD verification is bound to the exact loaded artifact bytes.
- UP/not-UP semantics are explicit.
- Non-READY results cannot expose a usable direction.
- Inference-time failures are contained within the adapter.
- Existing trading behaviour remains unchanged.
- The adapter can be tested independently.

## 0.4 What Stage B does NOT accomplish

Stage B does not activate ML Vote, change Step 7 scoring, change Entry Authorization, migrate C-1 through C-7, change strategy decisions, change trading behaviour, wire the production loader to the adapter, or authorize a new live trading path.

**Stage B completion is not Stage C authorization.**

## 0.5 Contract precedence

Where this spec and the final accepted contract differ:

- The contract governs field names, status and reason names, and any **stricter** field matrix.
- This spec may not be weakened by implementation convenience.
- Any conflict that cannot be resolved by "follow the stricter rule" is a STOP condition (Section 23).

Items in this spec marked **[CONTRACT-CONFIRM]** must be checked against the final contract before implementation. The default stated in the spec applies only if the contract is silent.

---

# 1. Authorization and prerequisite gates

Implementation must not begin until all conditions are satisfied.

| Gate    | Required condition                                                                                                          |
| ------- | --------------------------------------------------------------------------------------------------------------------------- |
| G-A3-1  | Stage A.3 completion report exists.                                                                                         |
| G-A3-2  | All mandatory A3 acceptance criteria pass.                                                                                  |
| G-A3-3  | Final `docs/PHASE3_1_CONTRACT.md` is available.                                                                           |
| G-A3-4  | Final contract version and SHA-256 are recorded.                                                                            |
| G-A3-5  | UP/not-UP semantics are reconciled.                                                                                         |
| G-A3-6  | `SELL = not-UP` is explicitly accepted.                                                                                   |
| G-A3-7  | `positive_class_label`, `p_up`, `p_not_up`, and `p_down` semantics are unambiguous.                                 |
| G-A3-8  | CD-OPEN-4 implementation hardening requirements are explicitly resolved in the final contract.                              |
| G-A3-9  | Exact artifact-specific CD evidence is available, including the model artifact SHA-256 and scaler artifact SHA-256.         |
| G-A3-10 | User explicitly authorizes Stage B implementation.                                                                          |
| G-A3-11 | All **[CONTRACT-CONFIRM]** items in this spec have been checked against the final contract and the outcomes recorded. |

The executor must quote the exact user approval message in the preflight record.

A draft, a review comment, or a Stage A.3 completion report does not independently authorize Stage B implementation.

If any prerequisite is missing: **STOP — DO NOT MODIFY CODE.**

## 1.1 Preflight evidence

Before implementation, record:

- Repository root.
- Current branch.
- `git rev-parse HEAD`.
- `git status --short`.
- Final contract version and SHA-256.
- Stage A.3 acceptance report reference.
- Exact model artifact SHA-256 and scaler artifact SHA-256.
- Accepted CD decision reference.
- Outcomes of all **[CONTRACT-CONFIRM]** checks.
- Explicit implementation approval message (quoted).

Do not reset, clean, stash, or overwrite existing user work. Do not assume a historical commit is the current baseline.

---

# 2. Repository inspection and implementation map

Inspect only the files necessary to implement the adapter. Inspection candidates (not modification authorization):

- `data_pipeline.py`
- `fx_trade_bot_ml.py`
- `strategy_decision.py`

## 2.1 Mandatory implementation map

Produce this map before any code modification:

| Item                     | Required evidence                                                                           |
| ------------------------ | ------------------------------------------------------------------------------------------- |
| Adapter module           | Proposed new module path                                                                    |
| Adapter entry point      | Function name and signature                                                                 |
| PredictionResult         | Field definitions and invariants                                                            |
| Existing inference path  | Exact function and call path                                                                |
| Model availability       | Actual ModelInitResult source, and which `ModelStatus` values count as usable vs unusable |
| Artifact loading         | Exact loading method, byte source, and `load_method` (`BYTES` or `TEMPFILE`)          |
| Artifact and scaler hash | Hash lifecycle and binding                                                                  |
| CD Registry              | Path, schema, revision, load point, read-only access                                        |
| Feature validation       | Existing feature-contract authority                                                         |
| Exception mapping        | Closed mapping table (Section 8)                                                            |
| Caller precondition      | Actual bars-count owner                                                                     |
| Clock injection          | Timestamp source                                                                            |
| Test modules             | Proposed test paths                                                                         |
| File allowlist           | Exact files expected to change                                                              |

The implementation map must identify the real runtime call path. Do not infer call paths from filenames.

## 2.2 Mandatory architecture decision

Stage B uses a **new, narrowly scoped Prediction Adapter module**. Do not embed the adapter in `fx_trade_bot_ml.py`, `strategy_decision.py`, `fx_trade_bot.py`, or `fx_trade_bot_v685.py`.

The new module must be independent of strategy decision and order execution.

If integration requires modifying an existing module, identify the exact minimum change and obtain explicit approval first. No broad refactoring.

---

# 3. P0 — Artifact identity and hash lifecycle

## 3.1 Principle

The artifact hash must identify the exact bytes from which the loaded model instance was constructed. Hashing a file on disk and loading it in a separate read is prohibited.

## 3.2 Approved mechanism

Stage B introduces `load_model_with_identity(...)` in the new adapter module (or a new sibling module). It is the only code that produces a `LoadedModelIdentity`.

1. Read the model artifact bytes once into an immutable `bytes` object.
2. Compute SHA-256 over those bytes.
3. Construct the model instance from those same in-memory bytes (for example via `BytesIO` or the library's bytes/buffer interface).
4. Apply the same single-read procedure to the scaler artifact.
5. Return `LoadedModelIdentity`.

If the installed model library cannot load from memory and a temporary file is unavoidable:

- Write the bytes object to a private temp file (mode 0600, private directory).
- Load from that file only.
- Do not re-read the original artifact path.
- Delete the temp file after loading.
- Record `load_method=TEMPFILE` in the implementation map and the report.

## 3.3 LoadedModelIdentity

Frozen dataclass:

| Field               | Rule                                             |
| ------------------- | ------------------------------------------------ |
| `artifact_sha256` | 64-char lowercase hex; validated at construction |
| `scaler_sha256`   | 64-char lowercase hex; validated at construction |
| `model_instance`  | Reference to the loaded model                    |
| `scaler_instance` | Reference to the loaded scaler                   |
| `load_timestamp`  | UTC-aware, from the injected clock               |
| `source_path`     | Informational only; never used for identity      |

Full SHA-256 only. Truncated hashes are rejected.

## 3.4 Scope relative to the production loader

Stage B does **not** modify the existing production loader or the Phase 3.0 initialization path.

- Stage B delivers `load_model_with_identity` plus tests.
- The adapter accepts a `LoadedModelIdentity` as an injected dependency.
- Wiring the production runtime to produce a `LoadedModelIdentity` is Stage C scope and requires separate approval.
- If the caller cannot supply a `LoadedModelIdentity`, the result is `UNINTERPRETABLE / CLASS_DEFINITION_UNVERIFIED` with `cd_failure_cause=HASH_UNAVAILABLE`.

Consequence, to be stated in the completion report: **Stage B proves identity binding in the new loader and its tests, not on the live production path.**

## 3.5 Immutability scope

The binding is immutable: the identity object cannot be rebound to a different hash or instance. The model and scaler instances themselves remain mutable library objects. B-10 asserts the binding is fixed, not that library internals are frozen.

## 3.6 Scaler identity

The scaler changes the model's input distribution, so CD evidence that ignores it is incomplete. The identity therefore covers both artifacts, and the CD Registry record (Section 4) carries both hashes. A match requires **both** hashes to be equal.

## 3.7 Prohibited approaches

Do not:

- Hash the artifact at one point and load an independently read file later.
- Re-read the artifact path after the hash is computed.
- Re-hash the disk file on every prediction.
- Compute identity inside the prediction call.
- Expose a mutable hash attribute.
- Assume a filename uniquely identifies an artifact.
- Use modification time as artifact identity.
- Inherit CD from another artifact with the same filename.
- Use a truncated SHA-256 for equality checks.
- Silently update the hash after model loading.

The adapter reads the binding. It does not recalculate artifact identity.

---

# 4. P0 — Version-controlled CD Registry

## 4.1 Registry location

`config/model_cd_registry.json`

This is a new, narrowly scoped artifact-interpretation record. It is not a runtime tuning parameter and must not be stored in `run.env`.

## 4.2 Minimum schema

```json
{
  "schema_version": 1,
  "records": [
    {
      "artifact_sha256": "<full SHA-256>",
      "scaler_sha256": "<full SHA-256>",
      "decision": "VERIFIED",
      "positive_class_label": 1,
      "positive_class_index": 1,
      "positive_class_semantics": "UP",
      "negative_class_semantics": "NOT_UP",
      "probability_semantics": "BINARY_EXCLUSIVE_EXHAUSTIVE",
      "evidence_record": "<document reference>",
      "evidence_record_version": "<version>",
      "decision_id": "<accepted decision reference>"
    }
  ]
}
```

The schema may be refined, but it must preserve every identity and evidence field. No placeholders or guessed values.

## 4.3 Requirements

1. Full artifact SHA-256 and full scaler SHA-256 are mandatory.
2. `positive_class_label` is the actual runtime class value (integer).
3. `positive_class_index` is explicitly recorded.
4. Semantic meaning is stored separately from the numeric class label.
5. Binary probability interpretation is explicit.
6. Evidence document and decision reference are traceable.
7. Registry changes are version-controlled.
8. Runtime access is read-only; prediction never writes or amends records.
9. `decision` is a closed set. `VERIFIED` is the only value that permits interpretation. Any other value (for example `REVOKED`, `PENDING`) fails closed.
10. Missing, duplicate, malformed or unreadable records fail closed.
11. The Registry is loaded **once at startup**; the adapter does not re-read it per prediction. The Registry SHA-256 is computed at load time and exposed as read-only metadata.

## 4.4 Authorship

The production `VERIFIED` record must be copied from the accepted Stage A.3 evidence and approved by the user. The Stage B executor must not author, infer or "complete" a production record.

Test fixtures live in a separate fixture location and must never write to the production Registry.

## 4.5 Provenance

The completion report must record: Registry path, Registry Git revision, Registry SHA-256, matching artifact and scaler hashes, matched decision ID, evidence record version.

At runtime the Registry SHA-256 is recorded; the Git revision is recorded in the report only (production may not have `.git`).

The Registry is not a cryptographic security boundary against an actor who can modify the repository. Its purpose is controlled, reviewable, versioned evidence management. Do not claim stronger tamper resistance than the implementation provides.

## 4.6 Exact-artifact lookup

A CD record is usable only when:

```text
loaded.artifact_sha256 == record.artifact_sha256
AND
loaded.scaler_sha256   == record.scaler_sha256
```

No partial matching. No filename matching. No family-level inheritance. No default CD. No self-certification.

---

# 5. P0 — PredictionResult

## 5.1 Construction rules

- Frozen dataclass; all validation in `__post_init__`.
- Violations raise an internal `PredictionResultInvariantError`. The constructor never repairs a value.
- `diagnostics` is stored as a `MappingProxyType` over a defensive copy, with JSON-serializable, bounded values. Non-serializable or oversized entries are rejected, not silently truncated into a different value.
- `p_down` is always `None` in Stage B. Any non-None value is an invariant violation.

## 5.2 Field set

Field names must follow the final accepted contract. At minimum:

| Field                    | Meaning                                             |
| ------------------------ | --------------------------------------------------- |
| `status`               | PredictionStatus                                    |
| `reason`               | PredictionReason                                    |
| `pair`                 | Instrument pair                                     |
| `timeframe`            | Prediction timeframe                                |
| `bar_time`             | Source bar timestamp (tz-aware UTC)                 |
| `direction`            | BUY / SELL / NONE                                   |
| `raw_probability`      | Validated neutral probability                       |
| `positive_class_label` | Registry-verified class value                       |
| `p_up`                 | Interpreted UP probability                          |
| `p_not_up`             | Interpreted not-UP probability                      |
| `p_down`               | Reserved; always None in Stage B                    |
| `model_id`             | Verified formal identity or None                    |
| `model_artifact_hash`  | Full artifact SHA-256                               |
| `release_id`           | Verified release identity or None                   |
| `feature_contract_id`  | Verified feature-contract identity or None          |
| `features_hash`        | Feature provenance fingerprint, if available        |
| `timestamp`            | Prediction timestamp (tz-aware UTC, injected clock) |
| `diagnostics`          | Supplementary only                                  |

`at_threshold` placement **[CONTRACT-CONFIRM]**: if the final contract defines it as a field, use the contract's definition. If the contract is silent, carry it in `diagnostics` under the key `at_threshold`. It must not be added as a top-level field, because the contract is frozen during Stage B.

## 5.3 Field matrix

The final contract may impose stricter rules; it may not be weakened.

| Field                    | READY          | UNINTERPRETABLE | NOT_RUN | UNAVAILABLE  | INVALID      | ERROR        |
| ------------------------ | -------------- | --------------- | ------- | ------------ | ------------ | ------------ |
| `direction`            | BUY / SELL     | NONE            | NONE    | NONE         | NONE         | NONE         |
| `raw_probability`      | float          | float           | None    | None         | None         | None         |
| `p_up`                 | float          | None            | None    | None         | None         | None         |
| `p_not_up`             | float          | None            | None    | None         | None         | None         |
| `p_down`               | None           | None            | None    | None         | None         | None         |
| `positive_class_label` | verified label | None ¹         | None    | None         | None         | None         |
| `model_artifact_hash`  | required       | if available    | None    | if available | if available | if available |
| `at_threshold`         | bool           | None            | None    | None         | None         | None         |

¹ **[CONTRACT-CONFIRM]** If the contract populates `positive_class_label` in UNINTERPRETABLE, follow the contract. Otherwise the runtime class value is carried in diagnostics as `runtime_class_label_at_extraction_index`.

## 5.4 Cross-field invariants

1. READY: `direction == BUY` iff `p_up > DECISION_THRESHOLD`; `SELL` iff `p_up <= DECISION_THRESHOLD`. `DECISION_THRESHOLD = 0.5` is one named constant shared by direction and `at_threshold`.
2. READY: `raw_probability == p_up` exactly (same float).
3. READY: `abs((p_up + p_not_up) - 1.0) <= COMPLEMENT_TOLERANCE` (`1e-9`). Holds by construction; the check guards against future edits.
4. READY: `at_threshold == (p_up == DECISION_THRESHOLD)`.
5. READY requires a non-None `model_artifact_hash` and a Registry-verified `positive_class_label`.
6. Every status has only its allowed reasons (5.5).
7. `bar_time` and `timestamp` are tz-aware UTC wherever present. `bar_time` may be None only for NOT_RUN if the caller genuinely has none.
8. `model_id`, `release_id`, `feature_contract_id` are None unless a verified source exists. Stage B has no such source, so they are None. `features_hash` is provenance only.

## 5.5 Status / reason compatibility

| Status          | Allowed reason                                                                          |
| --------------- | --------------------------------------------------------------------------------------- |
| READY           | Contract-defined success reason (do not invent one)                                     |
| UNINTERPRETABLE | CLASS_DEFINITION_UNVERIFIED                                                             |
| NOT_RUN         | INPUT_INSUFFICIENT                                                                      |
| UNAVAILABLE     | MODEL_NOT_USABLE                                                                        |
| INVALID         | FEATURE_CONTRACT_VIOLATION, PREDICTION_OUTPUT_MALFORMED, PREDICTION_INVALID_PROBABILITY |
| ERROR           | EXECUTION_ERROR                                                                         |
| ABSTAIN         | Defined, unreachable                                                                    |

## 5.6 Last-resort result

If result construction raises `PredictionResultInvariantError` inside the adapter (an adapter bug), the adapter returns a minimal `ERROR / EXECUTION_ERROR` result:

- All probability and direction fields None.
- Diagnostics: `failure_category=INTERNAL_INVARIANT_VIOLATION` and the exception type name.

The fallback constructor uses only literal None values and cannot fail the same invariant. If even this fails, that is a programmer error and may raise.

## 5.7 Invalid construction

`status=READY, direction=NONE` must fail immediately. It must not create a partially valid object. The same applies to any other illegal combination.

---

# 6. P0 — Adapter API and exception contract

## 6.1 Adapter API

One independent adapter entry point. Its signature is determined by the actual inference call path and recorded in the implementation map.

Inputs:

- Prepared inference input.
- `LoadedModelIdentity` (or the model context plus an identity, as established in the map).
- Instrument pair.
- Timeframe.
- Source bar time.
- Required feature-contract metadata.
- Injected clock.
- Registry handle (read-only).

No unrelated configuration arguments.

The adapter must not build a second feature pipeline, reconstruct the training feature matrix, redefine the bar-count threshold, introduce another model-loading mechanism, or perform strategy filtering.

## 6.2 Exception contract

**Inference-time failure → returns a `PredictionResult`.**
**Pre-inference API contract violation → raises.**

No alternative behaviour.

Inference-time failures (all return a result): model unusable, feature validation failure, inference exception, malformed output, invalid probability, missing/duplicate/mismatched CD record, hash unavailable, unexpected runtime exception.

Only these may raise: invalid required constructor argument, invalid dependency injection, wrong mandatory argument type, and naive `bar_time` (6.4).

## 6.3 Catch scope

The adapter catches `Exception`, never `BaseException`. `KeyboardInterrupt`, `SystemExit` and `GeneratorExit` propagate.

## 6.4 `bar_time` validation

A naive `bar_time` is a caller error and raises before inference. The caller owning source data must validate and supply a tz-aware value; the adapter normalizes aware non-UTC values to UTC and never assumes a naive value is UTC.

## 6.5 Unexpected exceptions

At the inference boundary, an unclassified exception becomes `ERROR / EXECUTION_ERROR`. Known model-usability failures are classified through the closed mapping in Section 8, not by catching at inference time. Record the exception type and safe diagnostic context. Do not silently suppress errors.

---

# 7. P0 — Deterministic validation order

The first failed condition determines the result.

| Order | Check                                         | Failure result                                               |
| ----: | --------------------------------------------- | ------------------------------------------------------------ |
|     1 | Model/scaler usability                        | UNAVAILABLE / MODEL_NOT_USABLE                               |
|     2 | Input feature contract                        | INVALID / FEATURE_CONTRACT_VIOLATION                         |
|     3 | Inference execution                           | ERROR / EXECUTION_ERROR                                      |
|     4 | Output structure (7.2)                        | INVALID / PREDICTION_OUTPUT_MALFORMED                        |
|     5 | Neutral extraction and numeric validity (7.3) | INVALID / PREDICTION_INVALID_PROBABILITY (or MALFORMED, 7.3) |
|     6 | Artifact identity and CD binding (7.4)        | UNINTERPRETABLE / CLASS_DEFINITION_UNVERIFIED                |
|     7 | Probability interpretation                    | READY                                                        |
|     8 | PredictionResult construction                 | Invariant violation → 5.6                                   |

## 7.1 Ordering rationale

Steps 4 and 5 use only information available from the runtime model and its output. **They must not read the CD Registry.** Step 6 is the first step that reads the Registry. If output structure or numeric validity fails, the result is INVALID, never UNINTERPRETABLE.

## 7.2 Output structure (step 4)

All must hold, otherwise `INVALID / PREDICTION_OUTPUT_MALFORMED`:

1. Output is 2-D array-like with exactly one row.
2. Runtime `classes_` is available and has exactly 2 entries.
3. The number of probability columns equals `len(classes_)`.
4. The two runtime class values are distinct.

The extraction index is the fixed structural constant `EXTRACTION_INDEX = 1`. It is not read from the Registry, not inferred from class values, and not selected by maximum probability. It denotes "the second column in runtime class order" and carries no semantic meaning.

## 7.3 Neutral extraction and numeric validity (step 5)

1. `candidate = output[0, EXTRACTION_INDEX]`.
2. `runtime_class_label = classes_[EXTRACTION_INDEX]`.
3. Validate `candidate` per Section 10. Failure → `INVALID / PREDICTION_INVALID_PROBABILITY`.
4. Validate the complementary column the same way. Failure → `INVALID / PREDICTION_INVALID_PROBABILITY`.
5. **[CONTRACT-CONFIRM]** Row sum must equal 1.0 within `ROW_SUM_TOLERANCE` (`1e-5`, sized for float32 output). Failure → `INVALID / PREDICTION_OUTPUT_MALFORMED`, because the output is not a probability distribution (for example logits). If the contract rejects this rule, remove it and its tests (B-T58); the default is to include it.

After step 5, `raw_probability` is the validated candidate and `runtime_class_label` is a validated runtime fact. Neither implies UP.

## 7.4 Artifact identity and CD binding (step 6)

All must hold, otherwise `UNINTERPRETABLE / CLASS_DEFINITION_UNVERIFIED`:

1. The identity exposes well-formed full artifact and scaler SHA-256 values.
2. The Registry was loaded successfully and is well-formed.
3. Exactly one Registry record matches both hashes.
4. The record's `decision` is `VERIFIED`.
5. `record.positive_class_index == EXTRACTION_INDEX`.
6. `record.positive_class_label` equals `runtime_class_label` under strict comparison (11.1).
7. Record semantics are exactly `UP` / `NOT_UP` with `BINARY_EXCLUSIVE_EXHAUSTIVE`.

Each failure sets a machine-readable `cd_failure_cause` in diagnostics: `HASH_UNAVAILABLE`, `REGISTRY_UNAVAILABLE`, `RECORD_MISSING`, `RECORD_DUPLICATE`, `DECISION_NOT_VERIFIED`, `INDEX_MISMATCH`, `LABEL_MISMATCH`, `SEMANTICS_UNSUPPORTED`. The cause is diagnostic only and adds no status or reason. **[CONTRACT-CONFIRM]** that the contract permits this diagnostic vocabulary.

## 7.5 Multi-fault rule

When more than one condition is invalid, the first failure in the order above wins. The adapter must not return different statuses depending on incidental code ordering.

---

# 8. P0 — Closed exception mapping

UNAVAILABLE is reserved for positively identified model-usability failures. The implementation map must contain a closed table derived from the **actual** model-loading and runtime paths. Do not invent exception types.

| Exception or condition                                                                        | Source (to be filled from code) | Classification |
| --------------------------------------------------------------------------------------------- | ------------------------------- | -------------- |
| ModelInitResult reports unusable (list the exact unusable `ModelStatus` values)             | Phase 3.0                       | UNAVAILABLE    |
| Required scaler missing                                                                       | Scaler validation path          | UNAVAILABLE    |
| Model object absent                                                                           | Runtime model state             | UNAVAILABLE    |
| Known model incompatibility                                                                   | Initialization exception path   | UNAVAILABLE    |
| Known model load failure (including malformed artifact bytes in `load_model_with_identity`) | Initialization / loader         | UNAVAILABLE    |
| Feature contract violation                                                                    | Adapter validation              | INVALID        |
| Malformed model output                                                                        | Output validation               | INVALID        |
| Invalid numeric probability                                                                   | Probability validation          | INVALID        |
| Any unclassified inference exception                                                          | Runtime                         | ERROR          |

The table is closed. No broad rule such as "all `ValueError` means INVALID" or "all runtime errors mean UNAVAILABLE" without evidence.

Any exception not explicitly classified as a model-usability condition maps to `ERROR / EXECUTION_ERROR`.

Do not expand the UNAVAILABLE list during implementation without recording evidence and obtaining approval if the change alters the accepted mapping contract.

---

# 9. P0 — Input and bars precondition ownership

## 9.1 Caller ownership

The caller that owns source data and bar history remains responsible for the bars-count precondition. The adapter must not recalculate the minimum bar count, duplicate the threshold, rebuild historical bars, or infer whether the caller should have invoked it.

## 9.2 NOT_RUN helper

The new module provides a pure helper:

```text
build_not_run_result(pair, timeframe, bar_time, clock, ...)
```

It executes no inference, does not read the bars threshold, and returns a validated NOT_RUN result (`INPUT_INSUFFICIENT`).

Stage B does **not** modify any caller. Stage B delivers the helper and its unit tests; wiring it into the caller is Stage C. B-T01 therefore tests the helper's output and that the adapter is not invoked in a stubbed caller scenario, not live caller behaviour.

## 9.3 Required ownership evidence

The report must identify the actual caller, the actual bars precondition, the existing threshold source, and the intended (Stage C) NOT_RUN construction location.

---

# 10. P0 — Probability extraction and type validation

## 10.1 Canonical probability

A finite Python `float` in `[0.0, 1.0]`, extracted at the fixed structural index (7.2). No column search, no selection by class value, no selection by maximum.

`raw_probability` means: the probability assigned to the runtime class at `EXTRACTION_INDEX`. It does not mean UP.

## 10.2 Accepted scalar types

- Python `int`, excluding `bool`.
- Python `float`.
- NumPy integer scalar, excluding `numpy.bool_`.
- NumPy floating scalar (including `float32`).

All accepted values are converted to a finite Python float after validation.

## 10.3 Rejected types

Python `bool`, NumPy boolean scalar, `Decimal`, complex numbers, strings, bytes, lists, tuples, dictionaries, NumPy arrays of any dimension (including 0-D), objects with ambiguous numeric conversion, any unsupported custom numeric object.

`Decimal` is rejected because no inference path produces it; accepting it adds surface with no source.

Structure (7.2) is validated before scalar extraction. A 0-D array is not a scalar probability.

## 10.4 Numeric checks

Reject NaN, ±infinity, values below 0, values above 1, and values that cannot be converted safely to a finite float. A bare range comparison is not sufficient.

## 10.5 INVALID probability storage

```text
status = INVALID
reason = PREDICTION_INVALID_PROBABILITY
raw_probability = None
p_up = None
p_not_up = None
direction = NONE
```

The invalid candidate may appear in diagnostics in a safe, bounded representation. It is never stored in `raw_probability`.

## 10.6 Units

Canonical unit is 0–1. Do not guess units from magnitude. Do not modify the MC cache or its percentage representation. If a source explicitly declares percent and the contract requires conversion, convert once at the adapter boundary; otherwise do not convert.

---

# 11. P0 — Class mapping and probability semantics

## 11.1 Runtime class label and Registry agreement

The adapter obtains runtime `classes_` and `runtime_class_label` as defined in 7.2 and 7.3. It does not guess either.

### 11.1.1 Strict label comparison

- Accept Python `int` and NumPy integer types; compare by integer value.
- Reject `bool` and `numpy.bool_`, even though `True == 1`.
- Reject `str`, `float` and `None` where the Registry label is an integer. No coercion.
- A type mismatch is `LABEL_MISMATCH`.

## 11.2 Accepted artifact

```text
runtime classes_ = [0, 1]
EXTRACTION_INDEX = 1
runtime_class_label = 1
Registry positive_class_label = 1
Registry positive_class_index = 1
positive_class_semantics = UP
negative_class_semantics = NOT_UP
```

The numeric value `1` is not itself proof of UP. Only the verified Registry record is.

The runtime `classes_` check is a **consistency check, not evidence**. XGBoost synthesizes `classes_` and does not prove the original training class array was serialized in the artifact. This limitation must remain visible in the report.

## 11.3 Probability interpretation

For a CD-verified artifact:

```text
p_up     = raw_probability
p_not_up = 1.0 - p_up
```

`p_down` is never populated with `p_not_up`. `SELL = not-UP`; it does not claim a guaranteed downward move.

## 11.4 Direction threshold

```text
BUY  if p_up > 0.5
SELL if p_up <= 0.5
```

No neutral band, no threshold adjustment, no calibration, no new decision rule.

## 11.5 Tie observability

```text
at_threshold = (p_up == DECISION_THRESHOLD)
```

| p_up | direction | at_threshold |
| ---: | --------- | ------------ |
| 0.73 | BUY       | false        |
| 0.51 | BUY       | false        |
| 0.50 | SELL      | true         |
| 0.49 | SELL      | false        |

`at_threshold` is diagnostic only. It must not change direction, create ABSTAIN, or activate downstream handling. For non-READY results it is None. Placement: see 5.2.

## 11.6 Floating-point complement

Tests for complementary values use approximate comparison with a documented tolerance of `1e-6`, which covers `float32` model output (for example `0.73` becoming `0.7300000190734863`). Do not require exact binary equality.

---

# 12. P0 — Status definitions

## 12.1 Statuses

READY, UNINTERPRETABLE, NOT_RUN, UNAVAILABLE, INVALID, ERROR, ABSTAIN (defined but unreachable). The legal field matrix is in 5.3.

## 12.2 UNINTERPRETABLE

Legal only when: inference succeeded, output structure is valid, the numeric probability is valid, **and** CD is unavailable, unverified, incomplete or mismatched for the exact artifact. It carries a valid `raw_probability` and no `p_up`, `p_not_up` or direction. It is not a generic error bucket.

## 12.3 ABSTAIN

ABSTAIN remains defined but unreachable. Stage B does not synthesize an ABSTAIN path. This is proven by static inspection (the adapter module has no ABSTAIN construction path; the enum member remains if the contract requires it), not by a runtime test.

## 12.4 Decision rejection

Decision rejection can never change PredictionStatus.

---

# 13. P0 — Time integrity

## 13.1 Clock injection

The adapter receives an injectable clock. The production default is a UTC clock; tests use a deterministic fake clock. No direct system-clock calls elsewhere in the adapter.

## 13.2 Semantics

`bar_time`: source market bar; tz-aware; normalized to UTC; naive values rejected (6.4).

`timestamp`: when the adapter created the result; tz-aware UTC; from the injected clock.

Never substitute prediction time for bar time.

## 13.3 Static check scope

"Direct system-clock call" means any call to `datetime.now`, `datetime.utcnow`, `datetime.today`, `time.time`, `time.time_ns`, `date.today`, or equivalents, outside the injected clock abstraction.

---

# 14. P0 — Failure isolation

1. Adapter failure must not interrupt unrelated non-ML management operations.
2. Must not mutate OANDA account state.
3. Must not modify open positions.
4. Must not modify SL/TP.
5. Must not change position sizing.
6. Must not submit orders.
7. Must not change scheduler cadence.
8. Must not alter model initialization policy.
9. Must not synthesize a fallback direction.
10. Must not fabricate a neutral ML vote.

The adapter returns a `PredictionResult` for inference-time failures. A naive `bar_time` is a caller error that raises (6.4); the caller is responsible for validating before invocation, so this cannot propagate from the adapter into unrelated management code in a correctly written caller.

No caller may reinterpret ERROR, INVALID, UNAVAILABLE or UNINTERPRETABLE as a trading direction.

---

# 15. P1 — Diagnostics

Diagnostics are supplementary only. Where available and permitted: status, reason, pair, timeframe, bar time, prediction timestamp, artifact and scaler SHA-256, Registry SHA-256, runtime class order, positive class index, runtime class label, raw probability, `at_threshold`, `cd_failure_cause`, feature fingerprint, exception type, safe failure context.

Do not log credentials or account secrets, dump entire feature arrays unnecessarily, store an invalid probability as a valid raw probability, use diagnostic text as status authority, or build a new monitoring dashboard or logging framework.

---

# 16. P0 — Required test matrix

All tests must be traceable to an acceptance criterion. No live OANDA account is required.

## 16.1 Core adapter tests

| ID    | Test                                                    | Expected                                                                            |
| ----- | ------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| B-T01 | Caller-side insufficient bars (stubbed caller)          | Adapter not invoked; `build_not_run_result` yields a legal NOT_RUN                |
| B-T02 | Model unavailable                                       | UNAVAILABLE / MODEL_NOT_USABLE                                                      |
| B-T03 | Required scaler missing                                 | UNAVAILABLE / MODEL_NOT_USABLE                                                      |
| B-T04 | Feature contract invalid                                | INVALID / FEATURE_CONTRACT_VIOLATION                                                |
| B-T05 | Unexpected inference exception                          | ERROR / EXECUTION_ERROR                                                             |
| B-T06 | Malformed output rank or shape                          | INVALID / PREDICTION_OUTPUT_MALFORMED                                               |
| B-T07 | Probability column count differs from `len(classes_)` | INVALID / MALFORMED                                                                 |
| B-T08 | `classes_` missing, wrong length, or duplicate values | INVALID / MALFORMED                                                                 |
| B-T09 | NaN probability                                         | INVALID; `raw_probability=None`                                                   |
| B-T10 | Infinite probability                                    | INVALID; `raw_probability=None`                                                   |
| B-T11 | Probability below 0                                     | INVALID; `raw_probability=None`                                                   |
| B-T12 | Probability above 1                                     | INVALID; `raw_probability=None`                                                   |
| B-T13 | Valid extraction, no matching Registry record           | UNINTERPRETABLE; `raw_probability` populated; `cd_failure_cause=RECORD_MISSING` |
| B-T14 | Exact artifact and scaler hashes match Registry         | CD record consumed                                                                  |
| B-T15 | Artifact hash mismatch                                  | UNINTERPRETABLE; no CD inheritance                                                  |
| B-T16 | Artifact hash unavailable                               | UNINTERPRETABLE; `cd_failure_cause=HASH_UNAVAILABLE`                              |
| B-T17 | Verified UP, `p_up=0.73`                              | READY; BUY; `p_not_up ≈ 0.27` (tol 1e-6)                                         |
| B-T18 | Verified UP, `p_up=0.51`                              | READY; BUY                                                                          |
| B-T19 | Verified UP, `p_up=0.50`                              | READY; SELL; `at_threshold=True`                                                  |
| B-T20 | Verified UP, `p_up=0.49`                              | READY; SELL                                                                         |
| B-T21 | Positive class label is numeric 1                       | Numeric label 1 preserved                                                           |
| B-T22 | Any non-READY result                                    | No usable direction                                                                 |
| B-T23 | READY + NONE construction                               | Rejected by invariant                                                               |
| B-T24 | `p_down`                                              | Never populated with the not-UP complement                                          |
| B-T25 | Formal identity unavailable                             | `model_id`, `release_id`, `feature_contract_id` are None                      |
| B-T26 | Injected clock                                          | Deterministic UTC timestamp                                                         |
| B-T27 | Adapter runtime failure                                 | Unrelated management path unaffected (diff and isolation evidence)                  |
| B-T28 | Existing `generate_signal()`                          | Signature and behaviour unchanged (diff and regression evidence)                    |
| B-T29 | C-1 through C-7                                         | No migration or behaviour change (diff evidence)                                    |
| B-T30 | ABSTAIN                                                 | Static check: no adapter construction path                                          |

## 16.2 Type, order, time, registry and identity edge cases

| ID    | Test                                                                                                                         | Expected                                                          |
| ----- | ---------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| B-T31 | Python `bool` probability                                                                                                  | Rejected                                                          |
| B-T32 | NumPy boolean scalar                                                                                                         | Rejected                                                          |
| B-T33 | NumPy integer/float scalar (incl. float32)                                                                                   | Accepted if finite and in range                                   |
| B-T34 | NumPy 0-D array                                                                                                              | Rejected                                                          |
| B-T35 | NumPy 1-D/2-D array as scalar                                                                                                | Rejected                                                          |
| B-T36 | `Decimal` (finite, in range)                                                                                               | Rejected                                                          |
| B-T37 | `Decimal` NaN or Infinity                                                                                                  | Rejected                                                          |
| B-T38 | Complex number                                                                                                               | Rejected                                                          |
| B-T39 | String numeric value                                                                                                         | Rejected                                                          |
| B-T40 | Unsupported custom numeric object                                                                                            | Rejected                                                          |
| B-T41 | Multiple simultaneous faults (model unavailable + input invalid)                                                             | UNAVAILABLE / MODEL_NOT_USABLE                                    |
| B-T42 | Unknown inference exception                                                                                                  | ERROR                                                             |
| B-T43 | Known model-usability exception                                                                                              | UNAVAILABLE                                                       |
| B-T44 | Naive `bar_time`                                                                                                           | Raises before inference                                           |
| B-T45 | Non-UTC aware `bar_time`                                                                                                   | Normalized to UTC                                                 |
| B-T46 | `PredictionResult` mutation attempt                                                                                        | Rejected                                                          |
| B-T47 | Registry duplicate artifact entries                                                                                          | Fail closed (RECORD_DUPLICATE)                                    |
| B-T48 | Registry malformed or missing                                                                                                | Fail closed (REGISTRY_UNAVAILABLE)                                |
| B-T49 | Loader consumes the hashed bytes: swap the on-disk file after the single read but before load completes (injected read hook) | Identity hash matches bytes actually loaded; swapped file ignored |
| B-T50 | Registry revision evidence                                                                                                   | Registry SHA-256 recorded; Git revision in report                 |

## 16.3 CD binding and ordering

| ID    | Test                                                               | Expected                                                |
| ----- | ------------------------------------------------------------------ | ------------------------------------------------------- |
| B-T51 | Registry `positive_class_index` ≠ 1                             | UNINTERPRETABLE; INDEX_MISMATCH; no column re-selection |
| B-T52 | Registry label 1, runtime label 0 (for example `classes_=[1,0]`) | UNINTERPRETABLE; LABEL_MISMATCH                         |
| B-T53 | Runtime label `True` against Registry label 1                    | UNINTERPRETABLE; LABEL_MISMATCH                         |
| B-T54 | Runtime label `"1"` or `1.0`                                   | UNINTERPRETABLE; LABEL_MISMATCH                         |
| B-T55 | Registry `decision` ≠ VERIFIED (for example REVOKED)            | UNINTERPRETABLE; DECISION_NOT_VERIFIED                  |
| B-T56 | Registry unsupported semantics                                     | UNINTERPRETABLE; SEMANTICS_UNSUPPORTED                  |
| B-T57 | Candidate column valid, complementary column NaN                   | INVALID / PREDICTION_INVALID_PROBABILITY                |
| B-T58 | Row sum ≠ 1 beyond tolerance (if 7.3.5 retained)                  | INVALID / MALFORMED                                     |
| B-T59 | Spy on the Registry accessor with a fault injected at step 4 or 5  | Registry accessor not called                            |
| B-T60 | Invalid candidate and missing Registry record                      | INVALID wins over UNINTERPRETABLE                       |

## 16.4 Loader binding

| ID    | Test                                             | Expected                                                                          |
| ----- | ------------------------------------------------ | --------------------------------------------------------------------------------- |
| B-T61 | Artifact bytes altered by one bit                | Different SHA-256; no CD match                                                    |
| B-T62 | Malformed or truncated artifact bytes            | Load failure; no identity produced; adapter yields UNAVAILABLE / MODEL_NOT_USABLE |
| B-T63 | Attempt to reassign identity fields              | Rejected                                                                          |
| B-T64 | Identity hash not 64-char lowercase hex          | Rejected at construction                                                          |
| B-T65 | Adapter reads the artifact path (filesystem spy) | No read                                                                           |
| B-T75 | Scaler hash mismatch (artifact hash matches)     | UNINTERPRETABLE; no CD match                                                      |
| B-T76 | Registry record lacks `scaler_sha256`          | Fail closed                                                                       |

## 16.5 Result integrity

| ID    | Test                                                              | Expected                                     |
| ----- | ----------------------------------------------------------------- | -------------------------------------------- |
| B-T66 | READY with `p_up=0.4, direction=BUY`                            | Rejected                                     |
| B-T67 | READY with `raw_probability != p_up`                            | Rejected                                     |
| B-T68 | UNINTERPRETABLE with non-None `p_up`, `p_not_up` or direction | Rejected                                     |
| B-T69 | Non-None `p_down` on any status                                 | Rejected                                     |
| B-T70 | Status/reason pair outside 5.5                                    | Rejected                                     |
| B-T71 | Mutating `diagnostics` after construction                       | Rejected                                     |
| B-T72 | Non-serializable value in diagnostics                             | Rejected at construction                     |
| B-T73 | Forced internal invariant violation inside adapter                | Fallback ERROR result returned; no exception |
| B-T74 | `at_threshold` population per 5.3                               | Matches matrix                               |

## 16.6 Multi-fault precedence

B-T41 is mandatory. Add at least one more combination (for example structure malformed + Registry missing → INVALID, B-T60) so the fixed order is proven by more than one pair.

## 16.7 Static checks

- No ABSTAIN result-construction path in the adapter.
- No strategy or order-execution imports or calls in the adapter.
- No mutation of the frozen `PredictionResult`.
- No direct system-clock calls (13.3).
- No fallback probability or direction.
- No guessed class-label default (for example no `positive_class_label = "UP"`).

## 16.8 Test integrity

- Do not weaken tests to obtain passing results.
- Do not count skipped tests as passed.
- Do not claim mocked CD tests prove actual artifact semantics.
- Do not claim stubbed inference proves real model loading.
- Report dependency-gated tests separately.
- Use the exact accepted artifact for artifact-specific integration evidence where feasible.
- Tests never write to the production Registry.

---

# 17. P0 — Legacy compatibility

Stage B is additive.

## 17.1 Existing interfaces

Do not change the `StrategyEngine.generate_signal()` signature, the `Optional[Signal]` return semantics, `Signal` fields, caller expectations, strategy thresholds, or scoring behaviour. `Signal` remains a Decision output; `PredictionResult` remains a Prediction output.

## 17.2 Consumer boundaries

| Consumer                       | Stage B requirement |
| ------------------------------ | ------------------- |
| C-1 Step 4 multi-TF confluence | Unchanged           |
| C-2 Step 7 scoring feed        | Unchanged           |
| C-3 Open-reason log            | Unchanged           |
| C-4 attribution live hook      | Unchanged           |
| C-5 attribution data bridge    | Unchanged           |
| C-6 `should_close()`         | Dormant             |
| C-7 `select_signals()`       | Dormant             |

No consumer migration, fallback removal, new ML Vote, or Entry Authorization change. A non-READY result is never converted into BUY, SELL, a default probability, a neutral vote or a synthesized XGB vote.

## 17.3 Mechanical regression evidence

"Unchanged" is proven mechanically:

1. Git diff file list.
2. `git diff --stat`.
3. Function-level diff inspection.
4. `generate_signal()` has no modified lines.
5. C-1 through C-7 consumer implementations have no modified lines.
6. Relevant regression test results.

If an unavoidable change to a protected consumer appears, STOP and obtain separate approval.

---

# 18. Forbidden scope

Entry Authorization, Step 7 scoring, ML Vote activation, ML weights or thresholds, fallback removal or replacement, exit logic, SL/TP, position sizing, OANDA order flow, scheduler cadence, training target changes, retraining, artifact regeneration or replacement, feature engineering, feature contract redesign, probability calibration, MC scoring, MC cache changes, Strength scoring, FINAL weights, consumer migration, **production loader modification**, strategy decision refactoring, `docs/Development_plan.md`, Phase 3.2–3.6, broad refactoring, unrelated cleanup, commit creation, deployment.

Do not modify the authoritative contract, training scripts, or model artifacts. Do not use Stage B to redesign unrelated architecture.

---

# 19. File modification allowlist

## 19.1 Permitted

1. New Prediction Adapter module (mandatory; path chosen in the implementation map).
2. New `config/model_cd_registry.json`, populated with the approved production record only (4.4).
3. New focused adapter test modules and test fixtures.

Nothing else. The optional loader and caller changes from v2 are removed (3.4, 9.2).

The exact allowlist must be approved before implementation.

## 19.2 Protected

`docs/Development_plan.md`, training scripts, existing model artifacts, the Phase 3.0 initialization path, strategy scoring consumers, Entry Authorization consumers, OANDA execution modules, scheduler logic, attribution consumers, unrelated configuration, `run.env`.

If implementation requires a protected-file change, STOP.

---

# 20. Acceptance criteria

Every mandatory criterion must pass.

## A. Architecture

| ID   | Criterion                                             |
| ---- | ----------------------------------------------------- |
| B-01 | One independent new Prediction Adapter module exists. |
| B-02 | Adapter produces structured PredictionResult.         |
| B-03 | PredictionResult is distinct from Signal.             |
| B-04 | Existing inference path is reused.                    |
| B-05 | No second feature pipeline is introduced.             |
| B-06 | Caller owns bars-count precondition.                  |
| B-07 | ModelStatus and PredictionStatus remain separate.     |
| B-08 | Adapter contains no Decision or Authorization logic.  |

## B. Artifact identity and CD

| ID   | Criterion                                                                               |
| ---- | --------------------------------------------------------------------------------------- |
| B-09 | Artifact hash identifies the exact bytes loaded (in `load_model_with_identity`).      |
| B-10 | Hash and loaded model instance are bound immutably (binding cannot be rebound).         |
| B-11 | No per-prediction disk rehash occurs.                                                   |
| B-12 | CD Registry is version-controlled.                                                      |
| B-13 | Registry is read-only at runtime and loaded once at startup.                            |
| B-14 | Registry records full artifact and scaler SHA-256.                                      |
| B-15 | Registry provenance is recorded.                                                        |
| B-16 | Exact hash equality (artifact and scaler) is required.                                  |
| B-17 | Missing, duplicate, malformed or non-VERIFIED CD records fail closed.                   |
| B-18 | CD cannot transfer between artifacts.                                                   |
| B-19 | Adapter cannot self-certify CD; production record authored from accepted evidence only. |
| B-20 | Runtime class order is not misrepresented as artifact-serialized metadata.              |
| B-21 | CD evidence limitations remain documented.                                              |
| B-22 | Stage A.3 CD-OPEN-4 hardening requirements are implemented.                             |

## C. Result integrity and probability

| ID   | Criterion                                                            |
| ---- | -------------------------------------------------------------------- |
| B-23 | PredictionResult is immutable.                                       |
| B-24 | Illegal result combinations are rejected at construction.            |
| B-25 | Status and reason are always compatible.                             |
| B-26 | Probability output structure is validated.                           |
| B-27 | Accepted scalar types are explicitly controlled.                     |
| B-28 | Bool, Decimal, arrays, complex and unsupported objects are rejected. |
| B-29 | NaN, infinity and out-of-range values are rejected.                  |
| B-30 | Invalid probability is not retained as `raw_probability`.          |
| B-31 | `raw_probability` remains neutral until CD permits interpretation. |
| B-32 | Actual positive class label is captured without guessing.            |
| B-33 | UP/not-UP interpretation is correct.                                 |
| B-34 | `p_down` is not misused as `p_not_up`.                           |
| B-35 | BUY/SELL threshold and tie rule are implemented exactly.             |
| B-36 | `at_threshold` is diagnostic only.                                 |
| B-37 | Complementary probability tests use approximate comparison.          |
| B-38 | UNINTERPRETABLE is used only for valid inference with unresolved CD. |

## D. Status, exception and time integrity

| ID   | Criterion                                                                                  |
| ---- | ------------------------------------------------------------------------------------------ |
| B-39 | Validation order is fixed.                                                                 |
| B-40 | First failed condition determines status.                                                  |
| B-41 | Closed exception mapping is documented from actual code.                                   |
| B-42 | Unknown inference exceptions map to ERROR.                                                 |
| B-43 | Inference-time failures always return PredictionResult.                                    |
| B-44 | Only pre-inference API contract errors may raise.                                          |
| B-45 | `build_not_run_result` exists and constructs a legal NOT_RUN without invoking inference. |
| B-46 | ABSTAIN remains unreachable in adapter.                                                    |
| B-47 | Clock is injectable.                                                                       |
| B-48 | `bar_time` must be timezone-aware.                                                       |
| B-49 | `timestamp` and `bar_time` are distinct UTC timestamps.                                |

## E. Isolation and compatibility

| ID   | Criterion                                                          |
| ---- | ------------------------------------------------------------------ |
| B-50 | Adapter failures do not interrupt unrelated management operations. |
| B-51 | No OANDA account or trading state is modified.                     |
| B-52 | No fallback direction or default probability is fabricated.        |
| B-53 | `generate_signal()` signature is unchanged.                      |
| B-54 | Signal structure and behaviour are unchanged.                      |
| B-55 | C-1 through C-7 are not migrated.                                  |
| B-56 | Entry Authorization is unchanged.                                  |
| B-57 | ML Vote is unchanged.                                              |

## F. Tests and scope integrity

| ID   | Criterion                                                                              |
| ---- | -------------------------------------------------------------------------------------- |
| B-58 | All mandatory B-T01 through B-T76 tests pass or have an explicitly approved exception. |
| B-59 | Static checks pass.                                                                    |
| B-60 | Relevant Phase 3.0 tests pass.                                                         |
| B-61 | Relevant inference regression tests pass.                                              |
| B-62 | Relevant strategy regression tests pass.                                               |
| B-63 | Test results distinguish passed, failed and skipped.                                   |
| B-64 | Only approved files are modified.                                                      |
| B-65 | No training script or model artifact is changed.                                       |
| B-66 | No trading behaviour is changed.                                                       |
| B-67 | `docs/Development_plan.md` remains untouched.                                        |
| B-68 | No Stage C consumer migration occurs.                                                  |
| B-69 | No commit is created.                                                                  |
| B-70 | No deployment is performed.                                                            |

## G. Additions in v3

| ID   | Criterion                                                                                      |
| ---- | ---------------------------------------------------------------------------------------------- |
| B-71 | The production loader and Phase 3.0 initialization path are not modified.                      |
| B-72 | Scaler identity is bound and required for CD match.                                            |
| B-73 | The CD Registry is not read before output structure and numeric validity are established.      |
| B-74 | An internal invariant violation yields the fallback ERROR result, never an escaping exception. |
| B-75 | Class-label comparison is strict and type-aware.                                               |
| B-76 | `diagnostics` is immutable and JSON-safe.                                                    |
| B-77 | All **[CONTRACT-CONFIRM]** items are resolved and recorded before implementation.        |

Any failed mandatory criterion means: **Stage B Status: NOT COMPLETE.** Do not claim completion based on partial implementation.

---

# 21. Acceptance traceability matrix

| Acceptance IDs | Required evidence                                                              |
| -------------- | ------------------------------------------------------------------------------ |
| B-01–B-08     | Module inspection, architecture review, import-boundary checks                 |
| B-09–B-11     | B-T49, B-T61–B-T65, byte-snapshot evidence                                    |
| B-12–B-15     | Registry schema validation, Git revision and SHA-256, B-T50                    |
| B-16–B-21     | B-T13–B-T16, B-T47–B-T48, B-T51–B-T56, B-T75–B-T76, CD evidence inspection |
| B-22           | Stage A.3 CD-OPEN-4 mapping plus dedicated hardening tests                     |
| B-23–B-25     | Frozen dataclass and invariant tests, B-T23, B-T46, B-T66–B-T72               |
| B-26–B-30     | B-T06–B-T12, B-T31–B-T40, B-T57–B-T58                                       |
| B-31–B-38     | B-T13, B-T17–B-T24, B-T74                                                     |
| B-39–B-40     | B-T41, B-T59–B-T60, validation-order inspection                               |
| B-41–B-44     | Exception mapping review, B-T05, B-T42, B-T43, B-T44, B-T73                    |
| B-45           | B-T01 and `build_not_run_result` unit tests                                  |
| B-46           | B-T30 static inspection                                                        |
| B-47–B-49     | B-T26, B-T44, B-T45                                                            |
| B-50–B-52     | B-T27, isolation tests, execution-boundary inspection                          |
| B-53–B-57     | B-T28, B-T29, Git diff and regression evidence                                 |
| B-58–B-63     | Test execution report, static check report, regression report                  |
| B-64–B-70     | Git diff, `git diff --stat`, protected-file checks, repository status        |
| B-71           | Git diff showing no changes to the loader or Phase 3.0 files                   |
| B-72           | B-T75, B-T76, identity construction tests                                      |
| B-73           | B-T59, B-T60                                                                   |
| B-74           | B-T73                                                                          |
| B-75           | B-T52–B-T54                                                                   |
| B-76           | B-T71, B-T72                                                                   |
| B-77           | Preflight record                                                               |

A criterion without a verifiable evidence source is not accepted. A test that was not executed cannot be marked PASS.

---

# 22. Required completion report

## 22.1 Implementation summary

Adapter module path, entry point and signature, PredictionResult fields and invariants, existing inference path reused, files changed, files inspected but not changed.

## 22.2 Artifact identity evidence

Exact artifact and scaler SHA-256, source of loaded bytes, `load_method`, hash computation point, proof the loader consumed the hashed bytes (B-T49), immutable binding, evidence that per-prediction rehash is not used.

State explicitly: **identity binding is proven in the new loader and tests, not on the production path (Stage C).**

## 22.3 CD Registry evidence

Registry path, Git revision, SHA-256, matching record, positive class index and label, UP/not-UP semantics, evidence record reference, missing/mismatch/duplicate/non-VERIFIED test results, and the CD evidence limitations (including that runtime `classes_` is a consistency check, not proof).

## 22.4 Exception and validation evidence

Full closed exception mapping with source locations, unknown-exception behaviour, validation order, multi-fault precedence results (B-T41, B-T60), proof that inference-time failures return a PredictionResult, and the fallback-result test (B-T73).

## 22.5 Probability evidence

Valid extraction, invalid type rejection, invalid numeric rejection, actual class mapping, UP/not-UP interpretation, tie handling, `at_threshold`, `p_down` handling, approximate-complement tests.

## 22.6 Status evidence

Concrete test evidence for READY, UNINTERPRETABLE, NOT_RUN, UNAVAILABLE, INVALID, ERROR. State explicitly: `ABSTAIN remains defined but unreachable in Stage B.`

## 22.7 Test report

Per group: exact command, passed, failed, skipped, dependency limitations, environment, relevant regression results. Skipped tests are never reported as passed.

## 22.8 Compatibility evidence

Confirm unchanged: `generate_signal()` signature, Signal structure, C-1 through C-7, Entry Authorization, ML Vote, MC, Strength, FINAL weights, OANDA execution, scheduler, production loader. Include `git diff --stat`, the changed-file list, and function-level diff inspection.

## 22.9 Repository integrity

Repository root, branch, HEAD before and after, `git status --short` before and after, exact diff file list, confirmation that pre-existing unrelated changes were preserved, no commit, no deployment.

## 22.10 CONTRACT-CONFIRM outcomes

For each **[CONTRACT-CONFIRM]** item (5.2 `at_threshold`, 5.3 `positive_class_label` in UNINTERPRETABLE, 7.3.5 row-sum rule, 7.4 diagnostic vocabulary): the contract's position and the resulting implementation.

---

# 23. Stop conditions

Stop immediately and report if:

1. Stage A.3 is not accepted.
2. Final contract semantics are ambiguous or conflict irreconcilably with this spec.
3. User implementation authorization is absent.
4. The exact artifact (or scaler) bytes used by the loader cannot be established.
5. Hash-to-model binding cannot be demonstrated.
6. CD Registry provenance cannot be established, or the approved production record is unavailable.
7. Positive class mapping cannot be reproduced.
8. Exception mapping cannot be grounded in actual code.
9. Inference-time failure cannot be contained without changing unrelated behaviour.
10. Implementation requires modifying protected consumers or the production loader.
11. Implementation requires changing training targets or artifacts.
12. Implementation requires changing Entry Authorization or trading behaviour.
13. An additional file outside the approved allowlist is required.
14. Existing user work would be overwritten or disturbed.

Do not bypass a stop condition by weakening the contract. Do not invent a new status or reason to avoid reporting a gap. Do not silently expand scope.

---

# 24. Final authorization boundary

Successful Stage B means: PredictionResult exists and is immutable; status and reason are deterministic; probability validation is explicit; artifact identity is bound to loaded bytes in the new loader; CD is version-controlled and exact-artifact-specific; UP/not-UP semantics are correct; ties are observable; failures are contained; existing strategy and trading behaviour are unchanged.

Successful Stage B does **not** mean: consumers use PredictionResult; ML Vote is activated or changed; Step 7 is modified; Entry Authorization is changed; C-1 through C-7 are migrated; the production loader produces identities; the bot trades differently; Stage C has started; Stage D verification is complete; controlled activation is approved.

**Stage B completion is not Stage C authorization.**

After the completion report, stop. Wait for separate explicit approval before consumer migration, production loader wiring, authorization changes, or any behaviour-changing work.

---

# Appendix A — Changes from v2

| Area                                        | v2                                                                       | v3                                                                                                              |
| ------------------------------------------- | ------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------- |
| Extraction vs CD ordering                   | Probability extracted before CD lookup, with the column source undefined | Fixed structural `EXTRACTION_INDEX=1`; Registry read only at step 6 and must agree with extraction (7.2–7.4) |
| Loader scope                                | Optional loader change needing separate approval                         | New `load_model_with_identity` only; production loader untouched; wiring is Stage C (3.4)                     |
| Scaler                                      | Not covered                                                              | Hashed with the same lifecycle; required for CD match (3.6, 4.2)                                                |
| `at_threshold`                            | Top-level field                                                          | Contract-governed; diagnostics if contract is silent (5.2)                                                      |
| `positive_class_label` in UNINTERPRETABLE | Unspecified                                                              | None unless contract populates it (5.3)                                                                         |
| NOT_RUN / B-T01                             | "Caller-side test" with no caller change                                 | Helper plus unit tests; caller wiring is Stage C (9.2)                                                          |
| Registry                                    | Schema only                                                              | Startup load, closed `decision` set, authorship rule, runtime SHA-256 (4.3–4.5)                              |
| Label comparison                            | Unspecified                                                              | Strict, type-aware (11.1.1)                                                                                     |
| Never-raises rule                           | Gaps                                                                     | `Exception` only; invariant fallback result (5.6, 6.3)                                                        |
| `Decimal`                                 | Accepted                                                                 | Rejected (10.3)                                                                                                 |
| `diagnostics`                             | Not frozen                                                               | `MappingProxyType`, JSON-safe, bounded (5.1)                                                                  |
| Row-sum check                               | None                                                                     | Added, **[CONTRACT-CONFIRM]** (7.3.5)                                                                     |
| Tests                                       | B-T01–B-T50                                                             | B-T01–B-T76                                                                                                    |
| Acceptance                                  | B-01–B-70                                                               | B-01–B-77                                                                                                      |

# Appendix B — Open items to close before G-A3-11

| Item                                        | Default if contract is silent                             |
| ------------------------------------------- | --------------------------------------------------------- |
| `at_threshold` placement                  | Diagnostics key                                           |
| `positive_class_label` in UNINTERPRETABLE | None; runtime label in diagnostics                        |
| Row-sum check (7.3.5)                       | Include with `ROW_SUM_TOLERANCE=1e-5`                   |
| `cd_failure_cause` diagnostic vocabulary  | Allowed in diagnostics only                               |
| Scaler SHA-256 in the accepted CD evidence  | Required; if absent from A.3 evidence, STOP (gate G-A3-9) |
