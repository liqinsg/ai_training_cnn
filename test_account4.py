#!/usr/bin/env python3
"""Test OANDA Account 004 connectivity & permissions."""

# ─── CONFIG — Account 004 ──────────────────────────────────────
OANDA_ACCOUNT_ID = "001-003-21515688-004"
OANDA_ENV = "practice"  # or "live"

# ─── TEST EXECUTION ────────────────────────────────────────────
if __name__ == "__main__":
    from utils.oanda_execution import check_oanda_account
    
    print(f"🔍 Testing Account 004 — ID: {OANDA_ACCOUNT_ID}")
    print("─" * 55)
    
    try:
        check_oanda_account(account_id=OANDA_ACCOUNT_ID)
        print(f"\n✅ ACCOUNT OK: {OANDA_ACCOUNT_ID} — API key has access")
    except Exception as e:
        print(f"\n❌ FORBIDDEN / MISMATCH: {e}")
        print("💡 Likely causes:")
        print("   • API token does NOT include Account 004")
        print("   • Wrong account ID")
        print("   • API key is for live instead of practice (or vice versa)")
