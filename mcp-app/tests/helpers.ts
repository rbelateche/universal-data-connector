/**
 * Test harness: a real MCP client talking to the app over an in-memory
 * transport, with the UDC REST API replaced by responses captured from the
 * running backend (tests/fixtures/udc-responses.json).
 */
import { Client, InMemoryTransport } from "@modelcontextprotocol/client";
import { vi } from "vitest";
import type { CallLogger } from "../src/lib/call-log.js";
import { createApp } from "../src/server.js";
import fixtures from "./fixtures/udc-responses.json" with { type: "json" };

export type Fixture = { method: string; path: string; status: number; body: unknown };
export const captured = fixtures as Record<string, Fixture>;

export const UDC_URL = "http://udc.test";

export type FakeRoute = { status: number; body: unknown } | (() => Promise<Response>);

/** Serve captured fixtures by "METHOD /path?query"; extra routes override them. */
export function fakeUdc(names: string[], extra: Record<string, FakeRoute> = {}) {
  const routes: Record<string, FakeRoute> = {};
  for (const name of names) {
    const f = captured[name];
    if (!f) throw new Error(`unknown fixture ${name}`);
    routes[`${f.method} ${f.path}`] = { status: f.status, body: f.body };
  }
  Object.assign(routes, extra);

  const calls: { key: string; body: unknown; headers: Headers }[] = [];
  const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const url = new URL(String(input));
    const key = `${init?.method ?? "GET"} ${url.pathname}${url.search}`;
    calls.push({
      key,
      body: init?.body ? JSON.parse(String(init.body)) : undefined,
      headers: new Headers(init?.headers),
    });
    const route = routes[key];
    if (!route) {
      return new Response(JSON.stringify({ detail: `no fake route for ${key}` }), { status: 599 });
    }
    if (typeof route === "function") return route();
    return new Response(JSON.stringify(route.body), {
      status: route.status,
      headers: { "content-type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { fetchMock, calls };
}

export async function connect(options: { logger?: CallLogger; apiKey?: string } = {}) {
  const app = createApp({
    config: {
      udcApiUrl: UDC_URL,
      udcApiKey: options.apiKey,
      timeoutMs: 2_000,
      inferTimeoutMs: 2_000,
    },
    logger: options.logger,
  });
  const client = new Client({ name: "vitest", version: "1.0.0" });
  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
  await app.connect(serverTransport);
  await client.connect(clientTransport);
  return client;
}

export type ToolResult = {
  isError?: boolean;
  content: { type: string; text?: string }[];
  structuredContent?: Record<string, unknown>;
  _meta?: Record<string, unknown>;
};

export async function call(
  client: Client,
  name: string,
  args: Record<string, unknown> = {},
): Promise<ToolResult> {
  return (await client.callTool({ name, arguments: args })) as ToolResult;
}

export function text(result: ToolResult): string {
  return result.content.map((c) => c.text ?? "").join("\n");
}
