"""allow manual success upload history

Revision ID: 202605140002
Revises: 202605140001
Create Date: 2026-05-14 15:10:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202605140002"
down_revision: Union[str, None] = "202605140001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index(
        "uq_waybill_uploads_success_normalized_number",
        table_name="waybill_uploads",
    )


def downgrade() -> None:
    op.create_index(
        "uq_waybill_uploads_success_normalized_number",
        "waybill_uploads",
        ["normalized_air_waybill_number"],
        unique=True,
        postgresql_where=sa.text("platform_submission_status = 'success'"),
    )
