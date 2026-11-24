"""Concurrent access to the DuckDB-backed stores.

FastAPI runs sync endpoints in a thread pool, and the review view fires
overlapping requests. Before the stores serialised their connection this
returned wrong results, duplicate ids, and could segfault the process.
"""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from udc.core.source_store import Source, SourceStore
from udc.mapper.models import FieldMapping, MappingResult
from udc.mapper.store import MappingStore


def _result() -> MappingResult:
    return MappingResult(
        source_id="erp",
        target_schema_name="Product",
        mappings=[FieldMapping("MATNR", "sku", "rename", 0.9, "id")],
        unmapped_source=[],
        unmapped_target=[],
    )


def test_concurrent_reads_and_writes(tmp_path: Path) -> None:
    db = str(tmp_path / "c.duckdb")
    mappings, sources = MappingStore(db), SourceStore(db)
    sources.register(Source("erp", "ERP", "erp", "Product", [], [{"MATNR": "1"}]))
    first = mappings.save(_result())

    def work(i: int) -> None:
        if i % 4 == 0:
            mappings.save(_result())
        elif i % 4 == 1:
            mappings.apply_override(first, "MATNR", {"status": "accepted" if i % 8 else "rejected"})
        elif i % 4 == 2:
            assert sources.get("erp").name == "ERP"
        else:
            assert mappings.load(first).mappings[0].source_col == "MATNR"

    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(work, range(400)))

    # every save got its own id
    ids = [r["id"] for r in mappings.list_for_source("erp")]
    assert len(ids) == len(set(ids)) == 101
