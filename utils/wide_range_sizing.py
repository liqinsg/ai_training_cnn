"""utils/wide_range_sizing.py — §3 宽幅震荡判别（影子层 · fx_trade_bot v685）

依据 docs/NEXT_DEV_PLAN_20261117.md §3 / §3.1（Owner 2026-11-18 拍板口径）。

只做一件事：用一个**时序敏感**的特征判别当前 pair 是否处于「宽幅震荡」
（双向扫损风险高）—— ``ATR_pct = 当日 ATR / 近 N 日 ATR 的 rolling 中位``。

为什么不用 MC 区间宽度 W？
    §3.1 实测：``W = (q95 − q05) / price × 100`` 的逐日中位在 39 个交易日里只在
    2.38 ~ 2.58% 之间波动（≈±4%），几乎不随时间变化 → 它不是时序判别器，
    只能反映跨币种差异。ATR_pct 才是「相对自身历史」的时序量。

判别分档（初步阈值，影子待验）：
    narrow   ``ATR_pct < 0.8``   （可交易）
    normal   ``0.8 ≤ ATR_pct < 1.3``
    wide     ``ATR_pct ≥ 1.3``   （双向扫损风险 ↑）→ 影子标记

契约：本模块**只读 + 只落盘**，``compute_atr_ratio()`` / ``log_wide_range_shadow()``
永不抛异常；**不改变任何下单 / 仓位 / TP 决策**（Owner 纪律 §5.5）。

验收：被标为 wide 的时段，其 SL 命中率应显著高于常态 —— 对照 ``logs/exit_audit_*.jsonl``。
"""

from __future__ import annotations

import json
import logging
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"

ATR_PERIOD = 14        # 与 bot ATRModule / ATR_SL_MULT 口径一致
LOOKBACK_DAYS = 20     # 近 20 个交易日作为 ATR 参照基准（rolling 中位）
THRESH_NARROW = 0.8    # ATR_pct < 0.8 → 窄幅
THRESH_WIDE = 1.3      # ATR_pct ≥ 1.3 → 宽幅
MIN_ATR_POINTS = 10    # 中位基准所需的最少 ATR 点数（不足 → unknown）


def _num(value: Any, default: Optional[float] = None) -> Optional[float]:
    """安全 float（拒绝 bool / NaN / inf）。"""
    if isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number or number in (float("inf"), float("-inf")):
        return default
    return number


def classify_tier(atr_pct: Any) -> str:
    """把 ATR_pct 归入 ``narrow`` / ``normal`` / ``wide``（非法 → ``unknown``）。"""
    value = _num(atr_pct)
    if value is None:
        return "unknown"
    if value < THRESH_NARROW:
        return "narrow"
    if value < THRESH_WIDE:
        return "normal"
    return "wide"


def _atr_series_from_candles(candles: Any, atr_period: int) -> List[float]:
    """从 OANDA 日线蜡烛算 ATR 时间序列（TR 的 atr_period 简单均值，与既有口径一致）。

    只使用**已收线**的日线（``complete`` 为真）——未完成的当日 K 线会低估 ATR。
    数据不足 / 结构异常 → ``[]``（绝不抛异常）。
    """
    if not isinstance(candles, list) or len(candles) < atr_period + 1:
        return []
    usable = [
        c
        for c in candles
        if isinstance(c, dict)
        and c.get("complete", True)
        and isinstance(c.get("mid"), dict)
    ]
    if len(usable) < atr_period + 1:
        return []
    try:
        highs = [float(c["mid"]["h"]) for c in usable]
        lows = [float(c["mid"]["l"]) for c in usable]
        closes = [float(c["mid"]["c"]) for c in usable]
    except (KeyError, TypeError, ValueError):
        return []

    true_ranges: List[float] = []
    prev_close = closes[0]
    for i in range(1, len(usable)):
        high, low, prev = highs[i], lows[i], prev_close
        true_ranges.append(max(high - low, abs(high - prev), abs(low - prev)))
        prev_close = closes[i]

    return [
        sum(true_ranges[i - atr_period : i]) / atr_period
        for i in range(atr_period, len(true_ranges) + 1)
    ]


def compute_atr_ratio_from_candles(
    candles: Any,
    atr_period: int = ATR_PERIOD,
    lookback_days: int = LOOKBACK_DAYS,
) -> Dict[str, Any]:
    """纯函数：由日线蜡烛算 ``ATR_pct = 当日 ATR / 近 N 日 ATR 中位``（永不抛异常）。

    返回 ``{"atr_pct", "atr_current", "atr_median", "tier", "n_points", "n_bars"}``。
    数据不足 / 中位 ≤ 0 → ``atr_pct=None`` 且 ``tier="unknown"``（fail-closed）。
    """
    out: Dict[str, Any] = {
        "atr_pct": None,
        "atr_current": None,
        "atr_median": None,
        "tier": "unknown",
        "n_points": 0,
        "n_bars": len(candles) if isinstance(candles, list) else 0,
    }
    try:
        series = _atr_series_from_candles(candles, int(atr_period))
        out["n_points"] = len(series)
        if len(series) < MIN_ATR_POINTS:
            return out
        current = series[-1]
        median = statistics.median(series[-int(lookback_days) :])
        out["atr_current"] = current
        out["atr_median"] = median
        if median <= 0:
            return out
        atr_pct = current / median
        out["atr_pct"] = atr_pct
        out["tier"] = classify_tier(atr_pct)
        return out
    except Exception:  # pragma: no cover - 防御：绝不向上传播
        logger.warning("wide_range: compute_atr_ratio_from_candles failed — unknown")
        return out


def compute_atr_ratio(
    oanda_instrument: str,
    atr_period: int = ATR_PERIOD,
    lookback_days: int = LOOKBACK_DAYS,
) -> Dict[str, Any]:
    """取该 instrument 的日线并计算 ATR_pct（只读、永不抛异常）。"""
    try:
        from utils.trading_core import get_candles
    except Exception as exc:  # pragma: no cover - environment specific
        logger.warning("wide_range: get_candles unavailable (%s) — unknown", exc)
        return compute_atr_ratio_from_candles([], atr_period, lookback_days)
    try:
        candles = get_candles(
            oanda_instrument, "D", count=int(atr_period) + int(lookback_days) + 5
        )
    except Exception as exc:
        logger.warning("wide_range: get_candles(%s) failed (%s) — unknown", oanda_instrument, exc)
        candles = []
    return compute_atr_ratio_from_candles(candles, atr_period, lookback_days)


def log_wide_range_shadow(
    record: Dict[str, Any], logs_dir: Optional[Path] = None
) -> Optional[str]:
    """追加一行影子记录到 ``logs/wide_range_shadow_YYYYMMDD.jsonl``（永不抛异常）。"""
    try:
        rec = dict(record) if isinstance(record, dict) else {}
        now = datetime.now(timezone.utc)
        rec.setdefault("ts", now.isoformat(timespec="seconds"))
        rec.setdefault("day", now.strftime("%Y-%m-%d"))
        directory = Path(logs_dir) if logs_dir is not None else LOGS_DIR
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"wide_range_shadow_{now.strftime('%Y%m%d')}.jsonl"
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        return str(path)
    except Exception as exc:  # pragma: no cover - 审计绝不能打断运行
        logger.warning("wide_range: shadow write skipped (%s)", exc)
        return None
