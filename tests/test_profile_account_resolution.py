import pytest

import config_bot


def test_profile1_is_bound_to_account_one():
    profile = config_bot.get_profile(1)

    assert profile["account_id_demo"] == "101-003-39389016-001"
    assert profile["account_id_live"] == "001-003-21515688-001"


def test_profile4_is_bound_to_account_four():
    profile = config_bot.get_profile(4)

    assert profile["account_id_demo"] == "101-003-39389016-004"
    assert profile["account_id_live"] == "001-003-21515688-004"


@pytest.mark.parametrize(
    ("profile_id", "live", "key"),
    [
        (1, False, "account_id_demo"),
        (1, True, "account_id_live"),
        (2, False, "account_id_demo"),
        (2, True, "account_id_live"),
        (3, False, "account_id_demo"),
        (3, True, "account_id_live"),
        (4, False, "account_id_demo"),
        (4, True, "account_id_live"),
    ],
)
def test_profile_account_resolution_uses_profile_binding(profile_id, live, key):
    expected = config_bot.get_profile(profile_id)[key]

    account_id, source = config_bot.resolve_account_id(profile_id, live)

    assert account_id == expected
    assert source == "Profile内置"


@pytest.mark.parametrize("live", [False, True])
def test_explicit_account_override_wins(live):
    profile_id = 1
    override_id = "explicit-account"
    account_map = {2: override_id}

    account_id, source = config_bot.resolve_account_id(
        profile_id, live, account_override=2, indexed_accounts=account_map
    )

    assert account_id == override_id
    assert source == "-a 2"


def test_missing_profile_account_fails_without_fallback(monkeypatch):
    profiles = {
        key: dict(profile) for key, profile in config_bot.PROFILES.items()
    }
    profiles["1"].pop("account_id_demo")
    monkeypatch.setattr(config_bot, "PROFILES", profiles)

    with pytest.raises(ValueError, match="Profile 1 is missing a valid account_id_demo"):
        config_bot.resolve_account_id(1, live=False)


def test_invalid_explicit_account_fails():
    with pytest.raises(ValueError, match="No DEMO account configured for -a 5"):
        config_bot.resolve_account_id(
            1, live=False, account_override=5, indexed_accounts={2: "account"}
        )
