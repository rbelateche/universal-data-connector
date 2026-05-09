"""Tests for Reconciler — multi-source merge strategies."""

import pytest

from udc.mapper.reconcile import Reconciler

_LEFT = [
    {"customer_id": 1, "name": "Alice", "source": "pg"},
    {"customer_id": 2, "name": "Bob", "source": "pg"},
]

_RIGHT = [
    {"customer_id": 2, "name": "Bob Updated", "source": "csv"},
    {"customer_id": 3, "name": "Carol", "source": "csv"},
]


def test_last_wins_overlap() -> None:
    rec = Reconciler(key="customer_id", strategy="last_wins")
    merged = rec.merge(_LEFT, _RIGHT)
    by_id = {r["customer_id"]: r for r in merged}

    assert len(merged) == 3
    assert by_id[2]["name"] == "Bob Updated"  # right wins
    assert by_id[1]["source"] == "pg"


def test_left_wins_overlap() -> None:
    rec = Reconciler(key="customer_id", strategy="left_wins")
    merged = rec.merge(_LEFT, _RIGHT)
    by_id = {r["customer_id"]: r for r in merged}

    assert len(merged) == 3
    assert by_id[2]["name"] == "Bob"  # left wins


def test_union_keeps_all() -> None:
    rec = Reconciler(key="customer_id", strategy="union")
    merged = rec.merge(_LEFT, _RIGHT)
    assert len(merged) == 4  # no dedup


def test_no_overlap() -> None:
    left = [{"id": 1, "v": "a"}]
    right = [{"id": 2, "v": "b"}]
    rec = Reconciler(key="id")
    merged = rec.merge(left, right)
    assert len(merged) == 2


def test_empty_left() -> None:
    rec = Reconciler(key="customer_id")
    merged = rec.merge([], _RIGHT)
    assert len(merged) == len(_RIGHT)


def test_empty_right() -> None:
    rec = Reconciler(key="customer_id")
    merged = rec.merge(_LEFT, [])
    assert len(merged) == len(_LEFT)


def test_invalid_strategy_raises() -> None:
    with pytest.raises(ValueError, match="Unknown strategy"):
        Reconciler(key="id", strategy="random")


def test_stats() -> None:
    rec = Reconciler(key="customer_id")
    s = rec.stats(_LEFT, _RIGHT)
    assert s["left_count"] == 2
    assert s["right_count"] == 2
    assert s["overlap_count"] == 1  # customer_id=2 appears in both
    assert s["merged_count"] == 3
