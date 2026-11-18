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
    extreme  ``ATR_pct ≥ 1.8``   （仅兜底，不作默认）

第二轴（仅前向）：``D_skew = |q50 − P0| / (q95 − q05)``，在等高带宽下区分
「单边趋势 vs 双向震荡」。q50 仅在 MC schema 1.2.0 起写入，缺失 → ``None``。

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
THRESH_EXTREME = 1.8   # ATR_pct ≥ 1.8 → 极端（仅兜底，不作默认）
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
    """把 ATR_pct 归入 ``narrow`` / ``normal`` / ``wide`` / ``extreme``（非法 → ``unknown``）。"""
    value = _num(atr_pct)
    if value is None:
        return "unknown"
    if value < THRESH_NARROW:
        return "narrow"
    if value < THRESH_WIDE:
        return "normal"
    if value < THRESH_EXTREME:
        return "wide"
    return "extreme"


def compute_d_skew(mc_snapshot: Any, current_price: Any) -> Optional[float]:
    """第二轴 ``D_skew = |q50 − P0| / (q95 − q05)``（等高带宽下区分趋势 vs 双向震荡）。

    仅**前向**：q50 仅 MC schema 1.2.0 起写入（``distribution.quantiles["0.50"]``）。
    不可用（无 q50 / 带宽 ≤ 0 / 非法）→ ``None``；永不抛异常。
    """
    price = _num(current_price)
    if not isinstance(mc_snapshot, dict) or price is None:
        return None
    try:
        dist = mc_snapshot.get("distribution") or {}
        quantiles = dist.get("quantiles") or {}
        q50 = quantiles.get("0.50") or quantiles.get("50") or quantiles.get(0.5)
        if q50 is None:
            return None
        rng = mc_snapshot.get("range_90") or dist.get("range_90") or []
        if not (isinstance(rng, (list, tuple)) and len(rng) == 2):
            return None
        q05, q95 = _num(rng[0]), _num(rng[1])
        q50 = _num(q50)
        if q05 is None or q95 is None or q50 is None or q95 <= q05:
            return None
        return round(abs(q50 - price) / (q95 - q05), 4)
    except Exception:  # pragma: no cover - 防御：绝不向上传播
        return None


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


def update_trade_id(
    logs_dir: Any, client_order_id: str, trade_id: str
) -> Optional[str]:
    """下单返回后回填 ``trade_id``（与 exit_audit 主键 ``trade_id`` join 的唯一键）。

    读取当日 ``logs/wide_range_shadow_YYYYMMDD.jsonl`` → 匹配 ``client_order_id``
    且尚未回填的行 → 写回。**never raises**；失败仅告警返回 ``None``。
    """
    try:
        if not client_order_id or not trade_id:
            return None
        day = datetime.now(timezone.utc).strftime("%Y%m%d")
        directory = Path(logs_dir) if logs_dir is not None else LOGS_DIR
        path = directory / f"wide_range_shadow_{day}.jsonl"
        if not path.exists():
            return None
        rows: List[Dict[str, Any]] = []
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if (
                    isinstance(row, dict)
                    and row.get("client_order_id") == client_order_id
                    and not row.get("trade_id")
                ):
                    row["trade_id"] = trade_id
                rows.append(row)
        with open(path, "w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        return str(path)
    except Exception as exc:  # pragma: no cover - 回填绝不能打断运行
        logger.warning("wide_range: update_trade_id skipped (%s)", exc)
        return None


if __name__ == "__main__":
    # 自测：极端档分类 + D_skew（无 q50 → None；有 q50 → 计算）
    assert classify_tier(0.5) == "narrow"
    assert classify_tier(1.0) == "normal"
    assert classify_tier(1.5) == "wide"
    assert classify_tier(2.1) == "extreme"
    assert classify_tier(None) == "unknown"
    assert compute_d_skew({"range_90": [1.09, 1.11]}, 1.10) is None
    d = compute_d_skew(
        {"range_90": [1.09, 1.11], "distribution": {"quantiles": {"0.50": 1.105}}},
        1.10,
    )
    print(f"tier OK | D_skew={d}（|1.105-1.10|/0.02=0.25）")
    assert d is not None and abs(d - 0.25) < 0.01
    print("✅ wide_range 自测通过")
