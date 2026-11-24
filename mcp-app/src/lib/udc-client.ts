/**
 * Typed client for the Universal Data Connector REST API (the "customer system").
 *
 * Every failure becomes a UdcError whose message is safe to show an agent: the
 * backend's own `detail` when it sent one (those name the fix), otherwise a
 * plain description of what went wrong. Stack traces never leave this module.
 */
import type { AppConfig } from "./config.js";

// ── API shapes (mirror backend/src/udc/api/routers/*.py) ─────────────────────

export type ReviewStatus = "not_mapped" | "needs_review" | "reviewed";
export type MappingStatus = "proposed" | "accepted" | "rejected" | "edited";
export type MappingState = "mapped" | "needs_review" | "rejected" | "dropped";
export type FieldStatus = "mapped" | "needs_review" | "missing";
export type ExportFormat = "json" | "dbt_sql" | "pyspark";

export type SchemaField = {
  path: string;
  type: string;
  required: boolean;
  description: string;
};

export type SourceSummary = {
  source_id: string;
  name: string;
  system: string;
  target_schema: string;
  field_count: number;
  sample_row_count: number;
  mapping_id: number | null;
  review_status: ReviewStatus;
  required_mapped: number;
  required_total: number;
};

export type SourceDetail = SourceSummary & {
  fields: { name: string; type: string; description: string }[];
  sample_rows: Record<string, unknown>[];
};

export type MappingRow = {
  source_col: string;
  target_col: string;
  transform: string;
  confidence: number;
  reasoning: string;
  value_map: Record<string, unknown>;
  status: MappingStatus;
  state: MappingState;
};

export type Coverage = {
  required_total: number;
  required_mapped: number;
  missing_required: string[];
  pending_required: string[];
};

export type SourceMapping = {
  source_id: string;
  mapping_id: number;
  target_schema: string;
  mappings: MappingRow[];
  unmapped_source: string[];
  coverage: Coverage;
};

export type Decision = {
  status: "accepted" | "rejected" | "edited";
  target_col?: string;
  transform?: string;
  value_map?: Record<string, unknown>;
};

export type DecisionResult = {
  source_id: string;
  mapping_id: number;
  mapping: MappingRow;
  coverage: Coverage;
};

export type Issue = {
  severity: "error" | "warning";
  code: string;
  field: string;
  message: string;
};

export type Validation = {
  source_id: string;
  mapping_id: number;
  ok: boolean;
  issues: Issue[];
  dry_run: { rows_tested: number; rows_ok: number; preview: Record<string, unknown>[] };
};

export type ExportResult = {
  source_id: string;
  mapping_id: number;
  format: ExportFormat;
  filename: string;
  content: string;
  warnings: string[];
};

export type CoverageMatrix = {
  target_schema: string;
  fields: { path: string; required: boolean }[];
  sources: { source_id: string; name: string; mapping_id: number | null }[];
  cells: {
    field: string;
    source_id: string;
    status: FieldStatus;
    source_col: string | null;
    confidence: number | null;
  }[];
};

export type RegisterSource = {
  source_id: string;
  name: string;
  system?: string;
  target_schema?: string;
  fields?: { name: string; type?: string; description?: string }[];
  sample_rows?: Record<string, unknown>[];
};

// ── errors ────────────────────────────────────────────────────────────────────

export type UdcErrorKind =
  | "not_found" // 404
  | "conflict" // 409
  | "invalid" // 422
  | "unavailable" // 503: a backend feature is not configured
  | "upstream" // 502: the backend's own dependency (Claude API) failed
  | "unreachable" // network error
  | "timeout"
  | "server"; // other 5xx

export class UdcError extends Error {
  readonly kind: UdcErrorKind;
  readonly status?: number;

  constructor(kind: UdcErrorKind, message: string, status?: number) {
    super(message);
    this.name = "UdcError";
    this.kind = kind;
    this.status = status;
  }
}

function kindFor(status: number): UdcErrorKind {
  if (status === 404) return "not_found";
  if (status === 409) return "conflict";
  if (status === 400 || status === 422) return "invalid";
  if (status === 502) return "upstream";
  if (status === 503) return "unavailable";
  return "server";
}

/** FastAPI sends `detail` as a string, or as a list of pydantic errors. */
export function formatDetail(detail: unknown): string | undefined {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const parts = detail.map((d) => {
      const item = d as { loc?: unknown[]; msg?: string };
      const loc = (item.loc ?? []).filter((p) => p !== "body").join(".");
      const msg = (item.msg ?? "invalid value").replace(/^Value error, /, "");
      return loc ? `${loc}: ${msg}` : msg;
    });
    return parts.join("; ");
  }
  return undefined;
}

// ── client ────────────────────────────────────────────────────────────────────

type RequestOptions = {
  method?: "GET" | "POST" | "PATCH";
  body?: unknown;
  query?: Record<string, string | number>;
  timeoutMs?: number;
};

export class UdcClient {
  constructor(private readonly config: AppConfig) {}

  listSources(): Promise<SourceSummary[]> {
    return this.request("/sources");
  }

  getSource(sourceId: string): Promise<SourceDetail> {
    return this.request(`/sources/${enc(sourceId)}`);
  }

  registerSource(body: RegisterSource): Promise<SourceSummary> {
    return this.request("/sources", { method: "POST", body });
  }

  getSchema(name = "Product"): Promise<{ name: string; fields: SchemaField[] }> {
    return this.request(`/schemas/${enc(name)}`);
  }

  getMapping(sourceId: string): Promise<SourceMapping> {
    return this.request(`/sources/${enc(sourceId)}/mapping`);
  }

  inferMapping(sourceId: string): Promise<SourceMapping> {
    return this.request(`/sources/${enc(sourceId)}/mapping`, {
      method: "POST",
      timeoutMs: this.config.inferTimeoutMs,
    });
  }

  decide(sourceId: string, sourceCol: string, decision: Decision): Promise<DecisionResult> {
    return this.request(`/sources/${enc(sourceId)}/mapping/fields/${enc(sourceCol)}`, {
      method: "PATCH",
      body: decision,
    });
  }

  validate(sourceId: string, sampleLimit: number): Promise<Validation> {
    return this.request(`/sources/${enc(sourceId)}/mapping/validate`, {
      method: "POST",
      query: { sample_limit: sampleLimit },
    });
  }

  exportMapping(sourceId: string, format: ExportFormat): Promise<ExportResult> {
    return this.request(`/sources/${enc(sourceId)}/mapping/export`, { query: { format } });
  }

  coverage(targetSchema = "Product"): Promise<CoverageMatrix> {
    return this.request("/coverage", { query: { target_schema: targetSchema } });
  }

  private async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const url = new URL(this.config.udcApiUrl + path);
    for (const [k, v] of Object.entries(options.query ?? {})) {
      url.searchParams.set(k, String(v));
    }
    const headers: Record<string, string> = { accept: "application/json" };
    if (options.body !== undefined) headers["content-type"] = "application/json";
    if (this.config.udcApiKey) headers["x-api-key"] = this.config.udcApiKey;

    const timeoutMs = options.timeoutMs ?? this.config.timeoutMs;
    let response: Response;
    try {
      response = await fetch(url, {
        method: options.method ?? "GET",
        headers,
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
        signal: AbortSignal.timeout(timeoutMs),
      });
    } catch (error) {
      if (error instanceof DOMException && error.name === "TimeoutError") {
        throw new UdcError(
          "timeout",
          `The UDC backend did not answer within ${Math.round(timeoutMs / 1000)}s. Try again.`,
        );
      }
      throw new UdcError(
        "unreachable",
        `The UDC backend is unreachable at ${this.config.udcApiUrl}. ` +
          "It needs to be running (make demo-api) before this app can work.",
      );
    }

    const payload: unknown = await response.json().catch(() => undefined);
    if (!response.ok) {
      const detail = formatDetail((payload as { detail?: unknown } | undefined)?.detail);
      throw new UdcError(
        kindFor(response.status),
        detail ?? `The UDC backend returned HTTP ${response.status}.`,
        response.status,
      );
    }
    return payload as T;
  }
}

function enc(segment: string): string {
  return encodeURIComponent(segment);
}
