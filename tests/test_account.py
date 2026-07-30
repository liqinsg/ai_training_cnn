python -c "
import oandapyV20
from oandapyV20.endpoints.accounts import AccountSummary
from utils.oanda_execution import api, OANDA_ACCOUNT_ID_1

try:
    r = AccountSummary(OANDA_ACCOUNT_ID_1)
    resp = api.request(r)
    print('✅ ACCOUNT OK:', resp['account']['id'], '—', resp['account']['currency'])
except Exception as e:
    print('❌ FORBIDDEN / MISMATCH:', str(e))
"
