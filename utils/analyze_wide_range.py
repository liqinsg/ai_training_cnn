"""
analyze_wide_range.py — Wide-range 损失聚集研究分析器（P1-B 配套）
==================================================================
读取：
  logs/wide_range_shadow_*.jsonl（pair/day/tier，含 trade_id 桥）
  logs/exit_audit_*.jsonl（OWNED 逐笔平仓，TASK-1 产出）
按 trade_id / 时间 / pair 对齐 join，每笔平仓标注其开仓时 tier。
输出 §3.2 六项指标（按 tier 分组）：
  1. SL 命中率
  2. 连续 SL 游程（max / mean run）
  3. 双向 SL 事件（同 pair 时间窗 T 内先 BUY 后 SELL 均 SL）
  4. 净 P&L（聚合口径）
  5. MFE / MAE（需 K 线，缺失则标注 not_available）
  6. 交易频率（单位时间开仓笔数 / 每 pair 每日笔数）
+ 处置方案反事实对比（阶梯降仓 0.25x/0.5x vs 频率抑制 vs 极端 skip）
+ 失败条件判断（wide 与 normal 无显著差异 → 判别量无效）

用法：
    python utils/analyze_wide_range.py --log-dir logs --out report.json
"""

from __future__ import annotations

import argparse
import json
import os
import glob
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

BIDIRECTIONAL_WINDOW_HOURS = 24  # 双向 SL 事件时间窗


def load_jsonl(path_pattern: str) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for path in sorted(glob.glob(path_pattern)):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    return records


def parse_time(iso: str) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def join_audit_with_tier(
    audit_records: List[Dict[str, Any]],
    wide_records: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """每笔平仓（OWNED + 聚合口径）标注其开仓时 tier。优先用 trade_id 精确匹配，否则按 pair+时间最近匹配。"""
    # 仓库 exit_audit（fx_trade_bot_utils_v1.audit_owned_closed_trades）已只含本 bot
    # OWNED 平仓，且按 trade_id 去重落盘 → 直接使用，仅再做一次 trade_id 去重兜底。
    seen_tid = set()
    owned = []
    for r in audit_records:
        tid = str(r.get("trade_id") or "")
        if tid:
            if tid in seen_tid:
                continue
            seen_tid.add(tid)
        owned.append(r)

    # trade_id → tier 映射
    tier_by_trade: Dict[str, str] = {}
    dskew_by_trade: Dict[str, float] = {}
    for w in wide_records:
        tid = w.get("trade_id")
        if tid:
            tier_by_trade[str(tid)] = w.get("tier", "normal")
            if w.get("d_skew") is not None:
                dskew_by_trade[str(tid)] = float(w.get("d_skew"))

    joined = []
    for r in owned:
        tid = str(r.get("trade_id", ""))
        tier = tier_by_trade.get(tid)
        d_skew = dskew_by_trade.get(tid)
        if tier is None:
            # fallback：按 pair + 时间最近匹配（开仓时间 ≈ 平仓时间 - 持仓时长；近似用 close_time 前 N 小时）
            pair = r.get("instrument", "")
            close_t = parse_time(r.get("close_time", ""))
            best = None
            best_dt = None
            for w in wide_records:
                if w.get("pair", "").replace("_", "").replace("=X", "") != pair.replace("_", "").replace("=X", ""):
                    continue
                wt = parse_time(w.get("timestamp") or w.get("ts") or "")
                if not wt or not close_t:
                    continue
                dt = abs((close_t - wt).total_seconds())
                if best_dt is None or dt < best_dt:
                    best_dt = dt
                    best = w
            if best and best_dt and best_dt < 7 * 24 * 3600:  # 7 天内
                tier = best.get("tier", "normal")
                d_skew = best.get("d_skew")
        tier = tier or "unknown"
        r2 = dict(r)
        r2["tier"] = tier
        r2["d_skew"] = d_skew
        joined.append(r2)
    return joined


def sl_hit_rate(records: List[Dict[str, Any]]) -> float:
    if not records:
        return 0.0
    sl = sum(1 for r in records if r.get("exit_reason") == "SL")
    return round(sl / len(records) * 100, 1)


def consecutive_sl_runs(records: List[Dict[str, Any]]) -> Dict[str, float]:
    """同一 profile 按 close_time 排序，统计连续 SL 游程长度分布"""
    sorted_r = sorted(records, key=lambda r: r.get("close_time", ""))
    runs: List[int] = []
    cur = 0
    for r in sorted_r:
        if r.get("exit_reason") == "SL":
            cur += 1
        else:
            if cur > 0:
                runs.append(cur)
            cur = 0
    if cur > 0:
        runs.append(cur)
    if not runs:
        return {"max_run": 0, "mean_run": 0.0, "run_count": 0}
    return {
        "max_run": max(runs),
        "mean_run": round(sum(runs) / len(runs), 2),
        "run_count": len(runs),
    }


def bidirectional_sl_events(records: List[Dict[str, Any]], window_hours: int = BIDIRECTIONAL_WINDOW_HOURS) -> int:
    """同 pair 在时间窗内先 BUY 后 SELL（或反之）且均 SL → 计 1 次双向扫损"""
    sl_records = [r for r in records if r.get("exit_reason") == "SL"]
    by_pair: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in sl_records:
        by_pair[r.get("instrument", "")].append(r)
    count = 0
    for pair, recs in by_pair.items():
        recs_sorted = sorted(recs, key=lambda r: r.get("close_time", ""))
        for i in range(len(recs_sorted)):
            for j in range(i + 1, len(recs_sorted)):
                ti = parse_time(recs_sorted[i].get("close_time", ""))
                tj = parse_time(recs_sorted[j].get("close_time", ""))
                if not ti or not tj:
                    continue
                if (tj - ti).total_seconds() > window_hours * 3600:
                    break
                di = recs_sorted[i].get("direction", "")
                dj = recs_sorted[j].get("direction", "")
                if di != dj:
                    count += 1
                    break  # 每笔最多计一次
    return count


def trade_frequency(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """单位时间开仓笔数 / 每 pair 每日笔数"""
    if not records:
        return {"trades_per_day": 0.0, "per_pair_per_day": {}}
    times = [parse_time(r.get("close_time", "")) for r in records]
    times = [t for t in times if t]
    if not times:
        return {"trades_per_day": 0.0, "per_pair_per_day": {}}
    span_days = max(1, (max(times) - min(times)).days + 1)
    per_pair: Dict[str, int] = defaultdict(int)
    for r in records:
        per_pair[r.get("instrument", "")] += 1
    per_pair_per_day = {p: round(c / span_days, 2) for p, c in per_pair.items()}
    return {
        "total_trades": len(records),
        "span_days": span_days,
        "trades_per_day": round(len(records) / span_days, 2),
        "per_pair_per_day": per_pair_per_day,
    }


def counterfactual_pnl(records: List[Dict[str, Any]], tier: str, wide_multiplier: float = 0.5) -> Dict[str, float]:
    """反事实：对 wide tier 时段降仓，对比实际 P&L"""
    wide = [r for r in records if r.get("tier") == tier]
    actual = sum(float(r.get("realized_pl", 0) or 0) for r in wide)
    cf = sum(float(r.get("realized_pl", 0) or 0) * wide_multiplier for r in wide)
    return {
        f"{tier}_actual_pl": round(actual, 2),
        f"{tier}_cf_{wide_multiplier}x_pl": round(cf, 2),
        f"{tier}_cf_diff": round(cf - actual, 2),
    }


def analyze(joined: List[Dict[str, Any]]) -> Dict[str, Any]:
    tiers = ["narrow", "normal", "wide", "extreme", "unknown"]
    by_tier: Dict[str, List[Dict[str, Any]]] = {t: [] for t in tiers}
    for r in joined:
        by_tier.setdefault(r.get("tier", "unknown"), []).append(r)

    report: Dict[str, Any] = {"total_joined": len(joined), "by_tier": {}}

    for tier in tiers:
        recs = by_tier.get(tier, [])
        if not recs:
            continue
        net_pl = round(sum(float(r.get("realized_pl", 0) or 0) for r in recs), 2)
        report["by_tier"][tier] = {
            "count": len(recs),
            "sl_hit_rate_pct": sl_hit_rate(recs),
            "consecutive_sl": consecutive_sl_runs(recs),
            "bidirectional_sl_events": bidirectional_sl_events(recs),
            "net_pl": net_pl,
            "avg_pl_per_trade": round(net_pl / len(recs), 2),
            "trade_frequency": trade_frequency(recs),
            "mfe_mae": "not_available（需 M1/M5 K 线离线计算）",
        }

    # 处置方案反事实（wide tier）
    if "wide" in report["by_tier"]:
        report["counterfactual"] = {}
        for mult in [0.25, 0.5]:
            report["counterfactual"].update(counterfactual_pnl(joined, "wide", mult))
        # 极端 skip（wide 全部不下单）
        wide_pl = report["by_tier"]["wide"]["net_pl"]
        report["counterfactual"]["wide_skip_pl"] = 0.0
        report["counterfactual"]["wide_skip_diff"] = round(-wide_pl, 2)

    # 失败条件判断：wide 与 normal 在关键指标上无显著差异 → 判别量无效
    fail = False
    reasons = []
    if "wide" in report["by_tier"] and "normal" in report["by_tier"]:
        w = report["by_tier"]["wide"]
        n = report["by_tier"]["normal"]
        if abs(w["sl_hit_rate_pct"] - n["sl_hit_rate_pct"]) < 5:
            fail = True
            reasons.append("SL 命中率差异 <5%")
        if w["consecutive_sl"]["max_run"] <= n["consecutive_sl"]["max_run"]:
            fail = True
            reasons.append("连续 SL max_run 未高于 normal")
        if w["bidirectional_sl_events"] <= n["bidirectional_sl_events"]:
            fail = True
            reasons.append("双向 SL 事件未高于 normal")
    report["verdict"] = {
        "discriminator_valid": not fail,
        "fail_reasons": reasons,
        "next_step": "回退改特征（已实现波动分位 / BB 宽度分位）" if fail else "判别有效，提交 Owner 评审阶梯降仓上线",
    }

    # D_skew 双轴分组（若可用）
    has_dskew = any(r.get("d_skew") is not None for r in joined)
    if has_dskew:
        high_atr_low_skew = [r for r in joined if r.get("tier") in ("wide", "extreme") and r.get("d_skew") is not None and float(r.get("d_skew")) < 0.3]
        high_atr_high_skew = [r for r in joined if r.get("tier") in ("wide", "extreme") and r.get("d_skew") is not None and float(r.get("d_skew")) >= 0.3]
        report["d_skew_axis"] = {
            "high_atr_low_skew_count": len(high_atr_low_skew),
            "high_atr_low_skew_sl_rate": sl_hit_rate(high_atr_low_skew),
            "high_atr_high_skew_count": len(high_atr_high_skew),
            "high_atr_high_skew_sl_rate": sl_hit_rate(high_atr_high_skew),
        }
    return report


def print_report(report: Dict[str, Any]) -> None:
    print("=" * 60)
    print("Wide-range Loss Clustering Analysis")
    print("=" * 60)
    print(f"Join 后总笔数: {report['total_joined']}")
    print("-" * 60)
    for tier, data in report.get("by_tier", {}).items():
        print(f"[{tier:8s}] n={data['count']:3d}  SL命中率={data['sl_hit_rate_pct']:5.1f}%  净P&L={data['net_pl']:+.2f}  均值={data['avg_pl_per_trade']:+.2f}")
        cs = data["consecutive_sl"]
        print(f"           连续SL: max_run={cs['max_run']} mean={cs['mean_run']}  双向SL事件={data['bidirectional_sl_events']}")
        tf = data["trade_frequency"]
        print(f"           交易频率: {tf['trades_per_day']} 笔/天")
    if "counterfactual" in report:
        print("-" * 60)
        cf = report["counterfactual"]
        print(f"反事实(wide tier): 实际P&L={cf.get('wide_actual_pl', 'N/A')}")
        print(f"  降仓0.25x: {cf.get('wide_cf_0.25x_pl', 'N/A')} (diff {cf.get('wide_cf_0.25x_diff', 'N/A')})")
        print(f"  降仓0.5x:  {cf.get('wide_cf_0.5x_pl', 'N/A')} (diff {cf.get('wide_cf_0.5x_diff', 'N/A')})")
        print(f"  极端skip: {cf.get('wide_skip_pl', 'N/A')} (diff {cf.get('wide_skip_diff', 'N/A')})")
    if "d_skew_axis" in report:
        print("-" * 60)
        ds = report["d_skew_axis"]
        print(f"D_skew 双轴: 高ATR低偏斜(宽幅震荡) SL率={ds['high_atr_low_skew_sl_rate']}% (n={ds['high_atr_low_skew_count']})")
        print(f"             高ATR高偏斜(单边趋势) SL率={ds['high_atr_high_skew_sl_rate']}% (n={ds['high_atr_high_skew_count']})")
    print("-" * 60)
    v = report["verdict"]
    print(f"判别量有效性: {'✅ 有效' if v['discriminator_valid'] else '❌ 无效'}")
    if v["fail_reasons"]:
        print(f"  失败原因: {'; '.join(v['fail_reasons'])}")
    print(f"  下一步: {v['next_step']}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--log-dir", default="logs")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    audit = load_jsonl(os.path.join(args.log_dir, "exit_audit_*.jsonl"))
    wide = load_jsonl(os.path.join(args.log_dir, "wide_range_shadow_*.jsonl"))
    if not audit:
        print("No exit_audit records found (需要 TASK-1 先产出)。")
        return
    if not wide:
        print("No wide_range_shadow records found。")
        return
    joined = join_audit_with_tier(audit, wide)
    report = analyze(joined)
    print_report(report)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\nReport saved to {args.out}")


if __name__ == "__main__":
    main()
