import subprocess
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from utils.logging_utils import get_logger

logger = get_logger(__name__)

_MAX_CAPTURED_OUTPUT = 2600
_MC_TIMEOUT_SECONDS = 180


def _output_text(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


def report_mc_refresh_error(
    profile_label,
    script_path,
    results_dir,
    send_telegram,
    now_utc=None,
):
    now_utc = now_utc or datetime.now(timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    else:
        now_utc = now_utc.astimezone(timezone.utc)

    script_path = Path(script_path)
    results_dir = Path(results_dir)
    timeframe = "D"
    utc_day = now_utc.strftime("%Y%m%d")
    expected_pattern = f"mc_{timeframe}_all_pairs_{utc_day}_*.json"
    london_now = now_utc.astimezone(ZoneInfo("Europe/London"))
    message = (
        f"🚨 FX BOT {profile_label}: MC {timeframe} bundle missing\n"
        f"UTC now: {now_utc:%Y-%m-%d %H:%M:%S}\n"
        f"Launcher: {script_path}\n"
        f"Expected: {results_dir / expected_pattern}"
    )

    if not script_path.is_file():
        diagnostic = f"MC launcher not found: {script_path}"
    elif (london_now.hour, london_now.minute) not in {(0, 0), (0, 5), (0, 10)}:
        diagnostic = (
            "Refresh not started: run_fx_mc.sh only runs at 00:00, 00:05, "
            "or 00:10 Europe/London. "
            f"Current London time: {london_now:%Y-%m-%d %H:%M:%S %Z}. "
            "Outside those slots the launcher exits without generating data; "
            "this is a missing bundle, not an MC computation error."
        )
    else:
        try:
            result = subprocess.run(
                ["bash", str(script_path)],
                cwd=str(script_path.parent),
                capture_output=True,
                text=True,
                timeout=_MC_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            captured = "\n".join(
                part
                for part in (
                    _output_text(exc.stdout).strip(),
                    _output_text(exc.stderr).strip(),
                )
                if part
            )
            diagnostic = (
                f"MC launcher timed out after {_MC_TIMEOUT_SECONDS} seconds."
            )
            if captured:
                diagnostic += f"\nCaptured output (tail):\n{captured[-_MAX_CAPTURED_OUTPUT:]}"
        except OSError as exc:
            diagnostic = f"Could not start MC launcher: {type(exc).__name__}: {exc}"
        else:
            captured = "\n".join(
                part
                for part in (
                    f"STDOUT:\n{result.stdout.strip()}" if result.stdout.strip() else "",
                    f"STDERR:\n{result.stderr.strip()}" if result.stderr.strip() else "",
                )
                if part
            )
            generated = sorted(results_dir.glob(expected_pattern))
            if result.returncode:
                diagnostic = f"MC launcher failed with exit code {result.returncode}."
            elif generated:
                diagnostic = f"MC launcher exited successfully; found {generated[-1].name}."
            else:
                diagnostic = (
                    "MC launcher exited with code 0 but produced no daily bundle "
                    f"matching {expected_pattern}."
                )
            if captured:
                diagnostic += f"\nCaptured output (tail):\n{captured[-_MAX_CAPTURED_OUTPUT:]}"
            else:
                diagnostic += "\nNo stdout/stderr was captured."

    message = f"{message}\n{diagnostic}\n🛑 This bot cycle is aborted; retry after the D bundle is available."
    logger.error("%s", message)
    send_telegram(message)
    return message
