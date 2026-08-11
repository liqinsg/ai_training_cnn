# fx_trade_bot_integrated.py — v3.0 Defensive
# Strategy: strategy_decision.py | Data: data_pipeline.py

import sys
import json
import logging
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

import numpy as np
import pandas as pd

from utils.trading_core import get_candles as get_oanda_candles
from utils.calculate_currency_strength import calculate_currency_strength
from utils.strategy_helpers import build_strength_matrix, format_strength_ranking
from telegram_message import send_telegram_message
import config
from config_oanda import OANDA_API_TOKEN, OANDA_ACCOUNT_ID, OANDA_ENV
import oandapyV20

from oandapyV20.endpoints.instruments import InstrumentsCandles
from oandapyV20.endpoints.positions import PositionDetails
from oandapyV20.endpoints.orders import OrderCreate

from strategy_decision import StrategyConfig, StrategyEngine, FilterMode, Direction
from data_pipeline import FeatureConfig, FeatureEngine, ModelWrapper, DataFetcher, ATRModule

api = oandapyV20.API(access_token=OANDA_API_TOKEN, environment=OANDA_ENV)


def cfg(name, default):
    return getattr(config, name, default)


MODE = cfg("MODE", "LEVEL10")
USE_OANDA_DATA = True
TIMEFRAME = cfg("TIMEFRAME", "15m")
OANDA_GRANULARITY_MAP = {
    "1m": "M1", "5m": "M5", "15m": "M15",
    "30m": "M30", "1h": "H1", "4h": "H4", "1d": "D",
}
OANDA_GRANULARITY = OANDA_GRANULARITY_MAP.get(TIMEFRAME, "M15")
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

REOPEN_DELAY_RUNS = 2
last_closed: dict = {}
COOLDOWN_FILE = BASE_DIR / "cooldown_state.json"

RESULTS_DIR = BASE_DIR / "daily_results"
RESULTS_DIR.mkdir(exist_ok=True)
TODAY_STR = datetime.now(timezone.utc).strftime("%Y%m%d")
MC_MAX_AGE_HOURS = cfg("MC_MAX_AGE_HOURS", 24)

# ---------------------------------------------------------------------------
# INIT PIPELINE
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# COOLDOWN
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# MARKET STATUS
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# POSITION HELPERS
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# ORDER
# ---------------------------------------------------------------------------
def open_oanda_order(signal: dict, units: int) -> dict:
    if not OANDA_ACCOUNT_ID or not OANDA_API_TOKEN:
        return {"status": "ERROR", "message": "Missing OANDA credentials"}
    pair_raw = signal.get("pair")
    action = signal.get("action")
    if action not in {"BUY", "SELL"}:
        return {"status": "ERROR", "message": f"Invalid action: {action}"}
    units = int(units) if action == "BUY" else -int(units)
    sl = signal.get("stop_loss")
    tp = signal.get("take_profit")
    if sl is None or tp is None:
        return {"status": "ERROR", "message": "SL/TP missing"}
    is_jpy = "JPY" in pair_raw
    decimals = 3 if is_jpy else 5
    order_payload = {
        "order": {
            "type": "MARKET",
            "instrument": pair_raw,
            "units": str(units),
            "timeInForce": "FOK",
            "positionFill": "DEFAULT",
            "stopLossOnFill": {
                "price": str(round(float(sl), decimals)),
                "timeInForce": "GTC",
            },
            "takeProfitOnFill": {
                "price": str(round(float(tp), decimals)),
                "timeInForce": "GTC",
            },
        }
    }
    try:
        resp = api.request(OrderCreate(accountID=OANDA_ACCOUNT_ID, data=order_payload))
        logger.info(f"OANDA accepted order for {pair_raw}")
        return {"status": "OK", "response": resp}
    except Exception as e:
        logger.error(f"OANDA order failed for {pair_raw}: {e}")
        return {"status": "ERROR", "message": str(e)}


# ---------------------------------------------------------------------------
# MC LOADER
# ---------------------------------------------------------------------------
def load_mc(pair):
    safe = pair.replace("=X", "").replace("=", "_")
    f = RESULTS_DIR / f"fx_daily_{safe}_{TODAY_STR}.json"
    if not f.exists():
        return None, False
    age = (datetime.now(timezone.utc) - datetime.fromtimestamp(f.stat().st_mtime, timezone.utc)).total_seconds() / 3600
    if age > MC_MAX_AGE_HOURS:
        return None, False
    with open(f) as j:
        return json.load(j), True


# ---------------------------------------------------------------------------
# EQUITY
# ---------------------------------------------------------------------------
def get_account_equity() -> float:
    try:
        from oandapyV20.endpoints.accounts import AccountDetails
        resp = api.request(AccountDetails(accountID=OANDA_ACCOUNT_ID))
        return float(resp["account"]["balance"])
    except Exception as e:
        logger.warning(f"Could not fetch equity: {e}, using fallback 10000")
        return 10000.0


# ---------------------------------------------------------------------------
# MODEL
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    logger.info(f"\n🤖 RUN — {now} | MODE={MODE} | MODEL=XGBoost | DATA=OANDA")

    if forex_market_closed():
        logger.info("Market closed — skipping")
        send_telegram_message("⏸️ FX BOT: Market closed")
        return

    ensure_model()

    logger.info("[STRATEGY] Step 1 — Currency Strength...")
    strength_scores = build_strength_matrix()
    logger.info(format_strength_ranking(strength_scores))

    # Fetch & build features for all pairs
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
            pair_data[pair] = {"df": df, "oanda": oanda}
            atr_val = df.iloc[-1].get("atr", "N/A")
            logger.info(f"📊 {pair}: {len(df)} bars, ATR={atr_val}")
        except Exception as e:
            logger.error(f"Failed to fetch/build {pair}: {e}")
            continue

    if not pair_data:
        logger.error("No pairs have usable data. Aborting run.")
        send_telegram_message("❌ FX BOT: No usable pair data")
        return

    # ==========================================
    # 1. CLOSE CHECK
    # ==========================================
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

        should_close, reason = strat_engine.should_close(pos["units"], df.iloc[-1])
        if should_close:
            logger.info(f"🔄 CLOSE {pair}: {reason}")
            close_position(oanda)
            last_closed[pair] = (
                Direction.LONG if pos["units"] > 0 else Direction.SHORT,
                REOPEN_DELAY_RUNS,
            )

    save_cooldown(last_closed)

    # ==========================================
    # 2. GENERATE SIGNALS
    # ==========================================
    candidates = []
    equity = get_account_equity()

    for pair in DEFAULT_PAIRS:
        oanda = YAHOO_TO_OANDA[pair]

        # Cooldown
        if pair in last_closed:
            dir_closed, runs_left = last_closed[pair]
            if runs_left > 0:
                last_closed[pair] = (dir_closed, runs_left - 1)
                logger.info(f"⏳ COOLDOWN: {pair} — {runs_left - 1} runs remaining")
                continue
            else:
                del last_closed[pair]

        if get_open_position(oanda):
            logger.info(f"⏭️ {pair}: position open — skip")
            continue

        if pair not in pair_data:
            logger.info(f"⏭️ {pair}: no data — skip")
            continue

        df = pair_data[pair]["df"]
        if len(df) < 5:
            logger.info(f"⏭️ {pair}: insufficient bars ({len(df)})")
            continue

        # Current price & spread
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

        mc_data, mc_ok = load_mc(pair)
        if not mc_ok:
            logger.info(f"⚠️ MC missing/stale for {pair}")

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

        # ATR-based SL/TP override
        atr_val = df.iloc[-1].get("atr")
        if atr_val and not np.isnan(atr_val):
            atr_sl, atr_tp = atr_mod.sl_tp_from_atr(
                entry=current,
                direction=sig.action,
                atr_value=atr_val,
                is_jpy="JPY" in pair,
                sl_mult=FEAT_CFG.atr_sl_mult,
                tp_mult=FEAT_CFG.atr_tp_mult,
            )
            if atr_sl and atr_tp:
                sig.stop_loss = atr_sl
                sig.take_profit = atr_tp
                sig.filter_notes.append(f"ATR SL/TP: mult={FEAT_CFG.atr_sl_mult}/{FEAT_CFG.atr_tp_mult}")

        # Position sizing
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
            f"| Prob={sig.raw_prob:.1%} | SL={sig.stop_loss} | TP={sig.take_profit} | Units={units}"
        )
        logger.info(f"   Breakdown: {sig.score_breakdown}")
        if sig.filter_notes:
            logger.info(f"   Notes: {sig.filter_notes}")

    save_cooldown(last_closed)

    # ==========================================
    # 3. SELECT & EXECUTE
    # ==========================================
    winners = strat_engine.select_signals(candidates)

    lines = [f"🤖 MULTI‑PAIR UPDATE — {now}"]
    if not winners:
        lines.append("➡️ No high‑probability setups found")
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
            )
            logger.info(f"📤 Order result for {w.pair}: {res}")
            if res.get("status") == "OK":
                lines.append(
                    f"✅ {w.pair} | {w.action} | Score={w.conviction_score} | "
                    f"Prob={w.raw_prob:.1%} | SL={w.stop_loss} | TP={w.take_profit} | Units={units}"
                )
            else:
                lines.append(f"❌ {w.pair} | ORDER FAILED: {res.get('message')}")

    msg = "\n".join(lines)
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