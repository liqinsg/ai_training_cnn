# fx_trade_bot_mc.py — Monte Carlo Engine (RARELY CHANGES)
# Contains: MCGenerator class, MCConfig globals

import logging
import json
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


# ============================================================================
# MC CONFIG — Set once per timeframe
# ============================================================================
class MCConfig:
    TIMEFRAME = "H4"
    YF_INTERVAL = "4h"
    YF_PERIOD_FULL = "30d"
    YF_PERIOD_RESAMPLE = "60d"
    MC_LOOKBACK = 90
    MC_FORECAST = 8
    PERIODS_YEAR = 252 * 6
    DT_SCALE = 6
    MC_REPORT_TITLE = "FX H4 MONTE CARLO"
    RESULTS_DIR = None  # type: Path

    @classmethod
    def set_timeframe(cls, tf: str, cfg_dict: dict):
        cls.TIMEFRAME = tf
        for k, v in cfg_dict.items():
            setattr(cls, k, v)


# ============================================================================
# 🎲 MONTE CARLO ENGINE — Pure Simulation Logic
# ============================================================================
class MCGenerator:
    def __init__(self, fetcher, YAHOO_TO_OANDA: dict,
                 simulations: int = 5000, confidence: float = 0.90):
        self.fetcher = fetcher
        self.symbol_map = YAHOO_TO_OANDA
        self.simulations = simulations
        self.confidence = confidence

    @staticmethod
    def _price_decimals(pair: str) -> int:
        return 3 if "JPY" in pair.upper() else 5

    def fetch_data(self, pair: str, oanda_symbol: str) -> pd.DataFrame:
        cfg = MCConfig
        try:
            raw = self.fetcher.fetch(pair, oanda_symbol, count=max(cfg.MC_LOOKBACK + 50, 200))
            if len(raw) >= cfg.MC_LOOKBACK:
                df = raw[["Open", "High", "Low", "Close"]].copy()
                for col in ["Open", "High", "Low", "Close"]:
                    if col not in df.columns:
                        cands = [c for c in df.columns if str(c).lower() == col.lower()]
                        if cands:
                            df.rename(columns={cands[0]: col}, inplace=True)
                return df[["Open", "High", "Low", "Close"]].dropna()
        except Exception as e:
            logger.debug(f"MC OANDA fetch fallback for {pair}: {e}")

        try:
            df = yf.download(pair, period=cfg.YF_PERIOD_FULL, interval=cfg.YF_INTERVAL, progress=False)
            if len(df) >= cfg.MC_LOOKBACK:
                return df[["Open", "High", "Low", "Close"]].dropna()
        except Exception:
            pass

        try:
            fallback_interval = "1h" if cfg.TIMEFRAME == "H4" else "4h"
            df = yf.download(pair, period=cfg.YF_PERIOD_RESAMPLE, interval=fallback_interval, progress=False)
            if df.empty:
                return pd.DataFrame()
            df = df[["Open", "High", "Low", "Close"]].resample(cfg.YF_INTERVAL).agg({
                "Open": "first", "High": "max", "Low": "min", "Close": "last"
            }).dropna()
            if len(df) >= cfg.MC_LOOKBACK:
                return df
        except Exception as e:
            logger.warning(f"MC data failed {pair}: {e}")
        return pd.DataFrame()

    def run_for_pair(self, pair: str, df: pd.DataFrame = None):
        cfg = MCConfig
        oanda_symbol = self.symbol_map[pair]

        if df is None or len(df) < cfg.MC_LOOKBACK:
            df = self.fetch_data(pair, oanda_symbol)
        if len(df) < cfg.MC_LOOKBACK:
            logger.warning(f"MC: insufficient data for {pair} ({len(df)} < {cfg.MC_LOOKBACK})")
            return None, False

        closes = df["Close"].values[-cfg.MC_LOOKBACK:]
        current = float(closes[-1].item())
        log_returns = np.log(closes[1:] / closes[:-1])
        mu, sigma = float(np.mean(log_returns)), float(np.std(log_returns))
        drift = mu * cfg.PERIODS_YEAR
        vol = sigma * np.sqrt(cfg.PERIODS_YEAR)

        rng = np.random.default_rng()
        paths = np.zeros((self.simulations, cfg.MC_FORECAST + 1))
        paths[:, 0] = current
        for t in range(1, cfg.MC_FORECAST + 1):
            z = rng.normal(0, 1, self.simulations)
            paths[:, t] = paths[:, t - 1] * np.exp((mu - 0.5 * sigma ** 2) + sigma * z)

        final = paths[:, -1]
        lower = float(np.percentile(final, (1 - self.confidence) / 2 * 100))
        upper = float(np.percentile(final, (1 + self.confidence) / 2 * 100))
        percentile = round((np.sum(final <= current) / self.simulations) * 100, 1)
        p_up = round((np.sum(final > current) / self.simulations) * 100, 1)
        p_down = round(100 - p_up, 1)
        touch_upper = round((np.any(paths >= upper, axis=1).sum() / self.simulations) * 100, 1)
        touch_lower = round((np.any(paths <= lower, axis=1).sum() / self.simulations) * 100, 1)

        if percentile >= 85 and p_down > 55:
            regime = f"🔴 {cfg.TIMEFRAME} OVERBOUGHT | Mean‑Reversion Risk"
        elif percentile <= 15 and p_up > 55:
            regime = f"🟢 {cfg.TIMEFRAME} OVERSOLD | Bullish Reversal Chance"
        elif abs(drift) > vol * 0.7 and max(p_up, p_down) > 60:
            regime = f"⚡ {cfg.TIMEFRAME} STRONG MOMENTUM"
        elif abs(p_up - p_down) < 4 and abs(drift) < vol * 0.3:
            regime = f"⏳ {cfg.TIMEFRAME} CONSOLIDATION RANGE"
        else:
            regime = f"🔹 {cfg.TIMEFRAME} NEUTRAL"

        dec = self._price_decimals(pair)
        result = {
            "timeframe": cfg.TIMEFRAME, "pair": pair, "current_price": round(current, dec),
            "ann_drift_pct": round(drift * 100, 2), "ann_vol_pct": round(vol * 100, 2),
            "range_90": [round(lower, dec), round(upper, dec)],
            "percentile_rank": percentile, "p_up": p_up, "p_down": p_down,
            "p_up_pct": p_up, "p_down_pct": p_down,
            "touch_upper_pct": touch_upper, "touch_lower_pct": touch_lower,
            "regime": regime, "lookback": cfg.MC_LOOKBACK, "forecast": cfg.MC_FORECAST,
            "simulations": self.simulations, "generated_utc": datetime.now(timezone.utc).isoformat(),
        }
        return result, True

    def save(self, result: dict):
        cfg = MCConfig
        safe = result["pair"].replace("=X", "").replace("=", "_")
        tag = "daily" if cfg.TIMEFRAME == "D" else "h4"
        now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
        fname = cfg.RESULTS_DIR / f"{tag}_mc_{safe}_{now_str}.json"
        with open(fname, "w") as f:
            json.dump(result, f, indent=2)
        return fname