#!/usr/bin/env python3
"""精准排查版：查账户信息 → 查Trades（含已平仓）→ 查Transactions
解决：ID正确但查不到记录的问题
"""

import os
import sys
from datetime import datetime, timedelta, timezone

_this_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _this_dir)

from config_oanda import api, OANDA_ACCOUNT_ID_DEMO_2
import oandapyV20.endpoints.accounts as accounts
import oandapyV20.endpoints.transactions as transactions
import oandapyV20.endpoints.trades as trades
import oandapyV20.endpoints.positions as positions

TARGET_ACCOUNT = OANDA_ACCOUNT_ID_DEMO_2

print("=" * 70)
print("🔍 步骤1：验证账户信息 + 获取起始TransactionID")
print("=" * 70)

# 关键：查账户详情拿到 lastTransactionID —— 这才是 sinceID 的正确起点！
try:
    acc_detail = api.request(accounts.AccountDetails(TARGET_ACCOUNT))
    acc = acc_detail["account"]
    last_tx_id = acc.get("lastTransactionID", "?")
    
    print(f"✅ 账户ID    : {acc['id']}")
    print(f"   账户别名    : {acc.get('alias', '—')}")
    print(f"   起始可用ID  : {last_tx_id}")
    print(f"   未平仓交易数 : {acc.get('openTradeCount', '?')}")
    print(f"   未结持仓数   : {acc.get('openPositionCount', '?')}")
    
    if acc["id"] != TARGET_ACCOUNT:
        print(f"⚠️  ID不匹配！配置={TARGET_ACCOUNT} 实际={acc['id']}")
except Exception as e:
    print(f"❌ 账户详情查询失败: {e}")
    sys.exit(1)

print("\n" + "=" * 70)
print("🔍 步骤2：查 Trades 列表（含已平仓！这是关键）")
print("=" * 70)

# 🔑 Trades 接口 = 能看到已平仓记录，比 Transactions 更直接
try:
    # state=ALL → 包括 OPEN + CLOSED
    trades_resp = api.request(
        trades.TradesList(TARGET_ACCOUNT, params={"state": "ALL", "limit": 500})
    )
    all_trades = trades_resp.get("trades", [])
    
    opened = [t for t in all_trades if t.get("state") == "OPEN"]
    closed = [t for t in all_trades if t.get("state") == "CLOSED"]
    
    print(f"✅ 查到 {len(all_trades)} 条交易记录")
    print(f"   进行中 : {len(opened)}")
    print(f"   已平仓 : {len(closed)} ← 我们重点关注的！\n")
    
    if closed:
        print("📋 已平仓记录详情：")
        print(f"{'ID':<10} {'工具':<12} {'出场原因':<20} {'盈亏':>10} {'平仓时间':<20}")
        print("-" * 90)
        
        for t in closed:
            tid = t.get("id", "—")
            instr = t.get("instrument", "—")
            reason = t.get("closeReason", "—")
            pnl = t.get("realizedPL", "—")
            close_time = t.get("closeTime", "—").replace("T", " ")[:19]
            
            # 识别平仓类型
            if reason == "TAKE_PROFIT":
                tag = "✅ TP触发"
            elif reason == "STOP_LOSS":
                tag = "⚠️ SL触发"
            elif reason == "CLIENT_ORDER":
                tag = "🔧 主动平仓"
            elif reason == "PARTIAL_CLOSE":
                tag = "📌 部分平仓"
            else:
                tag = f"? {reason}"
            
            print(f"{tid:<10} {instr:<12} {tag:<20} {pnl:>10} {close_time:<20}")
            
            # 提取币种用于冷却
            if "_" in instr:
                base, quote = instr.split("_")
                print(f"            → 影响币种: {base}, {quote}")
    else:
        print("⚠️  暂无已平仓记录")
        
except Exception as e:
    print(f"❌ Trades 查询失败: {e}")

print("\n" + "=" * 70)
print("🔍 步骤3：Transactions 用正确 sinceID 查询")
print("=" * 70)

# 用账户返回的 last_tx_id 往前查（OANDA sinceID 不包含自身，所以从它往回查）
try:
    tx_resp = api.request(
        transactions.TransactionsSinceID(
            TARGET_ACCOUNT,
            params={"id": last_tx_id, "limit": 100}
        )
    )
    txs = tx_resp.get("transactions", [])
    print(f"✅ TransactionsSinceID 返回 {len(txs)} 条记录\n")
    
    type_count = {}
    tp_sl_count = 0
    for tx in txs:
        t = tx.get("type", "UNKNOWN")
        type_count[t] = type_count.get(t, 0) + 1
        if "TAKE_PROFIT" in t or "STOP_LOSS" in t:
            tp_sl_count += 1
            instr = tx.get("instrument", "—")
            print(f"   🎯 {t:30} {instr}")
    
    print(f"\n类型统计:")
    for t, cnt in sorted(type_count.items()):
        flag = " ← TP/SL" if ("TAKE_PROFIT" in t or "STOP_LOSS" in t) else ""
        print(f"   {t:<35} × {cnt}{flag}")
    print(f"\nTP/SL 相关记录: {tp_sl_count} 条")
    
except Exception as e:
    print(f"❌ TransactionsSinceID 失败: {e}")
    print("   改用时间范围查询...")
    try:
        now = datetime.now(timezone.utc)
        from_t = now - timedelta(days=90)
        tx_resp = api.request(transactions.TransactionList(TARGET_ACCOUNT, params={
            "from": from_t.strftime("%Y-%m-%dT%H:%M:%S.000000Z"),
        }))
        txs = tx_resp.get("transactions", [])
        print(f"✅ 时间查询返回 {len(txs)} 条")
    except Exception as e2:
        print(f"❌ 时间查询也失败: {e2}")

print("\n✅ 排查完成！")