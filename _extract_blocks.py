#!/usr/bin/env python3
"""Extract blocks from fx_trade_bot_utils.py into fx/ subpackage modules."""
import re
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

def find_block_end(lines, start):
    i = start + 1
    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip("\n")
        if re.match(r"^(def |class |[^\s#])", stripped):
            break
        i += 1
    return i

def extract_blocks(src_text, names):
    lines = src_text.splitlines(keepends=True)
    result = []
    for i, line in enumerate(lines):
        for n in names:
            if re.match(rf"^(def|class)\s+{re.escape(n)}\b", line):
                end = find_block_end(lines, i)
                result.append("".join(lines[i:end]))
                break
    return "\n".join(result).rstrip() + "\n"

def main():
    src = SRC.read_text()
    for target, names in BLOCKS.items():
        out_path = ROOT / target
        body = extract_blocks(src, names)
        header = ORDER_HEADER if "order.py" in target else PORTFOLIO_HEADER
        out_path.write_text(header + "\n" + body + "\n")
        print(f"✅ {target}: {len(names)} blocks → {out_path.stat().st_size} bytes")

if __name__ == "__main__":
    main()
