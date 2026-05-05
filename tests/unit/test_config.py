"""Smoke tests for the Settings config layer."""

import pytest

from udc.core.config import Settings, get_settings

_REQUIRED = {
    "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/test",
    "ANTHROPIC_API_KEY": "sk-ant-test",
}


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, val in _REQUIRED.items():
        monkeypatch.setenv(key, val)
    # Remove any CI-injected overrides so we test the true defaults
    monkeypatch.delenv("DUCKDB_PATH", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("API_KEY", raising=False)
    get_settings.cache_clear()

    settings = Settings()  # type: ignore[call-arg]

    assert settings.duckdb_path == "./data/udc.duckdb"
    assert settings.log_level == "INFO"
    assert settings.app_env == "development"
    assert settings.api_key == "dev-secret"


def test_settings_required_fields_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    # Scrub all env vars that would satisfy the required fields
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    get_settings.cache_clear()

    with pytest.raises(Exception):
        Settings()  # type: ignore[call-arg]


def test_settings_anthropic_model_default(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, val in _REQUIRED.items():
        monkeypatch.setenv(key, val)
    get_settings.cache_clear()

    settings = Settings()  # type: ignore[call-arg]

    assert "claude" in settings.anthropic_model
