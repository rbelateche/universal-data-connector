"""Tests for the review policy (udc.mapper.review)."""

import pytest

from udc.mapper.models import FieldMapping
from udc.mapper.review import mapping_state, nest, type_problem


def _m(transform: str = "rename", confidence: float = 0.9, status: str = "proposed") -> FieldMapping:
    return FieldMapping("src", "tgt", transform, confidence, "r", {}, status)


@pytest.mark.parametrize(
    ("mapping", "state"),
    [
        (_m(confidence=0.7), "mapped"),  # threshold is inclusive
        (_m(confidence=0.69), "needs_review"),
        (_m(confidence=0.1, status="accepted"), "mapped"),  # a human decided
        (_m(confidence=0.99, status="rejected"), "rejected"),
        (_m(transform="drop"), "dropped"),
        (_m(transform="drop", confidence=0.4), "needs_review"),  # "unsure where it goes"
        (_m(transform="drop", confidence=0.4, status="accepted"), "dropped"),
    ],
)
def test_mapping_state(mapping: FieldMapping, state: str) -> None:
    assert mapping_state(mapping) == state


@pytest.mark.parametrize(
    ("transform", "target_type", "source_type", "ok"),
    [
        ("rename", "TEXT", "integer", True),  # zero-padded ids stay strings
        ("cast_int", "TEXT", "integer", False),
        ("parse_decimal", "DECIMAL", "string", True),
        ("parse_decimal", "INTEGER", "float", True),  # numeric → numeric
        ("rename", "DECIMAL", "string", False),
        ("rename", "TIMESTAMP", "datetime", True),
        ("cast_int", "TIMESTAMP", "integer", False),
    ],
)
def test_type_problem(transform: str, target_type: str, source_type: str, ok: bool) -> None:
    assert (type_problem(_m(transform), target_type, source_type) is None) is ok


def test_nest_dotted_paths() -> None:
    assert nest({"price.amount": 1.0, "price.currency": "EUR", "sku": "A"}) == {
        "price": {"amount": 1.0, "currency": "EUR"},
        "sku": "A",
    }


def test_pending_drop_neither_fills_nor_blocks_its_target() -> None:
    from udc.mapper.canonical import get_fields
    from udc.mapper.models import MappingResult
    from udc.mapper.review import coverage, validate

    result = MappingResult(
        "ecom",
        "Product",
        [
            FieldMapping("handle", "brand", "drop", 0.3, "slug, not a brand"),
            FieldMapping("title_fr", "", "drop", 0.4, "no target"),
        ],
        [],
        [],
    )
    fields = get_fields("Product")
    assert "brand" in coverage(result, fields).missing_required  # not "pending"

    issues = validate(result, fields, [{"handle": "lune-bag", "title_fr": "Sac"}]).issues
    pending = [i for i in issues if i.code == "PENDING_REVIEW"]
    assert {(i.field, i.severity) for i in pending} == {("handle", "warning"), ("title_fr", "warning")}
    assert not [i for i in issues if i.code == "UNKNOWN_TARGET"]
