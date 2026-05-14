"""create scrape tables

Revision ID: 202605110001
Revises:
Create Date: 2026-05-11 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "202605110001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scrape_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_system", sa.String(length=64), nullable=False),
        sa.Column("page_name", sa.String(length=128), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_scrape_runs_page_name"), "scrape_runs", ["page_name"], unique=False
    )
    op.create_index(
        op.f("ix_scrape_runs_source_system"),
        "scrape_runs",
        ["source_system"],
        unique=False,
    )

    op.create_table(
        "air_waybills",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scrape_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("number", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=255), nullable=True),
        sa.Column("status_changed_at_raw", sa.String(length=255), nullable=True),
        sa.Column("weight_kg_raw", sa.String(length=255), nullable=True),
        sa.Column("received_raw", sa.String(length=255), nullable=True),
        sa.Column("in_warehouse_raw", sa.String(length=255), nullable=True),
        sa.Column("released_raw", sa.String(length=255), nullable=True),
        sa.Column("outbound_raw", sa.String(length=255), nullable=True),
        sa.Column("actions_raw", sa.Text(), nullable=True),
        sa.Column("scraped_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["scrape_run_id"], ["scrape_runs.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_air_waybills_scrape_run_id"),
        "air_waybills",
        ["scrape_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_air_waybills_scrape_run_id"), table_name="air_waybills")
    op.drop_table("air_waybills")
    op.drop_index(op.f("ix_scrape_runs_source_system"), table_name="scrape_runs")
    op.drop_index(op.f("ix_scrape_runs_page_name"), table_name="scrape_runs")
    op.drop_table("scrape_runs")
