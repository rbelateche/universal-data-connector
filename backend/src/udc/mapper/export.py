"""Export a reviewed mapping as code that runs outside UDC.

Formats:

- ``json``    — a portable mapping spec;
- ``dbt_sql`` — a dbt staging model (DuckDB / dbt-duckdb dialect);
- ``pyspark`` — a ``DataFrame -> DataFrame`` function.

Only mappings in state ``mapped`` (see udc.mapper.review) are exported. Every
canonical field becomes an output column; a field nothing maps to is emitted
as a typed NULL with a TODO so the gap stays visible. Nested paths become
snake_case columns: ``price.amount`` → ``price_amount``.

The SQL and PySpark expressions mirror udc.mapper.transform, so the generated
code gives the same values as UDC's own dry run.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from udc.core.source_store import Source
from udc.mapper.canonical import CanonicalField
from udc.mapper.models import FieldMapping, MappingResult
from udc.mapper.review import mapping_state

ExportFormat = Literal["json", "dbt_sql", "pyspark"]
EXPORT_FORMATS: tuple[str, ...] = ("json", "dbt_sql", "pyspark")

_DATE_FORMATS = [
    "%Y%m%d",
    "%Y-%m-%d",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d.%m.%Y",
]
_SQL_TYPES = {
    "TEXT": "varchar",
    "INTEGER": "bigint",
    "DECIMAL": "decimal(18, 2)",
    "FLOAT": "double",
    "BOOLEAN": "boolean",
    "TIMESTAMP": "timestamp",
}
_SPARK_TYPES = {
    "TEXT": "string",
    "INTEGER": "bigint",
    "DECIMAL": "decimal(18,2)",
    "FLOAT": "double",
    "BOOLEAN": "boolean",
    "TIMESTAMP": "timestamp",
}
_TRUE = ("true", "1", "yes", "y", "on")
_FALSE = ("false", "0", "no", "n", "off")
# Characters parse_decimal ignores (thousands separators), as a regex class.
_SEPARATORS_RE = "[ \\x{00A0}\\x{202F}']"


@dataclass
class ExportResult:
    format: str
    filename: str
    content: str
    warnings: list[str] = field(default_factory=list)


@dataclass
class _Plan:
    """Which source column feeds each canonical field."""

    columns: list[tuple[CanonicalField, FieldMapping | None]]
    date_formats: dict[str, str | None]
    warnings: list[str]
    pending: dict[str, str]  # target path → source column proposed but not reviewed


def column_name(path: str) -> str:
    return path.replace(".", "_")


def detect_date_format(values: list[Any]) -> str | None:
    """The first strftime format that parses every non-empty sample value."""
    samples = [str(v).strip() for v in values if v not in (None, "")]
    if not samples:
        return None
    for fmt in _DATE_FORMATS:
        try:
            for s in samples:
                datetime.strptime(s, fmt)
        except ValueError:
            continue
        return fmt
    return None


def _plan(source: Source, result: MappingResult, fields: list[CanonicalField]) -> _Plan:
    warnings: list[str] = []
    by_target: dict[str, FieldMapping] = {}
    pending: dict[str, str] = {}
    known = {f.path for f in fields}
    for m in result.mappings:
        state = mapping_state(m)
        if state == "needs_review" and m.transform == "drop":
            continue  # left out either way
        if state == "needs_review":
            pending.setdefault(m.target_col, m.source_col)
            warnings.append(
                f"{m.source_col} → {m.target_col} is pending review "
                f"({m.confidence:.0%}) and was left out."
            )
        elif state == "mapped" and m.target_col not in known:
            warnings.append(
                f"{m.source_col} → {m.target_col} was left out: {m.target_col} is not a "
                f"{result.target_schema_name} field."
            )
        elif state == "mapped":
            if m.target_col in by_target:
                warnings.append(
                    f"{m.target_col} is mapped from both {by_target[m.target_col].source_col} "
                    f"and {m.source_col}; only {by_target[m.target_col].source_col} is exported."
                )
            else:
                by_target[m.target_col] = m

    columns: list[tuple[CanonicalField, FieldMapping | None]] = []
    for f in fields:
        feeder = by_target.get(f.path)
        if feeder is None and f.required and f.path not in pending:
            warnings.append(f"Required field {f.path} has no source field; it is exported as NULL.")
        elif feeder is None and f.required:
            warnings.append(
                f"Required field {f.path} is exported as NULL until "
                f"{pending[f.path]} → {f.path} is reviewed."
            )
        columns.append((f, feeder))

    date_formats: dict[str, str | None] = {}
    for _, feeder in columns:
        if feeder is not None and feeder.transform == "parse_date":
            fmt = detect_date_format([r.get(feeder.source_col) for r in source.sample_rows])
            date_formats[feeder.source_col] = fmt
            if fmt is None:
                warnings.append(
                    f"Could not detect the date format of {feeder.source_col} from the sample "
                    "rows; the export falls back to a plain cast."
                )
    return _Plan(columns, date_formats, warnings, pending)


# ── JSON ──────────────────────────────────────────────────────────────────────


def _to_json(source: Source, mapping_id: int, schema: str, plan: _Plan) -> str:
    spec = {
        "source_id": source.source_id,
        "target_schema": schema,
        "mapping_id": mapping_id,
        "fields": [
            {
                "target": f.path,
                "required": f.required,
                "source": m.source_col if m else None,
                "transform": m.transform if m else None,
                "value_map": dict(m.value_map) if m else {},
                "date_format": plan.date_formats.get(m.source_col) if m else None,
                "status": m.status if m else None,
                "confidence": m.confidence if m else None,
            }
            for f, m in plan.columns
        ],
        "warnings": plan.warnings,
    }
    return json.dumps(spec, indent=2, ensure_ascii=False) + "\n"


# ── dbt SQL (DuckDB) ──────────────────────────────────────────────────────────


def _sql_literal(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return repr(value)
    return "'" + str(value).replace("'", "''") + "'"


def _sql_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _decimal_col(source_col: str) -> str:
    """Name of the helper column holding the separator-free text of *source_col*."""
    return f"{source_col}__num"


def _sql_numeric(expr: str, produced: str, target: CanonicalField) -> str:
    """Cast a numeric expression to the target's SQL type when they differ."""
    sql_type = _SQL_TYPES.get(target.type, "double")
    if target.type in ("INTEGER", "DECIMAL", "FLOAT") and sql_type != produced:
        return f"cast({expr} as {sql_type})"
    return expr


def _sql_expr(m: FieldMapping, target: CanonicalField, date_fmt: str | None) -> str:
    col = _sql_ident(m.source_col)
    sql_type = _SQL_TYPES.get(target.type, "varchar")
    t = m.transform
    if t == "rename":
        return f"cast({col} as varchar)" if target.type == "TEXT" else col
    if t == "cast_int":
        return _sql_numeric(f"cast({col} as bigint)", "bigint", target)
    if t == "cast_float":
        return _sql_numeric(f"cast({col} as double)", "double", target)
    if t == "parse_decimal":
        num = _sql_ident(_decimal_col(m.source_col))
        expr = (
            f"cast(case when regexp_matches({num}, ',[^.,]*$') "
            f"then replace(replace({num}, '.', ''), ',', '.') "
            f"else replace({num}, ',', '') end as double)"
        )
        return _sql_numeric(expr, "double", target)
    if t == "cast_bool":
        trues = ", ".join(_sql_literal(v) for v in _TRUE)
        falses = ", ".join(_sql_literal(v) for v in _FALSE)
        return (
            f"case when lower(trim(cast({col} as varchar))) in ({trues}) then true "
            f"when lower(trim(cast({col} as varchar))) in ({falses}) then false end"
        )
    if t == "parse_date":
        if date_fmt:
            return f"strptime(trim({col}), {_sql_literal(date_fmt)})"
        return f"cast({col} as timestamp)"
    if t == "map_values":
        whens = " ".join(
            f"when {_sql_literal(k)} then {_sql_literal(v)}" for k, v in m.value_map.items()
        )
        return f"case cast({col} as varchar) {whens} end"
    return f"cast(null as {sql_type})"


def _todo(f: CanonicalField, plan: _Plan) -> str:
    why = (
        f"{plan.pending[f.path]} is pending review" if f.path in plan.pending else "no source field"
    )
    return f"TODO: {why}" + (" (required)" if f.required else "")


def _to_dbt_sql(source: Source, mapping_id: int, schema: str, plan: _Plan) -> str:
    lines = [
        f"-- Generated by Universal Data Connector from mapping #{mapping_id}",
        f"-- Source: {source.source_id} ({source.name}) → {schema}",
        "-- Dialect: DuckDB (dbt-duckdb). Only reviewed or high-confidence mappings are applied.",
    ]
    if plan.warnings:
        lines.append("-- Warnings:")
        lines.extend(f"--   - {w}" for w in plan.warnings)
    lines += [
        "",
        "with source as (",
        f"    select * from {{{{ source('udc', '{source.source_id}') }}}}",
        "),",
        "",
    ]
    decimal_cols = [m.source_col for _, m in plan.columns if m and m.transform == "parse_decimal"]
    pattern = _SEPARATORS_RE.replace("'", "''")
    lines.append("prepared as (")
    if decimal_cols:
        lines.append(
            "    -- parse_decimal: drop spaces and apostrophes used as thousands separators"
        )
        lines.append("    select")
        lines.append("        *,")
        for i, c in enumerate(decimal_cols):
            sep = "," if i < len(decimal_cols) - 1 else ""
            lines.append(
                f"        regexp_replace(trim({_sql_ident(c)}), '{pattern}', '', 'g') "
                f"as {_sql_ident(_decimal_col(c))}{sep}"
            )
        lines.append("    from source")
    else:
        lines.append("    select * from source")
    lines += [")", "", "select"]
    select: list[tuple[str, str]] = []
    for f, m in plan.columns:
        alias = column_name(f.path)
        if m is None:
            expr = f"cast(null as {_SQL_TYPES.get(f.type, 'varchar')})"
            note = _todo(f, plan)
        else:
            expr = _sql_expr(m, f, plan.date_formats.get(m.source_col))
            note = f"{m.source_col}, {m.transform}"
        select.append((f"{expr} as {alias}", note))
    for i, (code, note) in enumerate(select):
        sep = "," if i < len(select) - 1 else ""
        lines.append(f"    {code}{sep}  -- {note}")
    lines += ["from prepared", ""]
    return "\n".join(lines)


# ── PySpark ───────────────────────────────────────────────────────────────────

_PARSE_DECIMAL_PY = '''

def _parse_decimal(c: Column) -> Column:
    """Same rule as UDC parse_decimal: the last , or . is the decimal separator."""
    cleaned = F.regexp_replace(F.trim(c), "[ \\u00a0\\u202f']", "")
    return (
        F.when(
            cleaned.rlike(",[^.,]*$"),
            F.regexp_replace(F.regexp_replace(cleaned, "\\\\.", ""), ",", "."),
        )
        .otherwise(F.regexp_replace(cleaned, ",", ""))
        .cast("double")
    )
'''


def _java_date_pattern(fmt: str) -> str:
    for py, java in (
        ("%Y", "yyyy"),
        ("%m", "MM"),
        ("%d", "dd"),
        ("%H", "HH"),
        ("%M", "mm"),
        ("%S", "ss"),
    ):
        fmt = fmt.replace(py, java)
    return fmt.replace("T", "'T'")


def _py_literal(value: object) -> str:
    return repr(value)


def _spark_expr(m: FieldMapping, target: CanonicalField, date_fmt: str | None) -> str:
    col = f"F.col({m.source_col!r})"
    spark_type = _SPARK_TYPES.get(target.type, "string")
    t = m.transform
    if t == "rename":
        return f'{col}.cast("string")' if target.type == "TEXT" else col
    numeric_target = target.type in ("INTEGER", "DECIMAL", "FLOAT")
    if t == "cast_int":
        expr = f'{col}.cast("bigint")'
        return f'{expr}.cast("{spark_type}")' if numeric_target and spark_type != "bigint" else expr
    if t in ("cast_float", "parse_decimal"):
        expr = f'{col}.cast("double")' if t == "cast_float" else f"_parse_decimal({col})"
        return f'{expr}.cast("{spark_type}")' if numeric_target and spark_type != "double" else expr
    if t == "cast_bool":
        low = f"F.lower(F.trim({col}.cast('string')))"
        return (
            f"F.when({low}.isin({', '.join(map(repr, _TRUE))}), F.lit(True))"
            f".when({low}.isin({', '.join(map(repr, _FALSE))}), F.lit(False))"
        )
    if t == "parse_date":
        if date_fmt:
            return f"F.to_timestamp(F.trim({col}), {_java_date_pattern(date_fmt)!r})"
        return f'{col}.cast("timestamp")'
    if t == "map_values":
        chain = "F"
        for k, v in m.value_map.items():
            chain += f"\n            .when({col}.cast('string') == {k!r}, F.lit({_py_literal(v)}))"
        return chain if m.value_map else f'F.lit(None).cast("{spark_type}")'
    return f'F.lit(None).cast("{spark_type}")'


def _to_pyspark(source: Source, mapping_id: int, schema: str, plan: _Plan) -> str:
    func = f"to_{schema.lower()}"
    header = [
        f'"""Generated by Universal Data Connector from mapping #{mapping_id}.',
        "",
        f"Source: {source.source_id} ({source.name}) → {schema}.",
        "Only reviewed or high-confidence mappings are applied.",
    ]
    if plan.warnings:
        header += ["", "Warnings:"] + [f"- {w}" for w in plan.warnings]
    header.append('"""')
    needs_decimal = any(m is not None and m.transform == "parse_decimal" for _, m in plan.columns)
    lines = [
        *header,
        "",
        "from pyspark.sql import Column, DataFrame",
        "from pyspark.sql import functions as F",
    ]
    if needs_decimal:
        lines.append(_PARSE_DECIMAL_PY.rstrip("\n"))
    lines += [
        "",
        "",
        f"def {func}(df: DataFrame) -> DataFrame:",
        f'    """Map the {source.source_id} source DataFrame to the {schema} core model."""',
        "    return df.select(",
    ]
    for f, m in plan.columns:
        alias = column_name(f.path)
        if m is None:
            note = f"  # {_todo(f, plan)}"
            expr = f'F.lit(None).cast("{_SPARK_TYPES.get(f.type, "string")}")'
        else:
            note = f"  # {m.source_col}, {m.transform}"
            expr = _spark_expr(m, f, plan.date_formats.get(m.source_col))
        lines.append(f"        ({expr}).alias({alias!r}),{note}")
    lines += ["    )", ""]
    return "\n".join(lines)


# ── entry point ───────────────────────────────────────────────────────────────


def export_mapping(
    source: Source,
    mapping_id: int,
    result: MappingResult,
    fields: list[CanonicalField],
    fmt: str,
) -> ExportResult:
    """Render *result* in format *fmt*. Raises ValueError for an unknown format."""
    plan = _plan(source, result, fields)
    schema = result.target_schema_name
    base = f"{source.source_id}_to_{schema.lower()}"
    if fmt == "json":
        content, filename = _to_json(source, mapping_id, schema, plan), f"{base}.json"
    elif fmt == "dbt_sql":
        content = _to_dbt_sql(source, mapping_id, schema, plan)
        filename = f"stg_{source.source_id}__{schema.lower()}.sql"
    elif fmt == "pyspark":
        content, filename = _to_pyspark(source, mapping_id, schema, plan), f"{base}.py"
    else:
        raise ValueError(f"Unknown export format {fmt!r}. Use one of: {', '.join(EXPORT_FORMATS)}.")
    return ExportResult(format=fmt, filename=filename, content=content, warnings=plan.warnings)
