"""create cancelled waybill audit records

Revision ID: 202607280001
Revises: 202607270001
Create Date: 2026-07-28 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202607280001"
down_revision: Union[str, None] = "202607270001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cancelled_waybills",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("original_upload_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("user_email", sa.String(length=255), nullable=False),
        sa.Column("username", sa.String(length=120), nullable=False),
        sa.Column("uploaded_by_email", sa.String(length=255), nullable=True),
        sa.Column("supplier_id", sa.Uuid(), nullable=True),
        sa.Column("supplier_name", sa.String(length=120), nullable=True),
        sa.Column("supplier_version_number", sa.Integer(), nullable=True),
        sa.Column("shipment_type", sa.String(length=20), nullable=False),
        sa.Column("air_waybill_number", sa.String(length=255), nullable=False),
        sa.Column("gross_weight_kg", sa.Numeric(12, 3), nullable=False),
        sa.Column("pieces", sa.Integer(), nullable=False),
        sa.Column("arrival_flight_number", sa.String(length=120), nullable=True),
        sa.Column("airport_of_departure", sa.String(length=120), nullable=True),
        sa.Column("airport_of_arrival", sa.String(length=120), nullable=True),
        sa.Column("original_status", sa.String(length=30), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("file_count", sa.Integer(), nullable=False),
        sa.Column("tax_amount_deleted", sa.Numeric(12, 2), nullable=False),
        sa.Column("refunded_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("balance_after_refund", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("cancelled_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("cancelled_by_email", sa.String(length=255), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["cancelled_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_cancelled_waybills_original_upload_id"),
        "cancelled_waybills",
        ["original_upload_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_cancelled_waybills_user_id"),
        "cancelled_waybills",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_cancelled_waybills_supplier_id"),
        "cancelled_waybills",
        ["supplier_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_cancelled_waybills_cancelled_by_user_id"),
        "cancelled_waybills",
        ["cancelled_by_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_cancelled_waybills_cancelled_at"),
        "cancelled_waybills",
        ["cancelled_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_cancelled_waybills_cancelled_at"),
        table_name="cancelled_waybills",
    )
    op.drop_index(
        op.f("ix_cancelled_waybills_cancelled_by_user_id"),
        table_name="cancelled_waybills",
    )
    op.drop_index(
        op.f("ix_cancelled_waybills_supplier_id"),
        table_name="cancelled_waybills",
    )
    op.drop_index(
        op.f("ix_cancelled_waybills_user_id"),
        table_name="cancelled_waybills",
    )
    op.drop_index(
        op.f("ix_cancelled_waybills_original_upload_id"),
        table_name="cancelled_waybills",
    )
    op.drop_table("cancelled_waybills")
