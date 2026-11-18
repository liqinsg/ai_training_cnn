#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""utils/analyze_exit_audit.py — 平仓审计分析（只读）

数据源：logs/exit_audit_YYYYMMDD.jsonl（由 audit_owned_closed_trades 落盘，见
fx_trade_bot_utils_v1.py）。产出计划 docs/NEXT_DEV_PLAN_20261117.md §5.2 要求的
「SL/TP/ACTIVE 分解 + 逐 pair 尾部统计」，用于：
  * §1 验收：SL/TP/ACTIVE 计数与 P&L 可与 OANDA 手工对账；
  * §3 验收：影子标出的 wide-range 时段 SL 命中率是否显著更高（需先有基线）。

本脚本**纯只读**：不写任何 state、不改任何决策、绝不抛异常（坏行跳过）。

用法：
    python utils/analyze_exit_audit.py                # 全部历史 jsonl
    python utils/analyze_exit_audit.py --days 7       # 仅最近 7 个文件
    python utils/analyze_exit_audit.py --logs-dir logs
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


# ─────────────────────────────────────────────────────────────────────────────
# 数据加载
# ─────────────────────────────────────────────────────────────────────────────
def load_records(logs_dir: Path, days: Optional[int]) -> List[Dict[str, Any]]:
    files = sorted(logs_dir.glob("exit_audit_*.jsonl"))
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
    v = rec.get(key)
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def pct(values: List[float], q: float) -> Optional[float]:
    """线性插值分位。空列表 → None。"""
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
# 报告
# ─────────────────────────────────────────────────────────────────────────────
def build_report(records: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    if not records:
        return "（无审计记录：logs/exit_audit_*.jsonl 为空）"

    total = len(records)
    by_reason: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in records:
        by_reason[str(r.get("exit_reason") or "UNKNOWN")].append(r)

    files = sorted({str(r.get("close_time") or "")[:10] for r in records})

    lines.append("=" * 72)
    lines.append("Exit Audit Report")
    lines.append(f"闭合日(close_time 前缀): {', '.join(f for f in files if f)}")
    lines.append(f"总平仓笔数: {total}")
    lines.append("=" * 72)

    # ── 1. 按平仓原因分解 ─────────────────────────────────────────────
    lines.append("")
    lines.append("[1] 按 exit_reason 分解")
    lines.append(f"  {'reason':<8}{'n':>6}{'sum_pl':>12}{'avg_pl':>10}{'med_pl':>10}{'med_pips':>10}")
    for reason, rs in sorted(by_reason.items(), key=lambda kv: -len(kv[1])):
        pls = [x for x in (_f(r, "realized_pl") for r in rs) if x is not None]
        pips = [x for x in (_f(r, "pips") for r in rs) if x is not None]
        lines.append(
            f"  {reason:<8}{len(rs):>6}{_fmt(sum(pls), 12)}"
            f"{_fmt(sum(pls) / len(pls) if pls else None, 10)}{_fmt(_med(pls), 10)}"
            f"{_fmt(_med(pips), 10)}"
        )

    # ── 2. SL 尾部 ────────────────────────────────────────────────────
    sl = by_reason.get("SL", [])
    if sl:
        # 按「亏损幅度」升序（abs）→ p50 < p90 < p95 直观表示"越来越深"；
        # 直接对负数排序会让 p90 显示成"小亏损"，语义反直觉，故取 abs。
        sl_usd_mag = sorted(abs(x) for x in (_f(r, "realized_pl") for r in sl) if x is not None)
        sl_pips_mag = sorted(abs(x) for x in (_f(r, "pips") for r in sl) if x is not None)
        lines.append("")
        lines.append(f"[2] SL 亏损幅度尾部（共 {len(sl)} 笔，越靠右越深）")
        lines.append(f"  USD  p50={_fmt(_med(sl_usd_mag))}  p90={_fmt(pct(sl_usd_mag,0.9))}"
                     f"  p95={_fmt(pct(sl_usd_mag,0.95))}  max={_fmt(sl_usd_mag[-1] if sl_usd_mag else None)}")
        lines.append(f"  pips p50={_fmt(_med(sl_pips_mag))}  p90={_fmt(pct(sl_pips_mag,0.9))}"
                     f"  p95={_fmt(pct(sl_pips_mag,0.95))}  max={_fmt(sl_pips_mag[-1] if sl_pips_mag else None)}")
        # 尾部集中度
        tail_n = max(1, round(len(sl_usd_mag) * 0.25))
        tail_loss = sum(sl_usd_mag[-tail_n:])  # 最大的 tail_n 笔
        total_loss = sum(sl_usd_mag)
        if total_loss:
            lines.append(
                f"  最深 {tail_n} 笔(约 p75 尾部) 合计 -{tail_loss:.2f}"
                f" = 全部 SL 亏损的 {100 * tail_loss / total_loss:.0f}%"
            )

    # ── 3. R:R 几何 ───────────────────────────────────────────────────
    tp = by_reason.get("TP", [])
    tp_pips = [x for x in (_f(r, "pips") for r in tp) if x is not None]
    sl_pips_all = [abs(x) for x in (_f(r, "pips") for r in sl) if x is not None]
    m_tp, m_sl = _med(tp_pips), _med(sl_pips_all)
    lines.append("")
    lines.append("[3] R:R 几何（|pips| 中位）")
    lines.append(f"  TP 中位 {_fmt(m_tp)} | SL 中位 {_fmt(m_sl)}"
                 + (f" | SL/TP = {m_sl / m_tp:.2f}" if (m_tp and m_sl) else ""))

    # ── 4. 逐 pair（按 SL 亏损排序）────────────────────────────────────
    by_pair: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in records:
        by_pair[str(r.get("instrument") or "?")].append(r)
    rows = []
    for pair, rs in by_pair.items():
        sl_rs = [r for r in rs if r.get("exit_reason") == "SL"]
        sl_sum = sum(x for x in (_f(r, "realized_pl") for r in sl_rs) if x is not None)
        rows.append((sl_sum, pair, len(rs), len(sl_rs)))
    rows.sort()
    lines.append("")
    lines.append("[4] 逐 pair（按 SL 亏损升序，前 15）")
    lines.append(f"  {'pair':<10}{'n':>5}{'SL_n':>6}{'SL_rate':>9}{'SL_sum':>12}")
    for sl_sum, pair, n, sln in rows[:15]:
        rate = f"{100 * sln / n:.0f}%" if n else "-"
        lines.append(f"  {pair:<10}{n:>5}{sln:>6}{rate:>9}{_fmt(sl_sum, 12)}")

    # ── 5. 最差 10 笔 SL ──────────────────────────────────────────────
    if sl:
        worst = sorted(sl, key=lambda r: (_f(r, "realized_pl") or 0))[:10]
        lines.append("")
        lines.append("[5] 最差 10 笔 SL")
        lines.append(f"  {'close_time':<20}{'pair':<10}{'dir':<6}{'pips':>9}{'usd':>10}{'profile':>9}")
        for r in worst:
            lines.append(
                f"  {str(r.get('close_time') or '')[:19]:<20}"
                f"{str(r.get('instrument') or '?'):<10}"
                f"{str(r.get('direction') or '?'):<6}"
                f"{_fmt(_f(r,'pips'), 9)}{_fmt(_f(r,'realized_pl'), 10)}"
                f"{str(r.get('profile') or '-'):>9}"
            )

    # ── 6. SL 时间聚簇（同分钟被扫）────────────────────────────────────
    if sl:
        buckets: Counter = Counter()
        for r in sl:
            t = str(r.get("close_time") or "").replace("T", " ")[:16]  # 到分钟
            if t:
                buckets[t] += 1
        multi = [(t, c) for t, c in buckets.most_common() if c >= 2]
        lines.append("")
        lines.append("[6] SL 同分钟聚簇（c≥2，相关性扫损候选）")
        if multi:
            for t, c in multi[:10]:
                pairs = [str(x.get("instrument")) for x in sl
                         if str(x.get("close_time") or "").replace("T", " ")[:16] == t]
                lines.append(f"  {t}  命中 {c} 笔: {', '.join(pairs)}")
        else:
            lines.append("  （无）")

    lines.append("")
    lines.append("=" * 72)
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Exit audit report (read-only)")
    ap.add_argument("--logs-dir", default="logs", help="审计 jsonl 所在目录 (默认 logs)")
    ap.add_argument("--days", type=int, default=None, help="仅分析最近 N 个文件")
    args = ap.parse_args()

    logs_dir = Path(args.logs_dir)
    if not logs_dir.is_absolute():
        logs_dir = Path(__file__).resolve().parent.parent / logs_dir
    records = load_records(logs_dir, args.days)
    print(build_report(records))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
