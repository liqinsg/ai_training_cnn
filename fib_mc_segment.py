#!/usr/bin/env python3
"""
Fibonacci segmentation & labeling for FX Monte-Carlo results.

For a given day:
  1. pick the EARLIEST version of each timeframe file (mc_D_*/mc_W_*, by HHMM in name),
  2. split the MC range (range_90) with Fibonacci ratios 0 / 0.236 / 0.382 / 0.5 /
     0.618 / 0.786 / 1.0 and label every zone,
  3. write back into the MC json (fib block per pair + metadata),
  4. save as mc_<TF>_all_pairs_<YYYYMMDD>_fib.json (date only, no time).

Usage:
    python3 fib_mc_segment.py 20261103
    python3 fib_mc_segment.py 20261103 --dir /home/qili/projects/fx_monte_carlo/mc_results
"""
import argparse
import json
import re
from pathlib import Path

MC_DIR = Path("/home/qili/projects/fx_monte_carlo/mc_results")

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


def segment_pair(rec: dict) -> dict:
    lo, hi = float(rec["range_90"][0]), float(rec["range_90"][1])
    levels = fib_levels(lo, hi)
    # ratio -> price lookup for zone edges
    edge = {r: lo + (hi - lo) * r for r in FIB_RATIOS}

    zones = []
    for a, b, tag, name in FIB_ZONES:
        zones.append({
            "tag": tag,
            "label": name,
            "ratio": [a, b],
            "price": [round(edge[a], 6), round(edge[b], 6)],
        })

    zone_idx = locate_zone(float(rec["current_price"]), lo, hi)
    z = FIB_ZONES[zone_idx]
    edge_lo, edge_hi = edge[z[0]], edge[z[1]]
    width = edge_hi - edge_lo
    zone_pos = ((float(rec["current_price"]) - edge_lo) / width * 100) if width > 0 else 50.0

    rec["fib"] = {
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
        "labels": {
            "fib_zone": f"FIB {z[2]} | {z[3]}",
            "fib_position": f"FIB {zone_idx + 1}/6 {round(zone_pos)}% in {z[2]}",
            "action": fib_bias_action(zone_idx, float(rec.get("p_up", 50.0))),
        },
        # combined label: fib zone + existing MC regime
        "fib_regime_label": f"🧭 FIB {z[2]} {z[3]} | {rec.get('regime', '')}",
    }
    return rec


def pick_earliest(files):
    """files: list of (path, HHMM). Return path with smallest HHMM."""
    return sorted(files, key=lambda x: x[1])[0][0]


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
        data = json.loads(src.read_text())

        for pair, rec in data["results"].items():
            data["results"][pair] = segment_pair(rec)

        data.setdefault("metadata", {})
        data["metadata"]["fib_segmentation"] = {
            "method": "Fibonacci grid on range_90",
            "ratios": FIB_RATIOS,
            "zones": [{"tag": z[2], "label": z[3], "ratio": [z[0], z[1]]} for z in FIB_ZONES],
            "source_file": src.name,
            "date": day,
        }

        out = out_dir / f"mc_{tf}_all_pairs_{day}_fib.json"
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        print(f"[✓] {src.name}  ->  {out.name}")
        results.append(out)
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("day", help="YYYYMMDD")
    ap.add_argument("--dir", default=str(MC_DIR))
    args = ap.parse_args()
    process(args.day, Path(args.dir))
