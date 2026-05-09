"""Registry of registered data source connectors, persisted in DuckDB."""

import json
import uuid
from dataclasses import dataclass
from typing import Any

import duckdb

_INIT_SQL = """
CREATE TABLE IF NOT EXISTS registered_connectors (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    type        TEXT NOT NULL,
    config_json TEXT NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CONNECTOR_TYPES: frozenset[str] = frozenset({"postgres", "csv", "json_api"})


@dataclass
class ConnectorConfig:
    """A registered connector's identity and configuration."""

    id: str
    name: str
    type: str
    config: dict[str, Any]


class ConnectorRegistry:
    """
    Persists connector registrations (type + credentials) in DuckDB.

    Usage::

        registry = ConnectorRegistry("./data/udc.duckdb")
        cfg = registry.register("pg-crm", "postgres", {"url": "...", "table": "customers"})
        loaded = registry.get(cfg.id)
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

    def register(self, name: str, type_: str, config: dict[str, Any]) -> ConnectorConfig:
        """Register a new connector. Returns the saved config with a generated id."""
        if type_ not in CONNECTOR_TYPES:
            raise ValueError(
                f"Unknown connector type {type_!r}. Choose from {sorted(CONNECTOR_TYPES)}."
            )
        connector_id = str(uuid.uuid4())
        self._get_conn().execute(
            "INSERT INTO registered_connectors (id, name, type, config_json) VALUES (?, ?, ?, ?)",
            [connector_id, name, type_, json.dumps(config)],
        )
        return ConnectorConfig(id=connector_id, name=name, type=type_, config=config)

    def get(self, connector_id: str) -> ConnectorConfig:
        """Return the connector config for *connector_id*. Raises KeyError if missing."""
        row = (
            self._get_conn()
            .execute(
                "SELECT id, name, type, config_json FROM registered_connectors WHERE id = ?",
                [connector_id],
            )
            .fetchone()
        )
        if row is None:
            raise KeyError(f"Connector {connector_id!r} not found.")
        return ConnectorConfig(id=row[0], name=row[1], type=row[2], config=json.loads(row[3]))

    def list_all(self) -> list[ConnectorConfig]:
        """Return all registered connectors, ordered by creation time."""
        rows = (
            self._get_conn()
            .execute(
                "SELECT id, name, type, config_json FROM registered_connectors ORDER BY created_at",
            )
            .fetchall()
        )
        return [
            ConnectorConfig(id=r[0], name=r[1], type=r[2], config=json.loads(r[3])) for r in rows
        ]
