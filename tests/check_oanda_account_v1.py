import sys
import oandapyV20
from oandapyV20.endpoints.accounts import AccountSummary
from utils.oanda_execution import api, OANDA_ACCOUNT_ID

def check_account(account_id: str):
    r = AccountSummary(account_id)
    resp = api.request(r)
    print('✅ ACCOUNT OK:', resp['account']['id'], '—', resp['account']['currency'])

def main():
    # Defaults to current OANDA_ACCOUNT_ID from utils.oanda_execution
    account_ids = [str(OANDA_ACCOUNT_ID)]

    # If user passed args, use them instead
    # Example: python check_oanda_account_v1.py ac1 ac2
    if len(sys.argv) > 1:
        # allow comma-separated as one arg too: "ac1,ac2"
        raw = []
        for arg in sys.argv[1:]:
            raw.extend([x.strip() for x in arg.split(',') if x.strip()])

        account_ids = raw

    print("Using account ids:", account_ids)

    for acc in account_ids:
        print(f"\n--- Checking {acc!r} ---")
        try:
            check_account(acc)
        except Exception as e:
            print('❌ FORBIDDEN / MISMATCH:', str(e))

if __name__ == "__main__":
    main()