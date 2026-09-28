import logging
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from oandapyV20.endpoints.instruments import InstrumentsCandles

logger = logging.getLogger(__name__)

def price_decimals(pair: str) -> int:
    return 3 if "JPY" in pair.upper() else 5

def pip_size(pair: str) -> float:
    return 0.01 if "JPY" in pair.upper() else 0.0001

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
    logger.debug(f"📊 Fetched {oanda_instrument} {gran} bars={len(df)}")
    return df

def calculate_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

def fetch_weekly_ema100(oanda_instrument, api):
    import contextlib

    try:
        resp = api.request(
            InstrumentsCandles(
                instrument=oanda_instrument,
                params={"granularity": "W", "count": 105, "price": "M"},
            )
        )
        candles = resp.get("candles") or []
        if len(candles) < 100:
            logger.warning(f"Weekly EMA100 {oanda_instrument}: insufficient candles")
            return None
        closes = []
        for c in candles:
            mid = c.get("mid") or {}
            with contextlib.suppress(Exception):
                closes.append(float(mid["c"]))
        if len(closes) < 100:
            return None
        ema100 = float(calculate_ema(pd.Series(closes), 100).iloc[-1])
        last_close = float(closes[-1])
        if not np.isfinite(ema100) or ema100 <= 0 or last_close <= 0:
            return None
        return ema100
    except Exception as e:
        logger.warning(f"EMA100 fetch failed: {e}")
        return None

def forex_market_closed_schedule() -> bool:
    now = datetime.now(ZoneInfo("Europe/London"))
    wd = now.weekday()
    return (
        wd == 5
        or (wd == 6 and now.hour < 21)
        or (wd == 4 and now.hour >= 21)
    )

def forex_market_closed(api, oanda_account_id: str, oanda_granularity: str) -> bool:
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
