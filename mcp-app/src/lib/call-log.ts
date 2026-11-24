/**
 * Structured tool-call log (JSONL), groundwork for agent evaluation.
 *
 * Enabled by UDC_TOOL_LOG=<path>. One line per `tools/call`:
 *
 *   { ts, session_id, session_source, client, tool, args, is_error, error_kind,
 *     error, result_summary, latency_ms }
 *
 * Skybridge serves MCP statelessly, so there is no MCP session to key on.
 * session_id is the best stable id the host offers: ChatGPT's anonymised
 * conversation id (`openai/session`), else an `mcp-session-id` header, else
 * null. session_source records which one, so analysis knows how far to trust it.
 */
import { appendFile, mkdir } from "node:fs/promises";
import { dirname } from "node:path";
import type { McpExtra, McpMiddlewareFn } from "skybridge/server";
import { getToolError } from "skybridge/server";

export type CallLogEntry = {
  ts: string;
  session_id: string | null;
  session_source: "openai/session" | "mcp-session-id" | "none";
  client: string | null;
  tool: string;
  args: unknown;
  is_error: boolean;
  error_kind: string | null;
  error: string | null;
  result_summary: Record<string, unknown>;
  latency_ms: number;
};

const CLIENT_INFO_KEY = "io.modelcontextprotocol/clientInfo";
const MAX_STRING = 300;
const MAX_ARRAY = 10;

/** Shrink a value for logging: long strings and arrays are cut, with a marker. */
export function compact(value: unknown, depth = 0): unknown {
  if (typeof value === "string") {
    return value.length > MAX_STRING ? `${value.slice(0, MAX_STRING)}…(+${value.length - MAX_STRING})` : value;
  }
  if (Array.isArray(value)) {
    const head = value.slice(0, MAX_ARRAY).map((v) => compact(v, depth + 1));
    return value.length > MAX_ARRAY ? [...head, `…(+${value.length - MAX_ARRAY} items)`] : head;
  }
  if (value && typeof value === "object") {
    if (depth > 4) return "{…}";
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([k, v]) => [k, compact(v, depth + 1)]),
    );
  }
  return value;
}

/** Counts and scalars of a tool result, never the full payload. */
export function summarizeResult(result: unknown): Record<string, unknown> {
  const r = (result ?? {}) as {
    content?: { type?: string; text?: string }[];
    structuredContent?: Record<string, unknown>;
  };
  const summary: Record<string, unknown> = {};
  const text = r.content?.find((c) => c.type === "text")?.text;
  if (text) summary.text = compact(text);
  for (const [key, value] of Object.entries(r.structuredContent ?? {})) {
    if (Array.isArray(value)) summary[`${key}_count`] = value.length;
    else if (value === null || typeof value !== "object") summary[key] = compact(value);
  }
  return summary;
}

function headerValue(extra: McpExtra | undefined, name: string): string | null {
  const req = extra?.http?.req as { headers?: { get?: (n: string) => string | null } } | undefined;
  return req?.headers?.get?.(name) ?? null;
}

export function sessionOf(
  extra: McpExtra | undefined,
): Pick<CallLogEntry, "session_id" | "session_source"> {
  const meta = (extra?.mcpReq?._meta ?? {}) as Record<string, unknown>;
  const openaiSession = meta["openai/session"];
  if (typeof openaiSession === "string" && openaiSession) {
    return { session_id: openaiSession, session_source: "openai/session" };
  }
  const header = headerValue(extra, "mcp-session-id");
  if (header) return { session_id: header, session_source: "mcp-session-id" };
  return { session_id: null, session_source: "none" };
}

export function clientOf(
  request: { params: Record<string, unknown> },
  extra: McpExtra | undefined,
): string | null {
  const meta = (request.params._meta ?? {}) as Record<string, unknown>;
  const info = meta[CLIENT_INFO_KEY] as { name?: string; version?: string } | undefined;
  if (info?.name) return info.version ? `${info.name}/${info.version}` : info.name;
  return headerValue(extra, "user-agent");
}

export type CallLogger = {
  enabled: boolean;
  middleware: McpMiddlewareFn;
  /** Resolves once every entry queued so far is on disk (tests, shutdown). */
  flush: () => Promise<void>;
};

export function createCallLogger(path: string | undefined): CallLogger {
  let queue: Promise<void> = Promise.resolve();
  let dirReady: Promise<unknown> | undefined;

  const write = (entry: CallLogEntry) => {
    if (!path) return;
    dirReady ??= mkdir(dirname(path), { recursive: true });
    queue = queue
      .then(() => dirReady)
      .then(() => appendFile(path, `${JSON.stringify(entry)}\n`, "utf8"))
      .catch((error: unknown) => {
        console.error("[udc-mcp] could not write the tool-call log:", error);
      });
  };

  const middleware: McpMiddlewareFn = async (request, extra, next) => {
    if (!path) return next();
    const started = performance.now();
    const ts = new Date().toISOString();
    let result: unknown;
    let thrown: unknown;
    try {
      result = await next();
      return result;
    } catch (error) {
      thrown = error;
      throw error;
    } finally {
      const r = result as
        | { isError?: boolean; content?: { text?: string }[]; _meta?: Record<string, unknown> }
        | undefined;
      const handlerError = thrown ?? getToolError(extra);
      const isError = Boolean(r?.isError || handlerError);
      write({
        ts,
        ...sessionOf(extra),
        client: clientOf(request, extra),
        tool: String(request.params.name ?? "unknown"),
        args: compact(request.params.arguments ?? {}),
        is_error: isError,
        error_kind: isError ? String(r?._meta?.["udc/error_kind"] ?? "unexpected") : null,
        error: isError
          ? (r?.content?.[0]?.text ?? (handlerError instanceof Error ? handlerError.message : null))
          : null,
        result_summary: r && !isError ? summarizeResult(r) : {},
        latency_ms: Math.round(performance.now() - started),
      });
    }
  };

  return { enabled: Boolean(path), middleware, flush: () => queue };
}
