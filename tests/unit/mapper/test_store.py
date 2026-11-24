"""Tests for MappingStore — save, load, overrides, list."""

from pathlib import Path

import pytest

from udc.mapper.models import FieldMapping, MappingResult
from udc.mapper.store import MappingStore


def _sample_result(source_id: str = "pg-crm") -> MappingResult:
    return MappingResult(
        source_id=source_id,
        target_schema_name="Contact",
        mappings=[
            FieldMapping(
                source_col="cust_id",
                target_col="customer_id",
                transform="cast_int",
                confidence=0.95,
                reasoning="Obvious ID column.",
                value_map={},
            ),
            FieldMapping(
                source_col="actv",
                target_col="is_active",
                transform="map_values",
                confidence=0.80,
                reasoning="Y/N flag maps to boolean.",
                value_map={"Y": True, "N": False},
            ),
        ],
        unmapped_source=[],
        unmapped_target=["email"],
    )


def test_save_and_load(tmp_path: Path) -> None:
    store = MappingStore(str(tmp_path / "test.duckdb"))
    result = _sample_result()
    mid = store.save(result)
    loaded = store.load(mid)

    assert loaded.source_id == result.source_id
    assert loaded.target_schema_name == result.target_schema_name
    assert len(loaded.mappings) == 2
    assert loaded.unmapped_target == ["email"]
    store.close()


def test_load_missing_raises(tmp_path: Path) -> None:
    store = MappingStore(str(tmp_path / "test.duckdb"))
    with pytest.raises(KeyError):
        store.load(999)
    store.close()


def test_sequential_ids(tmp_path: Path) -> None:
    store = MappingStore(str(tmp_path / "test.duckdb"))
    id1 = store.save(_sample_result("src-a"))
    id2 = store.save(_sample_result("src-b"))
    assert id2 == id1 + 1
    store.close()


def test_list_for_source(tmp_path: Path) -> None:
    store = MappingStore(str(tmp_path / "test.duckdb"))
    store.save(_sample_result("pg-crm"))
    store.save(_sample_result("pg-crm"))
    store.save(_sample_result("csv-export"))

    crm_list = store.list_for_source("pg-crm")
    assert len(crm_list) == 2
    assert all(r["source_id"] == "pg-crm" for r in crm_list)
    store.close()


def test_apply_override_changes_field(tmp_path: Path) -> None:
    store = MappingStore(str(tmp_path / "test.duckdb"))
    mid = store.save(_sample_result())

    # Human corrects: cust_id should actually cast to float, confidence 1.0
    store.apply_override(mid, "cust_id", {"transform": "cast_float", "confidence": 1.0})
    loaded = store.load(mid)

    corrected = next(m for m in loaded.mappings if m.source_col == "cust_id")
    assert corrected.transform == "cast_float"
    assert corrected.confidence == 1.0
    store.close()


def test_override_nonexistent_mapping_raises(tmp_path: Path) -> None:
    store = MappingStore(str(tmp_path / "test.duckdb"))
    with pytest.raises(KeyError):
        store.apply_override(999, "col", {"transform": "rename"})
    store.close()


def test_value_map_roundtrip(tmp_path: Path) -> None:
    store = MappingStore(str(tmp_path / "test.duckdb"))
    mid = store.save(_sample_result())
    loaded = store.load(mid)

    actv = next(m for m in loaded.mappings if m.source_col == "actv")
    assert actv.value_map == {"Y": True, "N": False}
    store.close()


def test_needs_review_on_loaded(tmp_path: Path) -> None:
    store = MappingStore(str(tmp_path / "test.duckdb"))
    mid = store.save(_sample_result())
    loaded = store.load(mid)
    # unmapped_target=["email"] → needs_review is True
    assert loaded.needs_review is True
    store.close()


# ── Review statuses ───────────────────────────────────────────────────────────


def test_status_defaults_to_proposed_and_round_trips(tmp_path: Path) -> None:
    store = MappingStore(str(tmp_path / "test.duckdb"))
    result = _sample_result()
    result.mappings[0].status = "accepted"
    mid = store.save(result)

    loaded = store.load(mid)

    assert [m.status for m in loaded.mappings] == ["accepted", "proposed"]


def test_latest_override_wins(tmp_path: Path) -> None:
    store = MappingStore(str(tmp_path / "test.duckdb"))
    mid = store.save(_sample_result())

    store.apply_override(mid, "cust_id", {"status": "accepted"})
    store.apply_override(mid, "cust_id", {"status": "rejected"})

    loaded = store.load(mid)
    assert loaded.mappings[0].status == "rejected"


def test_override_on_unmapped_column_adds_a_mapping(tmp_path: Path) -> None:
    store = MappingStore(str(tmp_path / "test.duckdb"))
    result = _sample_result()
    result.unmapped_source = ["mail_addr"]
    mid = store.save(result)

    store.apply_override(
        mid, "mail_addr", {"status": "edited", "target_col": "email", "transform": "rename"}
    )

    loaded = store.load(mid)
    added = [m for m in loaded.mappings if m.source_col == "mail_addr"]
    assert len(added) == 1
    assert added[0].target_col == "email"
    assert added[0].status == "edited"
    assert loaded.unmapped_source == []


def test_latest_for_source(tmp_path: Path) -> None:
    store = MappingStore(str(tmp_path / "test.duckdb"))
    assert store.latest_for_source("pg-crm") is None

    first = store.save(_sample_result())
    second = store.save(_sample_result())
    store.save(_sample_result(source_id="other"))

    assert store.latest_for_source("pg-crm") == second != first
