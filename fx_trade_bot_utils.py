# fx_trade_bot_utils.py — Shared Helpers Extracted from v6.1 + Dynamic TP
# Contains: Cooldown, Market Check, Position Helpers, Order Helpers, Telegram Builders, Strength Close, MC Loader, Dynamic TP

import json
import logging
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from telegram_message import send_telegram_message
from utils.strategy_helpers import get_live_prices
from oandapyV20.endpoints.instruments import InstrumentsCandles
from oandapyV20.endpoints.positions import PositionDetails
from oandapyV20.endpoints.orders import OrderCreate
from oandapyV20.endpoints.trades import OpenTrades, TradeCRCDO

logger = logging.getLogger(__name__)
# logging.getLogger("oandapyV20").setLevel(logging.WARNING)

# ==================================================
# 🛡️ STOP-LOSS RULES — LOCKED — v6.x+ IMMUTABLE
# RULES:
#   SELL → SL = max(4 closed H4 highs) + 20 pips
#   BUY  → SL = min(4 closed H4 lows) - 20 pips
#   MAX  → >200 pips → ABORT TRADE
# ==================================================
SL_OFFSET_PIPS = 20  # Buffer from extreme levels — LOCKED
SL_MAX_ALLOWED_PIPS = 200  # Max allowed distance — adjust later if needed
REQUIRED_H4_CANDLES = 4  # Only fully closed H4 — LOCKED


# ──────────────────────────────────────────────────────────────────────
# ✅ HYBRID SL: H4 PRIMARY + ATR GUARD — ALWAYS PICK CLOSER-TO-ENTRY
# ──────────────────────────────────────────────────────────────────────
def calculate_hybrid_sl(instrument, direction, entry_price, h4_closed, atr_value, pip_sz):
    """
    Unified Hybrid SL — same logic for NEW orders + EXISTING positions
    Returns: (final_sl_price, h4_sl, atr_sl, chosen_source, total_pips, skip_trade)

    Args:
        instrument: OANDA instrument name (e.g. 'EUR_USD', 'USD_JPY') — used for decimal detection
        direction: 'BUY' or 'SELL'
        entry_price: estimated entry price
        h4_closed: list of fully closed H4 candles [{'high':x,'low':y}, ...]
        atr_value: ATR value for ATR guard calculation
        pip_sz: pip size (0.0001 non-JPY, 0.01 JPY, etc.)
    """
    decimals = price_decimals(instrument)

    # Step 1: Calculate H4 Zone Hierarchy SL
    try:
        h4_sl, h4_pips, h4_skip = calculate_stop_loss(
            direction, entry_price, h4_closed, pip_sz
        )
        h4_sl = round(h4_sl, decimals)
    except Exception:
        logger.exception("H4 SL calculation failed for %s — falling back to ATR guard", instrument)
        h4_sl = h4_pips = h4_skip = None

    # Step 2: Calculate ATR Guard SL (ATR × 2.0)
    try:
        atr_offset = atr_value * 2.0
        if direction == "BUY":
            atr_sl = round(entry_price - atr_offset, decimals)
        else:  # SELL
            atr_sl = round(entry_price + atr_offset, decimals)
        atr_pips = atr_offset / pip_sz
        atr_skip = atr_pips > SL_MAX_ALLOWED_PIPS
    except Exception:
        logger.exception("ATR guard SL calculation failed for %s — falling back to H4", instrument)
        atr_sl = atr_pips = atr_skip = None

    # Step 3: Fallback Logic — pick available
    if h4_sl is None and atr_sl is None:
        return None, None, None, "NONE", 0, True  # Skip — both failed

    if h4_sl is None:
        final_sl = atr_sl
        chosen = "ATR"
        final_pips = atr_pips
        skip_trade = atr_skip
    elif atr_sl is None:
        final_sl = h4_sl
        chosen = "H4"
        final_pips = h4_pips
        skip_trade = h4_skip
    else:
        # ✅ BOTH AVAILABLE → ALWAYS PICK THE CLOSER (more conservative)
        if direction == "BUY":
            # BUY: higher SL = closer to entry = tighter
            if h4_sl >= atr_sl:
                final_sl = h4_sl
                chosen = "H4"
                final_pips = h4_pips
            else:
                final_sl = atr_sl
                chosen = "ATR-GUARD"
                final_pips = atr_pips
        else:  # SELL
            # SELL: lower SL = closer to entry = tighter
            if h4_sl <= atr_sl:
                final_sl = h4_sl
                chosen = "H4"
                final_pips = h4_pips
            else:
                final_sl = atr_sl
                chosen = "ATR-GUARD"
                final_pips = atr_pips
        skip_trade = final_pips > SL_MAX_ALLOWED_PIPS

    return final_sl, h4_sl, atr_sl, chosen, final_pips, skip_trade


def calculate_stop_loss(
    side: str, entry_price: float, h4_candles, pip_size: float, instrument: str = ""
) -> tuple[float, float, bool]:
    """
    Calculate Stop-Loss per H4 Zone Hierarchy + Max SL Cap

    ⚠️  CRITICAL: h4_candles must contain ONLY fully closed H4 candles
                 — ALWAYS exclude the current forming candle before calling

    Args:
        side: 'BUY' or 'SELL'
        entry_price: estimated entry price
        h4_candles: list of dicts — [{"high":x, "low":y}, ...]
        pip_size: 0.0001 (non-JPY) / 0.01 (JPY)

    Returns:
        (sl_price: float, sl_pips: float, skip_trade: bool)
    """

    # ─── Validate Candle Count ───
    if len(h4_candles) < REQUIRED_H4_CANDLES:
        raise ValueError(
            f"⚠️ H4 candle count insufficient: need ≥{REQUIRED_H4_CANDLES}, got {len(h4_candles)} — "
            "Did you forget to remove the forming candle? Use h4_data[:-1]"
        )

    # ─── Calculate SL per H4 Zone Hierarchy ───
    if side.upper() == "SELL":
        ref_level = max(c["high"] for c in h4_candles)
        sl_price = ref_level + (SL_OFFSET_PIPS * pip_size)
        sl_pips = (sl_price - entry_price) / pip_size  # positive value

    elif side.upper() == "BUY":
        ref_level = min(c["low"] for c in h4_candles)
        sl_price = ref_level - (SL_OFFSET_PIPS * pip_size)
        sl_pips = (entry_price - sl_price) / pip_size  # positive value

    else:
        raise ValueError(f"Invalid order side: '{side}' — use BUY or SELL")

    # ─── Enforce Max SL Cap ───
    _cap = _sl_cap_for(instrument)
    if sl_pips > _cap:
        skip_trade = True
        logger.warning(
            "SL TOO LARGE — TRADE ABORTED | Side: %s | Ref: %.5f | "
            "Entry: %.5f | SL: %.5f | Distance: %.1f pips | MAX ALLOWED: %s",
            side, ref_level, entry_price, sl_price, sl_pips, _cap,
        )
    else:
        skip_trade = False
        logger.info(
            "SL ACCEPTED | Side: %s | Ref: %.5f | Entry: %.5f | SL: %.5f | Distance: %.1f pips",
            side, ref_level, entry_price, sl_price, sl_pips,
        )

    return sl_price, sl_pips, skip_trade


# ✅ KEEP THIS — proper candle fetcher
def fetch_candles(api, oanda_instrument: str, gran: str, count: int = 100):
    """Fetch historical OHLC candles — returns clean DataFrame"""
    resp = api.request(
        InstrumentsCandles(
            instrument=oanda_instrument,
            params={"granularity": gran, "count": count, "price": "M"},
        )
    )
    df = pd.DataFrame(
        [
            {
                "Time": c["time"],
                "Open": float(c["mid"]["o"]),
                "High": float(c["mid"]["h"]),
                "Low": float(c["mid"]["l"]),
                "Close": float(c["mid"]["c"]),
            }
            for c in resp["candles"]
        ]
    ).set_index("Time")
    logger.debug(f"📊 Fetched {oanda_instrument} {gran} bars={len(df)}")
    return df


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


def close_position(api, oanda_account_id: str, instrument: str, telegram_send=None, dry_run=False):
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


# ✅ Drop-in replacement — matches YOUR call signature exactly
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
) -> dict:
    if dry_run:
        dec = price_decimals(instrument)
        logger.info(f"🧊 DRY-RUN — would OPEN: {instrument} {direction} | SL={sl_price:.{dec}f} TP={tp_price:.{dec}f}")
        return {"ok": True, "status": "DRY_RUN", "instrument": instrument, "direction": direction}

    from oandapyV20.endpoints.orders import OrderCreate
    from oandapyV20.endpoints.trades import TradeClientExtensions

    dec = price_decimals(instrument)

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
            "units": str(abs(units) if direction.upper() == "BUY" else -abs(units)),
            "positionFill": "DEFAULT",
        }
    }

    # Attach client extensions to order
    if client_extensions:
        order_payload["order"]["clientExtensions"] = client_extensions

    try:
        resp = api.request(
            OrderCreate(
                accountID=oanda_account_id,
                data=order_payload,
            )
        )

        logger.info(f"✅ OANDA accepted order for {instrument}")

        trade_id = ""

        if "orderFillTransaction" in resp:
            fill = resp["orderFillTransaction"]

            trade_opened = fill.get("tradeOpened", {})
            trade_id = str(trade_opened.get("tradeID", ""))

            logger.info(f"📦 Trade opened: TradeID={trade_id}")

        elif "orderCreateTransaction" in resp:
            trade_id = str(resp["orderCreateTransaction"].get("id", ""))

            logger.info(f"📦 Order created: OrderID={trade_id}")

        if not trade_id:
            return {
                "ok": False,
                "status": "ERROR",
                "error": "TradeID missing",
                "message": "TradeID missing",
            }

        # Attach tag directly to trade
        if client_extensions:
            try:
                api.request(
                    TradeClientExtensions(
                        accountID=oanda_account_id,
                        tradeID=trade_id,
                        data={"clientExtensions": client_extensions},
                    )
                )

                logger.info(
                    f"🏷️ Trade tagged: " f"tag={tag}, id={client_id}, comment={comment}"
                )

            except Exception as ce:
                logger.warning(f"⚠️ Failed to set trade metadata: {ce}")

        # Stop Loss
        if sl_price is not None:
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

        # Take Profit
        if tp_price is not None:
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

        return {
            "ok": True,
            "status": "OK",
            "trade_id": trade_id,
            "tag": tag,
            "client_id": client_id,
            "comment": comment,
            "response": resp,
        }

    except Exception as e:
        logger.error(f"❌ FAILED {instrument}: " f"{type(e).__name__}: {e}")

        return {
            "ok": False,
            "status": "ERROR",
            "error": str(e),
            "message": str(e),
        }


# ============================================================================
# ORDER EXECUTION WITH SAFETY CHECKS
# ============================================================================
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


# ============================================================================
# ✅ DYNAMIC TP UPDATE FUNCTION
# ============================================================================
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
            logger.info(f"🧊 DRY-RUN — would RAISE TP: {instrument} trade={trade_id} → {new_tp_str}")
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
def should_close_by_strength(
    pair: str, side: str, strength_scores: dict, threshold: float = 1.0
) -> tuple:
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
        return (
            True,
            f"Strength flip: {quote} (+{quote_score:.2f}) stronger than {base} ({base_score:.2f}), gap={-gap:.2f}",
        )
    if side == "short" and gap > threshold:
        return (
            True,
            f"Strength flip: {base} (+{base_score:.2f}) stronger than {quote} ({quote_score:.2f}), gap={gap:.2f}",
        )
    return False, ""


# ============================================================================
# LEGACY MC LOADER
# ============================================================================
def load_mc_legacy(
    pair: str, results_dir: Path, today_str: str, max_age_hours: int = 24
):
    """Load cached MC result from today's files if fresh enough."""
    safe = pair.replace("=X", "").replace("=", "_")
    for f in [
        results_dir / f"fx_daily_{safe}_{today_str}.json",
        results_dir / f"daily_mc_{safe}_{today_str}.json",
        results_dir / f"h4_mc_{safe}_{today_str}.json",
    ]:
        if f.exists():
            age = (
                datetime.now(timezone.utc)
                - datetime.fromtimestamp(f.stat().st_mtime, timezone.utc)
            ).total_seconds() / 3600
            if age <= max_age_hours:
                with open(f) as j:
                    return json.load(j), True
    return None, False


# ============================================================================
# TELEGRAM REPORT BUILDERS
# ============================================================================
def build_mc_telegram(
    mc_results: list,
    mc_report_title: str,
    mc_tf: str,
    mc_lookback: int,
    mc_forecast: int,
    simulations: int,
) -> str:
    """Format MC results for Telegram message."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"📊 **{mc_report_title}**",
        f"📅 Generated: {now}",
        f"🔹 TF: {mc_tf} | Lookback: {mc_lookback} | Forecast: {mc_forecast} | Sims: {simulations}",
        "",
    ]
    for r in mc_results:
        lo, hi = r["range_90"]
        lines.extend(
            [
                f"🔹 **{r['pair']}**",
                f"   💵 Last Close: `{r['current_price']}`",
                f"   📊 Percentile: `{r['percentile_rank']}%`",
                f"   🎯 UP: `{r['p_up_pct']}%` | DOWN: `{r['p_down_pct']}%`",
                f"   📏 90% Band: `{lo}` – `{hi}`",
                f"   🔍 Touch: Low `{r['touch_lower_pct']}%` | High `{r['touch_upper_pct']}%`",
                f"   {r['regime']}",
                "",
            ]
        )
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


def compute_sl_zone(api, oanda_instrument, direction, entry_price, pip_size, cfg_fn):
    """Hierarchical SL: H4 → H8 → Daily → ATR → Fixed"""
    BUFFER_PIPS = cfg_fn("SL_BUFFER_PIPS", 25)
    MIN_DIST_PIPS = cfg_fn("SL_MIN_DISTANCE_PIPS", 20)
    ATR_MULT = cfg_fn("ATR_SL_MULT", 2.0)
    FIXED_PIPS = cfg_fn("SL_FALLBACK_FIXED_PIPS", 35)

    TF_LIST = [
        ("H4", "H4", cfg_fn("SL_H4_LOOKBACK_BARS", 6)),
        ("H8", "H8", cfg_fn("SL_H8_LOOKBACK_BARS", 4)),
        ("DAILY", "D", cfg_fn("SL_DAILY_LOOKBACK_BARS", 2)),
    ]

    def _fetch_zone(gran, count, dir):
        try:
            resp = api.request(
                InstrumentsCandles(
                    instrument=oanda_instrument,
                    params={"granularity": gran, "count": count, "price": "M"},
                )
            )
            candles = resp.get("candles", [])
            if len(candles) < count * 0.5:
                return None, 0
            highs = [float(c["mid"]["h"]) for c in candles]
            lows = [float(c["mid"]["l"]) for c in candles]
            closes = [float(c["mid"]["c"]) for c in candles]
            trs = []
            for i in range(1, len(candles)):
                tr = max(
                    highs[i] - lows[i],
                    abs(highs[i] - closes[i - 1]),
                    abs(lows[i] - closes[i - 1]),
                )
                trs.append(tr)
            atr = np.mean(trs[-14:]) if len(trs) >= 14 else np.mean(trs) if trs else 0
            if dir == "BUY":
                return min(lows), atr
            else:
                return max(highs), atr
        except Exception as e:
            logger.debug(f"⚠️ {gran} fetch failed: {e}")
            return None, 0

    buffer_amt = BUFFER_PIPS * pip_size

    for name, gran, lookback in TF_LIST:
        zone, atr = _fetch_zone(gran, lookback, direction)
        if zone is None:
            logger.info(f"⏭️ {oanda_instrument} {direction} {name}: no data → next")
            continue
        if direction == "BUY":
            sl_candidate = zone - buffer_amt
        else:
            sl_candidate = zone + buffer_amt
        dist = abs(entry_price - sl_candidate) / pip_size
        if dist >= MIN_DIST_PIPS:
            logger.info(
                f"📏 SL {name}: Zone={zone:.5f} ±{BUFFER_PIPS}p → {sl_candidate:.5f} | Dist={dist:.1f}p"
            )
            return sl_candidate, f"{name} Zone {dist:.0f}p"
        else:
            logger.info(
                f"⚠️ {name} too close ({dist:.1f}p < {MIN_DIST_PIPS}p) → stepping up"
            )

    _, atr = _fetch_zone("H4", 14, direction)
    if atr and atr > 0:
        if direction == "BUY":
            sl_atr = entry_price - atr * ATR_MULT
        else:
            sl_atr = entry_price + atr * ATR_MULT
        dist = abs(entry_price - sl_atr) / pip_size
        logger.info(f"🔁 SL ATR-{ATR_MULT}x: {sl_atr:.5f} | Dist={dist:.1f}p")
        return sl_atr, f"ATR-{ATR_MULT}x {dist:.0f}p"

    if direction == "BUY":
        sl_fix = entry_price - FIXED_PIPS * pip_size
    else:
        sl_fix = entry_price + FIXED_PIPS * pip_size
    logger.info(f"🚨 SL FIXED-{FIXED_PIPS}p: {sl_fix:.5f}")
    return sl_fix, f"FIXED-{FIXED_PIPS}p"


# ============================================================================
# 🎯 DYNAMIC POSITION MANAGER — Breakeven + Trailing Stop + ✅ DYNAMIC TP
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
        dynamic_tp: bool = True,
        tp_raise_thresh_pips: int = 15,
        telegram_send=None,
        dry_run: bool = False,
        zone_trailing: bool = False,
        min_sl_step_pips: float = 15.0,
        sl_buffer_pips: float = 25.0,
        sl_zone_lookback: int = 6,
        use_h4_escale: bool = False,
        tp_link_sl: bool = False,
        instrument_overrides: dict | None = None,
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
        self.dry_run = dry_run
        self.zone_trailing = zone_trailing
        self.min_sl_step_pips = min_sl_step_pips
        self.sl_buffer_pips = sl_buffer_pips
        self.sl_zone_lookback = sl_zone_lookback
        self.use_h4_escale = use_h4_escale
        self.tp_link_sl = tp_link_sl
        self.instrument_overrides = instrument_overrides or {}

    def _get_open_trades(self, instrument: str):
        try:
            resp = self.api.request(OpenTrades(accountID=self.account_id))
            return [
                t for t in resp.get("trades", []) if t.get("instrument") == instrument
            ]

        except Exception as e:
            if "404" in str(e) or "NO_SUCH_POSITION" in str(e):
                logger.info(
                    f"  ✅ {instrument}: No open trades"
                )  # was DEBUG → now INFO
            else:
                logger.error(f"  ❌ Failed to fetch trades for {instrument}: {e}")
            return []

    def _current_price(self, instrument: str, side: str) -> float:
        """Get live bid/ask price — uses CORRECT OANDA format (EUR_USD)."""
        try:
            # ✅ DO NOT strip underscores! OANDA NEEDS EUR_USD, NOT EURUSD
            prices = get_live_prices(instrument)

            if prices and "bid" in prices and "ask" in prices:
                # LONG → use BID price | SHORT → use ASK price
                return prices["bid"] if side == "long" else prices["ask"]

            logger.debug(f"  ⚠️ Price fallback for {instrument}")
            return None

        except Exception as e:
            logger.warning(f"  ⚠️ Price fetch failed for {instrument}: {e}")
            return None

    def _is_daily_closed(self) -> bool:
        """启发式：OANDA D1 日线在 UTC 00:00 切换。
        UTC 00:05 之后视为前一根日线已收盘，零 API 成本。
        未来如需精确可替换为拉 D1 candle 检查 .complete 字段。"""
        now = datetime.now(timezone.utc)
        return now.hour >= 0 and now.minute >= 5

    def _recalc_zone_sl(self, oanda_inst, side, pip, gran_override=None) -> float | None:
        try:
            from oandapyV20.endpoints.instruments import InstrumentsCandles
            _gran = gran_override or "H4"
            resp = self.api.request(
                InstrumentsCandles(
                    instrument=oanda_inst,
                    params={"granularity": _gran, "count": self.sl_zone_lookback + 1, "price": "M"},
                )
            )
            candles = resp.get("candles", [])
            closed = candles[:-1] if len(candles) > 1 else candles
            if len(closed) < 3:
                return None
            highs = [float(c["mid"]["h"]) for c in closed]
            lows = [float(c["mid"]["l"]) for c in closed]
            buffer_amt = self.sl_buffer_pips * pip
            if side == "short":
                return max(highs) + buffer_amt
            else:
                return min(lows) - buffer_amt
        except Exception as e:
            logger.debug(f"  ⚠️ zone SL recalc failed for {oanda_inst}: {e}")
            return None

    def _h4_atr(self, oanda_inst) -> float:
        try:
            from oandapyV20.endpoints.instruments import InstrumentsCandles
            resp = self.api.request(
                InstrumentsCandles(
                    instrument=oanda_inst,
                    params={"granularity": "H4", "count": 15, "price": "M"},
                )
            )
            candles = resp.get("candles", [])
            if len(candles) < 5:
                return 0.0
            closed = candles[:-1] if len(candles) > 1 else candles
            highs = [float(c["mid"]["h"]) for c in closed]
            lows = [float(c["mid"]["l"]) for c in closed]
            closes = [float(c["mid"]["c"]) for c in closed]
            trs = []
            for i in range(1, len(closed)):
                tr = max(
                    highs[i] - lows[i],
                    abs(highs[i] - closes[i - 1]),
                    abs(lows[i] - closes[i - 1]),
                )
                trs.append(tr)
            return float(np.mean(trs[-14:])) if trs else 0.0
        except Exception as e:
            logger.debug(f"  ⚠️ H4 ATR fetch failed for {oanda_inst}: {e}")
            return 0.0

    def _update_trade_sl(self, trade_id: str, new_sl: float, decimals: int):
        if self.dry_run:
            logger.info(f"🧊 DRY-RUN — would MOVE SL: trade={trade_id} → {round(new_sl, decimals)}")
            return True
        try:
            data = {
                "stopLoss": {
                    "price": str(round(new_sl, decimals)),
                    "timeInForce": "GTC",
                }
            }
            self.api.request(
                TradeCRCDO(accountID=self.account_id, tradeID=trade_id, data=data)
            )
            logger.info(
                f"   🔄 Updated SL on trade {trade_id} → {round(new_sl, decimals)}"
            )
            return True
        except Exception as e:
            logger.error(f"   ❌ Failed to update SL on trade {trade_id}: {e}")
            return False

    def _update_trade_tp(
        self, trade_id: str, instrument: str, new_tp: float, decimals: int
    ):
        """✅ Update TP on an open trade — uses shared helper"""
        return update_order_tp(
            self.api,
            self.account_id,
            trade_id,
            instrument,
            new_tp,
            send_telegram=self.telegram,
            dry_run=self.dry_run,
        )

    def update_all(self, pair_data: dict, close_position_fn=None):
        BAR_HOURS = {"15m": 0.25, "1H": 1, "H4": 4, "D": 24}
        bar_hours_default = 4 if self.use_h4_escale else BAR_HOURS.get(self.timeframe, 4)
        pip_size_map = lambda p: 0.01 if "JPY" in p.upper() else 0.0001

        for pair, info in pair_data.items():
            instrument = info["oanda"]
            df = info.get("df")
            if df is None or len(df) < 2:
                continue

            # ── Per-instrument override ──
            _ov = self.instrument_overrides.get(instrument, {})
            _bar_hours = _ov.get("bar_hours", bar_hours_default)
            _max_hold = _ov.get("max_hold", self.max_hold)
            _sl_gran = _ov.get("sl_granularity", None)
            _use_d1_close_only = _ov.get("confirm_on_close", False)

            atr_val = self._h4_atr(instrument) if self.use_h4_escale and not _ov else df.iloc[-1].get("atr")
            if atr_val is None or np.isnan(atr_val) or atr_val <= 0:
                continue

            decimals = price_decimals(pair)
            pip = pip_size_map(pair)
            trades = self._get_open_trades(instrument)
            if not trades:
                continue

            # ✅ Load TP state
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

                profit_pips = (
                    (current_price - entry) / pip
                    if side == "long"
                    else (entry - current_price) / pip
                )
                open_time = datetime.fromisoformat(
                    trade["openTime"].replace("Z", "+00:00")
                )
                bars_held = (
                    (datetime.now(timezone.utc) - open_time).total_seconds()
                    / 3600
                    / _bar_hours
                )

                # ⏰ Time-based exit
                if bars_held >= _max_hold:
                    logger.info(
                        f"⏰ TIME EXIT: {pair} trade {tid} held {bars_held:.1f} bars"
                    )
                    if close_position_fn:
                        close_position_fn(instrument)
                    continue

                # ── ✅ DYNAMIC TP — Only RAISE, never lower ──
                if self.dynamic_tp:
                    atr_mult_tp = 3.0  # Match your config
                    if side == "long":
                        new_tp_candidate = current_price + (atr_mult_tp * atr_val)
                        if current_tp is None or new_tp_candidate > current_tp + (
                            self.tp_thresh_pips * pip
                        ):
                            self._update_trade_tp(
                                tid, instrument, new_tp_candidate, decimals
                            )
                    else:  # SHORT
                        new_tp_candidate = current_price - (atr_mult_tp * atr_val)
                        if current_tp is None or new_tp_candidate < current_tp - (
                            self.tp_thresh_pips * pip
                        ):
                            self._update_trade_tp(
                                tid, instrument, new_tp_candidate, decimals
                            )

                # ── SL LOGIC → Breakeven → Trailing (均为 profit-gated) ──
                new_sl = action = None
                _jpy = "JPY" in instrument
                _trig_mult = 2.0 if _jpy else 1.0   # JPY 门槛 ×2
                _trail_mult = 1.5 if _jpy else 1.0  # JPY TRAIL 宽度 ×1.5
                be_pips = self.be_trigger * _trig_mult * atr_val / pip
                trail_pips = self.trail_trigger * _trig_mult * atr_val / pip

                # Breakeven SL (profit-gated only)
                if profit_pips >= be_pips:
                    be_sl = entry - pip if side == "long" else entry + pip
                    if (
                        current_sl is None
                        or (side == "long" and be_sl > current_sl)
                        or (side == "short" and be_sl < current_sl)
                    ):
                        new_sl, action = be_sl, "BREAKEVEN"

                if profit_pips >= trail_pips:
                    if self.zone_trailing:
                        cand = self._recalc_zone_sl(instrument, side, pip, gran_override=_sl_gran)
                        if cand is not None:
                            cand = round(cand, decimals)
                            favorable = (
                                (side == "long" and cand > current_sl)
                                or (side == "short" and cand < current_sl)
                                or current_sl is None
                            )
                            big_enough = (
                                current_sl is None
                                or abs(cand - current_sl) >= self.min_sl_step_pips * pip
                            )
                            if favorable and big_enough:
                                new_sl, action = cand, "ZONE-TRAIL"
                        else:
                            logger.debug(f"  ⚠️ {pair} #{tid}: zone SL recalc failed → skip")
                    else:
                        trail_sl = (
                            current_price - self.trail_mult * _trail_mult * atr_val
                            if side == "long"
                            else current_price + self.trail_mult * _trail_mult * atr_val
                        )
                        if (
                            current_sl is None
                            or (side == "long" and trail_sl > current_sl)
                            or (side == "short" and trail_sl < current_sl)
                        ):
                            new_sl, action = trail_sl, "TRAIL"

                if new_sl and action:
                    # ── Gate: D_STRATEGY_GROUPS 的 pair 必须等 D1 收盘 ──
                    if _use_d1_close_only and not self._is_daily_closed():
                        logger.info(
                            f"  ⏳ {pair} #{tid}: SKIP {action} — D1-close-only, "
                            f"waiting for daily candle close"
                        )
                        continue
                    if (side == "long" and current_sl and new_sl < current_sl) or (
                        side == "short" and current_sl and new_sl > current_sl
                    ):
                        continue
                    if self._update_trade_sl(tid, new_sl, decimals):
                        if self.telegram:
                            self.telegram(
                                f"🎯 {action} on {pair} #{tid} | Price: {current_price} | New SL: {round(new_sl, decimals)} | Profit: {profit_pips:.1f} pips"
                            )
                        if self.tp_link_sl:
                            sl_dist = abs(entry - new_sl)
                            if side == "long":
                                new_tp = round(new_sl + sl_dist * 1.5, decimals)
                            else:
                                new_tp = round(new_sl - sl_dist * 1.5, decimals)
                            if (current_tp is None) or (
                                (side == "long" and new_tp > current_tp)
                                or (side == "short" and new_tp < current_tp)
                            ):
                                self._update_trade_tp(tid, instrument, new_tp, decimals)
                                if self.telegram:
                                    self.telegram(
                                        f"🎯 TP×1.5 on {pair} #{tid} | New TP: {new_tp:.{decimals}f}"
                                    )


class DynamicPositionManager_v2:
    def __init__(
        self,
        api,
        account_id: str,
        timeframe: str,
        be_trigger_atr_mult: float = 2.0,  # 提高门槛：默认从1.5改为2.0
        trail_trigger_atr_mult: float = 3.0,  # 提高门槛：默认从2.5改为3.0
        trail_atr_mult: float = 2.0,  # 提高容忍度：默认从1.5改为2.0 (JPY可设为2.5)
        max_hold_bars: int = 12,
        min_hold_bars: int = 4,  # ✅ 新增：最少持仓Bar数（防止过早退出）
        exit_on_close_only: bool = True,  # ✅ 新增：仅收盘价确认，忽略盘中影线
        ratchet_exit: bool = True,  # ✅ 新增：止损只进不退（Ratchet）
        dynamic_tp: bool = True,
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
        self.min_hold_bars = min_hold_bars
        self.exit_on_close_only = exit_on_close_only
        self.ratchet_exit = ratchet_exit
        self.dynamic_tp = dynamic_tp
        self.tp_thresh_pips = tp_raise_thresh_pips
        self.telegram = telegram_send

    def _get_open_trades(self, instrument: str):
        try:
            resp = self.api.request(OpenTrades(accountID=self.account_id))
            return [
                t for t in resp.get("trades", []) if t.get("instrument") == instrument
            ]
        except Exception as e:
            if "404" in str(e) or "NO_SUCH_POSITION" in str(e):
                logger.info(f"  ✅ {instrument}: No open trades")
            else:
                logger.error(f"  ❌ Failed to fetch trades for {instrument}: {e}")
            return []

    def _current_price(self, instrument: str, side: str) -> float:
        try:
            prices = get_live_prices(instrument)
            if prices and "bid" in prices and "ask" in prices:
                return prices["bid"] if side == "long" else prices["ask"]
            return None
        except Exception as e:
            logger.warning(f"  ⚠️ Price fetch failed for {instrument}: {e}")
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
                TradeCRCDO(accountID=self.account_id, tradeID=trade_id, data=data)
            )
            logger.info(
                f"   🔄 Updated SL on trade {trade_id} → {round(new_sl, decimals)}"
            )
            return True
        except Exception as e:
            logger.error(f"   ❌ Failed to update SL on trade {trade_id}: {e}")
            return False

    def _update_trade_tp(
        self, trade_id: str, instrument: str, new_tp: float, decimals: int
    ):
        return update_order_tp(
            self.api,
            self.account_id,
            trade_id,
            instrument,
            new_tp,
            send_telegram=self.telegram,
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

            # ✅ 针对 JPY 货币对自适应调整 ATR 乘数上限与基准
            is_jpy = "JPY" in pair.upper()
            active_trail_mult = 2.5 if is_jpy else self.trail_mult

            decimals = price_decimals(pair)
            pip = pip_size_map(pair)
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
                current_tp_raw = trade.get("takeProfitOrder", {}).get("price")
                current_tp = float(current_tp_raw) if current_tp_raw else None

                current_price = self._current_price(instrument, side)
                if current_price is None:
                    continue

                profit_pips = (
                    (current_price - entry) / pip
                    if side == "long"
                    else (entry - current_price) / pip
                )
                open_time = datetime.fromisoformat(
                    trade["openTime"].replace("Z", "+00:00")
                )
                bars_held = (
                    (datetime.now(timezone.utc) - open_time).total_seconds()
                    / 3600
                    / bar_hours
                )

                # ⏰ Time-based exit (需同时满足超过最小持仓 bar 数，防止过早被时间清仓)
                if bars_held >= self.max_hold:
                    logger.info(
                        f"⏰ TIME EXIT: {pair} trade {tid} held {bars_held:.1f} bars"
                    )
                    if close_position_fn:
                        close_position_fn(instrument)
                    continue

                # 🛡️ 保护机制：初期持仓保护（不满足最小持仓根数，跳过动态止损判定）
                if bars_held < self.min_hold_bars:
                    logger.debug(
                        f"🛡️ {pair}: bars held {bars_held:.1f} < MIN_HOLD ({self.min_hold_bars}) — skip dynamic exit"
                    )
                    continue

                # ── ✅ DYNAMIC TP ──
                if self.dynamic_tp:
                    atr_mult_tp = 3.0
                    if side == "long":
                        new_tp_candidate = current_price + (atr_mult_tp * atr_val)
                        if current_tp is None or new_tp_candidate > current_tp + (
                            self.tp_thresh_pips * pip
                        ):
                            self._update_trade_tp(
                                tid, instrument, new_tp_candidate, decimals
                            )
                    else:
                        new_tp_candidate = current_price - (atr_mult_tp * atr_val)
                        if current_tp is None or new_tp_candidate < current_tp - (
                            self.tp_thresh_pips * pip
                        ):
                            self._update_trade_tp(
                                tid, instrument, new_tp_candidate, decimals
                            )

                # ── SL LOGIC → Breakeven → Trailing (Wider & Ratchet) ──
                new_sl = action = None
                be_pips = self.be_trigger * atr_val / pip
                trail_pips = self.trail_trigger * atr_val / pip

                # Breakeven SL
                if profit_pips >= be_pips:
                    be_sl = entry - pip if side == "long" else entry + pip
                    if (
                        current_sl is None
                        or (side == "long" and be_sl > current_sl)
                        or (side == "short" and be_sl < current_sl)
                    ):
                        new_sl, action = be_sl, "BREAKEVEN"

                # Trailing SL (使用加宽后的 active_trail_mult，给予利润更多奔跑空间)
                if profit_pips >= trail_pips:
                    trail_sl = (
                        current_price - active_trail_mult * atr_val
                        if side == "long"
                        else current_price + active_trail_mult * atr_val
                    )
                    if (
                        current_sl is None
                        or (side == "long" and trail_sl > current_sl)
                        or (side == "short" and trail_sl < current_sl)
                    ):
                        new_sl, action = trail_sl, "TRAIL"

                # Apply SL update with Ratchet and Close-Only safeguards
                if new_sl and action:
                    if self.ratchet_exit:
                        # 严格保证止损只能朝着有利方向移动，绝不回退
                        if (side == "long" and current_sl and new_sl < current_sl) or (
                            side == "short" and current_sl and new_sl > current_sl
                        ):
                            continue

                    if self._update_trade_sl(tid, new_sl, decimals) and self.telegram:
                        self.telegram(
                            f"🎯 {action} on {pair} #{tid} | Price: {current_price} | New SL: {round(new_sl, decimals)} | Profit: {profit_pips:.1f} pips"
                        )