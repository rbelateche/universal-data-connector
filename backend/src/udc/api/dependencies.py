"""Shared FastAPI dependencies: API-key guard and process-level store singletons."""

import secrets

from fastapi import Depends, Header, HTTPException

from udc.core.config import Settings, get_settings
from udc.core.source_store import SourceStore
from udc.mapper.store import MappingStore

_mapping_store: MappingStore | None = None
_source_store: SourceStore | None = None


def _reset_singletons() -> None:
    """Drop the cached stores. For test use only."""
    global _mapping_store, _source_store
    _mapping_store = None
    _source_store = None


def get_mapping_store(settings: Settings = Depends(get_settings)) -> MappingStore:
    global _mapping_store
    if _mapping_store is None:
        _mapping_store = MappingStore(settings.duckdb_path)
    return _mapping_store


def get_source_store(settings: Settings = Depends(get_settings)) -> SourceStore:
    global _source_store
    if _source_store is None:
        _source_store = SourceStore(settings.duckdb_path)
    return _source_store


def check_api_key(
    x_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    """Reject requests without the right X-Api-Key when REQUIRE_API_KEY is on."""
    if not settings.require_api_key:
        return
    if x_api_key is None or not secrets.compare_digest(x_api_key, settings.api_key):
        raise HTTPException(status_code=401, detail="Missing or invalid X-Api-Key header.")
