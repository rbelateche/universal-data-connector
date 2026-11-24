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
