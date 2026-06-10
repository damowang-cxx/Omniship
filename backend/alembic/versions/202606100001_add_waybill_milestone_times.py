"""add waybill milestone times

Revision ID: 202606100001
Revises: 202606060001
Create Date: 2026-06-10 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202606100001"
down_revision: Union[str, None] = "202606060001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "waybill_tracking_records",
        sa.Column("noa_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "waybill_tracking_records",
        sa.Column("collection_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "waybill_tracking_records",
        sa.Column("scanned_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "waybill_tracking_records",
        sa.Column("customs_clearance_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "waybill_tracking_records",
        sa.Column("outbound_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("waybill_tracking_records", "outbound_at")
    op.drop_column("waybill_tracking_records", "customs_clearance_at")
    op.drop_column("waybill_tracking_records", "scanned_at")
    op.drop_column("waybill_tracking_records", "collection_at")
    op.drop_column("waybill_tracking_records", "noa_at")
