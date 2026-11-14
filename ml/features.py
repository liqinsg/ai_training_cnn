# ─────────────────────────────────────────────────────────────────────────────
# 非权威（NON-AUTHORITATIVE）— DO NOT WIRE  ｜ Phase 3.1 隔离标注
# ─────────────────────────────────────────────────────────────────────────────
# 注意：文件名/正文自称 "AUTHORITATIVE"，实为非权威。本文件来自一条分歧
# （Gemini）开发线，自造了一套并行特征契约，仅供存档参考；严禁接线。
# 与权威实现的冲突：
#   * 与 data_pipeline.FeatureEngine 及 trade_model_xgb.features.json 不同源
#     （列名 / 顺序 / NaN 清洗策略均不一致），接线即制造训练-推理特征偏离
#   * build_target() 默认 horizon=5，而生产 TARGET_HORIZON=6
# 权威替代：data_pipeline.py（生产特征引擎与特征契约）
# ─────────────────────────────────────────────────────────────────────────────
# ml/features.py — AUTHORITATIVE FEATURE CONTRACT (PHASE 3)
# Single implementation shared by offline training and online inference.
# Guarantees deterministic calculation, explicit schema, and parity.

import logging
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "v1.0"


class FeatureContractEngine:
    """
    Authoritative feature engineering engine enforcing 100% parity 
    between training and live inference.
    """

    def __init__(self, config=None):
        self.config = config or {}
        self.schema_version = SCHEMA_VERSION

    def build(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Computes all technical features deterministically on raw OHLCV candles.
        
        Args:
            df: DataFrame containing at least ['open', 'high', 'low', 'close', 'volume']
            config: Optional configuration dictionary for feature engineering parameters.
        Returns:
            DataFrame with all engineered feature columns added.
        """
        if df.empty or len(df) < 20:
            raise ValueError(f"Insufficient data for feature engineering: len={len(df)}")

        work_df = df.copy()

        # Ensure lowercase column names for internal consistency
        work_df.columns = [c.lower() for c in work_df.columns]

        required_cols = ["open", "high", "low", "close"]
        for col in required_cols:
            if col not in work_df.columns:
                raise KeyError(f"Missing required price column: {col}")

        # 1. Returns & Momentum Features
        work_df["ret_1"] = work_df["close"].pct_change(1)
        work_df["ret_5"] = work_df["close"].pct_change(5)
        work_df["ret_10"] = work_df["close"].pct_change(10)

        # 2. Moving Averages & Trend
        work_df["sma_20"] = work_df["close"].rolling(window=20).mean()
        work_df["sma_50"] = work_df["close"].rolling(window=50).mean()
        work_df["price_to_sma20"] = (work_df["close"] - work_df["sma_20"]) / work_df["sma_20"]

        # 3. Volatility (ATR - True Range)
        high_low = work_df["high"] - work_df["low"]
        high_close = (work_df["high"] - work_df["close"].shift()).abs()
        low_close = (work_df["low"] - work_df["close"].shift()).abs()
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        work_df["atr_14"] = true_range.rolling(window=14).mean()
        work_df["atr_ratio"] = work_df["atr_14"] / work_df["close"]

        # 4. RSI (Relative Strength Index - 14 period)
        delta = work_df["close"].diff()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta).where(delta < 0, 0.0)
        avg_gain = gain.rolling(window=14).mean()
        avg_loss = loss.rolling(window=14).mean()
        rs = avg_gain / (avg_loss + 1e-8)
        work_df["rsi_14"] = 100.0 - (100.0 / (1.0 + rs))

        # 5. Deterministic NaN & Inf Cleaning Policy
        # Replace infinite values with NaN, then forward/backward fill or drop boundary warm-ups
        work_df.replace([np.inf, -np.inf], np.nan, inplace=True)

        return work_df

    def build_target(self, df: pd.DataFrame, horizon: int = 5, threshold: float = 0.0005) -> pd.DataFrame:
        """
        Builds the authoritative classification target / label.
        Directional target: 1 if future return > threshold, else 0.
        """
        work_df = df.copy()
        # Future return over horizon
        future_close = work_df["close"].shift(-horizon)
        future_return = (future_close - work_df["close"]) / work_df["close"]
        
        # Binary classification target (1 for up, 0 for down/flat)
        work_df["target"] = (future_return > threshold).astype(int)
        
        # Drop rows where future return cannot be calculated (end of dataset)
        work_df.dropna(subset=["target"], inplace=True)
        return work_df

    def get_feature_columns(self, df: pd.DataFrame) -> list:
        """
        Returns the strictly ordered, deterministic list of feature column names.
        Excludes raw price data, timestamps, and target columns.
        """
        excluded = {"open", "high", "low", "close", "volume", "target", "time", "date"}
        features = [c for c in df.columns if c not in excluded and not c.startswith("unnamed")]
        # Sort to ensure absolute deterministic column ordering between training and inference
        return sorted(features)