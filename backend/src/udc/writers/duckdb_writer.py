"""DuckDB writer — appends rows to a local DuckDB table."""

from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from udc.core._utils import validate_identifier
from udc.writers.base import BaseWriter


class DuckDBWriter(BaseWriter):
    """
    Write rows to a named table in a DuckDB file.

    Creates the table on the first write; appends on subsequent writes.
    """

    def __init__(self, db_path: str | Path, table: str) -> None:
        self.db_path = str(Path(db_path).resolve())
        self.table = validate_identifier(table, "table")

    def write(
        self,
        rows: list[dict[str, Any]],
        schema: dict[str, str] | None = None,
    ) -> None:
        if not rows:
            return
        df = pd.DataFrame(rows)
        with duckdb.connect(self.db_path) as conn:
            conn.register("_write_df", df)
            conn.execute(
                f"CREATE TABLE IF NOT EXISTS {self.table} AS SELECT * FROM _write_df LIMIT 0"
            )
            conn.execute(f"INSERT INTO {self.table} SELECT * FROM _write_df")
