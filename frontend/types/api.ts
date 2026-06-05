export interface MergePlanDecision {
	approved: boolean
	merge_strategy: string
	merge_key_column: string | null
	column_routing: Record<string, string>
}
export interface CleaningDecision {
	step_id: string
	status: 'approved' | 'modified' | 'rejected'
	override: string | null
}
export interface IntentRequest {
	intent_text: string
	language?: string
	preferred_chart_types?: string[]
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
