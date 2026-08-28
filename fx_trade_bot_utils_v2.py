# fx_trade_bot_utils.py — Shared Helpers + Dynamic TP + Position Manager
# From v6.x: Cooldown, Market Check, Position Helpers, Order Helpers,
#            Telegram Builders, Strength Close, MC Loader, Dynamic TP,
#            H4-based SL calc, DynamicPositionManager (Breakeven + Trailing + TP)

import json
from pathlib import Path
from datetime import datetime, timezone
# from enum import Enum
import numpy as np
import pandas as pd
from dataclasses import dataclass
from telegram_message import send_telegram_message
from oandapyV20.endpoints.instruments import InstrumentsCandles
from oandapyV20.endpoints.positions import PositionDetails
from oandapyV20.endpoints.orders import OrderCreate
from oandapyV20.endpoints.trades import OpenTrades, TradeCRCDO
import logging
logger = logging.getLogger(__name__)

# from utils.logger_config import get_logger
# logger = get_logger(__name__)

# =============================================================================
# 🛡️ STOP-LOSS RULES — H4-based — LOCKED v6.x+
# SELL → SL = max(4 closed H4 highs) + 20 pips
# BUY  → SL = min(4 closed H4 lows) - 20 pips
# MAX  → >200 pips → ABORT TRADE
# =============================================================================
SL_OFFSET_PIPS       = 20
SL_MAX_ALLOWED_PIPS  = 200
REQUIRED_H4_CANDLES  = 4

def calculate_stop_loss(side: str, entry_price: float, h4_candles, pip_size: float) -> tuple[float, float, bool]:
    """
    Calculate Stop-Loss per H4 Zone Hierarchy + Max SL Cap.
    ⚠️ h4_candles MUST be ONLY fully closed candles — exclude forming candle.
    Returns: (sl_price, sl_pips, skip_trade)
    """
    if len(h4_candles) < REQUIRED_H4_CANDLES:
        raise ValueError(
            f"⚠️ H4 candle count insufficient: need ≥{REQUIRED_H4_CANDLES}, got {len(h4_candles)} — "
            "Did you forget h4_data[:-1]?"
        )

    if side.upper() == "SELL":
        ref_level = max(c["high"] for c in h4_candles)
        sl_price  = ref_level + (SL_OFFSET_PIPS * pip_size)
        sl_pips   = (sl_price - entry_price) / pip_size
    elif side.upper() == "BUY":
        ref_level = min(c["low"] for c in h4_candles)
        sl_price  = ref_level - (SL_OFFSET_PIPS * pip_size)
        sl_pips   = (entry_price - sl_price) / pip_size
    else:
        raise ValueError(f"Invalid side: '{side}' — use BUY or SELL")

    if sl_pips > SL_MAX_ALLOWED_PIPS:
        skip_trade = True
        logger.warning(
            f"🚫 SL TOO LARGE — TRADE ABORTED | Side: {side} | Ref: {ref_level:.5f} | "
            f"Entry: {entry_price:.5f} | SL: {sl_price:.5f} | "
            f"Distance: {sl_pips:.1f} pips | MAX: {SL_MAX_ALLOWED_PIPS}"
        )
    else:
        skip_trade = False
        logger.info(
            f"✅ SL ACCEPTED | Side: {side} | Ref: {ref_level:.5f} | "
            f"Entry: {entry_price:.5f} | SL: {sl_price:.5f} | Distance: {sl_pips:.1f} pips"
        )
    return sl_price, sl_pips, skip_trade

# =============================================================================
# CANDLE FETCHER
# =============================================================================
def fetch_candles(api, oanda_instrument: str, gran: str, count: int = 100):
    """Fetch OHLC → clean DataFrame indexed by Time."""
    resp = api.request(
        InstrumentsCandles(instrument=oanda_instrument,
                           params={"granularity": gran, "count": count, "price": "M"})
    )
    return pd.DataFrame([
        {"Time": c["time"], "Open": float(c["mid"]["o"]),
         "High": float(c["mid"]["h"]), "Low": float(c["mid"]["l"]),
         "Close": float(c["mid"]["c"])}
        for c in resp["candles"]
    ]).set_index("Time")

# =============================================================================
# CONFIG HELPERS
# =============================================================================
def price_decimals(pair: str) -> int:
    return 3 if "JPY" in pair.upper() else 5

def pip_size(pair: str) -> float:
    return 0.01 if "JPY" in pair.upper() else 0.0001

# =============================================================================
# COOLDOWN
# =============================================================================
def load_cooldown(cooldown_file: Path, Direction):
    if cooldown_file.exists():
        with open(cooldown_file) as f:
            raw = json.load(f)
        return {k: (Direction(v[0]), v[1]) for k, v in raw.items()}
    return {}

def save_cooldown(cooldown_file: Path, state: dict):
    serializable = {k: (v[0].value, v[1]) for k, v in state.items()}
    with open(cooldown_file, "w") as f:
        json.dump(serializable, f)

# =============================================================================
# MARKET CHECK
# =============================================================================
def forex_market_closed(api, oanda_account_id: str, oanda_granularity: str) -> bool:
    try:
        resp = api.request(InstrumentsCandles(
            instrument="EUR_USD", params={"count": 1, "granularity": oanda_granularity}
        ))
        return len(resp.get("candles", [])) == 0
    except Exception as e:
        logger.error(f"Market check failed: {e}")
        return True

# =============================================================================
# ✅ POSITION QUERY — CLEANED (kept best version)
# =============================================================================
def get_open_position(api, oanda_account_id: str, instrument: str):
    """Return dict {"units": int, "side": "long"/"short"} or None if none."""
    try:
        resp = api.request(PositionDetails(accountID=oanda_account_id, instrument=instrument))
        pos = resp.get("position", {})
        long_units = pos.get("long", {}).get("units", "0")
        short_units = pos.get("short", {}).get("units", "0")
        if long_units != "0":
            return {"units": int(long_units), "side": "long"}
        if short_units != "0":
            return {"units": -int(short_units), "side": "short"}
        return None
    except Exception as e:
        err = str(e)
        if "NO_SUCH_POSITION" in err or "404" in err:
            logger.info(f"✅ {instrument}: No open position")
            return None
        logger.warning(f"⚠️ Position check failed for {instrument}: {err[:120]}")
        return None

# =============================================================================
# ✅ TP UPDATE — kept the correct TradeCRCDO version
# =============================================================================
def update_order_tp(
    api, account_id, trade_id, instrument, new_tp_price,
    token=None, environment="practice", send_telegram=None
):
    """Update TP on an OPEN TRADE via TradeCRCDO (OANDA API-correct method)."""
    try:
        dec = price_decimals(instrument)
        new_tp_str = f"{float(new_tp_price):.{dec}f}"
        data = {"takeProfit": {"price": new_tp_str, "timeInForce": "GTC"}}
        resp = api.request(TradeCRCDO(accountID=account_id, tradeID=trade_id, data=data))
        if "takeProfitOrderTransaction" in resp:
            txid = resp["takeProfitOrderTransaction"]["id"]
            msg = f"✅ TP UPDATED {instrument} → {new_tp_str} (TxID: {txid})"
            logger.info(msg)
            if send_telegram: send_telegram_message(msg)
            return {"ok": True, "status": "UPDATED", "new_tp": new_tp_price, "txid": txid}
        logger.warning(f"⚠️ Unexpected TP resp: {resp}")
        return {"ok": False, "status": "UNEXPECTED", "response": resp}
    except Exception as e:
        err = f"❌ TP UPDATE FAILED {instrument}: {type(e).__name__}: {e}"
        logger.error(err)
        if send_telegram: send_telegram_message(err)
        return {"ok": False, "status": "ERROR", "error": str(e)}

# =============================================================================
# CLOSE POSITION
# =============================================================================
def close_position(api, oanda_account_id: str, instrument: str, telegram_send=None):
    try:
        pos = api.request(PositionDetails(accountID=oanda_account_id, instrument=instrument)).get("position", {})
        if pos.get("long", {}).get("units", "0") != "0":
            units = -int(pos["long"]["units"])
        elif pos.get("short", {}).get("units", "0") != "0":
            units = abs(int(pos["short"]["units"]))
        else:
            logger.info(f"No position to close: {instrument}")
            return
        api.request(OrderCreate(accountID=oanda_account_id, data={
            "order": {"type": "MARKET", "instrument": instrument,
                      "units": str(units), "positionFill": "REDUCE_ONLY"}
        }))
        logger.info(f"Closed {instrument}")
        if telegram_send: telegram_send(f"🔄 AUTO‑CLOSE: {instrument}")
    except Exception as e:
        logger.error(f"Close failed for {instrument}: {e}")

# =============================================================================
# ORDER HELPERS
# =============================================================================
def open_oanda_order_simple(
    api, oanda_account_id: str, instrument: str, direction: str,
    units: int, sl_price: float, tp_price: float
) -> dict:
    dec = price_decimals(instrument)
    order_payload = {"order": {
        "type": "MARKET", "instrument": instrument,
        "units": str(abs(units) if direction == "BUY" else -abs(units)),
        "positionFill": "DEFAULT"
    }}
    try:
        resp = api.request(OrderCreate(accountID=oanda_account_id, data=order_payload))
        logger.info(f"✅ OANDA accepted order for {instrument}")
        trade_id = ""
        if "orderFillTransaction" in resp:
            trade_id = str(resp["orderFillTransaction"].get("tradeOpened", {}).get("tradeID", ""))
            logger.info(f"📦 Trade opened: TradeID={trade_id}")
        elif "orderCreateTransaction" in resp:
            trade_id = str(resp["orderCreateTransaction"].get("id", ""))
            logger.info(f"📦 Order created: OrderID={trade_id}")
        if not trade_id:
            return {"status": "ERROR", "message": "TradeID missing"}
        if sl_price:
            api.request(OrderCreate(accountID=oanda_account_id, data={
                "order": {"type": "STOP_LOSS", "tradeID": trade_id,
                          "price": f"{float(sl_price):.{dec}f}", "timeInForce": "GTC"}
            }))
            logger.info(f"   ✅ SL: {sl_price}")
        if tp_price:
            api.request(OrderCreate(accountID=oanda_account_id, data={
                "order": {"type": "TAKE_PROFIT", "tradeID": trade_id,
                          "price": f"{tp_price:.{dec}f}", "timeInForce": "GTC"}
            }))
            logger.info(f"   ✅ TP: {tp_price}")
        return {"status": "OK", "trade_id": trade_id, "response": resp}
    except Exception as e:
        logger.error(f"❌ FAILED {instrument}: {type(e).__name__}: {e}")
        return {"status": "ERROR", "message": str(e)}

def open_oanda_order(
    signal: dict, units: int, current_price: float,
    api, oanda_account_id: str, oanda_token: str,
    trailing_tp: bool = False, dynamic_tp: bool = False,
    max_sl_pips: int = None, max_sl_pct: float = 0.03,
    telegram_send=None, cfg=None
) -> dict:
    if not oanda_account_id or not oanda_token:
        return {"status": "ERROR", "message": "Missing credentials"}
    pair_raw, action, sl, tp = signal.get("pair"), signal.get("action"), signal.get("stop_loss"), signal.get("take_profit")
    if action not in {"BUY", "SELL"}: return {"status": "ERROR", "message": f"Invalid action: {action}"}
    if sl is None: return {"status": "ERROR", "message": "SL missing"}
    if current_price is None:
        logger.error(f"❌ Cannot open {pair_raw}: entry price required")
        return {"status": "ERROR", "message": "Entry price missing"}

    entry, dec, pip = current_price, price_decimals(pair_raw), pip_size(pair_raw)
    is_jpy = "JPY" in pair_raw.upper()
    if max_sl_pips is None: max_sl_pips = 500 if is_jpy else 50
    sl_pips, sl_pct = abs(entry - sl)/pip, abs(entry - sl)/entry

    if sl_pips > max_sl_pips or sl_pct > max_sl_pct:
        err = f"SL GUARD BLOCKED {pair_raw}: SL={sl} is {sl_pips:.0f}p / {sl_pct:.1%}. Max: {max_sl_pips}p / {max_sl_pct:.1%}"
        logger.error(err)
        if telegram_send: telegram_send(f"🛡️ {err}")
        return {"status": "ERROR", "message": err}
    if (action == "BUY" and sl >= entry) or (action == "SELL" and sl <= entry):
        err = f"SL GUARD BLOCKED {pair_raw}: SL on wrong side of entry"
        logger.error(err)
        return {"status": "ERROR", "message": err}

    order_payload = {"order": {"type": "MARKET", "instrument": pair_raw,
        "units": str(units if action == "BUY" else -units), "positionFill": "DEFAULT"}}
    try:
        resp = api.request(OrderCreate(accountID=oanda_account_id, data=order_payload))
        logger.info(f"✅ OANDA accepted order for {pair_raw}")
        trade_id, entry_price = "", current_price
        if "orderFillTransaction" in resp:
            trade_id = str(resp["orderFillTransaction"].get("id", ""))
            entry_price = float(resp["orderFillTransaction"].get("price", current_price))
            logger.info(f"📦 Trade opened: TradeID={trade_id} @ {entry_price}")
        elif "orderCreateTransaction" in resp:
            trade_id = str(resp["orderCreateTransaction"].get("id", ""))
            logger.info(f"📦 Order created: OrderID={trade_id}")
        if not trade_id:
            logger.warning(f"⚠️ TradeID missing! Keys: {list(resp.keys())}")
        else:
            if sl is not None:
                try:
                    api.request(OrderCreate(accountID=oanda_account_id, data={
                        "order": {"type": "STOP_LOSS", "tradeID": trade_id,
                                  "price": str(round(float(sl), dec)), "timeInForce": "GTC"}
                    }))
                    logger.info(f"   ✅ SL ORDER created: {sl}")
                except Exception as e:
                    logger.warning(f"   ⚠️ SL order failed: {e}")
            if not trailing_tp and tp is not None:
                if ((action == "BUY" and tp > entry_price) or (action == "SELL" and tp < entry_price)):
                    try:
                        api.request(OrderCreate(accountID=oanda_account_id, data={
                            "order": {"type": "TAKE_PROFIT", "tradeID": trade_id,
                                      "price": str(round(float(tp), dec)), "timeInForce": "GTC"}
                        }))
                        logger.info(f"   ✅ TP ORDER created: {round(float(tp), dec)}")
                    except Exception as e:
                        logger.warning(f"   ⚠️ TP order failed: {e}")
        return {"status": "OK", "response": resp}
    except Exception as e:
        logger.error(f"❌ OANDA order failed for {pair_raw}: {e}")
        return {"status": "ERROR", "message": str(e)}

# =============================================================================
# ACCOUNT EQUITY
# =============================================================================
def get_account_equity(api, oanda_account_id: str) -> float:
    try:
        from oandapyV20.endpoints.accounts import AccountDetails
        return float(api.request(AccountDetails(accountID=oanda_account_id))["account"]["balance"])
    except Exception as e:
        logger.warning(f"Could not fetch equity: {e}, fallback 10000")
        return 10000.0

# =============================================================================
# STRENGTH-BASED CLOSE
# =============================================================================
def should_close_by_strength(
    pair: str, side: str, strength_scores: dict, threshold: float = 1.0
) -> tuple:
    clean = pair.replace("=X", "").replace("_", "")
    base, quote = clean[:3], clean[3:] if len(clean)==6 else (
        (lambda p: (p[0], p[1]))(pair.replace("=X","").split("_"))
    )
    base_score, quote_score = strength_scores.get(base,0), strength_scores.get(quote,0)
    gap = base_score - quote_score
    if side == "long" and -gap > threshold:
        return True, f"Strength flip: {quote} stronger than {base}, gap={-gap:.2f}"
    if side == "short" and gap > threshold:
        return True, f"Strength flip: {base} stronger than {quote}, gap={gap:.2f}"
    return False, ""

# =============================================================================
# MC RESULT LOADER
# =============================================================================
def load_mc_legacy(pair: str, results_dir: Path, today_str: str, max_age_hours: int = 24):
    safe = pair.replace("=X", "").replace("=", "_")
    for f in [results_dir/f"fx_daily_{safe}_{today_str}.json",
              results_dir/f"daily_mc_{safe}_{today_str}.json",
              results_dir/f"h4_mc_{safe}_{today_str}.json"]:
        if f.exists():
            age = (datetime.now(timezone.utc) - datetime.fromtimestamp(f.stat().st_mtime, timezone.utc)).total_seconds()/3600
            if age <= max_age_hours:
                with open(f) as j: return json.load(j), True
    return None, False

# =============================================================================
# TELEGRAM BUILDERS
# =============================================================================
def build_mc_telegram(mc_results: list, title: str, tf: str, lookback: int, forecast: int, sims: int) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"📊 **{title}**", f"📅 {now}", f"🔹 TF:{tf} Lookback:{lookback} Forecast:{forecast} Sims:{sims}", ""]
    for r in mc_results:
        lo, hi = r["range_90"]
        lines.extend([
            f"🔹 **{r['pair']}**",
            f"   💵 Close: `{r['current_price']}` | Percentile: `{r['percentile_rank']}%`",
            f"   🎯 UP:`{r['p_up_pct']}%` DOWN:`{r['p_down_pct']}%`",
            f"   📏 90% Band: `{lo}`–`{hi}`",
            f"   🔍 Touch: Low `{r['touch_lower_pct']}%` | High `{r['touch_upper_pct']}%`",
            f"   {r['regime']}", ""
        ])
    return "\n".join(lines)

def build_trade_telegram(trade_lines: list, mc_summary: list = None) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"🤖 MULTI‑PAIR UPDATE — {now}"] + trade_lines
    if mc_summary:
        lines += ["", "📊 *MC Context:*"] + [f"   {s}" for s in mc_summary]
    return "\n".join(lines)

# =============================================================================
# HIERARCHICAL SL CALC
# =============================================================================
def compute_sl_zone(api, oanda_instrument, direction, entry_price, pip_size, cfg_fn):
    BUFFER_PIPS   = cfg_fn("SL_BUFFER_PIPS", 25)
    MIN_DIST_PIPS = cfg_fn("SL_MIN_DISTANCE_PIPS", 20)
    ATR_MULT      = cfg_fn("ATR_SL_MULT", 2.0)
    FIXED_PIPS    = cfg_fn("SL_FALLBACK_FIXED_PIPS", 35)
    TF_LIST = [("H4","H4",cfg_fn("SL_H4_LOOKBACK_BARS",6)),
               ("H8","H8",cfg_fn("SL_H8_LOOKBACK_BARS",4)),
               ("DAILY","D",cfg_fn("SL_DAILY_LOOKBACK_BARS",2))]

    def _fetch_zone(gran, count, dir):
        try:
            resp = api.request(InstrumentsCandles(instrument=oanda_instrument,
                params={"granularity":gran,"count":count,"price":"M"}))
            c = resp.get("candles",[])
            if len(c) < count*0.5: return None,0
            highs = [float(x["mid"]["h"]) for x in c]
            lows  = [float(x["mid"]["l"]) for x in c]
            closes = [float(x["mid"]["c"]) for x in c]
            trs = [max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])) for i in range(1,len(c))]
            atr = np.mean(trs[-14:]) if len(trs)>=14 else np.mean(trs) if trs else 0
            return (min(lows), atr) if dir=="BUY" else (max(highs), atr)
        except Exception as e:
            logger.debug(f"⚠️ {gran} fetch failed: {e}")
            return None,0

    buffer_amt = BUFFER_PIPS * pip_size
    for name,gran,lookback in TF_LIST:
        zone,atr = _fetch_zone(gran,lookback,direction)
        if zone is None:
            logger.info(f"⏭️ {oanda_instrument} {direction} {name}: no data → next")
            continue
        sl_candidate = zone - buffer_amt if direction=="BUY" else zone + buffer_amt
        dist = abs(entry_price - sl_candidate)/pip
        if dist >= MIN_DIST_PIPS:
            logger.info(f"📏 SL {name}: Zone={zone:.5f} ±{BUFFER_PIPS}p → {sl_candidate:.5f} | Dist={dist:.1f}p")
            return sl_candidate, f"{name} Zone {dist:.0f}p"
        logger.info(f"⚠️ {name} too close ({dist:.1f}p) → stepping up")

    _,atr = _fetch_zone("H4",14,direction)
    if atr and atr>0:
        sl_atr = entry_price - atr*ATR_MULT if direction=="BUY" else entry_price + atr*ATR_MULT
        dist = abs(entry_price-sl_atr)/pip
        logger.info(f"🔁 SL ATR-{ATR_MULT}x: {sl_atr:.5f} | Dist={dist:.1f}p")
        return sl_atr, f"ATR-{ATR_MULT}x {dist:.0f}p"

    sl_fix = entry_price - FIXED_PIPS*pip if direction=="BUY" else entry_price + FIXED_PIPS*pip
    logger.info(f"🚨 SL FIXED-{FIXED_PIPS}p: {sl_fix:.5f}")
    return sl_fix, f"FIXED-{FIXED_PIPS}p"

# =============================================================================
# POSITION MANAGER PROFILES
# =============================================================================
@dataclass
class PositionManagerProfile:
    be_trigger_atr_mult: float
    trail_trigger_atr_mult: float
    trail_atr_mult: float
    max_hold_bars: int
    jpy_trail_factor: float

PROFILE_BALANCED = PositionManagerProfile(
    be_trigger_atr_mult=2.0, trail_trigger_atr_mult=3.0,
    trail_atr_mult=2.0, max_hold_bars=12, jpy_trail_factor=1.25
)
PROFILE_TREND_FOLLOWING = PositionManagerProfile(
    be_trigger_atr_mult=3.0, trail_trigger_atr_mult=4.5,
    trail_atr_mult=3.0, max_hold_bars=24, jpy_trail_factor=1.20
)

# =============================================================================
# DYNAMIC POSITION MANAGER — Breakeven + Trailing + Dynamic TP
# UPDATED v6.8.5.1: Profile3 → Zone-Based Trailing SL; Profile2 → ATR Trail UNCHANGED
# =============================================================================
class DynamicPositionManager:
    def __init__(
        self, api, account_id: str, timeframe: str,
        be_trigger_atr_mult: float = 1.5,
        trail_trigger_atr_mult: float = 2.5,
        trail_atr_mult: float = 1.5,
        max_hold_bars: int = 12,
        min_hold_bars: int = 4,
        exit_on_close_only: bool = True,
        ratchet_exit: bool = True,
        dynamic_tp: bool = True,
        tp_raise_thresh_pips: int = 15,
        tp_atr_mult: float = 3.0,
        telegram_send=None,
        jpy_trail_factor: float = 1.25,
        use_zone_based_trailing: bool = False  # ← True = Profile3 mode
    ):
        self.api, self.account_id, self.timeframe = api, account_id, timeframe
        self.be_trigger = be_trigger_atr_mult
        self.trail_trigger = trail_trigger_atr_mult
        self.trail_mult = trail_atr_mult
        self.max_hold = max_hold_bars
        self.min_hold_bars = min_hold_bars
        self.exit_on_close_only = exit_on_close_only
        self.ratchet_exit = ratchet_exit
        self.dynamic_tp = dynamic_tp
        self.tp_thresh_pips = tp_raise_thresh_pips
        self.tp_atr_mult = tp_atr_mult
        self.telegram = telegram_send
        self.jpy_trail_factor = jpy_trail_factor
        self.use_zone_based_trailing = use_zone_based_trailing  # Profile3 flag


    def _recalculate_zone_sl(self, instrument: str, side: str):
        """
        ✅ PROFILE3 ONLY: Recalc SL using SAME H4 zone method as trade opening
        SELL → max(4 closed H4 highs) + 20 pips
        BUY  → min(4 closed H4 lows)  - 20 pips
        Returns (sl_price, pip_size) or (None, None) on failure.
        """
        try:
            h4_df = fetch_candles(self.api, instrument, "H4", count=5)
            if h4_df is None or len(h4_df) < 5:
                logger.debug(f"⚠️ {instrument}: insufficient H4 candles for zone SL")
                return None, None

            # Use ONLY fully closed candles — drop forming bar
            h4_closed = [
                {"high": float(r["High"]), "low": float(r["Low"])}
                for _, r in h4_df.iloc[:-1].iterrows()
            ]
            if len(h4_closed) < 4:
                logger.debug(f"⚠️ {instrument}: need ≥4 closed H4 bars")
                return None, None

            pip = 0.01 if "JPY" in instrument.upper() else 0.0001
            decimals = 3 if "JPY" in instrument.upper() else 5

            if side == "long":  # BUY
                ref_level = min(c["low"] for c in h4_closed)
                sl_price = round(ref_level - (20 * pip), decimals)
            else:  # SELL
                ref_level = max(c["high"] for c in h4_closed)
                sl_price = round(ref_level + (20 * pip), decimals)

            return sl_price, pip

        except Exception as e:
            logger.debug(f"⚠️ Zone SL recalc failed {instrument}: {e}")
            return None, None


    def _get_open_trades(self, instrument: str):
        try:
            resp = self.api.request(OpenTrades(accountID=self.account_id))
            return [t for t in resp.get("trades", []) if t.get("instrument") == instrument]
        except Exception as e:
            if "404" in str(e) or "NO_SUCH_POSITION" in str(e):
                logger.info(f"✅ {instrument}: No open trades")
            else:
                logger.error(f"❌ Failed to fetch trades for {instrument}: {e}")
            return []


    def _current_price(self, instrument: str, side: str):
        try:
            from utils.strategy_helpers import get_live_prices
            prices = get_live_prices(instrument)
            if prices and "bid" in prices and "ask" in prices:
                return prices["bid"] if side == "long" else prices["ask"]
            return None
        except Exception as e:
            logger.warning(f"⚠️ Price fetch failed for {instrument}: {e}")
            return None


    def _update_trade_sl(self, trade_id: str, new_sl: float, decimals: int):
        try:
            data = {"stopLoss": {"price": str(round(new_sl, decimals)), "timeInForce": "GTC"}}
            self.api.request(TradeCRCDO(accountID=self.account_id, tradeID=trade_id, data=data))
            logger.info(f"🔄 Updated SL trade {trade_id} → {round(new_sl, decimals)}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to update SL {trade_id}: {e}")
            return False


    def _update_trade_tp(self, trade_id: str, instrument: str, new_tp: float, decimals: int):
        return update_order_tp(self.api, self.account_id, trade_id, instrument, new_tp, send_telegram=self.telegram)


    def update_all(self, pair_data: dict, close_position_fn=None):
        BAR_HOURS = {"15m":0.25, "1H":1, "H4":4, "D":24}
        bar_hours = BAR_HOURS.get(self.timeframe, 4)
        pip_size_map = lambda p: 0.01 if "JPY" in p.upper() else 0.0001

        for pair, info in pair_data.items():
            instrument, df = info["oanda"], info.get("df")
            if df is None or len(df) < 2: continue
            atr_index = -2 if self.exit_on_close_only else -1
            atr_val = df.iloc[atr_index].get("atr")
            if atr_val is None or np.isnan(atr_val) or atr_val <= 0: continue

            is_jpy = "JPY" in pair.upper()
            active_trail_mult = self.trail_mult * self.jpy_trail_factor if is_jpy else self.trail_mult
            decimals, pip = (3, 0.01) if is_jpy else (5, 0.0001)

            trades = self._get_open_trades(instrument)
            if not trades: continue

            for trade in trades:
                tid = trade["id"]
                units = int(trade["currentUnits"])
                side = "long" if units > 0 else "short"
                entry = float(trade["price"])
                current_sl = float((trade.get("stopLossOrder") or {}).get("price")) if (trade.get("stopLossOrder") or {}).get("price") else None
                current_tp = float((trade.get("takeProfitOrder") or {}).get("price")) if (trade.get("takeProfitOrder") or {}).get("price") else None
                current_price = self._current_price(instrument, side)
                if current_price is None: continue

                profit_pips = (current_price - entry)/pip if side == "long" else (entry - current_price)/pip
                open_time = datetime.fromisoformat(trade["openTime"].replace("Z","+00:00"))
                bars_held = (datetime.now(timezone.utc) - open_time).total_seconds()/3600/bar_hours

                # ─── TIME EXIT ───
                if bars_held >= self.max_hold:
                    logger.info(f"⏰ TIME EXIT {pair} #{tid} — held {bars_held:.1f} bars")
                    if close_position_fn: close_position_fn(instrument)
                    continue

                in_min_hold = bars_held < self.min_hold_bars
                new_sl = action = None
                be_pips = self.be_trigger * atr_val / pip
                trail_pips = self.trail_trigger * atr_val / pip

                # ─── BREAKEVEN (shared) ───
                if profit_pips >= be_pips:
                    be_sl = round(entry - pip if side == "long" else entry + pip, decimals)
                    if current_sl is None or (side=="long" and be_sl>current_sl) or (side=="short" and be_sl<current_sl):
                        new_sl, action = be_sl, "BREAKEVEN"

                # ─── TRAILING — BRANCH BY PROFILE ───
                if not in_min_hold and profit_pips >= trail_pips:
                    if self.use_zone_based_trailing:
                        # ==========================================
                        # ✅ PROFILE3: ZONE-BASED TRAILING (NEW LOGIC)
                        # Recalc SL exactly like opening SL
                        # SELL: only move SL DOWN (never up)
                        # BUY:  only move SL UP   (never down)
                        # ==========================================
                        zone_sl, _ = self._recalculate_zone_sl(instrument, side)
                        if zone_sl is not None:
                            if side == "long":  # BUY
                                # Only allow SL UP → zone_sl > current_sl ✅
                                if current_sl is None:
                                    new_sl, action = zone_sl, "ZONE-TRAIL"
                                elif zone_sl > current_sl:
                                    new_sl, action = zone_sl, "ZONE-TRAIL"
                                # Else: new SL is worse → IGNORE
                            else:  # SELL
                                # Only allow SL DOWN → zone_sl < current_sl ✅
                                if current_sl is None:
                                    new_sl, action = zone_sl, "ZONE-TRAIL"
                                elif zone_sl < current_sl:
                                    new_sl, action = zone_sl, "ZONE-TRAIL"
                                # Else: new SL is worse → IGNORE
                    else:
                        # ==========================================
                        # ✅ PROFILE2: ORIGINAL ATR TRAILING (UNCHANGED)
                        # ==========================================
                        trail_sl = round(
                            current_price - active_trail_mult*atr_val if side=="long"
                            else current_price + active_trail_mult*atr_val,
                            decimals
                        )
                        new_sl, action = trail_sl, "ATR-TRAIL"

                # ─── APPLY SL UPDATE (ratchet protection) ───
                if new_sl and action:
                    if self.ratchet_exit:
                        # Never move SL against you — double safety
                        if side == "long":
                            if current_sl and new_sl < current_sl:
                                new_sl = action = None
                        else:
                            if current_sl and new_sl > current_sl:
                                new_sl = action = None

                    if new_sl and action:
                        if self._update_trade_sl(tid, new_sl, decimals) and self.telegram:
                            self.telegram(
                                f"🎯 {action} {pair} #{tid} | Price: {current_price:.{decimals}f} | "
                                f"SL→{new_sl:.{decimals}f} | Profit: {profit_pips:.1f}p"
                            )

                # ─── DYNAMIC TP (shared, unchanged) ───
                if self.dynamic_tp and not in_min_hold:
                    if side == "long":
                        tp_candidate = round(current_price + self.tp_atr_mult * atr_val, decimals)
                        if current_tp is None or tp_candidate > current_tp + self.tp_thresh_pips * pip:
                            self._update_trade_tp(tid, instrument, tp_candidate, decimals)
                    else:
                        tp_candidate = round(current_price - self.tp_atr_mult * atr_val, decimals)
                        if current_tp is None or tp_candidate < current_tp - self.tp_thresh_pips * pip:
                            self._update_trade_tp(tid, instrument, tp_candidate, decimals)
