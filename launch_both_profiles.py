# ══════════════════════════════════════════════════════════════
# FX BOT v6.8.2 — LAUNCH BOTH PROFILES
# Profile2 → Account 001 | S=0.40 X=0.20 | Aggressive/ML-focused
# Profile3 → Account 003 | S=0.50 X=0.12 | Conservative/Strength-focused
# ══════════════════════════════════════════════════════════════

import sys
import subprocess
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent

print("=" * 70)
print("🤖 FX BOT v6.8.2 — LAUNCH BOTH PROFILES")
print(f"🕐 Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 70)
print()
print("📊 PROFILE2 → Account 002 | Weights: S=40 R=15 A=15 X=20 M=10 | Threshold 30")
print("📊 PROFILE3 → Account 003 | Weights: S=50 R=15 A=15 X=12 M=08 | Threshold 40")
print()
print("✅ Logs → bot_profile2.log / bot_profile3.log")
print("✅ Separate cooldowns & MC results — NO CONFLICTS")
print()
print("=" * 70)
print()

# ─── LAUNCH BOTH ───
p2_path = BASE_DIR / "fx_trade_bot_v6.8.2_profile2.py"
p3_path = BASE_DIR / "fx_trade_bot_v6.8.2_profile3.py"

if not p2_path.exists():
    print(f"❌ MISSING: {p2_path.name}")
    sys.exit(1)
if not p3_path.exists():
    print(f"❌ MISSING: {p3_path.name}")
    sys.exit(1)

print("🚀 Starting PROFILE2 (Account 002)...")
proc2 = subprocess.Popen(
    [sys.executable, str(p2_path)],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True
)

print("🚀 Starting PROFILE3 (Account 003)...")
proc3 = subprocess.Popen(
    [sys.executable, str(p3_path)],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True
)

print()
print("✅ BOTH BOTS RUNNING!")
print(f"   Profile2 PID: {proc2.pid}")
print(f"   Profile3 PID: {proc3.pid}")
print()
print("💡 Tip: Check logs anytime → tail -f bot_profile2.log & tail -f bot_profile3.log")
print("💡 Tip: Press Ctrl+C to stop BOTH bots")
print()

# ─── WATCH BOTH PROCESSES ───
try:
    while True:
        ret2 = proc2.poll()
        ret3 = proc3.poll()

        if ret2 is not None:
            print(f"\n⚠️ Profile2 exited with code {ret2}")
        if ret3 is not None:
            print(f"\n⚠️ Profile3 exited with code {ret3}")
        if ret2 is not None and ret3 is not None:
            print("\n🛑 Both bots stopped.")
            break

except KeyboardInterrupt:
    print("\n\n🛑 Ctrl+C detected — SHUTTING DOWN BOTH BOTS...")
    proc2.terminate()
    proc3.terminate()
    proc2.wait()
    proc3.wait()
    print("✅ Both bots stopped cleanly.")