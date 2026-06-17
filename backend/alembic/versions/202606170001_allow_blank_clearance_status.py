"""allow blank clearance status

Revision ID: 202606170001
Revises: 202606160002
Create Date: 2026-06-17 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202606170001"
down_revision: Union[str, None] = "202606160002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "waybill_tracking_records",
        "fyco_status",
        existing_type=sa.String(length=20),
        nullable=True,
    )


def downgrade() -> None:
    op.execute(
        "UPDATE waybill_tracking_records SET fyco_status = 'released' WHERE fyco_status IS NULL"
    )
    op.alter_column(
        "waybill_tracking_records",
        "fyco_status",
        existing_type=sa.String(length=20),
        nullable=False,
    )
