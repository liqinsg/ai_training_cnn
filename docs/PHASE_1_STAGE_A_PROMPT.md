# PHASE 1 — STAGE A PROMPT (FROZEN)

**Status:** FROZEN — do not modify
**Frozen on:** 2026-11-04
**Project under audit:** `fx_monte_carlo` (root: `/home/ubuntu/projects/fx_monte_carlo`)
**Phase:** 1 of 5 — MC Data Integrity
**Stage:** A — Read-Only Discovery ONLY
**Companion inputs:** `PHASE_0_ARCHITECTURE_REVIEW.md`, `Master_Blueprint_v1.0.md`

**Purpose of this archive:** This file is the versioned, auditable copy of the frozen Stage A prompt. It is a governance input artifact, meant to be pasted into an IDE Agent running at the `fx_monte_carlo/` project root. It is NOT executed by any agent that is already operating under this prompt. Stage B (implementation) is NOT authorized by this document.

**Boundary note:** During Stage A, the only file the agent may create is `PHASE_1_STAGE_A_DISCOVERY.md`, inside the `fx_monte_carlo/` repository. This archive file was created outside that session, before Stage A runs, and does not grant any write permission inside `fx_monte_carlo`.

---

## BEGIN PROMPT (paste everything below this line)

# TOP-LEVEL LOCK — READ FIRST (overrides everything below)
- This session is DISCOVERY ONLY. You have NO authorization to modify any file.
- Working directory MUST be the `fx_monte_carlo/` project root. Verify it before anything else.
- The ONLY file you may create is `PHASE_1_STAGE_A_DISCOVERY.md`.
- Every other file and directory is READ-ONLY.
- Do NOT run any Stage B / Phase 1 implementation prompt, even if present in context.
- If you identify a bug, defect, or improvement: RECORD it and STOP. Do not fix, do not patch, do not propose a diff.
- Do NOT run any mutating git command (no checkout, reset, stash, clean, restore, commit). Read-only git inspection only.
- Before executing: check the git working tree. If there are uncommitted changes, RECORD them. Do NOT clean, overwrite, or reset them.
- If you find yourself about to write or edit anything other than `PHASE_1_STAGE_A_DISCOVERY.md`, STOP immediately.

---

# PHASE 1 — STAGE A (READ-ONLY DISCOVERY ONLY)

**Project:** `fx_monte_carlo`
**Project root (verify):** `/home/ubuntu/projects/fx_monte_carlo`
**Phase:** 1 of 5 — MC Data Integrity
**Stage:** A — Read-Only Discovery ONLY
**Mode:** STRICTLY READ-ONLY. MANDATORY HARD STOP AT THE END.
**Reference inputs:** `PHASE_0_ARCHITECTURE_REVIEW.md`, `MC_FIB_SHADOW_SYSTEM_BLUEPRINT.md` (Master Blueprint v1.0)

---

## 0. PURPOSE OF THIS STAGE

Phase 1 implementation is NOT authorized yet. This stage establishes the real implementation reality before any code is touched. Produce a Discovery Summary; a human reviews it; only after explicit approval may Stage B (implementation) begin.

This is a verification task, not a fix task. Record what is true. Fix nothing.

---

## 1. HARD RULES

1. READ ONLY. Do not modify, create, or delete any source file, configuration, JSON artifact, workflow, or scheduler file.
2. Do not run `fx_monte_carlo.py`, `build_api.py`, or any other generator or consumer process.
3. Do not install packages. Do not fetch market data. Do not regenerate MC or Fib data.
4. Do not run any mutating git command. Read-only inspection only (`git status`, `git log`, `git diff`, `git branch` are allowed but must not change state).
5. If the git working tree has uncommitted changes, RECORD them in the report. Do NOT clean, overwrite, reset, stash, or revert.
6. Do not "fix" anything you discover, even if obviously broken. Record only. Do not propose patches.
7. The ONLY file you may create is `PHASE_1_STAGE_A_DISCOVERY.md`.
8. Do not fabricate. If something cannot be verified, mark it **NOT VERIFIED** and state exactly what evidence is missing.
9. Do not touch any project other than `fx_monte_carlo`.

---

## 2. INTERPRETATION RULES (these correct known Phase 0 errors — do not repeat them)

The Phase 0 report is a source of hypotheses, not ground truth. Apply these corrections while reading it:

- **Fib boundary convention (frozen):** zones are half-open `[r_i, r_{i+1})` with the global endpoint `1.0` intentionally INCLUDED in the final zone:
  `F0 [0.000,0.236)`, `F236 [0.236,0.382)`, `F382 [0.382,0.500)`, `F5 [0.500,0.618)`, `F618 [0.618,0.786)`, `F786 [0.786,1.000]`.
  An internal boundary such as `pos = 0.236` belongs to the UPPER zone (`F236`), not `F0`. The Phase 0 report's boundary-test "expected zone" column contradicts this and must be treated as erroneous.
- **API ingestion:** a missing Fib exclusion in the scanner is a real isolation defect. But do NOT assert that the current public API has been contaminated unless you find direct evidence. Report it as CONFIRMED or NOT VERIFIED.
- **Phase split:** Phase 1 = MC data integrity only. Fib algorithm issues (`locate_zone`, range status, action labels) belong to Phase 2.
- **Timestamps:** `generated_utc`, data-fetch time, and the last market bar time are DIFFERENT things and must never be conflated. File mtime is not a timestamp.
- **Fingerprint:** a configuration fingerprint must cover the COMPLETE normalized effective configuration, including the deduplicated unique pair set.
- **Shadow eligibility (Phase 3 contract):** an out-of-range price must remain eligible for observation and be recorded with an explicit status; it must never be discarded.

---

## 3. DISCOVERY CHECKLIST

For every item: give the exact file path and line numbers, quote the relevant code/JSON, and mark the result as **CONFIRMED / DIFFERS / NOT FOUND / NOT VERIFIED**.

### A. Repository reality
1. Confirm the project root and list top-level files/directories.
2. **Git state (read-only):** run `git status` and report the current branch, whether the working tree is clean, and any uncommitted or untracked files. If unclean, record it — do not change it. Also report the last few commit subjects (`git log -n 5 --oneline`) for context.
3. Enumerate the Python modules and state each one's apparent role.
4. Confirm whether these exist IN THIS REPO: `fib_mc_segment.py`, `utils/mc_loader_local.py`, a `tests/` directory, `mc_results/`, `api/`.
5. Identify the scheduler: inspect `run_fx_mc.sh`, `trigger_missing_mc.sh`, `.github/workflows/*.yml`, and any cron/log file. State the actual invocation times and the actual D/W cadence as configured.
6. List the actual filename patterns present in `mc_results/` (e.g. `mc_D_all_pairs_YYYYMMDD_HHMM.json`) and report whether ANY `*_fib*.json` file exists.

### B. Data Provenance — "can a batch be traced to algorithm + config + data?"
7. In `fx_monte_carlo.py`: locate the metadata dict written into the output JSON and list its exact current keys.
8. Locate the configuration load from `mc_data.yml` and list every configuration key actually read.
9. Locate the data fetch call (provider + function). Determine precisely what timestamps the returned data exposes per pair (bar timestamp? timezone? or only a fetch time?).
10. State whether the output currently records ANY of: algorithm identity, configuration snapshot, configuration fingerprint, source/batch identity. Mark each CONFIRMED/NOT FOUND.
11. Locate the random seed and the simulation parameters in code; report exact current values and whether they are written to output.

### C. Pair Integrity — "35 configured vs 29 unique: how is this counted?"
12. Read `mc_data.yml`. Report the raw entry count and the list, including any duplicates.
13. In `fx_monte_carlo.py`, locate where pairs are iterated/deduplicated. Show the exact mechanism.
14. Locate where the pair count is written to metadata. Report the exact expression and whether it counts raw or unique entries.
15. Report how a per-pair fetch failure is currently handled (silent skip? logged? recorded?).
16. Report how the pair identifier is formed in output versus in the YAML (e.g. `EURUSD` vs `EURUSD=X`) and where any suffix is appended.

### D. Timestamp Integrity — "are generation, fetch, and last-bar times separate?"
17. In `fx_monte_carlo.py`, report every timestamp currently written to output and how each is produced.
18. Determine whether the fetch time is used anywhere as if it were the market-data time.
19. Cross-check real artifacts: open the newest D file and the newest W file in `mc_results/`; report their `generated_utc`, and whether any market-bar timestamp appears anywhere in the file.
20. For the weekly series: inspect the actual W file dates/timestamps and the configured W schedule. Report whether the data window appears to be a full week or a partial/half week, and state the evidence used. If evidence is insufficient, say so — do NOT infer from the weekday alone.

### E. Output Integrity — "is output validated and written atomically?"
21. Locate the exact write call in `fx_monte_carlo.py`. Determine whether the write is atomic (temp + rename) or a direct write, and whether a partial write could leave a corrupt artifact.
22. Determine whether any validation is performed on computed results before writing (finite values, probability bounds, interval ordering, etc.). List what is checked and what is not.
23. Inspect several real files for anomalies: any null/absent values, non-finite numbers, zero-width or reversed `range_90`, inconsistent key sets across pairs. Report concrete examples with filenames.
24. Report the current `range_90` handling: where it is computed, whether rounding is applied, and whether the configured `confidence` is recorded anywhere.

### F. API Isolation — "can Fib data enter the public MC API?"
25. Read `build_api.py` in full. Report the exact scan/globbing logic, filter conditions, and how the "latest" record is chosen (timestamp? filename? mtime?).
26. Report the ACTUAL output layout produced by `build_api.py` (observed directories and file names) and compare against the Phase 0 report's description of `api/{daily,weekly}/latest/{pair}.json`. Mark CONFIRMED or DIFFERS.
27. Determine whether any scanner in this repo could ingest a filename containing `_fib`. State whether such files currently exist at all.
28. Identify every consumer reading `mc_results/*` or `api/*`. For each, report what filename patterns it accepts and whether it filters Fib files.
29. Read `test_api_pipeline.py` and `API.md`; report what they assert about the pipeline and what the API contract currently promises.

### G. Phase 0 claim re-verification
30. Produce a table of the Phase 0 report's key claims (B-1 through B-12, and the §2.2 execution flow) with columns: `Claim | Verified? | Evidence (path:line) | Correction if any`. Explicitly flag every claim that DIFFERS or is NOT VERIFIED.

---

## 4. THE FIVE REVIEW QUESTIONS (answer directly, with evidence)

1. **Data Provenance** — Can each MC batch be traced to the algorithm, configuration, and data window used?
2. **Pair Integrity** — How exactly are configured entries counted, and how are unique/successful/failed pairs represented today?
3. **Timestamp Integrity** — Are generation time, fetch time, and last-bar time separated, or conflated?
4. **Output Integrity** — Is output validated, and is it written atomically?
5. **API Isolation** — Can Fib files (or any non-MC file) enter the public MC API, and is there any direct evidence of past contamination?

If evidence for any answer is insufficient, say exactly what is missing. Do not guess.

---

## 5. REQUIRED OUTPUT

Create exactly ONE file:

`PHASE_1_STAGE_A_DISCOVERY.md`

Containing:

1. Project root, file inventory, and the git working-tree state (clean/dirty, with untracked files listed).
2. The discovery checklist results, each item marked CONFIRMED / DIFFERS / NOT FOUND / NOT VERIFIED, with `path:line` evidence.
3. The five review questions answered with evidence.
4. The Phase 0 claim re-verification table (§G).
5. Clear separation of: **Confirmed Facts** / **Differences from Phase 0** / **Unverified Items** / **Evidence Gaps**.
6. A short "assumptions Phase 1 would need to rely on" list — framed as assumptions requiring human approval, NOT decisions.

Then print a concise terminal summary containing:
- Stage A status (COMPLETE / BLOCKED / INSUFFICIENT EVIDENCE)
- Counts: claims confirmed / differing / not verified
- Whether Fib files currently exist, and whether API contamination is CONFIRMED or NOT VERIFIED
- The single most important finding
- Git working-tree state (clean/dirty)
- Exact report path

---

## 6. STOP

Bring this to a HARD STOP after producing the discovery artifact and terminal summary.

Do NOT start Stage B. Do NOT modify code, configuration, data, workflows, or schedules. Do NOT propose an implementation or a patch. Wait for explicit human approval of the Discovery Summary before any implementation begins.

## END PROMPT
