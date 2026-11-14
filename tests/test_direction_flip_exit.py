from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from fx_trade_bot_utils_v1 import should_close_by_opposite_signal


def test_close_long_when_new_signal_turns_sell():
    close_now, detail = should_close_by_opposite_signal(
        {"direction": "long"},
        "SELL",
        pair="GBP_JPY",
    )

    assert close_now is True
    assert "GBP_JPY" in detail
    assert "LONG" in detail
    assert "SELL" in detail


def test_close_short_when_new_signal_turns_buy():
    close_now, detail = should_close_by_opposite_signal(
        {"direction": "short"},
        "BUY",
        pair="USD_JPY",
    )

    assert close_now is True
    assert "USD_JPY" in detail
    assert "SHORT" in detail
    assert "BUY" in detail


def test_keep_position_when_signal_is_same_direction():
    close_now, detail = should_close_by_opposite_signal(
        {"direction": "long"},
        "BUY",
        pair="EUR_USD",
    )

    assert close_now is False
    assert detail == ""
