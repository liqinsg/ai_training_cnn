"""utils/mc_boundary_watch.py — MC 概率带内部边界触及观察（只观察，不改仓位）。

监控当前**实际生效**的 ``prob_bands.bands[]`` 四条内部边界 Q20/Q40/Q60/Q80：

    * 边界值 = ``bands[i].price_hi``（i = 0..3），等价于 ``bands[i+1].price_lo``
    * 用「已完成 M15 K 线」的 high/low + 前一根 close 判定触及/穿越：
          touch      : L <= B <= H 且收盘未越界（影线触及）
          cross_up   : prev_close < B 且 close > B
          cross_down : prev_close > B 且 close < B
    * 记录触及方向（from_below / from_above）、candle-open 时间、边界标签
    * 按 (pair, batch, boundary, candle_open_time) 去重（跨重启累积）

契约：本模块**只读 + 只落盘**，所有函数永不抛异常；**不改变任何下单 / 仓位
决策**。不引入 pivot / ATR 距离 / 支撑阻力规则。当前所在概率带一律由 ``bands[]``
区间包含计算，**不使用**静态 ``prob_bands.current``（融合后其 index/tag 未重算）。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"

# 默认 5 带的四条内部边界标签（band_count 不同时以 band.tag 为准回退到此表）。
INTERNAL_BOUNDARY_LABELS: Tuple[str, ...] = ("Q20", "Q40", "Q60", "Q80")


def _num(value: Any) -> Optional[float]:
    """安全 float（拒绝 bool / NaN / inf）。"""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _bands(prob_bands: Any) -> List[Dict[str, Any]]:
    if not isinstance(prob_bands, dict):
        return []
    bands = prob_bands.get("bands")
    if not isinstance(bands, list):
        return []
    return [b for b in bands if isinstance(b, dict)]


def _boundary_label(band: Dict[str, Any], fallback: str) -> str:
    """由 band.tag（如 ``Q0-20``）派生内部边界标签 ``Q20``；失败回退 fallback。"""
    tag = band.get("tag")
    if isinstance(tag, str) and "-" in tag:
        upper = tag.split("-")[-1].strip()
        if upper:
            return f"Q{upper}"
    return fallback


def extract_internal_boundaries(prob_bands: Any) -> List[Tuple[str, float]]:
    """返回 ``[(label, price), ...]`` —— 除最高带外的每条带的 ``price_hi``。"""
    bands = _bands(prob_bands)
    out: List[Tuple[str, float]] = []
    for i in range(len(bands) - 1):
        value = _num(bands[i].get("price_hi"))
        if value is None:
            continue
        fallback = (
            INTERNAL_BOUNDARY_LABELS[i] if i < len(INTERNAL_BOUNDARY_LABELS) else f"Q{i}"
        )
        out.append((_boundary_label(bands[i], fallback), value))
    return out


def band_tag_for_price(prob_bands: Any, price: Any) -> str:
    """按 ``bands[]`` 区间包含返回当前带 tag；越界 → ``OUT_OF_RANGE``。

    相邻带的公共端点归**较低**带（先匹配者胜）；不使用 ``prob_bands.current``。
    """
    value = _num(price)
    if value is None:
        return "UNKNOWN"
    bands = _bands(prob_bands)
    if not bands:
        return "UNKNOWN"
    for band in bands:
        lo, hi = _num(band.get("price_lo")), _num(band.get("price_hi"))
        if lo is None or hi is None:
            continue
        if lo <= value <= hi:
            tag = band.get("tag")
            return tag if isinstance(tag, str) and tag else "UNKNOWN"
    return "OUT_OF_RANGE"


def bars_from_dataframe(df: Any, lookback: int = 200) -> List[Dict[str, Any]]:
    """把已收盘 K 线 df（DatetimeIndex，含 High/Low/Close）尾部转成升序 bar 列表。"""
    bars: List[Dict[str, Any]] = []
    try:
        tail = df.tail(int(lookback))
        for ts, row in tail.iterrows():
            bars.append(
                {
                    "open_time": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                    "high": _num(row.get("High")),
                    "low": _num(row.get("Low")),
                    "close": _num(row.get("Close")),
                }
            )
    except Exception as exc:  # pragma: no cover - 只读降级
        logger.warning("mc_boundary: bars_from_dataframe failed (%s)", exc)
        return []
    return bars


def detect_boundary_events(
    bars: Sequence[Dict[str, Any]],
    boundaries: Sequence[Tuple[str, float]],
) -> List[Dict[str, Any]]:
    """逐根（自第 2 根起，需前一根 close）判定边界触及/穿越。"""
    events: List[Dict[str, Any]] = []
    if not bars or not boundaries:
        return events
    for i in range(1, len(bars)):
        prev_close = _num((bars[i - 1] or {}).get("close"))
        bar = bars[i] or {}
        high, low, close = _num(bar.get("high")), _num(bar.get("low")), _num(bar.get("close"))
        if None in (prev_close, high, low, close):
            continue
        for label, value in boundaries:
            if value is None or not (low <= value <= high):
                continue
            if prev_close < value:
                direction = "from_below"
                kind = "cross_up" if close > value else "touch"
            elif prev_close > value:
                direction = "from_above"
                kind = "cross_down" if close < value else "touch"
            else:
                direction = "at_boundary"
                kind = "touch"
            events.append(
                {
                    "boundary": label,
                    "boundary_price": value,
                    "kind": kind,
                    "direction": direction,
                    "open_time": bar.get("open_time"),
                    "high": high,
                    "low": low,
                    "close": close,
                    "prev_close": prev_close,
                }
            )
    return events


def _dedupe_key(pair: str, batch: Any, boundary: str, open_time: Any) -> str:
    return f"{pair}|{batch}|{boundary}|{open_time}"


def _seen_keys(directory: Path, days: int = 2) -> set:
    """读取近 N 日观察文件的 dedupe_key（never raises）。"""
    seen: set = set()
    now = datetime.now(timezone.utc)
    for i in range(int(days)):
        path = directory / f"mc_boundary_watch_{(now - timedelta(days=i)).strftime('%Y%m%d')}.jsonl"
        if not path.exists():
            continue
        try:
            with open(path, "r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(row, dict) and row.get("dedupe_key"):
                        seen.add(str(row["dedupe_key"]))
        except OSError as exc:  # pragma: no cover - 只读降级
            logger.warning("mc_boundary: read %s failed (%s)", path, exc)
    return seen


def _append(directory: Path, record: Dict[str, Any]) -> Optional[str]:
    try:
        now = datetime.now(timezone.utc)
        rec = dict(record)
        rec.setdefault("ts", now.isoformat(timespec="seconds"))
        rec.setdefault("day", now.strftime("%Y-%m-%d"))
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"mc_boundary_watch_{now.strftime('%Y%m%d')}.jsonl"
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        return str(path)
    except Exception as exc:  # pragma: no cover - 审计绝不能打断运行
        logger.warning("mc_boundary: write skipped (%s)", exc)
        return None


def watch_mc_boundaries(
    pair: str,
    prob_bands: Any,
    bars: Sequence[Dict[str, Any]],
    batch: Any,
    *,
    current: Any = None,
    logs_dir: Any = None,
    seen: Optional[set] = None,
) -> Dict[str, Any]:
    """观测一个品种：算当前带 + 新增边界事件（去重后落盘）。**永不抛异常**。

    返回 ``{pair, batch, current_band, boundaries, new_events, n_new}``。
    ``seen`` 可传入共享集合以在单轮内跨品种复用（缺省从近两日文件加载）。
    """
    boundaries = extract_internal_boundaries(prob_bands)
    current_band = band_tag_for_price(prob_bands, current)
    new_events: List[Dict[str, Any]] = []
    try:
        directory = Path(logs_dir) if logs_dir is not None else LOGS_DIR
        if seen is None:
            seen = _seen_keys(directory)
        for ev in detect_boundary_events(bars, boundaries):
            key = _dedupe_key(pair, batch, ev["boundary"], ev["open_time"])
            if key in seen:
                continue
            seen.add(key)
            rec = {
                "pair": pair,
                "batch": batch,
                "boundary": ev["boundary"],
                "boundary_price": ev["boundary_price"],
                "kind": ev["kind"],
                "direction": ev["direction"],
                "open_time": ev["open_time"],
                "high": ev["high"],
                "low": ev["low"],
                "close": ev["close"],
                "prev_close": ev["prev_close"],
                "current_band": current_band,
                "current_price": _num(current),
                "applied": False,
                "dedupe_key": key,
            }
            _append(directory, rec)
            new_events.append(rec)
    except Exception as exc:  # pragma: no cover - 只读降级
        logger.warning("mc_boundary: watch failed (%s)", exc)
    return {
        "pair": pair,
        "batch": batch,
        "current_band": current_band,
        "boundaries": boundaries,
        "new_events": new_events,
        "n_new": len(new_events),
    }
