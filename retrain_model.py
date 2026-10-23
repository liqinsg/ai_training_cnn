#!/usr/bin/env python3
"""
RETRAIN XGBoost Model on RECENT market data
Produces: trade_model_xgb.json, scaler.joblib, trade_model_xgb.features.json
"""

import sys
import logging
import numpy as np
import pandas as pd
import shutil
from pathlib import Path
from datetime import datetime
import xgboost as xgb
from sklearn.metrics import accuracy_score, roc_auc_score

import config
from config_oanda import OANDA_API_TOKEN, OANDA_ENV
from data_pipeline import FeatureConfig, FeatureEngine, DataFetcher, ModelWrapper

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
LOOKBACK_BARS = 500
TARGET_HORIZON = 6
TARGET_THRESHOLD = 0.0005
TRAIN_TEST_SPLIT = 0.20

DEFAULT_PAIRS = config.DEFAULT_PAIRS
YAHOO_TO_OANDA = config.YAHOO_TO_OANDA

FEAT_CFG = FeatureConfig(
    use_atr=True,
    atr_sl_mult=2.0,
    atr_tp_mult=3.0,
    # MUST match the live inference config (fx_trade_bot_v685: use_macd=True,
    # config_profile.json USE_MACD=true) — otherwise the retrained artifact has
    # 34 features while the bot builds 37, breaking the Phase-1 feature contract.
    use_macd=True,
    use_rsi=True,
    use_adx=True,
    model_type="xgboost",
    target_horizon=TARGET_HORIZON,
    train_lookback_bars=LOOKBACK_BARS,
)

MODEL_STEM = BASE_DIR / "trade_model_xgb"
OUTPUT_XGB = MODEL_STEM.with_suffix(".json")
OUTPUT_SCALER = BASE_DIR / "scaler.joblib"
OUTPUT_FEAT = MODEL_STEM.with_suffix(".features.json")
OUTPUT_CFG = MODEL_STEM.with_suffix(".cfg.json")
LEGACY_PKL = MODEL_STEM.with_suffix(".pkl")


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
    fetcher = DataFetcher(
        use_oanda=True, oanda_api=api, oanda_granularity=OANDA_GRANULARITY
    )
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
        df["target"] = (df["future_return"] > TARGET_THRESHOLD).astype(int)

        df["pair"] = pair
        all_dfs.append(df)
        logger.info(f"  ✅ {len(df)} bars | UP: {df['target'].mean()*100:.1f}%")

    if not all_dfs:
        raise RuntimeError("No data fetched!")

    combined = pd.concat(all_dfs, ignore_index=True)
    logger.info(
        f"\n📊 COMBINED: {len(combined)} rows | {len(combined['pair'].unique())} pairs"
    )
    return combined


# ── TRAIN ───────────────────────────────────────────────
def train_model(df):
    """Train XGBoost on prepared dataset — STRING-SAFE"""
    from sklearn.preprocessing import StandardScaler

    # ── EXCLUDE NON-NUMERIC & META COLUMNS ──────────────────────
    exclude = [
        "target",
        "future_return",
        "pair",
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
        "regime",
        "market_condition",
        "trend_state",
        "mode",
    ]

    # Select ONLY numeric features — auto-skips any string columns
    feature_cols = [
        c
        for c in df.columns
        if c not in exclude and pd.api.types.is_numeric_dtype(df[c])
    ]

    logger.info(f"🧪 Features: {len(feature_cols)} (numeric only)")

    # ── PER-PAIR TEMPORAL SPLIT ─────────────────────────────
    # 每个币种各自按时间顺序切分：最新的 TRAIN_TEST_SPLIT 进验证集。
    # 取代"拼接整表 shuffle=False"的切法 —— 后者会让验证集退化成最后 1~2 个
    # 币种，且除末币种外每个币种尾部 6 行（无未来收益）被误标为 0 混进训练集。
    X_all = df[feature_cols].values
    y_all = df["target"].values
    pair_arr = df["pair"].values
    X_train_list, y_train_list, X_val_list, y_val_list = [], [], [], []
    for p in pd.unique(pair_arr):
        mask = pair_arr == p
        Xp = X_all[mask]
        yp = y_all[mask]
        n_valid = len(Xp) - TARGET_HORIZON
        split_idx = int(n_valid * (1 - TRAIN_TEST_SPLIT))
        X_train_list.append(Xp[:split_idx])
        y_train_list.append(yp[:split_idx])
        X_val_list.append(Xp[split_idx:n_valid])
        y_val_list.append(yp[split_idx:n_valid])
    X_train = np.concatenate(X_train_list)
    y_train = np.concatenate(y_train_list)
    X_val = np.concatenate(X_val_list)
    y_val = np.concatenate(y_val_list)

    logger.info(f"Training: {len(X_train)} | Validation: {len(X_val)}")
    logger.info(
        f"UP ratio — Train: {y_train.mean()*100:.1f}% | Val: {y_val.mean()*100:.1f}%"
    )

    # Scale with a REAL fitted scaler: inference always calls scaler.transform()
    # (data_pipeline._build_matrix), so the model must be trained in the same
    # scaled space.  A dummy / identity scaler only "worked" by accident and
    # violates the Phase-1 artifact-dimension contract (n_features_in_ == 1).
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_val_s = scaler.transform(X_val)

    # ── MODEL
    model = xgb.XGBClassifier(
        n_estimators=200,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        use_label_encoder=False,
        eval_metric="logloss",
    )

    logger.info("🏋️ Training XGBoost...")
    model.fit(X_train_s, y_train)

    # ── EVAL
    train_acc = accuracy_score(y_train, model.predict(X_train_s))
    val_acc = accuracy_score(y_val, model.predict(X_val_s))
    val_proba = model.predict_proba(X_val_s)[:, 1]
    roc = roc_auc_score(y_val, val_proba) if len(np.unique(y_val)) > 1 else 0.5

    logger.info(f"\n📈 RESULTS:")
    logger.info(f"   Train Accuracy:  {train_acc:.2%}")
    logger.info(f"   Val   Accuracy:  {val_acc:.2%}")
    logger.info(f"   Val   ROC-AUC:   {roc:.4f}")

    # ── Feature Importance
    imp = pd.DataFrame(
        {"feature": feature_cols, "importance": model.feature_importances_}
    )
    imp = imp.sort_values("importance", ascending=False).head(10)
    logger.info(f"\n🏆 TOP 10 FEATURES:")
    for _, row in imp.iterrows():
        logger.info(f"   {row['feature']:25s} {row['importance']:.4f}")

    return model, scaler, feature_cols


# ── SAVE ─────────────────────────────────────────────────
def save_model(model, scaler, feature_cols):
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    for p in (OUTPUT_XGB, OUTPUT_SCALER, OUTPUT_FEAT, OUTPUT_CFG, LEGACY_PKL):
        if p.exists():
            bak = p.with_name(f"{p.stem}_bak_{stamp}{p.suffix}")
            shutil.copy2(p, bak)

    # Delegate to the canonical writer so the artifact quartet
    # (.json / scaler.joblib / .features.json / .cfg.json) is always emitted
    # together and stays consistent with what ModelWrapper.load() validates.
    wrapper = ModelWrapper(FEAT_CFG, model_path=MODEL_STEM)
    wrapper.model = model
    wrapper.scaler = scaler
    wrapper.feature_names = list(feature_cols)
    wrapper.save()

    logger.info(f"✅ Model saved → {OUTPUT_XGB.parent}")
    logger.info(f"   xgb   : {OUTPUT_XGB.name}  ({OUTPUT_XGB.stat().st_size} B)")
    logger.info(f"   scaler: {OUTPUT_SCALER.name}  ({OUTPUT_SCALER.stat().st_size} B)")
    logger.info(f"   feat  : {OUTPUT_FEAT.name}  ({len(feature_cols)} features)")
    logger.info(f"   cfg   : {OUTPUT_CFG.name}  (use_macd={FEAT_CFG.use_macd})")


# ── MAIN ─────────────────────────────────────────────────
if __name__ == "__main__":
    from utils.utils import apply_jitter
    logger.info("=" * 60)
    logger.info("🚀 XGBOOST MODEL RETRAINING — FRESH DATA")
    logger.info("=" * 60)

    try:
        apply_jitter(1.0, 10.0)
        
        df = fetch_all_data()
        model, scaler, features = train_model(df)
        save_model(model, scaler, features)

        logger.info("\n🎉 RETRAINING COMPLETE! Restart your bot to use new model.")

    except Exception as e:
        log.exception(f"Fatal error in retrain_model.py main loop")
        send_telegram_message(f"❌ retrain_model.py FATAL ERROR: {e}")
        raise
