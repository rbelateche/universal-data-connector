"""Source-level mapping operations, shared by the API and the demo tooling."""

from typing import Any

from udc.core.sampler import ColumnStats, SchemaSampler
from udc.core.source_store import Source
from udc.mapper.canonical import CANONICAL_SCHEMAS, get_fields
from udc.mapper.mapper import SchemaMapper
from udc.mapper.models import FieldMapping, MappingResult
from udc.mapper.prompt import ALLOWED_TRANSFORMS
from udc.mapper.store import MappingStore


class DecisionError(ValueError):
    """A review decision that cannot be applied, with a message saying why."""


def stats_for_source(source: Source) -> dict[str, ColumnStats]:
    """Column statistics for the prompt, covering every field of the source.

    Fields without sample values (declared only) are described by their
    declared type so the LLM still sees them.
    """
    stats = SchemaSampler().run(source.sample_rows) if source.sample_rows else {}
    declared = {f.name: f.type for f in source.fields}
    for name in source.field_names:
        if name not in stats:
            stats[name] = ColumnStats(
                name=name,
                inferred_type=declared.get(name, "unknown"),
                null_count=0,
                null_pct=0.0,
                distinct_count=0,
                min_value=None,
                max_value=None,
                sample_values=[],
            )
    return stats


def infer_mapping(source: Source, mapper: SchemaMapper, store: MappingStore) -> int:
    """Run LLM inference for *source*, save it, and keep earlier human decisions.

    Returns the new mapping id.
    """
    previous_id = store.latest_for_source(source.source_id)
    result = mapper.infer(
        stats=stats_for_source(source),
        target_schema=CANONICAL_SCHEMAS[source.target_schema],
        source_id=source.source_id,
        target_schema_name=source.target_schema,
    )
    mapping_id = store.save(result)
    if previous_id is not None:
        carry_over_decisions(store.load(previous_id), mapping_id, store)
    return mapping_id


def carry_over_decisions(previous: MappingResult, new_id: int, store: MappingStore) -> None:
    """Re-apply reviewer decisions from *previous* onto mapping *new_id*.

    Accepted and edited mappings are kept as decided. A rejection is kept only
    while the new proposal is the same one that was rejected.
    """
    new_targets = {m.source_col: m.target_col for m in store.load(new_id).mappings}
    for m in previous.mappings:
        if m.status in ("accepted", "edited"):
            store.apply_override(
                new_id,
                m.source_col,
                {
                    "status": m.status,
                    "target_col": m.target_col,
                    "transform": m.transform,
                    "value_map": m.value_map,
                },
            )
        elif m.status == "rejected" and new_targets.get(m.source_col) == m.target_col:
            store.apply_override(new_id, m.source_col, {"status": "rejected"})


def decide(
    store: MappingStore,
    mapping_id: int,
    source: Source,
    source_col: str,
    status: str,
    target_col: str | None = None,
    transform: str | None = None,
    value_map: dict[str, Any] | None = None,
) -> FieldMapping:
    """Record a reviewer decision for one source column and return the result.

    Raises KeyError for an unknown column and DecisionError for a decision that
    doesn't make sense (both carry a message meant for the caller).
    """
    result = store.load(mapping_id)
    current = next((m for m in result.mappings if m.source_col == source_col), None)
    known_cols = source.field_names
    if current is None and source_col not in known_cols:
        raise KeyError(
            f"{source.source_id} has no field {source_col!r}. Fields: {', '.join(known_cols)}."
        )

    valid_targets = [f.path for f in get_fields(source.target_schema)]
    if target_col is not None and target_col not in valid_targets:
        raise DecisionError(
            f"{target_col!r} is not a {source.target_schema} field. "
            f"Valid fields: {', '.join(valid_targets)}."
        )
    if transform is not None and transform not in ALLOWED_TRANSFORMS:
        raise DecisionError(
            f"Unknown transformation {transform!r}. Use one of: {', '.join(ALLOWED_TRANSFORMS)}."
        )

    patch: dict[str, Any] = {"status": status}
    if status == "rejected":
        if current is None:
            raise DecisionError(f"{source_col} has no proposed mapping to reject.")
    elif status == "accepted":
        # Accepting a drop is allowed: it confirms the column stays out.
        if current is None:
            raise DecisionError(
                f"{source_col} has no proposed target to accept. "
                "Use status 'edited' with a target field to map it."
            )
        changed = (target_col not in (None, current.target_col)) or (
            transform not in (None, current.transform)
        )
        if changed:
            patch["status"] = "edited"
    elif status == "edited":
        if target_col is None and (current is None or current.transform == "drop"):
            raise DecisionError(f"Editing {source_col} needs a target field.")
        if target_col is None and transform is None and value_map is None:
            raise DecisionError(
                "An edit must change something: give a target field and/or a transformation."
            )
    else:
        raise DecisionError(f"Unknown status {status!r}. Use accepted, rejected or edited.")

    if target_col is not None:
        patch["target_col"] = target_col
    if transform is not None:
        patch["transform"] = transform
    if value_map is not None:
        patch["value_map"] = value_map
    effective_transform = transform or (current.transform if current else "rename")
    effective_map = value_map if value_map is not None else (current.value_map if current else {})
    if patch["status"] != "rejected" and effective_transform == "map_values" and not effective_map:
        raise DecisionError("The map_values transformation needs a value_map.")
    # Giving a target to a column the mapper wanted to drop maps it as is.
    if (
        current is not None
        and current.transform == "drop"
        and transform is None
        and patch["status"] == "edited"
        and "target_col" in patch
    ):
        patch["transform"] = "rename"

    store.apply_override(mapping_id, source_col, patch)
    updated = store.load(mapping_id)
    return next(m for m in updated.mappings if m.source_col == source_col)
