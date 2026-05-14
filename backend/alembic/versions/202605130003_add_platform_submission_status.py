"""add platform submission status

Revision ID: 202605130003
Revises: 202605130002
Create Date: 2026-05-13 18:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202605130003"
down_revision: Union[str, None] = "202605130002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "waybill_uploads",
        sa.Column(
            "platform_submission_status",
            sa.String(length=30),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "waybill_uploads",
        sa.Column("platform_submission_error", sa.Text(), nullable=True),
    )
    op.add_column(
        "waybill_uploads",
        sa.Column("platform_submitted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.alter_column(
        "waybill_uploads",
        "platform_submission_status",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_column("waybill_uploads", "platform_submitted_at")
    op.drop_column("waybill_uploads", "platform_submission_error")
    op.drop_column("waybill_uploads", "platform_submission_status")
