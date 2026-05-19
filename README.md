# Universal Data Connector

Connect any data source, map it to a canonical schema using Claude, and serve the clean output over a REST API.

## What it does

1. **Register a connector** — point it at a Postgres table, CSV file, or JSON API
2. **Trigger a job** — the pipeline samples rows, infers column types, calls Claude to map fields to a target schema (Contact / Order / Product), applies type coercions, and stores the result
3. **Inspect & correct** — review field mappings with confidence scores and LLM reasoning; patch any field with a human override
4. **Consume the output** — paginated canonicalized rows via REST; schema diff detection across runs

## Stack

- **Python 3.11**, FastAPI, pydantic-settings, SQLAlchemy Core
- **Anthropic Claude** (`claude-3-5-haiku`) via `tool_use` for structured schema inference
- **DuckDB** — local persistence for connectors, jobs, mappings, transformed rows, schema snapshots
- **uv** package manager, `src/` layout, ruff + mypy strict, pytest

## API

```
POST   /connectors                          register a data source
POST   /jobs                                trigger ingestion + mapping (202, background)
GET    /jobs/{id}                           poll status + progress %
GET    /jobs/{id}/mapping                   field mappings with confidence + reasoning
PATCH  /jobs/{id}/mapping/fields/{field}    human override
GET    /data/{job_id}?offset=&limit=        paginated canonicalized rows
GET    /schema/{job_id}/diff               schema diff vs previous run
POST   /mappings/infer                      one-shot mapping without a job
```

All endpoints require `X-Api-Key` header. Set `API_KEY` in `.env`.

## Quick start

```bash
cp backend/.env.example backend/.env   # fill in DATABASE_URL + ANTHROPIC_API_KEY
cd infra && make install
make api                               # FastAPI on :8000
make check                             # lint + types + 146 tests
```
