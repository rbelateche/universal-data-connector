"""Schema sampler — computes per-column statistics from raw rows."""

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ColumnStats:
    name: str
    inferred_type: str
    null_count: int
    null_pct: float          # 0.0 – 1.0
    distinct_count: int
    min_value: Any
    max_value: Any
    sample_values: list[Any] = field(default_factory=list)


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")


class SchemaSampler:
    """
    Compute per-column statistics from a list of row dicts.

    Works with the output of any connector's ``sample()`` call::

        with CsvConnector("data.csv") as conn:
            rows = conn.sample(200)

        stats = SchemaSampler().run(rows)
        for col, s in stats.items():
            print(col, s.inferred_type, f"{s.null_pct:.0%} nulls")
    """

    def run(self, rows: list[dict[str, Any]]) -> dict[str, ColumnStats]:
        if not rows:
            return {}

        columns = list(rows[0].keys())
        result: dict[str, ColumnStats] = {}

        for col in columns:
            values = [row.get(col) for row in rows]
            non_null = [v for v in values if v is not None]
            null_count = len(values) - len(non_null)
            null_pct = null_count / len(values) if values else 0.0
            distinct_count = len({self._key(v) for v in non_null})

            try:
                min_val: Any = min(non_null) if non_null else None
                max_val: Any = max(non_null) if non_null else None
            except TypeError:
                min_val = min(str(v) for v in non_null) if non_null else None
                max_val = max(str(v) for v in non_null) if non_null else None

            # Up to 5 distinct sample values, preserving insertion order
            seen: set[str] = set()
            samples: list[Any] = []
            for v in non_null:
                key = self._key(v)
                if key not in seen:
                    seen.add(key)
                    samples.append(v)
                if len(samples) >= 5:
                    break

            result[col] = ColumnStats(
                name=col,
                inferred_type=self._infer_type(non_null),
                null_count=null_count,
                null_pct=null_pct,
                distinct_count=distinct_count,
                min_value=min_val,
                max_value=max_val,
                sample_values=samples,
            )

        return result

    # ── type inference ────────────────────────────────────────────────────

    def _infer_type(self, values: list[Any]) -> str:
        if not values:
            return "unknown"
        first = values[0]
        if isinstance(first, bool):
            return "boolean"
        if isinstance(first, int):
            return "integer"
        if isinstance(first, float):
            return "float"
        if isinstance(first, dict | list):
            return "json"
        if isinstance(first, str):
            sample = values[:20]
            if all(self._is_integer(v) for v in sample):
                return "integer"
            if all(self._is_float(v) for v in sample):
                return "float"
            if all(self._is_date(v) for v in sample):
                return "datetime"
            return "string"
        return "string"

    @staticmethod
    def _is_integer(v: Any) -> bool:
        try:
            int(str(v))
            return True
        except (ValueError, TypeError):
            return False

    @staticmethod
    def _is_float(v: Any) -> bool:
        try:
            float(str(v))
            return True
        except (ValueError, TypeError):
            return False

    @staticmethod
    def _is_date(v: Any) -> bool:
        return isinstance(v, str) and bool(_DATE_RE.match(v))

    @staticmethod
    def _key(v: Any) -> str:
        try:
            return str(v)
        except Exception:
            return repr(v)
