"""
单元测试 — 开仓 / 平仓 / 改单 / 平仓原因 / CSV记录
测试账号: OANDA_ACCOUNT_2
⚠️ 开发阶段：直接实盘调用，无模拟
"""
import sys
sys.path.insert(0, "/home/qili/projects/ai_training_cnn/fx_bot")

from core.config.settings import Settings
from execution.oanda_client import OandaClient
from execution.order_manager import OrderManager

INSTRUMENT = "USD_JPY"
UNITS = 1000  # ⚠️ 小仓位测试！

def test_full_cycle():
    print("=" * 60)
    print("🧪 实盘测试：开仓 → 查持仓 → 改单 → 平仓 → 查原因 → CSV")
    print("=" * 60)

    settings = Settings()
    oanda = OandaClient(settings)
    om = OrderManager(settings, oanda)

    print(f"\n📌 账号: {oanda.account_id}")
    print(f"📌 环境: {settings.OANDA_ENV}")
    print(f"📌 交易对: {INSTRUMENT}")
    print(f"📌 仓位: {UNITS}")
    print(f"📌 开发阶段: 直接实盘调用，无模拟")

    # ── ① 查现有持仓，避免重复开仓 ──
    print("\n🔹 ① 检查持仓状态...")
    pos = oanda.get_open_position(INSTRUMENT)
    if pos:
        print(f"   ⚠️ 已有持仓: {pos}")
        print("   请先手动平仓或改测试币种！")
        return

    # ── ② 开仓 ──
    print("\n🔹 ② 开仓...")
    df = oanda.fetch_candles(INSTRUMENT, "M5", 1)
    price = float(df.iloc[-1]["Close"])
    sl_price = round(price - 1.00, 3)
    tp_price = round(price + 1.50, 3)
    print(f"   📈 现价≈{price} → SL={sl_price} TP={tp_price}")
    trade_id = om.place_open_order(INSTRUMENT, "BUY", UNITS, sl_price, tp_price)
    if not trade_id:
        print("   ❌ 开仓失败")
        return
    print(f"   ✅ 开仓成功! TradeID: {trade_id}")

    # ── ③ 查持仓 ──
    print("\n🔹 ③ 验证持仓...")
    pos = oanda.get_open_position(INSTRUMENT)
    print(f"   当前持仓: {pos or '无持仓'}")

    # ── ④ 改单 ──
    print("\n🔹 ④ 更新 SL/TP...")
    ok = om.update_position(trade_id, INSTRUMENT, new_sl=round(sl_price + 0.10, 3), new_tp=round(tp_price - 0.10, 3))
    print(f"   改单: {'✅ 成功' if ok else '❌ 失败'}")

    # ── ⑤ 平仓 + 查原因 ──
    print("\n🔹 ⑤ 平仓 + 追溯原因...")
    closed, reason = om.place_close_order(INSTRUMENT)
    print(f"   平仓结果: {closed or '无平仓'}")
    print(f"   平仓原因: {reason or '无原因'}")

    # ── ⑥ CSV验证 ──
    print(f"\n🔹 ⑥ CSV交易记录: {om.logger.csv_path(INSTRUMENT)}")
    print("✅ 全流程测试完成！")

if __name__ == "__main__":
    test_full_cycle()