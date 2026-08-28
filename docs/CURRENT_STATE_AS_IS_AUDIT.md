# CURRENT-STATE AS-IS TECHNICAL AUDIT — ai_training_cnn FX Trading System

- Audit date: 2026-08-26
- Repository: `/home/nie/projects/ai_training_cnn`
- Branch: `v20260825` (HEAD `2995e0d`)
- Nature: READ-ONLY audit of what the code and running system do **today**.
- Evidence: repository source files (cited by path + symbol), the installed user crontab, running logs under `logs/`, and filesystem state. Where evidence is insufficient, the item is marked **UNKNOWN**.
- **No source code was modified by this audit.** This document is a new file only.

---

## 1. Source of Truth

| Layer | Source | Status |
|---|---|---|
| Active schedule | Installed user crontab (verified `crontab -l`, 2026-08-26) | AUTHORITATIVE for runtime |
| Production trading entry points | `fx_trade_bot_v6.8.3.py` (Profile2), `fx_trade_bot_v6.8.4.1.py` (Profile3) | LIVE |
| Scheduled MC runner | `fx_monte_carlo_v1.py` | LIVE |
| Scheduled retrain | `retrain_model.py` (cron job, **observed failing**) | LIVE-scheduled |
| Config | `config_bot.py`, `config_bot_profile2.py`, `config_bot_profile3.py`, `config_oanda.py`, `config.py`, `.env` | LIVE |
| Support modules | `fx_trade_bot_utils.py`, `fx_trade_bot_mc.py`, `fx_trade_bot_ml.py`, `strategy_decision.py`, `data_pipeline.py`, `utils/*` | partially LIVE (see §3) |
| Stale / non-authoritative files in repo | `cronjobs.txt`, `crontab`, `docker-compose.yml`, `Dockerfile`, `fx-trade-bot.service`, `README*.md`, `TBD*.md`, `cheet_sheet*.md`, `tmp/` | NOT the active schedule — ignored as runtime evidence |

### Verified runtime facts
- No bot process was running at inspection time (`ps aux`); cron invocations are transient, one-shot processes.
- The systemd unit `fx-trade-bot.service` (repo file `fx-trade-bot.service`, `ExecStart=... fx_trade_bot_v6.py`) is **not registered**: `systemctl status fx-trade-bot` → `Unit fx-trade-bot.service could not be found`.
- The repo files `cronjobs.txt` (references `fx_trade_bot_integrated_v6.5.py`, which does not exist) and `crontab` (references a docker-compose run) do **not** match the installed crontab. The installed crontab is the operative schedule.

---

## 2. Runtime Reality & Component Separation

### 2.1 Separate processes (installed crontab — active entries only)

| # | Schedule | Command | Log | Component |
|---|---|---|---|---|
| 1 | `3,18,33,48 * * * *` | `/home/nie/projects/gemini_api/scheduled_runner_v1.3.py` | gemini_api logs | EXTERNAL project — separate repo; has its own `utils/` copy |
| 2 | `5 0 * * *` | gemini_api `rotate_logs.sh` | gemini_api logs | EXTERNAL |
| 3 | `0 8 * * *` | `fx_monte_carlo_v1.py --timeframe D` | `logs/mc_daily.log` | MC daily runner (THIS repo) |
| 4 | `0 */4 * * *` | `fx_monte_carlo_v1.py --timeframe H4` | `logs/mc_h4.log` | MC H4 runner (THIS repo) |
| 5 | `0 0 * * 0` | `mv logs/bot_h4.log ...` | — | Log rotation — target `logs/bot_h4.log` does not exist → no-op/error |
| 6 | `0 3 * * *` | `find daily_results -name "*.json" -mtime +7 -delete` | — | MC JSON retention (7 days) |
| 7 | `0 0 * * *` | `python retrain_model.py` | `logs/bot_cron.log` | Daily XGBoost retrain — **observed failing**: log contains `/bin/sh: 1: python: not found` |
| 8 | `*/15 * * * *` | `fx_trade_bot_v6.8.3.py --profile2 --timeframe 15m` | `logs/fx_trade_bot_v6.8.4_profile2.log` | **Trading bot — Profile2 / Account 002** |
| 9 | `7-59/15 * * * *` | `fx_trade_bot_v6.8.4.1.py --profile3 --timeframe 15m` | `logs/fx_trade_bot_v6.8.4_profile3.log` | **Trading bot — Profile3 / Account 003** |

Notes:
- Entries 1–2 live in `/home/nie/projects/gemini_api/`, a **separate repository** that contains its **own copies** of `utils/risk_integration.py`, `utils/signal_instrumentation.py`, `utils/dynamic_risk_manager.py`, `utils/pyramid_cluster.py`, `utils/cluster_state_store.py`, `utils/trading_core.py`, etc. Its `sys.path[0]` is the gemini_api directory, so `from utils import ...` resolves to its own `utils/`, **not** to this repo's `utils/`. Whether the two copies ever converge is **UNKNOWN**.
- `launch_both_profiles.py` (runs `fx_trade_bot_v6.8.2_profile2.py` + `_profile3.py` via `subprocess`) exists but was **not** running at inspection; it is not in the crontab.

### 2.2 LIVE runtime path (proven from cron + imports)

```
cron #8/#9
  → fx_trade_bot_v6.8.3.py / fx_trade_bot_v6.8.4.1.py
      → main()  [fx_trade_bot_v6.8.3.py:464]
          → apply_jitter(1–10 s)  [utils/utils.py:10]
          → ensure_model()        [fx_trade_bot_ml.py:11]   loads/trains trade_model_xgb.pkl
          → build_strength_matrix [utils/strategy_helpers.py:146]  (OANDA data)
          → DataFetcher.fetch     [data_pipeline.py:440]     M15 candles from OANDA
          → FeatureEngine.build   [data_pipeline.py:194]
          → fetch_weekly_ema100   [fx_trade_bot_v6.8.3.py:98] W candles
          → MCGenerator.run_for_pair [fx_trade_bot_mc.py:88] (in-process MC)
          → DynamicPositionManager.update_all [fx_trade_bot_utils.py:1099] (manages existing trades)
          → get_open_position     [fx_trade_bot_utils.py:255]
          → StrategyEngine.generate_signal [strategy_decision.py:101]  (output partially unused, see §5)
          → calc_weighted_score   [fx_trade_bot_v6.8.3.py:414]
          → evaluate_trend_and_tp [fx_trade_bot_v6.8.3.py:112]
          → compute_sl_zone       [fx_trade_bot_utils.py:933]
          → open_oanda_order_simple [fx_trade_bot_utils.py:414]  (MARKET + separate SL/TP orders)
          → send_telegram_message [telegram_message.py:17]
```

```
cron #3/#4
  → fx_monte_carlo_v1.py
      → main()          [fx_monte_carlo_v1.py:210]
          → run_mc()    [fx_monte_carlo_v1.py:131 area]  yfinance data
          → writes daily_results/{h4,daily}_mc_<PAIR>_<UTC>.json
          → send_telegram_message
```

```
cron #7 (currently FAILING)
  → retrain_model.py
      → fetch_all_data() / train_model() / save_model()
      → writes trade_model_xgb.pkl (+ backup)
  Observed failure: `logs/bot_cron.log` = "/bin/sh: 1: python: not found"
```


### 2.3 Exists / Imported / Called / LIVE classification

| Module | Exists | Imported (LIVE process) | Called (LIVE process) | LIVE |
|---|---|---|---|---|
| `fx_trade_bot_v6.8.3.py` | ✅ | — | — | ✅ (cron #8) |
| `fx_trade_bot_v6.8.4.1.py` | ✅ | — | — | ✅ (cron #9) |
| `fx_monte_carlo_v1.py` | ✅ | — | — | ✅ (cron #3,#4) |
| `retrain_model.py` | ✅ | — | — | ✅-scheduled (currently failing) |
| `config_bot.py` | ✅ | ✅ | (values read) | ✅ |
| `config_bot_profile2.py` | ✅ | ✅ | (values read) | ✅ |
| `config_bot_profile3.py` | ✅ | ✅ | (values read) | ✅ |
| `config_oanda.py` | ✅ | ✅ | (`api` used for all OANDA calls) | ✅ |
| `config.py` | ✅ | ✅ | (fallback lookups) | ✅ |
| `telegram_message.py` | ✅ | ✅ | `send_telegram_message` | ✅ |
| `fx_trade_bot_utils.py` | ✅ | ✅ | core helpers | ✅ |
| `fx_trade_bot_mc.py` | ✅ | ✅ | `MCGenerator`, `MCConfig` | ✅ |
| `fx_trade_bot_ml.py` | ✅ | ✅ | `ensure_model` | ✅ |
| `strategy_decision.py` | ✅ | ✅ | `generate_signal` (output partially unused) | ✅ |
| `data_pipeline.py` | ✅ | ✅ | `FeatureEngine.build`, `ModelWrapper`, `DataFetcher` | ✅ |
| `utils/trading_core.py` | ✅ | ✅ | `forex_market_closed`; `oanda_client` (via `utils/__init__`) | ✅ |
| `utils/strategy_helpers.py` | ✅ | ✅ | `build_strength_matrix`, `format_strength_ranking`, `get_live_prices` | ✅ |
| `utils/utils.py` | ✅ | ✅ | `apply_jitter` | ✅ |
| `utils/__init__.py` | ✅ | ✅ (executed as package import) | import hub only | ✅ (side effects: instantiates clients) |
| `utils/data_provider.py`, `utils/schemas.py`, `utils/oanda_execution.py`, `utils/find_support_resistence.py`, `utils/sl_tp_helper.py`, `utils/indicator_provider.py`, `utils/regime_detector.py`, `utils/breaking_entry.py`, `utils/currency_strength.py`, `utils/quota_guard.py`, `utils/ml_confirmation.py` | ✅ | ✅ (via `utils/__init__.py`) | ❌ no call site in LIVE path | IMPORTED ONLY |
| `utils/signal_instrumentation.py` | ✅ | ❌ | ❌ | **NOT LIVE** (observation layer) |
| `utils/risk_integration.py` | ✅ | ❌ | ❌ | **NOT LIVE** |
| `utils/dynamic_risk_manager.py` | ✅ | ❌ | ❌ | **NOT LIVE** |
| `utils/pyramid_cluster.py` | ✅ | ❌ | ❌ | **NOT LIVE** |
| `utils/cluster_state_store.py` | ✅ | ❌ | ❌ | **NOT LIVE** |
| `utils/position_direction.py`, `utils/custom_strategy.py`, `utils/range_detector.py`, `utils/check_reverse_and_close.py`, `utils/calculate_pivots.py`, `utils/calculate_risk_reward.py`, `utils/calc_weighted_score.py`, `utils/get_last_trade_info.py`, `utils/ai_client.py`, `utils/yahoo_finance.py`, `utils/calculate_currency_strength.py` | ✅ | ❌ | ❌ | **NOT LIVE** |
| `sl_zone_hierarchy.py` | ✅ | ❌ | ❌ | NOT LIVE (tests only; LIVE bots use `fx_trade_bot_utils.compute_sl_zone`) |
| `portfolio_balance.py` | ✅ | ❌ | ❌ | NOT LIVE (import commented out in `fx_trade_bot_v6.8.3.py`) |
| `fx_trade_bot.py`, `fx_trade_bot_v6.py`, `fx_trade_bot_v6.8.py`, `fx_trade_bot_v6.8.2.py`, `fx_trade_bot_v6.8.2_profile2.py`, `fx_trade_bot_v6.8.2_profile3.py`, `fx_trade_bot_v6.8.4.py`, `signal_generator*.py`, `close_all*.py`, `check_*.py`, `OANDA_ACCOUNT_ID_3.py`, etc. | ✅ | ❌ | ❌ | NOT LIVE (not in installed crontab) |

---

## 3. Project Architecture

### 3.1 Overall purpose
Automated FX trading on OANDA practice accounts (2 accounts, 12 currency pairs), driven by: currency-strength momentum, indicator scoring (RSI/ADX), an XGBoost model, and Monte-Carlo forecast probabilities, plus a scheduled Monte-Carlo reporting process and a daily model-retrain job. All order placement, position queries and SL/TP modifications go through the OANDA v20 REST API (`oandapyV20`).

### 3.2 Components & responsibilities

**Trading bots (cron #8/#9) — the only order-placing components**
- `fx_trade_bot_v6.8.3.py` — Profile2 / Account 002. 15-minute cron. Executes the full pipeline in one shot (no daemon loop).
- `fx_trade_bot_v6.8.4.1.py` — Profile3 / Account 003. 15-minute cron (offset minutes 7,22,37,52).
- Both call the same helpers; profile differences come from `config_bot_profile2.py` / `config_bot_profile3.py`.

**Scheduled MC runner**
- `fx_monte_carlo_v1.py` — daily (`D`) and every 4h (`H4`). yfinance-based geometric Brownian Monte-Carlo; writes JSON per pair to `daily_results/`; sends a Telegram report. **Does not place orders.** Outputs are not read by the trading bots (see §7).

**Scheduled retrain**
- `retrain_model.py` — retrains `trade_model_xgb.pkl` on M15 OANDA data (500 bars/pair, 12 pairs), backups the old model. Cron entry currently fails (`python: not found`).

**Config**
- `config_bot.py` — central strategy config + import-time validation (`validate_config()` runs on import, exits if errors — `config_bot.py:352`).
- `config_bot_profile2.py` / `config_bot_profile3.py` — profile overrides (weights, thresholds, account ID).
- `config_oanda.py` — OANDA credentials/accounts from `.env`, instantiates module-level `api` (`config_oanda.py:81`) used by LIVE bots.
- `config.py` — legacy fallback config (only reached via `cfg_bot` when key absent in profile + `config_bot`).

**Shared libraries**
- `fx_trade_bot_utils.py` — order execution, position queries, SL-zone computation, dynamic position manager, cooldown, MC loader.
- `fx_trade_bot_mc.py` — `MCConfig` + `MCGenerator` (in-process MC used by the bots).
- `fx_trade_bot_ml.py` — `ensure_model()` load-or-train XGBoost.
- `strategy_decision.py` — `StrategyEngine.generate_signal` (used for confluence only; main score path bypasses its direction — see §5.8).
- `data_pipeline.py` — feature engineering (`FeatureEngine`), ATR, XGBoost wrapper (`ModelWrapper`), data fetch (`DataFetcher`).
- `utils/trading_core.py` — market-hours check, OANDA/Gemini client singletons (clients instantiated at import).
- `utils/strategy_helpers.py` — currency strength matrix, live bid/ask.
- `telegram_message.py` — Telegram notifications (MarkdownV2-escaped).

### 3.3 Dependencies & boundaries
- OANDA: `oandapyV20` client (`config_oanda.api`) — instruments candles, positions, orders, trades, accounts, pricing.
- Market data: OANDA (M15 candles via `DataFetcher`; strength candles via `utils.oanda_client`; weekly via direct `InstrumentsCandles`). yfinance used only by `fx_monte_carlo_v1.py` and as MC fallback.
- Telegram: `telebot` with token/chat from `.env`.
- Gemini: `google.genai` client is **instantiated at import** (`utils/trading_core.py:30`, `USE_GEMINI_AI=True` in `config.py`) but no LIVE bot code calls it. Gemini APIs exist in `utils/strategy_helpers.py`/`utils/trading_core.py` (news sentiment) — not in the LIVE path.
- `utils/__init__.py` import hub pulls in 11 extra modules into every LIVE process (import side effects: creates `oanda_client` in `utils/trading_core.py:29` and `api` in `utils/oanda_execution.py:8`).

### 3.4 External services (required)
1. OANDA v20 REST API (practice environment; token/accounts in `.env`).
2. Telegram Bot API (alerts).
3. yfinance (scheduled MC only; bot MC fallback).
4. (Instantiated, unused by LIVE path) Google Gemini API client.

### 3.5 Persistence
See §7.

### 3.6 Logging / observation
- Bots: `logging.basicConfig` → file `bot_profile2.log` / `bot_profile3.log` (repo root) **and** stdout, which cron redirects to `logs/fx_trade_bot_v6.8.4_profile2.log` / `_profile3.log`. Log level INFO. `oandapyV20` logger set to WARNING (unless DEBUG_MODE). `fx_trade_bot_v6.8.3.py:256-258`, `fx_trade_bot_v6.8.3.py:302-303`.
- MC runner: prints to stdout → `logs/mc_h4.log` / `logs/mc_daily.log` + Telegram.
- Dedicated observation layer (`utils/signal_instrumentation.py`) exists but is **not reachable** from any LIVE entry point in this repo (see §8).



---

## 4. End-to-End Workflow & Data Flow (LIVE trading bot, one cron run)

| Stage | Module / function | Input | Transformation | Output / destination |
|---|---|---|---|---|
| 0. Start | `__main__` (both bots) | CLI `--profileX --timeframe 15m` | `apply_jitter(1,10)` sleep; profile select; config lookup | profile config, account ID |
| 1. Market check | `forex_market_closed()` `utils/trading_core.py:420` | wall clock (Europe/London) | Sat, Sun<21:00, Fri≥21:00 → closed | silent return (no Telegram) |
| 2. Model | `ensure_model()` `fx_trade_bot_ml.py:11` | `trade_model_xgb.pkl` mtime | load; if >`retrain_every_n_days` (7) stale or missing → retrain on 12 pairs | `strat_engine.model`, `feature_names` |
| 3. Strength | `build_strength_matrix()` `utils/strategy_helpers.py:146` | OANDA H1/H4/H8 candles for 10 `STRENGTH_PAIRS` | momentum % (5/20-bar) × TF weights | `scores{ccy}` (used for gap + S-score) |
| 4. Pairs | main() Step 2 | 12 pairs | `USE_TOP_PAIRS_ONLY=False` → all | scan list |
| 5. Data | `DataFetcher.fetch` `data_pipeline.py:440` | OANDA `M15`, count=200 | OHLCV DataFrame | `pair_data[pair]["raw"]` |
| 6. Features | `FeatureEngine.build` `data_pipeline.py:194` | raw M15 | rets, vol, body, ATR(14), RSI(14), ADX(14), MACD, distance-from-extrema, volume, time features | `pair_data[pair]["df"]` (+ `atr`,`rsi`,`adx` last row) |
| 7. Weekly EMA | `fetch_weekly_ema100` `fx_trade_bot_v6.8.3.py:98` | OANDA `W`, count=105 | EMA100 of weekly closes | cache `weekly_ema100` (per pair) |
| 8. MC | `MCGenerator.run_for_pair` `fx_trade_bot_mc.py:88` | **M15 raw df** + H4-derived config (lookback 90, forecast 8, `PERIODS_YEAR=252*6`) | GBM simulation, 5000 paths, 90% band | `mc_cache[pair]` (in-memory only; **not saved**) |
| 9. Exit mgmt | `DynamicPositionManager.update_all` `fx_trade_bot_utils.py:1099` | open trades + `atr` | time-exit(12 bars), breakeven(1.5×ATR), trailing SL(trigger 2.5×ATR, 1.5×ATR) | OANDA `TradeCRCDO` SL updates / closes |
| 10. Positions | `get_open_position` `fx_trade_bot_utils.py:255` | OANDA positions | per-instrument open map | `open_pos_by_oanda`, count |
| 11. Signal | `StrategyEngine.generate_signal` `strategy_decision.py:101` | features, MC, strength, price | XGB `p_up`, filters, SL/TP | `Signal` object (see §5.8) |
| 12. Score | `calc_weighted_score` `fx_trade_bot_v6.8.3.py:414` | gap, RSI, ADX, xgb_prob, mc p_up | consensus vote + weighted FINAL | direction + score dict; **skip if FINAL < 30** |
| 13. Trend/TP | `evaluate_trend_and_tp` `fx_trade_bot_v6.8.3.py:112` | direction, MC p_up, EMA, weekly EMA100 | Rule A (OFF), Rule B (weekly EMA100), TP pips | allow/deny + TP pips |
| 14. SL | `compute_sl_zone` `fx_trade_bot_utils.py:933` | H4/H8/D candles, ATR | H4 zone(6 bars)→H8(4)→D(2), ±25p, ≥20p min dist; ATR-2× fallback; 35p fixed last resort | `sl_price` |
| 15. TP | main() Step 7 | smart_tp_pips | price offset | `tp_price` |
| 16. Execute | `open_oanda_order_simple` `fx_trade_bot_utils.py:414` | candidate (ranked by FINAL) | MARKET order `±10000` units; then separate STOP_LOSS and TAKE_PROFIT orders | OANDA orders |
| 17. Notify | `send_telegram_message` `telegram_message.py:17` | trade summary | MarkdownV2 escaping | Telegram chat |

Guardrails enforced in execution loop: skip if position already open (per instrument); skip if instrument already executed this run; skip if `open_pos_count >= MAX_OPEN (4)`.


---

## 5. Core Trading Logic & Rules (what the code actually implements)

### 5.1 Market-data requirements
- Timeframe for entry analysis: **15m** (cron passes `--timeframe 15m`; `OANDA_GRANULARITY = "M15"` — `fx_trade_bot_v6.8.3.py:307`). 200 M15 candles fetched.
- **No closed-candle rule in the LIVE entry path.** `DataFetcher._from_oanda` (`data_pipeline.py:447`) reads `resp["candles"]` and does **not** filter on `complete`. The last (forming) M15 candle is included in feature computation and as `current` fallback price.
- MC simulation uses the same raw M15 data (including the forming candle).
- The only closed-candle rule exists in `calculate_stop_loss` (`fx_trade_bot_utils.py:33`, `REQUIRED_H4_CANDLES=4`, "only fully closed H4") — but this function is **not called** by the LIVE bots (they use `compute_sl_zone`). `get_candles` in `utils/strategy_helpers.py:38` filters `complete` — used by the strength matrix path (strength uses `get_pair_momentum` → `get_candles` which filters closed candles).

### 5.2 Timeframes used
- 15m entry (M15 OANDA).
- H1/H4/H8 for the currency strength matrix (`STRENGTH_TIMEFRAMES = {"H1":1,"H4":3,"H8":6}` — `config.py:93`).
- H4 / H8 / Daily for SL zones (`compute_sl_zone` TF_LIST).
- Weekly (W) for the EMA100 counter-trend gate.
- H4-configured MC lookback/forecast applied to the M15 data series (see §4 stage 8).

### 5.3 Indicator calculations
- RSI(14): `pandas_ta.rsi` (`data_pipeline.py:232`); `rsi_slope = rsi.diff(3)`.
- ADX(14): local `adx()` in `data_pipeline.py:34` (Wilder-style DMI, `.fillna(0.0)`).
- ATR(14): `pandas_ta.atr`, fallback manual TR (`data_pipeline.py:104-148`).
- MACD(12,26,9): `pandas_ta.macd` (feature column only; MACD not used in scoring).
- Currency strength: `get_pair_momentum` (`utils/strategy_helpers.py:110`) — blended fast(5-bar)/slow(20-bar) % moves, weights 0.7/0.3, averaged per currency over pairs × TF weights; ATR-normalization and acceleration flags default **off** (`config.py:98-102`).
- Weekly EMA100: `ewm(span=100, adjust=False)` over weekly closes (`fx_trade_bot_v6.8.3.py:79-88`).
- EMA10 slope: `(ema_now - ema_prev)/ema_prev` over 5 bars (Rule A; **disabled**).


### 5.4 Entry conditions (all must pass)
1. Strength gap `abs(base_score − quote_score) ≥ MIN_SCORE_GAP = 0.25` (`calc_weighted_score`/Step 7; logs show `gap=… ≥ 0.25 — QUALIFIED`).
2. Direction consensus ≥2 of 3 votes (`REQUIRE_DIRECTION_CONSENSUS=True`, `CONSENSUS_THRESHOLD=2`): Strength(vote) + XGB(vote) + MC(vote) — `calc_weighted_score`.
   - **Effective behavior (verified from code + logs):** `xgb_prob` passed to `calc_weighted_score` is **always 0.0** because the `Signal` object returned by `generate_signal` exposes `raw_prob`, while the bot reads `sig.probability/model_prob/prob` (all absent → `0.0`) — `fx_trade_bot_v6.8.3.py:629`, `strategy_decision.py:213-229`. Hence `xgb_dir = "SELL"` on every pair (logs: `XGB=SELL` for all), and the X component falls back to `X = 0.3·(S+R)`.
   - Consequence: BUY requires Strength=BUY **and** MC=BUY; SELL requires Strength=SELL and/or MC=SELL (XGB always contributes one SELL vote).
3. Weighted score: `FINAL = 0.40·S + 0.15·R + 0.15·A + 0.20·X + 0.10·M ≥ 30.0` (`MIN_CONVICTION_SCORE`).
   - `S = min(100, |gap|/3.5·100)`
   - `R = min(100, (50−rsi)·2)` for BUY; `min(100, (rsi−50)·2)` for SELL
   - `A`: ADX×2.0 (cap 100), floored at 20, +10 boost if ADX≥30
   - `X = xgb_prob·100` (=0) → fallback `0.3·(S+R)`
   - `M = p_up` (MC % up)
4. Trend filter `evaluate_trend_and_tp`:
   - Rule A (EMA10-slope alignment) — **disabled** (`TREND_FILTER_ENABLED=False` in `config_bot.py:198` and profile configs; logs confirm `ema_cross_filter=False`).
   - Rule B (weekly EMA100 counter-trend) — active when `WEEK_EMA100_FILTER_ENABLED=True` (both profiles). BUY blocked if price < EMA100; SELL blocked if price > EMA100.
     - **Observed anomaly (2026-08-26 logs):** the gate evaluates at exactly `1.00000` for every pair (profile2 log: `SKIP SELL … Price above 1.00000`, `SKIP BUY … Price below 1.00000`), which blocks most candidates. Root cause **UNKNOWN**.
5. MC availability: `REQUIRE_STRONG_MOMENTUM=False` (`config_bot.py:167`) → MC regime does **not** restrict entry; MC `p_up` still votes.
6. Duplicate/instrument guards (open position, same-run, MAX_OPEN=4).
7. Cooldown: **disabled** (`REMOVE_COOLDOWN=True`; `last_closed = []`, `fx_trade_bot_v6.8.3.py:394`).

### 5.5 Exit conditions (managed by `DynamicPositionManager.update_all`, runs every cycle before new entries)
- **Time exit:** position held ≥ `MAX_HOLD_BARS = 12` bars (bar hours by timeframe: 15m=0.25) → `close_position` (`fx_trade_bot_utils.py:1156-1162`).
- **Breakeven:** profit ≥ `1.5 × ATR` (pips) → SL = entry ±1 pip (`fx_trade_bot_utils.py:1190-1197`).
- **Trailing SL:** profit ≥ `2.5 × ATR` (pips) → SL = current price ∓ `1.5 × ATR` (`fx_trade_bot_utils.py:1200-1211`). Only moves SL in the favorable direction.
- **Dynamic TP (raise):** **disabled** (`DYNAMIC_TP=False` in `config_bot.py:97`).
- **SL/TP server-side:** SL and TP are attached as GTC orders at order creation (`open_oanda_order_simple`).
- There is **no ML-based close** in the LIVE path: `StrategyEngine.should_close` (`strategy_decision.py:87`) is not called by the LIVE bots.

### 5.6 SL / TP / trailing values
- SL: `compute_sl_zone` — H4(6 closed candles) zone ±25p buffer; if <20p min distance step up to H8(4) → Daily(2) → ATR-2× → fixed 35p (`fx_trade_bot_utils.py:933-1004`; `config_bot.py:178-184,195-204`).
  - Note: `calculate_stop_loss`'s 200-pip SL cap (`SL_MAX_ALLOWED_PIPS=200`) is **not** applied by the LIVE bots.
- TP (Profile2, `fx_trade_bot_v6.8.3.py`): base **30 pips**; ×1.0 normal, ×2.0 (60p) when `p_up ≥ 75%`.
- TP (Profile3, `fx_trade_bot_v6.8.4.1.py`): base **50 pips** (`BASE_TP_PIPS`), `TP_MULT=2.5` → **125 pips** normal; `TP_STRONG_MULT=3.0` → **150 pips** when `p_up ≥ 75%` (`config_bot_profile3.py:71-73`).
- EMA100 buffer (30p TP push-away): present in `fx_trade_bot_v6.8.3.py` TP path; **absent** in `fx_trade_bot_v6.8.4.1.py` TP path.

### 5.7 Position sizing & pyramiding
- Fixed size: `DEFAULT_LOT_SIZE = 10000` units per order (both profiles). No equity-based sizing in the LIVE path (`FeatureConfig.atr_position_sizing` exists in `data_pipeline.py:61` but is unused by the LIVE bots).
- Max 4 open positions (`MAX_OPEN_POSITIONS = 4`).
- **No pyramiding in the LIVE path.** `utils/pyramid_cluster.py` implements pyramiding but is not reachable from the LIVE entry points.

### 5.8 XGBoost model usage (important finding)
- `ensure_model` loads `trade_model_xgb.pkl` into `strat_engine.model`.
- `StrategyEngine.generate_signal` computes `p_up` via `_predict` and returns a `Signal` with `raw_prob`/`action`.
- The LIVE bots read `sig.probability`/`sig.model_prob`/`sig.prob` — none of which exist on `Signal` — so the model probability **never reaches** `calc_weighted_score` (always 0.0; X component is derived from S+R instead).
- `generate_signal`'s `action`/`direction` are used **only** in the confluence filter (`MULTI_TF_CONFLUENCE`), which is **disabled** (`config_bot.py:107`).
- Net effect: the XGBoost model is loaded every run but its predictions do **not** influence LIVE decisions (only its vote is fixed to "SELL" via the 0.0 bug path).

### 5.9 Risk thresholds & limits (LIVE)
- Max open positions: 4 per account.
- Consensus ≥2/3; FINAL ≥ 30.
- SL min distance 20p, H4 zone buffer 25p, ATR SL mult 2.0, fixed fallback 35p.
- No daily loss limit, no equity-based stop, no max drawdown circuit breaker in the LIVE code path (**UNKNOWN if enforced elsewhere**; none found in repo).

---

## 6. Configuration & Parameters (material settings)

| Parameter | Current Value | Unit | Location | Effect |
|---|---|---|---|---|
| `--timeframe` (cron) | `15m` | — | crontab → `args.timeframe` | OANDA granularity `M15` |
| Cron schedule P2 | `*/15` (min 0,15,30,45) | min | crontab | bot run frequency |
| Cron schedule P3 | `7-59/15` (min 7,22,37,52) | min | crontab | bot run frequency (jitter) |
| MC H4 schedule | `0 */4` | h | crontab | `fx_monte_carlo_v1.py --timeframe H4` |
| MC Daily schedule | `0 8` | h | crontab | `fx_monte_carlo_v1.py --timeframe D` |
| Retrain schedule | `0 0` daily | — | crontab | `retrain_model.py` (currently fails) |
| `DEFAULT_LOT_SIZE` | 10000 | units | `config_bot_profile2.py:43`, `_profile3.py:43` | order size |
| `MAX_OPEN_POSITIONS` / `MAX_OPEN` | 4 | positions | `config_bot_profile2.py:42` | max concurrent trades |
| `MIN_CONVICTION_SCORE` | 30.0 | score | profile configs / `config_bot.py:123` | FINAL threshold |
| `MIN_SCORE_GAP` | 0.25 | score | `config_bot_profile2.py:34` | min strength gap |
| `WEIGHT_STRENGTH/RSI/ADX/XGB/MC` | 0.40/0.15/0.15/0.20/0.10 | — | profile configs | FINAL weights |
| `XGB_BULLISH_THRESHOLD` | 0.55 | prob | `config_bot.py:132` | XGB vote (moot — see §5.8) |
| `MC_BULLISH_THRESHOLD_PCT` | 55.0 | % | `config_bot_profile2/3.py:47` | MC vote threshold |
| `CONSENSUS_THRESHOLD` | 2 | votes | `config_bot.py:131` | ≥2 of 3 consensus |
| `ADX_SCALE_FACTOR` | 2.0 | — | `config_bot.py:136` | ADX ×2 scoring |
| `ADX_MIN_SCORE` (floor) | 20.0 | — | `config_bot.py:138` | ADX floor |
| `ADX_BOOST_THRESHOLD` / `_VALUE` | 30.0 / 10.0 | — | `config_bot.py:140-141` | ADX boost |
| `ATR_SL_MULT` | 2.0 | ×ATR | `config_bot.py:7` | ATR SL fallback |
| `SL_USE_ZONE_HIERARCHY` | True | — | `config_bot.py:178` | enables zone SL |
| `SL_BUFFER_PIPS` | 25 | pips | `config_bot.py:179` | zone buffer |
| `SL_MIN_DISTANCE_PIPS` | 20 | pips | `config_bot.py:180` | min SL distance |
| `SL_H4/H8/DAILY_LOOKBACK_BARS` | 6/4/2 | bars | `config_bot.py:181-183` | zone lookbacks |
| `SL_FALLBACK_FIXED_PIPS` | 35 | pips | `config_bot.py:184` | last-resort SL |
| `BASE_TP_PIPS` (P3) | 50 | pips | `config_bot_profile3.py:71` | profile3 base TP |
| `TP_MULT` (P3) | 2.5 | — | `config_bot_profile3.py:72` | normal TP mult → 125p |
| `TP_STRONG_MULT` (P3) | 3.0 | — | `config_bot_profile3.py:73` | strong TP mult → 150p |
| P2 TP hardcoded | 30p / 60p strong | pips | `fx_trade_bot_v6.8.3.py:57-76` | profile2 TP |
| `MC_STRONG_THRESHOLD` | 0.75 | — | `config_bot.py` default / hardcoded | strong-MC TP gate |
| `TREND_FILTER_ENABLED` | False | — | `config_bot.py:198` | Rule A OFF |
| `WEEK_EMA100_FILTER_ENABLED` | True (both profiles) | — | `config_bot_profile2.py:66`, `_profile3.py:66` | Rule B ON |
| `REMOVE_COOLDOWN` | True | — | `config_bot.py:115` | cooldown disabled |
| `DYNAMIC_TP` | False | — | `config_bot.py:97` | TP-raise disabled |
| `TRAILING_TP` | True | — | `config_bot.py:98` | (flag not used by DPM; trailing is hardwired in DPM) |
| `BE_TRIGGER_ATR_MULT` | 1.5 | ×ATR | `config_bot.py:100` | breakeven trigger |
| `TRAIL_TRIGGER_ATR_MULT` | 2.5 | ×ATR | `config_bot.py:101` | trail trigger |
| `TRAIL_ATR_MULT` | 1.5 | ×ATR | `config_bot.py:102` | trailing distance |
| `MAX_HOLD_BARS` | 12 | bars | `config_bot.py:103` | time exit |
| `SKIP_MC` | False | — | `config_bot.py:50` | bots compute MC in-process |
| `MC_SIMULATIONS` / `MC_CONFIDENCE` | 5000 / 0.90 | — | `config_bot.py:48-49` | MC sims |
| `H4_LOOKBACK` / `H4_FORECAST` | 90 / 8 | bars | `config_bot.py:53-54` | MC lookback/forecast |
| `MULTI_TF_CONFLUENCE` | False | — | `config_bot.py:107` | confluence off |
| `OANDA_ENV` | `practice` | — | `config_oanda.py:16`, `.env` | practice environment |

---

## 7. Persistence & State

### 7.1 Persistent stores inventory

| Store | Path | Owner (writer) | Purpose / schema | When read/written | Survives restart | Authoritative? |
|---|---|---|---|---|---|---|
| MC results | `daily_results/{h4,daily}_mc_<PAIR>_<YYYYMMDD_HHMM>.json` | `fx_monte_carlo_v1.py` (`main()`, writes) | per-pair MC metrics (`p_up`, `p_down`, `range_90`, `regime`, …) | written every cron run; deleted by `find … -mtime +7 -delete` | ✅ | Observation/auxiliary; **not consumed by trading bots** (bots read `daily_results_profile2/3`) |
| XGBoost model | `trade_model_xgb.pkl` (+ `.features.json`, backups `trade_model_xgb_backup_*.pkl`) | `retrain_model.py`, `ModelWrapper.save/load` | pickle `{model, scaler, feature_names, cfg}` | loaded every bot run; written by retrain (currently failing) | ✅ | Authoritative for model (though predictions unused — §5.8) |
| Bot logs | `logs/fx_trade_bot_v6.8.4_profile{2,3}.log` (stdout capture); `bot_profile2/3.log` (file handler) | LIVE bots | INFO runtime log | appended each run | ✅ | Observation |
| MC runner logs | `logs/mc_h4.log`, `logs/mc_daily.log` | `fx_monte_carlo_v1.py` | stdout capture | each MC run | ✅ | Observation |
| Cron log | `logs/bot_cron.log` | retrain cron job | stdout of failed retrain | daily; currently contains `python: not found` | ✅ | Observation |
| Cooldown | `cooldown_state.json` (root, legacy), `cooldown_profile{2,3}.json` (declared, never created) | legacy bots | `{pair: [Direction, remaining_runs]}` | cooldown **disabled** in LIVE bots (`REMOVE_COOLDOWN=True`); files never written by LIVE path | ✅ (if existed) | NOT authoritative |
| TP state | `tp_state.json` | `_open_oanda_order` (`fx_trade_bot_utils.py:596-603`) — **legacy helper not used by LIVE bots**; `DynamicPositionManager` reads it but doesn't use values | per-instrument entry/TP/direction | legacy | ✅ | NOT authoritative (loaded-unused in LIVE path) |
| Cluster state | `state/open_clusters.json` — **does not exist**; only `state/open_clusters.json.lock` (0 bytes) | `utils/cluster_state_store.py` (via `risk_integration.py`) — **NOT LIVE** | `{schema_version, clusters}` | never in LIVE path | n/a | NOT LIVE |
| Profile MC dirs | `daily_results_profile2/3/4` | created empty at bot start (`RESULTS_DIR.mkdir`); **never written** | — | mkdir only | n/a | NOT authoritative |

### 7.2 State classification
- **Trading state:** broker-side only (OANDA holds open positions/orders; the bots query `get_open_position` each run). Local trading state is effectively none — each cron run is stateless.
- **Risk state:** `utils/risk_integration.py`/`ClusterStateStore` exist but are NOT LIVE; no risk state is persisted by LIVE bots.
- **Observation/audit records:** MC JSONs (auxiliary), Telegram messages, logs.
- **Temporary/derived:** `signal.json` (0 bytes, legacy), `live_signal_log.csv` (74 bytes, legacy), `__pycache__/`.

### 7.3 Missing/corrupt file behavior (from code)
- `trade_model_xgb.pkl` missing → `ensure_model` retrains on the fly (`fx_trade_bot_ml.py:24-33`); corrupted pickle → exception propagates → bot FATAL → Telegram error → cron reruns in 15 min (no persistent damage).
- `cooldown_state.json` missing → `{}` (`load_cooldown`), but unused.
- `tp_state.json` missing → `{}` (DPM read is best-effort).
- `ClusterStateStore` (not LIVE): missing/empty/corrupt JSON treated as empty state; corruption preserved and logged (`utils/cluster_state_store.py` docstring lines 23-28).

| Accounts | 002 (P2) / 003 (P3) | — | `.env` → `config_oanda.py` | target accounts |
| `MODEL_PATH` | `trade_model_xgb.pkl` | — | `fx_trade_bot_v6.8.3.py:392` | XGB model |
| `retrain_every_n_days` | 7 | days | `data_pipeline.py:80` | model staleness trigger |
| `TARGET_HORIZON` | 6 | bars | `config_bot.py:19` | training target horizon |
| Log files | `logs/fx_trade_bot_v6.8.4_profile{2,3}.log`, `logs/mc_{h4,daily}.log` | — | crontab | runtime logs |
| MC JSON dir | `daily_results/` | — | `fx_monte_carlo_v1.py:48` | MC outputs (7-day retention) |


---

## 8. Observation / Instrumentation / Audit

- **What is observed in the LIVE path:** every step of the bot logs INFO lines (strength ranking, per-pair ATR/RSI/ADX, consensus vote, score breakdown, trend-filter reason, SL zone chosen, executed orders with TradeID, open-position inventory). Telegram receives: trade summaries on execution, fatal errors, and MC reports. No trade-level outcomes are persisted by the LIVE bots.
- **`utils/signal_instrumentation.py`** is a dedicated observation layer (`logs/v2_signal_observations.jsonl`, `logs/v2_trade_outcomes.jsonl`) with an explicit "observation-only" contract in its docstring. **However, it is NOT imported or called by any LIVE entry point in this repository** (grep across `fx_trade_bot_v6.8.3.py`, `fx_trade_bot_v6.8.4.1.py`, `fx_trade_bot_utils.py`, `fx_trade_bot_mc.py`, `fx_trade_bot_ml.py`, `strategy_decision.py`, `data_pipeline.py` returns nothing). Its only consumers in this repo are `utils/risk_integration.py` (not LIVE) and `utils/test_*.py`.
  - **Passivity verdict for the repo copy:** PASSIVE BY CONSTRUCTION (docstring), but **NOT LIVE** — it never runs in the current system. The copy in the external `gemini_api` project is a separate file and its runtime is **UNKNOWN** from this repo.
- **`utils/risk_integration.py` / `dynamic_risk_manager.py` / `pyramid_cluster.py` / `cluster_state_store.py`:** these WOULD be position/risk-interfering (they issue `TradeCRCDO`/`TradeClose` and persist cluster state) if active — but they are **NOT LIVE** in this repo (no import from any production entry point). Their only runtime consumers are the external `gemini_api` project's own copies (separate repo, separate `utils/`).
- **The LIVE `DynamicPositionManager` DOES interfere** with positions (modifies SL via `TradeCRCDO`, closes positions on time-exit) — it is part of the trading process, not an observation layer.

---

## 9. Failure, Restart & Recovery (behavior categories from code)

| Scenario | Behavior | Category |
|---|---|---|
| OANDA API failure on data fetch | pair skipped (`except` → log error, continue); if **all** pairs fail → abort + Telegram "No usable data" (`fx_trade_bot_v6.8.3.py:552-558`) | SKIP / LOG |
| OANDA API failure on order placement | `open_oanda_order_simple` returns `{"status":"ERROR"}`; caller logs `ORDER FAILED`, continues to next candidate | SKIP / LOG |
| Position query failure | `get_open_position` catches exceptions; `NO_SUCH_POSITION`/404 treated as no position; other errors → warn, return None (assume closed) | SKIP / LOG |
| MC failure | `MCGenerator.run_for_pair` returns `(None, False)` → pair not in mc_cache → `mc_pct_up` defaults to 50.0 (`mc_cache.get(pair, {}).get("p_up", 50.0)`) → MC vote = SELL (50 < 55) | SKIP (effect) / LOG |
| Missing model file | retrained on the fly inside the bot run | RETRY (in-process) |
| Corrupt model file | exception propagates → FATAL log + Telegram → process exits; next cron run tries again | STOP / LOG / RETRY (next cron) |
| Telegram failure | `send_telegram_message` prints error, tries plain-text fallback; never raises | LOG |
| Retrain cron failure | `/bin/sh: 1: python: not found` logged to `logs/bot_cron.log`; job simply fails; no recovery in code | STOP / LOG (observed) |
| Market closed | silent return before any API trade activity | SKIP |
| Machine restart | cron is the only supervisor; no daemon; jobs simply fire again per schedule | SKIP→rerun |
| Timeout of any cron run | if a run exceeds 15 min, the next cron fire can overlap; no file locks in the LIVE path (only the non-LIVE `ClusterStateStore` uses `filelock`) | **UNKNOWN** impact |
| Double-run protection | duplicate-order protection is **per-instrument within one run** and against currently-open positions; no cross-process lock | **UNKNOWN** |



---

## 10. Tests & Verification

| Test file | Scope | Verifies | Status |
|---|---|---|---|
| `tests/test_trading_core.py` | `utils/trading_core` execution mocks (unittest) | None-signal/HOLD/existing-position/successful order paths | STATICALLY VERIFIED (code); EXECUTION NOT PROVEN (no CI; run evidence = `__pycache__` only) |
| `tests/test_oanda_functions.py` | OANDA execution | market status, candle fetch, position bool, close-all (real practice env) | STATICALLY VERIFIED; live trade test commented out |
| `tests/test_sl_zone_hierarchy.py` | `sl_zone_hierarchy.compute_sl_zone` | real OANDA data SL computation (script, not pytest asserts) | STATICALLY VERIFIED |
| `tests/test_range_detector.py` | `utils/range_detector.is_sideways` | trending/narrow/insufficient/MA-band cases (mocked) | STATICALLY VERIFIED |
| `tests/test_currency_strength.py` | `utils/calculate_currency_strength` | ATR calc with mock candles | STATICALLY VERIFIED |
| `tests/test_fx_trade_bot_data.py` | `fx_trade_bot.normalize_ohlc_data` | OHLC conversion (legacy bot fn) | STATICALLY VERIFIED |
| `tests/test_market_open.py` | `utils.oanda_execution.forex_market_closed` | returns bool | STATICALLY VERIFIED |
| `tests/test_account.py`, `tests/test_account4.py`, `tests/check_oanda_account_v1.py`, `tests/integration/test_oanda_roundtrip.py`, `tests/integration/test_oanda_live_practice.py` | account/roundtrip | account reachability; roundtrip logic (some files are empty or shell snippets) | STATICALLY VERIFIED / NOT RUNNABLE in isolation |
| `utils/test_risk_integration.py` | `utils.risk_integration` (mocked OANDA) | reconcile, SL update, partial/full close, cluster lifecycle, error handling | STATICALLY VERIFIED; **NOT LIVE code** |
| `utils/test_risk_persistence.py` | `dynamic_risk_manager`/`pyramid_cluster`/`cluster_state_store` | serialization round-trip, corrupt/missing file, file-lock concurrency | STATICALLY VERIFIED; **NOT LIVE code** |
| `utils/test_position_direction.py`, `utils/test_phase2_activation.py` | position-direction + phase-2 flag diagnostics | direction resolution; flag-default audit | STATICALLY VERIFIED; **NOT LIVE code** |

- **Integration/passivity tests:** there is no automated test that runs the LIVE bots against the live pipeline. No CI configuration exists in the repo. `test.sh` merely launches `fx_trade_bot_v6.8.2_profile3.py` + `check_order_details.py` (not an assertion suite).
- `__pycache__` contains `.cpython-312-pytest-9.1.1.pyc` files for the `utils/test_*` files, indicating pytest 9.1.1 was run on them at least once (OBSERVED artifact), but no evidence of scheduled/CI execution.
- **Coverage:** not measured anywhere.

---

## 11. Design Constraints & Assumptions (visible in code)

1. **Execution model:** cron-invoked one-shot processes (every 15 min); no long-running daemon, no in-process scheduler loop in the LIVE bots.
2. **Closed vs forming candles:** no exclusion of the forming candle in the LIVE entry data path (`DataFetcher._from_oanda`); closed-candle filtering exists only in strength fetches and the unused `calculate_stop_loss`.
3. **Timeframe convention:** entry analysis on 15m (M15), but SL zones on H4/H8/D, strength on H1/H4/H8, trend gate on W. MC lookback/forecast configured for H4 while applied to 15m data.
4. **Zero shared state between processes:** each cron run is stateless locally; positions are the source of truth at the broker. Cooldown and cluster persistence mechanisms exist but are disabled/unused in the LIVE path.
5. **API ownership:** all OANDA calls go through `config_oanda.api` (module singleton) for trading; `utils.oanda_client` (separate client) is used by strength/pricing helpers. Two OANDA client instances exist in one process.
6. **Account separation:** Profile2 → Account 002; Profile3 → Account 003 (IDs from profile configs → `.env`).
7. **Immutability/locked constants:** `SL_OFFSET_PIPS=20`, `SL_MAX_ALLOWED_PIPS=200`, `REQUIRED_H4_CANDLES=4` are marked "LOCKED" in `fx_trade_bot_utils.py:22-30` (though `SL_MAX_ALLOWED_PIPS`/`REQUIRED_H4_CANDLES` are not used by the LIVE SL path).
8. **Config precedence:** `profile_cfg → config_bot → config → default` (`cfg_bot`, `fx_trade_bot_v6.8.3.py:243`).
9. **Import-time side effects:** importing `config_bot` runs full config validation (exits on error); importing `utils` instantiates OANDA + Gemini clients.
10. **No test-trade mode:** all runs execute real orders on practice accounts (no `--test-trade` flag in v6.8.3/v6.8.4.1).

---

## 12. Known Limitations & Unknowns

### Known limitations (directly visible)
- **XGB probability is never consumed** in the LIVE decision path (§5.8); the model's vote is effectively hard-coded "SELL".
- **Weekly EMA100 gate** currently evaluates at 1.00000 for all pairs (observed), heavily skewing/blocking entries; the intended price-level semantics are not producing realistic values.
- **Daily retrain cron fails** (`python: not found`), so `trade_model_xgb.pkl` is refreshed only by `ensure_model`'s staleness check (age>7 days) inside bot runs — which itself needs network and only retrains when the model is stale/missing.
- **No persisted local trading state**, no cooldown, no daily risk limit, no drawdown circuit breaker in the LIVE path.
- **Scheduled MC outputs are not consumed** by the trading bots (different directories: `daily_results/` vs `daily_results_profile2/3`); bots compute their own in-process MC each run.
- **Bot MC runs on 15m data with H4-configured lookback/forecast** (possible lookahead/misalignment, visible from config wiring).
- **No closed-candle guard on the entry timeframe.**
- **No cross-process lock** for the trading bots; overlapping 15-min runs possible (jitter only on Profile3 offset).
- Repo contains many dead/legacy modules (multiple `get_open_position` variants, `tmp/`, stale bots); live code carries duplicates (`compute_sl_zone` in two places).
- `logs/bot_h4.log` rotation cron is a no-op (file absent).

### UNKNOWN (cannot be proven from repository evidence)
- Whether the **external** `gemini_api/scheduled_runner_v1.3.py` (crontab #1) trades on accounts that this repo's bots also use; it uses its own `utils/` copy. Any interference between the two systems is **UNKNOWN**.
- Current open positions/balances at OANDA (only log snippets available; no account snapshot in repo).
- Why `fetch_weekly_ema100` returns exactly 1.0 (root cause not in repo).
- Whether tests are run by any automated pipeline (no CI config found).
- Behavior when two 15-min cron runs overlap (no locking evidence either way).
- Whether `gemini_api` and this repo share `daily_results`/model files (no evidence of reads).
- Actual fill prices, slippage, and trade P&L (no broker-data ingestion in repo).
- Whether the retrain failure has any operational consequence today (model staleness is self-healed by `ensure_model`, but network-dependent).



---

## 13. One-Page System Summary

**Runtime — how it starts & runs.** The installed user crontab is the only supervisor. Every 15 minutes two one-shot processes run: `fx_trade_bot_v6.8.3.py --profile2 --timeframe 15m` (Account 002) and `fx_trade_bot_v6.8.4.1.py --profile3 --timeframe 15m` (Account 003). Each run: 1–10 s jitter → market-hours check (silent skip on weekend) → ensure XGBoost model → currency strength → fetch 200 M15 candles/pair → build features → in-process Monte-Carlo → manage existing positions (breakeven/trail/time-exit) → scan open positions → score & filter candidates → place orders with SL/TP → Telegram summary. Separately, `fx_monte_carlo_v1.py` runs daily (08:00) and every 4h (H4) producing `daily_results/*.json` + Telegram reports, and `retrain_model.py` runs daily at 00:00 (currently failing: `python: not found`).

**Decision path — Data → Strategy → Order.** OANDA M15 candles → strength matrix (H1/H4/H8) → strength-gap vote + MC vote (+ an XGB vote that is always "SELL" due to an attribute-name mismatch) → 2-of-3 consensus → weighted score `0.40S+0.15R+0.15A+0.20X+0.10M` ≥ 30 → weekly-EMA100 gate (observed evaluating at 1.0) → SL from H4/H8/D zone hierarchy → TP 30p(×1/×2) profile2 / 125–150p profile3 → MARKET order ±10,000 units + separate GTC SL/TP orders.

**Risk path.** Fixed 10k-unit size, max 4 positions/account, per-instrument duplicate guards. Post-entry: breakeven at 1.5×ATR profit, trailing SL at 2.5×ATR trigger / 1.5×ATR distance, time exit after 12 bars. No equity-based sizing, no daily-loss limit, no circuit breaker in code.

**State.** What survives restart: broker positions (OANDA), the XGBoost model file, MC JSONs (`daily_results/`), logs. What does NOT survive: everything else — each cron run is stateless; cooldown, cluster/risk state, and TP state persistence are disabled or unused in the LIVE path.

**Observation.** INFO logs to `logs/fx_trade_bot_v6.8.4_profile{2,3}.log`, `logs/mc_{h4,daily}.log`, `logs/bot_cron.log`; Telegram messages for trade execution, fatal errors, and MC reports. The dedicated observation layer (`utils/signal_instrumentation.py`) exists but is NOT live in this repo.

**External dependencies.** OANDA v20 REST API (practice, 2 accounts), Telegram Bot API, yfinance (MC runner + MC fallback). Gemini client is instantiated at import but unused by the LIVE path.

**Critical constraints future devs must not break.**
1. Live code path = `fx_trade_bot_v6.8.3.py` (P2) + `fx_trade_bot_v6.8.4.1.py` (P3); do not treat legacy bots/`tmp/` as current.
2. Profile config precedence `profile_cfg → config_bot → config → default`; account IDs come only from profile configs.
3. Consensus ≥2/3 + FINAL ≥30 + strength-gap ≥0.25 gate entries; MAX_OPEN=4; 10k units fixed.
4. SL via `compute_sl_zone` (H4→H8→D→ATR→35p), buffer 25p, min distance 20p.
5. TP: profile2 30/60p (MC≥75%), profile3 125/150p.
6. All OANDA calls go through `config_oanda.api`; do not create parallel order paths.
7. `utils/signal_instrumentation.py` and `utils/risk_integration.py` (and their peers) are NOT wired into the LIVE bots — wiring them changes risk behavior; verify import graph first.
8. Each cron run is stateless and one-shot; position truth lives at the broker.
9. `config_bot` import runs validation and can `sys.exit(1)` on config errors.
10. `ensure_model` may retrain `trade_model_xgb.pkl` in-process when stale/missing — it needs network and writes the model file.

---

## Appendix A — Sample observed log lines (2026-08-26)
- `logs/fx_trade_bot_v6.8.4_profile2.log`: `🤝 EURJPY=X: Strength=BUY | XGB=SELL | MC=SELL | BUY=1/3`; `⚖️  SCORE ... S= 25.7×0.40=10.3 R= 0.0×0.15=0.0 A=100.0×0.15=15.0 X= 7.7×0.20=1.5 M= 40.1×0.10=4.0 | FINAL=30.8`; `🔍 15m TREND FILTER: ema_cross_filter=False | profile=profile2`; `⏭️ SKIP SELL: COUNTER-TREND vs WEEKLY EMA100 — Price above 1.00000`; `➖ REASON: FINAL 22.9 < 30.0`.
- `logs/fx_trade_bot_v6.8.4_profile3.log`: `🏆 RANKED: 1 passed → opening top 1`; `#1 — AUDJPY=X BUY SCORE=31.7 SMART-TP=125.0p`; `⏭️ AUDJPY=X: MAX_OPEN reached — SKIP`.
- `logs/mc_h4.log`: `🔬 H4 MC RUN — 20260826_0000 UTC | Pairs: 8` … `✅ Telegram report sent`.
- `logs/bot_cron.log`: `/bin/sh: 1: python: not found`.
