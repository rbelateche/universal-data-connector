"""Parquet writer backed by pandas + pyarrow."""

from pathlib import Path
from typing import Any

import pandas as pd

from udc.writers.base import BaseWriter


class ParquetWriter(BaseWriter):
    """Write rows to a Parquet file (snappy-compressed by default)."""

    def __init__(self, path: str | Path, compression: str = "snappy") -> None:
        self.path = Path(path)
        self.compression = compression

    def write(
        self,
        rows: list[dict[str, Any]],
        schema: dict[str, str] | None = None,
    ) -> None:
        if not rows:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_parquet(self.path, index=False, compression=self.compression)
