"""Tests for POST/GET /connectors router."""

from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from udc.api import dependencies
from udc.api.app import create_app
from udc.core.config import Settings, get_settings
from udc.core.connector_registry import ConnectorConfig

API_KEY = "test-secret"


def _make_cfg(
    id_: str = "abc-123",
    name: str = "my-pg",
    type_: str = "postgres",
) -> ConnectorConfig:
    return ConnectorConfig(id=id_, name=name, type=type_, config={"url": "pg://x", "table": "t"})


def _test_settings() -> Settings:
    return Settings(
        database_url="postgresql://x:x@localhost/x",
        anthropic_api_key="sk-test",
        api_key=API_KEY,
        duckdb_path=":memory:",
    )


@pytest.fixture(autouse=True)
def reset() -> Any:
    dependencies._reset_singletons()
    yield
    dependencies._reset_singletons()


@pytest.fixture
def client() -> TestClient:
    registry = MagicMock()
    registry.register.return_value = _make_cfg()
    registry.list_all.return_value = [_make_cfg()]
    registry.get.return_value = _make_cfg()

    app = create_app()
    app.dependency_overrides[get_settings] = _test_settings
    app.dependency_overrides[dependencies.get_connector_registry] = lambda: registry
    return TestClient(app)


def test_register_connector_returns_201(client: TestClient) -> None:
    resp = client.post(
        "/connectors",
        json={"name": "my-pg", "type": "postgres", "config": {"url": "pg://x", "table": "t"}},
        headers={"X-Api-Key": API_KEY},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"] == "abc-123"
    assert data["type"] == "postgres"


def test_list_connectors_returns_200(client: TestClient) -> None:
    resp = client.get("/connectors", headers={"X-Api-Key": API_KEY})
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_get_connector_by_id(client: TestClient) -> None:
    resp = client.get("/connectors/abc-123", headers={"X-Api-Key": API_KEY})
    assert resp.status_code == 200
    assert resp.json()["name"] == "my-pg"


def test_register_unknown_type_returns_422(client: TestClient) -> None:
    registry = MagicMock()
    registry.register.side_effect = ValueError("Unknown connector type 'mysql'")
    client.app.dependency_overrides[dependencies.get_connector_registry] = lambda: registry

    resp = client.post(
        "/connectors",
        json={"name": "x", "type": "mysql", "config": {}},
        headers={"X-Api-Key": API_KEY},
    )
    assert resp.status_code == 422


def test_get_missing_connector_returns_404(client: TestClient) -> None:
    registry = MagicMock()
    registry.get.side_effect = KeyError("Connector 'xyz' not found.")
    client.app.dependency_overrides[dependencies.get_connector_registry] = lambda: registry

    resp = client.get("/connectors/xyz", headers={"X-Api-Key": API_KEY})
    assert resp.status_code == 404


def test_missing_api_key_returns_401(client: TestClient) -> None:
    resp = client.get("/connectors")
    assert resp.status_code == 401


def test_wrong_api_key_returns_401(client: TestClient) -> None:
    resp = client.get("/connectors", headers={"X-Api-Key": "wrong"})
    assert resp.status_code == 401
