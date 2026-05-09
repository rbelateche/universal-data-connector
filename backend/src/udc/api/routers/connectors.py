"""Connectors router — register and list data source configurations."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from udc.api.dependencies import get_connector_registry, require_api_key
from udc.core.connector_registry import ConnectorConfig, ConnectorRegistry

router = APIRouter(
    prefix="/connectors",
    tags=["connectors"],
    dependencies=[Depends(require_api_key)],
)


# ── Request / Response models ─────────────────────────────────────────────────


class RegisterConnectorRequest(BaseModel):
    name: str
    type: str  # postgres | csv | json_api
    config: dict[str, Any]


class ConnectorResponse(BaseModel):
    id: str
    name: str
    type: str
    config: dict[str, Any]


# ── Helpers ───────────────────────────────────────────────────────────────────


def _to_response(cfg: ConnectorConfig) -> ConnectorResponse:
    return ConnectorResponse(id=cfg.id, name=cfg.name, type=cfg.type, config=cfg.config)


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("", response_model=ConnectorResponse, status_code=201)
def register_connector(
    body: RegisterConnectorRequest,
    registry: ConnectorRegistry = Depends(get_connector_registry),
) -> ConnectorResponse:
    """Register a new data source connector configuration."""
    try:
        cfg = registry.register(name=body.name, type_=body.type, config=body.config)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _to_response(cfg)


@router.get("", response_model=list[ConnectorResponse])
def list_connectors(
    registry: ConnectorRegistry = Depends(get_connector_registry),
) -> list[ConnectorResponse]:
    """List all registered connectors."""
    return [_to_response(c) for c in registry.list_all()]


@router.get("/{connector_id}", response_model=ConnectorResponse)
def get_connector(
    connector_id: str,
    registry: ConnectorRegistry = Depends(get_connector_registry),
) -> ConnectorResponse:
    """Retrieve a single connector by id."""
    try:
        cfg = registry.get(connector_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_response(cfg)
