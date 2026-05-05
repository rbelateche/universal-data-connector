"""Smoke tests for the Settings config layer."""

import os

import pytest

from udc.core.config import Settings, get_settings


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost/test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    # Clear LRU cache so settings re-parse from env
    get_settings.cache_clear()

    settings = Settings(
        database_url="postgresql+asyncpg://user:pass@localhost/test",
        anthropic_api_key="sk-ant-test",
    )

    assert settings.duckdb_path == "./data/udc.duckdb"
    assert settings.log_level == "INFO"
    assert settings.app_env == "development"
    assert settings.api_key == "dev-secret"


def test_settings_required_fields_missing() -> None:
    with pytest.raises(Exception):
        Settings()  # type: ignore[call-arg]  — missing required fields


def test_settings_anthropic_model_default(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    settings = Settings(
        database_url="postgresql+asyncpg://user:pass@localhost/test",
        anthropic_api_key="sk-ant-test",
    )
    assert "claude" in settings.anthropic_model
