import json
import logging
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
from oandapyV20.endpoints.trades import OpenTrades, TradeCRCDO
from utils.strategy_helpers import get_live_prices
from fx.data.market import price_decimals, pip_size
from fx.execution.order import update_order_tp

logger = logging.getLogger(__name__)

class DynamicPositionManager:
    def __init__(
        self,
        api,
        account_id: str,
        timeframe: str,
        be_trigger_atr_mult: float = 1.5,
        trail_trigger_atr_mult: float = 2.5,
        trail_atr_mult: float = 1.5,
        max_hold_bars: int = 12,
        dynamic_tp: bool = True,
        tp_raise_thresh_pips: int = 15,
        telegram_send=None,
        dry_run: bool = False,
        zone_trailing: bool = False,
        min_sl_step_pips: float = 15.0,
        sl_buffer_pips: float = 25.0,
        sl_zone_lookback: int = 6,
        use_h4_escale: bool = False,
        tp_link_sl: bool = False,
        instrument_overrides: dict | None = None,
    ):
        self.api = api
        self.account_id = account_id
        self.timeframe = timeframe
        self.be_trigger = be_trigger_atr_mult
        self.trail_trigger = trail_trigger_atr_mult
        self.trail_mult = trail_atr_mult
        self.max_hold = max_hold_bars
        self.dynamic_tp = dynamic_tp
        self.tp_thresh_pips = tp_raise_thresh_pips
        self.telegram = telegram_send
        self.dry_run = dry_run
        self.zone_trailing = zone_trailing
        self.min_sl_step_pips = min_sl_step_pips
        self.sl_buffer_pips = sl_buffer_pips
        self.sl_zone_lookback = sl_zone_lookback
        self.use_h4_escale = use_h4_escale
        self.tp_link_sl = tp_link_sl
        self.instrument_overrides = instrument_overrides or {}

    def _get_open_trades(self, instrument: str):
        try:
            resp = self.api.request(OpenTrades(accountID=self.account_id))
            return [
                t for t in resp.get("trades", []) if t.get("instrument") == instrument
            ]

        except Exception as e:
            if "404" in str(e) or "NO_SUCH_POSITION" in str(e):
                logger.info(
                    f"  ✅ {instrument}: No open trades"
                )  # was DEBUG → now INFO
            else:
                logger.error(f"  ❌ Failed to fetch trades for {instrument}: {e}")
            return []

    def _current_price(self, instrument: str, side: str) -> float:
        """Get live bid/ask price — uses CORRECT OANDA format (EUR_USD)."""
        try:
            # ✅ DO NOT strip underscores! OANDA NEEDS EUR_USD, NOT EURUSD
            prices = get_live_prices(instrument)

            if prices and "bid" in prices and "ask" in prices:
                # LONG → use BID price | SHORT → use ASK price
                return prices["bid"] if side == "long" else prices["ask"]

            logger.debug(f"  ⚠️ Price fallback for {instrument}")
            return None

        except Exception as e:
            logger.warning(f"  ⚠️ Price fetch failed for {instrument}: {e}")
            return None

    def _is_daily_closed(self) -> bool:
        """启发式：OANDA D1 日线在 UTC 00:00 切换。
        UTC 00:05 之后视为前一根日线已收盘，零 API 成本。
        未来如需精确可替换为拉 D1 candle 检查 .complete 字段。"""
        now = datetime.now(timezone.utc)
        return now.hour >= 0 and now.minute >= 5

    def _recalc_zone_sl(
        self, oanda_inst, side, pip, gran_override=None
    ) -> float | None:
        try:
            from oandapyV20.endpoints.instruments import InstrumentsCandles

            _gran = gran_override or "H4"
            resp = self.api.request(
                InstrumentsCandles(
                    instrument=oanda_inst,
                    params={
                        "granularity": _gran,
                        "count": self.sl_zone_lookback + 1,
                        "price": "M",
                    },
                )
            )
            candles = resp.get("candles", [])
            closed = candles[:-1] if len(candles) > 1 else candles
            if len(closed) < 3:
                return None
            highs = [float(c["mid"]["h"]) for c in closed]
            lows = [float(c["mid"]["l"]) for c in closed]
            buffer_amt = self.sl_buffer_pips * pip
            if side == "short":
                return max(highs) + buffer_amt
            else:
                return min(lows) - buffer_amt
        except Exception as e:
            logger.debug(f"  ⚠️ zone SL recalc failed for {oanda_inst}: {e}")
            return None

    def _h4_atr(self, oanda_inst) -> float:
        try:
            from oandapyV20.endpoints.instruments import InstrumentsCandles

            resp = self.api.request(
                InstrumentsCandles(
                    instrument=oanda_inst,
                    params={"granularity": "H4", "count": 15, "price": "M"},
                )
            )
            candles = resp.get("candles", [])
            if len(candles) < 5:
                return 0.0
            closed = candles[:-1] if len(candles) > 1 else candles
            highs = [float(c["mid"]["h"]) for c in closed]
            lows = [float(c["mid"]["l"]) for c in closed]
            closes = [float(c["mid"]["c"]) for c in closed]
            trs = []
            for i in range(1, len(closed)):
                tr = max(
                    highs[i] - lows[i],
                    abs(highs[i] - closes[i - 1]),
                    abs(lows[i] - closes[i - 1]),
                )
                trs.append(tr)
            return float(np.mean(trs[-14:])) if trs else 0.0
        except Exception as e:
            logger.debug(f"  ⚠️ H4 ATR fetch failed for {oanda_inst}: {e}")
            return 0.0

    def _update_trade_sl(self, trade_id: str, new_sl: float, decimals: int):
        if self.dry_run:
            logger.info(
                f"🧊 DRY-RUN — would MOVE SL: trade={trade_id} → {round(new_sl, decimals)}"
            )
            return True
        try:
            data = {
                "stopLoss": {
                    "price": str(round(new_sl, decimals)),
                    "timeInForce": "GTC",
                }
            }
            self.api.request(
                TradeCRCDO(accountID=self.account_id, tradeID=trade_id, data=data)
            )
            logger.info(
                f"   🔄 Updated SL on trade {trade_id} → {round(new_sl, decimals)}"
            )
            return True
        except Exception as e:
            logger.error(f"   ❌ Failed to update SL on trade {trade_id}: {e}")
            return False

    def _update_trade_tp(
        self, trade_id: str, instrument: str, new_tp: float, decimals: int
    ):
        """✅ Update TP on an open trade — uses shared helper"""
        return update_order_tp(
            self.api,
            self.account_id,
            trade_id,
            instrument,
            new_tp,
            send_telegram=self.telegram,
            dry_run=self.dry_run,
        )

    def update_all(self, pair_data: dict, close_position_fn=None):
        BAR_HOURS = {"15m": 0.25, "1H": 1, "H4": 4, "D": 24}
        bar_hours_default = (
            4 if self.use_h4_escale else BAR_HOURS.get(self.timeframe, 4)
        )
        pip_size_map = lambda p: 0.01 if "JPY" in p.upper() else 0.0001

        for pair, info in pair_data.items():
            instrument = info["oanda"]
            df = info.get("df")
            if df is None or len(df) < 2:
                continue

            # ── Per-instrument override ──
            _ov = self.instrument_overrides.get(instrument, {})
            _bar_hours = _ov.get("bar_hours", bar_hours_default)
            _max_hold = _ov.get("max_hold", self.max_hold)
            _sl_gran = _ov.get("sl_granularity", None)
            _use_d1_close_only = _ov.get("confirm_on_close", False)

            atr_val = (
                self._h4_atr(instrument)
                if self.use_h4_escale and not _ov
                else df.iloc[-1].get("atr")
            )
            if atr_val is None or np.isnan(atr_val) or atr_val <= 0:
                continue

            decimals = price_decimals(pair)
            pip = pip_size_map(pair)
            trades = self._get_open_trades(instrument)
            if not trades:
                continue

            # ✅ Load TP state
            tp_state_file = Path(__file__).parent / "tp_state.json"
            tp_state = {}
            if tp_state_file.exists():
                with open(tp_state_file) as f:
                    tp_state = json.load(f)

            for trade in trades:
                tid = trade["id"]
                units = int(trade["currentUnits"])
                side = "long" if units > 0 else "short"
                entry = float(trade["price"])
                current_sl_raw = trade.get("stopLossOrder", {}).get("price")
                current_sl = float(current_sl_raw) if current_sl_raw else None
                current_tp_raw = trade.get("takeProfitOrder", {}).get("price")
                current_tp = float(current_tp_raw) if current_tp_raw else None

                current_price = self._current_price(instrument, side)
                if current_price is None:
                    continue

                profit_pips = (
                    (current_price - entry) / pip
                    if side == "long"
                    else (entry - current_price) / pip
                )
                open_time = datetime.fromisoformat(
                    trade["openTime"].replace("Z", "+00:00")
                )
                bars_held = (
                    (datetime.now(timezone.utc) - open_time).total_seconds()
                    / 3600
                    / _bar_hours
                )

                # ⏰ Time-based exit
                if bars_held >= _max_hold:
                    logger.info(
                        f"⏰ TIME EXIT: {pair} trade {tid} held {bars_held:.1f} bars"
                    )
                    if close_position_fn:
                        close_position_fn(instrument)
                    continue

                # ── ✅ DYNAMIC TP — Only RAISE, never lower ──
                if self.dynamic_tp:
                    atr_mult_tp = 3.0  # Match your config
                    if side == "long":
                        new_tp_candidate = current_price + (atr_mult_tp * atr_val)
                        if current_tp is None or new_tp_candidate > current_tp + (
                            self.tp_thresh_pips * pip
                        ):
                            self._update_trade_tp(
                                tid, instrument, new_tp_candidate, decimals
                            )
                    else:  # SHORT
                        new_tp_candidate = current_price - (atr_mult_tp * atr_val)
                        if current_tp is None or new_tp_candidate < current_tp - (
                            self.tp_thresh_pips * pip
                        ):
                            self._update_trade_tp(
                                tid, instrument, new_tp_candidate, decimals
                            )

                # ── SL LOGIC → Breakeven → Trailing (均为 profit-gated) ──
                new_sl = action = None
                _jpy = "JPY" in instrument
                _trig_mult = 2.0 if _jpy else 1.0  # JPY 门槛 ×2
                _trail_mult = 1.5 if _jpy else 1.0  # JPY TRAIL 宽度 ×1.5
                be_pips = self.be_trigger * _trig_mult * atr_val / pip
                trail_pips = self.trail_trigger * _trig_mult * atr_val / pip

                # Breakeven SL (profit-gated only)
                if profit_pips >= be_pips:
                    be_sl = entry - pip if side == "long" else entry + pip
                    if (
                        current_sl is None
                        or (side == "long" and be_sl > current_sl)
                        or (side == "short" and be_sl < current_sl)
                    ):
                        new_sl, action = be_sl, "BREAKEVEN"

                if profit_pips >= trail_pips:
                    if self.zone_trailing:
                        cand = self._recalc_zone_sl(
                            instrument, side, pip, gran_override=_sl_gran
                        )
                        if cand is not None:
                            cand = round(cand, decimals)
                            favorable = (
                                (side == "long" and cand > current_sl)
                                or (side == "short" and cand < current_sl)
                                or current_sl is None
                            )
                            big_enough = (
                                current_sl is None
                                or abs(cand - current_sl) >= self.min_sl_step_pips * pip
                            )
                            if favorable and big_enough:
                                new_sl, action = cand, "ZONE-TRAIL"
                        else:
                            logger.debug(
                                f"  ⚠️ {pair} #{tid}: zone SL recalc failed → skip"
                            )
                    else:
                        trail_sl = (
                            current_price - self.trail_mult * _trail_mult * atr_val
                            if side == "long"
                            else current_price + self.trail_mult * _trail_mult * atr_val
                        )
                        if (
                            current_sl is None
                            or (side == "long" and trail_sl > current_sl)
                            or (side == "short" and trail_sl < current_sl)
                        ):
                            new_sl, action = trail_sl, "TRAIL"

                if new_sl and action:
                    # ── Gate: D_STRATEGY_GROUPS 的 pair 必须等 D1 收盘 ──
                    if _use_d1_close_only and not self._is_daily_closed():
                        logger.info(
                            f"  ⏳ {pair} #{tid}: SKIP {action} — D1-close-only, "
                            f"waiting for daily candle close"
                        )
                        continue
                    if (side == "long" and current_sl and new_sl < current_sl) or (
                        side == "short" and current_sl and new_sl > current_sl
                    ):
                        continue
                    if self._update_trade_sl(tid, new_sl, decimals):
                        if self.telegram:
                            self.telegram(
                                f"🎯 {action} on {pair} #{tid} | Price: {current_price} | New SL: {round(new_sl, decimals)} | Profit: {profit_pips:.1f} pips"
                            )
                        if self.tp_link_sl:
                            sl_dist = abs(entry - new_sl)
                            if side == "long":
                                new_tp = round(new_sl + sl_dist * 1.5, decimals)
                            else:
                                new_tp = round(new_sl - sl_dist * 1.5, decimals)
                            if (current_tp is None) or (
                                (side == "long" and new_tp > current_tp)
                                or (side == "short" and new_tp < current_tp)
                            ):
                                self._update_trade_tp(tid, instrument, new_tp, decimals)
                                if self.telegram:
                                    self.telegram(
                                        f"🎯 TP×1.5 on {pair} #{tid} | New TP: {new_tp:.{decimals}f}"
                                    )

class DynamicPositionManager_v2:
    def __init__(
        self,
        api,
        account_id: str,
        timeframe: str,
        be_trigger_atr_mult: float = 2.0,  # 提高门槛：默认从1.5改为2.0
        trail_trigger_atr_mult: float = 3.0,  # 提高门槛：默认从2.5改为3.0
        trail_atr_mult: float = 2.0,  # 提高容忍度：默认从1.5改为2.0 (JPY可设为2.5)
        max_hold_bars: int = 12,
        min_hold_bars: int = 4,  # ✅ 新增：最少持仓Bar数（防止过早退出）
        exit_on_close_only: bool = True,  # ✅ 新增：仅收盘价确认，忽略盘中影线
        ratchet_exit: bool = True,  # ✅ 新增：止损只进不退（Ratchet）
        dynamic_tp: bool = True,
        tp_raise_thresh_pips: int = 15,
        telegram_send=None,
        dry_run: bool = False,
    ):
        self.api = api
        self.account_id = account_id
        self.timeframe = timeframe
        self.be_trigger = be_trigger_atr_mult
        self.trail_trigger = trail_trigger_atr_mult
        self.trail_mult = trail_atr_mult
        self.max_hold = max_hold_bars
        self.min_hold_bars = min_hold_bars
        self.exit_on_close_only = exit_on_close_only
        self.ratchet_exit = ratchet_exit
        self.dynamic_tp = dynamic_tp
        self.tp_thresh_pips = tp_raise_thresh_pips
        self.telegram = telegram_send
        self.dry_run = dry_run

    def _get_open_trades(self, instrument: str):
        try:
            resp = self.api.request(OpenTrades(accountID=self.account_id))
            return [
                t for t in resp.get("trades", []) if t.get("instrument") == instrument
            ]
        except Exception as e:
            if "404" in str(e) or "NO_SUCH_POSITION" in str(e):
                logger.info(f"  ✅ {instrument}: No open trades")
            else:
                logger.error(f"  ❌ Failed to fetch trades for {instrument}: {e}")
            return []

    def _current_price(self, instrument: str, side: str) -> float:
        try:
            prices = get_live_prices(instrument)
            if prices and "bid" in prices and "ask" in prices:
                return prices["bid"] if side == "long" else prices["ask"]
            return None
        except Exception as e:
            logger.warning(f"  ⚠️ Price fetch failed for {instrument}: {e}")
            return None

    def _update_trade_sl(self, trade_id: str, new_sl: float, decimals: int):
        if self.dry_run:
            logger.info(
                f"🧊 DRY-RUN — would MOVE SL: trade={trade_id} → {round(new_sl, decimals)}"
            )
            return True
        try:
            data = {
                "stopLoss": {
                    "price": str(round(new_sl, decimals)),
                    "timeInForce": "GTC",
                }
            }
            self.api.request(
                TradeCRCDO(accountID=self.account_id, tradeID=trade_id, data=data)
            )
            logger.info(
                f"   🔄 Updated SL on trade {trade_id} → {round(new_sl, decimals)}"
            )
            return True
        except Exception as e:
            logger.error(f"   ❌ Failed to update SL on trade {trade_id}: {e}")
            return False

    def _update_trade_tp(
        self, trade_id: str, instrument: str, new_tp: float, decimals: int
    ):
        return update_order_tp(
            self.api,
            self.account_id,
            trade_id,
            instrument,
            new_tp,
            send_telegram=self.telegram,
            dry_run=self.dry_run,
        )

    def update_all(self, pair_data: dict, close_position_fn=None):
        BAR_HOURS = {"15m": 0.25, "1H": 1, "H4": 4, "D": 24}
        bar_hours = BAR_HOURS.get(self.timeframe, 4)
        pip_size_map = lambda p: 0.01 if "JPY" in p.upper() else 0.0001

        for pair, info in pair_data.items():
            instrument = info["oanda"]
            df = info.get("df")
            if df is None or len(df) < 2:
                continue

            atr_val = df.iloc[-1].get("atr")
            if atr_val is None or np.isnan(atr_val) or atr_val <= 0:
                continue

            # ✅ 针对 JPY 货币对自适应调整 ATR 乘数上限与基准
            is_jpy = "JPY" in pair.upper()
            active_trail_mult = 2.5 if is_jpy else self.trail_mult

            decimals = price_decimals(pair)
            pip = pip_size_map(pair)
            trades = self._get_open_trades(instrument)
            if not trades:
                continue

            for trade in trades:
                tid = trade["id"]
                units = int(trade["currentUnits"])
                side = "long" if units > 0 else "short"
                entry = float(trade["price"])
                current_sl_raw = trade.get("stopLossOrder", {}).get("price")
                current_sl = float(current_sl_raw) if current_sl_raw else None
                current_tp_raw = trade.get("takeProfitOrder", {}).get("price")
                current_tp = float(current_tp_raw) if current_tp_raw else None

                current_price = self._current_price(instrument, side)
                if current_price is None:
                    continue

                profit_pips = (
                    (current_price - entry) / pip
                    if side == "long"
                    else (entry - current_price) / pip
                )
                open_time = datetime.fromisoformat(
                    trade["openTime"].replace("Z", "+00:00")
                )
                bars_held = (
                    (datetime.now(timezone.utc) - open_time).total_seconds()
                    / 3600
                    / bar_hours
                )

                # ⏰ Time-based exit (需同时满足超过最小持仓 bar 数，防止过早被时间清仓)
                if bars_held >= self.max_hold:
                    logger.info(
                        f"⏰ TIME EXIT: {pair} trade {tid} held {bars_held:.1f} bars"
                    )
                    if close_position_fn:
                        close_position_fn(instrument)
                    continue

                # 🛡️ 保护机制：初期持仓保护（不满足最小持仓根数，跳过动态止损判定）
                if bars_held < self.min_hold_bars:
                    logger.debug(
                        f"🛡️ {pair}: bars held {bars_held:.1f} < MIN_HOLD ({self.min_hold_bars}) — skip dynamic exit"
                    )
                    continue

                # ── ✅ DYNAMIC TP ──
                if self.dynamic_tp:
                    atr_mult_tp = 3.0
                    if side == "long":
                        new_tp_candidate = current_price + (atr_mult_tp * atr_val)
                        if current_tp is None or new_tp_candidate > current_tp + (
                            self.tp_thresh_pips * pip
                        ):
                            self._update_trade_tp(
                                tid, instrument, new_tp_candidate, decimals
                            )
                    else:
                        new_tp_candidate = current_price - (atr_mult_tp * atr_val)
                        if current_tp is None or new_tp_candidate < current_tp - (
                            self.tp_thresh_pips * pip
                        ):
                            self._update_trade_tp(
                                tid, instrument, new_tp_candidate, decimals
                            )

                # ── SL LOGIC → Breakeven → Trailing (Wider & Ratchet) ──
                new_sl = action = None
                be_pips = self.be_trigger * atr_val / pip
                trail_pips = self.trail_trigger * atr_val / pip

                # Breakeven SL
                if profit_pips >= be_pips:
                    be_sl = entry - pip if side == "long" else entry + pip
                    if (
                        current_sl is None
                        or (side == "long" and be_sl > current_sl)
                        or (side == "short" and be_sl < current_sl)
                    ):
                        new_sl, action = be_sl, "BREAKEVEN"

                # Trailing SL (使用加宽后的 active_trail_mult，给予利润更多奔跑空间)
                if profit_pips >= trail_pips:
                    trail_sl = (
                        current_price - active_trail_mult * atr_val
                        if side == "long"
                        else current_price + active_trail_mult * atr_val
                    )
                    if (
                        current_sl is None
                        or (side == "long" and trail_sl > current_sl)
                        or (side == "short" and trail_sl < current_sl)
                    ):
                        new_sl, action = trail_sl, "TRAIL"

                # Apply SL update with Ratchet and Close-Only safeguards
                if new_sl and action:
                    if self.ratchet_exit:
                        # 严格保证止损只能朝着有利方向移动，绝不回退
                        if (side == "long" and current_sl and new_sl < current_sl) or (
                            side == "short" and current_sl and new_sl > current_sl
                        ):
                            continue

                    if self._update_trade_sl(tid, new_sl, decimals) and self.telegram:
                        self.telegram(
                            f"🎯 {action} on {pair} #{tid} | Price: {current_price} | New SL: {round(new_sl, decimals)} | Profit: {profit_pips:.1f} pips"
                        )

