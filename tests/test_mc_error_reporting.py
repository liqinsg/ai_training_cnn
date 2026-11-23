from datetime import datetime, timezone
from pathlib import Path
import subprocess

from utils import mc_error_reporting


def test_missing_bundle_before_mc_schedule_sends_clear_diagnostic(
    tmp_path, monkeypatch
):
    launcher = tmp_path / "run_fx_mc.sh"
    launcher.touch()
    results_dir = tmp_path / "mc_results"
    results_dir.mkdir()
    messages = []

    def unexpected_run(*args, **kwargs):
        raise AssertionError("launcher should not run outside its scheduled window")

    monkeypatch.setattr(mc_error_reporting.subprocess, "run", unexpected_run)

    message = mc_error_reporting.report_mc_refresh_error(
        "PF-A",
        launcher,
        results_dir,
        messages.append,
        now_utc=datetime(2026, 11, 23, 23, 45, tzinfo=timezone.utc),
    )

    assert message == messages[0]
    assert "Expected:" in message
    assert "20261123" in message
    assert "00:00, 00:05, or 00:10 Europe/London" in message
    assert "not an MC computation error" in message


def test_due_mc_failure_includes_captured_error_in_telegram_message(
    tmp_path, monkeypatch
):
    launcher = tmp_path / "run_fx_mc.sh"
    launcher.touch()
    results_dir = tmp_path / "mc_results"
    results_dir.mkdir()
    messages = []
    monkeypatch.setattr(
        mc_error_reporting.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 1, stdout="starting daily run", stderr="market data request failed"
        ),
    )

    message = mc_error_reporting.report_mc_refresh_error(
        "PF-A",
        launcher,
        results_dir,
        messages.append,
        now_utc=datetime(2026, 11, 23, 0, 0, tzinfo=timezone.utc),
    )

    assert message == messages[0]
    assert "exit code 1" in message
    assert "market data request failed" in message
    assert "starting daily run" in message
