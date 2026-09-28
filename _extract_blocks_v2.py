#!/usr/bin/env python3
"""Extract blocks using Python AST — handles multi-line signatures correctly."""
import ast
from pathlib import Path

ROOT = Path("/home/qili/projects/ai_training_cnn")
SRC = ROOT / "fx_trade_bot_utils.py"

BLOCKS = {
    "fx/execution/order.py": [
        "attach_tp_to_open_positions",
        "get_open_position",
        "close_position",
        "open_oanda_order_simple",
        "open_oanda_order",
        "update_order_tp",
    ],
    "fx/execution/portfolio.py": [
        "DynamicPositionManager",
        "DynamicPositionManager_v2",
    ],
}

ORDER_HEADER = """import logging
import json
import contextlib
from datetime import datetime, timezone
import pandas as pd
import numpy as np
import oandapyV20.endpoints.orders as orders
from oandapyV20.endpoints.positions import PositionDetails
from oandapyV20.endpoints.trades import Trades, TradeCRCDO, OpenTrades
from oandapyV20 import API
from fx.data.market import price_decimals, pip_size

logger = logging.getLogger(__name__)
"""

PORTFOLIO_HEADER = """import json
import logging
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
from oandapyV20.endpoints.trades import OpenTrades, TradeCRCDO
from utils.strategy_helpers import get_live_prices
from fx.data.market import price_decimals, pip_size
from fx.execution.order import update_order_tp

logger = logging.getLogger(__name__)
"""

def get_block_ranges(source: str, names: list) -> list:
    """Use AST to find (start_line, end_line) for each named def/class."""
    tree = ast.parse(source)
    targets = set(names)
    ranges = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name in targets:
                end = getattr(node, "end_lineno", node.lineno)
                ranges.append((node.lineno - 1, end))
    ranges.sort()
    return ranges

def extract_by_ranges(source: str, ranges: list) -> str:
    lines = source.splitlines(keepends=True)
    chunks = []
    for start, end in ranges:
        chunks.append("".join(lines[start:end]))
    return "\n".join(chunks).rstrip() + "\n"

def main():
    src = SRC.read_text()

    for target, names in BLOCKS.items():
        out_path = ROOT / target
        ranges = get_block_ranges(src, names)
        body = extract_by_ranges(src, ranges)
        header = ORDER_HEADER if "order.py" in target else PORTFOLIO_HEADER
        out_path.write_text(header + "\n" + body + "\n")
        sizes = [f"{Path(t).stem}→{s+1}-{e+1}" for (s, e), t in zip(ranges, names)]
        print(f"✅ {target}: extracted {len(ranges)} blocks [{', '.join(sizes)}]")

if __name__ == "__main__":
    main()
