"""
FX Daily Monte Carlo Report Sender
✅ Runs advanced MC for all configured pairs
✅ Saves JSON payloads for trading bot
✅ Sends clean actionable summary to Telegram
✅ Backward compatible — same cron, same paths
"""
import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from fx_monte_carlo_advanced import run_monte_carlo, build_telegram_report
from telegram_message import send_telegram_message
import config

# --------------------------
# CONFIG — CENTRALIZED
# --------------------------
def cfg(name, default):
    return getattr(config, name, default)

DEFAULT_PAIRS = cfg("DEFAULT_PAIRS", [
    "EURUSD=X", "GBPUSD=X", "EURJPY=X", "GBPJPY=X",
    "AUDUSD=X", "USDJPY=X", "GBPAUD=X", "USDCHF=X"
])
RESULTS_DIR = Path(__file__).parent / "daily_results"
RESULTS_DIR.mkdir(exist_ok=True)

# --------------------------
# PARSE ARGS
# --------------------------
parser = argparse.ArgumentParser(
    description="Advanced FX Monte Carlo Daily Report"
)
parser.add_argument("pairs", nargs="*", default=DEFAULT_PAIRS)
parser.add_argument("--period", default="60d")
parser.add_argument("--sim", type=int, default=5000)
parser.add_argument("--json-out", action="store_true")
args = parser.parse_args()

# --------------------------
# RUN ALL PAIRS
# --------------------------
all_results = []
success = 0
failed = 0

print(f"🔬 ADVANCED MC RUN — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
print(f"🔹 Period: {args.period} | Simulations: {args.sim} | Pairs: {len(args.pairs)}")

for pair in args.pairs:
    try:
        print(f"🔬 Processing: {pair}")
        res = run_monte_carlo(pair, period=args.period, sims=args.sim)
        all_results.append(res)
        
        # Save JSON for trading bot
        json_file = RESULTS_DIR / f"fx_daily_{pair.replace('=X','')}_{datetime.now().strftime('%Y%m%d')}.json"
        with open(json_file, "w") as f:
            json.dump(res, f, indent=2)
        print(f"✅ Saved → {json_file.name}")
        success += 1

    except Exception as e:
        print(f"❌ Failed {pair}: {str(e)[:80]}")
        failed += 1

# --------------------------
# OUTPUT
# --------------------------
if args.json_out:
    print(json.dumps(all_results, indent=2))
else:
    if all_results:
        report = build_telegram_report(all_results)
        print("\n" + report)
        send_telegram_message(report)
    
    print(f"\n✅ Daily MC run complete\n   Success: {success} | Failed: {failed}")