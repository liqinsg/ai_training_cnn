#!/usr/bin/env python3
"""
每日写入CSV — 按Profile分文件、自动去重、永久保存
调用方式: python fx_trade_to_csv.py [天数] [ProfileID]
示例: python fx_trade_to_csv.py 7
      python fx_trade_to_csv.py 30 101-003-ABC
"""
import sys
import os
import re
import csv
from datetime import datetime
from collections import OrderedDict

# 配置
CSV_DIR = "./trade_data"
FIELDS = [
    "profile_id",
    "trade_id",
    "pair",
    "closed_dt",
    "tx_id",
    "reason_raw",
    "cat",
    "type",
    "date",
    "hour",
]


def ensure_dir():
    os.makedirs(CSV_DIR, exist_ok=True)


def get_csv_path(profile_id):
    return os.path.join(CSV_DIR, f"fx_trades_{profile_id}.csv")


def parse_output(lines, filter_profile=None):
    """解析输出，返回 (profile_id, records)"""
    profile_id = None
    for line in lines[:5]:
        if line.strip().startswith("Account:"):
            profile_id = line.strip().split("Account:")[1].split("|")[0].strip()
            break
    if not profile_id:
        return None, []
    if filter_profile and profile_id != filter_profile:
        return None, []

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
            d["date"] = dt.strftime("%Y-%m-%d")
            d["hour"] = dt.hour
        except Exception:
            d["date"] = "unknown"
            d["hour"] = -1
        if "TAKE_PROFIT" in d["reason"]:
            cat = "TP"
        elif "STOP_LOSS" in d["reason"]:
            cat = "SL"
        else:
            cat = "CLOSE"
        records.append(
            {
                "profile_id": profile_id,
                "trade_id": d["tid"],
                "pair": d["pair"],
                "closed_dt": d["closed"],
                "tx_id": d["tx"],
                "reason_raw": d["reason"].strip(),
                "cat": cat,
                "type": d["type"].strip(),
                "date": d["date"],
                "hour": d["hour"],
            }
        )
    return profile_id, records


def load_existing_ids(csv_path):
    """读取已有trade_id，避免重复"""
    if not os.path.exists(csv_path):
        return set()
    ids = set()
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ids.add(row["trade_id"])
    return ids


def write_records(csv_path, records):
    """写入新记录（去重）"""
    existing = load_existing_ids(csv_path)
    new_records = [r for r in records if r["trade_id"] not in existing]
    if not new_records:
        return 0
    mode = "a" if os.path.exists(csv_path) else "w"
    with open(csv_path, mode, encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if mode == "w":
            writer.writeheader()
        writer.writerows(new_records)
    return len(new_records)


if __name__ == "__main__":
    days = sys.argv[1] if len(sys.argv) > 1 else "7"
    filter_profile = sys.argv[2] if len(sys.argv) > 2 else None
    lines = sys.stdin.read().splitlines()

    profile_id, records = parse_output(lines, filter_profile)
    if not profile_id:
        print("⚠️  未识别到账户编号或不匹配")
        sys.exit(0)

    ensure_dir()
    csv_path = get_csv_path(profile_id)
    added = write_records(csv_path, records)

    print(f"✅ Profile: {profile_id} | 新增: {added} 条 | 保存: {csv_path}")
