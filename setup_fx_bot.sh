#!/usr/bin/env bash
set -euo pipefail

echo "=========================================="
echo "  🚀 Creating fx_bot Modular Architecture"
echo "=========================================="

# ── Create directory structure ──────────────
mkdir -p fx_bot/{config,risk,execution,utils,monte_carlo}

echo "✅ Directory structure created"

# ── fx_bot/__init__.py ─────────────────────
cat > fx_bot/__init__.py << 'EOF'
"""Forex Trading Bot — OANDA v7 API Hybrid SL/TP Strategy"""
__version__ = "0.2.0-refactored"
EOF

# ── config/__init__.py ─────────────────────
cat > fx_bot/config/__init__.py << 'EOF'
from .constants import OrderSide, PositionSide, InstrumentType
from .settings import settings

__all__ = ["OrderSide", "PositionSide", "InstrumentType", "settings"]
EOF

# ── config/constants.py ─────────────────────
cat > fx_bot/config/constants.py << 'EOF'
from enum import Enum

class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

class PositionSide(str, Enum):
    LONG = "long"
    SHORT = "short"

class InstrumentType(str, Enum):
    JPY_PAIR = "JPY_PAIR"
    OTHER = "OTHER"

# Price precision & pip sizing
PRICE_DECIMALS = {
    InstrumentType.JPY_PAIR: 3,
    InstrumentType.OTHER: 5,
}
PIP_SIZE = {
    InstrumentType.JPY_PAIR: 0.01,
    InstrumentType.OTHER: 0.0001,
}

# Risk defaults
ATR_SL_MULTIPLIER = 2.0
DEFAULT_SL_OFFSET_PIPS = 20
DEFAULT_SL_MAX_PIPS = 200
DEFAULT_REQUIRED_H4 = 4

# Timezone
LONDON_TZ = "Europe/London"
EOF

# ── config/settings.py ─────────────────────
cat > fx_bot/config/settings.py << 'EOF'
import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

class Settings:
    OANDA_API_TOKEN: str = os.getenv("OANDA_API_TOKEN", "")
    OANDA_ACCOUNT_ID: str = os.getenv("OANDA_ACCOUNT_ID", "")
    OANDA_ENV: str = os.getenv("OANDA_ENV", "practice")

    DRY_RUN: bool = os.getenv("DRY_RUN", "1").lower() in ("1", "true", "yes")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

    BASE_DIR: Path = Path(__file__).resolve().parent.parent

settings = Settings()
EOF

# ── risk/__init__.py ───────────────────────
cat > fx_bot/risk/__init__.py << 'EOF'
from .sl_tp_calculator import RiskCalculator

__all__ = ["RiskCalculator"]
EOF

# ── risk/sl_tp_calculator.py ───────────────
cat > fx_bot/risk/sl_tp_calculator.py << 'EOF'
import logging
from typing import Tuple, Optional, Dict, List
from fx_bot.config.constants import (
    OrderSide, ATR_SL_MULTIPLIER, PRICE_DECIMALS, PIP_SIZE,
    InstrumentType, DEFAULT_SL_OFFSET_PIPS, DEFAULT_SL_MAX_PIPS, DEFAULT_REQUIRED_H4
)

logger = logging.getLogger(__name__)

class RiskCalculator:
    def __init__(
        self,
        sl_offset_pips: int = DEFAULT_SL_OFFSET_PIPS,
        sl_max_allowed_pips: int = DEFAULT_SL_MAX_PIPS,
        required_h4_candles: int = DEFAULT_REQUIRED_H4,
    ):
        self.sl_offset_pips = sl_offset_pips
        self.sl_max_allowed_pips = sl_max_allowed_pips
        self.required_h4_candles = required_h4_candles

    @staticmethod
    def _instrument_type(instrument: str) -> InstrumentType:
        return InstrumentType.JPY_PAIR if "JPY" in instrument.upper() else InstrumentType.OTHER

    @staticmethod
    def get_price_decimals(pair: str) -> int:
        return PRICE_DECIMALS[RiskCalculator._instrument_type(pair)]

    @staticmethod
    def get_pip_size(pair: str) -> float:
        return PIP_SIZE[RiskCalculator._instrument_type(pair)]

    def calculate_stop_loss(
        self,
        side: OrderSide,
        entry_price: float,
        h4_candles: List[Dict[str, float]],
        pip_sz: float,
    ) -> Tuple[float, float, bool]:
        if len(h4_candles) < self.required_h4_candles:
            raise ValueError(
                f"H4 candle count insufficient: need ≥{self.required_h4_candles}, got {len(h4_candles)}"
            )

        if side == OrderSide.SELL:
            ref_level = max(c["high"] for c in h4_candles)
            sl_price = ref_level + (self.sl_offset_pips * pip_sz)
        else:
            ref_level = min(c["low"] for c in h4_candles)
            sl_price = ref_level - (self.sl_offset_pips * pip_sz)

        sl_pips = abs(sl_price - entry_price) / pip_sz
        skip_trade = sl_pips > self.sl_max_allowed_pips

        if skip_trade:
            logger.warning(
                f"SL TOO LARGE — ABORT | Side: {side.value} | "
                f"Distance: {sl_pips:.1f} pips | MAX: {self.sl_max_allowed_pips}"
            )
        return sl_price, sl_pips, skip_trade

    def calculate_hybrid_sl(
        self,
        instrument: str,
        direction: OrderSide,
        entry_price: float,
        h4_closed: List[Dict[str, float]],
        atr_value: float,
    ) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float], str, bool]:
        """Returns: (sl_price, h4_pips, atr_pips, chosen_pips, method, skip_trade)"""
        pip_sz = self.get_pip_size(instrument)
        decimals = self.get_price_decimals(instrument)

        h4_sl: Optional[float] = None
        h4_pips: Optional[float] = None
        atr_sl: Optional[float] = None
        atr_pips: Optional[float] = None
        h4_skip = atr_skip = False

        try:
            h4_sl, h4_pips, h4_skip = self.calculate_stop_loss(direction, entry_price, h4_closed, pip_sz)
            h4_sl = round(h4_sl, decimals)
        except Exception as e:
            logger.exception(f"H4 SL failed {instrument}: {e}")
            h4_skip = True

        try:
            atr_offset = atr_value * ATR_SL_MULTIPLIER
            if direction == OrderSide.BUY:
                atr_sl = round(entry_price - atr_offset, decimals)
            else:
                atr_sl = round(entry_price + atr_offset, decimals)
            atr_pips = atr_offset / pip_sz
            atr_skip = atr_pips > self.sl_max_allowed_pips
        except Exception as e:
            logger.exception(f"ATR SL failed {instrument}: {e}")
            atr_skip = True

        if h4_sl is None and atr_sl is None:
            return None, None, None, None, "NONE", True
        if h4_sl is None:
            return atr_sl, None, atr_pips, atr_pips, "ATR", atr_skip
        if atr_sl is None:
            return h4_sl, h4_pips, None, h4_pips, "H4", h4_skip

        if direction == OrderSide.BUY:
            if h4_sl >= atr_sl:
                return h4_sl, h4_pips, atr_pips, h4_pips, "H4", h4_skip
            return atr_sl, h4_pips, atr_pips, atr_pips, "ATR-GUARD", atr_skip
        else:
            if h4_sl <= atr_sl:
                return h4_sl, h4_pips, atr_pips, h4_pips, "H4", h4_skip
            return atr_sl, h4_pips, atr_pips, atr_pips, "ATR-GUARD", atr_skip
EOF

# ── execution/__init__.py ───────────────────
cat > fx_bot/execution/__init__.py << 'EOF'
from .oanda_client import OandaClient
from .order_manager import OrderManager

__all__ = ["OandaClient", "OrderManager"]
EOF

# ── execution/oanda_client.py ──────────────
cat > fx_bot/execution/oanda_client.py << 'EOF'
import logging
import pandas as pd
from oandapyV20.endpoints.instruments import InstrumentsCandles
from oandapyV20.endpoints.accounts import AccountDetails

logger = logging.getLogger(__name__)

class OandaClient:
    def __init__(self, api_context, account_id: str):
        self.api = api_context
        self.account_id = account_id

    def fetch_candles(self, instrument: str, granularity: str, count: int = 100) -> pd.DataFrame:
        req = InstrumentsCandles(
            instrument=instrument,
            params={"granularity": granularity, "count": count, "price": "M"},
        )
        resp = self.api.request(req)
        df = pd.DataFrame([
            {
                "Time": c["time"],
                "Open": float(c["mid"]["o"]),
                "High": float(c["mid"]["h"]),
                "Low": float(c["mid"]["l"]),
                "Close": float(c["mid"]["c"]),
            }
            for c in resp["candles"]
        ]).set_index("Time")
        return df

    def get_account_equity(self) -> float:
        try:
            resp = self.api.request(AccountDetails(accountID=self.account_id))
            return float(resp["account"]["balance"])
        except Exception as e:
            logger.warning(f"Could not fetch equity: {e}, using fallback 10000.0")
            return 10000.0
EOF

# ── execution/order_manager.py ─────────────
cat > fx_bot/execution/order_manager.py << 'EOF'
import logging
from typing import Dict, Any, Optional
from oandapyV20.endpoints.positions import PositionDetails
from oandapyV20.endpoints.orders import OrderCreate
from oandapyV20.endpoints.trades import TradeCRCDO

from fx_bot.config.constants import OrderSide
from fx_bot.risk.sl_tp_calculator import RiskCalculator

logger = logging.getLogger(__name__)

class OrderManager:
    def __init__(self, oanda_client, risk_calculator: Optional[RiskCalculator] = None, dry_run: bool = False):
        self.client = oanda_client.api
        self.account_id = oanda_client.account_id
        self.risk_calc = risk_calculator or RiskCalculator()
        self.dry_run = dry_run

    def get_open_position(self, instrument: str) -> Optional[Dict[str, Any]]:
        try:
            resp = self.client.request(PositionDetails(accountID=self.account_id, instrument=instrument))
            pos = resp.get("position", {})
            long_units = int(pos.get("long", {}).get("units", "0"))
            short_units = int(pos.get("short", {}).get("units", "0"))
            if long_units != 0:
                return {"units": long_units, "side": "long"}
            if short_units != 0:
                return {"units": -short_units, "side": "short"}
            return None
        except Exception as e:
            if "NO_SUCH_POSITION" in str(e) or "404" in str(e):
                return None
            logger.warning(f"Position check failed for {instrument}: {e}")
            return None

    def close_position(self, instrument: str) -> bool:
        if self.dry_run:
            logger.info(f"🧊 DRY-RUN — would CLOSE: {instrument}")
            return True
        try:
            pos = self.get_open_position(instrument)
            if not pos:
                logger.info(f"No position to close: {instrument}")
                return False
            units_to_close = -pos["units"]
            order_data = {
                "order": {
                    "type": "MARKET",
                    "instrument": instrument,
                    "units": str(units_to_close),
                    "positionFill": "REDUCE_ONLY",
                }
            }
            self.client.request(OrderCreate(accountID=self.account_id, data=order_data))
            logger.info(f"Closed position for {instrument}")
            return True
        except Exception as e:
            logger.error(f"Close failed for {instrument}: {e}")
            return False

    def open_order(
        self,
        instrument: str,
        direction: OrderSide | str,
        units: int,
        sl_price: Optional[float] = None,
        tp_price: Optional[float] = None,
        tag: str = "",
        client_id: str = "",
        comment: str = "",
    ) -> Dict[str, Any]:
        dec = self.risk_calc.get_price_decimals(instrument)
        direction_side = OrderSide(direction.upper())
        signed_units = abs(units) if direction_side == OrderSide.BUY else -abs(units)

        if self.dry_run:
            logger.info(f"DRY-RUN — OPEN: {instrument} {direction_side.value} | SL={sl_price} TP={tp_price}")
            return {"ok": True, "status": "DRY_RUN", "instrument": instrument}

        payload = {
            "order": {
                "type": "MARKET",
                "instrument": instrument,
                "units": str(signed_units),
                "positionFill": "DEFAULT",
            }
        }

        client_ext = {k: v for k, v in [("id", client_id), ("tag", tag), ("comment", comment)] if v}
        if client_ext:
            payload["order"]["clientExtensions"] = client_ext

        try:
            resp = self.client.request(OrderCreate(accountID=self.account_id, data=payload))
            trade_id = ""
            if "orderFillTransaction" in resp:
                trade_id = str(resp["orderFillTransaction"].get("tradeOpened", {}).get("tradeID", ""))
            elif "orderCreateTransaction" in resp:
                trade_id = str(resp["orderCreateTransaction"].get("id", ""))
            if not trade_id:
                return {"ok": False, "status": "ERROR", "message": "TradeID missing"}

            if sl_price is not None:
                sl_data = {
                    "order": {
                        "type": "STOP_LOSS", "tradeID": trade_id,
                        "price": f"{sl_price:.{dec}f}", "timeInForce": "GTC",
                    }
                }
                self.client.request(OrderCreate(accountID=self.account_id, data=sl_data))
            if tp_price is not None:
                tp_data = {
                    "order": {
                        "type": "TAKE_PROFIT", "tradeID": trade_id,
                        "price": f"{tp_price:.{dec}f}", "timeInForce": "GTC",
                    }
                }
                self.client.request(OrderCreate(accountID=self.account_id, data=tp_data))

            return {"ok": True, "status": "OK", "trade_id": trade_id, "response": resp}
        except Exception as e:
            logger.error(f"FAILED to open order for {instrument}: {e}")
            return {"ok": False, "status": "ERROR", "message": str(e)}

    def update_trade_tp(self, trade_id: str, instrument: str, new_tp_price: float) -> Dict[str, Any]:
        dec = self.risk_calc.get_price_decimals(instrument)
        new_tp_str = f"{new_tp_price:.{dec}f}"
        if self.dry_run:
            logger.info(f"DRY-RUN — UPDATE TP: {instrument} trade={trade_id} → {new_tp_str}")
            return {"ok": True, "status": "DRY_RUN", "new_tp": new_tp_price}
        try:
            data = {"takeProfit": {"price": new_tp_str, "timeInForce": "GTC"}}
            resp = self.client.request(TradeCRCDO(accountID=self.account_id, tradeID=trade_id, data=data))
            return {"ok": True, "status": "UPDATED", "response": resp}
        except Exception as e:
            logger.error(f"TP update failed for {instrument}: {e}")
            return {"ok": False, "status": "ERROR", "message": str(e)}
EOF

# ── utils/__init__.py ───────────────────────
cat > fx_bot/utils/__init__.py << 'EOF'
from .market_guard import MarketGuard
from .notifier import TelegramReporter

__all__ = ["MarketGuard", "TelegramReporter"]
EOF

# ── utils/market_guard.py ──────────────────
cat > fx_bot/utils/market_guard.py << 'EOF'
import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Dict, Tuple

from fx_bot.config.constants import LONDON_TZ, PositionSide

class MarketGuard:
    @staticmethod
    def is_forex_closed_schedule() -> bool:
        now = datetime.now(tz=ZoneInfo(LONDON_TZ))
        wd = now.weekday()
        return wd == 5 or (wd == 6 and now.hour < 21) or (wd == 4 and now.hour >= 21)

    @staticmethod
    def load_cooldown(cooldown_file: Path, direction_enum):
        if cooldown_file.exists():
            with open(cooldown_file, "r", encoding="utf-8") as f:
                raw = json.load(f)
            return {k: (direction_enum(v[0]), v[1]) for k, v in raw.items()}
        return {}

    @staticmethod
    def save_cooldown(cooldown_file: Path, state: Dict):
        serializable = {k: (v[0].value, v[1]) for k, v in state.items()}
        with open(cooldown_file, "w", encoding="utf-8") as f:
            json.dump(serializable, f, ensure_ascii=False, indent=2)

    @staticmethod
    def should_close_by_strength(pair: str, side: str, strength_scores: Dict[str, float], threshold: float = 1.0) -> Tuple[bool, str]:
        clean = pair.replace("=X", "").replace("_", "")
        if len(clean) != 6:
            return False, ""
        base, quote = clean[:3], clean[3:]
        base_score = strength_scores.get(base, 0.0)
        quote_score = strength_scores.get(quote, 0.0)
        gap = base_score - quote_score
        if side.lower() == PositionSide.LONG and -gap > threshold:
            return True, f"Strength flip: {quote} (+{quote_score:.2f}) > {base} ({base_score:.2f})"
        if side.lower() == PositionSide.SHORT and gap > threshold:
            return True, f"Strength flip: {base} (+{base_score:.2f}) > {quote} ({quote_score:.2f})"
        return False, ""
EOF

# ── utils/notifier.py ──────────────────────
cat > fx_bot/utils/notifier.py << 'EOF'
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

class TelegramReporter:
    @staticmethod
    def build_mc_report(mc_results: List[Dict[str, Any]], title: str, tf: str, lookback: int, forecast: int, sims: int) -> str:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        lines = [
            f"📊 **{title}**",
            f"📅 Generated: {now}",
            f"🔹 TF: {tf} | Lookback: {lookback} | Forecast: {forecast} | Sims: {sims}\n",
        ]
        for r in mc_results:
            lo, hi = r.get("range_90", (0, 0))
            lines.extend([
                f"🔹 **{r['pair']}**",
                f"   💵 Last Close: `{r['current_price']}`",
                f"   🎯 UP: `{r['p_up_pct']}%` | DOWN: `{r['p_down_pct']}%`",
                f"   📏 90% Band: `{lo}` – `{hi}`",
                "",
            ])
        return "\n".join(lines)

    @staticmethod
    def build_trade_summary(trade_lines: List[str], mc_summary: Optional[List[str]] = None) -> str:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        lines = [f"🤖 MULTI‑PAIR UPDATE — {now}"] + trade_lines
        if mc_summary:
            lines.extend(["", "📊 *MC Context:*"] + [f"   {s}" for s in mc_summary])
        return "\n".join(lines)
EOF

# ── monte_carlo/__init__.py ─────────────────
cat > fx_bot/monte_carlo/__init__.py << 'EOF'
# Monte Carlo simulation package placeholder
EOF

# ── main.py ────────────────────────────────
cat > fx_bot/main.py << 'EOF'
import logging
from fx_bot.config.settings import settings
from oandapyV20 import API

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)

def main():
    logger.info("✅ Bot started (refactored architecture)")
    api = API(access_token=settings.OANDA_API_TOKEN, environment=settings.OANDA_ENV)
    logger.info(f"Account: {settings.OANDA_ACCOUNT_ID} | Dry-run: {settings.DRY_RUN}")

if __name__ == "__main__":
    main()
EOF

# ── .env.example ───────────────────────────
cat > fx_bot/.env.example << 'EOF'
OANDA_API_TOKEN=your_token_here
OANDA_ACCOUNT_ID=your_account_id
OANDA_ENV=practice
DRY_RUN=1
LOG_LEVEL=INFO
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
EOF

echo ""
echo "✅ All files generated!"
echo ""
echo "📁 Structure:"
tree fx_bot -L 3 --dirsfirst 2>/dev/null || find fx_bot -type f | sort
echo ""
echo "📋 Next steps:"
echo "  1. cp fx_bot/.env.example .env     # copy env config"
echo "  2. vi .env                          # fill in your tokens"
echo "  3. pip install oandapyv20 pandas python-dotenv"
echo "  4. python -m fx_bot.main"
echo "
