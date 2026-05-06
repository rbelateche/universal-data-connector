"""Writers package — output adapters."""

from udc.writers.base import BaseWriter
from udc.writers.duckdb_writer import DuckDBWriter
from udc.writers.parquet import ParquetWriter
from udc.writers.postgres_writer import PostgresWriter

__all__ = ["BaseWriter", "DuckDBWriter", "ParquetWriter", "PostgresWriter"]
