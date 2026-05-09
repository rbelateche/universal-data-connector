"""Unit tests for CsvConnector."""

import csv
import tempfile
from pathlib import Path

import pytest

from udc.connectors.csv import CsvConnector


@pytest.fixture
def csv_file(tmp_path: Path) -> Path:
    path = tmp_path / "orders.csv"
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "customer", "amount", "date"])
        writer.writeheader()
        writer.writerows([
            {"id": 1, "customer": "Alice", "amount": 99.9, "date": "2024-01-01"},
            {"id": 2, "customer": "Bob", "amount": 149.0, "date": "2024-01-02"},
            {"id": 3, "customer": "Carol", "amount": 49.5, "date": "2024-01-03"},
        ])
    return path


def test_csv_sample(csv_file: Path) -> None:
    with CsvConnector(csv_file) as conn:
        rows = conn.sample(2)
    assert len(rows) == 2
    assert rows[0]["customer"] == "Alice"


def test_csv_sample_all(csv_file: Path) -> None:
    with CsvConnector(csv_file) as conn:
        rows = conn.sample(100)
    assert len(rows) == 3


def test_csv_get_schema(csv_file: Path) -> None:
    with CsvConnector(csv_file) as conn:
        schema = conn.get_schema()
    assert "id" in schema
    assert "customer" in schema
    assert "amount" in schema


def test_csv_stream(csv_file: Path) -> None:
    with CsvConnector(csv_file) as conn:
        batches = list(conn.stream(batch_size=2))
    # 3 rows with batch_size=2 → 2 batches
    assert len(batches) == 2
    assert len(batches[0]) == 2
    assert len(batches[1]) == 1


def test_csv_file_not_found() -> None:
    with pytest.raises(FileNotFoundError):
        CsvConnector("/nonexistent/path/data.csv")


def test_csv_connect_required(csv_file: Path) -> None:
    conn = CsvConnector(csv_file)
    with pytest.raises(RuntimeError, match="connect"):
        conn.sample()
