import logging
import json
import contextlib
from datetime import datetime, timezone
import pandas as pd
import numpy as np
import oandapyV20.endpoints.orders as orders
from oandapyV20.endpoints.positions import PositionDetails
from oandapyV20.endpoints.trades import Trades, TradeCRCDO, OpenTrades
from oandapyV20 import API
from fx.data.market import price_decimals, pip_size

logger = logging.getLogger(__name__)

def attach_tp_to_open_positions(engine, instrument=None, dry_run: bool = False):
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
        if instrument and inst != instrument:
            continue
        current_tp = trade.get("takeProfitOrder", {}).get("price")
        units = float(trade["currentUnits"])
        entry_price = float(trade["price"])

        if current_tp:
            logger.debug(f"   ✅ {inst} Trade {tid}: TP already exists @ {current_tp}")
            continue

        # Calculate FIXED TP based on direction + ATR distance
        is_short = units < 0
        pip = pip_size(inst)
        dec = price_decimals(inst)
        dist = atr_dist_pips * pip

        if is_short:
            tp_price = round(entry_price - dist, dec)
            dir_label = "SHORT → TP BELOW"
        else:
            tp_price = round(entry_price + dist, dec)
            dir_label = "LONG → TP ABOVE"

        logger.info(
            f"🔧 ATTACH TP {inst} Trade {tid} | {dir_label} | Entry={entry_price} → TP={tp_price}"
        )

        # Send TP update to OANDA
        data = {"takeProfit": {"price": f"{tp_price}", "timeInForce": "GTC"}}
        if dry_run:
            logger.info(
                f"🧊 DRY-RUN — would ATTACH TP: {inst} trade={tid} → {tp_price}"
            )
            attached_count += 1
            continue
        try:
            client.request(TradeCRCDO(account_id, tid, data=data))
            attached_count += 1
            logger.info(f"   ✅ TP ATTACHED for {inst} @ {tp_price}")
        except Exception as e:
            logger.warning(f"   ❌ Failed: {e}")

    logger.info(f"📋 TP Attach Summary: {attached_count} positions updated with TP")
    return attached_count

def get_open_position(api, oanda_account_id: str, instrument: str):
    """Get current open position for an instrument.
    Returns None if no position exists, else dict: {"units": int, "side": "long"/"short"}
    """
    try:
        resp = api.request(
            PositionDetails(accountID=oanda_account_id, instrument=instrument)
        )
        pos = resp.get("position", {})
        long_units = pos.get("long", {}).get("units", "0")
        short_units = pos.get("short", {}).get("units", "0")

        if long_units != "0":
            return {"units": int(long_units), "side": "long"}
        if short_units != "0":
            return {"units": -int(short_units), "side": "short"}
        return None

    except Exception as e:
        err_text = str(e)
        if "NO_SUCH_POSITION" in err_text or "404" in err_text:
            logger.info("%s: No open position", instrument)
            return None
        logger.warning("Position check failed for %s: %s", instrument, err_text[:120])
        return None

def close_position(
    api, oanda_account_id: str, instrument: str, telegram_send=None, dry_run=False
):
    """Close existing position for instrument."""
    if dry_run:
        logger.info(f"🧊 DRY-RUN — would CLOSE: {instrument}")
        return
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

def open_oanda_order_simple(
    api,
    oanda_account_id: str,
    instrument: str,
    direction: str,
    units: int,
    sl_price: float,
    tp_price: float,
    tag: str = "",
    client_id: str = "",
    comment: str = "",
    dry_run: bool = False,
    max_confirm_wait: float = 5.0,
    retry_interval: float = 0.8,
) -> dict:
    import time as _time
    from oandapyV20.endpoints.orders import OrderCreate
    from oandapyV20.endpoints.trades import TradeClientExtensions

    dec = price_decimals(instrument)
    side = "BUY" if direction.upper() == "BUY" else "SELL"
    signed_units = str(abs(units) if side == "BUY" else -abs(units))

    if dry_run:
        logger.info(
            f"🧊 DRY-RUN — would OPEN: {instrument} {side} | SL={sl_price:.{dec}f} TP={tp_price:.{dec}f}"
        )
        return {
            "ok": True,
            "status": "DRY_RUN",
            "instrument": instrument,
            "direction": direction,
        }

    client_extensions = {}
    if client_id:
        client_extensions["id"] = client_id
    if tag:
        client_extensions["tag"] = tag
    if comment:
        client_extensions["comment"] = comment

    order_payload = {
        "order": {
            "type": "MARKET",
            "instrument": instrument,
            "units": signed_units,
            "positionFill": "DEFAULT",
        }
    }
    if client_extensions:
        order_payload["order"]["clientExtensions"] = client_extensions

    try:
        resp = api.request(OrderCreate(accountID=oanda_account_id, data=order_payload))
    except Exception as e:
        logger.error(f"❌ HTTP error placing MARKET order {instrument}: {e}")
        return {"ok": False, "status": "NETWORK_ERROR", "error": str(e)}

    # ── 1) Reject ──────────────────────────────────────────────────
    if "orderRejectTransaction" in resp:
        r = resp["orderRejectTransaction"]
        reason = r.get("rejectReason", "UNKNOWN")
        msg = r.get("errorMessage", "No message")
        logger.error(f"❌ OANDA REJECT {instrument}: reason={reason} | {msg}")
        return {"ok": False, "status": "REJECTED", "error": f"{reason}: {msg}"}

    # ── 2) Cancel (order created but never filled) ─────────────────
    if "orderCancelTransaction" in resp:
        c = resp["orderCancelTransaction"]
        reason = c.get("reason", c.get("type", "UNKNOWN"))
        try:
            reason = c.get("rejectReason", reason)
        except Exception:
            pass
        logger.error(
            f"❌ OANDA CANCEL {instrument}: reason={reason} "
            f"(order was created but never filled — check margin/account state)"
        )
        return {
            "ok": False,
            "status": "CANCELED",
            "error": f"{reason}: order never filled",
        }

    # ── 3) Fill (the ONLY path where we have a real tradeID) ──────
    trade_id = ""
    trade_opened = {}
    if "orderFillTransaction" in resp:
        fill = resp["orderFillTransaction"]
        trade_opened = fill.get("tradeOpened", {})
        trade_closed = fill.get("tradeClosed", {})
        trade_reduced = fill.get("tradeReduced", {})

        trade_id = str(trade_opened.get("tradeID", ""))
        if trade_closed:
            logger.info(f"📦 Fill also closed existing trade: {trade_closed}")
        if trade_reduced:
            logger.info(f"📦 Fill also reduced trade: {trade_reduced}")

    if not trade_id:
        logger.error(
            f"❌ No tradeID after MARKET order! "
            f"Response keys: {list(resp.keys())}. Full resp: {resp}"
        )
        return {
            "ok": False,
            "status": "NO_TRADE",
            "error": f"No trade opened. Keys: {list(resp.keys())}",
        }

    logger.info(f"📦 Trade filled! TradeID={trade_id} | instrument={instrument}")

    # ── 4) Confirm trade visible (live env race-condition protection) ─
    logger.info(f"⏳ Confirming trade T{trade_id} is visible...")
    trade_confirmed = False
    deadline = _time.monotonic() + max_confirm_wait
    last_verify_err = None
    while _time.monotonic() < deadline:
        try:
            # Reuse TradeList endpoint via the account — simplest portable check
            from oandapyV20.endpoints.trades import TradesList

            verify_resp = api.request(TradesList(accountID=oanda_account_id))
            existing_ids = [str(t.get("id", "")) for t in verify_resp.get("trades", [])]
            if trade_id in existing_ids:
                trade_confirmed = True
                break
        except Exception as ve:
            last_verify_err = str(ve)
        _time.sleep(retry_interval)

    if not trade_confirmed:
        logger.warning(
            f"⚠️ Trade T{trade_id} not visible after {max_confirm_wait}s — "
            f"proceeding anyway (may be a race condition). last_err={last_verify_err}"
        )
    else:
        logger.info(f"✅ Trade T{trade_id} confirmed visible on account")

    # ── 5) Attach metadata (with retry for live env) ───────────────
    if client_extensions:
        for attempt in range(3):
            try:
                api.request(
                    TradeClientExtensions(
                        accountID=oanda_account_id,
                        tradeID=trade_id,
                        data={"clientExtensions": client_extensions},
                    )
                )
                logger.info(f"🏷️ Trade T{trade_id} tagged: id={client_id}")
                break
            except Exception as ce:
                if attempt < 2 and "TRADE_DOESNT_EXIST" in str(ce):
                    logger.warning(
                        f"⚠️ Metadata attach attempt {attempt+1} failed (race) — retrying in {retry_interval}s"
                    )
                    _time.sleep(retry_interval)
                else:
                    logger.warning(f"⚠️ Failed to set trade metadata: {ce}")

    # ── 6) Stop Loss (with retry) ──────────────────────────────────
    if sl_price is not None:
        for attempt in range(3):
            try:
                api.request(
                    OrderCreate(
                        accountID=oanda_account_id,
                        data={
                            "order": {
                                "type": "STOP_LOSS",
                                "tradeID": trade_id,
                                "price": f"{float(sl_price):.{dec}f}",
                                "timeInForce": "GTC",
                            }
                        },
                    )
                )
                logger.info(f"✅ SL set at {sl_price}")
                break
            except Exception as se:
                if attempt < 2 and "TRADE_DOESNT_EXIST" in str(se):
                    logger.warning(
                        f"⚠️ SL attach attempt {attempt+1} failed (race) — retrying in {retry_interval}s"
                    )
                    _time.sleep(retry_interval)
                else:
                    logger.error(f"❌ Failed to set SL: {se}")

    # ── 7) Take Profit (with retry) ───────────────────────────────
    if tp_price is not None:
        for attempt in range(3):
            try:
                api.request(
                    OrderCreate(
                        accountID=oanda_account_id,
                        data={
                            "order": {
                                "type": "TAKE_PROFIT",
                                "tradeID": trade_id,
                                "price": f"{tp_price:.{dec}f}",
                                "timeInForce": "GTC",
                            }
                        },
                    )
                )
                logger.info(f"✅ TP set at {tp_price}")
                break
            except Exception as te:
                if attempt < 2 and "TRADE_DOESNT_EXIST" in str(te):
                    logger.warning(
                        f"⚠️ TP attach attempt {attempt+1} failed (race) — retrying in {retry_interval}s"
                    )
                    _time.sleep(retry_interval)
                else:
                    logger.error(f"❌ Failed to set TP: {te}")

    return {
        "ok": True,
        "status": "OK",
        "trade_id": trade_id,
        "tag": tag,
        "client_id": client_id,
        "comment": comment,
        "response": resp,
    }

def open_oanda_order(
    signal: dict,
    units: int,
    current_price: float,
    api,
    oanda_account_id: str,
    oanda_token: str,
    trailing_tp: bool = False,
    dynamic_tp: bool = False,
    max_sl_pips: int = None,
    max_sl_pct: float = 0.03,
    telegram_send=None,
    cfg=None,
    dry_run: bool = False,
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
        err = (
            f"SL GUARD BLOCKED {pair_raw}: SL={sl} is {sl_pips:.0f} pips / {sl_pct:.1%} from entry. "
            f"Max allowed: {max_sl_pips} pips / {max_sl_pct:.1%}"
        )
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

    if dry_run:
        logger.info(
            f"🧊 DRY-RUN — would OPEN: {pair_raw} {action} | SL={sl:.{dec}f} TP={tp:.{dec}f}"
        )
        return {
            "ok": True,
            "status": "DRY_RUN",
            "instrument": pair_raw,
            "direction": action,
        }

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
            entry_price = float(
                resp["orderFillTransaction"].get("price", current_price)
            )
            logger.info(f"📦 Trade opened: TradeID={trade_id} @ {entry_price}")
        elif "orderCreateTransaction" in resp:
            trade_id = str(resp["orderCreateTransaction"].get("id", ""))
            logger.info(f"📦 Order created: OrderID={trade_id}")
        else:
            logger.warning(
                f"⚠️ Could not find TradeID! Response keys: {list(resp.keys())}"
            )

        # ✅ ONLY proceed if we have a valid TradeID
        if not trade_id:
            logger.error("❌ Cannot create SL/TP — TradeID is EMPTY!")
        else:
            # ✅ STEP 2: Create SL ORDER separately
            if sl is not None:
                sl_data = {
                    "order": {
                        "type": "STOP_LOSS",
                        "tradeID": trade_id,
                        "price": str(round(float(sl), dec)),
                        "timeInForce": "GTC",
                    }
                }
                try:
                    api.request(OrderCreate(accountID=oanda_account_id, data=sl_data))
                    logger.info(f"   ✅ SL ORDER created: {sl}")
                except Exception as e:
                    logger.warning(f"   ⚠️ SL order failed: {e}")

            # ✅ STEP 3: Create TP ORDER separately
            if not trailing_tp and tp is not None:
                if (action == "BUY" and tp > entry_price) or (
                    action == "SELL" and tp < entry_price
                ):
                    tp_data = {
                        "order": {
                            "type": "TAKE_PROFIT",
                            "tradeID": trade_id,
                            "price": str(round(float(tp), dec)),
                            "timeInForce": "GTC",
                        }
                    }
                    try:
                        api.request(
                            OrderCreate(accountID=oanda_account_id, data=tp_data)
                        )
                        logger.info(f"   ✅ TP ORDER created: {round(float(tp), dec)}")
                    except Exception as e:
                        logger.warning(f"   ⚠️ TP order failed: {e}")
        return {"status": "OK", "response": resp}

    except Exception as e:
        logger.error(f"❌ OANDA order failed for {pair_raw}: {e}")
        return {"status": "ERROR", "message": str(e)}

def update_order_tp(
    api,
    account_id,
    trade_id,
    instrument,
    new_tp_price: float,
    token=None,
    environment="practice",
    send_telegram=None,
    dry_run: bool = False,
):
    """
    Update Take-Profit on an OPEN TRADE (OANDA Trade API — correct approach).
    OANDA does NOT allow updating orders once filled — we update the TRADE's TP instead.
    Returns: {"ok": bool, "status": str, "old_tp": float, "new_tp": float}
    """
    from oandapyV20.endpoints.trades import TradeCRCDO

    try:
        dec = price_decimals(instrument)
        new_tp_str = f"{new_tp_price:.{dec}f}"

        if dry_run:
            logger.info(
                f"🧊 DRY-RUN — would RAISE TP: {instrument} trade={trade_id} → {new_tp_str}"
            )
            return {"ok": True, "status": "DRY_RUN", "new_tp": new_tp_price}

        # ✅ OANDA: Update TP on the TRADE (not the order — orders are immutable once filled)
        data = {"takeProfit": {"price": new_tp_str, "timeInForce": "GTC"}}

        logger.info(f"🔄 Updating TP: {instrument} trade {trade_id} → {new_tp_str}")
        r = TradeCRCDO(accountID=account_id, tradeID=trade_id, data=data)
        resp = api.request(r)

        if "takeProfitOrderTransaction" in resp:
            txid = resp["takeProfitOrderTransaction"]["id"]
            msg = f"✅ TP UPDATED {instrument} → {new_tp_str} (TxID: {txid})"
            logger.info(msg)
            if send_telegram:
                send_telegram_message(msg)
            return {
                "ok": True,
                "status": "UPDATED",
                "new_tp": new_tp_price,
                "txid": txid,
            }
        else:
            logger.warning(f"⚠️ Unexpected TP update response: {resp}")
            return {"ok": False, "status": "UNEXPECTED", "response": resp}

    except Exception as e:
        err = f"❌ TP UPDATE FAILED {instrument}: {type(e).__name__}: {e}"
        logger.error(err)
        if send_telegram:
            send_telegram_message(err)
        return {"ok": False, "status": "ERROR", "error": str(e)}

