# config_oanda.py — v6.8.4 | Multi-Account Config + Self-Validation (CLI)
# ────────────────────────────────────────────────────────────────
"""
Central configuration — edit this file to control all strategy behaviour.
Do not hardcode these values elsewhere in the codebase.
"""
import os
import sys
from dotenv import load_dotenv
import oandapyV20
# from oandapyV20.endpoints.accounts import AccountSummary
# from oandapyV20.endpoints.instruments import InstrumentsCandles
import oandapyV20.endpoints as oanda_endpoint


OANDA_ENV = "practice"

load_dotenv()
OANDA_API_TOKEN = os.getenv("OANDA_API_TOKEN", "")

# ────────────────────────────────────────────────────────────────
# Account IDs (from .env)
# ────────────────────────────────────────────────────────────────
# Optional alias (your #1 request)
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID", "")

# Main 3 accounts we validate by default when no args are passed
OANDA_ACCOUNT_ID_1 = os.getenv("OANDA_ACCOUNT_ID_1", "")
OANDA_ACCOUNT_ID_2 = os.getenv("OANDA_ACCOUNT_ID_2", "")
OANDA_ACCOUNT_ID_3 = os.getenv("OANDA_ACCOUNT_ID_3", "")


# ────────────────────────────────────────────────────────────────
# 🔍 SELF-VALIDATION — Run: python config_oanda.py [ac1 ac2 ...]
#   Examples:
#     python config_oanda.py
#     python config_oanda.py 003-12345-001 003-12345-002
#     python config_oanda.py "003-12345-001,003-12345-002"
#     python config_oanda.py --include-default 003-12345-009
# ────────────────────────────────────────────────────────────────
def validate_account(account_id, label="Account"):
    """Validate an OANDA account ID and return True/False."""
    if not account_id:
        print(f"❌ {label}: NOT SET")
        return False

    api = oandapyV20.API(access_token=OANDA_API_TOKEN, environment=OANDA_ENV)

    try:
        r = oanda_endpoint.AccountSummary(account_id)
        resp = api.request(r)
        acc = resp["account"]
        print(
            f"✅ {label} OK: {acc['id']} — {acc['currency']} "
            f"| Balance: {acc.get('balance', 'N/A')}"
        )
        return True
    except Exception as e:
        print(f"❌ {label} FAILED: {account_id}")
        print(f"   ⚠️  Error: {str(e)[:140]}")
        return False


def parse_cli_accounts(argv):
    """
    Accepts:
      - python config_oanda.py ac1 ac2
      - python config_oanda.py "ac1,ac2"
    Returns list[str].
    """
    accounts = []
    for arg in argv:
        arg = arg.strip()
        if not arg:
            continue
        parts = [x.strip() for x in arg.split(",") if x.strip()]
        accounts.extend(parts)
    return accounts

api = oandapyV20.API(access_token=OANDA_API_TOKEN, environment=OANDA_ENV)

def oanda_tick(instrument):
    return api.request(oanda_endpoint.InstrumentsCandles(instrument=instrument,
    params={"count":1, "granularity":"M1", "price":"BA"}))["candles"][0]

if __name__ == "__main__":
    print("=" * 60)
    print("🔍 OANDA ACCOUNT VALIDATION — v6.8.4")
    print("=" * 60)
    print(f"API Token:   {'✅ SET' if OANDA_API_TOKEN else '❌ MISSING'}")
    print(f"Environment: {OANDA_ENV}")
    print("-" * 60)

    # (1) Print requested variables
    print(f"OANDA_ACCOUNT_ID   : {OANDA_ACCOUNT_ID or 'NOT SET'}")
    print(f"OANDA_ACCOUNT_ID_1 : {OANDA_ACCOUNT_ID_1 or 'NOT SET'}")
    print(f"OANDA_ACCOUNT_ID_2 : {OANDA_ACCOUNT_ID_2 or 'NOT SET'}")
    print(f"OANDA_ACCOUNT_ID_3 : {OANDA_ACCOUNT_ID_3 or 'NOT SET'}")

    print("-" * 60)

    argv = sys.argv[1:]

    # Optional flag: if args are provided, also validate defaults
    include_default = False
    if "--include-default" in argv:
        include_default = True
        argv = [a for a in argv if a != "--include-default"]

    cli_accounts = parse_cli_accounts(argv)

    defaults = [
        ("🔵 ACCOUNT 1 (Default)", OANDA_ACCOUNT_ID_1),
        ("⚪ ACCOUNT 2 (Default)", OANDA_ACCOUNT_ID_2),
        ("🟣 ACCOUNT 3 (Default)", OANDA_ACCOUNT_ID_3),
    ]

    ok_any = False

    if not cli_accounts:
        # (2) If no args -> validate ac1, ac2, ac3
        print()
        print("MODE: default — validating ACCOUNT 1/2/3 from .env")
        print()

        for label, acc_id in defaults:
            ok_any = validate_account(acc_id, label) or ok_any

    else:
        # (3) If args are provided -> validate manually fed accounts
        print()
        print("MODE: CLI — validating provided manual account ids")
        if include_default:
            print("INFO : --include-default enabled; also validating default ACCOUNT 1/2/3")
        print()

        # Optionally include defaults first
        if include_default:
            for label, acc_id in defaults:
                ok_any = validate_account(acc_id, label + " +default") or ok_any

        # Validate CLI accounts
        for i, acc_id in enumerate(cli_accounts, start=1):
            ok_any = validate_account(acc_id, f"🧪 CLI ACCOUNT {i}") or ok_any

    print()
    print("=" * 60)
    if ok_any:
        print("✅ At least one account OK.")
    else:
        print("❌ No accounts OK — check API token / account ids / permissions.")
    print("=" * 60)
