/**
 * Runtime configuration, read once from the environment (or mcp-app/.env).
 *
 *   UDC_API_URL      UDC backend base URL            (default http://localhost:8000)
 *   UDC_API_KEY      sent as X-Api-Key when set      (the backend's auth branch needs it)
 *   UDC_TIMEOUT_MS   per-request timeout             (default 20000)
 *   UDC_INFER_TIMEOUT_MS  timeout for live inference (default 90000)
 *   UDC_TOOL_LOG     path of a JSONL file; when set, every tool call is logged there
 */
export type AppConfig = {
  udcApiUrl: string;
  udcApiKey?: string;
  timeoutMs: number;
  inferTimeoutMs: number;
  toolLogPath?: string;
};

function loadDotEnv(): void {
  try {
    process.loadEnvFile();
  } catch {
    // no .env file: rely on the process environment
  }
}

function positiveInt(value: string | undefined, fallback: number): number {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : fallback;
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): AppConfig {
  if (env === process.env) {
    loadDotEnv();
  }
  return {
    udcApiUrl: (env.UDC_API_URL || "http://localhost:8000").replace(/\/+$/, ""),
    udcApiKey: env.UDC_API_KEY || undefined,
    timeoutMs: positiveInt(env.UDC_TIMEOUT_MS, 20_000),
    inferTimeoutMs: positiveInt(env.UDC_INFER_TIMEOUT_MS, 90_000),
    toolLogPath: env.UDC_TOOL_LOG || undefined,
  };
}
