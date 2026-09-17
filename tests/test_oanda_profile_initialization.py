"""Offline configuration tests; never import or execute the trading loop."""

import argparse
import ast
import importlib.util
import json
import logging
from pathlib import Path
import sys
from unittest.mock import Mock

import dotenv
import oandapyV20
import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
ENVIRONMENTS = {"1": "live", "2": "live", "3": "practice", "4": "live"}


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def configs(monkeypatch):
    # Do not read real credentials or allow any OANDA requests, including reads.
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **kw: False)
    monkeypatch.setenv("OANDA_ENV", "practice")
    monkeypatch.setenv("OANDA_API_TOKEN_DEMO", "test-practice-token")
    monkeypatch.setenv("OANDA_API_TOKEN_LIVE", "test-live-token")
    for num in ENVIRONMENTS:
        monkeypatch.setenv(f"OANDA_ACCOUNT_ID_DEMO_{num}", f"101-000-00000000-00{num}")
        monkeypatch.setenv(f"OANDA_ACCOUNT_ID_{num}_LIVE", f"001-000-00000000-00{num}")
    monkeypatch.setattr(
        oandapyV20.API, "request",
        Mock(side_effect=AssertionError("OANDA requests forbidden during initialization")),
    )
    monkeypatch.chdir(ROOT)
    return load_module("config_bot_v7"), load_module("config_oanda")


@pytest.mark.parametrize("num", ENVIRONMENTS)
def test_profile_ownership_and_selection(configs, num):
    bot, oanda = configs
    profile = bot.load_profile(f"profile{num}")
    ctx = oanda.get_oanda_profile(profile_num=num)
    bindings = yaml.safe_load((ROOT / "config_bot_v7.yml").read_text())["profiles"]
    params = json.loads((ROOT / "profiles_all.json").read_text())
    assert profile["strategy"] == params[bindings[f"profile{num}"]["param_set"]]
    assert not {"account_id", "mode", "OANDA_ACCOUNT_ID", "api", "token"} & profile.keys()
    assert all("OANDA_ACCOUNT_ID" not in p for p in bot.PROFILE_CFG.values())
    assert "config_oanda" not in vars(bot)
    assert ctx["env"] == ENVIRONMENTS[num]
    assert ctx["is_live"] == (ctx["env"] == "live")
    assert ctx["account_id"].endswith(f"-00{num}")
    assert ctx["account_ids"] == [ctx["account_id"]]
    assert isinstance(ctx["api"], oandapyV20.API)
    assert ctx["api"].environment == ctx["env"]
    assert ctx["api"].access_token == f"test-{ctx['env']}-token"


@pytest.mark.parametrize("num", ENVIRONMENTS)
@pytest.mark.parametrize("override", ["001", "002", "003", "004", "101-000-00000000-099"])
def test_account_override_preserves_connection(configs, num, override):
    _, oanda = configs
    ctx = oanda.get_oanda_profile(profile_num=num, account_override=override)
    assert ctx["env"] == ENVIRONMENTS[num]
    assert ctx["api"].access_token == f"test-{ctx['env']}-token"
    if len(override) == 3:
        prefix = "001" if ctx["is_live"] else "101"
        assert ctx["account_id"] == f"{prefix}-000-00000000-{override}"
    else:
        assert ctx["account_id"] == override


@pytest.mark.parametrize("num", ENVIRONMENTS)
@pytest.mark.parametrize("env", ["practice", "live"])
def test_environment_override_and_cwd_independence(configs, monkeypatch, tmp_path, num, env):
    _, oanda = configs
    monkeypatch.chdir(tmp_path)
    ctx = oanda.get_oanda_profile(profile_num=num, env_override=env)
    assert ctx["env"] == env
    assert ctx["api"].access_token == f"test-{env}-token"
    assert ctx["account_id"].startswith("001" if env == "live" else "101")


def startup_namespace(configs, monkeypatch, argv):
    """Execute the actual CLI/init statements, stopping before audit/trading code.

    Heavy runtime imports are intentionally excluded. Configuration modules and
    OANDA API construction are real, with synthetic credentials and no requests.
    """
    bot, oanda = configs
    source = ROOT / "fx_trade_bot_v71.py"
    tree = ast.parse(source.read_text())
    start = next(i for i, node in enumerate(tree.body)
                 if isinstance(node, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == "parser" for t in node.targets))
    end = next(i for i, node in enumerate(tree.body)
               if isinstance(node, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == "TODAY_STR" for t in node.targets))
    namespace = {
        "__file__": str(source), "argparse": argparse, "Path": Path,
        "load_profile": bot.load_profile, "cfg": bot.cfg,
        "get_oanda_profile": oanda.get_oanda_profile,
        "logger": logging.getLogger("test_oanda_init"),
        "send_telegram_message": Mock(side_effect=AssertionError("No Telegram calls")),
    }
    monkeypatch.setattr(sys, "argv", [str(source), *argv])
    monkeypatch.setattr(Path, "mkdir", Mock())  # Never touch runtime state directories.
    exec(compile(ast.Module(body=tree.body[start:end], type_ignores=[]), str(source), "exec"), namespace)
    return namespace


@pytest.mark.parametrize("num", ENVIRONMENTS)
@pytest.mark.parametrize("override", [None, "002", "101-000-00000000-099"])
def test_actual_cli_initialization(configs, monkeypatch, capsys, num, override):
    argv = ["-p", num]
    if override:
        argv += ["--account", override]
    ns = startup_namespace(configs, monkeypatch, argv)
    assert ns["PROFILE_NAME"] == f"profile{num}"
    assert ns["api"] is ns["oanda_ctx"]["api"]
    assert ns["OANDA_ACCOUNT_ID"] == ns["oanda_ctx"]["account_id"]
    assert ns["IS_LIVE"] == (ENVIRONMENTS[num] == "live")
    assert ns["ACCOUNT_NAME"] == ns["P"]["account_alias"]
    assert ns["COOLDOWN_FILE"] == ns["S"]["COOLDOWN_FILE"]
    assert ns["RESULTS_DIR"] == Path(ns["S"]["RESULTS_DIR"])
    assert ns["BASE_DIR"] == ROOT
    output = capsys.readouterr().out
    assert f"OANDA environment: {ENVIRONMENTS[num]}" in output
    assert "OANDA api: initialized" in output
    assert "test-practice-token" not in output
    assert "test-live-token" not in output


def test_missing_token_fails_before_runtime(configs, monkeypatch, capsys):
    _, oanda = configs
    monkeypatch.setattr(oanda, "OANDA_API_TOKEN_DEMO", "")
    with pytest.raises(SystemExit) as exc:
        startup_namespace(configs, monkeypatch, ["-p", "3"])
    assert exc.value.code == 2
    assert "missing token for practice" in capsys.readouterr().err


def test_default_context_compatibility(configs):
    _, oanda = configs
    ctx = oanda.get_oanda_profile()
    assert ctx["env"] == "practice"
    assert len(ctx["account_ids"]) == 4
    assert oanda.api is oanda.default_profile["api"]


def test_unconfigured_profile_is_not_invented(configs):
    bot, oanda = configs
    with pytest.raises(ValueError, match="not defined"):
        bot.load_profile("profile9")
    with pytest.raises(ValueError, match="not configured"):
        oanda.get_oanda_profile(profile_num="9")