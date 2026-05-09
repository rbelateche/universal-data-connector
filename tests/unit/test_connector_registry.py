"""Tests for ConnectorRegistry."""

import pytest

from udc.core.connector_registry import ConnectorRegistry


@pytest.fixture
def registry(tmp_path: pytest.TempPathFactory) -> ConnectorRegistry:
    return ConnectorRegistry(str(tmp_path / "test.duckdb"))  # type: ignore[arg-type]


def test_register_returns_config_with_id(registry: ConnectorRegistry) -> None:
    cfg = registry.register("pg-crm", "postgres", {"url": "pg://...", "table": "customers"})
    assert cfg.id is not None
    assert len(cfg.id) == 36  # UUID length
    assert cfg.name == "pg-crm"
    assert cfg.type == "postgres"
    assert cfg.config["table"] == "customers"


def test_get_roundtrips_config(registry: ConnectorRegistry) -> None:
    cfg = registry.register("my-csv", "csv", {"path": "/tmp/data.csv"})
    loaded = registry.get(cfg.id)
    assert loaded.id == cfg.id
    assert loaded.name == "my-csv"
    assert loaded.config == {"path": "/tmp/data.csv"}


def test_unknown_type_raises_value_error(registry: ConnectorRegistry) -> None:
    with pytest.raises(ValueError, match="Unknown connector type"):
        registry.register("bad", "mysql", {})


def test_get_missing_raises_key_error(registry: ConnectorRegistry) -> None:
    with pytest.raises(KeyError, match="not found"):
        registry.get("00000000-0000-0000-0000-000000000000")


def test_list_all_empty(registry: ConnectorRegistry) -> None:
    assert registry.list_all() == []


def test_list_all_multiple(registry: ConnectorRegistry) -> None:
    registry.register("a", "csv", {"path": "/a.csv"})
    registry.register("b", "json_api", {"base_url": "http://x", "endpoint": "/y"})
    all_ = registry.list_all()
    assert len(all_) == 2
    assert {c.name for c in all_} == {"a", "b"}
