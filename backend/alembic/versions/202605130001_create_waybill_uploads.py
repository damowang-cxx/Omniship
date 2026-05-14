"""create waybill uploads

Revision ID: 202605130001
Revises: 202605120003
Create Date: 2026-05-13 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "202605130001"
down_revision: Union[str, None] = "202605120003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "waybill_uploads",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("uploaded_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("shipment_type", sa.String(length=20), nullable=False),
        sa.Column("air_waybill_number", sa.String(length=255), nullable=False),
        sa.Column("normalized_air_waybill_number", sa.String(length=255), nullable=False),
        sa.Column("gross_weight_kg", sa.Numeric(12, 3), nullable=False),
        sa.Column("pieces", sa.Integer(), nullable=False),
        sa.Column("arrival_flight_number", sa.String(length=120), nullable=True),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default="pending_review",
        ),
        sa.Column("reviewed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_waybill_uploads_user_id"),
        "waybill_uploads",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_waybill_uploads_uploaded_by_user_id"),
        "waybill_uploads",
        ["uploaded_by_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_waybill_uploads_normalized_air_waybill_number"),
        "waybill_uploads",
        ["normalized_air_waybill_number"],
        unique=True,
    )

    op.create_table(
        "waybill_upload_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("upload_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_kind", sa.String(length=40), nullable=False),
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
        sa.ForeignKeyConstraint(["upload_id"], ["waybill_uploads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_waybill_upload_files_upload_id"),
        "waybill_upload_files",
        ["upload_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_waybill_upload_files_upload_id"),
        table_name="waybill_upload_files",
    )
    op.drop_table("waybill_upload_files")
    op.drop_index(
        op.f("ix_waybill_uploads_normalized_air_waybill_number"),
        table_name="waybill_uploads",
    )
    op.drop_index(
        op.f("ix_waybill_uploads_uploaded_by_user_id"),
        table_name="waybill_uploads",
    )
    op.drop_index(op.f("ix_waybill_uploads_user_id"), table_name="waybill_uploads")
    op.drop_table("waybill_uploads")
