"""add parcels raw to air waybills

Revision ID: 202605110002
Revises: 202605110001
Create Date: 2026-05-11 00:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202605110002"
down_revision: Union[str, None] = "202605110001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "air_waybills",
        sa.Column("parcels_raw", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("air_waybills", "parcels_raw")

