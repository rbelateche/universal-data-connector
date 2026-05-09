"""Tests for SchemaMapper — mocks the Anthropic client, no real API calls."""

from unittest.mock import MagicMock

import pytest

from udc.core.sampler import ColumnStats, SchemaSampler
from udc.mapper.mapper import SchemaMapper
from udc.mapper.models import MappingResult


def _make_stats() -> dict[str, ColumnStats]:
    rows = [
        {"cust_id": "1", "full_nm": "Alice", "actv": "Y", "rev": "99.9"},
        {"cust_id": "2", "full_nm": "Bob", "actv": "N", "rev": "149.0"},
    ]
    return SchemaSampler().run(rows)


_TARGET_SCHEMA = {
    "customer_id": "INTEGER",
    "full_name": "TEXT",
    "is_active": "BOOLEAN",
    "revenue_usd": "FLOAT",
}

_CLAUDE_RESPONSE = {
    "mappings": [
        {
            "source_col": "cust_id",
            "target_col": "customer_id",
            "transform": "cast_int",
            "confidence": 0.95,
            "reasoning": "Numeric ID column.",
            "value_map": {},
        },
        {
            "source_col": "full_nm",
            "target_col": "full_name",
            "transform": "rename",
            "confidence": 0.90,
            "reasoning": "Name abbreviation.",
            "value_map": {},
        },
        {
            "source_col": "actv",
            "target_col": "is_active",
            "transform": "map_values",
            "confidence": 0.85,
            "reasoning": "Y/N flag.",
            "value_map": {"Y": True, "N": False},
        },
        {
            "source_col": "rev",
            "target_col": "revenue_usd",
            "transform": "cast_float",
            "confidence": 0.80,
            "reasoning": "Revenue column.",
            "value_map": {},
        },
    ],
    "unmapped_source": [],
    "unmapped_target": [],
}


def _mock_client(tool_input: dict) -> MagicMock:
    """Build a minimal mock that mimics the Anthropic client response."""
    block = MagicMock()
    block.type = "tool_use"
    block.input = tool_input

    message = MagicMock()
    message.content = [block]

    client = MagicMock()
    client.messages.create.return_value = message
    return client


def test_infer_returns_mapping_result() -> None:
    client = _mock_client(_CLAUDE_RESPONSE)
    mapper = SchemaMapper(api_key="test-key", client=client)
    result = mapper.infer(
        stats=_make_stats(),
        target_schema=_TARGET_SCHEMA,
        source_id="pg-crm",
        target_schema_name="Contact",
    )
    assert isinstance(result, MappingResult)
    assert len(result.mappings) == 4


def test_infer_field_details() -> None:
    client = _mock_client(_CLAUDE_RESPONSE)
    mapper = SchemaMapper(api_key="test-key", client=client)
    result = mapper.infer(_make_stats(), _TARGET_SCHEMA, "src", "Contact")

    cust = next(m for m in result.mappings if m.source_col == "cust_id")
    assert cust.target_col == "customer_id"
    assert cust.transform == "cast_int"
    assert cust.confidence == pytest.approx(0.95)


def test_infer_value_map_preserved() -> None:
    client = _mock_client(_CLAUDE_RESPONSE)
    mapper = SchemaMapper(api_key="test-key", client=client)
    result = mapper.infer(_make_stats(), _TARGET_SCHEMA, "src", "Contact")

    actv = next(m for m in result.mappings if m.source_col == "actv")
    assert actv.value_map == {"Y": True, "N": False}


def test_infer_low_confidence_flagged() -> None:
    low = dict(_CLAUDE_RESPONSE)
    low["mappings"] = [
        {**m, "confidence": 0.5} for m in _CLAUDE_RESPONSE["mappings"]
    ]
    client = _mock_client(low)
    mapper = SchemaMapper(api_key="test-key", client=client)
    result = mapper.infer(_make_stats(), _TARGET_SCHEMA, "src", "Contact")
    assert result.needs_review is True
    assert len(result.low_confidence) == 4


def test_infer_unmapped_target() -> None:
    response = dict(_CLAUDE_RESPONSE)
    response = {**_CLAUDE_RESPONSE, "unmapped_target": ["email"]}
    client = _mock_client(response)
    mapper = SchemaMapper(api_key="test-key", client=client)
    result = mapper.infer(_make_stats(), _TARGET_SCHEMA, "src", "Contact")
    assert "email" in result.unmapped_target
    assert result.needs_review is True


def test_no_tool_use_block_raises() -> None:
    block = MagicMock()
    block.type = "text"  # not tool_use

    message = MagicMock()
    message.content = [block]

    client = MagicMock()
    client.messages.create.return_value = message

    mapper = SchemaMapper(api_key="test-key", client=client)
    with pytest.raises(ValueError, match="submit_mapping"):
        mapper.infer(_make_stats(), _TARGET_SCHEMA, "src", "Contact")
