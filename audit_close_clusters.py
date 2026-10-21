#!/usr/bin/env python3
"""
Read-only OANDA closed-trade / close-transaction audit.

Purpose
-------
1. Fetch recently closed trades from OANDA.
2. Fetch each distinct closing transaction once.
3. Group trade rows by transaction ID so one transaction affecting multiple
   trades is not mistaken for multiple independent close actions.
4. Identify nearby close events (time clusters) across instruments.
5. Export CSVs for trade rows, unique transactions, and close clusters.

Examples
--------
    python audit_close_clusters.py
    python audit_close_clusters.py 336
    python audit_close_clusters.py 336 --profile 2
    python audit_close_clusters.py 336 --cluster-seconds 10 --out-dir audit_close_clusters

READ ONLY: this script only calls OANDA GET endpoints. It does not place,
modify, or close orders/trades.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from oandapyV20.endpoints.trades import TradesList
    from oandapyV20.endpoints.transactions import TransactionDetails
except ImportError as exc:
    raise SystemExit(
        "Missing dependency. Install with: pip install oandapyV20"
    ) from exc


UTC = timezone.utc


def parse_oanda_time(value: Any) -> Optional[datetime]:
    """Parse an OANDA RFC3339 timestamp, including nanosecond fractions."""
    if not value:
        return None
    s = str(value).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    # Python datetime supports microseconds, while OANDA can return 9 digits.
    if "." in s:
        head, rest = s.split(".", 1)
        tz_pos = max(rest.find("+"), rest.find("-"))
        if tz_pos >= 0:
            fraction, tz = rest[:tz_pos], rest[tz_pos:]
        else:
            fraction, tz = rest, ""
        s = head + "." + (fraction[:6].ljust(6, "0")) + tz
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except (TypeError, ValueError):
        return None


def iso(dt: Optional[datetime]) -> str:
    return dt.astimezone(UTC).isoformat(timespec="seconds") if dt else ""


def safe_float(value: Any) -> Optional[float]:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def compact_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        return str(value)


def classify_transaction(tx: Dict[str, Any]) -> str:
    """
    Classification is descriptive, not a claim about who initiated the action.
    In particular, POSITION_CLOSEOUT must be reviewed with account/bot logs.
    """
    tx_type = str(tx.get("type") or "").upper()
    reason = str(tx.get("reason") or "").upper()
    # Closing fills are often returned as type=ORDER_FILL, while the trigger
    # is recorded in reason (e.g. TAKE_PROFIT_ORDER / STOP_LOSS_ORDER).
    # Check reason as well as type; otherwise TP/SL would be mislabelled.
    combined = f"{tx_type} {reason}"

    if "TAKE_PROFIT_ORDER" in combined:
        return "TP"
    if "STOP_LOSS_ORDER" in combined:
        return "SL"
    if "POSITION_CLOSEOUT" in combined:
        return "POSITION_CLOSEOUT"
    if "MARKET_ORDER" in combined:
        return "MARKET_ORDER"
    if "MARGIN" in combined:
        return "MARGIN_RELATED"
    if tx_type:
        return "OTHER_TRANSACTION"
    return "UNKNOWN"


def transaction_trade_ids(tx: Dict[str, Any]) -> List[str]:
    """Collect trade IDs affected by a transaction, tolerating API shape variants."""
    found = set()

    for key in ("tradeID", "tradeId"):
        value = tx.get(key)
        if value not in (None, ""):
            found.add(str(value))

    for key in ("tradesClosed", "tradesReduced", "tradesOpened"):
        values = tx.get(key) or []
        if isinstance(values, list):
            for item in values:
                if isinstance(item, dict):
                    value = item.get("tradeID") or item.get("tradeId")
                    if value not in (None, ""):
                        found.add(str(value))

    return sorted(found, key=lambda x: (not x.isdigit(), int(x) if x.isdigit() else x))


def get_profile_api_and_account(profile: int):
    """
    Uses the project's existing config_oanda conventions.
    The API client is taken from config_oanda.api; account defaults to the
    matching OANDA_ACCOUNT_ID_DEMO_<profile> constant.
    """
    try:
        import config_oanda  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "Could not import config_oanda. Run this from the project directory "
            "and verify the project's environment/config."
        ) from exc

    api_client = getattr(config_oanda, "api", None)
    account_name = f"OANDA_ACCOUNT_ID_DEMO_{profile}"
    account_id = getattr(config_oanda, account_name, None)

    if api_client is None:
        raise RuntimeError("config_oanda.api was not found.")
    if not account_id:
        raise RuntimeError(
            f"config_oanda.{account_name} was not found. "
            "Use --account-id to supply an account ID explicitly."
        )
    return api_client, str(account_id)


def fetch_closed_trades(
    api_client: Any,
    account_id: str,
    hours: int,
    max_count: int,
) -> Tuple[List[Dict[str, Any]], datetime, datetime]:
    now = datetime.now(UTC)
    cutoff = now - timedelta(hours=hours)

    params = {"state": "CLOSED", "count": min(max_count, 500)}
    response = TradesList(accountID=account_id, params=params)
    api_client.request(response)

    payload = response.response or {}
    trades = payload.get("trades") or []
    selected = []
    for trade in trades:
        close_time = parse_oanda_time(trade.get("closeTime"))
        if close_time and cutoff <= close_time <= now:
            selected.append(trade)

    selected.sort(key=lambda t: parse_oanda_time(t.get("closeTime")) or datetime.min.replace(tzinfo=UTC))
    return selected, cutoff, now


def fetch_transaction(api_client: Any, account_id: str, tx_id: str) -> Dict[str, Any]:
    request = TransactionDetails(accountID=account_id, transactionID=tx_id)
    api_client.request(request)
    payload = request.response or {}
    # OANDA commonly returns {"transaction": {...}}.
    tx = payload.get("transaction")
    if isinstance(tx, dict):
        return tx
    # Keep raw response for audit if the endpoint response shape differs.
    return payload if isinstance(payload, dict) else {"raw_response": payload}


def trade_closing_ids(trade: Dict[str, Any]) -> List[str]:
    values = trade.get("closingTransactionIDs")
    if values is None:
        # Defensive compatibility with any output using a singular field.
        values = trade.get("closingTransactionID")
    if isinstance(values, list):
        return [str(v) for v in values if v not in (None, "")]
    if values not in (None, ""):
        return [str(values)]
    return []


def build_trade_rows(
    trades: List[Dict[str, Any]],
    transactions: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    for trade in trades:
        trade_id = str(trade.get("id") or trade.get("tradeID") or "")
        close_time = parse_oanda_time(trade.get("closeTime"))
        closing_ids = trade_closing_ids(trade)

        # A closed trade should normally have closingTransactionIDs. Keep a
        # row even when missing, so data gaps are visible rather than hidden.
        if not closing_ids:
            rows.append({
                "trade_id": trade_id,
                "instrument": trade.get("instrument", ""),
                "initial_units": trade.get("initialUnits", ""),
                "current_units": trade.get("currentUnits", ""),
                "open_time_utc": iso(parse_oanda_time(trade.get("openTime"))),
                "close_time_utc": iso(close_time),
                "realized_pl": trade.get("realizedPL", ""),
                "financing": trade.get("financing", ""),
                "closing_transaction_id": "",
                "transaction_type": "",
                "transaction_reason": "",
                "classification": "MISSING_CLOSING_TX_ID",
                "transaction_time_utc": "",
                "transaction_trade_ids": "",
                "client_extensions": compact_json(trade.get("clientExtensions") or {}),
                "trade_raw": compact_json(trade),
            })
            continue

        for tx_id in closing_ids:
            tx = transactions.get(tx_id, {})
            rows.append({
                "trade_id": trade_id,
                "instrument": trade.get("instrument", ""),
                "initial_units": trade.get("initialUnits", ""),
                "current_units": trade.get("currentUnits", ""),
                "open_time_utc": iso(parse_oanda_time(trade.get("openTime"))),
                "close_time_utc": iso(close_time),
                "realized_pl": trade.get("realizedPL", ""),
                "financing": trade.get("financing", ""),
                "closing_transaction_id": tx_id,
                "transaction_type": tx.get("type", ""),
                "transaction_reason": tx.get("reason", ""),
                "classification": classify_transaction(tx) if tx else "TX_LOOKUP_FAILED",
                "transaction_time_utc": iso(parse_oanda_time(tx.get("time"))),
                "transaction_trade_ids": ";".join(transaction_trade_ids(tx)),
                "client_extensions": compact_json(
                    tx.get("clientExtensions") or trade.get("clientExtensions") or {}
                ),
                "trade_raw": compact_json(trade),
            })

    return rows


def build_transaction_rows(
    transactions: Dict[str, Dict[str, Any]],
    lookup_errors: Dict[str, str],
) -> List[Dict[str, Any]]:
    rows = []
    for tx_id, tx in transactions.items():
        dt = parse_oanda_time(tx.get("time"))
        rows.append({
            "transaction_id": tx_id,
            "time_utc": iso(dt),
            "type": tx.get("type", ""),
            "reason": tx.get("reason", ""),
            "classification": classify_transaction(tx),
            "instrument": tx.get("instrument", ""),
            "units": tx.get("units", ""),
            "pl": tx.get("pl", ""),
            "account_balance": tx.get("accountBalance", ""),
            "trade_ids_affected": ";".join(transaction_trade_ids(tx)),
            "client_extensions": compact_json(tx.get("clientExtensions") or {}),
            "lookup_error": lookup_errors.get(tx_id, ""),
            "transaction_raw": compact_json(tx),
        })
    for tx_id, error in lookup_errors.items():
        if tx_id not in transactions:
            rows.append({
                "transaction_id": tx_id,
                "time_utc": "",
                "type": "",
                "reason": "",
                "classification": "TX_LOOKUP_FAILED",
                "instrument": "",
                "units": "",
                "pl": "",
                "account_balance": "",
                "trade_ids_affected": "",
                "client_extensions": "",
                "lookup_error": error,
                "transaction_raw": "",
            })
    rows.sort(key=lambda r: (r["time_utc"], r["transaction_id"]))
    return rows


def build_close_clusters(
    transaction_rows: List[Dict[str, Any]],
    trade_rows: List[Dict[str, Any]],
    cluster_seconds: int,
) -> List[Dict[str, Any]]:
    """
    Cluster distinct transactions by timestamp proximity. Each unique
    transaction is counted once even if it closes/reduces several trades.
    """
    by_tx_trades: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in trade_rows:
        tx_id = str(row.get("closing_transaction_id") or "")
        if tx_id:
            by_tx_trades[tx_id].append(row)

    events = []
    for tx in transaction_rows:
        tx_id = str(tx.get("transaction_id") or "")
        dt = parse_oanda_time(tx.get("time_utc"))
        if not tx_id or not dt:
            continue
        # Ignore failed lookup rows with no timestamp.
        events.append({
            "dt": dt,
            "tx_id": tx_id,
            "type": tx.get("type", ""),
            "reason": tx.get("reason", ""),
            "classification": tx.get("classification", ""),
            "trade_ids": set(filter(None, str(tx.get("trade_ids_affected") or "").split(";"))),
            "instruments": set(),
            "pl_values": [],
        })

    for event in events:
        linked_rows = by_tx_trades.get(event["tx_id"], [])
        for row in linked_rows:
            if row.get("instrument"):
                event["instruments"].add(str(row["instrument"]))
            pl = safe_float(row.get("realized_pl"))
            if pl is not None:
                event["pl_values"].append(pl)
            if row.get("trade_id"):
                event["trade_ids"].add(str(row["trade_id"]))

    events.sort(key=lambda e: (e["dt"], e["tx_id"]))

    # Time-proximity grouping is deliberately transitive: if each adjacent
    # transaction is within the threshold, they belong to the same cluster.
    groups: List[List[Dict[str, Any]]] = []
    current: List[Dict[str, Any]] = []
    previous: Optional[datetime] = None
    for event in events:
        if previous is None or (event["dt"] - previous).total_seconds() <= cluster_seconds:
            current.append(event)
        else:
            groups.append(current)
            current = [event]
        previous = event["dt"]
    if current:
        groups.append(current)

    rows = []
    cluster_no = 0
    for group in groups:
        if not group:
            continue
        cluster_no += 1
        all_trade_ids = set()
        all_instruments = set()
        classifications = set()
        types = set()
        tx_ids = []
        for event in group:
            all_trade_ids.update(event["trade_ids"])
            all_instruments.update(event["instruments"])
            classifications.add(event["classification"] or "UNKNOWN")
            if event["type"]:
                types.add(str(event["type"]))
            tx_ids.append(event["tx_id"])

        rows.append({
            "cluster_id": f"C{cluster_no:04d}",
            "start_time_utc": iso(group[0]["dt"]),
            "end_time_utc": iso(group[-1]["dt"]),
            "span_seconds": round((group[-1]["dt"] - group[0]["dt"]).total_seconds(), 3),
            "unique_transaction_count": len(set(tx_ids)),
            "linked_trade_count": len(all_trade_ids),
            "transaction_ids": ";".join(sorted(set(tx_ids), key=lambda x: (not x.isdigit(), int(x) if x.isdigit() else x))),
            "trade_ids": ";".join(sorted(all_trade_ids, key=lambda x: (not x.isdigit(), int(x) if x.isdigit() else x))),
            "instruments": ";".join(sorted(all_instruments)),
            "classifications": ";".join(sorted(classifications)),
            "transaction_types": ";".join(sorted(types)),
            "note": (
                "Review as a possible coordinated/batch close; time proximity alone "
                "does not prove a common cause or identify the actor."
                if len(set(tx_ids)) > 1 or len(all_trade_ids) > 1
                else "Single transaction event."
            ),
        })
    return rows


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def summarize(trade_rows: List[Dict[str, Any]], tx_rows: List[Dict[str, Any]], cluster_rows: List[Dict[str, Any]]) -> None:
    counts: Dict[str, int] = defaultdict(int)
    for row in tx_rows:
        counts[str(row.get("classification") or "UNKNOWN")] += 1

    print("\n=== READ-ONLY CLOSE CLUSTER AUDIT ===")
    print(f"Trade/closing-tx rows : {len(trade_rows)}")
    print(f"Unique tx rows       : {len(tx_rows)}")
    print(f"Time clusters        : {len(cluster_rows)}")
    print("Unique transaction classification counts:")
    for key in sorted(counts):
        print(f"  {key:<24} {counts[key]}")

    print("\nLargest clusters (by linked trades, then unique transactions):")
    largest = sorted(
        cluster_rows,
        key=lambda r: (int(r.get("linked_trade_count") or 0), int(r.get("unique_transaction_count") or 0)),
        reverse=True,
    )[:15]
    if not largest:
        print("  (none)")
    for row in largest:
        print(
            f"  {row['cluster_id']} {row['start_time_utc']} -> {row['end_time_utc']} "
            f"| tx={row['unique_transaction_count']} "
            f"| trades={row['linked_trade_count']} "
            f"| pairs={row['instruments'] or '-'} "
            f"| classes={row['classifications'] or '-'}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only OANDA close-transaction cluster audit")
    parser.add_argument(
        "hours", nargs="?", type=int, default=336,
        help="Rolling lookback window in hours (default: 336 = 14 days)",
    )
    parser.add_argument("--profile", type=int, default=2, help="Demo profile number used by config_oanda (default: 2)")
    parser.add_argument("--account-id", default=None, help="Explicit OANDA account ID override")
    parser.add_argument("--max-count", type=int, default=500, help="Maximum closed trades to request (OANDA limit up to 500)")
    parser.add_argument("--cluster-seconds", type=int, default=10, help="Maximum gap between adjacent transactions in a time cluster")
    parser.add_argument("--out-dir", default="audit_close_clusters", help="Output directory")
    args = parser.parse_args()

    if args.hours <= 0:
        parser.error("hours must be > 0")
    if args.max_count <= 0:
        parser.error("--max-count must be > 0")
    if args.cluster_seconds < 0:
        parser.error("--cluster-seconds must be >= 0")

    try:
        api_client, configured_account = get_profile_api_and_account(args.profile)
        account_id = str(args.account_id or configured_account)
        trades, cutoff, now = fetch_closed_trades(
            api_client, account_id, args.hours, args.max_count
        )
    except Exception as exc:
        print(f"FATAL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    print(f"Account: {account_id}")
    print(f"Window UTC: {iso(cutoff)} -> {iso(now)}")
    print("Mode: READ ONLY (GET endpoints only)")
    print(f"Closed trades in window: {len(trades)}")

    closing_ids = sorted({txid for trade in trades for txid in trade_closing_ids(trade)})
    transactions: Dict[str, Dict[str, Any]] = {}
    lookup_errors: Dict[str, str] = {}

    for index, tx_id in enumerate(closing_ids, start=1):
        try:
            tx = fetch_transaction(api_client, account_id, tx_id)
            # Avoid silently treating an unexpected response as a valid tx.
            if not tx or not tx.get("type"):
                lookup_errors[tx_id] = "Transaction response missing expected 'type' field"
            else:
                transactions[tx_id] = tx
        except Exception as exc:
            lookup_errors[tx_id] = f"{type(exc).__name__}: {exc}"
        if index % 25 == 0 or index == len(closing_ids):
            print(f"Fetched transaction details: {index}/{len(closing_ids)}")

    trade_rows = build_trade_rows(trades, transactions)
    tx_rows = build_transaction_rows(transactions, lookup_errors)
    cluster_rows = build_close_clusters(tx_rows, trade_rows, args.cluster_seconds)

    out_dir = Path(args.out_dir)
    trade_csv = out_dir / "trade_close_rows.csv"
    tx_csv = out_dir / "unique_close_transactions.csv"
    cluster_csv = out_dir / "close_clusters.csv"
    errors_csv = out_dir / "transaction_lookup_errors.csv"
    report_txt = out_dir / "summary.txt"

    write_csv(trade_csv, trade_rows)
    write_csv(tx_csv, tx_rows)
    write_csv(cluster_csv, cluster_rows)
    write_csv(errors_csv, [
        {"transaction_id": tx_id, "error": error}
        for tx_id, error in sorted(lookup_errors.items())
    ])

    summary_lines = [
        "READ-ONLY OANDA CLOSE CLUSTER AUDIT",
        f"Account: {account_id}",
        f"Window UTC: {iso(cutoff)} -> {iso(now)}",
        f"Closed trades in window: {len(trades)}",
        f"Trade/closing-tx rows: {len(trade_rows)}",
        f"Unique closing transaction IDs requested: {len(closing_ids)}",
        f"Unique transaction details retrieved: {len(transactions)}",
        f"Transaction lookup errors: {len(lookup_errors)}",
        f"Time clusters: {len(cluster_rows)}",
        "",
        "IMPORTANT: rows are not independent close decisions. A single OANDA transaction",
        "may affect multiple trades. Time proximity does not prove common cause or actor.",
        "POSITION_CLOSEOUT classification is descriptive; verify full transaction/account",
        "details and bot logs before assigning a cause.",
        "",
        "Files:",
        f"  {trade_csv}",
        f"  {tx_csv}",
        f"  {cluster_csv}",
        f"  {errors_csv}",
    ]
    report_txt.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    summarize(trade_rows, tx_rows, cluster_rows)
    print("\nOutput files:")
    print(f"  {trade_csv}")
    print(f"  {tx_csv}")
    print(f"  {cluster_csv}")
    print(f"  {errors_csv}")
    print(f"  {report_txt}")

    if lookup_errors:
        print(f"\nWARNING: {len(lookup_errors)} transaction detail lookups failed; inspect {errors_csv}.")
    print("\nNo orders or trades were modified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
