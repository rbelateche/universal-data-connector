"""SourceStore — registered source schemas and their sample rows, in DuckDB.

A *source* here is what a mapping is inferred from: a named field list plus a
few sample rows (for example an ERP export someone pasted). It is lighter than a
connector, which holds connection settings to pull data itself.
"""

import json
import threading
from dataclasses import dataclass, field
from typing import Any

import duckdb

from udc.core.locking import serialized

_INIT_SQL = """
CREATE TABLE IF NOT EXISTS sources (
    source_id        TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    system           TEXT NOT NULL,
    target_schema    TEXT NOT NULL,
    fields_json      TEXT NOT NULL,
    sample_rows_json TEXT NOT NULL,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


@dataclass
class SourceField:
    name: str
    type: str = "unknown"  # as declared by the source system, e.g. "CHAR(18)"
    description: str = ""


@dataclass
class Source:
    source_id: str
    name: str
    system: str
    target_schema: str
    fields: list[SourceField] = field(default_factory=list)
    sample_rows: list[dict[str, Any]] = field(default_factory=list)

    @property
    def field_names(self) -> list[str]:
        """Declared fields, then any extra keys seen in sample rows, in order."""
        names = [f.name for f in self.fields]
        seen = set(names)
        for row in self.sample_rows:
            for key in row:
                if key not in seen:
                    seen.add(key)
                    names.append(key)
        return names


class SourceStore:
    """
    Persists registered sources in DuckDB.

    Usage::

        store = SourceStore("./data/udc.duckdb")
        store.register(Source("erp", "SAP ERP export", "erp", "Product", fields, rows))
        erp = store.get("erp")
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._conn: duckdb.DuckDBPyConnection | None = None
        self._lock = threading.RLock()

    def _get_conn(self) -> duckdb.DuckDBPyConnection:
        if self._conn is None:
            self._conn = duckdb.connect(self._db_path)
            self._conn.execute(_INIT_SQL)
        return self._conn

    @serialized
    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @serialized
    def exists(self, source_id: str) -> bool:
        row = (
            self._get_conn()
            .execute("SELECT 1 FROM sources WHERE source_id = ?", [source_id])
            .fetchone()
        )
        return row is not None

    @serialized
    def register(self, source: Source) -> Source:
        """Persist a new source. Raises ValueError if the id is taken."""
        if self.exists(source.source_id):
            raise ValueError(f"Source {source.source_id!r} already exists.")
        self._get_conn().execute(
            """
            INSERT INTO sources
                (source_id, name, system, target_schema, fields_json, sample_rows_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                source.source_id,
                source.name,
                source.system,
                source.target_schema,
                json.dumps([f.__dict__ for f in source.fields]),
                json.dumps(source.sample_rows, default=str),
            ],
        )
        return source

    @serialized
    def get(self, source_id: str) -> Source:
        """Return the source. Raises KeyError if it is not registered."""
        row = (
            self._get_conn()
            .execute(
                """
                SELECT source_id, name, system, target_schema, fields_json, sample_rows_json
                FROM sources WHERE source_id = ?
                """,
                [source_id],
            )
            .fetchone()
        )
        if row is None:
            raise KeyError(f"Source {source_id!r} not found.")
        return self._to_source(row)

    @serialized
    def list_all(self) -> list[Source]:
        """All sources, oldest first."""
        rows = (
            self._get_conn()
            .execute(
                """
                SELECT source_id, name, system, target_schema, fields_json, sample_rows_json
                FROM sources ORDER BY created_at, source_id
                """
            )
            .fetchall()
        )
        return [self._to_source(r) for r in rows]

    @staticmethod
    def _to_source(row: tuple[Any, ...]) -> Source:
        return Source(
            source_id=row[0],
            name=row[1],
            system=row[2],
            target_schema=row[3],
            fields=[SourceField(**f) for f in json.loads(row[4])],
            sample_rows=json.loads(row[5]),
        )
