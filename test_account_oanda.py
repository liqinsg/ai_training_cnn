import oandapyV20
from config import OANDA_ACCOUNT_ID_1, OANDA_API_TOKEN, OANDA_ENV

print(f"Testing Account: {OANDA_ACCOUNT_ID_1} | Env: {OANDA_ENV}")
api = oandapyV20.API(access_token=OANDA_API_TOKEN, environment=OANDA_ENV)

try:
    from oandapyV20.endpoints.accounts import AccountDetails
    OANDA_ACCOUNT_ID_1 = '101-003-39389016-003'
    resp = api.request(AccountDetails(OANDA_ACCOUNT_ID_1))

    print("✅ SUCCESS — Account works!")
    print(f"Name: {resp['account']['alias']} | Balance: {resp['account']['balance']}")
except Exception as e:
    print(f"❌ FAILED — Error: {str(e)}")
    if "insufficient authorization" in str(e):
        print("👉 Fix: Add *03 to your app's allowed accounts & regenerate token")
    elif "No such account" in str(e):
        print("👉 Fix: Wrong Account ID or wrong environment (practice/live)")