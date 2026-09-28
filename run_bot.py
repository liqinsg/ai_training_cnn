import logging
from jpy_trend_bot import JPYTrendBot, OANDAConfig

# ─── 1. 全局统一Logger配置 ───
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("trading.log")],
)
shared_logger = logging.getLogger("trading_system")

# ─── 2. 组装Profile参数包（可多份并行） ───
CONSERVATIVE = {
    "PROFILE_LABEL": "conservative_jpy",
    "TRADE_PAIRS": ["EUR_JPY", "GBP_JPY", "USD_JPY", "AUD_JPY"],
    "JPY_PIP": 0.01,
    "MIN_MARKET_STRENGTH": 0.35,
    "MIN_DOMINANCE_RATIO": 0.6,
    "REQUIRE_ALIGNED": 3,
    "MIN_VALID_PAIRS_TO_TRADE": 1,
    "SKIP_SIDEWAYS_PAIRS": True,
    "SL_BUFFER_PIPS": 15,
    "SPREAD_PIPS": 8,
    "MIN_RR": 1.5,
    "FRONT_RUN_PIPS": 5,
    "MACRO_PROTECTION_PIPS": 30,
    "ENABLE_ATR_SLTP": True,
    "JPY_ATR_PERIOD": 14,
    "JPY_ATR_HISTORY_LOOKBACK": 60,
    "JPY_ATR_SL_MULTIPLIER_NORMAL": 1.5,
    "JPY_ATR_SL_MULTIPLIER_HIGH_VOL": 2.0,
    "JPY_ATR_SL_MULTIPLIER_LOW_VOL": 1.2,
    "JPY_ATR_RR_MULTIPLE": 2.0,
    "ENABLE_MACRO_PROTECTION": True,
    "ENABLE_BREAKOUT_CONFIRMATION": True,
    "BREAKOUT_CONFIRMATION_CLOSES": 3,
    "ENABLE_EMA_TREND": True,
    "ENABLE_NEWS_FILTER": True,
    "ENABLE_RANGE_DETECTOR": True,
}

# ─── 3. OANDA执行配置（独立于策略参数） ───
OANDA_LIVE = OANDAConfig(
    api_key="YOUR_LIVE_KEY",
    account_id="YOUR_LIVE_ACCT",
    environment="live",
    max_slippage_pips=1.5,
)

OANDA_DEMO = OANDAConfig(
    api_key="YOUR_DEMO_KEY",
    account_id="YOUR_DEMO_ACCT",
    environment="practice",
)

# ─── 4. 实例化Bot ───
bot = JPYTrendBot(
    strategy_config=CONSERVATIVE,
    oanda_config=OANDA_DEMO,
    logger=shared_logger,
)

# ─── 5. 运行周期 ───
if __name__ == "__main__":
    result = bot.run_cycle()
    print(f"\nResult: {result['status']} — {result.get('reason', 'OK')}")
