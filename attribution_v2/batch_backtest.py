"""
batch_backtest.py — Feed your bot's data through all 4 attribution_v2 profiles
Output: logs/pf-*/YYYY-MM-DD.jsonl + summary table
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from profile_runner import run_all_profiles
from profile_logger import write_all
from data_bridge import FactorDataBridge
from real_data_source import load_real_candidates, describe_sources


# Mapping of v2 record fields → real bot field (for the run report)
V2_FIELD_MAP = {
    "symbol": "pair",
    "candidate_direction": "action / direction (LONG|BUY → BUY, SHORT|SELL → SELL)",
    "trend_raw": "score_final sign (signal_csv) | trend / trend_dir (bot dict)",
    "location_raw": "location / sr_level / pivot (bot dict) — NULL in CSV → degraded",
    "xgb_p_up": "score_x / 100 (XGB factor 0-100 → 0-1)",
    "mc_p_up": "score_m / 100 (MC factor 0-100 → 0-1)",
}


class AttributionBacktester:
    """
    Batch processor — take your bot's candidate records → run all 4 v2 profiles → log & compare.
    Two modes:
    - replay_history(list_of_your_candidates)  # Past data
    - stream_live()                             # Real-time observation
    """

    def __init__(self, symbol: str = "USD/JPY"):
        self.bridge = FactorDataBridge(symbol)
        self.results: List[Dict[str, Any]] = []

    def process_one(
        self,
        bot_candidate: Dict[str, Any],
        cycle_id: str = "",
    ) -> Dict[str, Dict[str, Any]]:
        """
        ONE bot candidate → ALL 4 profiles.
        Pass your bot's native dict — bridge handles format translation.
        """
        # Translate your bot's format → v2 standard
        v2_input = self.bridge.from_bot_candidate(bot_candidate, cycle_id=cycle_id)

        # Run through all 4 attribution profiles
        results = run_all_profiles(**v2_input)

        # Write to isolated logs
        write_all(results)

        # Store for summary
        self.results.append({
            "v2_input": v2_input,
            "profile_results": results,
            "provenance": {
                "source": bot_candidate.get("_source", bot_candidate.get("source", "unknown")),
                "source_kind": bot_candidate.get("source_kind", "unknown"),
                "final_score": bot_candidate.get("_final_score"),
                "action_taken": bot_candidate.get("_action_taken", ""),
                "degraded": bot_candidate.get("_degraded", False),
            },
        })

        return results

    def replay_history(
        self,
        bot_candidate_list: List[Dict[str, Any]],
        label: str = "HISTORY_BATCH",
    ) -> Dict[str, Any]:
        """
        Process a list of historical bot candidates.

        Each dict in your list should have keys matching your bot, e.g.:
        {
            "symbol": "USD/JPY",
            "direction": "BUY",
            "trend": 1,
            "location": "SUPPORT",
            "xgb_p_up": 0.75,
            "mc_p_up": 0.65,
            "timestamp": "2026-10-09T10:00:00Z"  # optional
        }
        """
        decisions = {k: [] for k in ["PF-A", "PF-B", "PF-C", "PF-D"]}
        scores = {k: [] for k in ["PF-A", "PF-B", "PF-C", "PF-D"]}

        for idx, cand in enumerate(bot_candidate_list, 1):
            results = self.process_one(cand, cycle_id=f"{label}_{idx:04d}")
            for pid, rec in results.items():
                decisions[pid].append(rec["decision"]["action"])
                scores[pid].append(rec["decision"]["rel_score"])

        # Build summary
        summary = {}
        for pid in decisions:
            n = len(decisions[pid])
            summary[pid] = {
                "total": n,
                "pass": decisions[pid].count("PASS"),
                "watch": decisions[pid].count("WATCH"),
                "reject": decisions[pid].count("REJECT"),
                "pass_rate": round(decisions[pid].count("PASS") / n, 4) if n else 0,
                "watch_rate": round(decisions[pid].count("WATCH") / n, 4) if n else 0,
                "reject_rate": round(decisions[pid].count("REJECT") / n, 4) if n else 0,
                "avg_score": round(sum(scores[pid]) / n, 4) if n else 0,
            }

        # Provenance breakdown — single source of truth from load_real_candidates
        degraded = sum(1 for r in self.results if r["provenance"].get("degraded", False))
        sources = {}
        for r in self.results:
            key = r["provenance"]["source"]
            sources[key] = sources.get(key, 0) + 1

        return {
            "label": label,
            "candidates": len(bot_candidate_list),
            "summary": summary,
            "degraded": degraded,
            "sources": sources,
        }

    def print_summary(self, result: Dict[str, Any]):
        s = result["summary"]
        print("\n" + "=" * 70)
        print(f"📊 BATCH SUMMARY — {result['label']}")
        print(f"   Candidates Processed: {result['candidates']}")
        print(f"   Degraded records:     {result.get('degraded', 0)}")
        print("=" * 70)
        print(f"{'Profile':<8} {'PASS':>8} {'WATCH':>8} {'REJECT':>8} {'AVG_SCORE':>10}")
        print("-" * 70)
        for pid in ["PF-A", "PF-B", "PF-C", "PF-D"]:
            print(
                f"{pid:<8} "
                f"{s[pid]['pass_rate']:8.2%} "
                f"{s[pid]['watch_rate']:8.2%} "
                f"{s[pid]['reject_rate']:8.2%} "
                f"{s[pid]['avg_score']:10.4f}"
            )
        print("=" * 70)


# ══════════════════════════════════════════════════════════════════
# MAIN — REAL DATA (read-only, observation mode, no orders)
# ══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 70)
    print("🔁 ATTRIBUTION v2 — BATCH REPLAY ON REAL BOT DATA")
    print("   Mode: OBSERVATION ONLY — no orders, no broker calls")
    print("=" * 70)

    # ── Discover & load REAL historical candidates from the main system ──
    src = describe_sources()
    print("\n📂 REAL DATA SOURCES (read-only):")
    for kind, files in src.items():
        print(f"   {kind:<12}: {len(files)} file(s)")

    print("\n🔗 FIELD MAPPING (real bot → attribution_v2):")
    for v2_field, real_field in V2_FIELD_MAP.items():
        print(f"   {v2_field:<20} <- {real_field}")

    real_candidates = load_real_candidates()
    print(f"\n✅ Loaded {len(real_candidates)} real candidates")
    if not real_candidates:
        print("❌ No real candidates found — aborting (demo data NOT used).")
        raise SystemExit(1)

    # ── Replay every candidate through all 4 v2 profiles ──
    bt = AttributionBacktester()
    result = bt.replay_history(real_candidates, label="REAL_BOT_HISTORY")
    bt.print_summary(result)

    print("\n📁 Per-source contribution:")
    for src_path, n in sorted(result["sources"].items()):
        print(f"   {src_path:<50} {n:>4}")

    print("\n✅ Done — logs written to attribution_v2/logs/pf-*/")
    print("🛡️  No execution: every record carries execution.order_submitted=false")