"""Review policy for inferred mappings.

The LLM proposes, a human decides the uncertain cases:

- a mapping a reviewer accepted or edited is **mapped**;
- a mapping a reviewer rejected is **rejected** (not applied);
- an untouched proposal counts as **mapped** when its confidence is at least
  ``REVIEW_THRESHOLD`` and **needs_review** below it;
- a proposal to drop a column is **dropped** once confident or accepted. A
  low-confidence drop also needs review: it is how the mapper says "I don't
  know where this goes" (e.g. a column whose meaning changes per row).

Everything that judges a mapping (coverage of required fields, validation,
export) goes through ``mapping_state`` so the rule lives in one place.
"""

from dataclasses import dataclass, field, replace
from typing import Any, Literal

from udc.core.sampler import SchemaSampler
from udc.mapper.canonical import CanonicalField
from udc.mapper.models import REVIEW_THRESHOLD, FieldMapping, MappingResult
from udc.mapper.transform import RowTransformer, _parse_decimal

MappingState = Literal["mapped", "needs_review", "rejected", "dropped"]
FieldStatus = Literal["mapped", "needs_review", "missing"]
Severity = Literal["error", "warning"]


def mapping_state(m: FieldMapping) -> MappingState:
    """Classify one mapping under the review policy."""
    if m.status == "rejected":
        return "rejected"
    if m.status == "proposed" and m.confidence < REVIEW_THRESHOLD:
        return "needs_review"
    return "dropped" if m.transform == "drop" else "mapped"


def effective_result(result: MappingResult) -> MappingResult:
    """Only the mappings that would be applied today (state ``mapped``)."""
    return replace(result, mappings=[m for m in result.mappings if mapping_state(m) == "mapped"])


# ── coverage ──────────────────────────────────────────────────────────────────


def field_statuses(result: MappingResult, fields: list[CanonicalField]) -> dict[str, FieldStatus]:
    """Status of every target field: mapped, needs_review (only a pending
    proposal targets it) or missing (nothing targets it)."""
    status: dict[str, FieldStatus] = {f.path: "missing" for f in fields}
    for m in result.mappings:
        # A drop never fills a field, whatever target_col the mapper wrote.
        if m.transform == "drop" or m.target_col not in status:
            continue
        state = mapping_state(m)
        if state == "mapped":
            status[m.target_col] = "mapped"
        elif state == "needs_review" and status[m.target_col] == "missing":
            status[m.target_col] = "needs_review"
    return status


@dataclass
class Coverage:
    required_total: int
    required_mapped: int
    missing_required: list[str]  # nothing maps to it
    pending_required: list[str]  # only a low-confidence proposal maps to it


def coverage(result: MappingResult, fields: list[CanonicalField]) -> Coverage:
    statuses = field_statuses(result, fields)
    required = [f.path for f in fields if f.required]
    return Coverage(
        required_total=len(required),
        required_mapped=sum(statuses[p] == "mapped" for p in required),
        missing_required=[p for p in required if statuses[p] == "missing"],
        pending_required=[p for p in required if statuses[p] == "needs_review"],
    )


# ── type compatibility ────────────────────────────────────────────────────────

_SAMPLER_TO_CANONICAL = {
    "integer": "INTEGER",
    "float": "FLOAT",
    "datetime": "TIMESTAMP",
    "boolean": "BOOLEAN",
}
_NUMERIC = {"INTEGER", "FLOAT", "DECIMAL"}
_PRODUCES = {
    "cast_int": "INTEGER",
    "cast_float": "FLOAT",
    "parse_decimal": "FLOAT",
    "cast_bool": "BOOLEAN",
    "parse_date": "TIMESTAMP",
}


def _map_values_type(value_map: dict[str, object]) -> str:
    values = list(value_map.values())
    if values and all(isinstance(v, bool) for v in values):
        return "BOOLEAN"
    if values and all(isinstance(v, int) and not isinstance(v, bool) for v in values):
        return "INTEGER"
    if values and all(isinstance(v, int | float) and not isinstance(v, bool) for v in values):
        return "FLOAT"
    return "TEXT"


def produced_type(m: FieldMapping, source_type: str) -> str:
    """Canonical type a mapping's transform produces."""
    if m.transform == "rename":
        return _SAMPLER_TO_CANONICAL.get(source_type, "TEXT")
    if m.transform == "map_values":
        return _map_values_type(m.value_map)
    return _PRODUCES.get(m.transform, "TEXT")


def type_problem(m: FieldMapping, target_type: str, source_type: str) -> str | None:
    """Explain why *m* cannot feed a *target_type* field, or None if it can."""
    if m.transform == "drop":
        return None
    produces = produced_type(m, source_type)
    if target_type == "TEXT":
        # rename keeps the raw (string) value, so any source type is fine.
        if m.transform == "rename" or produces == "TEXT":
            return None
        if produces in _NUMERIC:
            return (
                f"{m.transform} turns {m.source_col} into a number, but {m.target_col} is "
                "text: leading zeros and formatting would be lost. Use rename."
            )
        return f"{m.transform} produces {produces}, but {m.target_col} is TEXT. Use rename."
    if target_type in _NUMERIC and produces in _NUMERIC:
        return None
    if produces == target_type:
        return None
    hint = {
        "TIMESTAMP": " Use parse_date.",
        "BOOLEAN": " Use cast_bool or map_values.",
        "INTEGER": " Use cast_int or parse_decimal.",
        "DECIMAL": " Use parse_decimal.",
        "FLOAT": " Use cast_float or parse_decimal.",
    }.get(target_type, "")
    return f"{m.transform} produces {produces}, but {m.target_col} expects {target_type}.{hint}"


# ── validation ────────────────────────────────────────────────────────────────


@dataclass
class Issue:
    severity: Severity
    code: str  # UNMAPPED_REQUIRED | PENDING_REVIEW | TYPE_MISMATCH | TRANSFORM_FAILED
    #            | DUPLICATE_TARGET | UNKNOWN_TARGET
    field: str  # target field path, or source column for source-side issues
    message: str


@dataclass
class ValidationReport:
    issues: list[Issue]
    rows_tested: int
    rows_ok: int
    preview: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)


def nest(row: dict[str, Any]) -> dict[str, Any]:
    """Turn dotted keys into nested objects: {"price.amount": 1} → {"price": {"amount": 1}}."""
    out: dict[str, Any] = {}
    for key, value in row.items():
        node = out
        *parents, leaf = key.split(".")
        for p in parents:
            node = node.setdefault(p, {})
        node[leaf] = value
    return out


def _decimal_rescues(values: list[Any]) -> bool:
    try:
        for v in values:
            _parse_decimal(v, "")
    except Exception:
        return False
    return True


def validate(
    result: MappingResult,
    fields: list[CanonicalField],
    sample_rows: list[dict[str, Any]],
    sample_limit: int = 5,
) -> ValidationReport:
    """Check a mapping against its target schema and dry-run it on sample rows."""
    issues: list[Issue] = []
    by_path = {f.path: f for f in fields}
    source_types = {c: s.inferred_type for c, s in SchemaSampler().run(sample_rows).items()}

    # Per-mapping checks
    for m in result.mappings:
        state = mapping_state(m)
        if state in ("rejected", "dropped"):
            continue
        if m.transform == "drop":  # a pending drop: nothing to type-check
            issues.append(
                Issue(
                    "warning",
                    "PENDING_REVIEW",
                    m.source_col,
                    f"The mapper proposes not to map {m.source_col} ({m.confidence:.0%} "
                    "confidence). Accept to leave it out, or edit it to map it.",
                )
            )
            continue
        target = by_path.get(m.target_col)
        if target is None:
            issues.append(
                Issue(
                    "error",
                    "UNKNOWN_TARGET",
                    m.source_col,
                    f"{m.source_col} maps to {m.target_col!r}, which is not a "
                    f"{result.target_schema_name} field. Valid fields: {', '.join(by_path)}.",
                )
            )
            continue
        problem = type_problem(m, target.type, source_types.get(m.source_col, "unknown"))
        if problem:
            issues.append(Issue("error", "TYPE_MISMATCH", m.target_col, problem))
        if state == "needs_review":
            issues.append(
                Issue(
                    "error" if target.required else "warning",
                    "PENDING_REVIEW",
                    m.target_col,
                    f"{m.source_col} → {m.target_col} was proposed at {m.confidence:.0%} "
                    "confidence and needs a decision: accept, reject or edit it.",
                )
            )

    # Two applied mappings writing the same field
    writers: dict[str, list[str]] = {}
    for m in effective_result(result).mappings:
        if m.target_col in by_path:
            writers.setdefault(m.target_col, []).append(m.source_col)
    for target_col, cols in writers.items():
        if len(cols) > 1:
            issues.append(
                Issue(
                    "error",
                    "DUPLICATE_TARGET",
                    target_col,
                    f"{target_col} is mapped from {len(cols)} source fields "
                    f"({', '.join(cols)}). Keep one and reject the others.",
                )
            )

    # Required fields nothing maps to (pending ones are reported above)
    statuses = field_statuses(result, fields)
    for f in fields:
        if f.required and statuses[f.path] == "missing":
            issues.append(
                Issue(
                    "error",
                    "UNMAPPED_REQUIRED",
                    f.path,
                    f"Required field {f.path} has no source field here. Map a source field "
                    "to it (edit that field's target) or take it from another source.",
                )
            )

    # Dry run on sample rows, applied mappings only
    rows = sample_rows[: max(sample_limit, 0)]
    out_rows, errors = RowTransformer(effective_result(result)).transform_with_errors(rows)
    failed_by_col: dict[str, list[Any]] = {}
    targets: dict[str, str] = {}
    for e in errors:
        failed_by_col.setdefault(e.source_col, []).append(e.value)
        targets[e.source_col] = e.target_col
    transforms = {m.source_col: m.transform for m in result.mappings}
    for col, values in failed_by_col.items():
        hint = ""
        if transforms.get(col) != "parse_decimal" and _decimal_rescues(values):
            hint = " parse_decimal reads these values."
        issues.append(
            Issue(
                "error",
                "TRANSFORM_FAILED",
                targets[col],
                f"{col} → {targets[col]}: {transforms.get(col)} failed on "
                f"{len(values)} of {len(rows)} sample rows (e.g. {values[0]!r}).{hint}",
            )
        )
    failed_rows = {e.row_index for e in errors}

    return ValidationReport(
        issues=issues,
        rows_tested=len(rows),
        rows_ok=len(rows) - len(failed_rows),
        preview=[nest(r) for r in out_rows[:3]],
    )
