"""create invoice records and settings

Revision ID: 202608170001
Revises: 202607280001
Create Date: 2026-08-17 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202608170001"
down_revision: Union[str, None] = "202607280001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("payer_company_name", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("payer_address_info", sa.Text(), nullable=True))
    op.create_table(
        "invoice_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("issuer_company_name", sa.String(length=255), nullable=True),
        sa.Column("issuer_address_info", sa.Text(), nullable=True),
        sa.Column("beneficiary_name", sa.String(length=255), nullable=True),
        sa.Column("bank_account", sa.String(length=255), nullable=True),
        sa.Column("bank_name_and_code", sa.String(length=500), nullable=True),
        sa.Column("branch_code", sa.String(length=120), nullable=True),
        sa.Column("swift_bic", sa.String(length=120), nullable=True),
        sa.Column("bank_address", sa.Text(), nullable=True),
        sa.Column("stamp_original_filename", sa.String(length=255), nullable=True),
        sa.Column("stamp_storage_path", sa.Text(), nullable=True),
        sa.Column("stamp_content_type", sa.String(length=255), nullable=True),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "invoice_counters",
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("last_sequence", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("year"),
    )
    op.create_table(
        "invoices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_number", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("issued_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("payer_snapshot", sa.JSON(), nullable=False),
        sa.Column("issuer_snapshot", sa.JSON(), nullable=False),
        sa.Column("stamp_storage_path", sa.Text(), nullable=True),
        sa.Column("stamp_position", sa.JSON(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("voided_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("void_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["voided_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invoice_number"),
    )
    op.create_index(op.f("ix_invoices_user_id"), "invoices", ["user_id"], unique=False)
    op.create_index(op.f("ix_invoices_invoice_number"), "invoices", ["invoice_number"], unique=True)
    op.create_index(op.f("ix_invoices_status"), "invoices", ["status"], unique=False)
    op.create_table(
        "invoice_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("invoice_id", sa.Uuid(), nullable=False),
        sa.Column("billing_entry_id", sa.Uuid(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("waybill_number", sa.String(length=255), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_rate", sa.Numeric(12, 2), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.ForeignKeyConstraint(["billing_entry_id"], ["billing_entries.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invoice_id", "line_number", name="uq_invoice_line_number"),
    )
    op.create_index(op.f("ix_invoice_lines_invoice_id"), "invoice_lines", ["invoice_id"], unique=False)
    op.create_index(op.f("ix_invoice_lines_billing_entry_id"), "invoice_lines", ["billing_entry_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_invoice_lines_billing_entry_id"), table_name="invoice_lines")
    op.drop_index(op.f("ix_invoice_lines_invoice_id"), table_name="invoice_lines")
    op.drop_table("invoice_lines")
    op.drop_index(op.f("ix_invoices_status"), table_name="invoices")
    op.drop_index(op.f("ix_invoices_invoice_number"), table_name="invoices")
    op.drop_index(op.f("ix_invoices_user_id"), table_name="invoices")
    op.drop_table("invoices")
    op.drop_table("invoice_counters")
    op.drop_table("invoice_settings")
    op.drop_column("users", "payer_address_info")
    op.drop_column("users", "payer_company_name")
