"""Tests for the /sources, /schemas and /coverage API routers."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from udc.api.app import create_app
from udc.api.dependencies import _reset_singletons
from udc.core.config import Settings, get_settings
from udc.mapper.models import FieldMapping, MappingResult

ERP_ROWS = [
    {
        "MATNR": "000000010001234",
        "MAKTX": "Sac Lune cuir grainé",
        "MTART": "FERT",
        "MATKL": "BAGS",
        "NETPR": "1.250,00",
        "WAERS": "EUR",
        "LABST": "12.000",
        "ERSDA": "20260315",
    },
    {
        "MATNR": "000000010001235",
        "MAKTX": "Foulard Soie Orage",
        "MTART": "FERT",
        "MATKL": "ACCS",
        "NETPR": "390,00",
        "WAERS": "EUR",
        "LABST": "40.000",
        "ERSDA": "20260402",
    },
]

ERP_SOURCE = {
    "source_id": "erp",
    "name": "SAP ERP material export",
    "system": "erp",
    "fields": [{"name": k, "type": "CHAR"} for k in ERP_ROWS[0]],
    "sample_rows": ERP_ROWS,
}


def _erp_result() -> MappingResult:
    return MappingResult(
        source_id="erp",
        target_schema_name="Product",
        mappings=[
            FieldMapping("MATNR", "sku", "cast_int", 0.90, "Material number."),
            FieldMapping("MAKTX", "name", "rename", 0.85, "Material description."),
            FieldMapping("MTART", "material", "rename", 0.40, "Looks like material."),
            FieldMapping("MATKL", "category", "rename", 0.55, "Material group."),
            FieldMapping("NETPR", "price.amount", "cast_float", 0.90, "Net price."),
            FieldMapping("WAERS", "price.currency", "rename", 0.95, "Currency key."),
            FieldMapping("LABST", "stock_quantity", "cast_int", 0.80, "Unrestricted stock."),
            FieldMapping("ERSDA", "created_at", "parse_date", 0.75, "Created on."),
        ],
        unmapped_source=[],
        unmapped_target=["brand", "color", "size"],
    )


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url="postgresql://test:test@localhost/test",
        anthropic_api_key="test-key",
        duckdb_path=str(tmp_path / "test.duckdb"),
    )


@pytest.fixture()
def client(settings: Settings) -> Iterator[TestClient]:
    _reset_singletons()
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    yield TestClient(app)
    _reset_singletons()


def _register_and_map(client: TestClient, result: MappingResult | None = None) -> dict[str, Any]:
    assert client.post("/sources", json=ERP_SOURCE).status_code == 201
    with patch("udc.api.routers.sources.SchemaMapper") as MockMapper:
        MockMapper.return_value.infer.return_value = result or _erp_result()
        resp = client.post("/sources/erp/mapping")
    assert resp.status_code == 200, resp.text
    body: dict[str, Any] = resp.json()
    return body


def _codes(validation: dict[str, Any]) -> set[tuple[str, str]]:
    return {(i["code"], i["field"]) for i in validation["issues"]}


# ── /schemas ──────────────────────────────────────────────────────────────────


def test_get_product_schema(client: TestClient) -> None:
    resp = client.get("/schemas/Product")
    assert resp.status_code == 200
    fields = {f["path"]: f for f in resp.json()["fields"]}
    assert fields["price.currency"]["required"] is True
    assert fields["color"]["required"] is False


def test_unknown_schema_returns_404_with_choices(client: TestClient) -> None:
    resp = client.get("/schemas/Invoice")
    assert resp.status_code == 404
    assert "Product" in resp.json()["detail"]


# ── register / list / get ─────────────────────────────────────────────────────


def test_register_list_and_get_source(client: TestClient) -> None:
    resp = client.post("/sources", json=ERP_SOURCE)
    assert resp.status_code == 201
    assert resp.json()["review_status"] == "not_mapped"
    assert resp.json()["field_count"] == 8

    listed = client.get("/sources").json()
    assert [s["source_id"] for s in listed] == ["erp"]

    detail = client.get("/sources/erp").json()
    assert detail["sample_rows"][0]["NETPR"] == "1.250,00"


def test_register_duplicate_returns_409(client: TestClient) -> None:
    client.post("/sources", json=ERP_SOURCE)
    resp = client.post("/sources", json=ERP_SOURCE)
    assert resp.status_code == 409
    assert "already exists" in resp.json()["detail"]


@pytest.mark.parametrize(
    ("patch_body", "fragment"),
    [
        ({"fields": [], "sample_rows": []}, "fields, some sample rows"),
        ({"source_id": "Bad Id!"}, "source_id"),
        ({"target_schema": "Invoice"}, "Unknown target_schema"),
        ({"sample_rows": [{"MATNR": "1", "EXTRA": "x"}]}, "undeclared fields"),
    ],
)
def test_register_rejects_invalid_sources(
    client: TestClient, patch_body: dict[str, Any], fragment: str
) -> None:
    resp = client.post("/sources", json={**ERP_SOURCE, **patch_body})
    assert resp.status_code == 422
    assert fragment in resp.text


def test_unknown_source_lists_registered_ones(client: TestClient) -> None:
    client.post("/sources", json=ERP_SOURCE)
    resp = client.get("/sources/sap/mapping")
    assert resp.status_code == 404
    assert "Registered sources: erp" in resp.json()["detail"]


# ── inference ─────────────────────────────────────────────────────────────────


def test_mapping_before_inference_returns_404(client: TestClient) -> None:
    client.post("/sources", json=ERP_SOURCE)
    resp = client.get("/sources/erp/mapping")
    assert resp.status_code == 404
    assert "no mapping yet" in resp.json()["detail"]


def test_inference_without_api_key_returns_503(client: TestClient, settings: Settings) -> None:
    client.post("/sources", json=ERP_SOURCE)
    settings.anthropic_api_key = ""
    resp = client.post("/sources/erp/mapping")
    assert resp.status_code == 503
    assert "ANTHROPIC_API_KEY" in resp.json()["detail"]


def test_inference_returns_review_state_and_coverage(client: TestClient) -> None:
    body = _register_and_map(client)

    states = {m["source_col"]: m["state"] for m in body["mappings"]}
    assert states["MATKL"] == "needs_review"  # 0.55 < 0.7
    assert states["MATNR"] == "mapped"
    cov = body["coverage"]
    assert cov["required_total"] == 6
    assert cov["missing_required"] == ["brand"]
    assert cov["pending_required"] == ["category"]
    assert cov["required_mapped"] == 4
    assert client.get("/sources").json()[0]["review_status"] == "needs_review"


def test_reinference_keeps_human_decisions(client: TestClient) -> None:
    _register_and_map(client)
    client.patch("/sources/erp/mapping/fields/MATKL", json={"status": "accepted"})
    client.patch("/sources/erp/mapping/fields/MTART", json={"status": "rejected"})

    with patch("udc.api.routers.sources.SchemaMapper") as MockMapper:
        MockMapper.return_value.infer.return_value = _erp_result()
        body = client.post("/sources/erp/mapping").json()

    status = {m["source_col"]: m["status"] for m in body["mappings"]}
    assert status["MATKL"] == "accepted"
    assert status["MTART"] == "rejected"
    assert status["MAKTX"] == "proposed"


# ── decisions ─────────────────────────────────────────────────────────────────


def test_accept_reject_and_edit(client: TestClient) -> None:
    _register_and_map(client)

    accepted = client.patch("/sources/erp/mapping/fields/MATKL", json={"status": "accepted"})
    assert accepted.status_code == 200
    assert accepted.json()["mapping"]["state"] == "mapped"
    assert accepted.json()["coverage"]["pending_required"] == []

    rejected = client.patch("/sources/erp/mapping/fields/MTART", json={"status": "rejected"})
    assert rejected.json()["mapping"]["state"] == "rejected"

    edited = client.patch(
        "/sources/erp/mapping/fields/NETPR",
        json={"status": "edited", "transform": "parse_decimal"},
    )
    assert edited.json()["mapping"]["transform"] == "parse_decimal"
    assert edited.json()["mapping"]["target_col"] == "price.amount"


def test_accept_with_a_change_is_recorded_as_edit(client: TestClient) -> None:
    _register_and_map(client)
    resp = client.patch(
        "/sources/erp/mapping/fields/MATNR",
        json={"status": "accepted", "transform": "rename"},
    )
    assert resp.json()["mapping"]["status"] == "edited"


def test_edit_to_unknown_target_lists_valid_fields(client: TestClient) -> None:
    _register_and_map(client)
    resp = client.patch(
        "/sources/erp/mapping/fields/MTART",
        json={"status": "edited", "target_col": "material_type"},
    )
    assert resp.status_code == 422
    assert "price.amount" in resp.json()["detail"]


def test_unknown_source_field_returns_404(client: TestClient) -> None:
    _register_and_map(client)
    resp = client.patch("/sources/erp/mapping/fields/BRAND", json={"status": "accepted"})
    assert resp.status_code == 404
    assert "MATNR" in resp.json()["detail"]


def test_map_a_field_the_llm_left_unmapped(client: TestClient) -> None:
    result = _erp_result()
    result.mappings = [m for m in result.mappings if m.source_col != "MAKTX"]
    result.unmapped_source = ["MAKTX"]
    body = _register_and_map(client, result)
    assert "MAKTX" in body["unmapped_source"]

    accept = client.patch("/sources/erp/mapping/fields/MAKTX", json={"status": "accepted"})
    assert accept.status_code == 422
    assert "status 'edited'" in accept.json()["detail"]

    edit = client.patch(
        "/sources/erp/mapping/fields/MAKTX",
        json={"status": "edited", "target_col": "name"},
    )
    assert edit.status_code == 200
    assert edit.json()["mapping"]["transform"] == "rename"
    assert "MAKTX" not in client.get("/sources/erp/mapping").json()["unmapped_source"]


def test_map_values_needs_a_value_map(client: TestClient) -> None:
    _register_and_map(client)
    resp = client.patch(
        "/sources/erp/mapping/fields/MATKL",
        json={"status": "edited", "transform": "map_values"},
    )
    assert resp.status_code == 422
    assert "value_map" in resp.json()["detail"]


# ── validation ────────────────────────────────────────────────────────────────


def test_validation_finds_the_erp_traps(client: TestClient) -> None:
    _register_and_map(client)

    report = client.post("/sources/erp/mapping/validate").json()

    assert report["ok"] is False
    codes = _codes(report)
    assert ("TYPE_MISMATCH", "sku") in codes  # cast_int on a zero-padded id
    assert ("TRANSFORM_FAILED", "price.amount") in codes  # "1.250,00"
    assert ("TRANSFORM_FAILED", "stock_quantity") in codes  # "12.000"
    assert ("PENDING_REVIEW", "category") in codes
    assert ("UNMAPPED_REQUIRED", "brand") in codes
    price_issue = next(i for i in report["issues"] if i["field"] == "price.amount")
    assert "parse_decimal" in price_issue["message"]
    material = next(i for i in report["issues"] if i["field"] == "material")
    assert material["severity"] == "warning"  # optional target
    assert report["dry_run"]["rows_tested"] == 2
    assert report["dry_run"]["rows_ok"] == 0


def test_validation_passes_once_reviewed(client: TestClient) -> None:
    result = _erp_result()
    result.mappings.append(FieldMapping("MAKTX", "brand", "rename", 0.2, "Placeholder."))
    _register_and_map(client, result)
    decisions = [
        ("MATNR", {"status": "edited", "transform": "rename"}),
        ("NETPR", {"status": "edited", "transform": "parse_decimal"}),
        ("LABST", {"status": "edited", "transform": "parse_decimal"}),
        ("MATKL", {"status": "accepted"}),
        ("MTART", {"status": "rejected"}),
    ]
    for col, body in decisions:
        assert client.patch(f"/sources/erp/mapping/fields/{col}", json=body).status_code == 200

    report = client.post("/sources/erp/mapping/validate").json()
    codes = _codes(report)
    # MAKTX → brand is still pending (0.2) and is the only blocker left
    assert codes == {("PENDING_REVIEW", "brand")}

    preview = report["dry_run"]["preview"][0]
    assert preview["price"] == {"amount": 1250.0, "currency": "EUR"}
    assert preview["sku"] == "000000010001234"
    assert preview["stock_quantity"] == 12.0


def test_duplicate_and_unknown_targets(client: TestClient) -> None:
    result = _erp_result()
    result.mappings.append(FieldMapping("MAKTX", "title", "rename", 0.9, "Hallucinated."))
    result.mappings[2] = FieldMapping("MTART", "sku", "rename", 0.9, "Also an id?")
    _register_and_map(client, result)

    codes = _codes(client.post("/sources/erp/mapping/validate").json())
    assert ("DUPLICATE_TARGET", "sku") in codes
    assert ("UNKNOWN_TARGET", "MAKTX") in codes


# ── coverage matrix ───────────────────────────────────────────────────────────


def test_coverage_matrix(client: TestClient) -> None:
    _register_and_map(client)
    client.post(
        "/sources",
        json={"source_id": "pim", "name": "PIM", "sample_rows": [{"product_ref": "A"}]},
    )

    body = client.get("/coverage").json()

    assert [s["source_id"] for s in body["sources"]] == ["erp", "pim"]
    cells = {(c["source_id"], c["field"]): c for c in body["cells"]}
    assert cells[("erp", "sku")]["status"] == "mapped"
    assert cells[("erp", "sku")]["source_col"] == "MATNR"
    assert cells[("erp", "category")]["status"] == "needs_review"
    assert cells[("erp", "brand")]["status"] == "missing"
    assert cells[("pim", "sku")]["status"] == "missing"  # not mapped yet
    assert len(body["cells"]) == 2 * 11


# ── export ────────────────────────────────────────────────────────────────────


def test_export_dbt_sql(client: TestClient) -> None:
    _register_and_map(client)
    resp = client.get("/sources/erp/mapping/export", params={"format": "dbt_sql"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["filename"] == "stg_erp__product.sql"
    assert "{{ source('udc', 'erp') }}" in body["content"]
    assert any("Required field brand" in w for w in body["warnings"])


def test_export_rejects_unknown_format(client: TestClient) -> None:
    _register_and_map(client)
    resp = client.get("/sources/erp/mapping/export", params={"format": "xml"})
    assert resp.status_code == 422
    assert "dbt_sql" in resp.text


def test_accepting_a_pending_drop_keeps_the_column_out(client: TestClient) -> None:
    result = _erp_result()
    result.mappings[2] = FieldMapping("MTART", "category", "drop", 0.40, "Material type.")
    body = _register_and_map(client, result)
    mtart = next(m for m in body["mappings"] if m["source_col"] == "MTART")
    assert mtart["state"] == "needs_review"

    resp = client.patch("/sources/erp/mapping/fields/MTART", json={"status": "accepted"})
    assert resp.status_code == 200
    assert resp.json()["mapping"]["state"] == "dropped"
    assert resp.json()["mapping"]["transform"] == "drop"

    # giving it a target instead maps it as is
    resp = client.patch(
        "/sources/erp/mapping/fields/MTART",
        json={"status": "edited", "target_col": "material"},
    )
    assert resp.json()["mapping"]["transform"] == "rename"
    assert resp.json()["mapping"]["state"] == "mapped"
