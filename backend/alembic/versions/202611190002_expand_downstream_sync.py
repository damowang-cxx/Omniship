"""Track downstream field locks, sync results, and imported POD identities."""
from alembic import op
import sqlalchemy as sa

revision = "202611190002"
down_revision = "202611190001"
branch_labels = None
depends_on = None


def upgrade():
    for column in ("airline_record_created_at", "airline_arrived_at", "aj_warehouse_arrived_at"):
        op.add_column("waybill_tracking_records", sa.Column(column, sa.DateTime(timezone=True), nullable=True))
    op.add_column("downstream_bindings", sa.Column("data_locks", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("downstream_bindings", sa.Column("sync_report", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("waybill_pod_files", sa.Column("provider_code", sa.String(40), nullable=True))
    op.add_column("waybill_pod_files", sa.Column("provider_document_id", sa.String(120), nullable=True))
    op.add_column("waybill_pod_files", sa.Column("provider_document_version", sa.Integer(), nullable=True))
    op.add_column("waybill_pod_files", sa.Column("provider_vendor_code", sa.String(120), nullable=True))
    op.add_column("waybill_pod_files", sa.Column("provider_uploaded_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("waybill_pod_files", sa.Column("provider_note", sa.Text(), nullable=True))
    op.create_index("uq_waybill_pod_provider_document", "waybill_pod_files", ["tracking_record_id", "provider_code", "provider_document_id"], unique=True)
    # Existing nonzero counters and parcel edits predate automatic synchronization.
    # Preserve them as manual values until an administrator explicitly unlocks them.
    conditions = {
        "received_count": "r.received_count > 0", "received_total": "r.received_total <> u.pieces",
        "in_warehouse_count": "r.in_warehouse_count > 0", "released_count": "r.released_count > 0",
        "outbound_count": "r.outbound_count > 0",
        "parcels": "EXISTS (SELECT 1 FROM waybill_parcels p WHERE p.tracking_record_id = r.id AND (p.status <> 'created' OR p.inbound OR p.outbound))",
    }
    for field, condition in conditions.items():
        if op.get_context().dialect.name == "postgresql":
            updated = f"CAST(CAST(data_locks AS jsonb) || '[\"{field}\"]'::jsonb AS json)"
        else:
            updated = f"json_insert(data_locks, '$[#]', '{field}')"
        op.execute(sa.text(
            f"UPDATE downstream_bindings SET data_locks = {updated} WHERE tracking_record_id IN "
            f"(SELECT r.id FROM waybill_tracking_records r JOIN waybill_uploads u ON u.id = r.upload_id WHERE {condition})"
        ))


def downgrade():
    if op.get_bind().execute(sa.text("SELECT 1 FROM waybill_pod_files WHERE provider_code IS NOT NULL LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade while imported downstream POD files exist")
    op.drop_index("uq_waybill_pod_provider_document", table_name="waybill_pod_files")
    for column in ("provider_note", "provider_uploaded_at", "provider_vendor_code", "provider_document_version", "provider_document_id", "provider_code"):
        op.drop_column("waybill_pod_files", column)
    op.drop_column("downstream_bindings", "sync_report")
    op.drop_column("downstream_bindings", "data_locks")
    for column in ("aj_warehouse_arrived_at", "airline_arrived_at", "airline_record_created_at"):
        op.drop_column("waybill_tracking_records", column)
