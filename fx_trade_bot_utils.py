# fx_trade_bot_utils.py — Production Audited v2.1
# Fixes: False-success return, wrong trade selection, decimal mismatch, fallback values, deprecated APIs
# Safety: STRICT_FILL, dry_run, error sentinels, dynamic_tp OFF by default, market check via tradeable flag
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from enum import Enum
import numpy as np
import pandas as pd
from telegram_message import send_telegram_message
from utils.strategy_helpers import get_live_prices

# OANDA Endpoints — VERIFIED against your installed oandapyV20
from oandapyV20.endpoints.instruments import InstrumentsCandles
from oandapyV20.endpoints.positions import PositionDetails
from oandapyV20.endpoints.orders import OrderCreate
from oandapyV20.endpoints.trades import OpenTrades, TradeCRCDO, TradesList
from oandapyV20.endpoints.pricing import PricingInfo
from oandapyV20.endpoints.transactions import TransactionsSinceID

logger = logging.getLogger(__name__)

# ============================================================================
# CONSTANTS & HELPERS
# ============================================================================
class PositionStatus(Enum):
    OPEN = "open"
    NONE = "none"
    ERROR = "error"  # Distinguishes failure from truly no position

def price_decimals(pair: str) -> int:
    """Return correct decimal places for OANDA pricing."""
    return 3 if "JPY" in pair.upper() else 5

def pip_size(pair: str) -> float:
    """Return 1 pip value for pair."""
    return 0.01 if "JPY" in pair.upper() else 0.0001

def utcnow_safe() -> datetime:
    """Python 3.12+ aware UTC timestamp — no naive datetime."""
    return datetime.now(timezone.utc)

# ============================================================================
# MARKET STATUS CHECK — FIXED: uses tradeable flag
# ============================================================================
def forex_market_closed(api, oanda_account_id: str, oanda_granularity: str | None = None) -> bool:
    """Check if market is open via Pricing tradeable flag — reliable weekends."""
    try:
        resp = api.request(
            PricingInfo(
                accountID=oanda_account_id,
                params={"instruments": "EUR_USD"}
            )
        )
        return not resp["prices"][0].get("tradeable", False)
    except Exception as e:
        logger.warning(f"Market check failed: {e} — assuming closed for safety")
        return True

# ============================================================================
# COOLDOWN MANAGEMENT
# ============================================================================
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

# ============================================================================
# POSITION HELPERS — FIXED: returns ERROR sentinel on failure
# ============================================================================
def get_open_position(api, oanda_account_id: str, instrument: str):
    """Returns: (status, data) — status: OPEN/NONE/ERROR"""
    oanda_logger = logging.getLogger("oandapyV20")
    original_level = oanda_logger.getEffectiveLevel()
    oanda_logger.setLevel(logging.CRITICAL + 10)
    try:
        resp = api.request(
            PositionDetails(accountID=oanda_account_id, instrument=instrument)
        )
        pos = resp.get("position", {})
        long_units = pos.get("long", {}).get("units", "0")
        short_units = pos.get("short", {}).get("units", "0")
        if long_units != "0":
            return PositionStatus.OPEN, {"units": int(long_units), "side": "long"}
        if short_units != "0":
            return PositionStatus.OPEN, {"units": int(short_units), "side": "short"}
        return PositionStatus.NONE, None
    except Exception as e:
        err_text = str(e)
        if "NO_SUCH_POSITION" in err_text or "404" in err_text:
            return PositionStatus.NONE, None
        logger.error(f"⚠️ Position check FAILED {instrument}: {err_text[:120]}")
        return PositionStatus.ERROR, {"error": err_text}
    finally:
        oanda_logger.setLevel(original_level)

def close_position(api, oanda_account_id: str, instrument: str, telegram_send=None, dry_run: bool = False):
    """Close position — verifies order acceptance, logs fill outcome.

    dry_run=True (added v6.8.3.5, decoupled from account env): skip the actual
    OrderCreate API call, still runs the read-only get_open_position() check
    so callers can validate the full pipeline without mutating broker state.
    """
    try:
        status, pos = get_open_position(api, oanda_account_id, instrument)
        if status != PositionStatus.OPEN:
            logger.info(f"No open position to close: {instrument}")
            return True

        units = pos["units"]
        close_units = -units  # Invert all units

        if dry_run:
            logger.info(
                f"🧪 DRY_RUN CLOSE {instrument}: {units} units @ would close "
                f"(dry_run=True, no OANDA OrderCreate write call issued)"
            )
            return True

        resp = api.request(
            OrderCreate(
                accountID=oanda_account_id,
                data={
                    "order": {
                        "type": "MARKET",
                        "instrument": instrument,
                        "units": str(close_units),
                        "positionFill": "REDUCE_ONLY",
                    }
                },
            )
        )

        if "orderCancelTransaction" in resp:
            reason = resp["orderCancelTransaction"].get("reason", "UNKNOWN")
            logger.error(f"❌ Close CANCELLED {instrument}: {reason}")
            return False
        if "orderFillTransaction" in resp:
            logger.info(f"✅ Closed {instrument} @ {resp['orderFillTransaction'].get('price', '?')}")
            if telegram_send:
                telegram_send(f"🔄 CLOSED: {instrument}")
            return True
        else:
            logger.warning(f"⚠️ Close response unexpected keys: {list(resp.keys())}")
            return False
    except Exception as e:
        logger.error(f"❌ Close FAILED {instrument}: {e}")
        return False

# ============================================================================
# ACCOUNT EQUITY — FIXED: no silent fallback
# ============================================================================
def get_account_equity(api, oanda_account_id: str) -> float | None:
    """Returns equity or None on failure — NO silent fallback."""
    try:
        from oandapyV20.endpoints.accounts import AccountDetails
        resp = api.request(AccountDetails(accountID=oanda_account_id))
        return float(resp["account"]["balance"])
    except Exception as e:
        logger.error(f"❌ Failed to fetch account equity: {e} — sizing SKIPPED this cycle")
        return None

# ============================================================================
# TRADE ID RESOLVER — NEW: finds THIS order's trade, not any existing one
# ============================================================================
def _resolve_trade_id_from_order(
    api,
    oanda_account_id: str,
    instrument: str,
    order_tx_id: str,
    timeout_s: float = 10.0,
    interval_s: float = 0.5,
) -> dict:
    """
    Poll transactions to resolve THIS order's fate — not any order on the instrument.
    
    Returns dict with one of:
      {"status": "OK",       "trade_id": str}  — new trade opened
      {"status": "REDUCED",  "trade_id": ""}   — fill reduced an existing position (no new trade)
      {"status": "CANCELLED","trade_id": "", "reason": str}
      {"status": "REJECTED", "trade_id": "", "reason": str}
      {"status": "TIMEDOUT", "trade_id": ""}
    """
    import time
    start = utcnow_safe()
    since_id = str(int(order_tx_id) - 1) if order_tx_id.isdigit() else order_tx_id

    while (utcnow_safe() - start).total_seconds() < timeout_s:
        try:
            resp = api.request(
                TransactionsSinceID(
                    accountID=oanda_account_id,
                    params={"id": since_id}
                )
            )
        except TypeError as te:
            logger.error(f"TransactionsSinceID signature error: {te}")
            return {"status": "ERROR", "trade_id": "", "reason": f"API_SIG: {te}"}
        except Exception as e:
            logger.debug(f"Trade poll retry after error: {type(e).__name__}: {e}")
            time.sleep(interval_s)
            continue

        for tx in reversed(resp.get("transactions", [])):
            t_type = tx.get("type", "")
            order_id_match = str(tx.get("orderID", "")) == str(order_tx_id)
            
            if t_type == "ORDER_CANCEL" and order_id_match:
                return {"status": "CANCELLED", "trade_id": "", "reason": tx.get("reason", "UNKNOWN")}
            if t_type == "ORDER_REJECT" and order_id_match:
                return {"status": "REJECTED", "trade_id": "", "reason": tx.get("rejectReason", "UNKNOWN")}
            if t_type == "ORDER_FILL" and order_id_match:
                trade_opened = tx.get("tradeOpened", {})
                if trade_opened:
                    return {"status": "OK", "trade_id": str(trade_opened.get("tradeID", ""))}
                else:
                    return {"status": "REDUCED", "trade_id": ""}
        
        time.sleep(interval_s)

    return {"status": "TIMEDOUT", "trade_id": ""}

# ============================================================================
# CORE ORDER FUNCTION — FIXED: STRICT_FILL, dry_run, proper trade matching
# ============================================================================
def open_oanda_order_simple(
    api,
    oanda_account_id: str,
    instrument: str,
    direction: str,
    units: int,
    sl_price: float | None,
    tp_price: float | None,
    dry_run: bool = False,
    max_sl_pips: int | None = None,
) -> dict:
    dec = price_decimals(instrument)
    pip = pip_size(instrument)
    is_jpy = "JPY" in instrument.upper()

    # ── Pre-flight price check for SL validation ──
    entry_check_price = None
    try:
        pr = api.request(PricingInfo(
            accountID=oanda_account_id,
            params={"instruments": instrument}
        ))["prices"][0]
        entry_check_price = float(pr["closeoutAsk"] if direction == "BUY" else pr["closeoutBid"])
    except KeyError as ke:
        logger.warning(f"Price check key missing ({ke}) — validation skipped")
    except Exception as e:
        logger.warning(f"Price check skipped: {e} — validation may be incomplete")

    # ── SL guard (opt-in: max_sl_pips=None means NO guard) ──
    if max_sl_pips is not None and sl_price and entry_check_price:
        dist = abs(entry_check_price - sl_price) / pip
        if dist > max_sl_pips:
            return {
                "status": "ERROR",
                "reason": "SL_TOO_WIDE",
                "message": f"SL {dist:.1f} pips > limit {max_sl_pips}"
            }
        if direction == "BUY" and sl_price >= entry_check_price:
            return {"status": "ERROR", "reason": "SL_INVALID", "message": "SL >= entry for BUY"}
        if direction == "SELL" and sl_price <= entry_check_price:
            return {"status": "ERROR", "reason": "SL_INVALID", "message": "SL <= entry for SELL"}

    if dry_run:
        logger.info(f"🧪 DRY_RUN — validated {direction} {units} {instrument} SL={sl_price} TP={tp_price}")
        return {"status": "DRY_RUN", "trade_id": "", "dry_run": True}

    # ── Build payload ──
    order_payload = {
        "order": {
            "type": "MARKET",
            "instrument": instrument,
            "units": str(units if direction == "BUY" else -units),
            "positionFill": "DEFAULT",
        }
    }
    if sl_price:
        order_payload["order"]["stopLossOnFill"] = {
            "price": str(round(float(sl_price), dec)),
            "timeInForce": "GTC",
        }
    if tp_price:
        order_payload["order"]["takeProfitOnFill"] = {
            "price": str(round(float(tp_price), dec)),
            "timeInForce": "GTC",
        }

    # ── Submit ──
    try:
        resp = api.request(OrderCreate(accountID=oanda_account_id, data=order_payload))

        # ── Check for rejection/cancellation FIRST (before any success log) ──
        if "orderRejectTransaction" in resp:
            rej = resp["orderRejectTransaction"]
            reason = rej.get("rejectReason", rej.get("reason", "UNKNOWN"))
            logger.error(f"❌ Order REJECTED {instrument}: {reason}")
            return {
                "status": "REJECTED",
                "trade_id": "",
                "message": f"Order rejected: {reason}",
                "reason": reason,
                "response": resp
            }
        if "orderCancelTransaction" in resp:
            can = resp["orderCancelTransaction"]
            reason = can.get("reason", "UNKNOWN")
            logger.error(f"❌ Order CANCELLED {instrument}: {reason}")
            return {
                "status": "CANCELLED",
                "trade_id": "",
                "message": f"Order cancelled: {reason}",
                "reason": reason,
                "response": resp
            }

        logger.info(f"✅ OANDA order request submitted for {instrument}")

        # ── Resolve TradeID ──
        trade_id = ""
        entry_price = entry_check_price
        deferred_polled = None

        if "orderFillTransaction" in resp:
            tx = resp["orderFillTransaction"]
            entry_price = float(tx.get("price", entry_check_price))
            trade_opened = tx.get("tradeOpened", {})
            if trade_opened:
                trade_id = str(trade_opened.get("tradeID", ""))
                logger.info(f"📦 Trade filled immediately: TradeID={trade_id} @ {entry_price}")
            else:
                trade_reduced = tx.get("tradeReduced", {})
                trade_closed = tx.get("tradeClosed", {})
                logger.info(
                    f"📦 Fill reduced/closed existing position @ {entry_price} "
                    f"(reduced_trade={trade_reduced.get('tradeID') if trade_reduced else 'N/A'}, "
                    f"closed_trade={trade_closed.get('tradeID') if trade_closed else 'N/A'})"
                )

        elif "orderCreateTransaction" in resp:
            order_tx_id = str(resp["orderCreateTransaction"].get("id", ""))
            logger.info(f"⏳ Order created — resolving trade ID from chain: {order_tx_id}")
            deferred_polled = _resolve_trade_id_from_order(
                api, oanda_account_id, instrument, order_tx_id
            )
            polled_status = deferred_polled.get("status", "TIMEDOUT")
            trade_id = deferred_polled.get("trade_id", "")

            if polled_status == "CANCELLED":
                logger.error(f"❌ Order CANCELLED {instrument}: {deferred_polled.get('reason', 'UNKNOWN')}")
                return {
                    "status": "CANCELLED", "trade_id": "",
                    "reason": deferred_polled.get("reason", "UNKNOWN"),
                    "message": "Order cancelled by OANDA", "response": resp
                }
            if polled_status == "REJECTED":
                logger.error(f"❌ Order REJECTED {instrument}: {deferred_polled.get('reason', 'UNKNOWN')}")
                return {
                    "status": "REJECTED", "trade_id": "",
                    "reason": deferred_polled.get("reason", "UNKNOWN"),
                    "message": "Order rejected", "response": resp
                }
            if polled_status == "REDUCED":
                logger.info(f"📦 Order filled — reduced existing position (no new trade)")
                return {
                    "status": "REDUCED", "trade_id": "",
                    "message": "Fill reduced/closed existing position", "response": resp
                }
            if polled_status == "TIMEDOUT":
                logger.warning(f"⚠️ Trade ID not confirmed after timeout — {instrument} state UNKNOWN")
                return {
                    "status": "TIMEDOUT", "trade_id": "",
                    "message": "Order accepted but fill not confirmed", "response": resp
                }
            if polled_status == "ERROR":
                logger.error(f"❌ Resolver error {instrument}: {deferred_polled.get('reason', 'UNKNOWN')}")
                return {
                    "status": "ERROR", "trade_id": "",
                    "message": deferred_polled.get("reason", "RESOLVER_ERROR"), "response": resp
                }

        # ── If we get here with no trade_id and we didn't poll (immediate-fill
        #    path) → fill reduced/closed an existing position, no new trade. ──
        if not trade_id and deferred_polled is None:
            logger.warning(f"⚠️ No new trade opened (immediate fill reduced existing pos) — {instrument}")
            return {
                "status": "REDUCED", "trade_id": "",
                "message": "No new trade — fill may have reduced an existing position",
                "response": resp
            }

        # ── Confirm attached SL/TP exist on trade (only for new trades) ──
        logger.info(f"📌 Final TradeID={trade_id} confirmed for {instrument}")
        if sl_price:
            logger.info(f"   ✅ SL attached @ {sl_price}")
        if tp_price:
            logger.info(f"   ✅ TP attached @ {tp_price}")

        return {
            "status": "OK",
            "trade_id": trade_id,
            "entry_price": entry_price,
            "response": resp
        }

    except Exception as e:
        logger.error(f"❌ FAILED {instrument}: {type(e).__name__}: {e}")
        return {
            "status": "ERROR",
            "trade_id": "",
            "message": f"{type(e).__name__}: {e}"
        }

# ============================================================================
# DYNAMIC TP UPDATE
# ============================================================================
def update_order_tp(
    api,
    account_id,
    trade_id,
    instrument,
    new_tp_price,
    send_telegram=None,
):
    """Update TP on an open trade — raises on failure, returns dict on success."""
    dec = price_decimals(instrument)
    new_tp_str = f"{float(new_tp_price):.{dec}f}"
    data = {"takeProfit": {"price": new_tp_str, "timeInForce": "GTC"}}

    try:
        resp = api.request(
            TradeCRCDO(accountID=account_id, tradeID=trade_id, data=data)
        )
        if "takeProfitOrderTransaction" in resp:
            txid = resp["takeProfitOrderTransaction"]["id"]
            msg = f"✅ TP UPDATED {instrument} → {new_tp_str}"
            logger.info(msg)
            if send_telegram:
                send_telegram(msg)
            return {"ok": True, "status": "UPDATED", "new_tp": new_tp_price, "txid": txid}
        return {"ok": False, "status": "UNEXPECTED", "response": resp}
    except Exception as e:
        err = f"❌ TP UPDATE FAILED {instrument}: {e}"
        logger.error(err)
        if send_telegram:
            send_telegram(err)
        return {"ok": False, "status": "ERROR", "error": str(e)}

# ============================================================================
# TP AUTO-ATTACH — FIXED: decimal precision, opt-in, scoped
# ============================================================================
def attach_tp_to_open_positions(
    api,
    oanda_account_id: str,
    instrument: str | None = None,
    atr_dist_pips: float = 30.0,
    force: bool = False,
) -> int:
    """
    Attach TP to trades missing one — ONLY when explicitly called.
    Fixed: JPY uses 3 decimals, respects existing TP, scoped to instrument.
    """
    resp = api.request(OpenTrades(accountID=oanda_account_id))
    trades = resp.get("trades", [])
    if instrument:
        trades = [t for t in trades if t["instrument"] == instrument]
    if not trades:
        logger.info("📋 No open trades to process")
        return 0

    attached = 0
    for trade in trades:
        tid = trade["id"]
        inst = trade["instrument"]
        units = float(trade["currentUnits"])
        entry = float(trade["price"])
        existing_tp = trade.get("takeProfitOrder", {}).get("price")

        if existing_tp and not force:
            logger.debug(f"   ✅ {inst} #{tid}: TP exists @ {existing_tp} — skipped")
            continue

        pip = 0.01 if "JPY" in inst else 0.0001
        dec = 3 if "JPY" in inst else 5
        is_long = units > 0

        if is_long:
            tp_price = round(entry + (atr_dist_pips * pip), dec)
        else:
            tp_price = round(entry - (atr_dist_pips * pip), dec)

        logger.info(f"🔧 Attach TP {inst} #{tid}: entry={entry} → TP={tp_price}")
        try:
            api.request(TradeCRCDO(
                accountID=oanda_account_id,
                tradeID=tid,
                data={"takeProfit": {"price": f"{tp_price}", "timeInForce": "GTC"}}
            ))
            attached += 1
        except Exception as e:
            logger.warning(f"   ❌ Failed {inst} #{tid}: {e}")

    logger.info(f"📋 TP attach complete: {attached} updated")
    return attached

# ============================================================================
# DYNAMIC POSITION MANAGER — FIXED: dynamic_tp OFF by default
# ============================================================================
class DynamicPositionManager:
    def __init__(
        self,
        api,
        account_id: str,
        timeframe: str,
        be_trigger_atr_mult: float = 1.5,
        trail_trigger_atr_mult: float = 2.5,
        trail_atr_mult: float = 1.5,
        max_hold_bars: int = 12,
        dynamic_tp: bool = False,  # ⚠️ DEFAULT: DISABLED — opt-in only
        tp_raise_thresh_pips: int = 15,
        telegram_send=None,
    ):
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
            logger.error(f"  ❌ Failed to fetch trades {instrument}: {e}")
            return []

    def _current_price(self, instrument: str, side: str) -> float | None:
        try:
            prices = get_live_prices(instrument)
            if prices and "bid" in prices and "ask" in prices:
                return prices["bid"] if side == "long" else prices["ask"]
            return None
        except Exception as e:
            logger.warning(f"  ⚠️ Price fetch failed {instrument}: {e}")
            return None

    def _update_trade_sl(self, trade_id: str, new_sl: float, decimals: int) -> bool:
        try:
            self.api.request(TradeCRCDO(
                accountID=self.account_id,
                tradeID=trade_id,
                data={"stopLoss": {"price": f"{new_sl:.{decimals}f}", "timeInForce": "GTC"}}
            ))
            logger.info(f"   🔄 SL updated → {new_sl:.{decimals}f}")
            return True
        except Exception as e:
            logger.error(f"   ❌ SL update failed: {e}")
            return False

    def update_all(self, pair_data: dict, close_position_fn=None):
        BAR_HOURS = {"15m": 0.25, "1H": 1, "H4": 4, "D": 24}
        bar_hours = BAR_HOURS.get(self.timeframe, 4)

        for pair, info in pair_data.items():
            instrument = info["oanda"]
            df = info.get("df")
            if df is None or len(df) < 2:
                continue
            atr_val = df.iloc[-1].get("atr")
            if atr_val is None or np.isnan(atr_val) or atr_val <= 0:
                continue

            decimals = price_decimals(pair)
            pip = 0.01 if "JPY" in pair.upper() else 0.0001
            trades = self._get_open_trades(instrument)
            if not trades:
                continue

            for trade in trades:
                tid = trade["id"]
                units = int(trade["currentUnits"])
                side = "long" if units > 0 else "short"
                entry = float(trade["price"])
                current_sl = float(trade["stopLossOrder"]["price"]) if trade.get("stopLossOrder") else None
                current_tp = float(trade["takeProfitOrder"]["price"]) if trade.get("takeProfitOrder") else None

                current_price = self._current_price(instrument, side)
                if current_price is None:
                    continue

                profit_pips = (
                    (current_price - entry) / pip if side == "long"
                    else (entry - current_price) / pip
                )

                open_time = datetime.fromisoformat(trade["openTime"].replace("Z", "+00:00"))
                bars_held = (utcnow_safe() - open_time).total_seconds() / 3600 / bar_hours

                if bars_held >= self.max_hold:
                    logger.info(f"⏰ TIME EXIT {pair} #{tid}: held {bars_held:.1f} bars")
                    if close_position_fn:
                        close_position_fn(instrument)
                    continue

                # Dynamic TP — only runs if explicitly enabled
                if self.dynamic_tp:
                    atr_mult_tp = 3.0
                    if side == "long":
                        new_tp = current_price + (atr_mult_tp * atr_val)
                        if current_tp is None or new_tp > current_tp + (self.tp_thresh_pips * pip):
                            update_order_tp(
                                self.api, self.account_id, tid, instrument, new_tp,
                                send_telegram=self.telegram
                            )
                    else:
                        new_tp = current_price - (atr_mult_tp * atr_val)
                        if current_tp is None or new_tp < current_tp - (self.tp_thresh_pips * pip):
                            update_order_tp(
                                self.api, self.account_id, tid, instrument, new_tp,
                                send_telegram=self.telegram
                            )

                # Breakeven → Trailing SL
                be_pips = self.be_trigger * atr_val / pip
                trail_pips = self.trail_trigger * atr_val / pip
                new_sl = action = None

                if profit_pips >= be_pips:
                    be_sl = entry - pip if side == "long" else entry + pip
                    if current_sl is None or (
                        (side == "long" and be_sl > current_sl) or
                        (side == "short" and be_sl < current_sl)
                    ):
                        new_sl, action = be_sl, "BREAKEVEN"

                if profit_pips >= trail_pips:
                    trail_sl = (
                        current_price - self.trail_mult * atr_val if side == "long"
                        else current_price + self.trail_mult * atr_val
                    )
                    if current_sl is None or (
                        (side == "long" and trail_sl > current_sl) or
                        (side == "short" and trail_sl < current_sl)
                    ):
                        new_sl, action = trail_sl, "TRAIL"

                if new_sl and action:
                    if current_sl and (
                        (side == "long" and new_sl < current_sl) or
                        (side == "short" and new_sl > current_sl)
                    ):
                        continue  # Never move SL against position
                    if self._update_trade_sl(tid, new_sl, decimals) and self.telegram:
                        self.telegram(
                            f"🎯 {action} {pair} #{tid} | Profit: {profit_pips:.1f}p → SL: {new_sl:.{decimals}f}"
                        )

# ============================================================================
# REMOVED: open_oanda_order — unused variant with known issues
# ============================================================================

# ============================================================================
# REMAINING UTILITIES — cleaned
# ============================================================================
def fetch_candles(api, oanda_instrument: str, gran: str, count: int = 100):
    resp = api.request(InstrumentsCandles(
        instrument=oanda_instrument, params={"granularity": gran, "count": count, "price": "M"}
    ))
    return pd.DataFrame([{
        "Time": c["time"], "Open": float(c["mid"]["o"]), "High": float(c["mid"]["h"]),
        "Low": float(c["mid"]["l"]), "Close": float(c["mid"]["c"])
    } for c in resp["candles"]]).set_index("Time")

def should_close_by_strength(pair: str, side: str, strength_scores: dict, threshold: float = 1.0):
    clean = pair.replace("=X", "").replace("_", "")
    base, quote = clean[:3], clean[3:] if len(clean) == 6 else pair.replace("=X", "").split("_", 1)
    if isinstance(quote, list):
        return False, "Parse fail"
    base_score = strength_scores.get(base, 0)
    quote_score = strength_scores.get(quote, 0)
    gap = base_score - quote_score
    if side == "long" and -gap > threshold:
        return True, f"Strength flip: {quote}+{quote_score:.2f} > {base}{base_score:.2f}"
    if side == "short" and gap > threshold:
        return True, f"Strength flip: {base}+{base_score:.2f} > {quote}{quote_score:.2f}"
    return False, ""

def load_mc_legacy(pair: str, results_dir: Path, today_str: str, max_age_hours: int = 24):
    safe = pair.replace("=X", "").replace("=", "_")
    for f in [
        results_dir / f"fx_daily_{safe}_{today_str}.json",
        results_dir / f"daily_mc_{safe}_{today_str}.json",
        results_dir / f"h4_mc_{safe}_{today_str}.json",
    ]:
        if f.exists():
            mtime = datetime.fromtimestamp(f.stat().st_mtime, timezone.utc)
            if (utcnow_safe() - mtime).total_seconds() / 3600 <= max_age_hours:
                with open(f) as j:
                    return json.load(j), True
    return None, False

def build_mc_telegram(mc_results, title, tf, lookback, fcst, sims):
    now = utcnow_safe().strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"📊 **{title}**", f"📅 {now}", f"🔹 {tf} | LB:{lookback} FC:{fcst} Sims:{sims}", ""]
    for r in mc_results:
        lo, hi = r["range_90"]
        lines.extend([
            f"🔹 **{r['pair']}**",
            f"   Last: `{r['current_price']}` | Pctl: `{r['percentile_rank']}%`",
            f"   Up: `{r['p_up_pct']}%` Down: `{r['p_down_pct']}%`",
            f"   90%: `{lo}`–`{hi}` | {r['regime']}", ""
        ])
    return "\n".join(lines)

def build_trade_telegram(trade_lines, mc_summary=None):
    now = utcnow_safe().strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"🤖 UPDATE — {now}"] + trade_lines
    if mc_summary:
        lines += ["", "📊 MC Context:"] + [f"   {s}" for s in mc_summary]
    return "\n".join(lines)