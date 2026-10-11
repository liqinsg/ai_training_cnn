# test_market_gate.py
import fx_trade_bot_utils as u

class FakeAPI:
    def __init__(self, resp=None, exc=None): self.resp, self.exc, self.calls = resp, exc, 0
    def request(self, r):
        self.calls += 1
        if self.exc: raise self.exc
        return self.resp

def _reset(): u._market_cache.update(ts=0.0, closed=None)

def test_closed():
    _reset()
    assert u.forex_market_closed(FakeAPI({"prices": [{"tradeable": False}]}), "acct") is True

def test_open():
    _reset()
    assert u.forex_market_closed(FakeAPI({"prices": [{"tradeable": True}]}), "acct") is False

def test_error_fails_closed_and_is_not_cached():
    _reset()
    api = FakeAPI(exc=ConnectionError("boom"))
    assert u.forex_market_closed(api, "acct") is True
    assert u._market_cache["closed"] is None

def test_cache_hit_skips_api():
    _reset()
    api = FakeAPI({"prices": [{"tradeable": True}]})
    u.forex_market_closed(api, "acct"); u.forex_market_closed(api, "acct")
    assert api.calls == 1

def test_missing_tradeable_key_means_closed():
    _reset()
    assert u.forex_market_closed(FakeAPI({"prices": [{}]}), "acct") is True