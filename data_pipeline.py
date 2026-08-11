"""
data_pipeline.py
Data ingestion, feature engineering, and model training layer.
ATR-aware, XGBoost-first, minimal traditional indicators.
"""
import json
import pickle
import logging
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pandas_ta as ta

# Optional: XGBoost
xgboost_available = False
try:
    import xgboost as xgb
    xgboost_available = True
except ImportError:
    pass

# Optional: sklearn fallback
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. CONFIG
# ---------------------------------------------------------------------------

@dataclass
class FeatureConfig:
    """Control which features are generated. Toggle OFF anything you don't want."""

    # --- ATR (volatility) ---
    use_atr: bool = True
    atr_period: int = 14
    atr_sl_mult: float = 2.0       # SL = entry ± ATR * mult
    atr_tp_mult: float = 3.0       # TP = entry ± ATR * mult (1.5:1 R/R)
    atr_position_sizing: bool = True
    risk_per_trade_pct: float = 0.01  # 1% of equity per trade

    # --- Price action / momentum (lightweight, non-lagging) ---
    use_returns: bool = True
    use_volatility: bool = True
    use_body_features: bool = True

    # --- Minimal traditional (can disable) ---
    use_rsi: bool = True
    rsi_period: int = 14
    use_macd: bool = False         # off by default — laggy
    use_adx: bool = True           # trend strength, not direction
    adx_period: int = 14

    # --- ML model ---
    model_type: str = "xgboost"    # "xgboost" | "sklearn_rf"
    target_horizon: int = 6        # bars ahead to predict (6 * 15m = 1.5h)
    train_lookback_bars: int = 5000
    retrain_every_n_days: int = 7

    # --- Data ---
    required_bars: int = 200


# ---------------------------------------------------------------------------
# 2. ATR MODULE (extracted from your PDFs)
# ---------------------------------------------------------------------------

class ATRModule:
    """
    ATR is NOT a trend indicator. It measures volatility.
    - High ATR → wide stops, reduce size
    - Low ATR → tight stops, normal size
    - ATR expansion → potential breakout / regime change
    - ATR contraction → consolidation, beware false breaks
    """

    def __init__(self, period: int = 14):
        self.period = period

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add ATR columns to df."""
        df = df.copy()

        # Standard ATR
        df["atr"] = ta.atr(df["High"], df["Low"], df["Close"], length=self.period)

        # ATR as % of price (normalized across pairs)
        df["atr_pct"] = df["atr"] / df["Close"]

        # ATR percentile (where does current ATR sit vs last 20 days?)
        df["atr_percentile"] = df["atr"].rolling(20 * 96).apply(  # 20 days of 15m
            lambda x: pd.Series(x).rank(pct=True).iloc[-1] if len(x) > 1 else 0.5,
            raw=False
        )

        # ATR trend: expanding or contracting?
        df["atr_ma"] = df["atr"].rolling(self.period).mean()
        df["atr_expanding"] = (df["atr"] > df["atr_ma"]).astype(int)

        # ATR ratio vs recent history (spike detection)
        df["atr_ratio"] = df["atr"] / df["atr"].rolling(self.period * 2).mean()

        # Volatility regime
        df["vol_regime"] = pd.cut(
            df["atr_percentile"],
            bins=[0, 0.25, 0.75, 1.0],
            labels=["low", "normal", "high"]
        ).astype(str)

        return df

    def sl_tp_from_atr(self, entry: float, direction: str,
                       atr_value: float, is_jpy: bool,
                       sl_mult: float = 2.0, tp_mult: float = 3.0
                       ) -> Tuple[float, float]:
        """
        Build SL/TP purely from ATR.
        SELL: SL above entry, TP below entry
        BUY:  SL below entry, TP above entry
        """
        pip = 0.01 if is_jpy else 0.0001
        decimals = 3 if is_jpy else 5

        sl_distance = atr_value * sl_mult
        tp_distance = atr_value * tp_mult

        if direction == "SELL":
            sl = round(entry + sl_distance, decimals)
            tp = round(entry - tp_distance, decimals)
        else:
            sl = round(entry - sl_distance, decimals)
            tp = round(entry + tp_distance, decimals)

        return sl, tp

    def position_size(self, equity: float, risk_pct: float,
                      entry: float, sl: float,
                      pair: str, atr_value: float) -> int:
        """
        Risk-based position sizing using ATR.
        Units = (Equity * Risk%) / |entry - SL|
        """
        risk_amount = equity * risk_pct
        sl_distance = abs(entry - sl)
        if sl_distance == 0:
            return 0

        units = int(risk_amount / sl_distance)

        # Cap by ATR: if ATR is huge (volatile), reduce size further
        atr_pct = atr_value / entry
        if atr_pct > 0.002:  # > 0.2% ATR = very volatile
            units = int(units * 0.5)
            logger.info(f"High volatility ({atr_pct:.4f}), halving size")

        return max(units, 1000)  # minimum 1k units


# ---------------------------------------------------------------------------
# 3. FEATURE ENGINE
# ---------------------------------------------------------------------------

class FeatureEngine:
    """
    Build ML-ready features. Avoids heavy traditional indicators.
    Focus: price action, volatility, microstructure.
    """

    def __init__(self, cfg: FeatureConfig):
        self.cfg = cfg
        self.atr_mod = ATRModule(period=cfg.atr_period)

    def build(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Main pipeline. Input: raw OHLCV DataFrame.
        Output: DataFrame with features + target (if historical).
        """
        if len(df) < self.cfg.required_bars:
            raise ValueError(f"Need {self.cfg.required_bars} bars, got {len(df)}")

        df = df.copy()

        # --- 1. Returns (momentum, not lagging) ---
        if self.cfg.use_returns:
            for p in [1, 3, 6, 12]:
                df[f"ret_{p}h"] = df["Close"].pct_change(p)
            df["ret_log"] = np.log(df["Close"] / df["Close"].shift(1))

        # --- 2. Volatility (realized, not implied) ---
        if self.cfg.use_volatility:
            for p in [12, 24, 48]:  # 3h, 6h, 12h of 15m bars
                df[f"vol_{p}h"] = df["Close"].pct_change().rolling(p).std() * np.sqrt(p * 4)

        # --- 3. Candle body / wick features (price action) ---
        if self.cfg.use_body_features:
            df["body"] = (df["Close"] - df["Open"]).abs() / df["Open"]
            df["upper_wick"] = (df["High"] - df[["Close", "Open"]].max(axis=1)) / df["Open"]
            df["lower_wick"] = (df[["Close", "Open"]].min(axis=1) - df["Low"]) / df["Open"]
            df["range"] = (df["High"] - df["Low"]) / df["Open"]
            df["direction"] = np.where(df["Close"] > df["Open"], 1, -1)

        # --- 4. ATR (volatility backbone) ---
        if self.cfg.use_atr:
            df = self.atr_mod.compute(df)

        # --- 5. RSI (minimal, for regime context) ---
        if self.cfg.use_rsi:
            df["rsi"] = ta.rsi(df["Close"], length=self.cfg.rsi_period)
            # RSI slope (momentum of momentum)
            df["rsi_slope"] = df["rsi"].diff(3)

        # --- 6. ADX (trend strength only, not direction) ---
        if self.cfg.use_adx:
            adx_df = ta.adx(df["High"], df["Low"], df["Close"], length=self.cfg.adx_period)
            df = pd.concat([df, adx_df], axis=1)
            # Rename collision if needed
            if "ADXR_14" in df.columns and "ADXR_14_2" not in df.columns:
                df = df.rename(columns={"ADXR_14": "ADXR_14_2"})

        # --- 7. MACD (disabled by default) ---
        if self.cfg.use_macd:
            macd = ta.macd(df["Close"])
            df = pd.concat([df, macd], axis=1)

        # --- 8. Distance from recent highs/lows (mean reversion / breakout) ---
        for p in [24, 48, 96]:  # 6h, 12h, 24h
            df[f"dist_high_{p}"] = (df["Close"] - df["High"].rolling(p).max()) / df["Close"]
            df[f"dist_low_{p}"] = (df["Close"] - df["Low"].rolling(p).min()) / df["Close"]

        # --- 9. Volume features (if available) ---
        if "Volume" in df.columns and df["Volume"].sum() > 0:
            df["vol_sma_ratio"] = df["Volume"] / df["Volume"].rolling(24).mean()
            df["vol_trend"] = np.where(df["Volume"] > df["Volume"].shift(1), 1, -1)

        # --- 10. Time features (seasonality) ---
        df["hour"] = df.index.hour
        df["day_of_week"] = df.index.dayofweek
        df["is_london"] = ((df["hour"] >= 8) & (df["hour"] <= 16)).astype(int)
        df["is_ny"] = ((df["hour"] >= 13) & (df["hour"] <= 21)).astype(int)

        return df

    def build_target(self, df: pd.DataFrame, horizon: int = 6) -> pd.DataFrame:
        """
        Binary target: will price be higher in `horizon` bars?
        This is what the model learns to predict.
        """
        future_return = df["Close"].shift(-horizon) / df["Close"] - 1
        df["target"] = (future_return > 0).astype(int)
        df["future_return"] = future_return  # for analysis, not training
        return df

    def get_feature_columns(self, df: pd.DataFrame) -> List[str]:
        """Return list of feature column names (exclude target, metadata)."""
        exclude = {"target", "future_return", "Open", "High", "Low", "Close", "Volume",
                   "time", "date"}
        return [c for c in df.columns if c not in exclude and df[c].dtype in (np.float64, np.float32, np.int64)]


# ---------------------------------------------------------------------------
# 4. MODEL WRAPPER (XGBoost + sklearn fallback)
# ---------------------------------------------------------------------------

class ModelWrapper:
    """
    Unified interface for XGBoost or sklearn models.
    Handles training, prediction, feature importance, and persistence.
    """

    def __init__(self, cfg: FeatureConfig, model_path: Optional[Path] = None):
        self.cfg = cfg
        self.model = None
        self.scaler = StandardScaler()
        self.feature_names: List[str] = []
        self.model_path = model_path or Path("trade_model.pkl")
        self.is_xgb = cfg.model_type == "xgboost" and xgboost_available

    def _create_model(self):
        if self.is_xgb:
            return xgb.XGBClassifier(
                n_estimators=200,
                max_depth=5,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                objective="binary:logistic",
                eval_metric="logloss",
                use_label_encoder=False,
                random_state=42,
                n_jobs=-1,
            )
        else:
            logger.warning("XGBoost not available, falling back to RandomForest")
            return RandomForestClassifier(
                n_estimators=200,
                max_depth=8,
                min_samples_leaf=50,
                random_state=42,
                n_jobs=-1,
            )

    def fit(self, df: pd.DataFrame, feature_cols: List[str]) -> dict:
        """
        Train on historical data.
        Returns metrics dict.
        """
        self.feature_names = feature_cols
        df_clean = df[feature_cols + ["target"]].dropna()

        if len(df_clean) < 1000:
            raise ValueError(f"Insufficient training data: {len(df_clean)} rows")

        X = df_clean[feature_cols].values
        y = df_clean["target"].values

        # Scale for stability (XGBoost handles raw fine, but scaling helps RF)
        X = self.scaler.fit_transform(X)

        # Time-series split for validation
        tscv = TimeSeriesSplit(n_splits=3)
        scores = []
        for train_idx, val_idx in tscv.split(X):
            X_train, X_val = X[train_idx], X[val_idx]
            y_train, y_val = y[train_idx], y[val_idx]

            model = self._create_model()
            model.fit(X_train, y_train)
            scores.append(model.score(X_val, y_val))

        # Final fit on all data
        self.model = self._create_model()
        self.model.fit(X, y)

        metrics = {
            "cv_accuracy": round(np.mean(scores), 4),
            "train_samples": len(df_clean),
            "features": len(feature_cols),
            "model": "xgboost" if self.is_xgb else "sklearn_rf",
        }

        self.save()
        logger.info(f"Model trained: {metrics}")
        return metrics

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Return [p_down, p_up] for each row."""
        if self.model is None:
            self.load()
        X_scaled = self.scaler.transform(X[self.feature_names].values)
        proba = self.model.predict_proba(X_scaled)
        return proba

    def feature_importance(self) -> pd.DataFrame:
        """Return feature importance sorted."""
        if self.model is None:
            raise RuntimeError("Model not trained")

        if self.is_xgb:
            imp = self.model.feature_importances_
        else:
            imp = self.model.feature_importances_

        return pd.DataFrame({
            "feature": self.feature_names,
            "importance": imp
        }).sort_values("importance", ascending=False)

    def save(self):
        """Persist model + scaler + feature names."""
        payload = {
            "model": self.model,
            "scaler": self.scaler,
            "feature_names": self.feature_names,
            "cfg": self.cfg,
        }
        with open(self.model_path, "wb") as f:
            pickle.dump(payload, f)
        # Also save feature list as JSON for the bot
        with open(self.model_path.with_suffix(".features.json"), "w") as f:
            json.dump(self.feature_names, f)

    def load(self):
        """Load model from disk."""
        with open(self.model_path, "rb") as f:
            payload = pickle.load(f)
        self.model = payload["model"]
        self.scaler = payload["scaler"]
        self.feature_names = payload["feature_names"]
        self.cfg = payload.get("cfg", self.cfg)


# ---------------------------------------------------------------------------
# 5. DATA FETCHER (abstraction over OANDA / yfinance)
# ---------------------------------------------------------------------------

class DataFetcher:
    """
    Unified data fetcher. Normalizes OANDA and yfinance into same format.
    """

    def __init__(self, use_oanda: bool = True, oanda_api=None,
                 oanda_granularity: str = "M15"):
        self.use_oanda = use_oanda
        self.oanda_api = oanda_api
        self.oanda_granularity = oanda_granularity

    def fetch(self, pair: str, oanda_sym: str, count: int = 200) -> pd.DataFrame:
        if self.use_oanda and self.oanda_api:
            return self._from_oanda(oanda_sym, count)
        else:
            return self._from_yfinance(pair, count)

    def _from_oanda(self, instrument: str, count: int) -> pd.DataFrame:
        from oandapyV20.endpoints.instruments import InstrumentsCandles
        resp = self.oanda_api.request(
            InstrumentsCandles(
                instrument=instrument,
                params={"count": count, "granularity": self.oanda_granularity}
            )
        )
        candles = resp.get("candles", [])
        rows = []
        for c in candles:
            mid = c.get("mid", {})
            if not mid:
                continue
            try:
                rows.append({
                    "time": pd.to_datetime(c["time"]),
                    "Open": float(mid["o"]),
                    "High": float(mid["h"]),
                    "Low": float(mid["l"]),
                    "Close": float(mid["c"]),
                    "Volume": float(c.get("volume", 0)),
                })
            except Exception:
                continue
        df = pd.DataFrame(rows)
        if df.empty:
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
        return df.set_index("time").astype({
            "Open": float, "High": float, "Low": float, "Close": float, "Volume": float
        })

    def _from_yfinance(self, pair: str, count: int) -> pd.DataFrame:
        import yfinance as yf
        # yfinance doesn't take count, use period
        df = yf.download(pair, period="5d", interval="15m", progress=False)
        if df.empty:
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
        # Flatten multi-index columns if present
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] for c in df.columns]
        return df[["Open", "High", "Low", "Close", "Volume"]].tail(count)


# ---------------------------------------------------------------------------
# 6. INTEGRATION EXAMPLE
# ---------------------------------------------------------------------------
"""
# In fx_trade_bot.py, replace data fetching + feature building with:

from data_pipeline import FeatureConfig, FeatureEngine, ModelWrapper, DataFetcher, ATRModule

# --- Setup ---
cfg = FeatureConfig(
    use_atr=True,
    atr_sl_mult=2.0,
    atr_tp_mult=3.0,
    use_macd=False,
    use_rsi=True,
    model_type="xgboost",
    target_horizon=6,
)
feat_engine = FeatureEngine(cfg)
fetcher = DataFetcher(use_oanda=USE_OANDA_DATA, oanda_api=api, oanda_granularity="M15")

# --- Training (run once per week) ---
model_wrapper = ModelWrapper(cfg, model_path=BASE_DIR / "trade_model_xgb.pkl")
if not model_wrapper.model_path.exists() or needs_retrain():
    # Fetch long history for all pairs
    train_dfs = []
    for pair in DEFAULT_PAIRS:
        oanda = YAHOO_TO_OANDA[pair]
        raw = fetcher.fetch(pair, oanda, count=cfg.train_lookback_bars)
        df = feat_engine.build(raw)
        df = feat_engine.build_target(df, horizon=cfg.target_horizon)
        train_dfs.append(df)
    full_df = pd.concat(train_dfs).dropna()
    feature_cols = feat_engine.get_feature_columns(full_df)
    metrics = model_wrapper.fit(full_df, feature_cols)
    print(f"Training complete: {metrics}")
    print(model_wrapper.feature_importance().head(10))
else:
    model_wrapper.load()
    feature_cols = model_wrapper.feature_names

# --- Inference (each run) ---
for pair in DEFAULT_PAIRS:
    oanda = YAHOO_TO_OANDA[pair]
    raw = fetcher.fetch(pair, oanda, count=200)
    df = feat_engine.build(raw).dropna()
    latest = df.iloc[-1]
    proba = model_wrapper.predict_proba(pd.DataFrame([latest[feature_cols]]))
    p_up = proba[0, 1]
    # ... pass p_up to strategy_decision.py ...

# --- ATR-based SL/TP (instead of pivot-based) ---
atr_mod = ATRModule(period=14)
atr_val = latest["atr"]
sl, tp = atr_mod.sl_tp_from_atr(
    entry=current_price,
    direction="BUY",  # or "SELL"
    atr_value=atr_val,
    is_jpy="JPY" in pair,
    sl_mult=cfg.atr_sl_mult,
    tp_mult=cfg.atr_tp_mult,
)

# --- Position sizing ---
equity = get_account_equity()  # you implement this
units = atr_mod.position_size(
    equity=equity,
    risk_pct=cfg.risk_per_trade_pct,
    entry=current_price,
    sl=sl,
    pair=pair,
    atr_value=atr_val,
)
"""