"""Type coercion engine — applies FieldMapping transforms to rows.

Claude specifies *what* to do; this module *executes* it safely.
Claude never runs code — it only picks from the ALLOWED_TRANSFORMS whitelist.
"""

from datetime import datetime
from typing import Any

from udc.mapper.models import FieldMapping, MappingResult


class TransformError(Exception):
    """Raised when a value cannot be coerced with the requested transform."""


def _cast_int(value: Any, col: str) -> int:
    try:
        return int(value)
    except (ValueError, TypeError) as exc:
        raise TransformError(f"Cannot cast {value!r} to int for column {col!r}") from exc


def _cast_float(value: Any, col: str) -> float:
    try:
        return float(value)
    except (ValueError, TypeError) as exc:
        raise TransformError(f"Cannot cast {value!r} to float for column {col!r}") from exc


def _cast_bool(value: Any, col: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    s = str(value).strip().lower()
    if s in {"true", "1", "yes", "y", "on"}:
        return True
    if s in {"false", "0", "no", "n", "off"}:
        return False
    raise TransformError(f"Cannot cast {value!r} to bool for column {col!r}")


_DATE_FORMATS = [
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%m/%d/%Y",
]


def _parse_date(value: Any, col: str) -> datetime:
    if isinstance(value, datetime):
        return value
    s = str(value).strip()
    # Try fromisoformat first (handles fractional seconds, timezone offsets)
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        pass
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise TransformError(f"Cannot parse {value!r} as a date for column {col!r}")


def _apply_single(
    mapping: FieldMapping,
    value: Any,
) -> Any:
    """Apply one transform to one value. Returns the transformed value."""
    t = mapping.transform
    col = mapping.source_col

    if t == "rename":
        return value
    if t == "cast_int":
        return _cast_int(value, col)
    if t == "cast_float":
        return _cast_float(value, col)
    if t == "cast_bool":
        return _cast_bool(value, col)
    if t == "parse_date":
        return _parse_date(value, col)
    if t == "map_values":
        key = str(value)
        if key not in mapping.value_map:
            raise TransformError(
                f"Value {value!r} not in value_map for column {col!r}. "
                f"Known keys: {list(mapping.value_map)}"
            )
        return mapping.value_map[key]
    if t == "drop":
        # Caller skips drop mappings; this path should not be reached
        return None
    raise TransformError(f"Unknown transform {t!r} for column {col!r}")


class RowTransformer:
    """
    Applies a MappingResult to batches of raw rows.

    Usage::

        transformer = RowTransformer(mapping_result)
        clean_rows = transformer.transform(raw_rows)
    """

    def __init__(self, result: MappingResult) -> None:
        # Pre-index mappings by source_col for O(1) lookup per row
        self._active = {m.source_col: m for m in result.mappings if m.transform != "drop"}

    def transform(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return a new list of rows with all transforms applied."""
        return [self._transform_row(row) for row in rows]

    def _transform_row(self, row: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for src_col, mapping in self._active.items():
            raw = row.get(src_col)
            if raw is None:
                out[mapping.target_col] = None
            else:
                out[mapping.target_col] = _apply_single(mapping, raw)
        return out
