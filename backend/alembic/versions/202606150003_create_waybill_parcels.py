"""create waybill parcels

Revision ID: 202606150003
Revises: 202606150002
Create Date: 2026-06-15 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "202606150003"
down_revision: Union[str, None] = "202606150002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "waybill_parcels",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tracking_record_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parcel_unit_number", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            sa.String(length=40),
            nullable=False,
            server_default="created",
        ),
        sa.Column("number_of_items", sa.Integer(), nullable=False),
        sa.Column("weight_kg", sa.Numeric(12, 3), nullable=False),
        sa.Column("destination_raw", sa.String(length=255), nullable=True),
        sa.Column("destination_code", sa.String(length=2), nullable=True),
        sa.Column("destination_name", sa.String(length=120), nullable=True),
        sa.Column("inbound", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("outbound", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "special_instruction",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
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
        sa.ForeignKeyConstraint(
            ["tracking_record_id"],
            ["waybill_tracking_records.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_waybill_parcels_parcel_unit_number"),
        "waybill_parcels",
        ["parcel_unit_number"],
        unique=False,
    )
    op.create_index(
        op.f("ix_waybill_parcels_tracking_record_id"),
        "waybill_parcels",
        ["tracking_record_id"],
        unique=False,
    )
    for column in (
        "status",
        "inbound",
        "outbound",
        "special_instruction",
        "created_at",
        "updated_at",
    ):
        op.alter_column("waybill_parcels", column, server_default=None)


def downgrade() -> None:
    op.drop_index(
        op.f("ix_waybill_parcels_tracking_record_id"),
        table_name="waybill_parcels",
    )
    op.drop_index(
        op.f("ix_waybill_parcels_parcel_unit_number"),
        table_name="waybill_parcels",
    )
    op.drop_table("waybill_parcels")
