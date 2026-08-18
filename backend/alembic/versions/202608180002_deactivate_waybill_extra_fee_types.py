"""allow waybill extra fee options to be deactivated

Revision ID: 202608180002
Revises: 202608180001
Create Date: 2026-08-18 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202608180002"
down_revision: Union[str, None] = "202608180001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "waybill_extra_fee_types",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("waybill_extra_fee_types", "is_active")
