from .baseline import StrategyBaseline

STRATEGIES = {
    "baseline": StrategyBaseline,
    "balanced": StrategyBaseline,  # TODO: StrategyBalanced 独立实现
}

def get_strategy(name: str, params: dict):
    cls = STRATEGIES.get(name) or StrategyBaseline
    return cls(params)
