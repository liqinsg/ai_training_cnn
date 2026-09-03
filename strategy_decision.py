"""
strategy_decision.py — v3.0 Defensive
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
from enum import Enum
import numpy as np
import pandas as pd
from config import MAX_TOTAL_TRADES, MAX_PER_USD_GROUP, MAX_PER_JPY_GROUP


class Direction(Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class FilterMode(Enum):
    OFF = "off"
    PENALIZE = "penalize"
    BLOCK = "block"


@dataclass
class StrategyConfig:
    mc_filter_mode: FilterMode = FilterMode.PENALIZE
    regime_filter_mode: FilterMode = FilterMode.OFF
    adx_filter_mode: FilterMode = FilterMode.OFF
    pivot_filter_mode: FilterMode = FilterMode.PENALIZE
    strength_gap_filter_mode: FilterMode = FilterMode.PENALIZE
    cooldown_filter_mode: FilterMode = FilterMode.BLOCK

    min_conviction_score: float = 45.0
    base_min_edge: float = 0.50
    normal_min_edge: float = 0.51

    base_score: float = 25.0
    model_edge_weight: float = 30.0
    mc_alignment_weight: float = 20.0
    regime_alignment_weight: float = 0.0
    adx_weight: float = 0.0
    pivot_proximity_weight: float = 15.0
    strength_gap_weight: float = 10.0

    adx_strong: float = 25.0
    adx_moderate: float = 20.0

    pivot_proximity_pct: float = 0.0015
    pivot_buffer_pips: float = 30.0

    strength_gap_threshold: float = 10.0
    close_threshold: float = 0.55

    max_total_trades: int = MAX_TOTAL_TRADES
    max_per_usd_group: int = MAX_PER_USD_GROUP
    max_per_jpy_group: int = MAX_PER_JPY_GROUP

    mode: str = "LEVEL10"


@dataclass
class Signal:
    pair: str
    oanda_symbol: str
    direction: Direction
    action: str
    entry_price: float
    stop_loss: float
    take_profit: float
    conviction_score: float
    raw_prob: float
    edge: float
    model_p_up: float
    adx: float
    mc_data: Optional[dict] = None
    pivot_levels: Optional[dict] = None
    filter_notes: List[str] = field(default_factory=list)
    score_breakdown: Dict[str, float] = field(default_factory=dict)


class StrategyEngine:
    def __init__(self, config: StrategyConfig, model, feature_list: List[str], scaler=None):
        self.cfg = config
        self.model = model
        self.features = feature_list
        self.scaler = scaler

    def should_close(
        self, position_units: int, latest_features: pd.Series
    ) -> Tuple[bool, str]:
        try:
            p_up = self._predict(latest_features)
        except Exception as e:
            return False, f"predict failed: {e}"
        p_down = 1 - p_up
        if position_units > 0 and p_down >= self.cfg.close_threshold:
            return True, f"LONG reversal: DOWN prob {p_down:.1%}"
        if position_units < 0 and p_up >= self.cfg.close_threshold:
            return True, f"SHORT reversal: UP prob {p_up:.1%}"
        return False, "hold"

    def generate_signal(
        self,
        pair: str,
        oanda_symbol: str,
        df: pd.DataFrame,
        mc_data: Optional[dict],
        strength_scores: dict,
        current_price: float,
        spread_pips: float,
    ) -> Optional[Signal]:
        notes: List[str] = []
        breakdown: Dict[str, float] = {"base": self.cfg.base_score}

        if df.empty or len(df) < 5:
            return None

        latest = df.iloc[-1]

        try:
            p_up = self._predict(latest)
        except Exception as e:
            notes.append(f"Model predict failed: {e}")
            return None

        p_down = 1 - p_up
        adx = float(latest.get("ADX_14", latest.get("adx", 0)))

        direction = Direction.LONG if p_up > p_down else Direction.SHORT
        action = "BUY" if direction == Direction.LONG else "SELL"
        raw_prob = p_up if direction == Direction.LONG else p_down
        edge = abs(raw_prob - 0.5)

        min_prob = (
            self.cfg.base_min_edge
            if self.cfg.mode == "LEVEL10"
            else self.cfg.normal_min_edge
        )
        if raw_prob < min_prob:
            notes.append(f"Raw prob {raw_prob:.2%} < min {min_prob:.2%}")
            return None

        score = self.cfg.base_score

        edge_pts = self._score_model_edge(edge)
        score += edge_pts
        breakdown["model_edge"] = edge_pts

        mc_pts, mc_note = self._eval_mc(mc_data, direction, raw_prob, min_prob)
        if self.cfg.mc_filter_mode == FilterMode.BLOCK and mc_pts < -50:
            notes.append(f"MC BLOCK: {mc_note}")
            return None
        score += mc_pts
        breakdown["mc"] = mc_pts
        if mc_note:
            notes.append(mc_note)

        reg_pts, reg_note = self._eval_regime(mc_data, direction)
        if self.cfg.regime_filter_mode == FilterMode.BLOCK and reg_pts < 0:
            notes.append(f"REGIME BLOCK: {reg_note}")
            return None
        score += reg_pts
        breakdown["regime"] = reg_pts
        if reg_note:
            notes.append(reg_note)

        adx_pts, adx_note = self._eval_adx(adx)
        if self.cfg.adx_filter_mode == FilterMode.BLOCK and adx_pts < 0:
            notes.append(f"ADX BLOCK: {adx_note}")
            return None
        score += adx_pts
        breakdown["adx"] = adx_pts
        if adx_note:
            notes.append(adx_note)

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

        gap_pts, gap_note = self._eval_strength_gap(strength_scores, pair, direction)
        if self.cfg.strength_gap_filter_mode == FilterMode.BLOCK and gap_pts < 0:
            notes.append(f"GAP BLOCK: {gap_note}")
            return None
        score += gap_pts
        breakdown["strength_gap"] = gap_pts
        if gap_note:
            notes.append(gap_note)

        score = max(0.0, min(100.0, score))
        breakdown["final"] = score

        if score < self.cfg.min_conviction_score:
            notes.append(f"Score {score:.1f} < min {self.cfg.min_conviction_score}")
            return None

        sl, tp = self._build_sl_tp(
            pair, direction, current_price, pivot_levels, spread_pips
        )
        if sl is None or tp is None:
            notes.append("SL/TP build failed")
            return None

        if not self._valid_rr(direction, current_price, sl, tp):
            notes.append(f"R/R invalid: entry={current_price}, SL={sl}, TP={tp}")
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

    def _predict(self, latest: pd.Series) -> float:
        try:
            row = {f: latest.get(f, 0.0) for f in self.features}
            X = pd.DataFrame([row])
            if self.scaler is not None:
                X = self.scaler.transform(X.values)
            return float(self.model.predict_proba(X)[0, 1])
            # print(f"🔍 _predict OK: p_up={p:.6f} | row0_keys={list(row.keys())[:3]} | X_shape={X.shape}")
            # return p
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise

    def _score_model_edge(self, edge: float) -> float:
        normalized = min(edge / 0.20, 1.0)
        return normalized * self.cfg.model_edge_weight

    def _eval_mc(self, mc_data, direction, model_prob, min_prob):
        if mc_data is None or self.cfg.mc_filter_mode == FilterMode.OFF:
            return 0.0, ""
        percentile = mc_data.get("percentile_rank", 50)
        if not (1 <= percentile <= 99):
            return -100.0, f"Extreme percentile {percentile}"
        mc_p_up = mc_data.get("p_up", 0.5)
        mc_p_down = mc_data.get("p_down", 0.5)
        mc_prob = mc_p_up if direction == Direction.LONG else mc_p_down
        mc_dir = Direction.LONG if mc_p_up > mc_p_down else Direction.SHORT
        if mc_dir == direction:
            mc_edge = abs(mc_prob - 0.5)
            bonus = min(mc_edge / 0.15, 1.0) * self.cfg.mc_alignment_weight
            return bonus, f"MC aligned {mc_prob:.1%} (+{bonus:.1f})"
        else:
            penalty = -self.cfg.mc_alignment_weight * 0.6
            note = f"MC disagrees {mc_prob:.1%} ({penalty:.1f})"
            if abs(mc_prob - 0.5) > 0.10:
                penalty -= self.cfg.mc_alignment_weight * 0.2
                note += ", MC confident against"
            return penalty, note

    def _eval_regime(self, mc_data, direction):
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

    def _eval_adx(self, adx: float):
        if self.cfg.adx_filter_mode == FilterMode.OFF:
            return 0.0, ""
        if adx >= self.cfg.adx_strong:
            pts = self.cfg.adx_weight
            return pts, f"ADX strong {adx:.1f} (+{pts:.1f})"
        elif adx >= self.cfg.adx_moderate:
            ratio = (adx - self.cfg.adx_moderate) / max(
                self.cfg.adx_strong - self.cfg.adx_moderate, 0.001
            )
            pts = ratio * self.cfg.adx_weight
            return pts, f"ADX moderate {adx:.1f} (+{pts:.1f})"
        else:
            penalty = -self.cfg.adx_weight * 0.5
            return penalty, f"ADX weak {adx:.1f} ({penalty:.1f})"

    def _eval_pivots(self, df, current_price, direction, spread_pips):
        if self.cfg.pivot_filter_mode == FilterMode.OFF:
            return 0.0, "", None
        try:
            daily = self._resample_daily(df)
            if len(daily) < 2:
                return 0.0, "No daily data for pivots", None
        except Exception:
            return 0.0, "Pivot resample failed", None

        prev = daily.iloc[-2]
        pivots = self._calculate_pivots(prev["High"], prev["Low"], prev["Close"])

        if direction == Direction.LONG:
            dist_s1 = abs(current_price - pivots["S1"]) / current_price
            dist_p = abs(current_price - pivots["P"]) / current_price
            best_dist = min(dist_s1, dist_p)
            label = "S1" if dist_s1 < dist_p else "P"
        else:
            dist_r1 = abs(current_price - pivots["R1"]) / current_price
            dist_p = abs(current_price - pivots["P"]) / current_price
            best_dist = min(dist_r1, dist_p)
            label = "R1" if dist_r1 < dist_p else "P"

        ratio = max(0.0, 1.0 - (best_dist / (self.cfg.pivot_proximity_pct * 2)))
        pts = ratio * self.cfg.pivot_proximity_weight
        note = f"Pivot {label} dist={best_dist:.4f} (+{pts:.1f})"
        return pts, note, pivots

    def _eval_strength_gap(self, strength_scores, pair, direction):
        if self.cfg.strength_gap_filter_mode == FilterMode.OFF:
            return 0.0, ""
        base = pair[:3]
        quote = pair[3:6]
        base_score = strength_scores.get(base, 50)
        quote_score = strength_scores.get(quote, 50)
        gap = abs(base_score - quote_score)
        if gap < self.cfg.strength_gap_threshold:
            return 0.0, f"Gap {gap:.1f} below threshold"
        if direction == Direction.LONG and base_score > quote_score:
            pts = self.cfg.strength_gap_weight
            return pts, f"Strength gap {gap:.1f} favors LONG (+{pts:.1f})"
        if direction == Direction.SHORT and quote_score > base_score:
            pts = self.cfg.strength_gap_weight
            return pts, f"Strength gap {gap:.1f} favors SHORT (+{pts:.1f})"
        penalty = -self.cfg.strength_gap_weight * 0.5
        return penalty, f"Strength gap {gap:.1f} against signal ({penalty:.1f})"

    def _build_sl_tp(self, pair, direction, entry, pivots, spread_pips):
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
            if self._valid_rr(direction, entry, sl, tp):
                return sl, tp

        # Fallback
        atr_sl_pips = 50.0
        atr_tp_pips = 75.0
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
    def _valid_rr(direction, entry, sl, tp):
        if direction == Direction.SHORT:
            return sl > entry > tp
        else:
            return tp > entry > sl

    @staticmethod
    def _resample_daily(df):
        if not isinstance(df.index, pd.DatetimeIndex):
            raise ValueError("DataFrame needs DatetimeIndex")
        return (
            df.resample("D")
            .agg(
                {
                    "Open": "first",
                    "High": "max",
                    "Low": "min",
                    "Close": "last",
                    "Volume": "sum",
                }
            )
            .dropna()
        )

    @staticmethod
    def _calculate_pivots(prev_high, prev_low, prev_close, pivot_type="Classic"):
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
        return {}