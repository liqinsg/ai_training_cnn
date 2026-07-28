import oandapyV20
from oandapyV20.endpoints.accounts import AccountSummary
from utils.oanda_execution import api
# from config import OANDA_ACCOUNT_ID
OANDA_ACCOUNT_ID = "101-003-39389016-002"
print(OANDA_ACCOUNT_ID)
try:
    r = AccountSummary(OANDA_ACCOUNT_ID)
    resp = api.request(r)
    print('✅ ACCOUNT OK:', resp['account']['id'], '—', resp['account']['currency'])
except Exception as e:
    print('❌ FORBIDDEN / MISMATCH:', str(e))
