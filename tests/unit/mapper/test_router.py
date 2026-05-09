"""Tests for the /mappings API router."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from udc.api.app import create_app
from udc.core.config import Settings, get_settings
from udc.mapper.models import FieldMapping, MappingResult

_SAMPLE_ROWS = [
    {"cust_id": "1", "full_nm": "Alice", "actv": "Y"},
    {"cust_id": "2", "full_nm": "Bob", "actv": "N"},
]

_MOCK_RESULT = MappingResult(
    source_id="pg-crm",
    target_schema_name="Contact",
    mappings=[
        FieldMapping("cust_id", "customer_id", "cast_int", 0.95, "ID col", {}),
        FieldMapping("full_nm", "full_name", "rename", 0.90, "Name", {}),
        FieldMapping("actv", "is_active", "map_values", 0.85, "Flag", {"Y": True, "N": False}),
    ],
    unmapped_source=[],
    unmapped_target=[],
)


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    app = create_app()

    settings = Settings(
        database_url="postgresql://test:test@localhost/test",
        anthropic_api_key="test-key",
        duckdb_path=str(tmp_path / "test.duckdb"),
    )
    app.dependency_overrides[get_settings] = lambda: settings

    # Reset the router-level singleton store between tests
    import udc.api.routers.mappings as m_mod

    m_mod._STORE = None
    return TestClient(app)


# ── POST /mappings/infer ──────────────────────────────────────────────────────

def test_infer_returns_200(client: TestClient) -> None:
    with patch("udc.api.routers.mappings.SchemaMapper") as MockMapper:
        MockMapper.return_value.infer.return_value = _MOCK_RESULT
        resp = client.post(
            "/mappings/infer",
            json={
                "source_id": "pg-crm",
                "target_schema_name": "Contact",
                "sample_rows": _SAMPLE_ROWS,
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "mapping_id" in data
    assert data["source_id"] == "pg-crm"
    assert len(data["mappings"]) == 3


def test_infer_unknown_schema_returns_422(client: TestClient) -> None:
    resp = client.post(
        "/mappings/infer",
        json={
            "source_id": "pg-crm",
            "target_schema_name": "NonExistent",
            "sample_rows": _SAMPLE_ROWS,
        },
    )
    assert resp.status_code == 422


# ── GET /mappings/{id} ────────────────────────────────────────────────────────

def test_get_saved_mapping(client: TestClient) -> None:
    with patch("udc.api.routers.mappings.SchemaMapper") as MockMapper:
        MockMapper.return_value.infer.return_value = _MOCK_RESULT
        post = client.post(
            "/mappings/infer",
            json={
                "source_id": "pg-crm",
                "target_schema_name": "Contact",
                "sample_rows": _SAMPLE_ROWS,
            },
        )
    mid = post.json()["mapping_id"]
    resp = client.get(f"/mappings/{mid}")
    assert resp.status_code == 200
    assert resp.json()["mapping_id"] == mid


def test_get_missing_mapping_returns_404(client: TestClient) -> None:
    resp = client.get("/mappings/999")
    assert resp.status_code == 404


# ── PATCH /mappings/{id}/overrides ────────────────────────────────────────────

def test_override_existing_mapping(client: TestClient) -> None:
    with patch("udc.api.routers.mappings.SchemaMapper") as MockMapper:
        MockMapper.return_value.infer.return_value = _MOCK_RESULT
        post = client.post(
            "/mappings/infer",
            json={
                "source_id": "pg-crm",
                "target_schema_name": "Contact",
                "sample_rows": _SAMPLE_ROWS,
            },
        )
    mid = post.json()["mapping_id"]

    resp = client.patch(
        f"/mappings/{mid}/overrides",
        json={"source_col": "cust_id", "patch": {"transform": "cast_float", "confidence": 1.0}},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_override_missing_mapping_returns_404(client: TestClient) -> None:
    resp = client.patch(
        "/mappings/999/overrides",
        json={"source_col": "col", "patch": {"transform": "rename"}},
    )
    assert resp.status_code == 404


# ── POST /mappings/apply ──────────────────────────────────────────────────────

def test_apply_mapping(client: TestClient) -> None:
    with patch("udc.api.routers.mappings.SchemaMapper") as MockMapper:
        MockMapper.return_value.infer.return_value = _MOCK_RESULT
        post = client.post(
            "/mappings/infer",
            json={
                "source_id": "pg-crm",
                "target_schema_name": "Contact",
                "sample_rows": _SAMPLE_ROWS,
            },
        )
    mid = post.json()["mapping_id"]

    resp = client.post(
        "/mappings/apply",
        json={
            "mapping_id": mid,
            "rows": [{"cust_id": "5", "full_nm": "Eve", "actv": "Y"}],
        },
    )
    assert resp.status_code == 200
    row = resp.json()[0]
    assert row["customer_id"] == 5
    assert row["full_name"] == "Eve"
    assert row["is_active"] is True


def test_apply_missing_mapping_returns_404(client: TestClient) -> None:
    resp = client.post(
        "/mappings/apply",
        json={"mapping_id": 999, "rows": []},
    )
    assert resp.status_code == 404


# ── POST /mappings/merge ──────────────────────────────────────────────────────

def test_merge_last_wins(client: TestClient) -> None:
    resp = client.post(
        "/mappings/merge",
        json={
            "left_rows": [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}],
            "right_rows": [{"id": 2, "name": "Bob Updated"}, {"id": 3, "name": "Carol"}],
            "key": "id",
            "strategy": "last_wins",
        },
    )
    assert resp.status_code == 200
    by_id = {r["id"]: r for r in resp.json()}
    assert len(by_id) == 3
    assert by_id[2]["name"] == "Bob Updated"


def test_merge_invalid_strategy_returns_422(client: TestClient) -> None:
    resp = client.post(
        "/mappings/merge",
        json={
            "left_rows": [],
            "right_rows": [],
            "key": "id",
            "strategy": "bad",
        },
    )
    assert resp.status_code == 422
