#!/usr/bin/env python3
"""
Fibonacci segmentation & labeling for FX Monte-Carlo results.

For a given day:
  1. pick the EARLIEST version of each timeframe file (mc_D_*/mc_W_*, by HHMM in name),
  2. split the MC range (range_90) with Fibonacci ratios 0 / 0.236 / 0.382 / 0.5 /
     0.618 / 0.786 / 1.0 and label every zone,
  3. write back into the MC json (fib block per pair + metadata),
  4. save the segmented payload back to the same source JSON file.

Usage:
    python3 fib_mc_segment.py 20261103
"""
import argparse
import copy
import json
import os
import re
import tempfile
from pathlib import Path

MC_DIR = Path(__file__).resolve().parent / "mc_results"

# Fibonacci ratios: retracement/extension grid used for zone splitting
FIB_RATIOS = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]

# (low_ratio, high_ratio) -> (short tag, label)
FIB_ZONES = [
    (0.0, 0.236, "F0", "Deep Discount"),
    (0.236, 0.382, "F236", "Discount"),
    (0.382, 0.5, "F382", "Below Equilibrium"),
    (0.5, 0.618, "F5", "Above Equilibrium"),
    (0.618, 0.786, "F618", "Premium"),
    (0.786, 1.0, "F786", "Deep Premium"),
]

# Which zone sets up what, given direction of bias
def fib_bias_action(zone_idx: int, p_up: float) -> str:
    """zone_idx: 0 = lowest zone ... 5 = highest zone."""
    bull = p_up >= 50.0
    if zone_idx <= 1:            # bottom of range
        return "BUY_ZONE" if bull else "REVERSAL_WATCH_LONG"
    if zone_idx == 2:
        return "BUY_LIMIT" if bull else "NEUTRAL"
    if zone_idx == 3:
        return "NEUTRAL" if bull else "SELL_LIMIT"
    if zone_idx == 4:
        return "REVERSAL_WATCH_SHORT" if bull else "SELL_ZONE"
    return "SELL_ZONE" if not bull else "REVERSAL_WATCH_SHORT"


def fib_levels(lo: float, hi: float) -> dict:
    span = hi - lo
    return {f"fib_{int(r*1000)/10:g}": round(lo + span * r, 6) for r in FIB_RATIOS}


def locate_zone(price: float, lo: float, hi: float) -> int:
    if hi <= lo:
        return 3
    pos = (price - lo) / (hi - lo)
    for i, (a, b, _tag, _name) in enumerate(FIB_ZONES):
        if a <= pos <= b:
            return i
    return 5 if pos > 1 else 0


def compute_zone_metrics(current_price: float, lo: float, hi: float) -> dict:
    diff = hi - lo
    if diff <= 0 or lo <= 0:
        return {
            "degenerate": True,
            "range_90_pct": 0.0,
            "ratio_pos": 0.5,
            "breakout": False,
            "zone_index": 3,
            "clipped_pos": 0.5,
        }

    range_90_pct = round((diff / current_price) * 100, 3)
    ratio_pos = (current_price - lo) / diff
    breakout = ratio_pos < 0.0 or ratio_pos > 1.0
    clipped_pos = max(0.0, min(1.0, ratio_pos))

    zone_idx = 3
    for i, (a, b, _tag, _name) in enumerate(FIB_ZONES):
        if a <= clipped_pos <= b:
            zone_idx = i
            break

    return {
        "degenerate": False,
        "range_90_pct": range_90_pct,
        "ratio_pos": round(ratio_pos, 4),
        "breakout": breakout,
        "zone_index": zone_idx,
        "clipped_pos": clipped_pos,
    }


def segment_pair(rec: dict, *, min_width_pct_gate: float = 1.2) -> dict:
    lo, hi = float(rec["range_90"][0]), float(rec["range_90"][1])
    current_price = float(rec["current_price"])
    levels = fib_levels(lo, hi)
    edge = {r: lo + (hi - lo) * r for r in FIB_RATIOS}

    zones = []
    for a, b, tag, name in FIB_ZONES:
        zones.append({
            "tag": tag,
            "label": name,
            "ratio": [a, b],
            "price": [round(edge[a], 6), round(edge[b], 6)],
        })

    metrics = compute_zone_metrics(current_price, lo, hi)
    zone_idx = metrics["zone_index"]
    z = FIB_ZONES[zone_idx]
    edge_lo, edge_hi = edge[z[0]], edge[z[1]]
    width = edge_hi - edge_lo
    clipped_pos = metrics["clipped_pos"]
    zone_pos = ((clipped_pos - z[0]) / (z[1] - z[0]) * 100) if width > 0 else 50.0

    if metrics["degenerate"] or metrics["range_90_pct"] < min_width_pct_gate:
        k_factor = 1.0
        k_reason = "range_too_narrow_or_degenerate"
    else:
        if zone_idx in [2, 3]:
            k_factor = 1.0
            k_reason = "equilibrium_zone"
        elif zone_idx in [1, 4]:
            k_factor = 0.5
            k_reason = "warning_zone"
        else:
            k_factor = 0.2
            k_reason = "extreme_tail_zone"

    rec["fib"] = {
        "schema_version": "1.1.0",
        "levels": levels,
        "zones": zones,
        "current_zone": {
            "tag": z[2],
            "label": z[3],
            "ratio": [z[0], z[1]],
            "price": [round(edge_lo, 6), round(edge_hi, 6)],
            "position_in_zone_pct": round(zone_pos, 1),
        },
        "zone_index": zone_idx,
        "range_90_pct": metrics["range_90_pct"],
        "ratio_pos": metrics["ratio_pos"],
        "breakout": metrics["breakout"],
        "degenerate": metrics["degenerate"],
        "risk_model": {
            "multiplier_k": k_factor,
            "reason": k_reason,
            "min_width_gate_pct": min_width_pct_gate,
        },
        "labels": {
            "fib_zone": f"FIB {z[2]} | {z[3]}",
            "fib_position": f"FIB {zone_idx + 1}/6 {round(zone_pos)}% in {z[2]}",
            "action": fib_bias_action(zone_idx, float(rec.get("p_up", 50.0))),
        },
        "fib_regime_label": f"🧭 FIB {z[2]} {z[3]} | {rec.get('regime', '')}",
    }
    return rec


def segment_mc_data(mc_data: dict, *, date: str | None = None, min_width_pct_gate: float = 1.2) -> dict:
    """Return an MC payload enriched with Fibonacci data, without file I/O.

    The input shape is the unified MC JSON object: ``metadata`` and a
    ``results`` mapping keyed by pair. The input is left unchanged.
    """
    if not isinstance(mc_data, dict) or not isinstance(mc_data.get("results"), dict):
        raise ValueError("MC data must be a dict containing a 'results' mapping")

    segmented = copy.deepcopy(mc_data)
    for pair, rec in segmented["results"].items():
        if not isinstance(rec, dict):
            raise ValueError(f"MC result for {pair!r} must be a dictionary")
        segmented["results"][pair] = segment_pair(rec, min_width_pct_gate=min_width_pct_gate)

    metadata = segmented.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError("MC data 'metadata' must be a dictionary")
    metadata["schema_version"] = "1.1.0"
    metadata["fib_segmentation"] = {
        "method": "Fibonacci grid on range_90",
        "ratios": FIB_RATIOS,
        "zones": [
            {"tag": z[2], "label": z[3], "ratio": [z[0], z[1]]}
            for z in FIB_ZONES
        ],
        "date": date,
    }
    return segmented


def pick_earliest(files):
    """files: list of (path, HHMM). Return path with smallest HHMM."""
    return sorted(files, key=lambda x: x[1])[0][0]


def save_json_safely(file_path: Path, data: dict) -> None:
    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(
        dir=str(file_path.parent), prefix="tmp_fib_", suffix=".json"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(temp_path, file_path)
    except Exception as e:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        raise e


def process(day: str, out_dir: Path):
    results = []
    for tf in ("D", "W"):
        pat = re.compile(rf"^mc_{tf}_all_pairs_{day}_(\d{{4}})\.json$")
        cands = []
        for p in out_dir.glob(f"mc_{tf}_all_pairs_{day}_*.json"):
            m = pat.match(p.name)
            if m:
                cands.append((p, m.group(1)))
        if not cands:
            print(f"[!] no {tf} file for {day}")
            continue
        src = pick_earliest(cands)
        data = segment_mc_data(json.loads(src.read_text(encoding="utf-8")), date=day)
        save_json_safely(src, data)
        print(f"[✓] Segmented in place: {src.name}")
        results.append(src)
    return results


apply_fib_segmentation = segment_mc_data


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("day", help="YYYYMMDD")
    ap.add_argument("--dir", default=str(MC_DIR))
    args = ap.parse_args()
    process(args.day, Path(args.dir))