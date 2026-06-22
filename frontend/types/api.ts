export interface UploadURLRequest {
  filenames: string[]
}

export interface UploadURLResponse {
  dataset_id: string
  upload_urls: Record<string, string>
}

export interface IngestResponse {
  job_id: string
  status: string
}

// Matches backend/app/models/schemas.py: MergePlanDecision
export interface MergePlanDecision {
	approved: boolean
	merge_strategy_override?: string | null
	join_key_override?: string | null
	excluded_columns?: string[]
	type_routing_overrides?: Record<string, string>
}
// Matches backend/app/models/schemas.py: CleaningPlanDecision
export interface CleaningPlanDecision {
	approved_step_ids: number[]
	step_modifications: Record<number, Record<string, any>>
}
// Matches backend/app/models/schemas.py: IntentRequest
export interface IntentRequest {
	dataset_id: string
	question: string
}
export interface IntentResponse {
	intent_id: string
	restatement: string
	analysis_spec: {
		dimensions: string[]
		measures: string[]
		time_range?: string
	}
	suggested_chart_types: string[]
	confidence: number
}
export interface JobStatus {
	job_id: string
	status: string
	progress: number
	error?: string
	result_id?: string
}
export interface LlmConfig {
	default_provider: string
	default_model: string
	per_agent_overrides: Record<string, { provider: string; model: string }>
}
