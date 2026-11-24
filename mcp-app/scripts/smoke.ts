/**
 * End-to-end smoke test over HTTP, the way a host connects.
 *
 *   npm run dev            # in one terminal (with the UDC API running)
 *   npm run smoke          # in another; MCP_URL defaults to http://localhost:3000/mcp
 *
 * Lists the tools, then calls the read-only ones against the demo sources and
 * prints one line per call. Exits non-zero if a call that should succeed fails.
 */
import { Client, StreamableHTTPClientTransport } from "@modelcontextprotocol/client";

const url = new URL(process.env.MCP_URL ?? "http://localhost:3000/mcp");

type Result = {
  isError?: boolean;
  content: { type: string; text?: string }[];
  structuredContent?: Record<string, unknown>;
  _meta?: Record<string, unknown>;
};

const client = new Client({ name: "udc-smoke", version: "1.0.0" });
await client.connect(new StreamableHTTPClientTransport(url));

const { tools } = await client.listTools();
console.log(`tools (${tools.length}): ${tools.map((t) => t.name).join(", ")}`);

let failures = 0;
async function check(name: string, args: Record<string, unknown>, expectError = false) {
  const started = performance.now();
  const result = (await client.callTool({ name, arguments: args })) as Result;
  const ms = Math.round(performance.now() - started);
  const text = result.content.find((c) => c.type === "text")?.text ?? "";
  const ok = Boolean(result.isError) === expectError;
  if (!ok) failures++;
  console.log(`${ok ? "ok  " : "FAIL"} ${name} ${JSON.stringify(args)} (${ms} ms)\n     ${text}`);
  return result;
}

await check("list_sources", {});
await check("get_core_model", {});
const review = await check("propose_mapping", { source_id: "erp" });
console.log(`     view meta keys: ${Object.keys(review._meta ?? {}).join(", ")}`);
await check("validate_mapping", { source_id: "erp" });
await check("export_mapping", { source_id: "pim", format: "dbt_sql" });
await check("get_coverage", {});
await check("propose_mapping", { source_id: "sap" }, true);

await client.close();
if (failures) {
  console.error(`${failures} unexpected result(s)`);
  process.exit(1);
}
