"""Unit tests for JsonApiConnector using httpx mock transport."""

import json

import httpx
import pytest

from udc.connectors.json_api import JsonApiConnector


def _make_transport(pages: list[list[dict] | dict]) -> httpx.MockTransport:
    """Build a mock transport that serves a sequence of responses."""
    responses = iter(pages)

    def handler(request: httpx.Request) -> httpx.Response:
        try:
            body = next(responses)
        except StopIteration:
            return httpx.Response(404)
        return httpx.Response(200, json=body)

    return httpx.MockTransport(handler)


_RECORDS = [{"id": i, "name": f"item-{i}"} for i in range(1, 6)]


def test_sample_flat_array() -> None:
    transport = _make_transport([_RECORDS])
    conn = JsonApiConnector("http://api/items", transport=transport)
    with conn:
        rows = conn.sample(3)
    assert len(rows) == 3
    assert rows[0]["id"] == 1


def test_sample_with_data_key() -> None:
    transport = _make_transport([{"results": _RECORDS, "next": None}])
    conn = JsonApiConnector(
        "http://api/items", data_key="results", next_key="next", transport=transport
    )
    with conn:
        rows = conn.sample(100)
    assert len(rows) == 5


def test_pagination_next_key() -> None:
    page1 = {"data": [{"id": 1}, {"id": 2}], "next": "http://api/items?page=2"}
    page2 = {"data": [{"id": 3}], "next": None}
    transport = _make_transport([page1, page2])
    conn = JsonApiConnector(
        "http://api/items", data_key="data", next_key="next", transport=transport
    )
    with conn:
        rows = conn.sample(100)
    assert len(rows) == 3
    assert rows[2]["id"] == 3


def test_stream_batches() -> None:
    transport = _make_transport([_RECORDS])
    conn = JsonApiConnector("http://api/items", transport=transport)
    with conn:
        batches = list(conn.stream(batch_size=2))
    assert len(batches) == 3  # 5 items / batch_size 2 → ceil(5/2) = 3


def test_stream_watermark() -> None:
    transport = _make_transport([_RECORDS])
    conn = JsonApiConnector("http://api/items", transport=transport)
    with conn:
        rows = list(conn.stream(watermark_col="id", watermark_val=3))
    flat = [r for batch in rows for r in batch]
    assert all(r["id"] > 3 for r in flat)


def test_get_schema() -> None:
    transport = _make_transport([_RECORDS])
    conn = JsonApiConnector("http://api/items", transport=transport)
    with conn:
        schema = conn.get_schema()
    assert schema["id"] == "int"
    assert schema["name"] == "str"


def test_connect_required() -> None:
    conn = JsonApiConnector("http://api/items")
    with pytest.raises(RuntimeError, match="connect"):
        conn.sample()
