#!/usr/bin/env python3
"""
TAG 完整流程测试 — Profile2
含详细错误日志，定位开仓失败原因
"""
import csv
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.config.settings import Settings
from execution.oanda_client import OandaClient
from execution.order_manager import OrderManager
from utils.trade_logger import TradeLogger

INSTRUMENT = "USD_JPY"
PROFILE = "profile2"


def make_sl_tp(oanda, instrument, direction="BUY", sl_dist=1.00, tp_dist=1.50):
    """Generate SL/TP dynamically based on the current market price
    to avoid OANDA rejections caused by stale hardcoded values.

    OANDA rule:
    For BUY positions, TP must be above the entry price and SL below it.
    Prices on the wrong side will be rejected
    (e.g. TAKE_PROFIT_ON_FILL_LOSS).
    """
    df = oanda.fetch_candles(instrument, "M5", 1)
    price = float(df.iloc[-1]["Close"])
    if direction == "BUY":
        sl, tp = price - sl_dist, price + tp_dist
    else:
        sl, tp = price + sl_dist, price - tp_dist
    return round(sl, 3), round(tp, 3), price


def phase1_no_csv(om: OrderManager):
    """Phase 1: Open / Modify / Close — returns trade_id for Phase 3 verify"""
    print("\n" + "="*60)
    print("🔹 Phase 1 - No CSV Mode: Open → Modify → Close")
    print("="*60)

    print("\n1.1 Open Position (with TAG + decision snapshot)")
    sl, tp, px = make_sl_tp(om.oanda, INSTRUMENT)
    print(f"📈 Current Price≈{px} → SL={sl} TP={tp}")
    trade_id_tagged = om.place_open_order(
        INSTRUMENT, "BUY", 1000, sl=sl, tp=tp,
        reason="H1多+RSI超卖+低波动",       # ✅ 模拟信号层传入理由
        score_final="68.5",                # ✅ 模拟信号层传入综合分
    )
    if not trade_id_tagged:
        print("⚠️  Order open failed - see logs above for details")
        return None
    print(f"✅ Tagged order opened successfully - TradeID={trade_id_tagged}")

    print("\n1.2 Modify Position (TAG matched)")
    ok = om.update_position(
        trade_id_tagged,
        INSTRUMENT,
        new_sl=round(sl + 0.10, 3),
        new_tp=round(tp - 0.10, 3)
    )
    print(f"✅ Update successful" if ok else "❌ Update failed")

    print("\n1.3 Close Position (TAG matching mode)")
    ok, _ = om.place_close_order(INSTRUMENT)
    print(f"✅ TAG-matched close successful" if ok else "⚠️  TAG mismatch → SAFE STOP, position not closed")

    print("\n✅ Phase 1 completed")
    return trade_id_tagged


def phase2_with_csv(om: OrderManager):
    """Phase 2: Full TAG workflow — returns trade_id for Phase 3 verify"""
    print("\n" + "="*60)
    print("🔹 Phase 2 - TAG Mode + CSV Logging")
    print("="*60)

    print("\n2.1 Open Position (force TAG + decision snapshot)")
    sl, tp, px = make_sl_tp(om.oanda, INSTRUMENT)
    print(f"📈 Current Price≈{px} → SL={sl} TP={tp}")
    trade_id = om.place_open_order(
        INSTRUMENT, "BUY", 1000, sl=sl, tp=tp,
        reason="布林上轨突破+放量",         # ✅ 模拟信号层传入理由
        score_final="55.0",                # ✅ 模拟信号层传入综合分
    )
    if not trade_id:
        print("❌ Order open failed - see logs above for details")
        return None
    print(f"✅ Order opened successfully - TradeID={trade_id} TAG={om.tag}")

    print("\n2.2 Modify Position SL/TP")
    ok = om.update_position(
        trade_id,
        INSTRUMENT,
        new_sl=round(sl + 0.10, 3),
        new_tp=round(tp - 0.10, 3)
    )
    print(f"✅ Update successful" if ok else "❌ Update failed")

    print("\n2.3 Close Position → Write to CSV")
    ok, reason = om.place_close_order(INSTRUMENT)
    if ok:
        print(f"✅ Position closed successfully - Reason: {reason}")
        print(
            f"📄 CSV: "
            f"{om.logger.csv_path(INSTRUMENT).relative_to(Path(__file__).resolve().parent.parent)}"
        )
    else:
        print(f"❌ Close failed: {reason}")
        return None

    print("\n✅ Phase 2 completed")
    return trade_id


def phase3_csv_verify(om: OrderManager, expected_trade_ids: list):
    """Phase 3: Read CSV back → verify each row has correct TAG + status=CLOSED

    Goal: prove the CSV file faithfully records OUR trades with OUR tag,
    never mixing up with other bots'/manual trades.
    """
    print("\n" + "="*60)
    print("🔹 Phase 3 - CSV TAG Ownership Verification")
    print("="*60)

    csv_path = om.logger.csv_path(INSTRUMENT)
    if not csv_path.exists():
        print(f"❌ CSV not found: {csv_path}")
        return False

    # ── 读全部 CSV 行 ────────────────────────────────────────────────────
    with open(csv_path, newline="") as f:
        rows = list(csv.DictReader(f))
    print(f"\n📄 CSV loaded: {csv_path.name} → {len(rows)} rows")

    tag_col = "tag" if "tag" in rows[0] else None
    if not tag_col:
        print("⚠️  CSV missing 'tag' column — old file, skip TAG verification")
        return False

    # ── 逐 trade_id 验证归属 ─────────────────────────────────────────────
    ok_all = True
    for tid in expected_trade_ids:
        row = next((r for r in rows if r["trade_id"] == str(tid)), None)
        if not row:
            print(f"  ❌ TradeID={tid} NOT FOUND in CSV")
            ok_all = False
            continue
        match_tag = row[tag_col] == om.tag
        closed = row["status"] == "CLOSED"
        icon = "✅" if (match_tag and closed) else "❌"
        print(
            f"  {icon} TradeID={tid}  tag={row[tag_col]:<15} "
            f"status={row['status']:<6} reason={row.get('close_reason','')}"
        )
        if not match_tag or not closed:
            ok_all = False

    print(f"\n{'✅ All CSV rows verified — TAG ownership correct' if ok_all else '❌ MISMATCH DETECTED'}")
    return ok_all


def main():
    settings = Settings(PROFILE)
    oanda = OandaClient(settings)
    om = OrderManager(settings, oanda)
    om.logger = TradeLogger(settings, filename_prefix="test_trade_log_")

    print(f"\n🚀 Test Run - Profile: {PROFILE} | Instrument: {INSTRUMENT}")
    print(f"🏷️  TAG: {om.tag}")

    tid1 = phase1_no_csv(om)
    tid2 = phase2_with_csv(om)

    expected = [t for t in (tid1, tid2) if t]
    if expected:
        phase3_csv_verify(om, expected)
    else:
        print("\n⚠️  No trade_ids collected — Phase 3 skipped")

    print("\n" + "="*60)
    print("💡 Common reasons for order-open failures:")
    print("   1) SL/TP is too close to the current market price (OANDA minimum distance restriction)")
    print("   2) Invalid units / position size format")
    print("   3) Instrument name should be USD_JPY instead of USD/JPY")
    print("   4) API Key / Account ID configuration issue")
    print("="*60)


if __name__ == "__main__":
    main()