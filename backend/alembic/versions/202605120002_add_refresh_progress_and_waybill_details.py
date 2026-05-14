"""add refresh progress and waybill details

Revision ID: 202605120002
Revises: 202605120001
Create Date: 2026-05-12 01:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "202605120002"
down_revision: Union[str, None] = "202605120001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("scrape_runs", sa.Column("mode", sa.String(length=30), nullable=False, server_default="incremental"))
    op.add_column("scrape_runs", sa.Column("total_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("scrape_runs", sa.Column("processed_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("scrape_runs", sa.Column("inserted_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("scrape_runs", sa.Column("updated_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("scrape_runs", sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("scrape_runs", sa.Column("detail_failed_count", sa.Integer(), nullable=False, server_default="0"))

    op.add_column("air_waybills", sa.Column("action_href", sa.Text(), nullable=True))
    op.add_column("air_waybills", sa.Column("summary_hash", sa.String(length=64), nullable=True))
    op.add_column("air_waybills", sa.Column("detail_hash", sa.String(length=64), nullable=True))
    op.add_column("air_waybills", sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")))
    op.add_column("air_waybills", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")))
    op.add_column("air_waybills", sa.Column("last_summary_scraped_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("air_waybills", sa.Column("last_detail_scraped_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("air_waybills", sa.Column("last_scrape_run_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("air_waybills", sa.Column("detail_error_message", sa.Text(), nullable=True))
    op.create_index(op.f("ix_air_waybills_summary_hash"), "air_waybills", ["summary_hash"], unique=False)
    op.create_index(op.f("ix_air_waybills_last_scrape_run_id"), "air_waybills", ["last_scrape_run_id"], unique=False)
    op.create_foreign_key(
        "fk_air_waybills_last_scrape_run_id_scrape_runs",
        "air_waybills",
        "scrape_runs",
        ["last_scrape_run_id"],
        ["id"],
        ondelete="SET NULL",
    )

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
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("waybill_number"),
    )
    op.create_index(op.f("ix_air_waybill_details_waybill_number"), "air_waybill_details", ["waybill_number"], unique=False)

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
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_air_waybill_destinations_waybill_number"), "air_waybill_destinations", ["waybill_number"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_air_waybill_destinations_waybill_number"), table_name="air_waybill_destinations")
    op.drop_table("air_waybill_destinations")
    op.drop_index(op.f("ix_air_waybill_details_waybill_number"), table_name="air_waybill_details")
    op.drop_table("air_waybill_details")
    op.drop_constraint("fk_air_waybills_last_scrape_run_id_scrape_runs", "air_waybills", type_="foreignkey")
    op.drop_index(op.f("ix_air_waybills_last_scrape_run_id"), table_name="air_waybills")
    op.drop_index(op.f("ix_air_waybills_summary_hash"), table_name="air_waybills")
    for column in [
        "detail_error_message",
        "last_scrape_run_id",
        "last_detail_scraped_at",
        "last_summary_scraped_at",
        "last_seen_at",
        "first_seen_at",
        "detail_hash",
        "summary_hash",
        "action_href",
    ]:
        op.drop_column("air_waybills", column)
    for column in [
        "detail_failed_count",
        "skipped_count",
        "updated_count",
        "inserted_count",
        "processed_count",
        "total_count",
        "mode",
    ]:
        op.drop_column("scrape_runs", column)
