"""Canonical Pydantic schemas for well-known entity types.

These are the *target* schemas that source data gets mapped into.
Any source (Postgres, CSV, JSON API) is normalised to one of these shapes.
"""

from datetime import datetime

from pydantic import BaseModel


class ContactSchema(BaseModel):
    """A person or organisation in a CRM / customer database."""

    customer_id: int
    full_name: str
    email: str | None = None
    phone: str | None = None
    is_active: bool = True
    created_at: datetime | None = None


class OrderSchema(BaseModel):
    """A sales order or transaction."""

    order_id: int
    customer_id: int
    revenue_usd: float
    currency: str = "USD"
    status: str = "unknown"
    created_at: datetime | None = None


class ProductSchema(BaseModel):
    """A product or SKU in a catalogue."""

    product_id: int
    name: str
    sku: str | None = None
    price_usd: float | None = None
    category: str | None = None
    is_available: bool = True


# Registry: maps schema name → Pydantic model + field type map for prompting
CANONICAL_SCHEMAS: dict[str, dict[str, str]] = {
    "Contact": {
        "customer_id": "INTEGER",
        "full_name": "TEXT",
        "email": "TEXT",
        "phone": "TEXT",
        "is_active": "BOOLEAN",
        "created_at": "TIMESTAMP",
    },
    "Order": {
        "order_id": "INTEGER",
        "customer_id": "INTEGER",
        "revenue_usd": "FLOAT",
        "currency": "TEXT",
        "status": "TEXT",
        "created_at": "TIMESTAMP",
    },
    "Product": {
        "product_id": "INTEGER",
        "name": "TEXT",
        "sku": "TEXT",
        "price_usd": "FLOAT",
        "category": "TEXT",
        "is_available": "BOOLEAN",
    },
}
