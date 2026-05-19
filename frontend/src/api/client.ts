import type {
  ConnectorConfig,
  DataResponse,
  FieldOverrideRequest,
  InferMappingRequest,
  Job,
  MappingResult,
  RegisterConnectorRequest,
  SchemaDiffResponse,
  TriggerJobRequest,
} from "./types";

const BASE_URL = import.meta.env.VITE_API_URL ?? "/api";
const API_KEY = import.meta.env.VITE_API_KEY ?? "";

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-Api-Key": API_KEY,
      ...init.headers,
    },
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(
      (body as { detail?: string }).detail ?? `HTTP ${res.status}`
    );
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ─── Connectors ───────────────────────────────────────────────────────────────

export const registerConnector = (req: RegisterConnectorRequest) =>
  request<ConnectorConfig>("/connectors", {
    method: "POST",
    body: JSON.stringify(req),
  });

export const listConnectors = () => request<ConnectorConfig[]>("/connectors");

export const getConnector = (id: string) =>
  request<ConnectorConfig>(`/connectors/${id}`);

// ─── Jobs ─────────────────────────────────────────────────────────────────────

export const triggerJob = (req: TriggerJobRequest) =>
  request<Job>("/jobs", { method: "POST", body: JSON.stringify(req) });

export const listJobs = () => request<Job[]>("/jobs");

export const getJob = (id: string) => request<Job>(`/jobs/${id}`);

export const getJobMapping = (id: string) =>
  request<MappingResult>(`/jobs/${id}/mapping`);

export const overrideField = (
  jobId: string,
  fieldName: string,
  override: FieldOverrideRequest
) =>
  request<MappingResult>(
    `/jobs/${jobId}/mapping/fields/${encodeURIComponent(fieldName)}`,
    { method: "PATCH", body: JSON.stringify(override) }
  );

// ─── Data ─────────────────────────────────────────────────────────────────────

export const getData = (jobId: string, offset = 0, limit = 25) =>
  request<DataResponse>(`/data/${jobId}?offset=${offset}&limit=${limit}`);

// ─── Schema diff ──────────────────────────────────────────────────────────────

export const getSchemaDiff = (jobId: string) =>
  request<SchemaDiffResponse>(`/schema/${jobId}/diff`);

// ─── One-shot mapping ─────────────────────────────────────────────────────────

export const inferMapping = (req: InferMappingRequest) =>
  request<MappingResult>("/mappings/infer", {
    method: "POST",
    body: JSON.stringify(req),
  });
