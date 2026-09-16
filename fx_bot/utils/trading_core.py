"""
交易核心 — 整合两套代码精华
来源：fx_trade_bot_utils.py + trading_core.py
新架构：全部通过 Settings + OandaClient 注入，不引用任何老配置
"""
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import json
import numpy as np
import pandas as pd
import oandapyV20

from core.config.settings import Settings
from execution.oanda_client import OandaClient

logger = logging.getLogger(__name__)

# ==================================================
# ⚙️ 常量（统一放这里，不分散）
# ==================================================
SL_OFFSET_PIPS = 20
SL_MAX_ALLOWED_PIPS = 200
REQUIRED_H4_CANDLES = 4

# ==================================================
# 💰 价格/货币对工具
# ==================================================
def price_decimals(pair: str) -> int:
    return 3 if "JPY" in pair.upper() else 5

def pip_size(pair: str) -> float:
    return 0.01 if "JPY" in pair.upper() else 0.0001

def format_price(price, instrument: str) -> str:
    try:
        n = float(price)
        return f"{n:.3f}" if instrument.endswith("_JPY") else f"{n:.5f}"
    except (TypeError, ValueError):
        return str(price)

# ==================================================
# 📊 K线/价格获取（两套方法合并，统一入口）
# ==================================================
def fetch_candles(
    oanda: OandaClient,
    instrument: str,
    granularity: str = "H1",
    count: int = 100,
    as_df: bool = True
):
    """获取K线 — 返回DataFrame(默认)或原始列表"""
    df = oanda.fetch_candles(instrument, granularity, count)
    if as_df:
        return df
    # 返回原始格式兼容旧代码
    return [
        {
            "time": idx,
            "mid": {"o": row.Open, "h": row.High, "l": row.Low, "c": row.Close},
            "complete": True
        }
        for idx, row in df.iterrows()
    ]

def get_latest_price(oanda: OandaClient, instrument: str) -> float | None:
    """获取最新中间价"""
    try:
        return oanda.get_account_equity()  # 临时占位 — 补充 pricing 接口后替换
    except Exception as e:
        logger.warning(f"价格获取失败: {e}")
        return None

def get_recent_range(oanda: OandaClient, instrument: str, gran="H1", lookback=20):
    """近期高低位 + 现价"""
    candles = fetch_candles(oanda, instrument, gran, lookback + 1, as_df=False)
    closed = [c for c in candles if c.get("complete", True)]
    if len(closed) < lookback:
        return None
    highs = [float(c["mid"]["h"]) for c in closed[:-1]]
    lows = [float(c["mid"]["l"]) for c in closed[:-1]]
    close = float(closed[-1]["mid"]["c"])
    return max(highs), min(lows), close

# ==================================================
# 🛡️ 止损计算 — H4 + ATR 双保险（精华算法）
# ==================================================
def calculate_stop_loss(side: str, entry_price: float, h4_candles, pip_sz, instrument=""):
    """H4高低位 + 20点缓冲 → 返回 SL、点数、是否放弃"""
    if len(h4_candles) < REQUIRED_H4_CANDLES:
        raise ValueError(f"需至少{REQUIRED_H4_CANDLES}根H4K线")
    dec = price_decimals(instrument)
    if side.upper() == "BUY":
        ref = min(float(c["Low"]) if isinstance(c,dict) else c.Low for c in h4_candles)
        sl = round(ref - SL_OFFSET_PIPS * pip_sz, dec)
    else:
        ref = max(float(c["High"]) if isinstance(c,dict) else c.High for c in h4_candles)
        sl = round(ref + SL_OFFSET_PIPS * pip_sz, dec)
    pips = abs(entry_price - sl) / pip_sz
    skip = pips > (500 if "JPY" in instrument.upper() else 50)
    logger.info(f"📏 SL={sl} ({pips:.1f}点) | {'超限放弃' if skip else 'OK'}")
    return sl, pips, skip

def calculate_hybrid_sl(instrument, direction, entry, h4_closed, atr_2x, pip_sz):
    """H4止损 × ATR止损 → 自动选更近、更保守的"""
    dec = price_decimals(instrument)
    h4_sl = h4_pips = h4_skip = None
    try:
        h4_sl, h4_pips, h4_skip = calculate_stop_loss(direction, entry, h4_closed, pip_sz, instrument)
    except Exception as e:
        logger.warning(f"H4止损跳过: {e}")

    if direction == "BUY":
        atr_sl = round(entry - atr_2x, dec)
    else:
        atr_sl = round(entry + atr_2x, dec)
    atr_pips = atr_2x / pip_sz
    atr_skip = atr_pips > SL_MAX_ALLOWED_PIPS

    # 选更近的
    if h4_sl is None:
        return atr_sl, None, atr_sl, "ATR", atr_pips, atr_skip
    if direction == "BUY":
        chosen_h4 = h4_sl >= atr_sl
    else:
        chosen_h4 = h4_sl <= atr_sl

    if chosen_h4:
        return h4_sl, h4_sl, atr_sl, "H4", h4_pips, h4_skip
    return atr_sl, h4_sl, atr_sl, "ATR-GUARD", atr_pips, atr_skip

# ==================================================
# 🌍 市场休市（统一逻辑）
# ==================================================
def forex_market_closed() -> bool:
    """伦敦时间判断休市：周五21:00后 ~ 周日21:00前"""
    now = datetime.now(ZoneInfo("Europe/London"))
    wd = now.weekday()
    closed = (wd == 5) or (wd == 6 and now.hour < 21) or (wd == 4 and now.hour >= 21)
    if closed:
        logger.info("🌍 市场休市中")
    return closed

# ==================================================
# 📋 持仓/交易查询（统一接口）
# ==================================================
def get_open_position(oanda: OandaClient, instrument: str):
    """查指定持仓 → 返回标准化格式 {units, side} 或 None"""
    return oanda.get_open_position(instrument)

def get_close_reason(oanda: OandaClient, trade_id: str) -> str:
    """【关键】通过 Trade API 查询平仓原因 — 可追溯 SL/TP/手动/到期"""
    try:
        resp = oanda.api.request(
            oandapyV20.endpoints.trades.TradeDetails(
                accountID=oanda.account_id, tradeID=trade_id
            )
        )
        trade = resp.get("trade", {})
        state = trade.get("state", "ACTIVE")
        close_tx = trade.get("closingTransactionID", "")

        if state == "CLOSED":
            reason = trade.get("closeReason", "")
            mapping = {
                "STOP_LOSS_ORDER": "STOP_LOSS",
                "TAKE_PROFIT_ORDER": "TAKE_PROFIT",
                "CLIENT_ORDER": "CLIENT_CLOSE",
                "PARTIAL_CLOSE": "PARTIAL",
            }
            return mapping.get(reason, reason or "UNKNOWN")
        return "ACTIVE"
    except Exception as e:
        if "NO_SUCH_TRADE" in str(e):
            # 刚手动平仓 → trade 不在可查范围内，属正常，不警告
            return "CLIENT_CLOSE"
        logger.warning(f"平仓原因查询失败 trade_id={trade_id}: {e}")
        return "UNKNOWN"

# ==================================================
# 🤝 开仓/平仓 — 统一入口、两种执行模式
# ==================================================
def open_position_stepwise(
    oanda: OandaClient, instrument: str, direction: str, units: int, sl, tp, tag="", dry_run=False
):
    """模式A：先市价入场 → 拿到ID → 再挂SL/TP（更稳、可查ID）"""
    return oanda.open_order(instrument, direction, units, sl, tp, tag=tag, dry_run=dry_run)

def close_position(oanda: OandaClient, instrument: str, dry_run=False):
    """平仓 → 成功返回 (ok, reason, pl) 失败返回 (False, None, 0)"""
    return oanda.close_position(instrument, dry_run=dry_run)

# ==================================================
# 🧠 Gemini/AI 增强（保留接口，按需启用）
# ==================================================
def get_news_sentiment(settings: Settings) -> str:
    """预留：读取 GEMINI_API_KEY 后接入"""
    if not settings.GEMINI_API_KEY:
        return "Gemini not configured"
    return "Gemini ready (not connected yet)"