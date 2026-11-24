"""Canonical schemas for well-known entity types.

These are the *target* schemas that source data gets mapped into.
Any source (Postgres, CSV, JSON API) is normalised to one of these shapes.

Each schema is described once, as a list of ``CanonicalField`` (path, type,
required, description). ``CANONICAL_SCHEMAS`` — the ``{field: TYPE}`` view the
mapping prompt uses — is derived from it. Nested fields use dotted paths
(``price.amount``).
"""

from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel


@dataclass(frozen=True)
class CanonicalField:
    """One field of a canonical schema."""

    path: str  # dotted for nested fields, e.g. "price.amount"
    type: str  # TEXT | INTEGER | DECIMAL | FLOAT | BOOLEAN | TIMESTAMP
    required: bool
    description: str


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


class Price(BaseModel):
    amount: float
    currency: str


class ProductSchema(BaseModel):
    """A sellable product or variant in a retail catalogue."""

    sku: str
    name: str
    brand: str
    category: str
    price: Price
    material: str | None = None
    color: str | None = None
    size: str | None = None
    stock_quantity: int | None = None
    created_at: datetime | None = None


CANONICAL_FIELDS: dict[str, list[CanonicalField]] = {
    "Contact": [
        CanonicalField("customer_id", "INTEGER", True, "Unique customer identifier."),
        CanonicalField("full_name", "TEXT", True, "Person or organisation name."),
        CanonicalField("email", "TEXT", False, "Primary email address."),
        CanonicalField("phone", "TEXT", False, "Primary phone number."),
        CanonicalField("is_active", "BOOLEAN", False, "Whether the customer is active."),
        CanonicalField("created_at", "TIMESTAMP", False, "When the record was created."),
    ],
    "Order": [
        CanonicalField("order_id", "INTEGER", True, "Unique order identifier."),
        CanonicalField("customer_id", "INTEGER", True, "Customer who placed the order."),
        CanonicalField("revenue_usd", "FLOAT", True, "Order revenue in USD."),
        CanonicalField("currency", "TEXT", False, "Original currency code."),
        CanonicalField("status", "TEXT", False, "Order status."),
        CanonicalField("created_at", "TIMESTAMP", False, "When the order was placed."),
    ],
    "Product": [
        CanonicalField(
            "sku",
            "TEXT",
            True,
            "Stock keeping unit: unique identifier of the sellable item or variant. "
            "Text, leading zeros are significant.",
        ),
        CanonicalField("name", "TEXT", True, "Customer-facing product name, English preferred."),
        CanonicalField("brand", "TEXT", True, "Brand or maison the product is sold under."),
        CanonicalField(
            "category", "TEXT", True, "Merchandise category, e.g. Bags, Shoes, Ready-to-wear."
        ),
        CanonicalField(
            "price.amount",
            "DECIMAL",
            True,
            "Current selling price, tax included. Not a compare-at or original price.",
        ),
        CanonicalField("price.currency", "TEXT", True, "ISO 4217 currency code, e.g. EUR."),
        CanonicalField("material", "TEXT", False, "Main material or composition."),
        CanonicalField("color", "TEXT", False, "Colour name, e.g. Black."),
        CanonicalField("size", "TEXT", False, "Size label, e.g. M, 38, One size."),
        CanonicalField("stock_quantity", "INTEGER", False, "Units available to sell."),
        CanonicalField("created_at", "TIMESTAMP", False, "When the product record was created."),
    ],
}

# Registry used by the mapping prompt: schema name → {field path: TYPE}
CANONICAL_SCHEMAS: dict[str, dict[str, str]] = {
    name: {f.path: f.type for f in fields} for name, fields in CANONICAL_FIELDS.items()
}


def get_fields(schema_name: str) -> list[CanonicalField]:
    """Return the fields of *schema_name*. Raises KeyError for unknown schemas."""
    if schema_name not in CANONICAL_FIELDS:
        raise KeyError(f"Unknown schema {schema_name!r}. Choose from: {sorted(CANONICAL_FIELDS)}")
    return CANONICAL_FIELDS[schema_name]


def required_paths(schema_name: str) -> list[str]:
    """Paths of the required fields of *schema_name*, in declaration order."""
    return [f.path for f in get_fields(schema_name) if f.required]
