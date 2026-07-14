"""Pydantic v2 request/response schemas — all agent I/O contracts."""
import uuid
from typing import Optional
from pydantic import BaseModel, EmailStr, field_validator


# ─── Auth ─────────────────────────────────────────────────────────────────────

class SignUpRequest(BaseModel):
    email: EmailStr
    password: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    user_id: str
    role: str
    active_domain: Optional[str] = None


# ─── User / Domain ────────────────────────────────────────────────────────────

class DomainUpdateRequest(BaseModel):
    domain: str
    other_descriptor: Optional[str] = None

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, v: str) -> str:
        allowed = {"finance", "healthcare", "retail", "marketing", "operations", "other"}
        if v not in allowed:
            raise ValueError(f"domain must be one of {allowed}")
        return v


# ─── Dataset / Upload ─────────────────────────────────────────────────────────

class FileRowCount(BaseModel):
    filename: str
    row_count: int

class DatasetSummary(BaseModel):
    dataset_id: str
    source_files: list[FileRowCount]
    merged_row_count: int
    clean_row_count: Optional[int] = None
    dropped_rows: Optional[int] = None
    status: str

class UploadURLRequest(BaseModel):
    filenames: list[str]

class UploadURLResponse(BaseModel):
    dataset_id: str
    upload_urls: dict[str, str]  # filename → presigned URL

class IngestRequest(BaseModel):
    dataset_id: str

class JobResponse(BaseModel):
    job_id: str
    status: str


# ─── HITL #1 — Schema & Merge ─────────────────────────────────────────────────

class ColumnProfile(BaseModel):
    name: str
    dtype: str
    null_count: int
    distinct_count: int
    avg_length: Optional[float] = None
    classification: str  # numeric | structured | textual | ambiguous


# ─── LLM Column Classification (used internally by IngestionAgent) ────────────

class ColumnClassificationItem(BaseModel):
    name: str
    classification: str  # numeric | textual
    dtype: str            # float | integer | text | categorical | datetime | boolean

class ColumnClassificationResponse(BaseModel):
    columns: list[ColumnClassificationItem]


class MergePlan(BaseModel):
    strategy: str  # single | union | join | separate
    join_key: Optional[str] = None
    confidence: float
    column_profiles: list[ColumnProfile]
    source_file_counts: list[FileRowCount] = []
    merged_row_count: int = 0

class MergePlanDecision(BaseModel):
    approved: bool
    merge_strategy_override: Optional[str] = None
    join_key_override: Optional[str] = None
    excluded_columns: list[str] = []
    type_routing_overrides: dict[str, str] = {}  # column → numeric | textual


# ─── HITL #2 — Cleaning Plan ──────────────────────────────────────────────────

class CleaningStep(BaseModel):
    step_id: int
    action: str  # deduplicate | impute | coerce_type | flag_outlier
    column: Optional[str] = None
    method: str
    rationale: str
    confidence: float
    rows_affected: int
    before_sample: Optional[dict] = None
    after_sample: Optional[dict] = None

class CleaningPlan(BaseModel):
    steps: list[CleaningStep]
    total_rows_before: int
    total_rows_after: int

class CleaningPlanDecision(BaseModel):
    approved_step_ids: list[int]
    step_modifications: dict[int, dict] = {}  # step_id → overrides


# ─── HITL #3 — Intent ────────────────────────────────────────────────────────

class IntentRequest(BaseModel):
    dataset_id: str
    question: str

class AnalysisSpec(BaseModel):
    reasoning: str
    original_question: str = ""      # the user's exact question, passed to the SQL agent
    dimensions: list[str]
    measures: list[str]
    aggregation: str = "sum"          # sum | avg | count | max | min — the mathematical operation requested
    time_range: Optional[dict] = None
    filters: Optional[list[dict]] = None
    suggested_chart_types: list[str]
    restatement: str
    confidence: float


# ─── Dashboard ────────────────────────────────────────────────────────────────

class KPICard(BaseModel):
    label: str
    value: str
    change: Optional[str] = None
    change_pct: Optional[float] = None

class ChartSpec(BaseModel):
    chart_type: str  # line | bar | table
    title: str
    data: list[dict]
    x_field: str
    y_field: str
    color_field: Optional[str] = None

class DashboardSpec(BaseModel):
    kpi_cards: list[KPICard]
    charts: list[ChartSpec]
    narrative: str
    recommended_action: str


# ─── Job / Audit ──────────────────────────────────────────────────────────────

class JobStatus(BaseModel):
    job_id: str
    status: str
    progress_pct: Optional[int] = None
    current_step: Optional[str] = None
    error: Optional[str] = None
