import logging
import numpy as np
from oandapyV20.endpoints.instruments import InstrumentsCandles

logger = logging.getLogger(__name__)

SL_OFFSET_PIPS = 20
SL_MAX_ALLOWED_PIPS = 200
REQUIRED_H4_CANDLES = 4

def price_decimals(pair: str) -> int:
    return 3 if "JPY" in pair.upper() else 5

def _sl_cap_for(instrument: str = "") -> float:
    if "JPY" in (instrument or "").upper():
        return 300.0
    return SL_MAX_ALLOWED_PIPS

def calculate_stop_loss(
    side: str, entry_price: float, h4_candles, pip_size: float, instrument: str = ""
) -> tuple[float, float, bool]:
    if len(h4_candles) < REQUIRED_H4_CANDLES:
        raise ValueError(
            f"⚠️ H4 candle count insufficient: need ≥{REQUIRED_H4_CANDLES}, got {len(h4_candles)} — "
            "Did you forget to remove the forming candle? Use h4_data[:-1]"
        )

    if side.upper() == "SELL":
        ref_level = max(c["high"] for c in h4_candles)
        sl_price = ref_level + (SL_OFFSET_PIPS * pip_size)
        sl_pips = (sl_price - entry_price) / pip_size
    elif side.upper() == "BUY":
        ref_level = min(c["low"] for c in h4_candles)
        sl_price = ref_level - (SL_OFFSET_PIPS * pip_size)
        sl_pips = (entry_price - sl_price) / pip_size
    else:
        raise ValueError(f"Invalid order side: '{side}' — use BUY or SELL")

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

def calculate_hybrid_sl(
    instrument, direction, entry_price, h4_closed, atr_value, pip_sz
):
    decimals = price_decimals(instrument)

    try:
        h4_sl, h4_pips, h4_skip = calculate_stop_loss(
            direction, entry_price, h4_closed, pip_sz, instrument
        )
        h4_sl = round(h4_sl, decimals)
    except Exception:
        logger.exception(
            "H4 SL calculation failed for %s — falling back to ATR guard", instrument
        )
        h4_sl = h4_pips = h4_skip = None

    try:
        atr_offset = atr_value * 2.0
        if direction == "BUY":
            atr_sl = round(entry_price - atr_offset, decimals)
        else:
            atr_sl = round(entry_price + atr_offset, decimals)
        atr_pips = atr_offset / pip_sz
        atr_skip = atr_pips > SL_MAX_ALLOWED_PIPS
    except Exception:
        logger.exception(
            "ATR guard SL calculation failed for %s — falling back to H4", instrument
        )
        atr_sl = atr_pips = atr_skip = None

    if h4_sl is None and atr_sl is None:
        return None, None, None, "NONE", 0, True

    if h4_sl is None:
        final_sl, chosen, final_pips, skip_trade = atr_sl, "ATR", atr_pips, atr_skip
    elif atr_sl is None:
        final_sl, chosen, final_pips, skip_trade = h4_sl, "H4", h4_pips, h4_skip
    else:
        if direction == "BUY":
            if h4_sl >= atr_sl:
                final_sl, chosen, final_pips = h4_sl, "H4", h4_pips
            else:
                final_sl, chosen, final_pips = atr_sl, "ATR-GUARD", atr_pips
        else:
            if h4_sl <= atr_sl:
                final_sl, chosen, final_pips = h4_sl, "H4", h4_pips
            else:
                final_sl, chosen, final_pips = atr_sl, "ATR-GUARD", atr_pips
        skip_trade = final_pips > SL_MAX_ALLOWED_PIPS

    return final_sl, h4_sl, atr_sl, chosen, final_pips, skip_trade

def compute_sl_zone(api, oanda_instrument, direction, entry_price, pip_size, cfg_fn):
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
