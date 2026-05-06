"""Unit tests for SchemaSampler."""

from udc.core.sampler import ColumnStats, SchemaSampler


def test_empty_rows() -> None:
    assert SchemaSampler().run([]) == {}


def test_null_tracking() -> None:
    rows = [{"x": 1}, {"x": None}, {"x": 3}]
    stats = SchemaSampler().run(rows)
    assert stats["x"].null_count == 1
    assert abs(stats["x"].null_pct - 1 / 3) < 0.001


def test_infer_integer() -> None:
    rows = [{"n": i} for i in range(10)]
    stats = SchemaSampler().run(rows)
    assert stats["n"].inferred_type == "integer"


def test_infer_float() -> None:
    rows = [{"v": float(i) + 0.5} for i in range(5)]
    stats = SchemaSampler().run(rows)
    assert stats["v"].inferred_type == "float"


def test_infer_string() -> None:
    rows = [{"name": "Alice"}, {"name": "Bob"}]
    stats = SchemaSampler().run(rows)
    assert stats["name"].inferred_type == "string"


def test_infer_boolean() -> None:
    rows = [{"flag": True}, {"flag": False}]
    stats = SchemaSampler().run(rows)
    assert stats["flag"].inferred_type == "boolean"


def test_infer_datetime_string() -> None:
    rows = [{"ts": "2024-01-01T10:00:00"}, {"ts": "2024-06-15T00:00:00"}]
    stats = SchemaSampler().run(rows)
    assert stats["ts"].inferred_type == "datetime"


def test_infer_json() -> None:
    rows = [{"meta": {"k": "v"}}, {"meta": {"k": "w"}}]
    stats = SchemaSampler().run(rows)
    assert stats["meta"].inferred_type == "json"


def test_distinct_count() -> None:
    rows = [{"c": "a"}, {"c": "a"}, {"c": "b"}]
    stats = SchemaSampler().run(rows)
    assert stats["c"].distinct_count == 2


def test_sample_values_max_five() -> None:
    rows = [{"x": i} for i in range(20)]
    stats = SchemaSampler().run(rows)
    assert len(stats["x"].sample_values) == 5


def test_min_max() -> None:
    rows = [{"v": i} for i in range(1, 6)]
    stats = SchemaSampler().run(rows)
    assert stats["v"].min_value == 1
    assert stats["v"].max_value == 5


def test_all_nulls() -> None:
    rows = [{"x": None}, {"x": None}]
    stats = SchemaSampler().run(rows)
    assert stats["x"].null_pct == 1.0
    assert stats["x"].inferred_type == "unknown"
    assert stats["x"].min_value is None
