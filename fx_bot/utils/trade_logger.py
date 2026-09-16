"""
交易记录器 — 按货币对(instrument) 分文件记录 开仓/平仓/改单/平仓原因

输出: daily_results_{profile}/trade_log_{pair}.csv
  · 文件名只含货币对信息，不含日期 —— 日期由外层迭代分日归档
  · 配对 naming: USD_JPY → usdjpy （对齐 analyze_v1.py 的扫描约定）
  · 兼容下游: fx_bot/analyze_v1.py 自动扫描 daily_results_*/trade_log_*.csv
"""
import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.config.settings import Settings

logger = logging.getLogger(__name__)

FIELDS = [
    "timestamp", "trade_id", "tag", "instrument", "direction", "units",
    "open_price", "close_price", "sl", "tp",
    "status", "close_reason", "pl",
    "reason", "score_final",        # ✅ 决策快照：开仓理由+当时综合分
]

# fx_bot/utils/trade_logger.py → parent.parent = .../fx_bot
_FX_BOT_DIR = Path(__file__).resolve().parent.parent


def _profile_slug(settings: Settings) -> str:
    """PROFILE-2/3/4 → profile2/3/4 （用于 daily_results_{profile} 目录）"""
    name = settings.profile_name
    if "PROFILE-4" in name:
        return "profile4"
    if "PROFILE-3" in name:
        return "profile3"
    return "profile2"


class TradeLogger:
    def __init__(self, settings: Settings, results_dir: Optional[Path] = None,
                 filename_prefix: str = "trade_log_"):
        self.settings = settings
        if results_dir is None:
            results_dir = _FX_BOT_DIR / f"daily_results_{_profile_slug(settings)}"
        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.filename_prefix = filename_prefix

    # ── 路径/命名 helpers ────────────────────────────────────────────────

    @staticmethod
    def pair_name(instrument: str) -> str:
        """货币对 short 名（仅货币对，无日期）: USD_JPY → usdjpy"""
        return str(instrument).replace("_", "").lower()

    def csv_path(self, instrument: str) -> Path:
        """daily_results_{profile}/{prefix}{pair}.csv  (prefix default: trade_log_)"""
        return self.results_dir / f"{self.filename_prefix}{self.pair_name(instrument)}.csv"

    def _init_file(self, path: Path):
        if not path.exists():
            with open(path, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=FIELDS)
                w.writeheader()
            logger.info(f"📁 交易日志初始化: {path}")

    # ── 记录入口 ─────────────────────────────────────────────────────────

    def record_open(self, trade_id, instrument, direction, units, price, sl, tp,
                    tag="", reason="", score_final=""):
        """记录开仓 — 写入对应货币对文件（tag 用于归属识别）

        Args:
            tag:          归属标签（TAG matching 用）
            reason:       开仓理由一句话 ≤50字，例如 "H1多+RSI超卖+低波动"
            score_final:  当时综合分 0-100，用于事后相关性/阈值分析
        """
        path = self.csv_path(instrument)
        self._init_file(path)
        row = {
            "timestamp": datetime.utcnow().isoformat(),
            "trade_id": trade_id,
            "tag": tag,
            "instrument": instrument,
            "direction": direction,
            "units": units,
            "open_price": price,
            "sl": sl,
            "tp": tp,
            "status": "OPEN",
            "reason": reason,              # ✅ 决策快照
            "score_final": score_final,     # ✅ 决策快照
        }
        self._append(path, row)
        logger.info(f"📝 开仓记录: {instrument} {direction} trade={trade_id} score={score_final} → {path}")

    def record_close(self, trade_id, instrument, close_price, reason, pl=0.0):
        """更新平仓记录 — 填入价格、原因、盈亏（对应货币对文件）"""
        path = self.csv_path(instrument)
        rows = self._read_all(path)
        found = False
        for r in rows:
            if r["trade_id"] == str(trade_id) and r["status"] == "OPEN":
                r["close_price"] = close_price
                r["status"] = "CLOSED"
                r["close_reason"] = reason
                r["pl"] = f"{pl:.2f}"
                found = True
                break
        if found:
            self._write_all(path, rows)
            logger.info(f"📝 平仓记录 trade={trade_id} 原因={reason} → {path}")
        else:
            logger.warning(f"⚠️ 找不到开仓记录 trade_id={trade_id} ({path})")

    def record_modify(self, trade_id, new_sl, new_tp):
        """记录改单 — 仅日志，不改动CSV"""
        logger.info(f"📝 改单记录 trade={trade_id} → SL={new_sl} TP={new_tp}")

    # ── 底层 IO ──────────────────────────────────────────────────────────

    def _append(self, path: Path, row):
        rows = self._read_all(path)
        rows.append(row)
        self._write_all(path, rows)

    def _read_all(self, path: Path):
        if not path.exists():
            return []
        with open(path, "r", newline="") as f:
            return list(csv.DictReader(f))

    def _write_all(self, path: Path, rows):
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(rows)