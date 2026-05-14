"""add platform to waybill uploads

Revision ID: 202605130002
Revises: 202605130001
Create Date: 2026-05-13 15:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202605130002"
down_revision: Union[str, None] = "202605130001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "waybill_uploads",
        sa.Column(
            "platform",
            sa.String(length=40),
            nullable=False,
            server_default="ALLINE",
        ),
    )
    op.alter_column("waybill_uploads", "platform", server_default=None)


def downgrade() -> None:
    op.drop_column("waybill_uploads", "platform")
