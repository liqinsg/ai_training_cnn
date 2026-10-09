"""
profile_logger.py — Independent JSONL logger per profile
- Separate directory per profile: logs/pf-a/, pf-b/, etc.
- Daily file: YYYY-MM-DD.jsonl
- Append-only, flush after write
- No shared locks, no cross-contamination
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

# Base directory — relative to project root
LOGS_ROOT = Path(__file__).parent / "logs"


class ProfileLogger:
    """Write JSONL records to profile-specific daily log file."""

    def __init__(self, profile_id: str, logs_root: Optional[Path] = None):
        self.profile_id = profile_id.lower()
        self.logs_root = Path(logs_root) if logs_root else LOGS_ROOT
        self._ensure_dir()

    def _ensure_dir(self) -> Path:
        """Create profile directory if missing. Returns path."""
        dir_path = self.logs_root / self.profile_id
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path

    def _get_file_path(self, date_str: Optional[str] = None) -> Path:
        """Return path for today's (or specified date's) log file."""
        if date_str is None:
            date_str = datetime.utcnow().strftime("%Y-%m-%d")
        return self._ensure_dir() / f"{date_str}.jsonl"

    def write(self, record: Dict[str, Any], date_str: Optional[str] = None) -> int:
        """
        Append one JSON record to file. Flush immediately.
        Returns bytes written.
        """
        file_path = self._get_file_path(date_str)
        line = json.dumps(record, ensure_ascii=False) + "\n"
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
        return len(line.encode("utf-8"))

    def read_tail(self, n: int = 5, date_str: Optional[str] = None) -> list:
        """Read last N records from today's file (for verification)."""
        file_path = self._get_file_path(date_str)
        if not file_path.exists():
            return []
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        return [json.loads(line) for line in lines[-n:]]


def write_all(records: Dict[str, Dict[str, Any]], date_str: Optional[str] = None) -> Dict[str, int]:
    """
    Write all 4 records in one call.
    records: {'PF-A': rec, 'PF-B': rec, ...}
    Returns bytes written per profile.
    """
    results = {}
    for profile_id, record in records.items():
        logger = ProfileLogger(profile_id)
        results[profile_id] = logger.write(record, date_str)
    return results


def clear_all_logs() -> None:
    """Delete all log files (for test cleanup only)."""
    import shutil
    if LOGS_ROOT.exists():
        shutil.rmtree(LOGS_ROOT)
        LOGS_ROOT.mkdir(parents=True, exist_ok=True)