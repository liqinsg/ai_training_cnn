# ─────────────────────────────────────────────────────────────────────────────
# 非权威（NON-AUTHORITATIVE）— DO NOT WIRE  ｜ Phase 3.1 隔离标注
# ─────────────────────────────────────────────────────────────────────────────
# 本文件来自一条分歧（Gemini）开发线，是 fx_trade_bot_ml.py 的平行副本，
# 仅供存档参考；严禁被实盘主循环 import 或接线。
# 与权威实现的冲突：
#   * 采用 ModelBundleContractError 硬中止（Hard-Stop）哲学，与本仓库刻意采用的
#     结果对象 ModelInitResult（不崩溃、隔离单点故障）相反
# 权威替代：fx_trade_bot_ml.py
# ─────────────────────────────────────────────────────────────────────────────
# fx_trade_bot_ml.py — MODEL & TRAINING (PHASE 3 REFACTORED)
# Enforces Model Bundle atomicity, strict feature schema parity, and hard-stop error behavior.
# Revised by Gemini
import json
import logging
from pathlib import Path
import pandas as pd

logger = logging.getLogger(__name__)


class ModelBundleContractError(RuntimeError):
    """Raised when Model Bundle artifacts fail schema, hash, or dimension validation."""
    pass


def ensure_model(
    MODEL_PATH: Path,
    FEAT_CFG,
    model_wrapper,
    strat_engine,
    fetcher,
    feat_engine,
    DEFAULT_PAIRS,
    YAHOO_TO_OANDA,
    cfg,
):
    """
    Load or train XGBoost model using strict Model Bundle versioning and contracts.
    Returns (model_wrapper, strat_engine).
    """
    stem = MODEL_PATH.with_suffix("") if MODEL_PATH.suffix else MODEL_PATH
    xgb_json = stem.with_suffix(".json")
    scaler_jl = stem.parent / "scaler.joblib"
    feat_json = stem.with_suffix(".features.json")
    manifest_json = stem.with_suffix(".manifest.json")

    # 1. Atomic Bundle Existence Check
    artifacts_exist = all([
        xgb_json.exists(),
        scaler_jl.exists(),
        feat_json.exists(),
        manifest_json.exists(),
    ])

    needs_train = False
    manifest = {}

    if not artifacts_exist:
        needs_train = True
        logger.info("Model Bundle artifacts incomplete or missing. Initiating training...")
    else:
        # Load and validate manifest
        try:
            with open(manifest_json, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            
            # Schema Version Verification
            expected_schema_version = getattr(FEAT_CFG, "schema_version", "v1.0")
            if manifest.get("schema_version") != expected_schema_version:
                logger.warning(
                    f"Schema version mismatch: bundle={manifest.get('schema_version')}, "
                    f"expected={expected_schema_version}. Retraining..."
                )
                needs_train = True
            
            # Expiration / Retrain Check via explicit metadata (not file mtime)
            train_timestamp = pd.Timestamp(manifest.get("created_at", "2000-01-01"))
            age_days = (pd.Timestamp.now(tz="UTC") - train_timestamp).total_seconds() / 86400
            retrain_limit = getattr(FEAT_CFG, "retrain_every_n_days", 30)
            
            if not needs_train and age_days > retrain_limit:
                needs_train = True
                logger.info(f"Model bundle expired (age: {age_days:.1f} days > limit: {retrain_limit}). Retraining...")

        except Exception as e:
            logger.error(f"Failed to parse model manifest: {e}. Forcing retraining...")
            needs_train = True

    if needs_train:
        train_dfs = []
        for pair in DEFAULT_PAIRS:
            oanda = YAHOO_TO_OANDA[pair]
            try:
                raw = fetcher.fetch(pair, oanda, count=FEAT_CFG.train_lookback_bars)
                if len(raw) < getattr(FEAT_CFG, "required_bars", 100):
                    logger.warning(f"Insufficient bars for {pair}: {len(raw)}")
                    continue
                df = feat_engine.build(raw)
                df = feat_engine.build_target(df, horizon=FEAT_CFG.target_horizon)
                train_dfs.append(df)
            except Exception as e:
                logger.error(f"Training fetch failed for {pair}: {e}")
                continue

        if not train_dfs:
            raise ModelBundleContractError("No training data available for any pair. Cannot train model.")
        
        full_df = pd.concat(train_dfs).dropna()
        feature_cols = feat_engine.get_feature_columns(full_df)
        logger.info(f"Training on {len(full_df)} rows, {len(feature_cols)} features")
        
        metrics = model_wrapper.fit(full_df, feature_cols)
        logger.info(f"Training complete: {metrics}")
        
        # Save model wrapper along with explicit manifest
        model_wrapper.save()
        
        # Ensure parent directory exists before writing manifest
        manifest_json.parent.mkdir(parents=True, exist_ok=True)

        # Write atomic manifest containing schema and feature metadata
        new_manifest = {
            "schema_version": getattr(FEAT_CFG, "schema_version", "v1.0"),
            "created_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "feature_names": feature_cols,
            "n_features": len(feature_cols),
        }
        with open(manifest_json, "w", encoding="utf-8") as f:
            json.dump(new_manifest, f, indent=2)
            
        logger.info(f"Model Bundle successfully packed and saved to {stem}")
    else:
        # Load existing verified bundle
        model_wrapper.load()
        logger.info(f"Loaded verified Model Bundle from {xgb_json}")

    # 2. Strict Runtime Feature & Dimension Parity Validation
    model_n_feat = getattr(model_wrapper.model, "n_features_in_", None)
    scaler_n_feat = getattr(model_wrapper.scaler, "n_features_in_", None)
    expected_features_len = len(model_wrapper.feature_names)

    if model_n_feat is not None and model_n_feat != expected_features_len:
        raise ModelBundleContractError(
            f"Feature dimension mismatch: model expects {model_n_feat} features, "
            f"but feature_names list contains {expected_features_len}."
        )

    if scaler_n_feat is not None and scaler_n_feat != expected_features_len:
        raise ModelBundleContractError(
            f"Scaler dimension mismatch: scaler expects {scaler_n_feat} features, "
            f"but feature_names list contains {expected_features_len}."
        )

    # 3. Secure Dependency Injection
    strat_engine.model = model_wrapper.model
    strat_engine.scaler = model_wrapper.scaler
    strat_engine.features = model_wrapper.feature_names

    logger.info(
        "Inference wiring verified: model_n_features=%s | scaler_n_features=%s | "
        "feature_count=%s | schema_version=%s",
        model_n_feat,
        scaler_n_feat,
        len(model_wrapper.feature_names),
        manifest.get("schema_version", getattr(FEAT_CFG, "schema_version", "v1.0")),
    )
    
    return model_wrapper, strat_engine