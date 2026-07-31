"""
Collect daily forex Monte Carlo stats for all configured pairs,
save per‑pair JSON, and send consolidated report to Telegram.

Usage:
  1. Default (all 6 pairs)
     python fx_daily_telegram.py
  2. Custom pairs only
     python fx_daily_telegram.py EURUSD=X USDJPY=X
  3. Override settings
     python fx_daily_telegram.py --period 90d --account-risk 0.005 --sim 8000
  4. Mixed
     python fx_daily_telegram.py EURUSD=X --period 90d
"""
import config
from telegram_message import send_telegram_message
import json
import subprocess
import sys
import shlex
import argparse
from datetime import datetime, timezone
from pathlib import Path
from utils.oanda_execution import is_forex_market_open

# Exit immediately if market is closed
if not is_forex_market_open():
    print("⏸️ Market is closed — skipping run")
    raise SystemExit(0)

sys.path.append(str(Path.home() / "ai_training_cnn"))


# --------------------------
# CONFIG
# --------------------------

def cfg(name, default):
    return getattr(config, name, default)


DEFAULT_PAIRS = cfg("DEFAULT_PAIRS", ["EURUSD=X", "GBPUSD=X", "EURJPY=X", "GBPJPY=X", "AUDUSD=X", "USDJPY=X"])
YAHOO_TO_OANDA = cfg("YAHOO_TO_OANDA", {
    "EURUSD=X": "EUR_USD", "GBPUSD=X": "GBP_USD", "EURJPY=X": "EUR_JPY",
    "GBPJPY=X": "GBP_JPY", "AUDUSD=X": "AUD_USD", "USDJPY=X": "USD_JPY"
})

BASE_DIR = Path(__file__).resolve().parent
DAILY_VIEW = BASE_DIR / "fx_daily_view.py"
# RESULTS_DIR = Path.home() / "ai_training_cnn" / "daily_results"
RESULTS_DIR = Path(__file__).parent / "daily_results"
RESULTS_DIR.mkdir(exist_ok=True)

# --------------------------
# PARSE ARGS
# --------------------------
parser = argparse.ArgumentParser()
parser.add_argument("pairs", nargs="*", default=DEFAULT_PAIRS)
parser.add_argument("--period", default="60d")
parser.add_argument("--account-risk", type=float, default=0.01)
parser.add_argument("--sim", type=int, default=5000)
args = parser.parse_args()

PERIOD = args.period
RISK = args.account_risk
SIM = args.sim
TARGET_PAIRS = args.pairs

# --------------------------
# RUN MC + SAVE FOR EACH PAIR
# --------------------------
all_results = []
errors = []

for pair in TARGET_PAIRS:
    print(f"\n🔬 Processing: {pair}")
    cmd = [
        sys.executable, str(DAILY_VIEW),
        pair,
        "--period", PERIOD,
        "--account-risk", str(RISK),
        "--sim", str(SIM),
        "--json-out"  # Add this flag to fx_daily_view.py to output JSON only
    ]
    print(f"▶ {' '.join(shlex.quote(c) for c in cmd)}")

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if proc.returncode != 0:
            errors.append(f"{pair}: FAILED\n{proc.stderr}")
            continue

        # Parse JSON output from fx_daily_view
        data = json.loads(proc.stdout.strip())
        data["pair"] = pair
        data["oanda_pair"] = YAHOO_TO_OANDA.get(pair, pair.replace("=X", ""))
        data["generated_utc"] = datetime.now(timezone.utc).isoformat()

        # Save per‑pair file
        safe = pair.replace("=X", "").replace("=", "_")
        out_file = RESULTS_DIR / f"fx_daily_{safe}_{datetime.now(timezone.utc).strftime('%Y%m%d')}.json"
        with open(out_file, "w") as f:
            json.dump(data, f, indent=2)

        all_results.append(data)
        print(f"✅ Saved → {out_file.name}")

    except Exception as e:
        errors.append(f"{pair}: ERROR\n{str(e)}")

# --------------------------
# BUILD TELEGRAM REPORT
# --------------------------
msg_lines = ["📊 *FX DAILY MONTE CARLO REPORT*",
             f"📅 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
             f"📈 Period: {PERIOD} | Simulations: {SIM} | Risk: {RISK:.1%}", ""]

for r in all_results:
    drift = r.get("ann_drift", 0)
    rlo, rhi = r.get("range_90", [0, 0])
    msg_lines.append(
        f"🔹 *{r['pair']}*\n"
        f"   Drift: {drift:+.2f}% | 90% Range: {rlo:.5f} – {rhi:.5f}"
    )

if errors:
    msg_lines.extend(["", "⚠️ *FAILED PAIRS*"] + errors)

msg = "\n".join(msg_lines)
send_telegram_message(msg)

print("\n✅ Daily MC run complete")
print(f"   Success: {len(all_results)} | Failed: {len(errors)}")
