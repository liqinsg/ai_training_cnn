import pytest
import time

from config_oanda import (
    OANDA_ENV,
    OANDA_ACCOUNT_ID,
    OANDA_API_TOKEN,
)

from utils.oanda_execution import (
    forex_market_closed,
    get_oanda_candles,
    has_open_position,
    open_oanda_order,
    # check_order_status,
    close_all_trades,
)

# ---------------------------------------
# ENVIRONMENT SAFETY CHECK
# ---------------------------------------

@pytest.fixture(scope="session", autouse=True)
def validate_environment():
    """
    Never allow tests to run on a live account.
    """
    assert OANDA_ENV.lower() == "practice", (
        f"Refusing to run tests on environment: {OANDA_ENV}"
    )

    assert OANDA_ACCOUNT_ID
    assert OANDA_API_TOKEN


# ---------------------------------------
# MARKET STATUS
# ---------------------------------------

def test_market_status():
    result = is_forex_market_open()
    assert isinstance(result, bool)


# ---------------------------------------
# CANDLE DOWNLOAD
# ---------------------------------------

def test_get_oanda_candles():
    df = get_oanda_candles(
        instrument="EUR_USD",
        timeframe="15m",
        count=50
    )

    assert not df.empty

    required_cols = [
        "Open",
        "High",
        "Low",
        "Close",
        "Volume"
    ]

    for c in required_cols:
        assert c in df.columns


# ---------------------------------------
# TRADE LIFECYCLE
# ---------------------------------------

@pytest.fixture
def cleanup_after_test():
    """
    Ensure account is clean before & after.
    """
    close_all_trades()

    yield

    close_all_trades()


# def test_open_and_close_trade(cleanup_after_test):
#     """
#     REAL trade on Practice account.
#     """

#     signal = {
#         "pair": "EUR_USD",
#         "action": "BUY",
#         "stop_loss": 1.05000,
#         "take_profit": 1.25000,
#     }

#     result = open_oanda_order(
#         signal=signal,
#         units=1000,
#         tag="PYTEST_REAL_TRADE"
#     )

#     assert result["status"] == "SUCCESS"

#     assert "order_id" in result
#     assert "instrument" in result

#     time.sleep(2)

#     assert has_open_position("EUR_USD") is True

#     status = check_order_status("EUR_USD")

#     assert status["summary"]["open_count"] > 0

#     close_result = close_all_trades()

#     assert close_result["status"] == "SUCCESS"

#     time.sleep(2)

#     assert has_open_position("EUR_USD") is False


# ---------------------------------------
# ORDER STATUS
# ---------------------------------------

# def test_check_status_returns_expected_fields():
#     status = check_order_status()

#     assert isinstance(status, dict)

#     assert "open_trades" in status
#     assert "recent_orders" in status
#     assert "summary" in status


# ---------------------------------------
# HAS POSITION
# ---------------------------------------

def test_has_open_position_returns_bool():
    result = has_open_position("EUR_USD")

    assert isinstance(result, bool)


# ---------------------------------------
# CLOSE ALL
# ---------------------------------------

def test_close_all_trades():
    result = close_all_trades()

    assert isinstance(result, dict)

    assert "status" in result