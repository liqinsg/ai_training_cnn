"""
strategy_decision.py
Drop-in Strategy & Decision layer for fx_trade_bot.
Refactored for clarity, configurable filters, and conviction-based scoring.
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
from enum import Enum
from datetime import datetime
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# 1. ENUMS & CONFIG
# ---------------------------------------------------------------------------

class Direction(Enum):
    LONG = "LONG"
    SHORT = "SHORT"

class FilterMode(Enum):
    """Control how aggressively each filter behaves.

    OFF       = disabled entirely
    PENALIZE  = reduces conviction score, never blocks (good for testing)
    BLOCK     = can kill a signal entirely (use once validated)
    """
    OFF = "off"
    PENALIZE = "penalize"
    BLOCK = "block"


@dataclass
class StrategyConfig:
    """One knob per filter. Start relaxed (OFF/PENALIZE), tighten later."""

    # --- Filter behaviour ---
    mc_filter_mode: FilterMode = FilterMode.PENALIZE
    regime_filter_mode: FilterMode = FilterMode.OFF        # <- start OFF
    adx_filter_mode: FilterMode = FilterMode.OFF           # <- start OFF
    pivot_filter_mode: FilterMode = FilterMode.PENALIZE
    strength_gap_filter_mode: FilterMode = FilterMode.PENALIZE
    cooldown_filter_mode: FilterMode = FilterMode.BLOCK    # safety only

    # --- Hard thresholds ---
    min_conviction_score: float = 45.0   # 0-100, signals below dropped
    base_min_edge: float = 0.50          # 50% for LEVEL10
    normal_min_edge: float = 0.51        # 51% for normal mode

    # --- Scoring weights (flexible, need not sum to 100) ---
    base_score: float = 25.0
    model_edge_weight: float = 30.0
    mc_alignment_weight: float = 20.0
    regime_alignment_weight: float = 0.0   # 0 while regime is OFF
    adx_weight: float = 0.0                # 0 while adx is OFF
    pivot_proximity_weight: float = 15.0
    strength_gap_weight: float = 10.0

    # --- ADX levels ---
    adx_strong: float = 25.0
    adx_moderate: float = 20.0

    # --- Pivot ---
    pivot_proximity_pct: float = 0.0015    # 0.15% to pivot = full bonus
    pivot_buffer_pips: float = 30.0        # added to spread for SL buffer

    # --- Strength gap ---
    strength_gap_threshold: float = 10.0

    # --- Close logic ---
    close_threshold: float = 0.55          # prob needed to flip & close

    # --- Selection limits ---
    max_total_trades: int = 2
    max_per_usd_group: int = 2
    max_per_jpy_group: int = 2

    # --- Execution ---
    mode: str = "LEVEL10"                  # "LEVEL10" | "NORMAL"


# ---------------------------------------------------------------------------
# 2. SIGNAL DATA CLASS
# ---------------------------------------------------------------------------

@dataclass
class Signal:
    pair: str
    oanda_symbol: str
    direction: Direction
    action: str                          # "BUY" or "SELL"
    entry_price: float
    stop_loss: float
    take_profit: float
    conviction_score: float              # 0-100
    raw_prob: float                      # model prob in signal direction
    edge: float                          # |prob - 0.5|
    model_p_up: float
    adx: float
    mc_data: Optional[dict] = None
    pivot_levels: Optional[dict] = None
    filter_notes: List[str] = field(default_factory=list)
    score_breakdown: Dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 3. STRATEGY ENGINE
# ---------------------------------------------------------------------------

class StrategyEngine:
    def __init__(self, config: StrategyConfig, model, feature_list: List[str]):
        self.cfg = config
        self.model = model
        self.features = feature_list

    # ===================================================================
    # PUBLIC API
    # ===================================================================

    def should_close(self, position_units: int,
                     latest_features: pd.Series) -> Tuple[bool, str]:
        """Decide if an open position should be closed.
        Returns: (should_close, reason_string)
        """
        p_up = self._predict(latest_features)
        p_down = 1 - p_up

        if position_units > 0 and p_down >= self.cfg.close_threshold:
            return True, f"LONG reversal: DOWN prob {p_down:.1%}"
        if position_units < 0 and p_up >= self.cfg.close_threshold:
            return True, f"SHORT reversal: UP prob {p_up:.1%}"

        return False, "hold"

    def generate_signal(self, pair: str, oanda_symbol: str,
                        df: pd.DataFrame,
                        mc_data: Optional[dict],
                        strength_scores: dict,
                        current_price: float,
                        spread_pips: float) -> Optional[Signal]:
        """
        Full pipeline for one pair:
          1. Predict
          2. Score conviction (filters add/subtract points)
          3. Build SL/TP
          4. Validate R/R
          5. Return Signal or None
        """
        notes: List[str] = []
        breakdown: Dict[str, float] = {"base": self.cfg.base_score}

        # ---- 1. Model prediction ----------------------------------------
        latest = df.iloc[-1]
        p_up = self._predict(latest)
        p_down = 1 - p_up
        adx = float(latest.get("ADX_14", 0))

        direction = Direction.LONG if p_up > p_down else Direction.SHORT
        action = "BUY" if direction == Direction.LONG else "SELL"
        raw_prob = p_up if direction == Direction.LONG else p_down
        edge = abs(raw_prob - 0.5)

        # ---- 2. Hard minimum edge check ---------------------------------
        min_prob = self.cfg.base_min_edge if self.cfg.mode == "LEVEL10" else self.cfg.normal_min_edge
        if raw_prob < min_prob:
            # Even LEVEL10 needs *some* edge; 50.0% exactly is a coin flip.
            # If you truly want 50.0 to pass, set base_min_edge=0.50 and remove this.
            notes.append(f"Raw prob {raw_prob:.2%} < min {min_prob:.2%}")
            return None

        # ---- 3. Build conviction score ----------------------------------
        score = self.cfg.base_score

        # 3a. Model edge (0 -> 0 pts, 0.20 -> full weight)
        edge_pts = self._score_model_edge(edge)
        score += edge_pts
        breakdown["model_edge"] = edge_pts

        # 3b. Monte Carlo
        mc_pts, mc_note = self._eval_mc(mc_data, direction, raw_prob, min_prob)
        if self.cfg.mc_filter_mode == FilterMode.BLOCK and mc_pts < -50:
            notes.append(f"MC BLOCK: {mc_note}")
            return None
        score += mc_pts
        breakdown["mc"] = mc_pts
        if mc_note:
            notes.append(mc_note)

        # 3c. Regime alignment
        reg_pts, reg_note = self._eval_regime(mc_data, direction)
        if self.cfg.regime_filter_mode == FilterMode.BLOCK and reg_pts < 0:
            notes.append(f"REGIME BLOCK: {reg_note}")
            return None
        score += reg_pts
        breakdown["regime"] = reg_pts
        if reg_note:
            notes.append(reg_note)

        # 3d. ADX
        adx_pts, adx_note = self._eval_adx(adx)
        if self.cfg.adx_filter_mode == FilterMode.BLOCK and adx_pts < 0:
            notes.append(f"ADX BLOCK: {adx_note}")
            return None
        score += adx_pts
        breakdown["adx"] = adx_pts
        if adx_note:
            notes.append(adx_note)

        # 3e. Pivot proximity & SL/TP construction
        pivot_pts, pivot_note, pivot_levels = self._eval_pivots(
            df, current_price, direction, spread_pips
        )
        if self.cfg.pivot_filter_mode == FilterMode.BLOCK and pivot_pts < 0:
            notes.append(f"PIVOT BLOCK: {pivot_note}")
            return None
        score += pivot_pts
        breakdown["pivot"] = pivot_pts
        if pivot_note:
            notes.append(pivot_note)

        # 3f. Currency strength gap
        gap_pts, gap_note = self._eval_strength_gap(strength_scores, pair, direction)
        if self.cfg.strength_gap_filter_mode == FilterMode.BLOCK and gap_pts < 0:
            notes.append(f"GAP BLOCK: {gap_note}")
            return None
        score += gap_pts
        breakdown["strength_gap"] = gap_pts
        if gap_note:
            notes.append(gap_note)

        # Clamp
        score = max(0.0, min(100.0, score))
        breakdown["final"] = score

        if score < self.cfg.min_conviction_score:
            notes.append(f"Score {score:.1f} < min {self.cfg.min_conviction_score}")
            return None

        # ---- 4. SL / TP -------------------------------------------------
        sl, tp = self._build_sl_tp(
            pair, direction, current_price, pivot_levels, spread_pips
        )
        if sl is None or tp is None:
            notes.append("SL/TP build failed")
            return None

        # ---- 5. Hard R/R safety check -----------------------------------
        if not self._valid_rr(direction, current_price, sl, tp):
            notes.append(
                f"R/R invalid: entry={current_price}, SL={sl}, TP={tp}"
            )
            return None

        return Signal(
            pair=pair,
            oanda_symbol=oanda_symbol,
            direction=direction,
            action=action,
            entry_price=round(current_price, 5),
            stop_loss=sl,
            take_profit=tp,
            conviction_score=round(score, 1),
            raw_prob=round(raw_prob, 4),
            edge=round(edge, 4),
            model_p_up=round(p_up, 4),
            adx=round(adx, 2),
            mc_data=mc_data,
            pivot_levels=pivot_levels,
            filter_notes=notes,
            score_breakdown=breakdown,
        )

    def select_signals(self, signals: List[Signal]) -> List[Signal]:
        """Rank by conviction and enforce group limits."""
        signals.sort(key=lambda s: s.conviction_score, reverse=True)

        winners: List[Signal] = []
        usd_count = jpy_count = 0

        for sig in signals:
            if "USD=X" in sig.pair and sig.pair != "USDJPY=X":
                if usd_count >= self.cfg.max_per_usd_group:
                    continue
                usd_count += 1
            if "JPY" in sig.pair:
                if jpy_count >= self.cfg.max_per_jpy_group:
                    continue
                jpy_count += 1
            if len(winners) >= self.cfg.max_total_trades:
                break
            winners.append(sig)

        return winners

    # ===================================================================
    # INTERNAL SCORING METHODS
    # ===================================================================

    def _predict(self, latest: pd.Series) -> float:
        """Wrapper around sklearn model predict_proba."""
        X = pd.DataFrame([latest[self.features]])
        return float(self.model.predict_proba(X)[0, 1])

    def _score_model_edge(self, edge: float) -> float:
        """Edge 0.00 -> 0 pts. Edge 0.20 -> full weight."""
        normalized = min(edge / 0.20, 1.0)
        return normalized * self.cfg.model_edge_weight

    def _eval_mc(self, mc_data: Optional[dict], direction: Direction,
                 model_prob: float, min_prob: float) -> Tuple[float, str]:
        if mc_data is None or self.cfg.mc_filter_mode == FilterMode.OFF:
            return 0.0, ""

        percentile = mc_data.get("percentile_rank", 50)
        if not (1 <= percentile <= 99):
            # Extreme percentile = broken MC or extreme day. Heavy penalty.
            return -100.0, f"Extreme percentile {percentile}"

        mc_p_up = mc_data.get("p_up", 0.5)
        mc_p_down = mc_data.get("p_down", 0.5)
        mc_prob = mc_p_up if direction == Direction.LONG else mc_p_down
        mc_dir = Direction.LONG if mc_p_up > mc_p_down else Direction.SHORT

        if mc_dir == direction:
            # Aligned: bonus scaled by MC edge
            mc_edge = abs(mc_prob - 0.5)
            bonus = min(mc_edge / 0.15, 1.0) * self.cfg.mc_alignment_weight
            return bonus, f"MC aligned {mc_prob:.1%} (+{bonus:.1f})"
        else:
            # Disagree: penalty
            penalty = -self.cfg.mc_alignment_weight * 0.6
            note = f"MC disagrees {mc_prob:.1%} ({penalty:.1f})"
            # Extra penalty if MC is confident against us
            if abs(mc_prob - 0.5) > 0.10:
                penalty -= self.cfg.mc_alignment_weight * 0.2
                note += ", MC confident against"
            return penalty, note

    def _eval_regime(self, mc_data: Optional[dict],
                     direction: Direction) -> Tuple[float, str]:
        if mc_data is None or self.cfg.regime_filter_mode == FilterMode.OFF:
            return 0.0, ""

        regime = str(mc_data.get("regime", ""))
        up = "Uptrend" in regime
        down = "Downtrend" in regime

        if up and direction == Direction.LONG:
            return self.cfg.regime_alignment_weight, "Uptrend+LONG"
        if down and direction == Direction.SHORT:
            return self.cfg.regime_alignment_weight, "Downtrend+SHORT"
        if up and direction == Direction.SHORT:
            return -self.cfg.regime_alignment_weight * 0.5, "Uptrend+SHORT"
        if down and direction == Direction.LONG:
            return -self.cfg.regime_alignment_weight * 0.5, "Downtrend+LONG"

        return 0.0, f"Regime={regime}"

    def _eval_adx(self, adx: float) -> Tuple[float, str]:
        if self.cfg.adx_filter_mode == FilterMode.OFF:
            return 0.0, ""

        if adx >= self.cfg.adx_strong:
            pts = self.cfg.adx_weight
            return pts, f"ADX strong {adx:.1f} (+{pts:.1f})"
        elif adx >= self.cfg.adx_moderate:
            ratio = (adx - self.cfg.adx_moderate) / (
                self.cfg.adx_strong - self.cfg.adx_moderate
            )
            pts = ratio * self.cfg.adx_weight
            return pts, f"ADX moderate {adx:.1f} (+{pts:.1f})"
        else:
            penalty = -self.cfg.adx_weight * 0.5
            return penalty, f"ADX weak {adx:.1f} ({penalty:.1f})"

    def _eval_pivots(self, df: pd.DataFrame, current_price: float,
                     direction: Direction, spread_pips: float
                     ) -> Tuple[float, str, Optional[dict]]:
        """
        Returns (score_points, note, pivot_dict).
        pivot_dict may be None if daily data insufficient.
        """
        if self.cfg.pivot_filter_mode == FilterMode.OFF:
            return 0.0, "", None

        # Resample to daily for pivots
        try:
            daily = self._resample_daily(df)
            if len(daily) < 2:
                return 0.0, "No daily data for pivots", None
        except Exception:
            return 0.0, "Pivot resample failed", None

        prev = daily.iloc[-2]
        pivots = self._calculate_pivots(
            prev["High"], prev["Low"], prev["Close"]
        )

        # Measure distance to relevant pivot
        if direction == Direction.LONG:
            # For BUY, ideal entry near S1 or P (support)
            dist_s1 = abs(current_price - pivots["S1"]) / current_price
            dist_p = abs(current_price - pivots["P"]) / current_price
            best_dist = min(dist_s1, dist_p)
            label = "S1" if dist_s1 < dist_p else "P"
        else:
            # For SELL, ideal entry near R1 or P (resistance)
            dist_r1 = abs(current_price - pivots["R1"]) / current_price
            dist_p = abs(current_price - pivots["P"]) / current_price
            best_dist = min(dist_r1, dist_p)
            label = "R1" if dist_r1 < dist_p else "P"

        # Score: 0 distance -> full weight, 2x threshold -> 0
        ratio = max(0.0, 1.0 - (best_dist / (self.cfg.pivot_proximity_pct * 2)))
        pts = ratio * self.cfg.pivot_proximity_weight

        note = f"Pivot {label} dist={best_dist:.4f} (+{pts:.1f})"
        return pts, note, pivots

    def _eval_strength_gap(self, strength_scores: dict, pair: str,
                           direction: Direction) -> Tuple[float, str]:
        if self.cfg.strength_gap_filter_mode == FilterMode.OFF:
            return 0.0, ""

        # Parse pair like "EURUSD=X" -> base=EUR, quote=USD
        base = pair[:3]
        quote = pair[3:6]

        base_score = strength_scores.get(base, 50)
        quote_score = strength_scores.get(quote, 50)
        gap = abs(base_score - quote_score)

        if gap < self.cfg.strength_gap_threshold:
            return 0.0, f"Gap {gap:.1f} below threshold"

        # Bonus if direction aligns with strength
        if direction == Direction.LONG and base_score > quote_score:
            pts = self.cfg.strength_gap_weight
            return pts, f"Strength gap {gap:.1f} favors LONG (+{pts:.1f})"
        if direction == Direction.SHORT and quote_score > base_score:
            pts = self.cfg.strength_gap_weight
            return pts, f"Strength gap {gap:.1f} favors SHORT (+{pts:.1f})"

        # Penalty if fighting the strength gap
        penalty = -self.cfg.strength_gap_weight * 0.5
        return penalty, f"Strength gap {gap:.1f} against signal ({penalty:.1f})"

    # ===================================================================
    # SL / TP & SAFETY
    # ===================================================================

    def _build_sl_tp(self, pair: str, direction: Direction,
                     entry: float, pivots: Optional[dict],
                     spread_pips: float) -> Tuple[Optional[float], Optional[float]]:
        """Build SL/TP from pivots. Falls back to ATR if pivots invalid."""
        is_jpy = "JPY" in pair
        pip = 0.01 if is_jpy else 0.0001
        decimals = 3 if is_jpy else 5
        buffer = (spread_pips + self.cfg.pivot_buffer_pips) * pip

        if pivots:
            if direction == Direction.SHORT:
                sl = round(max(pivots["R1"], pivots["P"]) + buffer, decimals)
                tp = round(pivots["S1"], decimals)
            else:
                sl = round(min(pivots["S1"], pivots["P"]) - buffer, decimals)
                tp = round(pivots["R1"], decimals)

            # Validate pivot-based levels
            if self._valid_rr(direction, entry, sl, tp):
                return sl, tp

        # ---- Fallback: ATR-based SL/TP ---------------------------------
        # If you have ATR in your df, use it. Otherwise use fixed 50 pips.
        # This keeps you trading even when pivots are far away.
        atr_sl_pips = 50.0  # default
        atr_tp_pips = 75.0  # 1.5:1 rough R/R

        if direction == Direction.SHORT:
            sl = round(entry + atr_sl_pips * pip + buffer, decimals)
            tp = round(entry - atr_tp_pips * pip, decimals)
        else:
            sl = round(entry - atr_sl_pips * pip - buffer, decimals)
            tp = round(entry + atr_tp_pips * pip, decimals)

        if self._valid_rr(direction, entry, sl, tp):
            return sl, tp

        return None, None

    @staticmethod
    def _valid_rr(direction: Direction, entry: float,
                  sl: float, tp: float) -> bool:
        """Hard safety: SL and TP must be on correct sides of entry."""
        if direction == Direction.SHORT:
            return sl > entry > tp
        else:
            return tp > entry > sl

    # ===================================================================
    # HELPERS (imported/adapted from original bot)
    # ===================================================================

    @staticmethod
    def _resample_daily(df: pd.DataFrame) -> pd.DataFrame:
        if not isinstance(df.index, pd.DatetimeIndex):
            raise ValueError("DataFrame needs DatetimeIndex")
        return (
            df.resample("D")
            .agg({
                "Open": "first",
                "High": "max",
                "Low": "min",
                "Close": "last",
                "Volume": "sum",
            })
            .dropna()
        )

    @staticmethod
    def _calculate_pivots(prev_high, prev_low, prev_close,
                          pivot_type: str = "Classic") -> dict:
        h, l, c = float(prev_high), float(prev_low), float(prev_close)
        rng = h - l
        if pivot_type == "Classic":
            p = (h + l + c) / 3
            return {
                "R3": round(p + 2 * rng, 5),
                "R2": round(p + rng, 5),
                "R1": round(2 * p - l, 5),
                "P": round(p, 5),
                "S1": round(2 * p - h, 5),
                "S2": round(p - rng, 5),
                "S3": round(p - 2 * rng, 5),
            }
        # Extend with Fibonacci / Camarilla / Woodie if needed
        return {}


# ---------------------------------------------------------------------------
# 4. INTEGRATION EXAMPLE (how to wire into fx_trade_bot.py)
# ---------------------------------------------------------------------------
"""
# In fx_trade_bot.py, replace the decision block with:

from strategy_decision import StrategyConfig, StrategyEngine, FilterMode

config = StrategyConfig(
    mode=MODE,
    mc_filter_mode=FilterMode.PENALIZE,
    regime_filter_mode=FilterMode.OFF,      # <- toggle ON later
    adx_filter_mode=FilterMode.OFF,         # <- toggle ON later
    pivot_filter_mode=FilterMode.PENALIZE,
    strength_gap_filter_mode=FilterMode.PENALIZE,
    min_conviction_score=45.0,              # <- lower = more trades
)
engine = StrategyEngine(config, model, features)

# --- Close check ---
for pair in DEFAULT_PAIRS:
    oanda = YAHOO_TO_OANDA[pair]
    pos = get_open_position(oanda)
    if not pos:
        continue
    df = build_features(get_data(pair, oanda, 200)).dropna()
    if len(df) < 5:
        continue
    should_close, reason = engine.should_close(pos["units"], df.iloc[-1])
    if should_close:
        print(f"CLOSE {pair}: {reason}")
        close_position(oanda)
        last_closed[pair] = (Direction.LONG if pos["units"] > 0 else Direction.SHORT, REOPEN_DELAY_RUNS)

# --- New signals ---
candidates = []
for pair in DEFAULT_PAIRS:
    # ... cooldown check ...
    oanda = YAHOO_TO_OANDA[pair]
    if get_open_position(oanda):
        continue
    df = build_features(get_data(pair, oanda, 200)).dropna()
    if len(df) < 20:
        continue

    # Get current price & spread
    try:
        tick = api.request(InstrumentsCandles(
            instrument=oanda,
            params={"count": 1, "granularity": "M1", "price": "BA"}
        ))["candles"][0]
        current = float(tick["mid"]["c"])
        spread_pips = abs(float(tick["ask"]["c"]) - float(tick["bid"]["c"])) / (0.01 if "JPY" in pair else 0.0001)
    except Exception:
        current = df.iloc[-1]["Close"]
        spread_pips = 1.0

    mc_data, _ = load_mc(pair)
    sig = engine.generate_signal(pair, oanda, df, mc_data, strength_scores, current, spread_pips)
    if sig:
        candidates.append(sig)
        print(f"SIGNAL {pair}: score={sig.conviction_score}, notes={sig.filter_notes}")
    else:
        print(f"NO SIGNAL {pair}")

# --- Select & execute ---
winners = engine.select_signals(candidates)
for w in winners:
    res = open_oanda_order({
        "pair": w.oanda_symbol,
        "action": w.action,
        "stop_loss": w.stop_loss,
        "take_profit": w.take_profit,
    })
    print(f"EXECUTED {w.pair} | Score={w.conviction_score} | SL={w.stop_loss} | TP={w.take_profit}")
    print(f"  Breakdown: {w.score_breakdown}")
    print(f"  Notes: {w.filter_notes}")
"""