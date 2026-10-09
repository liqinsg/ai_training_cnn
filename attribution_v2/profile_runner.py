"""
profile_runner.py — Independent execution engine per profile
- Process one candidate through ONE profile
- Or run ALL 4 profiles in parallel on the same candidate
- Observation mode only: never touches execution logic
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from attribution_core import (
    candidate_relative,
    weighted_calc,
    decision_from_score,
    calc_consensus,
    counterfactuals_full,
    decision_sensitive_factors,
    build_jsonl,
)
from profiles.attribution_profiles import get_profile, list_profiles


class ProfileAttribution:
    """Process candidates through a single profile's configuration."""

    def __init__(self, profile_id: str):
        self.profile_id = profile_id
        self.profile = get_profile(profile_id)  # Deep copy — isolated
        self._config_hash = self._hash_config(self.profile)

    @staticmethod
    def _hash_config(profile: Dict[str, Any]) -> str:
        """Generate short stable hash for config version tracking."""
        sig = json.dumps(
            {k: profile[k] for k in ["weights", "thresholds", "neutral_band"]},
            sort_keys=True
        )
        return hashlib.sha1(sig.encode()).hexdigest()[:10]

    def process_candidate(
        self,
        timestamp: Optional[str] = None,
        symbol: str = "",
        candidate_direction: str = "",
        trend_raw: Optional[float] = None,
        location_raw: Optional[float] = None,
        xgb_p_up: Optional[float] = None,
        mc_p_up: Optional[float] = None,
        market_snapshot_ts: Optional[str] = None,
        cycle_id: Optional[str] = None,
        candidate_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Process one candidate → full attribution record.

        Inputs (raw values from upstream system):
          - trend_raw:   +1=BULL / 0=NEUTRAL / -1=BEAR
          - location_raw: +1=SUPPORT / 0=NEUTRAL / -1=RESISTANCE
          - xgb_p_up:    float in [0, 1] — probability of upward movement
          - mc_p_up:     float in [0, 1] — Monte Carlo upward probability

        Returns:
            Complete JSONL-compatible dict for logging/analysis
        """
        # Auto-fill timestamp if not provided
        if timestamp is None:
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # ── Step 1: Normalize all factors to candidate-relative space ──
        # Convert probability [0,1] → centered [-1, +1]
        def _p_to_rel(p_val: Optional[float]) -> Optional[float]:
            return None if p_val is None else (p_val - 0.5) * 2

        factors_raw: Dict[str, Optional[float]] = {
            "trend": trend_raw,
            "location": location_raw,
            "xgb": _p_to_rel(xgb_p_up),
            "mc": _p_to_rel(mc_p_up),
        }

        # Align to candidate direction
        factors_aligned: Dict[str, Optional[float]] = {
            name: (None if val is None else candidate_relative(val, candidate_direction))
            for name, val in factors_raw.items()
        }

        # ── Step 2: Weighted calculation ──
        rel_score, contributions, missing_factors, degraded = weighted_calc(
            factors_aligned, self.profile["weights"]
        )

        # ── Step 3: Decision ──
        action = decision_from_score(rel_score, self.profile["thresholds"])

        # ── Step 4: Consensus ──
        consensus = calc_consensus(factors_aligned, self.profile["neutral_band"])

        # ── Step 5: Counterfactuals ──
        counterfactuals = counterfactuals_full(
            factors_aligned, self.profile["weights"], self.profile["thresholds"]
        )

        # ── Step 6: Attribution ──
        sensitive = decision_sensitive_factors(counterfactuals)
        attribution = {
            "decision_sensitive_factors": sensitive,
            "primary_driver": sensitive[0] if sensitive else None
        }

        # ── Step 7: Execution stub — OBSERVATION MODE ──
        execution = {
            "eligible_for_execution": False,
            "execution_block_reason": "OBSERVATION_MODE",
            "order_submitted": False
        }

        # ── Step 8: Build final record ──
        return build_jsonl(
            schema_version="1.1",
            timestamp=timestamp,
            cycle_id=cycle_id or "",
            candidate_id=candidate_id or "",
            profile_id=self.profile_id,
            config_hash=self._config_hash,
            symbol=symbol,
            candidate_direction=candidate_direction,
            market_snapshot_ts=market_snapshot_ts or timestamp,
            weights=self.profile["weights"],
            neutral_band=self.profile["neutral_band"],
            factors={
                name: {
                    "raw": factors_raw[name],
                    "aligned": factors_aligned[name],
                    "contribution": contributions.get(name)
                }
                for name in factors_aligned
            },
            consensus=consensus,
            rel_score=rel_score,
            decision=action,
            degraded=degraded,
            missing_factors=missing_factors,
            counterfactuals=counterfactuals,
            attribution=attribution,
            execution=execution
        )


def run_all_profiles(**kwargs) -> Dict[str, Dict[str, Any]]:
    """
    Run the same candidate through ALL 4 profiles in parallel.

    Accepts same keyword args as ProfileAttribution.process_candidate().
    Returns: { "PF-A": record, "PF-B": record, ..., "PF-D": record }
    """
    results: Dict[str, Dict[str, Any]] = {}
    for pid in list_profiles():
        runner = ProfileAttribution(pid)
        results[pid] = runner.process_candidate(**kwargs)
    return results