/**
 * Zod shapes for tool inputs and outputs. The `.describe()` texts are part of
 * the prompt surface: they tell the model what each field means.
 */
import { z } from "zod";
import { TRANSFORMATIONS } from "./present.js";

export const sourceId = z
  .string()
  .min(1)
  .describe("Source identifier as returned by list_sources, e.g. 'erp'");

const scalar = z.union([z.string(), z.number(), z.boolean(), z.null()]);

export const transformation = z
  .enum(TRANSFORMATIONS)
  .describe(
    "rename (copy as is), cast_int, cast_float, parse_decimal (locale numbers like '1.250,00'), " +
      "cast_bool, parse_date, map_values (needs value_map), drop",
  );

export const coverage = z
  .object({
    required_total: z.number().int(),
    required_mapped: z.number().int().describe("Required core fields an applied mapping fills"),
    missing_required: z.array(z.string()).describe("Required core fields no source field maps to"),
    pending_required: z
      .array(z.string())
      .describe("Required core fields only a low-confidence proposal maps to, awaiting a decision"),
  })
  .describe("How much of the core model's required fields this source covers");

export const reviewRow = z.object({
  source_field: z.string(),
  target_field: z
    .string()
    .nullable()
    .describe("Core field path, e.g. price.amount; null when the source field is dropped"),
  confidence: z.number().min(0).max(1).describe("Mapper confidence; below 0.7 needs a human decision"),
  transformation: z.string(),
  rationale: z.string().describe("One-line reason for the proposal"),
  status: z
    .enum(["proposed", "accepted", "rejected", "edited"])
    .describe("proposed = untouched mapper output; accepted/rejected/edited = a human decided"),
  state: z
    .enum(["mapped", "needs_review", "rejected", "dropped"])
    .describe("mapped = applied on export; needs_review = below 0.7 and undecided"),
  value_map: z.record(z.string(), z.unknown()).optional().describe("For map_values"),
});

export const issue = z.object({
  severity: z.enum(["error", "warning"]).describe("errors block export, warnings don't"),
  code: z
    .string()
    .describe(
      "UNMAPPED_REQUIRED | PENDING_REVIEW | TYPE_MISMATCH | TRANSFORM_FAILED | DUPLICATE_TARGET | UNKNOWN_TARGET",
    ),
  field: z.string().describe("Core field path (or source field for UNKNOWN_TARGET)"),
  message: z.string().describe("What is wrong and how to fix it"),
});

// ── inputs ────────────────────────────────────────────────────────────────────

export const registerSourceInput = {
  source_id: z
    .string()
    .regex(/^[a-z0-9][a-z0-9_-]{0,62}$/)
    .describe("New short lowercase id, e.g. 'wms'"),
  name: z.string().min(1).describe("Human-readable name, e.g. 'Warehouse stock export'"),
  system: z.string().optional().describe("Source system, e.g. 'SAP S/4HANA' or 'Shopify'"),
  fields: z
    .array(
      z.object({
        name: z.string().min(1),
        type: z.string().optional().describe("Type as the source declares it, e.g. CHAR(18)"),
        description: z.string().optional(),
      }),
    )
    .optional()
    .describe("The source's fields. Optional when sample_rows are given"),
  sample_rows: z
    .array(z.record(z.string(), scalar))
    .max(200)
    .optional()
    .describe("3–20 rows of real values keyed by field name; mapping quality depends on them"),
};

export const proposeMappingInput = {
  source_id: sourceId,
  refresh: z
    .boolean()
    .optional()
    .describe("Re-run the LLM mapper instead of returning the current mapping. Keeps human decisions"),
};

export const updateMappingInput = {
  source_id: sourceId,
  source_field: z.string().min(1).describe("Source field name exactly as in the mapping, e.g. 'MATKL'"),
  status: z
    .enum(["accepted", "rejected", "edited"])
    .describe("accepted = keep the proposal; rejected = don't map this field; edited = change it"),
  target_field: z
    .string()
    .optional()
    .describe("New core field path for 'edited', e.g. 'category' (see get_core_model)"),
  transformation: transformation.optional(),
  value_map: z
    .record(z.string(), scalar)
    .optional()
    .describe('Source value → core value for map_values, e.g. {"NR": "Black"}'),
};

export const validateMappingInput = {
  source_id: sourceId,
  sample_limit: z
    .number()
    .int()
    .min(1)
    .max(50)
    .optional()
    .describe("Sample rows to dry-run (default 5)"),
};

export const exportMappingInput = {
  source_id: sourceId,
  format: z
    .enum(["json", "dbt_sql", "pyspark"])
    .describe("json = mapping spec; dbt_sql = dbt staging model (DuckDB SQL); pyspark = DataFrame function"),
};

// ── outputs ───────────────────────────────────────────────────────────────────

export const listSourcesOutput = {
  sources: z.array(
    z.object({
      source_id: z.string(),
      name: z.string(),
      system: z.string(),
      field_count: z.number().int(),
      sample_row_count: z.number().int(),
      review_status: z
        .enum(["not_mapped", "needs_review", "reviewed"])
        .describe("reviewed = no pending decision and every required field covered"),
      required_mapped: z.number().int(),
      required_total: z.number().int(),
    }),
  ),
};

export const registerSourceOutput = {
  source_id: z.string(),
  field_count: z.number().int(),
  sample_row_count: z.number().int(),
};

export const coreModelOutput = {
  entity: z.string(),
  fields: z.array(
    z.object({
      path: z.string().describe("Dotted for nested fields, e.g. price.amount"),
      type: z.string(),
      required: z.boolean(),
      description: z.string(),
    }),
  ),
};

export const proposeMappingOutput = {
  source_id: z.string(),
  source_name: z.string(),
  coverage,
  mappings: z.array(reviewRow),
  unmapped_source_fields: z.array(z.string()).describe("Source fields no mapping uses"),
};

export const updateMappingOutput = {
  source_id: z.string(),
  mapping: reviewRow,
  coverage,
};

export const validateMappingOutput = {
  source_id: z.string(),
  ok: z.boolean().describe("true when nothing blocks export"),
  issues: z.array(issue),
  dry_run: z.object({
    rows_tested: z.number().int(),
    rows_ok: z.number().int(),
    preview: z.array(z.record(z.string(), z.unknown())).describe("First transformed records"),
  }),
};

export const exportMappingOutput = {
  source_id: z.string(),
  format: z.string(),
  filename: z.string(),
  content: z.string().describe("The generated file"),
  warnings: z.array(z.string()).describe("Gaps the export leaves (pending or unmapped fields)"),
};

export const coverageOutput = {
  sources: z.array(
    z.object({
      source_id: z.string(),
      name: z.string(),
      required_mapped: z.number().int(),
      required_total: z.number().int(),
    }),
  ),
  fields: z.array(
    z.object({
      field: z.string(),
      required: z.boolean(),
      by_source: z
        .record(z.string(), z.enum(["mapped", "needs_review", "missing"]))
        .describe("Status of this core field in each source"),
    }),
  ),
  unsourced_required: z
    .array(z.string())
    .describe("Required core fields no source maps yet (pending proposals don't count)"),
};
