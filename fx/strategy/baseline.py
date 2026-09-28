import logging
import numpy as np
from datetime import datetime, timezone

from fx.data.market import calculate_ema, fetch_candles
from fx.indicator.strength import calc_weighted_score
from fx.indicator.trend import evaluate_trend_and_tp
from fx.indicator.sltp import calculate_stop_loss
from fx.strategy.base import TradeSignal

logger = logging.getLogger(__name__)

class StrategyBaseline:
    name = "baseline"

    def __init__(self, P: dict):
        self.P = P

    def evaluate(self, ctx) -> list:
        P = self.P
        log = ctx.log or logger

        pip_cache = {p: self._pip_size(p) for p in ctx.selected_pairs}
        pair_parts = {p: (p[:3], p[3:].replace("=X", "")) for p in ctx.selected_pairs}

        try:
            from utils.strategy_helpers import get_live_prices
        except Exception:
            get_live_prices = None

        all_candidates = []
        for pair in ctx.selected_pairs:
            if pair not in ctx.pair_data:
                continue
            oanda = ctx.pair_data[pair]["oanda"]
            atr_val = ctx.pair_data[pair]["atr"]
            rsi_val = ctx.pair_data[pair]["rsi"]
            adx_val = ctx.pair_data[pair]["adx"]

            d = ctx.cooldown.get(pair)
            if d and d[1] > 0:
                ctx.cooldown[pair] = (d[0], d[1] - 1)
                continue
            if d and d[1] <= 0:
                ctx.cooldown.pop(pair, None)

            if ctx.open_pos_by_oanda.get(oanda, False):
                continue

            current, spread_pips = self._get_price(
                oanda, ctx.pair_data[pair]["df"], get_live_prices
            )
            base, quote = pair_parts[pair]
            gap = ctx.strength_scores.get(base, 0) - ctx.strength_scores.get(quote, 0)

            MIN_STRENGTH_GAP = self._cfg(P, "MIN_STRENGTH_GAP", 0.10)
            if abs(gap) < MIN_STRENGTH_GAP:
                continue

            MULTI_TF_CONFLUENCE = self._cfg(P, "MULTI_TF_CONFLUENCE", False)
            if MULTI_TF_CONFLUENCE:
                if not ctx.tf_confluence.get(pair, {}).get("passes", True):
                    continue

            sig = ctx.strat_engine.generate_signal(
                pair, oanda, ctx.pair_data[pair]["df"],
                ctx.mc_cache.get(pair), ctx.strength_scores, current, spread_pips,
            )
            prob_raw = getattr(sig, "model_p_up", None) or 0.0
            mc_pct_up = ctx.mc_cache.get(pair, {}).get("p_up", 50.0)

            direction, w = calc_weighted_score(pair, gap, rsi_val, adx_val, prob_raw, mc_pct_up)
            if not (direction and w and w["PASS"]):
                continue

            TREND_FILTER_ENABLED = self._cfg(P, "TREND_FILTER_ENABLED", False)
            EMA_PERIOD_FAST = self._cfg(P, "EMA_PERIOD_FAST", 20)
            EMA_PERIOD_SLOW = self._cfg(P, "EMA_PERIOD_SLOW", 50)
            BASE_TP_PIPS = self._cfg(P, "BASE_TP_PIPS", 60)
            MC_STRONG_THRESHOLD = self._cfg(P, "MC_STRONG_THRESHOLD", 0.65)
            TP_MULT = self._cfg(P, "TP_MULT", 1.0)
            TP_STRONG_MULT = self._cfg(P, "TP_STRONG_MULT", 1.5)
            EMA100_BUFFER_PIPS = self._cfg(P, "EMA100_BUFFER_PIPS", 30)
            EMA100_TP_FLOOR_PIPS = self._cfg(P, "EMA100_TP_FLOOR_PIPS", 30)
            WEEK_EMA100_FILTER_ENABLED = self._cfg(P, "WEEK_EMA100_FILTER_ENABLED", False)
            TIMEFRAME = self._cfg(P, "TIMEFRAME", "15m")

            weekly_ema100_price = ctx.weekly_ema_cache.get(oanda)
            allow_entry, smart_tp_pips, tp_info, lot_mult, tp_mult_reduce = evaluate_trend_and_tp(
                self._cfg(P, "PROFILE_NAME", "default"),
                direction, mc_pct_up, current, pip_cache[pair],
                ctx.pair_data[pair]["df"], weekly_ema100_price,
                ema_cross_filter=TREND_FILTER_ENABLED,
                fast_period=EMA_PERIOD_FAST, slow_period=EMA_PERIOD_SLOW,
                base_tp_pips=BASE_TP_PIPS, mc_strong_threshold=MC_STRONG_THRESHOLD,
                tp_mult=TP_MULT, tp_strong_mult=TP_STRONG_MULT,
                ema100_buffer_pips=EMA100_BUFFER_PIPS,
                ema100_tp_floor_pips=EMA100_TP_FLOOR_PIPS,
                week_ema100_filter_enabled=WEEK_EMA100_FILTER_ENABLED,
                timeframe=TIMEFRAME,
            )
            if not allow_entry:
                continue

            dec = 3 if "JPY" in pair else 5
            sl_price = None
            SL_USE_ZONE_HIERARCHY = self._cfg(P, "SL_USE_ZONE_HIERARCHY", True)
            if SL_USE_ZONE_HIERARCHY:
                try:
                    h4_df = fetch_candles(ctx.api, oanda, "H4", count=5)
                    if h4_df is None or len(h4_df) < 5:
                        raise ValueError("insufficient H4")
                    h4_closed = [
                        {"high": float(r["High"]), "low": float(r["Low"])}
                        for _, r in h4_df.iloc[:-1].iterrows()
                    ]
                    sl_price, sl_pips, skip_trade = calculate_stop_loss(
                        direction, current, h4_closed, pip_cache[pair]
                    )
                    if skip_trade:
                        continue
                    sl_price = round(sl_price, dec)
                except Exception:
                    pass

            if sl_price is None:
                MIN_SL_PIPS_JPY = self._cfg(P, "MIN_SL_PIPS_JPY", 30)
                MIN_SL_PIPS = self._cfg(P, "MIN_SL_PIPS", 20)
                ATR_SL_MULT = self._cfg(P, "ATR_SL_MULT", 2.0)
                sl_pips = max(
                    MIN_SL_PIPS_JPY if "JPY" in pair else MIN_SL_PIPS,
                    round(atr_val / pip_cache[pair] * ATR_SL_MULT, 1),
                )
                sl_price = (
                    round(current - sl_pips * pip_cache[pair], dec)
                    if direction == "BUY"
                    else round(current + sl_pips * pip_cache[pair], dec)
                )

            tp_price = (
                round(current + smart_tp_pips * pip_cache[pair], dec)
                if direction == "BUY"
                else round(current - smart_tp_pips * pip_cache[pair], dec)
            )

            sig = TradeSignal(
                pair=pair, oanda=oanda, direction=direction,
                entry_price=current, sl_price=sl_price, tp_price=tp_price,
                score_final=w["FINAL"], score_s=w["S"], score_r=w["R"],
                score_a=w["A"], score_x=w["X"], score_m=w["M"],
                pip_size=pip_cache[pair], decimals=dec,
                tp_pips=smart_tp_pips, lot_mult=lot_mult,
            )
            all_candidates.append(sig)

        all_candidates.sort(key=lambda s: -s.score_final)
        return all_candidates

    @staticmethod
    def _cfg(P, key, default):
        return P.get(key, default)

    @staticmethod
    def _pip_size(pair):
        return 0.01 if "JPY" in pair.upper() else 0.0001

    @staticmethod
    def _get_price(oanda, df, get_live_prices=None):
        try:
            if get_live_prices:
                prices = get_live_prices(oanda)
                if prices and "bid" in prices and "ask" in prices:
                    ps = 0.01 if "JPY" in oanda.upper() else 0.0001
                    return prices["bid"], abs(prices["ask"] - prices["bid"]) / ps
        except Exception:
            pass
        return float(df.iloc[-1]["Close"]), 1.0
