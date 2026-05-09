"""Tests for RowTransformer and individual transform functions."""

import pytest

from udc.mapper.models import FieldMapping, MappingResult
from udc.mapper.transform import RowTransformer, TransformError


def _result(mappings: list[FieldMapping]) -> MappingResult:
    return MappingResult(
        source_id="test",
        target_schema_name="Contact",
        mappings=mappings,
        unmapped_source=[],
        unmapped_target=[],
    )


def _mapping(src: str, tgt: str, transform: str, **kwargs: object) -> FieldMapping:
    return FieldMapping(
        source_col=src,
        target_col=tgt,
        transform=transform,
        confidence=1.0,
        reasoning="test",
        value_map=kwargs.get("value_map", {}),  # type: ignore[arg-type]
    )


# ── rename ────────────────────────────────────────────────────────────────────

def test_rename() -> None:
    result = _result([_mapping("full_nm", "full_name", "rename")])
    rows = RowTransformer(result).transform([{"full_nm": "Alice"}])
    assert rows == [{"full_name": "Alice"}]


# ── cast_int ──────────────────────────────────────────────────────────────────

def test_cast_int_from_string() -> None:
    result = _result([_mapping("cust_id", "customer_id", "cast_int")])
    rows = RowTransformer(result).transform([{"cust_id": "42"}])
    assert rows[0]["customer_id"] == 42


def test_cast_int_from_float() -> None:
    result = _result([_mapping("cust_id", "customer_id", "cast_int")])
    rows = RowTransformer(result).transform([{"cust_id": 3.9}])
    assert rows[0]["customer_id"] == 3


def test_cast_int_fails() -> None:
    result = _result([_mapping("cust_id", "customer_id", "cast_int")])
    with pytest.raises(TransformError):
        RowTransformer(result).transform([{"cust_id": "not-a-number"}])


# ── cast_float ────────────────────────────────────────────────────────────────

def test_cast_float_from_string() -> None:
    result = _result([_mapping("rev", "revenue_usd", "cast_float")])
    rows = RowTransformer(result).transform([{"rev": "99.9"}])
    assert rows[0]["revenue_usd"] == pytest.approx(99.9)


def test_cast_float_fails() -> None:
    result = _result([_mapping("rev", "revenue_usd", "cast_float")])
    with pytest.raises(TransformError):
        RowTransformer(result).transform([{"rev": "abc"}])


# ── cast_bool ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    (True, True), (False, False),
    ("true", True), ("false", False),
    ("yes", True), ("no", False),
    ("Y", True), ("N", False),
    ("1", True), ("0", False),
])
def test_cast_bool_truthy(raw: object, expected: bool) -> None:
    result = _result([_mapping("actv", "is_active", "cast_bool")])
    rows = RowTransformer(result).transform([{"actv": raw}])
    assert rows[0]["is_active"] is expected


def test_cast_bool_fails() -> None:
    result = _result([_mapping("actv", "is_active", "cast_bool")])
    with pytest.raises(TransformError):
        RowTransformer(result).transform([{"actv": "maybe"}])


# ── parse_date ────────────────────────────────────────────────────────────────

def test_parse_date_iso() -> None:
    from datetime import datetime

    result = _result([_mapping("dt", "created_at", "parse_date")])
    rows = RowTransformer(result).transform([{"dt": "2024-01-15T10:30:00"}])
    assert isinstance(rows[0]["created_at"], datetime)
    assert rows[0]["created_at"].year == 2024


def test_parse_date_simple() -> None:
    result = _result([_mapping("dt", "created_at", "parse_date")])
    rows = RowTransformer(result).transform([{"dt": "2024-06-01"}])
    assert rows[0]["created_at"].month == 6


def test_parse_date_fails() -> None:
    result = _result([_mapping("dt", "created_at", "parse_date")])
    with pytest.raises(TransformError):
        RowTransformer(result).transform([{"dt": "not-a-date"}])


# ── map_values ────────────────────────────────────────────────────────────────

def test_map_values() -> None:
    fm = _mapping("actv", "is_active", "map_values", value_map={"Y": True, "N": False})
    result = _result([fm])
    rows = RowTransformer(result).transform([{"actv": "Y"}, {"actv": "N"}])
    assert rows[0]["is_active"] is True
    assert rows[1]["is_active"] is False


def test_map_values_unknown_key_raises() -> None:
    fm = _mapping("actv", "is_active", "map_values", value_map={"Y": True})
    result = _result([fm])
    with pytest.raises(TransformError, match="not in value_map"):
        RowTransformer(result).transform([{"actv": "X"}])


# ── drop ──────────────────────────────────────────────────────────────────────

def test_drop_removes_column() -> None:
    mappings = [
        _mapping("id", "customer_id", "rename"),
        _mapping("internal_flag", "internal_flag", "drop"),
    ]
    result = _result(mappings)
    rows = RowTransformer(result).transform([{"id": 1, "internal_flag": "secret"}])
    assert "internal_flag" not in rows[0]
    assert rows[0]["customer_id"] == 1


# ── null passthrough ──────────────────────────────────────────────────────────

def test_null_value_passes_through() -> None:
    result = _result([_mapping("email", "email", "rename")])
    rows = RowTransformer(result).transform([{"email": None}])
    assert rows[0]["email"] is None


# ── multiple mappings ─────────────────────────────────────────────────────────

def test_multiple_mappings() -> None:
    mappings = [
        _mapping("cust_id", "customer_id", "cast_int"),
        _mapping("full_nm", "full_name", "rename"),
        _mapping("rev", "revenue_usd", "cast_float"),
    ]
    result = _result(mappings)
    raw = [{"cust_id": "1", "full_nm": "Alice", "rev": "99.5"}]
    rows = RowTransformer(result).transform(raw)
    assert rows[0] == {"customer_id": 1, "full_name": "Alice", "revenue_usd": 99.5}
