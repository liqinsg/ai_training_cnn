"""Regression tests for Yahoo Finance ticker normalization."""

import ast
from pathlib import Path

import pandas as pd
import pytest

from utils.fib_zone_sizing import to_mc_key


SCRIPT = Path(__file__).resolve().parent.parent / "fx_monte_carlo.py"


class FakeYahooFinance:
    def __init__(self, frames):
        self.frames = iter(frames)
        self.calls = []

    def download(self, symbol, **kwargs):
        self.calls.append((symbol, kwargs))
        return next(self.frames)


def _load_fetch_data(fake_yf):
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "fetch_data"
    )
    namespace = {
        "yf": fake_yf,
        "pd": pd,
        "to_mc_key": to_mc_key,
        "YF_PERIOD_FULL": "30d",
        "YF_INTERVAL": "4h",
        "YF_PERIOD_RESAMPLE": "60d",
        "LOOKBACK": 2,
        "TF": "H4",
    }
    exec(
        compile(ast.Module(body=[function], type_ignores=[]), str(SCRIPT), "exec"),
        namespace,
    )
    return namespace["fetch_data"]


@pytest.mark.parametrize(
    ("pair", "yahoo_symbol"),
    [
        ("EUR_USD", "EURUSD=X"),
        ("GBP_JPY", "GBPJPY=X"),
    ],
)
def test_fetch_data_translates_oanda_pair_for_yahoo(pair, yahoo_symbol):
    frame = pd.DataFrame(
        {
            "Open": [1.0, 1.1],
            "High": [1.2, 1.3],
            "Low": [0.9, 1.0],
            "Close": [1.1, 1.2],
        }
    )
    yahoo = FakeYahooFinance([frame])

    result = _load_fetch_data(yahoo)(pair)

    assert not result.empty
    assert yahoo.calls[0][0] == yahoo_symbol
    assert len(yahoo.calls) == 1


def test_fetch_data_uses_yahoo_symbol_for_fallback_download_too():
    yahoo = FakeYahooFinance([pd.DataFrame(), pd.DataFrame()])

    result = _load_fetch_data(yahoo)("EUR_USD")

    assert result.empty
    assert [call[0] for call in yahoo.calls] == ["EURUSD=X", "EURUSD=X"]
