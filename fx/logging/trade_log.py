import csv as _csv
import contextlib
import logging
from pathlib import Path
from datetime import datetime, timezone as _tz

logger = logging.getLogger(__name__)

def init_csv(path, header, _logger=None):
    log = _logger or logger
    if not path.exists():
        try:
            with open(path, "w", newline="") as f:
                _csv.DictWriter(f, fieldnames=header).writeheader()
            log.info(f"AUDIT init: {path}")
        except Exception as e:
            log.warning(f"AUDIT init failed {path}: {e}")

def append_to_csv(filepath, row_dict, _logger=None):
    log = _logger or logger
    try:
        fn = list(row_dict.keys())
        if filepath.exists():
            with open(filepath, "r", newline="") as f:
                eh = next(_csv.reader(f), None)
                if eh and list(eh) != fn:
                    log.warning(f"Header mismatch: {filepath} — skipping")
                    return
        with open(filepath, "a", newline="") as f:
            _csv.DictWriter(f, fieldnames=fn).writerow(row_dict)
    except Exception as e:
        log.warning(f"Append failed {filepath}: {e}")

def update_trade_on_close(
    instrument, trade_log_path, api, oanda_account_id,
    exit_reason="UNKNOWN", _logger=None,
):
    import pandas as pd

    log = _logger or logger
    try:
        if not trade_log_path.exists():
            return
        df = pd.read_csv(trade_log_path, dtype={"trade_id": str})
        for c in ("pips", "profit_usd", "exit_reason", "exit_time"):
            if c in df.columns:
                df[c] = df[c].astype(object)
        if df.empty:
            return
        mask = (df["pair"] == instrument) & df["exit_time"].isna()
        match = df.loc[mask].head(1)
        if match.empty:
            return
        tid = str(match.iloc[0]["trade_id"])
        if tid.startswith("DRY_RUN_"):
            df.loc[match.index, "exit_reason"] = exit_reason
            df.loc[match.index, "exit_time"] = datetime.now(_tz.utc).isoformat()
            df.to_csv(trade_log_path, index=False)
            return
        realized_pl = 0.0
        with contextlib.suppress(Exception):
            from oandapyV20.endpoints.trades import TradeDetails
            t = api.request(TradeDetails(accountID=oanda_account_id, tradeID=tid)).get(
                "trade", {}
            )
            realized_pl = float(t.get("realizedPL", 0.0))
        df.loc[match.index, "profit_usd"] = round(realized_pl, 2)
        df.loc[match.index, "exit_reason"] = exit_reason
        df.loc[match.index, "exit_time"] = datetime.now(_tz.utc).isoformat()
        df.to_csv(trade_log_path, index=False)
    except Exception as e:
        log.warning(f"Backfill error {instrument}: {e}")
