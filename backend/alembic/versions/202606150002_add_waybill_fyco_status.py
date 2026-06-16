"""add waybill fyco status

Revision ID: 202606150002
Revises: 202606150001
Create Date: 2026-06-15 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202606150002"
down_revision: Union[str, None] = "202606150001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "waybill_tracking_records",
        sa.Column(
            "fyco_status",
            sa.String(length=20),
            nullable=False,
            server_default="released",
        ),
    )
    op.alter_column(
        "waybill_tracking_records",
        "fyco_status",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_column("waybill_tracking_records", "fyco_status")
