import pytest
from unittest.mock import Mock, call

from fx_trade_bot_utils import open_oanda_order

# We need to provide mocks for the external dependencies used in open_oanda_order.
# Assuming these are imported at module level in fx_trade_bot_utils:
# - logger
# - price_decimals
# - pip_size
# - OrderCreate
#
# We monkeypatch them in the tests.

@pytest.fixture(autouse=True)
def patch_dependencies(monkeypatch):
    logger_mock = Mock()
    price_decimals_mock = Mock(return_value=5)
    pip_size_mock = Mock(return_value=0.0001)

    # Patch into the target module
    monkeypatch.setattr("fx_trade_bot_utils.logger", logger_mock)
    monkeypatch.setattr("fx_trade_bot_utils.price_decimals", price_decimals_mock)
    monkeypatch.setattr("fx_trade_bot_utils.pip_size", pip_size_mock)

    # Patch OrderCreate so we can assert it is constructed correctly but doesn't do real work
    class DummyOrderCreate:
        def __init__(self, accountID, data):
            self.accountID = accountID
            self.data = data

    monkeypatch.setattr("fx_trade_bot_utils.OrderCreate", DummyOrderCreate)

    # Expose for assertions if needed
    return {
        "logger": logger_mock,
        "price_decimals": price_decimals_mock,
        "pip_size": pip_size_mock,
    }


@pytest.mark.parametrize(
    "signal, units, current_price, api_resp, trailing_tp, dynamic_tp, max_sl_pips, max_sl_pct, telegram_send, cfg, expected_tp_calls",
    [
        (
            # id: happy_buy_with_tp
            {"pair": "EUR_USD", "action": "BUY", "stop_loss": 1.0950, "take_profit": 1.1050},
            1000,
            1.1000,
            {
                "orderFillTransaction": {
                    "id": "123",
                    "price": 1.1000,
                }
            },
            False,
            False,
            None,
            0.03,
            None,
            None,
            1,
        ),
        (
            # id: happy_sell_with_tp
            {"pair": "GBP_USD", "action": "SELL", "stop_loss": 1.3050, "take_profit": 1.2950},
            2000,
            1.3000,
            {
                "orderFillTransaction": {
                    "id": "456",
                    "price": 1.3000,
                }
            },
            False,
            False,
            None,
            0.03,
            None,
            None,
            1,
        ),
        (
            # id: happy_buy_no_tp_when_trailing
            {"pair": "EUR_USD", "action": "BUY", "stop_loss": 1.0950, "take_profit": 1.1050},
            1000,
            1.1000,
            {
                "orderFillTransaction": {
                    "id": "789",
                    "price": 1.1000,
                }
            },
            True,   # trailing_tp enabled => TP not created
            False,
            None,
            0.03,
            None,
            None,
            0,
        ),
        (
            # id: happy_buy_tp_blocked_by_price_direction
            {"pair": "EUR_USD", "action": "BUY", "stop_loss": 1.0950, "take_profit": 1.0955},
            1000,
            1.1000,
            {
                "orderFillTransaction": {
                    "id": "111",
                    "price": 1.1000,
                }
            },
            False,
            False,
            None,
            0.03,
            None,
            None,
            0,     # TP not created because tp <= entry_price for BUY
        ),
        (
            # id: happy_sell_tp_blocked_by_price_direction
            {"pair": "EUR_USD", "action": "SELL", "stop_loss": 1.1050, "take_profit": 1.1040},
            1000,
            1.1000,
            {
                "orderFillTransaction": {
                    "id": "222",
                    "price": 1.1000,
                }
            },
            False,
            False,
            None,
            0.03,
            None,
            None,
            0,     # TP not created because tp >= entry_price for SELL
        ),
        (
            # id: happy_order_create_transaction_only
            {"pair": "EUR_USD", "action": "BUY", "stop_loss": 1.0950, "take_profit": 1.1050},
            1000,
            1.1000,
            {
                "orderCreateTransaction": {
                    "id": "333",
                }
            },
            False,
            False,
            None,
            0.03,
            None,
            None,
            1,     # TP created, trade_id from orderCreateTransaction
        ),
    ],
    ids=[
        "happy_buy_with_tp",
        "happy_sell_with_tp",
        "happy_buy_no_tp_when_trailing",
        "happy_buy_tp_blocked_by_price_direction",
        "happy_sell_tp_blocked_by_price_direction",
        "happy_order_create_transaction_only",
    ],
)
def test_open_oanda_order_happy_paths(
    signal,
    units,
    current_price,
    api_resp,
    trailing_tp,
    dynamic_tp,
    max_sl_pips,
    max_sl_pct,
    telegram_send,
    cfg,
    expected_tp_calls,
    patch_dependencies,
):
    # Act
    api_mock = Mock()
    api_mock.request = Mock(return_value=api_resp)

    result = open_oanda_order(
        signal=signal,
        units=units,
        current_price=current_price,
        api=api_mock,
        oanda_account_id="acct-1",
        oanda_token="token-1",
        trailing_tp=trailing_tp,
        dynamic_tp=dynamic_tp,
        max_sl_pips=max_sl_pips,
        max_sl_pct=max_sl_pct,
        telegram_send=telegram_send,
        cfg=cfg,
    )

    # Assert
    assert result["status"] == "OK"
    assert result["response"] == api_resp

    # First request must be MARKET order
    first_call = api_mock.request.call_args_list[0]
    market_order_data = first_call[0][0].data
    assert market_order_data["order"]["type"] == "MARKET"
    assert market_order_data["order"]["instrument"] == signal["pair"]
    expected_units = str(units if signal["action"] == "BUY" else -units)
    assert market_order_data["order"]["units"] == expected_units

    # SL order should be created once if trade_id exists
    assert api_mock.request.call_count >= 1
    sl_calls = [
        c for c in api_mock.request.call_args_list[1:]  # skip first MARKET call
        if c[0][0].data["order"]["type"] == "STOP_LOSS"
    ]
    if "orderFillTransaction" in api_resp or "orderCreateTransaction" in api_resp:
        assert len(sl_calls) == 1
    else:
        # No trade_id => no SL / TP
        assert len(sl_calls) == 0

    tp_calls = [
        c for c in api_mock.request.call_args_list[1:]
        if c[0][0].data["order"]["type"] == "TAKE_PROFIT"
    ]
    assert len(tp_calls) == expected_tp_calls


@pytest.mark.parametrize(
    "signal, units, current_price, max_sl_pips, max_sl_pct, oanda_account_id, oanda_token, expected_status, expected_message_substr",
    [
        (
            # id: error_missing_credentials_both_none
            {"pair": "EUR_USD", "action": "BUY", "stop_loss": 1.09, "take_profit": 1.11},
            1000,
            1.10,
            None,
            0.03,
            None,
            None,
            "ERROR",
            "Missing OANDA credentials",
        ),
        (
            # id: error_missing_credentials_account_only
            {"pair": "EUR_USD", "action": "BUY", "stop_loss": 1.09, "take_profit": 1.11},
            1000,
            1.10,
            None,
            0.03,
            "",
            "token",
            "ERROR",
            "Missing OANDA credentials",
        ),
        (
            # id: error_invalid_action
            {"pair": "EUR_USD", "action": "HOLD", "stop_loss": 1.09, "take_profit": 1.11},
            1000,
            1.10,
            None,
            0.03,
            "acct",
            "token",
            "ERROR",
            "Invalid action",
        ),
        (
            # id: error_missing_sl
            {"pair": "EUR_USD", "action": "BUY", "stop_loss": None, "take_profit": 1.11},
            1000,
            1.10,
            None,
            0.03,
            "acct",
            "token",
            "ERROR",
            "SL missing",
        ),
        (
            # id: error_missing_entry_price
            {"pair": "EUR_USD", "action": "BUY", "stop_loss": 1.09, "take_profit": 1.11},
            1000,
            None,
            None,
            0.03,
            "acct",
            "token",
            "ERROR",
            "Entry price missing",
        ),
    ],
    ids=[
        "error_missing_credentials_both_none",
        "error_missing_credentials_account_only",
        "error_invalid_action",
        "error_missing_sl",
        "error_missing_entry_price",
    ],
)
def test_open_oanda_order_basic_error_cases(
    signal,
    units,
    current_price,
    max_sl_pips,
    max_sl_pct,
    oanda_account_id,
    oanda_token,
    expected_status,
    expected_message_substr,
):
    # Act
    result = open_oanda_order(
        signal=signal,
        units=units,
        current_price=current_price,
        api=Mock(),
        oanda_account_id=oanda_account_id,
        oanda_token=oanda_token,
        trailing_tp=False,
        dynamic_tp=False,
        max_sl_pips=max_sl_pips,
        max_sl_pct=max_sl_pct,
        telegram_send=None,
        cfg=None,
    )

    # Assert
    assert result["status"] == expected_status
    assert expected_message_substr in result["message"]


@pytest.mark.parametrize(
    "signal, current_price, expect_guard_message_substr",
    [
        (
            # id: guard_sl_too_far_pips_non_jpy
            {"pair": "EUR_USD", "action": "BUY", "stop_loss": 1.0500, "take_profit": 1.10},
            1.1000,
            "SL GUARD BLOCKED",
        ),
        (
            # id: guard_sl_too_far_pct_custom_pct
            {"pair": "EUR_USD", "action": "BUY", "stop_loss": 1.0500, "take_profit": 1.10},
            1.1000,
            "SL GUARD BLOCKED",
        ),
        (
            # id: guard_sl_too_far_pips_jpy_default_500
            {"pair": "USD_JPY", "action": "SELL", "stop_loss": 160.0, "take_profit": 150.0},
            150.0,
            "SL GUARD BLOCKED",
        ),
    ],
    ids=[
        "guard_sl_too_far_pips_non_jpy",
        "guard_sl_too_far_pct_custom_pct",
        "guard_sl_too_far_pips_jpy_default_500",
    ],
)
def test_open_oanda_order_sl_guard_distance(
    signal,
    current_price,
    expect_guard_message_substr,
    patch_dependencies,
):
    # Arrange
    patch_dependencies["pip_size"].return_value = 0.0001 if "JPY" not in signal["pair"] else 0.01

    api_mock = Mock()
    telegram_mock = Mock()

    # Act
    result = open_oanda_order(
        signal=signal,
        units=1000,
        current_price=current_price,
        api=api_mock,
        oanda_account_id="acct",
        oanda_token="token",
        trailing_tp=False,
        dynamic_tp=False,
        max_sl_pips=None,
        max_sl_pct=0.03,
        telegram_send=telegram_mock,
        cfg=None,
    )

    # Assert
    assert result["status"] == "ERROR"
    assert expect_guard_message_substr in result["message"]
    patch_dependencies["logger"].error.assert_called()
    telegram_mock.assert_called()


@pytest.mark.parametrize(
    "signal, current_price, expected_message",
    [
        (
            # id: guard_buy_sl_above_entry
            {"pair": "EUR_USD", "action": "BUY", "stop_loss": 1.11, "take_profit": 1.12},
            1.10,
            "SL GUARD BLOCKED EUR_USD: SL 1.11 >= entry 1.1 for LONG",
        ),
        (
            # id: guard_sell_sl_below_entry
            {"pair": "EUR_USD", "action": "SELL", "stop_loss": 1.09, "take_profit": 1.08},
            1.10,
            "SL GUARD BLOCKED EUR_USD: SL 1.09 <= entry 1.1 for SHORT",
        ),
    ],
    ids=[
        "guard_buy_sl_above_entry",
        "guard_sell_sl_below_entry",
    ],
)
def test_open_oanda_order_sl_direction_guard(
    signal,
    current_price,
    expected_message,
    patch_dependencies,
):
    # Arrange
    api_mock = Mock()

    # Act
    result = open_oanda_order(
        signal=signal,
        units=1000,
        current_price=current_price,
        api=api_mock,
        oanda_account_id="acct",
        oanda_token="token",
        trailing_tp=False,
        dynamic_tp=False,
        max_sl_pips=1000,
        max_sl_pct=1.0,
        telegram_send=None,
        cfg=None,
    )

    # Assert
    assert result["status"] == "ERROR"
    assert result["message"] == expected_message
    patch_dependencies["logger"].error.assert_called()


def test_open_oanda_order_no_trade_id_no_sl_tp(patch_dependencies):
    # Arrange
    api_resp = {"someOtherKey": {}}
    api_mock = Mock()
    api_mock.request = Mock(return_value=api_resp)

    signal = {"pair": "EUR_USD", "action": "BUY", "stop_loss": 1.09, "take_profit": 1.11}

    # Act
    result = open_oanda_order(
        signal=signal,
        units=1000,
        current_price=1.10,
        api=api_mock,
        oanda_account_id="acct",
        oanda_token="token",
        trailing_tp=False,
        dynamic_tp=False,
        max_sl_pips=1000,
        max_sl_pct=1.0,
        telegram_send=None,
        cfg=None,
    )

    # Assert
    assert result["status"] == "OK"
    assert result["response"] == api_resp

    # MARKET order only, no SL/TP
    assert api_mock.request.call_count == 1
    patch_dependencies["logger"].warning.assert_called()
    patch_dependencies["logger"].error.assert_called_with("❌ Cannot create SL/TP — TradeID is EMPTY!")


def test_open_oanda_order_sl_creation_failure_logged(patch_dependencies):
    # Arrange
    api_mock = Mock()

    # MARKET call succeeds, SL call raises, TP call succeeds
    def request_side_effect(arg):
        data = arg.data
        if data["order"]["type"] == "MARKET":
            return {"orderFillTransaction": {"id": "999", "price": 1.10}}
        elif data["order"]["type"] == "STOP_LOSS":
            raise RuntimeError("SL failed")
        else:
            return {"tpOrder": "ok"}

    api_mock.request.side_effect = request_side_effect

    signal = {"pair": "EUR_USD", "action": "BUY", "stop_loss": 1.09, "take_profit": 1.11}

    # Act
    result = open_oanda_order(
        signal=signal,
        units=1000,
        current_price=1.10,
        api=api_mock,
        oanda_account_id="acct",
        oanda_token="token",
        trailing_tp=False,
        dynamic_tp=False,
        max_sl_pips=1000,
        max_sl_pct=1.0,
        telegram_send=None,
        cfg=None,
    )

    # Assert
    assert result["status"] == "OK"

    # SL failure should be logged as warning
    warning_calls = [c for c in patch_dependencies["logger"].warning.call_args_list
                     if "SL order failed" in c[0][0]]
    assert warning_calls, "Expected SL order failure warning to be logged"


def test_open_oanda_order_tp_creation_failure_logged(patch_dependencies):
    # Arrange
    api_mock = Mock()

    def request_side_effect(arg):
        data = arg.data
        if data["order"]["type"] == "MARKET":
            return {"orderFillTransaction": {"id": "1000", "price": 1.10}}
        elif data["order"]["type"] == "TAKE_PROFIT":
            raise RuntimeError("TP failed")
        else:
            return {"slOrder": "ok"}

    api_mock.request.side_effect = request_side_effect

    signal = {"pair": "EUR_USD", "action": "BUY", "stop_loss": 1.09, "take_profit": 1.11}

    # Act
    result = open_oanda_order(
        signal=signal,
        units=1000,
        current_price=1.10,
        api=api_mock,
        oanda_account_id="acct",
        oanda_token="token",
        trailing_tp=False,
        dynamic_tp=False,
        max_sl_pips=1000,
        max_sl_pct=1.0,
        telegram_send=None,
        cfg=None,
    )

    # Assert
    assert result["status"] == "OK"

    warning_calls = [c for c in patch_dependencies["logger"].warning.call_args_list
                     if "TP order failed" in c[0][0]]
    assert warning_calls, "Expected TP order failure warning to be logged"


def test_open_oanda_order_api_failure_at_market(patch_dependencies):
    # Arrange
    api_mock = Mock()
    api_mock.request.side_effect = RuntimeError("OANDA down")

    signal = {"pair": "EUR_USD", "action": "BUY", "stop_loss": 1.09, "take_profit": 1.11}

    # Act
    result = open_oanda_order(
        signal=signal,
        units=1000,
        current_price=1.10,
        api=api_mock,
        oanda_account_id="acct",
        oanda_token="token",
        trailing_tp=False,
        dynamic_tp=False,
        max_sl_pips=1000,
        max_sl_pct=1.0,
        telegram_send=None,
        cfg=None,
    )

    # Assert
    assert result["status"] == "ERROR"
    assert "OANDA down" in result["message"]
    patch_dependencies["logger"].error.assert_called()

# 在文件末尾添加你的具体测试用例

def test_open_oanda_order_buy_success(patch_dependencies):
    # 这里 patch_dependencies 已经被 autouse 运行过了，环境已 Mock 好

    # 1. 准备测试数据
    symbol = "EUR_USD"
    units = 10000
    side = "buy"

    # 2. 调用目标函数
    # 假设该函数在 fx_trade_bot_utils.py 中被定义为接受这几个参数
    # 你需要根据 fx_trade_bot_utils.py 的实际代码来调用它
    order_id = open_oanda_order(symbol, units, side)

    # 3. 进行断言 (Assert)
    # 检查返回的订单 ID 是否符合预期 (这里假设它应该返回一个字符串)
    assert isinstance(order_id, str)
    assert len(order_id) > 0
    
    # 你还可以验证 Mock 的行为，例如验证 logger 是否被调用了
    # patch_dependencies.logger_mock.info.assert_called()