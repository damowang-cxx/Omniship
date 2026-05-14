"""allow retry failed uploads

Revision ID: 202605130004
Revises: 202605130003
Create Date: 2026-05-13 19:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202605130004"
down_revision: Union[str, None] = "202605130003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index(
        op.f("ix_waybill_uploads_normalized_air_waybill_number"),
        table_name="waybill_uploads",
    )
    op.create_index(
        op.f("ix_waybill_uploads_normalized_air_waybill_number"),
        "waybill_uploads",
        ["normalized_air_waybill_number"],
        unique=False,
    )
    op.create_index(
        "uq_waybill_uploads_success_normalized_number",
        "waybill_uploads",
        ["normalized_air_waybill_number"],
        unique=True,
        postgresql_where=sa.text("platform_submission_status = 'success'"),
    )
    op.execute(
        """
        DELETE FROM waybill_user_bindings AS binding
        USING waybill_uploads AS upload
        WHERE binding.source = 'pre_alert_upload'
          AND binding.normalized_number = upload.normalized_air_waybill_number
          AND upload.platform_submission_status != 'success'
          AND NOT EXISTS (
              SELECT 1
              FROM waybill_uploads AS successful_upload
              WHERE successful_upload.normalized_air_waybill_number = binding.normalized_number
                AND successful_upload.platform_submission_status = 'success'
          )
        """
    )


def downgrade() -> None:
    op.drop_index(
        "uq_waybill_uploads_success_normalized_number",
        table_name="waybill_uploads",
    )
    op.drop_index(
        op.f("ix_waybill_uploads_normalized_air_waybill_number"),
        table_name="waybill_uploads",
    )
    op.create_index(
        op.f("ix_waybill_uploads_normalized_air_waybill_number"),
        "waybill_uploads",
        ["normalized_air_waybill_number"],
        unique=True,
    )
