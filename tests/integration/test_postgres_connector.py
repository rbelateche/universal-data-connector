"""Integration tests for PostgresConnector — requires a live DATABASE_URL."""

import os

import pytest

from udc.connectors.postgres import PostgresConnector

DATABASE_URL = os.getenv("DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL not set — skipping Postgres integration tests",
)

# Sync SQLAlchemy needs psycopg2, but the env var may use asyncpg scheme.
# Normalise to a sync URL for these tests.
_SYNC_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg2://")


@pytest.fixture(scope="module", autouse=True)
def seed_table() -> None:
    """Create and seed a test table, drop it afterwards."""
    from sqlalchemy import create_engine, text

    engine = create_engine(_SYNC_URL)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS udc_test_orders"))
        conn.execute(text(
            """
            CREATE TABLE udc_test_orders (
                id         SERIAL PRIMARY KEY,
                customer   TEXT,
                amount     NUMERIC(10,2),
                updated_at TIMESTAMP DEFAULT NOW()
            )
            """
        ))
        conn.execute(text(
            "INSERT INTO udc_test_orders (customer, amount) VALUES "
            "('Alice', 99.9), ('Bob', 149.0), ('Carol', 49.5)"
        ))
    yield
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS udc_test_orders"))
    engine.dispose()


def test_connect_and_sample() -> None:
    with PostgresConnector(_SYNC_URL, "udc_test_orders") as conn:
        rows = conn.sample(2)
    assert len(rows) == 2


def test_sample_returns_dicts() -> None:
    with PostgresConnector(_SYNC_URL, "udc_test_orders") as conn:
        rows = conn.sample(10)
    assert isinstance(rows[0], dict)
    assert "customer" in rows[0]


def test_get_schema() -> None:
    with PostgresConnector(_SYNC_URL, "udc_test_orders") as conn:
        schema = conn.get_schema()
    assert "id" in schema
    assert "customer" in schema
    assert "amount" in schema


def test_stream_all_rows() -> None:
    with PostgresConnector(_SYNC_URL, "udc_test_orders") as conn:
        rows = [r for batch in conn.stream(batch_size=2) for r in batch]
    assert len(rows) == 3


def test_invalid_table_name() -> None:
    with pytest.raises(ValueError, match="Unsafe SQL"):
        PostgresConnector(_SYNC_URL, "bad-table; DROP TABLE orders--")


def test_connect_required() -> None:
    conn = PostgresConnector(_SYNC_URL, "udc_test_orders")
    with pytest.raises(RuntimeError, match="connect"):
        conn.sample()
