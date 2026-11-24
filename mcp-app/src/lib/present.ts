/**
 * Shapes the UDC API's answers for the model and the views.
 *
 * The REST API speaks in source_col / target_col / transform / reasoning; the
 * MCP surface uses source_field / target_field / transformation / rationale,
 * the vocabulary of the people reviewing mappings. Narration (`content`) is a
 * one-line status: the data itself lives in structuredContent.
 */
import { UdcError } from "./udc-client.js";
import type { Coverage, MappingRow, SourceMapping, Validation } from "./udc-client.js";

export const REVIEW_THRESHOLD = 0.7;

export const TRANSFORMATIONS = [
  "rename",
  "cast_int",
  "cast_float",
  "parse_decimal",
  "cast_bool",
  "parse_date",
  "map_values",
  "drop",
] as const;

export type ReviewRow = {
  source_field: string;
  target_field: string | null;
  confidence: number;
  transformation: string;
  rationale: string;
  status: MappingRow["status"];
  state: MappingRow["state"];
  value_map?: Record<string, unknown>;
};

export function toReviewRow(m: MappingRow): ReviewRow {
  const row: ReviewRow = {
    source_field: m.source_col,
    target_field: m.transform === "drop" ? null : m.target_col,
    confidence: Math.round(m.confidence * 100) / 100,
    transformation: m.transform,
    rationale: m.reasoning,
    status: m.status,
    state: m.state,
  };
  if (Object.keys(m.value_map).length > 0) row.value_map = m.value_map;
  return row;
}

export function coverageLine(c: Coverage): string {
  const parts = [`${c.required_mapped}/${c.required_total} required fields mapped`];
  if (c.pending_required.length) parts.push(`pending review: ${c.pending_required.join(", ")}`);
  if (c.missing_required.length) parts.push(`no source field: ${c.missing_required.join(", ")}`);
  return parts.join("; ");
}

export function describeMapping(sourceName: string, mapping: SourceMapping): string {
  const pending = mapping.mappings.filter((m) => m.state === "needs_review");
  const pendingText = pending.length
    ? `${pending.length} proposal(s) need a decision: ${pending
        .map((m) => `${m.source_col} → ${m.target_col} (${Math.round(m.confidence * 100)}%)`)
        .join(", ")}`
    : "no proposal is waiting for a decision";
  return (
    `${sourceName}: ${coverageLine(mapping.coverage)}; ${pendingText}. ` +
    "The review table is shown to the user, who can accept, reject or edit each row."
  );
}

export function describeValidation(v: Validation): string {
  const errors = v.issues.filter((i) => i.severity === "error").length;
  const warnings = v.issues.length - errors;
  const dry = `dry run: ${v.dry_run.rows_ok}/${v.dry_run.rows_tested} sample rows transformed cleanly`;
  if (v.ok) {
    return `Ready to export${warnings ? ` (${warnings} warning(s))` : ""}; ${dry}.`;
  }
  return `Not ready: ${errors} blocking issue(s), ${warnings} warning(s); ${dry}.`;
}

// ── tool results ──────────────────────────────────────────────────────────────

export type ErrorResult = {
  isError: true;
  content: [{ type: "text"; text: string }];
  _meta: { "udc/error_kind": string };
};

/** Turn any failure into an MCP error result the agent can act on. */
export function toolError(error: unknown): ErrorResult {
  if (error instanceof UdcError) {
    return {
      isError: true,
      content: [{ type: "text", text: error.message }],
      _meta: { "udc/error_kind": error.kind },
    };
  }
  console.error("[udc-mcp] unexpected error in a tool handler:", error);
  return {
    isError: true,
    content: [
      {
        type: "text",
        text: "Unexpected error in the UDC app. Try again; if it keeps failing, check the mcp-app server logs.",
      },
    ],
    _meta: { "udc/error_kind": "unexpected" },
  };
}

/** A validation error raised by the MCP app itself, before calling UDC. */
export function invalid(message: string): UdcError {
  return new UdcError("invalid", message);
}
