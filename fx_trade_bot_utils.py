# fx_trade_bot_utils.py — Shared Helpers Extracted from v6.1 + Dynamic TP
# Contains: Cooldown, Market Check, Position Helpers, Order Helpers, Telegram Builders, Strength Close, MC Loader, Dynamic TP

import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from enum import Enum
import numpy as np
import pandas as pd
from telegram_message import send_telegram_message

from oandapyV20.endpoints.instruments import InstrumentsCandles
from oandapyV20.endpoints.positions import PositionDetails
from oandapyV20.endpoints.orders import OrderCreate
from oandapyV20.endpoints.trades import OpenTrades, TradeCRCDO

logger = logging.getLogger(__name__)


# ============================================================================
# CONFIG HELPERS
# ============================================================================
def price_decimals(pair: str) -> int:
    """Return correct decimal places for OANDA pricing."""
    return 3 if "JPY" in pair.upper() else 5

def pip_size(pair: str) -> float:
    """Return 1 pip value for pair."""
    return 0.01 if "JPY" in pair.upper() else 0.0001


# ============================================================================
# COOLDOWN MANAGEMENT
# ============================================================================
def load_cooldown(cooldown_file: Path, Direction):
    """Load cooldown state from JSON."""
    if cooldown_file.exists():
        with open(cooldown_file) as f:
            raw = json.load(f)
            return {k: (Direction(v[0]), v[1]) for k, v in raw.items()}
    return {}

def save_cooldown(cooldown_file: Path, state: dict):
    """Save cooldown state to JSON."""
    serializable = {k: (v[0].value, v[1]) for k, v in state.items()}
    with open(cooldown_file, "w") as f:
        json.dump(serializable, f)


# ============================================================================
# MARKET STATUS CHECK
# ============================================================================
# Add this inside fx_trade_bot_utils.py
def update_order_tp(api, account_id: str, trade_id: str, instrument: str,
                    new_tp: float, decimals: int = 5, send_telegram=None):
    """✅ Update TP on an open trade via TradeCRCDO"""
    try:
        tp_data = {
            "takeProfit": {
                "price": str(round(new_tp, decimals)),
                "timeInForce": "GTC"
            }
        }
        api.request(TradeCRCDO(accountID=account_id, tradeID=trade_id, data=tp_data))
        logger.info(f"   🔄 Updated TP on trade {trade_id} → {round(new_tp, decimals)}")
        if send_telegram:
            send_telegram(f"🎯 TP UPDATED {instrument} #{trade_id} → {round(new_tp, decimals)}")
        return True
    except Exception as e:
        logger.error(f"   ❌ Failed to update TP on trade {trade_id}: {e}")
        return False

def forex_market_closed(api, oanda_account_id: str, oanda_granularity: str) -> bool:
    """Check if forex market is closed via recent candle availability."""
    try:
        resp = api.request(
            InstrumentsCandles(
                instrument="EUR_USD",
                params={"count": 1, "granularity": oanda_granularity},
            )
        )
        return len(resp.get("candles", [])) == 0
    except Exception as e:
        logger.error(f"Market check failed: {e}")
        return True


# ============================================================================
# POSITION HELPERS
# ============================================================================
def attach_tp_to_open_positions(engine, instrument=None):
    """
    Scan open positions → attach FIXED TP if missing
    Call this at bot startup to ensure ALL positions have TP
    """
    from oandapyV20.endpoints.trades import OpenTrades, TradeCRCDO
    import config
    def cfg(name, default):
        return getattr(config, name, default)

    client = engine.client
    account_id = engine.account_id
    atr_dist_pips = getattr(config, "TP_ATR_PIPS", 30)  # TP distance in pips

    resp = client.request(OpenTrades(account_id))
    trades = resp.get("trades", [])

    if not trades:
        logger.info("📋 No open positions to attach TP")
        return 0

    attached_count = 0
    for trade in trades:
        tid = trade["id"]
        inst = trade["instrument"]
        current_tp = trade.get("takeProfitOrder", {}).get("price")
        units = float(trade["currentUnits"])
        entry_price = float(trade["price"])

        if current_tp:
            logger.debug(f"   ✅ {inst} Trade {tid}: TP already exists @ {current_tp}")
            continue

        # Calculate FIXED TP based on direction + ATR distance
        is_short = units < 0
        pip_sizes = {"JPY": 0.01, "XAU": 0.1, "DEFAULT": 0.0001}
        pip = pip_sizes["JPY"] if "JPY" in inst else pip_sizes["DEFAULT"]
        dist = atr_dist_pips * pip

        if is_short:
            tp_price = round(entry_price - dist, 5)
            dir_label = "SHORT → TP BELOW"
        else:
            tp_price = round(entry_price + dist, 5)
            dir_label = "LONG → TP ABOVE"

        logger.info(f"🔧 ATTACH TP {inst} Trade {tid} | {dir_label} | Entry={entry_price} → TP={tp_price}")

        # Send TP update to OANDA
        data = {"takeProfit": {"price": f"{tp_price}", "timeInForce": "GTC"}}
        try:
            client.request(TradeCRCDO(account_id, tid, data=data))
            attached_count += 1
            logger.info(f"   ✅ TP ATTACHED for {inst} @ {tp_price}")
        except Exception as e:
            logger.warning(f"   ❌ Failed: {e}")

    logger.info(f"📋 TP Attach Summary: {attached_count} positions updated with TP")
    return attached_count

def get_open_position(api, oanda_account_id: str, instrument: str):
    """Get current open position for an instrument."""
    try:
        pos = api.request(
            PositionDetails(accountID=oanda_account_id, instrument=instrument)
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

def close_position(api, oanda_account_id: str, instrument: str, telegram_send=None):
    """Close existing position for instrument."""
    try:
        pos = api.request(
            PositionDetails(accountID=oanda_account_id, instrument=instrument)
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
                accountID=oanda_account_id,
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
        if telegram_send:
            telegram_send(f"🔄 AUTO‑CLOSE: {instrument}")
    except Exception as e:
        logger.error(f"Close failed for {instrument}: {e}")


# ============================================================================
# ORDER EXECUTION WITH SAFETY CHECKS
# ============================================================================
def _open_oanda_order(
    signal: dict, units: int, current_price: float,
    api, oanda_account_id: str, oanda_token: str,
    trailing_tp: bool = False, dynamic_tp: bool = False,
    max_sl_pips: int = None, max_sl_pct: float = 0.03,
    telegram_send=None, cfg=None
) -> dict:
    """Open order with SL/TP logic and safety guards."""
    if not oanda_account_id or not oanda_token:
        return {"status": "ERROR", "message": "Missing OANDA credentials"}

    pair_raw = signal.get("pair")
    action = signal.get("action")
    sl = signal.get("stop_loss")
    tp = signal.get("take_profit")

    if action not in {"BUY", "SELL"}:
        return {"status": "ERROR", "message": f"Invalid action: {action}"}
    if sl is None:
        return {"status": "ERROR", "message": "SL missing"}
    if current_price is None:
        logger.error(f"❌ Cannot open {pair_raw}: entry price required")
        return {"status": "ERROR", "message": "Entry price missing"}

    entry = current_price
    dec = price_decimals(pair_raw)
    pip = pip_size(pair_raw)

    is_jpy = "JPY" in pair_raw.upper()
    if max_sl_pips is None:
        max_sl_pips = 500 if is_jpy else 50

    sl_distance = abs(entry - sl)
    sl_pips = sl_distance / pip
    sl_pct = sl_distance / entry

    if sl_pips > max_sl_pips or sl_pct > max_sl_pct:
        err = (f"SL GUARD BLOCKED {pair_raw}: SL={sl} is {sl_pips:.0f} pips / {sl_pct:.1%} from entry. "
               f"Max allowed: {max_sl_pips} pips / {max_sl_pct:.1%}")
        logger.error(err)
        if telegram_send:
            telegram_send(f"🛡️ {err}")
        return {"status": "ERROR", "message": err}

    if action == "BUY" and sl >= entry:
        err = f"SL GUARD BLOCKED {pair_raw}: SL {sl} >= entry {entry} for LONG"
        logger.error(err)
        return {"status": "ERROR", "message": err}
    if action == "SELL" and sl <= entry:
        err = f"SL GUARD BLOCKED {pair_raw}: SL {sl} <= entry {entry} for SHORT"
        logger.error(err)
        return {"status": "ERROR", "message": err}

    order_payload = {
        "order": {
            "type": "MARKET",
            "instrument": pair_raw,
            "units": str(units if action == "BUY" else -units),
            "timeInForce": "FOK",
            "positionFill": "DEFAULT",
            "stopLossOnFill": {"price": str(round(float(sl), dec)), "timeInForce": "GTC"},
        }
    }

    if not trailing_tp and tp is not None:
        if (action == "BUY" and tp > entry) or (action == "SELL" and tp < entry):
            order_payload["takeProfitOnFill"] = {"price": str(round(float(tp), dec)), "timeInForce": "GTC"}
            logger.info(f"   ✅ Fixed TP attached: {round(float(tp), dec)}")
        else:
            logger.warning(f"   ⚠️ TP {tp} invalid vs entry {entry} — omitted")
    elif trailing_tp:
        logger.info("   ℹ️ TRAILING_TP=True — using OANDA server-side trailing")
    else:
        logger.warning("   ⚠️ No TP value — sending SL only")

    try:
        resp = api.request(OrderCreate(accountID=oanda_account_id, data=order_payload))
        logger.info(f"✅ OANDA accepted order for {pair_raw}")

        # ✅ Store order details for Dynamic TP updates — NO undefined variables!
        if dynamic_tp and tp is not None:
            try:
                direction = "BUY" if action == "BUY" else "SELL"
                order_info = {
                    "order_id": str(resp.get("orderFillTransactionID", resp.get("orderCreateTransactionID", "?"))),
                    "instrument": pair_raw,
                    "entry_price": float(resp.get("price", current_price)),
                    "initial_tp": float(tp),
                    "direction": direction,
                    "time_opened": datetime.utcnow().isoformat()
                }
                tp_state_file = Path(__file__).parent / "tp_state.json"
                tp_state = {}
                if tp_state_file.exists():
                    with open(tp_state_file) as f:
                        tp_state = json.load(f)
                tp_state[pair_raw] = order_info
                with open(tp_state_file, "w") as f:
                    json.dump(tp_state, f, indent=2)
                logger.info(f"💾 TP STATE SAVED: {pair_raw} → TP={tp}")
            except Exception as e:
                logger.warning(f"⚠️ Could not save TP state: {e}")

        return {"status": "OK", "response": resp}
    except Exception as e:
        logger.error(f"❌ OANDA order failed for {pair_raw}: {e}")
        return {"status": "ERROR", "message": str(e)}

def open_oanda_order(
    signal: dict, units: int, current_price: float,
    api, oanda_account_id: str, oanda_token: str,
    trailing_tp: bool = False, 
    dynamic_tp: bool = False,
    max_sl_pips: int = None, max_sl_pct: float = 0.03,
    telegram_send=None, cfg=None
) -> dict:
    """Open order with SL/TP logic and safety guards."""

    if not oanda_account_id or not oanda_token:
        return {"status": "ERROR", "message": "Missing OANDA credentials"}

    pair_raw = signal.get("pair")
    action = signal.get("action")
    sl = signal.get("stop_loss")
    tp = signal.get("take_profit")

    if action not in {"BUY", "SELL"}:
        return {"status": "ERROR", "message": f"Invalid action: {action}"}
    if sl is None:
        return {"status": "ERROR", "message": "SL missing"}
    if current_price is None:
        logger.error(f"❌ Cannot open {pair_raw}: entry price required")
        return {"status": "ERROR", "message": "Entry price missing"}

    entry = current_price
    dec = price_decimals(pair_raw)
    pip = pip_size(pair_raw)

    is_jpy = "JPY" in pair_raw.upper()
    if max_sl_pips is None:
        max_sl_pips = 500 if is_jpy else 50

    sl_distance = abs(entry - sl)
    sl_pips = sl_distance / pip
    sl_pct = sl_distance / entry

    if sl_pips > max_sl_pips or sl_pct > max_sl_pct:
        err = (f"SL GUARD BLOCKED {pair_raw}: SL={sl} is {sl_pips:.0f} pips / {sl_pct:.1%} from entry. "
               f"Max allowed: {max_sl_pips} pips / {max_sl_pct:.1%}")
        logger.error(err)
        if telegram_send:
            telegram_send(f"🛡️ {err}")
        return {"status": "ERROR", "message": err}

    if action == "BUY" and sl >= entry:
        err = f"SL GUARD BLOCKED {pair_raw}: SL {sl} >= entry {entry} for LONG"
        logger.error(err)
        return {"status": "ERROR", "message": err}
    if action == "SELL" and sl <= entry:
        err = f"SL GUARD BLOCKED {pair_raw}: SL {sl} <= entry {entry} for SHORT"
        logger.error(err)
        return {"status": "ERROR", "message": err}


    # ✅ STEP 1: Send MARKET order WITHOUT attached SL/TP
    order_payload = {
        "order": {
            "type": "MARKET",
            "instrument": pair_raw,
            "units": str(units if action == "BUY" else -units),
            "positionFill": "DEFAULT",
            # ❌ NO SL/TP HERE — we attach them SEPARATELY!
        }
    }

    try:
        resp = api.request(OrderCreate(accountID=oanda_account_id, data=order_payload))
        logger.info(f"✅ OANDA accepted order for {pair_raw}")

        # ✅ CORRECTLY extract TradeID from OANDA response
        trade_id = ""
        entry_price = current_price
        if "orderFillTransaction" in resp:
            trade_id = str(resp["orderFillTransaction"].get("id", ""))
            entry_price = float(resp["orderFillTransaction"].get("price", current_price))
            logger.info(f"📦 Trade opened: TradeID={trade_id} @ {entry_price}")
        elif "orderCreateTransaction" in resp:
            trade_id = str(resp["orderCreateTransaction"].get("id", ""))
            logger.info(f"📦 Order created: OrderID={trade_id}")
        else:
            logger.warning(f"⚠️ Could not find TradeID! Response keys: {list(resp.keys())}")

        # ✅ ONLY proceed if we have a valid TradeID
        if not trade_id:
            logger.error(f"❌ Cannot create SL/TP — TradeID is EMPTY!")
        else:
            # ✅ STEP 2: Create SL ORDER separately
            if sl is not None:
                sl_data = {
                    "order": {
                        "type": "STOP_LOSS",
                        "tradeID": trade_id,
                        "price": str(round(float(sl), dec)),
                        "timeInForce": "GTC"
                    }
                }
                try:
                    api.request(OrderCreate(accountID=oanda_account_id, data=sl_data))
                    logger.info(f"   ✅ SL ORDER created: {sl}")
                except Exception as e:
                    logger.warning(f"   ⚠️ SL order failed: {e}")

            # ✅ STEP 3: Create TP ORDER separately
            if not trailing_tp and tp is not None:
                if (action == "BUY" and tp > entry_price) or (action == "SELL" and tp < entry_price):
                    tp_data = {
                        "order": {
                            "type": "TAKE_PROFIT",
                            "tradeID": trade_id,
                            "price": str(round(float(tp), dec)),
                            "timeInForce": "GTC"
                        }
                    }
                    try:
                        api.request(OrderCreate(accountID=oanda_account_id, data=tp_data))
                        logger.info(f"   ✅ TP ORDER created: {round(float(tp), dec)}")
                    except Exception as e:
                        logger.warning(f"   ⚠️ TP order failed: {e}")
        return {"status": "OK", "response": resp}

    except Exception as e:
        logger.error(f"❌ OANDA order failed for {pair_raw}: {e}")
        return {"status": "ERROR", "message": str(e)}

# ============================================================================
# ✅ DYNAMIC TP UPDATE FUNCTION
# ============================================================================
def update_order_tp(api, account_id, trade_id, instrument, new_tp_price,
                    token=None, environment="practice", send_telegram=None):
    """
    Update Take-Profit on an OPEN TRADE (OANDA Trade API — correct approach).
    OANDA does NOT allow updating orders once filled — we update the TRADE's TP instead.
    Returns: {"ok": bool, "status": str, "old_tp": float, "new_tp": float}
    """
    from oandapyV20.endpoints.trades import TradeCRCDO

    try:
        dec = price_decimals(instrument)
        new_tp_str = f"{float(new_tp_price):.{dec}f}"

        # ✅ OANDA: Update TP on the TRADE (not the order — orders are immutable once filled)
        data = {
            "takeProfit": {
                "price": new_tp_str,
                "timeInForce": "GTC"
            }
        }

        logger.info(f"🔄 Updating TP: {instrument} trade {trade_id} → {new_tp_str}")
        r = TradeCRCDO(accountID=account_id, tradeID=trade_id, data=data)
        resp = api.request(r)

        if "takeProfitOrderTransaction" in resp:
            txid = resp["takeProfitOrderTransaction"]["id"]
            msg = f"✅ TP UPDATED {instrument} → {new_tp_str} (TxID: {txid})"
            logger.info(msg)
            if send_telegram:
                send_telegram_message(msg)
            return {"ok": True, "status": "UPDATED", "new_tp": new_tp_price, "txid": txid}
        else:
            logger.warning(f"⚠️ Unexpected TP update response: {resp}")
            return {"ok": False, "status": "UNEXPECTED", "response": resp}

    except Exception as e:
        err = f"❌ TP UPDATE FAILED {instrument}: {type(e).__name__}: {e}"
        logger.error(err)
        if send_telegram:
            send_telegram_message(err)
        return {"ok": False, "status": "ERROR", "error": str(e)}


# ============================================================================
# ACCOUNT EQUITY
# ============================================================================
def get_account_equity(api, oanda_account_id: str) -> float:
    """Fetch current account balance."""
    try:
        from oandapyV20.endpoints.accounts import AccountDetails
        resp = api.request(AccountDetails(accountID=oanda_account_id))
        return float(resp["account"]["balance"])
    except Exception as e:
        logger.warning(f"Could not fetch equity: {e}, using fallback 10000")
        return 10000.0


# ============================================================================
# STRENGTH-BASED CLOSE LOGIC
# ============================================================================
def should_close_by_strength(pair: str, side: str, strength_scores: dict, threshold: float = 1.0) -> tuple:
    """Determine if position should close based on currency strength flip."""
    clean = pair.replace("=X", "").replace("_", "")
    if len(clean) == 6:
        base, quote = clean[:3], clean[3:]
    else:
        parts = pair.replace("=X", "").split("_")
        if len(parts) == 2:
            base, quote = parts[0], parts[1]
        else:
            return False, ""

    base_score = strength_scores.get(base, 0)
    quote_score = strength_scores.get(quote, 0)
    gap = base_score - quote_score

    if side == "long" and -gap > threshold:
        return True, f"Strength flip: {quote} (+{quote_score:.2f}) stronger than {base} ({base_score:.2f}), gap={-gap:.2f}"
    if side == "short" and gap > threshold:
        return True, f"Strength flip: {base} (+{base_score:.2f}) stronger than {quote} ({quote_score:.2f}), gap={gap:.2f}"
    return False, ""


# ============================================================================
# LEGACY MC LOADER
# ============================================================================
def load_mc_legacy(pair: str, results_dir: Path, today_str: str, max_age_hours: int = 24):
    """Load cached MC result from today's files if fresh enough."""
    safe = pair.replace("=X", "").replace("=", "_")
    for f in [
        results_dir / f"fx_daily_{safe}_{today_str}.json",
        results_dir / f"daily_mc_{safe}_{today_str}.json",
        results_dir / f"h4_mc_{safe}_{today_str}.json",
    ]:
        if f.exists():
            age = (datetime.now(timezone.utc) - datetime.fromtimestamp(f.stat().st_mtime, timezone.utc)).total_seconds() / 3600
            if age <= max_age_hours:
                with open(f) as j:
                    return json.load(j), True
    return None, False


# ============================================================================
# TELEGRAM REPORT BUILDERS
# ============================================================================
def build_mc_telegram(mc_results: list, mc_report_title: str, mc_tf: str, mc_lookback: int, mc_forecast: int, simulations: int) -> str:
    """Format MC results for Telegram message."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"📊 **{mc_report_title}**",
        f"📅 Generated: {now}",
        f"🔹 TF: {mc_tf} | Lookback: {mc_lookback} | Forecast: {mc_forecast} | Sims: {simulations}",
        ""
    ]
    for r in mc_results:
        dec = price_decimals(r["pair"])
        lo, hi = r["range_90"]
        lines.extend([
            f"🔹 **{r['pair']}**",
            f"   💵 Last Close: `{r['current_price']}`",
            f"   📊 Percentile: `{r['percentile_rank']}%`",
            f"   🎯 UP: `{r['p_up_pct']}%` | DOWN: `{r['p_down_pct']}%`",
            f"   📏 90% Band: `{lo}` – `{hi}`",
            f"   🔍 Touch: Low `{r['touch_lower_pct']}%` | High `{r['touch_upper_pct']}%`",
            f"   {r['regime']}", ""
        ])
    return "\n".join(lines)

def build_trade_telegram(trade_lines: list, mc_summary: list = None) -> str:
    """Format trade summary for Telegram message."""
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
# 🎯 DYNAMIC POSITION MANAGER — Breakeven + Trailing Stop + ✅ DYNAMIC TP
# ============================================================================
class DynamicPositionManager:
    def __init__(self, api, account_id: str, timeframe: str,
                 be_trigger_atr_mult: float = 1.5, trail_trigger_atr_mult: float = 2.5,
                 trail_atr_mult: float = 1.5, max_hold_bars: int = 12,
                 dynamic_tp: bool = True, tp_raise_thresh_pips: int = 15,
                 telegram_send=None):
        self.api = api
        self.account_id = account_id
        self.timeframe = timeframe
        self.be_trigger = be_trigger_atr_mult
        self.trail_trigger = trail_trigger_atr_mult
        self.trail_mult = trail_atr_mult
        self.max_hold = max_hold_bars
        self.dynamic_tp = dynamic_tp
        self.tp_thresh_pips = tp_raise_thresh_pips
        self.telegram = telegram_send

    def _get_open_trades(self, instrument: str):
        try:
            resp = self.api.request(OpenTrades(accountID=self.account_id))
            return [t for t in resp.get("trades", []) if t.get("instrument") == instrument]
        except Exception as e:
            logger.error(f"Failed to fetch open trades for {instrument}: {e}")
            return []

    def _current_price(self, instrument: str, side: str) -> float:
        try:
            r = InstrumentsCandles(instrument=instrument, params={"count": 1, "granularity": "M1", "price": "BA"})
            resp = self.api.request(r)["candles"][0]
            return float(resp["bid"]["c"]) if side == "long" else float(resp["ask"]["c"])
        except Exception as e:
            logger.warning(f"Price fetch failed for {instrument}: {e}")
            return None

    def _update_trade_sl(self, trade_id: str, new_sl: float, decimals: int):
        try:
            data = {"stopLoss": {"price": str(round(new_sl, decimals)), "timeInForce": "GTC"}}
            self.api.request(TradeCRCDO(accountID=self.account_id, tradeID=trade_id, data=data))
            logger.info(f"   🔄 Updated SL on trade {trade_id} → {round(new_sl, decimals)}")
            return True
        except Exception as e:
            logger.error(f"   ❌ Failed to update SL on trade {trade_id}: {e}")
            return False

    def _update_trade_tp(self, trade_id: str, instrument: str, new_tp: float, decimals: int):
        """✅ Update TP on an open trade — called automatically."""
        return update_order_tp(
            self.api, self.account_id, trade_id, instrument,
            new_tp, send_telegram=self.telegram
        )

    def update_all(self, pair_data: dict, close_position_fn=None):
        BAR_HOURS = {"15m": 0.25, "1H": 1, "H4": 4, "D": 24}
        bar_hours = BAR_HOURS.get(self.timeframe, 4)
        pip_size_map = lambda p: 0.01 if "JPY" in p.upper() else 0.0001

        for pair, info in pair_data.items():
            instrument = info["oanda"]
            df = info.get("df")
            if df is None or len(df) < 2:
                continue
            atr_val = df.iloc[-1].get("atr")
            if atr_val is None or np.isnan(atr_val) or atr_val <= 0:
                continue

            decimals = price_decimals(pair)
            pip = pip_size_map(pair)
            trades = self._get_open_trades(instrument)
            if not trades:
                continue

            # ✅ Load saved TP state
            tp_state_file = Path(__file__).parent / "tp_state.json"
            tp_state = {}
            if tp_state_file.exists():
                with open(tp_state_file) as f:
                    tp_state = json.load(f)

            for trade in trades:
                tid = trade["id"]
                units = int(trade["currentUnits"])
                side = "long" if units > 0 else "short"
                entry = float(trade["price"])
                current_sl_raw = trade.get("stopLossOrder", {}).get("price")
                current_sl = float(current_sl_raw) if current_sl_raw else None
                current_tp_raw = trade.get("takeProfitOrder", {}).get("price")
                current_tp = float(current_tp_raw) if current_tp_raw else None

                current_price = self._current_price(instrument, side)
                if current_price is None:
                    continue

                profit_pips = (current_price - entry) / pip if side == "long" else (entry - current_price) / pip
                open_time = datetime.fromisoformat(trade["openTime"].replace("Z", "+00:00"))
                bars_held = (datetime.now(timezone.utc) - open_time).total_seconds() / 3600 / bar_hours

                if bars_held >= self.max_hold:
                    logger.info(f"⏰ TIME EXIT: {pair} trade {tid} held {bars_held:.1f} bars")
                    if close_position_fn:
                        close_position_fn(instrument)
                    continue

                # ── ✅ DYNAMIC TP LOGIC — Raise TP as price moves ──
                if self.dynamic_tp:
                    # Calculate new TP from current ATR
                    atr_mult_tp = 3.0  # Match FEAT_CFG.atr_tp_mult
                    if side == "long":
                        new_tp_candidate = current_price + (atr_mult_tp * atr_val)
                        # Only RAISE TP — never lower it!
                        if current_tp is None or new_tp_candidate > current_tp + (self.tp_thresh_pips * pip):
                            self._update_trade_tp(tid, instrument, new_tp_candidate, decimals)
                    else:  # SHORT
                        new_tp_candidate = current_price - (atr_mult_tp * atr_val)
                        # Only RAISE TP price level (lower number = better for SHORT)
                        if current_tp is None or new_tp_candidate < current_tp - (self.tp_thresh_pips * pip):
                            self._update_trade_tp(tid, instrument, new_tp_candidate, decimals)

                # ── SL LOGIC (Breakeven + Trailing) ──
                new_sl = action = None
                be_pips = self.be_trigger * atr_val / pip
                trail_pips = self.trail_trigger * atr_val / pip

                if profit_pips >= be_pips:
                    be_sl = entry - pip if side == "long" else entry + pip
                    if current_sl is None or (side == "long" and be_sl > current_sl) or (side == "short" and be_sl < current_sl):
                        new_sl, action = be_sl, "BREAKEVEN"

                if profit_pips >= trail_pips:
                    trail_sl = current_price - self.trail_mult * atr_val if side == "long" else current_price + self.trail_mult * atr_val
                    if current_sl is None or (side == "long" and trail_sl > current_sl) or (side == "short" and trail_sl < current_sl):
                        new_sl, action = trail_sl, "TRAIL"

                if new_sl and action:
                    if (side == "long" and current_sl and new_sl < current_sl) or (side == "short" and current_sl and new_sl > current_sl):
                        continue
                    if self._update_trade_sl(tid, new_sl, decimals) and self.telegram:
                        self.telegram(
                            f"🎯 {action} on {pair} #{tid} | Price: {current_price} | New SL: {round(new_sl, decimals)} | Profit: {profit_pips:.1f} pips"
                        )
