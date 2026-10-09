"""
real_data_source.py — 读取 CSV + 日志双源，自动补全缺失字段
✅ 只读 · 不碰生产 · 可回滚
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
    direction: str  # BUY / SELL
    trend_raw: float  # +1.0 / 0.0 / -1.0
    location_raw: float  # +1.0=ABOVE / 0.0=AT / -1.0=BELOW
    xgb_p_up: float  # 0.0–1.0
    mc_p_up: float  # 0.0–1.0
    source: str
    timestamp: str = ""


def parse_symbol(raw: str) -> str:
    """EURJPY=X → EUR/JPY"""
    s = raw.strip()
    if "=" in s:
        s = s.split("=")[0]
    if len(s) == 6 and "/" not in s:
        return f"{s[:3]}/{s[3:]}"
    return s


def norm_direction(val: Any, score_final: Optional[float] = None) -> str:
    """多种输入 → BUY/SELL；score_final>50 兜底"""
    if not val and score_final is not None:
        return "BUY" if score_final > 50 else "SELL"
    if isinstance(val, (int, float)):
        return "BUY" if val > 0 else "SELL"
    s = str(val).strip().upper()
    if any(w in s for w in ["BUY", "LONG", "UP", "1"]):
        return "BUY"
    if any(w in s for w in ["SELL", "SHORT", "DOWN", "-1"]):
        return "SELL"
    # 数值字符串
    try:
        n = float(s)
        return "BUY" if n > 0 else "SELL"
    except ValueError:
        return "BUY" if score_final and score_final > 50 else "SELL"


def norm_trend(val: Any, score_s: Optional[float] = None) -> float:
    """trend_raw 或 score_s → ±1/0"""
    if not val and score_s is not None:
        if score_s > 55:
            return 1.0
        elif score_s < 45:
            return -1.0
        return 0.0
    try:
        n = float(val)
        if abs(n) < 0.1:
            return 0.0
        return 1.0 if n > 0 else -1.0
    except ValueError:
        s = str(val).upper()
        if "BULL" in s or "UP" in s or "HIGH" in s:
            return 1.0
        if "BEAR" in s or "DOWN" in s or "LOW" in s:
            return -1.0
        return 0.0


def norm_location(val: Any, score_s: Optional[float] = None) -> float:
    """location 或 score_s → +1=ABOVE / 0=AT / -1=BELOW"""
    if not val and score_s is not None:
        if score_s > 55:
            return 1.0
        elif score_s < 45:
            return -1.0
        return 0.0
    s = str(val).strip().upper()
    if "ABOVE" in s or "HIGH" in s or "OVER" in s:
        return 1.0
    if "BELOW" in s or "LOW" in s or "UNDER" in s:
        return -1.0
    if "AT" in s or "MID" in s or "NEUTRAL" in s:
        return 0.0
    # 数值
    try:
        n = float(s)
        if n > 0.5:
            return 1.0
        elif n < -0.5:
            return -1.0
        return 0.0
    except ValueError:
        if score_s:
            if score_s > 55:
                return 1.0
            elif score_s < 45:
                return -1.0
        return 0.0


def norm_prob(val: Any) -> float:
    """0–100 或 0–1 → 0–1"""
    try:
        f = float(val)
        if f > 1.0:
            f = f / 100.0
        return max(0.0, min(1.0, f))
    except (TypeError, ValueError):
        return 0.5


def load_from_csv(file_path: Path) -> List[Candidate]:
    candidates = []
    with open(file_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            score_final = float(row.get("score_final", row.get("FINAL", 50)) or 50)
            score_s = float(row.get("score_s", row.get("S", 50)) or 50)
            score_x = float(row.get("score_x", row.get("X", 50)) or 50)
            score_m = float(row.get("score_m", row.get("M", 50)) or 50)

            direction = norm_direction(row.get("direction") or row.get("action"), score_final)
            trend_raw = norm_trend(row.get("trend_raw"), score_s)
            location_raw = norm_location(row.get("location"), score_s)

            cand = Candidate(
                symbol=parse_symbol(row.get("pair", row.get("symbol", ""))),
                direction=direction,
                trend_raw=trend_raw,
                location_raw=location_raw,
                xgb_p_up=norm_prob(score_x),
                mc_p_up=norm_prob(score_m),
                source=f"csv:{file_path.parent.name}/{file_path.name}",
                timestamp=row.get("timestamp", ""),
            )
            candidates.append(cand)
    return candidates


def load_from_log(file_path: Path) -> List[Candidate]:
    """解析日志行: ⚖️ SCORE EURJPY=X SELL | S= 50.1×0.40=… X= 15.0×0.20= 3.0 M= 36.4×0.10= 3.6"""
    pattern = re.compile(
        r"SCORE\s+(\S+)\s+(BUY|SELL|LONG|SHORT)\s+"
        r".*?S=\s*([\d.]+)"
        r".*?X=\s*([\d.]+)"
        r".*?M=\s*([\d.]+)"
        r".*?FINAL=\s*([\d.]+)",
        re.IGNORECASE,
    )
    candidates = []
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            m = pattern.search(line)
            if not m:
                continue
            symbol = parse_symbol(m.group(1))
            side = m.group(2)
            s_score = float(m.group(3))
            x_score = float(m.group(4))
            m_score = float(m.group(5))
            final = float(m.group(6))

            direction = "BUY" if side.upper() in ["BUY", "LONG"] else "SELL"
            trend_raw = 1.0 if s_score > 55 else (-1.0 if s_score < 45 else 0.0)
            location_raw = 1.0 if s_score > 55 else (-1.0 if s_score < 45 else 0.0)

            candidates.append(Candidate(
                symbol=symbol,
                direction=direction,
                trend_raw=trend_raw,
                location_raw=location_raw,
                xgb_p_up=norm_prob(x_score),
                mc_p_up=norm_prob(m_score),
                source=f"log:{file_path.name}",
            ))
    return candidates


def load_real_candidates() -> List[Dict[str, Any]]:
    all_cands: List[Candidate] = []
    seen_keys = set()

    # CSV 源
    for pattern in ["**/*_signal_log.csv", "live_signal_log.csv"]:
        for p in PROJECT_ROOT.glob(pattern):
            if "attribution_v2" in str(p):
                continue
            for c in load_from_csv(p):
                key = (c.symbol, c.direction, c.trend_raw, c.xgb_p_up, c.mc_p_up)
                if key not in seen_keys:
                    seen_keys.add(key)
                    all_cands.append(c)

    # 日志源
    for p in (PROJECT_ROOT / "logs").glob("fx_bot_*.log"):
        for c in load_from_log(p):
            key = (c.symbol, c.direction, c.trend_raw, c.xgb_p_up, c.mc_p_up)
            if key not in seen_keys:
                seen_keys.add(key)
                all_cands.append(c)

    # 转为 batch_backtest 可用格式
    degraded_count = 0
    result = []
    for c in all_cands:
        is_degraded = (c.trend_raw == 0.0 and c.location_raw == 0.0)
        if is_degraded:
            degraded_count += 1
        result.append({
            "symbol": c.symbol,
            "direction": c.direction,
            "trend_raw": c.trend_raw,
            "location_raw": c.location_raw,
            "xgb_p_up": c.xgb_p_up,
            "mc_p_up": c.mc_p_up,
            "_source": c.source,
            "_degraded": is_degraded,
        })

    print(f"✅ Loaded {len(result)} real candidates")
    if degraded_count > 0:
        pct = degraded_count * 100 / len(result)
        print(f"   Degraded records:     {degraded_count} ({pct:.1f}%)")
    return result


if __name__ == "__main__":
    cands = load_real_candidates()
    print(f"\nSample:\n{cands[0] if cands else 'None'}")