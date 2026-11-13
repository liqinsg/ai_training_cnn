
**Verdict:** the doc is faithful to `AUDIT_PHASE3.md` (REPAIR stance, N/F numbering, thresholds and units all match), and Phase 3.0 as an inspection-first step is the right start. Several gaps should be fixed before it becomes the implementation authority.

## 1. Doc contradicts itself

- **Status:** the header says "Proposed", but section 16 marks D01–D15 as ACCEPTED, and section 0.4 defines ACCEPTED as explicitly approved. Change them to PROPOSED until you approve.
- **ID collision:** the register's D01–D15 clash with the audit's D1–D9. "D08" (purge) versus "D8" (price source) will confuse an implementation agent. Rename the register to PD-01…PD-15.
- **Unverified reference:** `docs/Development_plan.md` is cited as higher authority, but I haven't seen it. Confirm it exists and is consistent.

## 2. Missing design decisions (N1 is not implementable as written)

- **Abstain math (add as O10):** the doc bans synthetic votes but doesn't say what replaces them. With the ML vote abstaining, does 2-of-3 consensus become strength and MC unanimous? And does the XGB weight (`W_X`) in the score get renormalized or fail the entry? Today's behavior is a fabricated X.
- **Run-abort on model failure (new, High):** `ensure_model()` is called in `main()` without a try/except. Any failure (retrain fetch error, bad artifact, missing file) aborts the whole run before Step 5/6, so exit management and QUICK-FLIP never execute. The doc's "explicit unavailable state" must also say the run continues and entries follow the O10 policy. Add test **T23**: model unavailable → run completes, exits unaffected.
- **MC unit blast radius:** `mc_cache` percent values feed `calc_weighted_score`, the locked 0.625 TP threshold, and the Fib module. Convert to 0–1 in an adapter inside the new path only. Changing the shared cache would silently change live TP and scoring.
- **Null outcome:** there is no criterion for "model shows no edge after costs". Your earlier SVM prototype hit exactly the always-UP failure. Add a decision that if XGB fails the baselines out-of-sample, the ML vote weight goes to 0 or the vote is removed.

## 3. Sequencing problems

- **S0 observability was dropped.** The audit's first step (log `p_up`, abstain reason, score breakdown; the `XGB-LOW` count) is not in any phase. It is free, class A, and sizes N1 before anything is built. Add it to 3.0, with the open grep items (Top features, `pandas_ta`/pip per host).
- **Shadow comes too late.** Shadow (3.5) needs a new model release (3.4), so no live evidence arrives until after four phases. Phase 3.1 doesn't need a new model, so ship its shadow comparison against the current model.
- **Feature and model activate together.** The canonical-backend change (5.3) alters feature values, and under 5.2/T17 the active model would be rejected. State that 3.2 can't go live until a model trained under it is released.
- **Containment is not free.** Making artifacts read-only would make `fit()` raise and trigger the run-abort above. Safer: a default-on guard that loads a stale model instead of retraining, and ML UNAVAILABLE instead of training when files are missing.

## 4. Orphaned findings

- **F1, F12, N8, D2–D7:** not mapped to any phase. F1 (no-op probability gate) belongs in 3.1.
- **D8 (live price source):** only a "verification item" with no owner. It affects live entry and SL/TP anchoring, so give it a track, not just a note.

## 5. Smaller fixes

- **Model distribution across hosts:** with the OCI VM and laptop on one account, add a startup check that logs and compares release hashes across hosts (T16 covers features, not models).
- **Manifest:** add `git_dirty`, the XGB hyperparameters, and `random_state` (audit F-series: unrecorded seeds).
- **Statistics:** 6-bar overlapping labels shrink effective sample size. Report block-bootstrap confidence intervals, otherwise small accuracy differences read as signal.
- **Model identity:** training universe and trading universe differ (P2 has 13 pairs, the others 8). Key identity on the training superset plus a "serves" list.
- **Formatting:** `\[ \]` math doesn't render on GitHub; use `$$ … $$`.

Want me to turn these into a patch for `PHASE3_REDESIGN.md`, or draft the Phase 3.0 task spec with the S0 and containment items folded in?
