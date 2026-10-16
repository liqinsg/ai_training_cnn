import json
import os
from datetime import datetime
from typing import Dict, Set


class TPCooldownTracker:
    """出场冷却追踪 — 出场时手动记录，不依赖OANDA推送"""

    def __init__(self, cooldown_hours: float = 2.0, storage_path: str = "tp_cooldown_state.json"):
        self.cooldown_hours = cooldown_hours
        self.storage_path = storage_path
        self.last_exit: Dict[str, datetime] = self._load_state()

    def _load_state(self) -> Dict[str, datetime]:
        if os.path.exists(self.storage_path):
            with open(self.storage_path) as f:
                data = json.load(f)
                return {
                    curr: datetime.fromisoformat(ts)
                    for curr, ts in data.get("last_exit", {}).items()
                }
        return {}

    def _save_state(self):
        data = {
            "last_exit": {
                curr: dt.isoformat()
                for curr, dt in self.last_exit.items()
            }
        }
        with open(self.storage_path, "w") as f:
            json.dump(data, f, indent=2)

    def record_exit(self, instrument: str, exit_time: datetime = None):
        """
        ⭐ 出场时调用此方法记录冷却
        :param instrument: "AUD_JPY" 格式
        """
        if "_" not in instrument:
            return
        base, quote = instrument.split("_")
        t = exit_time or datetime.utcnow()
        self.last_exit[base] = t
        self.last_exit[quote] = t
        self._save_state()
        print(f"🔒 COOLDOWN: 记录 {instrument} 出场 → {base}, {quote} 进入 {self.cooldown_hours}h 冷却")

    def is_in_cooldown(self, currency: str) -> tuple[bool, float]:
        if currency not in self.last_exit:
            return False, 0.0
        elapsed = (datetime.utcnow() - self.last_exit[currency]).total_seconds() / 3600
        remaining = self.cooldown_hours - elapsed
        return (True, round(remaining, 1)) if remaining > 0 else (False, 0.0)

    def pair_cooldown_status(self, base: str, quote: str) -> tuple[bool, str]:
        cd_base, rem_base = self.is_in_cooldown(base)
        cd_quote, rem_quote = self.is_in_cooldown(quote)
        if cd_base:
            return True, f"{base} 剩余 {rem_base}h"
        if cd_quote:
            return True, f"{quote} 剩余 {rem_quote}h"
        return False, ""