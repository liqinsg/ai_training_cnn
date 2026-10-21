#!/usr/bin/env python3
"""
OANDA 交易记录提取 — 已平仓 + 当前持仓
用法:
  python fx_daily_report_v2.py [天数] [账户ID]
输出:
  ./trade_data/fx_trades_{账户ID}.csv   已平仓完整记录（含开仓时间）
  ./trade_data/fx_open_{账户ID}.csv      当前持仓
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
from oandapyV20.endpoints.positions import OpenPositions
from config_oanda import api, OANDA_ACCOUNT_ID_DEMO_2 as DEFAULT_ACCOUNT

# ===== 配置 =====
CSV_DIR = "./trade_data"
CLOSED_FIELDS = [
    "trade_id", "pair", "open_time", "close_time", "duration_min",
    "tx_id", "reason_raw", "category", "realized_pl", "date", "hour"
]
OPEN_FIELDS = [
    "instrument", "side", "units", "current_price",
    "open_time", "unrealized_pl", "take_profit", "stop_loss"
]

def ensure_dir():
    os.makedirs(CSV_DIR, exist_ok=True)

def get_csv_path(account_id):
    return os.path.join(CSV_DIR, f"fx_trades_{account_id}.csv")

def get_open_path(account_id):
    return os.path.join(CSV_DIR, f"fx_open_{account_id}.csv")

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

# ========== 1. 获取已平仓记录（含开仓时间） ==========
def get_closed_trades(account_id, days):
    hours = days * 24
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)

    resp = api.request(TradesList(account_id, params={"state": "CLOSED", "count": 500}))
    all_trades = resp.get("trades", [])

    results = []
    for t in all_trades:
        close_time_str = t.get("closeTime")
        open_time_str = t.get("openTime")  # ← 直接拿到开仓时间
        if not close_time_str or not open_time_str:
            continue
        close_dt = parse_time(close_time_str)
        if close_dt < cutoff:
            continue

        open_dt = parse_time(open_time_str)
        duration_min = round((close_dt - open_dt).total_seconds() / 60, 1)

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
            "open_time": open_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "close_time": close_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "duration_min": duration_min,
            "tx_id": tx_ids[0] if tx_ids else "",
            "reason_raw": reason_raw,
            "category": category,
            "realized_pl": float(t.get("realizedPL", 0.0)),
            "date": close_dt.strftime("%Y-%m-%d"),
            "hour": close_dt.hour,
        })

    results.sort(key=lambda x: x["close_time"], reverse=True)
    return results

# ========== 2. 获取当前持仓 ==========
def get_open_positions(account_id):
    resp = api.request(OpenPositions(account_id))
    positions = resp.get("positions", [])
    results = []
    for p in positions:
        long = p.get("long", {})
        short = p.get("short", {})
        if long and float(long.get("units", 0)) != 0:
            side, units = "LONG", long.get("units")
            price = long.get("price", "")
            open_time = long.get("openTime", "")
            up = float(long.get("unrealizedPL", 0.0))
            tp = long.get("takeProfitOrder", {}).get("price", "")
            sl = long.get("stopLossOrder", {}).get("price", "")
        elif short and float(short.get("units", 0)) != 0:
            side, units = "SHORT", short.get("units")
            price = short.get("price", "")
            open_time = short.get("openTime", "")
            up = float(short.get("unrealizedPL", 0.0))
            tp = short.get("takeProfitOrder", {}).get("price", "")
            sl = short.get("stopLossOrder", {}).get("price", "")
        else:
            continue
        if open_time:
            try:
                open_time = parse_time(open_time).strftime("%Y-%m-%d %H:%M:%S")
            except:
                pass
        results.append({
            "instrument": p.get("instrument"),
            "side": side,
            "units": units,
            "current_price": price,
            "open_time": open_time,
            "unrealized_pl": up,
            "take_profit": tp or "-",
            "stop_loss": sl or "-",
        })
    return results

# ========== 保存CSV ==========
def save_closed(records, account_id):
    ensure_dir()
    path = get_csv_path(account_id)
    existing_ids = set()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            existing_ids = {row["trade_id"] for row in csv.DictReader(f)}
    new = [r for r in records if r["trade_id"] not in existing_ids]
    if new:
        mode = "a" if os.path.exists(path) else "w"
        with open(path, mode, encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=CLOSED_FIELDS)
            if mode == "w": w.writeheader()
            w.writerows(new)
    return len(new), path

def save_open(records, account_id):
    ensure_dir()
    path = get_open_path(account_id)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=OPEN_FIELDS)
        w.writeheader()
        w.writerows(records)
    return len(records), path

# ========== 输出显示 ==========
def print_closed_list(records):
    print(f"\n{'='*110}")
    print(f"{'TRADE_ID':<10} {'PAIR':<12} {'OPEN_TIME':<19} → {'CLOSE_TIME':<19} "
          f"{'MIN':>6} {'CAT':<13} {'P/L':>10}  REASON")
    print(f"{'-'*110}")
    for r in records:
        print(f"{r['trade_id']:<10} {r['pair']:<12} {r['open_time']:<19} → "
              f"{r['close_time']:<19} {r['duration_min']:6.1f} {r['category']:<13} "
              f"{r['realized_pl']:>10.2f}  {r['reason_raw']}")
    print(f"{'='*110}")

def print_open_list(records):
    if not records:
        print("\n📭 当前无持仓")
        return
    print(f"\n{'='*95}")
    print(f"{'INSTRUMENT':<12} {'SIDE':<6} {'UNITS':>8} {'PRICE':>10} "
          f"{'UNREAL_P/L':>10} {'TP':>10} {'SL':>10}  OPEN_TIME")
    print(f"{'-'*95}")
    for r in records:
        print(f"{r['instrument']:<12} {r['side']:<6} {r['units']:>8} {r['current_price']:>10} "
              f"{r['unrealized_pl']:>+10.2f} {r['take_profit']:>10} {r['stop_loss']:>10}  {r['open_time']}")
    print(f"{'='*95}")

def print_summary(closed, added_closed, closed_path, open_cnt, open_path, days):
    total = len(closed)
    tp = sum(1 for r in closed if r["category"] == "TP")
    sl = sum(1 for r in closed if r["category"] == "SL")
    market = sum(1 for r in closed if r["category"] == "MARKET_CLOSE")
    pl_sum = sum(r["realized_pl"] for r in closed)
    avg_min = sum(r["duration_min"] for r in closed) / total if total else 0

    print(f"\n📋  最近 {days} 天 ｜ 已平仓: {total} 笔 (新增 {added_closed})")
    print(f"💰  净盈亏: {pl_sum:+.2f} ｜ TP: {tp} ｜ SL: {sl} ｜ 手动: {market}")
    print(f"⏱️  平均持仓: {avg_min:.1f} 分钟")
    print(f"📁  平仓记录: {closed_path}")
    print(f"💼  当前持仓: {open_cnt} 个 ｜ {open_path}")
    print()

# ========== 主入口 ==========
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OANDA交易全记录 — 已平仓+当前持仓")
    parser.add_argument("days", nargs="?", type=float, default=7.0, help="倒数N天 (默认7)")
    parser.add_argument("account", nargs="?", default=DEFAULT_ACCOUNT, help="账户ID")
    parser.add_argument("--account", "-a", dest="account_opt", help="指定账户ID")
    args = parser.parse_args()

    account_id = args.account_opt if args.account_opt else args.account
    days = args.days

    print(f"🔍 查询: {account_id} ｜ 最近 {days} 天")

    closed_records = get_closed_trades(account_id, days)
    added_closed, closed_path = save_closed(closed_records, account_id)

    open_records = get_open_positions(account_id)
    added_open, open_path = save_open(open_records, account_id)

    if closed_records:
        print_closed_list(closed_records)
    else:
        print("⚠️  未找到已平仓记录")

    print_open_list(open_records)
    print_summary(closed_records, added_closed, closed_path, added_open, open_path, days)