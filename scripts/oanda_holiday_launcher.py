#!/usr/bin/env python3
"""Skip a scheduled command during OANDA holiday trading-hour exceptions.

The launcher treats any product-specific holiday exception on OANDA's page as
a global pause for the wrapped command. It refreshes the source every six hours,
uses a seven-day-old cache at most, and fails closed if no readable schedule is
available. Times on the page are Eastern Time.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta
from html.parser import HTMLParser
from pathlib import Path
import re
import subprocess
import sys
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


URL = "https://www.oanda.com/bvi-en/cfds/holiday-trading-hours/"
ET = ZoneInfo("America/New_York")
DATE_RE = re.compile(r"\b(\d{1,2})\s+([A-Za-z]+)\s+(20\d{2})\b")
TIME_RE = re.compile(r"\b(\d{1,2}):(\d{2})(?:\s*(AM|PM))?\s*(?:ET)?\b", re.I)
BLOCK_TAGS = {
    "address", "article", "br", "dd", "div", "dt", "h1", "h2", "h3",
    "h4", "h5", "h6", "li", "ol", "p", "section", "tr", "ul",
}


class PageText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.ignored = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self.ignored += 1
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self.ignored:
            self.ignored -= 1
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.ignored:
            self.parts.append(data)


def _read_page(cache_path: Path, refresh_hours: float, max_stale_days: float) -> str:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    age = float("inf")
    if cache_path.exists():
        age = (datetime.now().timestamp() - cache_path.stat().st_mtime) / 3600
    if age <= refresh_hours:
        return cache_path.read_text(encoding="utf-8")
    try:
        request = Request(URL, headers={"User-Agent": "Mozilla/5.0 OANDA-hours-check/1.0"})
        with urlopen(request, timeout=15) as response:
            raw = response.read()
        html = raw.decode("utf-8", errors="replace")
        parser = PageText()
        parser.feed(html)
        page_text = "\n".join(parser.parts)
        if not DATE_RE.search(page_text):
            raise ValueError("OANDA page contained no recognizable dated schedule")
        cache_path.write_text(html, encoding="utf-8")
        return html
    except Exception as exc:
        if cache_path.exists() and age <= max_stale_days * 24:
            print(f"holiday launcher: fetch failed; using cached page ({exc})", file=sys.stderr)
            return cache_path.read_text(encoding="utf-8")
        raise RuntimeError(f"OANDA holiday page unavailable or cache expired: {exc}") from exc


def _to_minutes(match: re.Match[str]) -> int:
    hour, minute = int(match.group(1)), int(match.group(2))
    meridiem = (match.group(3) or "").upper()
    if minute > 59 or hour > (12 if meridiem else 23):
        raise ValueError("invalid time")
    if meridiem:
        if hour < 1:
            raise ValueError("invalid 12-hour time")
        hour %= 12
        if meridiem == "PM":
            hour += 12
    return hour * 60 + minute


def _date_from_line(line: str, year_hint: int | None) -> date | None:
    match = DATE_RE.search(line)
    if match:
        try:
            return datetime.strptime(
                f"{match.group(1)} {match.group(2)} {match.group(3)}", "%d %B %Y"
            ).date()
        except ValueError:
            return None
    return None


def _day_intervals(day: date, text: str) -> list[tuple[datetime, datetime, str]]:
    """Convert one page bullet to conservative ET pause intervals."""
    lowered = text.lower()
    if "regular trading hours" in lowered or not any(
        word in lowered for word in ("close", "closed", "open", "reopen")
    ):
        return []
    matches = list(TIME_RE.finditer(text))
    minutes: list[int] = []
    for match in matches:
        try:
            minutes.append(_to_minutes(match))
        except ValueError:
            continue

    midnight = datetime.combine(day, time.min, ET)
    end_day = midnight + timedelta(days=1)
    intervals: list[tuple[datetime, datetime, str]] = []
    if "closed" in lowered and not minutes:
        return [(midnight, end_day, text.strip())]

    if "reopen" in lowered or "reopening" in lowered:
        if len(minutes) >= 2:
            start, finish = minutes[0], minutes[1]
            end = midnight + timedelta(minutes=finish)
            if finish <= start:
                end += timedelta(days=1)
            return [(midnight + timedelta(minutes=start), end, text.strip())]
        if minutes:
            return [(midnight, midnight + timedelta(minutes=minutes[-1]), text.strip())]
        return [(midnight, end_day, text.strip())]

    if "closed" in lowered or "late open" in lowered or "open late" in lowered:
        if not minutes:
            return [(midnight, end_day, text.strip())]
        intervals.append((midnight, midnight + timedelta(minutes=minutes[0]), text.strip()))
        if "close" in lowered and len(minutes) > 1:
            intervals.append((midnight + timedelta(minutes=minutes[-1]), end_day, text.strip()))
        return [item for item in intervals if item[0] < item[1]]

    if "open" in lowered and "close" in lowered and len(minutes) >= 2:
        intervals.extend(
            [
                (midnight, midnight + timedelta(minutes=minutes[0]), text.strip()),
                (midnight + timedelta(minutes=minutes[-1]), end_day, text.strip()),
            ]
        )
        return [item for item in intervals if item[0] < item[1]]

    if "open" in lowered and minutes:
        return [(midnight, midnight + timedelta(minutes=minutes[0]), text.strip())]
    if ("close" in lowered or "early close" in lowered) and minutes:
        return [(midnight + timedelta(minutes=minutes[0]), end_day, text.strip())]
    return [(midnight, end_day, text.strip())]


def schedule_intervals(html: str, now: datetime) -> list[tuple[datetime, datetime, str]]:
    parser = PageText()
    parser.feed(html)
    lines = [re.sub(r"\s+", " ", line).strip(" \t:-") for line in "\n".join(parser.parts).splitlines()]
    lines = [line for line in lines if line]
    dated: list[tuple[date, str]] = []
    year_hint: int | None = None
    for line in lines:
        if re.fullmatch(r"20\d{2}", line):
            year_hint = int(line)
        day = _date_from_line(line, year_hint)
        if day:
            dated.append((day, line))

    intervals: list[tuple[datetime, datetime, str]] = []
    if not dated:
        return intervals
    for index, (day, header) in enumerate(dated):
        start = lines.index(header) + 1 if header in lines else 0
        next_header = dated[index + 1][1] if index + 1 < len(dated) else None
        end = lines.index(next_header, start) if next_header in lines and next_header in lines[start:] else len(lines)
        section = lines[start:end]
        # A holiday title may itself carry a product and a time; process it as well.
        if any(word in header.lower() for word in ("open", "close", "closed", "reopen")):
            section.insert(0, header)
        for bullet in section:
            if any(word in bullet.lower() for word in ("open", "close", "closed", "reopen")):
                intervals.extend(_day_intervals(day, bullet))
    return intervals


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", default="logs/oanda_holiday_hours.html")
    parser.add_argument("--refresh-hours", type=float, default=6)
    parser.add_argument("--max-stale-days", type=float, default=7)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    try:
        html = _read_page(Path(args.cache), args.refresh_hours, args.max_stale_days)
        now = datetime.now(ET)
        intervals = schedule_intervals(html, now)
        if not intervals:
            raise RuntimeError("no holiday windows could be parsed; refusing to launch")
    except Exception as exc:
        print(f"holiday launcher: FAIL CLOSED — {exc}", file=sys.stderr)
        return 0 if args.check_only else 75

    active = [item for item in intervals if item[0] <= now < item[1]]
    if active:
        reasons = "; ".join(sorted({item[2] for item in active}))
        until = max(item[1] for item in active)
        print(
            f"holiday launcher: SKIP {now.isoformat(timespec='minutes')} ET; "
            f"window ends {until.isoformat(timespec='minutes')} ET; {reasons}"
        )
        return 0

    if args.check_only:
        print(f"holiday launcher: ALLOW {now.isoformat(timespec='minutes')} ET")
        return 0
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("supply a command after --, or use --check-only")
    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
