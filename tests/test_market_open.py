# tests/test_market_open.py

import unittest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

from utils.oanda_execution import forex_market_closed


def test_market_close_bool():
    result = forex_market_closed()
    assert isinstance(result, bool)