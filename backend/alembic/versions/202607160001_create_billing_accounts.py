"""create billing accounts

Revision ID: 202607160001
Revises: 202606170001
Create Date: 2026-07-16 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202607160001"
down_revision: Union[str, None] = "202606170001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "balance",
            sa.Numeric(precision=12, scale=2),
            server_default="0",
            nullable=False,
        ),
    )
    op.create_table(
        "billing_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("entry_type", sa.String(length=20), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("balance_after", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("waybill_upload_id", sa.Uuid(), nullable=True),
        sa.Column("waybill_number", sa.String(length=255), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("receipt_original_filename", sa.String(length=255), nullable=True),
        sa.Column("receipt_storage_path", sa.Text(), nullable=True),
        sa.Column("receipt_content_type", sa.String(length=255), nullable=True),
        sa.Column("receipt_size_bytes", sa.Integer(), nullable=True),
        sa.Column("receipt_sha256", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["waybill_upload_id"], ["waybill_uploads.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_billing_entries_created_by_user_id"),
        "billing_entries",
        ["created_by_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_billing_entries_entry_type"),
        "billing_entries",
        ["entry_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_billing_entries_user_id"),
        "billing_entries",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_billing_entries_waybill_upload_id"),
        "billing_entries",
        ["waybill_upload_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_billing_entries_waybill_upload_id"),
        table_name="billing_entries",
    )
    op.drop_index(op.f("ix_billing_entries_user_id"), table_name="billing_entries")
    op.drop_index(op.f("ix_billing_entries_entry_type"), table_name="billing_entries")
    op.drop_index(
        op.f("ix_billing_entries_created_by_user_id"),
        table_name="billing_entries",
    )
    op.drop_table("billing_entries")
    op.drop_column("users", "balance")
