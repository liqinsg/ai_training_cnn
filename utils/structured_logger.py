#!/usr/bin/env python3
"""结构化日志 — 区分主动(BOT)/被动(OANDA)操作"""
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


def _safe_profile_name(name: str) -> str:
    """把 profile 名转成安全的文件名片段。

    处理 '/'、'\\'、空格、'.' 等可能被当作路径分隔符或非法字符的符号，
    避免如 'PF-D Structure/D-Gate' 被拼成子目录路径。
    """
    return re.sub(r"[^\w\-]+", "_", name.strip().lower()).strip("_")


class StructuredLogger:
    def __init__(self, name: str):
        self.name = name
        self.filepath = LOG_DIR / f"profile_{_safe_profile_name(name)}.jsonl"
        self._known_trades: Dict[str, Dict[str, Any]] = {}

    def _write(self, record: Dict[str, Any]) -> None:
        record.setdefault("ts", datetime.utcnow().isoformat(timespec="seconds") + "Z")
        record.setdefault("profile", self.name)
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(self.filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # ── 主动操作 ──
    def bot_open(
        self,
        pair: str,
        direction: str,
        units: int,
        entry_price: float,
        trade_id: str,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        score_final: Optional[float] = None,
        **extra,
    ) -> None:
        rec = {
            "type": "BOT_OPEN",
            "op_source": "BOT",
            "pair": pair,
            "direction": direction,
            "units": units,
            "entry_price": entry_price,
            "trade_id": trade_id,
            "sl": sl,
            "tp": tp,
            "score_final": score_final,
            **extra,
        }
        self._known_trades[trade_id] = rec
        self._write(rec)

    def bot_close(
        self,
        pair: str,
        reason: str,
        units: int,
        exit_price: float,
        pnl: float,
        trade_id: str,
        **extra,
    ) -> None:
        self._known_trades.pop(trade_id, None)
        self._write(
            {
                "type": "BOT_CLOSE",
                "op_source": "BOT",
                "pair": pair,
                "reason": reason,
                "units": units,
                "exit_price": exit_price,
                "pnl": pnl,
                "trade_id": trade_id,
                **extra,
            }
        )

    def bot_update_sl(
        self,
        pair: str,
        trade_id: str,
        old_sl: float,
        new_sl: float,
        update_type: str = "TRAILING",
        **extra,
    ) -> None:
        self._write(
            {
                "type": "BOT_UPDATE_SL",
                "op_source": "BOT",
                "pair": pair,
                "trade_id": trade_id,
                "old_sl": old_sl,
                "new_sl": new_sl,
                "update_type": update_type,
                **extra,
            }
        )

    def bot_update_tp(
        self,
        pair: str,
        trade_id: str,
        old_tp: Optional[float],
        new_tp: float,
        update_type: str = "DYNAMIC_TP",
        **extra,
    ) -> None:
        self._write(
            {
                "type": "BOT_UPDATE_TP",
                "op_source": "BOT",
                "pair": pair,
                "trade_id": trade_id,
                "old_tp": old_tp,
                "new_tp": new_tp,
                "update_type": update_type,
                **extra,
            }
        )

    def skip_signal(self, pair: str, reason: str, **extra) -> None:
        self._write(
            {
                "type": "SKIP",
                "op_source": "BOT",
                "pair": pair,
                "reason": reason,
                **extra,
            }
        )

    # ── 被动平仓检测 ──
    def oanda_close_detected(
        self,
        pair: str,
        trade_id: str,
        reason_detected: str,
        pnl: Optional[float] = None,
        exit_price: Optional[float] = None,
        **extra,
    ) -> None:
        prior = self._known_trades.pop(trade_id, {})
        self._write(
            {
                "type": "OANDA_CLOSE",
                "op_source": "OANDA",
                "pair": prior.get("pair", pair),
                "trade_id": trade_id,
                "reason_detected": reason_detected,
                "pnl": pnl,
                "exit_price": exit_price,
                "entry_price_from_open": prior.get("entry_price"),
                "note": "Detected next run — triggered server-side",
                **extra,
            }
        )

    def get_known_trade_ids(self) -> List[str]:
        return list(self._known_trades.keys())

    def positions_snapshot(
        self,
        positions: List[Dict[str, Any]],
        source: str = "OANDA_QUERY",
        **extra,
    ) -> None:
        self._write(
            {
                "type": "POSITIONS_SNAPSHOT",
                "op_source": "BOT",
                "snapshot_source": source,
                "count": len(positions),
                "positions": positions,
                **extra,
            }
        )