"""Internal utilities shared across the udc package."""

import re

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def validate_identifier(name: str, label: str = "identifier") -> str:
    """Raise ValueError if *name* is not a safe SQL identifier.

    Allows only letters, digits and underscores — no spaces, dots, or
    special characters — to prevent SQL injection via column/table names.
    """
    if not _IDENT_RE.fullmatch(name):
        raise ValueError(
            f"Unsafe SQL {label} {name!r}. "
            "Only letters, digits and underscores are allowed."
        )
    return name
