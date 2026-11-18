#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""utils/analyze_sizing_shadow.py — L2 风险定额仓位 · 影子分析（只读）

数据源：
  * logs/sizing_shadow_YYYYMMDD.jsonl  （v685 影子层落盘，见 utils/risk_parity_sizing.py）
  * logs/exit_audit_YYYYMMDD.jsonl     （P0 平仓审计，用于反事实真实结果）

产出 docs/NEXT_DEV_PLAN_20261117.md §2.1 的验收指标：
  [1] 影子覆盖概览        [2] rp_mult 分布 / 缩量占比
  [3] units 前后对比      [4] 逐 pair rp_mult
  [5] 反事实 SL 尾部       [6] 反事实净期望（EV 是否恶化）

反事实口径：同一价格波动下 realized_pl ∝ units，故对每笔真实平仓
    cf_pl = realized_pl × (units_l2 / units_prob)
(units_l2/units_prob 取自该笔对应的影子候选，按 pair+direction+entry_price 最近匹配)。

本脚本**纯只读**：不写 state、不改决策、绝不抛异常（坏行/未匹配跳过）。

用法：
    python utils/analyze_sizing_shadow.py                 # 全部历史
    python utils/analyze_sizing_shadow.py --days 1        # 仅最近 1 个影子文件
    python utils/analyze_sizing_shadow.py --logs-dir logs
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ─────────────────────────────────────────────────────────────────────────────
# 数据加载
# ─────────────────────────────────────────────────────────────────────────────
def load_jsonl(logs_dir: Path, glob_pat: str, days: Optional[int]) -> List[Dict[str, Any]]:
    files = sorted(logs_dir.glob(glob_pat))
    if days is not None and days > 0:
        files = files[-days:]
    records: List[Dict[str, Any]] = []
    for fp in files:
        try:
            with fp.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except Exception:
                        continue  # 坏行跳过，永不抛
        except Exception:
            continue
    return records


# ─────────────────────────────────────────────────────────────────────────────
# 统计小工具
# ─────────────────────────────────────────────────────────────────────────────
def _f(rec: Dict[str, Any], key: str) -> Optional[float]:
    try:
        return float(rec.get(key))
    except (TypeError, ValueError):
        return None


def pct(values: List[float], q: float) -> Optional[float]:
    if not values:
        return None
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    pos = (len(s) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def _med(values: List[float]) -> Optional[float]:
    return pct(values, 0.5)


def _fmt(v: Optional[float], w: int = 8, dec: int = 2) -> str:
    return f"{v:>{w}.{dec}f}" if v is not None else f"{'-':>{w}}"


# ─────────────────────────────────────────────────────────────────────────────
# 反事实匹配：影子候选 → 真实平仓
# ─────────────────────────────────────────────────────────────────────────────
def _match_ratio(
    cand: Dict[Tuple[str, str], List[Tuple[float, float]]],
    pair: str,
    direction: str,
    entry: Optional[float],
    rel_tol: float = 0.005,
) -> Optional[float]:
    """在影子候选中找与 (pair, direction, entry) 最接近的一条，返回缩量比 units_l2/units_prob。"""
    if entry is None:
        return None
    options = cand.get((pair, direction))
    if not options:
        return None
    best_r: Optional[float] = None
    best_d = None
    for price, ratio in options:
        d = abs(price - entry)
        if d <= abs(entry) * rel_tol and (best_d is None or d < best_d):
            best_d, best_r = d, ratio
    return best_r


def _tail_summary(rows: List[Tuple[float, float]]) -> Dict[str, Optional[float]]:
    """rows = [(actual_pl, cf_pl)]，仅取 SL（负值）。返回 actual/cf 的幅度尾部。"""
    act_mag = sorted(abs(a) for a, _ in rows)
    cf_mag = sorted(abs(c) for _, c in rows)
    out: Dict[str, Optional[float]] = {
        "n": float(len(rows)),
        "act_p50": _med(act_mag), "act_p90": pct(act_mag, 0.9), "act_max": act_mag[-1] if act_mag else None,
        "cf_p50": _med(cf_mag), "cf_p90": pct(cf_mag, 0.9), "cf_max": cf_mag[-1] if cf_mag else None,
    }
    if act_mag:
        tn = max(1, round(len(act_mag) * 0.25))
        out["act_tail_share"] = 100.0 * sum(act_mag[-tn:]) / sum(act_mag) if sum(act_mag) else None
    if cf_mag:
        tn = max(1, round(len(cf_mag) * 0.25))
        out["cf_tail_share"] = 100.0 * sum(cf_mag[-tn:]) / sum(cf_mag) if sum(cf_mag) else None
    return out


# ─────────────────────────────────────────────────────────────────────────────
# 报告
# ─────────────────────────────────────────────────────────────────────────────
def build_report(shadow: List[Dict[str, Any]], exits: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    lines.append("=" * 72)
    lines.append("Sizing Shadow Report · L2 风险定额仓位（只缩不放大）")
    lines.append("=" * 72)
    if not shadow:
        lines.append("（无影子记录：logs/sizing_shadow_*.jsonl 为空 —— 等 bot 跑过一个周期）")
        return "\n".join(lines)

    n = len(shadow)
    applied = sum(1 for r in shadow if r.get("applied"))
    days = sorted({str(r.get("ts") or "")[:10] for r in shadow if r.get("ts")})
    lines.append(f"影子笔数: {n} | 时间跨度(UTC): {days[0] if days else '?'} ~ {days[-1] if days else '?'}")
    lines.append(f"applied(RISK_PARITY_SIZING=ON): {applied}/{n}")
    lines.append("")

    # ── [2] rp_mult 分布 ─────────────────────────────────────────────
    mults = [m for m in (_f(r, "rp_mult") for r in shadow) if m is not None]
    shrink = [m for m in mults if m < 0.999]
    lines.append("[2] rp_mult 分布（只缩不放大，1.0 = 不动）")
    lines.append(f"  p10={_fmt(pct(mults,0.1))}  p25={_fmt(pct(mults,0.25))}  p50={_fmt(_med(mults))}"
                 f"  p75={_fmt(pct(mults,0.75))}  p90={_fmt(pct(mults,0.9))}")
    lines.append(f"  缩量笔数(rp_mult<1): {len(shrink)}/{len(mults)}"
                 f" ({100*len(shrink)/len(mults):.0f}%)" if mults else "  （无）")
    if mults:
        clamps = sum(1 for m in mults if m <= 0.2501)
        lines.append(f"  触底(clamp 至 RP_F_LO≈0.25): {clamps} ({100*clamps/len(mults):.0f}%)")

    # ── [3] units 前后对比 ───────────────────────────────────────────
    u_prob = [u for u in (_f(r, "units_prob") for r in shadow) if u is not None]
    u_l2 = [u for u in (_f(r, "units_l2") for r in shadow) if u is not None]
    lines.append("")
    lines.append("[3] units 前后对比（影子反事实 vs 当前下单）")
    lines.append(f"  units_prob p50={_fmt(_med(u_prob),8,0)}  sum={_fmt(sum(u_prob),12,0)}")
    lines.append(f"  units_l2   p50={_fmt(_med(u_l2),8,0)}  sum={_fmt(sum(u_l2),12,0)}"
                 + (f"  overall={100*sum(u_l2)/sum(u_prob):.0f}%" if sum(u_prob) else ""))

    # ── [4] 逐 pair ─────────────────────────────────────────────────
    by_pair: Dict[str, List[float]] = defaultdict(list)
    for r in shadow:
        m = _f(r, "rp_mult")
        if m is not None:
            by_pair[str(r.get("pair") or "?")].append(m)
    rows = sorted((( _med(v) or 1.0, k, len(v)) for k, v in by_pair.items()))
    lines.append("")
    lines.append("[4] 逐 pair（按 rp_mult 中位升序，前 15；越小缩得越狠）")
    lines.append(f"  {'pair':<10}{'n':>5}{'med_rp_mult':>13}")
    for med, pair, cnt in rows[:15]:
        lines.append(f"  {pair:<10}{cnt:>5}{_fmt(med, 13)}")

    # ── 反事实：影子候选索引 ─────────────────────────────────────────
    cand: Dict[Tuple[str, str], List[Tuple[float, float]]] = defaultdict(list)
    for r in shadow:
        pair = str(r.get("pair") or "")
        direction = str(r.get("direction") or "")
        price = _f(r, "entry_price")
        up, ul = _f(r, "units_prob"), _f(r, "units_l2")
        if pair and direction and price is not None and up and up > 0 and ul is not None:
            cand[(pair, direction)].append((price, ul / up))

    matched: List[Tuple[str, float, float, float]] = []  # (reason, actual_pl, cf_pl, ratio)
    for e in exits:
        pair = str(e.get("instrument") or "")
        direction = str(e.get("direction") or "")
        act = _f(e, "realized_pl")
        if act is None:
            continue
        ratio = _match_ratio(cand, pair, direction, _f(e, "entry_price"))
        if ratio is None:
            continue
        matched.append((str(e.get("exit_reason") or "UNKNOWN"), act, act * ratio, ratio))

    lines.append("")
    lines.append("=" * 72)
    if not matched:
        lines.append("（反事实跳过：exit_audit 无匹配到影子候选 —— 影子与平仓需同日/同 pair）")
        return "\n".join(lines)

    matched_sl = [(a, c) for rs, a, c, _ in matched if rs == "SL"]
    lines.append(f"反事实匹配: {len(matched)}/{len(exits)} 笔（SL {len(matched_sl)}）")
    lines.append("=" * 72)

    # ── [5] 反事实 SL 尾部 ───────────────────────────────────────────
    if matched_sl:
        t = _tail_summary(matched_sl)
        lines.append("")
        lines.append("[5] SL 亏损幅度尾部（USD，abs）—— actual vs 反事实")
        lines.append(f"  {'':<8}{'p50':>9}{'p90':>9}{'max':>9}{'最深25%占比':>14}")
        lines.append(f"  {'actual':<8}{_fmt(t['act_p50'],9)}{_fmt(t['act_p90'],9)}"
                     f"{_fmt(t['act_max'],9)}{_fmt(t.get('act_tail_share'),14,1)}")
        lines.append(f"  {'cf(L2)':<8}{_fmt(t['cf_p50'],9)}{_fmt(t['cf_p90'],9)}"
                     f"{_fmt(t['cf_max'],9)}{_fmt(t.get('cf_tail_share'),14,1)}")

    # ── [6] 反事实净期望 ─────────────────────────────────────────────
    act_net = sum(a for _, a, _, _ in matched)
    cf_net = sum(c for _, _, c, _ in matched)
    by_reason: Dict[str, List[Tuple[float, float]]] = defaultdict(list)
    for rs, a, c, _ in matched:
        by_reason[rs].append((a, c))
    lines.append("")
    lines.append("[6] 反事实净期望（EV 是否恶化 —— L2 的唯一风险点）")
    lines.append(f"  {'reason':<8}{'n':>6}{'actual_net':>13}{'cf_net':>13}")
    for rs, pairs in sorted(by_reason.items()):
        lines.append(f"  {rs:<8}{len(pairs):>6}{_fmt(sum(a for a,_ in pairs),13)}"
                     f"{_fmt(sum(c for _,c in pairs),13)}")
    d = cf_net - act_net
    lines.append(f"  合计 actual={act_net:.2f}  cf={cf_net:.2f}  Δ={d:+.2f}"
                 + (f"  ({100*d/abs(act_net):+.1f}%)" if act_net else ""))
    lines.append("")
    lines.append("  注：只缩不放大 → 宽 SL 笔的盈亏同步缩小；若 Δ 显著为负，须重新评估参考口径。")
    lines.append("=" * 72)
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Sizing shadow report (read-only)")
    ap.add_argument("--logs-dir", default="logs", help="jsonl 所在目录 (默认 logs)")
    ap.add_argument("--days", type=int, default=None, help="仅分析最近 N 个影子文件")
    args = ap.parse_args()

    logs_dir = Path(args.logs_dir)
    if not logs_dir.is_absolute():
        logs_dir = Path(__file__).resolve().parent.parent / logs_dir
    shadow = load_jsonl(logs_dir, "sizing_shadow_*.jsonl", args.days)
    exits = load_jsonl(logs_dir, "exit_audit_*.jsonl", args.days)
    print(build_report(shadow, exits))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
