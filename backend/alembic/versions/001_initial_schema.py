"""Initial schema — tenants, users, datasets, hitl_decisions, pipeline_runs, llm_provider_config, audit_log.

Revision ID: 001
Revises:
Create Date: 2026-05-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID, ARRAY

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # tenants
    op.create_table(
        "tenants",
        sa.Column("tenant_id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("default_llm_provider", sa.String(50), nullable=False, server_default="google_gemini"),
        sa.Column("default_llm_model", sa.String(100), nullable=False, server_default="gemini-2.0-flash"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # users — user_id references Supabase Auth auth.users(id)
    op.create_table(
        "users",
        sa.Column("user_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="user"),
        sa.Column("active_domain", sa.String(20), nullable=False, server_default="other"),
        sa.Column("other_domain_descriptor", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint("role IN ('user', 'admin')", name="ck_users_role"),
        sa.CheckConstraint(
            "active_domain IN ('finance','healthcare','retail','marketing','operations','other')",
            name="ck_users_domain",
        ),
    )

    # datasets
    op.create_table(
        "datasets",
        sa.Column("dataset_id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("original_filenames", ARRAY(sa.Text), nullable=False),
        sa.Column("detected_format", sa.String(20), nullable=False),
        sa.Column("file_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column("merge_strategy", sa.String(20)),
        sa.Column("merge_key_column", sa.String(255)),
        sa.Column("domain_at_creation", sa.String(20)),
        sa.Column("archive_uris", ARRAY(sa.Text)),
        sa.Column("json_uri", sa.Text),
        sa.Column("row_count_raw", sa.BigInteger),
        sa.Column("row_count_clean", sa.BigInteger),
        sa.Column("status", sa.String(30), nullable=False, server_default="uploaded"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint(
            "detected_format IN ('csv','xlsx','json','parquet')",
            name="ck_datasets_format",
        ),
        sa.CheckConstraint(
            "merge_strategy IN ('single','union','join','separate')",
            name="ck_datasets_merge",
        ),
        sa.CheckConstraint(
            "status IN ('uploaded','profiling','awaiting_hitl_merge','cleaning_plan',"
            "'awaiting_hitl_cleaning','executing','ready','error')",
            name="ck_datasets_status",
        ),
    )

    # hitl_decisions
    op.create_table(
        "hitl_decisions",
        sa.Column("decision_id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("dataset_id", UUID(as_uuid=True), sa.ForeignKey("datasets.dataset_id"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("checkpoint", sa.String(30), nullable=False),
        sa.Column("proposal_json", JSONB, nullable=False),
        sa.Column("decision_json", JSONB, nullable=False),
        sa.Column("latency_seconds", sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint(
            "checkpoint IN ('schema_merge','cleaning_plan','intent','dashboard_accept')",
            name="ck_hitl_checkpoint",
        ),
    )

    # pipeline_runs
    op.create_table(
        "pipeline_runs",
        sa.Column("run_id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("dataset_id", UUID(as_uuid=True), sa.ForeignKey("datasets.dataset_id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("error_summary", sa.Text),
        sa.Column("audit_log_uri", sa.Text),
        sa.Column("llm_provider", sa.String(50), nullable=False, server_default="google_gemini"),
        sa.Column("total_llm_tokens", sa.BigInteger),
        sa.Column("total_llm_cost_usd", sa.Numeric(10, 6)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint(
            "status IN ('queued','running','paused_for_hitl','complete','failed')",
            name="ck_pipeline_status",
        ),
    )

    # llm_provider_config
    op.create_table(
        "llm_provider_config",
        sa.Column("config_id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("default_provider", sa.String(50), nullable=False, server_default="google_gemini"),
        sa.Column("default_model", sa.String(100), nullable=False, server_default="gemini-2.0-flash"),
        sa.Column("per_agent_overrides", JSONB, server_default="{}"),
        sa.Column("secrets_vault_path", sa.Text, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.user_id")),
    )

    # audit_log
    op.create_table(
        "audit_log",
        sa.Column("entry_id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("dataset_id", UUID(as_uuid=True), sa.ForeignKey("datasets.dataset_id")),
        sa.Column("run_id", UUID(as_uuid=True), sa.ForeignKey("pipeline_runs.run_id")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.user_id")),
        sa.Column("agent_name", sa.String(50), nullable=False),
        sa.Column("action_type", sa.String(50), nullable=False),
        sa.Column("rows_affected", sa.Integer),
        sa.Column("rationale", sa.Text),
        sa.Column("confidence", sa.Numeric(3, 2)),
        sa.Column("llm_provider", sa.String(50)),
        sa.Column("llm_model", sa.String(100)),
        sa.Column("tokens_used", sa.Integer),
        sa.Column("before_snapshot", JSONB),
        sa.Column("after_snapshot", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # dataset_embeddings (pgvector)
    op.execute("""
        CREATE TABLE IF NOT EXISTS dataset_embeddings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            dataset_id UUID NOT NULL REFERENCES datasets(dataset_id) ON DELETE CASCADE,
            content TEXT NOT NULL,
            metadata JSONB,
            embedding vector(1024)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_dataset_embeddings_hnsw
        ON dataset_embeddings USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)

    # Useful indexes
    op.create_index("idx_datasets_user_id", "datasets", ["user_id"])
    op.create_index("idx_datasets_status", "datasets", ["status"])
    op.create_index("idx_hitl_decisions_dataset_id", "hitl_decisions", ["dataset_id"])
    op.create_index("idx_pipeline_runs_dataset_id", "pipeline_runs", ["dataset_id"])
    op.create_index("idx_audit_log_run_id", "audit_log", ["run_id"])
    op.create_index("idx_audit_log_dataset_id", "audit_log", ["dataset_id"])


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS dataset_embeddings")
    op.drop_table("audit_log")
    op.drop_table("llm_provider_config")
    op.drop_table("pipeline_runs")
    op.drop_table("hitl_decisions")
    op.drop_table("datasets")
    op.drop_table("users")
    op.drop_table("tenants")
