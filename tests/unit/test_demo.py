"""Tests for the retail demo data and seeding."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from udc.api.app import create_app
from udc.api.dependencies import _reset_singletons
from udc.core.config import get_settings
from udc.core.source_store import SourceStore
from udc.demo import load_demo_sources, load_recorded, seed_demo
from udc.mapper.canonical import CANONICAL_FIELDS
from udc.mapper.prompt import ALLOWED_TRANSFORMS
from udc.mapper.store import MappingStore


def test_demo_sources_are_consistent() -> None:
    sources = load_demo_sources()
    assert [s.source_id for s in sources] == ["erp", "pim", "ecom"]
    for s in sources:
        assert len(s.sample_rows) >= 5
        declared = [f.name for f in s.fields]
        assert all(list(row) == declared for row in s.sample_rows), s.source_id


@pytest.mark.parametrize("source_id", ["erp", "pim", "ecom"])
def test_recorded_proposals_reference_real_fields(source_id: str) -> None:
    source = next(s for s in load_demo_sources() if s.source_id == source_id)
    recorded = load_recorded(source_id)
    assert recorded is not None
    targets = {f.path for f in CANONICAL_FIELDS["Product"]}
    for m in recorded.mappings:
        assert m.source_col in source.field_names
        assert m.transform in ALLOWED_TRANSFORMS
        assert m.target_col in targets or m.transform == "drop", m
    # the LLM prompt asks each target to appear at most once
    mapped = [m.target_col for m in recorded.mappings if m.transform != "drop"]
    assert len(mapped) == len(set(mapped))


def test_seed_is_idempotent(tmp_path: Path) -> None:
    db = str(tmp_path / "demo.duckdb")
    sources, mappings = SourceStore(db), MappingStore(db)

    assert seed_demo(sources, mappings) == ["erp", "pim", "ecom"]
    assert seed_demo(sources, mappings) == []
    assert mappings.latest_for_source("erp") == 1


@pytest.fixture()
def demo_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused@localhost/unused")
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "demo.duckdb"))
    monkeypatch.setenv("SEED_DEMO", "true")
    # Explicitly empty: an env var beats backend/.env, which may hold a real key
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    get_settings.cache_clear()
    _reset_singletons()
    with TestClient(create_app()) as client:  # runs the lifespan → seeds
        yield client
    _reset_singletons()
    get_settings.cache_clear()


def test_demo_story(demo_client: TestClient) -> None:
    """Pins the recorded demo the README demo script walks through.

    The proposals were recorded from claude-haiku-5-5 (2026-11-24). Re-recording
    can change them; update this test and the README demo script together.
    """
    listed = {s["source_id"]: s for s in demo_client.get("/sources").json()}
    assert set(listed) == {"erp", "pim", "ecom"}
    assert all(s["review_status"] == "needs_review" for s in listed.values())

    def pending(source_id: str) -> set[str]:
        body = demo_client.get(f"/sources/{source_id}/mapping").json()
        return {m["source_col"] for m in body["mappings"] if m["state"] == "needs_review"}

    # ERP: one hesitant proposal (MTART, the SAP material type); the dry run is
    # clean, and brand has no ERP source at all
    assert pending("erp") == {"MTART"}
    report = demo_client.post("/sources/erp/mapping/validate").json()
    assert {(i["code"], i["field"]) for i in report["issues"]} == {
        ("PENDING_REVIEW", "MTART"),
        ("UNMAPPED_REQUIRED", "brand"),
    }
    assert report["dry_run"]["rows_ok"] == report["dry_run"]["rows_tested"]

    # PIM: colours arrive as codes (NR, IV...) mapped as is; no price at all
    pim = demo_client.get("/sources/pim/mapping").json()
    colour = next(m for m in pim["mappings"] if m["source_col"] == "colour_code")
    assert (colour["target_col"], colour["transform"], colour["state"]) == (
        "color",
        "rename",
        "mapped",
    )
    assert pim["coverage"]["missing_required"] == ["category", "price.amount", "price.currency"]

    # E-commerce: the mapper is unsure about four columns, including the
    # option1/option2 pair whose meaning changes per product
    assert pending("ecom") == {"handle", "compare_at_price", "option1", "option2"}
    ecom = demo_client.get("/sources/ecom/mapping").json()
    assert ecom["coverage"]["missing_required"] == ["brand", "price.currency"]

    cells = {
        (c["source_id"], c["field"]): c["status"]
        for c in demo_client.get("/coverage").json()["cells"]
    }
    assert [s for s in ("erp", "pim", "ecom") if cells[(s, "brand")] == "mapped"] == ["pim"]
    assert [s for s in ("erp", "pim", "ecom") if cells[(s, "price.currency")] == "mapped"] == [
        "erp"
    ]

    # Live inference is off without a key, and says so
    assert demo_client.post("/sources/erp/mapping").status_code == 503
