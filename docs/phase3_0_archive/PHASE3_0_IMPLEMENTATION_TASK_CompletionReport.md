I've completed the read-only **Stage A — Bounded source confirmation**. No files were modified. Here is the evidence report and the required Gate A checkpoint.

## A. Repository state (preflight)

| Item | Value |
|---|---|
| Root | `/Users/liqin/projects/ai_training_cnn` |
| Branch | `v2026c` ✔ (matches target) |
| HEAD | `ddba734` ("phase3 rdesign v1.2") |
| Reviewed baseline | `e13c3e4` — HEAD is **2 commits ahead** |
| Working tree | Only unrelated doc changes: deleted `README_DOC.md`/`README_doc.md`, untracked `docs/Bot_Workflow.md`, `docs/PHASE3_0_IMPLEMENTATION_TASK.md`. No target runtime file touched. |
| Python | 3.12.16 |
| Tests | `tests/` present (no pytest/unittest runner config found); `test.sh` exists |

Baseline delta that matters: commit `3bec4af` ("v685->fx_trade.bot") **renamed the live bot** to [fx_trade_bot.py](file:///Users/liqin/projects/ai_training_cnn/fx_trade_bot.py); `fx_trade_bot_v685.py` is a byte-identical copy (verified via `diff`). The `ensure_model()` path and entry/exit logic are unchanged from baseline.

## B. Actual runtime entrypoint

The design's candidate `scheduled_runner_v3.py` **does not exist in this repository** — it belongs to a separate project (`gemini_ai`, per [crontab](file:///Users/liqin/projects/ai_training_cnn/crontab#L2-L4)). Cron files here reference non-existent `fx_trade_bot_v685_1.py` / `fx_trade_bot_v683.py`, so they are **stale**.

The real entrypoint is:

[fx_trade_bot.py → `__main__`](file:///Users/liqin/projects/ai_training_cnn/fx_trade_bot.py#L2942-L2951) → [`main()`](file:///Users/liqin/projects/ai_training_cnn/fx_trade_bot.py#L1667)

## C. `ensure_model()` call path

```
__main__ (L2942)
└─ try: main()
   └─ forex_market_closed? (L1684)
   └─ ensure_model(...)                      ← L1700  ██ FAILURE HERE ABORTS THE WHOLE CYCLE
      └─ fx_trade_bot_ml.ensure_model()       (fx_trade_bot_ml.py L11)
         ├─ artifacts missing → TRAIN        (L31-63) → ModelWrapper.fit() (data_pipeline L520) → save() (L582)
         ├─ stale (>retrain_every_n_days) → TRAIN           ↑ same
         ├─ else ModelWrapper.load()          (L67)  → data_pipeline L601
         └─ inject strat_engine.model/scaler/features (L74-76)
   └─ MAX_OPEN EARLY-GATE (L1712) ── may run Step 5 only (L1787-1858)
   └─ Step 1 Strength → Step 2 Fetch → Step 2.5 D-Gate → Step 3 MC → Step 4 Confluence (L2117)
   └─ Step 5 Dynamic Exit (L2198)          ← existing-position mgmt
   └─ Step 6 owned snapshot (L2229) / _revise_owned_position (L2327)
   └─ Step 7 score + quick-flip + entry (L2423) → order submit (L2837)
   └─ except Exception: log + telegram + **raise** (L2948-2950)
```

**Confirmed core risk (P0-03):** `ensure_model()` is called at [L1700](file:///Users/liqin/projects/ai_training_cnn/fx_trade_bot.py#L1700-L1710), *before* every management step. If it raises — `RuntimeError` ("No training data", [fx_trade_bot_ml.py L58](file:///Users/liqin/projects/ai_training_cnn/fx_trade_bot_ml.py#L58)), `FileNotFoundError` / `InferenceFeatureError` from load ([data_pipeline.py L646](file:///Users/liqin/projects/ai_training_cnn/data_pipeline.py#L646)) — the exception propagates through the top-level handler ([L2942-2950](file:///Users/liqin/projects/ai_training_cnn/fx_trade_bot.py#L2942-L2950)) which **re-raises**. Step 5 / owned-position management never runs.

## D. Branch classification

| Branch | Lines | Class | Evidence |
|---|---|---|---|
| MAX_OPEN EARLY-GATE (incl. minimal Step 5) | [1712–1858](file:///Users/liqin/projects/ai_training_cnn/fx_trade_bot.py#L1712-L1858) | **ML_INDEPENDENT** | ATRA `DynamicPositionManager` only; no model call |
| Step 5 Dynamic Exit | [2198–2227](file:///Users/liqin/projects/ai_training_cnn/fx_trade_bot.py#L2198-L2227) | **ML_INDEPENDENT** | `dyn_mgr.update_all`, ATR/time only |
| Owned positions + `_revise_owned_position` | [2229–2421](file:///Users/liqin/projects/ai_training_cnn/fx_trade_bot.py#L2229-L2421) | **ML_INDEPENDENT** | OANDA trade data + SL zone only |
| QUICK-FLIP | [2493–2528](file:///Users/liqin/projects/ai_training_cnn/fx_trade_bot.py#L2493-L2528) | **ML_INDEPENDENT** | strength gap + MC p_up only |
| Multi-TF confluence (Step 4) | [2117–2149](file:///Users/liqin/projects/ai_training_cnn/fx_trade_bot.py#L2117-L2149) | **ML_REQUIRED** | `strat_engine.generate_signal` ×3; exceptions `contextlib.suppress`ed → all-fail ⇒ `passes=False` ⇒ pair blocked (fail-safe) |
| Step 7 score / entry | [2423–2732](file:///Users/liqin/projects/ai_training_cnn/fx_trade_bot.py#L2423-L2732) | **ML_OPTIONAL** | XGB is one of 3 voters + a weighted score component |
| Order submission | [2768–2895](file:///Users/liqin/projects/ai_training_cnn/fx_trade_bot.py#L2768-L2895) | **ML_INDEPENDENT** | decision already made upstream |

## E. Entry-authorization boundary (Section 4.5 checkpoint)

**This is the exact path where unavailable ML can influence a new entry — it is unverified-approved behavior and I will not touch it without your approval.**

| Required item | Finding |
|---|---|
| **Current behavior** | When ML is unavailable, `generate_signal()` returns `None` ([strategy_decision.py L139-153](file:///Users/liqin/projects/ai_training_cnn/strategy_decision.py#L139-L153)). Bot sets `_sig_model_missing=True`, `prob_raw=None` ([L2556-2557](file:///Users/liqin/projects/ai_training_cnn/fx_trade_bot.py#L2556-L2557)). |
| **Reachability** | `main()` L2568 → `calc_weighted_score` ([L1508](file:///Users/liqin/projects/ai_training_cnn/fx_trade_bot.py#L1508)) |
| **Current vote/score** | XGB abstains from the **direction vote** (`xgb_dir="NEUTRAL"`, [L1525-1532](file:///Users/liqin/projects/ai_training_cnn/fx_trade_bot.py#L1525-L1532)) — good. **But** the XGB **score component `X` is substituted**: `X = S*0.3 + R*0.3` ([L1628-1629](file:///Users/liqin/projects/ai_training_cnn/fx_trade_bot.py#L1628-L1629)) and still contributes `X*W_X` to `FINAL` ([L1652](file:///Users/liqin/projects/ai_training_cnn/fx_trade_bot.py#L1652)). With `REQUIRE_DIRECTION_CONSENSUS=True` / `CONSENSUS_THRESHOLD=2` ([L879-880](file:///Users/liqin/projects/ai_training_cnn/fx_trade_bot.py#L879-L880)), Strength+MC agreeing alone yields consensus ⇒ **an ML-dependent entry can be authorized on a synthetic X**. |
| **Proposed behavior** | Per Section 0.2 #3 / AC-06: with ML `UNAVAILABLE`, do not let ML-dependent entry proceed (e.g. suppress Step 7 entry while preserving Steps 5/6 + owned mgmt). Exact minimal diff TBD with you. |
| **Healthy-path impact** | With a valid model, `X` uses the real probability ([L1625-1627](file:///Users/liqin/projects/ai_training_cnn/fx_trade_bot.py#L1625-L1627)); unchanged. |
| **Tests** | P3T-09/16/18/19 (Section 8). |
| **Diff** | Not yet written — awaiting approval. |

## F. Runtime artifact write-path inventory

| Write path | Location | Trigger |
|---|---|---|
| `ModelWrapper.fit()` → `self.save()` | [data_pipeline.py L520-554](file:///Users/liqin/projects/ai_training_cnn/data_pipeline.py#L520-L554) | live `ensure_model` when artifacts missing/stale ([fx_trade_bot_ml.py L42-63](file:///Users/liqin/projects/ai_training_cnn/fx_trade_bot_ml.py#L42-L63)) |
| `ModelWrapper.save()` writes 4 files | [data_pipeline.py L582-599](file:///Users/liqin/projects/ai_training_cnn/data_pipeline.py#L582-L599) | `.json`, `scaler.joblib`, `.features.json`, `.cfg.json` |
| **Legacy `load()` fallback re-saves** | [data_pipeline.py L630-644](file:///Users/liqin/projects/ai_training_cnn/data_pipeline.py#L630-L644) | loads `.pkl` then calls `self.save()` — silent re-publish (Section 5.3 concern) |
| Offline trainer (must stay working) | [retrain_model.py](file:///Users/liqin/projects/ai_training_cnn/retrain_model.py#L229-L243) | cron `0 0 * * 1-5` |

`fx_trade_bot.py` itself has **no direct** `fit`/`save`/`joblib.dump` — writes are all indirect via `ensure_model`.

## G. Model path resolution

`MODEL_PATH = BASE_DIR / "trade_model_xgb.pkl"` ([L1242](file:///Users/liqin/projects/ai_training_cnn/fx_trade_bot.py#L1242)) — **hardcoded, identical for all 4 profiles**. No per-profile artifact path. Sibling artifacts derived by stem: `trade_model_xgb.json`, `scaler.joblib`, `trade_model_xgb.features.json`, `trade_model_xgb.cfg.json`. This directly bears on AC-12 (cross-host release visibility).

---

## Gate A — decision required

I found an **owner-approval boundary** (Section E) and a **control-flow defect** (Section C). Per the task's own rules (Sections 0.3, 4.5, Stage A "Gate A"), I must stop and get your direction before writing code.

Please confirm how you want me to proceed:

1. **Approve the entry-authorization contract** in Section E (what should happen when ML is `UNAVAILABLE` at entry), so I can implement Stage B–E; **or**
2. **Authorize only the non-boundary work first** — explicit ML status/reason, narrow failure isolation so Step 5/owned-position management survives an `ensure_model` failure, artifact-write protection, and host/release diagnostics — leaving entry authorization untouched; **or**
3. Something else (e.g. just a written Stage A report, or a different scope).

I have **not** modified any file. No live deployment is performed. If you approve option 1, I'll return the minimal diff for the entry path for your explicit sign-off before applying it, as Section 4.5 requires.

---

# Stage B–E implementation report (approved Option 2 — Entry Authorization frozen)

Scope executed exactly as approved: **Stage B → C → D → E**. No entry-authorization change. No real orders. No live deployment.

## 1. Stage status

| Stage | Work item | Status | Evidence |
|---|---|---|---|
| B — Runtime containment | Explicit ML status + failure reason; `ensure_model()` failure isolation | ✅ Done | [fx_trade_bot_ml.py](file:///Users/liqin/projects/ai_training_cnn/fx_trade_bot_ml.py#L33-L315), [fx_trade_bot.py](file:///Users/liqin/projects/ai_training_cnn/fx_trade_bot.py#L1699-L1731) |
| C — Artifact write protection | Block live training/publish; keep offline trainer writable | ✅ Done | [data_pipeline.py](file:///Users/liqin/projects/ai_training_cnn/data_pipeline.py#L53-L500) |
| D — Observability | host / profile / artifact path / hashes / status / reason | ✅ Done | `ModelInitResult.as_log_fields()` + `_record()` `[ML-INIT]` record |
| E — Regression tests | Healthy path + all failure paths + artifact immutability | ✅ Done | [test_phase3_runtime_containment.py](file:///Users/liqin/projects/ai_training_cnn/tests/test_phase3_runtime_containment.py) — 30 passed, 3 skipped |
| — Entry Authorization | **UNCHANGED** | ⛔ Frozen | §4.5 checkpoint approval withheld |

## 2. Precise diff

`git diff --numstat` (working tree vs `ddba734`):

```
30      0       data_pipeline.py
23      2       fx_trade_bot.py
281     50      fx_trade_bot_ml.py
23      2       fx_trade_bot_v685.py
```

`fx_trade_bot.py` and `fx_trade_bot_v685.py` remain **byte-identical** after the edit (`diff -q` → IDENTICAL); this is required because [launch_dual_bot.sh](file:///Users/liqin/projects/ai_training_cnn/launch_dual_bot.sh#L7) still launches `fx_trade_bot_v685.py` via the shared `fx_trade_bot_ml` module.

### 2.1 `fx_trade_bot_ml.py` — status contract + isolation (Stage B/D)

* `class ModelStatus` — `READY` / `UNAVAILABLE` / `INCOMPATIBLE` / `LOAD_FAILED` ([L33](file:///Users/liqin/projects/ai_training_cnn/fx_trade_bot_ml.py#L33)).
* `class ModelReason` — 11 distinct reason codes incl. `MODEL_MISSING`, `MODEL_STALE`, `MODEL_INCOMPATIBLE`, `MODEL_LOAD_EXCEPTION`, `SCALER_MISSING`, `FEATURE_CONTRACT_MISMATCH`, `LEGACY_FALLBACK_BLOCKED` ([L43](file:///Users/liqin/projects/ai_training_cnn/fx_trade_bot_ml.py#L43)).
* `@dataclass ModelInitResult` — `status/reason/detail/artifact_path/release_id/manifest_present/model_hash/scaler_hash/features_hash/cfg_hash/backend/host_id/profile/timestamp` + `ok` + `as_log_fields()`.
* `ensure_model(...) -> ModelInitResult` ([L173](file:///Users/liqin/projects/ai_training_cnn/fx_trade_bot_ml.py#L173)):
  * marks `model_wrapper.read_only = bool(live)` (defence-in-depth);
  * incomplete split → `UNAVAILABLE/MODEL_MISSING`; stale → `UNAVAILABLE/MODEL_STALE` (live does **not** retrain);
  * `load()` exception classified by exception **name**, so the module never imports the heavy stack: name ∉ `_EXPECTED_LOAD_ERRORS` → `logger.exception` + **re-raise** (unexpected errors stay visible, §4.4); `LiveArtifactWriteError` → `INCOMPATIBLE/LEGACY_FALLBACK_BLOCKED`; `_INCOMPATIBLE_ERRORS` → `INCOMPATIBLE/MODEL_INCOMPATIBLE`; else → `LOAD_FAILED/MODEL_LOAD_EXCEPTION`;
  * validation → `INCOMPATIBLE/FEATURE_CONTRACT_MISMATCH` or `SCALER_MISSING`;
  * READY → injects the **same** `model/scaler/feature_names` instances into `strat_engine` (wiring semantics unchanged from baseline).
* **Deliberately removed**: the draft `should_skip_signal_generation()` helper (would have altered entry behaviour). Absence is pinned by a test.

### 2.2 `fx_trade_bot.py` (+ identical `fx_trade_bot_v685.py`) — call-site (Stage B)

* Dropped `global model_wrapper, strat_engine` and the tuple-unpack `model_wrapper, strat_engine = ensure_model(...)`; `strat_engine` / `model_wrapper` are module-level globals ([L1240](file:///Users/liqin/projects/ai_training_cnn/fx_trade_bot.py#L1240), [L1243](file:///Users/liqin/projects/ai_training_cnn/fx_trade_bot.py#L1243)) and are mutated in place — identical to baseline wiring.
* New call site [L1699–1731](file:///Users/liqin/projects/ai_training_cnn/fx_trade_bot.py#L1699-L1731): `ml_init = ensure_model(..., live=True, profile=PROFILE_NAME)`, then log READY or a `⚠️ ML NOT READY` warning. **No raise on expected failure**, so Step 5 / Step 6 / owned-position management stay reachable.

### 2.3 `data_pipeline.py` — artifact write protection (Stage C)

* `class LiveArtifactWriteError(RuntimeError)` ([L53](file:///Users/liqin/projects/ai_training_cnn/data_pipeline.py#L53)).
* `ModelWrapper.read_only = False` default ([L489](file:///Users/liqin/projects/ai_training_cnn/data_pipeline.py#L489)) — offline trainer unaffected.
* `_assert_writable()` ([L491](file:///Users/liqin/projects/ai_training_cnn/data_pipeline.py#L491)) + guards in `fit()` ([L546](file:///Users/liqin/projects/ai_training_cnn/data_pipeline.py#L546)), `save()` ([L609](file:///Users/liqin/projects/ai_training_cnn/data_pipeline.py#L609)) and the legacy `.pkl` load-and-republish fallback ([L660](file:///Users/liqin/projects/ai_training_cnn/data_pipeline.py#L660)).

## 3. Test evidence

Command and result:

```
$ python -m pytest tests/test_phase3_runtime_containment.py -q
30 passed, 3 skipped in 0.18s
```

Compile/import checks:

```
$ python -m py_compile fx_trade_bot_ml.py data_pipeline.py fx_trade_bot.py fx_trade_bot_v685.py tests/test_phase3_runtime_containment.py
PY_COMPILE_OK
```

Coverage map:

| Group | Tests |
|---|---|
| §8.1 init | P3T-01 READY+identity+injection, 02 MODEL_MISSING, 03 LOAD_FAILED, 04/04b INCOMPATIBLE + SCALER_MISSING, 05 FEATURE_CONTRACT_MISMATCH, 06 MODEL_STALE (no retrain), 07 LEGACY_FALLBACK_BLOCKED |
| §8.2 isolation | P3T-15 unexpected error re-raised; P3T-08 all expected failures return `ModelInitResult` (cycle continues); P3T-12 ×3 inits write nothing / never train; P3T-24 hashes identical before/after |
| §8.5 observability | P3T-25/26 `[ML-INIT]` fields, P3T-27 two hosts distinguishable, P3T-28 no invented release id |
| Source-level (AST) | `ml_init` single non-fatal assignment; Step 5→7 region free of `strat_engine`/`model_wrapper`/`ml_init`; QUICK-FLIP ML-independent — asserted for **both** live bots |
| Entry boundary (frozen) | `test_entry_authorization_is_unchanged_and_unresolved`, `test_ml_status_does_not_gate_entry`, `test_no_dead_skip_helper_was_added_to_the_ml_module`, `test_ml_module_stays_free_of_the_heavy_stack` |
| Offline trainer | P3T-23 `read_only` defaults writable; `retrain_model.py` still calls `wrapper.save()` |

Deferred on purpose (owner decision): **P3T-09 / P3T-16 / P3T-19** (entry-path tests) are **not** executed.

BLOCKED (environment, not code):

```
SKIPPED [3] tests/test_phase3_runtime_containment.py: BLOCKED: sklearn not installed in this interpreter (§9.3 no dependency changes)
```

→ These 3 (`test_p3t21_22_readonly_wrapper_blocks_fit_and_save`, `test_p3t07_legacy_load_republish_blocked_in_readonly`, `test_p3t20_readonly_init_writes_nothing`) exercise the **real** `ModelWrapper` but cannot run here because `sklearn` / `xgboost` / `joblib` / `oandapyV20` are absent from conda `ai-sprint`. They are written and will run in the deployed environment; the equivalent contract is proven locally through the wrapper doubles.

## 4. Required acceptance list

| Requirement | Result |
|---|---|
| `ensure_model()` failure no longer blocks independent position management | ✅ PASS — returns `ModelInitResult`, never raises on expected failure; AST proves Step 5 / Step 6 / owned-pos region is ML-free |
| ML failure is never disguised as a valid model result | ✅ PASS — explicit `status`/`reason`; unexpected errors re-raised |
| Live runtime does not train / write / republish artifacts | ✅ PASS — `read_only=True` + `_assert_writable` in `fit`/`save`/legacy-load; hash-before == hash-after |
| Offline trainer still works | ✅ PASS — `read_only` defaults `False`; `retrain_model.py` untouched |
| Two hosts' model identity can be checked independently | ✅ PASS (local) — `host_id`/`profile`/`artifact_path`/4 hashes in `[ML-INIT]`; cross-host segregation asserted with a monkeypatched `FX_BOT_HOST_ID` |
| Healthy model path regression test passes | ✅ PASS — P3T-01/24 (READY, identity, wiring, immutability). Real-load e2e **NOT VERIFIED** here (missing runtime stack) |
| Entry Authorization unmodified and marked pending approval | ✅ PASS — pinned by tests; **Entry Authorization remains unchanged and unresolved.** |
| No real orders, no live deployment | ✅ PASS — no OANDA calls in tests; no deployment |

## 5. Unresolved / not verified

* **Entry Authorization remains unchanged and unresolved.** ML-unavailable still lets the synthetic `X = S*0.3 + R*0.3` ([L1629](file:///Users/liqin/projects/ai_training_cnn/fx_trade_bot.py#L1629)) reach `FINAL` scoring ([L1628](file:///Users/liqin/projects/ai_training_cnn/fx_trade_bot.py#L1628)); Strength + MC consensus can therefore still authorize an ML-dependent entry. **This implementation must NOT be treated as a deployable safe version until §4.5 is separately approved.**
* **NOT VERIFIED**: real `READY` load through `ModelWrapper` end-to-end (missing `sklearn`/`xgboost`/`joblib`); the 3 skipped tests + the `XGBoostError` classification path.
* **NOT VERIFIED**: cross-host release comparison executed on the two real hosts — only modelled locally.
* **Pre-existing, untouched**: the 14 collection errors in the wider `tests/` tree (missing `python-dotenv`, stale `fx_trade_bot_v683.py` references) are unrelated to this change. The new test file `tests/test_phase3_runtime_containment.py` is matched by the repo's `test_*.py` `.gitignore` rule and is therefore currently untracked.