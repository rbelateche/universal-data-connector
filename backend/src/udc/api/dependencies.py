"""Shared FastAPI dependencies: auth guard and singleton stores."""

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader

from udc.core.config import Settings, get_settings
from udc.core.connector_registry import ConnectorRegistry
from udc.core.data_store import DataStore
from udc.core.job_store import JobStore
from udc.core.versioning import SchemaVersionStore
from udc.mapper.store import MappingStore

_api_key_header = APIKeyHeader(name="X-Api-Key", auto_error=False)

# ── process-level singletons ──────────────────────────────────────────────────

_connector_registry: ConnectorRegistry | None = None
_job_store: JobStore | None = None
_mapping_store: MappingStore | None = None
_data_store: DataStore | None = None
_schema_version_store: SchemaVersionStore | None = None


def _reset_singletons() -> None:
    """Reset all store singletons. For test use only."""
    global _connector_registry, _job_store, _mapping_store, _data_store, _schema_version_store
    _connector_registry = None
    _job_store = None
    _mapping_store = None
    _data_store = None
    _schema_version_store = None


# ── auth ──────────────────────────────────────────────────────────────────────


def require_api_key(
    api_key: str | None = Security(_api_key_header),
    settings: Settings = Depends(get_settings),
) -> None:
    """Reject requests that do not carry a valid X-Api-Key header."""
    if not api_key or api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")


# ── store providers ───────────────────────────────────────────────────────────


def get_connector_registry(
    settings: Settings = Depends(get_settings),
) -> ConnectorRegistry:
    global _connector_registry
    if _connector_registry is None:
        _connector_registry = ConnectorRegistry(settings.duckdb_path)
    return _connector_registry


def get_job_store(settings: Settings = Depends(get_settings)) -> JobStore:
    global _job_store
    if _job_store is None:
        _job_store = JobStore(settings.duckdb_path)
    return _job_store


def get_mapping_store(settings: Settings = Depends(get_settings)) -> MappingStore:
    global _mapping_store
    if _mapping_store is None:
        _mapping_store = MappingStore(settings.duckdb_path)
    return _mapping_store


def get_data_store(settings: Settings = Depends(get_settings)) -> DataStore:
    global _data_store
    if _data_store is None:
        _data_store = DataStore(settings.duckdb_path)
    return _data_store


def get_schema_version_store(
    settings: Settings = Depends(get_settings),
) -> SchemaVersionStore:
    global _schema_version_store
    if _schema_version_store is None:
        _schema_version_store = SchemaVersionStore(settings.duckdb_path)
    return _schema_version_store
