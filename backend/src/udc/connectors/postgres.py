"""PostgreSQL connector using SQLAlchemy Core (synchronous)."""

from collections.abc import Iterator
from typing import Any

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from udc.connectors.base import BaseConnector
from udc.core._utils import validate_identifier


class PostgresConnector(BaseConnector):
    """Read data from a single Postgres table via SQLAlchemy Core."""

    def __init__(
        self,
        url: str,
        table: str,
        schema: str = "public",
    ) -> None:
        self.url = url
        self.table = validate_identifier(table, "table")
        self.schema = validate_identifier(schema, "schema")
        self._engine: Engine | None = None

    # ── lifecycle ─────────────────────────────────────────────────────────

    def connect(self) -> None:
        self._engine = create_engine(self.url, pool_pre_ping=True)
        with self._engine.connect() as conn:
            conn.execute(text("SELECT 1"))

    def close(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None

    # ── helpers ───────────────────────────────────────────────────────────

    def _qualified(self) -> str:
        return f"{self.schema}.{self.table}"

    def _assert_connected(self) -> Engine:
        if self._engine is None:
            raise RuntimeError("Call connect() before reading data.")
        return self._engine

    # ── data access ───────────────────────────────────────────────────────

    def sample(self, n: int = 100) -> list[dict[str, Any]]:
        engine = self._assert_connected()
        with engine.connect() as conn:
            rows = conn.execute(
                text(f"SELECT * FROM {self._qualified()} LIMIT :n"),
                {"n": n},
            )
            return [dict(row._mapping) for row in rows]

    def stream(
        self,
        batch_size: int = 1000,
        watermark_col: str | None = None,
        watermark_val: Any = None,
    ) -> Iterator[list[dict[str, Any]]]:
        engine = self._assert_connected()

        query = f"SELECT * FROM {self._qualified()}"
        params: dict[str, Any] = {}

        if watermark_col is not None and watermark_val is not None:
            col = validate_identifier(watermark_col, "watermark column")
            query += f" WHERE {col} > :watermark"
            params["watermark"] = watermark_val

        with engine.connect() as conn:
            result = conn.execution_options(stream_results=True).execute(
                text(query), params
            )
            while True:
                batch = result.fetchmany(batch_size)
                if not batch:
                    break
                yield [dict(row._mapping) for row in batch]

    def get_schema(self) -> dict[str, str]:
        engine = self._assert_connected()
        inspector = inspect(engine)
        columns = inspector.get_columns(self.table, schema=self.schema)
        return {col["name"]: str(col["type"]) for col in columns}
