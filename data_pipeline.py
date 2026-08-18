"""
data_pipeline.py — v3.1 ADX-Fixed
ATR-aware, XGBoost-first, bulletproof feature engineering.
"""
import json
import pickle
import logging
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone


import numpy as np
import pandas as pd


xgboost_available = False
try:
    import xgboost as xgb
    xgboost_available = True
except ImportError:
    pass


from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler


logger = logging.getLogger(__name__)


def adx(high, low, close, period=14):
    # Ensure we work with Pandas Series to preserve .rolling()
    high = pd.Series(high)
    low = pd.Series(low)
    close = pd.Series(close)

    tr = np.maximum(high - low, np.maximum(abs(high - close.shift(1)), abs(low - close.shift(1))))
    plus_dm = np.where((high - high.shift(1)) > (low.shift(1) - low), high - high.shift(1), 0)
    minus_dm = np.where((low.shift(1) - low) > (high - high.shift(1)), low.shift(1) - low, 0)

    # Convert np arrays back to Series so .rolling() works
    tr = pd.Series(tr)
    plus_dm = pd.Series(plus_dm, index=high.index)
    minus_dm = pd.Series(minus_dm, index=high.index)

    atr = tr.rolling(period).mean()
    plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(period).mean() / atr)
    dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
    return dx.rolling(period).mean()

@dataclass
class FeatureConfig:
    use_atr: bool = True
    atr_period: int = 14
    atr_sl_mult: float = 2.0
    atr_tp_mult: float = 3.0
    atr_position_sizing: bool = True
    risk_per_trade_pct: float = 0.01


    use_returns: bool = True
    use_volatility: bool = True
    use_body_features: bool = True


    use_rsi: bool = True
    rsi_period: int = 14
    use_macd: bool = False
    use_adx: bool = True
    adx_period: int = 14


    model_type: str = "xgboost"
    target_horizon: int = 6
    train_lookback_bars: int = 5000
    retrain_every_n_days: int = 7
    required_bars: int = 20  # absolute minimum



class ATRModule:
    def __init__(self, period: int = 14):
        self.period = period


    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        n = len(df)
        if n < 2:
            df["atr"] = np.nan
            df["atr_pct"] = np.nan
            df["atr_percentile"] = 0.5
            df["atr_ma"] = np.nan
            df["atr_expanding"] = 0
            df["atr_ratio"] = 1.0
            df["vol_regime"] = "normal"
            return df


        try:
            import pandas_ta as ta
            atr_series = ta.atr(df["High"], df["Low"], df["Close"], length=self.period)
            if atr_series is None or atr_series.empty:
                raise ValueError("ta.atr returned None/empty")
            df["atr"] = atr_series
        except Exception as e:
            logger.warning(f"ta.atr failed ({e}), using manual TR")
            df["tr1"] = df["High"] - df["Low"]
            df["tr2"] = (df["High"] - df["Close"].shift(1)).abs()
            df["tr3"] = (df["Low"] - df["Close"].shift(1)).abs()
            df["tr"] = df[["tr1", "tr2", "tr3"]].max(axis=1)
            df["atr"] = df["tr"].rolling(window=self.period, min_periods=1).mean()
            df = df.drop(columns=["tr1", "tr2", "tr3", "tr"], errors="ignore")


        df["atr_pct"] = df["atr"] / df["Close"]


        # ATR percentile — safe rolling min/max method
        lookback = min(n, max(self.period * 2, 50))
        atr_min = df["atr"].rolling(window=lookback, min_periods=1).min()
        atr_max = df["atr"].rolling(window=lookback, min_periods=1).max()
        atr_range = (atr_max - atr_min).replace(0, np.nan)
        df["atr_percentile"] = ((df["atr"] - atr_min) / atr_range).fillna(0.5).clip(0, 1)


        df["atr_ma"] = df["atr"].rolling(window=self.period, min_periods=1).mean()
        df["atr_expanding"] = (df["atr"] > df["atr_ma"]).fillna(0).astype(int)


        hist_window = min(n, self.period * 2)
        atr_hist_mean = df["atr"].rolling(window=hist_window, min_periods=1).mean().replace(0, np.nan)
        df["atr_ratio"] = (df["atr"] / atr_hist_mean).fillna(1.0)


        # Vol regime
        df["vol_regime"] = "normal"
        df.loc[df["atr_percentile"] < 0.25, "vol_regime"] = "low"
        df.loc[df["atr_percentile"] > 0.75, "vol_regime"] = "high"


        return df


    def sl_tp_from_atr(self, entry: float, direction: str,
                       atr_value: float, is_jpy: bool,
                       sl_mult: float = 2.0, tp_mult: float = 3.0
                       ) -> Tuple[Optional[float], Optional[float]]:
        if not atr_value or np.isnan(atr_value) or atr_value <= 0:
            return None, None
        pip = 0.01 if is_jpy else 0.0001
        decimals = 3 if is_jpy else 5
        sl_dist = atr_value * sl_mult
        tp_dist = atr_value * tp_mult
        if direction == "SELL":
            sl = round(entry + sl_dist, decimals)
            tp = round(entry - tp_dist, decimals)
        else:
            sl = round(entry - sl_dist, decimals)
            tp = round(entry + tp_dist, decimals)
        if direction == "SELL" and not (sl > entry > tp):
            return None, None
        if direction == "BUY" and not (tp > entry > sl):
            return None, None
        return sl, tp


    def position_size(self, equity: float, risk_pct: float,
                      entry: float, sl: float,
                      pair: str, atr_value: float) -> int:
        risk_amount = equity * risk_pct
        sl_distance = abs(entry - sl)
        if sl_distance == 0:
            return 0
        units = int(risk_amount / sl_distance)
        atr_pct = (atr_value / entry) if entry and atr_value else 0
        if atr_pct > 0.002:
            units = int(units * 0.5)
            logger.info(f"High volatility ({atr_pct:.4f}), halving size")
        return max(units, 1000)



class FeatureEngine:
    def __init__(self, cfg: FeatureConfig):
        self.cfg = cfg
        self.atr_mod = ATRModule(period=cfg.atr_period)


    def build(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            raise ValueError("Empty DataFrame passed to FeatureEngine")
        n = len(df)
        if n < self.cfg.required_bars:
            logger.warning(f"Only {n} bars, minimum {self.cfg.required_bars} recommended")
        df = df.copy()


        # 1. Returns
        if self.cfg.use_returns:
            for p in [1, 3, 6, 12]:
                if n > p:
                    df[f"ret_{p}h"] = df["Close"].pct_change(p)
            if n > 1:
                df["ret_log"] = np.log(df["Close"] / df["Close"].shift(1))


        # 2. Realized volatility
        if self.cfg.use_volatility:
            for p in [12, 24, 48]:
                if n > p:
                    df[f"vol_{p}h"] = df["Close"].pct_change().rolling(p, min_periods=1).std() * np.sqrt(p * 4)


        # 3. Candle microstructure
        if self.cfg.use_body_features and n > 1:
            df["body"] = (df["Close"] - df["Open"]).abs() / df["Open"]
            df["upper_wick"] = (df["High"] - df[["Close", "Open"]].max(axis=1)) / df["Open"]
            df["lower_wick"] = (df[["Close", "Open"]].min(axis=1) - df["Low"]) / df["Open"]
            df["range"] = (df["High"] - df["Low"]) / df["Open"]
            df["direction"] = np.where(df["Close"] > df["Open"], 1, -1)


        # 4. ATR
        if self.cfg.use_atr:
            try:
                df = self.atr_mod.compute(df)
            except Exception as e:
                logger.error(f"ATR computation failed: {e}")


        # 5. RSI
        if self.cfg.use_rsi and n > self.cfg.rsi_period:
            try:
                import pandas_ta as ta
                df["rsi"] = ta.rsi(df["Close"], length=self.cfg.rsi_period)
                if n > self.cfg.rsi_period + 3:
                    df["rsi_slope"] = df["rsi"].diff(3)
            except Exception as e:
                logger.warning(f"RSI failed: {e}")


        # ─── 6. ADX ✅ FIXED: self.config → self.cfg + bar guard ───
        if self.cfg.use_adx and n > self.cfg.adx_period:
            df['adx'] = adx(df['High'], df['Low'], df['Close'], self.cfg.adx_period).fillna(0.0)


        # 7. MACD
        if self.cfg.use_macd and n > 26:
            try:
                import pandas_ta as ta
                macd = ta.macd(df["Close"])
                if macd is not None and not macd.empty:
                    df = pd.concat([df, macd], axis=1)
            except Exception as e:
                logger.warning(f"MACD failed: {e}")


        # 8. Distance from extremes
        for p in [24, 48, 96]:
            if n > p:
                df[f"dist_high_{p}"] = (df["Close"] - df["High"].rolling(p, min_periods=1).max()) / df["Close"]
                df[f"dist_low_{p}"] = (df["Close"] - df["Low"].rolling(p, min_periods=1).min()) / df["Close"]


        # 9. Volume
        if "Volume" in df.columns and df["Volume"].sum() > 0 and n > 24:
            df["vol_sma_ratio"] = df["Volume"] / df["Volume"].rolling(24, min_periods=1).mean()
            df["vol_trend"] = np.where(df["Volume"] > df["Volume"].shift(1), 1, -1)


        # 10. Time features
        if isinstance(df.index, pd.DatetimeIndex):
            df["hour"] = df.index.hour
            df["day_of_week"] = df.index.dayofweek
            df["is_london"] = ((df["hour"] >= 8) & (df["hour"] <= 16)).astype(int)
            df["is_ny"] = ((df["hour"] >= 13) & (df["hour"] <= 21)).astype(int)
        else:
            df["hour"] = 0
            df["day_of_week"] = 0
            df["is_london"] = 0
            df["is_ny"] = 0


        return df


    def build_target(self, df: pd.DataFrame, horizon: int = 6) -> pd.DataFrame:
        df = df.copy()
        if len(df) > horizon:
            future_return = df["Close"].shift(-horizon) / df["Close"] - 1
            df["target"] = (future_return > 0).astype(int)
            df["future_return"] = future_return
        else:
            df["target"] = np.nan
            df["future_return"] = np.nan
        return df


    def get_feature_columns(self, df: pd.DataFrame) -> List[str]:
        exclude = {"target", "future_return", "Open", "High", "Low", "Close", "Volume",
                   "time", "date", "vol_regime"}
        cols = []
        for c in df.columns:
            if c in exclude:
                continue
            dtype = df[c].dtype
            if np.issubdtype(dtype, np.number):
                cols.append(c)
        return cols



class ModelWrapper:
    def __init__(self, cfg: FeatureConfig, model_path: Optional[Path] = None):
        self.cfg = cfg
        self.model = None
        self.scaler = StandardScaler()
        self.feature_names: List[str] = []
        self.model_path = model_path or Path("trade_model_xgb.pkl")
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
                random_state=42,
                n_jobs=-1,
            )
        else:
            logger.warning("XGBoost not available, falling back to RandomForest")
            return RandomForestClassifier(
                n_estimators=200, max_depth=8, min_samples_leaf=50,
                random_state=42, n_jobs=-1,
            )


    def fit(self, df: pd.DataFrame, feature_cols: List[str]) -> dict:
        self.feature_names = feature_cols
        df_clean = df[feature_cols + ["target"]].dropna()
        if len(df_clean) < 100:
            raise ValueError(f"Insufficient training data: {len(df_clean)} rows (need >= 100)")


        X = df_clean[feature_cols].values
        y = df_clean["target"].values
        X = self.scaler.fit_transform(X)


        tscv = TimeSeriesSplit(n_splits=3)
        scores = []
        for train_idx, val_idx in tscv.split(X):
            if len(train_idx) < 50 or len(val_idx) < 10:
                continue
            X_train, X_val = X[train_idx], X[val_idx]
            y_train, y_val = y[train_idx], y[val_idx]
            model = self._create_model()
            model.fit(X_train, y_train)
            scores.append(model.score(X_val, y_val))


        self.model = self._create_model()
        self.model.fit(X, y)


        metrics = {
            "cv_accuracy": round(np.mean(scores), 4) if scores else None,
            "train_samples": len(df_clean),
            "features": len(feature_cols),
            "model": "xgboost" if self.is_xgb else "sklearn_rf",
        }
        self.save()
        logger.info(f"Model trained: {metrics}")
        return metrics


    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        if self.model is None:
            self.load()
        for col in self.feature_names:
            if col not in X.columns:
                X[col] = 0.0
        X_subset = X[self.feature_names].fillna(0)
        X_scaled = self.scaler.transform(X_subset.values)
        return self.model.predict_proba(X_scaled)


    def feature_importance(self) -> pd.DataFrame:
        if self.model is None:
            raise RuntimeError("Model not trained")
        imp = self.model.feature_importances_
        return pd.DataFrame({
            "feature": self.feature_names,
            "importance": imp
        }).sort_values("importance", ascending=False)


    def save(self):
        payload = {
            "model": self.model,
            "scaler": self.scaler,
            "feature_names": self.feature_names,
            "cfg": self.cfg,
        }
        with open(self.model_path, "wb") as f:
            pickle.dump(payload, f)
        with open(self.model_path.with_suffix(".features.json"), "w") as f:
            json.dump(self.feature_names, f)


    def load(self):
        with open(self.model_path, "rb") as f:
            payload = pickle.load(f)
        self.model = payload["model"]
        self.scaler = payload["scaler"]
        self.feature_names = payload["feature_names"]
        self.cfg = payload.get("cfg", self.cfg)



class DataFetcher:
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
            logger.warning(f"OANDA returned no candles for {instrument}")
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
        df = df.set_index("time").astype({
            "Open": float, "High": float, "Low": float, "Close": float, "Volume": float
        })
        return df


    def _from_yfinance(self, pair: str, count: int) -> pd.DataFrame:
        import yfinance as yf
        df = yf.download(pair, period="5d", interval="15m", progress=False)
        if df.empty:
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] for c in df.columns]
        return df[["Open", "High", "Low", "Close", "Volume"]].tail(count)