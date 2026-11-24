"""Seed the demo sources into UDC, and re-record their mapping proposals."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from udc.core.source_store import Source, SourceField, SourceStore
from udc.mapper.canonical import CANONICAL_SCHEMAS
from udc.mapper.mapper import SchemaMapper
from udc.mapper.models import MappingResult
from udc.mapper.service import stats_for_source
from udc.mapper.store import MappingStore, result_from_dict, result_to_dict

DATA_DIR = Path(__file__).parent / "data"
SOURCES_DIR = DATA_DIR / "sources"
RECORDED_DIR = DATA_DIR / "recorded"


def load_demo_sources() -> list[Source]:
    """The demo sources, in a stable order (erp, pim, ecom)."""
    order = {"erp": 0, "pim": 1, "ecom": 2}
    sources = []
    for path in SOURCES_DIR.glob("*.json"):
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        sources.append(
            Source(
                source_id=data["source_id"],
                name=data["name"],
                system=data["system"],
                target_schema=data["target_schema"],
                fields=[SourceField(**f) for f in data["fields"]],
                sample_rows=data["sample_rows"],
            )
        )
    return sorted(sources, key=lambda s: (order.get(s.source_id, 99), s.source_id))


def load_recorded(source_id: str) -> MappingResult | None:
    """The recorded mapping proposal for *source_id*, if there is one."""
    path = RECORDED_DIR / f"{source_id}.json"
    if not path.exists():
        return None
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    data.pop("_provenance", None)
    return result_from_dict(data)


def seed_demo(sources: SourceStore, mappings: MappingStore) -> list[str]:
    """Register the demo sources and their recorded proposals.

    Idempotent: sources that already exist are left untouched. Returns the ids
    of the sources it added.
    """
    added: list[str] = []
    for source in load_demo_sources():
        if sources.exists(source.source_id):
            continue
        sources.register(source)
        recorded = load_recorded(source.source_id)
        if recorded is not None:
            mappings.save(recorded)
        added.append(source.source_id)
    return added


def record_demo(mapper: SchemaMapper, model: str) -> list[Path]:
    """Run live inference for every demo source and overwrite its recorded file."""
    written: list[Path] = []
    for source in load_demo_sources():
        result = mapper.infer(
            stats=stats_for_source(source),
            target_schema=CANONICAL_SCHEMAS[source.target_schema],
            source_id=source.source_id,
            target_schema_name=source.target_schema,
        )
        payload = result_to_dict(result)
        for m in payload["mappings"]:
            m.pop("status", None)  # a recording is a raw proposal
        payload = {
            "_provenance": {
                "kind": "recorded",
                "model": model,
                "recorded_at": datetime.now(UTC).strftime("%Y-%m-%d"),
            },
            **payload,
        }
        path = RECORDED_DIR / f"{source.source_id}.json"
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        written.append(path)
    return written
