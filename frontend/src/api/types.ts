export type ConnectorType = "postgres" | "csv" | "json_api";

export interface ConnectorConfig {
  id: string;
  name: string;
  type: ConnectorType;
  config: Record<string, string>;
}

export interface RegisterConnectorRequest {
  name: string;
  type: ConnectorType;
  config: Record<string, string>;
}

export type JobStatus = "pending" | "running" | "done" | "failed";

export interface Job {
  id: string;
  connector_id: string;
  target_schema: string;
  status: JobStatus;
  progress_pct: number;
  error: string | null;
  mapping_id: string | null;
  rows_processed: number;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface TriggerJobRequest {
  connector_id: string;
  target_schema: string;
}

export interface FieldMapping {
  source_field: string;
  target_field: string;
  transform: string;
  confidence: number;
  reasoning: string;
  overridden: boolean;
}

export interface MappingResult {
  id: string;
  connector_id: string;
  source_schema: string;
  target_schema: string;
  fields: FieldMapping[];
  version: number;
  created_at: string;
}

export interface FieldOverrideRequest {
  target_field: string;
  transform: string;
}

export interface DataResponse {
  job_id: string;
  total_rows: number;
  offset: number;
  limit: number;
  rows: Record<string, unknown>[];
}

export interface SchemaDiffResponse {
  source_id: string;
  has_changes: boolean;
  added: string[];
  removed: string[];
  changed: { field: string; before: string; after: string }[];
}

export interface InferMappingRequest {
  rows: Record<string, unknown>[];
  target_schema: string;
}
