"""Demo tooling.

    uv run python -m udc.demo seed     # load demo sources into DUCKDB_PATH
    uv run python -m udc.demo record [source_id ...]   # re-record with live Claude calls

``seed`` writes to the DuckDB file directly, so run it while the API is stopped
(DuckDB allows one writing process). ``make demo-api`` seeds at startup instead.
"""

import sys

import anthropic

from udc.core.config import get_settings
from udc.core.source_store import SourceStore
from udc.demo.seed import record_demo, seed_demo
from udc.mapper.mapper import SchemaMapper, describe_api_error
from udc.mapper.store import MappingStore


def main(argv: list[str]) -> int:
    command = argv[1] if len(argv) > 1 else ""
    settings = get_settings()
    if command == "seed":
        added = seed_demo(SourceStore(settings.duckdb_path), MappingStore(settings.duckdb_path))
        print(
            f"Seeded {', '.join(added) or 'nothing (already present)'} into {settings.duckdb_path}"
        )
        return 0
    if command == "record":
        if not settings.anthropic_api_key:
            print(
                "ANTHROPIC_API_KEY is not set (backend/.env or the environment).", file=sys.stderr
            )
            return 1
        mapper = SchemaMapper(api_key=settings.anthropic_api_key, model=settings.anthropic_model)
        try:
            for path in record_demo(mapper, settings.anthropic_model, argv[2:] or None):
                print(f"Recorded {path}")
        except anthropic.APIStatusError as exc:
            print(describe_api_error(exc), file=sys.stderr)
            return 1
        except anthropic.APIConnectionError:
            print("Could not reach the Claude API. Check the network and retry.", file=sys.stderr)
            return 1
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
