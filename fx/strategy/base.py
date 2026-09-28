from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

@dataclass
class TradeSignal:
    pair: str               # e.g. "GBPJPY=X"
    oanda: str              # e.g. "GBP_JPY"
    direction: str          # "BUY" / "SELL"
    entry_price: float
    sl_price: float
    tp_price: float
    units_hint: int = 0
    score_final: float = 0.0
    score_s: float = 0.0
    score_r: float = 0.0
    score_a: float = 0.0
    score_x: float = 0.0
    score_m: float = 0.0
    pip_size: float = 0.0
    decimals: int = 5
    tp_pips: float = 0.0
    lot_mult: float = 1.0
    raw: Dict[str, Any] = field(default_factory=dict)

@dataclass
class TradeContext:
    api: Any
    account_id: str
    strength_scores: Dict[str, float]
    pair_data: Dict[str, Any]
    mc_cache: Dict[str, Any]
    weekly_ema_cache: Dict[str, Optional[float]]
    tf_confluence: Dict[str, Any]
    selected_pairs: List[str]
    open_pos_by_oanda: Dict[str, bool]
    cooldown: Dict[str, Any]
    cfg: Any                 # profile config dict
    p_fn: Any                # cfg(P, key, default) callable
    strat_engine: Any
    fetcher: Any
    feat_engine: Any
    open_slots_remaining: int = 1
    log: Any = None

class IStrategy(ABC):
    name: str = "base"

    @abstractmethod
    def evaluate(self, ctx: TradeContext) -> List[TradeSignal]:
        """Score + filter + rank → 候选信号列表。"""
        ...
