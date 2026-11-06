import ast
from pathlib import Path

import config_bot


BOT = Path(__file__).resolve().parent.parent / "fx_trade_bot_v685.py"
STRENGTHS = {
    "USD": 3.0,
    "GBP": 2.0,
    "JPY": 1.0,
    "CAD": 0.0,
    "NZD": -0.5,
    "AUD": -1.0,
    "CHF": -2.0,
    "EUR": -3.0,
}


class LogCapture:
    def __init__(self):
        self.messages = []

    def info(self, message, *args):
        self.messages.append(message % args if args else message)


def _load_build_top_pairs():
    tree = ast.parse(BOT.read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "build_top_pairs"
    )
    logger = LogCapture()
    namespace = {
        "TOP_N_CURRENCIES": 3,
        "TOP_PAIRS_MIN_GAP": 0.5,
        "log": logger,
    }
    module = ast.Module(body=[function], type_ignores=[])
    exec(compile(module, str(BOT), "exec"), namespace)
    return namespace["build_top_pairs"], logger


def test_top_three_matrix_works_for_profiles_one_and_two():
    build_top_pairs, logger = _load_build_top_pairs()
    ranked = sorted(STRENGTHS.items(), key=lambda item: item[1], reverse=True)
    assert [currency for currency, _ in ranked[:3]] == ["USD", "GBP", "JPY"]
    assert {currency for currency, _ in ranked[-3:]} == {"EUR", "CHF", "AUD"}

    for profile_id in (1, 2):
        profile = config_bot.get_profile(profile_id)
        whitelist = profile["WHITELIST"]
        selected, candidates = build_top_pairs(
            STRENGTHS,
            profile["ALL_PAIRS"],
            config_bot.YAHOO_TO_OANDA,
            top_n=3,
            min_gap=0.5,
            whitelist=whitelist,
        )

        assert selected, f"Profile{profile_id} returned no Top-3 pairs"
        assert "AUD_USD" in selected
        assert "USD_CHF" in selected
        assert "EUR_JPY" in selected
        assert all(pair in whitelist for pair in selected)
        assert all(candidate["pair"].count("_") == 1 for candidate in candidates)

    assert any("generated candidates" in message for message in logger.messages)
    assert any("normalized candidates" in message for message in logger.messages)
    assert any("whitelist matches" in message for message in logger.messages)
    assert any("mapping hits" in message for message in logger.messages)
    assert any("rejected candidates" in message for message in logger.messages)

    restricted, _ = build_top_pairs(
        STRENGTHS,
        config_bot.get_profile(2)["ALL_PAIRS"],
        config_bot.YAHOO_TO_OANDA,
        top_n=3,
        min_gap=0.5,
        whitelist=["AUD_USD"],
    )
    assert restricted == ["AUD_USD"]
    assert any("not in whitelist" in message for message in logger.messages)


def test_every_profile_whitelist_pair_has_oanda_mapping():
    for profile_id, pairs in config_bot.WHITELIST.items():
        missing = [
            pair
            for pair in pairs
            if not config_bot.YAHOO_TO_OANDA.get(pair)
        ]
        assert not missing, (
            f"Profile{profile_id} whitelist has pairs without OANDA mappings: "
            f"{missing}"
        )
