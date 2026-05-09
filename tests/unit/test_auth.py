"""Tests for API key authentication across all protected routes."""

from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from udc.api import dependencies
from udc.api.app import create_app
from udc.core.config import Settings, get_settings

API_KEY = "super-secret"


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
    registry.list_all.return_value = []

    app = create_app()
    app.dependency_overrides[get_settings] = _test_settings
    app.dependency_overrides[dependencies.get_connector_registry] = lambda: registry
    app.dependency_overrides[dependencies.get_job_store] = lambda: MagicMock()
    app.dependency_overrides[dependencies.get_mapping_store] = lambda: MagicMock()
    app.dependency_overrides[dependencies.get_data_store] = lambda: MagicMock()
    app.dependency_overrides[dependencies.get_schema_version_store] = lambda: MagicMock()
    return TestClient(app)


def test_valid_key_accepted(client: TestClient) -> None:
    resp = client.get("/connectors", headers={"X-Api-Key": API_KEY})
    assert resp.status_code == 200


def test_missing_key_rejected(client: TestClient) -> None:
    resp = client.get("/connectors")
    assert resp.status_code == 401


def test_wrong_key_rejected(client: TestClient) -> None:
    resp = client.get("/connectors", headers={"X-Api-Key": "wrong"})
    assert resp.status_code == 401


def test_health_endpoint_needs_no_key(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200


def test_auth_applies_to_jobs_route(client: TestClient) -> None:
    resp = client.get("/jobs")
    assert resp.status_code == 401


def test_auth_applies_to_data_route(client: TestClient) -> None:
    resp = client.get("/data/any-job-id")
    assert resp.status_code == 401
