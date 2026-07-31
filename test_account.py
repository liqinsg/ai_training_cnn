import oandapyV20
from oandapyV20.endpoints.accounts import AccountSummary
from utils.oanda_execution import api
for OANDA_ACCOUNT_ID  in ['101-003-39389016-001', '101-003-39389016-002', '101-003-39389016-003']:
    try:
        r = AccountSummary(OANDA_ACCOUNT_ID)
        resp = api.request(r)
        print('✅ ACCOUNT OK:', resp['account']['id'], '—', resp['account']['currency'])
    except Exception as e:
        print('❌ FORBIDDEN / MISMATCH:', str(e))
