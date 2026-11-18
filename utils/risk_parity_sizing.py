"""utils/risk_parity_sizing.py — L2 风险定额仓位（影子层 · fx_trade_bot v685）

依据 docs/NEXT_DEV_PLAN_20261117.md §2.1（Owner 2026-11-18 拍板口径）。

只做一件事：把「结构 SL 比 ATR 应然更宽」的笔数按比例缩量，使每笔 SL 的
美元亏损大致定额（削 §0.4 的尾部）。

    rp_ref_pips = 应然 SL 距离（ATR 口径，调用方传入）
    sl_pips_act = 实际下单 SL 距离
    rp_mult     = clamp(rp_ref_pips / sl_pips_act, F_LO, 1.0)   ← 只缩不放大
    units_l2    = max(MIN_LOT, round(size_units × rp_mult))

与 §14 prob overlay 的 size_units 相乘互补：prob 按「市场轴」（方向确信度 /
regime / MC 区间宽度）缩，本模块按「交易轴」（SL 几何）缩。

契约：compute_risk_parity() 纯函数、永不抛异常；log_sizing_shadow() 只落盘、
永不抛异常。默认影子（调用方开关默认 off，不改变下单决策）。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
DEFAULT_F_LO = 0.25  # 与 §14 F_LO 同量级的单笔最大缩量下限


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


def compute_risk_parity(
    size_units: Any,
    sl_pips_act: Any,
    ref_pips: Any,
    min_lot: Any = 1,
    f_lo: Any = DEFAULT_F_LO,
) -> Dict[str, Any]:
    """风险定额后的仓位计划（永不抛异常）。

    返回 ``{"rp_mult", "units_l2", "ref_pips", "sl_pips_act"}``。
    任一输入非法（SL/ref ≤ 0、NaN…）→ ``rp_mult = 1.0`` 的直通计划（不缩）。
    """
    base = _num(min_lot)
    base = 1 if base is None or base < 1 else int(base)
    out: Dict[str, Any] = {
        "rp_mult": 1.0,
        "units_l2": base,
        "ref_pips": None,
        "sl_pips_act": None,
    }
    try:
        units = _num(size_units)
        if units is None or units <= 0:
            return out

        sl = _num(sl_pips_act)
        ref = _num(ref_pips)
        out["ref_pips"] = ref
        out["sl_pips_act"] = sl

        fl = _num(f_lo, DEFAULT_F_LO)
        fl = DEFAULT_F_LO if fl is None else max(0.0, min(1.0, fl))

        # 几何缺失 → 直通（只缩不放大，绝不放风险）。
        if sl is None or sl <= 0 or ref is None or ref <= 0:
            out["units_l2"] = max(base, int(units + 0.5))
            return out

        mult = max(fl, min(1.0, ref / sl))
        out["rp_mult"] = mult
        out["units_l2"] = max(base, int(units * mult + 0.5))
        return out
    except Exception:  # pragma: no cover - 防御：绝不向上传播
        logger.exception("risk_parity: compute failed — passthrough (rp_mult=1.0)")
        return out


def log_sizing_shadow(
    record: Dict[str, Any], logs_dir: Optional[Path] = None
) -> Optional[str]:
    """追加一行影子记录到 ``logs/sizing_shadow_YYYYMMDD.jsonl``（永不抛异常）。"""
    try:
        rec = dict(record) if isinstance(record, dict) else {}
        now = datetime.now(timezone.utc)
        rec.setdefault("ts", now.isoformat(timespec="seconds"))
        directory = Path(logs_dir) if logs_dir is not None else LOGS_DIR
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"sizing_shadow_{now.strftime('%Y%m%d')}.jsonl"
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        return str(path)
    except Exception as exc:  # pragma: no cover - 审计绝不能打断运行
        logger.warning("risk_parity: shadow write skipped (%s)", exc)
        return None
