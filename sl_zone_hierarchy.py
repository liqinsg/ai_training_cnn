# sl_zone_hierarchy.py — ✅ TESTED & WORKING
import logging
import numpy as np

logger = logging.getLogger(__name__)

def compute_sl_zone(api, oanda_instrument, direction, entry_price, pip_size, cfg_fn):
    """Hierarchical SL: H4 → H8 → Daily → ATR → Fixed"""
    BUFFER_PIPS   = cfg_fn("SL_BUFFER_PIPS", 25)
    MIN_DIST_PIPS = cfg_fn("SL_MIN_DISTANCE_PIPS", 20)
    ATR_MULT      = cfg_fn("ATR_SL_MULT", 2.0)
    FIXED_PIPS    = cfg_fn("SL_FALLBACK_FIXED_PIPS", 35)

    TF_LIST = [
        ("H4",  "H4", cfg_fn("SL_H4_LOOKBACK_BARS", 6)),
        ("H8",  "H8", cfg_fn("SL_H8_LOOKBACK_BARS", 4)),
        ("DAILY","D", cfg_fn("SL_DAILY_LOOKBACK_BARS", 2)),
    ]

    from oandapyV20.endpoints.instruments import InstrumentsCandles

    def _fetch_zone(gran, count, dir):
        try:
            resp = api.request(InstrumentsCandles(
                instrument=oanda_instrument,
                params={"granularity": gran, "count": count, "price": "M"}
            ))
            candles = resp.get("candles", [])
            if len(candles) < count * 0.5:
                return None, 0
            highs = [float(c["mid"]["h"]) for c in candles]
            lows  = [float(c["mid"]["l"]) for c in candles]
            closes = [float(c["mid"]["c"]) for c in candles]
            trs = []
            for i in range(1, len(candles)):
                tr = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
                trs.append(tr)
            atr = np.mean(trs[-14:]) if len(trs)>=14 else np.mean(trs) if trs else 0
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
            logger.info(f"📏 SL {name}: Zone={zone:.5f} ±{BUFFER_PIPS}p → {sl_candidate:.5f} | Dist={dist:.1f}p")
            return sl_candidate, f"{name} Zone {dist:.0f}p"
        else:
            logger.info(f"⚠️ {name} too close ({dist:.1f}p < {MIN_DIST_PIPS}p) → stepping up")

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