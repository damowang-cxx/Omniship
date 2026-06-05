"""remove alline integration

Drops the Omniship/ALLINE scraping + binding tables and the ALLINE-specific
platform submission columns on waybill_uploads. This is a destructive cleanup:
all scraped Air Waybill history and waybill/user bindings are discarded.

The downgrade is a best-effort structural rebuild (tables/columns/indexes/FKs)
so the migration can be rehearsed in reverse; it does NOT restore any data.

Revision ID: 202606050001
Revises: 202605140002
Create Date: 2026-06-05 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "202606050001"
down_revision: Union[str, None] = "202605140002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop in FK-safe order. air_waybills has FKs into scrape_runs
    # (scrape_run_id CASCADE, last_scrape_run_id SET NULL) so it must be
    # dropped before scrape_runs. drop_table cascades the table's indexes.
    op.drop_table("air_waybill_destinations")
    op.drop_table("air_waybill_details")
    op.drop_table("air_waybills")
    op.drop_table("scrape_runs")
    op.drop_table("waybill_user_bindings")

    for column in (
        "platform",
        "platform_submission_status",
        "platform_submission_method",
        "platform_submission_error",
        "platform_submitted_at",
    ):
        op.drop_column("waybill_uploads", column)


def downgrade() -> None:
    # Re-add ALLINE-specific columns on waybill_uploads.
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
    op.add_column(
        "waybill_uploads",
        sa.Column(
            "platform_submission_status",
            sa.String(length=30),
            nullable=False,
            server_default="pending",
        ),
    )
    op.alter_column(
        "waybill_uploads", "platform_submission_status", server_default=None
    )
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
        "waybill_uploads", "platform_submission_method", server_default=None
    )
    op.add_column(
        "waybill_uploads",
        sa.Column("platform_submission_error", sa.Text(), nullable=True),
    )
    op.add_column(
        "waybill_uploads",
        sa.Column(
            "platform_submitted_at", sa.DateTime(timezone=True), nullable=True
        ),
    )

    # Rebuild waybill_user_bindings.
    op.create_table(
        "waybill_user_bindings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("number", sa.String(length=255), nullable=False),
        sa.Column("normalized_number", sa.String(length=255), nullable=False),
        sa.Column(
            "source", sa.String(length=50), nullable=False, server_default="upload"
        ),
        sa.Column(
            "created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
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

    # Rebuild scrape_runs (base columns + refresh-progress columns).
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
        sa.Column(
            "mode",
            sa.String(length=30),
            nullable=False,
            server_default="incremental",
        ),
        sa.Column("total_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "processed_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "inserted_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "updated_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "skipped_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "detail_failed_count", sa.Integer(), nullable=False, server_default="0"
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

    # Rebuild air_waybills (base + parcels_raw + detail/refresh columns).
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
        sa.Column("parcels_raw", sa.String(length=255), nullable=True),
        sa.Column("action_href", sa.Text(), nullable=True),
        sa.Column("summary_hash", sa.String(length=64), nullable=True),
        sa.Column("detail_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_summary_scraped_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "last_detail_scraped_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "last_scrape_run_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("detail_error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["scrape_run_id"], ["scrape_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["last_scrape_run_id"],
            ["scrape_runs.id"],
            name="fk_air_waybills_last_scrape_run_id_scrape_runs",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_air_waybills_scrape_run_id"),
        "air_waybills",
        ["scrape_run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_air_waybills_summary_hash"),
        "air_waybills",
        ["summary_hash"],
        unique=False,
    )
    op.create_index(
        op.f("ix_air_waybills_last_scrape_run_id"),
        "air_waybills",
        ["last_scrape_run_id"],
        unique=False,
    )

    # Rebuild air_waybill_details.
    op.create_table(
        "air_waybill_details",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("waybill_number", sa.String(length=255), nullable=False),
        sa.Column("waybill_status", sa.String(length=255), nullable=True),
        sa.Column("status_changed_raw", sa.String(length=255), nullable=True),
        sa.Column("uploaded_on_raw", sa.String(length=255), nullable=True),
        sa.Column("date_received_raw", sa.String(length=255), nullable=True),
        sa.Column("airline_raw", sa.String(length=255), nullable=True),
        sa.Column("incoming_flight_raw", sa.String(length=255), nullable=True),
        sa.Column("arrived_raw", sa.String(length=255), nullable=True),
        sa.Column("ground_handler_raw", sa.String(length=255), nullable=True),
        sa.Column("broker_raw", sa.String(length=255), nullable=True),
        sa.Column("units_raw", sa.String(length=255), nullable=True),
        sa.Column("units_inbound_raw", sa.String(length=255), nullable=True),
        sa.Column("units_outbound_raw", sa.String(length=255), nullable=True),
        sa.Column("pre_alert_weight_raw", sa.String(length=255), nullable=True),
        sa.Column("gross_weight_raw", sa.String(length=255), nullable=True),
        sa.Column("odd_sized_raw", sa.String(length=255), nullable=True),
        sa.Column("scraped_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("waybill_number"),
    )
    op.create_index(
        op.f("ix_air_waybill_details_waybill_number"),
        "air_waybill_details",
        ["waybill_number"],
        unique=False,
    )

    # Rebuild air_waybill_destinations.
    op.create_table(
        "air_waybill_destinations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("waybill_number", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("country", sa.String(length=255), nullable=True),
        sa.Column("units_received_raw", sa.String(length=255), nullable=True),
        sa.Column("units_outbound_raw", sa.String(length=255), nullable=True),
        sa.Column("total_weight_raw", sa.String(length=255), nullable=True),
        sa.Column("released_raw", sa.String(length=255), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("scraped_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_air_waybill_destinations_waybill_number"),
        "air_waybill_destinations",
        ["waybill_number"],
        unique=False,
    )
