"""Tests for JobStore."""

import pytest

from udc.core.job_store import JobStore


@pytest.fixture
def store(tmp_path: pytest.TempPathFactory) -> JobStore:
    return JobStore(str(tmp_path / "test.duckdb"))  # type: ignore[arg-type]


def test_create_returns_pending_job(store: JobStore) -> None:
    job = store.create("conn-1", "Contact")
    assert job.id is not None
    assert job.connector_id == "conn-1"
    assert job.target_schema == "Contact"
    assert job.status == "pending"
    assert job.progress_pct == 0.0
    assert job.error is None
    assert job.mapping_id is None
    assert job.rows_processed == 0


def test_get_roundtrips_job(store: JobStore) -> None:
    created = store.create("conn-1", "Order")
    loaded = store.get(created.id)
    assert loaded.id == created.id
    assert loaded.target_schema == "Order"


def test_get_missing_raises_key_error(store: JobStore) -> None:
    with pytest.raises(KeyError, match="not found"):
        store.get("no-such-id")


def test_update_status_and_progress(store: JobStore) -> None:
    job = store.create("conn-1", "Contact")
    store.update(job.id, status="running", progress_pct=25.0)
    updated = store.get(job.id)
    assert updated.status == "running"
    assert updated.progress_pct == 25.0


def test_update_error_field(store: JobStore) -> None:
    job = store.create("conn-1", "Contact")
    store.update(job.id, status="failed", error="Something went wrong")
    loaded = store.get(job.id)
    assert loaded.status == "failed"
    assert loaded.error == "Something went wrong"


def test_update_unknown_field_raises(store: JobStore) -> None:
    job = store.create("conn-1", "Contact")
    with pytest.raises(ValueError, match="Unknown job fields"):
        store.update(job.id, bad_field="x")


def test_list_all(store: JobStore) -> None:
    store.create("c1", "Contact")
    store.create("c2", "Order")
    jobs = store.list_all()
    assert len(jobs) == 2
    # newest first
    assert jobs[0].target_schema == "Order"
