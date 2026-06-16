"""create waybill pod files

Revision ID: 202606150001
Revises: 202606100001
Create Date: 2026-06-15 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "202606150001"
down_revision: Union[str, None] = "202606100001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "waybill_pod_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tracking_record_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("uploaded_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["tracking_record_id"],
            ["waybill_tracking_records.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_waybill_pod_files_tracking_record_id"),
        "waybill_pod_files",
        ["tracking_record_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_waybill_pod_files_uploaded_by_user_id"),
        "waybill_pod_files",
        ["uploaded_by_user_id"],
        unique=False,
    )
    op.alter_column("waybill_pod_files", "created_at", server_default=None)


def downgrade() -> None:
    op.drop_index(
        op.f("ix_waybill_pod_files_uploaded_by_user_id"),
        table_name="waybill_pod_files",
    )
    op.drop_index(
        op.f("ix_waybill_pod_files_tracking_record_id"),
        table_name="waybill_pod_files",
    )
    op.drop_table("waybill_pod_files")
