import oandapyV20
from oandapyV20.endpoints.accounts import AccountList, AccountSummary
from config_oanda import OANDA_API_TOKEN, OANDA_ENV

# Initialize OANDA client directly (no utils import)
api = oandapyV20.API(access_token=OANDA_API_TOKEN, environment=OANDA_ENV)

def check_all_accounts():
    try:
        # Step 1: Fetch list of all sub-account IDs
        account_list_request = AccountList()
        list_response = api.request(account_list_request)
        accounts = list_response.get("accounts", [])

        if not accounts:
            print("❌ No accounts found for this API token.")
            return

        print(f"Found {len(accounts)} sub-account(s):\n" + "-" * 40)

        # Step 2: Loop through each account and fetch summary
        for acc in accounts:
            acc_id = acc.get("id")
            tags = ", ".join(acc.get("tags", []))
            tag_str = f" [{tags}]" if tags else ""

            try:
                summary_request = AccountSummary(acc_id)
                summary = api.request(summary_request).get("account", {})

                currency = summary.get("currency", "N/A")
                balance = summary.get("balance", "N/A")
                nav = summary.get("NAV", "N/A")
                unrealized_pnl = summary.get("unrealizedPL", "0.00")

                print(f"✅ Account: {acc_id}{tag_str}")
                print(f"   Currency : {currency}")
                print(f"   Balance  : {balance} {currency}")
                print(f"   NAV      : {nav} {currency}")
                print(f"   Unrealized P/L: {unrealized_pnl} {currency}")
                print("-" * 40)

            except Exception as e:
                print(f"❌ Failed to fetch summary for {acc_id}: {e}\n" + "-" * 40)

    except Exception as e:
        print(f"❌ Account list request failed: {e}")

if __name__ == "__main__":
    check_all_accounts()