"""Add source_file_counts to datasets table.

Revision ID: 002
Revises: 001
Create Date: 2026-06-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("datasets", sa.Column("source_file_counts", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("datasets", "source_file_counts")
