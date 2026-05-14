"""add platform submission method

Revision ID: 202605140001
Revises: 202605130004
Create Date: 2026-05-14 13:45:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202605140001"
down_revision: Union[str, None] = "202605130004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "waybill_uploads",
        sa.Column(
            "platform_submission_method",
            sa.String(length=30),
            nullable=False,
            server_default="automated",
        ),
    )
    op.alter_column(
        "waybill_uploads",
        "platform_submission_method",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_column("waybill_uploads", "platform_submission_method")
