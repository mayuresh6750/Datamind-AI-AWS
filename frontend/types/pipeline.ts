// Matches backend/app/models/schemas.py: ColumnProfile, MergePlan (column_routing
// is the only thing not sent by the backend — it's derived client-side from
// `classification` so the user can override per-column before submitting).
export type ColumnClassification = 'numeric' | 'textual' | 'ambiguous'
export interface ColumnProfile {
	name: string
	dtype: string
	null_count: number
	distinct_count: number
	avg_length: number | null
	classification: ColumnClassification
}
export interface MergePlan {
	strategy: 'single' | 'union' | 'join' | 'separate'
	join_key: string | null
	confidence: number
	column_profiles: ColumnProfile[]
}
// Matches backend/app/models/schemas.py: CleaningStep, CleaningPlan
export interface CleaningStep {
	step_id: number
	action: 'deduplicate' | 'impute' | 'coerce_type' | 'flag_outlier'
	column: string | null
	method: string
	rationale: string
	confidence: number
	rows_affected: number
	before_sample: Record<string, any> | null
	after_sample: Record<string, any> | null
}
export interface CleaningPlan {
	steps: CleaningStep[]
	total_rows_before: number
	total_rows_after: number
}
export interface KPICard {
	label: string
	value: string
	change?: string | null
	change_pct?: number | null
}
export interface ChartSpec {
	chart_type: 'bar' | 'line' | 'table'
	title: string
	data: Record<string, any>[]
	x_field: string
	y_field: string
	color_field?: string | null
}
export interface DashboardSpec {
	kpi_cards: KPICard[]
	charts: ChartSpec[]
	narrative: string
	recommended_action: string
}
