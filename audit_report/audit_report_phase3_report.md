
# AUDIT_PHASE3.md — v685 ML System Assessment

|                              |                                                                                    |
| ---------------------------- | ---------------------------------------------------------------------------------- |
| **Repo / branch**      | `ai_training_cnn` @ `v2026c`                                                   |
| **Commit audited**     | `<fill: git rev-parse HEAD>`                                                     |
| **Date**               | 2026-11-13                                                                         |
| **Mode**               | Audit-only. No code was changed.                                                   |
| **Spec under review**  | "Phase 3 — ML System Comprehensive Assessment & Redesign Specification" (ChatGPT) |
| **Status of evidence** | Code review complete. Runtime evidence still open (section 10).                    |

Severity: Critical / High / Med / Low.
Class: **A** = behavior-preserving cleanup, **B** = behavior change (must be switch-gated, default off).

---

## 1. Summary

The spec's headline diagnosis (separate train/inference feature code, random K-Fold, local-time leakage, ATR formula mismatch) is **mostly not what the code shows**. A shared `FeatureEngine` already exists, `TimeSeriesSplit` is used, OANDA timestamps are UTC, and the inference contract (`_build_matrix`, `predict_p_up`) already fails loudly.

The real defects are elsewhere:

1. **The decision layer fabricates the XGB vote** whenever `generate_signal()` returns `None` for any reason (N1), and the engine's internal score has unit bugs that make that `None` path frequent and direction-biased (N9, N10, N11).
2. **Evaluation is not out-of-sample** (F2) and `cv_accuracy` has no baseline.
3. **Artifacts have no provenance**, are shared by all four profiles, and are silently retrained inside the live cycle (N3).
4. **Backend dependence** (`pandas_ta` present or absent) changes ATR/RSI values and can break MACD features per host (F4, N12).

Evidence supports **REPAIR**, not the spec's wholesale REPLACE of feature code.

---

## 2. Scope and evidence base

Files reviewed in full: `fx_trade_bot.py`, `fx_trade_bot_ml.py`, `fx_trade_bot_utils_v1.py`, `data_pipeline.py`, `strategy_decision.py`, `data_guard.py`, `config.py`, `config_bot.py`, `config_profile.json`, `forex_pairs.json`, `utils/strategy_helpers.py`, plus a log excerpt of `STRENGTH_SCORES` lines (2026-10-01/02).

Not yet reviewed: `utils/trading_core.py`, `utils/strategy_config.py`, `utils/oanda_client.py`, full logs, cron, per-host environments, existing tests.

Findings marked *(pending)* depend on that missing evidence.

---

## 3. Spec claims vs. code

| Spec claim                                   | Verdict                 | Evidence                                                                                                                                                                           |
| -------------------------------------------- | ----------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Separate train/inference feature code (s3-5) | **PARTIAL**       | Both paths call the same `FeatureEngine.build`. Residual skew: 5000-bar vs 200-bar windows (N6), `dropna()` vs `ffill/bfill/fillna(0)` (N5), `pandas_ta` vs fallback (F4). |
| ATR formula mismatch (EMA at inference)      | **CONTRADICTED**  | One `ATRModule` for both paths. Real issue is backend dependence (F4).                                                                                                           |
| Timezone / local-time leakage                | **CONTRADICTED**  | OANDA times are UTC. Session flags are fixed-UTC in both paths.                                                                                                                    |
| Label construction (s6)                      | **PARTIAL**       | Explicit 6-bar horizon, computed per pair (no cross-pair boundary leak). Threshold is 0 with no cost or spread margin.                                                             |
| Random K-Fold (s7)                           | **CONTRADICTED**  | `TimeSeriesSplit` is used, but see F2.                                                                                                                                           |
| Loose artifacts (s8)                         | **PARTIAL**       | Four split files exist. No run ID, commit, hash, granularity, universe, library versions. Non-atomic write.                                                                        |
| ML is a read-only advisor (s9)               | **FALSE**         | XGB is 1 of 3 entry votes plus a score weight. It is not used for exits.                                                                                                           |
| Fabricated neutral signals (s9)              | **CONFIRMED**     | N1.                                                                                                                                                                                |
| Provenance missing (s10)                     | **CONFIRMED**     | F7, N3.                                                                                                                                                                            |
| Shadow mode (s9, s15)                        | **ABSENT**        | Only a trade-level DRY_RUN gate exists.                                                                                                                                            |
| Decision 2: hard stop on schema mismatch     | **PARTIAL**       | The engine raises, but the caller converts it to a neutral vote (N1). The spec does not define what the decision layer does when the advisor halts.                                |
| REPLACE feature code (s11, Decision 1)       | **NOT SUPPORTED** | Shared module already exists. REPAIR.                                                                                                                                              |

---

## 4. Findings: model, training, artifacts

| ID            | Sev  | Class | Finding                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| ------------- | ---- | ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **F1**  | High | B     | **Probability gate is a no-op in LEVEL10.** `base_min_edge` resolves to 0.50 (`BASE_MIN_EDGE` is defined nowhere), and `raw_prob = max(p_up, p_down) >= 0.5` always.                                                                                                                                                                                                                                                                                   |
| **F2**  | High | B     | **CV is not out-of-sample.** `pd.concat(train_dfs)` stacks rows by pair (whitelist order), and `TimeSeriesSplit` splits by position, so validation folds are later *pairs*, not later *time*; correlated same-period pairs sit in train. Also: scaler fit before CV, no embargo for the 6-bar label overlap, accuracy only with no always-up baseline, final model has no holdout, and a new model overwrites live artifacts with no promotion gate. |
| **F3**  | High | B     | **Price-unit features pooled across pairs.** Raw `atr`, `atr_ma` and MACD columns (JPY ~150 vs non-JPY ~1.1) go through one scaler and act as a pair-ID proxy. Importance *(pending: "Top features" training log)*.                                                                                                                                                                                                                                    |
| **F4**  | High | B     | **ATR/RSI depend on whether `pandas_ta` imports.** `pandas_ta` ATR is Wilder RMA, the fallback is a rolling SMA with `min_periods=1`. Artifacts do not record which path trained the model.                                                                                                                                                                                                                                                            |
| **F5**  | Med  | B     | **Granularity is not part of the artifact contract.** Timeframe comes from `--timeframe`. A different timeframe loads a fresh artifact silently; if stale, it retrains and overwrites at that granularity. Feature names (`ret_12h`, `sqrt(p*4)`) assume M15. Step 4 (`MULTI_TF_CONFLUENCE`) feeds H4/H1/M15 candles to the same model and swallows errors.                                                                                          |
| **F6**  | Med  | B     | **`load()` overwrites the shared `FEAT_CFG` from `.cfg.json`** via `setattr`. Config changes (e.g. `USE_MACD`) are ignored until the artifact is stale, which breaks CLI > run.env > default precedence. It also keeps inference features consistent with the loaded model.                                                                                                                                                                        |
| **F7**  | Med  | B     | **Weak artifact integrity.** Four-file save is non-atomic. Load requires three files (`.cfg.json` optional) and checks feature *count* only, not names or a hash. `scaler.joblib` path is not tied to the model stem.                                                                                                                                                                                                                                  |
| **F8**  | Med  | B     | **Silent RandomForest fallback.** If `xgboost` is missing it saves `.sklearn.pkl`, but `split_ok` requires `.json`, so it retrains on every startup. Legacy `pickle.load` fallback also re-saves silently.                                                                                                                                                                                                                                         |
| **F9**  | —   | —    | **WITHDRAWN.** `should_close` is never called by this bot; exits do not use the model.                                                                                                                                                                                                                                                                                                                                                                     |
| **F10** | Low  | A     | **Latent label bug.** `(NaN > 0).astype(int)` labels the last 6 rows per pair as 0. Rescued only because `ensure_model`'s global `dropna()` drops them via `future_return`.                                                                                                                                                                                                                                                                          |
| **F11** | Low  | B     | **Partial-window values in later rows.** MACD NaN warm-up (~33 rows) is removed by `dropna()`, but 48/96-bar features use `min_periods=1`, so rows ~34-96 carry partial-window values.                                                                                                                                                                                                                                                                   |
| **F12** | Low  | A     | **Mismatched bar guards.** `has_min_bars(df, 5)` and `required_bars=20` vs a real need of >96 bars. Fails safe but logs misleadingly.                                                                                                                                                                                                                                                                                                                    |
| **F13** | —   | —    | **MOOT.** `DataFetcher(use_oanda=True)` is hard-coded; the yfinance path is unreachable.                                                                                                                                                                                                                                                                                                                                                                   |

---

## 5. Findings: decision layer (entry scoring)

| ID            | Sev                | Class | Finding                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| ------------- | ------------------ | ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **N1**  | **Critical** | B     | **`generate_signal() -> None` is treated as "model missing".** `_sig_model_missing = sig is None or ...` sets `prob_raw=None`, so the XGB vote becomes NEUTRAL and `X = S*0.3 + R*0.3` is **fabricated** (strength and RSI double-counted). `None` is also returned for non-model reasons: insufficient bars, R:R or SL/TP build failure, score below engine minimum, probability below minimum, or any predict exception. The model only votes when an unrelated filter passed.                                                                                                                                                  |
| **N2**  | High               | B     | **Vote asymmetry.** `xgb_dir = BUY if p_up >= 0.55 else SELL` and the MC vote uses the same 55.0, with no neutral band. `p_up` of 0.45-0.549 votes SELL. The engine itself uses 0.5, so thresholds are inconsistent.                                                                                                                                                                                                                                                                                                                                                                                                                          |
| **N3**  | High               | B     | **Shared artifact and silent retrain.** All four profiles load one `trade_model_xgb.*` + `scaler.joblib`. A model older than 7 days (mtime, `retrain_every_n_days` default) is retrained at startup by whichever profile's live run sees it first, on that profile's whitelist (13 pairs for P2, 8 for P1/P3/P4), from live-fetched data, with no promotion gate. Retrain runs inside the live cycle; start jitter (1-10 s) is far shorter than a retrain, so concurrent runs can race on the same files. Overwrites happen at the profile that retrains, not by design.                                                                    |
| **N5**  | Med                | B     | **NaN handling differs.** Inference uses `.ffill().bfill().fillna(0)`, training uses `dropna()`. This bypasses `_build_matrix`'s "never zero-fill" guarantee.                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| **N6**  | Med                | B     | **Window mismatch.** Training fetches 5000 bars (about 10 weeks of M15, a single regime), inference 200. Recursive indicators (RSI, ATR, MACD) differ slightly. `TRAIN_LOOKBACK_BARS: 1500` in `config_profile.json` is never exported, so 5000 is used.                                                                                                                                                                                                                                                                                                                                                                                      |
| **N7**  | Low                | B     | **Candle completeness inferred from clock** (30 s tolerance). OANDA's `complete` flag is ignored.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| **N8**  | Low                | A     | **Config drift.** `config.py` ML block (`ML_LABEL_HORIZON=3`, `ML_TRAIN_GRANULARITY="H1"`, `ML_RETRAIN_HOURS=24`) is unread and contradicts live values (6, M15, 7 days). `TARGET_HORIZON` is not exported and only matches by default (6). `USE_MACD` defaults True in config, False in `FeatureConfig`. Indicator periods and `required_bars` are not wired to config. A parameter named `df_h1` actually receives the entry-timeframe df.                                                                                                                                                                                    |
| **N9**  | **Critical** | B     | **Engine strength-gap term is broken (CONFIRMED).** `_eval_strength_gap` slices `pair[:3]` / `pair[3:6]`, but the bot always passes `EUR_USD`-style pairs, so quote = `"_US"` and falls back to the default 50 while base is a real score. Real scores are about +/-2 (log excerpt: USD +2.06, EUR -0.72, GBP -0.22, AUD -1.47, JPY +0.12; max pair gap about 3.5), so `base > quote` is never true: **LONG always gets -5, SHORT always gets +10**, a constant 15-point SHORT-over-LONG bias on every pair. Even with correct parsing, the threshold of 10 is unreachable on a +/-2 scale, so the term would be permanently 0. |
| **N10** | High               | B     | **MC term is mis-scaled.** `_eval_mc` assumes fractions (`0.5`, `edge/0.15`, `>0.10`), but `p_up` is in percent. Agreement always saturates at **+20**, disagreement is always **-16**.                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| **N11** | High               | B     | **Engine score is compared to the profile's `MIN_CONVICTION`** (P1 50, P2 45, P3 55, P4 42), but it is a different 0-100 scale (25 base + up to 30 edge, 20 MC, 15 pivot, 10 gap). Derived arithmetic: with MC aligned and zero model edge, SHORT scores 55 and passes every profile; LONG scores 40 and needs +2 (P4), +5 (P2), +10 (P1), +15 (P3) more points. With MC disagreeing, passing is rare. Combined with N1, the "3-vote consensus" is not three independent votes, and BUY votes are suppressed relative to SELL.                                                                                                                  |
| **N12** | High               | B     | **Host backend mismatch can break every prediction.** `USE_MACD` is true. If an artifact was trained with MACD columns and a host lacks `pandas_ta`, those columns are missing at inference, `_build_matrix` raises for every pair, and N1 makes XGB abstain everywhere with only a WARNING. ATR/RSI would also silently use fallback formulas.                                                                                                                                                                                                                                                                                             |

Carry-over: per-pair `except: continue` in training (partial universe trained silently); concat column union plus global `dropna()` can silently drop a pair's rows; no data snapshot (training data is live-fetched).

---

## 6. Dangerous defaults outside ML scope

| ID           | Sev               | Finding                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| ------------ | ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **D1** | High              | `_revise_owned_position` can raise TP to `current +/- 3*ATR` every cycle for any owned trade, with no profit gate and regardless of `DYNAMIC_TP=false`. It can override the Smart TP and the Fib-zone TP scaling (min 10 pips) one cycle after entry. Check with `grep STRUCT_REVISE logs/*.log`.                                                                                                                                                                                                                                                                                          |
| **D2** | Med               | Step 5 (`DynamicPositionManager`) is effectively a no-op: `enabled` defaults to False and is not passed, `MAX_HOLD_BARS=9999`. Real exits are broker SL/TP, D1, and QUICK-FLIP (strength + MC only).                                                                                                                                                                                                                                                                                                                                                                                         |
| **D3** | Med               | Step 4 calls `fetch_candles(instrument, gran)` but the signature is `(api, instrument, gran)`. The exception is swallowed by `contextlib.suppress`, so `--confluence` would silently block every pair.                                                                                                                                                                                                                                                                                                                                                                                     |
| **D4** | Low               | D-Gate summary logs "SHADOW ... log-only" even though `D_GATE_SHADOW` is false (enforced) for all four profiles.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| **D5** | Low               | `max_sl_pips=None` skips the SL-side sanity check in `open_oanda_order_simple`; OANDA rejection is the only guard.                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| **D6** | Low               | Config drift: `meta.note` says cooldown 3h but value is 8h; header says v6.8.4 while the bot is v6.8.5.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| **D7** | Low               | SL/TP reference price is `bid` for both sides; BUY fills at ask, so SL/TP are anchored one spread away.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| **D8** | Med *(pending)* | `get_live_prices` (entry price, spread, and the exit manager) builds its own client via `utils.oanda_client` and queries `config.OANDA_ACCOUNT_ID` (= env `OANDA_ACCOUNT_ID_1`, with `OANDA_ENV = "practice"`), not the `api`/account chosen by `--live` and `-a`. If environment and account do not match it fails with a plain `print` (not logged), and the bot silently falls back to the last candle close with an assumed 1.0-pip spread, so entry, SL and TP are anchored to a stale price. Check `utils/oanda_client.py` and `grep "Price fetch failed" logs/*.log`. |
| **D9** | Med *(pending)* | Strength pool coverage. `config.STRENGTH_PAIRS` has no CHF pair (the live pool comes from `utils/strategy_config.py`, not yet seen). If CHF is in `CURRENCIES` without a CHF pair it scores exactly 0.0, so `USD_CHF` gaps are measured against a constant. Separately, NZD and CHF scores are identical in the Oct log excerpt (e.g. 0.1029), which suggests one shared source pair. Verify.                                                                                                                                                                                              |

---

## 7. RETAIN / REPAIR / REPLACE / RETIRE (revised)

- **RETAIN:** XGBoost family; shared `FeatureEngine`; `_build_matrix` + single `predict_p_up` contract; single injected scaler instance; closed-candle trimming at source; `TimeSeriesSplit` intent; OANDA integration patterns.
- **REPAIR:** decision-layer abstain handling (N1, N2); engine score units (N9-N11); evaluation methodology (F2); artifact manifest and integrity (F7, N3); config wiring (N8); NaN policy parity (N5).
- **REPLACE:** in-cycle retraining with an offline training job and a promotion gate (S4). Nothing else wholesale.
- **RETIRE:** auto-retrain on stale mtime in the live path; legacy `.pkl` fallback; `.cfg.json` `setattr` overwrite of live config; dead config keys.

---

## 8. Proposed implementation order

Every step is a separate change behind a default-off switch. No step may alter live behavior until its acceptance tests pass. Each behavior change (class B) is classified and merged separately from cleanups (class A).

1. **S0 — Observability only (no behavior change).** Per pair, log `p_up`, an abstain reason (`score_fail` / `exception` / `missing_feature` / `bars`), and the engine score breakdown. Accumulate at least 20 rows before any decision.
2. **S1 — `OPT_XGB_DIRECT_VOTE`.** Take the XGB vote from `strat_engine._predict(latest)` directly. Abstain only on a real exception, recorded as `ML_ABSTAIN(reason)`, never as a substitute value.
3. **S2 — `OPT_ENGINE_SCORE_FIXES`.** Fix pair parsing (N9) and MC scale (N10); decide the score/threshold relationship (N11).
4. **S3 — Artifact manifest (additive).** Run ID, commit, SHA-256 of all four files, universe, granularity, lookback, horizon, library versions, `pandas_ta` flag. Atomic write, lockfile, load refuses on mismatch.
5. **S4 — Offline training + promotion gate.** Per-pair time-ordered walk-forward with 6-bar embargo, always-up baseline, immutable data snapshot, explicit promote step.
6. **S5 — Feature scaling hygiene.** Normalize or drop price-unit features (F3); retrain only after S3/S4 exist.

Config precedence CLI > run.env > config_bot/default must be preserved throughout.

---

## 9. Acceptance tests

| ID           | Test                                                                                                                                                                                                                                               | Blocking |
| ------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| **T1** | **Window parity.** Last-row value of every feature, 5000-bar vs 200-bar build, over at least 500 end bars. Hard tolerance for non-recursive features; for RSI/ATR/MACD record the difference in sigma and set the tolerance after measuring. | Yes      |
| **T2** | **Backend parity.** `pandas_ta` vs fallback for ATR and RSI on identical data.                                                                                                                                                             | Yes      |
| **T3** | **Contract.** Missing column, NaN, or wrong width must raise; the decision layer must record `ML_ABSTAIN(reason)` and never synthesize an XGB vote.                                                                                        | Yes      |
| **T4** | **Artifact integrity.** Tampering with any of the four files makes load refuse.                                                                                                                                                              | Yes      |
| **T5** | **Score sanity.** For identical inputs, LONG and SHORT engine scores are symmetric within a stated tolerance (guards N9-N11).                                                                                                                | Yes      |
| **T6** | **Shadow run.** New voting path runs alongside the live path, logging only, for an agreed number of cycles with no order interference.                                                                                                       | Yes      |

---

## 10. Open items (need runtime evidence)

```bash
grep -n "STRENGTH_PAIRS\|CURRENCIES" -A12 utils/strategy_config.py       # D9: does the pool contain a CHF pair?
grep -c "Price fetch failed" logs/*.log                                   # D8
grep -n "environment\|account" utils/oanda_client.py | head -20           # D8: which env/account do live prices use?
grep -h "XGB-LOW.*score=" logs/*.log | wc -l                              # how often N1 fires
grep -c "XGB model missing" logs/*.log; grep -c "SCORE " logs/*.log
grep -h "XGB-FAIL" logs/*.log | sed 's/.*\] //' | cut -c1-80 | sort | uniq -c | sort -rn | head
grep -h "Model stale\|Training on\|Training complete\|Top features" logs/*.log | tail -40   # F3, N3, N6
grep -c "STRUCT_REVISE" logs/*.log                                        # D1
ls -la --time-style=full-iso trade_model_xgb* scaler.joblib; crontab -l   # N3 who retrains, overlap
python -c "import pandas_ta"; pip list | grep -Ei 'pandas|numpy|xgboost|scikit|pandas.ta|joblib'   # every host: F4, N12
git ls-files | grep -Ei 'test_|shadow|backtest'                           # existing coverage
```

Hosts to compare: the OCI VM and the laptop (both run the same account).

---

## 11. Revision history of findings (this audit)

- F9 withdrawn: `should_close` is not called by this bot.
- F13 moot: yfinance path unreachable.
- F11 downgraded: MACD warm-up is removed by `dropna()`.
- F2 refined: validation folds are later pairs, not later time.
- Retrain age is 7 days (dataclass default), not 30 (`getattr` fallback).
- `OPT_SLOPE_HONOR_CONFIG` is inactive while `TREND_FILTER_ENABLED` is false.
- N9 confirmed: strength scores from `build_strength_matrix` are about +/-2 (verified against log excerpt), so the engine's strength-gap term is a constant +10 SHORT / -5 LONG. Added D8 and D9 as pending.
