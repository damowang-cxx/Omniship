"""add customs tax reversal entries

Revision ID: 202607270001
Revises: 202607160003
Create Date: 2026-07-27 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202607270001"
down_revision: Union[str, None] = "202607160003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "billing_entries",
        sa.Column("reversal_of_entry_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_billing_entries_reversal_of_entry_id",
        "billing_entries",
        "billing_entries",
        ["reversal_of_entry_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_billing_entries_reversal_of_entry_id"),
        "billing_entries",
        ["reversal_of_entry_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_billing_entries_reversal_of_entry_id"),
        table_name="billing_entries",
    )
    op.drop_constraint(
        "fk_billing_entries_reversal_of_entry_id",
        "billing_entries",
        type_="foreignkey",
    )
    op.drop_column("billing_entries", "reversal_of_entry_id")
