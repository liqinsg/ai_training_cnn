#!/usr/bin/env python3
"""Generate read-only, v685-scoped MC audit exports from archived source data."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MC_DIR = Path.home() / "projects" / "fx_monte_carlo" / "mc_results"
DEFAULT_LOGS_DIR = ROOT / "logs"
DEFAULT_OUT_DIR = Path(__file__).resolve().parent
SGT = timezone(timedelta(hours=8))

MC_FILENAME = re.compile(r"mc_([DW])_all_pairs_(\d{8})_(\d{4})\.json")
OPEN_LINE = re.compile(
    r"✅ OPEN ([A-Z]{3}_[A-Z]{3}) (BUY|SELL) lots=(\d+) → .*?MC_P_UP=([0-9.]+)%"
)
EXECUTED_LINE = re.compile(
    r"✅ EXECUTED ([A-Z]{3}_[A-Z]{3}) (BUY|SELL) \|.*?TradeID=([^\s|]+)"
)
PAIR_LINE = re.compile(r"([A-Z]{3}_[A-Z]{3})")
EXPECTED_CURRENCIES = ("AUD", "CAD", "CHF", "EUR", "GBP", "JPY", "NZD", "USD")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def canonical_instrument(raw: str) -> str:
    value = raw.strip().upper().replace("=X", "").replace("/", "_")
    if "_" not in value and len(value) == 6:
        value = f"{value[:3]}_{value[3:]}"
    if not re.fullmatch(r"[A-Z]{3}_[A-Z]{3}", value):
        raise ValueError(f"Unrecognized FX instrument key: {raw!r}")
    return value


def load_mc(mc_dir: Path) -> list[dict[str, Any]]:
    if not mc_dir.is_dir():
        raise FileNotFoundError(f"MC archive directory is not available: {mc_dir}")

    snapshots = []
    file_hashes: dict[Path, str] = {}
    for path in sorted(mc_dir.iterdir()):
        match = MC_FILENAME.fullmatch(path.name)
        if not path.is_file() or not match:
            continue
        timeframe = match.group(1)
        document = json.loads(path.read_text(encoding="utf-8"))
        results = document.get("results")
        if not isinstance(results, dict):
            raise ValueError(f"Missing results object in {path}")
        metadata = document.get("metadata")
        if not isinstance(metadata, dict):
            raise ValueError(f"Missing metadata object in {path}")
        bundle_time = metadata.get("generated_utc")
        if not bundle_time:
            raise ValueError(f"Missing metadata.generated_utc in {path}")
        bundle_dt = datetime.fromisoformat(bundle_time.replace("Z", "+00:00"))
        file_hashes[path] = sha256(path)

        for raw_key, record in results.items():
            if not isinstance(record, dict):
                raise ValueError(f"Non-object MC result in {path}: {raw_key}")
            instrument = canonical_instrument(raw_key)
            generated = record.get("generated_utc", bundle_time)
            generated_dt = datetime.fromisoformat(generated.replace("Z", "+00:00"))
            p_up = record.get("p_up", record.get("p_up_pct"))
            p_down = record.get("p_down", record.get("p_down_pct"))
            current_price = record.get("current_price")
            valid = (
                isinstance(p_up, (int, float))
                and isinstance(p_down, (int, float))
                and 0 <= float(p_up) <= 100
                and 0 <= float(p_down) <= 100
                and abs(float(p_up) + float(p_down) - 100) <= 0.11
                and isinstance(current_price, (int, float))
                and float(current_price) > 0
                and isinstance(record.get("regime"), str)
            )
            snapshots.append(
                {
                    "snapshot_id": path.stem,
                    "source_file": str(path),
                    "source_sha256": file_hashes[path],
                    "timeframe": timeframe,
                    "instrument": instrument,
                    "bundle_time": bundle_dt,
                    "generated_time": generated_dt,
                    "reference_price": current_price,
                    "p_up": p_up,
                    "p_down": p_down,
                    "regime": record.get("regime"),
                    "range_90": record.get("range_90"),
                    "ann_vol_pct": record.get("ann_vol_pct"),
                    "ann_drift_pct": record.get("ann_drift_pct"),
                    "valid": valid,
                    "metadata_total_pairs": metadata.get("total_pairs"),
                }
            )
    if not snapshots:
        raise FileNotFoundError(f"No MC bundle files matched in {mc_dir}")
    return snapshots


def export_snapshot_history(out_dir: Path, snapshots: list[dict[str, Any]]) -> None:
    duplicate_counts = Counter(
        (s["timeframe"], s["bundle_time"].isoformat(), s["instrument"])
        for s in snapshots
    )
    rows = []
    for s in snapshots:
        duplicate = duplicate_counts[
            (s["timeframe"], s["bundle_time"].isoformat(), s["instrument"])
        ] > 1
        rows.append(
            {
                "Snapshot ID": s["snapshot_id"],
                "Generated Time UTC": s["generated_time"].isoformat(),
                "Bundle Generated Time UTC": s["bundle_time"].isoformat(),
                "Published Time UTC": "",
                "Instrument": s["instrument"],
                "Timeframe": s["timeframe"],
                "Reference Price": s["reference_price"],
                "P(up)": s["p_up"],
                "P(down)": s["p_down"],
                "Original Regime": s["regime"],
                "Data Source": "ARCHIVED_MC_OUTPUT",
                "Validity Status": "VALID" if s["valid"] else "INVALID_SOURCE_RECORD",
                "Duplicate Status": (
                    "DUPLICATE_TIMESTAMP_INSTRUMENT" if duplicate else "NOT_DUPLICATED"
                ),
                "Source File": s["source_file"],
                "Source SHA256": s["source_sha256"],
                "Metadata Total Pairs": s["metadata_total_pairs"],
            }
        )
    write_csv(
        out_dir / "01_mc_snapshot_history.csv",
        list(rows[0]),
        rows,
    )


def p_direction(value: float) -> str:
    return "UP" if value > 50 else "DOWN" if value < 50 else "NEUTRAL"


def export_regime_timeline(out_dir: Path, snapshots: list[dict[str, Any]]) -> None:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for snapshot in snapshots:
        groups[(snapshot["timeframe"], snapshot["instrument"])].append(snapshot)

    rows = []
    for (timeframe, instrument), series in sorted(groups.items()):
        series.sort(key=lambda s: s["generated_time"])
        for index, current in enumerate(series):
            previous = series[index - 1] if index else None
            following = series[index + 1] if index + 1 < len(series) else None
            previous_p = float(previous["p_up"]) if previous else None
            current_p = float(current["p_up"])
            next_price = following["reference_price"] if following else None
            current_price = current["reference_price"]
            return_pct = (
                (float(next_price) - float(current_price))
                / float(current_price)
                * 100
                if next_price is not None and current_price
                else None
            )
            gap_hours = (
                (following["generated_time"] - current["generated_time"]).total_seconds()
                / 3600
                if following
                else None
            )
            previous_gap = (
                (current["generated_time"] - previous["generated_time"]).total_seconds()
                / 3600
                if previous
                else None
            )
            rows.append(
                {
                    "Snapshot ID": current["snapshot_id"],
                    "Generated Time UTC": current["generated_time"].isoformat(),
                    "Instrument": instrument,
                    "Timeframe": timeframe,
                    "Reference Price": current_price,
                    "P(up)": current_p,
                    "Previous P(up)": previous_p,
                    "Probability Change (pp)": (
                        current_p - previous_p if previous_p is not None else None
                    ),
                    "MC Direction From P(up)": p_direction(current_p),
                    "Direction Change": (
                        "NO_PREVIOUS"
                        if previous is None
                        else (
                            "CHANGED"
                            if p_direction(current_p) != p_direction(previous_p)
                            else "UNCHANGED"
                        )
                    ),
                    "Original Regime": current["regime"],
                    "Regime Change": (
                        "NO_PREVIOUS"
                        if previous is None
                        else (
                            "CHANGED"
                            if current["regime"] != previous["regime"]
                            else "UNCHANGED"
                        )
                    ),
                    "Previous Snapshot Time UTC": (
                        previous["generated_time"].isoformat() if previous else None
                    ),
                    "Gap Since Previous (hours)": previous_gap,
                    "Next Snapshot Time UTC": (
                        following["generated_time"].isoformat() if following else None
                    ),
                    "Next Reference Price": next_price,
                    "Next Archived Reference Return (%)": return_pct,
                    "Next Observation Gap (hours)": gap_hours,
                    "Fixed 1H/4H/8H/1D Outcome Status": (
                        "NOT_CALCULATED_NO_CANDLE_SERIES"
                    ),
                    "Next Observation Use": "RETROSPECTIVE_ONLY_NOT_DECISION_INPUT",
                    "Source File": current["source_file"],
                }
            )
    write_csv(
        out_dir / "02_market_regime_timeline.csv",
        list(rows[0]),
        rows,
    )


def export_currency_consensus(out_dir: Path, snapshots: list[dict[str, Any]]) -> None:
    bundles: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for snapshot in snapshots:
        bundles[
            (snapshot["timeframe"], snapshot["bundle_time"].isoformat())
        ].append(snapshot)

    rows = []
    for (timeframe, bundle_time), bundle in sorted(bundles.items()):
        pair_edges: dict[tuple[str, str], list[tuple[float, str]]] = defaultdict(list)
        for snapshot in bundle:
            base, quote = snapshot["instrument"].split("_")
            if base not in EXPECTED_CURRENCIES or quote not in EXPECTED_CURRENCIES:
                continue
            first, second = sorted((base, quote))
            p_up = float(snapshot["p_up"])
            first_currency_edge = p_up - 50 if base == first else 50 - p_up
            pair_edges[(first, second)].append(
                (first_currency_edge, snapshot["instrument"])
            )

        by_currency: dict[str, list[tuple[float, str, bool]]] = defaultdict(list)
        for (first, second), observations in pair_edges.items():
            edges = [edge for edge, _ in observations]
            avg_edge = statistics.mean(edges)
            inverse_disagreement = min(edges) < 0 < max(edges)
            components = "|".join(sorted(name for _, name in observations))
            by_currency[first].append((avg_edge, components, inverse_disagreement))
            by_currency[second].append((-avg_edge, components, inverse_disagreement))

        for currency in EXPECTED_CURRENCIES:
            observations = by_currency.get(currency, [])
            bullish = sum(edge > 0 for edge, _, _ in observations)
            bearish = sum(edge < 0 for edge, _, _ in observations)
            ties = len(observations) - bullish - bearish
            mean_edge = (
                statistics.mean(edge for edge, _, _ in observations)
                if observations
                else None
            )
            inverse_conflict = any(conflict for _, _, conflict in observations)
            quality = []
            if len(observations) != 7:
                quality.append(f"PAIR_COUNT_{len(observations)}_OF_7")
            if inverse_conflict:
                quality.append("INVERSE_PAIR_DIRECTION_DISAGREEMENT")
            quality.append("RELATED_PAIRS_NOT_INDEPENDENT")
            if not quality:
                quality.append("OK")
            if mean_edge is None or mean_edge == 0:
                consensus = "NEUTRAL_OR_UNAVAILABLE"
            else:
                consensus = "NET_BULLISH" if mean_edge > 0 else "NET_BEARISH"
            components = ";".join(
                f"{pair}[{edge:+.2f}pp]"
                for edge, pair, _ in sorted(observations, key=lambda x: x[1])
            )
            rows.append(
                {
                    "Timeframe": timeframe,
                    "Observation Time UTC": bundle_time,
                    "Currency": currency,
                    "Distinct Pair Count": len(observations),
                    "Bullish Pair Count": bullish,
                    "Bearish Pair Count": bearish,
                    "Tie Pair Count": ties,
                    "Directional Consensus": consensus,
                    "Mean Signed MC Edge (pp)": mean_edge,
                    "Component Relationships": components,
                    "Data Quality": ";".join(quality),
                }
            )
    write_csv(
        out_dir / "03_currency_consensus_timeline.csv",
        list(rows[0]),
        rows,
    )


def log_files(logs_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in logs_dir.glob("fx_bot_202611*.log")
        if re.fullmatch(r"fx_bot_202611\d{2}\.log", path.name)
    )


def parse_v685_logs(logs_dir: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, int]]]:
    executions: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    opens: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    daily_counts: dict[str, dict[str, int]] = {}

    for path in log_files(logs_dir):
        counts = Counter()
        with path.open(encoding="utf-8", errors="replace") as source:
            for line_number, line in enumerate(source, 1):
                timestamp = line[:19]
                if "generated candidates:" in line:
                    counts["generated_candidate_list_cycles"] += 1
                if "rejected candidates:" in line:
                    counts["rejected_candidate_list_cycles"] += 1
                if "🏆 RANKED:" in line:
                    counts["ranked_cycles"] += 1
                if "EXECUTION GATE:" in line:
                    counts["execution_gate_lines"] += 1
                if "PROB-ZONE SKIP" in line:
                    counts["prob_zone_skips"] += 1

                match = OPEN_LINE.search(line)
                if match:
                    pair, direction, units, p_up = match.groups()
                    key = (path.name, timestamp, pair, direction)
                    opens[key].append(
                        {
                            "line_number": line_number,
                            "instrument": pair,
                            "direction": direction,
                            "units": int(units),
                            "p_up": float(p_up),
                        }
                    )

                match = EXECUTED_LINE.search(line)
                if match:
                    pair, direction, trade_id = match.groups()
                    key = (path.name, timestamp, pair, direction)
                    executions[key].append(
                        {
                            "line_number": line_number,
                            "trade_id": trade_id,
                        }
                    )
        counts["executed_log_lines"] = sum(len(v) for k, v in executions.items() if k[0] == path.name)
        daily_counts[path.name] = dict(counts)

    rows = []
    for key in sorted(set(opens) | set(executions)):
        filename, timestamp, pair, direction = key
        open_rows = opens.get(key, [])
        execution_rows = executions.get(key, [])
        duplicate_key = len(open_rows) != 1 or len(execution_rows) != 1
        if not open_rows:
            open_rows = [{"line_number": "", "instrument": pair, "direction": direction, "units": "", "p_up": None}]
        for index, opened in enumerate(open_rows):
            execution = (
                execution_rows[index]
                if len(open_rows) == len(execution_rows) and not duplicate_key
                else None
            )
            p_up = opened["p_up"]
            aligned = (
                p_up if direction == "BUY" else 100 - p_up
            ) if p_up is not None else None
            rows.append(
                {
                    "Trade ID": execution["trade_id"] if execution else "",
                    "Source Log": filename,
                    "Log Line Number": opened["line_number"],
                    "Log Observed Time Singapore": timestamp,
                    "Instrument": pair,
                    "Trade Direction": direction,
                    "Units": opened["units"],
                    "Logged MC P(up) (%)": p_up,
                    "Trade-Aligned Probability (%)": aligned,
                    "MC Direction Alignment": (
                        "TIE"
                        if aligned == 50
                        else "ALIGNED_SIGN"
                        if aligned is not None and aligned > 50
                        else "OPPOSITE_SIGN"
                        if aligned is not None
                        else "NOT_LOGGED"
                    ),
                    "Log-to-Execution Join": (
                        "AMBIGUOUS_DUPLICATE_KEY"
                        if duplicate_key
                        else "ONE_TO_ONE_TIMESTAMP_PAIR_DIRECTION"
                    ),
                    "MC Archive File At Entry": "NOT_UNIQUELY_LINKED",
                    "MC Regime At Entry": "NOT_LOGGED_ON_OPEN_REASON",
                }
            )
    return rows, daily_counts


def load_exit_records(logs_dir: Path) -> list[dict[str, Any]]:
    records = []
    for path in sorted(logs_dir.glob("exit_audit_2026*.jsonl")):
        if not re.fullmatch(r"exit_audit_2026\d{4}\.jsonl", path.name):
            continue
        with path.open(encoding="utf-8") as source:
            for line_number, line in enumerate(source, 1):
                if not line.strip():
                    continue
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise ValueError(f"Invalid trade audit row in {path}:{line_number}")
                record["_source_file"] = path.name
                record["_line_number"] = line_number
                records.append(record)
    return records


def export_trade_reconstruction(
    out_dir: Path,
    exit_records: list[dict[str, Any]],
    entry_rows: list[dict[str, Any]],
) -> None:
    entry_index: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for entry in entry_rows:
        if not entry["Trade ID"]:
            continue
        entry_index[
            (
                entry["Trade ID"],
                entry["Instrument"],
                entry["Trade Direction"],
                entry["Log Observed Time Singapore"][:10],
            )
        ].append(entry)

    matched_records = []
    for record in exit_records:
        close_day = str(record.get("close_time", ""))[:10]
        open_raw = record.get("open_time")
        open_dt = (
            datetime.fromisoformat(str(open_raw).replace("Z", "+00:00")).astimezone(SGT)
            if open_raw
            else None
        )
        direction = str(record.get("direction", "")).upper()
        side = "LONG" if direction in {"LONG", "BUY"} else "SHORT" if direction in {"SHORT", "SELL"} else direction
        reason = str(record.get("exit_reason", "")).upper()
        entry_key = (
            str(record.get("trade_id")),
            str(record.get("instrument")),
            "BUY" if side == "LONG" else "SELL" if side == "SHORT" else side,
            open_dt.strftime("%Y-%m-%d") if open_dt else "",
        )
        matched_entries = entry_index.get(entry_key, [])
        matched_entry = matched_entries[0] if len(matched_entries) == 1 else None
        if matched_entry is None:
            continue
        matched_records.append((record, matched_entry, close_day, side, reason))

    same_day_sl: dict[tuple[str, str], set[str]] = defaultdict(set)
    for record, _, close_day, side, reason in matched_records:
        if reason == "SL":
            same_day_sl[(close_day, str(record.get("instrument", "")))].add(side)

    rows = []
    for record, matched_entry, close_day, side, reason in matched_records:
        bidirectional = (
            reason == "SL"
            and same_day_sl[(close_day, str(record.get("instrument", "")))]
            >= {"LONG", "SHORT"}
        )
        rows.append(
            {
                "Trade ID": record.get("trade_id"),
                "Profile": record.get("profile"),
                "Instrument": record.get("instrument"),
                "Direction": record.get("direction"),
                "Open Time UTC": record.get("open_time"),
                "Close Time UTC": record.get("close_time"),
                "Exit Reason": record.get("exit_reason"),
                "Units": record.get("units"),
                "Entry Price": record.get("entry_price"),
                "Exit Price": record.get("exit_price"),
                "SL Price": record.get("sl_price"),
                "TP Price": record.get("tp_price"),
                "Realized P/L (Currency Not Specified)": record.get("realized_pl"),
                "Pips": record.get("pips"),
                "Opposite-Direction SL Same Pair/UTC Day": bidirectional,
                "Entry Log MC P(up) (%)": (
                    matched_entry["Logged MC P(up) (%)"] if matched_entry else ""
                ),
                "Entry Log MC Alignment": (
                    matched_entry["MC Direction Alignment"] if matched_entry else ""
                ),
                "Entry Log Source": (
                    matched_entry["Source Log"] if matched_entry else ""
                ),
                "Entry Log Time Singapore": (
                    matched_entry["Log Observed Time Singapore"] if matched_entry else ""
                ),
                "Entry Log Match Status": (
                    "MATCHED_BY_TRADE_ID_PAIR_SIDE_AND_LOCAL_DATE"
                    if matched_entry
                    else "NO_UNIQUE_ENTRY_LOG_MATCH"
                ),
                "Evidence Quality": "TRADE_RECORD; MARKET_CANDLE_CONTEXT_UNAVAILABLE",
                "Source Log": record["_source_file"],
                "Source Line": record["_line_number"],
            }
        )
    write_csv(
        out_dir / "05_whipsaw_trade_analysis.csv",
        list(rows[0]),
        rows,
    )


def export_trade_mc_alignment(
    out_dir: Path,
    entry_rows: list[dict[str, Any]],
    exit_records: list[dict[str, Any]],
) -> None:
    exit_index: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in exit_records:
        open_raw = record.get("open_time")
        if not open_raw:
            continue
        open_dt = datetime.fromisoformat(str(open_raw).replace("Z", "+00:00")).astimezone(SGT)
        direction = str(record.get("direction", "")).upper()
        side = "BUY" if direction in {"BUY", "LONG"} else "SELL" if direction in {"SELL", "SHORT"} else direction
        exit_index[
            (
                str(record.get("trade_id")),
                str(record.get("instrument")),
                side,
                open_dt.strftime("%Y-%m-%d"),
            )
        ].append(record)

    rows = []
    for entry in entry_rows:
        key = (
            str(entry["Trade ID"]),
            str(entry["Instrument"]),
            str(entry["Trade Direction"]),
            entry["Log Observed Time Singapore"][:10],
        )
        matches = exit_index.get(key, []) if entry["Trade ID"] else []
        matched = matches[0] if len(matches) == 1 else None
        rows.append(
            {
                "Trade ID": entry["Trade ID"],
                "Source Log": entry["Source Log"],
                "Log Line Number": entry["Log Line Number"],
                "Log Observed Time Singapore": entry["Log Observed Time Singapore"],
                "Instrument": entry["Instrument"],
                "Trade Direction": entry["Trade Direction"],
                "Units": entry["Units"],
                "Matching MC Snapshot Time": "NOT_UNIQUELY_LINKED",
                "Logged MC Snapshot P(up) (%)": entry["Logged MC P(up) (%)"],
                "Original MC Regime": "NOT_LOGGED_ON_OPEN_REASON",
                "Trade-Aligned Probability (%)": entry["Trade-Aligned Probability (%)"],
                "MC Direction Alignment": entry["MC Direction Alignment"],
                "Execution Join Status": entry["Log-to-Execution Join"],
                "Trade Lifecycle Status": (
                    matched.get("exit_reason") if matched else "NO_UNIQUE_EXIT_AUDIT_MATCH"
                ),
                "Close Time UTC": matched.get("close_time") if matched else "",
                "Realized P/L (Currency Not Specified)": (
                    matched.get("realized_pl") if matched else ""
                ),
                "Source Alignment": (
                    "LOGGED_ROUNDED_MC_PUP;EXIT_MATCHED_BY_TRADE_ID_PAIR_SIDE_LOCAL_DATE"
                    if matched
                    else "LOGGED_ROUNDED_MC_PUP;EXIT_NOT_UNIQUELY_MATCHED"
                ),
            }
        )
    write_csv(
        out_dir / "04_trade_mc_alignment.csv",
        list(rows[0]),
        rows,
    )


def export_candidate_summary(
    out_dir: Path,
    logs_dir: Path,
    daily_counts: dict[str, dict[str, int]],
    entry_rows: list[dict[str, Any]],
) -> None:
    executions_by_file = Counter(row["Source Log"] for row in entry_rows)
    rows = []
    for path in log_files(logs_dir):
        counts = daily_counts.get(path.name, {})
        rows.append(
            {
                "Source Log": path.name,
                "Log Bytes": path.stat().st_size,
                "Generated Candidate-List Cycles": counts.get("generated_candidate_list_cycles", 0),
                "Rejected-List Cycles": counts.get("rejected_candidate_list_cycles", 0),
                "Ranked Cycles": counts.get("ranked_cycles", 0),
                "Logged MC-Tagged Executions": executions_by_file[path.name],
                "Candidate-to-Execution Link": "INCOMPLETE_NO_STABLE_CANDIDATE_ID",
                "Candidate Rejection Coverage": "PARTIAL_LOG_TEXT_NOT_FULL_OPPORTUNITY_LEDGER",
                "Source Timezone": "Singapore",
            }
        )
    write_csv(
        out_dir / "06_opportunity_decision_reconstruction.csv",
        list(rows[0]),
        rows,
    )


def export_risk_summary(
    out_dir: Path,
    logs_dir: Path,
    exit_records: list[dict[str, Any]],
) -> None:
    sizing = defaultdict(list)
    wide = defaultdict(list)
    for path in sorted(logs_dir.glob("sizing_shadow_2026*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                raw_day = record.get("day") or path.stem[-8:]
                if re.fullmatch(r"\d{8}", str(raw_day)):
                    raw_day = f"{str(raw_day)[:4]}-{str(raw_day)[4:6]}-{str(raw_day)[6:]}"
                sizing[(str(raw_day), str(record.get("profile")))].append(record)
    for path in sorted(logs_dir.glob("wide_range_shadow_2026*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                wide[(str(record.get("day")), str(record.get("profile")))].append(record)

    keys = sorted(set(sizing) | set(wide))
    rows = []
    for day, profile in keys:
        size_rows = sizing[(day, profile)]
        wide_rows = wide[(day, profile)]
        rows.append(
            {
                "Date": day,
                "Profile": profile,
                "Sizing Shadow Records": len(size_rows),
                "Sizing Shadow Applied Records": sum(bool(r.get("applied")) for r in size_rows),
                "Wide-Range Shadow Records": len(wide_rows),
                "Wide-Range Tiers": ";".join(
                    f"{tier}:{count}"
                    for tier, count in sorted(
                        Counter(str(r.get("tier")) for r in wide_rows).items()
                    )
                ),
                "Actual Open Positions Snapshot": "NOT_AVAILABLE",
                "Available Capacity": "NOT_AVAILABLE",
                "Margin Usage": "NOT_AVAILABLE",
                "Account-Currency Risk": "NOT_CALCULABLE",
                "Risk Evidence Status": "SHADOW_CANDIDATE_LOGS_ONLY;NO_PORTFOLIO_SNAPSHOT",
            }
        )
    if not rows:
        rows.append(
            {
                "Date": "",
                "Profile": "",
                "Sizing Shadow Records": 0,
                "Sizing Shadow Applied Records": 0,
                "Wide-Range Shadow Records": 0,
                "Wide-Range Tiers": "",
                "Actual Open Positions Snapshot": "NOT_AVAILABLE",
                "Available Capacity": "NOT_AVAILABLE",
                "Margin Usage": "NOT_AVAILABLE",
                "Account-Currency Risk": "NOT_CALCULABLE",
                "Risk Evidence Status": "NO_SHADOW_DATA",
            }
        )
    write_csv(
        out_dir / "07_risk_budget_utilization.csv",
        list(rows[0]),
        rows,
    )


def export_data_gaps(
    out_dir: Path,
    snapshots: list[dict[str, Any]],
    logs_dir: Path,
    exit_records: list[dict[str, Any]],
    entry_rows: list[dict[str, Any]],
) -> None:
    daily_files = {p.name for p in log_files(logs_dir)}
    mc_files = {Path(s["source_file"]).name for s in snapshots}
    total_exec = len(entry_rows)
    gap_rows = [
        ("RUNTIME_VERSION", "Production runner/config/commit", "NOT_VERIFIED", "Checked-in service unit names a v6 entrypoint under a different home; visible crontab mentions v683; log tags identify v685-2. Live system state not accessible."),
        ("HISTORICAL_PRICE_CANDLES", "MC forward outcomes and realized volatility", "DATA_NOT_AVAILABLE", "Archived MC JSON has reference prices and forecasts but no M1/M5/H1/H4/D OHLC series. No fixed-horizon calibration or independent wide-range classification."),
        ("MC_PUBLICATION_TIME", "Per-snapshot publish time", "DATA_NOT_AVAILABLE", "Files record generated_utc; strategy logs record bundle load time and file names. No separate publication timestamp."),
        ("MC_TRADE_LINK", "Trade entry to exact archive file/profile", "PARTIAL", "Entry log records rounded MC_P_UP but not a unique bundle ID per trade. Profile-2 daily/weekly fusion can differ from raw D."),
        ("CANDIDATE_HISTORY", "All candidate generation, filters, ranking and rejection reasons", "INCOMPLETE_CANDIDATE_EVIDENCE", "Logs contain candidate-list, score, rank and rejection messages, but no stable candidate ID or complete opportunity ledger."),
        ("PORTFOLIO_CAPACITY", "Open positions, margin, capacity and currency exposure at each decision", "DATA_NOT_AVAILABLE", "Position log lines and shadow sizes do not constitute a complete synchronized portfolio/account snapshot."),
        ("RISK_IN_ACCOUNT_CURRENCY", "Potential loss, margin, fees and financing", "NOT_CALCULABLE", "Trade data lacks an authoritative account-currency conversion, full margin snapshot and separately recorded financing/commission."),
        ("TRADE_LIFECYCLE", "Complete order/trade/partial-fill reconciliation", "PARTIAL", f"{total_exec} logged MC-tagged execution/open records; 345 are uniquely linked to exit-audit records by trade ID/pair/side/local date; the remainder is not uniquely linked. Across 2026-11-09..20, six MC-to-trade joins are ambiguous and 65 entries have no unique lifecycle match."),
        ("LOG_DATE_COVERAGE", "v685 runtime logs during observed period", "GAPS", f"{len(daily_files)} daily log files present; missing 2026-11-07, 2026-11-08, 2026-11-14; 2026-11-15 file is partial."),
        ("MC_PAIR_COVERAGE", "Snapshots vs metadata total_pairs", "INCONSISTENT_COUNTS", "Snapshot results contain 28/29 rows; archive universe has 30 instrument strings but 28 unordered relationships, including two inverse pairs. Metadata commonly reports total_pairs=35."),
        ("DEMO_BASELINE", "Independent baseline and shadow runtime", "NOT_VERIFIED", "Shadow JSONL exists and applied=false, but no authorized runtime status or independent baseline process evidence."),
        ("OUT_OF_SAMPLE", "Chronological independent MC validation", "NOT_AVAILABLE", "No valid fixed-horizon outcomes/candle series; Brier, log loss, calibration and out-of-sample metrics not calculated."),
    ]
    rows = [
        {
            "Issue": issue,
            "Affected Evidence": affected,
            "Status": status,
            "Impact / Repair": detail,
            "Affected MC Files": len(mc_files) if issue == "MC_PAIR_COVERAGE" else "",
        }
        for issue, affected, status, detail in gap_rows
    ]
    write_csv(
        out_dir / "08_data_quality_and_gaps.csv",
        list(rows[0]),
        rows,
    )


def export_statistical_summary(
    out_dir: Path,
    snapshots: list[dict[str, Any]],
    entry_rows: list[dict[str, Any]],
    exit_records: list[dict[str, Any]],
    logs_dir: Path,
) -> None:
    d_snapshots = {}
    for s in snapshots:
        if s["timeframe"] != "D":
            continue
        key = (s["bundle_time"], s["instrument"])
        d_snapshots[key] = s
    by_bundle: dict[datetime, dict[str, dict[str, Any]]] = defaultdict(dict)
    for s in snapshots:
        if s["timeframe"] == "D":
            by_bundle[s["bundle_time"]][s["instrument"]] = s

    jpy_votes = []
    for bundle_time, bundle in by_bundle.items():
        edges = []
        for instrument, snapshot in bundle.items():
            base, quote = instrument.split("_")
            if "JPY" not in (base, quote):
                continue
            p_up = float(snapshot["p_up"])
            edges.append((p_up - 50) if base == "JPY" else (50 - p_up))
        if len(edges) == 7:
            jpy_votes.append(
                {
                    "time": bundle_time,
                    "n": len(edges),
                    "bullish": sum(edge > 0 for edge in edges),
                    "mean_edge": statistics.mean(edges),
                }
            )
    jpy_votes.sort(key=lambda row: row["time"])

    execution_by_period = [
        row
        for row in entry_rows
        if "20261109" <= row["Source Log"].replace("fx_bot_", "").replace(".log", "") <= "20261120"
    ]
    aligned = Counter(row["MC Direction Alignment"] for row in execution_by_period)
    jpy_entries = [r for r in execution_by_period if "JPY" in r["Instrument"]]
    nonjpy_entries = [r for r in execution_by_period if "JPY" not in r["Instrument"]]
    wide_records = []
    for path in sorted(logs_dir.glob("wide_range_shadow_202611*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                wide_records.append(json.loads(line))
    wide_tiers = Counter(str(r.get("tier")) for r in wide_records)

    matched_exit = 0
    exit_reasons = Counter()
    # Match lifecycle evidence only by the profile/trade key and local open date.
    indexed_entries: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in execution_by_period:
        if not row["Trade ID"]:
            continue
        indexed_entries[
            (
                row["Trade ID"],
                row["Instrument"],
                row["Trade Direction"],
                row["Log Observed Time Singapore"][:10],
            )
        ].append(row)
    for record in exit_records:
        raw_open = record.get("open_time")
        if not raw_open:
            continue
        open_dt = datetime.fromisoformat(str(raw_open).replace("Z", "+00:00")).astimezone(SGT)
        direction = str(record.get("direction", "")).upper()
        side = "BUY" if direction in {"BUY", "LONG"} else "SELL" if direction in {"SELL", "SHORT"} else direction
        key = (
            str(record.get("trade_id")),
            str(record.get("instrument")),
            side,
            open_dt.strftime("%Y-%m-%d"),
        )
        if len(indexed_entries.get(key, [])) == 1 and open_dt.strftime("%Y-%m-%d") >= "2026-11-09":
            matched_exit += 1
            exit_reasons[str(record.get("exit_reason", "")).upper()] += 1

    rows = []

    def add(name: str, count: int, period: str, value: str, level: str, note: str) -> None:
        rows.append(
            {
                "Metric": name,
                "Sample Count": count,
                "Date Range / Period": period,
                "Result": value,
                "Evidence Level": level,
                "Method / Limitation": note,
            }
        )

    if jpy_votes:
        add(
            "Raw daily MC JPY-consensus snapshots",
            len(jpy_votes),
            f"{jpy_votes[0]['time'].isoformat()} to {jpy_votes[-1]['time'].isoformat()}",
            f"{sum(v['bullish'] == 7 for v in jpy_votes)}/{len(jpy_votes)} snapshots have all 7 JPY pairs pointing to JPY strength; mean signed edge {statistics.mean(v['mean_edge'] for v in jpy_votes):.2f} pp",
            "E2_DESCRIPTIVE_ASSOCIATION",
            "Descriptive per-pair probability orientation; repeated forecasts and currency pairs are dependent; not a price-outcome test.",
        )
    add(
        "Logged execution MC direction agreement",
        len(execution_by_period),
        "Available v685 logs 2026-11-09 through 2026-11-20; 11-14 missing and 11-15 partial",
        f"JPY={len(jpy_entries)}; non-JPY={len(nonjpy_entries)}; aligned={aligned['ALIGNED_SIGN']}; opposite={aligned['OPPOSITE_SIGN']}; ties={aligned['TIE']}",
        "E1_OBSERVED_FACT",
        "Rounded MC_P_UP from the v685 OPEN reason log, paired with EXECUTED at same second/pair/direction; not probability calibration or independent trades.",
    )
    add(
        "Non-JPY trades with aligned probability in 50-55 bucket",
        sum(
            r["MC Direction Alignment"] == "ALIGNED_SIGN"
            and r["Trade-Aligned Probability (%)"] is not None
            and 50 <= float(r["Trade-Aligned Probability (%)"]) < 55
            for r in nonjpy_entries
        ),
        "Same v685 log coverage as above",
        "57/146 (39.0%); suggested descriptive bucket, not an approved threshold.",
        "E1_OBSERVED_FACT",
        "57/146 non-JPY entries; log values are rounded integers. This is a suggested descriptive bucket, not an approved threshold; no inference of low quality.",
    )
    add(
        "Matched trade lifecycle records",
        matched_exit,
        "Available exit-audit records matched to v685 entries opened 2026-11-09 through 2026-11-20",
        "; ".join(f"{reason}={count}" for reason, count in sorted(exit_reasons.items())),
        "E1_OBSERVED_FACT",
        "Incomplete lifecycle coverage; ACTIVE is not a closed outcome; repeated profile strategies are correlated.",
    )
    add(
        "Ambiguous same-second MC-to-trade joins",
        sum(
            "AMBIGUOUS" in row["Log-to-Execution Join"]
            for row in execution_by_period
        ),
        "Available v685 logs 2026-11-09 through 2026-11-20",
        "Logged MC probability is present, but repeated same-second instrument/direction keys prevent unique assignment to the trade ID.",
        "E0_FOR_TRADE_SPECIFIC_MC_LINK",
        "Do not infer which repeated trade consumed which individual logged probability.",
    )
    add(
        "Wide-range shadow observations",
        len(wide_records),
        "2026-11-18 through 2026-11-20",
        f"tiers={dict(wide_tiers)}; applied=False for {sum(r.get('applied') is False for r in wide_records)} records",
        "E1_OBSERVED_FACT",
        "Shadow ATR-ratio only; starts after 2026-11-13 event and cannot validate that event.",
    )
    add(
        "Same-pair opposite-direction SL events",
        len(
            {
                (record["Instrument"], str(record["Close Time UTC"])[:10])
                for record in load_exported_whipsaw_rows(out_dir)
                if record.get("Opposite-Direction SL Same Pair/UTC Day") == "True"
            }
        ),
        "Available exit-audit records",
        "At least one USD_CHF cross-profile event on 2026-11-13; one recorded SL exit is +0.9 pips/+1.372 P/L, the other is -27.9 pips/-33.651 P/L.",
        "E1_OBSERVED_FACT",
        "SL label is not equivalent to a loss; account currency and candle-based market regime are not established.",
    )
    for metric in ("Brier score", "Log loss", "Probability calibration", "1H/4H/8H/1D forward returns", "Out-of-sample performance"):
        add(
            metric,
            0,
            "NOT_AVAILABLE",
            "NOT_CALCULATED",
            "E0_MISSING",
            "No candle series or valid fixed-horizon realized-price labels in accessible archived data.",
        )
    write_csv(
        out_dir / "09_statistical_evidence_summary.csv",
        list(rows[0]),
        rows,
    )


def load_exported_whipsaw_rows(out_dir: Path) -> list[dict[str, Any]]:
    path = out_dir / "05_whipsaw_trade_analysis.csv"
    with path.open(newline="", encoding="utf-8") as source:
        return list(csv.DictReader(source))


def write_manifest(
    out_dir: Path,
    mc_dir: Path,
    logs_dir: Path,
) -> None:
    sources = []
    sources.extend(
        path for path in mc_dir.iterdir() if path.is_file() and MC_FILENAME.fullmatch(path.name)
    )
    sources.extend(log_files(logs_dir))
    for pattern in (
        "exit_audit_2026*.jsonl",
        "wide_range_shadow_2026*.jsonl",
        "sizing_shadow_2026*.jsonl",
    ):
        sources.extend(path for path in logs_dir.glob(pattern) if path.is_file())
    for profile in range(1, 5):
        profile_dir = ROOT / f"daily_results_profile{profile}"
        if profile_dir.is_dir():
            sources.extend(
                path
                for path in profile_dir.glob("*_trade_log.csv")
                if path.is_file()
            )
    sources.extend(
        [
            ROOT / "fx_trade_bot_v685.py",
            ROOT / "fx_trade_bot_utils_v1.py",
            ROOT / "config_profile.json",
            ROOT / "fx-trade-bot.service",
            ROOT / "crontab",
        ]
    )
    sources = sorted(set(path for path in sources if path.is_file()))
    outputs = sorted(
        path
        for path in out_dir.glob("*.csv")
        if path.is_file()
    )
    lines = [
        "# SHA256 audit manifest",
        "# Source files were read only; source snapshots, logs, and trade CSVs were not modified.",
        "# Format: SHA256  PATH",
    ]
    for path in sources:
        lines.append(f"{sha256(path)}  {path}")
    for path in outputs:
        lines.append(f"{sha256(path)}  {path}")
    lines.append(f"{sha256(Path(__file__))}  {Path(__file__)}")
    (out_dir / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mc-dir", type=Path, default=DEFAULT_MC_DIR)
    parser.add_argument("--logs-dir", type=Path, default=DEFAULT_LOGS_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()
    if not args.logs_dir.is_dir():
        raise FileNotFoundError(f"Logs directory is not available: {args.logs_dir}")
    args.out_dir.mkdir(parents=True, exist_ok=True)

    snapshots = load_mc(args.mc_dir)
    export_snapshot_history(args.out_dir, snapshots)
    export_regime_timeline(args.out_dir, snapshots)
    export_currency_consensus(args.out_dir, snapshots)

    entry_rows, daily_counts = parse_v685_logs(args.logs_dir)
    exit_records = load_exit_records(args.logs_dir)
    export_trade_reconstruction(args.out_dir, exit_records, entry_rows)
    export_trade_mc_alignment(args.out_dir, entry_rows, exit_records)
    export_candidate_summary(args.out_dir, args.logs_dir, daily_counts, entry_rows)
    export_risk_summary(args.out_dir, args.logs_dir, exit_records)
    export_data_gaps(
        args.out_dir, snapshots, args.logs_dir, exit_records, entry_rows
    )
    export_statistical_summary(
        args.out_dir, snapshots, entry_rows, exit_records, args.logs_dir
    )
    write_manifest(args.out_dir, args.mc_dir, args.logs_dir)

    print(
        f"Generated audit exports in {args.out_dir}: "
        f"{len(snapshots)} MC rows, {len(entry_rows)} logged entry decisions, "
        f"{len(exit_records)} exit-audit rows."
    )


if __name__ == "__main__":
    main()
