# fx_trade_closed_status-v2.py
#!/usr/bin/env python3
import sys
import re
import argparse
from collections import defaultdict
from datetime import datetime

# --------------------------
# 解析交易记录
# --------------------------
def parse_records(lines):
    pattern = re.compile(
        r"(?P<tid>\d+)\s+"
        r"(?P<pair>[A-Z]+_[A-Z]+)\s+"
        r"closed=(?P<closed>[^\s]+)\s+"
        r"tx=(?P<tx>\d+)\s+"
        r"reason=(?P<reason>[^->]+)\s+->\s+(?P<type>.+)"
    )
    records = []
    for line in lines:
        m = pattern.search(line)
        if not m:
            continue
        d = m.groupdict()
        try:
            dt = datetime.fromisoformat(d["closed"])
            d["dt"] = dt
            d["date"] = dt.strftime("%Y-%m-%d")
            d["hour"] = dt.hour
        except Exception:
            d["dt"] = None
            d["date"] = "unknown"
        if "TAKE_PROFIT" in d["reason"]:
            d["cat"] = "TP"
        elif "STOP_LOSS" in d["reason"]:
            d["cat"] = "SL"
        else:
            d["cat"] = "NON_TP"
        records.append(d)
    return records

# --------------------------
# 统计
# --------------------------
def analyze(records):
    total = len(records)
    by_cat = defaultdict(int)
    by_pair = defaultdict(lambda: defaultdict(int))
    by_date = defaultdict(lambda: defaultdict(int))
    pair_list = set()
    date_list = set()

    for r in records:
        cat = r["cat"]
        pair = r["pair"]
        date = r["date"]
        by_cat[cat] += 1
        by_pair[pair][cat] += 1
        by_date[date][cat] += 1
        pair_list.add(pair)
        date_list.add(date)

    return {
        "total": total,
        "by_cat": dict(by_cat),
        "by_pair": dict(by_pair),
        "by_date": dict(by_date),
        "pairs": sorted(pair_list),
        "dates": sorted(date_list),
    }

# --------------------------
# 输出报告
# --------------------------
def print_report(stats, profile=None):
    TP = stats["by_cat"].get("TP", 0)
    SL = stats["by_cat"].get("SL", 0)
    NON = stats["by_cat"].get("NON_TP", 0)
    total = stats["total"]

    header = f"📊 汇总报告  总数: {total}"
    if profile:
        header = f"📊 汇总报告 | Profile: {profile} | 总数: {total}"

    print("=" * 60)
    print(header)
    print("-" * 60)
    print(f"✅ TP 止盈:     {TP:3d}  {TP/total*100:5.1f}%")
    print(f"❌ SL 止损:     {SL:3d}  {SL/total*100:5.1f}%")
    print(f"⚠️  NON_TP 提前: {NON:3d}  {NON/total*100:5.1f}%")
    print("=" * 60)

    print("\n📈 品种明细 (TP / SL / NON_TP | TP%)")
    print("-" * 60)
    pair_rpt = []
    for p, v in stats["by_pair"].items():
        pt = v.get("TP", 0)
        sl = v.get("SL", 0)
        no = v.get("NON_TP", 0)
        sub = pt + sl + no
        pct = pt / sub * 100 if sub else 0
        pair_rpt.append((-pct, -pt, sl, p, pt, sl, no, pct))
    for _, _, sl, p, pt, slv, no, pct in sorted(pair_rpt):
        flag = "🔴" if slv > pt or pt == 0 else "🟢" if pct >= 30 else "🟡"
        print(f"{flag} {p:12s} | {pt:3d} / {slv:3d} / {no:3d} | {pct:5.1f}%")

    print("\n📅 每日趋势 (TP/SL/NON_TP | TP%)")
    print("-" * 60)
    for d in stats["dates"]:
        v = stats["by_date"][d]
        pt = v.get("TP", 0)
        sl = v.get("SL", 0)
        no = v.get("NON_TP", 0)
        sub = pt + sl + no
        pct = pt / sub * 100 if sub else 0
        trend = "⬆" if pct >= 30 else "⬇" if sl > pt else "➖"
        print(f"{trend} {d} | TP:{pt:3d} SL:{sl:3d} NON:{no:3d} | {pct:5.1f}%")

    print("\n🚨 异常与建议")
    print("-" * 60)
    if NON / total > 0.5:
        print("🔴 提前平仓占比 >50%：拿不住盈利，需严格执行分级止盈")
    if SL > TP:
        print("🔴 止损次数 > 止盈次数：入场质量偏低，严控开仓数量+品种")
    bad_pairs = [
        p for p, v in stats["by_pair"].items()
        if v.get("SL", 0) > v.get("TP", 0) or v.get("TP", 0) == 0
    ]
    if bad_pairs:
        print(f"🔴 建议暂停品种: {', '.join(bad_pairs)}")
    good_pairs = [
        p for p, v in stats["by_pair"].items()
        if v.get("TP", 0) >= 3 and v.get("SL", 0) <= v.get("TP", 0)
    ]
    if good_pairs:
        print(f"🟢 优先主力品种: {', '.join(good_pairs)}")
    print("\n执行规则:")
    print("  ✅ 优先选近期状态好的品种")
    print("  ✅ 单笔风险 ≤1% | TP1=1:1平30-50% 保本上移入场价")
    print("  ✅ SL后24h不重开同品种 | 日开仓≤6笔 亏3%停手")

# --------------------------
# 入口
# --------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FX交易报告")
    parser.add_argument("--profile", "-p", help="指定Profile编号，显示在报告头部")
    parser.add_argument("--input", "-i", help="从文件读取而非管道")
    parser.add_argument("--date-from", "-f", help="起始日期 YYYY-MM-DD")
    parser.add_argument("--date-to", "-t", help="结束日期 YYYY-MM-DD")
    args = parser.parse_args()

    # 读取数据源
    if args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    else:
        lines = sys.stdin.read().splitlines()

    records = parse_records(lines)

    # 日期过滤
    if args.date_from or args.date_to:
        filtered = []
        for r in records:
            d = r["date"]
            if args.date_from and d < args.date_from:
                continue
            if args.date_to and d > args.date_to:
                continue
            filtered.append(r)
        records = filtered

    if not records:
        print("未解析到交易记录，请确认输出格式或日期范围")
        sys.exit(1)

    stats = analyze(records)
    print_report(stats, profile=args.profile)