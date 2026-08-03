import pandas as pd

from fx_trade_bot import normalize_ohlc_data


def test_normalize_ohlc_data_converts_oanda_candles():
    candles = [
        {
            "complete": True,
            "time": "2026-08-03T07:00:00.000000000Z",
            "volume": 100,
            "mid": {"o": "1.1000", "h": "1.1100", "l": "1.0900", "c": "1.1050"},
        }
    ]

    df = normalize_ohlc_data(candles)

    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert df.iloc[0]["Close"] == 1.1050
    assert df.iloc[0]["Volume"] == 100.0
