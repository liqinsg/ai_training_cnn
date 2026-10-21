#!/usr/bin/env python3
"""
OANDA 已平仓交易记录提取 + 保存CSV
用法:
  python fx_daily_report_v2.py [天数] [账户ID]
  python fx_daily_report_v2.py 7                         ← 默认账户，最近7天
  python fx_daily_report_v2.py 30 101-003-XXX           ← 指定账户+天数
输出:
  ./trade_data/fx_trades_{账户ID}.csv  完整交易记录（自动去重）
"""
import sys
import os
import csv
import argparse
from datetime import datetime, timedelta, timezone
from collections import defaultdict

# ===== OANDA API =====
from oandapyV20.endpoints.trades import TradesList
from oandapyV20.endpoints.transactions import TransactionDetails
from config_oanda import api, OANDA_ACCOUNT_ID_DEMO_2 as DEFAULT_ACCOUNT

# ===== 配置 =====
CSV_DIR = "./trade_data"
FIELDS = [
    "trade_id", "pair", "close_time", "tx_id",
    "reason_raw", "category", "realized_pl", "date", "hour"
]

def ensure_dir():
    os.makedirs(CSV_DIR, exist_ok=True)

def get_csv_path(account_id):
    return os.path.join(CSV_DIR, f"fx_trades_{account_id}.csv")

def parse_time(s):
    base, _, frac = s.rstrip("Z").partition(".")
    return datetime.fromisoformat(f"{base}.{frac[:6] or '0'}").replace(tzinfo=timezone.utc)

def classify_close(reason):
    if reason == "TAKE_PROFIT_ORDER":
        return "TP"
    if "STOP_LOSS" in reason:
        return "SL"
    if reason.startswith("MARKET_ORDER"):
        return "MARKET_CLOSE"
    return "OTHER"

def get_closed_trades(account_id, days):
    """获取完整交易记录"""
    hours = days * 24
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)

    resp = api.request(TradesList(account_id, params={"state": "CLOSED", "count": 500}))
    all_trades = resp.get("trades", [])

    results = []
    for t in all_trades:
        close_time_str = t.get("closeTime")
        if not close_time_str:
            continue
        close_dt = parse_time(close_time_str)
        if close_dt < cutoff:
            continue

        tx_ids = t.get("closingTransactionIDs", [])
        reason_raw = ""
        category = "OTHER"
        if tx_ids:
            tx_resp = api.request(TransactionDetails(account_id, str(tx_ids[0])))
            tx = tx_resp.get("transaction", {})
            reason_raw = tx.get("reason", "")
            category = classify_close(reason_raw)

        results.append({
            "trade_id": t.get("id"),
            "pair": t.get("instrument"),
            "close_time": close_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "tx_id": tx_ids[0] if tx_ids else "",
            "reason_raw": reason_raw,
            "category": category,
            "realized_pl": float(t.get("realizedPL", 0.0)),
            "date": close_dt.strftime("%Y-%m-%d"),
            "hour": close_dt.hour,
        })

    results.sort(key=lambda x: x["close_time"], reverse=True)
    return results

def save_to_csv(records, account_id):
    """保存完整记录，自动去重"""
    ensure_dir()
    path = get_csv_path(account_id)
    existing_ids = set()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            existing_ids = {row["trade_id"] for row in csv.DictReader(f)}

    new_records = [r for r in records if r["trade_id"] not in existing_ids]
    if new_records:
        mode = "a" if os.path.exists(path) else "w"
        with open(path, mode, encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            if mode == "w":
                writer.writeheader()
            writer.writerows(new_records)
    return len(new_records), path

def print_trades_list(records):
    """打印完整交易列表"""
    print(f"\n{'='*90}")
    print(f"{'TRADE_ID':<10} {'PAIR':<12} {'CLOSE_TIME':<19} {'CAT':<13} {'P/L':>10}  REASON")
    print(f"{'-'*90}")
    for r in records:
        print(f"{r['trade_id']:<10} {r['pair']:<12} {r['close_time']:<19} {r['category']:<13} {r['realized_pl']:>10.2f}  {r['reason_raw']}")
    print(f"{'='*90}")

def print_brief(records, added, csv_path, days):
    """简要统计放最后，不干扰主记录输出"""
    total = len(records)
    tp = sum(1 for r in records if r["category"] == "TP")
    sl = sum(1 for r in records if r["category"] == "SL")
    market = sum(1 for r in records if r["category"] == "MARKET_CLOSE")
    pl_sum = sum(r["realized_pl"] for r in records)

    print(f"\n📋  最近 {days} 天 ｜ 总计: {total} 笔 ｜ 新增: {added} 笔")
    print(f"💰  净盈亏: {pl_sum:+.2f} ｜ TP: {tp} ｜ SL: {sl} ｜ 手动: {market}")
    print(f"📁  文件: {csv_path}\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="提取OANDA已平仓交易记录")
    parser.add_argument("days", nargs="?", type=float, default=7.0, help="倒数N天 (默认7)")
    parser.add_argument("account", nargs="?", default=DEFAULT_ACCOUNT, help="账户ID")
    parser.add_argument("--account", "-a", dest="account_opt", help="指定账户ID")
    args = parser.parse_args()

    account_id = args.account_opt if args.account_opt else args.account
    days = args.days

    print(f"🔍 查询: {account_id} ｜ 最近 {days} 天")
    records = get_closed_trades(account_id, days)
    added, csv_path = save_to_csv(records, account_id)

    if not records:
        print("⚠️  未找到交易记录")
        sys.exit(0)

    print_trades_list(records)
    print_brief(records, added, csv_path, days)