import logging

logger = logging.getLogger(__name__)

def build_top_pairs(strength_scores, all_pairs, top_n=4, min_gap=0.25):
    ranked = sorted(strength_scores.items(), key=lambda x: x[1], reverse=True)
    strongest = [c for c, _ in ranked[:top_n]]
    weakest = [c for c, _ in ranked[-top_n:]]
    best_by_sym = {}
    for base in strongest:
        for quote in weakest:
            if base == quote:
                continue
            gap = strength_scores[base] - strength_scores[quote]
            if abs(gap) < min_gap:
                continue
            sym = (
                f"{base}{quote}=X"
                if f"{base}{quote}=X" in all_pairs
                else f"{quote}{base}=X"
            )
            if sym not in all_pairs:
                continue
            abs_gap = abs(gap)
            prev = best_by_sym.get(sym)
            if prev is None or abs_gap > prev[1]:
                best_by_sym[sym] = (sym, abs_gap, base, quote)
    result = sorted(best_by_sym.values(), key=lambda x: x[1], reverse=True)
    return [p[0] for p in result[:top_n]], result[:top_n]

def calc_weighted_score(
    pair, gap, rsi_val, adx_val, xgb_prob, mc_pct_up,
    min_strength_gap=0.10,
    xgb_bullish_threshold=0.55,
    mc_bullish_threshold=55.0,
    require_direction_consensus=True,
    consensus_threshold=2,
    min_conviction_score=30.0,
    w_s=0.40, w_r=0.15, w_a=0.15, w_x=0.20, w_m=0.10,
    adx_scale_factor=2.0,
    _logger=None,
):
    log = _logger or logger
    strength_dir = (
        "BUY"
        if gap >= min_strength_gap
        else "SELL" if gap <= -min_strength_gap else "NEUTRAL"
    )
    xgb_dir = "BUY" if (xgb_prob or 0.0) >= xgb_bullish_threshold else "SELL"
    mc_dir = "BUY" if (mc_pct_up or 50.0) >= mc_bullish_threshold else "SELL"
    buy_votes = sum(1 for d in (strength_dir, xgb_dir, mc_dir) if d == "BUY")
    sell_votes = sum(1 for d in (strength_dir, xgb_dir, mc_dir) if d == "SELL")
    log.info(
        f"{pair}: Strength={strength_dir} | XGB={xgb_dir} | MC={mc_dir} | BUY={buy_votes}/3"
    )
    if require_direction_consensus:
        if buy_votes >= consensus_threshold:
            direction = "BUY"
            log.info(f"{pair}: BUY consensus ({buy_votes}/3)")
        elif sell_votes >= consensus_threshold:
            direction = "SELL"
            log.info(f"{pair}: SELL consensus ({sell_votes}/3)")
        else:
            log.info(f"{pair}: NO CONSENSUS")
            return None, None
    else:
        direction = "BUY" if gap > 0 else "SELL"
    S = max(0.0, min(100.0, abs(gap) / 3.5 * 100.0))
    rsi = max(0.0, min(100.0, rsi_val))
    R = (
        max(0.0, min(100.0, (50.0 - rsi) * 2.0))
        if direction == "BUY"
        else max(0.0, min(100.0, (rsi - 50.0) * 2.0))
    )
    A = max(0.0, min(100.0, adx_val * adx_scale_factor))
    X = max(0.0, min(100.0, (xgb_prob or 0.0) * 100.0)) or 50.0
    M = max(0.0, min(100.0, mc_pct_up if mc_pct_up is not None else 50.0))
    FINAL = S * w_s + R * w_r + A * w_a + X * w_x + M * w_m
    return direction, {
        "S": round(S, 1),
        "R": round(R, 1),
        "A": round(A, 1),
        "X": round(X, 1),
        "M": round(M, 1),
        "FINAL": round(FINAL, 1),
        "PASS": FINAL >= min_conviction_score,
        "THRESHOLD": round(min_conviction_score, 1),
    }
