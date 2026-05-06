"""Abstract base class for all data source connectors."""

from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Any


class BaseConnector(ABC):
    """
    Common interface every connector must implement.

    Typical usage::

        with PostgresConnector(url="...", table="orders") as conn:
            rows = conn.sample(100)
            schema = conn.get_schema()
    """

    @abstractmethod
    def connect(self) -> None:
        """Open the connection to the data source."""

    @abstractmethod
    def sample(self, n: int = 100) -> list[dict[str, Any]]:
        """Return up to *n* rows as a list of plain dicts."""

    @abstractmethod
    def stream(
        self,
        batch_size: int = 1000,
        watermark_col: str | None = None,
        watermark_val: Any = None,
    ) -> Iterator[list[dict[str, Any]]]:
        """
        Yield batches of rows.

        If *watermark_col* and *watermark_val* are provided, only rows where
        ``watermark_col > watermark_val`` are returned (incremental sync).
        """

    @abstractmethod
    def get_schema(self) -> dict[str, str]:
        """Return a mapping of ``column_name → type_string``."""

    @abstractmethod
    def close(self) -> None:
        """Close the connection and release resources."""

    # ── context manager ───────────────────────────────────────────────────

    def __enter__(self) -> "BaseConnector":
        self.connect()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
