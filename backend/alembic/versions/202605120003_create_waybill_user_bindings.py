"""create waybill user bindings

Revision ID: 202605120003
Revises: 202605120002
Create Date: 2026-05-12 16:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "202605120003"
down_revision: Union[str, None] = "202605120002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "waybill_user_bindings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("number", sa.String(length=255), nullable=False),
        sa.Column("normalized_number", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False, server_default="upload"),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "normalized_number",
            name="uq_waybill_user_bindings_user_normalized_number",
        ),
    )
    op.create_index(
        op.f("ix_waybill_user_bindings_user_id"),
        "waybill_user_bindings",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_waybill_user_bindings_normalized_number"),
        "waybill_user_bindings",
        ["normalized_number"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_waybill_user_bindings_normalized_number"),
        table_name="waybill_user_bindings",
    )
    op.drop_index(
        op.f("ix_waybill_user_bindings_user_id"),
        table_name="waybill_user_bindings",
    )
    op.drop_table("waybill_user_bindings")
