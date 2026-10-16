import logging
from datetime import datetime, timezone
from oandapyV20.endpoints.trades import TradesList

logger = logging.getLogger(__name__)


def _parse_oanda_time(s):
    s = s.rstrip("Z")
    if "." in s:
        head, frac = s.split(".")
        s = f"{head}.{frac[:6]}"
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def recent_tp_close_mins(api, account_id, instrument, owner_tag=None):
    """Minutes since the latest TP fill on this instrument, or None."""
    try:
        resp = api.request(TradesList(account_id, params={
            "instrument": instrument, "state": "CLOSED", "count": 10}))
    except Exception as e:
        logger.warning(f"⚠️ cooldown lookup failed {instrument}: {e} (fail-OPEN)")
        return None
    latest = None
    for t in resp.get("trades", []):
        if t.get("takeProfitOrder", {}).get("state") != "FILLED":
            continue
        if owner_tag and t.get("clientExtensions", {}).get("tag") != owner_tag:
            continue
        ct = _parse_oanda_time(t["closeTime"])
        latest = ct if latest is None or ct > latest else latest
    if latest is None:
        return None
    return (datetime.now(timezone.utc) - latest).total_seconds() / 60
