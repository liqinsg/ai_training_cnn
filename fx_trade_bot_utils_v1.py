# fx_trade_bot_utils_v1.py
import json
import os
import time
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from enum import Enum
import numpy as np
import pandas as pd
from data_guard import get_safe_series, safe_last, trim_to_closed_candles
# from telegram_message import send_telegram_message
from utils.strategy_helpers import get_live_prices
from utils.logging_utils import get_logger

# OANDA Endpoints — VERIFIED against your installed oandapyV20
from oandapyV20.endpoints.instruments import InstrumentsCandles
from oandapyV20.endpoints.positions import PositionDetails
from oandapyV20.endpoints.orders import OrderCreate
from oandapyV20.endpoints.trades import OpenTrades, TradeCRCDO, TradesList
from oandapyV20.endpoints.pricing import PricingInfo
from oandapyV20.endpoints.transactions import (
    TransactionList,
    TransactionDetails,
    TransactionsSinceID,
)
from oandapyV20.endpoints.accounts import AccountDetails

logger = get_logger("fx_trade_bot_utils")


REASON_TAKE_PROFIT = "TAKE_PROFIT"
REASON_TRAIL_STOP = "TRAIL_STOP"
REASON_TIME_EXPIRY = "TIME_EXPIRY"
REASON_DIRECTION_FLIP = "DIRECTION_FLIP"
REASON_SCORE_DROP = "SCORE_DROP"
REASON_MC_SHIFT = "MC_SHIFT"
REASON_MAX_DRAWDOWN = "MAX_DRAWDOWN"
REASON_REBALANCE = "REBALANCE"
REASON_USER_MANUAL = "USER_MANUAL"
REASON_OTHER = "OTHER"

_VALID_REASON_CODES = {
    REASON_TAKE_PROFIT,
    REASON_TRAIL_STOP,
    REASON_TIME_EXPIRY,
    REASON_DIRECTION_FLIP,
    REASON_SCORE_DROP,
    REASON_MC_SHIFT,
    REASON_MAX_DRAWDOWN,
    REASON_REBALANCE,
    REASON_USER_MANUAL,
    REASON_OTHER,
}


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
# MARKET STATUS CHECK — FIXED: uses tradeable flag + PER-INSTRUMENT CACHE
# ============================================================================
# MARKET_GATE_ENABLED = os.getenv("MARKET_GATE", "1") == "1"
MARKET_PROBE = os.getenv("MARKET_PROBE", "EUR_USD")
MARKET_TTL_SEC = int(os.getenv("MARKET_TTL_SEC", "30"))
MIN_CONVICTION = float(os.getenv("MIN_CONVICTION", "45.0"))

_market_cache = {
    "ts": 0.0,
    "closed": None,
    "halted_instruments": {},  # per-instrument cache: {name: {ts, closed}}
}


def forex_market_closed(
    api, oanda_account_id: str, oanda_granularity=None, instrument: str | None = None
) -> bool:
    """
    Check if market is CLOSED/HALTED — returns True = SKIP TRADES.
    - Per-instrument caching: AUD_JPY halted ≠ affect USD_CHF
    - Fail-closed: any error → treat as halted (safe)
    - Positive results cached; errors = NO cache → retry next cycle
    """
    target = instrument or MARKET_PROBE
    now = time.time()

    # 1. Per-instrument cache hit
    halted = _market_cache["halted_instruments"]
    if target in halted:
        rec = halted[target]
        if (now - rec["ts"]) < MARKET_TTL_SEC:
            return rec["closed"]

    # 2. Global cache (only when probing default instrument)
    if (
        _market_cache["closed"] is not None
        and (now - _market_cache["ts"]) < MARKET_TTL_SEC
        and instrument is None
    ):
        return _market_cache["closed"]

    # if not MARKET_GATE_ENABLED:
    #     return False  # Gate disabled = always open

    # 3. Fresh check from OANDA
    try:
        resp = api.request(
            PricingInfo(
                accountID=oanda_account_id,
                params={"instruments": target},
            )
        )
        prices = resp.get("prices", [])
        if not prices:
            logger.warning(f"[{target}] No price data → treat as HALTED")
            return True

        tradeable = prices[0].get("tradeable", False)
        is_halted = not tradeable

        # Write cache
        halted[target] = {"ts": now, "closed": is_halted}
        if instrument is None:
            _market_cache.update(ts=now, closed=is_halted)

        return is_halted

    except Exception as e:
        logger.warning(f"[{target}] Market check failed: {repr(e)} → SAFE HALT")
        return True  # No cache on error → retry next cycle


def can_trade(api, oanda_account_id: str, instrument: str) -> bool:
    """Gatekeeper: True = proceed; False = skip open/close/update."""
    return not forex_market_closed(api, oanda_account_id, instrument=instrument)


def mark_instrument_halted(instrument: str, ttl_sec: int = 300):
    """Call when OANDA explicitly returns MARKET_HALTED — cache immediately."""
    _market_cache["halted_instruments"][instrument] = {
        "ts": time.time(),
        "closed": True,
    }
    logger.info(f"🔴 CACHED {instrument} as HALTED for {ttl_sec}s")


def _detect_and_cache_halt(instrument: str, resp: dict):
    """Helper: parse OANDA cancel/reject response → cache if MARKET_HALTED."""
    reason = next(
        (
            str(resp[key])
            for key in ("reason", "rejectReason", "message")
            if key in resp
        ),
        "",
    )
    if "MARKET_HALTED" in reason or "MARKET_HALTED".upper() in reason.upper():
        mark_instrument_halted(instrument)
        return True
    return False


# ============================================================================
# COOLDOWN MANAGEMENT — TIME-BASED (not run-based)
# State format: {pair: {"direction": "LONG"/"SHORT", "until_ts": float}}
# ============================================================================
def load_cooldown(cooldown_file: Path, Direction):
    if cooldown_file.exists():
        try:
            with open(cooldown_file) as f:
                raw = json.load(f)
            now_ts = datetime.now(timezone.utc).timestamp()
            result = {}
            legacy_keys = []
            for k, v in raw.items():
                if isinstance(v, dict) and "until_ts" in v:
                    if v["until_ts"] > now_ts:
                        result[k] = (Direction(v["direction"]), v["until_ts"])
                        if "_" not in k and len(k) == 3 and k.isalpha():
                            legacy_keys.append(k)
                elif isinstance(v, list) and len(v) == 2:
                    if isinstance(v[1], (int, float)) and v[1] > 0:
                        result[k] = (Direction(v[0]), v[1])
                        if "_" not in k and len(k) == 3 and k.isalpha():
                            legacy_keys.append(k)
            if legacy_keys:
                logger.warning(
                    f"⚠️ Legacy bare-currency cooldown keys detected in {cooldown_file.name}: "
                    f"{legacy_keys} — these are CURRENCY-level, not pair-level, and will "
                    f"be cleaned on next save. Recommend migrating to OANDA pair keys "
                    f"(e.g. EUR_USD)."
                )
            logger.info(f"✅ Cooldown loaded: {len(result)} entries from {cooldown_file.name}")
            return result
        except Exception as e:
            logger.warning(
                f"⚠️ load_cooldown FAILED ({cooldown_file.name}): {e} — "
                f"returning empty state. If this recurs, delete the file so "
                f"it rebuilds cleanly, or check Direction enum compatibility."
            )
    else:
        logger.info(f"📭 No cooldown file at {cooldown_file.name} — starting fresh")
    return {}


def save_cooldown(cooldown_file: Path, state: dict):
    serializable = {
        k: {"direction": v[0].value, "until_ts": float(v[1])}
        for k, v in state.items()
    }
    with open(cooldown_file, "w") as f:
        json.dump(serializable, f)


def check_and_record_tp_cooldown(
    api,
    oanda_account_id: str,
    instrument: str,
    tag_filter: str | None,
    cooldown_hours: float,
    cooldown_state: dict,
) -> bool:
    """Check the latest CLOSED trade for *instrument*.  If it was closed by
    TAKE_PROFIT_ORDER, add the instrument to ``cooldown_state`` for
    ``cooldown_hours``.  Returns True if a TP-triggered cooldown was added."""
    if cooldown_hours <= 0:
        return False
    try:
        resp = api.request(
            TradesList(
                oanda_account_id,
                params={"state": "CLOSED", "count": 10},
            )
        )
    except Exception as e:
        logger.warning(f"TradesList failed for TP-cooldown check: {e!s}")
        return False

    closed_trades = resp.get("trades", [])
    if not closed_trades:
        return False

    def _match_tag(t: dict) -> bool:
        if not tag_filter:
            return True
        ce = t.get("clientExtensions", {}) or {}
        cid = ce.get("id", "")
        ctag = ce.get("tag", "")
        return tag_filter in cid or tag_filter in ctag or instrument in cid

    target_trade = None
    for t in closed_trades:
        if t.get("instrument") != instrument:
            continue
        if _match_tag(t):
            target_trade = t
            break

    if target_trade is None:
        return False

    closing_ids = target_trade.get("closingTransactionIDs") or []
    if not closing_ids:
        return False

    try:
        acct = api.request(AccountDetails(oanda_account_id))
        last_tid = int(acct["account"]["lastTransactionID"])
        min_tid = max(0, last_tid - 500)
        tx_resp = api.request(
            TransactionsSinceID(
                oanda_account_id,
                params={"id": str(min_tid), "count": 500},
            )
        )
        tx_map = {tx["id"]: tx for tx in tx_resp.get("transactions", [])}
    except Exception as e:
        logger.warning(f"TransactionsSinceID failed for TP-cooldown: {e!s}")
        return False

    for cid_str in closing_ids:
        tx = tx_map.get(str(cid_str))
        if tx and tx.get("reason") == "TAKE_PROFIT_ORDER":
            until = time.time() + cooldown_hours * 3600
            cooldown_state[instrument] = (Direction.NONE, until)
            logger.info(
                f"❄️  TP-COOLDOWN  {instrument} locked for "
                f"{cooldown_hours:.1f}h (closed by TAKE_PROFIT)"
            )
            return True
    return False


def refresh_tp_cooldown_from_recent_tx(
    api,
    oanda_account_id: str,
    cooldown_hours: float,
    cooldown_state: dict,
    Direction=None,
) -> list[str]:
    """Bulk scan of recent transactions — find any ORDER_FILL whose reason is
    TAKE_PROFIT_ORDER, extract the instrument from that trade, and add it to
    cooldown_state.  Returns list of instrument names newly locked.

    ``Direction`` is the caller-provided enum used to construct the state
    tuples (same shape as ``load_cooldown`` and ``set_cooldown``).  When not
    supplied, string ``"NONE"`` is used — load_cooldown() accepts both.
    """
    if cooldown_hours <= 0:
        return []
    _NONE = Direction.NONE if Direction is not None else "NONE"
    try:
        acct = api.request(AccountDetails(oanda_account_id))
        last_tid = int(acct["account"]["lastTransactionID"])
        min_tid = max(0, last_tid - 500)
        tx_resp = api.request(
            TransactionsSinceID(
                oanda_account_id,
                params={"id": str(min_tid), "count": 500},
            )
        )
    except Exception as e:
        logger.warning(f"refresh_tp_cooldown: tx fetch failed: {e!s}")
        return []

    new_locks: list[str] = []
    for tx in tx_resp.get("transactions", []):
        if tx.get("type") != "ORDER_FILL":
            continue
        if tx.get("reason") != "TAKE_PROFIT_ORDER":
            continue
        inst = tx.get("instrument", "")
        trade_id = tx.get("tradeID") or next(
            (c.get("tradeID") for c in tx.get("tradesClosed", []) if c.get("tradeID")),
            "",
        )
        if not inst or not trade_id:
            continue
        # Find the actual instrument — ORDER_FILL on close reason carries the
        # instrument directly, double-check via TradesList if needed.
        # But reason=TAKE_PROFIT_ORDER on ORDER_FILL already gives us the
        # instrument.
        # ── 从 TP close 时刻开始算 cooldown，不是从 refresh 时刻 ──
        from datetime import timezone as _tz
        _tx_time_str = tx.get("time", "")
        try:
            _close_ts = datetime.fromisoformat(
                _tx_time_str.replace("Z", "+00:00")
            ).timestamp() if _tx_time_str else time.time()
        except Exception:
            _close_ts = time.time()
        _until_ts = _close_ts + cooldown_hours * 3600
        _remain = _until_ts - time.time()
        if _remain <= 0:
            continue
        base, _, quote = inst.partition("_")
        if "_" not in inst or not base or not quote:
            continue
        _prev = cooldown_state.get(inst)
        if not (_prev and _prev[1] > _until_ts):
            cooldown_state[inst] = (_NONE, _until_ts)
            if inst not in new_locks:
                new_locks.append(inst)
            logger.info(
                f"❄️  TP-COOLDOWN  {inst} locked for "
                f"{cooldown_hours:.1f}h (trade {trade_id}, "
                f"closes-in {_remain / 3600:.1f}h)"
            )
    return new_locks


# ============================================================================
# POSITION HELPERS — FIXED: returns ERROR sentinel on failure
# ============================================================================
def _get_open_position(api, oanda_account_id, instrument):
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


def get_open_position(api, oanda_account_id: str, instrument: str):
    """Returns: (status, data) — status: OPEN/NONE/ERROR"""
    oanda_logger = get_logger("oandapyV20")
    original_level = oanda_logger.getEffectiveLevel()
    oanda_logger.setLevel(logging.CRITICAL + 10)
    try:
        return _get_open_position(api, oanda_account_id, instrument)
    except Exception as e:
        err_text = str(e)
        if "NO_SUCH_POSITION" in err_text or "404" in err_text:
            return PositionStatus.NONE, None
        logger.error(f"⚠️ Position check FAILED {instrument}: {err_text[:120]}")
        return PositionStatus.ERROR, {"error": err_text}
    finally:
        oanda_logger.setLevel(original_level)


def has_open_trade_with_tags(
    api,
    oanda_account_id: str,
    instrument: str,
    required_tags: list[str],
    client_ext_id: str | None = None,
    client_ext_tag: str | None = None,
) -> tuple[bool, dict | None]:
    """
    Check if ANY open trade on `instrument` carries ownership metadata.

    Priority: clientExtensions (trade-level, PERSISTED by OANDA v20) > tags/comment (order-level, NOT persisted).

    OANDA v20 API behavior for MARKET orders:
      - tags / comment → NOT persisted to Trade objects (order-only metadata)
      - clientExtensions → Order-level metadata, NOT on Trade
      - tradeClientExtensions → Persisted as trade.clientExtensions = {id, tag}

    Returns: (found: bool, trade_or_None)
    """
    try:
        resp = api.request(OpenTrades(accountID=oanda_account_id))
    except Exception as e:
        logger.error(f"❌ OpenTrades fetch FAILED: {e}")
        return False, None

    for trade in resp.get("trades", []):
        if trade.get("instrument") != instrument:
            continue

        trade_ce = trade.get("clientExtensions") or {}
        trade_ce_id = trade_ce.get("id", "")
        trade_ce_tag = trade_ce.get("tag", "")

        owned = False
        if client_ext_id and trade_ce_id == client_ext_id:
            owned = True
        elif client_ext_tag and trade_ce_tag == client_ext_tag:
            owned = True
        elif required_tags:
            trade_tags = set(trade.get("tags") or [])
            if set(required_tags).issubset(trade_tags):
                owned = True

        if owned:
            direction = "long" if float(trade.get("currentUnits", 0)) > 0 else "short"
            return True, {
                "trade_id": trade.get("id", ""),
                "direction": direction,
                "units": trade.get("currentUnits", "0"),
                "price": trade.get("price", ""),
                "tags": list(trade.get("tags") or []),
                "client_ext": trade_ce,
                "sl": (
                    float(trade["stopLossOrder"]["price"])
                    if trade.get("stopLossOrder")
                    else None
                ),
                "tp": (
                    float(trade["takeProfitOrder"]["price"])
                    if trade.get("takeProfitOrder")
                    else None
                ),
            }
    return False, None


def list_open_trades(
    api, oanda_account_id: str, instrument: str | None = None
) -> list[dict]:
    """Return all open trades (optionally filtered by instrument) with clientExtensions."""
    try:
        resp = api.request(OpenTrades(accountID=oanda_account_id))
    except Exception as e:
        logger.error(f"❌ OpenTrades fetch FAILED: {e}")
        return []
    return [
        {
            "trade_id": trade.get("id", ""),
            "instrument": trade.get("instrument", ""),
            "units": trade.get("currentUnits", "0"),
            "price": trade.get("price", ""),
            "tags": trade.get("tags") or [],
            "client_ext": trade.get("clientExtensions") or {},
            "client_ext_id": (trade.get("clientExtensions") or {}).get("id", ""),
            "client_ext_tag": (trade.get("clientExtensions") or {}).get("tag", ""),
        }
        for trade in resp.get("trades", [])
            if not instrument or trade.get("instrument") == instrument
    ]


def close_position(
    api,
    oanda_account_id: str,
    instrument: str,
    telegram_send=None,
    dry_run: bool = False,
    reason_code: str | None = None,
    detail_msg: str = "",
    json_log=None,
):
    reason_code = reason_code if reason_code in _VALID_REASON_CODES else REASON_OTHER
    reason_header = f"📤 {reason_code}"
    reason_body = f" | {detail_msg}" if detail_msg else ""

    if not can_trade(api, oanda_account_id, instrument):
        logger.info(f"⏭️ [SKIP CLOSE] {instrument}: MARKET_HALTED / not tradeable")
        return True

    try:
        status, pos = get_open_position(api, oanda_account_id, instrument)
        if status != PositionStatus.OPEN:
            logger.info(f"No open position to close: {instrument}")
            return True
        units = pos["units"]
        close_units = -units
        if dry_run:
            logger.info(
                f"🧪 DRY_RUN CLOSE {instrument}: {units} units @ would close "
                f"(dry_run=True, no OANDA OrderCreate write call issued)"
            )
            logger.info(f"📤 CLOSE {instrument} → {reason_code}{reason_body}")
            if telegram_send:
                telegram_send(
                    f"📤 CLOSED: {instrument}\n└─ Reason: {reason_code}"
                    + (f" — {detail_msg}" if detail_msg else "")
                    + "\n🧪 DRY-RUN (no real order)"
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
            cancel_reason = resp["orderCancelTransaction"].get("reason", "UNKNOWN")
            logger.error(f"❌ Close CANCELLED {instrument}: {cancel_reason}")
            _detect_and_cache_halt(instrument, {"reason": cancel_reason})
            return False
        if "orderFillTransaction" in resp:
            fill_price = resp["orderFillTransaction"].get("price", "?")
            trades_closed = resp["orderFillTransaction"].get("tradesClosed", [])
            total_pnl = 0.0
            trade_ids = []
            for tc in trades_closed:
                trade_ids.append(tc.get("tradeID", ""))
                try:
                    total_pnl += float(tc.get("realizedPL", 0))
                except (ValueError, TypeError):
                    pass
            logger.info(f"✅ Closed {instrument} @ {fill_price}")
            logger.info(f"📤 CLOSE {instrument} → {reason_code}{reason_body}")
            if json_log is not None:
                yahoo_pair = instrument.replace("_", "") + "=X"
                json_log.bot_close(
                    pair=yahoo_pair,
                    reason=reason_code,
                    units=units,
                    exit_price=float(fill_price),
                    pnl=total_pnl,
                    trade_id=",".join(trade_ids) if trade_ids else instrument,
                    detail_msg=detail_msg,
                )
            if telegram_send:
                telegram_send(
                    f"📤 CLOSED: {instrument}\n└─ Reason: {reason_code}"
                    + (f" — {detail_msg}" if detail_msg else "")
                    + f"\n💵 Fill @ {fill_price}"
                )
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
        logger.error(
            f"❌ Failed to fetch account equity: {e} — sizing SKIPPED this cycle"
        )
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
    import time

    start = utcnow_safe()
    since_id = str(int(order_tx_id) - 1) if order_tx_id.isdigit() else order_tx_id
    while (utcnow_safe() - start).total_seconds() < timeout_s:
        try:
            resp = api.request(
                TransactionsSinceID(accountID=oanda_account_id, params={"id": since_id})
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
                _detect_and_cache_halt(instrument, tx)
                return {
                    "status": "CANCELLED",
                    "trade_id": "",
                    "reason": tx.get("reason", "UNKNOWN"),
                }
            if t_type == "ORDER_REJECT" and order_id_match:
                _detect_and_cache_halt(instrument, tx)
                return {
                    "status": "REJECTED",
                    "trade_id": "",
                    "reason": tx.get("rejectReason", "UNKNOWN"),
                }
            if t_type == "ORDER_FILL" and order_id_match:
                trade_opened = tx.get("tradeOpened", {})
                if trade_opened:
                    return {
                        "status": "OK",
                        "trade_id": str(trade_opened.get("tradeID", "")),
                    }
                else:
                    return {"status": "REDUCED", "trade_id": ""}
        time.sleep(interval_s)
    return {"status": "TIMEDOUT", "trade_id": ""}


# ============================================================================
# CORE ORDER FUNCTION — FIXED: STRICT_FILL, dry_run, MARKET_HALTED SKIP
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
    tags: list[str] | None = None,
    comment: str | None = None,
    client_ext: dict | None = None,
) -> dict:
    """Submit order — SKIP immediately if market halted."""
    # ── NEW: SKIP if halted BEFORE any API call ──
    if not can_trade(api, oanda_account_id, instrument):
        logger.info(f"⏭️ [SKIP OPEN] {instrument}: MARKET_HALTED / not tradeable")
        return {
            "status": "SKIPPED",
            "trade_id": "",
            "reason": "MARKET_HALTED",
            "skipped": True,
        }

    dec = price_decimals(instrument)
    pip = pip_size(instrument)
    is_jpy = "JPY" in instrument.upper()

    # Pre-flight price check
    entry_check_price = None
    try:
        pr = api.request(
            PricingInfo(accountID=oanda_account_id, params={"instruments": instrument})
        )["prices"][0]
        entry_check_price = float(
            pr["closeoutAsk"] if direction == "BUY" else pr["closeoutBid"]
        )
    except KeyError as ke:
        logger.warning(f"Price check key missing ({ke}) — validation skipped")
    except Exception as e:
        logger.warning(f"Price check skipped: {e} — validation may be incomplete")

    # SL guard
    if max_sl_pips is not None and sl_price and entry_check_price:
        dist = abs(entry_check_price - sl_price) / pip
        if dist > max_sl_pips:
            return {
                "status": "ERROR",
                "reason": "SL_TOO_WIDE",
                "message": f"SL {dist:.1f} pips > limit {max_sl_pips}",
            }
        if direction == "BUY" and sl_price >= entry_check_price:
            return {
                "status": "ERROR",
                "reason": "SL_INVALID",
                "message": "SL >= entry for BUY",
            }
        if direction == "SELL" and sl_price <= entry_check_price:
            return {
                "status": "ERROR",
                "reason": "SL_INVALID",
                "message": "SL <= entry for SELL",
            }

    if dry_run:
        logger.info(
            f"🧪 DRY_RUN — validated {direction} {units} {instrument} "
            f"SL={sl_price} TP={tp_price}"
        )
        return {"status": "DRY_RUN", "trade_id": "", "dry_run": True}

    # Build payload
    order_payload = {
        "order": {
            "type": "MARKET",
            "instrument": instrument,
            "units": str(units if direction == "BUY" else -units),
            "positionFill": "DEFAULT",
        }
    }
    # OANDA v20 API: tags/comment are NOT persisted to Trade objects for MARKET orders.
    # tradeClientExtensions is the ONLY ownership metadata that persists as trade.clientExtensions.
    if client_ext:
        order_payload["order"]["tradeClientExtensions"] = client_ext
        order_payload["order"]["clientExtensions"] = client_ext
    elif tags or comment:
        ext_id = comment or "_".join(tags) if tags else ""
        ext_tag = tags[-1] if tags else ""
        order_payload["order"]["tradeClientExtensions"] = {
            "id": ext_id,
            "tag": ext_tag,
        }
        order_payload["order"]["clientExtensions"] = {
            "id": ext_id,
            "tag": ext_tag,
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

    # Submit
    try:
        resp = api.request(OrderCreate(accountID=oanda_account_id, data=order_payload))

        # REJECT/CANCEL — detect and cache MARKET_HALTED
        if "orderRejectTransaction" in resp:
            rej = resp["orderRejectTransaction"]
            reason = rej.get("rejectReason", rej.get("reason", "UNKNOWN"))
            logger.error(f"❌ Order REJECTED {instrument}: {reason}")
            _detect_and_cache_halt(instrument, rej)
            return {
                "status": "REJECTED",
                "trade_id": "",
                "message": f"Order rejected: {reason}",
                "reason": reason,
                "response": resp,
            }
        if "orderCancelTransaction" in resp:
            can = resp["orderCancelTransaction"]
            reason = can.get("reason", "UNKNOWN")
            logger.error(f"❌ Order CANCELLED {instrument}: {reason}")
            _detect_and_cache_halt(instrument, can)
            return {
                "status": "CANCELLED",
                "trade_id": "",
                "message": f"Order cancelled: {reason}",
                "reason": reason,
                "response": resp,
            }

        logger.info(f"✅ OANDA order request submitted for {instrument}")

        # Resolve trade ID
        trade_id = ""
        entry_price = entry_check_price
        deferred_polled = None

        if "orderFillTransaction" in resp:
            tx = resp["orderFillTransaction"]
            entry_price = float(tx.get("price", entry_check_price))
            trade_opened = tx.get("tradeOpened", {})
            if trade_opened:
                trade_id = str(trade_opened.get("tradeID", ""))
                logger.info(
                    f"📦 Trade filled immediately: TradeID={trade_id} @ {entry_price}"
                )
            else:
                logger.info(f"📦 Fill reduced/closed existing position @ {entry_price}")
        elif "orderCreateTransaction" in resp:
            order_tx_id = str(resp["orderCreateTransaction"].get("id", ""))
            logger.info(
                f"⏳ Order created — resolving trade ID from chain: {order_tx_id}"
            )
            deferred_polled = _resolve_trade_id_from_order(
                api, oanda_account_id, instrument, order_tx_id
            )
            polled_status = deferred_polled.get("status", "TIMEDOUT")
            trade_id = deferred_polled.get("trade_id", "")

            if polled_status == "CANCELLED":
                logger.error(
                    f"❌ Order CANCELLED {instrument}: "
                    f"{deferred_polled.get('reason', 'UNKNOWN')}"
                )
                return {
                    "status": "CANCELLED",
                    "trade_id": "",
                    "reason": deferred_polled.get("reason", "UNKNOWN"),
                    "message": "Order cancelled by OANDA",
                    "response": resp,
                }
            if polled_status == "REJECTED":
                logger.error(
                    f"❌ Order REJECTED {instrument}: "
                    f"{deferred_polled.get('reason', 'UNKNOWN')}"
                )
                return {
                    "status": "REJECTED",
                    "trade_id": "",
                    "reason": deferred_polled.get("reason", "UNKNOWN"),
                    "message": "Order rejected",
                    "response": resp,
                }
            if polled_status == "REDUCED":
                logger.info(
                    f"📦 Order filled — reduced existing position (no new trade)"
                )
                return {
                    "status": "REDUCED",
                    "trade_id": "",
                    "message": "Fill reduced/closed existing position",
                    "response": resp,
                }
            if polled_status == "TIMEDOUT":
                logger.warning(
                    f"⚠️ Trade ID not confirmed after timeout — {instrument} state UNKNOWN"
                )
                return {
                    "status": "TIMEDOUT",
                    "trade_id": "",
                    "message": "Order accepted but fill not confirmed",
                    "response": resp,
                }
            if polled_status == "ERROR":
                logger.error(
                    f"❌ Resolver error {instrument}: "
                    f"{deferred_polled.get('reason', 'UNKNOWN')}"
                )
                return {
                    "status": "ERROR",
                    "trade_id": "",
                    "message": deferred_polled.get("reason", "RESOLVER_ERROR"),
                    "response": resp,
                }

        if not trade_id and deferred_polled is None:
            logger.warning(
                f"⚠️ No new trade opened (immediate fill reduced existing pos) — {instrument}"
            )
            return {
                "status": "REDUCED",
                "trade_id": "",
                "message": "No new trade — fill may have reduced an existing position",
                "response": resp,
            }

        logger.info(f"📌 Final TradeID={trade_id} confirmed for {instrument}")
        if sl_price:
            logger.info(f"   ✅ SL attached @ {sl_price}")
        if tp_price:
            logger.info(f"   ✅ TP attached @ {tp_price}")
        return {
            "status": "OK",
            "trade_id": trade_id,
            "entry_price": entry_price,
            "response": resp,
        }

    except Exception as e:
        logger.error(f"❌ FAILED {instrument}: {type(e).__name__}: {e}")
        return {
            "status": "ERROR",
            "trade_id": "",
            "message": f"{type(e).__name__}: {e}",
        }


# ============================================================================
# DYNAMIC TP UPDATE — WITH MARKET HALTED SKIP
# ============================================================================
def update_order_tp(
    api,
    account_id,
    trade_id,
    instrument,
    new_tp_price,
    send_telegram=None,
    dry_run: bool = False,
    old_tp_price=None,
    update_reason: str = "DYNAMIC_TP",
    json_log=None,
):
    """Update TP — SKIP if market halted."""
    if not can_trade(api, account_id, instrument):
        logger.info(f"⏭️ [SKIP TP-UPDATE] {instrument}: MARKET_HALTED")
        return {"ok": False, "status": "SKIPPED", "reason": "MARKET_HALTED"}

    dec = price_decimals(instrument)
    new_tp_str = f"{float(new_tp_price):.{dec}f}"
    old_tp_str = (
        f"{float(old_tp_price):.{dec}f}" if old_tp_price is not None else "None"
    )
    data = {"takeProfit": {"price": new_tp_str, "timeInForce": "GTC"}}

    if dry_run:
        logger.info(
            f"🧪 DRY_RUN TP UPDATE {instrument}: would set takeProfit → {new_tp_str} "
            f"(no TradeCRCDO write sent)"
        )
        logger.info(
            f"🔄 UPDATE {instrument} → TP_REVISED: {old_tp_str} → {new_tp_str} | {update_reason}"
        )
        if send_telegram:
            send_telegram(
                f"🔄 UPDATE TP: {instrument}\n"
                f"└─ {old_tp_str} → {new_tp_str} | {update_reason}\n"
                f"🧪 DRY-RUN (no real order)"
            )
        return {"ok": True, "status": "DRY_RUN", "new_tp": new_tp_price, "txid": ""}

    try:
        resp = api.request(
            TradeCRCDO(accountID=account_id, tradeID=trade_id, data=data)
        )
        if "takeProfitOrderTransaction" in resp:
            txid = resp["takeProfitOrderTransaction"]["id"]
            logger.info(
                f"🔄 UPDATE {instrument} → TP_REVISED: {old_tp_str} → {new_tp_str} | {update_reason}"
            )
            if send_telegram:
                send_telegram(
                    f"🔄 UPDATE TP: {instrument}\n"
                    f"└─ {old_tp_str} → {new_tp_str} | {update_reason}"
                )
            return {
                "ok": True,
                "status": "UPDATED",
                "new_tp": new_tp_price,
                "txid": txid,
            }
        return {"ok": False, "status": "UNEXPECTED", "response": resp}
    except Exception as e:
        err = f"❌ TP UPDATE FAILED {instrument}: {e}"
        logger.error(err)
        if send_telegram:
            send_telegram(err)
        return {"ok": False, "status": "ERROR", "error": str(e)}


# ============================================================================
# TP AUTO-ATTACH
# ============================================================================
def attach_tp_to_open_positions(
    api,
    oanda_account_id: str,
    instrument: str | None = None,
    atr_dist_pips: float = 30.0,
    force: bool = False,
) -> int:
    """Attach TP to trades missing one — runs only when explicitly called."""
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
            api.request(
                TradeCRCDO(
                    accountID=oanda_account_id,
                    tradeID=tid,
                    data={"takeProfit": {"price": f"{tp_price}", "timeInForce": "GTC"}},
                )
            )
            attached += 1
        except Exception as e:
            logger.warning(f"   ❌ Failed {inst} #{tid}: {e}")
    logger.info(f"📋 TP attach complete: {attached} updated")
    return attached


# ============================================================================
# DYNAMIC POSITION MANAGER
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
        dynamic_tp: bool = False,
        tp_raise_thresh_pips: int = 15,
        telegram_send=None,
        dry_run: bool = False,
        json_log=None,
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
        self.json_log = json_log

    def _get_open_trades(self, instrument: str):
        try:
            resp = self.api.request(OpenTrades(accountID=self.account_id))
            return [
                t for t in resp.get("trades", []) if t.get("instrument") == instrument
            ]
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

    def _update_trade_sl(
        self,
        trade_id: str,
        new_sl: float,
        decimals: int,
        old_sl: float | None = None,
        pair: str = "",
        sl_action: str = "TRAIL_SL",
    ) -> bool:
        old_sl_str = f"{old_sl:.{decimals}f}" if old_sl is not None else "None"
        new_sl_str = f"{new_sl:.{decimals}f}"
        yahoo_pair = pair.replace("_", "") + "=X"
        if self.dry_run:
            logger.info(
                f"   🧪 DRY_RUN SL #{trade_id}: would set stopLoss → {new_sl_str} "
                f"(no TradeCRCDO write sent)"
            )
            logger.info(f"🔄 UPDATE {pair} → {sl_action}: {old_sl_str} → {new_sl_str}")
            if self.telegram:
                self.telegram(
                    f"🔄 UPDATE SL: {pair} #{trade_id}\n"
                    f"└─ {old_sl_str} → {new_sl_str} | {sl_action}\n"
                    f"🧪 DRY-RUN (no real order)"
                )
            if self.json_log is not None:
                self.json_log.bot_update_sl(
                    pair=yahoo_pair,
                    trade_id=trade_id,
                    old_sl=old_sl if old_sl is not None else 0.0,
                    new_sl=new_sl,
                    update_type=sl_action,
                    dry_run=True,
                )
            return True
        try:
            self.api.request(
                TradeCRCDO(
                    accountID=self.account_id,
                    tradeID=trade_id,
                    data={
                        "stopLoss": {
                            "price": f"{new_sl_str}",
                            "timeInForce": "GTC",
                        }
                    },
                )
            )
            logger.info(f"🔄 UPDATE {pair} → {sl_action}: {old_sl_str} → {new_sl_str}")
            if self.telegram:
                self.telegram(
                    f"🔄 UPDATE SL: {pair} #{trade_id}\n"
                    f"└─ {old_sl_str} → {new_sl_str} | {sl_action}"
                )
            if self.json_log is not None:
                self.json_log.bot_update_sl(
                    pair=yahoo_pair,
                    trade_id=trade_id,
                    old_sl=old_sl if old_sl is not None else 0.0,
                    new_sl=new_sl,
                    update_type=sl_action,
                )
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
            atr_series = get_safe_series(
                df, "atr", min_bars=2, context=f"ExitManager {pair}"
            )
            if atr_series is None:
                continue
            atr_val = safe_last(atr_series, context=f"ExitManager {pair}")
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
                current_sl = (
                    float(trade["stopLossOrder"]["price"])
                    if trade.get("stopLossOrder")
                    else None
                )
                current_tp = (
                    float(trade["takeProfitOrder"]["price"])
                    if trade.get("takeProfitOrder")
                    else None
                )
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
                    (utcnow_safe() - open_time).total_seconds() / 3600 / bar_hours
                )
                if bars_held >= self.max_hold:
                    detail = f"held {bars_held:.1f} bars >= max_hold={self.max_hold}"
                    logger.info(f"⏰ TIME EXIT {pair} #{tid}: {detail}")
                    logger.info(
                        f"🚪 EXIT_DECISION: CLOSE_FULL pair={pair} oanda={instrument} "
                        f"side={side} profit={profit_pips:.1f}p reason=TIME_EXPIRY"
                    )
                    if close_position_fn:
                        try:
                            close_position_fn(
                                instrument,
                                reason_code=REASON_TIME_EXPIRY,
                                detail_msg=detail,
                            )
                        except TypeError:
                            close_position_fn(instrument)
                    continue

                tp_updated_this_cycle = False
                sl_updated_this_cycle = False

                if self.dynamic_tp:
                    atr_mult_tp = 3.0
                    if side == "long":
                        new_tp = current_price + (atr_mult_tp * atr_val)
                        if current_tp is None or new_tp > current_tp + (
                            self.tp_thresh_pips * pip
                        ):
                            old_tp_str = (
                                f"{current_tp:.{decimals}f}"
                                if current_tp is not None
                                else "None"
                            )
                            logger.info(
                                f"🚪 EXIT_DECISION: UPDATE_TP pair={pair} oanda={instrument} "
                                f"old={old_tp_str} new={new_tp:.{decimals}f} "
                                f"reason=DYNAMIC_TP_LONG"
                            )
                            update_order_tp(
                                self.api,
                                self.account_id,
                                tid,
                                instrument,
                                new_tp,
                                send_telegram=self.telegram,
                                dry_run=self.dry_run,
                                old_tp_price=current_tp,
                                update_reason=f"DYNAMIC_TP LONG (profit={profit_pips:.1f}p)",
                                json_log=self.json_log,
                            )
                            tp_updated_this_cycle = True
                    else:
                        new_tp = current_price - (atr_mult_tp * atr_val)
                        if current_tp is None or new_tp < current_tp - (
                            self.tp_thresh_pips * pip
                        ):
                            old_tp_str = (
                                f"{current_tp:.{decimals}f}"
                                if current_tp is not None
                                else "None"
                            )
                            logger.info(
                                f"🚪 EXIT_DECISION: UPDATE_TP pair={pair} oanda={instrument} "
                                f"old={old_tp_str} new={new_tp:.{decimals}f} "
                                f"reason=DYNAMIC_TP_SHORT"
                            )
                            update_order_tp(
                                self.api,
                                self.account_id,
                                tid,
                                instrument,
                                new_tp,
                                send_telegram=self.telegram,
                                dry_run=self.dry_run,
                                old_tp_price=current_tp,
                                update_reason=f"DYNAMIC_TP SHORT (profit={profit_pips:.1f}p)",
                                json_log=self.json_log,
                            )
                            tp_updated_this_cycle = True

                if self.enabled:
                    be_pips = self.be_trigger * atr_val / pip
                    trail_pips = self.trail_trigger * atr_val / pip
                    new_sl = action = None
                    if profit_pips >= be_pips:
                        be_sl = entry - pip if side == "long" else entry + pip
                        if current_sl is None or (
                            (side == "long" and be_sl > current_sl)
                            or (side == "short" and be_sl < current_sl)
                        ):
                            new_sl, action = be_sl, "BREAKEVEN"
                    if profit_pips >= trail_pips:
                        trail_sl = (
                            current_price - self.trail_mult * atr_val
                            if side == "long"
                            else current_price + self.trail_mult * atr_val
                        )
                        if current_sl is None or (
                            (side == "long" and trail_sl > current_sl)
                            or (side == "short" and trail_sl < current_sl)
                        ):
                            new_sl, action = trail_sl, "TRAIL_STOP"
                    if new_sl and action:
                        if current_sl and (
                            (side == "long" and new_sl < current_sl)
                            or (side == "short" and new_sl > current_sl)
                        ):
                            logger.info(
                                f"🚪 EXIT_DECISION: HOLD pair={pair} oanda={instrument} "
                                f"side={side} profit={profit_pips:.1f}p reason=SL_REGRESSION_BLOCKED "
                                f"(proposed={action} SL moves backward → keep {current_sl:.{decimals}f})"
                            )
                            continue
                        old_sl_str = (
                            f"{current_sl:.{decimals}f}"
                            if current_sl is not None
                            else "None"
                        )
                        logger.info(
                            f"🚪 EXIT_DECISION: UPDATE_SL pair={pair} oanda={instrument} "
                            f"side={side} profit={profit_pips:.1f}p "
                            f"old={old_sl_str} new={new_sl:.{decimals}f} reason={action}"
                        )
                        self._update_trade_sl(
                            tid,
                            new_sl,
                            decimals,
                            old_sl=current_sl,
                            pair=pair,
                            sl_action=f"{action} (profit={profit_pips:.1f}p)",
                        )
                        sl_updated_this_cycle = True

                if not tp_updated_this_cycle and not sl_updated_this_cycle:
                    if self.enabled:
                        be_pips = self.be_trigger * atr_val / pip
                        trail_pips = self.trail_trigger * atr_val / pip
                        reason = (
                            "UNDERWATER" if profit_pips < 0 else
                            "BE_TRIGGER_WAIT" if profit_pips < be_pips else
                            "TRAIL_TRIGGER_WAIT" if profit_pips < trail_pips else
                            "NO_IMPROVEMENT"
                        )
                        hold_extra = f" be={be_pips:.1f}p trail={trail_pips:.1f}p"
                    else:
                        reason = "UNDERWATER" if profit_pips < 0 else "TRAILING_DISABLED"
                        hold_extra = ""
                    logger.info(
                        f"🚪 EXIT_DECISION: HOLD pair={pair} oanda={instrument} "
                        f"side={side} bars_held={bars_held:.1f}/{self.max_hold} "
                        f"profit={profit_pips:.1f}p{hold_extra} "
                        f"reason={reason}"
                    )


# ============================================================================
# REMAINING UTILITIES
# ============================================================================
def fetch_candles(api, oanda_instrument: str, gran: str, count: int = 100):
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
    df = trim_to_closed_candles(df, granularity=gran, context=oanda_instrument)
    return df


def should_close_by_strength(
    pair: str, side: str, strength_scores: dict, threshold: float = 1.0
):
    clean = pair.replace("=X", "").replace("_", "")
    base, quote = clean[:3], (
        clean[3:] if len(clean) == 6 else pair.replace("=X", "").split("_", 1)
    )
    if isinstance(quote, list):
        return False, "Parse fail"
    base_score = strength_scores.get(base, 0)
    quote_score = strength_scores.get(quote, 0)
    gap = base_score - quote_score
    if side == "long" and -gap > threshold:
        return (
            True,
            f"Strength flip: {quote}+{quote_score:.2f} > {base}{base_score:.2f}",
        )
    if side == "short" and gap > threshold:
        return (
            True,
            f"Strength flip: {base}+{base_score:.2f} > {quote}{quote_score:.2f}",
        )
    return False, ""


def load_mc_legacy(
    pair: str, results_dir: Path, today_str: str, max_age_hours: int = 24
):
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


def load_mc_bundle(mc_dir: Path, timeframe_prefix: str = "D"):
    """Load pre-computed MC bundle from mc_results/ based on filename date.

    D (Daily): match only files whose filename date == today (YYYYMMDD).
    W (Weekly): match only files whose filename date >= this Monday.

    Within the eligible set, the latest (by filename timestamp) is picked.

    Args:
        mc_dir: Path to the mc_results directory.
        timeframe_prefix: "D" or "W".

    Returns:
        (bundle_dict, ok, filename) tuple.
    """
    if not mc_dir or not mc_dir.is_dir():
        return None, False, None

    import re

    pattern = re.compile(
        rf"^mc_{timeframe_prefix}_all_pairs_(\d{{8}})_(\d{{4}})\.json$"
    )

    candidates = []
    for f in mc_dir.iterdir():
        if not f.is_file():
            continue
        m = pattern.match(f.name)
        if not m:
            continue
        candidates.append((f, m.group(1), m.group(2)))

    if not candidates:
        return None, False, None

    now = utcnow_safe()
    today_str = now.strftime("%Y%m%d")

    if timeframe_prefix == "D":
        eligible = [(f, d, t) for f, d, t in candidates if d == today_str]
        if not eligible:
            logger.warning(f"⚠️ 今日未找到 D 包 (今日={today_str})")
            return None, False, None
    elif timeframe_prefix == "W":
        monday = now - timedelta(days=now.weekday())
        monday_str = monday.strftime("%Y%m%d")
        eligible = [(f, d, t) for f, d, t in candidates if d >= monday_str]
        if not eligible:
            logger.warning(f"⚠️ 本周未找到 W 包 (本周一={monday_str})")
            return None, False, None
    else:
        return None, False, None

    eligible.sort(key=lambda x: (x[1], x[2]), reverse=True)
    f = eligible[0][0]

    try:
        with open(f) as j:
            data = json.load(j)
        bundle = data.get("results", data) if isinstance(data, dict) else {}
        if not bundle:
            logger.warning(f"⚠️ MC bundle {f.name} has empty 'results'")
            return None, False, None
        return bundle, True, f.name
    except Exception as e:
        logger.warning(f"⚠️ Failed to load MC bundle {f.name}: {e}")
        return None, False, None


def get_mc_results_dir():
    """Return the mc_results directory path (sibling to the fx_monte_carlo project)."""
    candidates = [
        Path.home() / "projects" / "fx_monte_carlo" / "mc_results",
        Path(__file__).resolve().parent.parent / "fx_monte_carlo" / "mc_results",
        Path("/home/qili/projects/fx_monte_carlo/mc_results"),
    ]
    for c in candidates:
        if c.is_dir():
            return c
    return candidates[0]


def build_mc_telegram(mc_results, title, tf, lookback, fcst, sims):
    now = utcnow_safe().strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"📊 **{title}**",
        f"📅 {now}",
        f"🔹 {tf} | LB:{lookback} FC:{fcst} Sims:{sims}",
        "",
    ]
    for r in mc_results:
        lo, hi = r["range_90"]
        lines.extend(
            [
                f"🔹 **{r['pair']}**",
                f"   Last: `{r['current_price']}` | Pctl: `{r['percentile_rank']}%`",
                f"   Up: `{r['p_up_pct']}%` Down: `{r['p_down_pct']}%`",
                f"   90%: `{lo}`–`{hi}` | {r['regime']}",
                "",
            ]
        )
    return "\n".join(lines)


def build_trade_telegram(trade_lines, mc_summary=None):
    now = utcnow_safe().strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"🤖 UPDATE — {now}"] + trade_lines
    if mc_summary:
        lines += ["", "📊 MC Context:"] + [f"   {s}" for s in mc_summary]
    return "\n".join(lines)


def fetch_weekly_ema100(oanda_instrument, api):
    try:
        resp = api.request(
            InstrumentsCandles(
                instrument=oanda_instrument,
                params={"granularity": "W", "count": 105, "price": "M"},
            )
        )
        candles = resp["candles"]
        if len(candles) < 100:
            return None
        closes = [float(c["mid"]["c"]) for c in candles]

        df = pd.DataFrame(
            [{"Time": c["time"], "Close": float(c["mid"]["c"])} for c in candles]
        ).set_index("Time")
        df = trim_to_closed_candles(df, granularity="W", context=oanda_instrument)
        if df.empty:
            return None

        series = df["Close"]
        if len(series) < 100:
            return None
        return series.ewm(span=100, adjust=False).mean().iloc[-1]
    except Exception as e:
        logger.warning(f"⚠️ Cannot fetch Weekly EMA100 for {oanda_instrument}: {e}")
        return None


def record_cooldown_from_closed_trades(
    api,
    oanda_account_id: str,
    instruments: list,
    owner_client_ext_id: str,
    owner_client_ext_tag: str,
    cooldown_hours: float,
    remove_cooldown: bool,
    cooldown_state: dict,
    Direction,
):
    """Scan recently CLOSED owned trades and lock TP-closed instruments.

    Operates directly on ``cooldown_state`` (same shape as load_cooldown output:
    {key: (Direction, until_ts)}). When remove_cooldown=True it also strips
    entries so the caller's state stays in sync.
    """
    if cooldown_hours <= 0 and not remove_cooldown:
        return
    for oanda_inst in list(instruments):
        try:
            resp = api.request(
                TradesList(
                    oanda_account_id,
                    params={"state": "CLOSED", "instrument": oanda_inst, "count": 5},
                )
            )
        except Exception as e:
            logger.warning(
                f"⚠️ TP-cooldown TradesList failed for {oanda_inst}: {e!s}"
            )
            continue
        closed = resp.get("trades", [])
        if not closed:
            continue
        t = closed[0]
        ce = t.get("clientExtensions", {}) or {}
        if ce.get("id") != owner_client_ext_id and ce.get("tag") != owner_client_ext_tag:
            continue
        closing_ids = [str(x) for x in (t.get("closingTransactionIDs") or [])]
        if not closing_ids:
            continue
        ctype = ""
        reasons = set()
        try:
            for cid in closing_ids:
                try:
                    td_resp = api.request(
                        TransactionDetails(oanda_account_id, cid)
                    )
                    tx = td_resp.get("transaction", {})
                    reasons.add(tx.get("reason", ""))
                except Exception as inner_e:
                    logger.debug(
                        f"TransactionDetails({cid}) failed: {inner_e!s}"
                    )
            if "TAKE_PROFIT_ORDER" in reasons:
                ctype = "TP"
            elif "STOP_LOSS_ORDER" in reasons:
                ctype = "SL"
            elif reasons:
                ctype = "OTHER"
        except Exception as e:
            logger.warning(
                f"⚠️ TP-cooldown transaction lookup failed for {oanda_inst}: {e!s}"
            )

        if ctype == "TP" and not remove_cooldown:
            expire_ts = datetime.now(timezone.utc).timestamp() + cooldown_hours * 3600
            cooldown_state[oanda_inst] = (Direction.NONE, expire_ts)
            logger.info(
                f"❄️  TP close detected on {oanda_inst} — cooldown applied "
                f"({cooldown_hours}h)"
            )
        if remove_cooldown:
            cooldown_state.pop(oanda_inst, None)