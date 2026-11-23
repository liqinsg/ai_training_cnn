"""utils/prob_zone_sizing.py — 概率路线仓位/TP 执行覆盖层 (fx_trade_bot v685).

依据 docs/MC_PROB_ANNOTATION_SPEC_v1.0.md §14（消费者侧 · 候选 · 非冻结）。
本模块是**执行覆盖层**，只允许改三件事：

    1. 仓位       size_units   (只缩不放大, 以 MIN_LOT 兜底)
    2. 止盈距离   tp_pips      (目标分位带留余量 → 再受 MIN_TP_PIPS / TP_MAX_MULT 约束)
    3. skip       MC 方向门控命中时

绝不触碰：信号方向 / 打分权重 / SL 距离（compute_sl_zone 保持全权）/ MC 融合。

三条轴（§14.3）
---------------
  方向确信度 (L0)：S = |p_up − p_down| / 100  →  conv(S)                [§14.3.1]
  风险封顶   (L1)：risk_cap(W) = clamp(R_ref / W, C_lo, 1.0)            [§14.3.2]
  合成           ：size_scale = min(conv, risk_cap)   (独立封顶 · 非乘法) [§14.3.3]

本仓库补充的三条 Owner 裁定（超出 §14 原文）
--------------------------------------------
  * 开仓门控    ：对齐概率 < MC_MIN_ALIGNED_PCT → skip（"MC 概率质量控制：开仓与否"）
  * regime 定仓 ：MOMENTUM/OVERBOUGHT/OVERSOLD → ×1.0（标准仓）
                  CONSOLIDATION/RANGE/NEUTRAL  → ×REGIME_MIN_MULT（最低仓）
  * TP 口径     ：目标分位带留余量（BUY→q95 / SELL→q05，按 TP_BAND_MARGIN 回撤留余）

verdict 门控（§14.6 · VERDICT_MODE）
-----------------------------------
  strict ：verdict == NO_EDGE → size_scale 硬锁 F_LO（一刀切）
  soft   ：NO_EDGE / RANGE / NEUTRAL → size_scale × VERDICT_SOFT_MULT（保留单调性）
  off    ：忽略 verdict，不折减

fail-closed（§14.7）
-------------------
「不知道 ≠ 安全」：数据缺失 / 过期 / 退化 / 窄区间 / p_up 非法
→ size_scale **只允许 F_LO**（禁止加仓），且**不进入** conv/risk_cap。

契约纪律
--------
只读（C-1）；数据访问全部经 interface.py；`compute_prob_plan` 永不抛异常，
异常 → floor plan（fail-closed，绝不回退到 1.0）。
"""

import logging
import math
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# 本阶段只支持 Daily 快照；"W" 等一律按"数据不可用"降级，绝不抛异常。
SUPPORTED_TIMEFRAMES = ("D",)
PROB_FACTORS = (1.0, 0.5, 0.25, 0.125)

# 与 config_bot.PROB_ZONE_DEFAULTS 同构（权威副本在 config_bot.py）。
# 仅当调用方传入不完整 / 空的 cfg 时兜底。
_CFG_FALLBACK: Dict[str, Any] = {
    "S0": 0.10,
    "S1": 0.40,
    "F_LO": 0.25,
    "R_REF": 2.0,
    "C_LO": 0.25,
    "MIN_LOT_LIVE": 1,
    "MIN_LOT_DEMO": 1000,
    "MIN_TP_PIPS": 10,
    "REQUIRE_ALIGNED": True,
    "MC_MIN_ALIGNED_PCT": 50.0,
    "REGIME_MIN_MULT": 0.25,
    # W 侧无边（RANGE/NEUTRAL/…）保守倍率：融合时 W 提示谨慎 → 至少降 20%
    "REGIME_W_CALM_MULT": 0.8,
    "TP_BAND_MARGIN": 0.20,
    "TP_MAX_MULT": 2.0,
    "VERDICT_MODE": "soft",
    "VERDICT_SOFT_MULT": 0.5,
    "FAILCLOSED_SKIP": False,
}


# ─────────────────────────────────────────────────────────────────────────────
# 数据访问（每次运行只读一次文件，经 interface.py）
# ─────────────────────────────────────────────────────────────────────────────
def load_prob_index(day: str, timeframe: str = "D") -> Dict[str, Any]:
    """加载一次 MC 快照并返回 ``results`` 索引。

    不支持的 timeframe / 缺文件 / IO 或解析失败 → ``{}``（永不抛异常）。
    """
    if timeframe not in SUPPORTED_TIMEFRAMES:
        logger.warning(
            "Prob Zone: timeframe %r unsupported (only %s) — prob unavailable",
            timeframe,
            "/".join(SUPPORTED_TIMEFRAMES),
        )
        return {}
    try:
        import interface as mc_iface
    except Exception as exc:  # pragma: no cover - environment specific
        logger.warning("Prob Zone: interface.py unavailable (%s) — prob unavailable", exc)
        return {}
    try:
        bundle = mc_iface.get_latest_fib_mc_data(day, timeframe)
    except Exception as exc:
        logger.warning(
            "Prob Zone: get_latest_fib_mc_data(%s, %s) failed (%s) — prob unavailable",
            day,
            timeframe,
            exc,
        )
        return {}
    results = (bundle or {}).get("results") if isinstance(bundle, dict) else None
    if not isinstance(results, dict):
        return {}
    return results


def _advisory(rec: Any) -> Optional[Dict[str, Any]]:
    """经 interface.get_pair_advisory() 取标注状态；interface 不可用 → None（fail-closed）。"""
    try:
        import interface as mc_iface
    except Exception as exc:  # pragma: no cover - environment specific
        logger.warning("Prob Zone: interface.py unavailable (%s) — fail-closed", exc)
        return None
    try:
        return mc_iface.get_pair_advisory(rec)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Prob Zone: get_pair_advisory failed (%s) — fail-closed", exc)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 小而全（永不抛异常）的取值助手
# ─────────────────────────────────────────────────────────────────────────────
def _cfg_get(cfg: Dict[str, Any], key: str, default: Any) -> Any:
    try:
        value = cfg.get(key, default)
    except Exception:
        return default
    return default if value is None else value


def _as_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return number


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("1", "true", "yes", "on"):
            return True
        if text in ("0", "false", "no", "off", ""):
            return False
    return default


def _as_int(value: Any, default: int) -> int:
    number = _as_float(value)
    return default if number is None else int(number)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _normalize_direction(direction: Any) -> Optional[str]:
    try:
        text = str(direction).strip().upper()
    except Exception:  # pragma: no cover
        return None
    return text if text in ("BUY", "SELL") else None


def to_mc_key(pair: str) -> str:
    """Map an OANDA pair (``EUR_USD``) to its MC snapshot key (``EURUSD=X``)."""
    if pair is None:
        return ""
    try:
        key = str(pair).strip().upper()
    except Exception:  # pragma: no cover - str() of a broken __str__
        return ""
    if not key:
        return ""
    if key.endswith("=X"):
        return key
    return key.replace("_", "").replace("/", "").replace("-", "") + "=X"


def _prob_rungs(base_lot: Any, min_units: Any) -> list[int]:
    lot = _as_float(base_lot)
    if lot is None or lot <= 0:
        return []
    floor = max(1, _as_int(min_units, 1))
    return sorted(
        {
            int(lot * factor + 0.5)
            for factor in PROB_FACTORS
            if int(lot * factor + 0.5) >= floor
        },
        reverse=True,
    )


def normalize_to_prob_factor(
    size_units: Any, base_lot: Any, min_units: Any = 1
) -> int:
    """Snap a size down to the configured minimum and probability factor rungs."""
    units = _as_int(size_units, 0)
    floor = max(1, _as_int(min_units, 1))
    rungs = _prob_rungs(base_lot, floor)
    if not rungs:
        return max(floor, units)
    for rung in rungs:
        if units >= rung:
            return rung
    return rungs[-1]


def next_prob_rung_up(
    current_units: Any, base_lot: Any, min_units: Any = 1
) -> tuple[int, int]:
    """Return the next larger probability rung and the units needed to reach it."""
    current = _as_int(current_units, 0)
    if current <= 0:
        return 0, 0
    for rung in reversed(_prob_rungs(base_lot, min_units)):
        if rung > current:
            return rung, rung - current
    return 0, 0


def min_prob_factor_units(base_lot: Any) -> int:
    """Return the rounded unit threshold for the minimum (0.125) factor."""
    lot = _as_float(base_lot)
    return 0 if lot is None or lot <= 0 else int(lot * PROB_FACTORS[-1] + 0.5)


def below_min_prob_factor(size_units: Any, base_lot: Any) -> bool:
    """Whether a positive size is below the minimum probability-factor rung."""
    units = _as_int(size_units, 0)
    threshold = min_prob_factor_units(base_lot)
    return units > 0 and threshold > 0 and units < threshold


def prob_tier_for_units(size_units: Any, base_lot: Any) -> int:
    """Map units to the nearest named tier, numbering Minimum=1 through Full=4."""
    units = _as_float(size_units)
    lot = _as_float(base_lot)
    if units is None or lot is None or lot <= 0:
        return 1
    if units <= min_prob_factor_units(lot):
        return 1
    factor = units / lot
    if factor >= 0.75:
        return 4
    if factor >= 0.375:
        return 3
    if factor >= 0.1875:
        return 2
    return 1


# ─────────────────────────────────────────────────────────────────────────────
# §14.3 三个数学件
# ─────────────────────────────────────────────────────────────────────────────
def _conv(s_value: float, s0: float, s1: float, f_lo: float) -> float:
    """方向确信度映射（死区 + 线性斜坡），值域 [F_LO, 1.0]，只缩不放大。"""
    f_lo = _clamp(f_lo, 0.0, 1.0)
    s0 = _clamp(s0, 0.0, 1.0)
    s1 = max(s0, _clamp(s1, 0.0, 1.0))
    if s_value <= s0:
        return f_lo
    if s_value >= s1:
        return 1.0
    ramp = (s_value - s0) / (s1 - s0)
    return _clamp(f_lo + (1.0 - f_lo) * ramp, f_lo, 1.0)


def _risk_cap(w_pct: float, r_ref: float, c_lo: float) -> float:
    """风险封顶（倒数封顶），值域 [C_LO, 1.0]，W ≤ R_REF 时不约束。"""
    c_lo = _clamp(c_lo, 0.0, 1.0)
    if w_pct <= 0:
        return 1.0
    if r_ref <= 0:
        return 1.0
    return _clamp(r_ref / w_pct, c_lo, 1.0)


def _regime_mult_side(text: Any, strong_mult: float, calm_mult: float) -> float:
    """单侧 regime 文本 → 仓位倍率（只降不升）。

    MOMENTUM / OVERBOUGHT / OVERSOLD（有边）→ strong_mult（标准/基础仓）；
    CONSOLIDATION / RANGE / NEUTRAL（无边）→ calm_mult（保守仓）；
    未识别 / 缺失 → 1.0（不因未知而降级，方向由 MC 门控负责）。
    """
    t = text.upper() if isinstance(text, str) else ""
    if "MOMENTUM" in t or "OVERBOUGHT" in t or "OVERSOLD" in t:
        return strong_mult
    if "CONSOLIDATION" in t or "RANGE" in t or "NEUTRAL" in t:
        return calm_mult
    return 1.0


def is_strong_momentum_regime(regime: Any) -> bool:
    """Recognize the canonical and display forms emitted by the MC reports."""
    if not isinstance(regime, str):
        return False
    text = " ".join(
        regime.strip().upper().replace("-", " ").replace("_", " ").split()
    )
    return text == "MOMENTUM" or text.endswith("STRONG MOMENTUM")


def apply_strong_momentum_bonus(
    base_units: Any,
    *,
    enabled: bool,
    min_units: Any,
    max_units: Any,
) -> int:
    """Double a positive position for strong momentum within the sizing bounds."""
    units = _as_int(base_units, 0)
    if not enabled or units <= 0:
        return units

    minimum = max(1, _as_int(min_units, 1))
    maximum = max(minimum, _as_int(max_units, minimum))
    return min(max(units * 2, minimum), maximum)


def _regime_mult(
    regime_d: Any, regime_w: Any, d_min_mult: float, w_calm_mult: float
) -> float:
    """W+D 两侧 regime 独立判读 → 取保守值 ``min()``（只降不升）。

    只读原始标签 ``regime_D`` / ``regime_W``，不读复合串 ``regime_fused``
    （后者含 "MOMENTUM"/"NEUTRAL" 等多词，子串判断会互相"或"掉风险提示）。
    任一侧提示无边（RANGE/NEUTRAL/…）→ 整体降仓：D 侧用 d_min_mult，
    W 侧用 w_calm_mult（W 中/区间略保守）

    非融合记录两侧同源（regime_D == regime_W == 原始串）→ 结果与修复前一致。
    """
    d_mult = _regime_mult_side(regime_d, 1.0, _clamp(d_min_mult, 0.0, 1.0))
    w_mult = _regime_mult_side(regime_w, 1.0, _clamp(w_calm_mult, 0.0, 1.0))
    return min(d_mult, w_mult)


def _verdict_mult(verdict: Any, soft_mult: float) -> float:
    """无方向 verdict 文本 → 仓位折减倍率（只降不升，软惩罚）。

    MOMENTUM / OVERBOUGHT / OVERSOLD（有边）→ 1.0；
    NO_EDGE / RANGE / NEUTRAL（无信号）→ soft_mult；
    未识别 / 缺失 → 1.0（不因未知而降级，方向由开仓门控负责）。
    """
    text = verdict if isinstance(verdict, str) else ""
    text = text.upper()
    if "MOMENTUM" in text or "OVERBOUGHT" in text or "OVERSOLD" in text:
        return 1.0
    if "NO_EDGE" in text or "RANGE" in text or "NEUTRAL" in text:
        return _clamp(soft_mult, 0.0, 1.0)
    return 1.0


def _band_edge(rec: Dict[str, Any], direction: str) -> Optional[float]:
    """目标分位带边缘：BUY → q95，SELL → q05。

    优先取 ``distribution.quantiles``（L1 分位），缺失时回退 ``range_90``。
    """
    q_lo = q_hi = None
    distribution = rec.get("distribution") if isinstance(rec, dict) else None
    if isinstance(distribution, dict):
        quantiles = distribution.get("quantiles")
        if isinstance(quantiles, dict):
            q_lo = _as_float(quantiles.get("0.05"))
            q_hi = _as_float(quantiles.get("0.95"))
    if q_lo is None or q_hi is None:
        rng = rec.get("range_90") if isinstance(rec, dict) else None
        if isinstance(rng, (list, tuple)) and len(rng) == 2:
            q_lo = _as_float(rng[0])
            q_hi = _as_float(rng[1])
    if q_lo is None or q_hi is None:
        return None
    return q_hi if direction == "BUY" else q_lo


def _width_pct(rec: Dict[str, Any]) -> Optional[float]:
    """L1 区间宽度 W = (q95 − q05) / current_price × 100（%，§4.3.2）。"""
    if not isinstance(rec, dict):
        return None
    rng = rec.get("range_90")
    if not isinstance(rng, (list, tuple)) or len(rng) != 2:
        return None
    lower = _as_float(rng[0])
    upper = _as_float(rng[1])
    price = _as_float(rec.get("current_price"))
    if lower is None or upper is None or price is None or price <= 0:
        return None
    return (upper - lower) / price * 100.0


def _p_up_down(rec: Dict[str, Any]) -> "tuple":
    """返回 (p_up, p_down)；非法 / 不自洽 → (None, None)（fail-closed）。"""
    if not isinstance(rec, dict):
        return None, None
    p_up = _as_float(rec.get("p_up"))
    if p_up is None or p_up < 0.0 or p_up > 100.0:
        return None, None
    p_down = _as_float(rec.get("p_down"))
    if p_down is None:
        p_down = 100.0 - p_up
    if p_down < 0.0 or p_down > 100.0:
        return None, None
    if abs((p_up + p_down) - 100.0) > 0.5:  # 不自洽
        return None, None
    return p_up, p_down


# ─────────────────────────────────────────────────────────────────────────────
# 返回契约
# ─────────────────────────────────────────────────────────────────────────────
def _size_units(base_lot: Any, size_scale: float, min_lot: int) -> int:
    """int(base_lot · scale + 0.5)（禁用 banker's rounding）后以 MIN_LOT 兜底。"""
    lot = _as_float(base_lot)
    if lot is None or lot <= 0:
        lot = 1.0
    units = int(lot * float(size_scale) + 0.5)
    return max(int(min_lot), units)


def _base_plan(
    base_lot: Any,
    base_tp_pips: Any,
    cfg: Dict[str, Any],
    reason: str,
    *,
    size_scale: float,
    skip: bool = False,
    advisory: Optional[Dict[str, Any]] = None,
    p_up: Optional[float] = None,
    p_down: Optional[float] = None,
    aligned: Optional[float] = None,
    s_value: Optional[float] = None,
    conv: Optional[float] = None,
    width_pct: Optional[float] = None,
    risk_cap: Optional[float] = None,
    regime_mult: Optional[float] = None,
    tp_pips: Optional[float] = None,
    tp_scale: float = 1.0,
) -> Dict[str, Any]:
    """完整契约字典（永远包含全部键）。"""
    f_lo = _as_float(_cfg_get(cfg, "F_LO", _CFG_FALLBACK["F_LO"]))
    f_lo = 0.25 if f_lo is None else _clamp(f_lo, 0.0, 1.0)
    min_lot = _as_int(_cfg_get(cfg, "MIN_LOT", 1), 1)
    if min_lot < 1:
        min_lot = 1
    base_tp = _as_float(base_tp_pips)
    base_tp = 0.0 if base_tp is None else base_tp
    advisory = advisory if isinstance(advisory, dict) else {}
    return {
        "skip": bool(skip),
        "reason": reason,
        "advisory_state": advisory.get("state", "unknown"),
        "verdict": advisory.get("verdict", "NO_EDGE"),
        "p_up": p_up,
        "p_down": p_down,
        "aligned": aligned,
        "S": s_value,
        "conv": conv,
        "W": width_pct,
        "risk_cap": risk_cap,
        "regime_mult": regime_mult,
        "f_lo": f_lo,
        "size_scale": float(size_scale),
        "size_units": _size_units(base_lot, size_scale, min_lot),
        "tp_scale": float(tp_scale),
        "tp_pips": float(base_tp if tp_pips is None else tp_pips),
    }


def _floor_plan(
    base_lot: Any,
    base_tp_pips: Any,
    cfg: Dict[str, Any],
    reason: str,
    *,
    skip: bool = False,
    advisory: Optional[Dict[str, Any]] = None,
    p_up: Optional[float] = None,
    p_down: Optional[float] = None,
    aligned: Optional[float] = None,
) -> Dict[str, Any]:
    """fail-closed 计划：size_scale 只取 F_LO，禁止加仓；TP 不缩放。"""
    f_lo = _as_float(_cfg_get(cfg, "F_LO", _CFG_FALLBACK["F_LO"]))
    f_lo = 0.25 if f_lo is None else _clamp(f_lo, 0.0, 1.0)
    return _base_plan(
        base_lot,
        base_tp_pips,
        cfg,
        reason,
        size_scale=f_lo,
        skip=skip,
        advisory=advisory,
        p_up=p_up,
        p_down=p_down,
        aligned=aligned,
    )


def _tp_pips(
    rec: Dict[str, Any],
    direction: str,
    current_price: Any,
    pip_value: Any,
    base_tp: float,
    cfg: Dict[str, Any],
) -> "tuple":
    """目标分位带留余量 → tp_pips（受 MIN_TP_PIPS 与 TP_MAX_MULT 约束）。"""
    if base_tp <= 0.0:
        return base_tp, 1.0
    min_tp = _as_float(_cfg_get(cfg, "MIN_TP_PIPS", _CFG_FALLBACK["MIN_TP_PIPS"]))
    min_tp = 10.0 if min_tp is None else max(0.0, min_tp)
    max_mult = _as_float(_cfg_get(cfg, "TP_MAX_MULT", _CFG_FALLBACK["TP_MAX_MULT"]))
    max_mult = 1.0 if max_mult is None else max(0.0, max_mult)
    margin = _as_float(_cfg_get(cfg, "TP_BAND_MARGIN", _CFG_FALLBACK["TP_BAND_MARGIN"]))
    margin = 0.20 if margin is None else _clamp(margin, 0.0, 0.95)

    edge = _band_edge(rec, direction)
    price = _as_float(current_price)
    pip = _as_float(pip_value)
    if edge is None or price is None or pip is None or pip <= 0.0:
        return base_tp, 1.0

    dist_price = (edge - price) if direction == "BUY" else (price - edge)
    if dist_price <= 0.0:
        # 现价已在/越过目标带边缘 → 无法给出更远的带内目标，保留基准 TP。
        return base_tp, 1.0

    band_pips = dist_price * (1.0 - margin) / pip
    tp_cap = base_tp * max_mult
    tp_pips = min(tp_cap, max(min_tp, band_pips))
    return round(tp_pips, 1), (tp_pips / base_tp if base_tp > 0 else 1.0)


# ─────────────────────────────────────────────────────────────────────────────
# 唯一对外的覆盖层入口
# ─────────────────────────────────────────────────────────────────────────────
def compute_prob_plan(
    rec: Any,
    direction: str,
    cfg: Optional[Dict[str, Any]],
    base_lot: int,
    base_tp_pips: float,
    current_price: Any = None,
    pip_value: Any = None,
    regime: Any = None,
) -> Dict[str, Any]:
    """单个 pair 的概率路线计划（永不抛异常，永远返回完整契约）。

    ``direction`` 必须是 BUY / SELL（BUY=LONG, SELL=SHORT），其余降级为 floor plan。
    """
    cfg_dict: Dict[str, Any] = cfg if isinstance(cfg, dict) else {}
    try:
        record: Dict[str, Any] = rec if isinstance(rec, dict) else {}

        normalized = _normalize_direction(direction)
        if normalized is None:
            logger.error(
                "Prob Zone: direction %r rejected — only BUY/SELL allowed", direction
            )
            return _floor_plan(base_lot, base_tp_pips, cfg_dict, "prob_invalid_direction")

        # ── 1) 标注健康闸门（§14.7 + §14.6）───────────────────────────────────
        advisory = _advisory(record)
        state = advisory.get("state") if isinstance(advisory, dict) else None
        if state != "healthy":
            logger.warning(
                "Prob Zone: advisory state=%s (verdict=%s) → fail-closed (F_LO)",
                state or "unavailable",
                (advisory or {}).get("verdict", "?"),
            )
            return _floor_plan(
                base_lot,
                base_tp_pips,
                cfg_dict,
                f"advisory_{state or 'unavailable'}",
                skip=_as_bool(_cfg_get(cfg_dict, "FAILCLOSED_SKIP", False), False),
                advisory=advisory if isinstance(advisory, dict) else None,
            )

        # ── 2) L0 方向概率（唯一真理源）─────────────────────────────────────
        p_up, p_down = _p_up_down(record)
        if p_up is None:
            logger.warning("Prob Zone: p_up/p_down missing or inconsistent → fail-closed")
            return _floor_plan(
                base_lot,
                base_tp_pips,
                cfg_dict,
                "p_up_invalid",
                skip=_as_bool(_cfg_get(cfg_dict, "FAILCLOSED_SKIP", False), False),
                advisory=advisory,
            )

        aligned = p_up if normalized == "BUY" else p_down

        # ── 3) 开仓门控：MC 概率质量控制（对齐概率不足 → 不开仓）─────────────
        min_aligned = _as_float(
            _cfg_get(cfg_dict, "MC_MIN_ALIGNED_PCT", _CFG_FALLBACK["MC_MIN_ALIGNED_PCT"])
        )
        min_aligned = 50.0 if min_aligned is None else _clamp(min_aligned, 0.0, 100.0)
        if _as_bool(
            _cfg_get(cfg_dict, "REQUIRE_ALIGNED", _CFG_FALLBACK["REQUIRE_ALIGNED"]), True
        ) and aligned < min_aligned:
            logger.warning(
                "Prob Zone: MC direction conflict — %s aligned=%.1f%% < %.1f%% → SKIP",
                normalized,
                aligned,
                min_aligned,
            )
            return _floor_plan(
                base_lot,
                base_tp_pips,
                cfg_dict,
                "mc_direction_conflict",
                skip=True,
                advisory=advisory,
                p_up=p_up,
                p_down=p_down,
                aligned=aligned,
            )

        # ── 4) §14.3 计算 ────────────────────────────────────────────────────
        s_value = abs(p_up - p_down) / 100.0
        conv = _conv(
            s_value,
            _as_float(_cfg_get(cfg_dict, "S0", _CFG_FALLBACK["S0"]), 0.10),
            _as_float(_cfg_get(cfg_dict, "S1", _CFG_FALLBACK["S1"]), 0.40),
            _as_float(_cfg_get(cfg_dict, "F_LO", _CFG_FALLBACK["F_LO"]), 0.25),
        )
        width_pct = _width_pct(record)
        risk_cap = (
            _risk_cap(
                width_pct,
                _as_float(_cfg_get(cfg_dict, "R_REF", _CFG_FALLBACK["R_REF"]), 2.0),
                _as_float(_cfg_get(cfg_dict, "C_LO", _CFG_FALLBACK["C_LO"]), 0.25),
            )
            if width_pct is not None
            else 1.0
        )

        # 融合记录：分别读两侧原始标签 regime_D / regime_W（不回退到复合串）；
        # 非融合记录两者缺省 → 同源为单一文本，行为与修复前一致。
        regime_text = regime if regime else record.get("regime")
        regime_d = record.get("regime_D") or regime_text
        regime_w = record.get("regime_W") or regime_text
        regime_mult = _regime_mult(
            regime_d,
            regime_w,
            _as_float(
                _cfg_get(cfg_dict, "REGIME_MIN_MULT", _CFG_FALLBACK["REGIME_MIN_MULT"]),
                0.25,
            ),
            _as_float(
                _cfg_get(
                    cfg_dict,
                    "REGIME_W_CALM_MULT",
                    _CFG_FALLBACK["REGIME_W_CALM_MULT"],
                ),
                0.8,
            ),
        )

        f_lo = _as_float(_cfg_get(cfg_dict, "F_LO", _CFG_FALLBACK["F_LO"]), 0.25)
        size_scale = _clamp(min(conv, risk_cap, regime_mult), f_lo, 1.0)
        reason = "ok"

        # ── 5) §14.6 verdict 门控（VERDICT_MODE：strict / soft / off）────────
        verdict = advisory.get("verdict") if isinstance(advisory, dict) else None
        verdict_mode = str(
            _cfg_get(cfg_dict, "VERDICT_MODE", _CFG_FALLBACK["VERDICT_MODE"]) or "soft"
        ).strip().lower()
        if verdict_mode == "strict":
            if verdict == "NO_EDGE":
                size_scale = min(size_scale, f_lo)
                reason = "verdict_no_edge"
        elif verdict_mode == "soft":
            soft_mult = _as_float(
                _cfg_get(cfg_dict, "VERDICT_SOFT_MULT", _CFG_FALLBACK["VERDICT_SOFT_MULT"])
            )
            soft_mult = 0.5 if soft_mult is None else _clamp(soft_mult, 0.0, 1.0)
            penalty = _verdict_mult(verdict, soft_mult)
            if penalty < 1.0:
                size_scale = _clamp(size_scale * penalty, f_lo, 1.0)
                reason = "verdict_soft_penalty"

        tp_pips, tp_scale = _tp_pips(
            record,
            normalized,
            current_price,
            pip_value,
            _as_float(base_tp_pips) or 0.0,
            cfg_dict,
        )

        return _base_plan(
            base_lot,
            base_tp_pips,
            cfg_dict,
            reason,
            size_scale=size_scale,
            advisory=advisory,
            p_up=p_up,
            p_down=p_down,
            aligned=aligned,
            s_value=s_value,
            conv=conv,
            width_pct=width_pct,
            risk_cap=risk_cap,
            regime_mult=regime_mult,
            tp_pips=tp_pips,
            tp_scale=tp_scale,
        )
    except Exception:  # pragma: no cover - 防御：绝不向上传播
        logger.exception("Prob Zone: compute_prob_plan failed — fail-closed floor plan")
        return _floor_plan(base_lot, base_tp_pips, cfg_dict, "prob_error")


# ─────────────────────────────────────────────────────────────────────────────
# 审计日志（每笔候选一行，开仓与 skip 都记录）
# ─────────────────────────────────────────────────────────────────────────────
def format_prob_audit(pair: str, direction: str, plan: Optional[Dict[str, Any]]) -> str:
    """渲染强制审计字段为单行 ``key=value | ...``（永不抛异常）。"""
    try:
        safe: Dict[str, Any] = plan if isinstance(plan, dict) else {}

        def _num(value: Any, digits: int = 2) -> str:
            number = _as_float(value)
            return "None" if number is None else f"{number:.{digits}f}"

        parts = [
            f"pair={pair}",
            f"dir={direction}",
            f"reason={safe.get('reason', '?')}",
            f"state={safe.get('advisory_state', '?')}",
            f"verdict={safe.get('verdict', '?')}",
            f"P_UP={_num(safe.get('p_up'), 1)}",
            f"aligned={_num(safe.get('aligned'), 1)}",
            f"S={_num(safe.get('S'), 3)}",
            f"conv={_num(safe.get('conv'))}",
            f"W%={_num(safe.get('W'), 2)}",
            f"risk_cap={_num(safe.get('risk_cap'))}",
            f"regime_mult={_num(safe.get('regime_mult'))}",
            f"size_scale={_num(safe.get('size_scale'))}",
            f"units={safe.get('size_units')}",
            f"tp_scale={_num(safe.get('tp_scale'))}",
            f"tp={_num(safe.get('tp_pips'), 1)}",
        ]
        return " | ".join(parts)
    except Exception:  # pragma: no cover - 审计绝不能打断运行
        return f"pair={pair} | dir={direction} | reason=audit_error"
