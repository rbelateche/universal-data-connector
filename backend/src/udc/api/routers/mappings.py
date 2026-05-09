"""Mappings router — infer, retrieve, override, and apply schema mappings."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from udc.core.config import Settings, get_settings
from udc.core.sampler import ColumnStats, SchemaSampler
from udc.mapper.canonical import CANONICAL_SCHEMAS
from udc.mapper.mapper import SchemaMapper
from udc.mapper.reconcile import Reconciler
from udc.mapper.store import MappingStore
from udc.mapper.transform import RowTransformer

router = APIRouter(prefix="/mappings", tags=["mappings"])


# ── Request / Response models ─────────────────────────────────────────────────


class InferRequest(BaseModel):
    source_id: str
    target_schema_name: str  # must be a key in CANONICAL_SCHEMAS
    sample_rows: list[dict[str, Any]]  # raw rows from connector.sample()


class InferResponse(BaseModel):
    mapping_id: int
    source_id: str
    target_schema_name: str
    mappings: list[dict[str, Any]]
    unmapped_source: list[str]
    unmapped_target: list[str]
    needs_review: bool


class OverrideRequest(BaseModel):
    source_col: str
    patch: dict[str, Any]  # keys to override e.g. {"target_col": "...", "confidence": 1.0}


class ApplyRequest(BaseModel):
    mapping_id: int
    rows: list[dict[str, Any]]


class MergeRequest(BaseModel):
    left_rows: list[dict[str, Any]]
    right_rows: list[dict[str, Any]]
    key: str
    strategy: str = "last_wins"


# ── Shared DuckDB store (singleton per process) ───────────────────────────────

_STORE: MappingStore | None = None


def _get_store(settings: Settings = Depends(get_settings)) -> MappingStore:
    global _STORE
    if _STORE is None:
        _STORE = MappingStore(settings.duckdb_path)
    return _STORE


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/infer", response_model=InferResponse)
def infer_mapping(
    body: InferRequest,
    settings: Settings = Depends(get_settings),
    store: MappingStore = Depends(_get_store),
) -> InferResponse:
    """
    Sample the provided rows, call Claude, and persist the inferred mapping.
    Returns the mapping_id so subsequent calls can reference it.
    """
    if body.target_schema_name not in CANONICAL_SCHEMAS:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown schema {body.target_schema_name!r}. "
            f"Choose from: {list(CANONICAL_SCHEMAS)}",
        )

    target_schema = CANONICAL_SCHEMAS[body.target_schema_name]
    stats: dict[str, ColumnStats] = SchemaSampler().run(body.sample_rows)

    mapper = SchemaMapper(api_key=settings.anthropic_api_key)
    result = mapper.infer(
        stats=stats,
        target_schema=target_schema,
        source_id=body.source_id,
        target_schema_name=body.target_schema_name,
    )

    mapping_id = store.save(result)

    return InferResponse(
        mapping_id=mapping_id,
        source_id=result.source_id,
        target_schema_name=result.target_schema_name,
        mappings=[
            {
                "source_col": m.source_col,
                "target_col": m.target_col,
                "transform": m.transform,
                "confidence": m.confidence,
                "reasoning": m.reasoning,
                "value_map": m.value_map,
            }
            for m in result.mappings
        ],
        unmapped_source=result.unmapped_source,
        unmapped_target=result.unmapped_target,
        needs_review=result.needs_review,
    )


@router.get("/{mapping_id}", response_model=InferResponse)
def get_mapping(
    mapping_id: int,
    store: MappingStore = Depends(_get_store),
) -> InferResponse:
    """Retrieve a saved mapping (with any overrides applied)."""
    try:
        result = store.load(mapping_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return InferResponse(
        mapping_id=mapping_id,
        source_id=result.source_id,
        target_schema_name=result.target_schema_name,
        mappings=[
            {
                "source_col": m.source_col,
                "target_col": m.target_col,
                "transform": m.transform,
                "confidence": m.confidence,
                "reasoning": m.reasoning,
                "value_map": m.value_map,
            }
            for m in result.mappings
        ],
        unmapped_source=result.unmapped_source,
        unmapped_target=result.unmapped_target,
        needs_review=result.needs_review,
    )


@router.patch("/{mapping_id}/overrides")
def apply_override(
    mapping_id: int,
    body: OverrideRequest,
    store: MappingStore = Depends(_get_store),
) -> dict[str, str]:
    """Persist a human correction for one field in a saved mapping."""
    try:
        store.load(mapping_id)  # validate mapping exists
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    store.apply_override(mapping_id, body.source_col, body.patch)
    return {"status": "ok"}


@router.post("/apply")
def apply_mapping(
    body: ApplyRequest,
    store: MappingStore = Depends(_get_store),
) -> list[dict[str, Any]]:
    """Transform raw rows using a saved mapping. Returns clean, renamed rows."""
    try:
        result = store.load(body.mapping_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    transformer = RowTransformer(result)
    return transformer.transform(body.rows)


@router.post("/merge")
def merge_sources(body: MergeRequest) -> list[dict[str, Any]]:
    """Merge two pre-mapped row sets on a shared key column."""
    try:
        reconciler = Reconciler(key=body.key, strategy=body.strategy)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return reconciler.merge(body.left_rows, body.right_rows)
