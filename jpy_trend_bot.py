from __future__ import annotations
import logging
from typing import Dict, List, Tuple, Optional, Any
import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 策略内部依赖 —— 无全局config导入
from utils.ml_confirmation import ml_filter
from utils.range_detector import is_sideways
from utils.find_support_resistence import get_support_resistance 
from utils.trading_core import (
    get_latest_news_sentiment, get_news_risk_bias,
    validate_signal_with_fundamentals, get_ensemble_consensus, execute_market_trade
)
from utils.strategy_helpers import (
    get_atr_with_volatility_context, check_ma5_alignment,
    confirmed_breakout, get_live_prices, build_strength_matrix,
    format_strength_ranking, NewsFilter
)
from utils.logging_utils import get_logger
# ──────────────────────────────────────────────
# 共用Logger：外部传入，统一日志格式/输出
# ──────────────────────────────────────────────
DEFAULT_LOGGER = get_logger("jpy_trend_bot")

# ──────────────────────────────────────────────
# 数据结构：参数包（显式约定字段）
# ──────────────────────────────────────────────
class OANDAConfig:
    """OANDA执行层参数 —— 认证/环境/交易配置"""
    def __init__(
        self,
        api_key: str,
        account_id: str,
        environment: str = "practice",
        max_slippage_pips: float = 1.5,
        execution_timeout_sec: int = 10,
    ):
        self.api_key = api_key
        self.account_id = account_id
        self.environment = environment
        self.max_slippage_pips = max_slippage_pips
        self.execution_timeout_sec = execution_timeout_sec

    def to_dict(self) -> Dict[str, Any]:
        return {
            "api_key": f"***{self.api_key[-4:] if len(self.api_key) > 4 else '***'}",
            "account_id": self.account_id,
            "environment": self.environment,
            "max_slippage_pips": self.max_slippage_pips,
        }


class StrategyConfig:
    """策略运行参数 —— 风控/阈值/开关，与OANDA完全解耦"""
    def __init__(self, params: Dict[str, Any]):
        # ── 交易对 ──
        self.TRADE_PAIRS: List[str] = params["TRADE_PAIRS"]
        # ── JPY基础单位 ──
        self.JPY_PIP: float = params["JPY_PIP"]
        # ── 强度阈值 ──
        self.MIN_MARKET_STRENGTH: float = params["MIN_MARKET_STRENGTH"]
        self.MIN_DOMINANCE_RATIO: float = params.get("MIN_DOMINANCE_RATIO", 0.6)
        # ── 对齐/筛选 ──
        self.REQUIRE_ALIGNED: int = params["REQUIRE_ALIGNED"]
        self.MIN_VALID_PAIRS_TO_TRADE: int = params["MIN_VALID_PAIRS_TO_TRADE"]
        self.SKIP_SIDEWAYS_PAIRS: bool = params["SKIP_SIDEWAYS_PAIRS"]
        self.TRADE_TOP_PAIRS: int = params.get("TRADE_TOP_PAIRS", 1)
        # ── SL/TP基础 ──
        self.SL_BUFFER_PIPS: float = params["SL_BUFFER_PIPS"]
        self.SPREAD_PIPS: float = params["SPREAD_PIPS"]
        self.MIN_RR: float = params["MIN_RR"]
        self.FRONT_RUN_PIPS: float = params["FRONT_RUN_PIPS"]
        self.MACRO_PROTECTION_PIPS: float = params["MACRO_PROTECTION_PIPS"]
        # ── ATR体系 ──
        self.ENABLE_ATR_SLTP: bool = params["ENABLE_ATR_SLTP"]
        self.JPY_ATR_PERIOD: int = params["JPY_ATR_PERIOD"]
        self.JPY_ATR_HISTORY_LOOKBACK: int = params["JPY_ATR_HISTORY_LOOKBACK"]
        self.JPY_ATR_SL_MULTIPLIER_NORMAL: float = params["JPY_ATR_SL_MULTIPLIER_NORMAL"]
        self.JPY_ATR_SL_MULTIPLIER_HIGH_VOL: float = params["JPY_ATR_SL_MULTIPLIER_HIGH_VOL"]
        self.JPY_ATR_SL_MULTIPLIER_LOW_VOL: float = params["JPY_ATR_SL_MULTIPLIER_LOW_VOL"]
        self.JPY_ATR_RR_MULTIPLE: float = params["JPY_ATR_RR_MULTIPLE"]
        # ── 层级保护 ──
        self.ENABLE_MACRO_PROTECTION: bool = params["ENABLE_MACRO_PROTECTION"]
        self.ENABLE_BREAKOUT_CONFIRMATION: bool = params["ENABLE_BREAKOUT_CONFIRMATION"]
        self.BREAKOUT_CONFIRMATION_CLOSES: int = params["BREAKOUT_CONFIRMATION_CLOSES"]
        # ── 趋势/过滤 ──
        self.ENABLE_EMA_TREND: bool = params["ENABLE_EMA_TREND"]
        self.ENABLE_NEWS_FILTER: bool = params["ENABLE_NEWS_FILTER"]
        self.ENABLE_RANGE_DETECTOR: bool = params.get("ENABLE_RANGE_DETECTOR", True)
        # ── 附加 ──
        self.PROFILE_LABEL: str = params.get("PROFILE_LABEL", "unnamed_profile")
        self._raw = params

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def __repr__(self) -> str:
        return f"<StrategyConfig: {self.PROFILE_LABEL} | {len(self.TRADE_PAIRS)} pairs>"


# ──────────────────────────────────────────────
# Bot主类：一个实例 = 一套完整运行环境
# ──────────────────────────────────────────────
class JPYTrendBot:
    """
    JPY趋势策略交易Bot —— 全封装一体实例
    • 构造时传入全部参数，运行零外部依赖
    • 共用Logger：外部统一传入，日志可聚合
    • 多实例并行：不同profile/OANDA账号互不干扰
    • 无磁盘写入、无全局单例、无隐式配置加载
    """

    def __init__(
        self,
        strategy_config: Dict[str, Any] | StrategyConfig,
        oanda_config: OANDAConfig,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Args:
            strategy_config: 策略运行参数字典/对象
            oanda_config: OANDA执行配置（认证/环境）
            logger: 外部共用Logger，不传则用默认
        """
        # ── 配置层 ──
        self.cfg = (
            strategy_config if isinstance(strategy_config, StrategyConfig)
            else StrategyConfig(strategy_config)
        )
        self.oanda = oanda_config

        # ── 共用日志 ──
        self.logger = logger or DEFAULT_LOGGER
        self._log_prefix = f"[{self.cfg.PROFILE_LABEL}]"

        # ── 筛选JPY交易对 ──
        self.jpy_pairs: List[str] = [p for p in self.cfg.TRADE_PAIRS if p.endswith("_JPY")]
        if dropped := [p for p in self.cfg.TRADE_PAIRS if not p.endswith("_JPY")]:
            self.logger.warning(f"{self._log_prefix} Non-JPY pairs dropped: {dropped}")

        # ── 内部组件 ──
        self._news_filter = NewsFilter()
        self._last_signal: Optional[Dict[str, Any]] = None

        # ── 启动确认 ──
        self.logger.info(
            f"{self._log_prefix} Bot initialized | "
            f"Pairs={len(self.jpy_pairs)} | "
            f"OANDA={self.oanda.environment} | "
            f"MinRR={self.cfg.MIN_RR}"
        )

    # ────────── 核心运行入口 ──────────
    def run_cycle(self) -> Dict[str, Any]:
        """执行一次完整交易周期 —— 主程序唯一调用方法"""
        self.logger.info(f"{self._log_prefix} === START CYCLE ===")
        result = {
            "profile": self.cfg.PROFILE_LABEL,
            "timestamp": None,
            "status": "pending",
            "signal": None,
            "reason": None,
        }

        try:
            # Step 1: 强度矩阵
            scores = build_strength_matrix()
            self.logger.debug(f"{self._log_prefix} Strength matrix built")

            # Step 2: 生成信号
            signals = self._generate_signals(scores)
            if not signals:
                result.update(status="hold", reason="No valid signal")
                self.logger.info(f"{self._log_prefix} → HOLD: no valid signal")
                return result

            signal = signals[0]
            result["signal"] = signal
            self.logger.info(
                f"{self._log_prefix} SIGNAL: {signal['action']} {signal['pair']} "
                f"Entry={signal['entry']} SL={signal['stop_loss']} TP={signal['take_profit']} "
                f"RR={signal['risk_reward']}"
            )

            # Step 3: 新闻风控
            news = get_news_risk_bias(signal["pair"])
            if news["impact"] >= 2:
                result.update(status="hold", reason=f"High news impact: {news['impact']}")
                self.logger.info(f"{self._log_prefix} → HOLD: news impact too high")
                return result

            # Step 4: 基本面校验
            sentiment = get_latest_news_sentiment()
            ok, reason = validate_signal_with_fundamentals(signal, sentiment)
            if not ok:
                result.update(status="rejected", reason=f"Fundamentals: {reason}")
                self.logger.info(f"{self._log_prefix} → REJECTED: {reason}")
                return result

            # Step 5: 最终确认 & 执行
            report_text = self._build_report(scores, signal)
            final_signal, _ = get_ensemble_consensus(report_text)
            if final_signal:
                execute_market_trade(final_signal)
                result["status"] = "executed"
                self.logger.info(f"{self._log_prefix} ✅ TRADE EXECUTED")
            else:
                result["status"] = "withheld"
                self.logger.info(f"{self._log_prefix} → WITHHELD by consensus")

        except Exception as e:
            result.update(status="error", reason=str(e))
            self.logger.error(f"{self._log_prefix} Cycle failed: {e}", exc_info=True)

        return result

    # ────────── 信号生成逻辑 ──────────
    def _generate_signals(self, scores: Dict[str, float]) -> List[Dict[str, Any]]:
        """核心策略逻辑 —— 全部读取自self.cfg"""
        self._news_filter.reset_cycle()

        # JPY相对强度排名
        jpy_score = scores.get("JPY", 0.0)
        ranked = sorted(
            [
                (pair, scores.get(pair.split("_")[0], 0.0) - jpy_score)
                for pair in self.jpy_pairs
            ],
            key=lambda x: abs(x[1]),
            reverse=True,
        )

        max_gap = max((abs(v) for _, v in ranked), default=0.0)
        if max_gap < self.cfg.MIN_MARKET_STRENGTH:
            self.logger.info(f"{self._log_prefix} Strength gap {max_gap:.4f} below floor {self.cfg.MIN_MARKET_STRENGTH}")
            max_gap = self.cfg.MIN_MARKET_STRENGTH

        valid_signals: List[Dict[str, Any]] = []

        for pair, strength in ranked:
            # 动态阈值过滤
            if abs(strength) < max_gap * 0.4:
                self.logger.debug(f"{self._log_prefix} {pair}: strength too low → skip")
                continue

            # 新闻过滤
            avoid, reason = self._news_filter.should_avoid_pair(pair)
            if avoid:
                self.logger.info(f"{self._log_prefix} {pair}: news risk → {reason}")
                continue

            # 横盘过滤
            if self.cfg.SKIP_SIDEWAYS_PAIRS:
                sideways, sreason, _ = is_sideways(pair)
                if sideways:
                    self.logger.info(f"{self._log_prefix} {pair}: sideways → skip")
                    continue

            # 趋势对齐
            direction = check_ma5_alignment(pair, require_aligned=self.cfg.REQUIRE_ALIGNED)
            if direction is None:
                self.logger.info(f"{self._log_prefix} {pair}: mixed alignment → skip")
                continue

            # 方向一致性校验
            if (direction == "BUY" and strength < 0) or (direction == "SELL" and strength > 0):
                self.logger.info(f"{self._log_prefix} {pair}: direction mismatch → skip")
                continue

            # ML过滤
            avoid_ml, ml_reason = ml_filter.should_avoid_pair(pair, direction)
            if avoid_ml:
                self.logger.info(f"{self._log_prefix} {pair}: ML filter → {ml_reason}")
                continue

            # 价格数据
            prices = get_live_prices(pair)
            if not prices:
                continue

            # 支撑阻力
            daily = get_support_resistance(pair, granularity="D", count=60, window=3)
            weekly = get_support_resistance(pair, granularity="W", count=52, window=2)
            if None in (daily["support"], daily["resistance"], weekly["support"], weekly["resistance"]):
                continue

            # SL/TP计算
            entry, sl, tp, ref, ttype = self._calc_levels(pair, direction, prices, daily, weekly)
            if not entry:
                continue

            # 风控校验
            risk = abs(entry - sl)
            reward = abs(tp - entry)
            rr = reward / risk if risk > 0 else 0
            if rr < self.cfg.MIN_RR:
                self.logger.info(f"{self._log_prefix} {pair}: RR {rr:.2f} < {self.cfg.MIN_RR} → skip")
                continue

            valid_signals.append({
                "pair": pair,
                "action": direction,
                "entry": round(entry, 5),
                "stop_loss": round(sl, 5),
                "take_profit": round(tp, 5),
                "risk_reward": round(rr, 2),
                "strength_score": round(strength, 4),
                "reasoning": f"{ref} | {ttype}",
            })

        if len(valid_signals) < self.cfg.MIN_VALID_PAIRS_TO_TRADE:
            self.logger.info(f"{self._log_prefix} Valid pairs {len(valid_signals)} < minimum {self.cfg.MIN_VALID_PAIRS_TO_TRADE}")
            return []

        # 选最强信号
        return sorted(valid_signals, key=lambda x: abs(x["strength_score"]), reverse=True)[:1]

    # ────────── SL/TP层级计算 ──────────
    def _calc_levels(self, pair, direction, prices, daily, weekly):
        """统一ATR/结构双模式"""
        PIP = self.cfg.JPY_PIP

        if self.cfg.ENABLE_ATR_SLTP:
            atr, z_score = get_atr_with_volatility_context(
                pair, self.cfg.JPY_ATR_PERIOD, self.cfg.JPY_ATR_HISTORY_LOOKBACK
            )
            if not atr or atr <= 0:
                return None, None, None, None, None

            z = z_score or 0
            mult = (
                self.cfg.JPY_ATR_SL_MULTIPLIER_HIGH_VOL if z > 1 else
                self.cfg.JPY_ATR_SL_MULTIPLIER_LOW_VOL if z < -1 else
                self.cfg.JPY_ATR_SL_MULTIPLIER_NORMAL
            )
            sl_dist = atr * mult
            tp_dist = sl_dist * self.cfg.JPY_ATR_RR_MULTIPLE

            if direction == "BUY":
                entry = prices["ask"]
                sl = entry - sl_dist
                tp = entry + tp_dist
                if self.cfg.ENABLE_MACRO_PROTECTION and entry > weekly["resistance"] - self.cfg.MACRO_PROTECTION_PIPS * PIP:
                    return None, None, None, None, None
            else:
                entry = prices["bid"]
                sl = entry + sl_dist
                tp = entry - tp_dist
                if self.cfg.ENABLE_MACRO_PROTECTION and entry < weekly["support"] + self.cfg.MACRO_PROTECTION_PIPS * PIP:
                    return None, None, None, None, None

            return entry, sl, tp, f"ATR×{mult:.1f}", f"ATR×{mult*self.cfg.JPY_ATR_RR_MULTIPLE:.1f}"

        # 结构模式
        if direction == "BUY":
            entry = prices["ask"]
            sl = daily["support"] - (self.cfg.SL_BUFFER_PIPS + self.cfg.SPREAD_PIPS) * PIP
            broke = (
                confirmed_breakout(pair, daily["resistance"], "above", closes=self.cfg.BREAKOUT_CONFIRMATION_CLOSES)
                if self.cfg.ENABLE_BREAKOUT_CONFIRMATION else entry > daily["resistance"]
            )
            tp = (weekly["resistance"] if broke else daily["resistance"]) - self.cfg.FRONT_RUN_PIPS * PIP
            if self.cfg.ENABLE_MACRO_PROTECTION and entry > weekly["resistance"] - self.cfg.MACRO_PROTECTION_PIPS * PIP:
                return None, None, None, None, None
            if tp <= entry or sl >= entry:
                return None, None, None, None, None
            return entry, sl, tp, "Daily Support", "Weekly Resistance" if broke else "Daily Resistance"

        else:  # SELL
            entry = prices["bid"]
            sl = daily["resistance"] + (self.cfg.SL_BUFFER_PIPS + self.cfg.SPREAD_PIPS) * PIP
            broke = (
                confirmed_breakout(pair, daily["support"], "below", closes=self.cfg.BREAKOUT_CONFIRMATION_CLOSES)
                if self.cfg.ENABLE_BREAKOUT_CONFIRMATION else entry < daily["support"]
            )
            tp = (weekly["support"] if broke else daily["support"]) + self.cfg.FRONT_RUN_PIPS * PIP
            if self.cfg.ENABLE_MACRO_PROTECTION and entry < weekly["support"] + self.cfg.MACRO_PROTECTION_PIPS * PIP:
                return None, None, None, None, None
            if tp >= entry or sl <= entry:
                return None, None, None, None, None
            return entry, sl, tp, "Daily Resistance", "Weekly Support" if broke else "Daily Support"

    # ────────── 报告输出 ──────────
    def _build_report(self, scores, signal) -> str:
        ranking = " | ".join(f"{p}({s:+.3f})" for p, s in sorted(
            [(pair, scores.get(pair.split("_")[0], 0) - scores.get("JPY", 0)) for pair in self.jpy_pairs],
            key=lambda x: abs(x[1]), reverse=True
        ))
        return f"""
PROFILE: {self.cfg.PROFILE_LABEL}
OANDA_ENV: {self.oanda.environment}
RANKING: {ranking}
SIGNAL: {signal['action']} {signal['pair']}
ENTRY: {signal['entry']} | SL: {signal['stop_loss']} | TP: {signal['take_profit']}
RR: {signal['risk_reward']}
"""

    # ────────── 状态查询 ──────────
    def get_last_signal(self) -> Optional[Dict[str, Any]]:
        return self._last_signal

    def get_status(self) -> Dict[str, Any]:
        return {
            "profile": self.cfg.PROFILE_LABEL,
            "oanda_env": self.oanda.environment,
            "pairs_count": len(self.jpy_pairs),
            "last_signal": self._last_signal,
        }
