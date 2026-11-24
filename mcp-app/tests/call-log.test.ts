import { mkdtemp, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { McpExtra } from "skybridge/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  type CallLogEntry,
  clientOf,
  compact,
  createCallLogger,
  sessionOf,
  summarizeResult,
} from "../src/lib/call-log.js";
import { call, connect, fakeUdc } from "./helpers.js";

afterEach(() => {
  vi.unstubAllGlobals();
});

async function readLog(path: string): Promise<CallLogEntry[]> {
  const raw = await readFile(path, "utf8");
  return raw
    .trim()
    .split("\n")
    .map((line) => JSON.parse(line) as CallLogEntry);
}

describe("tool-call log", () => {
  it("writes one structured line per tool call", async () => {
    const dir = await mkdtemp(join(tmpdir(), "udc-log-"));
    const path = join(dir, "nested", "tool-calls.jsonl");
    const logger = createCallLogger(path);
    fakeUdc(["list-sources", "err-unknown-source"]);
    const client = await connect({ logger });

    await call(client, "list_sources");
    await call(client, "propose_mapping", { source_id: "sap", refresh: false });
    await client.listTools(); // not a tool call: not logged
    await logger.flush();

    const [ok, failed] = await readLog(path);
    expect(await readLog(path)).toHaveLength(2);

    expect(ok).toMatchObject({
      tool: "list_sources",
      is_error: false,
      error_kind: null,
      error: null,
      session_id: null,
      session_source: "none",
      result_summary: { sources_count: 3 },
    });
    expect(Number.isNaN(Date.parse(ok.ts))).toBe(false);
    expect(ok.latency_ms).toBeTypeOf("number");

    expect(failed).toMatchObject({
      tool: "propose_mapping",
      args: { source_id: "sap", refresh: false },
      is_error: true,
      error_kind: "not_found",
      error: "Unknown source_id 'sap'. Registered sources: erp, pim, ecom.",
      result_summary: {},
    });
  });

  it("does nothing when UDC_TOOL_LOG is not set", async () => {
    const logger = createCallLogger(undefined);
    expect(logger.enabled).toBe(false);
    fakeUdc(["list-sources"]);
    const result = await call(await connect({ logger }), "list_sources");
    expect(result.isError).toBeFalsy();
  });
});

describe("log helpers", () => {
  it("compacts long strings and arrays", () => {
    const rows = Array.from({ length: 25 }, (_, i) => ({ id: i }));
    const out = compact({ sample_rows: rows, note: "x".repeat(400) }) as {
      sample_rows: unknown[];
      note: string;
    };
    expect(out.sample_rows).toHaveLength(11);
    expect(out.sample_rows.at(-1)).toBe("…(+15 items)");
    expect(out.note).toMatch(/…\(\+100\)$/);
  });

  it("summarises results as counts and scalars", () => {
    const summary = summarizeResult({
      content: [{ type: "text", text: "Not ready." }],
      structuredContent: { ok: false, issues: [1, 2, 3], dry_run: { rows_ok: 0 } },
    });
    expect(summary).toEqual({ text: "Not ready.", ok: false, issues_count: 3 });
  });

  it("prefers ChatGPT's conversation id, then an mcp-session-id header", () => {
    const chatgpt = { mcpReq: { _meta: { "openai/session": "conv_123" } } } as unknown as McpExtra;
    expect(sessionOf(chatgpt)).toEqual({ session_id: "conv_123", session_source: "openai/session" });

    const header = {
      mcpReq: { _meta: {} },
      http: { req: new Request("http://x", { headers: { "mcp-session-id": "sess-9" } }) },
    } as unknown as McpExtra;
    expect(sessionOf(header)).toEqual({ session_id: "sess-9", session_source: "mcp-session-id" });
    expect(sessionOf(undefined)).toEqual({ session_id: null, session_source: "none" });
  });

  it("reads the client from request _meta, else the user agent", () => {
    const params = {
      _meta: { "io.modelcontextprotocol/clientInfo": { name: "claude-ai", version: "0.1" } },
    };
    expect(clientOf({ params }, undefined)).toBe("claude-ai/0.1");
    const extra = {
      http: { req: new Request("http://x", { headers: { "user-agent": "openai-mcp/1.0" } }) },
    } as unknown as McpExtra;
    expect(clientOf({ params: {} }, extra)).toBe("openai-mcp/1.0");
  });
});
