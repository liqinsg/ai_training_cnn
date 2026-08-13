# fx_trade_bot_ml.py — MODEL & TRAINING (RARELY CHANGES)
# Contains: ensure_model(), globals needed for training

import logging
import pandas as pd
from pathlib import Path

logger = logging.getLogger(__name__)


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
    """Load or train XGBoost model. Returns (model_wrapper, strat_engine)."""
    needs_train = False
    if not MODEL_PATH.exists():
        needs_train = True
        logger.info("Model not found. Training...")
    else:
        age_days = (Path(__file__).parent.joinpath(MODEL_PATH).stat().st_mtime - MODEL_PATH.stat().st_mtime) / 86400
        age_days = (pd.Timestamp.now(tz="UTC").timestamp() - MODEL_PATH.stat().st_mtime) / 86400
        if age_days > getattr(FEAT_CFG, "retrain_every_n_days", 30):
            needs_train = True
            logger.info(f"Model stale ({age_days:.1f} days). Retraining...")

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
            raise RuntimeError("No training data available for any pair")
        full_df = pd.concat(train_dfs).dropna()
        feature_cols = feat_engine.get_feature_columns(full_df)
        logger.info(f"Training on {len(full_df)} rows, {len(feature_cols)} features")
        metrics = model_wrapper.fit(full_df, feature_cols)
        logger.info(f"Training complete: {metrics}")
        top_features = model_wrapper.feature_importance().head(10)
        logger.info("Top features:\n" + top_features.to_string(index=False))
    else:
        model_wrapper.load()
        logger.info(f"Loaded model from {MODEL_PATH}")

    strat_engine.model = model_wrapper.model
    strat_engine.features = model_wrapper.feature_names
    return model_wrapper, strat_engine