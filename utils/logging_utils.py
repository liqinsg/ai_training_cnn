# utils/logger_config.py
import logging
import sys
from pathlib import Path
from datetime import datetime
from datetime import timezone

# ─── Log Directory ───
LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / f"fx_bot_{datetime.now(timezone.utc).strftime('%Y%m%d')}.log"

# ─── Format ───
LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S UTC"

# ─── Initialize ───
logger = logging.getLogger("fx_bot")
logger.setLevel(logging.DEBUG)
logger.propagate = False  # Prevent duplicate output

# ─── File Handler ───
file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
file_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
file_handler.setLevel(logging.DEBUG)

# ─── Console Handler ───
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
console_handler.setLevel(logging.INFO)

# ─── Attach ───
logger.addHandler(file_handler)
logger.addHandler(console_handler)

def get_logger(name: str = None) -> logging.Logger:
    """Get a shared logger — use in every .py file"""
    return logging.getLogger(name or "fx_bot")