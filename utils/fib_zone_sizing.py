"""utils/fib_zone_sizing.py — Fib Zone execution overlay for fx_trade_bot v685.

The Fib Zone is an EXECUTION overlay only. It is allowed to touch exactly three
things:

    1. position size         -> size_units
    2. take-profit distance  -> tp_pips  (shrink-only, never amplifies)
    3. skip                  -> only for degenerate / breakout records

It never touches (and must never be wired into):
    * signal generation / direction / scoring weights
    * SL distance (compute_sl_zone() keeps full authority)
    * MC fusion (load_mc_bundle / mc_bundle_loader)

Data access
-----------
The snapshot is loaded ONCE per run through ``interface.py``
(``load_fib_index``). ``compute_zone_plan`` is a pure function over a single
pair record — it performs no file IO, so N pairs cost exactly one file read.

Live schema (MC snapshot ``schema_version`` 1.1.0)::

    pair_record["fib"] = {
        "zone_index": 3,
        "current_zone": {"ratio": [0.5, 0.618], "position_in_zone_pct": 52.3},
        ...
    }

``ratio_pos`` / ``degenerate`` / ``breakout`` do NOT exist in the live schema
yet; they are derived (ratio_pos) or hard-wired to False (degenerate/breakout)
and the keys are kept in the return contract for forward compatibility.

Fail-safe
---------
``compute_zone_plan`` never raises and always returns the full contract dict.
Missing / invalid Fib data degrades to the v685 behaviour: full default size,
original TP, no skip.
"""

import logging
import math
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Only the Daily snapshot is supported this phase. "W" (and anything else) is
# treated as "fib unavailable" -> graceful fallback, never an exception.
SUPPORTED_TIMEFRAMES = ("D",)

# Mirror of config_bot.FIB_ZONE_DEFAULTS (authoritative copy lives there).
# Used only when a caller passes an incomplete / empty cfg dict.
_CFG_FALLBACK: Dict[str, Any] = {
    "ENABLED": True,
    "MODE": "filter",
    "CENTER_EDGE": 2,
    "SIZE_LADDER": [1.0, 0.5, 0.25, 0.125],
    "MIN_LOT": 1000,
    "TP_ROOM_REF": 0.5,
    "TP_SCALE_MIN": 0.5,
    "TP_SCALE_MAX": 1.0,
    "MIN_TP_PIPS": 10,
    "SKIP_WHEN_DEGENERATE": True,
    "SKIP_BREAKOUT": False,
}

ZONE_MIN = 0
ZONE_MAX = 5
# Float noise tolerance for the ratio_pos range check (e.g. 0.786 + 0.214).
_EPS = 1e-9
# Allowed slack on position_in_zone_pct before it is considered invalid.
_PCT_SLACK = 1e-6


# ─────────────────────────────────────────────────────────────────────────────
# Pair key mapping — the ONE place that translates OANDA pair → snapshot key
# ─────────────────────────────────────────────────────────────────────────────
def to_mc_key(pair: str) -> str:
    """Map a bot pair (``EUR_USD``) to the MC/Fib snapshot key (``EURUSD=X``).

    Always use this helper; do not ``replace()/upper()/split()`` ad hoc
    elsewhere in the pipeline.
    """
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


# ─────────────────────────────────────────────────────────────────────────────
# Data access (single file read per run, via interface.py only)
# ─────────────────────────────────────────────────────────────────────────────
def load_fib_index(day: str, timeframe: str = "D") -> Dict[str, Any]:
    """Load the MC+Fib bundle ONCE and return its ``results`` index.

    Returns ``{}`` (fib unavailable) for unsupported timeframes, missing
    bundles, or any IO/parse error — never raises.
    """
    if timeframe not in SUPPORTED_TIMEFRAMES:
        logger.warning(
            "Fib Zone: timeframe %r unsupported (only %s) — fib unavailable, "
            "falling back to v685 sizing/TP",
            timeframe,
            "/".join(SUPPORTED_TIMEFRAMES),
        )
        return {}
    try:
        import interface as mc_iface
    except Exception as exc:  # pragma: no cover - environment specific
        logger.warning("Fib Zone: interface.py unavailable (%s) — fib unavailable", exc)
        return {}
    try:
        bundle = mc_iface.get_latest_fib_mc_data(day, timeframe)
    except Exception as exc:
        logger.warning(
            "Fib Zone: get_latest_fib_mc_data(%s, %s) failed (%s) — fib unavailable",
            day,
            timeframe,
            exc,
        )
        return {}
    results = (bundle or {}).get("results") if isinstance(bundle, dict) else None
    if not isinstance(results, dict):
        return {}
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Small, total (never-raising) coercion helpers
# ─────────────────────────────────────────────────────────────────────────────
def _cfg_get(cfg: Dict[str, Any], key: str, default: Any) -> Any:
    try:
        value = cfg.get(key, default)
    except Exception:
        return default
    return default if value is None else value


def _as_finite_float(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
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


def _as_zone_index(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        zone = int(value)
    elif isinstance(value, float) and float(value).is_integer():
        zone = int(value)
    else:
        return None
    if zone < ZONE_MIN or zone > ZONE_MAX:
        return None
    return zone


def _as_int(value: Any, default: int) -> int:
    number = _as_finite_float(value)
    if number is None:
        return default
    return int(number)


def _normalize_direction(direction: Any) -> Optional[str]:
    """Only BUY / SELL are accepted (BUY=LONG, SELL=SHORT). None otherwise."""
    try:
        text = str(direction).strip().upper()
    except Exception:  # pragma: no cover
        return None
    return text if text in ("BUY", "SELL") else None


def _size_ladder(cfg: Dict[str, Any]) -> list:
    """Sanitised size ladder: finite floats clamped to [0.0, 1.0] (never >1)."""
    raw = _cfg_get(cfg, "SIZE_LADDER", _CFG_FALLBACK["SIZE_LADDER"])
    ladder = []
    if isinstance(raw, (list, tuple)):
        for item in raw:
            number = _as_finite_float(item)
            if number is not None:
                ladder.append(min(1.0, max(0.0, number)))
    return ladder or [1.0]


def _size_units(base_lot: Any, size_scale: float) -> int:
    """int(base_lot * scale + 0.5) — never round(): banker's rounding is banned."""
    lot = _as_finite_float(base_lot)
    if lot is None or lot <= 0:
        lot = 1.0
    return max(1, int(lot * float(size_scale) + 0.5))


def _base_tp(base_tp_pips: Any) -> float:
    tp = _as_finite_float(base_tp_pips)
    return 0.0 if tp is None else tp


# ─────────────────────────────────────────────────────────────────────────────
# Return contract
# ─────────────────────────────────────────────────────────────────────────────
def _neutral_plan(
    base_lot: Any,
    base_tp_pips: Any,
    reason: str = "ok",
    skip: bool = False,
    zone_index: Optional[int] = None,
    ratio_pos: Optional[float] = None,
    room: Optional[float] = None,
    late_distance: int = 0,
    size_scale: float = 1.0,
    tp_scale: float = 1.0,
    degenerate: bool = False,
    breakout: bool = False,
) -> Dict[str, Any]:
    """Full contract dict with v685 behaviour (no size/TP change, no skip)."""
    base_tp = _base_tp(base_tp_pips)
    return {
        "skip": bool(skip),
        "reason": reason,
        "zone_index": zone_index,
        "ratio_pos": ratio_pos,
        "room": room,
        "late_distance": int(late_distance),
        "size_scale": float(size_scale),
        "size_units": _size_units(base_lot, size_scale),
        "tp_scale": float(tp_scale),
        "tp_pips": base_tp,
        # Reserved for a future schema — always False on schema 1.1.0.
        "degenerate": bool(degenerate),
        "breakout": bool(breakout),
    }


def _extract_fib(rec: Any) -> "tuple":
    """Return ``(fib_block, None)`` or ``(None, reason)``.

    Accepts either the full pair record (``{"fib": {...}, ...}``) or the fib
    block itself, so both calling conventions map onto the same logic.
    """
    if not isinstance(rec, dict) or not rec:
        return None, "fib_missing"
    fib = rec["fib"] if "fib" in rec else rec
    if not isinstance(fib, dict) or not fib:
        return None, "fib_missing"
    return fib, None


def _validate_fib(fib: Dict[str, Any]) -> "tuple":
    """Map the live schema onto (zone_index, ratio_pos) or return a reason.

    Live source fields: ``fib.zone_index`` and
    ``fib.current_zone.{ratio[0], ratio[1], position_in_zone_pct}``.
    """
    zone_index = _as_zone_index(fib.get("zone_index"))
    if zone_index is None:
        return None, None, "zone_index missing / out of range"

    current_zone = fib.get("current_zone")
    if not isinstance(current_zone, dict) or not current_zone:
        return None, None, "current_zone missing"

    ratio = current_zone.get("ratio")
    if not isinstance(ratio, (list, tuple)) or len(ratio) < 2:
        return None, None, "current_zone.ratio missing"
    ratio_lo = _as_finite_float(ratio[0])
    ratio_hi = _as_finite_float(ratio[1])
    if ratio_lo is None or ratio_hi is None:
        return None, None, "current_zone.ratio not finite"

    pct_in_zone = _as_finite_float(current_zone.get("position_in_zone_pct"))
    if pct_in_zone is None:
        return None, None, "position_in_zone_pct missing / not finite"

    if ratio_lo < 0.0 or ratio_hi > 1.0 or ratio_lo > ratio_hi:
        return None, None, f"ratio bounds invalid ({ratio_lo}, {ratio_hi})"
    if pct_in_zone < -_PCT_SLACK or pct_in_zone > 100.0 + _PCT_SLACK:
        return None, None, f"position_in_zone_pct out of range ({pct_in_zone})"

    # ratio_pos = ratio_lo + pct/100 * (ratio_hi - ratio_lo), written in the
    # lerp form so the 0 % / 100 % ends land exactly on ratio_lo / ratio_hi
    # (the naive form yields 1.0000000000000002 for [0.786, 1.0] @ 100 %).
    weight = pct_in_zone / 100.0
    ratio_pos = ratio_lo * (1.0 - weight) + ratio_hi * weight
    if not math.isfinite(ratio_pos):
        return None, None, "ratio_pos not finite"
    if ratio_pos < -_EPS or ratio_pos > 1.0 + _EPS:
        return None, None, f"ratio_pos out of [0, 1] ({ratio_pos})"
    return zone_index, min(1.0, max(0.0, ratio_pos)), None


# ─────────────────────────────────────────────────────────────────────────────
# Public API — the only overlay entry point used by the bot
# ─────────────────────────────────────────────────────────────────────────────
def compute_zone_plan(
    rec: Any,
    direction: str,
    cfg: Optional[Dict[str, Any]],
    base_lot: int,
    base_tp_pips: float,
) -> Dict[str, Any]:
    """Direction-aware Fib Zone plan for ONE pair.

    Never raises and always returns the complete contract dict
    (``skip``/``reason``/``zone_index``/``ratio_pos``/``room``/
    ``late_distance``/``size_scale``/``size_units``/``tp_scale``/``tp_pips``
    plus the reserved ``degenerate``/``breakout`` flags).

    ``direction`` must be BUY or SELL (BUY=LONG, SELL=SHORT). SHORT/LONG are
    rejected and degrade to the neutral plan — the bot never re-labels them.
    """
    try:
        cfg_dict: Dict[str, Any] = cfg if isinstance(cfg, dict) else {}
        base_tp = _base_tp(base_tp_pips)

        # Overlay switched off (safety net; the bot also gates the load on it).
        if not _as_bool(_cfg_get(cfg_dict, "ENABLED", True), True):
            return _neutral_plan(base_lot, base_tp, reason="ok")

        normalized = _normalize_direction(direction)
        if normalized is None:
            logger.error(
                "Fib Zone: direction %r rejected — only BUY/SELL allowed; "
                "using neutral plan (v685 behaviour)",
                direction,
            )
            return _neutral_plan(base_lot, base_tp, reason="fib_invalid")

        fib, missing_reason = _extract_fib(rec)
        if fib is None:
            logger.warning(
                "Fib Zone: %s — using default size and original TP (no skip)",
                missing_reason,
            )
            return _neutral_plan(base_lot, base_tp, reason=missing_reason)

        # Reserved fields — not produced by schema 1.1.0 yet (always False).
        degenerate = _as_bool(fib.get("degenerate", False))
        breakout = _as_bool(fib.get("breakout", False))

        if degenerate and _as_bool(_cfg_get(cfg_dict, "SKIP_WHEN_DEGENERATE", True), True):
            logger.warning("Fib Zone: degenerate fib record — SKIP this candidate")
            return _neutral_plan(
                base_lot,
                base_tp,
                reason="fib_degenerate",
                skip=True,
                degenerate=True,
                breakout=breakout,
            )
        if breakout and _as_bool(_cfg_get(cfg_dict, "SKIP_BREAKOUT", False), False):
            logger.warning("Fib Zone: breakout fib record — SKIP this candidate")
            return _neutral_plan(
                base_lot,
                base_tp,
                reason="fib_breakout",
                skip=True,
                degenerate=degenerate,
                breakout=True,
            )

        zone_index, ratio_pos, invalid_reason = _validate_fib(fib)
        if zone_index is None:
            logger.warning(
                "Fib Zone: invalid fib (%s) — treated as fib_missing, "
                "default size + original TP (no skip)",
                invalid_reason,
            )
            return _neutral_plan(
                base_lot,
                base_tp,
                reason="fib_invalid",
                degenerate=degenerate,
                breakout=breakout,
            )

        center_edge = _as_int(_cfg_get(cfg_dict, "CENTER_EDGE", 2), 2)
        ladder = _size_ladder(cfg_dict)
        min_lot = _as_int(_cfg_get(cfg_dict, "MIN_LOT", 1000), 1000)

        is_short = normalized == "SELL"
        if is_short:
            late_distance = max(0, center_edge - zone_index)
        else:
            late_distance = max(0, zone_index - center_edge - 1)

        size_scale = ladder[min(late_distance, len(ladder) - 1)]
        raw_units = _size_units(base_lot, size_scale)
        size_units = max(raw_units, min_lot)

        room = ratio_pos if is_short else (1.0 - ratio_pos)
        room_ref = _as_finite_float(_cfg_get(cfg_dict, "TP_ROOM_REF", 0.5))
        if room_ref is None or room_ref <= 0.0:
            room_ref = 0.5

        tp_min = _as_finite_float(_cfg_get(cfg_dict, "TP_SCALE_MIN", 0.5))
        tp_max = _as_finite_float(_cfg_get(cfg_dict, "TP_SCALE_MAX", 1.0))
        tp_min = 0.5 if tp_min is None else max(0.0, tp_min)
        tp_max = 1.0 if tp_max is None else tp_max
        tp_max = min(1.0, tp_max)  # guardrail: TP is shrink-only
        tp_min = min(tp_min, tp_max)
        tp_scale = min(tp_max, max(tp_min, room / room_ref))

        min_tp = _as_finite_float(_cfg_get(cfg_dict, "MIN_TP_PIPS", 10))
        min_tp = 10.0 if min_tp is None else max(0.0, min_tp)
        if base_tp > 0.0:
            # min() keeps the hard rule "TP only shrinks": the MIN_TP_PIPS
            # floor may lift the scaled value, never above the base TP.
            tp_pips = min(base_tp, max(min_tp, round(base_tp * tp_scale, 1)))
        else:
            tp_pips = base_tp

        return {
            "skip": False,
            "reason": "ok",
            "zone_index": zone_index,
            "ratio_pos": ratio_pos,
            "room": room,
            "late_distance": late_distance,
            "size_scale": float(size_scale),
            "size_units": size_units,
            "tp_scale": float(tp_scale),
            "tp_pips": float(tp_pips),
            "degenerate": degenerate,
            "breakout": breakout,
        }
    except Exception:  # pragma: no cover - defensive: must never propagate
        logger.exception(
            "Fib Zone: compute_zone_plan failed unexpectedly — neutral plan "
            "(v685 behaviour preserved)"
        )
        return _neutral_plan(base_lot, base_tp_pips, reason="fib_invalid")


# ─────────────────────────────────────────────────────────────────────────────
# Audit log formatting (one line per candidate: open AND skip)
# ─────────────────────────────────────────────────────────────────────────────
def format_zone_audit(
    pair: str,
    direction: str,
    plan: Optional[Dict[str, Any]],
    base_lot: Optional[Any] = None,
    base_tp_pips: Optional[Any] = None,
) -> str:
    """Render the mandatory Fib Zone audit fields as one `key=value | ...` line.

    Fields: pair, direction, zone_index, ratio_pos, room, late_distance,
    size_scale, units(base→final), tp_scale, tp(base→final), reason.
    Never raises (the audit log must not be able to break a run).
    """
    try:
        safe_plan: Dict[str, Any] = plan if isinstance(plan, dict) else {}

        def _num(value: Any, digits: int = 3) -> str:
            number = _as_finite_float(value)
            return "None" if number is None else f"{number:.{digits}f}"

        base_units = (
            safe_plan.get("size_units")
            if base_lot is None
            else _as_int(base_lot, 0)
        )
        base_tp = (
            safe_plan.get("tp_pips")
            if base_tp_pips is None
            else _as_finite_float(base_tp_pips)
        )
        parts = [
            f"pair={pair}",
            f"dir={direction}",
            f"reason={safe_plan.get('reason', '?')}",
            f"zone={safe_plan.get('zone_index')}",
            f"ratio_pos={_num(safe_plan.get('ratio_pos'))}",
            f"room={_num(safe_plan.get('room'))}",
            f"late={safe_plan.get('late_distance', 0)}",
            f"size_scale={_num(safe_plan.get('size_scale'), 2)}",
            f"units={base_units}->{safe_plan.get('size_units')}",
            f"tp_scale={_num(safe_plan.get('tp_scale'), 2)}",
            f"tp={_num(base_tp, 1)}->{_num(safe_plan.get('tp_pips'), 1)}",
        ]
        return " | ".join(parts)
    except Exception:  # pragma: no cover - audit must never raise
        return f"pair={pair} | dir={direction} | reason=audit_error"