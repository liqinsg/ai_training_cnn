"""
data_bridge.py — Read existing configs & feed real factors into attribution_v2
Reads from: ../config_oanda.py, ../config_bot.py
READ-ONLY — never modifies existing files ✅
"""

import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

# ── Project root first → clean import ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ✅ Direct import — matches your actual structure
from config_oanda import get_oanda_profile, is_market_open
from config_bot import get_profile as load_profile


class FactorDataBridge:
    """
    Bridge — connect your existing bot's data to attribution_v2
    One symbol/cycle → extract 4 factors → run all 4 v2 profiles → write logs
    """

    def __init__(self, symbol: str = "USD/JPY", env: str = None):
        self.symbol = symbol
        self.instrument = symbol.replace("/", "_")  # USD/JPY → USD_JPY
        self.profile = get_oanda_profile(env)
        self.api = self.profile.get("api")
        self.account_id = self.profile.get("account_ids", [""])[0] if self.profile else ""

    # ══════════════════════════════════════════════════════════════════
    # ADAPTERS — Map YOUR bot's output → attribution_v2 format
    # ══════════════════════════════════════════════════════════════════
    def from_bot_candidate(
        self,
        bot_candidate: Dict[str, Any],
        cycle_id: str = "",
    ) -> Dict[str, Any]:
        """
        Call this from YOUR bot loop — pass its candidate dict.

        REAL field names discovered in the main system (see Step-1 probe):

        | v2 target         | primary key         | aliases accepted                   |
        |-------------------|---------------------|------------------------------------|
        | symbol            | "symbol" / "pair"   | self.symbol fallback               |
        | direction         | "direction"         | "action", "signal", "side"        |
        | trend_raw         | "trend"             | "trend_dir", "trend_state"         |
        | location_raw      | "location"          | "sr_level", "pivot", "pivot_state" |
        | xgb_p_up          | "xgb_p_up"          | "xgb_prob", "prob_raw", "model_p_up", "p_up" |
        | mc_p_up           | "mc_p_up"           | "mc_prob", "mc_pct_up", "mc_p_up_pct" |

        Scores from the main bot are 0–100 ("X"/"M" keys in `calc_weighted_score`),
        so all probability inputs are routed through `_prob_clip`, which
        auto-detects the scale (0–1 vs 0–100) instead of silently clamping
        e.g. X=50 → 1.0.
        """
        # symbol — accept explicit pair on the record, else use bridge default
        symbol = bot_candidate.get("symbol", bot_candidate.get("pair"))
        if not symbol:
            symbol = self.symbol
        # normalise Yahoo style (EURUSD=X) → readable (EUR/USD)
        symbol = self._norm_symbol(symbol)

        direction = bot_candidate.get(
            "direction",
            bot_candidate.get("action", bot_candidate.get("signal", bot_candidate.get("side"))),
        )

        # --- Map YOUR trend output ---
        trend_val = bot_candidate.get(
            "trend_raw",
            bot_candidate.get(
                "trend", bot_candidate.get("trend_dir", bot_candidate.get("trend_state"))
            ),
        )
        trend_raw = self._norm_trend(trend_val)

        # --- Map YOUR location/support-resistance ---
        loc_val = bot_candidate.get(
            "location_raw",
            bot_candidate.get(
                "location",
                bot_candidate.get(
                    "sr_level", bot_candidate.get("pivot", bot_candidate.get("pivot_state"))
                ),
            ),
        )
        location_raw = self._norm_location(loc_val)

        # --- Map YOUR model probabilities ---
        xgb_p_up = bot_candidate.get(
            "xgb_p_up",
            bot_candidate.get(
                "xgb_prob", bot_candidate.get("prob_raw", bot_candidate.get("model_p_up"))
            ),
        )
        mc_p_up = bot_candidate.get(
            "mc_p_up",
            bot_candidate.get(
                "mc_prob", bot_candidate.get("mc_pct_up", bot_candidate.get("mc_p_up_pct"))
            ),
        )

        # Normalize probabilities (scale-aware: 0–1 or 0–100)
        xgb_p_up = self._prob_clip(xgb_p_up)
        mc_p_up = self._prob_clip(mc_p_up)

        ts = bot_candidate.get("timestamp") or datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )

        return {
            "symbol": symbol,
            "candidate_direction": self._norm_direction(direction),
            "trend_raw": trend_raw,
            "location_raw": location_raw,
            "xgb_p_up": xgb_p_up,
            "mc_p_up": mc_p_up,
            "timestamp": ts,
            "cycle_id": cycle_id,
        }

    # ══════════════════════════════════════════════════════════════════
    # NORMALIZERS — Any format → v2 standard
    # ══════════════════════════════════════════════════════════════════
    @staticmethod
    def _norm_trend(val) -> Optional[float]:
        """Your trend format → +1=BULL, 0=NEUTRAL, -1=BEAR"""
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return max(-1.0, min(1.0, float(val)))
        s = str(val).upper()
        bullish = {"BULL", "UP", "LONG", "BUY", "RISE"}
        bearish = {"BEAR", "DOWN", "SHORT", "SELL", "FALL"}
        if any(w in s for w in bullish):
            return 1.0
        if any(w in s for w in bearish):
            return -1.0
        return 0.0

    @staticmethod
    def _norm_location(val) -> Optional[float]:
        """Your location format → +1=SUPPORT, 0=NEUTRAL, -1=RESISTANCE"""
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return max(-1.0, min(1.0, float(val)))
        s = str(val).upper()
        if "SUPPORT" in s or "SUPP" in s or "BOTTOM" in s:
            return 1.0
        if "RESIST" in s or "TOP" in s:
            return -1.0
        return 0.0

    @staticmethod
    def _norm_direction(val) -> str:
        """Any direction format → canonical 'BUY' | 'SELL'.

        Handles the main system's Direction enum ('LONG'/'SHORT'), action
        strings ('BUY'/'SELL') and numeric encoding (+1/-1).
        """
        if val is None:
            return "BUY"
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            return "BUY" if float(val) >= 0 else "SELL"
        s = str(val).strip().upper()
        if s in {"LONG", "BUY", "BULL", "UP", "+1"}:
            return "BUY"
        if s in {"SHORT", "SELL", "BEAR", "DOWN", "-1"}:
            return "SELL"
        # fall back to substring match (e.g. "Direction.LONG")
        if "LONG" in s or "BUY" in s:
            return "BUY"
        if "SHORT" in s or "SELL" in s:
            return "SELL"
        return "BUY"

    @staticmethod
    def _norm_symbol(val) -> str:
        """Yahoo/bot symbol → readable 'BASE/QUOTE' (EURUSD=X → EUR/USD)."""
        if not val:
            return ""
        s = str(val).strip().upper().replace("=X", "").replace("_", "/")
        if "/" in s:
            base, quote = s.split("/", 1)
            return f"{base}/{quote}"
        if len(s) == 6 and s.isalpha():
            return f"{s[:3]}/{s[3:]}"
        return s

    @staticmethod
    def _prob_clip(val) -> Optional[float]:
        """Any probability → safely in [0, 1], scale-aware.

        The main bot's XGB/MC factors are published on a 0–100 scale (see
        `calc_weighted_score`: X = xgb_prob*100, M = mc_pct_up). If a value
        arrives as 0–100 it is rescaled to 0–1 rather than clamped to 1.0.
        """
        if val is None:
            return None
        try:
            f = float(val)
        except (TypeError, ValueError):
            return None
        if f > 1.0:  # 0–100 scale (or percent) → 0–1
            f = f / 100.0
        return max(0.0, min(1.0, f))

    # ══════════════════════════════════════════════════════════════════
    # Live market check helper
    # ══════════════════════════════════════════════════════════════════
    def is_tradeable(self) -> bool:
        """Forward to your existing is_market_open()"""
        return is_market_open(self.instrument)


def inspect_all() -> Dict[str, Any]:
    """Report what's connected"""
    info = {
        "project_root": str(PROJECT_ROOT),
        "get_oanda_profile_available": callable(get_oanda_profile),
        "load_profile_available": callable(load_profile),
        "is_market_open_available": callable(is_market_open),
        "profiles_available": [],
        "oanda_env": None,
        "account_ids": [],
    }

    prof = get_oanda_profile()
    info["oanda_env"] = prof.get("env")
    info["account_ids"] = prof.get("account_ids", [])

    for pid in [1, 2, 3, 4]:
        try:
            p = load_profile(pid)
            info["profiles_available"].append({
                "id": f"profile{pid}",
                "name": p.get("NAME", f"profile{pid}"),
                "weights": p.get("WEIGHTS", {}),
            })
        except Exception as e:
            info["profiles_errors"] = info.get("profiles_errors", [])
            info["profiles_errors"].append(f"profile{pid}: {e}")

    return info


if __name__ == "__main__":
    print("=" * 70)
    print("🔍 DATA BRIDGE — Connection Status")
    print("=" * 70)
    info = inspect_all()

    print(f"\n📁 Project Root: {info['project_root']}")
    print(f"🔗 OANDA Profile:  {'✅' if info['get_oanda_profile_available'] else '❌'}")
    print(f"📂 Bot Profiles:   {'✅' if info['load_profile_available'] else '❌'}")
    print(f"🏪 Market Check:   {'✅' if info['is_market_open_available'] else '❌'}")

    if info["oanda_env"]:
        print(f"\n🌐 OANDA Env: {info['oanda_env'].upper()}")
        for aid in info["account_ids"]:
            print(f"   Account: {aid}")

    if info["profiles_available"]:
        print(f"\n📊 Loaded Profiles ({len(info['profiles_available'])}):")
        for p in info["profiles_available"]:
            w = p["weights"]
            print(f"   {p['id']:12} | S:{w.get('S',0):.2f} R:{w.get('R',0):.2f} "
                  f"A:{w.get('A',0):.2f} X:{w.get('X',0):.2f} M:{w.get('M',0):.2f}")

    print("\n" + "=" * 70)
    print("✅ Bridge ready — use from_bot_candidate() in your bot loop")
    print("=" * 70)