"""Tests for mapping export (JSON spec, dbt SQL, PySpark)."""

import json
from datetime import datetime
from typing import Any

import duckdb
import pytest

from udc.core.source_store import Source
from udc.mapper.canonical import get_fields
from udc.mapper.export import detect_date_format, export_mapping
from udc.mapper.models import FieldMapping, MappingResult
from udc.mapper.review import effective_result
from udc.mapper.transform import RowTransformer

ROWS = [
    {
        "MATNR": "000000010001234",
        "MAKTX": "Sac Lune cuir grainé",
        "MATKL": "BAGS",
        "NETPR": "1.250,00",
        "WAERS": "EUR",
        "LABST": "12.000",
        "ERSDA": "20260315",
        "COLOR": "NR",
    },
    {
        "MATNR": "000000010001235",
        "MAKTX": "Foulard l'Orage",
        "MATKL": "ACCS",
        "NETPR": "390,00",
        "WAERS": "EUR",
        "LABST": "40.000",
        "ERSDA": "20260402",
        "COLOR": "IV",
    },
]
SOURCE = Source("erp", "SAP ERP material export", "erp", "Product", [], ROWS)


def _reviewed() -> MappingResult:
    return MappingResult(
        source_id="erp",
        target_schema_name="Product",
        mappings=[
            FieldMapping("MATNR", "sku", "rename", 0.9, "", {}, "accepted"),
            FieldMapping("MAKTX", "name", "rename", 0.85, ""),
            FieldMapping("MATKL", "category", "rename", 0.55, ""),  # pending → excluded
            FieldMapping("NETPR", "price.amount", "parse_decimal", 0.9, "", {}, "edited"),
            FieldMapping("WAERS", "price.currency", "rename", 0.95, ""),
            FieldMapping("LABST", "stock_quantity", "parse_decimal", 0.8, "", {}, "edited"),
            FieldMapping("ERSDA", "created_at", "parse_date", 0.75, ""),
            FieldMapping(
                "COLOR", "color", "map_values", 0.8, "", {"NR": "Black", "IV": "Ivory"}, "accepted"
            ),
        ],
        unmapped_source=[],
        unmapped_target=[],
    )


def _export(fmt: str) -> Any:
    return export_mapping(SOURCE, 7, _reviewed(), get_fields("Product"), fmt)


def test_detect_date_format() -> None:
    assert detect_date_format(["20260315", "20260402"]) == "%Y%m%d"
    assert detect_date_format(["2026-03-15", None]) == "%Y-%m-%d"
    assert detect_date_format(["15.03.2026"]) == "%d.%m.%Y"
    assert detect_date_format(["soon"]) is None


def test_warnings_flag_pending_and_missing_required() -> None:
    warnings = _export("json").warnings
    assert any("MATKL → category is pending review" in w for w in warnings)
    assert any("Required field brand" in w for w in warnings)
    assert any("category is exported as NULL until MATKL → category" in w for w in warnings)


def test_json_spec_lists_every_field() -> None:
    spec = json.loads(_export("json").content)
    fields = {f["target"]: f for f in spec["fields"]}
    assert len(fields) == 11
    assert fields["price.amount"]["transform"] == "parse_decimal"
    assert fields["created_at"]["date_format"] == "%Y%m%d"
    assert fields["brand"]["source"] is None
    assert fields["category"]["source"] is None  # pending, not exported


def test_dbt_sql_matches_python_dry_run() -> None:
    """Run the generated model in DuckDB and compare with UDC's own transforms."""
    exported = _export("dbt_sql")
    assert exported.filename == "stg_erp__product.sql"
    sql = exported.content.replace("{{ source('udc', 'erp') }}", "erp_raw")

    con = duckdb.connect()
    cols = list(ROWS[0])
    con.execute(f"create table erp_raw ({', '.join(f'{c} varchar' for c in cols)})")
    con.executemany(
        f"insert into erp_raw values ({', '.join('?' for _ in cols)})",
        [[r[c] for c in cols] for r in ROWS],
    )
    rel = con.execute(sql)
    names = [d[0] for d in rel.description]
    sql_rows = [dict(zip(names, row, strict=True)) for row in rel.fetchall()]

    python_rows = RowTransformer(effective_result(_reviewed())).transform(ROWS)
    for sql_row, py_row in zip(sql_rows, python_rows, strict=True):
        for target, value in py_row.items():
            got = sql_row[target.replace(".", "_")]
            if isinstance(value, float):
                assert float(got) == pytest.approx(value), target
            else:
                assert got == value, target
        assert sql_row["brand"] is None
        assert sql_row["category"] is None
    assert sql_rows[0]["created_at"] == datetime(2026, 3, 15)
    assert sql_rows[1]["color"] == "Ivory"


def test_parse_decimal_sql_matches_python_on_tricky_values() -> None:
    values = ["1.250,00", "1,250.00", "1250,5", "12.000", " 89.9 ", "1'250.00", "1 250,00"]
    source = Source("s", "s", "", "Product", [], [{"p": v} for v in values])
    result = MappingResult(
        "s",
        "Product",
        [FieldMapping("p", "price.amount", "parse_decimal", 1.0, "", {}, "accepted")],
        [],
        [],
    )
    sql = export_mapping(source, 1, result, get_fields("Product"), "dbt_sql").content
    sql = sql.replace("{{ source('udc', 's') }}", "(select unnest(?::varchar[]) as p)")

    rel = duckdb.connect().execute(sql, [values])
    names = [d[0] for d in rel.description]
    got = [float(dict(zip(names, row, strict=True))["price_amount"]) for row in rel.fetchall()]

    expected = [r["price.amount"] for r in RowTransformer(result).transform(source.sample_rows)]
    assert got == pytest.approx(expected)


def test_pyspark_is_valid_python_with_the_right_calls() -> None:
    exported = _export("pyspark")
    assert exported.filename == "erp_to_product.py"
    code = exported.content
    compile(code, exported.filename, "exec")  # syntax check without pyspark installed
    assert "def to_product(df: DataFrame) -> DataFrame:" in code
    assert "def _parse_decimal(c: Column) -> Column:" in code
    assert "F.to_timestamp(F.trim(F.col('ERSDA')), 'yyyyMMdd')" in code
    assert ".alias('brand'),  # TODO: no source field (required)" in code
    assert ".alias('category'),  # TODO: MATKL is pending review (required)" in code
    assert "(_parse_decimal(F.col('LABST')).cast(\"bigint\")).alias('stock_quantity')" in code


def test_unknown_format_is_rejected() -> None:
    with pytest.raises(ValueError, match="dbt_sql"):
        _export("xml")
