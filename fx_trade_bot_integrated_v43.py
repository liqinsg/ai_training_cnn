# fx_trade_bot_integrated.py — v4.2 Clean Rebuild (Bot + MC + Dynamic Exit + Strength Guard)
# Strategy: strategy_decision.py | Data: data_pipeline.py | MC: inline
import config
def cfg(name, default):
    return getattr(config, name, default)

import sys
import json
import logging
import argparse
from pathlib import Path
from datetime import datetime, timezone
from enum import Enum

BASE_DIR = Path(__file__).resolve().parent
sys.path.extend([str(BASE_DIR), str(BASE_DIR / "utils")])

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(BASE_DIR / "bot.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# ── Suppress noisy oandapyV20 "performing request" logs ──
# Set DEBUG_API=True in config.py to see every API call
DEBUG_API = cfg("DEBUG_MODE", False)
if not DEBUG_API:
    logging.getLogger("oandapyV20").setLevel(logging.WARNING)
    logging.getLogger("oandapyV20.oandapyV20").setLevel(logging.WARNING)
    logging.getLogger("oandapyV20.endpoints").setLevel(logging.WARNING)

import numpy as np
import pandas as pd
import yfinance as yf

from utils.trading_core import get_candles as get_oanda_candles
from utils.calculate_currency_strength import calculate_currency_strength
from utils.strategy_helpers import build_strength_matrix, format_strength_ranking
from telegram_message import send_telegram_message

from config_oanda import OANDA_API_TOKEN, OANDA_ACCOUNT_ID, OANDA_ENV
import oandapyV20

from oandapyV20.endpoints.instruments import InstrumentsCandles
from oandapyV20.endpoints.positions import PositionDetails
from oandapyV20.endpoints.orders import OrderCreate
from oandapyV20.endpoints.trades import OpenTrades, TradeCRCDO

from strategy_decision import StrategyConfig, StrategyEngine, FilterMode, Direction
from data_pipeline import FeatureConfig, FeatureEngine, ModelWrapper, DataFetcher, ATRModule

api = oandapyV20.API(access_token=OANDA_API_TOKEN, environment=OANDA_ENV)


def cfg(name, default):
    return getattr(config, name, default)


# ============================================================================
# ARGUMENT PARSING
# ============================================================================
parser = argparse.ArgumentParser(description="FX Trade Bot + Monte Carlo")
parser.add_argument("--timeframe", choices=["D", "H4", "15m", "1h"], default="H4",
                    help="Primary timeframe: drives OANDA granularity and MC config")
parser.add_argument("--mc-only", action="store_true",
                    help="Run only MC generation + report, skip trading")
parser.add_argument("--skip-mc", action="store_true",
                    help="Skip MC generation (legacy file fallback)")
parser.add_argument("--test-trade", action="store_true",
                    help="TEST MODE: bypass strength veto, lower threshold, trade any >51% prob")
args = parser.parse_args()

MODE = cfg("MODE", "LEVEL10")
USE_OANDA_DATA = True
TIMEFRAME = args.timeframe
OANDA_GRANULARITY_MAP = {
    "1m": "M1", "5m": "M5", "15m": "M15",
    "30m": "M30", "1h": "H1", "4h": "H4", "H4": "H4", "1d": "D", "D": "D",
}
OANDA_GRANULARITY = OANDA_GRANULARITY_MAP.get(TIMEFRAME, "H4")

USE_DEFAULT_LOT_SIZE = cfg("USE_DEFAULT_LOT_SIZE", True)
DEFAULT_LOT_SIZE = cfg("DEFAULT_LOT_SIZE", 10000)
DEFAULT_PAIRS = cfg(
    "DEFAULT_PAIRS",
    [
        "EURUSD=X", "GBPUSD=X", "EURJPY=X", "GBPJPY=X",
        "AUDUSD=X", "USDJPY=X", "GBPAUD=X", "USDCHF=X",
    ],
)
YAHOO_TO_OANDA = cfg(
    "YAHOO_TO_OANDA",
    {
        "EURUSD=X": "EUR_USD", "GBPUSD=X": "GBP_USD",
        "EURJPY=X": "EUR_JPY", "GBPJPY=X": "GBP_JPY",
        "AUDUSD=X": "AUD_USD", "USDJPY=X": "USD_JPY",
        "GBPAUD=X": "GBP_AUD", "USDCHF=X": "USD_CHF",
    },
)
OANDA_TO_YAHOO = {v: k for k, v in YAHOO_TO_OANDA.items()}

REOPEN_DELAY_RUNS = 2
last_closed: dict = {}
COOLDOWN_FILE = BASE_DIR / "cooldown_state.json"

RESULTS_DIR = BASE_DIR / "daily_results"
RESULTS_DIR.mkdir(exist_ok=True)
TODAY_STR = datetime.now(timezone.utc).strftime("%Y%m%d")
MC_MAX_AGE_HOURS = cfg("MC_MAX_AGE_HOURS", 24)

# ============================================================================
# TIMEFRAME CONFIG
# ============================================================================
if TIMEFRAME in ("H4", "4h"):
    MC_TF = "H4"
    YF_INTERVAL = "4h"
    YF_PERIOD_FULL = "30d"
    YF_PERIOD_RESAMPLE = "60d"
    MC_LOOKBACK = cfg("H4_LOOKBACK", 90)
    MC_FORECAST = cfg("H4_FORECAST", 8)
    PERIODS_YEAR = 252 * 6
    DT_SCALE = 6
    MC_REPORT_TITLE = "FX H4 MONTE CARLO"
elif TIMEFRAME in ("D", "1d"):
    MC_TF = "D"
    YF_INTERVAL = "1d"
    YF_PERIOD_FULL = "120d"
    YF_PERIOD_RESAMPLE = "180d"
    MC_LOOKBACK = cfg("DAILY_LOOKBACK", 90)
    MC_FORECAST = cfg("DAILY_FORECAST", 5)
    PERIODS_YEAR = 252
    DT_SCALE = 1
    MC_REPORT_TITLE = "FX DAILY MONTE CARLO"
else:
    MC_TF = "H4"
    YF_INTERVAL = "4h"
    YF_PERIOD_FULL = "30d"
    YF_PERIOD_RESAMPLE = "60d"
    MC_LOOKBACK = cfg("H4_LOOKBACK", 90)
    MC_FORECAST = cfg("H4_FORECAST", 8)
    PERIODS_YEAR = 252 * 6
    DT_SCALE = 6
    MC_REPORT_TITLE = "FX H4 MONTE CARLO (Intraday Context)"

SIMULATIONS = cfg("MC_SIMULATIONS", 5000)
CONFIDENCE = cfg("MC_CONFIDENCE", 0.90)

# ============================================================================
# INIT PIPELINE
# ============================================================================
FEAT_CFG = FeatureConfig(
    use_atr=True,
    atr_sl_mult=2.0,
    atr_tp_mult=3.0,
    use_macd=False,
    use_rsi=True,
    use_adx=True,
    model_type="xgboost",
    target_horizon=6,
    train_lookback_bars=5000,
)
STRAT_CFG = StrategyConfig(
    mode=MODE,
    min_conviction_score=45.0,
    base_min_edge=0.50 if MODE == "LEVEL10" else 0.51,
    mc_filter_mode=FilterMode.PENALIZE,
    regime_filter_mode=FilterMode.OFF,
    adx_filter_mode=FilterMode.OFF,
    pivot_filter_mode=FilterMode.PENALIZE,
    strength_gap_filter_mode=FilterMode.PENALIZE,
    cooldown_filter_mode=FilterMode.BLOCK,
)

feat_engine = FeatureEngine(FEAT_CFG)
strat_engine = StrategyEngine(STRAT_CFG, model=None, feature_list=[])
fetcher = DataFetcher(use_oanda=USE_OANDA_DATA, oanda_api=api, oanda_granularity=OANDA_GRANULARITY)
atr_mod = ATRModule(period=FEAT_CFG.atr_period)

MODEL_PATH = BASE_DIR / "trade_model_xgb.pkl"
model_wrapper = ModelWrapper(FEAT_CFG, model_path=MODEL_PATH)


# ============================================================================
# COOLDOWN
# ============================================================================
def load_cooldown():
    if COOLDOWN_FILE.exists():
        with open(COOLDOWN_FILE) as f:
            raw = json.load(f)
            return {k: (Direction(v[0]), v[1]) for k, v in raw.items()}
    return {}


def save_cooldown(state):
    serializable = {k: (v[0].value, v[1]) for k, v in state.items()}
    with open(COOLDOWN_FILE, "w") as f:
        json.dump(serializable, f)


last_closed = load_cooldown()


# ============================================================================
# MARKET STATUS
# ============================================================================
def forex_market_closed():
    try:
        resp = api.request(
            InstrumentsCandles(
                instrument="EUR_USD",
                params={"count": 1, "granularity": OANDA_GRANULARITY},
            )
        )
        return len(resp.get("candles", [])) == 0
    except Exception as e:
        logger.error(f"Market check failed: {e}")
        return True


# ============================================================================
# POSITION HELPERS
# ============================================================================
def get_open_position(instrument: str):
    try:
        pos = api.request(
            PositionDetails(accountID=OANDA_ACCOUNT_ID, instrument=instrument)
        ).get("position", {})
        long_units = pos.get("long", {}).get("units", "0")
        short_units = pos.get("short", {}).get("units", "0")
        if long_units != "0":
            return {"units": int(long_units), "side": "long"}
        if short_units != "0":
            return {"units": -int(short_units), "side": "short"}
        return None
    except Exception as e:
        logger.error(f"Position check failed for {instrument}: {e}")
        return None


def close_position(instrument: str):
    try:
        pos = api.request(
            PositionDetails(accountID=OANDA_ACCOUNT_ID, instrument=instrument)
        ).get("position", {})
        if pos.get("long", {}).get("units", "0") != "0":
            units = -int(pos["long"]["units"])
        elif pos.get("short", {}).get("units", "0") != "0":
            units = abs(int(pos["short"]["units"]))
        else:
            logger.info(f"No position to close: {instrument}")
            return
        api.request(
            OrderCreate(
                accountID=OANDA_ACCOUNT_ID,
                data={
                    "order": {
                        "type": "MARKET",
                        "instrument": instrument,
                        "units": str(units),
                        "positionFill": "REDUCE_ONLY",
                    }
                },
            )
        )
        logger.info(f"Closed {instrument}")
        send_telegram_message(f"🔄 AUTO‑CLOSE: {instrument}")
    except Exception as e:
        logger.error(f"Close failed for {instrument}: {e}")


# ============================================================================
# ORDER
# ============================================================================
def open_oanda_order(signal: dict, units: int, current_price: float = None) -> dict:
    if not OANDA_ACCOUNT_ID or not OANDA_API_TOKEN:
        return {"status": "ERROR", "message": "Missing OANDA credentials"}
    pair_raw = signal.get("pair")
    action = signal.get("action")
    if action not in {"BUY", "SELL"}:
        return {"status": "ERROR", "message": f"Invalid action: {action}"}
    units = int(units) if action == "BUY" else -int(units)
    sl = signal.get("stop_loss")
    if sl is None:
        return {"status": "ERROR", "message": "SL missing"}

    # ── HARD SAFETY GUARD ──
    is_jpy = "JPY" in pair_raw
    dec = 3 if is_jpy else 5
    pip_size = 0.01 if is_jpy else 0.0001
    entry = current_price if current_price else sl

    max_sl_pips = cfg("MAX_SL_PIPS", 500 if is_jpy else 50)
    max_sl_pct = cfg("MAX_SL_DISTANCE_PCT", 0.03)
    sl_distance = abs(entry - sl)
    sl_pips = sl_distance / pip_size
    sl_pct = sl_distance / entry

    if sl_pips > max_sl_pips or sl_pct > max_sl_pct:
        err = (f"SL GUARD BLOCKED {pair_raw}: SL={sl} is {sl_pips:.0f} pips / {sl_pct:.1%} from entry. "
               f"Max allowed: {max_sl_pips} pips / {max_sl_pct:.1%}")
        logger.error(err)
        send_telegram_message(f"🛡️ {err}")
        return {"status": "ERROR", "message": err}

    if action == "BUY" and sl >= entry:
        err = f"SL GUARD BLOCKED {pair_raw}: SL {sl} >= entry {entry} for LONG"
        logger.error(err)
        return {"status": "ERROR", "message": err}
    if action == "SELL" and sl <= entry:
        err = f"SL GUARD BLOCKED {pair_raw}: SL {sl} <= entry {entry} for SHORT"
        logger.error(err)
        return {"status": "ERROR", "message": err}

    # ── PERMANENTLY NO TP ──
    order_payload = {
        "order": {
            "type": "MARKET",
            "instrument": pair_raw,
            "units": str(units),
            "timeInForce": "FOK",
            "positionFill": "DEFAULT",
            "stopLossOnFill": {
                "price": str(round(float(sl), dec)),
                "timeInForce": "GTC",
            },
        }
    }
    # TP intentionally omitted. Profit captured by dynamic trailing/breakeven SL.

    try:
        resp = api.request(OrderCreate(accountID=OANDA_ACCOUNT_ID, data=order_payload))
        logger.info(f"OANDA accepted order for {pair_raw}")
        return {"status": "OK", "response": resp}
    except Exception as e:
        logger.error(f"OANDA order failed for {pair_raw}: {e}")
        return {"status": "ERROR", "message": str(e)}


# ============================================================================
# EQUITY
# ============================================================================
def get_account_equity() -> float:
    try:
        from oandapyV20.endpoints.accounts import AccountDetails
        resp = api.request(AccountDetails(accountID=OANDA_ACCOUNT_ID))
        return float(resp["account"]["balance"])
    except Exception as e:
        logger.warning(f"Could not fetch equity: {e}, using fallback 10000")
        return 10000.0


# ============================================================================
# MODEL
# ============================================================================
def ensure_model():
    global model_wrapper, strat_engine
    needs_train = False
    if not MODEL_PATH.exists():
        needs_train = True
        logger.info("Model not found. Training...")
    else:
        age_days = (datetime.now(timezone.utc).timestamp() - MODEL_PATH.stat().st_mtime) / 86400
        if age_days > FEAT_CFG.retrain_every_n_days:
            needs_train = True
            logger.info(f"Model stale ({age_days:.1f} days). Retraining...")

    if needs_train:
        train_dfs = []
        for pair in DEFAULT_PAIRS:
            oanda = YAHOO_TO_OANDA[pair]
            try:
                raw = fetcher.fetch(pair, oanda, count=FEAT_CFG.train_lookback_bars)
                if len(raw) < FEAT_CFG.required_bars:
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


# ============================================================================
# 🎲 MONTE CARLO ENGINE
# ============================================================================
class MCGenerator:
    def __init__(self, simulations: int = 5000, confidence: float = 0.90):
        self.simulations = simulations
        self.confidence = confidence

    def fetch_data(self, pair: str, oanda_symbol: str) -> pd.DataFrame:
        try:
            raw = fetcher.fetch(pair, oanda_symbol, count=max(MC_LOOKBACK + 50, 200))
            if len(raw) >= MC_LOOKBACK:
                df = raw[["Open", "High", "Low", "Close"]].copy() if isinstance(raw, pd.DataFrame) else raw
                for col in ["Open", "High", "Low", "Close"]:
                    if col not in df.columns:
                        cands = [c for c in df.columns if str(c).lower() == col.lower()]
                        if cands:
                            df.rename(columns={cands[0]: col}, inplace=True)
                return df[["Open", "High", "Low", "Close"]].dropna()
        except Exception as e:
            logger.debug(f"MC OANDA fetch fallback for {pair}: {e}")

        try:
            df = yf.download(pair, period=YF_PERIOD_FULL, interval=YF_INTERVAL, progress=False)
            if len(df) >= MC_LOOKBACK:
                return df[["Open", "High", "Low", "Close"]].dropna()
        except Exception:
            pass

        try:
            fallback_interval = "1h" if MC_TF == "H4" else "4h"
            df = yf.download(pair, period=YF_PERIOD_RESAMPLE, interval=fallback_interval, progress=False)
            if df.empty:
                return pd.DataFrame()
            df = df[["Open", "High", "Low", "Close"]].resample(YF_INTERVAL).agg({
                "Open": "first", "High": "max", "Low": "min", "Close": "last"
            }).dropna()
            if len(df) >= MC_LOOKBACK:
                return df
        except Exception as e:
            logger.warning(f"MC data failed {pair}: {e}")

        return pd.DataFrame()

    def run_for_pair(self, pair: str, oanda_symbol: str, df: pd.DataFrame = None):
        if df is None or len(df) < MC_LOOKBACK:
            df = self.fetch_data(pair, oanda_symbol)

        if len(df) < MC_LOOKBACK:
            logger.warning(f"MC: insufficient data for {pair} ({len(df)} < {MC_LOOKBACK})")
            return None, False

        closes = df["Close"].values[-MC_LOOKBACK:]
        current = float(closes[-1].item())
        log_returns = np.log(closes[1:] / closes[:-1])

        mu = float(np.mean(log_returns))
        drift = mu * PERIODS_YEAR  # annualized for regime display
        sigma = float(np.std(log_returns))
        vol = sigma * np.sqrt(PERIODS_YEAR)  # annualized for regime display

        rng = np.random.default_rng()  # fresh seed every run
        paths = np.zeros((self.simulations, MC_FORECAST + 1))
        paths[:, 0] = current
        for t in range(1, MC_FORECAST + 1):
            z = rng.normal(0, 1, self.simulations)
            # Use raw per-period returns directly — no dt scaling needed
            paths[:, t] = paths[:, t - 1] * np.exp(
                (mu - 0.5 * sigma ** 2) + sigma * z
            )

        final = paths[:, -1]
        lower = float(np.percentile(final, (1 - self.confidence) / 2 * 100))
        upper = float(np.percentile(final, (1 + self.confidence) / 2 * 100))

        percentile = round((np.sum(final <= current) / self.simulations) * 100, 1)
        p_up = round((np.sum(final > current) / self.simulations) * 100, 1)
        p_down = round(100 - p_up, 1)
        touch_upper = round((np.any(paths >= upper, axis=1).sum() / self.simulations) * 100, 1)
        touch_lower = round((np.any(paths <= lower, axis=1).sum() / self.simulations) * 100, 1)

        if percentile >= 85 and p_down > 55:
            regime = f"🔴 {MC_TF} OVERBOUGHT | Mean‑Reversion Risk"
        elif percentile <= 15 and p_up > 55:
            regime = f"🟢 {MC_TF} OVERSOLD | Bullish Reversal Chance"
        elif abs(drift) > vol * 0.7 and max(p_up, p_down) > 60:
            regime = f"⚡ {MC_TF} STRONG MOMENTUM"
        elif abs(p_up - p_down) < 4 and abs(drift) < vol * 0.3:
            regime = f"⏳ {MC_TF} CONSOLIDATION RANGE"
        else:
            regime = f"🔹 {MC_TF} NEUTRAL"

        dec = 3 if "JPY" in pair else 5
        result = {
            "timeframe": MC_TF,
            "pair": pair,
            "current_price": round(current, dec),
            "ann_drift_pct": round(drift * 100, 2),
            "ann_vol_pct": round(vol * 100, 2),
            "range_90": [round(lower, dec), round(upper, dec)],
            "percentile_rank": percentile,
            "p_up": p_up,
            "p_down": p_down,
            "p_up_pct": p_up,
            "p_down_pct": p_down,
            "touch_upper_pct": touch_upper,
            "touch_lower_pct": touch_lower,
            "regime": regime,
            "lookback": MC_LOOKBACK,
            "forecast": MC_FORECAST,
            "simulations": self.simulations,
            "generated_utc": datetime.now(timezone.utc).isoformat(),
        }
        return result, True

    def save(self, result: dict):
        safe = result["pair"].replace("=X", "").replace("=", "_")
        tag = "daily" if MC_TF == "D" else "h4"
        now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
        fname = RESULTS_DIR / f"{tag}_mc_{safe}_{now_str}.json"
        with open(fname, "w") as f:
            json.dump(result, f, indent=2)
        return fname


# ============================================================================
# 🎯 DYNAMIC POSITION MANAGER — Breakeven + Trailing Stop
# ============================================================================
class DynamicPositionManager:
    def __init__(
        self,
        api,
        account_id: str,
        be_trigger_atr_mult: float = 1.5,
        trail_trigger_atr_mult: float = 2.5,
        trail_atr_mult: float = 1.5,
        max_hold_bars: int = 12,
    ):
        self.api = api
        self.account_id = account_id
        self.be_trigger = be_trigger_atr_mult
        self.trail_trigger = trail_trigger_atr_mult
        self.trail_mult = trail_atr_mult
        self.max_hold = max_hold_bars

    def _get_open_trades(self, instrument: str):
        try:
            resp = self.api.request(OpenTrades(accountID=self.account_id))
            trades = []
            for t in resp.get("trades", []):
                if t.get("instrument") == instrument:
                    trades.append(t)
            return trades
        except Exception as e:
            logger.error(f"Failed to fetch open trades for {instrument}: {e}")
            return []

    def _current_price(self, instrument: str, side: str) -> float:
        try:
            r = InstrumentsCandles(
                instrument=instrument,
                params={"count": 1, "granularity": "M1", "price": "BA"},
            )
            resp = self.api.request(r)["candles"][0]
            if side == "long":
                return float(resp["bid"]["c"])
            return float(resp["ask"]["c"])
        except Exception as e:
            logger.warning(f"Price fetch failed for {instrument}: {e}")
            return None

    def _update_trade_sl(self, trade_id: str, new_sl: float, decimals: int):
        try:
            data = {
                "stopLoss": {
                    "price": str(round(new_sl, decimals)),
                    "timeInForce": "GTC",
                }
            }
            self.api.request(
                TradeCRCDO(
                    accountID=self.account_id,
                    tradeID=trade_id,
                    data=data,
                )
            )
            logger.info(f"   🔄 Updated SL on trade {trade_id} → {round(new_sl, decimals)}")
            return True
        except Exception as e:
            logger.error(f"   ❌ Failed to update SL on trade {trade_id}: {e}")
            return False

    def update_all(self, pair_data: dict):
        for pair, info in pair_data.items():
            instrument = info["oanda"]
            df = info.get("df")
            if df is None or len(df) < 2:
                continue

            atr_val = df.iloc[-1].get("atr")
            if atr_val is None or np.isnan(atr_val) or atr_val <= 0:
                continue

            is_jpy = "JPY" in pair
            decimals = 3 if is_jpy else 5
            pip_size = 0.01 if is_jpy else 0.0001

            trades = self._get_open_trades(instrument)
            if not trades:
                continue

            for trade in trades:
                tid = trade["id"]
                units = int(trade["currentUnits"])
                side = "long" if units > 0 else "short"
                entry = float(trade["price"])
                current_sl_raw = trade.get("stopLossOrder", {}).get("price")
                current_sl = float(current_sl_raw) if current_sl_raw else None

                current_price = self._current_price(instrument, side)
                if current_price is None:
                    continue

                if side == "long":
                    profit_pips = (current_price - entry) / pip_size
                else:
                    profit_pips = (entry - current_price) / pip_size

                open_time = datetime.fromisoformat(trade["openTime"].replace("Z", "+00:00"))
                BAR_HOURS = {"15m": 0.25, "1h": 1, "H4": 4, "4h": 4, "D": 24, "1d": 24}
                bar_hours = BAR_HOURS.get(TIMEFRAME, 4)
                bars_held = (datetime.now(timezone.utc) - open_time).total_seconds() / 3600 / bar_hours

                new_sl = None
                action = None

                # 1) TIME DECAY
                if bars_held >= self.max_hold:
                    logger.info(f"⏰ TIME EXIT: {pair} trade {tid} held {bars_held:.1f} H4 bars")
                    close_position(instrument)
                    continue

                # 2) BREAKEVEN
                be_pips = self.be_trigger * atr_val / pip_size
                if profit_pips >= be_pips:
                    if side == "long":
                        be_sl = entry - (1 * pip_size)
                    else:
                        be_sl = entry + (1 * pip_size)
                    if current_sl is None or (side == "long" and be_sl > current_sl) or (side == "short" and be_sl < current_sl):
                        new_sl = be_sl
                        action = "BREAKEVEN"

                # 3) TRAILING STOP
                trail_pips = self.trail_trigger * atr_val / pip_size
                if profit_pips >= trail_pips:
                    if side == "long":
                        trail_sl = current_price - (self.trail_mult * atr_val)
                    else:
                        trail_sl = current_price + (self.trail_mult * atr_val)
                    if current_sl is None or (side == "long" and trail_sl > current_sl) or (side == "short" and trail_sl < current_sl):
                        new_sl = trail_sl
                        action = "TRAIL"

                if new_sl is not None and action:
                    if side == "long" and current_sl and new_sl < current_sl:
                        continue
                    if side == "short" and current_sl and new_sl > current_sl:
                        continue
                    ok = self._update_trade_sl(tid, new_sl, decimals)
                    if ok:
                        send_telegram_message(
                            f"🎯 {action} on {pair} #{tid} | Price: {current_price} | New SL: {round(new_sl, decimals)} | Profit: {profit_pips:.1f} pips"
                        )


# ============================================================================
# STRENGTH-BASED CLOSE OVERRIDE
# ============================================================================
STRENGTH_CLOSE_THRESHOLD = cfg("STRENGTH_CLOSE_THRESHOLD", 1.0)


def should_close_by_strength(pair: str, side: str, strength_scores: dict) -> tuple:
    """
    Return (should_close: bool, reason: str) if position fights currency strength.

    For BASE/QUOTE pair:
    - LONG  = bullish BASE, bearish QUOTE
    - SHORT = bearish BASE, bullish QUOTE

    Close if strength gap contradicts position by > threshold.
    """
    # Extract base and quote from pair like "EURUSD=X" or "EUR_JPY"
    clean = pair.replace("=X", "").replace("_", "")
    # Map to 3-letter codes
    if len(clean) == 6:
        base, quote = clean[:3], clean[3:]
    elif "JPY" in pair and len(clean) == 6:
        base, quote = clean[:3], clean[3:]
    else:
        # Fallback: try to infer from OANDA symbol
        parts = pair.replace("=X", "").split("_")
        if len(parts) == 2:
            base, quote = parts[0], parts[1]
        else:
            return False, ""

    base_score = strength_scores.get(base, 0)
    quote_score = strength_scores.get(quote, 0)
    gap = base_score - quote_score

    if side == "long":
        # We want base stronger than quote. If quote is stronger by threshold, close.
        if -gap > STRENGTH_CLOSE_THRESHOLD:
            return True, f"Strength flip: {quote} (+{quote_score:.2f}) now stronger than {base} ({base_score:.2f}), gap={-gap:.2f}"
    else:
        # We want base weaker than quote. If base is stronger by threshold, close.
        if gap > STRENGTH_CLOSE_THRESHOLD:
            return True, f"Strength flip: {base} (+{base_score:.2f}) now stronger than {quote} ({quote_score:.2f}), gap={gap:.2f}"

    return False, ""


# ============================================================================
# LEGACY MC LOADER
# ============================================================================
def load_mc_legacy(pair):
    safe = pair.replace("=X", "").replace("=", "_")
    candidates = [
        RESULTS_DIR / f"fx_daily_{safe}_{TODAY_STR}.json",
        RESULTS_DIR / f"daily_mc_{safe}_{TODAY_STR}.json",
        RESULTS_DIR / f"h4_mc_{safe}_{TODAY_STR}.json",
    ]
    for f in candidates:
        if f.exists():
            age = (datetime.now(timezone.utc) - datetime.fromtimestamp(f.stat().st_mtime, timezone.utc)).total_seconds() / 3600
            if age <= MC_MAX_AGE_HOURS:
                with open(f) as j:
                    return json.load(j), True
    return None, False


# ============================================================================
# TELEGRAM REPORT BUILDERS
# ============================================================================
def build_mc_telegram(mc_results: list) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"📊 **{MC_REPORT_TITLE}**",
        f"📅 Generated: {now}",
        f"🔹 TF: {MC_TF} | Lookback: {MC_LOOKBACK} | Forecast: {MC_FORECAST} | Sims: {SIMULATIONS}",
        ""
    ]
    for r in mc_results:
        dec = 3 if "JPY" in r["pair"] else 5
        lo, hi = r["range_90"]
        lines.extend([
            f"🔹 **{r['pair']}**",
            f"   💵 Last Close: `{r['current_price']}`",
            f"   📊 Percentile: `{r['percentile_rank']}%`",
            f"   🎯 UP: `{r['p_up_pct']}%` | DOWN: `{r['p_down_pct']}%`",
            f"   📏 90% Band: `{lo}` – `{hi}`",
            f"   🔍 Touch: Low `{r['touch_lower_pct']}%` | High `{r['touch_upper_pct']}%`",
            f"   {r['regime']}",
            ""
        ])
    return "\n".join(lines)


def build_trade_telegram(trade_lines: list, mc_summary: list = None) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"🤖 MULTI‑PAIR UPDATE — {now}"]
    lines.extend(trade_lines)
    if mc_summary:
        lines.append("")
        lines.append("📊 *MC Context:*")
        for s in mc_summary:
            lines.append(f"   {s}")
    return "\n".join(lines)


# ============================================================================
# MAIN
# ============================================================================
def main():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    logger.info(f"\n🤖 RUN — {now} | MODE={MODE} | MODEL=XGBoost | DATA=OANDA | MC={MC_TF}")

    if forex_market_closed():
        logger.info("Market closed — skipping")
        send_telegram_message("⏸️ FX BOT: Market closed")
        return

    ensure_model()

    logger.info("[STRATEGY] Step 1 — Currency Strength...")
    strength_scores = build_strength_matrix()
    logger.info(format_strength_ranking(strength_scores))

    pair_data = {}
    for pair in DEFAULT_PAIRS:
        oanda = YAHOO_TO_OANDA[pair]
        try:
            raw = fetcher.fetch(pair, oanda, count=200)
            if raw.empty:
                logger.warning(f"{pair}: empty raw data from OANDA")
                continue
            df = feat_engine.build(raw)
            if df.empty:
                logger.warning(f"{pair}: empty after feature build")
                continue
            if len(df) < 5:
                logger.warning(f"{pair}: only {len(df)} rows after build")
                continue
            pair_data[pair] = {"df": df, "oanda": oanda, "raw": raw}
            atr_val = df.iloc[-1].get("atr", "N/A")
            logger.info(f"📊 {pair}: {len(df)} bars, ATR={atr_val}")
        except Exception as e:
            logger.error(f"Failed to fetch/build {pair}: {e}")
            continue

    if not pair_data:
        logger.error("No pairs have usable data. Aborting run.")
        send_telegram_message("❌ FX BOT: No usable pair data")
        return

    # ------------------------------------------------------------------
    # 2) MONTE CARLO GENERATION
    # ------------------------------------------------------------------
    mc_cache = {}
    mc_results = []

    if not args.skip_mc:
        logger.info("[MONTE CARLO] Generating forecasts...")
        mc_gen = MCGenerator(simulations=SIMULATIONS, confidence=CONFIDENCE)
        for pair in DEFAULT_PAIRS:
            oanda = YAHOO_TO_OANDA[pair]
            raw_df = pair_data.get(pair, {}).get("raw")
            mc_data, ok = mc_gen.run_for_pair(pair, oanda, df=raw_df)
            if ok:
                mc_cache[pair] = mc_data
                mc_results.append(mc_data)
                mc_gen.save(mc_data)
                logger.info(
                    f"🎲 MC {pair}: {mc_data['regime']} | "
                    f"90% [{mc_data['range_90'][0]}, {mc_data['range_90'][1]}] | "
                    f"P_up={mc_data['p_up']}%"
                )
            else:
                logger.warning(f"⚠️ MC failed for {pair}")
        if mc_results:
            send_telegram_message(build_mc_telegram(mc_results))
    else:
        logger.info("[MONTE CARLO] Skipped generation (--skip-mc), using legacy files...")
        for pair in DEFAULT_PAIRS:
            mc_data, ok = load_mc_legacy(pair)
            if ok:
                mc_cache[pair] = mc_data

    # ------------------------------------------------------------------
    # 3) CLOSE CHECK — Model reversal + Strength override
    # ------------------------------------------------------------------
    for pair in DEFAULT_PAIRS:
        if pair not in pair_data:
            continue
        oanda = pair_data[pair]["oanda"]
        pos = get_open_position(oanda)
        if not pos:
            continue

        df = pair_data[pair]["df"]
        if len(df) < 5:
            continue

        # A) Model-based close
        should_close, reason = strat_engine.should_close(pos["units"], df.iloc[-1])
        if should_close:
            logger.info(f"🔄 CLOSE {pair}: {reason}")
            close_position(oanda)
            last_closed[pair] = (
                Direction.LONG if pos["units"] > 0 else Direction.SHORT,
                REOPEN_DELAY_RUNS,
            )
            continue

        # B) Strength-based close override
        sc, sc_reason = should_close_by_strength(pair, pos["side"], strength_scores)
        if sc:
            logger.info(f"🔄 STRENGTH CLOSE {pair}: {sc_reason}")
            close_position(oanda)
            last_closed[pair] = (
                Direction.LONG if pos["units"] > 0 else Direction.SHORT,
                REOPEN_DELAY_RUNS,
            )
            continue

    save_cooldown(last_closed)

    # ------------------------------------------------------------------
    # 4) MC-ONLY EARLY EXIT
    # ------------------------------------------------------------------
    if args.mc_only:
        logger.info("--mc-only set: skipping trade signal generation.")
        return

    # ------------------------------------------------------------------
    # 5) DYNAMIC EXIT MANAGEMENT
    # ------------------------------------------------------------------
    logger.info("[DYNAMIC MANAGER] Scanning open positions...")
    dyn_mgr = DynamicPositionManager(
        api=api,
        account_id=OANDA_ACCOUNT_ID,
        be_trigger_atr_mult=cfg("BE_TRIGGER_ATR_MULT", 1.5),
        trail_trigger_atr_mult=cfg("TRAIL_TRIGGER_ATR_MULT", 2.5),
        trail_atr_mult=cfg("TRAIL_ATR_MULT", 1.5),
        max_hold_bars=cfg("MAX_HOLD_BARS", 12),
    )
    dyn_mgr.update_all(pair_data)

    # ------------------------------------------------------------------
    # 6) GENERATE SIGNALS
    # ------------------------------------------------------------------
    candidates = []
    equity = get_account_equity()

    for pair in DEFAULT_PAIRS:
        oanda = YAHOO_TO_OANDA[pair]

        if pair in last_closed and not args.test_trade:
            dir_closed, runs_left = last_closed[pair]
            if runs_left > 0:
                last_closed[pair] = (dir_closed, runs_left - 1)
                logger.info(f"⏳ COOLDOWN: {pair} — {runs_left - 1} runs remaining")
                continue
            else:
                del last_closed[pair]

        if get_open_position(oanda) and not args.test_trade:
            logger.info(f"⏭️ {pair}: position open — skip")
            continue

        if pair not in pair_data:
            logger.info(f"⏭️ {pair}: no data — skip")
            continue

        df = pair_data[pair]["df"]
        if len(df) < 5:
            logger.info(f"⏭️ {pair}: insufficient bars ({len(df)})")
            continue

        try:
            tick = api.request(
                InstrumentsCandles(
                    instrument=oanda,
                    params={"count": 1, "granularity": "M1", "price": "BA"},
                )
            )["candles"][0]
            current = float(tick["mid"]["c"])
            spread_pips = abs(float(tick["ask"]["c"]) - float(tick["bid"]["c"])) / (
                0.01 if "JPY" in pair else 0.0001
            )
        except Exception as e:
            logger.warning(f"Tick fetch failed for {pair}: {e}, using last close")
            current = df.iloc[-1]["Close"]
            spread_pips = 1.0

        mc_data = mc_cache.get(pair)
        if mc_data is None:
            logger.info(f"⚠️ MC missing/stale for {pair}")

        # ── STRENGTH PRE-FILTER ──
        # Block signals that fight currency strength trend
        clean = pair.replace("=X", "").replace("_", "")
        if len(clean) == 6:
            base, quote = clean[:3], clean[3:]
        else:
            parts = pair.replace("=X", "").split("_")
            base, quote = parts[0], parts[1] if len(parts) == 2 else ("", "")
        base_score = strength_scores.get(base, 0)
        quote_score = strength_scores.get(quote, 0)
        gap = base_score - quote_score
        strength_threshold = cfg("STRENGTH_SIGNAL_BLOCK_THRESHOLD", 1.0)

        # For SELL: we sell base (want it weak) and buy quote (want it strong)
        # If base is stronger than quote by threshold, SELL is wrong
        # For BUY: we buy base (want it strong) and sell quote (want it weak)
        # If quote is stronger than base by threshold, BUY is wrong
        # We don't know direction yet, so we check both and block if either is violated
        # Actually we need to check after signal direction is known... 
        # Better: let the model generate, then veto if it fights strength

        sig = strat_engine.generate_signal(
            pair=pair,
            oanda_symbol=oanda,
            df=df,
            mc_data=mc_data,
            strength_scores=strength_scores,
            current_price=current,
            spread_pips=spread_pips,
        )

        if not sig:
            logger.info(f"➖ {pair}: no signal")
            continue

        # Post-signal strength veto
        if not args.test_trade:
            if sig.action == "SELL" and gap > strength_threshold:
                logger.info(f"🚫 {pair}: SELL blocked — {base} (+{base_score:.2f}) stronger than {quote} ({quote_score:.2f}), gap={gap:.2f}")
                continue
            if sig.action == "BUY" and -gap > strength_threshold:
                logger.info(f"🚫 {pair}: BUY blocked — {quote} (+{quote_score:.2f}) stronger than {base} ({base_score:.2f}), gap={-gap:.2f}")
                continue
        else:
            logger.info(f"⚠️ TEST MODE: bypassing strength veto for {pair}")

        atr_val = df.iloc[-1].get("atr")
        if atr_val and not np.isnan(atr_val):
            # ── ATR floor guard ──
            is_jpy = "JPY" in pair
            pip_size = 0.01 if is_jpy else 0.0001
            min_sl_pips = cfg("MIN_SL_PIPS_JPY", 15) if is_jpy else cfg("MIN_SL_PIPS", 10)
            min_sl_distance = min_sl_pips * pip_size
            effective_atr = max(atr_val, min_sl_distance / FEAT_CFG.atr_sl_mult)

            atr_sl, atr_tp = atr_mod.sl_tp_from_atr(
                entry=current,
                direction=sig.action,
                atr_value=effective_atr,
                is_jpy=is_jpy,
                sl_mult=FEAT_CFG.atr_sl_mult,
                tp_mult=FEAT_CFG.atr_tp_mult,
            )
            if atr_sl and atr_tp:
                sig.stop_loss = atr_sl
                sig.take_profit = atr_tp
                sig.filter_notes.append(f"ATR SL/TP: mult={FEAT_CFG.atr_sl_mult}/{FEAT_CFG.atr_tp_mult}, floor={min_sl_pips}pips")

        units = DEFAULT_LOT_SIZE
        if not USE_DEFAULT_LOT_SIZE:
            units = atr_mod.position_size(
                equity=equity,
                risk_pct=FEAT_CFG.risk_per_trade_pct,
                entry=current,
                sl=sig.stop_loss,
                pair=pair,
                atr_value=atr_val or 0.0005,
            )

        candidates.append(sig)
        logger.info(
            f"📈 SIGNAL {pair} | {sig.action} | Score={sig.conviction_score} "
            f"| Prob={sig.raw_prob:.1%} | SL={sig.stop_loss} | RefTP={sig.take_profit} | Units={units}"
        )
        logger.info(f"   Breakdown: {sig.score_breakdown}")
        if sig.filter_notes:
            logger.info(f"   Notes: {sig.filter_notes}")

    save_cooldown(last_closed)

    # ------------------------------------------------------------------
    # 7) SELECT & EXECUTE
    # ------------------------------------------------------------------
    if args.test_trade:
        logger.info("⚠️ TEST MODE: selecting all candidates with prob > 51%")
        winners = [c for c in candidates if c.raw_prob > 0.51 or c.raw_prob < 0.49]
    else:
        winners = strat_engine.select_signals(candidates)

    trade_lines = []
    if not winners:
        trade_lines.append("➡️ No high‑probability setups found")
        logger.info("No winners selected")
    else:
        for w in winners:
            units = DEFAULT_LOT_SIZE
            if not USE_DEFAULT_LOT_SIZE:
                units = atr_mod.position_size(
                    equity=get_account_equity(),
                    risk_pct=FEAT_CFG.risk_per_trade_pct,
                    entry=w.entry_price,
                    sl=w.stop_loss,
                    pair=w.pair,
                    atr_value=w.mc_data.get("atr", 0.0005) if w.mc_data else 0.0005,
                )
            res = open_oanda_order(
                {"pair": w.oanda_symbol, "action": w.action,
                 "stop_loss": w.stop_loss, "take_profit": w.take_profit},
                units=units,
                current_price=w.entry_price,
            )
            logger.info(f"📤 Order result for {w.pair}: {res}")
            if res.get("status") == "OK":
                trade_lines.append(
                    f"✅ {w.pair} | {w.action} | Score={w.conviction_score} | "
                    f"Prob={w.raw_prob:.1%} | SL={w.stop_loss} | RefTP={w.take_profit} | Units={units}"
                )
            else:
                trade_lines.append(f"❌ {w.pair} | ORDER FAILED: {res.get('message')}")

    mc_summary = []
    for pair in DEFAULT_PAIRS:
        if pair in mc_cache:
            r = mc_cache[pair]
            mc_summary.append(
                f"{r['pair']}: {r['regime']} (P_up={r['p_up']}%, 90%={r['range_90'][0]}-{r['range_90'][1]})"
            )

    msg = build_trade_telegram(trade_lines, mc_summary)
    logger.info(msg)
    send_telegram_message(msg)
    logger.info("✅ Run complete")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.exception("Fatal error in main loop")
        send_telegram_message(f"❌ FX BOT FATAL ERROR: {e}")
        raise