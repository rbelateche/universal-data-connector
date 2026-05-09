"""Schema versioning — snapshots and diff detection across sync runs."""

import json
from dataclasses import dataclass
from typing import Any

import duckdb

_INIT_SQL = """
CREATE TABLE IF NOT EXISTS schema_snapshots (
    id          INTEGER,
    source_id   TEXT      NOT NULL,
    schema_json TEXT      NOT NULL,
    captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS schema_diffs (
    id           INTEGER,
    source_id    TEXT NOT NULL,
    from_id      INTEGER,
    to_id        INTEGER NOT NULL,
    added_cols   TEXT NOT NULL,
    removed_cols TEXT NOT NULL,
    changed_cols TEXT NOT NULL,
    detected_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);
"""


@dataclass
class SchemaDiff:
    added: list[str]
    removed: list[str]
    changed: dict[str, dict[str, str]]  # {col: {"from": old_type, "to": new_type}}

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.removed or self.changed)


class SchemaVersionStore:
    """
    Persists schema snapshots and detects diffs across sync runs.

    Usage::

        store = SchemaVersionStore("./data/udc.duckdb")
        diff = store.snapshot("pg-orders", {"id": "INTEGER", "name": "TEXT"})

        if diff and diff.has_changes:
            print("Schema changed!", diff.added, diff.removed, diff.changed)
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._conn: duckdb.DuckDBPyConnection | None = None

    def _get_conn(self) -> duckdb.DuckDBPyConnection:
        if self._conn is None:
            self._conn = duckdb.connect(self._db_path)
            self._conn.execute(_INIT_SQL)
        return self._conn

    def snapshot(self, source_id: str, schema: dict[str, str]) -> SchemaDiff | None:
        """
        Persist a schema snapshot.

        Returns the diff compared to the previous snapshot, or ``None``
        if this is the first snapshot for *source_id*.
        """
        conn = self._get_conn()
        schema_json = json.dumps(schema, sort_keys=True)

        # Previous snapshot
        prev = conn.execute(
            """
            SELECT id, schema_json
            FROM schema_snapshots
            WHERE source_id = ?
            ORDER BY captured_at DESC
            LIMIT 1
            """,
            [source_id],
        ).fetchone()

        # Compute next id
        row = conn.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM schema_snapshots").fetchone()
        new_id: int = row[0] if row else 1

        conn.execute(
            "INSERT INTO schema_snapshots (id, source_id, schema_json) VALUES (?, ?, ?)",
            [new_id, source_id, schema_json],
        )

        if prev is None:
            return None

        prev_id, prev_json = prev
        diff = self._compute_diff(json.loads(prev_json), schema)

        diff_id_row = conn.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM schema_diffs").fetchone()
        diff_id: int = diff_id_row[0] if diff_id_row else 1

        conn.execute(
            """
            INSERT INTO schema_diffs
                (id, source_id, from_id, to_id, added_cols, removed_cols, changed_cols)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                diff_id,
                source_id,
                prev_id,
                new_id,
                json.dumps(diff.added),
                json.dumps(diff.removed),
                json.dumps(diff.changed),
            ],
        )
        return diff

    def get_history(self, source_id: str) -> list[dict[str, Any]]:
        """Return all snapshots for *source_id*, newest first."""
        rows = (
            self._get_conn()
            .execute(
                """
            SELECT id, schema_json, captured_at
            FROM schema_snapshots
            WHERE source_id = ?
            ORDER BY captured_at DESC
            """,
                [source_id],
            )
            .fetchall()
        )
        return [{"id": r[0], "schema": json.loads(r[1]), "captured_at": str(r[2])} for r in rows]

    def get_latest_diff(self, source_id: str) -> SchemaDiff | None:
        """Return the most recent schema diff for *source_id*, or None if none exists."""
        row = (
            self._get_conn()
            .execute(
                """
                SELECT added_cols, removed_cols, changed_cols
                FROM schema_diffs
                WHERE source_id = ?
                ORDER BY detected_at DESC
                LIMIT 1
                """,
                [source_id],
            )
            .fetchone()
        )
        if row is None:
            return None
        return SchemaDiff(
            added=json.loads(row[0]),
            removed=json.loads(row[1]),
            changed=json.loads(row[2]),
        )

    @staticmethod
    def _compute_diff(old: dict[str, str], new: dict[str, str]) -> SchemaDiff:
        old_cols = set(old)
        new_cols = set(new)
        return SchemaDiff(
            added=sorted(new_cols - old_cols),
            removed=sorted(old_cols - new_cols),
            changed={
                col: {"from": old[col], "to": new[col]}
                for col in old_cols & new_cols
                if old[col] != new[col]
            },
        )

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
