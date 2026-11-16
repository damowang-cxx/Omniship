"""Add downstream waybill sync state and administrator incidents."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202611160001"
down_revision: Union[str, None] = "202611100002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "downstream_bindings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tracking_record_id", sa.Uuid(), sa.ForeignKey("waybill_tracking_records.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("provider_code", sa.String(40), nullable=False),
        sa.Column("assigned_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status_locked", sa.Boolean(), nullable=False),
        sa.Column("milestone_locks", sa.JSON(), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True)),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("remote_updated_at", sa.DateTime(timezone=True)),
        sa.Column("remote_stage", sa.String(80)),
        sa.Column("remote_completion", sa.String(80)),
        sa.Column("snapshot", sa.JSON()),
        sa.Column("first_missing_at", sa.DateTime(timezone=True)),
        sa.Column("first_network_error_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
    )
    op.create_index("ix_downstream_bindings_tracking_record_id", "downstream_bindings", ["tracking_record_id"], unique=True)
    op.create_index("ix_downstream_bindings_provider_code", "downstream_bindings", ["provider_code"])
    op.create_table(
        "downstream_sync_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("binding_id", sa.Uuid(), nullable=False),
        sa.Column("provider_code", sa.String(40), nullable=False),
        sa.Column("awb", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(60), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_downstream_sync_events_binding_id", "downstream_sync_events", ["binding_id"])
    op.create_table(
        "downstream_incidents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("binding_id", sa.Uuid(), nullable=False),
        sa.Column("provider_code", sa.String(40), nullable=False),
        sa.Column("awb", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(60), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_downstream_incidents_binding_id", "downstream_incidents", ["binding_id"])
    op.create_table(
        "downstream_incident_reads",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("incident_id", sa.Uuid(), sa.ForeignKey("downstream_incidents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("admin_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("incident_id", "admin_user_id", name="uq_downstream_incident_read"),
    )
    op.create_index("ix_downstream_incident_reads_incident_id", "downstream_incident_reads", ["incident_id"])
    op.create_index("ix_downstream_incident_reads_admin_user_id", "downstream_incident_reads", ["admin_user_id"])


def downgrade() -> None:
    op.drop_table("downstream_incident_reads")
    op.drop_table("downstream_incidents")
    op.drop_table("downstream_sync_events")
    op.drop_table("downstream_bindings")
