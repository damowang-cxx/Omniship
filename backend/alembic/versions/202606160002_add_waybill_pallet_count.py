"""add waybill pallet count

Revision ID: 202606160002
Revises: 202606160001
Create Date: 2026-06-16 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202606160002"
down_revision: Union[str, None] = "202606160001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "waybill_tracking_records",
        sa.Column(
            "pallet_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.alter_column(
        "waybill_tracking_records",
        "pallet_count",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_column("waybill_tracking_records", "pallet_count")
