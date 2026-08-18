# =============================================================
# portfolio_balance.py
# ⚖️ Balanced Long/Short Selection — v6.8
# Minimize main bot changes: import + 1 call
# =============================================================

import logging

logger = logging.getLogger(__name__)


def apply_balance(all_candidates, max_open, min_per_side=1, max_ratio=0.75, prefer_balanced=True):
    """
    Re-select candidates to enforce balanced LONG/SHORT.
    all_candidates: list of tuples (-score, score, pair, oanda, direction, ...)
    Returns re-sorted balanced list.
    """
    if not all_candidates:
        return all_candidates

    # Split directions
    longs = [c for c in all_candidates if c[4] == "BUY"]
    shorts = [c for c in all_candidates if c[4] == "SELL"]
    total = len(all_candidates)
    max_open = min(max_open, total)

    logger.info(f"⚖️ PRE-BALANCE: LONG={len(longs)} SHORT={len(shorts)} | MAX_RATIO={max_ratio:.2f}")

    # Nothing to balance
    if len(longs) == 0 or len(shorts) == 0:
        logger.warning("⚠️ ALL SAME DIRECTION — cannot balance, keeping original ranking")
        return all_candidates[:max_open]

    if not prefer_balanced:
        return all_candidates[:max_open]

    # Calculate limits
    max_long_count = max(1, int(max_open * max_ratio))
    max_short_count = max(1, int(max_open * max_ratio))
    take_per_side = max_open // 2  # target near-even split

    # Pick top from each side
    selected_longs = longs[:min(take_per_side, max_long_count)]
    selected_shorts = shorts[:min(take_per_side, max_short_count)]

    # Combine & fill remaining slots with highest score overall
    combined = selected_longs + selected_shorts
    used = {c[2] for c in combined}
    remaining = max_open - len(combined)

    for c in all_candidates:
        if remaining <= 0:
            break
        if c[2] not in used:
            # Respect per-side caps when filling
            if c[4] == "BUY" and c not in selected_longs and len(selected_longs) < max_long_count:
                combined.append(c)
                selected_longs.append(c)
                remaining -= 1
            elif c[4] == "SELL" and c not in selected_shorts and len(selected_shorts) < max_short_count:
                combined.append(c)
                selected_shorts.append(c)
                remaining -= 1

    # Re-sort final list by score (highest first)
    combined.sort()
    final_longs = [c for c in combined if c[4] == "BUY"]
    final_shorts = [c for c in combined if c[4] == "SELL"]

    logger.info(f"✅ BALANCED: LONG={len(final_longs)} SHORT={len(final_shorts)} | MAX={max_open}")
    return combined


# =============================================================
# CONFIG LOOKUP — call this from your bot
# =============================================================
def balance_from_config(all_candidates, max_open, cfg_fn):
    """Read settings from config_bot via cfg_bot()"""
    if not cfg_fn("ENFORCE_LONGS_SHORTS", True):
        return all_candidates[:max_open]

    return apply_balance(
        all_candidates,
        max_open,
        min_per_side=cfg_fn("MIN_PER_SIDE", 1),
        max_ratio=cfg_fn("MAX_RATIO", 0.75),
        prefer_balanced=cfg_fn("PREFER_BALANCED", True),
    )