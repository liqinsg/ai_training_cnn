# Doc 09 — Phase 3.3 Experiment Protocol (FROZEN)

- **Status:** `FROZEN (Owner) — 2026-11-16` | Revision `R4 (Frozen for Demo Preparation)`
- **Inference Validity:** `NOT VERIFIED — provisional` (pending Demo execution & statistical audit)
- **Authorization Boundary:**
  - **Authorized Now:** Protocol Freeze + Demo Harness Preparation (code generation & offline dry-run verification).
  - **Explicitly NOT Authorized (Requires Separate Gate):** Live/OANDA Demo Execution (`run`), Model Artifact Publication to Production, Live/Paper Bot Activation.

---

## 1. Owner-Frozen Run Decisions (2026-11-16)

| Parameter                          | Frozen Value / Rule                                                                                                                                                                                                                                                                                                 | Governance Tag        |
| :--------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | :-------------------- |
| **Instrument Universe**      | `mc_data.yml` (28 clean symbols normalized to OANDA native `XXX_YYY`) $\cap$ `config_bot.py` (`forex_pairs.json` whitelist union / Profile 2) = **13 OANDA-native pairs** (`AUD_JPY, EUR_JPY, GBP_JPY, USD_JPY, AUD_USD, EUR_USD, GBP_USD, USD_CHF, GBP_AUD, EUR_CHF, AUD_CHF, GBP_CHF, EUR_AUD`) | `FROZEN (Owner)`    |
| **Compute Budget**           | **4 vCPU / 24 GB RAM** (Oracle Cloud Infrastructure VM)                                                                                                                                                                                                                                                       | `FROZEN (Owner)`    |
| **Training Policy**          | **In-fold single fit + internal-CV calibration only**; global hyperparameter grid search is **prohibited**                                                                                                                                                                                              | `FROZEN (Owner)`    |
| **Temporal Split & Holdout** | Global timestamp grid $T$; 80% Development / 20% Holdout (strictly sealed); 30% initial seed window; $K=5$ expanding walk-forward folds; purge gap = **6 bars** ($H=6$ M15 bars)                                                                                                                        | `FROZEN (Protocol)` |
| **Learner & Scaling**        | `LogisticRegression` (L2, `C=1.0`, `max_iter=1000`) + fold-local `StandardScaler` (fit strictly on `train_k`)                                                                                                                                                                                             | `FROZEN (Protocol)` |
| **Baselines & Ablation**     | `B0a` (Majority), `B0b` (6-bar Persistence), `B1` (Price/Vol Core), `B2` (B1 + Regime/ECDF features), `B3` (Cross-pair Core), `B4` (Full 33-feature Contract)                                                                                                                                           | `FROZEN (Protocol)` |
| **Inference & Bootstrap**    | Synchronized cross-instrument Moving-Block Bootstrap on $T$ ($B=2000$, block lengths $L_b \in \{6, 12, 24, 48\}$); Benjamini-Hochberg FDR control per hypothesis family; all outputs tagged `NOT VERIFIED — provisional`                                                                                   | `FROZEN (Protocol)` |

---

## 2. Roadmap & Deliverable Mapping

1. **Module 1 — Data Loader & Universe Filter (`load_universe`, `build_aligned_dataset`):**
   - Reads `mc_data.yml` (`pairs` list), normalizes clean 6-char symbols (`EURUSD` $\to$ `EUR_USD`), intersects with `config_bot.py` / `forex_pairs.json` whitelist, logs excluded pairs (15 excluded, 13 retained).
   - Enforces single-source feature contract (`ml.feature_contract`) and attaches `close_now` / `close_lag6` for `B0b`.
2. **Module 2 — Global Timestamp-Grid Walk-Forward Splitter (`build_timestamp_grid`, `compute_folds`):**
   - Operates strictly on sorted unique timestamps $T$ across all instruments to prevent cross-pair leakage.
   - Reserves final 20% of $T$ as sealed Holdout; partitions 80% Dev into 30% seed + $K=5$ expanding folds with a 6-bar purge buffer before each test window and at the Dev/Holdout boundary.
3. **Module 3 — In-Fold Model Runner, LOPO & Block Bootstrap (`run_walk_forward`, `run_lopo`, `block_bootstrap_delta_auc`):**
   - Executes constrained in-fold fitting (`StandardScaler` + `LogisticRegression`, optional internal-CV sigmoid calibration).
   - Evaluates pooled and per-pair ROC-AUC, Log-Loss, and Brier Score, plus Leave-One-Pair-Out (LOPO) generalization.
   - Runs synchronized cross-instrument block bootstrap ($L_b \in \{6, 12, 24, 48\}$, $B=2000$) with BH-FDR adjustment and outputs run-scoped JSON/CSV evidence records under `experiments/phase3_3_demo/<run_id>/`.
