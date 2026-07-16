"""create supplier rules and automatic billing metadata

Revision ID: 202607160002
Revises: 202607160001
Create Date: 2026-07-16 00:00:00.000000
"""
import json
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa

from app.services.supplier_defaults import QLS_CONFIG


revision: str = "202607160002"
down_revision: Union[str, None] = "202607160001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

QLS_SUPPLIER_ID = uuid.UUID("00000000-0000-0000-0000-000000000501")
QLS_VERSION_ID = uuid.UUID("00000000-0000-0000-0000-000000000502")


def upgrade() -> None:
    suppliers = op.create_table(
        "suppliers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("current_version_number", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_suppliers_name"), "suppliers", ["name"], unique=True)

    supplier_versions = op.create_table(
        "supplier_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("supplier_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("supplier_id", "version_number", name="uq_supplier_version"),
    )
    op.create_index(
        op.f("ix_supplier_versions_supplier_id"),
        "supplier_versions",
        ["supplier_id"],
        unique=False,
    )

    billing_settings = op.create_table(
        "billing_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("unit_tax_eur", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("taxable_airports", sa.JSON(), nullable=False),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    qls_config_json = (
        json.dumps(QLS_CONFIG, separators=(",", ":"))
        .replace("'", "''")
        .replace(":", r"\:")
    )
    op.execute(
        sa.text(
            "INSERT INTO suppliers "
            "(id, name, status, current_version_number, created_by_user_id, created_at, updated_at) "
            f"VALUES ('{QLS_SUPPLIER_ID}', 'QLS', 'active', 1, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO supplier_versions "
            "(id, supplier_id, version_number, config, created_by_user_id, created_at) "
            f"VALUES ('{QLS_VERSION_ID}', '{QLS_SUPPLIER_ID}', 1, "
            f"'{qls_config_json}'::json, NULL, CURRENT_TIMESTAMP)"
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO billing_settings "
            "(id, unit_tax_eur, taxable_airports, updated_by_user_id, updated_at) "
            "VALUES (1, 3.00, '[\"AMS\"]'::json, NULL, CURRENT_TIMESTAMP)"
        )
    )

    op.add_column("waybill_uploads", sa.Column("supplier_id", sa.Uuid(), nullable=True))
    op.add_column(
        "waybill_uploads", sa.Column("supplier_version_id", sa.Uuid(), nullable=True)
    )
    op.add_column(
        "waybill_uploads",
        sa.Column("validation_issue_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "waybill_uploads",
        sa.Column(
            "validation_issues",
            sa.JSON(),
            server_default=sa.text("'[]'::json"),
            nullable=False,
        ),
    )
    op.execute(
        sa.text(
            "UPDATE waybill_uploads SET supplier_id = :supplier_id, "
            "supplier_version_id = :version_id"
        ).bindparams(
            supplier_id=QLS_SUPPLIER_ID,
            version_id=QLS_VERSION_ID,
        )
    )
    op.alter_column("waybill_uploads", "supplier_id", nullable=False)
    op.alter_column("waybill_uploads", "supplier_version_id", nullable=False)
    op.create_foreign_key(
        "fk_waybill_uploads_supplier_id",
        "waybill_uploads",
        "suppliers",
        ["supplier_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_waybill_uploads_supplier_version_id",
        "waybill_uploads",
        "supplier_versions",
        ["supplier_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        op.f("ix_waybill_uploads_supplier_id"),
        "waybill_uploads",
        ["supplier_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_waybill_uploads_supplier_version_id"),
        "waybill_uploads",
        ["supplier_version_id"],
        unique=False,
    )

    op.alter_column(
        "waybill_parcels", "number_of_items", existing_type=sa.Integer(), nullable=True
    )
    op.alter_column(
        "waybill_parcels",
        "weight_kg",
        existing_type=sa.Numeric(precision=12, scale=3),
        nullable=True,
    )

    op.add_column("billing_entries", sa.Column("supplier_id", sa.Uuid(), nullable=True))
    op.add_column(
        "billing_entries", sa.Column("supplier_name", sa.String(length=120), nullable=True)
    )
    op.add_column(
        "billing_entries", sa.Column("supplier_version_number", sa.Integer(), nullable=True)
    )
    op.add_column(
        "billing_entries", sa.Column("arrival_airport", sa.String(length=3), nullable=True)
    )
    op.add_column(
        "billing_entries", sa.Column("billable_unit_count", sa.Integer(), nullable=True)
    )
    op.add_column(
        "billing_entries",
        sa.Column("unit_rate", sa.Numeric(precision=12, scale=2), nullable=True),
    )
    op.create_foreign_key(
        "fk_billing_entries_supplier_id",
        "billing_entries",
        "suppliers",
        ["supplier_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_billing_entries_supplier_id", "billing_entries", type_="foreignkey")
    op.drop_column("billing_entries", "unit_rate")
    op.drop_column("billing_entries", "billable_unit_count")
    op.drop_column("billing_entries", "arrival_airport")
    op.drop_column("billing_entries", "supplier_version_number")
    op.drop_column("billing_entries", "supplier_name")
    op.drop_column("billing_entries", "supplier_id")

    op.alter_column(
        "waybill_parcels",
        "weight_kg",
        existing_type=sa.Numeric(precision=12, scale=3),
        nullable=False,
    )
    op.alter_column(
        "waybill_parcels", "number_of_items", existing_type=sa.Integer(), nullable=False
    )

    op.drop_index(op.f("ix_waybill_uploads_supplier_version_id"), table_name="waybill_uploads")
    op.drop_index(op.f("ix_waybill_uploads_supplier_id"), table_name="waybill_uploads")
    op.drop_constraint(
        "fk_waybill_uploads_supplier_version_id", "waybill_uploads", type_="foreignkey"
    )
    op.drop_constraint("fk_waybill_uploads_supplier_id", "waybill_uploads", type_="foreignkey")
    op.drop_column("waybill_uploads", "validation_issues")
    op.drop_column("waybill_uploads", "validation_issue_count")
    op.drop_column("waybill_uploads", "supplier_version_id")
    op.drop_column("waybill_uploads", "supplier_id")

    op.drop_table("billing_settings")
    op.drop_index(op.f("ix_supplier_versions_supplier_id"), table_name="supplier_versions")
    op.drop_table("supplier_versions")
    op.drop_index(op.f("ix_suppliers_name"), table_name="suppliers")
    op.drop_table("suppliers")
