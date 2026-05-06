"""CSV connector backed by DuckDB's read_csv_auto."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import duckdb

from udc.connectors.base import BaseConnector
from udc.core._utils import validate_identifier


class CsvConnector(BaseConnector):
    """
    Read data from a CSV file using DuckDB's auto-detection.

    DuckDB infers column types, handles encoding issues, and streams large
    files efficiently without loading everything into memory at once.
    """

    def __init__(self, path: str | Path) -> None:
        resolved = Path(path).resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"CSV file not found: {path}")
        # Single-quote escape to prevent SQL injection in DuckDB string literal
        self._safe_path = str(resolved).replace("'", "''")
        self._conn: duckdb.DuckDBPyConnection | None = None

    # ── lifecycle ─────────────────────────────────────────────────────────

    def connect(self) -> None:
        self._conn = duckdb.connect(":memory:")
        # Smoke-test: verify file is readable and parseable
        self._conn.execute(f"SELECT * FROM read_csv_auto('{self._safe_path}') LIMIT 0")

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ── helpers ───────────────────────────────────────────────────────────

    def _assert_connected(self) -> duckdb.DuckDBPyConnection:
        if self._conn is None:
            raise RuntimeError("Call connect() before reading data.")
        return self._conn

    # ── data access ───────────────────────────────────────────────────────

    def sample(self, n: int = 100) -> list[dict[str, Any]]:
        conn = self._assert_connected()
        df = conn.execute(
            f"SELECT * FROM read_csv_auto('{self._safe_path}') LIMIT {int(n)}"
        ).df()
        return df.to_dict(orient="records")

    def stream(
        self,
        batch_size: int = 1000,
        watermark_col: str | None = None,
        watermark_val: Any = None,
    ) -> Iterator[list[dict[str, Any]]]:
        conn = self._assert_connected()

        base = f"SELECT * FROM read_csv_auto('{self._safe_path}')"
        where = ""
        params: list[Any] = []

        if watermark_col is not None and watermark_val is not None:
            col = validate_identifier(watermark_col, "watermark column")
            where = f' WHERE "{col}" > ?'
            params.append(watermark_val)

        offset = 0
        while True:
            query = base + where + f" LIMIT {int(batch_size)} OFFSET {int(offset)}"
            df = conn.execute(query, params).df()
            if df.empty:
                break
            yield df.to_dict(orient="records")
            offset += batch_size

    def get_schema(self) -> dict[str, str]:
        conn = self._assert_connected()
        rows = conn.execute(
            f"DESCRIBE SELECT * FROM read_csv_auto('{self._safe_path}')"
        ).fetchall()
        return {row[0]: row[1] for row in rows}
