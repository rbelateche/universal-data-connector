# UDC Mapping Review — MCP App

## Value Proposition

Consolidate product data from several systems into one core **Product** model without
hand-writing field mappings. Target: data/integration teams at a retail brand (demo: the
fictional *Maison Vellandre*). Pain: every new source (ERP export, PIM, e-commerce
catalogue) means reading cryptic field names (`MATNR`, `option1`), guessing types and
formats, and writing transformation code by hand.

**Core actions**: review a proposed source → core mapping, decide the uncertain fields,
export the mapping as code.

## Why LLM?

**Conversational win**: "map the ERP export and tell me what's blocking" is one sentence
instead of a spreadsheet of 30 fields.
**LLM adds**: proposals with confidence and a rationale (UDC's mapper), and an agent that
explains issues, suggests fixes (`parse_decimal` for `1.250,00`) and chains
validate → export.
**What LLM lacks**: the source schemas, sample rows, the core model, persistence of
decisions, and the transformation engine. All of those live in UDC.

**Principle**: the LLM proposes, the human decides. Proposals below 0.7 confidence are
decided by the user, in the review table or by saying so.

## UI Overview

**First view**: the mapping review table for one source: coverage of required core
fields in the header, one row per source field (sample values, proposed target, confidence
badge, transformation, rationale). Rows below 0.7 are highlighted.
**Key interactions**: accept / reject a row, pick another target field or transformation
from a dropdown; each action is saved in UDC immediately and the coverage updates.
Validate runs the dry run in place. Expand switches to fullscreen.
**Second view**: the coverage matrix: core fields × sources, so the user sees where each
required field can come from.
**End state**: validation passes (or the remaining gaps are known) and the agent exports a
JSON spec, a dbt model or a PySpark function.

## Product Context

- **Existing product**: Universal Data Connector, a FastAPI backend (Python) with an
  LLM schema mapper, a transformation engine and DuckDB storage. It is the system of
  record: this app wraps its REST API and does not duplicate its logic.
- **API**: UDC REST on `UDC_API_URL` (default `http://localhost:8000`), optional
  `X-Api-Key`.
- **Auth**: none for the demo (local / tunnel).
- **Constraints**: Skybridge serves MCP statelessly, so every decision is persisted in UDC
  rather than in the view.

## UX Flows

Review a source:
1. Find the source (list_sources) or register one (register_source)
2. Review the mapping in the table (propose_mapping)
3. Decide low-confidence rows (in the table, or update_mapping from chat)
4. Validate (validate_mapping)
5. Export (export_mapping)

Compare sources:
1. Coverage matrix (get_coverage)

## Tools and Views

| Name | Kind | Input | Output |
|---|---|---|---|
| `list_sources` | tool | `{}` | `{ sources[] }` with review status and required coverage |
| `register_source` | tool | `{ source_id, name, system?, fields?, sample_rows? }` | `{ source_id, field_count, sample_row_count }` |
| `get_core_model` | tool | `{}` | `{ entity, fields[] }` with required flags |
| `propose_mapping` | **view** `mapping-review` | `{ source_id, refresh? }` | `{ source_name, coverage, mappings[], unmapped_source_fields }`; `_meta`: core fields, sample values |
| `update_mapping` | tool (called by the view) | `{ source_id, source_field, status, target_field?, transformation?, value_map? }` | `{ mapping, coverage }` |
| `validate_mapping` | tool (also called by the view) | `{ source_id, sample_limit? }` | `{ ok, issues[], dry_run }` |
| `export_mapping` | tool | `{ source_id, format: json \| dbt_sql \| pyspark }` | `{ filename, content, warnings[] }` |
| `get_coverage` | **view** `coverage-matrix` | `{}` | `{ sources[], fields[].by_source, unsourced_required }`; `_meta`: cells |

**View state** (`mapping-review`): the decisions made in the table (small, model-visible).
`data-llm` narrates what is still pending.
