"""
real_data_source.py — Unified CSV/Log loader + metadata
Single source of truth: discovery, parsing, normalization
✅ Read-only · No side effects · Idempotent
"""

import sys
from pathlib import Path
import csv
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class Candidate:
    symbol: str
    direction: str        # BUY / SELL
    trend_raw: float      # +1.0 / 0.0 / -1.0
    location_raw: float   # +1.0 / 0.0 / -1.0
    xgb_p_up: float       # 0.0–1.0
    mc_p_up: float        # 0.0–1.0
    source: str
    timestamp: str = ""
    degraded: bool = False


def parse_symbol(raw: str) -> str:
    """EURJPY=X → EUR/JPY"""
    s = raw.strip()
    if "=" in s:
        s = s.split("=")[0]
    if len(s) == 6 and "/" not in s:
        return f"{s[:3]}/{s[3:]}"
    return s


def norm_direction(row: Dict[str, Any]) -> str:
    """direction列 → action_taken列 → score_final兜底"""
    d = str(row.get("direction", "")).strip().upper()
    if d:
        if any(w in d for w in ["BUY", "LONG", "UP"]):
            return "BUY"
        if any(w in d for w in ["SELL", "SHORT", "DOWN"]):
            return "SELL"
    act = str(row.get("action_taken", "")).strip().upper()
    if act:
        if "BUY" in act or "LONG" in act:
            return "BUY"
        if "SELL" in act or "SHORT" in act:
            return "SELL"
    try:
        final = float(row.get("score_final", 50))
        return "BUY" if final > 50 else "SELL"
    except (TypeError, ValueError):
        return "BUY"


def norm_trend(row: Dict[str, Any]) -> float:
    """trend_raw列优先 → score_s推导；45–55=中性"""
    t = str(row.get("trend_raw", "")).strip()
    if t:
        try:
            n = float(t)
            if abs(n) < 0.1:
                return 0.0
            return 1.0 if n > 0 else -1.0
        except ValueError:
            pass
    try:
        s = float(row.get("score_s", 50))
        if s > 55:
            return 1.0
        elif s < 45:
            return -1.0
        return 0.0
    except (TypeError, ValueError):
        return 0.0


def norm_location(row: Dict[str, Any]) -> float:
    """location列优先 → score_s推导"""
    loc = str(row.get("location", "")).strip().upper()
    if loc:
        if "ABOVE" in loc or "HIGH" in loc:
            return 1.0
        if "BELOW" in loc or "LOW" in loc:
            return -1.0
        if "AT" in loc or "MID" in loc or "NEUTRAL" in loc:
            return 0.0
    try:
        s = float(row.get("score_s", 50))
        if s > 55:
            return 1.0
        elif s < 45:
            return -1.0
        return 0.0
    except (TypeError, ValueError):
        return 0.0


def norm_prob(val: Any) -> float:
    """0–100 或 0–1 → 归一化到 0.0–1.0"""
    try:
        f = float(val)
        if f > 1.0:
            f = f / 100.0
        return max(0.0, min(1.0, f))
    except (TypeError, ValueError):
        return 0.5


def discover_csv_files() -> List[Path]:
    patterns = ["**/*_signal_log.csv", "live_signal_log.csv"]
    files: List[Path] = []
    seen = set()
    for pat in patterns:
        for p in PROJECT_ROOT.glob(pat):
            if "attribution_v2" in str(p):
                continue
            rel = str(p.relative_to(PROJECT_ROOT))
            if rel not in seen:
                seen.add(rel)
                files.append(p)
    return sorted(files)


def discover_log_files() -> List[Path]:
    log_dir = PROJECT_ROOT / "logs"
    if not log_dir.exists():
        return []
    return sorted(log_dir.glob("fx_bot_*.log"))


def describe_sources() -> Dict[str, List[str]]:
    """Return discovered file lists for display — no loading, no side effects."""
    csv_files = [str(p.relative_to(PROJECT_ROOT)) for p in discover_csv_files()]
    log_files = [str(p.relative_to(PROJECT_ROOT)) for p in discover_log_files()]
    return {"csv": csv_files, "log": log_files}


def load_from_csv(file_path: Path) -> List[Candidate]:
    candidates = []
    with open(file_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                score_x = float(row.get("score_x", 50))
                score_m = float(row.get("score_m", 50))
            except (TypeError, ValueError):
                continue
            trend = norm_trend(row)
            loc = norm_location(row)
            cand = Candidate(
                symbol=parse_symbol(row.get("pair", "")),
                direction=norm_direction(row),
                trend_raw=trend,
                location_raw=loc,
                xgb_p_up=norm_prob(score_x),
                mc_p_up=norm_prob(score_m),
                source=f"csv:{file_path.parent.name}/{file_path.name}",
                timestamp=row.get("timestamp", ""),
                degraded=(trend == 0.0 and loc == 0.0),
            )
            candidates.append(cand)
    return candidates


def load_from_log(file_path: Path) -> List[Candidate]:
    pattern = re.compile(
        r"SCORE\s+(\S+)\s+(BUY|SELL|LONG|SHORT)\s+"
        r".*?S=\s*([\d.]+)"
        r".*?X=\s*([\d.]+)"
        r".*?M=\s*([\d.]+)",
        re.IGNORECASE,
    )
    candidates = []
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            m = pattern.search(line)
            if not m:
                continue
            s_score = float(m.group(3))
            trend = 1.0 if s_score > 55 else (-1.0 if s_score < 45 else 0.0)
            loc = trend  # same derivation from S score
            candidates.append(Candidate(
                symbol=parse_symbol(m.group(1)),
                direction="BUY" if m.group(2).upper() in ["BUY", "LONG"] else "SELL",
                trend_raw=trend,
                location_raw=loc,
                xgb_p_up=norm_prob(float(m.group(4))),
                mc_p_up=norm_prob(float(m.group(5))),
                source=f"log:{file_path.name}",
                degraded=(trend == 0.0 and loc == 0.0),
            ))
    return candidates


def load_real_candidates() -> List[Dict[str, Any]]:
    all_cands: List[Candidate] = []
    seen_keys = set()

    for p in discover_csv_files():
        for c in load_from_csv(p):
            key = (c.symbol, c.direction, round(c.trend_raw, 1), round(c.xgb_p_up, 2), round(c.mc_p_up, 2))
            if key not in seen_keys:
                seen_keys.add(key)
                all_cands.append(c)

    for p in discover_log_files():
        for c in load_from_log(p):
            key = (c.symbol, c.direction, round(c.trend_raw, 1), round(c.xgb_p_up, 2), round(c.mc_p_up, 2))
            if key not in seen_keys:
                seen_keys.add(key)
                all_cands.append(c)

    degraded_count = sum(1 for c in all_cands if c.degraded)
    result = []
    for c in all_cands:
        result.append({
            "symbol": c.symbol,
            "direction": c.direction,
            "trend_raw": c.trend_raw,
            "location_raw": c.location_raw,
            "xgb_p_up": c.xgb_p_up,
            "mc_p_up": c.mc_p_up,
            "_source": c.source,
            "_degraded": c.degraded,
        })

    print(f"✅ Loaded {len(result)} real candidates")
    if degraded_count > 0:
        pct = degraded_count * 100 / len(result)
        print(f"   Degraded records:     {degraded_count} ({pct:.1f}%)")
    return result


if __name__ == "__main__":
    print("Testing describe_sources():")
    for kind, paths in describe_sources().items():
        print(f"  {kind}: {len(paths)} file(s)")