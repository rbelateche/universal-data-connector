"""Tests for the canonical schema registry."""

import pytest

from udc.mapper.canonical import CANONICAL_SCHEMAS, get_fields, required_paths


def test_product_required_fields() -> None:
    assert required_paths("Product") == [
        "sku",
        "name",
        "brand",
        "category",
        "price.amount",
        "price.currency",
    ]


def test_prompt_view_is_derived_from_fields() -> None:
    assert CANONICAL_SCHEMAS["Product"]["price.amount"] == "DECIMAL"
    assert CANONICAL_SCHEMAS["Product"]["stock_quantity"] == "INTEGER"
    # Contact keeps the exact shape the mapper has always been prompted with
    assert CANONICAL_SCHEMAS["Contact"] == {
        "customer_id": "INTEGER",
        "full_name": "TEXT",
        "email": "TEXT",
        "phone": "TEXT",
        "is_active": "BOOLEAN",
        "created_at": "TIMESTAMP",
    }


def test_every_field_has_a_description() -> None:
    for name in CANONICAL_SCHEMAS:
        assert all(f.description for f in get_fields(name)), name


def test_unknown_schema_lists_valid_names() -> None:
    with pytest.raises(KeyError, match="Contact"):
        get_fields("Invoice")
