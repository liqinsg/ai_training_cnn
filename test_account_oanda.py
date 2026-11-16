from config_oanda import OANDA_ACCOUNT_ID, OANDA_ENV, api, request_with_retry

print(f"Testing Account: {OANDA_ACCOUNT_ID} | Env: {OANDA_ENV}")

try:
    from oandapyV20.endpoints.accounts import AccountDetails

    OANDA_ACCOUNT_ID = "101-003-39389016-003"
    resp = request_with_retry(api, AccountDetails(OANDA_ACCOUNT_ID), label="AccountDetails")

    print("✅ SUCCESS — Account works!")
    print(f"Name: {resp['account']['alias']} | Balance: {resp['account']['balance']}")
except Exception as e:
    print(f"❌ FAILED — Error: {str(e)}")
    if "insufficient authorization" in str(e):
        print("👉 Fix: Add *03 to your app's allowed accounts & regenerate token")
    elif "No such account" in str(e):
        print("👉 Fix: Wrong Account ID or wrong environment (practice/live)")
