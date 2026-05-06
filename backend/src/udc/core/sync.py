"""Watermark-based incremental sync engine backed by DuckDB."""

from typing import Any

import duckdb

_INIT_SQL = """
CREATE TABLE IF NOT EXISTS sync_watermarks (
    connector_id  TEXT      NOT NULL,
    table_name    TEXT      NOT NULL,
    watermark_col TEXT,
    watermark_val TEXT,
    synced_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (connector_id, table_name)
);
"""


class IncrementalSyncEngine:
    """
    Persists per-source watermarks in a local DuckDB file so that
    subsequent sync runs only fetch rows newer than the last run.

    Usage::

        engine = IncrementalSyncEngine("./data/udc.duckdb")

        col, val = engine.get_watermark("pg-orders", "orders")
        # col="updated_at", val="2024-01-15T10:00:00" (or None on first run)

        # ... fetch rows WHERE updated_at > val ...

        engine.set_watermark("pg-orders", "orders", "updated_at", max_updated_at)
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._conn: duckdb.DuckDBPyConnection | None = None

    def _get_conn(self) -> duckdb.DuckDBPyConnection:
        if self._conn is None:
            self._conn = duckdb.connect(self._db_path)
            self._conn.execute(_INIT_SQL)
        return self._conn

    def get_watermark(self, connector_id: str, table_name: str) -> tuple[str | None, Any]:
        """Return ``(watermark_col, watermark_val)`` or ``(None, None)`` on first run."""
        row = (
            self._get_conn()
            .execute(
                """
            SELECT watermark_col, watermark_val
            FROM sync_watermarks
            WHERE connector_id = ? AND table_name = ?
            """,
                [connector_id, table_name],
            )
            .fetchone()
        )
        if row is None:
            return None, None
        return row[0], row[1]

    def set_watermark(
        self,
        connector_id: str,
        table_name: str,
        watermark_col: str,
        watermark_val: Any,
    ) -> None:
        """Upsert the watermark after a successful sync run."""
        self._get_conn().execute(
            """
            INSERT INTO sync_watermarks
                (connector_id, table_name, watermark_col, watermark_val, synced_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT (connector_id, table_name) DO UPDATE SET
                watermark_col = excluded.watermark_col,
                watermark_val = excluded.watermark_val,
                synced_at     = excluded.synced_at
            """,
            [connector_id, table_name, watermark_col, str(watermark_val)],
        )

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
