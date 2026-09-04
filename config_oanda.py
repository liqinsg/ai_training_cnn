# config_oanda.py — v7.0.0 | Token Validate → Account Discovery → Compare → Optional Summary
# ────────────────────────────────────────────────────────────────
"""
Central OANDA configuration & health validator.
Run directly:
    python config_oanda.py              # Token + AccountList + Compare
    python config_oanda.py --summary    # Full summary for all visible accounts
"""
import os
import sys
import re
from dotenv import load_dotenv
import oandapyV20
import oandapyV20.endpoints.accounts as oanda_accounts

# ────────────────────────────────────────────────────────────────
# Environment + Tokens
# ────────────────────────────────────────────────────────────────
OANDA_ENV = "practice"
OANDA_ENV_LIVE = "live"

load_dotenv()
OANDA_API_TOKEN = os.getenv("OANDA_API_TOKEN", "")
OANDA_API_TOKEN_LIVE = os.getenv("OANDA_API_TOKEN_LIVE", "")

# ────────────────────────────────────────────────────────────────
# Account IDs (from .env with defaults)
# ────────────────────────────────────────────────────────────────
# Demo
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID", "")
OANDA_ACCOUNT_ID_1 = os.getenv("OANDA_ACCOUNT_ID_1", "101-003-39389016-001")
OANDA_ACCOUNT_ID_2 = os.getenv("OANDA_ACCOUNT_ID_2", "101-003-39389016-002")
OANDA_ACCOUNT_ID_3 = os.getenv("OANDA_ACCOUNT_ID_3", "101-003-39389016-003")
OANDA_ACCOUNT_ID_4 = os.getenv("OANDA_ACCOUNT_ID_4", "101-003-39389016-004")

# Live
OANDA_ACCOUNT_ID_1_LIVE = os.getenv("OANDA_ACCOUNT_ID_1_LIVE", "101-003-21515688-001")
OANDA_ACCOUNT_ID_2_LIVE = os.getenv("OANDA_ACCOUNT_ID_2_LIVE", "101-003-21515688-002")
OANDA_ACCOUNT_ID_3_LIVE = os.getenv("OANDA_ACCOUNT_ID_3_LIVE", "101-003-21515688-003")
OANDA_ACCOUNT_ID_4_LIVE = os.getenv("OANDA_ACCOUNT_ID_4_LIVE", "101-003-21515688-004")

# ────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────
def _collect_account_vars(var_regex: str):
    """Auto-collect account IDs matching pattern from this module."""

    out = []
    out.extend(
        (name, value)
        for name, value in vars(sys.modules[__name__]).items()
        if isinstance(name, str) and re.fullmatch(var_regex, name)
    )
    out.sort(key=lambda x: x[0])
    return out


def _discover_accounts(token: str, env_name: str, label: str):
    """
    Validate token + fetch ALL accounts visible to this token.
    Returns list[dict] on success; None on failure.
    """
    if not token:
        print(f"❌ {label}: TOKEN NOT SET")
        return None

    api = oandapyV20.API(access_token=token, environment=env_name)
    try:
        resp = api.request(oanda_accounts.AccountList())
        accounts = resp.get("accounts", [])
        print(f"✅ {label}: TOKEN VALID → {len(accounts)} account(s) visible")
        for acc in accounts:
            aid = acc.get("id", "?")
            tags = acc.get("tags", [])
            tag_str = f" | tags: {tags}" if tags else ""
            print(f"   └─ {aid}{tag_str}")
        return accounts
    except Exception as e:
        print(f"❌ {label}: TOKEN/API FAILED")
        print(f"    ⚠️ Error: {str(e)[:250]}")
        return None


def _compare_accounts(config_accounts, discovered_accounts, label: str):
    """Compare configured IDs vs OANDA visible IDs."""
    config_ids = {acc_id for _, acc_id in config_accounts if acc_id}
    discovered_ids = {acc.get("id") for acc in discovered_accounts if acc.get("id")}

    matched = config_ids & discovered_ids
    missing = config_ids - discovered_ids
    extra = discovered_ids - config_ids

    print(f"\n═══ {label} ACCOUNT COMPARISON ═══")
    print(f"Configured : {len(config_ids)}")
    print(f"OANDA sees : {len(discovered_ids)}")
    print(f"✅ Matched : {len(matched)}")
    print(f"❌ Missing : {len(missing)}")
    print(f"⚠️ Extra    : {len(extra)}")

    if matched:
        print("\n✅ Matched accounts:")
        for aid in sorted(matched):
            print(f"   {aid}")
    if missing:
        print("\n❌ Configured but NOT visible:")
        for aid in sorted(missing):
            print(f"   {aid}")
    if extra:
        print("\n⚠️ Visible but NOT in config:")
        for aid in sorted(extra):
            print(f"   {aid}")

    exact = config_ids == discovered_ids
    print(f"\n{'✅' if exact else '❌'} {label}: {'EXACT MATCH' if exact else 'MISMATCH'}")
    return exact


def _fetch_summary(acc, token, env_name):
    """Get full AccountSummary for one account."""
    aid = acc.get("id")
    api = oandapyV20.API(access_token=token, environment=env_name)
    try:
        resp = api.request(oanda_accounts.AccountSummary(aid))["account"]
        print(f"\n   📊 {aid}")
        print(f"      Currency    : {resp.get('currency','?')}")
        print(f"      Balance     : {resp.get('balance','?')}")
        print(f"      NAV         : {resp.get('nav','?')}")
        print(f"      UnrealizedPL: {resp.get('unrealizedPL','?')}")
        print(f"      MarginUsed  : {resp.get('marginUsed','?')}")
        print(f"      MarginAvail : {resp.get('marginAvailable','?')}")
        print(f"      OpenTrades  : {resp.get('openTradeCount','?')}")
        return True
    except Exception as e:
        print(f"\n   ❌ {aid} — Summary failed: {str(e)[:120]}")
        return False

api = oandapyV20.API(access_token=OANDA_API_TOKEN, environment=OANDA_ENV)

# ────────────────────────────────────────────────────────────────
# MAIN
# ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    SHOW_SUMMARY = "--summary" in sys.argv
    if SHOW_SUMMARY:
        sys.argv.remove("--summary")

    print("=" * 65)
    print("🔍 OANDA VALIDATION v7.0.0 | Token → Discovery → Compare")
    print("=" * 65)
    print(f"Demo Token : {'✅ SET' if OANDA_API_TOKEN else '❌ MISSING'}")
    print(f"Live Token : {'✅ SET' if OANDA_API_TOKEN_LIVE else '❌ MISSING'}")
    print("─" * 65)

    # ─── DEMO ───
    print("\n🟦 DEMO / PRACTICE")
    demo_cfg = _collect_account_vars(r"^OANDA_ACCOUNT_ID_\d+$")
    demo_visible = _discover_accounts(OANDA_API_TOKEN, OANDA_ENV_DEMO, "Demo Token")
    demo_ok = False
    if demo_visible:
        demo_ok = _compare_accounts(demo_cfg, demo_visible, "DEMO")
        if SHOW_SUMMARY:
            print("\n📋 DEMO SUMMARIES")
            for acc in demo_visible:
                _fetch_summary(acc, OANDA_API_TOKEN, OANDA_ENV_DEMO)

    # ─── LIVE ───
    print("\n🟥 LIVE")
    live_cfg = _collect_account_vars(r"^OANDA_ACCOUNT_ID_\d+_LIVE$")
    live_visible = _discover_accounts(OANDA_API_TOKEN_LIVE, OANDA_ENV_LIVE, "Live Token")
    live_ok = False
    if live_visible:
        live_ok = _compare_accounts(live_cfg, live_visible, "LIVE")
        if SHOW_SUMMARY:
            print("\n📋 LIVE SUMMARIES")
            for acc in live_visible:
                _fetch_summary(acc, OANDA_API_TOKEN_LIVE, OANDA_ENV_LIVE)

    # ─── FINAL ───
    print("\n" + "=" * 65)
    print(f"FINAL → DEMO: {'✅ PASS' if demo_ok else '❌ FAIL'}  |  LIVE: {'✅ PASS' if live_ok else '❌ FAIL'}")
    if demo_ok and live_ok:
        print("🎯 ALL OK")
        sys.exit(0)
    else:
        print("⚠️ CHECK LIVE TOKEN / ACCOUNT-ID / OANDA PERMISSIONS")
        sys.exit(1)
