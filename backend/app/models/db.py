"""SQLAlchemy ORM models — mirrors the LLD.md database schema."""
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey,
    Integer, Numeric, String, Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Tenant(Base):
    __tablename__ = "tenants"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    default_llm_provider: Mapped[str] = mapped_column(String(50), nullable=False, default="google_gemini")
    default_llm_model: Mapped[str] = mapped_column(String(100), nullable=False, default="gemini-2.0-flash")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'admin')", name="ck_users_role"),
        CheckConstraint(
            "active_domain IN ('finance','healthcare','retail','marketing','operations','other')",
            name="ck_users_domain",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="user")
    active_domain: Mapped[str] = mapped_column(String(20), nullable=False, default="other")
    other_domain_descriptor: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    datasets: Mapped[list["Dataset"]] = relationship(back_populates="user")


class Dataset(Base):
    __tablename__ = "datasets"
    __table_args__ = (
        CheckConstraint(
            "detected_format IN ('csv','xlsx','json','parquet')",
            name="ck_datasets_format",
        ),
        CheckConstraint(
            "merge_strategy IN ('single','union','join','separate')",
            name="ck_datasets_merge",
        ),
        CheckConstraint(
            "status IN ('uploaded','profiling','awaiting_hitl_merge','cleaning_plan',"
            "'awaiting_hitl_cleaning','executing','ready','error')",
            name="ck_datasets_status",
        ),
    )

    dataset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    original_filenames: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    detected_format: Mapped[str] = mapped_column(String(20), nullable=False)
    file_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    merge_strategy: Mapped[str | None] = mapped_column(String(20))
    merge_key_column: Mapped[str | None] = mapped_column(String(255))
    domain_at_creation: Mapped[str | None] = mapped_column(String(20))
    archive_uris: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    json_uri: Mapped[str | None] = mapped_column(Text)
    row_count_raw: Mapped[int | None] = mapped_column(BigInteger)
    row_count_clean: Mapped[int | None] = mapped_column(BigInteger)
    source_file_counts: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="uploaded")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship(back_populates="datasets")
    hitl_decisions: Mapped[list["HITLDecision"]] = relationship(back_populates="dataset")
    pipeline_runs: Mapped[list["PipelineRun"]] = relationship(back_populates="dataset")


class HITLDecision(Base):
    __tablename__ = "hitl_decisions"
    __table_args__ = (
        CheckConstraint(
            "checkpoint IN ('schema_merge','cleaning_plan','intent','dashboard_accept')",
            name="ck_hitl_checkpoint",
        ),
    )

    decision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("datasets.dataset_id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    checkpoint: Mapped[str] = mapped_column(String(30), nullable=False)
    proposal_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    decision_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    latency_seconds: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    dataset: Mapped["Dataset"] = relationship(back_populates="hitl_decisions")


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','paused_for_hitl','complete','failed')",
            name="ck_pipeline_status",
        ),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("datasets.dataset_id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_summary: Mapped[str | None] = mapped_column(Text)
    audit_log_uri: Mapped[str | None] = mapped_column(Text)
    llm_provider: Mapped[str] = mapped_column(String(50), nullable=False, default="google_gemini")
    total_llm_tokens: Mapped[int | None] = mapped_column(BigInteger)
    total_llm_cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 6))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    dataset: Mapped["Dataset"] = relationship(back_populates="pipeline_runs")
    audit_entries: Mapped[list["AuditLog"]] = relationship(back_populates="run")


class LLMProviderConfig(Base):
    __tablename__ = "llm_provider_config"

    config_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    default_provider: Mapped[str] = mapped_column(String(50), nullable=False, default="google_gemini")
    default_model: Mapped[str] = mapped_column(String(100), nullable=False, default="gemini-2.0-flash")
    per_agent_overrides: Mapped[dict] = mapped_column(JSONB, default={})
    secrets_vault_path: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"))


class AuditLog(Base):
    __tablename__ = "audit_log"

    entry_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("datasets.dataset_id"))
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("pipeline_runs.run_id"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    agent_name: Mapped[str] = mapped_column(String(50), nullable=False)
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    rows_affected: Mapped[int | None] = mapped_column(Integer)
    rationale: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Numeric(3, 2))
    llm_provider: Mapped[str | None] = mapped_column(String(50))
    llm_model: Mapped[str | None] = mapped_column(String(100))
    tokens_used: Mapped[int | None] = mapped_column(Integer)
    before_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    after_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    run: Mapped["PipelineRun | None"] = relationship(back_populates="audit_entries")
