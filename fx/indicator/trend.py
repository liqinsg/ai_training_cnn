import logging
from fx.data.market import calculate_ema

logger = logging.getLogger(__name__)

def evaluate_trend_and_tp(
    profile_name,
    direction,
    mc_pct_up,
    entry_price,
    pip_value,
    df,
    weekly_ema100,
    ema_cross_filter,
    fast_period,
    slow_period,
    base_tp_pips,
    mc_strong_threshold,
    tp_mult,
    tp_strong_mult,
    ema100_buffer_pips=30,
    ema100_tp_floor_pips=30,
    week_ema100_filter_enabled=False,
    timeframe="15m",
):
    current_price = entry_price
    if ema_cross_filter:
        ema_fast = calculate_ema(df["Close"], fast_period)
        ema_slow = calculate_ema(df["Close"], slow_period)
        fv, sv = ema_fast.iloc[-1], ema_slow.iloc[-1]
        if direction == "BUY" and not (current_price > fv and fv > sv):
            return (
                False,
                0.0,
                f"TREND_FILTER_BLOCKED: TREND MISALIGNED: Price>{fv:.5f}>{sv:.5f}",
                1.0,
                1.0,
            )
        if direction == "SELL" and not (current_price < fv and fv < sv):
            return (
                False,
                0.0,
                f"TREND_FILTER_BLOCKED: TREND MISALIGNED: Price<{fv:.5f}<{sv:.5f}",
                1.0,
                1.0,
            )
    mc_momentum = mc_pct_up / 100.0
    tp_pips = (
        base_tp_pips * tp_strong_mult
        if mc_momentum >= mc_strong_threshold
        else base_tp_pips * tp_mult
    )
    if not week_ema100_filter_enabled:
        return True, tp_pips, "OK: WEEKLY_EMA_SKIPPED", 1.0, 1.0
    if weekly_ema100 is not None and ema_cross_filter:
        if direction == "BUY":
            min_tp_pips = (
                (weekly_ema100 + ema100_tp_floor_pips * pip_value) - current_price
            ) / pip_value
        else:
            min_tp_pips = (
                current_price - (weekly_ema100 - ema100_tp_floor_pips * pip_value)
            ) / pip_value
        tp_pips = max(tp_pips, min_tp_pips)
    lot_mult = 1.0
    tp_mult_reduce = 1.0
    if weekly_ema100 is not None and pip_value > 0:
        dist_pips = abs(current_price - weekly_ema100) / pip_value
        if dist_pips <= ema100_buffer_pips:
            if direction == "BUY" and current_price < weekly_ema100:
                return (
                    False,
                    0.0,
                    f"WAIT_EMA_ALIGNMENT: WAIT_ABOVE_WEEKLY_EMA100 {weekly_ema100:.5f} dist={dist_pips:.1f}p",
                    1.0,
                    1.0,
                )
            if direction == "SELL" and current_price > weekly_ema100:
                return (
                    False,
                    0.0,
                    f"WAIT_EMA_ALIGNMENT: WAIT_BELOW_WEEKLY_EMA100 {weekly_ema100:.5f} dist={dist_pips:.1f}p",
                    1.0,
                    1.0,
                )
            lot_mult = 0.5
            tp_mult_reduce = 0.8
            tp_pips = tp_pips * tp_mult_reduce
            logger.info(
                f"BUFFER ZONE {direction}: dist={dist_pips:.1f}p ≤ {ema100_buffer_pips}p → lot×{lot_mult} TP×{tp_mult_reduce}"
            )
        else:
            logger.info(
                f"SAFE ZONE {direction}: dist={dist_pips:.1f}p > {ema100_buffer_pips}p"
            )
    return (
        True,
        tp_pips,
        f"TP={tp_pips:.1f}p (lot×{lot_mult} TP×{tp_mult_reduce})",
        lot_mult,
        tp_mult_reduce,
    )
