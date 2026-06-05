export type ColumnRouting = 'relational' | 'vector' | 'ambiguous'
export interface ColumnSchema {
	name: string
	inferred_type: string
	routing: ColumnRouting
	null_count: number
	distinct_count: number
	sample_values: string[]
}
export interface FileSchema {
	filename: string
	format: 'csv' | 'xlsx' | 'json' | 'parquet'
	row_count: number
	columns: ColumnSchema[]
	encoding: string
}
export interface MergePlan {
	files: FileSchema[]
	merge_strategy: 'single' | 'union' | 'join' | 'separate'
	merge_key_column: string | null
	confidence: number
	rationale: string
	column_routing: Record<string, ColumnRouting>
	cartesian_risk: boolean
}
export interface CleaningAction {
	id: string
	type: 'dedup' | 'impute' | 'coerce' | 'outlier_flag' | 'drop_column'
	category: string
	title: string
	rationale: string
	confidence: number
	rows_affected: number
	before_sample: Record<string, any>[]
	after_sample: Record<string, any>[]
	impute_options?: string[]
}
export interface CleaningPlan {
	dataset_id: string
	actions: CleaningAction[]
	generated_at: string
	llm_provider: string
	llm_model: string
}
export interface VegaLiteSpec {
	mark: 'bar' | 'line' | 'table'
	encoding: {
		x: { field: string; type: string }
		y: { field: string; type: string }
	}
}
export interface DashboardSpec {
	id: string
	intent_id: string
	kpi_cards: { label: string; value: string; delta?: string; trend?: 'up' | 'down' | 'flat' }[]
	charts: { title: string; spec: VegaLiteSpec; data: any[] }[]
	narrative: string
	next_action: string
	domain: string
	quality_score: number
	generated_at: string
}
