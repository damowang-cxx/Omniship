"""add waybill airport fields

Revision ID: 202606160001
Revises: 202606150003
Create Date: 2026-06-16 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202606160001"
down_revision: Union[str, None] = "202606150003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "waybill_uploads",
        sa.Column("airport_of_departure", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "waybill_uploads",
        sa.Column("airport_of_arrival", sa.String(length=120), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("waybill_uploads", "airport_of_arrival")
    op.drop_column("waybill_uploads", "airport_of_departure")
