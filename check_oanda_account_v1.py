import re
import importlib
import argparse
import oandapyV20
from oandapyV20.endpoints.accounts import AccountSummary

config = importlib.import_module("config_oanda")

OANDA_API_TOKEN = getattr(config, "OANDA_API_TOKEN", None)
OANDA_API_TOKEN_LIVE = getattr(config, "OANDA_API_TOKEN_LIVE", None)
OANDA_ENV_DEMO = getattr(config, "OANDA_ENV", "practice")
OANDA_ENV_LIVE = getattr(config, "OANDA_ENV_LIVE", "live")

assert OANDA_API_TOKEN and OANDA_API_TOKEN_LIVE, "OANDA TOKEN not found"

def collect_account_ids(prefix_regex: str):
    ids = []
    for name, value in vars(config).items():
        if re.fullmatch(prefix_regex, name):
            ids.append(str(value))
    return sorted(ids)

demo_account_ids = collect_account_ids(r"OANDA_ACCOUNT_ID_\d+")
live_account_ids = collect_account_ids(r"OANDA_ACCOUNT_ID_LIVE_\d+")

def check_accounts(env_value, env_name, account_ids):
    print(f"\n========== Checking {env_name.upper()} ==========")
    api = oandapyV20.API(access_token=OANDA_API_TOKEN, environment=env_value)

    if not account_ids:
        print(f"❌ No {env_name} account IDs found in config_oanda.py.")
        return

    for acc_id in account_ids:
        try:
            summary_request = AccountSummary(acc_id)
            summary = api.request(summary_request).get("account", {})

            currency = summary.get("currency", "N/A")
            balance = summary.get("balance", "N/A")
            nav = summary.get("NAV", "N/A")
            unrealized_pnl = summary.get("unrealizedPL", "0.00")

            print(f"✅ Account: {acc_id}")
            print(f"   Currency : {currency}")
            print(f"   Balance  : {balance} {currency}")
            print(f"   NAV      : {nav} {currency}")
            print(f"   Unrealized P/L: {unrealized_pnl} {currency}")
            print("-" * 40)

        except Exception as e:
            print(f"❌ Failed to fetch summary for {acc_id}: {e}\n" + "-" * 40)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--demo", action="store_true", help="Check demo (practice) accounts only")
    parser.add_argument("-l", "--live", action="store_true", help="Check live accounts only")
    args = parser.parse_args()

    # If neither flag => do both
    check_demo = args.demo or (not args.demo and not args.live)
    check_live = args.live or (not args.demo and not args.live)

    if check_demo:
        check_accounts(OANDA_ENV_DEMO, "demo", demo_account_ids)
    if check_live:
        check_accounts(OANDA_ENV_LIVE, "live", live_account_ids)

if __name__ == "__main__":
    main()