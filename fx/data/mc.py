import json
import logging
from pathlib import Path
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

def load_mc_legacy(
    pair: str, results_dir: Path, today_str: str, max_age_hours: int = 24
):
    safe = pair.replace("=X", "").replace("=", "_")
    for f in [
        results_dir / f"fx_daily_{safe}_{today_str}.json",
        results_dir / f"daily_mc_{safe}_{today_str}.json",
        results_dir / f"h4_mc_{safe}_{today_str}.json",
    ]:
        if f.exists():
            age = (
                datetime.now(timezone.utc)
                - datetime.fromtimestamp(f.stat().st_mtime, timezone.utc)
            ).total_seconds() / 3600
            if age <= max_age_hours:
                with open(f) as j:
                    return json.load(j), True
    return None, False
