"""Multi-source reconciliation — merge two sources mapped to the same schema."""

from typing import Any


class Reconciler:
    """
    Merges two lists of rows that have already been mapped to the same
    canonical schema, deduplicating on a shared key column.

    Strategies
    ----------
    - ``last_wins``  (default): if the same key appears in both sources,
      the row from *right* overwrites the row from *left*.
    - ``left_wins``:  row from *left* is kept when keys collide.
    - ``union``:      keep all rows from both sources; no dedup.

    Usage::

        reconciler = Reconciler(key="customer_id", strategy="last_wins")
        merged = reconciler.merge(pg_rows, csv_rows)
    """

    STRATEGIES = {"last_wins", "left_wins", "union"}

    def __init__(
        self,
        key: str,
        strategy: str = "last_wins",
    ) -> None:
        if strategy not in self.STRATEGIES:
            raise ValueError(f"Unknown strategy {strategy!r}. Choose from {self.STRATEGIES}.")
        self.key = key
        self.strategy = strategy

    def merge(
        self,
        left: list[dict[str, Any]],
        right: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Return merged + deduped rows."""
        if self.strategy == "union":
            return left + right

        # Index left rows by key
        index: dict[Any, dict[str, Any]] = {}
        for row in left:
            k = row.get(self.key)
            index[k] = row

        if self.strategy == "last_wins":
            for row in right:
                k = row.get(self.key)
                index[k] = row  # right overwrites left
        else:  # left_wins
            for row in right:
                k = row.get(self.key)
                if k not in index:
                    index[k] = row  # only add if key not already present

        return list(index.values())

    def stats(
        self,
        left: list[dict[str, Any]],
        right: list[dict[str, Any]],
    ) -> dict[str, int]:
        """Return counts before and after merge for observability."""
        merged = self.merge(left, right)
        left_keys = {r.get(self.key) for r in left}
        right_keys = {r.get(self.key) for r in right}
        return {
            "left_count": len(left),
            "right_count": len(right),
            "overlap_count": len(left_keys & right_keys),
            "merged_count": len(merged),
        }
