"""Tests for POST /jobs and GET /jobs/{id} router."""

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from udc.api import dependencies
from udc.api.app import create_app
from udc.core.config import Settings, get_settings
from udc.core.connector_registry import ConnectorConfig
from udc.core.job_store import Job

API_KEY = "test-secret"


def _test_settings() -> Settings:
    return Settings(
        database_url="postgresql://x:x@localhost/x",
        anthropic_api_key="sk-test",
        api_key=API_KEY,
        duckdb_path=":memory:",
    )


def _make_connector() -> ConnectorConfig:
    return ConnectorConfig(
        id="conn-uuid", name="pg-crm", type="postgres", config={"url": "pg://x", "table": "t"}
    )


def _make_job(status: str = "pending", mapping_id: int | None = None) -> Job:
    now = datetime.now(tz=timezone.utc)
    return Job(
        id="job-uuid",
        connector_id="conn-uuid",
        target_schema="Contact",
        status=status,
        progress_pct=0.0,
        error=None,
        mapping_id=mapping_id,
        rows_processed=0,
        started_at=None,
        finished_at=None,
        created_at=now,
    )


@pytest.fixture(autouse=True)
def reset() -> Any:
    dependencies._reset_singletons()
    yield
    dependencies._reset_singletons()


@pytest.fixture
def client() -> TestClient:
    connector_registry = MagicMock()
    connector_registry.get.return_value = _make_connector()

    job_store = MagicMock()
    job_store.create.return_value = _make_job()
    job_store.get.return_value = _make_job()
    job_store.list_all.return_value = [_make_job()]

    app = create_app()
    app.dependency_overrides[get_settings] = _test_settings
    app.dependency_overrides[dependencies.get_connector_registry] = lambda: connector_registry
    app.dependency_overrides[dependencies.get_job_store] = lambda: job_store
    app.dependency_overrides[dependencies.get_mapping_store] = lambda: MagicMock()
    app.dependency_overrides[dependencies.get_data_store] = lambda: MagicMock()
    app.dependency_overrides[dependencies.get_schema_version_store] = lambda: MagicMock()
    return TestClient(app)


@patch("udc.api.routers.jobs.run_job", new_callable=AsyncMock)
def test_create_job_returns_202(mock_run: AsyncMock, client: TestClient) -> None:
    resp = client.post(
        "/jobs",
        json={"connector_id": "conn-uuid", "target_schema_name": "Contact"},
        headers={"X-Api-Key": API_KEY},
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "pending"
    assert data["job_id"] == "job-uuid"


@patch("udc.api.routers.jobs.run_job", new_callable=AsyncMock)
def test_create_job_unknown_schema_returns_422(mock_run: AsyncMock, client: TestClient) -> None:
    resp = client.post(
        "/jobs",
        json={"connector_id": "conn-uuid", "target_schema_name": "NonExistent"},
        headers={"X-Api-Key": API_KEY},
    )
    assert resp.status_code == 422


@patch("udc.api.routers.jobs.run_job", new_callable=AsyncMock)
def test_create_job_missing_connector_returns_404(mock_run: AsyncMock, client: TestClient) -> None:
    connector_registry = MagicMock()
    connector_registry.get.side_effect = KeyError("Connector not found.")
    client.app.dependency_overrides[dependencies.get_connector_registry] = (
        lambda: connector_registry
    )
    resp = client.post(
        "/jobs",
        json={"connector_id": "bad-id", "target_schema_name": "Contact"},
        headers={"X-Api-Key": API_KEY},
    )
    assert resp.status_code == 404


def test_get_job_returns_status(client: TestClient) -> None:
    resp = client.get("/jobs/job-uuid", headers={"X-Api-Key": API_KEY})
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"


def test_get_missing_job_returns_404(client: TestClient) -> None:
    job_store = MagicMock()
    job_store.get.side_effect = KeyError("Job 'x' not found.")
    client.app.dependency_overrides[dependencies.get_job_store] = lambda: job_store

    resp = client.get("/jobs/no-such-job", headers={"X-Api-Key": API_KEY})
    assert resp.status_code == 404


def test_list_jobs(client: TestClient) -> None:
    resp = client.get("/jobs", headers={"X-Api-Key": API_KEY})
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_get_job_mapping_no_mapping_yet_returns_409(client: TestClient) -> None:
    # job has no mapping_id yet
    resp = client.get("/jobs/job-uuid/mapping", headers={"X-Api-Key": API_KEY})
    assert resp.status_code == 409


def test_get_job_mapping_returns_mapping(client: TestClient) -> None:
    from udc.mapper.models import FieldMapping, MappingResult

    result = MappingResult(
        source_id="conn-uuid",
        target_schema_name="Contact",
        mappings=[
            FieldMapping(
                source_col="cust_id",
                target_col="customer_id",
                transform="cast_int",
                confidence=0.95,
                reasoning="ID column",
            )
        ],
        unmapped_source=[],
        unmapped_target=[],
    )
    job_store = MagicMock()
    job_store.get.return_value = _make_job(status="done", mapping_id=1)
    mapping_store = MagicMock()
    mapping_store.load.return_value = result

    client.app.dependency_overrides[dependencies.get_job_store] = lambda: job_store
    client.app.dependency_overrides[dependencies.get_mapping_store] = lambda: mapping_store

    resp = client.get("/jobs/job-uuid/mapping", headers={"X-Api-Key": API_KEY})
    assert resp.status_code == 200
    data = resp.json()
    assert data["mapping_id"] == 1
    assert len(data["mappings"]) == 1
    assert data["mappings"][0]["source_col"] == "cust_id"
