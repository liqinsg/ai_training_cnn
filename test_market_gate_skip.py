import fx_trade_bot_utils as u

class FakeAPI:
    def __init__(self, resp=None, exc=None):
        self.resp = resp
        self.exc = exc
        self.calls = 0
    def request(self, req):
        self.calls += 1
        if self.exc: raise self.exc
        return self.resp

def _reset():
    u._market_cache = {"ts":0.0,"closed":None,"halted_instruments":{}}

def test_halted_skips_open():
    _reset()
    api = FakeAPI({"prices": [{"tradeable": False}]})
    r = u.open_oanda_order_simple(api, "acct", "AUD_JPY", "BUY", 1000, None, None)
    assert r["status"] == "SKIPPED"
    assert r["skipped"] == True
    assert api.calls == 1  # 只查一次状态，不发OrderCreate

def test_halted_skips_close():
    _reset()
    api = FakeAPI({"prices": [{"tradeable": False}]})
    assert u.close_position(api, "acct", "AUD_JPY") == True  # 跳过=视为成功

def test_cache_prevents_duplicate_check():
    _reset()
    api = FakeAPI({"prices": [{"tradeable": False}]})
    u.open_oanda_order_simple(api, "acct", "AUD_JPY", "BUY", 1000, None, None)
    u.open_oanda_order_simple(api, "acct", "AUD_JPY", "BUY", 1000, None, None)
    assert api.calls == 1  # 第二次缓存命中，不查API

def test_explicit_mark_halted():
    _reset()
    u.mark_instrument_halted("AUD_JPY")
    api = FakeAPI({"prices": [{"tradeable": True}]})  # API说可交易但标注优先
    assert u.can_trade(api, "acct", "AUD_JPY") == False
    assert api.calls == 0  # 连查都跳过
    
if __name__ == "__main__":
    test_halted_skips_open()
    print("✅ test_halted_skips_open — PASSED")

    test_halted_skips_close()
    print("✅ test_halted_skips_close — PASSED")

    test_cache_prevents_duplicate_check()
    print("✅ test_cache_prevents_duplicate_check — PASSED")

    test_explicit_mark_halted()
    print("✅ test_explicit_mark_halted — PASSED")

    print("\n🎉 ALL TESTS PASSED")