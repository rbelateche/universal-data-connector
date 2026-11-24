import { Skybridge } from "skybridge/server";
import { type CallLogger, createCallLogger } from "./lib/call-log.js";
import { type AppConfig, loadConfig } from "./lib/config.js";
import {
  coverageLine,
  describeMapping,
  describeValidation,
  REVIEW_THRESHOLD,
  TRANSFORMATIONS,
  toReviewRow,
  toolError,
} from "./lib/present.js";
import {
  coreModelOutput,
  coverageOutput,
  exportMappingInput,
  exportMappingOutput,
  listSourcesOutput,
  proposeMappingInput,
  proposeMappingOutput,
  registerSourceInput,
  registerSourceOutput,
  updateMappingInput,
  updateMappingOutput,
  validateMappingInput,
  validateMappingOutput,
} from "./lib/schemas.js";
import { type SourceDetail, type SourceMapping, UdcClient, UdcError } from "./lib/udc-client.js";

const CORE_MODEL = "Product";

const INSTRUCTIONS = `Universal Data Connector (UDC) maps product data from source systems \
(ERP, PIM, e-commerce) into one Product core model.

Typical flow: list_sources, then propose_mapping for one source (it shows the user a review \
table), then validate_mapping, then export_mapping. get_coverage compares all sources.

The mapper proposes; the user decides. Proposals below 0.7 confidence are the user's call: \
they decide in the review table or tell you, and only then do you call update_mapping. Never \
accept or reject a low-confidence proposal on your own initiative.

Decisions made in the table are saved in UDC but you may not see them in the conversation. \
Before summarising or exporting, call propose_mapping or validate_mapping again to read the \
current state instead of relying on an earlier result.`;

/** A few distinct sample values per source field, for the review table. */
function sampleValues(source: SourceDetail): Record<string, string[]> {
  const out: Record<string, string[]> = {};
  for (const row of source.sample_rows) {
    for (const [field, value] of Object.entries(row)) {
      if (value === null || value === "") continue;
      const list = (out[field] ??= []);
      const text = String(value);
      if (list.length < 3 && !list.includes(text)) list.push(text);
    }
  }
  return out;
}

async function currentMapping(
  udc: UdcClient,
  sourceId: string,
  refresh: boolean,
): Promise<SourceMapping> {
  if (refresh) return udc.inferMapping(sourceId);
  try {
    return await udc.getMapping(sourceId);
  } catch (error) {
    // The source exists (checked by the caller) but was never mapped: infer now.
    if (error instanceof UdcError && error.kind === "not_found") {
      return udc.inferMapping(sourceId);
    }
    throw error;
  }
}

export type AppDeps = { config?: AppConfig; logger?: CallLogger };

export function createApp(deps: AppDeps = {}) {
  return new Skybridge({
    name: "universal-data-connector",
    title: "Universal Data Connector",
    version: "0.1.0",
    instructions: INSTRUCTIONS,
    setup: () => {
      const config = deps.config ?? loadConfig();
      return {
        udc: new UdcClient(config),
        logger: deps.logger ?? createCallLogger(config.toolLogPath),
      };
    },
    handler: (server, { udc, logger }) =>
      server
        .mcpMiddleware("tools/call", logger.middleware)

        // ── sources & core model ──────────────────────────────────────────────
        .registerTool(
          {
            name: "list_sources",
            title: "List sources",
            description:
              "List the source systems registered in UDC (for example an ERP export, a PIM, an " +
              "e-commerce catalogue) with their mapping review status and how many required " +
              "Product fields each one covers. Start here to find a source_id.",
            outputSchema: listSourcesOutput,
            annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false },
          },
          async () => {
            try {
              const sources = await udc.listSources();
              const lines = sources.map(
                (s) =>
                  `${s.source_id} (${s.review_status.replace("_", " ")}, ` +
                  `${s.required_mapped}/${s.required_total} required fields)`,
              );
              return {
                structuredContent: {
                  sources: sources.map((s) => ({
                    source_id: s.source_id,
                    name: s.name,
                    system: s.system,
                    field_count: s.field_count,
                    sample_row_count: s.sample_row_count,
                    review_status: s.review_status,
                    required_mapped: s.required_mapped,
                    required_total: s.required_total,
                  })),
                },
                content: [
                  {
                    type: "text",
                    text: sources.length
                      ? `${sources.length} source(s): ${lines.join("; ")}.`
                      : "No source is registered yet. Use register_source to add one.",
                  },
                ],
              };
            } catch (error) {
              return toolError(error);
            }
          },
        )
        .registerTool(
          {
            name: "register_source",
            title: "Register a source",
            description:
              "Register a new source schema so it can be mapped to the Product core model. Give " +
              "its field names (and types if known) and, ideally, 3–20 sample rows of real " +
              "values: mapping quality depends on seeing them. Then call propose_mapping. Fails " +
              "if the source_id is already taken.",
            inputSchema: registerSourceInput,
            outputSchema: registerSourceOutput,
            annotations: {
              readOnlyHint: false,
              destructiveHint: false,
              idempotentHint: false,
              openWorldHint: false,
            },
          },
          async (input) => {
            try {
              const created = await udc.registerSource({ ...input, target_schema: CORE_MODEL });
              return {
                structuredContent: {
                  source_id: created.source_id,
                  field_count: created.field_count,
                  sample_row_count: created.sample_row_count,
                },
                content: [
                  {
                    type: "text",
                    text:
                      `Registered ${created.source_id} with ${created.field_count} field(s) and ` +
                      `${created.sample_row_count} sample row(s). Next: propose_mapping.`,
                  },
                ],
              };
            } catch (error) {
              return toolError(error);
            }
          },
        )
        .registerTool(
          {
            name: "get_core_model",
            title: "Get the core model",
            description:
              "Get the destination Product core model: every field with its type, whether it is " +
              "required, and what it means. Use it to explain the target or to pick a " +
              "target_field for update_mapping.",
            outputSchema: coreModelOutput,
            annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false },
          },
          async () => {
            try {
              const schema = await udc.getSchema(CORE_MODEL);
              const required = schema.fields.filter((f) => f.required).map((f) => f.path);
              return {
                structuredContent: { entity: schema.name, fields: schema.fields },
                content: [
                  {
                    type: "text",
                    text:
                      `${schema.name} has ${schema.fields.length} fields; required: ` +
                      `${required.join(", ")}.`,
                  },
                ],
              };
            } catch (error) {
              return toolError(error);
            }
          },
        )

        // ── mapping review (view) ─────────────────────────────────────────────
        .registerTool(
          {
            name: "propose_mapping",
            title: "Review a source mapping",
            description:
              "Show how a source maps to the Product core model, as an interactive review table " +
              "the user can act on. Each source field gets a target field, a confidence score " +
              "(0–1), a transformation and a one-line rationale; proposals below 0.7 need a " +
              "human decision. The first call for a source runs the mapper; later calls return " +
              "the current mapping with every decision made so far. refresh=true re-runs the " +
              "mapper and keeps human decisions.",
            inputSchema: proposeMappingInput,
            outputSchema: proposeMappingOutput,
            annotations: {
              readOnlyHint: false,
              destructiveHint: false,
              idempotentHint: false,
              openWorldHint: false,
            },
            _meta: {
              "openai/toolInvocation/invoking": "Loading the mapping review…",
              "openai/toolInvocation/invoked": "Mapping review ready",
            },
            view: {
              component: "mapping-review",
              description: "Source → core model mapping review table",
              prefersBorder: true,
            },
          },
          async ({ source_id, refresh }) => {
            try {
              const source = await udc.getSource(source_id);
              const mapping = await currentMapping(udc, source_id, refresh ?? false);
              const schema = await udc.getSchema(source.target_schema);
              return {
                structuredContent: {
                  source_id,
                  source_name: source.name,
                  coverage: mapping.coverage,
                  mappings: mapping.mappings.map(toReviewRow),
                  unmapped_source_fields: mapping.unmapped_source,
                },
                content: [{ type: "text", text: describeMapping(source.name, mapping) }],
                _meta: {
                  core_fields: schema.fields.map(({ path, type, required }) => ({
                    path,
                    type,
                    required,
                  })),
                  source_types: Object.fromEntries(source.fields.map((f) => [f.name, f.type])),
                  sample_values: sampleValues(source),
                  transformations: [...TRANSFORMATIONS],
                  threshold: REVIEW_THRESHOLD,
                },
              };
            } catch (error) {
              return toolError(error);
            }
          },
        )
        .registerTool(
          {
            name: "update_mapping",
            title: "Decide on a mapping",
            description:
              "Record a decision on one source field: accept the proposal, reject it (the field " +
              "is not mapped), or edit it with a new target_field and/or transformation. The " +
              "decision is saved in UDC and returned with the updated coverage. The review table " +
              "calls this when the user clicks; call it yourself only to carry out a decision the " +
              "user stated. Never decide proposals below 0.7 confidence on your own.",
            inputSchema: updateMappingInput,
            outputSchema: updateMappingOutput,
            annotations: {
              readOnlyHint: false,
              destructiveHint: false,
              idempotentHint: true,
              openWorldHint: false,
            },
          },
          async ({ source_id, source_field, status, target_field, transformation, value_map }) => {
            try {
              const result = await udc.decide(source_id, source_field, {
                status,
                target_col: target_field,
                transform: transformation,
                value_map,
              });
              const row = toReviewRow(result.mapping);
              const what =
                row.state === "rejected"
                  ? `${row.source_field} rejected (not mapped)`
                  : `${row.source_field} → ${row.target_field} ${row.status} (${row.transformation})`;
              return {
                structuredContent: { source_id, mapping: row, coverage: result.coverage },
                content: [{ type: "text", text: `${what}. Coverage: ${coverageLine(result.coverage)}.` }],
              };
            } catch (error) {
              return toolError(error);
            }
          },
        )
        .registerTool(
          {
            name: "validate_mapping",
            title: "Validate a mapping",
            description:
              "Check whether a source's mapping is ready to export: type compatibility with the " +
              "core model, required fields left unmapped, decisions still pending, and a dry run " +
              "on sample rows showing the transformed records. Each issue says how to fix it.",
            inputSchema: validateMappingInput,
            outputSchema: validateMappingOutput,
            annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false },
          },
          async ({ source_id, sample_limit }) => {
            try {
              const v = await udc.validate(source_id, sample_limit ?? 5);
              return {
                structuredContent: {
                  source_id,
                  ok: v.ok,
                  issues: v.issues,
                  dry_run: v.dry_run,
                },
                content: [{ type: "text", text: describeValidation(v) }],
              };
            } catch (error) {
              return toolError(error);
            }
          },
        )
        .registerTool(
          {
            name: "export_mapping",
            title: "Export a mapping",
            description:
              "Generate code that applies a source's mapping outside UDC: a JSON mapping spec, a " +
              "dbt staging model (DuckDB SQL) or a PySpark function. Only accepted mappings and " +
              "proposals at 0.7+ confidence are applied; gaps come back as warnings and as NULL " +
              "columns. Run validate_mapping first.",
            inputSchema: exportMappingInput,
            outputSchema: exportMappingOutput,
            annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false },
          },
          async ({ source_id, format }) => {
            try {
              const e = await udc.exportMapping(source_id, format);
              const lines = e.content.split("\n").length;
              return {
                structuredContent: {
                  source_id,
                  format: e.format,
                  filename: e.filename,
                  content: e.content,
                  warnings: e.warnings,
                },
                content: [
                  {
                    type: "text",
                    text:
                      `Generated ${e.filename} (${lines} lines)` +
                      (e.warnings.length ? ` with ${e.warnings.length} warning(s).` : "."),
                  },
                ],
              };
            } catch (error) {
              return toolError(error);
            }
          },
        )

        // ── coverage matrix (view) ────────────────────────────────────────────
        .registerTool(
          {
            name: "get_coverage",
            title: "Compare source coverage",
            description:
              "Show which Product fields each source covers, as a matrix of core fields × " +
              "sources with the status of every cell (mapped, needs review, missing). Use it to " +
              "see where each required field can come from across ERP, PIM and e-commerce.",
            outputSchema: coverageOutput,
            annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false },
            _meta: {
              "openai/toolInvocation/invoking": "Comparing sources…",
              "openai/toolInvocation/invoked": "Coverage ready",
            },
            view: {
              component: "coverage-matrix",
              description: "Core fields × sources coverage matrix",
              prefersBorder: true,
            },
          },
          async () => {
            try {
              const m = await udc.coverage(CORE_MODEL);
              const status = (field: string, sourceId: string) =>
                m.cells.find((c) => c.field === field && c.source_id === sourceId)?.status ??
                "missing";
              const required = m.fields.filter((f) => f.required).map((f) => f.path);
              const fields = m.fields.map((f) => ({
                field: f.path,
                required: f.required,
                by_source: Object.fromEntries(
                  m.sources.map((s) => [s.source_id, status(f.path, s.source_id)]),
                ),
              }));
              const unsourced = required.filter((p) =>
                m.sources.every((s) => status(p, s.source_id) !== "mapped"),
              );
              const where = required.map((p) => {
                const from = m.sources
                  .filter((s) => status(p, s.source_id) === "mapped")
                  .map((s) => s.source_id);
                return `${p} ← ${from.length ? from.join(", ") : "none"}`;
              });
              return {
                structuredContent: {
                  sources: m.sources.map((s) => ({
                    source_id: s.source_id,
                    name: s.name,
                    required_mapped: required.filter((p) => status(p, s.source_id) === "mapped")
                      .length,
                    required_total: required.length,
                  })),
                  fields,
                  unsourced_required: unsourced,
                },
                content: [
                  {
                    type: "text",
                    text: `Required fields by source: ${where.join("; ")}.`,
                  },
                ],
                _meta: { cells: m.cells },
              };
            } catch (error) {
              return toolError(error);
            }
          },
        ),
  });
}

export const app = createApp();

export type AppType = typeof app;
