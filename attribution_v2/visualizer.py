#!/usr/bin/env python3
"""
Attribution V2 — Visualizer + Dashboard JSON Exporter
Generates PNG charts, HTML report, AND machine-readable JSON summary.
SOLE SOURCE OF TRUTH: batch_backtest.SUMMARY
"""
from datetime import datetime, timezone
from pathlib import Path
import json
import sys

# ─── Paths ──────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
REPORT_DIR = BASE_DIR / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

# ─── Matplotlib ─────────────────────────────────────────────────
try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    HAS_MPL = True
except ImportError:
    HAS_MPL = False
    print("⚠️  Matplotlib not available — skipping plots")


# ================================================================
# LOAD LIVE DATA — single source of truth from batch_backtest
# ================================================================
def load_results_from_backtest():
    """Import REAL computed results from batch_backtest.py — auto-runs if needed"""
    sys.path.insert(0, str(BASE_DIR))
    try:
        import batch_backtest as bt

        if bt.SUMMARY is None:
            print("⚠️  SUMMARY is None — running batch_backtest pipeline now...")
            bt.run_and_build_summary()

        s = bt.SUMMARY
        print(
            f"🔗 Loaded live data: {s['total_candidates']} candidates, {s['degraded_count']} degraded"
        )
        print(
            f"   PF-A PASS: {s['profiles']['PF-A']['pass_pct']}%  "
            f"PF-D PASS: {s['profiles']['PF-D']['pass_pct']}%"
        )

        return {
            "total_candidates": s["total_candidates"],
            "degraded_count": s["degraded_count"],
            "profiles": s["profiles"],
            "score_data": s["score_data"],
        }

    except Exception as e:
        print(f"❌ Cannot load live data: {e}")
        sys.exit(1)


# ─── Load ONCE at import time — fail fast if missing ────────────
RESULTS = load_results_from_backtest()


# ─── Plot 1: Pass/Watch/Reject Bar Chart ────────────────────────
def plot_pass_rates():
    if not HAS_MPL:
        return None
    fig, ax = plt.subplots(figsize=(10, 6))
    labels = ["PF-A\nTrend", "PF-B\nBalanced", "PF-C\nModel", "PF-D\nStructure"]
    pass_rates = [RESULTS["profiles"][p]["pass_pct"] for p in RESULTS["profiles"]]
    watch_rates = [RESULTS["profiles"][p]["watch_pct"] for p in RESULTS["profiles"]]
    reject_rates = [RESULTS["profiles"][p]["reject_pct"] for p in RESULTS["profiles"]]

    x = range(len(labels))
    w = 0.75

    ax.bar(x, pass_rates, w, label="PASS", color="#2ecc71")
    ax.bar(x, watch_rates, w, bottom=pass_rates, label="WATCH", color="#f39c12")
    ax.bar(
        x,
        reject_rates,
        w,
        bottom=[a + b for a, b in zip(pass_rates, watch_rates)],
        label="REJECT",
        color="#e74c3c",
    )

    for i, (pa, wa, re) in enumerate(zip(pass_rates, watch_rates, reject_rates)):
        ax.text(
            i,
            pa / 2,
            f"{pa}%",
            ha="center",
            va="center",
            color="white",
            fontweight="bold",
        )
        ax.text(
            i,
            pa + wa / 2,
            f"{wa}%",
            ha="center",
            va="center",
            color="white",
            fontweight="bold",
        )
        ax.text(
            i,
            pa + wa + re / 2,
            f"{re}%",
            ha="center",
            va="center",
            color="white",
            fontweight="bold",
        )

    ax.set_ylabel("Rate (%)")
    ax.set_title("4-Profile Decision Distribution — Attribution V2")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.legend(loc="upper right")
    ax.set_ylim(0, 100)

    path = REPORT_DIR / "profile_pass_rates.png"
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close()
    print(f"✅ Saved: {path}")
    return str(path)


# ─── Plot 2: Score Boxplot ──────────────────────────────────────
def plot_score_box():
    if not HAS_MPL:
        return None
    fig, ax = plt.subplots(figsize=(8, 6))
    data = RESULTS["score_data"]
    bp = ax.boxplot(
        data, tick_labels=["PF-A", "PF-B", "PF-C", "PF-D"], patch_artist=True
    )

    colors = ["#27ae60", "#3498db", "#9b59b6", "#e67e22"]
    for box, c in zip(bp["boxes"], colors):
        box.set(facecolor=c, alpha=0.7)

    ax.set_ylabel("Score")
    ax.set_title("Score Distribution by Profile")

    path = REPORT_DIR / "score_boxplot.png"
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close()
    print(f"✅ Saved: {path}")
    return str(path)


# ─── Plot 3: Signal Quality Pie ─────────────────────────────────
def plot_signal_quality():
    if not HAS_MPL:
        return None
    total = RESULTS["total_candidates"]
    degraded = RESULTS["degraded_count"]
    valid = total - degraded
    valid_pct = round(valid / total * 100, 1) if total > 0 else 0.0
    deg_pct = round(degraded / total * 100, 1) if total > 0 else 0.0

    fig, ax = plt.subplots(figsize=(7, 7))
    ax.pie(
        [valid, degraded],
        labels=[
            f"Valid Signal\n({valid}, {valid_pct}%)",
            f"Degraded/Neutral\n({degraded}, {deg_pct}%)",
        ],
        colors=["#3498db", "#bdc3c7"],
        autopct="%1.1f%%",
        startangle=90,
    )
    ax.set_title(f"Signal Quality — {total} Candidates")

    path = REPORT_DIR / "signal_quality.png"
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close()
    print(f"✅ Saved: {path}")
    return str(path)


# ─── Generate JSON Summary ──────────────────────────────────────
def export_json_summary():
    """Write machine-readable summary for dashboard live updates"""
    total = RESULTS["total_candidates"]
    degraded = RESULTS["degraded_count"]
    valid_pct = round((total - degraded) / total * 100, 1) if total > 0 else 0.0

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generated_local": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_candidates": total,
        "degraded_count": degraded,
        "valid_pct": valid_pct,
        "profiles": RESULTS["profiles"],
    }

    out_path = REPORT_DIR / "report_latest.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"✅ JSON summary: {out_path}")
    return out_path


# ─── Generate HTML Report ──────────────────────────────────────
def generate_html_report():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = REPORT_DIR / f"report_{ts}.html"
    latest_path = REPORT_DIR / "latest.html"

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>Attribution V2 Report — {ts}</title>
  <style>
    body {{ font-family: -apple-system, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background: #f5f6f7; }}
    h1 {{ color: #2c3e50; text-align: center; }}
    .meta {{ text-align: center; color: #7f8c8d; margin-bottom: 30px; }}
    .card {{ background: white; border-radius: 12px; padding: 20px; margin-bottom: 25px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
    img {{ width: 100%; height: auto; border-radius: 6px; }}
    .footer {{ text-align: center; margin-top: 30px; color: #95a5a6; font-size: 0.9em; }}
  </style>
</head>
<body>
  <h1>📊 Attribution V2 — 4-Profile Report</h1>
  <p class="meta">生成时间: {ts} · 共 {RESULTS['total_candidates']} 条信号</p>

  <div class="card">
    <h2>📈 决策分布 PASS/WATCH/REJECT</h2>
    <img src="profile_pass_rates.png?t={ts}" alt="Pass Rates">
  </div>

  <div class="card">
    <h2>📊 分数分布箱线图</h2>
    <img src="score_boxplot.png?t={ts}" alt="Score Distribution">
  </div>

  <div class="card">
    <h2>🥧 信号质量诊断</h2>
    <img src="signal_quality.png?t={ts}" alt="Signal Quality">
  </div>

  <div class="footer">
    JSON 数据: <a href="report_latest.json">report_latest.json</a>
  </div>
</body>
</html>
"""

    report_path.write_text(html, encoding="utf-8")
    latest_path.write_text(html, encoding="utf-8")
    print(f"📄 Report: {report_path}")
    print(f"📄 Latest: {latest_path}")
    return str(report_path)


# ================================================================
# MAIN ENTRY POINT
# ================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("🎨 Attribution V2 — Generating Visuals")
    print("=" * 60)

    plot_pass_rates()
    plot_score_box()
    plot_signal_quality()
    export_json_summary()
    generate_html_report()

    print("\n✅ All outputs ready!")