"""MappingStore — persists mapping results and human overrides in DuckDB."""

import json
from typing import Any

import duckdb

from udc.mapper.models import FieldMapping, MappingResult

_INIT_SQL = """
CREATE TABLE IF NOT EXISTS mapping_configs (
    id                 INTEGER PRIMARY KEY,
    source_id          TEXT NOT NULL,
    target_schema_name TEXT NOT NULL,
    mapping_json       TEXT NOT NULL,
    created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS mapping_overrides (
    id            INTEGER PRIMARY KEY,
    mapping_id    INTEGER NOT NULL,
    source_col    TEXT NOT NULL,
    override_json TEXT NOT NULL,
    applied_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def _result_to_dict(result: MappingResult) -> dict[str, Any]:
    return {
        "source_id": result.source_id,
        "target_schema_name": result.target_schema_name,
        "mappings": [
            {
                "source_col": m.source_col,
                "target_col": m.target_col,
                "transform": m.transform,
                "confidence": m.confidence,
                "reasoning": m.reasoning,
                "value_map": m.value_map,
            }
            for m in result.mappings
        ],
        "unmapped_source": result.unmapped_source,
        "unmapped_target": result.unmapped_target,
    }


def _dict_to_result(data: dict[str, Any]) -> MappingResult:
    return MappingResult(
        source_id=data["source_id"],
        target_schema_name=data["target_schema_name"],
        mappings=[
            FieldMapping(
                source_col=m["source_col"],
                target_col=m["target_col"],
                transform=m["transform"],
                confidence=m["confidence"],
                reasoning=m["reasoning"],
                value_map=m.get("value_map") or {},
            )
            for m in data["mappings"]
        ],
        unmapped_source=data["unmapped_source"],
        unmapped_target=data["unmapped_target"],
    )


class MappingStore:
    """
    Persists MappingResult objects and human override patches to DuckDB.

    Usage::

        store = MappingStore("data/udc.duckdb")
        mapping_id = store.save(result)

        loaded = store.load(mapping_id)
        store.apply_override(mapping_id, "actv", {"target_col": "is_active", "transform": "cast_bool"})
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

    # ── save / load ───────────────────────────────────────────────────────

    def save(self, result: MappingResult) -> int:
        """Persist a MappingResult. Returns the new mapping_id."""
        conn = self._get_conn()
        row = conn.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM mapping_configs").fetchone()
        new_id: int = row[0] if row else 1
        conn.execute(
            """
            INSERT INTO mapping_configs (id, source_id, target_schema_name, mapping_json)
            VALUES (?, ?, ?, ?)
            """,
            [
                new_id,
                result.source_id,
                result.target_schema_name,
                json.dumps(_result_to_dict(result)),
            ],
        )
        return new_id

    def load(self, mapping_id: int) -> MappingResult:
        """Load and reconstruct a MappingResult, applying any stored overrides."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT mapping_json FROM mapping_configs WHERE id = ?",
            [mapping_id],
        ).fetchone()
        if row is None:
            raise KeyError(f"No mapping found with id={mapping_id}")
        data: dict[str, Any] = json.loads(row[0])

        # Apply any human overrides on top
        overrides = conn.execute(
            "SELECT source_col, override_json FROM mapping_overrides WHERE mapping_id = ?",
            [mapping_id],
        ).fetchall()
        for src_col, override_json in overrides:
            patch: dict[str, Any] = json.loads(override_json)
            for m in data["mappings"]:
                if m["source_col"] == src_col:
                    m.update(patch)
                    break

        return _dict_to_result(data)

    def list_for_source(self, source_id: str) -> list[dict[str, Any]]:
        """Return summary rows for all mappings saved for a given source."""
        conn = self._get_conn()
        rows = conn.execute(
            """
            SELECT id, source_id, target_schema_name, created_at
            FROM mapping_configs
            WHERE source_id = ?
            ORDER BY created_at DESC
            """,
            [source_id],
        ).fetchall()
        return [
            {
                "id": r[0],
                "source_id": r[1],
                "target_schema_name": r[2],
                "created_at": str(r[3]),
            }
            for r in rows
        ]

    # ── overrides (2.7) ───────────────────────────────────────────────────

    def apply_override(
        self,
        mapping_id: int,
        source_col: str,
        patch: dict[str, Any],
    ) -> None:
        """
        Persist a human correction for one field.

        *patch* contains only the keys to change, e.g.
        ``{"target_col": "revenue_eur", "confidence": 1.0}``.
        Applied on top of the stored mapping at load time.
        """
        conn = self._get_conn()

        # Validate mapping exists
        exists = conn.execute("SELECT 1 FROM mapping_configs WHERE id = ?", [mapping_id]).fetchone()
        if exists is None:
            raise KeyError(f"No mapping found with id={mapping_id}")
        row = conn.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM mapping_overrides").fetchone()
        new_id: int = row[0] if row else 1
        conn.execute(
            """
            INSERT INTO mapping_overrides (id, mapping_id, source_col, override_json)
            VALUES (?, ?, ?, ?)
            """,
            [new_id, mapping_id, source_col, json.dumps(patch)],
        )
