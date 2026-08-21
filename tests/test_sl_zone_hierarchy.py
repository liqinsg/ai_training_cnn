# =============================================================
# test_sl_zone_hierarchy.py — v1.3 🆕 100% REAL OANDA DATA
# NO hardcoded prices! → Entry Price = REAL-TIME TICK from OANDA
# Shows: Entry → H4 Zone → Buffer → SL → Distance
# =============================================================

import sys
import logging
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

import config_bot
from sl_zone_hierarchy import compute_sl_zone


def cfg_test(name, default):
    return getattr(config_bot, name, default)


def print_section(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def get_real_time_price(api, oanda_instrument):
    """Fetch REAL-TIME mid price from OANDA — NO hardcodes!"""
    from oandapyV20.endpoints.instruments import InstrumentsCandles
    try:
        resp = api.request(InstrumentsCandles(
            instrument=oanda_instrument,
            params={"granularity": "M1", "count": 1, "price": "M"}
        ))
        candle = resp["candles"][0]
        mid_price = float(candle["mid"]["c"])
        return round(mid_price, 5), True
    except Exception as e:
        print(f"   ⚠️ Price fetch failed: {e}")
        return None, False


def main():
    print_section("📏 HIERARCHICAL SL — CONFIGURATION")
    BUFFER_PIPS = cfg_test("SL_BUFFER_PIPS", 25)
    MIN_DIST_PIPS = cfg_test("SL_MIN_DISTANCE_PIPS", 20)
    print(f"  SL_BUFFER_PIPS         = {BUFFER_PIPS}")
    print(f"  SL_MIN_DISTANCE_PIPS   = {MIN_DIST_PIPS}")

    # ─── CONNECT OANDA ───
    try:
        from config_oanda import OANDA_API_TOKEN, OANDA_ENV
        import oandapyV20
        api = oandapyV20.API(access_token=OANDA_API_TOKEN, environment=OANDA_ENV)
        print("\n✅ OANDA API connected")
    except Exception as e:
        print(f"\n❌ OANDA API unavailable: {e}")
        return 1

    # ─── PAIRS TO TEST ───
    test_pairs = [
        ("EUR_USD",  0.00010),   # pip size
        ("USD_JPY",  0.01000),
        ("GBP_JPY",  0.01000),
        ("EUR_JPY",  0.01000),
        ("GBP_USD",  0.00010),
    ]

    print_section("🔍 FETCHING REAL PRICES + SL CALCULATION")
    print("   Entry Price = REAL-TIME from OANDA | Zone = H4 6-bar extremum")
    print()

    results = []
    directions = ["BUY", "SELL"]  # Test BOTH directions for each pair

    for oanda, pip in test_pairs:
        # ─── STEP 1: GET REAL PRICE FROM OANDA ───
        real_price, ok = get_real_time_price(api, oanda)
        if not ok or real_price is None:
            print(f"⚠️ {oanda}: SKIP — no price data")
            continue

        print(f"\n── {oanda} | REAL-TIME PRICE = {real_price:.5f} ──")

        # ─── STEP 2: TEST BOTH DIRECTIONS ───
        for direction in directions:
            sl_price, info = compute_sl_zone(api, oanda, direction, real_price, pip, cfg_test)
            zone_price = info.get("zone_price")
            dist_pips = abs(real_price - sl_price) / pip

            # ─── PRINT BREAKDOWN ───
            if zone_price:
                buffer_amt = BUFFER_PIPS * pip
                if direction == "BUY":
                    print(f"   BUY │ H4 LOW={zone_price:.5f} − {BUFFER_PIPS}p → SL={sl_price:.5f} │ DIST={dist_pips:.0f}p")
                else:
                    print(f"   SELL│ H4 HIGH={zone_price:.5f} + {BUFFER_PIPS}p → SL={sl_price:.5f} │ DIST={dist_pips:.0f}p")

                status = "✅ GOOD" if MIN_DIST_PIPS <= dist_pips <= 150 else ("⚠️ WIDE" if dist_pips > 150 else "🔧 TOO CLOSE")
                print(f"        │ Source={info['source']} │ {status}")
            else:
                print(f"   {direction} │ SL={sl_price:.5f} │ DIST={dist_pips:.0f}p │ Source={info['source']}")

            results.append({
                "pair": oanda, "dir": direction,
                "entry": real_price, "zone": zone_price,
                "sl": sl_price, "dist": round(dist_pips, 1),
                "source": info["source"],
            })

    # ─── FINAL SUMMARY TABLE ───
    print_section("📊 FINAL SUMMARY — ALL REAL OANDA DATA")
    print(f"{'Pair':<12} {'Dir':<5} {'Entry':<10} {'H4 Zone':<10} {'SL':<10} {'Dist(pips)':<10} {'Status':<10}")
    print("-" * 80)
    for r in results:
        status = "✅ GOOD" if 20 <= r["dist"] <= 150 else ("⚠️ WIDE" if r["dist"] > 150 else "🔧 CLOSE")
        zone_str = f"{r['zone']:.5f}" if r["zone"] else "N/A"
        print(f"{r['pair']:<12} {r['dir']:<5} {r['entry']:<10.5f} {zone_str:<10} {r['sl']:<10.5f} {r['dist']:<10} {status:<10}")

    print("\n✅ ALL DATA FROM OANDA — NO HARDCODED PRICES!")
    print("   ✅ GOOD = 20–150p (ideal) | ⚠️ WIDE = price far from zone | 🔧 CLOSE = will try H8/Daily")
    return 0


if __name__ == "__main__":
    sys.exit(main())