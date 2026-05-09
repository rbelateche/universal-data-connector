"""Schema diff router — GET /schema/{job_id}/diff."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from udc.api.dependencies import get_job_store, get_schema_version_store, require_api_key
from udc.core.job_store import JobStore
from udc.core.versioning import SchemaVersionStore

router = APIRouter(
    prefix="/schema",
    tags=["schema"],
    dependencies=[Depends(require_api_key)],
)


class SchemaDiffResponse(BaseModel):
    source_id: str
    has_changes: bool
    added: list[str]
    removed: list[str]
    changed: dict[str, dict[str, str]]


@router.get("/{job_id}/diff", response_model=SchemaDiffResponse)
def get_schema_diff(
    job_id: str,
    job_store: JobStore = Depends(get_job_store),
    schema_version_store: SchemaVersionStore = Depends(get_schema_version_store),
) -> SchemaDiffResponse:
    """
    Return the latest schema diff for the connector used by this job.

    The diff compares the two most recent schema snapshots for that connector.
    Returns ``has_changes=false`` if only one snapshot exists (first ever run).
    """
    try:
        job = job_store.get(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    diff = schema_version_store.get_latest_diff(job.connector_id)
    if diff is None:
        return SchemaDiffResponse(
            source_id=job.connector_id,
            has_changes=False,
            added=[],
            removed=[],
            changed={},
        )
    return SchemaDiffResponse(
        source_id=job.connector_id,
        has_changes=diff.has_changes,
        added=diff.added,
        removed=diff.removed,
        changed=diff.changed,
    )
