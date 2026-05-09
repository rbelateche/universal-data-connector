"""DataStore — persists transformed rows by job_id in DuckDB."""

import json
from typing import Any

import duckdb

_INIT_SQL = """
CREATE TABLE IF NOT EXISTS job_rows (
    job_id    TEXT    NOT NULL,
    row_index INTEGER NOT NULL,
    row_json  TEXT    NOT NULL,
    PRIMARY KEY (job_id, row_index)
);
"""


class DataStore:
    """
    Stores and retrieves paginated rows produced by RowTransformer.

    Usage::

        store = DataStore("./data/udc.duckdb")
        store.save_rows("job-uuid", transformed_rows)
        page = store.get_rows("job-uuid", offset=0, limit=50)
        total = store.count("job-uuid")
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._conn: duckdb.DuckDBPyConnection | None = None

    def _get_conn(self) -> duckdb.DuckDBPyConnection:
        if self._conn is None:
            self._conn = duckdb.connect(self._db_path)
            self._conn.execute(_INIT_SQL)
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def save_rows(self, job_id: str, rows: list[dict[str, Any]]) -> None:
        """Persist all transformed rows for a job."""
        self._get_conn().executemany(
            "INSERT INTO job_rows (job_id, row_index, row_json) VALUES (?, ?, ?)",
            [(job_id, i, json.dumps(row, default=str)) for i, row in enumerate(rows)],
        )

    def get_rows(
        self,
        job_id: str,
        offset: int = 0,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return a page of rows for *job_id*."""
        rows = (
            self._get_conn()
            .execute(
                """
            SELECT row_json FROM job_rows
            WHERE job_id = ?
            ORDER BY row_index
            LIMIT ? OFFSET ?
            """,
                [job_id, limit, offset],
            )
            .fetchall()
        )
        return [json.loads(r[0]) for r in rows]

    def count(self, job_id: str) -> int:
        """Total number of rows stored for *job_id*."""
        row = (
            self._get_conn()
            .execute(
                "SELECT COUNT(*) FROM job_rows WHERE job_id = ?",
                [job_id],
            )
            .fetchone()
        )
        return int(row[0]) if row else 0
