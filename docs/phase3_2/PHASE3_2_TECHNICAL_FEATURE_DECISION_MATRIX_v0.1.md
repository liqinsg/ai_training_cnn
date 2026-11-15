# Phase 3.2 — Technical Feature Decision Matrix v0.1

**Date:** 2026-11-15  
**Status:** PROPOSAL — OWNER DECISIONS PENDING  
**Purpose:** Decide technical eligibility and list exact proposed redefinitions for source-derived feature candidates. This matrix makes no claim about predictive value.

## 1. Decision boundary

Phase 3.2 decides whether a feature has a stable, implementable, reproducible technical definition and can be computed consistently in training and inference. Phase 3.3 evaluates predictive value. Technical eligibility alone does not imply inclusion in the model's final ordered input schema; that schema requires both decisions.

The current source inventory is evidence, not an approved contract. This matrix makes proposed design decisions for owner review. No production implementation, model training, artifact write, deployment, or trading behavior change is authorized by it.

### Status meanings

| Status | Meaning |
|---|---|
| `ACCEPTABLE AS-IS` | Current mathematical definition can be retained, subject to the common input and timeframe gates in this document. This does not make the feature valuable or automatically include it. |
| `REDEFINE` | Current semantics are ambiguous, misleading, unstable, or defective. The proposed replacement semantics below are explicit design candidates; approval and later implementation are still required. |
| `EXCLUDE` | Proposed removal from the technically eligible candidate set. None are assigned in v0.1 because there is not enough owner evidence to exclude a candidate on technical grounds alone. |
| `DEFER` | A blocking decision, backend choice, or experiment remains. The feature cannot enter the eligible set until resolved. |

## 2. Timeframe gate

**Proposed evaluation baseline: M15. Status: CANDIDATE ONLY — NOT APPROVED.** The local trainer source declares M15, but the historical artifact bundle is not reliably bound to that script. This is not evidence of the historical model's timeframe.

The matrix below is conditional on evaluating the formulas at M15. M15 is the first decision gate: if the owner selects another timeframe, all bar-to-time mappings, names, volatility scaling, session mapping, warm-up lengths, and corresponding tests must be recalculated before any contract is frozen.

At M15:

| Source window | M15 elapsed span | Proposed time meaning |
|---:|---:|---|
| 1 row | 15 minutes | one-candle return |
| 3 rows | 45 minutes | three-candle return |
| 6 rows | 90 minutes | six-candle return |
| 12 rows | 3 hours | 12-candle return/window |
| 24 rows | 6 hours | 24-candle window |
| 48 rows | 12 hours | 48-candle window |
| 96 rows | 24 hours | 96-candle window |

Use a declared, validated 15-minute cadence with timezone-aware UTC candle times. Validate monotonic order, uniqueness, and expected intervals before feature construction; session closures/gaps need an approved calendar policy. **Proposed v1 batch policy:** every input candle must pass Candle Validation. Duplicate timestamps, unordered timestamps, unexplained gaps, or invalid OHLC reject the entire input batch; do not delete bad rows and continue, or search backward for replacement candles. Training and inference use this same rule. Gaps explained by an approved market/session calendar are handled only as that calendar explicitly specifies; until the calendar policy is approved, such a gap is not silently accepted. “M15” alone does not settle whether the bar timestamp denotes open or close time, nor the incomplete-candle exclusion rule; those remain input-contract decisions.

## 3. Candidate decisions

Statuses below assess technical eligibility, not predictive utility. Names in the “M15 proposal” column are suggested stable names if M15 is approved; they are not aliases that may silently replace legacy names under an existing identity.

| Candidate | v0.1 status | M15 technical proposal / blocker |
|---|---|---|
| `ret_1h` | `REDEFINE` | Rename to `return_15m`; formula `Close[t]/Close[t-1]-1`. `t-1` means exactly timestamp `τ[t]-15 minutes`; do not search backward for another valid candle. |
| `ret_3h` | `REDEFINE` | Rename to `return_45m`; formula `Close[t]/Close[t-3]-1`, where `t-3` is exactly `τ[t]-45 minutes`; no skipping missing/invalid candles. |
| `ret_6h` | `REDEFINE` | Rename to `return_90m`; formula `Close[t]/Close[t-6]-1`, where `t-6` is exactly `τ[t]-90 minutes`; no skipping missing/invalid candles. |
| `ret_12h` | `REDEFINE` | Rename to `return_3h`; formula `Close[t]/Close[t-12]-1`, where `t-12` is exactly `τ[t]-3 hours`; no skipping missing/invalid candles. |
| `ret_log` | `REDEFINE` | Rename to `log_return_15m`; formula `ln(Close[t]/Close[t-1])`, where `t-1` is exactly the preceding M15 timestamp; require positive finite closes; no backward search. |
| `vol_12h` | `REDEFINE` | Rename to `horizon_vol_3h`; formula `sqrt(12) * sample_std(r[t-11:t])`, `r[i]=Close[i]/Close[i-1]-1`, `ddof=1`. This is horizon-scaled sample volatility, not the conventional realized-volatility measure `sqrt(sum(r_i^2))`. Requires 12 consecutive valid returns, hence 13 consecutive valid closes from `t-12` through `t`; no missing interval may be skipped. |
| `vol_24h` | `REDEFINE` | Rename to `horizon_vol_6h`; formula `sqrt(24) * sample_std(r[t-23:t])`, `ddof=1`; this is horizon-scaled sample volatility, not `sqrt(sum(r_i^2))`. Requires 24 consecutive valid returns, hence 25 consecutive valid closes from `t-24` through `t`. |
| `vol_48h` | `REDEFINE` | Rename to `horizon_vol_12h`; formula `sqrt(48) * sample_std(r[t-47:t])`, `ddof=1`; this is horizon-scaled sample volatility, not `sqrt(sum(r_i^2))`. Requires 48 consecutive valid returns, hence 49 consecutive valid closes from `t-48` through `t`. |
| `body` | `ACCEPTABLE AS-IS` | Retain `abs(Close-Open)/Open`; require finite OHLC and `Open > 0`; this is a per-candle dimensionless body fraction. |
| `upper_wick` | `ACCEPTABLE AS-IS` | Retain `(High-max(Open,Close))/Open`; require finite, valid OHLC and `Open > 0`. |
| `lower_wick` | `ACCEPTABLE AS-IS` | Retain `(min(Open,Close)-Low)/Open`; require finite, valid OHLC and `Open > 0`. |
| `range` | `ACCEPTABLE AS-IS` | Retain `(High-Low)/Open`; require finite, valid OHLC and `Open > 0`. |
| `direction` | `REDEFINE` | Three-state encoding: `1` when `Close>Open`, `0` when equal, `-1` when `Close<Open`. Requires finite valid OHLC. This changes current flat-candle semantics and therefore requires a new identity. |
| `atr` | `DEFER` | Decide one canonical ATR formula/backend, exact initialization and smoothing, period in M15 bars, dependency version, and warm-up before accepting. Current backend fallback is disallowed. |
| `atr_pct` | `DEFER` | Formula candidate `ATR[t]/Close[t]` is clear, but inherits the unresolved ATR definition/backend; require positive finite close and finite ATR. |
| `atr_percentile` | `REDEFINE` | Current calculation is rolling range position, not percentile rank. Proposed new name `atr_ecdf_50bar`: for a fully populated trailing 50-bar ATR window including current bar, `count(ATR[i] <= ATR[t], i=t-49..t)/50`. Ties count as less-than-or-equal; emit missing until 50 valid ATR values. Since current is included, a unique minimum yields `1/50` (not zero); this is a discrete empirical CDF value, not a continuous-distribution percentile. Requires canonical ATR first. |
| `atr_ma` | `DEFER` | Formula candidate is trailing simple mean of the last 14 ATR values, including current; window and missing policy are explicit, but ATR backend/period are unresolved. |
| `atr_expanding` | `DEFER` | Current semantics are `ATR[t] > SMA14(ATR)[t]`, not “expanding” in the statistical sense. Proposed rename `atr_above_sma14` with strict `>` comparison; only define after ATR is canonical. |
| `atr_ratio` | `DEFER` | Proposed formula `ATR[t]/mean(ATR[t-27..t])` over 28 valid values; no fill-to-1.0; missing until the full window exists. ATR backend remains unresolved. |
| `rsi` | `DEFER` | Select and freeze a single canonical calculation (including seed, smoothing, zero-gain/loss handling, dependency/version, and warm-up). Do not fall back between pandas-ta and local EWM. |
| `rsi_slope` | `DEFER` | Formula candidate is `RSI[t]-RSI[t-3]`; name should indicate 45-minute difference under M15, but depends on an accepted RSI definition and warm-up. |
| `adx` | `REDEFINE` | Replace local rolling-mean ADX and `NaN→0` behavior with the explicit Wilder proposal in §4. Invalid/warm-up values remain unavailable and are rejected or excluded by a separately approved sample policy. |
| `MACD_12_26_9` | `DEFER` | Explicitly choose fast/slow/signal periods, EMA seed and recurrence, price input, output names, and warm-up. Current implicit library defaults and silent output omission are not acceptable. |
| `MACDh_12_26_9` | `DEFER` | Same MACD decision; if later eligible, all MACD outputs must be calculated together and required outputs validated. |
| `MACDs_12_26_9` | `DEFER` | Same MACD decision; no silent partial output set. |
| `dist_high_24` | `REDEFINE` | Rename to `dist_high_6h`; formula `(Close[t]-max(High[t-23..t]))/Close[t]`, current candle included, full 24-candle window required, positive finite close required. |
| `dist_low_24` | `REDEFINE` | Rename to `dist_low_6h`; formula `(Close[t]-min(Low[t-23..t]))/Close[t]`, current candle included, full 24-candle window required. |
| `dist_high_48` | `REDEFINE` | Rename to `dist_high_12h`; formula `(Close[t]-max(High[t-47..t]))/Close[t]`, current candle included, full 48-candle window required. |
| `dist_low_48` | `REDEFINE` | Rename to `dist_low_12h`; formula `(Close[t]-min(Low[t-47..t]))/Close[t]`, current candle included, full 48-candle window required. |
| `dist_high_96` | `REDEFINE` | Rename to `dist_high_24h`; formula `(Close[t]-max(High[t-95..t]))/Close[t]`, current candle included, full 96-candle window required. |
| `dist_low_96` | `REDEFINE` | Rename to `dist_low_24h`; formula `(Close[t]-min(Low[t-95..t]))/Close[t]`, current candle included, full 96-candle window required. |
| `vol_sma_ratio` | `DEFER` | Decide whether the source field is tick volume or exchange-traded volume, whether it is available/meaningful for every supported instrument, and how missing/zero/invalid values are handled. If retained, define one invariant source and formula; no tick/real ambiguity, whole-input source switching, synthetic HL×Close proxy, or fill-to-1.0. |
| `vol_trend` | `DEFER` | Same source-semantics decision as `vol_sma_ratio`; comparability across instruments and identical training/inference volume definitions must be established before a formula is accepted. |
| `hour` | `REDEFINE` | Rename to `utc_hour`; define as the UTC hour component of candle timestamp `τ[t]` only after the input has passed Candle Validation and `τ[t]` is normalized to timezone-aware UTC, integer 0–23. Do not read an unnormalized raw `DatetimeIndex`. Renaming is a schema change and requires a new identity. |
| `day_of_week` | `REDEFINE` | Rename to `utc_day_of_week`; define as the UTC weekday component of Candle-Validated, normalized timestamp `τ[t]`, Monday=0 through Sunday=6. Do not read an unnormalized raw `DatetimeIndex`. Renaming is a schema change and requires a new identity. |
| `is_london` | `DEFER` | Define the London-local session interval and boundary convention first. Then calculate from UTC instants converted with IANA zone `Europe/London`, including database-controlled DST. Current fixed index-hour window is not eligible. |
| `is_ny` | `DEFER` | Define the New York-local session interval and boundary convention first. Then calculate from UTC instants converted with IANA zone `America/New_York`, including database-controlled DST. Current fixed index-hour window is not eligible. |

### M15 mapping for renamed row windows

The proposed formula windows are expressed in bars to make the source behavior auditable. At M15, 24/48/96 rows mean 6/12/24 elapsed hours respectively. The `return_3h` name maps to 12 prior candles; `horizon_vol_3h/6h/12h` use 12/24/48 one-candle returns. These are scaled sample standard deviations, not conventional realized volatility. A future change of timeframe requires a new calculation of these mappings and names, not a metadata-only edit.

## 4. Proposed ADX definition (pending approval)

To eliminate ambiguous local rolling means and hidden zero fill, the proposed ADX uses Wilder smoothing with period `n=14` bars (subject to owner approval of period):

1. **Directional movement:** For each candle `t>0`, define `up=High[t]-High[t-1]`, `down=Low[t-1]-Low[t]`; `+DM[t]=up` iff `up>down` and `up>0`, else 0; `-DM[t]=down` iff `down>up` and `down>0`, else 0. Ties produce both zero.
2. **True range:** `TR[t]=max(High[t]-Low[t], abs(High[t]-Close[t-1]), abs(Low[t]-Close[t-1]))`. Candle 0 has no prior-close transition and is unavailable. All candles must first pass OHLC and timestamp validation. Under the proposed v1 whole-batch rejection policy in §2, a missing/unexplained interval or invalid candle rejects the entire batch before ADX calculation; it is not dropped, skipped, or repaired.
3. **Smoothed sums and first DI/DX:** At `t=n`, seed smoothed TR and directional movements as sums over transitions `1..n`: `STR[n]=sum(TR[1..n])`, `S+DM[n]=sum(+DM[1..n])`, `S-DM[n]=sum(-DM[1..n])`. For `t>n`, update each series by `S[t]=S[t-1]-S[t-1]/n+x[t]`. Thus the first possible DI and DX are at index `t=n` (the `(n+1)`th candle when indexing from zero).
4. **Directional indicators and DX:** `+DI[t]=100*S+DM[t]/STR[t]`, `-DI[t]=100*S-DM[t]/STR[t]`. If `STR[t]=0`, DI and DX are unavailable. Let `D[t]=+DI[t]+(-DI[t])`; if `D[t]=0`, DX is unavailable; otherwise `DX[t]=100*abs(+DI[t]-(-DI[t]))/D[t]`.
5. **ADX seed, recurrence, and reseed:** Initially, with contiguous valid DX values, the first ADX is at index `t=2n-1`, seeded as `ADX[2n-1]=mean(DX[n..2n-1])` (exactly `n` DX values). Thereafter, while every DX remains valid and contiguous, `ADX[t]=((n-1)*ADX[t-1]+DX[t])/n`. If an input candle is invalid, §2 rejects the entire batch. If the candle is valid but its DI/DX is mathematically unavailable because a denominator is zero, mark `DX[t]` and `ADX[t]` unavailable and break the ADX smoothing chain. Do not carry the previous ADX across that point. Retain and continue the Wilder smoothed TR/+DM/-DM states over subsequent valid candles. Starting at the next valid DX, collect a fresh run of `n` consecutive valid DX values; seed ADX with their arithmetic mean at the index of the nth value, then resume the recurrence. Any further unavailable DX restarts this process. For `n=14`, after a break at index 40, if DX is valid continuously from index 41 onward, the next ADX seed is at index 54 from `DX[41..54]`.
6. **Invalidity and warm-up:** Emit unavailable before the initial seed and before any post-break reseed; never replace unavailable with zero. A missing/unexplained interval, duplicate/unordered timestamp, or invalid OHLC anywhere in the input batch rejects the whole batch under §2; this indicator-level DX break/reseed rule applies only to mathematically undefined DI/DX on otherwise valid candles. Training and inference must apply the same rules.

This is a proposal for a new technical definition, not a claim that it matches a library's ADX output. Any alternative seed/index convention must be recorded explicitly and compared in a separate fixture experiment. The period 14 remains a proposal pending approval.


## 5. Shared Feature Eligibility gate

A feature may enter the technically eligible candidate set only when all of the following are specified and satisfied:

1. Formula is complete and unambiguous.
2. Required input columns and their data meaning are explicit.
3. Timeframe and row-to-time mapping are explicit.
4. Canonical backend/implementation and version are fixed where applicable.
5. Warm-up and first-valid-row behavior are explicit.
6. Missing, invalid, and non-finite input/output behavior is explicit.
7. Calculation uses no future data.
8. The same declared historical input produces a repeatable output.
9. Training and inference use the same calculation semantics and validity rules.

Failure of any item means `DEFER`, even if a row in §3 currently says `ACCEPTABLE AS-IS` or `REDEFINE`; those labels are proposed dispositions, not waivers of this gate. Eligibility is still separate from Phase 3.3's predictive-value decision and final schema approval.

## 6. Cross-feature policy proposals

- **Canonical backend:** Each accepted indicator has one exact calculation path and pinned implementation/dependency identity. Missing dependency, calculation exception, missing expected output, or non-finite required output is a named failure; no unapproved fallback or numeric sentinel.
- **Missing values:** Warm-up is represented as unavailable. Do not `bfill`, blanket `fillna(0)`, or convert unavailable indicators into plausible values. Training row exclusion and inference rejection must implement the same validity definition.
- **Names/order:** Renaming or changing any formula, window, seed, default, input source, scale, timezone, or missing behavior changes contract semantics and therefore requires a new Feature Contract Identity. Candidate eligibility is not a final ordered schema.
- **Candle Validation failure scope:** In v1, the entire input batch must pass validation before any feature calculation. Duplicate or unordered timestamps, unexplained gaps, or invalid OHLC reject the batch. Do not delete invalid candles and continue, impute them, or substitute older candles. This same rule applies in training and inference. Any future local-recovery policy requires a separate versioned decision.
- **Price and candle validation:** Before feature calculation require finite OHLC, positive Open/Close where used as denominator/log input, `High >= max(Open,Close)`, `Low <= min(Open,Close)`, and `High >= Low`. Validate required timestamps as timezone-aware UTC, strictly increasing and unique, with expected interval/gap rules. Volume validity remains separately unresolved while volume features are `DEFER`.
- **Volume meaning:** Confirm whether source `Volume` means tick volume or exchange-traded volume, and whether it is available/meaningful for every supported instrument/feed. Until decided, both volume candidates remain `DEFER`.
- **Session features:** UTC is the stored timestamp basis; local session conversion uses IANA zone data. Define local session hours, whether endpoints are inclusive, and whether weekends/holidays are excluded before `is_london`/`is_ny` can be accepted.

## 7. Experiments and pre-registered acceptance criteria

No implementation experiment is run by this document. The following criteria are proposed to be approved before implementation/experiments and before inspecting new comparison results.

| Experiment | Fixed inputs / method | Proposed acceptance criteria |
|---|---|---|
| Timeframe, Candle Validation and row semantics | Same deterministic OHLC candles represented as UTC M15; test expected 15-minute cadence and deliberately add a duplicate, reorder rows, introduce an invalid OHLC row, and remove an interval. | Valid M15 input maps every row window to the table in §2. Any duplicate, unordered timestamp, invalid OHLC, or unexplained gap rejects the entire batch before any features are emitted; no row deletion, replacement, or partial output. An explained session gap is accepted only under an explicitly approved calendar rule. |
| Feature formula fixtures | Hand-calculated small fixtures for returns, volatility, candles, distances, volume and time; include rising, falling, flat, zero denominator, boundary-hour, and missing-input cases. For ADX, include a valid DX run, a mathematically undefined DX amid valid candles, and a subsequent valid DX run. | Exact output column names/order for the tested eligible subset; categorical/integer outputs exact; floating outputs satisfy `abs(candidate-reference) <= 1e-10 + 1e-8*abs(reference)`; invalid inputs produce the specified named invalidity, never a filled plausible value. ADX is unavailable at the break and until a fresh run of `n` consecutive valid DX values seeds it; prior ADX state is not carried across the break. |
| Return/volatility continuity and warm-up | For M15, check that return lag `k` reads timestamp `τ[t]-15k minutes` exactly; verify volatility windows use 12/24/48 contiguous returns and 13/25/49 contiguous closes. Insert a missing interval and an invalid Close within each required window. | Correct exact timestamp and count semantics; no skipping or searching for prior valid candles. Missing required timestamp/value is rejected or marked unavailable according to the common Candle Validation policy; no changed effective horizon. Volatility first valid output occurs only after the specified consecutive close count. |
| Backend identity / failure | Pin exact package/code identity; inject unavailable dependency, exception, null/empty output, missing column and non-finite output. | Normal outputs meet the numeric tolerance above on fixed fixtures; all failure injections are rejected with distinct actionable reasons; no backend switch, partial MACD output, or sentinel substitution. |
| History-length sensitivity / recursive convergence | Before examining results, lock sequence `200 → 300 → 500 → 800` bars, all ending at the same final completed candle and derived from the same OHLCV series. Record the final raw value for every feature at each length. Compare adjacent pairs `200 vs 300`, `300 vs 500`, and `500 vs 800`; the common suffix for each pair is respectively 200, 300, and 500 bars. Compare each feature independently. | For each pair, use the longer-history value as `reference`: 300 for `200 vs 300`, 500 for `300 vs 500`, and 800 for `500 vs 800`. Apply `abs(shorter_value-reference) <= 1e-10 + 1e-8*abs(reference)` independently to every feature and pair. Convergence passes only when both `300 vs 500` and `500 vs 800` pass for that feature; record `200 vs 300` separately as diagnostic evidence. No aggregate/average error may hide a failed feature. If either required pair fails at 800 bars, that feature's convergence/warm-up remains `NOT ESTABLISHED`; do not extend the sequence without a new pre-registered decision. |
| Warm-up boundary | Sweep lengths immediately below/at/above each declared full window and indicator seed length. | Column schema remains fixed at every length; rows before validity are explicitly unavailable; first valid row matches the declared seed/window index; no feature is omitted due to history length. |
| Volume source invariance | Same candles with positive historical volume inserted only before the compared common suffix; test missing, all-zero, negative and changing volume. | An eligible row's value is invariant to adding candles outside its declared lookback. Invalid/unavailable volume follows the single declared error policy. No real/proxy source switch occurs. |
| Session timezone / DST | UTC instants around London and New York session boundaries, spring-forward/fall-back transitions, and overlapping session hours using a pinned IANA tz database. | Results match the approved local-time interval at every test instant; behavior is identical between training/inference; nonexistent/ambiguous local times are avoided by converting UTC instants rather than localizing naive timestamps. |
| Train/inference parity | Identical raw candles, timeframe, feature config, dependency lock and contract identity through both paths; compare ordered raw feature rows before model scaling. | Names/order/types/missingness match exactly; floating values meet preregistered tolerance; both paths reject the same invalid fixtures. |

Keep two experiment questions separate in the report: (A) implementation correctness/parity on identical input, and (B) recursive-feature convergence across different history lengths. Both may use `1e-10 + 1e-8*abs(reference)`, but a pass for A is not a pass for B or vice versa. The existing Phase 3.2 same-final-candle 200-versus-500 experiment failed this tolerance for six features. Do not relax it after observing new results. The fixed sequence and convergence rule above remain proposed and require owner approval before running the new comparison. This history-convergence comparison is reported separately from implementation correctness/parity on identical input; the two results cannot substitute for one another.

**Production history length: `NOT YET APPROVED`.** The `200 → 300 → 500 → 800` sequence is an experiment plan, not a production configuration. No feature may be claimed to satisfy production warm-up until a production history length is separately approved and the feature passes the declared convergence and warm-up rules at that length. If the approved production length is not one of 200, 300, 500, or 800, preregister an additional same-final-candle comparison between that length and the 800-bar result before examining results. Treat 800 as a verified convergence baseline for a feature only if that feature passed both required pairs through 800; otherwise its convergence remains `NOT ESTABLISHED`, and no production warm-up claim may be made. In the additional comparison, use the longer-history value as reference, apply the same per-feature tolerance, and record the result separately; do not infer support for an untested length from the existing sequence alone.

## 8. Pending owner decisions (dependency order)

| Order | Decision | What it unlocks |
|---:|---|---|
| 1 | Select target timeframe (M15 remains a candidate), timestamp convention, incomplete-candle rule, UTC normalization, and Candle Validation policy including explained session gaps and whole-batch rejection. | Gives row windows their time meaning and fixes the common input-validity boundary. |
| 2 | Decide candidate formulas, names, periods, canonical backends/versions, warm-up, and invalidity for all features; this includes ATR, RSI, MACD and the proposed ADX definition. | Determines technical eligibility. Volume and session candidates remain deferred until their source/session semantics are resolved. |
| 3 | Approve the fixed history comparison sequence, per-feature tolerance, two-pair convergence rule, and any exception process. | Authorizes a bounded, reproducible convergence experiment. |
| 4 | Separately approve production history length (`NOT YET APPROVED`), volume source semantics/comparability/invalid-value policy, and London/New York session intervals and calendar rules. | Establishes runtime warm-up and can resolve the associated deferred candidates. |
| 5 | Freeze the technically eligible ordered schema only after decisions and required experiments are complete; then evaluate predictive value in Phase 3.3. | Creates the input candidate for Phase 3.3 and, after that phase's decisions, a future Feature Contract Identity. |

M15 approval and production history length are distinct decisions. The local trainer's M15 declaration is not proof of the historical artifact timeframe.

## 9. References

- [`PHASE3_2_FEATURE_SOURCE_EVIDENCE.md`](PHASE3_2_FEATURE_SOURCE_EVIDENCE.md) — source formulas and behavior for the 37 candidates.
- [`PHASE3_2_Tech_Feature_Contract_v1.0_Design.md`](PHASE3_2_Tech_Feature_Contract_v1.0_Design.md) — draft architecture and unresolved technical decisions.
- [`PHASE3_2_TRAIN_INFERENCE_PARITY_REPORT.md`](PHASE3_2_TRAIN_INFERENCE_PARITY_REPORT.md) — existing source-level and fixture evidence, including M15 fixture and history-length comparison.
- [`data_pipeline.py`](../data_pipeline.py) — current implementation baseline; no implementation changes are made by this matrix.
