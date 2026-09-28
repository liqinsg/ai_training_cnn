# utils/trading_core.py
"""
Core trading utilities: OANDA client, order execution, price formatting, Gemini helpers

所有 OANDA 相关函数通过参数接收 api 和 account_id，不再依赖模块级全局变量。
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import contextlib
import json
import importlib
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pandas as pd
from oandapyV20 import API
from google import genai
from google.genai import types
import oandapyV20.endpoints.instruments as instruments
import oandapyV20.endpoints.pricing as pricing
import logging

logger = logging.getLogger(__name__)


def _get_defaults():
    try:
        from config_oanda import OANDA_ACCOUNT_ID, OANDA_API_TOKEN, OANDA_ENV

        _api = API(access_token=OANDA_API_TOKEN, environment=OANDA_ENV)
        return _api, OANDA_ACCOUNT_ID
    except Exception:
        return None, None


oanda_client, OANDA_ACCOUNT_ID = _get_defaults()


# --------------------------
# Gemini Init (config 独有)
# --------------------------
try:
    from config import GEMINI_API_KEY, GEMINI_NEWS_MODEL, USE_GEMINI_AI

    gemini_client = genai.Client(api_key=GEMINI_API_KEY) if USE_GEMINI_AI else None
except Exception:
    gemini_client = None
    GEMINI_NEWS_MODEL = "gemini-3.5-flash"
    USE_GEMINI_AI = False


# --------------------------
# Basic Helpers
# --------------------------
def format_price_for_instrument(price, instrument: str) -> str:
    try:
        numeric_price = float(price)
    except (TypeError, ValueError):
        return str(price)
    return (
        f"{numeric_price:.3f}"
        if instrument.endswith("_JPY")
        else f"{numeric_price:.5f}"
    )


def get_open_position(instrument: str, api=None, account_id: str = None):
    api, account_id = _api_acct(api, account_id)
    positions_module = importlib.import_module("oandapyV20.endpoints.positions")
    req = positions_module.OpenPositions(accountID=account_id)
    api.request(req)
    return next(
        (
            p
            for p in req.response.get("positions", [])
            if p.get("instrument") == instrument
        ),
        None,
    )


def attach_sl_tp_to_open_trade(
    signal,
    instrument: str | None = None,
    dry_run: bool = False,
    api=None,
    account_id: str = None,
) -> bool:
    api, account_id = _api_acct(api, account_id)
    instrument = instrument or signal.pair_to_trade
    position = get_open_position(instrument, api=api, account_id=account_id)
    if not position:
        print(f"[EXEC] No open position for {instrument}")
        return False
    trade_ids = []
    for side in (position.get("long", {}), position.get("short", {})):
        trade_ids.extend(side.get("tradeIDs", []))
    if not trade_ids:
        return False
    trade_id = trade_ids[0]
    sl_str = format_price_for_instrument(signal.stop_loss, instrument)
    tp_str = format_price_for_instrument(signal.take_profit, instrument)
    if dry_run:
        print(
            f"[DRY-RUN] Would attach SL/TP to {instrument} trade={trade_id} SL={sl_str} TP={tp_str}"
        )
        return True
    trades_mod = importlib.import_module("oandapyV20.endpoints.trades")
    payload = {
        "stopLoss": {"price": sl_str, "timeInForce": "GTC"},
        "takeProfit": {"price": tp_str, "timeInForce": "GTC"},
    }
    try:
        api.request(trades_mod.TradeCRCDO(account_id, trade_id, data=payload))
        print(f"[EXEC] SL/TP attached to {instrument}")
        return True
    except Exception as e:
        print(f"[EXEC ERROR] {e}")
        return False


def verify_sl_tp_on_trade(
    trade_id: str, instrument: str, api=None, account_id: str = None
) -> None:
    api, account_id = _api_acct(api, account_id)
    trades_mod = importlib.import_module("oandapyV20.endpoints.trades")
    try:
        resp = api.request(trades_mod.TradeDetails(account_id, trade_id)).response
        sl = resp["trade"].get("stopLossOrder", {})
        tp = resp["trade"].get("takeProfitOrder", {})
        (
            print(f"[VERIFY] SL={sl.get('price')}, TP={tp.get('price')}")
            if sl or tp
            else print("[VERIFY] No SL/TP found")
        )
    except Exception as e:
        print(f"[VERIFY ERROR] {e}")


def get_recent_range(
    instrument: str,
    granularity: str = "H1",
    lookback: int = 20,
    api=None,
) -> tuple[float, float, float] | None:
    api, _ = _api_acct(api, None)
    inst_mod = importlib.import_module("oandapyV20.endpoints.instruments")
    try:
        resp = api.request(
            inst_mod.InstrumentsCandles(
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


def execute_market_trade(
    signal, units_override=None, dry_run: bool = False, api=None, account_id: str = None
):
    api, account_id = _api_acct(api, account_id)
    if not signal or signal.action == "HOLD":
        print("[EXEC] No action")
        return False
    if get_open_position(signal.pair_to_trade, api=api, account_id=account_id):
        print("[EXEC] Already have position")
        return False

    pricing_mod = importlib.import_module("oandapyV20.endpoints.pricing")
    try:
        resp = api.request(
            pricing_mod.PricingInfo(account_id, {"instruments": signal.pair_to_trade})
        )
        ask = float(resp["prices"][0]["asks"][0]["price"])
        bid = float(resp["prices"][0]["bids"][0]["price"])
        if (
            signal.action == "BUY"
            and (signal.stop_loss >= ask or signal.take_profit <= ask)
        ) or (
            signal.action == "SELL"
            and (signal.stop_loss <= bid or signal.take_profit >= bid)
        ):
            print("[EXEC] Invalid SL/TP")
            return False
    except Exception as e:
        print(f"[PRICE CHECK] {e}")
        return False

    units = (
        (units_override or 10000)
        if signal.action == "BUY"
        else -(units_override or 10000)
    )
    pair = signal.pair_to_trade
    sl_str = format_price_for_instrument(signal.stop_loss, pair)
    tp_str = format_price_for_instrument(signal.take_profit, pair)
    if dry_run:
        print(
            f"[DRY-RUN] Would {signal.action} {pair} units={units} "
            f"SL={sl_str} TP={tp_str}"
        )
        return True
    orders_mod = importlib.import_module("oandapyV20.endpoints.orders")
    payload = {
        "order": {
            "units": str(units),
            "instrument": pair,
            "timeInForce": "FOK",
            "type": "MARKET",
            "stopLossOnFill": {"price": sl_str},
            "takeProfitOnFill": {"price": tp_str},
            "clientExtensions": {
                "comment": signal.reasoning[:128],
                "tag": "ai-strategy",
            },
        }
    }
    try:
        resp = api.request(orders_mod.OrderCreate(account_id, payload))
        if "orderFillTransaction" in resp:
            fill = resp["orderFillTransaction"]
            print(
                f"[EXEC] Filled {signal.action} {pair} @ {fill.get('price')} (order id {fill.get('id')})"
            )
            attach_sl_tp_to_open_trade(
                signal, dry_run=dry_run, api=api, account_id=account_id
            )
            return True
        else:
            print(f"[EXEC] Order sent but no fill transaction in response: {resp}")
            return False
    except Exception as e:
        print(f"[EXEC ERROR] {e}")
        return False


# --------------------------
# Gemini Enhancements
# --------------------------


def get_latest_news_sentiment() -> str:
    if not USE_GEMINI_AI or not gemini_client:
        return "Gemini disabled"
    try:
        res = gemini_client.models.generate_content(
            model=GEMINI_NEWS_MODEL,
            contents="Summarize today's major FX/macro news: JPY, USD, EUR, GBP drivers + next 24h risk events.",
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())], temperature=0.1
            ),
        )
        return res.text.strip()
    except Exception as e:
        print(f"[SENTIMENT ERROR] {e}")
        return "No sentiment available"


def validate_signal_with_fundamentals(signal: dict, sentiment: str) -> tuple[bool, str]:
    if not USE_GEMINI_AI:
        return True, "Gemini disabled"
    prompt = f"""
    TECHNICAL: {signal['action']} {signal['pair']} | SL={signal['stop_loss']} TP={signal['take_profit']}
    MACRO: {sentiment}
    Return JSON: {{"approve": true/false, "reason": "..."}}
    """
    try:
        res = gemini_client.models.generate_content(
            model=GEMINI_NEWS_MODEL, contents=prompt, temperature=0.0
        )
        data = json.loads(res.text.strip("`json \n"))
        return data.get("approve", True), data.get("reason", "")
    except Exception as e:
        print(f"[VALIDATION ERROR] {e}")
        return True, "Validation skipped"


def get_news_risk_bias(pair: str) -> dict:
    if not USE_GEMINI_AI:
        return {"impact": 0, "bias": "NEUTRAL"}
    prompt = f'Search high-impact events for {pair} next 24h. Return JSON: {{"impact":0-3, "bias":"BUY/SELL/NEUTRAL"}}'
    try:
        res = gemini_client.models.generate_content(
            model=GEMINI_NEWS_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())]
            ),
        )
        return json.loads(res.text.strip("`json \n"))
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


def run_trading_cycle():
    from custom_strategy import analyze_custom_strategy, get_last_signal

    print("\n=== START TRADING CYCLE ===")
    try:
        report = analyze_custom_strategy()
        signal = get_last_signal()
        if not signal:
            print("[STRATEGY] No signal — HOLD")
            return
        sentiment = get_latest_news_sentiment()
        news = get_news_risk_bias(signal["pair"])
        if news["impact"] >= 2:
            print("[NEWS RISK] High impact — HOLD")
            return
        ok, reason = validate_signal_with_fundamentals(signal, sentiment)
        if not ok:
            print(f"[GEMINI REJECT] {reason}")
            return
        final_signal, _ = get_ensemble_consensus(f"{report}\n{sentiment}")
        if final_signal:
            execute_market_trade(final_signal)
    except Exception as e:
        print(f"[CYCLE ERROR] {e}")


def get_candles(
    instrument: str,
    granularity: str = "D",
    count: int = 50,
    start: datetime | None = None,
    end: datetime | None = None,
    api=None,
) -> list:
    api, _ = _api_acct(api, None)
    params = {"granularity": granularity, "count": count}
    if start:
        params["from"] = start.isoformat()
    if end:
        params["to"] = end.isoformat()

    try:
        req = instruments.InstrumentsCandles(instrument=instrument, params=params)
        resp = api.request(req)
        return resp.get("candles", [])
    except Exception as e:
        print(f"[OANDA] Error fetching candles: {str(e)}")
        return []


def get_latest_price(instrument: str, api=None, account_id: str = None) -> float | None:
    api, account_id = _api_acct(api, account_id)
    try:
        req = pricing.PricingInfo(
            accountID=account_id, params={"instruments": instrument}
        )
        resp = api.request(req)
        prices = resp.get("prices", [])
        if not prices:
            return None
        bid = float(prices[0]["bids"][0]["price"])
        ask = float(prices[0]["asks"][0]["price"])
        return round((bid + ask) / 2, 5)
    except Exception as e:
        print(f"[OANDA] Error fetching price: {str(e)}")
        return None


def close_position(
    instrument: str, dry_run: bool = False, api=None, account_id: str = None
) -> bool:
    api, account_id = _api_acct(api, account_id)
    positions_mod = importlib.import_module("oandapyV20.endpoints.positions")

    try:
        pos_req = positions_mod.OpenPositions(accountID=account_id)
        api.request(pos_req)

        position = next(
            (
                p
                for p in pos_req.response.get("positions", [])
                if p.get("instrument") == instrument
            ),
            None,
        )

        if not position:
            print(f"[CLOSE] No open position for {instrument}")
            return False

        long_units = int(float(position.get("long", {}).get("units", 0)))
        short_units = int(float(position.get("short", {}).get("units", 0)))

        payload = {}
        if long_units > 0:
            payload["longUnits"] = str(long_units)
        if short_units < 0:
            payload["shortUnits"] = str(abs(short_units))

        if dry_run:
            print(f"[DRY-RUN] Would CLOSE {instrument} payload={payload}")
            return True

        req = positions_mod.PositionClose(
            accountID=account_id,
            instrument=instrument,
            data=payload,
        )
        api.request(req)
        print(f"[CLOSE] Closed {instrument}")
        return True

    except Exception as e:
        print(f"[CLOSE ERROR] {e}")
        return False


def forex_market_closed():
    now = datetime.now(ZoneInfo("Europe/London"))
    wd = now.weekday()

    return wd == 5 or (wd == 6 and now.hour < 21) or (wd == 4 and now.hour >= 21)


def update_trade_on_close(
    instrument,
    exit_reason="UNKNOWN",
    TRADE_LOG_PATH=None,
    api=None,
    account_id: str = None,
):
    api, account_id = _api_acct(api, account_id)
    try:
        if not TRADE_LOG_PATH or not TRADE_LOG_PATH.exists():
            return
        df = pd.read_csv(TRADE_LOG_PATH, dtype={"trade_id": str})
        for c in ("pips", "profit_usd", "exit_reason", "exit_time"):
            if c in df.columns:
                df[c] = df[c].astype(object)
        if df.empty:
            return
        mask = (df["pair"] == instrument) & df["exit_time"].isna()
        match = df.loc[mask].head(1)
        if match.empty:
            return
        tid = str(match.iloc[0]["trade_id"])
        if tid.startswith("DRY_RUN_"):
            df.loc[match.index, "exit_reason"] = exit_reason
            df.loc[match.index, "exit_time"] = datetime.now(timezone.utc).isoformat()
            df.to_csv(TRADE_LOG_PATH, index=False)
            return
        realized_pl = 0.0
        with contextlib.suppress(Exception):
            from oandapyV20.endpoints.trades import TradeDetails

            t = api.request(TradeDetails(accountID=account_id, tradeID=tid)).get(
                "trade", {}
            )
            realized_pl = float(t.get("realizedPL", 0.0))
        df.loc[match.index, "profit_usd"] = round(realized_pl, 2)
        df.loc[match.index, "exit_reason"] = exit_reason
        df.loc[match.index, "exit_time"] = datetime.now(timezone.utc).isoformat()
        df.to_csv(TRADE_LOG_PATH, index=False)
    except Exception as e:
        logger.warning(f"⚠️ Backfill error {instrument}: {e}")


def _api_acct(api, account_id):
    """Resolve api client and account_id: use passed values, else fallback to config_oanda."""
    if api is None or account_id is None:
        _api, _acct = _get_defaults()
        api = api if api is not None else _api
        account_id = account_id if account_id is not None else _acct
    return api, account_id


if __name__ == "__main__":
    print("=" * 60)
    print("  trading_core.py  —  self-test")
    print("=" * 60)

    errors = 0

    # 1. _get_defaults()
    print("\n【1】_get_defaults() 从 config_oanda 拿默认值")
    try:
        _api, _acct = _get_defaults()
        print(f"  api     : {'OK (oandapyV20.API)' if _api else 'MISSING'}")
        print(f"  account : {_acct or 'MISSING'}")
        if not _api or not _acct:
            errors += 1
    except Exception as e:
        print(f"  FAIL: {e}")
        errors += 1

    # 2. _api_acct() 三件套
    print("\n【2】_api_acct() 回退逻辑")
    api2, acct2 = _api_acct(None, None)
    print(
        f"  (None, None)   → account={acct2}  ✅"
        if acct2
        else f"  (None, None)   → MISSING ❌"
    )

    api3, acct3 = _api_acct("FAKE_API", "FAKE_ACCT")
    print(
        f"  (fake, fake)   → account={acct3}  ✅"
        if acct3 == "FAKE_ACCT"
        else f"  FAIL ❌"
    )

    # 3. format_price_for_instrument
    print("\n【3】format_price_for_instrument()")
    tests = [
        ("JPY", 150.1234, "150.123"),
        ("USD", 1.087654, "1.08765"),
        ("EUR", 0.9234, "0.92340"),
    ]
    for pfx, val, expect in tests:
        got = format_price_for_instrument(val, f"EUR_{pfx}")
        ok = got == expect
        print(f"  {pfx}: {val} → {got} {'✅' if ok else f'❌ expect {expect}'}")
        if not ok:
            errors += 1

    # 4. get_recent_range(demo fallback)
    print("\n【4】get_recent_range() — DEMO H1 20根")
    try:
        r = get_recent_range("EUR_USD", granularity="H1", lookback=20)
        if r:
            hi, lo, last = r
            print(f"  EUR_USD H1  →  H={hi:.5f}  L={lo:.5f}  Last={last:.5f}  ✅")
        else:
            print("  None (可能市场闭市)  ⚠️  不算错")
    except Exception as e:
        print(f"  FAIL: {e}")
        errors += 1

    # 5. get_latest_price(demo fallback)
    print("\n【5】get_latest_price() — DEMO EUR_USD")
    try:
        p = get_latest_price("EUR_USD")
        print(f"  EUR_USD mid = {p}  {'✅' if p else 'MISSING ❌'}")
        if not p:
            errors += 1
    except Exception as e:
        print(f"  FAIL: {e}")
        errors += 1

    # 6. get_open_position(demo, 应返回 None 或空)
    print("\n【6】get_open_position() — DEMO EUR_USD")
    try:
        pos = get_open_position("EUR_USD")
        print(f"  position = {'FOUND' if pos else 'None (OK — 没开仓)'}  ✅")
    except Exception as e:
        print(f"  FAIL: {e}")
        errors += 1

    # 7. 真仓覆盖：显式传 live api + live account
    print("\n【7】显式传 live api + live account")
    try:
        from config_oanda import OANDA_API_TOKEN_LIVE, OANDA_ACCOUNT_ID_1_LIVE

        if OANDA_API_TOKEN_LIVE and OANDA_ACCOUNT_ID_1_LIVE:
            live_api = API(access_token=OANDA_API_TOKEN_LIVE, environment="live")
            p = get_latest_price(
                "EUR_USD", api=live_api, account_id=OANDA_ACCOUNT_ID_1_LIVE
            )
            print(f"  LIVE EUR_USD mid = {p}  {'✅' if p else 'MISSING ❌'}")
            if not p:
                errors += 1
        else:
            print("  跳过 — live token/a/c 未配置")
    except Exception as e:
        print(f"  FAIL: {e}")
        errors += 1

    # 8. 各 utils module import chain test
    print("\n【8】import chain (from utils.strategy_helpers → config_oanda)")
    try:
        from utils.strategy_helpers import OANDA_ACCOUNT_ID as ha

        print(f"  strategy_helpers.OANDA_ACCOUNT_ID = {ha}  ✅")
    except AssertionError as e:
        print(f"  ❌ {e}")
        errors += 1
    except Exception as e:
        print(f"  FAIL: {e}")
        errors += 1

    # 总结
    print("\n" + "=" * 60)
    if errors == 0:
        print("  ✅ ALL TESTS PASSED")
    else:
        print(f"  ❌ {errors} ERROR(S)")
    print("=" * 60)
