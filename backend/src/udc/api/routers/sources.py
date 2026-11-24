"""Sources router — register sources and review their mapping to a canonical schema.

These endpoints are keyed by ``source_id`` (the latest mapping of a source),
whereas ``/mappings`` works on individual inference runs by ``mapping_id``.
Error ``detail`` strings say what went wrong and what to do next, because the
caller is often an agent that has to recover on its own.
"""

from typing import Any, Literal

import anthropic
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from udc.api.dependencies import get_mapping_store, get_source_store
from udc.core.config import Settings, get_settings
from udc.core.source_store import Source, SourceField, SourceStore
from udc.mapper.canonical import CANONICAL_FIELDS, get_fields
from udc.mapper.export import export_mapping
from udc.mapper.mapper import SchemaMapper, describe_api_error
from udc.mapper.models import FieldMapping, MappingResult
from udc.mapper.review import coverage, field_statuses, mapping_state, validate
from udc.mapper.service import DecisionError, decide, infer_mapping
from udc.mapper.store import MappingStore

router = APIRouter(prefix="/sources", tags=["sources"])
coverage_router = APIRouter(tags=["sources"])

SOURCE_ID_PATTERN = r"^[a-z0-9][a-z0-9_-]{0,62}$"
MAX_SAMPLE_ROWS = 200

ReviewStatus = Literal["not_mapped", "needs_review", "reviewed"]


# ── Request / Response models ─────────────────────────────────────────────────


class SourceFieldModel(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    type: str = Field(default="unknown", max_length=64)
    description: str = Field(default="", max_length=500)


class RegisterSourceRequest(BaseModel):
    source_id: str = Field(pattern=SOURCE_ID_PATTERN)
    name: str = Field(min_length=1, max_length=200)
    system: str = Field(default="", max_length=100)
    target_schema: str = "Product"
    fields: list[SourceFieldModel] = Field(default_factory=list, max_length=500)
    sample_rows: list[dict[str, Any]] = Field(default_factory=list, max_length=MAX_SAMPLE_ROWS)

    @model_validator(mode="after")
    def _check_consistency(self) -> "RegisterSourceRequest":
        if not self.fields and not self.sample_rows:
            raise ValueError("Provide the source's fields, some sample rows, or both.")
        if self.target_schema not in CANONICAL_FIELDS:
            raise ValueError(
                f"Unknown target_schema {self.target_schema!r}. "
                f"Choose from: {', '.join(CANONICAL_FIELDS)}."
            )
        names = [f.name for f in self.fields]
        dupes = sorted({n for n in names if names.count(n) > 1})
        if dupes:
            raise ValueError(f"Duplicate field names: {', '.join(dupes)}.")
        if names:
            declared = set(names)
            for i, row in enumerate(self.sample_rows):
                extra = sorted(set(row) - declared)
                if extra:
                    raise ValueError(
                        f"sample_rows[{i}] has undeclared fields {extra}. "
                        "Declare them in fields or remove them from the rows."
                    )
        return self


class SourceSummary(BaseModel):
    source_id: str
    name: str
    system: str
    target_schema: str
    field_count: int
    sample_row_count: int
    mapping_id: int | None
    review_status: ReviewStatus
    required_mapped: int
    required_total: int


class SourceDetail(SourceSummary):
    fields: list[SourceFieldModel]
    sample_rows: list[dict[str, Any]]


class MappingRow(BaseModel):
    source_col: str
    target_col: str
    transform: str
    confidence: float
    reasoning: str
    value_map: dict[str, Any]
    status: str  # proposed | accepted | rejected | edited
    state: str  # mapped | needs_review | rejected | dropped


class CoverageModel(BaseModel):
    required_total: int
    required_mapped: int
    missing_required: list[str]
    pending_required: list[str]


class SourceMappingResponse(BaseModel):
    source_id: str
    mapping_id: int
    target_schema: str
    mappings: list[MappingRow]
    unmapped_source: list[str]
    coverage: CoverageModel


class DecisionRequest(BaseModel):
    status: Literal["accepted", "rejected", "edited"]
    target_col: str | None = None
    transform: str | None = None
    value_map: dict[str, Any] | None = None


class DecisionResponse(BaseModel):
    source_id: str
    mapping_id: int
    mapping: MappingRow
    coverage: CoverageModel


class IssueModel(BaseModel):
    severity: Literal["error", "warning"]
    code: str
    field: str
    message: str


class DryRunModel(BaseModel):
    rows_tested: int
    rows_ok: int
    preview: list[dict[str, Any]]


class ValidationResponse(BaseModel):
    source_id: str
    mapping_id: int
    ok: bool
    issues: list[IssueModel]
    dry_run: DryRunModel


class ExportResponse(BaseModel):
    source_id: str
    mapping_id: int
    format: str
    filename: str
    content: str
    warnings: list[str]


class CoverageCell(BaseModel):
    field: str
    source_id: str
    status: Literal["mapped", "needs_review", "missing"]
    source_col: str | None
    confidence: float | None


class CoverageSource(BaseModel):
    source_id: str
    name: str
    mapping_id: int | None


class CoverageField(BaseModel):
    path: str
    required: bool


class CoverageMatrixResponse(BaseModel):
    target_schema: str
    fields: list[CoverageField]
    sources: list[CoverageSource]
    cells: list[CoverageCell]


# ── Helpers ───────────────────────────────────────────────────────────────────


def _load_source(sources: SourceStore, source_id: str) -> Source:
    try:
        return sources.get(source_id)
    except KeyError as exc:
        known = [s.source_id for s in sources.list_all()]
        listing = ", ".join(known) if known else "none yet"
        raise HTTPException(
            status_code=404,
            detail=f"Unknown source_id {source_id!r}. Registered sources: {listing}.",
        ) from exc


def _latest(store: MappingStore, source: Source) -> tuple[int, MappingResult]:
    mapping_id = store.latest_for_source(source.source_id)
    if mapping_id is None:
        raise HTTPException(
            status_code=404,
            detail=f"Source {source.source_id!r} has no mapping yet. Run inference first "
            f"(POST /sources/{source.source_id}/mapping).",
        )
    return mapping_id, store.load(mapping_id)


def _row(m: FieldMapping) -> MappingRow:
    return MappingRow(
        source_col=m.source_col,
        target_col=m.target_col,
        transform=m.transform,
        confidence=m.confidence,
        reasoning=m.reasoning,
        value_map=dict(m.value_map),
        status=m.status,
        state=mapping_state(m),
    )


def _coverage(result: MappingResult, source: Source) -> CoverageModel:
    cov = coverage(result, get_fields(source.target_schema))
    return CoverageModel(**cov.__dict__)


def _summary(source: Source, store: MappingStore) -> SourceSummary:
    fields = get_fields(source.target_schema)
    mapping_id = store.latest_for_source(source.source_id)
    required_total = sum(f.required for f in fields)
    review_status: ReviewStatus = "not_mapped"
    required_mapped = 0
    if mapping_id is not None:
        result = store.load(mapping_id)
        cov = coverage(result, fields)
        required_mapped = cov.required_mapped
        pending = any(mapping_state(m) == "needs_review" for m in result.mappings)
        review_status = "needs_review" if pending or cov.missing_required else "reviewed"
    return SourceSummary(
        source_id=source.source_id,
        name=source.name,
        system=source.system,
        target_schema=source.target_schema,
        field_count=len(source.field_names),
        sample_row_count=len(source.sample_rows),
        mapping_id=mapping_id,
        review_status=review_status,
        required_mapped=required_mapped,
        required_total=required_total,
    )


def _mapping_response(
    source: Source, mapping_id: int, result: MappingResult
) -> SourceMappingResponse:
    mapped_cols = {m.source_col for m in result.mappings}
    return SourceMappingResponse(
        source_id=source.source_id,
        mapping_id=mapping_id,
        target_schema=source.target_schema,
        mappings=[_row(m) for m in result.mappings],
        unmapped_source=[c for c in source.field_names if c not in mapped_cols],
        coverage=_coverage(result, source),
    )


# ── Sources ───────────────────────────────────────────────────────────────────


@router.post("", response_model=SourceSummary, status_code=201)
def register_source(
    body: RegisterSourceRequest,
    sources: SourceStore = Depends(get_source_store),
    store: MappingStore = Depends(get_mapping_store),
) -> SourceSummary:
    """Register a source schema (fields and/or sample rows) to map."""
    if sources.exists(body.source_id):
        raise HTTPException(
            status_code=409,
            detail=f"Source {body.source_id!r} already exists. Pick another source_id.",
        )
    source = sources.register(
        Source(
            source_id=body.source_id,
            name=body.name,
            system=body.system,
            target_schema=body.target_schema,
            fields=[SourceField(**f.model_dump()) for f in body.fields],
            sample_rows=body.sample_rows,
        )
    )
    return _summary(source, store)


@router.get("", response_model=list[SourceSummary])
def list_sources(
    sources: SourceStore = Depends(get_source_store),
    store: MappingStore = Depends(get_mapping_store),
) -> list[SourceSummary]:
    """All registered sources with their review status."""
    return [_summary(s, store) for s in sources.list_all()]


@router.get("/{source_id}", response_model=SourceDetail)
def get_source(
    source_id: str,
    sources: SourceStore = Depends(get_source_store),
    store: MappingStore = Depends(get_mapping_store),
) -> SourceDetail:
    """One source with its fields and sample rows."""
    source = _load_source(sources, source_id)
    return SourceDetail(
        **_summary(source, store).model_dump(),
        fields=[
            SourceFieldModel(name=f.name, type=f.type, description=f.description)
            for f in source.fields
        ]
        or [SourceFieldModel(name=n) for n in source.field_names],
        sample_rows=source.sample_rows,
    )


# ── Mapping review ────────────────────────────────────────────────────────────


@router.get("/{source_id}/mapping", response_model=SourceMappingResponse)
def get_source_mapping(
    source_id: str,
    sources: SourceStore = Depends(get_source_store),
    store: MappingStore = Depends(get_mapping_store),
) -> SourceMappingResponse:
    """The latest mapping of a source, with review state and required-field coverage."""
    source = _load_source(sources, source_id)
    mapping_id, result = _latest(store, source)
    return _mapping_response(source, mapping_id, result)


@router.post("/{source_id}/mapping", response_model=SourceMappingResponse)
def infer_source_mapping(
    source_id: str,
    settings: Settings = Depends(get_settings),
    sources: SourceStore = Depends(get_source_store),
    store: MappingStore = Depends(get_mapping_store),
) -> SourceMappingResponse:
    """Run LLM inference for a source. Earlier human decisions are kept."""
    source = _load_source(sources, source_id)
    if not settings.anthropic_api_key:
        raise HTTPException(
            status_code=503,
            detail="Live mapping inference is not configured: ANTHROPIC_API_KEY is not set "
            "on the UDC backend. Existing mappings can still be read and reviewed.",
        )
    mapper = SchemaMapper(api_key=settings.anthropic_api_key, model=settings.anthropic_model)
    try:
        mapping_id = infer_mapping(source, mapper, store)
    except anthropic.APIStatusError as exc:
        raise HTTPException(status_code=502, detail=describe_api_error(exc)) from exc
    except anthropic.APIConnectionError as exc:
        raise HTTPException(
            status_code=502,
            detail="Mapping inference failed: could not reach the Claude API. Try again later.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=f"Mapping inference failed: {exc}") from exc
    return _mapping_response(source, mapping_id, store.load(mapping_id))


@router.patch(
    "/{source_id}/mapping/fields/{source_col}",
    response_model=DecisionResponse,
)
def decide_field(
    source_id: str,
    source_col: str,
    body: DecisionRequest,
    sources: SourceStore = Depends(get_source_store),
    store: MappingStore = Depends(get_mapping_store),
) -> DecisionResponse:
    """Accept, reject or edit the mapping of one source field."""
    source = _load_source(sources, source_id)
    mapping_id, _ = _latest(store, source)
    try:
        updated = decide(
            store,
            mapping_id,
            source,
            source_col,
            body.status,
            target_col=body.target_col,
            transform=body.transform,
            value_map=body.value_map,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=exc.args[0]) from exc
    except DecisionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return DecisionResponse(
        source_id=source.source_id,
        mapping_id=mapping_id,
        mapping=_row(updated),
        coverage=_coverage(store.load(mapping_id), source),
    )


@router.post("/{source_id}/mapping/validate", response_model=ValidationResponse)
def validate_source_mapping(
    source_id: str,
    sample_limit: int = Query(default=5, ge=1, le=50),
    sources: SourceStore = Depends(get_source_store),
    store: MappingStore = Depends(get_mapping_store),
) -> ValidationResponse:
    """Check types, required coverage and pending decisions, then dry-run on sample rows."""
    source = _load_source(sources, source_id)
    mapping_id, result = _latest(store, source)
    report = validate(result, get_fields(source.target_schema), source.sample_rows, sample_limit)
    return ValidationResponse(
        source_id=source.source_id,
        mapping_id=mapping_id,
        ok=report.ok,
        issues=[IssueModel(**i.__dict__) for i in report.issues],
        dry_run=DryRunModel(
            rows_tested=report.rows_tested,
            rows_ok=report.rows_ok,
            preview=report.preview,
        ),
    )


@router.get("/{source_id}/mapping/export", response_model=ExportResponse)
def export_source_mapping(
    source_id: str,
    format: Literal["json", "dbt_sql", "pyspark"] = Query(default="json"),
    sources: SourceStore = Depends(get_source_store),
    store: MappingStore = Depends(get_mapping_store),
) -> ExportResponse:
    """Render the applied mappings as a JSON spec, a dbt model or a PySpark function."""
    source = _load_source(sources, source_id)
    mapping_id, result = _latest(store, source)
    exported = export_mapping(source, mapping_id, result, get_fields(source.target_schema), format)
    return ExportResponse(
        source_id=source.source_id,
        mapping_id=mapping_id,
        format=exported.format,
        filename=exported.filename,
        content=exported.content,
        warnings=exported.warnings,
    )


# ── Coverage matrix ───────────────────────────────────────────────────────────


@coverage_router.get("/coverage", response_model=CoverageMatrixResponse)
def coverage_matrix(
    target_schema: str = Query(default="Product"),
    sources: SourceStore = Depends(get_source_store),
    store: MappingStore = Depends(get_mapping_store),
) -> CoverageMatrixResponse:
    """Status of every target field for every source mapped to *target_schema*."""
    try:
        fields = get_fields(target_schema)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=exc.args[0]) from exc

    out_sources: list[CoverageSource] = []
    cells: list[CoverageCell] = []
    for source in sources.list_all():
        if source.target_schema != target_schema:
            continue
        mapping_id = store.latest_for_source(source.source_id)
        out_sources.append(
            CoverageSource(source_id=source.source_id, name=source.name, mapping_id=mapping_id)
        )
        result = store.load(mapping_id) if mapping_id is not None else None
        statuses = field_statuses(result, fields) if result else {}
        for f in fields:
            status = statuses.get(f.path, "missing")
            match = None
            if result is not None and status != "missing":
                wanted = "mapped" if status == "mapped" else "needs_review"
                match = next(
                    (
                        m
                        for m in result.mappings
                        if m.target_col == f.path and mapping_state(m) == wanted
                    ),
                    None,
                )
            cells.append(
                CoverageCell(
                    field=f.path,
                    source_id=source.source_id,
                    status=status,
                    source_col=match.source_col if match else None,
                    confidence=match.confidence if match else None,
                )
            )
    return CoverageMatrixResponse(
        target_schema=target_schema,
        fields=[CoverageField(path=f.path, required=f.required) for f in fields],
        sources=out_sources,
        cells=cells,
    )
