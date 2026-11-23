"""
ML artifact health alerting.

The actual artifact checks (path integrity, staleness, feature-dimension
consistency) are performed by ``ensure_model()`` in ``fx_trade_bot_ml.py`` and
returned as a structured ``ModelInitResult``.  This module only translates that
result into a user-facing Telegram alert.

Design
------
* READY   → log only (no Telegram) — the bot runs every 15 min, so a success
  message on every cycle would be pure spam.
* Failure → Telegram alert, throttled to once per cooldown window per reason
  (a stale model must not generate 96 messages/day).
* Throttle state is persisted to a JSON file so it survives across cron cycles.
"""
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from utils.logging_utils import get_logger
from telegram_message import send_telegram_message

logger = get_logger(__name__)

# One alert per reason per cooldown window.  Bot cron is */15, so 1h = 4 cycles.
_ALERT_COOLDOWN_SECONDS = int(os.environ.get("ML_ALERT_COOLDOWN_SECONDS", "3600"))
_STATE_FILE = Path(__file__).resolve().parent.parent / "ml_alert_state.json"

# ModelReason → (short alert label, recommended user action)
_REASON_GUIDANCE = {
    "MODEL_MISSING": (
        "ML ARTIFACT MISSING",
        "Verify FX_BOT_MODEL_STEM env var matches the retrain output path",
    ),
    "MODEL_STALE": (
        "ML MODEL STALE",
        "Trigger the scheduled retrain — the model has expired",
    ),
    "FEATURE_CONTRACT_MISMATCH": (
        "ML FEATURE MISMATCH",
        "Retrain — scaler/model/feature-list are out of sync; check "
        "OPT_USE_FEATURE_CONTRACT_V2",
    ),
    "SCALER_MISSING": (
        "ML SCALER MISSING",
        "Retrain — scaler.joblib is absent from the artifact set",
    ),
    "MODEL_INCOMPATIBLE": (
        "ML MODEL INCOMPATIBLE",
        "Artifact version mismatch — retrain with the current codebase",
    ),
    "MODEL_LOAD_EXCEPTION": (
        "ML LOAD FAILED",
        "Inspect the bot log for the load-exception detail",
    ),
    "LEGACY_FALLBACK_BLOCKED": (
        "LEGACY FALLBACK BLOCKED",
        "Migrate the legacy .pkl bundle to split artifacts (offline retrain)",
    ),
    "MODEL_VALIDATION_FAILED": (
        "ML VALIDATION FAILED",
        "Artifact failed post-load validation — retrain",
    ),
    "LIVE_TRAINING_BLOCKED": (
        "LIVE TRAINING BLOCKED",
        "Live runtime cannot train — publish artifacts via retrain_model.py",
    ),
    "UNKNOWN_LOAD_FAILURE": (
        "ML UNKNOWN LOAD FAILURE",
        "Inspect the bot log for the load-failure detail",
    ),
}


def _load_state() -> dict:
    try:
        if _STATE_FILE.exists():
            return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_state(state: dict) -> None:
    try:
        _STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning("could not persist ml alert state: %s", e)


def _should_alert(reason: str) -> bool:
    """Return True if the cooldown since the last alert for ``reason`` elapsed."""
    now = time.time()
    state = _load_state()
    last = float(state.get(reason, 0) or 0)
    if now - last < _ALERT_COOLDOWN_SECONDS:
        return False
    state[reason] = now
    _save_state(state)
    return True


def report_ml_init_result(profile_label: str, ml_init: Any) -> None:
    """Send a Telegram alert when ``ml_init`` is not READY; throttled per reason.

    Args:
        profile_label: human-readable profile label (e.g. ``PROFILE_LABEL``).
        ml_init: ``ModelInitResult`` returned by ``ensure_model()``.
    """
    if getattr(ml_init, "ok", False):
        logger.info(
            "[%s] ML READY | reason=%s | path=%s",
            profile_label,
            getattr(ml_init, "reason", "?"),
            getattr(ml_init, "artifact_path", "?"),
        )
        return

    reason = getattr(ml_init, "reason", None) or "UNKNOWN"
    label, action = _REASON_GUIDANCE.get(
        reason, (f"ML {reason}", "Inspect the bot log for details")
    )
    now_local = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not _should_alert(reason):
        logger.info(
            "[%s] ML %s — alert throttled (cooldown %ds)",
            profile_label,
            reason,
            _ALERT_COOLDOWN_SECONDS,
        )
        return

    msg_lines = [
        f"🔴 {profile_label}: {label}",
        f"Time: {now_local}",
        f"Status: {getattr(ml_init, 'status', '?')}",
        f"Reason: {reason}",
    ]
    artifact_path = getattr(ml_init, "artifact_path", None)
    if artifact_path:
        msg_lines.append(f"Path: {artifact_path}")
    detail = getattr(ml_init, "detail", "")
    if detail:
        msg_lines.append(f"Detail: {detail}")
    msg_lines.append(f"Action: {action}")

    msg = "\n".join(msg_lines)
    logger.warning("[%s] %s", profile_label, msg)

    try:
        send_telegram_message(msg)
    except Exception as e:
        logger.error("[%s] Failed to send ML alert to Telegram: %s", profile_label, e)
