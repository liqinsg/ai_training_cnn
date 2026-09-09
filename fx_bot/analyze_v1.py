#!/usr/bin/env python3
"""
FX归因分析 — 按货币对独立文件（无日期）
Usage:
  python analyze_v1.py --profile profile2
  python analyze_v1.py --profile profile2 --pair usdjpy
"""
import pandas as pd
import argparse
from pathlib import Path


def normalize_columns(df):
    """Map CSV actual columns to the canonical column names used by analysis"""
    col_map = {
        "timestamp": "exit_time",
        "instrument": "pair",
        "pl": "profit_usd",
        # open_time 可能也有，不过暂不需要
    }
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

    # pair 列归一化: USD_JPY -> usdjpy
    if "pair" in df.columns:
        df["pair"] = df["pair"].astype(str).str.replace("_", "", regex=False).str.lower()

    return df


def load_all_trades(profile, pair_filter=None):
    """Automatically scan daily_results_*/trade_log_*.csv and merge all trades"""
    base = Path(f"daily_results_{profile}")
    if not base.exists():
        print(f"❌ Directory not found: {base}/")
        return pd.DataFrame()

    # Scan all pair files
    pattern = f"trade_log_{pair_filter}.csv" if pair_filter else "trade_log_*.csv"

    all_dfs = []
    for f in sorted(base.glob(pattern)):
        print(f"✅ Loading: {f.name}")
        df = pd.read_csv(f)
        df = normalize_columns(df)
        df["source_file"] = f.stem  # Mark source file
        all_dfs.append(df)

    if not all_dfs:
        print("❌ No trade logs found")
        return pd.DataFrame()

    return pd.concat(all_dfs, ignore_index=True)


def report_daily_pnl(trades):
    """PnL attribution by currency pair and direction"""
    print("\n" + "=" * 60)
    print("📊 PnL Attribution (Full History)")
    print("=" * 60)

    closed = trades[trades["exit_time"].notna()].copy()
    if closed.empty:
        print("ℹ️ No closed trades available")
        return

    closed["profit_usd"] = pd.to_numeric(closed["profit_usd"], errors="coerce").fillna(0)
    total = closed["profit_usd"].sum()

    by_pair = (
        closed.groupby("pair")["profit_usd"]
        .agg(["sum", "count"])
        .sort_values("sum", ascending=False)
    )
    by_dir = closed.groupby("direction")["profit_usd"].sum()

    print(f"💰 Total PnL: ${total:.2f} | Total Closed Trades: {len(closed)}")

    print("\n[By Currency Pair]")
    print(by_pair.to_string(float_format="%.2f"))

    print("\n[By Direction]")
    print(by_dir.to_string(float_format="%.2f"))


def report_feature_corr(trades):
    """Score correlation analysis"""
    print("\n" + "=" * 60)
    print("🎯 Score Correlation Analysis (Closer to 1 = Better)")
    print("=" * 60)

    closed = trades[trades["exit_time"].notna()].copy()
    if len(closed) < 5:
        print(f"⚠️ Sample size is only {len(closed)} trades, less than 5. Correlation is unreliable. Skipping.")
        return

    score_cols = [
        "score_s",
        "score_r",
        "score_a",
        "score_x",
        "score_m",
        "score_final",
    ]

    available = [c for c in score_cols if c in closed.columns]
    if not available:
        print("⚠️ No score columns available for analysis. Skipping.")
        return

    for col in available:
        closed[col] = pd.to_numeric(closed[col], errors="coerce")

    closed["profit_usd"] = pd.to_numeric(
        closed["profit_usd"], errors="coerce"
    ).fillna(0)

    corr = (
        closed[available + ["profit_usd"]]
        .corr()["profit_usd"]
        .drop("profit_usd")
        .sort_values(ascending=False)
    )

    print("Correlation with Profit:")
    print(corr.to_string(float_format="%.3f"))

    if len(corr) >= 2:
        print(
            f"\n🏆 Best Predictor: {corr.index[0]} | ⚠️ Worst Predictor: {corr.index[-1]}"
        )


def report_gate_simulation(trades):
    """MIN_SCORE threshold simulator"""
    print("\n" + "=" * 60)
    print("🔬 MIN_SCORE Threshold Simulator")
    print("=" * 60)

    closed = trades[trades["exit_time"].notna()].copy()

    if closed.empty or "score_final" not in closed.columns:
        print("ℹ️ No valid data available. Skipping.")
        return

    closed["profit_usd"] = pd.to_numeric(
        closed["profit_usd"], errors="coerce"
    ).fillna(0)

    closed["score_final"] = pd.to_numeric(
        closed["score_final"], errors="coerce"
    )

    print(f"{'Threshold':>10} | {'Trades':>6} | {'PnL (USD)':>12}")
    print("-" * 36)

    for gate in [20, 25, 30, 35, 40, 45]:
        df_gate = closed[closed["score_final"] >= gate]
        pnl = df_gate["profit_usd"].sum()
        cnt = len(df_gate)

        flag = " ✅" if pnl > 0 else " ❌"
        print(f"MIN_{gate:02d} | {cnt:6d} | ${pnl:+11.2f}{flag}")


def report_reason_groups(trades):
    """按 reason 关键词分组统计盈亏 — 看哪类策略赚最多

    Gracefully skips if `reason` column is missing (old CSV backward compat).
    """
    print("\n" + "=" * 60)
    print("🏷️  Strategy Attribution by Reason Keywords")
    print("=" * 60)

    if "reason" not in trades.columns:
        print("⚠️  No 'reason' column in trades — signal layer not connected yet. Skipping.")
        return

    # exit_time 由 normalize_columns 从 timestamp 映射而来；过滤 closed trades
    closed = trades[trades["exit_time"].notna()].copy()
    if closed.empty:
        print("ℹ️ No closed trades — skipping.")
        return

    # profit_usd 由 normalize_columns 从 pl 映射而来，已是 numeric
    closed["profit_usd"] = pd.to_numeric(closed["profit_usd"], errors="coerce").fillna(0)
    closed["reason"] = closed["reason"].fillna("(no reason)")

    # 按 reason 原文分组 — 每条 reason 都是独立的一行
    grouped = (
        closed.groupby("reason")
        .agg(
            trades=("reason", "count"),
            pnl=("profit_usd", "sum"),
            win_rate=("profit_usd", lambda x: (x > 0).mean() * 100),
            avg_score=("score_final", lambda s: pd.to_numeric(s, errors="coerce").mean() if "score_final" in closed.columns else float("nan")),
        )
        .sort_values("pnl", ascending=False)
    )

    print(f"\n📋 Breakdown by distinct reason ({len(grouped)} groups):")
    print(f"{'Reason':<40} | {'Trades':>6} | {'PnL':>10} | {'Win%':>7} | {'AvgScore':>9}")
    print("-" * 82)
    for reason, row in grouped.iterrows():
        avg_score_str = f"{row['avg_score']:.1f}" if pd.notna(row['avg_score']) else "   -   "
        pnl_icon = "✅" if row['pnl'] > 0 else ("❌" if row['pnl'] < 0 else "—")
        reason_display = (reason[:38] + "..") if len(reason) > 40 else reason
        print(f"{reason_display:<40} | {row['trades']:>6} | ${row['pnl']:>+9.2f} | {row['win_rate']:>6.1f}% | {avg_score_str:>9} {pnl_icon}")


def main():
    parser = argparse.ArgumentParser(
        description="FX Historical Attribution Analysis"
    )

    parser.add_argument(
        "--profile",
        default="profile2",
        help="Profile name"
    )

    parser.add_argument(
        "--pair",
        default=None,
        help="Analyze only one currency pair: usdjpy / eurusd ..."
    )

    args = parser.parse_args()

    print(f"\n📈 FX Attribution Analysis - Profile: {args.profile}")

    if args.pair:
        print(f"🎯 Currency Pair Filter: {args.pair}")

    trades = load_all_trades(args.profile, args.pair)

    if trades.empty:
        return

    report_daily_pnl(trades)
    report_reason_groups(trades)          # ✅ 新增：按策略理由分组
    report_feature_corr(trades)
    report_gate_simulation(trades)

    print("\n" + "=" * 60)
    print("✅ Analysis Complete!")
    print("💡 Next Step: Adjust config.py weights and MIN_SCORE based on the report")
    print("=" * 60)


if __name__ == "__main__":
    main()