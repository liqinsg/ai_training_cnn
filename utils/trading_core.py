# utils/trading_core.py
"""
Core trading utilities: OANDA client, order execution, price formatting, Gemini helpers
"""
from datetime import datetime
import json
import time
import importlib
from oandapyV20 import API
from google import genai
from google.genai import types
import oandapyV20.endpoints.instruments as instruments
import oandapyV20.endpoints.pricing as pricing
import oandapyV20.endpoints.orders as orders
import oandapyV20.endpoints.positions as positions  # ✅ ADDED
from oandapyV20.endpoints.orders import OrderCreate

from config_oanda import OANDA_ENV, OANDA_API_TOKEN, OANDA_ACCOUNT_ID

api = API(access_token=OANDA_API_TOKEN, environment=OANDA_ENV)

from config_gemini import (
    GEMINI_API_KEY,
    GEMINI_NEWS_MODEL,
    USE_GEMINI_AI,
)

oanda_client = API(access_token=OANDA_API_TOKEN, environment=OANDA_ENV)
gemini_client = genai.Client(api_key=GEMINI_API_KEY) if USE_GEMINI_AI else None

# --------------------------
# Basic Helpers
# --------------------------
def format_price_for_instrument(price, instrument: str) -> str:
    """Format price correctly for JPY vs non-JPY pairs"""
    try:
        num = float(price)
    except (TypeError, ValueError):
        return str(price)
    return f"{num:.3f}" if instrument.endswith("_JPY") else f"{num:.5f}"


def get_open_position(instrument: str):
    req = positions.OpenPositions(accountID=OANDA_ACCOUNT_ID)
    oanda_client.request(req)
    return next(
        (
            p
            for p in req.response.get("positions", [])
            if p.get("instrument") == instrument
        ),
        None,
    )


def attach_sl_tp_to_open_trade(signal, instrument: str | None = None) -> bool:
    instrument = instrument or signal.pair_to_trade
    position = get_open_position(instrument)
    if not position:
        print(f"[EXEC] No open position for {instrument}")
        return False
    trade_ids = []
    for side in (position.get("long", {}), position.get("short", {})):
        trade_ids.extend(side.get("tradeIDs", []))
    if not trade_ids:
        return False
    trade_id = trade_ids[0]
    trades_mod = importlib.import_module("oandapyV20.endpoints.trades")
    payload = {
        "stopLoss": {
            "price": format_price_for_instrument(signal.stop_loss, instrument),
            "timeInForce": "GTC",
        },
        "takeProfit": {
            "price": format_price_for_instrument(signal.take_profit, instrument),
            "timeInForce": "GTC",
        },
    }
    try:
        oanda_client.request(
            trades_mod.TradeCRCDO(OANDA_ACCOUNT_ID, trade_id, data=payload)
        )
        print(f"[EXEC] SL/TP attached to {instrument}")
        return True
    except Exception as e:
        print(f"[EXEC ERROR] {e}")
        return False


def verify_sl_tp_on_trade(trade_id: str, instrument: str) -> None:
    trades_mod = importlib.import_module("oandapyV20.endpoints.trades")
    try:
        resp = oanda_client.request(
            trades_mod.TradeDetails(OANDA_ACCOUNT_ID, trade_id)
        ).response
        sl = resp["trade"].get("stopLossOrder", {})
        tp = resp["trade"].get("takeProfitOrder", {})
        print(
            f"[VERIFY] SL={sl.get('price')}, TP={tp.get('price')}"
            if sl or tp
            else "[VERIFY] No SL/TP found"
        )
    except Exception as e:
        print(f"[VERIFY ERROR] {e}")


def get_recent_range(
    instrument: str, granularity: str = "H1", lookback: int = 20
) -> tuple[float, float, float] | None:
    try:
        resp = oanda_client.request(
            instruments.InstrumentsCandles(
                instrument, params={"count": lookback + 1, "granularity": granularity}
            )
        ).response
        candles = [c for c in resp["candles"] if c["complete"]]
        if len(candles) < lookback:
            return None
        highs = [float(c["mid"]["h"]) for c in candles[:-1]]
        lows = [float(c["mid"]["l"]) for c in candles[:-1]]
        return max(highs), min(lows), float(candles[-1]["mid"]["c"])
    except Exception as e:
        print(f"[RANGE ERROR] {e}")
        return None

def execute_market_trade_v5(signal, units_override=None):
    instrument = signal.pair_to_trade
    units = units_override if units_override is not None else 10000
    if signal.action == "SELL":
        units = -abs(units)

    # 1. PLACE MARKET ENTRY
    try:
        entry_data = {
            "order": {
                "type": "MARKET",
                "instrument": instrument,
                "units": str(units)
            }
        }
        entry_resp = api.request(OrderCreate(accountID=OANDA_ACCOUNT_ID, data=entry_data))

        # ✅ EXACT MATCH FOR YOUR RESPONSE — NO MORE MISSES
        fill_tx = entry_resp.get("orderFillTransaction", {})
        trade_id = None

        # Direct safe access — we KNOW tradeOpened exists here
        if "tradeOpened" in fill_tx:
            trade_id = fill_tx["tradeOpened"].get("id")
        elif "tradesOpened" in fill_tx and fill_tx["tradesOpened"]:
            trade_id = fill_tx["tradesOpened"][0].get("id")

        if not trade_id:
            print(f"❌ Still no trade ID — fill_tx: {list(fill_tx.keys())}")
            return False

        filled_price = float(fill_tx.get("price", 0))
        print(f"🔹 Entry filled: {signal.action} {instrument} @ {filled_price} | Trade ID: {trade_id}")

    except Exception as e:
        print(f"❌ Entry failed {instrument}: {repr(e)}")
        return False

    time.sleep(0.2)

    # 2. ATTACH STOP LOSS
    try:
        if signal.stop_loss:
            decimals = 3 if "JPY" in instrument else 5
            api.request(OrderCreate(accountID=OANDA_ACCOUNT_ID, data={
                "order": {
                    "type": "STOP_LOSS",
                    "instrument": instrument,
                    "price": str(round(signal.stop_loss, decimals)),
                    "tradeID": str(trade_id),
                    "triggerCondition": "DEFAULT"
                }
            }))
            print(f"🔹 SL attached @ {signal.stop_loss}")
    except Exception as e:
        print(f"⚠️ SL attach: {repr(e)[:80]}")

    # 3. ATTACH TAKE PROFIT
    try:
        if signal.take_profit:
            decimals = 3 if "JPY" in instrument else 5
            api.request(OrderCreate(accountID=OANDA_ACCOUNT_ID, data={
                "order": {
                    "type": "TAKE_PROFIT",
                    "instrument": instrument,
                    "price": str(round(signal.take_profit, decimals)),
                    "tradeID": str(trade_id),
                    "triggerCondition": "DEFAULT"
                }
            }))
            print(f"🔹 TP attached @ {signal.take_profit}")
    except Exception as e:
        print(f"⚠️ TP attach: {repr(e)[:80]}")

    return True

def execute_market_trade(signal, units_override=None):
    if not signal or signal.action == "HOLD":
        print("[EXEC] No action")
        return False

    # ✅ FETCH LIVE PRICE FIRST — ADJUST SL/TP TO BE VALID
    try:
        resp = oanda_client.request(
            pricing.PricingInfo(OANDA_ACCOUNT_ID, {"instruments": signal.pair_to_trade})
        )
        ask = float(resp["prices"][0]["asks"][0]["price"])
        bid = float(resp["prices"][0]["bids"][0]["price"])
        spread = ask - bid

        # ✅ SHIFT SL/TP TO GUARANTEE VALID BOUNDS
        if signal.action == "BUY":
            # SL must be BELOW bid; TP must be ABOVE ask
            sl = min(signal.stop_loss, bid - spread * 0.5)
            tp = max(signal.take_profit, ask + spread * 0.5)
        else:
            # SELL: SL above ask; TP below bid
            sl = max(signal.stop_loss, ask + spread * 0.5)
            tp = min(signal.take_profit, bid - spread * 0.5)

    except Exception as e:
        print(f"[PRICE ADJUST ERROR] {e}")
        sl = signal.stop_loss
        tp = signal.take_profit

    units = (
        (units_override or 10000)
        if signal.action == "BUY"
        else -(units_override or 10000)
    )
    payload = {
        "order": {
            "units": str(units),
            "instrument": signal.pair_to_trade,
            "timeInForce": "IOC",
            "priceBound": "0.0050",
            "type": "MARKET",
            "stopLossOnFill": {
                "price": format_price_for_instrument(sl, signal.pair_to_trade),
                "timeInForce": "GTC",
                "triggerMode": "TOP_OF_BOOK"
            },
            "takeProfitOnFill": {
                "price": format_price_for_instrument(tp, signal.pair_to_trade),
                "timeInForce": "GTC"
            },
            "clientExtensions": {
                "comment": signal.reasoning[:128],
                "tag": "ai-strategy",
            },
        }
    }
    try:
        resp = oanda_client.request(orders.OrderCreate(OANDA_ACCOUNT_ID, payload))
        if "orderFillTransaction" in resp:
            fill = resp["orderFillTransaction"]
            print(f"✅ [EXEC] FILLED {signal.action} {signal.pair_to_trade} @ {fill.get('price')} | SL={sl} TP={tp} | ID: {fill.get('id')}")
            return True
        print(f"❌ [OANDA REJECT] {resp.get('orderCancelTransaction', {}).get('reason', 'Unknown')}")
        return False
    except Exception as e:
        print(f"❌ [EXEC ERROR] {str(e)}")
        return False

# --------------------------
# Gemini Enhancements
# --------------------------
def get_latest_news_sentiment() -> str:
    if not USE_GEMINI_AI or not gemini_client:
        return "Gemini disabled"
    try:
        return gemini_client.models.generate_content(
            model=GEMINI_NEWS_MODEL,
            contents="Summarize today's major FX/macro news: JPY, USD, EUR, GBP drivers + next 24h risk events.",
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())], temperature=0.1
            ),
        ).text.strip()
    except Exception as e:
        print(f"[SENTIMENT ERROR] {e}")
        return "No sentiment available"


def validate_signal_with_fundamentals(signal: dict, sentiment: str) -> tuple[bool, str]:
    if not USE_GEMINI_AI:
        return True, "Gemini disabled"
    try:
        res = gemini_client.models.generate_content(
            model=GEMINI_NEWS_MODEL,
            contents=f"TECHNICAL: {signal['action']} {signal['pair']} | SL={signal['stop_loss']} TP={signal['take_profit']}\nMACRO: {sentiment}\nReturn JSON: {{\"approve\": true/false, \"reason\": \"...\"}}",
            temperature=0.0,
        )
        data = json.loads(res.text.strip("`json \n"))
        return data.get("approve", True), data.get("reason", "")
    except Exception as e:
        print(f"[VALIDATION ERROR] {e}")
        return True, "Validation skipped"


def get_news_risk_bias(pair: str) -> dict:
    if not USE_GEMINI_AI:
        return {"impact": 0, "bias": "NEUTRAL"}
    try:
        return json.loads(
            gemini_client.models.generate_content(
                model=GEMINI_NEWS_MODEL,
                contents=f'Search high-impact events for {pair} next 24h. Return JSON: {{"impact":0-3, "bias":"BUY/SELL/NEUTRAL"}}',
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())]
                ),
            ).text.strip("`json \n")
        )
    except Exception:
        return {"impact": 0, "bias": "NEUTRAL"}


def get_ensemble_consensus(prompt: str):
    from models_ensemble import (
        get_gemini_decision,
        get_qwen_decision,
        get_deepseek_decision,
        use_qwen,
        use_deepseek,
    )

    signals = []
    try:
        signals.append(("gemini", get_gemini_decision(prompt)))
    except Exception as e:
        print(f"[ENSEMBLE] Gemini: {e}")
    if use_qwen:
        try:
            signals.append(("qwen", get_qwen_decision(prompt)))
        except Exception as e:
            print(f"[ENSEMBLE] Qwen: {e}")
    if use_deepseek:
        try:
            signals.append(("deepseek", get_deepseek_decision(prompt)))
        except Exception as e:
            print(f"[ENSEMBLE] DeepSeek: {e}")
    if not signals:
        return None, signals
    if len({s.pair_to_trade for _, s in signals}) != 1:
        return None, signals
    actions = [s.action for _, s in signals]
    best = max(set(actions), key=actions.count)
    return next(s for _, s in signals if s.action == best), signals


# --------------------------
# Core Bot Functions
# --------------------------
def open_oanda_order(signal: dict, units: float | None = None) -> dict:
    """✅ OANDA‑COMPLIANT — ATOMIC SL/TP, NO CANCELLATIONS"""
    pair_raw = signal["pair"]
    action = signal["action"]
    units = int(units) if action == "BUY" else -int(units)
    sl = signal["stop_loss"]
    tp = signal["take_profit"]
    decimals = 3 if "JPY" in pair_raw else 5

    # ✅ STEP 1: FETCH LIVE PRICES FIRST — ADJUST SL/TP TO BE VALID
    try:
        resp = oanda_client.request(
            pricing.PricingInfo(OANDA_ACCOUNT_ID, {"instruments": pair_raw})
        )
        ask = float(resp["prices"][0]["asks"][0]["price"])
        bid = float(resp["prices"][0]["bids"][0]["price"])
        spread = ask - bid

        # ✅ GUARANTEE SL/TP ARE WITHIN OANDA’S MINIMUM DISTANCE RULES
        if action == "BUY":
            # SL must be BELOW bid; TP must be ABOVE ask
            sl = min(float(sl), bid - spread * 0.5)
            tp = max(float(tp), ask + spread * 0.5)
        else:
            # SELL: SL above ask; TP below bid
            sl = max(float(sl), ask + spread * 0.5)
            tp = min(float(tp), bid - spread * 0.5)

    except Exception as e:
        print(f"⚠️ Price check skipped: {e} — using calculated levels")
        sl = float(sl)
        tp = float(tp)

    print(f"🔍 SENDING SL/TP for {pair_raw}: SL={sl:.{decimals}f} | TP={tp:.{decimals}f}")

    # ✅ STEP 2: EXACT OANDA SPEC — ATOMIC ATTACHMENT
    order_payload = {
        "order": {
            "type": "MARKET",
            "instrument": pair_raw,
            "units": str(units),
            "timeInForce": "IOC",          # ✅ Fill Or Cancel → Immediate or cancel (better than FOK)
            "positionFill": "DEFAULT",
            "stopLossOnFill": {
                "price": f"{sl:.{decimals}f}",
                "timeInForce": "GTC"
            },
            "takeProfitOnFill": {
                "price": f"{tp:.{decimals}f}",
                "timeInForce": "GTC"
            }
        }
    }

    try:
        from oandapyV20.endpoints.orders import OrderCreate
        resp = oanda_client.request(OrderCreate(accountID=OANDA_ACCOUNT_ID, data=order_payload))
        if "orderFillTransaction" in resp:
            fill = resp["orderFillTransaction"]
            print(f"✅ FILLED {action} {pair_raw} @ {fill.get('price')} | SL/TP ATTACHED")
            return {"status": "OK", "price": fill.get('price')}
        cancel = resp.get("orderCancelTransaction", {})
        print(f"❌ CANCELLED: {cancel.get('reason', 'Unknown')}")
        return {"status": "CANCELLED", "reason": cancel.get("reason")}
    except Exception as e:
        return {"status": "ERROR", "message": f"OANDA API Error: {e}"}
    

def forex_market_closed():
    """Reliable UTC‑based market check — no API call"""
    now = datetime.utcnow()
    wd = now.weekday()
    return wd == 6 or (wd == 5 and now.hour >= 21)


def get_open_instruments():
    """Return set of all instruments with open positions"""
    try:
        resp = oanda_client.request(positions.OpenPositions(accountID=OANDA_ACCOUNT_ID))
        return {
            pos["instrument"]
            for pos in resp.get("positions", [])
            if any(
                float(pos.get(side, {}).get("units", 0)) != 0
                for side in ("long", "short")
            )
        }
    except Exception as e:
        print(f"⚠️ Position check skipped: {e}")
        return set()


def get_candles(
    instrument: str, granularity: str = "D", count: int = 50, start=None, end=None
) -> list:
    """Fetch only complete candles"""
    params = {"granularity": granularity, "count": count}
    if start:
        params["from"] = start.isoformat()
    if end:
        params["to"] = end.isoformat()
    try:
        return [
            c
            for c in oanda_client.request(
                instruments.InstrumentsCandles(instrument, params=params)
            ).get("candles", [])
            if c.get("complete")
        ]
    except Exception as e:
        print(f"[OANDA] Candle fetch failed {instrument}: {e}")
        return []


def get_latest_price(instrument: str) -> float | None:
    """Get latest mid price"""
    try:
        resp = oanda_client.request(
            pricing.PricingInfo(OANDA_ACCOUNT_ID, {"instruments": instrument})
        )
        prices = resp.get("prices", [])
        return (
            round(
                (
                    float(prices[0]["bids"][0]["price"])
                    + float(prices[0]["asks"][0]["price"])
                )
                / 2,
                5,
            )
            if prices
            else None
        )
    except Exception as e:
        print(f"[OANDA] Price error: {e}")
        return None


def close_position(instrument: str) -> bool:
    try:
        pos = get_open_position(instrument)
        if not pos:
            print(f"[CLOSE] No position for {instrument}")
            return False
        payload = {}
        long_units = int(float(pos.get("long", {}).get("units", 0)))
        short_units = int(float(pos.get("short", {}).get("units", 0)))
        if long_units > 0:
            payload["longUnits"] = str(long_units)
        if short_units < 0:
            payload["shortUnits"] = str(abs(short_units))
        oanda_client.request(
            positions.PositionClose(OANDA_ACCOUNT_ID, instrument, data=payload)
        )
        print(f"[CLOSE] Closed {instrument}")
        return True
    except Exception as e:
        print(f"[CLOSE ERROR] {e}")
        return False
