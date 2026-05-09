"""Jobs router — trigger and monitor ingestion + mapping jobs."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from udc.api.dependencies import (
    get_connector_registry,
    get_data_store,
    get_job_store,
    get_mapping_store,
    get_schema_version_store,
    require_api_key,
)
from udc.core.config import Settings, get_settings
from udc.core.connector_registry import ConnectorRegistry
from udc.core.data_store import DataStore
from udc.core.job_runner import run_job
from udc.core.job_store import Job, JobStore
from udc.core.versioning import SchemaVersionStore
from udc.mapper.canonical import CANONICAL_SCHEMAS
from udc.mapper.store import MappingStore

router = APIRouter(
    prefix="/jobs",
    tags=["jobs"],
    dependencies=[Depends(require_api_key)],
)


# ── Request / Response models ─────────────────────────────────────────────────


class CreateJobRequest(BaseModel):
    connector_id: str
    target_schema_name: str


class JobResponse(BaseModel):
    job_id: str
    connector_id: str
    target_schema: str
    status: str
    progress_pct: float
    error: str | None = None
    mapping_id: int | None = None
    rows_processed: int
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime


# ── Helpers ───────────────────────────────────────────────────────────────────


def _to_response(job: Job) -> JobResponse:
    return JobResponse(
        job_id=job.id,
        connector_id=job.connector_id,
        target_schema=job.target_schema,
        status=job.status,
        progress_pct=job.progress_pct,
        error=job.error,
        mapping_id=job.mapping_id,
        rows_processed=job.rows_processed,
        started_at=job.started_at,
        finished_at=job.finished_at,
        created_at=job.created_at,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("", response_model=JobResponse, status_code=202)
async def create_job(
    body: CreateJobRequest,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
    connector_registry: ConnectorRegistry = Depends(get_connector_registry),
    job_store: JobStore = Depends(get_job_store),
    mapping_store: MappingStore = Depends(get_mapping_store),
    data_store: DataStore = Depends(get_data_store),
    schema_version_store: SchemaVersionStore = Depends(get_schema_version_store),
) -> JobResponse:
    """
    Register a new ingestion + mapping job. Returns 202 immediately;
    the full pipeline (sample → map → transform → store) runs in the background.
    Poll GET /jobs/{job_id} for live progress updates.
    """
    if body.target_schema_name not in CANONICAL_SCHEMAS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unknown schema {body.target_schema_name!r}. "
                f"Choose from: {sorted(CANONICAL_SCHEMAS)}"
            ),
        )

    try:
        connector_config = connector_registry.get(body.connector_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    job = job_store.create(body.connector_id, body.target_schema_name)

    background_tasks.add_task(
        run_job,
        job_id=job.id,
        connector_config=connector_config,
        target_schema_name=body.target_schema_name,
        api_key=settings.anthropic_api_key,
        model=settings.anthropic_model,
        job_store=job_store,
        mapping_store=mapping_store,
        data_store=data_store,
        schema_version_store=schema_version_store,
    )

    return _to_response(job)


@router.get("", response_model=list[JobResponse])
def list_jobs(
    job_store: JobStore = Depends(get_job_store),
) -> list[JobResponse]:
    """List all jobs, newest first."""
    return [_to_response(j) for j in job_store.list_all()]


@router.get("/{job_id}", response_model=JobResponse)
def get_job(
    job_id: str,
    job_store: JobStore = Depends(get_job_store),
) -> JobResponse:
    """Get current status and progress of a job."""
    try:
        return _to_response(job_store.get(job_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ── Mapping sub-resource (3.5 / 3.6) ─────────────────────────────────────────


class MappingFieldOverrideRequest(BaseModel):
    patch: dict[str, Any]  # fields to override, e.g. {"target_col": "...", "confidence": 1.0}


@router.get("/{job_id}/mapping")
def get_job_mapping(
    job_id: str,
    job_store: JobStore = Depends(get_job_store),
    mapping_store: MappingStore = Depends(get_mapping_store),
) -> dict[str, Any]:
    """Return the full field mapping (with confidence scores and LLM reasoning) for a job."""
    try:
        job = job_store.get(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if job.mapping_id is None:
        raise HTTPException(
            status_code=409,
            detail=f"Job {job_id!r} has no mapping yet (status={job.status!r}).",
        )

    result = mapping_store.load(job.mapping_id)
    return {
        "job_id": job_id,
        "mapping_id": job.mapping_id,
        "source_id": result.source_id,
        "target_schema_name": result.target_schema_name,
        "needs_review": result.needs_review,
        "mappings": [
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
        "unmapped_source": result.unmapped_source,
        "unmapped_target": result.unmapped_target,
    }


@router.patch("/{job_id}/mapping/fields/{field_name}")
def override_mapping_field(
    job_id: str,
    field_name: str,
    body: MappingFieldOverrideRequest,
    job_store: JobStore = Depends(get_job_store),
    mapping_store: MappingStore = Depends(get_mapping_store),
) -> dict[str, str]:
    """Apply a human correction to a single field in a job's mapping."""
    try:
        job = job_store.get(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if job.mapping_id is None:
        raise HTTPException(
            status_code=409,
            detail=f"Job {job_id!r} has no mapping yet (status={job.status!r}).",
        )

    try:
        mapping_store.apply_override(job.mapping_id, field_name, body.patch)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {"status": "ok"}
