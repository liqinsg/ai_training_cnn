"""utils/risk_parity_sizing.py — L2 风险定额仓位（影子层 · fx_trade_bot v685）

依据 docs/NEXT_DEV_PLAN_20261117.md §2.1（Owner 2026-11-18 拍板口径）
+ TASK_BRIEF_FINAL_20261118.md TASK-2（MIN_LOT 硬边界修正）。

只做一件事：把「结构 SL 比 ATR 应然更宽」的笔数按比例缩量，使每笔 SL 的
美元亏损大致定额（削 §0.4 的尾部）。

    rp_ref_pips = 应然 SL 距离（ATR 口径，调用方传入）
    sl_pips_act = 实际下单 SL 距离
    rp_mult     = clamp(rp_ref_pips / sl_pips_act, F_LO, 1.0)   ← 只缩不放大
    units_raw   = round(size_units × rp_mult)                   ← 未兜底
    units_l2    = units_raw if units_raw ≥ MIN_LOT else None    ← None = 不下单

⚠️ MIN_LOT 硬边界（TASK-2 修正）：缩量后 units_raw < MIN_LOT 时，
   below_min / would_reject = True，**不抬到 MIN_LOT**（旧口径
   max(MIN_LOT, …) 会突破风险预算）。转正后 would_reject → 拒绝该候选。

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
    pip_value_usd: Any = None,
    jpy_net_units: Any = None,
) -> Dict[str, Any]:
    """风险定额后的仓位计划（永不抛异常）。

    返回 ``{"rp_mult", "units_raw", "units_l2", "below_min", "would_reject",
    "ref_pips", "sl_pips_act", "pip_value_usd", "jpy_net_units"}``。
    任一输入非法（SL/ref ≤ 0、NaN…）→ ``rp_mult = 1.0`` 的直通计划（不缩）。

    ``units_l2 = None`` 表示缩量后低于 MIN_LOT → 不下单（转正后拒绝该候选）。
    """
    base = _num(min_lot)
    base = 1 if base is None or base < 1 else int(base)
    out: Dict[str, Any] = {
        "rp_mult": 1.0,
        "units_prob": None,        # 缩量前（prob overlay 输出）
        "units_raw": None,
        "units_l2": None,          # None = 不下单
        "below_min": False,
        "would_reject": False,
        "ref_pips": None,
        "sl_pips_act": None,
        "pip_value_usd": _num(pip_value_usd),
        "jpy_net_units": _num(jpy_net_units),
    }
    try:
        units = _num(size_units)
        if units is None or units <= 0:
            return out
        out["units_prob"] = units

        sl = _num(sl_pips_act)
        ref = _num(ref_pips)
        out["ref_pips"] = ref
        out["sl_pips_act"] = sl

        fl = _num(f_lo, DEFAULT_F_LO)
        fl = DEFAULT_F_LO if fl is None else max(0.0, min(1.0, fl))

        # 几何缺失 → 直通（只缩不放大，绝不放风险）。
        if sl is None or sl <= 0 or ref is None or ref <= 0:
            mult = 1.0
        else:
            mult = max(fl, min(1.0, ref / sl))
        out["rp_mult"] = mult

        units_raw = int(units * mult + 0.5)
        out["units_raw"] = units_raw
        below = units_raw < base
        out["below_min"] = below
        out["would_reject"] = below
        # MIN_LOT 硬边界：缩量低于 MIN_LOT 不下单，绝不抬到 MIN_LOT。
        out["units_l2"] = None if below else units_raw
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


def apply_if_enabled(result: Dict[str, Any], enabled: bool) -> Dict[str, Any]:
    """转正（``OPT_RISK_PARITY_SIZING`` / ``RISK_PARITY_SIZING`` = on）时调用。

    返回 ``{"size_units", "rejected"}``：
      * enabled=False（影子）→ 原始 units，``rejected=False``（不改下单）；
      * enabled=True → ``would_reject`` 时 ``rejected=True``（跳过该候选，不下单）；
        否则 ``size_units = units_l2``。
    """
    units_raw = result.get("units_prob", result.get("units_raw"))
    if not enabled:
        return {"size_units": units_raw, "rejected": False}
    if result.get("would_reject"):
        return {"size_units": None, "rejected": True}
    return {"size_units": result.get("units_l2"), "rejected": False}


if __name__ == "__main__":
    # 自测：宽 SL → 缩量；窄 SL → 不动；缩量后低于 MIN_LOT → would_reject 且 units_l2=None
    r1 = compute_risk_parity(size_units=10000, sl_pips_act=120.0, ref_pips=50.0, min_lot=1000)
    print(f"宽SL: rp_mult={r1['rp_mult']} raw={r1['units_raw']} l2={r1['units_l2']} reject={r1['would_reject']}")
    assert r1["rp_mult"] < 1.0 and r1["units_l2"] is not None

    r2 = compute_risk_parity(size_units=10000, sl_pips_act=30.0, ref_pips=50.0, min_lot=1000)
    print(f"窄SL: rp_mult={r2['rp_mult']} raw={r2['units_raw']} l2={r2['units_l2']} reject={r2['would_reject']}")
    assert r2["rp_mult"] == 1.0 and r2["units_l2"] == 10000

    r3 = compute_risk_parity(size_units=2000, sl_pips_act=300.0, ref_pips=100.0, min_lot=1000)
    print(f"低于MIN: rp_mult={r3['rp_mult']} raw={r3['units_raw']} l2={r3['units_l2']} reject={r3['would_reject']}")
    assert r3["would_reject"] is True, "MIN_LOT 硬边界失效"
    assert r3["units_l2"] is None, "应返回 None（不下单），而非抬到 MIN_LOT"
    assert apply_if_enabled(r3, True)["rejected"] is True
    assert apply_if_enabled(r3, False)["rejected"] is False
    print("✅ MIN_LOT 硬边界自测通过")
