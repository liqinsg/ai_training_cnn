# fx_daily_report.py
#!/usr/bin/env python3
"""
每日交易报告 — 每日运行一次，评估前一日/全周期表现
核心：区分「运气盈利」vs「稳定能力」，不绑定单一品种
输出：汇总、盈亏结构、品种质量、时间窗口、次日风控提示
"""
import sys
import re
from collections import defaultdict
from datetime import datetime, timedelta

# ========== 配置项（按你的账户微调） ==========
RISK_PER_TRAIT_PCT = 1.0  # 单笔最大风险 %
MAX_DAILY_DRAWDOWN_PCT = 3.0  # 单日亏损停手线 %
WINDOW_DAYS = 7  # 近期趋势窗口
# ==========================================


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
        m = pattern.search(line.strip())
        if not m:
            continue
        d = m.groupdict()
        try:
            dt = datetime.fromisoformat(d["closed"])
            d["dt"] = dt
            d["date"] = dt.strftime("%Y-%m-%d")
            d["hour"] = dt.hour
            d["weekday"] = dt.strftime("%a")
        except Exception:
            continue
        # 分类
        if "TAKE_PROFIT" in d["reason"]:
            d["cat"] = "TP"
        elif "STOP_LOSS" in d["reason"]:
            d["cat"] = "SL"
        else:
            d["cat"] = "CLOSE"
        records.append(d)
    if not records:
        print("⚠️  未解析到有效交易记录，请核对 fx_trade_closed_status.py 输出格式")
        sys.exit(1)
    return records


def analyze(records):
    latest_date = max(r["dt"] for r in records).date()
    window_start = latest_date - timedelta(days=WINDOW_DAYS)

    # 全周期 + 近7日双统计
    stats = {
        "all": calc_stats(records, "全周期"),
        "window": calc_stats(
            [r for r in records if r["dt"].date() > window_start], f"近{WINDOW_DAYS}日"
        ),
        "latest": calc_stats(
            [r for r in records if r["date"] == latest_date.strftime("%Y-%m-%d")],
            "昨日",
        ),
    }
    return stats, latest_date


def calc_stats(records, label=""):
    if not records:
        return {"label": label, "total": 0}
    total = len(records)
    by_cat = defaultdict(int)
    by_pair = defaultdict(lambda: defaultdict(int))
    by_date = defaultdict(lambda: defaultdict(int))
    by_hour = defaultdict(int)

    for r in records:
        cat = r["cat"]
        pair = r["pair"]
        date = r["date"]
        hour = r["hour"]
        by_cat[cat] += 1
        by_pair[pair][cat] += 1
        by_date[date][cat] += 1
        by_hour[hour] += 1

    TP = by_cat.get("TP", 0)
    SL = by_cat.get("SL", 0)
    CLOSE = by_cat.get("CLOSE", 0)
    win_rate = TP / total * 100 if total else 0
    hold_quality = TP / (TP + CLOSE) * 100 if (TP + CLOSE) else 0

    return {
        "label": label,
        "total": total,
        "TP": TP,
        "SL": SL,
        "CLOSE": CLOSE,
        "win_rate": win_rate,
        "hold_quality": hold_quality,  # 该拿住的单子里真正吃到TP的比例
        "by_pair": dict(by_pair),
        "by_date": dict(by_date),
        "by_hour": dict(by_hour),
        "sl_excess": SL - TP,  # 止损超出止盈次数
    }


def print_section(title):
    width = 62
    print(f"\n{'='*width}")
    print(f"  {title}")
    print(f"{'='*width}")


def print_stats_block(s, show_details=True):
    if s["total"] == 0:
        print("  暂无数据")
        return
    TP, SL, CLOSE = s["TP"], s["SL"], s["CLOSE"]
    total = s["total"]
    print(
        f"  总成交: {total:3d}  |  ✅ TP: {TP:3d} ({TP/total*100:4.1f}%)  "
        f"❌ SL: {SL:3d} ({SL/total*100:4.1f}%)  ⚠️ 提前平: {CLOSE:3d} ({CLOSE/total*100:4.1f}%)"
    )
    print(
        f"  胜率(TP/总): {s['win_rate']:4.1f}%  |  持仓质量(TP/可盈利单): {s['hold_quality']:4.1f}%"
    )
    if s["sl_excess"] > 0:
        print(f"  🔴 止损超止盈: {s['sl_excess']} 单")
    elif s["sl_excess"] < 0:
        print(f"  🟢 止盈超止损: {abs(s['sl_excess'])} 单")

    if not show_details:
        return

    # 品种质量排名
    print("\n  品种质量 (TP/SL/提前平 | 持仓质量%)")
    pair_rpt = []
    for p, v in s["by_pair"].items():
        pt = v.get("TP", 0)
        sl = v.get("SL", 0)
        cl = v.get("CLOSE", 0)
        denom = pt + cl
        qual = pt / denom * 100 if denom else 0
        trend = "🟢" if qual >= 40 and pt >= sl else "🟡" if qual >= 25 else "🔴"
        pair_rpt.append((-qual, p, pt, sl, cl, qual, trend))
    for qual, p, pt, sl, cl, q, tr in sorted(pair_rpt):
        print(f"  {tr} {p:12s} | {pt:3d} / {sl:3d} / {cl:3d} | {q:4.1f}%")

    # 时段分布
    print("\n  活跃时段 (UTC 小时 | 成交数)")
    peak_hours = sorted(s["by_hour"].items(), key=lambda x: -x[1])[:5]
    for h, cnt in peak_hours:
        print(f"    {h:02d}:00–{h+1:02d}:00  | {cnt:3d} 单")


def print_alert(latest, window):
    print_section("🚨 今日风控提示")
    alerts = []
    advises = []

    if latest["total"] == 0:
        alerts.append("昨日无交易记录")
    else:
        if latest["CLOSE"] / latest["total"] > 0.5:
            alerts.append(
                f"提前平仓占比 {latest['CLOSE']/latest['total']*100:.1f}% > 50% — 拿不住盈利，严格执行分级出场"
            )
        if latest["SL"] > latest["TP"]:
            alerts.append(
                f"昨日止损 {latest['SL']} > 止盈 {latest['TP']} — 入场偏多/质量下降，降仓或观望"
            )

    if window["hold_quality"] < 40:
        alerts.append(
            f"近7日持仓质量 {window['hold_quality']:.1f}% < 40% — 整体信心不足，保本上移执行不坚决"
        )
    if window["sl_excess"] > 3:
        alerts.append(
            f"近7日止损累计超出止盈 {window['sl_excess']} 单 — 趋势转震荡/策略不匹配，减少开仓频率"
        )

    if not alerts:
        advises.append("🟢 整体状态稳定，维持现有规则")
    else:
        for a in alerts:
            print(f"  🔴 {a}")

    print("\n  📌 今日执行标准:")
    print("    1. 单笔风险 ≤ 1% 净值")
    print("    2. TP1=1:1 平 30–50%，止损上移到入场价（保本）")
    print("    3. SL后 24h 不重开同品种；连续2笔SL → 休息2h")
    print("    4. 单日开仓 ≤ 6 笔；亏损 ≥ 3% → 停手复盘")
    print("    5. 不绑定固定品种 → 优先选近7日「持仓质量 ≥ 40%」的品种做")

    for a in advises:
        print(f"\n  {a}")


if __name__ == "__main__":
    lines = sys.stdin.read().splitlines()
    records = parse_records(lines)
    stats, latest_date = analyze(records)

    print(f"\n{'#'*62}")
    print(
        f"#  每日交易报告 | 生成日期: {datetime.now().strftime('%Y-%m-%d %H:%M UTC+8')}"
    )
    print(f"#  数据截止: {latest_date} | 窗口: 近{WINDOW_DAYS}日")
    print(f"{'#'*62}")

    print_section("一、昨日表现")
    print_stats_block(stats["latest"])

    print_section(f"二、近{WINDOW_DAYS}日趋势（核心参考）")
    print_stats_block(stats["window"])

    print_section("三、全周期基准")
    print_stats_block(stats["all"], show_details=False)

    print_alert(stats["latest"], stats["window"])

    print(f"\n{'='*62}\n")
