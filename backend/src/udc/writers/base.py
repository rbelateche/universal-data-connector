"""Abstract base class for all output writers."""

from abc import ABC, abstractmethod
from typing import Any


class BaseWriter(ABC):
    @abstractmethod
    def write(
        self,
        rows: list[dict[str, Any]],
        schema: dict[str, str] | None = None,
    ) -> None:
        """Write *rows* to the destination. *schema* is optional metadata."""
