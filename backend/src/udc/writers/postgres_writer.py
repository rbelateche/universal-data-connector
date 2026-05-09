"""Postgres writer — appends rows to a Postgres table via pandas + SQLAlchemy."""

from typing import Any

import pandas as pd
from sqlalchemy import create_engine

from udc.writers.base import BaseWriter


class PostgresWriter(BaseWriter):
    """
    Write rows to a Postgres table.

    Uses ``if_exists="append"`` — the table must already exist or
    pandas will create it automatically on first write.
    """

    def __init__(
        self,
        url: str,
        table: str,
        schema: str = "public",
    ) -> None:
        self.url = url
        self.table = table
        self.pg_schema = schema

    def write(
        self,
        rows: list[dict[str, Any]],
        schema: dict[str, str] | None = None,
    ) -> None:
        if not rows:
            return
        df = pd.DataFrame(rows)
        engine = create_engine(self.url)
        try:
            df.to_sql(
                name=self.table,
                con=engine,
                schema=self.pg_schema,
                if_exists="append",
                index=False,
                method="multi",
            )
        finally:
            engine.dispose()
