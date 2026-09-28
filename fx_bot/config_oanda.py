# config_oanda.py — v6.8.5 | Multi-Account Config + Self-Validation (CLI)
# ────────────────────────────────────────────────────────────────
"""
Central configuration — edit this file to control all strategy behaviour.
Do not hardcode these values elsewhere in the codebase.
"""
import os
import sys
from dotenv import load_dotenv
import oandapyV20
import oandapyV20.endpoints as oanda_endpoint

OANDA_ENV = "practice"

load_dotenv()
OANDA_API_TOKEN = os.getenv("OANDA_API_TOKEN", "")

# ────────────────────────────────────────────────────────────────
# Account IDs (from .env) — DEMO / PRACTICE
# ────────────────────────────────────────────────────────────────
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID", "")

OANDA_ACCOUNT_ID_1 = os.getenv("OANDA_ACCOUNT_ID_1", "101-003-21515688-001")
OANDA_ACCOUNT_ID_2 = os.getenv("OANDA_ACCOUNT_ID_2", "101-003-21515688-002")
OANDA_ACCOUNT_ID_3 = os.getenv("OANDA_ACCOUNT_ID_3", "101-003-21515688-003")
OANDA_ACCOUNT_ID_4 = os.getenv("OANDA_ACCOUNT_ID_4", "101-003-21515688-004")

# ────────────────────────────────────────────────────────────────
# Account IDs — LIVE
# ────────────────────────────────────────────────────────────────
OANDA_ENV_LIVE = os.getenv("OANDA_ENV_LIVE", "live")
OANDA_API_TOKEN_LIVE = os.getenv("OANDA_API_TOKEN_LIVE", "")
OANDA_ACCOUNT_ID_1_LIVE = os.getenv("OANDA_ACCOUNT_ID_1_LIVE", "")
OANDA_ACCOUNT_ID_2_LIVE = os.getenv("OANDA_ACCOUNT_ID_2_LIVE", "")
OANDA_ACCOUNT_ID_3_LIVE = os.getenv("OANDA_ACCOUNT_ID_3_LIVE", "")
OANDA_ACCOUNT_ID_4_LIVE = os.getenv("OANDA_ACCOUNT_ID_4_LIVE", "")


# ────────────────────────────────────────────────────────────────
# 🔍 SELF-VALIDATION — Run: python config_oanda.py [ac1 ac2 ...]
#   Examples:
#     python config_oanda.py                     # default: all demo + all live
#     python config_oanda.py 003-12345-001
#     python config_oanda.py --demo-only
#     python config_oanda.py --live-only
#     python config_oanda.py "003-12345-001,003-12345-002"
# ────────────────────────────────────────────────────────────────

def _build_api(token, env):
    if not token:
        return None
    return oandapyV20.API(access_token=token, environment=env)


def _fmt_trade(t):
    side = t.get("side", "?").upper()
    units = float(t.get("currentUnits", 0))
    pnl = float(t.get("unrealizedPL", 0))
    return f"      📌 {side:4s} {units:>10.2f}  P&L={pnl:+.2f}"


def _validate_one(api, account_id, label):
    if not api or not account_id:
        print(f"  ⚠️  {label}: SKIP (no api/account)")
        return False
    try:
        resp = api.request(oanda_endpoint.AccountSummary(account_id))
        acc = resp["account"]
        balance = float(acc.get("balance", 0))
        unrealized = float(acc.get("unrealizedPL", 0))
        nav = float(acc.get("NAV", balance + unrealized))
        margin_avail = float(acc.get("marginAvailable", 0))
        margin_used = float(acc.get("marginUsed", 0))
        margin_rate = acc.get("marginRate", "N/A")
        trades = acc.get("trades", [])
        open_positions = acc.get("openPositions", len(trades))

        print(f"  ✅ {label}")
        print(f"     ID       : {acc['id']}")
        print(f"     Currency : {acc['currency']}  MarginRate: {margin_rate}")
        print(f"     Balance  : {balance:,.2f}  Unrealized: {unrealized:+,.2f}  NAV: {nav:,.2f}")
        print(f"     Margin   : used={margin_used:,.2f}  available={margin_avail:,.2f}")
        print(f"     Positions: {open_positions}")
        for t in trades:
            print(_fmt_trade(t))
        if not trades:
            print("      (none)")
        return True
    except Exception as e:
        msg = str(e).split("\n")[0][:160]
        print(f"  ❌ {label}: {account_id}")
        print(f"     Error: {msg}")
        return False


def validate_account(account_id, label="Account", api=None, env=None):
    if api is None:
        api = _build_api(OANDA_API_TOKEN, env or OANDA_ENV)
    return _validate_one(api, account_id, label)


def parse_cli_accounts(argv):
    accounts = []
    for arg in argv:
        arg = arg.strip()
        if not arg:
            continue
        accounts.extend(x.strip() for x in arg.split(",") if x.strip())
    return accounts


def oanda_tick(instrument):
    return api.request(oanda_endpoint.InstrumentsCandles(instrument=instrument,
    params={"count": 1, "granularity": "M1", "price": "BA"}))["candles"][0]


api = oandapyV20.API(access_token=OANDA_API_TOKEN, environment=OANDA_ENV)


if __name__ == "__main__":
    argv = sys.argv[1:]
    demo_only = "--demo-only" in argv
    live_only = "--live-only" in argv
    argv = [a for a in argv if a not in ("--demo-only", "--live-only")]
    cli_accounts = parse_cli_accounts(argv)

    print("=" * 70)
    print("🔍 OANDA ACCOUNT VALIDATION — v6.8.5")
    print("=" * 70)
    print(f"  DEMO  token : {'✅ SET' if OANDA_API_TOKEN else '❌ MISSING'}  env={OANDA_ENV}")
    print(f"  LIVE  token : {'✅ SET' if OANDA_API_TOKEN_LIVE else '❌ MISSING'}  env={OANDA_ENV_LIVE}")

    if cli_accounts:
        print()
        print("🎯 MODE: CLI — validating provided account ids (practice env)")
        demo_api = _build_api(OANDA_API_TOKEN, OANDA_ENV)
        for i, aid in enumerate(cli_accounts, 1):
            _validate_one(demo_api, aid, f"🧪 CLI #{i}")
    else:
        DEMO_ACCOUNTS = [
            ("🔵 ACCOUNT 1 (Demo)", OANDA_ACCOUNT_ID_1),
            ("⚪ ACCOUNT 2 (Demo)", OANDA_ACCOUNT_ID_2),
            ("🟣 ACCOUNT 3 (Demo)", OANDA_ACCOUNT_ID_3),
            ("🟡 ACCOUNT 4 (Demo)", OANDA_ACCOUNT_ID_4),
        ]
        LIVE_ACCOUNTS = [
            ("🔴 ACCOUNT 1 (Live)", OANDA_ACCOUNT_ID_1_LIVE),
            ("🟠 ACCOUNT 2 (Live)", OANDA_ACCOUNT_ID_2_LIVE),
            ("🟤 ACCOUNT 3 (Live)", OANDA_ACCOUNT_ID_3_LIVE),
            ("🟥 ACCOUNT 4 (Live)", OANDA_ACCOUNT_ID_4_LIVE),
        ]

        ok_any = False

        if not live_only:
            print()
            print("─" * 70)
            print("📦 DEMO / PRACTICE ENVIRONMENT")
            print("─" * 70)
            demo_api = _build_api(OANDA_API_TOKEN, OANDA_ENV)
            for label, aid in DEMO_ACCOUNTS:
                ok_any = _validate_one(demo_api, aid, label) or ok_any

        if not demo_only:
            print()
            print("─" * 70)
            print("💵 LIVE / REAL ENVIRONMENT")
            print("─" * 70)
            live_api = _build_api(OANDA_API_TOKEN_LIVE, OANDA_ENV_LIVE)
            for label, aid in LIVE_ACCOUNTS:
                ok_any = _validate_one(live_api, aid, label) or ok_any

    print()
    print("=" * 70)
    if ok_any:
        print("✅ At least one account OK.")
    else:
        print("❌ No accounts OK — check tokens / account ids / permissions.")
    print("=" * 70)