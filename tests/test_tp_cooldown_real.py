from datetime import datetime, timedelta, timezone
import time
import fx_trade_bot_utils_v1 as U

def iso(mins_ago):
    t = datetime.now(timezone.utc) - timedelta(minutes=mins_ago)
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + "123456789Z"

def fill(inst, mins_ago, reason="TAKE_PROFIT_ORDER", tid="10625"):
    return {"type": "ORDER_FILL", "reason": reason, "instrument": inst,
            "time": iso(mins_ago), "tradesClosed": [{"tradeID": tid}]}

class FakeApi:
    def __init__(self, txs, exc=None):
        self.txs, self.exc = txs, exc
    def request(self, ep):
        if self.exc:
            raise self.exc
        n = type(ep).__name__
        if n == "AccountDetails":
            return {"account": {"lastTransactionID": "1000"}}
        if n == "TransactionsSinceID":
            return {"transactions": self.txs}
        raise AssertionError(f"unexpected endpoint {n}")

def run(txs, hours=2.0, state=None, **kw):
    state = {} if state is None else state
    locks = U.refresh_tp_cooldown_from_recent_tx(FakeApi(txs, **kw), "ACC", hours, state)
    return locks, state

def test_tp_fill_locks_pair_with_correct_until():
    locks, st = run([fill("GBP_USD", 30)])
    assert locks == ["GBP_USD"]
    _, until = st["GBP_USD"]
    remain_min = (until - time.time()) / 60
    assert 88 < remain_min < 92          # 120 - 30 = 90 min left

def test_sl_fill_ignored():
    assert run([fill("GBP_USD", 30, reason="STOP_LOSS_ORDER")])[1] == {}

def test_expired_tp_ignored():
    assert run([fill("GBP_USD", 150)])[1] == {}

def test_disabled_when_hours_zero():
    assert run([fill("GBP_USD", 5)], hours=0)[1] == {}

def test_latest_of_two_fills_wins():
    _, st = run([fill("GBP_USD", 90), fill("GBP_USD", 10, tid="2")])
    assert (st["GBP_USD"][1] - time.time()) / 60 > 105

def test_api_error_fails_open():
    assert run([], exc=RuntimeError("boom"))[1] == {}
