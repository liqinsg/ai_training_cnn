"""
data_guard.py — 外汇交易系统 · K 线数据边界保护 (v1.0)

解决的问题
----------
K 线数据缺失 / 市场清淡时，代码直接 `df.iloc[-n]` 取值会抛出
`IndexError: single positional indexer is out-of-bounds`，导致整轮运行中断。

本模块提供：
  1. 统一最小数据量常量 MIN_REQUIRED_BARS（默认 200，可用环境变量覆盖）
  2. 通用安全取列 get_safe_series(df, column_name, min_bars) → 不足返回 None
  3. 一组安全取值封装（safe_last / safe_iloc / safe_tail / safe_last_row），
     把裸 `.iloc[-1]` / `.iloc[-n]` / `.iloc[-n:]` 全部换成有长度保护的调用

设计约束
--------
* 数据充足时**完全不介入**：不改变任何业务公式、返回值与变量命名。
* 数据不足时**只打日志 + 优雅返回**（None / 默认值），绝不抛异常、不中断流程。
* 不 import 交易模块，保持零依赖（pandas 以外），可被任意层级安全引用。

配置方式（优先级：环境变量 > 默认值）
    MIN_REQUIRED_BARS=200        # 写在 .env / run.env 或 shell 里

Run:  python -m pytest tests/test_data_guard.py -q
"""

from __future__ import annotations

import contextlib
import logging
import os
from pathlib import Path
from typing import Any, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# ─── 1) 统一最小数据量 ───────────────────────────────────────────────────────
DEFAULT_MIN_REQUIRED_BARS = 200


def _load_dotenv_best_effort() -> None:
    """Best-effort: pick up MIN_REQUIRED_BARS from .env / run.env if present."""
    try:
        from dotenv import load_dotenv
    except Exception:  # dotenv 不是必需依赖
        return
    root = Path(__file__).resolve().parent
    for name in (".env", "run.env"):
        with contextlib.suppress(Exception):
            load_dotenv(root / name, override=False)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        value = int(float(str(raw).strip()))
    except (TypeError, ValueError):
        logger.warning(
            f"⚠️ data_guard: {name}={raw!r} 不是有效整数 → 使用默认 {default}"
        )
        return default
    if value < 1:
        logger.warning(f"⚠️ data_guard: {name}={value} < 1 → 使用默认 {default}")
        return default
    return value


_load_dotenv_best_effort()
MIN_REQUIRED_BARS = _env_int("MIN_REQUIRED_BARS", DEFAULT_MIN_REQUIRED_BARS)


# ─── 2) 长度 / 列解析基础设施 ────────────────────────────────────────────────
def _length(obj: Any) -> int:
    """安全取长度：None / 标量 / 无 len 对象一律视为 0。"""
    if obj is None:
        return 0
    try:
        return len(obj)
    except TypeError:
        return 0


def _resolve_column(df: pd.DataFrame, column_name: str) -> Optional[pd.Series]:
    """把列名解析成 Series；兼容 yfinance 的 MultiIndex 列。找不到返回 None。"""
    if not isinstance(df, pd.DataFrame):
        return None
    cols = df.columns
    try:
        if isinstance(cols, pd.MultiIndex):
            matches = [c for c in cols if column_name in tuple(str(x) for x in c)]
            if not matches:
                return None
            got = df[matches[0]]
        elif column_name in cols:
            got = df[column_name]
        else:
            return None
    except Exception:
        return None
    if isinstance(got, pd.DataFrame):  # 重名列 → 取第一列
        got = got.iloc[:, 0]
    return got if isinstance(got, pd.Series) else None


def insufficient_bars(required: int, actual: int, context: str = "") -> bool:
    """actual < required 时记录标准日志并返回 True（调用方据此跳过）。"""
    if actual >= required:
        return False
    msg = f"数据不足：需要 {required} 根，实际只有 {actual} 根 → 跳过"
    if context:
        msg += f"（{context}）"
    logger.warning(msg)
    return True


def has_min_bars(data: Any, min_bars: int | None = None, context: str = "") -> bool:
    """统一最小数据量检查。min_bars 省略时取 MIN_REQUIRED_BARS。"""
    need = MIN_REQUIRED_BARS if min_bars is None else int(min_bars)
    return not insufficient_bars(need, _length(data), context)


# ─── 3) 通用安全取列 ─────────────────────────────────────────────────────────
def get_safe_series(
    df: Any,
    column_name: str,
    min_bars: int | None = None,
    context: str = "",
) -> Optional[pd.Series]:
    """数据不足 / 列缺失 / 全空值时返回 None，由上层判断处理；否则返回该列 Series。

    bar 不足时的日志格式：
        数据不足：需要 N 根，实际只有 M 根 → 跳过
    """
    need = MIN_REQUIRED_BARS if min_bars is None else int(min_bars)

    if df is None:
        insufficient_bars(need, 0, context or column_name)
        return None
    if not has_min_bars(df, need, context or column_name):
        return None

    series = _resolve_column(df, column_name)
    if series is None:
        logger.warning(f"字段缺失：列 {column_name} 不存在 → 跳过（{context}）")
        return None
    if series.dropna().empty:
        logger.warning(f"数据无效：列 {column_name} 无有效值 → 跳过（{context}）")
        return None
    return series


# ─── 4) 安全取值封装（替代裸 .iloc） ─────────────────────────────────────────
def safe_last(series, default=None, context: str = "") -> Any:
    """替代 `series.iloc[-1]`：空序列返回 default，不抛异常。"""
    if _length(series) == 0:
        insufficient_bars(1, 0, context)
        return default
    try:
        return series.iloc[-1]
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        logger.warning(
            f"取值失败：iloc[-1] {type(exc).__name__} → 返回 {default!r}（{context}）"
        )
        return default


def safe_iloc(series, offset: int, default=None, context: str = "") -> Any:
    """替代 `series.iloc[-n]`（例如 -2、-lookback_bars）。

    越界时**不静默替换成别的数据**，直接返回 default 由上层判断处理 ——
    否则「上一根」会被错当成「上上根」，属于静默错值（比崩溃更危险）。
    需要「夹到可用长度」的窗口语义请用安全计算或 safe_tail（切片）。
    """
    n = _length(series)
    if n == 0:
        insufficient_bars(1, 0, context)
        return default
    idx = int(offset)
    if idx < -n or idx >= n:
        # idx 为负时 |idx| 就是「需要几根」，为正时是「需要到第几位」
        needed = abs(idx) if idx < 0 else idx + 1
        insufficient_bars(needed, n, context)
        return default
    try:
        return series.iloc[idx]
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        logger.warning(
            f"取值失败：iloc[{offset}] {type(exc).__name__} → 返回 {default!r}（{context}）"
        )
        return default


def safe_tail(series, n: int, context: str = "") -> Any:
    """替代 `series.iloc[-n:]`：n 夹到实际长度，切片范围永不越界。"""
    total = _length(series)
    if total == 0:
        insufficient_bars(max(int(n), 1), 0, context)
        if hasattr(series, "iloc"):
            return series.iloc[0:0]
        return pd.Series(dtype=float)
    k = max(1, min(int(n), total))
    return series.iloc[-k:]


def safe_last_row(df, default=None, context: str = "") -> Any:
    """替代 `df.iloc[-1]`（取最新一行）。"""
    if not has_min_bars(df, 1, context):
        return default
    try:
        return df.iloc[-1]
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        logger.warning(
            f"取值失败：df.iloc[-1] {type(exc).__name__} → 返回 {default!r}（{context}）"
        )
        return default


def to_float(value, default: float | None = None) -> float | None:
    """None / NaN / 非数值 → default，避免 `float(round(None, 5))` 二次崩溃。"""
    if value is None:
        return default
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if out != out:  # NaN
        return default
    return out


# ─── 5) 最小数据量不足时的「返回 / 跳过」推荐模板 ────────────────────────────
#
#  ① 有返回值的函数 → 优雅返回（最常用）
#       if not has_min_bars(df, MIN_REQUIRED_BARS, context=pair):
#           return None                                  # 或 (False, 0.0, reason)
#
#  ② 循环里跳过单个标的 → 不中断整轮
#       for pair in selected_pairs:
#           series = get_safe_series(df, "Close", min_bars=200, context=pair)
#           if series is None:
#               continue                # 日志已由 get_safe_series 打出
#
#  ③ 单点取值 → 用 safe_* 包裹裸 .iloc
#       close = safe_last(get_safe_series(df, "Close", 200, pair))
#       if close is None:
#           continue
#
#  ④ 切片 → 永远走 safe_tail，禁止手写 .iloc[-20:]
#       tail = safe_tail(diff_pct, confirm_bars, context=pair)


# ─── 6) 未闭合 K 线防护 (Look-ahead / incomplete candle audit) ────────────────
# 解决的问题：OANDA / 多数 K 线 API 返回的最新一根 K 线**永远是正在形成中
# 的**（未闭合）。如果直接拿 .iloc[-1] 来算 EMA/RSI/斜率 → 等于把「半截数据」
# 塞进指标 → 回测好看、实盘信号跳（前视偏差 / 未来信息泄露）。
#
# 本模块在**数据源层**统一切掉最后一根未闭合 K 线，一处改、全局覆盖。
# 下游所有 .iloc[-1] 取值自动安全。

# OANDA granularity → interval_minutes 映射表
# 参考 OANDA docs: https://developer.oanda.com/rest-live-v20/instrument-datatypes/#Granularity
GRANULARITY_MINUTES: dict[str, int] = {
    "S5": 5 / 60, "S10": 10 / 60, "S15": 15 / 60, "S30": 30 / 60,
    "M1": 1, "M2": 2, "M3": 3, "M4": 4, "M5": 5, "M10": 10, "M15": 15,
    "M30": 30, "H1": 60, "H2": 120, "H3": 180, "H4": 240, "H6": 360,
    "H8": 480, "H12": 720, "D": 1440, "W": 10080, "M": 43200,
}

# 默认容错：允许 K 线结束后少量漂移（API 时间戳与本机时钟的微小偏差）
CANDLE_CLOSE_TOLERANCE_SECONDS: int = 30


def granularity_to_minutes(granularity: str) -> float:
    return GRANULARITY_MINUTES.get(str(granularity).upper(), 60)


def is_latest_candle_closed(
    df: pd.DataFrame | pd.Series,
    granularity: str | None = None,
    interval_minutes: float | None = None,
) -> bool:
    if df is None or _length(df) < 2:
        return False

    if interval_minutes is None:
        if granularity is None:
            logger.warning(
                "is_latest_candle_closed: 未指定 granularity / interval_minutes "
                "→ 保守返回 False（视为未闭合）"
            )
            return False
        interval_minutes = granularity_to_minutes(granularity)

    last_time = df.index[-1] if isinstance(df, pd.DataFrame) else df.index[-1]
    if not isinstance(last_time, pd.Timestamp):
        last_time = pd.to_datetime(last_time)

    if last_time.tz is None:
        last_time = last_time.tz_localize("UTC")
    now = pd.Timestamp.now(tz=last_time.tz)

    elapsed = now - last_time
    required = pd.Timedelta(minutes=float(interval_minutes))
    tolerance = pd.Timedelta(seconds=CANDLE_CLOSE_TOLERANCE_SECONDS)

    return elapsed >= (required - tolerance)


def trim_to_closed_candles(
    df: pd.DataFrame,
    granularity: str | None = None,
    interval_minutes: float | None = None,
    context: str = "",
) -> pd.DataFrame:
    """在 DataFrame **入口处**调用：如果最后一根 K 线未闭合，切掉它。

    用法（数据源 fetch 函数末尾）：
        df = trim_to_closed_candles(df, granularity=g, context=instrument)
        return df
    """
    if df is None or df.empty:
        return df

    if not is_latest_candle_closed(df, granularity=granularity, interval_minutes=interval_minutes):
        last_ts = df.index[-1]
        before = len(df)
        df = df.iloc[:-1].copy()
        after = len(df)
        label = f" [{context}]" if context else ""
        gran_label = granularity or (f"{interval_minutes}min" if interval_minutes else "?")
        logger.warning(
            f"🔒 CANDLE_INCOMPLETE{label} — dropped latest; "
            f"gran={gran_label} last_ts={last_ts} rows {before}→{after}"
        )
    return df