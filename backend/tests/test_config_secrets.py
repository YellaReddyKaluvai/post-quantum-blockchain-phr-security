"""No secret that ships in this repository is ever used as one.

The session-signing key, the consent-ledger key and the first administrator's
password all had published defaults. With the signing key anyone could mint an
Administrator token, so a placeholder is now replaced by a generated key.
"""

import pytest

from app import config


@pytest.fixture
def fresh_settings(monkeypatch, tmp_path):
    """get_settings() rebuilt against a scratch key directory, then restored."""
    monkeypatch.setattr(config, "_SECRET_KEY_FILE", tmp_path / ".secret_key")
    monkeypatch.setattr(config, "_LEDGER_KEY_FILE", tmp_path / ".ledger_key")
    monkeypatch.setattr(config, "_GENERATED", set())
    config.get_settings.cache_clear()
    yield monkeypatch
    config.get_settings.cache_clear()


@pytest.mark.parametrize("value", ["change-me-in-production", "replace-with-a-long-random-string",
                                   "", "short-key"])
def test_a_placeholder_or_short_signing_key_is_replaced(fresh_settings, value):
    settings = config.Settings(SECRET_KEY=value)
    fresh_settings.setattr(config, "Settings", lambda: settings)
    s = config.get_settings()
    assert s.SECRET_KEY != value and len(s.SECRET_KEY) >= config.MIN_SECRET_KEY_LENGTH
    assert config._SECRET_KEY_FILE.read_text().strip() == s.SECRET_KEY
    assert any("SECRET_KEY" in w for w in config.configuration_warnings(s))


def test_a_strong_signing_key_is_kept(fresh_settings):
    strong = "k" * 48
    settings = config.Settings(SECRET_KEY=strong, CONSENT_LEDGER_KEY="l" * 48)
    fresh_settings.setattr(config, "Settings", lambda: settings)
    s = config.get_settings()
    assert s.SECRET_KEY == strong and s.CONSENT_LEDGER_KEY == "l" * 48
    assert not config._SECRET_KEY_FILE.exists()
    assert not any("SECRET_KEY" in w for w in config.configuration_warnings(s))


def test_a_generated_key_is_stable_across_restarts(tmp_path):
    path = tmp_path / ".secret_key"
    first = config._generated_secret_key(path)
    assert config._generated_secret_key(path) == first


def test_a_corrupt_key_file_is_refused_not_trusted(tmp_path):
    path = tmp_path / ".secret_key"
    path.write_text("too-short")
    with pytest.raises(RuntimeError):
        config._generated_secret_key(path)


def test_the_public_example_encryption_key_is_reported():
    s = config.Settings(ENCRYPTION_KEY="0123456789abcdef0123456789abcdef")
    assert any("public example key" in w for w in config.configuration_warnings(s))


def test_no_administrator_password_ships_as_a_default():
    assert config.Settings(ADMIN_PASSWORD="").ADMIN_PASSWORD == ""
    assert "Admin@1234" in config._PUBLIC_ADMIN_PASSWORDS


def test_consent_references_do_not_depend_on_the_session_key(monkeypatch):
    from app import consent_ledger

    class S:
        SECRET_KEY = "a" * 48
        CONSENT_LEDGER_KEY = "b" * 48

    monkeypatch.setattr(consent_ledger, "get_settings", lambda: S)
    before = consent_ledger.party_ref("user-1")
    S.SECRET_KEY = "rotated" * 8
    assert consent_ledger.party_ref("user-1") == before
