// Mirrors backend Pydantic schemas — keep in sync with backend/app/models/schemas.py

export interface AuthResponse {
  access_token: string;
  refresh_token: string;
  user_id: string;
  role: string;
}

export interface ColumnProfile {
  name: string;
  dtype: string;
  null_count: number;
  distinct_count: number;
  avg_length?: number;
  classification: "numeric" | "textual" | "ambiguous";
}

export interface MergePlan {
  strategy: "single" | "union" | "join" | "separate";
  join_key?: string;
  confidence: number;
  column_profiles: ColumnProfile[];
}

export interface CleaningStep {
  step_id: number;
  action: "deduplicate" | "impute" | "coerce_type" | "flag_outlier";
  column?: string;
  method: string;
  rationale: string;
  confidence: number;
  rows_affected: number;
  before_sample?: Record<string, unknown>;
  after_sample?: Record<string, unknown>;
}

export interface CleaningPlan {
  steps: CleaningStep[];
  total_rows_before: number;
  total_rows_after: number;
}

export interface KPICard {
  label: string;
  value: string;
  change?: string;
  change_pct?: number;
}

export interface ChartSpec {
  chart_type: "line" | "bar" | "table";
  title: string;
  data: Record<string, unknown>[];
  x_field: string;
  y_field: string;
  color_field?: string;
}

export interface DashboardSpec {
  kpi_cards: KPICard[];
  charts: ChartSpec[];
  narrative: string;
  recommended_action: string;
}

export interface AgentOverride {
  provider: string;
  model: string;
}

export interface LlmConfig {
  config_id: string;
  tenant_id: string;
  default_provider: string;
  default_model: string;
  /** Nullable — backend stores empty JSON object or null when no overrides are set. */
  per_agent_overrides: Record<string, AgentOverride> | null;
  updated_at: string;
}

export interface UsageRow {
  provider: string;
  total_tokens: number;
  total_cost_usd: number;
  pipeline_count: number;
}

export interface User {
  user_id: string;
  email: string;
  role: string;
  active_domain: string | null;
  created_at: string;
}

export interface JobStatus {
  job_id: string;
  status: "queued" | "running" | "complete" | "failed";
  progress_pct?: number;
  current_step?: string;
  error?: string;
}

export interface AuditEntry {
  entry_id: string;
  dataset_id: string | null;
  run_id: string | null;
  agent_name: string;
  action_type: string;
  rows_affected: number | null;
  rationale: string | null;
  confidence: number | null;
  created_at: string;
}

export interface HealthData {
  queued_jobs: number;
  failed_24h: number;
}
