"""
live_hook.py — Bridge the main bot's candidate phase → attribution_v2 profiles
================================================================================
READ-ONLY INTEGRATION LAYER. Observation mode only:
  * never submits an order
  * never blocks / delays a candidate
  * never raises into the bot loop (fail-open by design)
  * never touches a file outside attribution_v2/logs/

Usage from the bot (see `observe_candidate()` docstring for the exact call):

    from attribution_v2.live_hook import AttributionObserver

    _observer = AttributionObserver(profile_label=PROFILE_LABEL)   # once, in main()

    _observer.observe_candidate({
        "pair":            pair,             # "GBPJPY=X" (Yahoo) or "GBP/JPY"
        "direction":       direction,        # "BUY" / "SELL"
        "trend_raw":       trend_raw,        # +1 / 0 / -1  (see derive_trend_raw)
        "location_raw":    location_raw,     # +1 / 0 / -1  (see derive_location_raw)
        "xgb_p_up":        xgb_p_up,         # 0–1  (bot's `X` is 0–100 → /100)
        "mc_p_up":         mc_p_up,          # 0–1  (bot's `M` is 0–100 → /100)
        "score_final":     w["FINAL"],       # optional, traceability only
        "gate":            "PASS",           # optional — only used for a richer trace
        "cycle_id":        f"{TODAY_STR}_{len(all_candidates):04d}",
    })

Every candidate — PASSing or not — is written to:
    attribution_v2/logs/pf-{a,b,c,d}/YYYY-MM-DD.jsonl

so the 4 profiles can later be compared against the bot's own outcome.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from data_bridge import FactorDataBridge          # noqa: E402
from profile_logger import write_all               # noqa: E402
from profile_runner import run_all_profiles        # noqa: E402

__all__ = [
    "AttributionObserver",
    "observe_candidate",
    "derive_trend_raw",
    "derive_location_raw",
    "derive_xgb_p_up",
    "derive_mc_p_up",
    "label_from_score",
]


# ══════════════════════════════════════════════════════════════════════
# FACTOR DERIVATION — bot output → attribution_v2 factor space
# ══════════════════════════════════════════════════════════════════════
def derive_trend_raw(w: Optional[Dict[str, Any]], gap: float) -> Optional[float]:
    """Bot's weighted-score block → trend_raw in {+1, 0, -1}.

    The bot has no explicit "trend" factor; the closest native quantities are:
      * `S`   — strength-gap score 0–100 (S = |gap|/3.5*100) — 0 when the
                strength gap is small, so a weak/absent trend reads as neutral
      * `gap` — signed base-minus-quote strength difference (direction carrier)

    Mapping (mirrors the 45/55 neutral band already used by
    `real_data_source.norm_trend`, so live and historical records agree):
      S > 55 → +1 (clear trend toward the candidate's base currency)
      S < 45 → -1
      else   → 0  (neutral band — NOT a missing factor)

    A candidate is only ever routed here when the bot already accepted its
    direction, so a non-neutral trend always agrees with `direction`.
    """
    if w is None:
        return None
    try:
        s = float(w.get("S", 50.0))
    except (TypeError, ValueError):
        s = 50.0
    if s > 55.0:
        return 1.0
    if s < 45.0:
        return -1.0
    # S sits in the neutral band but the strength gap itself is wide → the
    # trend is real, just outside the S-scale's saturating region.
    try:
        if abs(float(gap)) >= 3.5:          # S saturates at |gap| = 3.5
            return 1.0 if float(gap) > 0 else -1.0
    except (TypeError, ValueError):
        pass
    return 0.0


def derive_location_raw(
    sig: Any,
    direction: str,
    current_price: Optional[float],
) -> Optional[float]:
    """Signal pivot levels → location_raw in {+1, 0, -1}.

    Uses the same pivots `StrategyEngine._eval_pivots` already computed for the
    signal (classic P / S1 / R1), so no extra market data is fetched.

    The sign convention follows `data_bridge._norm_location`: +1 = SUPPORT
    (price sitting on a floor → bullish), -1 = RESISTANCE (price under a
    ceiling → bearish). That is an *absolute* reading of where price sits
    relative to the pivot, independent of the candidate's direction — exactly
    how the historical records were produced.

    Returns None when pivots are unavailable, so the profile records are
    honestly marked `degraded` instead of silently substituting a neutral 0.
    """
    pivots = getattr(sig, "pivot_levels", None)
    if not pivots or current_price is None:
        return None
    try:
        price = float(current_price)
        p = float(pivots.get("P"))
        s1 = float(pivots.get("S1"))
        r1 = float(pivots.get("R1"))
    except (TypeError, ValueError, AttributeError):
        return None

    if price <= p:
        # Below the daily pivot → nearer to support than to resistance.
        return 1.0 if abs(price - s1) <= abs(price - p) else 0.0
    # Above the daily pivot → nearer to resistance than to support.
    return -1.0 if abs(price - r1) <= abs(price - p) else 0.0


def derive_xgb_p_up(sig: Any, w: Optional[Dict[str, Any]]) -> Optional[float]:
    """Bot's XGB output → P(up) in [0, 1].

    `sig.model_p_up` is already the model's raw P(up) in [0, 1] — the preferred
    source. Falls back to the bot's `X` factor (0–100, see calc_weighted_score)
    and finally to the P(up) implied by the accepted direction and its raw
    probability. 0.5 = no edge.
    """
    p = getattr(sig, "model_p_up", None)
    if p is not None:
        try:
            return max(0.0, min(1.0, float(p)))
        except (TypeError, ValueError):
            pass

    if w is not None and w.get("X") is not None:
        try:
            return max(0.0, min(1.0, float(w["X"]) / 100.0))
        except (TypeError, ValueError):
            pass

    raw = getattr(sig, "raw_prob", None)
    if raw is not None:
        try:
            raw = max(0.0, min(1.0, float(raw)))
        except (TypeError, ValueError):
            raw = None
        if raw is not None:
            return raw if direction == "BUY" else 1.0 - raw
    return None


def derive_mc_p_up(mc_pct_up: Any) -> Optional[float]:
    """Bot's MC percentage → P(up) in [0, 1]. None stays None (→ degraded)."""
    if mc_pct_up is None:
        return None
    try:
        return max(0.0, min(1.0, float(mc_pct_up) / 100.0))
    except (TypeError, ValueError):
        return None


def label_from_score(score: Any) -> str:
    """Human-readable bucket for the bot's FINAL score — traceability only."""
    try:
        s = float(score)
    except (TypeError, ValueError):
        return "UNKNOWN"
    if s >= 70.0:
        return "STRONG"
    if s >= 55.0:
        return "MODERATE"
    if s >= 40.0:
        return "WEAK"
    return "VERY_WEAK"


# ══════════════════════════════════════════════════════════════════════
# OBSERVER
# ══════════════════════════════════════════════════════════════════════
class AttributionObserver:
    """Run every accepted bot candidate through all 4 attribution profiles.

    One instance per bot run. Holds a `FactorDataBridge` (read-only adapter
    around config_oanda / config_bot) and a per-run cycle counter.
    """

    def __init__(self, profile_label: str = "", enabled: bool = True):
        self.enabled = enabled
        self.profile_label = profile_label or "unknown"
        try:
            self.bridge = FactorDataBridge()
        except Exception as exc:                      # pragma: no cover - defensive
            self.enabled = False
            self.bridge = None
            print(f"⚠️  attribution_v2: bridge unavailable ({exc}) — observation OFF")
        self._seq = 0
        self._written = 0
        self._errors = 0

    # ── public API ────────────────────────────────────────────────────
    def observe_candidate(
        self,
        *,
        pair: str,
        direction: str,
        trend_raw: Optional[float] = None,
        location_raw: Optional[float] = None,
        xgb_p_up: Optional[float] = None,
        mc_p_up: Optional[float] = None,
        score_final: Optional[float] = None,
        gate: str = "",
        cycle_id: str = "",
        timestamp: Optional[str] = None,
        date_str: Optional[str] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """Feed ONE candidate to all 4 profiles, then append to the JSONL logs.

        Returns the 4 profile records ({} when observation is disabled or the
        candidate could not be processed). NEVER raises — a failure here must
        not be able to stop the trading loop.
        """
        if not self.enabled:
            return {}
        try:
            self._seq += 1
            bot_candidate = {
                "pair": pair,
                "direction": direction,
                "trend_raw": trend_raw,
                "location_raw": location_raw,
                "xgb_p_up": xgb_p_up,
                "mc_p_up": mc_p_up,
                "timestamp": timestamp
                or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }

            v2_input = self.bridge.from_bot_candidate(
                bot_candidate,
                cycle_id=cycle_id
                or f"{self.profile_label}_{self._seq:04d}",
            )

            results = run_all_profiles(**v2_input)

            # Provenance stamp — keeps the live stream self-describing and
            # distinguishable from the batch replay (REAL_BOT_HISTORY_*).
            for record in results.values():
                record["source"] = {
                    "kind": "LIVE_BOT_CANDIDATE",
                    "profile_label": self.profile_label,
                    "bot_score_final": score_final,
                    "bot_score_bucket": label_from_score(score_final),
                    "gate": gate,
                }

            write_all(results, date_str=date_str)
            self._written += 1
            return results
        except Exception as exc:                      # pragma: no cover - defensive
            self._errors += 1
            print(f"⚠️  attribution_v2 observe_candidate({pair}) failed: {exc}")
            return {}

    def stats(self) -> Dict[str, Any]:
        """Counters for the end-of-run summary line."""
        return {
            "enabled": self.enabled,
            "profile_label": self.profile_label,
            "candidates_observed": self._written,
            "errors": self._errors,
        }

    def summary_line(self) -> str:
        s = self.stats()
        if not s["enabled"]:
            return "🧪 ATTRIBUTION V2: OFF"
        return (
            f"🧪 ATTRIBUTION V2: {s['candidates_observed']} candidate(s) → "
            f"logs/pf-a..d/ ({s['errors']} error(s))"
        )


def observe_candidate(observer: Optional[AttributionObserver], **kwargs) -> Dict[str, Dict[str, Any]]:
    """Module-level convenience wrapper — safe to call with observer=None."""
    if observer is None:
        return {}
    return observer.observe_candidate(**kwargs)
