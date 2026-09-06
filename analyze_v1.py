#!/usr/bin/env python3
"""
fx_analyze_v1.py
Step1: 每日归因报表。回答3个问题：昨天赚了谁的钱？亏了谁的钱？谁的分数最准？
Usage: python analyze_v1.py --profile profile4 --date 2026-09-06
不填--date就默认昨天
"""
import pandas as pd
import argparse
from pathlib import Path
from datetime import datetime, timedelta, timezone


def load_today_csv(profile, date_str):
    base = Path(f"daily_results_{profile}")
    trade_path = base / f"{date_str}_trade_log.csv"
    signal_path = base / f"{date_str}_signal_log.csv"

    if not trade_path.exists():
        print(f"❌ 找不到 {trade_path}")
        return None, None
    trades = pd.read_csv(trade_path)
    signals = pd.read_csv(signal_path) if signal_path.exists() else pd.DataFrame()
    return trades, signals


def report_daily_pnl(trades):
    """报表1: 谁赚钱了"""
    print("\n========== REPORT 1: 昨日PNL归因 ==========")
    closed = trades[trades["exit_time"].notna()].copy()
    if closed.empty:
        print("昨日无平仓")
        return

    closed["profit_usd"] = pd.to_numeric(closed["profit_usd"], errors="coerce").fillna(
        0
    )
    total = closed["profit_usd"].sum()

    by_pair = (
        closed.groupby("pair")["profit_usd"]
        .agg(["sum", "count"])
        .sort_values("sum", ascending=False)
    )
    by_dir = closed.groupby("direction")["profit_usd"].sum()

    print(f"总PNL: ${total:.2f} | 共 {len(closed)} 单平仓")
    print("\n【按货币对】")
    print(by_pair.to_string())
    print("\n【按方向】")
    print(by_dir.to_string())


def report_feature_corr(trades):
    """报表2: 5个分数谁最准"""
    print("\n========== REPORT 2: 特征归因 ==========")
    closed = trades[trades["exit_time"].notna()].copy()
    if len(closed) < 5:
        print("样本<5，相关性不准。跳过")
        return

    for col in ["score_s", "score_r", "score_a", "score_x", "score_m", "score_final"]:
        closed[col] = pd.to_numeric(closed[col], errors="coerce")

    corr = (
        closed[
            [
                "score_s",
                "score_r",
                "score_a",
                "score_x",
                "score_m",
                "score_final",
                "profit_usd",
            ]
        ]
        .corr()["profit_usd"]
        .sort_values(ascending=False)
    )
    print("与最终profit_usd的相关性，越大越好:")
    print(corr.to_string())

    winner = corr.index[0]
    loser = corr.index[-1]
    print(f"\n结论: 最准的是 {winner} | 最坑的是 {loser}")


def report_gate_simulation(trades, signals):
    """报表3: 如果MIN_SCORE提高会怎样"""
    print("\n========== REPORT 3: 门槛模拟器 ==========")
    closed = trades[trades["exit_time"].notna()].copy()
    if closed.empty:
        return

    closed["profit_usd"] = pd.to_numeric(closed["profit_usd"], errors="coerce").fillna(
        0
    )
    closed["score_final"] = pd.to_numeric(closed["score_final"], errors="coerce")

    print("模拟不同MIN_SCORE下的PF")
    for gate in [20, 25, 30, 35, 40, 45]:
        df_gate = closed[closed["score_final"] >= gate]
        pnl = df_gate["profit_usd"].sum()
        cnt = len(df_gate)
        print(f"MIN_SCORE={gate}: 开 {cnt} 单 | PNL=${pnl:.2f}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="profile4")
    parser.add_argument("--date", default=None, help="YYYY-MM-DD. 默认昨天")
    args = parser.parse_args()

    if args.date is None:
        yday = datetime.now(timezone.utc) - timedelta(days=1)
        date_str = yday.strftime("%Y-%m-%d")
    else:
        date_str = args.date

    print(f"分析 Profile: {args.profile} | 日期: {date_str}")

    trades, signals = load_today_csv(args.profile, date_str)
    if trades is None:
        return

    report_daily_pnl(trades)
    report_feature_corr(trades)
    report_gate_simulation(trades, signals)

    print("\n========== DONE ==========")
    print("下一步: 根据REPORT2和3，手动改config.py里的W_和MIN_SCORE")


if __name__ == "__main__":
    main()
