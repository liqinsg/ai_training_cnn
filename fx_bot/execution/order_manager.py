"""
execution/order_manager.py
Unified workflow per TERMINOLOGY:
  place_open_order() → FILLED → Position held
  ├─ get_open_positions()      → TAG logic in ONE place
  ├─ update_position()         → modify SL/TP by trade_id
  ├─ place_close_order()        → TAG-aware close
  └─ close_all_positions()      → ⚠️ DANGEROUS

TAG logic (ONE rule set everywhere):
  TAG match found → use it
  No TAG match + no_tag_fallback=False → SAFE STOP (default)
  No TAG match + no_tag_fallback=True → take FIRST trade
"""
from core.config.settings import Settings
from execution.oanda_client import OandaClient
from utils.trade_logger import TradeLogger
from utils.trading_core import get_close_reason
import contextlib

def make_tag(settings: Settings) -> str:
    """Generate TAG: FXBOT-AUTO-P2/P3/P4 based on active profile."""
    profile = settings.profile_name
    if "PROFILE-2" in profile:
        return "FXBOT-AUTO-P2"
    elif "PROFILE-3" in profile:
        return "FXBOT-AUTO-P3"
    elif "PROFILE-4" in profile:
        return "FXBOT-AUTO-P4"
    return "FXBOT-AUTO"


class OrderManager:
    def __init__(self, settings: Settings, oanda: OandaClient):
        self.settings = settings
        self.oanda = oanda
        self.logger = TradeLogger(settings)
        self.tag = make_tag(settings)
        print(f"🏷️  TAG: {self.tag} — operates ONLY on Position with this tag")

    # ========== Open Order → FILLED → Position held ==========
    def place_open_order(self, instrument, direction, units, sl, tp, **kwargs):
        """Place Open Order → FILLED → Position stamped with our TAG → log to CSV.

        kwargs (decision snapshot — 开仓那一刻的决策现场):
            reason:       str  开仓理由一句话 ≤50字
            score_final:  float/str  当时综合分 0-100
        """
        result = self.oanda.open_order(instrument, direction, units, sl, tp, tag=self.tag)
        if result.get("ok"):
            trade_id = result.get("trade_id", "")
            entry_price = result.get("entry_price", 0.0)
            self.logger.record_open(
                trade_id, instrument, direction, units, entry_price, sl, tp,
                tag=self.tag,
                reason=kwargs.get("reason", ""),           # ✅ 透传理由
                score_final=kwargs.get("score_final", ""), # ✅ 透传综合分
            )
            return trade_id
        return None

    # ========== TAG Logic — ONE source of truth ==========
    def get_open_positions(self, instrument, no_tag_fallback=False):
        """Look up held Position — TAG logic in ONE place:
          ✅ TAG match → use it
          ⚠️ No TAG + fallback=False → SAFE STOP (return None)
          ⚡ No TAG + fallback=True → take FIRST trade
        """
        return self.oanda.get_my_position(instrument, self.tag, no_tag_fallback)

    # ========== Update Position — SL/TP by trade_id ==========
    def update_position(self, trade_id, instrument, new_sl=None, new_tp=None):
        """Update SL and/or TP — ONLY the specified trade_id."""
        ok = self.oanda.update_position(trade_id, instrument, sl_price=new_sl, tp_price=new_tp)
        self.logger.record_modify(trade_id, new_sl, new_tp)
        return ok

    # ========== Close Order — reuses SAME TAG logic ==========
    def place_close_order(self, instrument, no_tag_fallback=False):
        """Close Position — reuses get_open_positions() TAG logic automatically."""
        pos = self.get_open_positions(instrument, no_tag_fallback)
        if not pos:
            print("⚠️ No Position found — nothing to close")
            return False, "NO_POSITION"

        trade_id = pos["trade_id"]
        ok = self.oanda.close_my_position(instrument, self.tag, no_tag_fallback)

        if ok:
            reason = "CLIENT_CLOSE"
            with contextlib.suppress(Exception):
                r = get_close_reason(self.oanda, trade_id)
                # 查询不到(UNKNOWN/ACTIVE)时保留默认值 CLIENT_CLOSE，
                # 避免刚关闭的 trade 查不到详情(NO_SUCH_TRADE)而误报 UNKNOWN
                if r not in ("UNKNOWN", "ACTIVE"):
                    reason = r
            self.logger.record_close(trade_id, instrument, pos["entry_price"], reason, pl=0.0)

        return ok, (reason if ok else "NO_POSITION")

    # ========== Close ALL Positions — ⚠️ DANGEROUS ==========
    def close_all_positions(self, instrument):
        """Close EVERYTHING — TAG ignored, ALL positions closed. ⚠️ DANGEROUS."""
        return self.oanda.close_all_positions(instrument)