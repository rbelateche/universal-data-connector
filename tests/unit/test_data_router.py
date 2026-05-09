"""Tests for GET /data/{job_id} router."""

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from udc.api import dependencies
from udc.api.app import create_app
from udc.core.config import Settings, get_settings
from udc.core.job_store import Job

API_KEY = "test-secret"


def _test_settings() -> Settings:
    return Settings(
        database_url="postgresql://x:x@localhost/x",
        anthropic_api_key="sk-test",
        api_key=API_KEY,
        duckdb_path=":memory:",
    )


def _make_job(status: str = "done") -> Job:
    now = datetime.now(tz=timezone.utc)
    return Job(
        id="job-uuid",
        connector_id="conn-uuid",
        target_schema="Contact",
        status=status,
        progress_pct=100.0 if status == "done" else 50.0,
        error=None,
        mapping_id=1,
        rows_processed=3,
        started_at=now,
        finished_at=now,
        created_at=now,
    )


@pytest.fixture(autouse=True)
def reset() -> Any:
    dependencies._reset_singletons()
    yield
    dependencies._reset_singletons()


@pytest.fixture
def client() -> TestClient:
    _rows = [{"customer_id": i, "full_name": f"User {i}"} for i in range(3)]

    job_store = MagicMock()
    job_store.get.return_value = _make_job()

    data_store = MagicMock()
    data_store.get_rows.return_value = _rows
    data_store.count.return_value = 3

    app = create_app()
    app.dependency_overrides[get_settings] = _test_settings
    app.dependency_overrides[dependencies.get_job_store] = lambda: job_store
    app.dependency_overrides[dependencies.get_data_store] = lambda: data_store
    return TestClient(app)


def test_get_data_returns_rows(client: TestClient) -> None:
    resp = client.get("/data/job-uuid", headers={"X-Api-Key": API_KEY})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_rows"] == 3
    assert len(data["rows"]) == 3
    assert data["offset"] == 0
    assert data["limit"] == 100


def test_get_data_pagination_params(client: TestClient) -> None:
    resp = client.get("/data/job-uuid?offset=1&limit=2", headers={"X-Api-Key": API_KEY})
    assert resp.status_code == 200
    assert resp.json()["offset"] == 1
    assert resp.json()["limit"] == 2


def test_get_data_job_not_done_returns_409(client: TestClient) -> None:
    job_store = MagicMock()
    job_store.get.return_value = _make_job(status="running")
    client.app.dependency_overrides[dependencies.get_job_store] = lambda: job_store

    resp = client.get("/data/job-uuid", headers={"X-Api-Key": API_KEY})
    assert resp.status_code == 409


def test_get_data_missing_job_returns_404(client: TestClient) -> None:
    job_store = MagicMock()
    job_store.get.side_effect = KeyError("Job not found.")
    client.app.dependency_overrides[dependencies.get_job_store] = lambda: job_store

    resp = client.get("/data/no-such-job", headers={"X-Api-Key": API_KEY})
    assert resp.status_code == 404


def test_get_data_requires_api_key(client: TestClient) -> None:
    resp = client.get("/data/job-uuid")
    assert resp.status_code == 401
