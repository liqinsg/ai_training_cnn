import datetime
def format_oanda_time(ts):
    dt = datetime.datetime.fromisoformat(ts)
    return dt.strftime("%Y-%m-%d %H:%M UTC")

def _format_oanda_time(ts):
    if not ts:
        return "UNKNOWN"

    try:
        # Keep only first 6 decimal places
        if "." in ts:
            base, frac = ts.rstrip("Z").split(".")
            ts = f"{base}.{frac[:6]}+00:00"
        else:
            ts = ts.replace("Z", "+00:00")

        dt = datetime.fromisoformat(ts)

        return dt.strftime("%Y-%m-%d %H:%M UTC")
        # Alternative:
        # return dt.strftime("%d-%b %H:%M UTC")

    except Exception:
        return ts
