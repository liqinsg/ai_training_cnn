# fx_trade_closed_status-v2.py
#!/usr/bin/env python3
"""
OANDA 已平仓交易分析模块
- 可独立运行: python oanda_closed_audit.py [小时数]
- 可被主程序导入: from oanda_closed_audit import get_recent_closed_trades
"""

import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Tuple, Optional

from oandapyV20.endpoints.trades import TradesList
from oandapyV20.endpoints.transactions import TransactionDetails
from config_oanda import api, OANDA_ACCOUNT_ID_DEMO_2 as ACCOUNT


def parse_time(s: str) -> datetime:
    """解析 OANDA 时间戳（纳秒截断到微秒）"""
    base, _, frac = s.rstrip("Z").partition(".")
    return datetime.fromisoformat(f"{base}.{frac[:6] or '0'}").replace(tzinfo=timezone.utc)


def classify_transaction(tx: Dict) -> str:
    """
    判定平仓类型
    返回: TP / SL / NON_TP_CLOSE / UNKNOWN / NON_ORDER_FILL
    """
    if tx.get("type") != "ORDER_FILL":
        return "NON_ORDER_FILL"
    reason = tx.get("reason", "")
    if reason == "TAKE_PROFIT_ORDER":
        return "TP"
    if "STOP_LOSS" in reason:
        return "SL"
    if reason.startswith("MARKET_ORDER"):
        return "NON_TP_CLOSE"
    return "UNKNOWN"


def get_recent_closed_trades(
    hours: float = 72.0,
    count_limit: int = 500,
    account: str = ACCOUNT
) -> Tuple[List[Dict], Dict[str, int]]:
    """
    获取指定时间窗口内的已平仓交易并分类
    
    Args:
        hours: 回溯小时数
        count_limit: 单次API拉取上限
        account: OANDA 账户ID
    
    Returns:
        (交易详情列表, 分类统计字典)
        单条交易详情结构:
        {
            "id": str,
            "instrument": str,
            "close_time": datetime,
            "close_time_str": str,
            "tx_id": str,
            "reason_raw": str,
            "category": str,       # TP / SL / NON_TP_CLOSE / ...
            "realized_pl": float
        }
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)

    # 拉取已平仓
    resp = api.request(
        TradesList(account, params={"state": "CLOSED", "count": count_limit})
    )
    all_trades = resp.get("trades", [])

    # 筛选时间窗口
    recent_trades = []
    for t in all_trades:
        close_time_str = t.get("closeTime")
        if not close_time_str:
            continue
        close_time_dt = parse_time(close_time_str)
        if close_time_dt >= cutoff:
            recent_trades.append({
                "id": t.get("id"),
                "instrument": t.get("instrument"),
                "close_time": close_time_dt,
                "close_time_str": close_time_str[:19],
                "realized_pl": float(t.get("realizedPL", 0.0)),
                "closing_tx_ids": t.get("closingTransactionIDs", [])
            })

    # 逐条查 Transaction 判定类型
    results: List[Dict] = []
    totals: Dict[str, int] = Counter()

    for trade in recent_trades:
        for tx_id in trade["closing_tx_ids"]:
            tx_resp = api.request(TransactionDetails(account, str(tx_id)))
            tx = tx_resp.get("transaction", {})
            category = classify_transaction(tx)
            totals[category] += 1

            results.append({
                **trade,
                "tx_id": tx_id,
                "reason_raw": tx.get("reason", ""),
                "category": category
            })

    # 按平仓时间倒序排列（最新在前）
    results.sort(key=lambda x: x["close_time"], reverse=True)
    return results, dict(totals)


def print_summary(results: List[Dict], totals: Dict[str, int], hours: float) -> None:
    """控制台友好输出"""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)
    print(f"Account: {ACCOUNT} | Window UTC: {cutoff:%Y-%m-%d %H:%M} -> {now:%Y-%m-%d %H:%M} | READ ONLY")
    print("\n=== TRADES ===")
    for r in results:
        print(
            f"{r['id']} {r['instrument']} closed={r['close_time_str']} "
            f"tx={r['tx_id']} reason={r['reason_raw']} -> {r['category']}"
        )
    print("\n=== SUMMARY ===")
    print(f"In window: {len(results)}")
    for k in ("TP", "SL", "NON_TP_CLOSE", "UNKNOWN", "NON_ORDER_FILL"):
        print(f"{k}: {totals.get(k, 0)}")

#!/usr/bin/env python3
"""
单货币对交易状态查询
- 函数纯接口，无硬编码账户
- 默认值与示例仅在main中执行
- 返回: status = "open" / "closed" / "none"
"""

from datetime import datetime, timezone
from typing import Dict

from oandapyV20.endpoints.trades import TradesList
from oandapyV20.endpoints.transactions import TransactionDetails
from config_oanda import api, OANDA_ACCOUNT_ID_DEMO_2


def _parse_time(s: str) -> datetime:
    base, _, frac = s.rstrip("Z").partition(".")
    return datetime.fromisoformat(f"{base}.{frac[:6] or '0'}").replace(tzinfo=timezone.utc)


def _classify_close_type(reason: str) -> str:
    """返回: TP / SL / MARKET / OTHER"""
    if reason == "TAKE_PROFIT_ORDER":
        return "TP"
    if "STOP_LOSS" in reason:
        return "SL"
    if reason.startswith("MARKET_ORDER"):
        return "MARKET"
    return "OTHER"


def check_instrument(
    instrument: str,
    account_id: str,
    api_client,
    lookback_hours: float = 72.0
) -> Dict:
    """
    查询指定货币对最新状态（仅 lookback_hours 内的平仓）
    
    Args:
        instrument: "AUD_JPY" 格式
        account_id: OANDA 账户ID（必填）
        api_client: API 客户端实例（必填）
        lookback_hours: 只考虑最近 N 小时内的平仓，默认 72h（3天）
    
    Returns:
        {
            "instrument": str,
            "status": "open" | "closed" | "none",
            "data": {
                # status = "open"
                "trade_id": str,
                "open_time": str,
                "has_tp": bool,
                "has_sl": bool,
                
                # status = "closed"
                "trade_id": str,
                "close_time": str,
                "close_type": "TP" | "SL" | "MARKET" | "OTHER",
                "reason_raw": str,
                "realized_pl": float,
                "open_time": str
            }
        }
    """
    from datetime import timedelta as _td
    cutoff = datetime.now(timezone.utc) - _td(hours=lookback_hours)

    resp = api_client.request(TradesList(account_id, params={
        "instrument": instrument,
        "count": 100
    }))
    trades = resp.get("trades", [])

    if not trades:
        return {"instrument": instrument, "status": "none", "data": {}}

    open_trades = [t for t in trades if t.get("state") == "OPEN"]
    if open_trades:
        t = open_trades[0]
        return {
            "instrument": instrument,
            "status": "open",
            "data": {
                "trade_id": t.get("id"),
                "open_time": t.get("openTime", "").replace("T", " ")[:19],
                "has_tp": bool(t.get("takeProfitOrder")),
                "has_sl": bool(t.get("stopLossOrder"))
            }
        }

    closed_trades = []
    for t in trades:
        if t.get("state") != "CLOSED":
            continue
        ct_str = t.get("closeTime", "")
        if not ct_str:
            continue
        ct_dt = _parse_time(ct_str)
        if ct_dt >= cutoff:
            closed_trades.append((ct_dt, t))

    closed_trades.sort(key=lambda x: x[0], reverse=True)

    if closed_trades:
        _, t = closed_trades[0]
        tx_ids = t.get("closingTransactionIDs", [])
        close_type = "OTHER"
        reason_raw = ""

        if tx_ids:
            tx_resp = api_client.request(TransactionDetails(account_id, str(tx_ids[0])))
            tx = tx_resp.get("transaction", {})
            reason_raw = tx.get("reason", "")
            close_type = _classify_close_type(reason_raw)

        return {
            "instrument": instrument,
            "status": "closed",
            "data": {
                "trade_id": t.get("id"),
                "close_time": t.get("closeTime", "").replace("T", " ")[:19],
                "close_type": close_type,
                "reason_raw": reason_raw,
                "realized_pl": float(t.get("realizedPL", 0)),
                "open_time": t.get("openTime", "").replace("T", " ")[:19]
            }
        }

    return {"instrument": instrument, "status": "none", "data": {}}

        
# 独立运行入口
if __name__ == "__main__":
    hours = float(sys.argv[1]) if len(sys.argv) > 1 else 72.0
    results, totals = get_recent_closed_trades(hours=hours)
    print_summary(results, totals, hours)