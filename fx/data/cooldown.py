import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def load_cooldown(cooldown_file: Path, Direction):
    if cooldown_file.exists():
        with open(cooldown_file) as f:
            raw = json.load(f)
            return {k: (Direction(v[0]), v[1]) for k, v in raw.items()}
    return {}

def save_cooldown(cooldown_file: Path, state: dict):
    serializable = {k: (v[0].value, v[1]) for k, v in state.items()}
    with open(cooldown_file, "w") as f:
        json.dump(serializable, f)
