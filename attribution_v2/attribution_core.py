"""
attribution_core.py — Pure calculation engine, no side effects
Rules: signed values only, NO abs(), missing ≠ neutral
"""

import copy
import hashlib
import json
from typing import Dict, List, Optional, Tuple, Any


# ────────────────────────────────────────────────
# 1. Candidate-Relative Score
# ────────────────────────────────────────────────
def candidate_relative(raw_score: float, direction: str) -> float:
    """
    Align raw score to candidate direction.
    BUY  = +1 multiplier
    SELL = -1 multiplier

    Example: SELL, raw=-0.82 → relative=+0.82 (supports SELL)
    """
    sign = 1 if direction.strip().upper() == "BUY" else -1
    return raw_score * sign


# ────────────────────────────────────────────────
# 2. Classify Score
# ────────────────────────────────────────────────
def classify_score(relative_score: float, neutral_band: float = 0.10) -> str:
    """
    Classify relative score into SUPPORT / NEUTRAL / OPPOSE.
    """
    if abs(relative_score) < neutral_band:
        return "NEUTRAL"
    return "SUPPORT" if relative_score >= neutral_band else "OPPOSE"


# ────────────────────────────────────────────────
# 3. Weighted Calculation + Missing Factor Handling
# ────────────────────────────────────────────────
def weighted_calc(
    factors: Dict[str, Optional[float]],
    weights: Dict[str, float]
) -> Tuple[float, Dict[str, float], List[str], bool]:
    """
    Calculate weighted relative score, handling missing factors.

    Returns:
        rel_score: weighted sum in [-1, +1]
        contributions: {factor: weighted_contribution}
        missing_factors: list of keys with None value
        degraded: True if any factor was missing
    """
    all_keys = list(weights.keys())
    missing_factors = [k for k in all_keys if factors.get(k) is None]
    available = {k: factors[k] for k in all_keys if factors.get(k) is not None}

    if not available:
        return 0.0, {}, missing_factors, True

    # Renormalize weights over available factors only
    total_w = sum(weights[k] for k in available)
    norm_weights = {k: weights[k] / total_w for k in available}

    contributions = {k: v * norm_weights[k] for k, v in available.items()}
    rel_score = sum(contributions.values())

    return rel_score, contributions, missing_factors, len(missing_factors) > 0


# ────────────────────────────────────────────────
# 4. Decision from Score — SIGNED, never abs()
# ────────────────────────────────────────────────
def decision_from_score(rel_score: float, thresholds: Dict[str, float]) -> str:
    """
    ALWAYS use signed value. Negative = oppose, never PASS via magnitude.
    thresholds: {"pass": x, "watch": y}
    """
    if rel_score >= thresholds["pass"]:
        return "PASS"
    if rel_score >= thresholds["watch"]:
        return "WATCH"
    return "REJECT"


# ────────────────────────────────────────────────
# 5. Counterfactual Analysis
# ────────────────────────────────────────────────
def counterfactuals_full(
    factors: Dict[str, Optional[float]],
    weights: Dict[str, float],
    thresholds: Dict[str, float]
) -> Dict[str, Dict[str, Any]]:
    """
    Calculate FULL + remove-one-factor variants.
    Returns dict: {variant_name: {rel_score, action, delta, flipped}}
    """
    variants = {"FULL": list(weights.keys())}
    for factor in weights:
        variants[f"NO_{factor.upper()}"] = [k for k in weights if k != factor]

    results = {}
    full_score, _, _, _ = weighted_calc(factors, weights)
    full_action = decision_from_score(full_score, thresholds)

    for name, included in variants.items():
        sub_factors = {k: factors[k] for k in included}
        sub_weights = {k: weights[k] for k in included}
        score, _, _, _ = weighted_calc(sub_factors, sub_weights)
        action = decision_from_score(score, thresholds)
        results[name] = {
            "rel_score": round(score, 6),
            "action": action,
            "delta": round(score - full_score, 6),
            "flipped": action != full_action and name != "FULL"
        }

    return results


# ────────────────────────────────────────────────
# 6. Consensus Helper
# ────────────────────────────────────────────────
def calc_consensus(
    factors: Dict[str, Optional[float]],
    neutral_band: float = 0.10
) -> Dict[str, int]:
    """Count SUPPORT / NEUTRAL / OPPOSE across available factors."""
    counts = {"SUPPORT": 0, "NEUTRAL": 0, "OPPOSE": 0}
    for val in factors.values():
        if val is None:
            continue
        counts[classify_score(val, neutral_band)] += 1
    return counts


# ────────────────────────────────────────────────
# 7. Attribution — Decision-Sensitive Factors
# ────────────────────────────────────────────────
def decision_sensitive_factors(
    counterfactuals: Dict[str, Dict[str, Any]],
    threshold_delta: float = 0.05
) -> List[str]:
    """Identify factors that flipped decision or moved score materially."""
    sensitive = []
    for name, cf in counterfactuals.items():
        if name == "FULL":
            continue
        factor_name = name.replace("NO_", "").lower()
        if cf.get("flipped") or abs(cf.get("delta", 0)) >= threshold_delta:
            sensitive.append(factor_name)
    return sensitive


# ────────────────────────────────────────────────
# 8. Build Canonical JSONL Record
# ────────────────────────────────────────────────
def build_jsonl(
    schema_version: str = "1.1",
    timestamp: str = "",
    cycle_id: str = "",
    candidate_id: str = "",
    profile_id: str = "",
    config_hash: str = "",
    symbol: str = "",
    candidate_direction: str = "",
    market_snapshot_ts: str = "",
    weights: Dict[str, float] = None,
    neutral_band: float = 0.10,
    factors: Dict[str, Dict[str, Any]] = None,
    consensus: Dict[str, int] = None,
    rel_score: float = 0.0,
    decision: str = "REJECT",
    degraded: bool = False,
    missing_factors: List[str] = None,
    counterfactuals: Dict[str, Dict[str, Any]] = None,
    attribution: Dict[str, Any] = None,
    execution: Dict[str, Any] = None
) -> Dict[str, Any]:
    """Return standardized JSON-serializable decision record."""
    return {
        "schema_version": schema_version,
        "timestamp": timestamp,
        "cycle_id": cycle_id,
        "candidate_id": candidate_id,
        "profile_id": profile_id,
        "config_hash": config_hash,
        "symbol": symbol,
        "candidate_direction": candidate_direction,
        "market_snapshot_ts": market_snapshot_ts,
        "weights": weights or {},
        "neutral_band": neutral_band,
        "factors": factors or {},
        "consensus": consensus or {},
        "decision": {
            "rel_score": round(rel_score, 6),
            "action": decision,
            "degraded": degraded,
            "missing_factors": missing_factors or []
        },
        "counterfactuals": counterfactuals or {},
        "attribution": attribution or {},
        "execution": execution or {
            "eligible_for_execution": False,
            "execution_block_reason": "OBSERVATION_MODE",
            "order_submitted": False
        }
    }


# ────────────────────────────────────────────────
# 9. Config Hash Utility
# ────────────────────────────────────────────────
def hash_config(config: Dict[str, Any]) -> str:
    """Generate stable short hash from profile weights/thresholds."""
    h = hashlib.sha1(json.dumps(config, sort_keys=True).encode())
    return h.hexdigest()[:10]