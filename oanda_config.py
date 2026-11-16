# oanda_config.py
# OANDA API & account settings — sourced from config_oanda (the single gateway).
from config_oanda import OANDA_ENV, OANDA_API_TOKEN, OANDA_ACCOUNT_ID


class OandaConfig:
    ENV = OANDA_ENV if "OANDA_ENV" in dir() else "demo"
    API_TOKEN = OANDA_API_TOKEN if "OANDA_API_TOKEN" in dir() else ""
    ACCOUNT_ID = OANDA_ACCOUNT_ID if "OANDA_ACCOUNT_ID" in dir() else ""


oanda_config = OandaConfig()
