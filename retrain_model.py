#!/usr/bin/env python3
"""
RETRAIN XGBoost Model on RECENT market data
Produces: trade_model_xgb.pkl
"""

import sys
import logging
import numpy as np
import pandas as pd
import pickle
from pathlib import Path
from datetime import datetime, timezone
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, roc_auc_score

import config
from config_oanda import OANDA_API_TOKEN, OANDA_ACCOUNT_ID, OANDA_ENV
from data_pipeline import FeatureConfig, FeatureEngine, DataFetcher

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# ── CONFIG ──────────────────────────────────────────────
TIMEFRAME = "15m"
OANDA_GRANULARITY_MAP = {"15m": "M15", "1H": "H1", "H4": "H4"}
OANDA_GRANULARITY = OANDA_GRANULARITY_MAP.get(TIMEFRAME, "M15")
LOOKBACK_BARS = 500          # ✅ Within OANDA's hard limit per request
TARGET_HORIZON = 6
TRAIN_TEST_SPLIT = 0.20

DEFAULT_PAIRS = config.DEFAULT_PAIRS
YAHOO_TO_OANDA = config.YAHOO_TO_OANDA

FEAT_CFG = FeatureConfig(
    use_atr=True, atr_sl_mult=2.0, atr_tp_mult=3.0,
    use_macd=False, use_rsi=True, use_adx=True,
    model_type="xgboost", target_horizon=TARGET_HORIZON,
    train_lookback_bars=LOOKBACK_BARS,
)

OUTPUT_MODEL_PATH = BASE_DIR / "trade_model_xgb.pkl"
BACKUP_MODEL_PATH = BASE_DIR / f"trade_model_xgb_backup_{datetime.now().strftime('%Y%m%d_%H%M')}.pkl"

# ── FETCH SINGLE PAIR ────────────────────────────────────
def fetch_pair_data(fetcher, pair, oanda):
    """Fetch up to LOOKBACK_BARS for one pair (single batch)"""
    try:
        raw = fetcher.fetch(pair, oanda, count=LOOKBACK_BARS)
        if raw.empty or len(raw) < 200:
            logger.warning(f"  ⚠️ Insufficient data: {len(raw)} bars")
            return pd.DataFrame()
        return raw
    except Exception as e:
        logger.error(f"  ❌ Failed {pair}: {e}")
        return pd.DataFrame()

# ── FETCH ALL DATA ──────────────────────────────────────
def fetch_all_data():    
    from oandapyV20 import API
    api = API(access_token=OANDA_API_TOKEN, environment=OANDA_ENV)
    fetcher = DataFetcher(use_oanda=True, oanda_api=api, oanda_granularity=OANDA_GRANULARITY)
    feat_engine = FeatureEngine(FEAT_CFG)

    all_dfs = []
    for pair in DEFAULT_PAIRS:
        oanda = YAHOO_TO_OANDA[pair]
        logger.info(f"📥 Fetching {pair} ({OANDA_GRANULARITY})...")
        
        raw = fetch_pair_data(fetcher, pair, oanda)
        if raw.empty:
            continue

        df = feat_engine.build(raw)
        df = df.copy()

        # Clean NaN/Inf
        df = df.replace([np.inf, -np.inf], np.nan)
        df = df.ffill().bfill().fillna(0)

        # ── Build TARGET: Did price go UP > threshold in N bars?
        df["future_return"] = df["Close"].shift(-TARGET_HORIZON) / df["Close"] - 1
        df["target"] = (df["future_return"] > 0.002).astype(int)  # UP > 0.2% = BUY

        df["pair"] = pair
        all_dfs.append(df)
        logger.info(f"  ✅ {len(df)} bars | UP: {df['target'].mean()*100:.1f}%")

    if not all_dfs:
        raise RuntimeError("No data fetched!")

    combined = pd.concat(all_dfs, ignore_index=True)
    logger.info(f"\n📊 COMBINED: {len(combined)} rows | {len(combined['pair'].unique())} pairs")
    return combined

# ── TRAIN ───────────────────────────────────────────────
def train_model(df):
    """Train XGBoost on prepared dataset — STRING-SAFE"""
    
    # ── EXCLUDE NON-NUMERIC & META COLUMNS ──────────────────────
    exclude = [
        "target", "future_return", "pair", 
        "Open", "High", "Low", "Close", "Volume",
        "regime", "market_condition", "trend_state", "mode",
    ]
    
    # Select ONLY numeric features — auto-skips any string columns
    feature_cols = [
        c for c in df.columns 
        if c not in exclude 
        and pd.api.types.is_numeric_dtype(df[c])
    ]
    
    logger.info(f"🧪 Features: {len(feature_cols)} (numeric only)")

    X = df[feature_cols].values
    y = df["target"].values

    # Remove last N rows (no target available)
    X = X[:-TARGET_HORIZON]
    y = y[:-TARGET_HORIZON]

    # Split
    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=TRAIN_TEST_SPLIT, shuffle=False, random_state=42
    )

    logger.info(f"Training: {len(X_train)} | Validation: {len(X_val)}")
    logger.info(f"UP ratio — Train: {y_train.mean()*100:.1f}% | Val: {y_val.mean()*100:.1f}%")

    # ── MODEL
    model = xgb.XGBClassifier(
        n_estimators=200, max_depth=5, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8, random_state=42,
        use_label_encoder=False, eval_metric="logloss",
    )

    logger.info("🏋️ Training XGBoost...")
    model.fit(X_train, y_train)

    # ── EVAL
    train_acc = accuracy_score(y_train, model.predict(X_train))
    val_acc = accuracy_score(y_val, model.predict(X_val))
    val_proba = model.predict_proba(X_val)[:, 1]
    roc = roc_auc_score(y_val, val_proba) if len(np.unique(y_val)) > 1 else 0.5

    logger.info(f"\n📈 RESULTS:")
    logger.info(f"   Train Accuracy:  {train_acc:.2%}")
    logger.info(f"   Val   Accuracy:  {val_acc:.2%}")
    logger.info(f"   Val   ROC-AUC:   {roc:.4f}")

    # ── Feature Importance
    imp = pd.DataFrame({"feature": feature_cols, "importance": model.feature_importances_})
    imp = imp.sort_values("importance", ascending=False).head(10)
    logger.info(f"\n🏆 TOP 10 FEATURES:")
    for _, row in imp.iterrows():
        logger.info(f"   {row['feature']:25s} {row['importance']:.4f}")

    return model, feature_cols

# ── SAVE ─────────────────────────────────────────────────
def save_model(model, feature_cols):
    """Backup old model → save new model WITH scaler"""
    from sklearn.preprocessing import StandardScaler  # ✅ Add this
    
    if OUTPUT_MODEL_PATH.exists():
        OUTPUT_MODEL_PATH.rename(BACKUP_MODEL_PATH)
        logger.info(f"\n💾 Old model backed up: {BACKUP_MODEL_PATH.name}")

    # Create empty scaler (model doesn't require scaling, but bot expects it)
    dummy_scaler = StandardScaler()
    dummy_scaler.fit([[0.0]] * len(feature_cols))  # Minimal fit to satisfy structure

    # package = {
    #     "model": model,
    #     "feature_list": feature_cols,
    #     "scaler": dummy_scaler,  # ✅ ADD THIS LINE
    # }


    package = {
        "model": model,
        "feature_names": feature_cols,
        "scaler": dummy_scaler,
    }
    
    with open(OUTPUT_MODEL_PATH, "wb") as f:
        pickle.dump(package, f)

    logger.info(f"✅ NEW MODEL SAVED → {OUTPUT_MODEL_PATH}")
    logger.info(f"   Trained on {TIMEFRAME} data | {len(feature_cols)} features")

# ── MAIN ─────────────────────────────────────────────────
if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("🚀 XGBOOST MODEL RETRAINING — FRESH DATA")
    logger.info("=" * 60)

    df = fetch_all_data()
    model, features = train_model(df)
    save_model(model, features)

    logger.info("\n🎉 RETRAINING COMPLETE! Restart your bot to use new model.")