import random
import time

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"

def apply_jitter(min_sec: float = 1.0, max_sec: float = 8.0) -> None:
    """在脚本主逻辑开始前增加抖动延迟，避免并发请求撞车"""
    delay = random.uniform(min_sec, max_sec)
    time.sleep(delay)    

def forex_market_closed():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo("Europe/London"))
    wd = now.weekday()

    return (
        wd == 5  # Saturday
        or (wd == 6 and now.hour < 21)  # Sunday before open
        or (wd == 4 and now.hour >= 21)  # Friday after close
    )


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
