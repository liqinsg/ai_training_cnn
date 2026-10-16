#!/usr/bin/env python3
"""出场冷却追踪 — 主动记录版，适配市价/TP/SL所有出场方式"""

import os
from datetime import datetime
from typing import Dict, Set


class TPCooldownTracker:
    def __init__(self, cooldown_hours: float = 2.0, storage_path: str = "tp_cooldown.json"):
        self.cooldown_hours = cooldown_hours
        self.storage_path = storage_path
        self.last_exit: Dict[str, datetime] = self._load()

    def _load(self) -> Dict[str, datetime]:
        if os.path.exists(self.storage_path):
            import json
            with open(self.storage_path, "r") as f:
                data = json.load(f)
            return {
                curr: datetime.fromisoformat(ts)
                for curr, ts in data.get("last_exit", {}).items()
            }
        return {}

    def _save(self):
        import json
        data = {
            "last_exit": {
                curr: dt.isoformat()
                for curr, dt in self.last_exit.items()
            }
        }
        with open(self.storage_path, "w") as f:
            json.dump(data, f, indent=2)

    def record_exit(self, instrument: str, exit_time: datetime = None):
        """每平仓一个交易对时调用 — 记录该币种进入冷却"""
        if "_" not in instrument:
            return
        base, quote = instrument.split("_")
        t = exit_time or datetime.utcnow()
        self.last_exit[base] = t
        self.last_exit[quote] = t
        self._save()
        print(f"🔒 [冷却] 记录 {instrument} 出场 → {base}, {quote} 锁定 {self.cooldown_hours}h")

    def is_in_cooldown(self, currency: str) -> tuple[bool, float]:
        """检查单个币种是否在冷却期内 → 返回(是否锁定, 剩余小时)"""
        if currency not in self.last_exit:
            return False, 0.0
        elapsed = (datetime.utcnow() - self.last_exit[currency]).total_seconds() / 3600
        remaining = self.cooldown_hours - elapsed
        return (remaining > 0, round(max(0, remaining), 1))

    def check_pair(self, base: str, quote: str) -> tuple[bool, str]:
        """检查交易对是否可开仓 → 返回(是否锁定, 提示信息)"""
        cd_base, rem_base = self.is_in_cooldown(base)
        cd_quote, rem_quote = self.is_in_cooldown(quote)
        
        if cd_base:
            return True, f"{base} 剩余 {rem_base}h"
        if cd_quote:
            return True, f"{quote} 剩余 {rem_quote}h"
        return False, "✅ 可开仓"


# 全局实例
cooldown = TPCooldownTracker(cooldown_hours=2.0)