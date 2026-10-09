#!/usr/bin/env python3
"""
Demo: Same candidate → Run all 4 profiles → Print results → Write logs
Observation mode only — never touches execution.
Zero dependency: works from any directory, no env vars needed.
"""

import sys
from pathlib import Path

# ── Auto-resolve project root — works everywhere ──
# Go up TWO levels from examples/ → project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import json
from profile_runner import run_all_profiles
from profile_logger import write_all


def main():
    print("=" * 70)
    print("📊 ATTRIBUTION V2 — 4 Profiles Demo")
    print("=" * 70)

    # ── Test Candidate ──
    candidate = {
        "symbol": "USD/JPY",
        "candidate_direction": "BUY",
        "trend_raw": +1,
        "location_raw": +1,
        "xgb_p_up": 0.75,
        "mc_p_up": 0.65,
    }

    print(f"\n📈 Candidate: {candidate['symbol']} {candidate['candidate_direction']}")
    print(f"   Trend: {candidate['trend_raw']:+d} | Location: {candidate['location_raw']:+d}")
    print(f"   XGB P(up): {candidate['xgb_p_up']:.2f} | MC P(up): {candidate['mc_p_up']:.2f}")
    print("─" * 70)

    # ── Run All 4 Profiles ──
    results = run_all_profiles(**candidate)

    # ── Print Summary Table ──
    print(f"\n{'Profile':<8} {'Score':>8} {'Action':<8} {'Primary Driver':<16} {'Sensitive Factors'}")
    print("-" * 70)

    for pid in ["PF-A", "PF-B", "PF-C", "PF-D"]:
        rec = results[pid]
        score = rec["decision"]["rel_score"]
        action = rec["decision"]["action"]
        driver = rec["attribution"]["primary_driver"] or "—"
        sensitive = rec["attribution"]["decision_sensitive_factors"]
        sens_str = ", ".join(sensitive) if sensitive else "—"

        print(f"{pid:<8} {score:>8.4f}  {action:<8} {driver:<16} {sens_str}")

    # ── Write Logs ──
    print("\n" + "─" * 70)
    written = write_all(results)
    print(f"✅ Logs written to: {PROJECT_ROOT}/logs/")
    for pid, size in written.items():
        print(f"   {pid}: {pid.lower()}/YYYY-MM-DD.jsonl  ({size} bytes)")

    # ── Cross-Profile Comparison ──
    print("\n" + "=" * 70)
    print("🔍 PROFILE COMPARISON")
    print("=" * 70)

    decisions = {pid: rec["decision"]["action"] for pid, rec in results.items()}
    scores = {pid: rec["decision"]["rel_score"] for pid, rec in results.items()}

    print(f"\nDecisions: {decisions}")
    print(f"Score Range: {min(scores.values()):.4f} → {max(scores.values()):.4f}")

    if len(set(decisions.values())) > 1:
        print("\n⚠️  Profiles disagree — detail:")
        for pid, rec in results.items():
            print(f"   {pid}: {rec['decision']['action']} @ {rec['decision']['rel_score']:.4f}")
    else:
        print("\n✅ All profiles agree — consistent signal")

    print("\n🎉 Demo Complete — Observation Mode, No Execution")
    print("=" * 70)


if __name__ == "__main__":
    main()