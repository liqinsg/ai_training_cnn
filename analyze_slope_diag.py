#!/usr/bin/env python3
"""
analyze_slope_diag.py — read SLOPE DIAG lines and report tightening-ladder status.

The bot emits one line per evaluated candidate when SLOPE_DIAG is on:

    📊 SLOPE DIAG: profile=profile3 dir=SELL tf=15m slope=-0.000400
       min_slope=0.000300 price_ok=True loose(-0.000300>=)=True
       strict(-0.001000>=)=False sensitive=True would_flip=True

`would_flip=True` means the candidate passed ONLY because min_slope was relaxed
(price gate satisfied AND slope inside the widened band). Those rows are the
evidence the ladder needs before advancing a rung; `sensitive=True` alone is not
sufficient, because the same candidate may still be blocked by the price leg.

Usage:
    python analyze_slope_diag.py                      # auto-discover logs
    python analyze_slope_diag.py bot_profile3.log
    python analyze_slope_diag.py logs/bot_profile*.log
    python analyze_slope_diag.py --target 20 bot_profile3.log

Exit codes: 0 = report produced, 1 = no usable input, 2 = usage error.
"""

from __future__ import annotations

import argparse
import glob
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

DEFAULT_TARGET = 20

# Copied from the bot's SLOPE_DIAG block. Kept as a regex so a format change
# fails loudly here instead of silently reporting zero rows.
DIAG_RE = re.compile(
    r"SLOPE DIAG: profile=(?P<profile>\S+) dir=(?P<dir>\S+) tf=(?P<tf>\S+) "
    r"slope=(?P<slope>-?[\d.]+) min_slope=(?P<min_slope>[\d.]+) "
    r"price_ok=(?P<price_ok>True|False) "
    r"loose\((?P<loose_th>-?[\d.]+)(?P<loose_cmp>[<>]=)\)=(?P<loose>True|False) "
    r"strict\((?P<strict_th>-?[\d.]+)(?P<strict_cmp>[<>]=)\)=(?P<strict>True|False) "
    r"sensitive=(?P<sensitive>True|False) would_flip=(?P<flip>True|False)"
)

# Outcome markers the bot logs for a candidate, in the order they appear.
# First match wins, so the sequence matters: "passed the trend filter" is a
# meaningful middle state and must be tested before the rejection patterns.
OUTCOME_PATTERNS: Sequence[Tuple[str, re.Pattern]] = (
    ("executed", re.compile(r"EXECUTED\s+(?P<pair>\S+)\s+(?P<dir>BUY|SELL)")),
    ("qualified", re.compile(r": gap=[\d.]+ [≥>]=? [\d.]+ — QUALIFIED")),
    ("rejected_score", re.compile(r"REASON: FINAL .*< MIN_CONVICTION")),
    ("skipped_trend", re.compile(r"SKIP (?:BUY|SELL): .*TREND MISALIGNED")),
    ("skipped_weekly", re.compile(r"SKIP (?:BUY|SELL): .*COUNTER-TREND")),
    ("skipped_other", re.compile(r"SKIP DUPLICATE|MAX_OPEN reached|already open")),
)


@dataclass
class DiagRow:
    file: str
    lineno: int
    profile: str
    direction: str
    timeframe: str
    slope: float
    min_slope: float
    # Strict threshold as printed in the line (SLOPE_DIAG_BASELINE), so the
    # report never hardcodes a baseline that the bot might change.
    strict_threshold: float
    price_ok: bool
    loose: bool
    strict: bool
    sensitive: bool
    would_flip: bool
    outcome: Optional[str] = None

    @property
    def abs_slope(self) -> float:
        return abs(self.slope)


@dataclass
class Group:
    total: int = 0
    sensitive: int = 0
    would_flip: int = 0
    price_ok: int = 0
    loose: int = 0
    slopes: List[float] = field(default_factory=list)
    flips: List[DiagRow] = field(default_factory=list)

    def add(self, row: DiagRow) -> None:
        self.total += 1
        self.sensitive += int(row.sensitive)
        self.would_flip += int(row.would_flip)
        self.price_ok += int(row.price_ok)
        self.loose += int(row.loose)
        self.slopes.append(row.abs_slope)
        if row.would_flip:
            self.flips.append(row)


def discover_logs() -> List[str]:
    """Prefer the live per-profile logs, fall back to anything mentioning DIAG."""
    candidates: List[str] = []
    for pattern in (
        "bot_profile*.log",
        "logs/bot_profile*.log",
        "*.log",
        "logs/*.log",
    ):
        candidates.extend(sorted(glob.glob(pattern)))
    # De-duplicate while preserving order.
    seen = set()
    out = []
    for path in candidates:
        real = str(Path(path).resolve())
        if real not in seen:
            seen.add(real)
            out.append(path)
    return out


def parse_file(path: str, keep_unknown: bool = False) -> Tuple[List[DiagRow], int]:
    """Return (rows, lines_seen). Malformed DIAG-looking lines are counted."""
    rows: List[DiagRow] = []
    malformed = 0
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"  ! cannot read {path}: {exc}", file=sys.stderr)
        return [], 0

    lines = text.splitlines()
    current: Optional[DiagRow] = None
    for lineno, line in enumerate(lines, 1):
        if "SLOPE DIAG" not in line:
            # Outcome attribution: the first outcome marker after a DIAG row
            # belongs to that candidate (the bot handles one pair at a time).
            if current is not None and current.outcome is None:
                for name, pattern in OUTCOME_PATTERNS:
                    if pattern.search(line):
                        current.outcome = name
                        break
            continue

        m = DIAG_RE.search(line)
        if not m:
            malformed += 1
            if keep_unknown:
                print(f"  ! unparsed DIAG line {path}:{lineno}", file=sys.stderr)
            continue
        d = m.groupdict()
        row = DiagRow(
            file=path,
            lineno=lineno,
            profile=d["profile"],
            direction=d["dir"],
            timeframe=d["tf"],
            slope=float(d["slope"]),
            min_slope=float(d["min_slope"]),
            strict_threshold=abs(float(d["strict_th"])),
            price_ok=d["price_ok"] == "True",
            loose=d["loose"] == "True",
            strict=d["strict"] == "True",
            sensitive=d["sensitive"] == "True",
            would_flip=d["flip"] == "True",
        )
        rows.append(row)
        current = row
    return rows, len(lines) + malformed


def dedupe(rows: Iterable[DiagRow]) -> Tuple[List[DiagRow], int]:
    """Same candidate can be logged twice (bot FileHandler + cron redirect)."""
    seen = set()
    out = []
    dropped = 0
    for row in rows:
        key = (
            row.profile,
            row.direction,
            row.timeframe,
            round(row.slope, 9),
            round(row.min_slope, 9),
            row.price_ok,
            row.sensitive,
            row.would_flip,
        )
        if key in seen:
            dropped += 1
            continue
        seen.add(key)
        out.append(row)
    return out, dropped


def grouping(rows: Sequence[DiagRow]) -> Dict[Tuple[str, str, str], Group]:
    groups: Dict[Tuple[str, str, str], Group] = {}
    for row in rows:
        key = (row.profile, row.timeframe, row.direction)
        groups.setdefault(key, Group()).add(row)
    return groups


def fmt_pct(part: int, whole: int) -> str:
    return f"{part / whole * 100:5.1f}%" if whole else "    n/a"


def _display_loc(path: str, lineno: int) -> str:
    """Relative path + line when possible, so multi-file scans stay locatable."""
    try:
        return f"{Path(path).resolve().relative_to(Path.cwd().resolve())}:{lineno}"
    except ValueError:
        return f"{path}:{lineno}"


def pctile(values: Sequence[float], q: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))
    return ordered[idx]


def report(rows: Sequence[DiagRow], target: int, files: Sequence[str]) -> int:
    print("=" * 78)
    print("SLOPE DIAG ANALYSIS — tightening-ladder evidence")
    print("=" * 78)
    print(f"files scanned : {len(files)}")
    for f in files[:8]:
        print(f"                {f}")
    if len(files) > 8:
        print(f"                ... and {len(files) - 8} more")

    if not rows:
        print()
        print("No SLOPE DIAG rows found.")
        print("  1. Is SLOPE_DIAG enabled for this profile?")
        print("     grep -n 'SLOPE_DIAG' config_bot.py")
        print("  2. The bot writes to BOTH <repo>/bot_profileN.log (FileHandler)")
        print("     and logs/bot_profileN.log (cron redirect). Point this script")
        print("     at the one that exists:")
        print("     python analyze_slope_diag.py bot_profile3.log")
        return 1

    overall = Group()
    for row in rows:
        overall.add(row)

    print(f"rows parsed   : {overall.total}")
    flips = [r for r in rows if r.would_flip]
    print()
    print("-" * 78)
    print("LADDER GATE")
    print("-" * 78)
    print(f"  would_flip=True : {len(flips):3d} / {target}   "
          f"({fmt_pct(len(flips), target)} of target)")
    if len(flips) >= target:
        print("  -> target met: eligible to consider the next rung "
              "(0.0003 -> 0.0005).")
        print("     Confirm the outcomes below look acceptable before advancing.")
    else:
        print(f"  -> {target - len(flips)} more would_flip rows needed; "
              "do NOT advance on elapsed time alone.")
    if len(flips) == 0:
        print("  note: zero flips means the relaxation has not changed any")
        print("        decision yet — the slope threshold is not the binding")
        print("        constraint in the observed sample.")

    print()
    print("-" * 78)
    print("COUNTS BY PROFILE / TF / DIRECTION")
    print("-" * 78)
    header = (f"  {'profile':10} {'tf':5} {'dir':5} {'n':>4} "
              f"{'price_ok':>9} {'loose':>7} {'sensitive':>10} {'would_flip':>11}")
    print(header)
    print("  " + "-" * (len(header) - 2))
    for (profile, tf, direction), g in sorted(grouping(rows).items()):
        print(
            f"  {profile:10} {tf:5} {direction:5} {g.total:4d} "
            f"{g.price_ok:4d} ({fmt_pct(g.price_ok, g.total)}) "
            f"{g.loose:3d} "
            f"{g.sensitive:4d} ({fmt_pct(g.sensitive, g.total)}) "
            f"{g.would_flip:4d} ({fmt_pct(g.would_flip, g.total)})"
        )

    print()
    print("-" * 78)
    print("SLOPE MAGNITUDE DISTRIBUTION (|slope| of all evaluated candidates)")
    print("-" * 78)
    mags = sorted(r.abs_slope for r in rows)
    min_slope = rows[-1].min_slope
    strict_baseline = rows[-1].strict_threshold
    print(f"  n={len(mags)}  min={mags[0]:.6f}  p25={pctile(mags, .25):.6f}  "
          f"median={pctile(mags, .5):.6f}  p75={pctile(mags, .75):.6f}  "
          f"max={mags[-1]:.6f}")
    print(f"  active min_slope (widest rung) : {min_slope:.6f}")
    print(f"  strict baseline (from log)     : {strict_baseline:.6f}")
    bands = [
        ("< min_slope (would fail even widened)", lambda v: v < min_slope),
        ("in widened band (sensitive)", lambda v: min_slope <= v < strict_baseline),
        (f">= {strict_baseline:.4f} (always passed)", lambda v: v >= strict_baseline),
    ]
    for label, pred in bands:
        count = sum(1 for v in mags if pred(v))
        print(f"  {label:38} {count:4d}  ({fmt_pct(count, len(mags))})")

    print()
    print("-" * 78)
    print("WOULD_FLIP DETAIL (each row = a decision the relaxation changed)")
    print("-" * 78)
    if not flips:
        print("  (none)")
    else:
        print(f"  {'file:line':34} {'profile':10} {'dir':5} {'slope':>11} "
              f"{'min_slope':>10} {'outcome':>15}")
        for r in flips[:40]:
            loc = _display_loc(r.file, r.lineno)
            print(f"  {loc:34} {r.profile:10} {r.direction:5} "
                  f"{r.slope:11.6f} {r.min_slope:10.6f} "
                  f"{(r.outcome or 'unknown'):>15}")
        if len(flips) > 40:
            print(f"  ... and {len(flips) - 40} more")

    attributed = [r for r in flips if r.outcome]
    if flips:
        print()
        print(f"  outcome coverage: {len(attributed)}/{len(flips)} flip rows "
              "attributed to a following log line")
        if len(attributed) < len(flips):
            print("  note: unattributed rows are usually the last candidate of a")
            print("        run, or a line the outcome patterns do not cover.")

    print()
    print("-" * 78)
    print("SANITY")
    print("-" * 78)
    problems = []
    inconsistent = [
        r for r in rows
        if r.sensitive != (r.loose and not r.strict)
        or r.would_flip != (r.price_ok and r.sensitive)
    ]
    if inconsistent:
        problems.append(
            f"{len(inconsistent)} rows violate sensitive==(loose and not strict) "
            "or would_flip==(price_ok and sensitive)"
        )
    blocked_flips = [r for r in flips if not r.price_ok]
    if blocked_flips:
        problems.append(
            f"{len(blocked_flips)} flip rows have price_ok=False — the price leg "
            "should have blocked them"
        )
    if problems:
        for p in problems:
            print(f"  ! {p}")
        return 1
    print("  consistent: sensitive/would_flip/price_ok relationships hold for "
          "every row")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Report SLOPE DIAG evidence for the min_slope tightening ladder."
    )
    parser.add_argument(
        "logs",
        nargs="*",
        help="log files to scan (default: auto-discover bot_profile*.log)",
    )
    parser.add_argument(
        "--target",
        type=int,
        default=DEFAULT_TARGET,
        help=f"would_flip rows needed before advancing a rung (default {DEFAULT_TARGET})",
    )
    parser.add_argument(
        "--no-dedupe",
        action="store_true",
        help="keep duplicate rows (the bot logs to two files)",
    )
    args = parser.parse_args(argv)

    files = args.logs or discover_logs()
    if not files:
        print("No log files found. Pass paths explicitly.", file=sys.stderr)
        return 2

    all_rows: List[DiagRow] = []
    total_lines = 0
    for path in files:
        rows, seen = parse_file(path)
        total_lines += seen
        all_rows.extend(rows)

    dropped = 0
    if not args.no_dedupe:
        all_rows, dropped = dedupe(all_rows)

    print(f"scanned {total_lines} lines across {len(files)} file(s); "
          f"{len(all_rows)} DIAG rows"
          + (f" ({dropped} duplicates dropped)" if dropped else ""))
    return report(all_rows, args.target, files)


if __name__ == "__main__":
    sys.exit(main())
