"""Unit tests for output writers and core stores."""

import tempfile
from pathlib import Path

import pandas as pd
import pytest

from udc.core.sync import IncrementalSyncEngine
from udc.core.versioning import SchemaVersionStore
from udc.writers.duckdb_writer import DuckDBWriter
from udc.writers.parquet import ParquetWriter


_ROWS = [
    {"id": 1, "name": "Alice", "score": 9.5},
    {"id": 2, "name": "Bob", "score": 7.0},
    {"id": 3, "name": "Carol", "score": 8.25},
]


# ── ParquetWriter ──────────────────────────────────────────────────────────────

def test_parquet_write_and_read(tmp_path: Path) -> None:
    path = tmp_path / "out.parquet"
    ParquetWriter(path).write(_ROWS)
    df = pd.read_parquet(path)
    assert len(df) == 3
    assert list(df.columns) == ["id", "name", "score"]


def test_parquet_empty_rows_no_file(tmp_path: Path) -> None:
    path = tmp_path / "empty.parquet"
    ParquetWriter(path).write([])
    assert not path.exists()


def test_parquet_creates_parent_dirs(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "dir" / "out.parquet"
    ParquetWriter(path).write(_ROWS)
    assert path.exists()


# ── DuckDBWriter ───────────────────────────────────────────────────────────────

def test_duckdb_write_and_read(tmp_path: Path) -> None:
    import duckdb

    db = str(tmp_path / "test.duckdb")
    DuckDBWriter(db, "records").write(_ROWS)

    with duckdb.connect(db) as conn:
        rows = conn.execute("SELECT * FROM records ORDER BY id").fetchall()
    assert len(rows) == 3
    assert rows[0][0] == 1


def test_duckdb_append(tmp_path: Path) -> None:
    import duckdb

    db = str(tmp_path / "test.duckdb")
    writer = DuckDBWriter(db, "records")
    writer.write(_ROWS[:2])
    writer.write(_ROWS[2:])

    with duckdb.connect(db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM records").fetchone()[0]
    assert count == 3


def test_duckdb_empty_rows(tmp_path: Path) -> None:
    db = str(tmp_path / "test.duckdb")
    DuckDBWriter(db, "records").write([])  # should not raise


def test_duckdb_invalid_table_name(tmp_path: Path) -> None:
    db = str(tmp_path / "test.duckdb")
    with pytest.raises(ValueError, match="Unsafe SQL"):
        DuckDBWriter(db, "bad-table-name")


# ── IncrementalSyncEngine ──────────────────────────────────────────────────────

def test_sync_engine_first_run_returns_none(tmp_path: Path) -> None:
    engine = IncrementalSyncEngine(str(tmp_path / "sync.duckdb"))
    col, val = engine.get_watermark("pg", "orders")
    assert col is None
    assert val is None
    engine.close()


def test_sync_engine_set_and_get(tmp_path: Path) -> None:
    db = str(tmp_path / "sync.duckdb")
    engine = IncrementalSyncEngine(db)
    engine.set_watermark("pg", "orders", "updated_at", "2024-06-01")
    col, val = engine.get_watermark("pg", "orders")
    assert col == "updated_at"
    assert val == "2024-06-01"
    engine.close()


def test_sync_engine_upsert(tmp_path: Path) -> None:
    db = str(tmp_path / "sync.duckdb")
    engine = IncrementalSyncEngine(db)
    engine.set_watermark("pg", "orders", "updated_at", "2024-01-01")
    engine.set_watermark("pg", "orders", "updated_at", "2024-06-01")
    _, val = engine.get_watermark("pg", "orders")
    assert val == "2024-06-01"
    engine.close()


# ── SchemaVersionStore ─────────────────────────────────────────────────────────

def test_schema_first_snapshot_returns_none(tmp_path: Path) -> None:
    store = SchemaVersionStore(str(tmp_path / "schema.duckdb"))
    diff = store.snapshot("src1", {"id": "INTEGER", "name": "TEXT"})
    assert diff is None
    store.close()


def test_schema_no_diff(tmp_path: Path) -> None:
    store = SchemaVersionStore(str(tmp_path / "schema.duckdb"))
    store.snapshot("src1", {"id": "INTEGER", "name": "TEXT"})
    diff = store.snapshot("src1", {"id": "INTEGER", "name": "TEXT"})
    assert diff is not None
    assert not diff.has_changes
    store.close()


def test_schema_detects_added_column(tmp_path: Path) -> None:
    store = SchemaVersionStore(str(tmp_path / "schema.duckdb"))
    store.snapshot("src1", {"id": "INTEGER"})
    diff = store.snapshot("src1", {"id": "INTEGER", "email": "TEXT"})
    assert diff is not None
    assert "email" in diff.added
    store.close()


def test_schema_detects_removed_column(tmp_path: Path) -> None:
    store = SchemaVersionStore(str(tmp_path / "schema.duckdb"))
    store.snapshot("src1", {"id": "INTEGER", "old_col": "TEXT"})
    diff = store.snapshot("src1", {"id": "INTEGER"})
    assert diff is not None
    assert "old_col" in diff.removed
    store.close()


def test_schema_detects_type_change(tmp_path: Path) -> None:
    store = SchemaVersionStore(str(tmp_path / "schema.duckdb"))
    store.snapshot("src1", {"amount": "TEXT"})
    diff = store.snapshot("src1", {"amount": "FLOAT"})
    assert diff is not None
    assert "amount" in diff.changed
    assert diff.changed["amount"] == {"from": "TEXT", "to": "FLOAT"}
    store.close()


def test_schema_get_history(tmp_path: Path) -> None:
    store = SchemaVersionStore(str(tmp_path / "schema.duckdb"))
    store.snapshot("src1", {"id": "INTEGER"})
    store.snapshot("src1", {"id": "INTEGER", "name": "TEXT"})
    history = store.get_history("src1")
    assert len(history) == 2
    store.close()
