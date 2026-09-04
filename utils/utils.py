import random
import time
import datetime

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

    """
    Calculate Stop-Loss per H4 Zone Hierarchy Rules + Max SL Cap
    ────────────────────────────────────────────────────────────
    SELL: SL = max(H4 highs of last 4 CLOSED candles) + 20 pips
    BUY:  SL = min(H4 lows of last 4 CLOSED candles)  - 20 pips
    Cap:  If SL distance > 200 pips → abort trade (return skip=True)
    
    IMPORTANT: h4_candles MUST contain ONLY fully closed H4 candles
               — EXCLUDE the current forming candle always
    
    Args:
        side: 'BUY' or 'SELL'
        entry_price: Opening execution price
        h4_candles: List of H4 candle dicts [{"high":x,"low":y}, ...]
        pip_size: 0.0001 for non-JPY pairs, 0.01 for JPY pairs
    
    Returns:
        (sl_price: float, sl_pips: float, skip_trade: bool)
    """
    # ─── Validate Input ───
    if len(h4_candles) < REQUIRED_H4_CANDLES:
        raise ValueError(
            f"Insufficient H4 candles: need ≥{REQUIRED_H4_CANDLES}, got {len(h4_candles)} — "
            "Ensure forming candle was removed before calling this function"
        )

    # ─── Calculate SL per H4 Zone Hierarchy ───
    if side.upper() == "SELL":
        ref_level = max(c["high"] for c in h4_candles)
        sl_price  = ref_level + (SL_OFFSET_PIPS * pip_size)
        sl_pips   = (sl_price - entry_price) / pip_size  # Always positive

    elif side.upper() == "BUY":
        ref_level = min(c["low"] for c in h4_candles)
        sl_price  = ref_level - (SL_OFFSET_PIPS * pip_size)
        sl_pips   = (entry_price - sl_price) / pip_size  # Always positive

    else:
        raise ValueError(f"Invalid order side: '{side}' — must be 'BUY' or 'SELL'")

    # ─── Enforce Max SL Cap ───
    if sl_pips > SL_MAX_ALLOWED_PIPS:
        skip_trade = True
        print(
            f"🚫 SL TOO LARGE — TRADE ABORTED | Side: {side} | Ref: {ref_level:.5f} | "
            f"Entry: {entry_price:.5f} | SL: {sl_price:.5f} | "
            f"Distance: {sl_pips:.1f} pips | MAX ALLOWED: {SL_MAX_ALLOWED_PIPS}"
        )
    else:
        skip_trade = False
        print(
            f"✅ SL ACCEPTED | Side: {side} | Ref: {ref_level:.5f} | "
            f"Entry: {entry_price:.5f} | SL: {sl_price:.5f} | "
            f"Distance: {sl_pips:.1f} pips"
        )

    return sl_price, sl_pips, skip_trade