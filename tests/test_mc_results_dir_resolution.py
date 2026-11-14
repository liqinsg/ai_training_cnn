from pathlib import Path
import sys

import config_bot

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from fx_trade_bot_utils_v1 import get_mc_results_dir


def test_relative_config_path_falls_back_to_existing_absolute_mc_dir(
    tmp_path, monkeypatch
):
    fake_home = tmp_path / "home"
    fallback_dir = fake_home / "projects" / "fx_monte_carlo" / "mc_results"
    fallback_dir.mkdir(parents=True)

    repo_cwd = tmp_path / "repo"
    repo_cwd.mkdir()

    monkeypatch.chdir(repo_cwd)
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.delenv("MC_RESULTS_DIR", raising=False)
    monkeypatch.setattr(
        config_bot,
        "GLOBAL",
        {"monte_carlo": {"MC_RESULTS_DIR": "mc_results"}},
        raising=False,
    )

    assert get_mc_results_dir() == fallback_dir.resolve()
