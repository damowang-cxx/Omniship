"""Separate customs and declaration operation fees without rebilling history."""
from alembic import op
import sqlalchemy as sa

revision = "202611040001"
down_revision = "202608180002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("billing_entries", sa.Column("fee_type", sa.String(40), nullable=True))
    op.execute("UPDATE billing_entries SET fee_type = 'customs_tax' WHERE entry_type IN ('deduction', 'deduction_reversal')")
    op.create_check_constraint("ck_billing_fee_type", "billing_entries", "entry_type NOT IN ('deduction', 'deduction_reversal') OR (fee_type IS NOT NULL AND fee_type IN ('customs_tax', 'declaration_operation_fee'))")
    op.drop_index("ix_billing_entries_waybill_upload_id", table_name="billing_entries")
    op.create_index("ix_billing_entries_waybill_upload_id", "billing_entries", ["waybill_upload_id"])
    op.create_index("uq_upload_fee_type", "billing_entries", ["waybill_upload_id", "fee_type"], unique=True)
    op.add_column("invoice_lines", sa.Column("fee_type", sa.String(40), nullable=False, server_default="customs_tax"))
    op.add_column("invoice_lines", sa.Column("fee_name", sa.String(120), nullable=False, server_default="Customs tax"))
    op.add_column("cancelled_waybills", sa.Column("operation_fee_amount_deleted", sa.Numeric(12, 2), nullable=False, server_default="0"))


def downgrade():
    # Never collapse multi-fee history into the former one-entry-per-upload schema.
    count = op.get_bind().execute(sa.text("SELECT COUNT(*) FROM billing_entries WHERE fee_type = 'declaration_operation_fee'")).scalar()
    if count:
        raise RuntimeError("Cannot downgrade while operation fee history exists")
    op.drop_column("cancelled_waybills", "operation_fee_amount_deleted")
    op.drop_column("invoice_lines", "fee_name")
    op.drop_column("invoice_lines", "fee_type")
    op.drop_index("uq_upload_fee_type", table_name="billing_entries")
    op.drop_index("ix_billing_entries_waybill_upload_id", table_name="billing_entries")
    op.create_index("ix_billing_entries_waybill_upload_id", "billing_entries", ["waybill_upload_id"], unique=True)
    op.drop_constraint("ck_billing_fee_type", "billing_entries", type_="check")
    op.drop_column("billing_entries", "fee_type")
