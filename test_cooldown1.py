#!/usr/bin/env python3
"""纯测试 · 不接入主程序 · 彻底查清每笔平仓的真实方式"""

import sys
from datetime import datetime, timedelta, timezone

from config_oanda import api, OANDA_ACCOUNT_ID_DEMO_2
import oandapyV20.endpoints.trades as trades
import oandapyV20.endpoints.transactions as transactions
import oandapyV20.endpoints.accounts as accounts

TARGET_ACCOUNT = OANDA_ACCOUNT_ID_DEMO_2

print("=" * 72)
print("🔍 纯测试：查清每笔平仓的真实出场方式")
print(f"账户: {TARGET_ACCOUNT}")
print("=" * 72)

# 1. 获取账户信息和起始ID
acc_info = api.request(accounts.AccountDetails(TARGET_ACCOUNT))["account"]
first_tx_id = acc_info.get("lastTransactionID", "1")
print(f"\n账户最新 TransactionID: {first_tx_id}")

# 2. 拉 CLOSED Trades
trades_resp = api.request(
    trades.TradesList(TARGET_ACCOUNT, params={"state": "CLOSED", "limit": 20})  # 先查最近20条，更清晰
)
closed = trades_resp.get("trades", [])
print(f"\n已平仓数量: {len(closed)} (取最近20条分析)\n")

# 3. 收集所有需要查的 TransactionID
all_cids = set()
for t in closed:
    cids = t.get("closingTransactionIDs", [])
    for cid in cids:
        all_cids.add(cid)

print(f"需要查询的平仓 TransactionID 数量: {len(all_cids)}")
if all_cids:
    print(f"ID 列表: {sorted(all_cids)[:10]}{'...' if len(all_cids) > 10 else ''}")

# 4. 批量拉 Transactions — 扩大范围，确保覆盖
tx_map = {}
missing_ids = set(all_cids)

# 方法A: TransactionsSinceID 往前查
tx_resp = api.request(
    transactions.TransactionsSinceID(
        TARGET_ACCOUNT,
        params={"id": first_tx_id, "limit": 1000}
    )
)
tx_list = tx_resp.get("transactions", [])
print(f"\nTransactionsSinceID 返回: {len(tx_list)} 条")

for tx in tx_list:
    tid = tx.get("id")
    if tid in missing_ids:
        tx_map[tid] = tx
        missing_ids.remove(tid)

# 方法B: 时间范围兜底（往前推90天）
if missing_ids:
    print(f"仍缺失 {len(missing_ids)} 条 → 用时间范围补充查询...")
    now = datetime.now(timezone.utc)
    tx_resp2 = api.request(
        transactions.TransactionList(TARGET_ACCOUNT, params={
            "from": (now - timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%S.000000Z"),
        })
    )
    tx_list2 = tx_resp2.get("transactions", [])
    print(f"时间查询返回: {len(tx_list2)} 条")
    for tx in tx_list2:
        tid = tx.get("id")
        if tid in missing_ids:
            tx_map[tid] = tx
            missing_ids.remove(tid)

print(f"最终匹配成功: {len(tx_map)}/{len(all_cids)}")
if missing_ids:
    print(f"仍无法匹配的ID: {sorted(missing_ids)}")

# 5. 逐条分析
print("\n" + "=" * 72)
print("📋 逐条分析结果")
print("=" * 72)
print(f"{'ID':<8} {'工具':<12} {'平仓方式':<25} {'盈亏':>12}")
print("-" * 72)

stats = {"TP": 0, "SL": 0, "主动": 0, "未知": 0}

for t in closed:
    tid = t.get("id")
    instr = t.get("instrument")
    pl = float(t.get("realizedPL", 0))
    cids = t.get("closingTransactionIDs", [])
    
    how = "⚠️ 未知"
    emoji = "❓"
    
    if cids and cids[0] in tx_map:
        tx_type = tx_map[cids[0]].get("type", "")
        
        if "TAKE_PROFIT" in tx_type:
            how = "✅ TP触发成交"
            emoji = "🎯"
            stats["TP"] += 1
        elif "STOP_LOSS" in tx_type:
            how = "⚠️ SL触发成交"
            emoji = "🛑"
            stats["SL"] += 1
        elif "MARKET" in tx_type or "ORDER" in tx_type or "CLIENT" in tx_type:
            how = f"🔧 主动平仓 ({tx_type})"
            emoji = "📤"
            stats["主动"] += 1
        else:
            how = f"📌 {tx_type}"
            stats["未知"] += 1
    else:
        # 最后手段：从 Trade 结构推断
        has_tp = "takeProfitOrder" in t
        has_sl = "stopLossOrder" in t
        if has_tp and not has_sl:
            how = "❓ 有TP挂单/待确认"
        elif has_sl and not has_tp:
            how = "❓ 有SL挂单/待确认"
        elif has_tp and has_sl:
            how = "❓ TP/SL均挂单/待确认"
        stats["未知"] += 1
    
    print(f"{emoji} {tid:<6} {instr:<12} {how:<25} {pl:>+12.4f}")

print("\n" + "=" * 72)
print("📊 汇总统计")
print("=" * 72)
print(f"✅ TP触发成交 : {stats['TP']}")
print(f"🛑 SL触发成交 : {stats['SL']}")
print(f"📤 主动市价平仓 : {stats['主动']}")
print(f"❓ 无法确认     : {stats['未知']}")
print(f"总计           : {len(closed)}")

print("\n💡 结论说明:")
if stats["TP"] + stats["SL"] > 0:
    print("✅ 找到真正的 TP/SL 触发记录 → 可以用 API 监听方案")
else:
    print("⚠️  所选范围内无 TP/SL 触发成交记录")
    print("   → 若全部为主动平仓，推荐：出场代码处直接记录冷却")
    print("   → 这样最稳，不依赖 API 查询结果")