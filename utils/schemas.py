from pydantic import BaseModel, Field
from typing import Literal


class TradeSignal(BaseModel):
    pair_to_trade: Literal[
        # JPY crosses
        "USD_JPY", "EUR_JPY", "GBP_JPY", "AUD_JPY", "NZD_JPY", "CHF_JPY",
        # EUR crosses
        "EUR_USD", "EUR_GBP", "EUR_AUD", "EUR_CHF",
        # GBP crosses
        "GBP_USD", "GBP_AUD", "GBP_CHF",
        # Commodity/others
        "AUD_USD", "NZD_USD", "USD_CHF",
        "AUD_CHF", "AUD_NZD",
        "NZD_CHF"
        "HOLD"
    ] = Field(description="The specific currency pair selected for execution.")
    action: Literal["BUY", "SELL", "HOLD"]
    confidence_score: float = Field(description="Confidence score from 0.0 to 1.0")
    stop_loss: float = Field(description="Stop Loss price level for the chosen pair.")
    take_profit: float = Field(description="Take Profit price level for the chosen pair.")
    reasoning: str = Field(description="Brief macro/technical justification for this signal.")