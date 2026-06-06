"""create waybill tracking records

Revision ID: 202606060001
Revises: 202606050001
Create Date: 2026-06-06 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "202606060001"
down_revision: Union[str, None] = "202606050001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "waybill_tracking_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("upload_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_code", sa.String(length=8), nullable=False),
        sa.Column(
            "status",
            sa.String(length=40),
            nullable=False,
            server_default="created",
        ),
        sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "received_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "received_total", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "in_warehouse_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("released_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("outbound_count", sa.Integer(), nullable=False, server_default="0"),
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
        sa.ForeignKeyConstraint(["upload_id"], ["waybill_uploads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_waybill_tracking_records_public_code"),
        "waybill_tracking_records",
        ["public_code"],
        unique=True,
    )
    op.create_index(
        op.f("ix_waybill_tracking_records_upload_id"),
        "waybill_tracking_records",
        ["upload_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_waybill_tracking_records_user_id"),
        "waybill_tracking_records",
        ["user_id"],
        unique=False,
    )

    op.execute(
        """
        INSERT INTO waybill_tracking_records (
            id,
            upload_id,
            user_id,
            public_code,
            status,
            status_changed_at,
            received_count,
            received_total,
            in_warehouse_count,
            released_count,
            outbound_count,
            created_at,
            updated_at
        )
        SELECT
            approved_uploads.id,
            approved_uploads.id,
            approved_uploads.user_id,
            'WB' || lpad(approved_uploads.row_number::text, 6, '0'),
            'created',
            COALESCE(approved_uploads.reviewed_at, approved_uploads.created_at, now()),
            0,
            approved_uploads.pieces,
            0,
            0,
            0,
            now(),
            now()
        FROM (
            SELECT
                waybill_uploads.*,
                row_number() OVER (ORDER BY waybill_uploads.created_at, waybill_uploads.id) AS row_number
            FROM waybill_uploads
            WHERE waybill_uploads.status = 'approved'
        ) AS approved_uploads
        """
    )

    for column in (
        "status",
        "received_count",
        "received_total",
        "in_warehouse_count",
        "released_count",
        "outbound_count",
        "created_at",
        "updated_at",
    ):
        op.alter_column("waybill_tracking_records", column, server_default=None)


def downgrade() -> None:
    op.drop_index(
        op.f("ix_waybill_tracking_records_user_id"),
        table_name="waybill_tracking_records",
    )
    op.drop_index(
        op.f("ix_waybill_tracking_records_upload_id"),
        table_name="waybill_tracking_records",
    )
    op.drop_index(
        op.f("ix_waybill_tracking_records_public_code"),
        table_name="waybill_tracking_records",
    )
    op.drop_table("waybill_tracking_records")
