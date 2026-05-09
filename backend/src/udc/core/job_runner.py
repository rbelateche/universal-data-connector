"""Background job runner — full ingestion + mapping pipeline."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from udc.connectors.csv import CsvConnector
from udc.connectors.json_api import JsonApiConnector
from udc.connectors.postgres import PostgresConnector
from udc.core.sampler import SchemaSampler
from udc.mapper.canonical import CANONICAL_SCHEMAS
from udc.mapper.mapper import SchemaMapper
from udc.mapper.transform import RowTransformer

if TYPE_CHECKING:
    from udc.core.connector_registry import ConnectorConfig
    from udc.core.data_store import DataStore
    from udc.core.job_store import JobStore
    from udc.core.versioning import SchemaVersionStore
    from udc.mapper.store import MappingStore

log = logging.getLogger(__name__)


def _build_connector(config: ConnectorConfig) -> Any:
    """Instantiate the correct BaseConnector subclass from a registry config."""
    t = config.type
    c = config.config
    if t == "postgres":
        return PostgresConnector(url=c["url"], table=c["table"])
    if t == "csv":
        return CsvConnector(path=c["path"])
    if t == "json_api":
        return JsonApiConnector(url=c["url"])
    raise ValueError(f"Unknown connector type {t!r}")


async def run_job(
    job_id: str,
    connector_config: ConnectorConfig,
    target_schema_name: str,
    api_key: str,
    model: str,
    job_store: JobStore,
    mapping_store: MappingStore,
    data_store: DataStore,
    schema_version_store: SchemaVersionStore,
) -> None:
    """
    Execute the full ingestion + mapping pipeline for one job.

    Progress is written back to *job_store* at each stage so callers
    can poll ``GET /jobs/{id}`` for live status updates.
    """
    log.info(
        "Starting job %s (connector=%s schema=%s)",
        job_id,
        connector_config.id,
        target_schema_name,
    )
    job_store.update(
        job_id,
        status="running",
        started_at=datetime.now(tz=UTC),
        progress_pct=0.0,
    )

    try:
        target_schema = CANONICAL_SCHEMAS[target_schema_name]

        # ── Step 1: fetch rows (sync → thread pool) ────────────────────────
        def _fetch() -> tuple[list[dict[str, Any]], dict[str, str]]:
            connector = _build_connector(connector_config)
            with connector:
                rows: list[dict[str, Any]] = connector.sample(500)
                schema: dict[str, str] = connector.get_schema()
            return rows, schema

        rows, raw_schema = await asyncio.to_thread(_fetch)
        job_store.update(job_id, progress_pct=20.0)
        log.info("Job %s: fetched %d rows", job_id, len(rows))

        # ── Step 2: schema snapshot / diff ────────────────────────────────
        await asyncio.to_thread(schema_version_store.snapshot, connector_config.id, raw_schema)
        job_store.update(job_id, progress_pct=30.0)

        # ── Step 3: column statistics ──────────────────────────────────────
        stats = await asyncio.to_thread(SchemaSampler().run, rows)
        job_store.update(job_id, progress_pct=40.0)

        # ── Step 4: Claude mapping inference ──────────────────────────────
        def _infer() -> Any:
            mapper = SchemaMapper(api_key=api_key, model=model)
            return mapper.infer(
                stats=stats,
                target_schema=target_schema,
                source_id=connector_config.id,
                target_schema_name=target_schema_name,
            )

        result = await asyncio.to_thread(_infer)
        job_store.update(job_id, progress_pct=70.0)
        log.info("Job %s: mapping done, %d fields", job_id, len(result.mappings))

        # ── Step 5: persist mapping ────────────────────────────────────────
        mapping_id: int = await asyncio.to_thread(mapping_store.save, result)
        job_store.update(job_id, progress_pct=80.0, mapping_id=mapping_id)

        # ── Step 6: apply transforms ───────────────────────────────────────
        transformer = RowTransformer(result)
        transformed: list[dict[str, Any]] = await asyncio.to_thread(transformer.transform, rows)
        job_store.update(job_id, progress_pct=90.0)

        # ── Step 7: persist transformed rows ──────────────────────────────
        await asyncio.to_thread(data_store.save_rows, job_id, transformed)
        job_store.update(
            job_id,
            status="done",
            progress_pct=100.0,
            rows_processed=len(transformed),
            finished_at=datetime.now(tz=UTC),
            mapping_id=mapping_id,
        )
        log.info("Job %s: completed, %d rows processed", job_id, len(transformed))

    except Exception as exc:
        log.exception("Job %s failed: %s", job_id, exc)
        job_store.update(
            job_id,
            status="failed",
            error=str(exc),
            finished_at=datetime.now(tz=UTC),
        )
