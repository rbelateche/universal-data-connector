"""Tests for DataStore."""

import pytest

from udc.core.data_store import DataStore


@pytest.fixture
def store(tmp_path: pytest.TempPathFactory) -> DataStore:
    return DataStore(str(tmp_path / "test.duckdb"))  # type: ignore[arg-type]


def test_save_and_get_rows(store: DataStore) -> None:
    rows = [{"customer_id": 1, "full_name": "Alice"}, {"customer_id": 2, "full_name": "Bob"}]
    store.save_rows("job-1", rows)
    result = store.get_rows("job-1")
    assert result == rows


def test_count(store: DataStore) -> None:
    rows = [{"x": i} for i in range(10)]
    store.save_rows("job-2", rows)
    assert store.count("job-2") == 10


def test_empty_job_returns_empty(store: DataStore) -> None:
    assert store.get_rows("nonexistent") == []
    assert store.count("nonexistent") == 0


def test_pagination(store: DataStore) -> None:
    rows = [{"n": i} for i in range(20)]
    store.save_rows("job-3", rows)
    page = store.get_rows("job-3", offset=5, limit=5)
    assert len(page) == 5
    assert page[0]["n"] == 5
    assert page[-1]["n"] == 9


def test_multiple_jobs_isolated(store: DataStore) -> None:
    store.save_rows("job-a", [{"x": 1}])
    store.save_rows("job-b", [{"x": 2}, {"x": 3}])
    assert store.count("job-a") == 1
    assert store.count("job-b") == 2
