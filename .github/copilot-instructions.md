<!-- Auto-generated: tailored Copilot instructions for this repo -->
# Copilot / AI Agent Instructions — ai_training_cnn

Purpose: Provide concise, actionable repository knowledge so an AI agent can edit code safely and productively.

- **Big picture architecture**
  - `agent_skills/`: Markdown-based skill modules (e.g., `forex_analysis_skill.md`, `tools_guild.md`) drive agent behavior and output schemas.
  - Core trading code: multiple standalone scripts under repo root (`trading_bot_oanda.py`, `trading_bot.py`, `fx_trade_bot_utils.py`) implement OANDA interactions and trade logic.
  - Models & training: `retrain_model.py`, `cnn_model.py`, and model artifacts (`cnn_model.keras`, `trade_model_xgb.pkl`) live at the repo root.
  - Data & pipelines: `data/`, `data_pipeline.py`, `features_list.json` and `FeatureEngine` drive feature extraction for XGBoost training.
  - Support: `telegram_message.py` (notifications), `config*.py` (per-exchange configs), `state/` and multiple JSON state files (`signal.json`, `tp_state.json`, `cooldown_state.json`) represent runtime state.

- **Key integration points**
  - OANDA: `oandapyV20` is used everywhere; see `trading_bot_oanda.py`, `fx_trade_bot_utils.py`, and `retrain_model.py` for usage examples.
  - Telegram: use `send_telegram_message` in `telegram_message.py` to post bot alerts.
  - External configs/secrets: `config_oanda.py`, `OANDA_ACCOUNT_ID_3.py`, and a repository `.env` are expected — DO NOT commit secrets.

- **Project-specific conventions & gotchas**
  - Many scripts are standalone CLI-style programs (not a packaged Python module). Changes should preserve script-level behavior.
  - Inter-process communication: the file `signal.json` is used as a simple IPC signal for trading loops (write/read/clear pattern).
  - State files are authoritative at runtime (`tp_state.json`, `cooldown_state.json`) — avoid modifying them in tests or commits unless intentional.
  - Several functions carry `LOCKED` or explicit business rules (e.g., SL/TP logic in `fx_trade_bot_utils.py`). These are domain constraints — change only with owner approval.
  - Logging and error-handling: code often captures exceptions and continues (see many `try/except` blocks). Preserve that style when refactoring to avoid altering runtime robustness.

- **Common developer workflows & commands**
  - Activate Python env (example shown in repo terminal): `source /Users/liqin/miniforge3/bin/activate myenv` or `conda activate myenv`.
  - Retrain XGBoost model: `python retrain_model.py` (produces `trade_model_xgb.pkl`).
  - Run trading bot (local): `python trading_bot_oanda.py` (reads `signal.json`, uses `config_oanda.py`).
  - Train CNN demo: `python cnn_model.py` (writes `cnn_model.keras`).
  - Run tests: `pytest tests/` (project uses pytest-driven tests for agent skills & integration).
  - Docker: `docker-compose up --build` or use `Dockerfile` to reproduce environment.

- **Where to look first when changing behavior**
  - Trading logic & safety: `fx_trade_bot_utils.py`, `trading_bot_oanda.py`, `trading_bot.py`.
  - Feature engineering & data: `data_pipeline.py`, `FeatureConfig` / `FeatureEngine` used by `retrain_model.py`.
  - Model I/O: `retrain_model.py` (packaging `model`, `feature_names`, `scaler`) and consumer code that loads `trade_model_xgb.pkl`.
  - Agent skill definitions: `agent_skills/*.md` — changes here alter AI outputs and must follow existing output schemas (see `forex_analysis_skill.md`).

- **Examples of small, safe edits an agent can do**
  - Fix a logging message or add more structured logging in `fx_trade_bot_utils.py`.
  - Add a small unit test under `tests/` for a utility function referenced by `retrain_model.py`.
  - Improve parameter validation (e.g., check `h4_candles` length) while keeping existing error messages.

- **When NOT to change**
  - Do not alter live business rules marked `LOCKED` (stop-loss hierarchy, cooldown logic) without human approval.
  - Avoid committing secrets or replacing config files that contain API tokens.
  - Do not arbitrarily rename signal/state files (`signal.json`, `tp_state.json`) — many scripts expect exact filenames.

If anything above is unclear or you want examples expanded (e.g., concrete test skeletons or a step-by-step retrain + deploy runbook), tell me which section to expand. 
