"""add retroactive customs billing metadata

Revision ID: 202607160003
Revises: 202607160002
Create Date: 2026-07-16 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202607160003"
down_revision: Union[str, None] = "202607160002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "billing_settings",
        sa.Column(
            "tax_effective_date",
            sa.Date(),
            server_default=sa.text("'2026-07-01'"),
            nullable=False,
        ),
    )
    op.add_column(
        "billing_entries",
        sa.Column("billing_source", sa.String(length=20), nullable=True),
    )
    op.execute(
        "UPDATE billing_entries SET billing_source = 'upload' "
        "WHERE entry_type = 'deduction' AND billing_source IS NULL"
    )


def downgrade() -> None:
    op.drop_column("billing_entries", "billing_source")
    op.drop_column("billing_settings", "tax_effective_date")
