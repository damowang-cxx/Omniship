"""add configurable waybill extra fees

Revision ID: 202608180001
Revises: 202608170001
Create Date: 2026-08-18 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202608180001"
down_revision: Union[str, None] = "202608170001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "waybill_extra_fee_types",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_waybill_extra_fee_types_name"), "waybill_extra_fee_types", ["name"], unique=True)
    op.create_table(
        "waybill_extra_fees",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tracking_record_id", sa.Uuid(), nullable=False),
        sa.Column("fee_type_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["fee_type_id"], ["waybill_extra_fee_types.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tracking_record_id"], ["waybill_tracking_records.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tracking_record_id", "fee_type_id", name="uq_waybill_extra_fee_type"),
    )
    op.create_index(op.f("ix_waybill_extra_fees_tracking_record_id"), "waybill_extra_fees", ["tracking_record_id"], unique=False)
    op.create_index(op.f("ix_waybill_extra_fees_fee_type_id"), "waybill_extra_fees", ["fee_type_id"], unique=False)
    op.add_column(
        "invoice_lines",
        sa.Column("extra_fee_total", sa.Numeric(12, 2), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("invoice_lines", "extra_fee_total")
    op.drop_index(op.f("ix_waybill_extra_fees_fee_type_id"), table_name="waybill_extra_fees")
    op.drop_index(op.f("ix_waybill_extra_fees_tracking_record_id"), table_name="waybill_extra_fees")
    op.drop_table("waybill_extra_fees")
    op.drop_index(op.f("ix_waybill_extra_fee_types_name"), table_name="waybill_extra_fee_types")
    op.drop_table("waybill_extra_fee_types")
