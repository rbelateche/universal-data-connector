"""Data router — paginated preview of canonicalized output rows."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from udc.api.dependencies import get_data_store, get_job_store, require_api_key
from udc.core.data_store import DataStore
from udc.core.job_store import JobStore

router = APIRouter(
    prefix="/data",
    tags=["data"],
    dependencies=[Depends(require_api_key)],
)


class DataResponse(BaseModel):
    job_id: str
    total_rows: int
    offset: int
    limit: int
    rows: list[dict[str, Any]]


@router.get("/{job_id}", response_model=DataResponse)
def get_data(
    job_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    job_store: JobStore = Depends(get_job_store),
    data_store: DataStore = Depends(get_data_store),
) -> DataResponse:
    """Return a paginated preview of canonicalized rows for a completed job."""
    try:
        job = job_store.get(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if job.status != "done":
        raise HTTPException(
            status_code=409,
            detail=f"Job is not yet complete (status={job.status!r}). Try again later.",
        )

    rows = data_store.get_rows(job_id, offset=offset, limit=limit)
    total = data_store.count(job_id)
    return DataResponse(job_id=job_id, total_rows=total, offset=offset, limit=limit, rows=rows)
