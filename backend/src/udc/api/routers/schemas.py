"""Schemas router — the canonical target models sources are mapped into."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from udc.mapper.canonical import CANONICAL_FIELDS, get_fields

router = APIRouter(prefix="/schemas", tags=["schemas"])


class SchemaFieldModel(BaseModel):
    path: str
    type: str
    required: bool
    description: str


class SchemaSummary(BaseModel):
    name: str
    field_count: int
    required_count: int


class SchemaResponse(BaseModel):
    name: str
    fields: list[SchemaFieldModel]


@router.get("", response_model=list[SchemaSummary])
def list_schemas() -> list[SchemaSummary]:
    """List the canonical schemas."""
    return [
        SchemaSummary(
            name=name,
            field_count=len(fields),
            required_count=sum(f.required for f in fields),
        )
        for name, fields in CANONICAL_FIELDS.items()
    ]


@router.get("/{name}", response_model=SchemaResponse)
def get_schema(name: str) -> SchemaResponse:
    """Fields of one canonical schema, with required flags and descriptions."""
    try:
        fields = get_fields(name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=exc.args[0]) from exc
    return SchemaResponse(
        name=name,
        fields=[SchemaFieldModel(**f.__dict__) for f in fields],
    )
