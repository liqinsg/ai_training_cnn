from datetime import datetime, timedelta, timezone
from utils.cooldown_tp import recent_tp_close_mins, _parse_oanda_time

TAG = "fx_bot_v685_profile2_entry"

def ts(mins_ago):
    t = datetime.now(timezone.utc) - timedelta(minutes=mins_ago)
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + "123456789Z"   # 9-digit like OANDA

def trade(mins_ago, tp="FILLED", tag=TAG):
    return {"state": "CLOSED", "closeTime": ts(mins_ago),
            "takeProfitOrder": {"state": tp},
            "clientExtensions": {"tag": tag}}

class FakeApi:
    def __init__(self, trades=None, exc=None):
        self.trades, self.exc = trades or [], exc
    def request(self, _endpoint):
        if self.exc:
            raise self.exc
        return {"trades": self.trades}

def run(api): return recent_tp_close_mins(api, "ACC", "EUR_JPY", TAG)

def test_parse_nanosecond_timestamp():
    assert _parse_oanda_time("2026-10-16T01:02:03.123456789Z").microsecond == 123456

def test_no_trades():
    assert run(FakeApi([])) is None

def test_recent_tp_returns_minutes():
    m = run(FakeApi([trade(2)]))
    assert 1.5 < m < 2.5

def test_sl_close_ignored():
    assert run(FakeApi([trade(2, tp="CANCELLED")])) is None

def test_other_profile_tag_ignored():
    assert run(FakeApi([trade(2, tag="fx_bot_v685_profile3_entry")])) is None

def test_picks_latest_of_many():
    m = run(FakeApi([trade(90), trade(5), trade(30)]))
    assert 4.5 < m < 5.5

def test_api_error_fails_open():
    assert run(FakeApi(exc=RuntimeError("boom"))) is None

def test_cooldown_decision_boundary():
    m = run(FakeApi([trade(10)]))
    assert m < 0.25 * 60          # 0.25h window -> in cooldown
    assert not (m < 0.1 * 60)     # 0.1h window  -> expired