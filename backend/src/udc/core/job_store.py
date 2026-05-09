"""Job store — tracks ingestion + mapping job lifecycle in DuckDB."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import duckdb

_INIT_SQL = """
CREATE TABLE IF NOT EXISTS jobs (
    id             TEXT PRIMARY KEY,
    connector_id   TEXT NOT NULL,
    target_schema  TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'pending',
    progress_pct   FLOAT DEFAULT 0.0,
    error          TEXT,
    mapping_id     INTEGER,
    rows_processed INTEGER DEFAULT 0,
    started_at     TIMESTAMP,
    finished_at    TIMESTAMP,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

_ALLOWED_UPDATE_FIELDS: frozenset[str] = frozenset(
    {
        "status",
        "progress_pct",
        "error",
        "mapping_id",
        "rows_processed",
        "started_at",
        "finished_at",
    }
)


@dataclass
class Job:
    """Snapshot of a single ingestion + mapping job."""

    id: str
    connector_id: str
    target_schema: str
    status: str  # pending | running | done | failed
    progress_pct: float
    error: str | None
    mapping_id: int | None
    rows_processed: int
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class JobStore:
    """
    Persists job records and lifecycle updates to DuckDB.

    Usage::

        store = JobStore("./data/udc.duckdb")
        job = store.create("connector-uuid", "Contact")
        store.update(job.id, status="running", progress_pct=20.0)
        current = store.get(job.id)
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

    # ── CRUD ──────────────────────────────────────────────────────────────

    def create(self, connector_id: str, target_schema: str) -> "Job":
        """Create a new job in 'pending' state and return it."""
        job_id = str(uuid.uuid4())
        self._get_conn().execute(
            "INSERT INTO jobs (id, connector_id, target_schema) VALUES (?, ?, ?)",
            [job_id, connector_id, target_schema],
        )
        return self.get(job_id)

    def get(self, job_id: str) -> "Job":
        """Return the job. Raises KeyError if not found."""
        row = (
            self._get_conn()
            .execute(
                """
            SELECT id, connector_id, target_schema, status, progress_pct, error,
                   mapping_id, rows_processed, started_at, finished_at, created_at
            FROM jobs WHERE id = ?
            """,
                [job_id],
            )
            .fetchone()
        )
        if row is None:
            raise KeyError(f"Job {job_id!r} not found.")
        return Job(
            id=row[0],
            connector_id=row[1],
            target_schema=row[2],
            status=row[3],
            progress_pct=float(row[4]) if row[4] is not None else 0.0,
            error=row[5],
            mapping_id=row[6],
            rows_processed=int(row[7]) if row[7] is not None else 0,
            started_at=row[8],
            finished_at=row[9],
            created_at=row[10],
        )

    def update(self, job_id: str, **fields: Any) -> None:
        """Update arbitrary job fields. Raises ValueError for unknown field names."""
        unknown = set(fields) - _ALLOWED_UPDATE_FIELDS
        if unknown:
            raise ValueError(f"Unknown job fields: {unknown}")
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [job_id]
        self._get_conn().execute(
            f"UPDATE jobs SET {set_clause} WHERE id = ?",  # noqa: S608
            values,
        )

    def list_all(self) -> list["Job"]:
        """Return all jobs, newest first."""
        rows = (
            self._get_conn()
            .execute(
                """
            SELECT id, connector_id, target_schema, status, progress_pct, error,
                   mapping_id, rows_processed, started_at, finished_at, created_at
            FROM jobs ORDER BY created_at DESC
            """
            )
            .fetchall()
        )
        return [
            Job(
                id=r[0],
                connector_id=r[1],
                target_schema=r[2],
                status=r[3],
                progress_pct=float(r[4]) if r[4] is not None else 0.0,
                error=r[5],
                mapping_id=r[6],
                rows_processed=int(r[7]) if r[7] is not None else 0,
                started_at=r[8],
                finished_at=r[9],
                created_at=r[10],
            )
            for r in rows
        ]
