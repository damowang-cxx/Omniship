"""Add Supplier-configured LHR terminal surcharge ledger snapshots."""
from alembic import op
import sqlalchemy as sa

revision = "202611100001"
down_revision = "202611040002"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("ck_billing_fee_type", "billing_entries", type_="check")
    op.create_check_constraint(
        "ck_billing_fee_type", "billing_entries",
        "entry_type NOT IN ('deduction', 'deduction_reversal') OR (fee_type IS NOT NULL AND fee_type IN ('customs_tax', 'declaration_operation_fee', 'lhr_weight_handling', 'lhr_clearance', 'lhr_terminal_surcharge'))",
    )
    op.add_column("billing_entries", sa.Column("fee_description", sa.String(255), nullable=True))
    op.add_column("cancelled_waybills", sa.Column("lhr_terminal_surcharge_amount_deleted", sa.Numeric(12, 2), nullable=False, server_default="0"))


def downgrade():
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT COUNT(*) FROM billing_entries WHERE fee_type='lhr_terminal_surcharge'")).scalar():
        raise RuntimeError("Cannot downgrade while LHR surcharge ledger entries exist")
    if connection.execute(sa.text("SELECT COUNT(*) FROM cancelled_waybills WHERE lhr_terminal_surcharge_amount_deleted <> 0")).scalar():
        raise RuntimeError("Cannot downgrade while LHR surcharge cancellation history exists")
    op.drop_column("cancelled_waybills", "lhr_terminal_surcharge_amount_deleted")
    op.drop_column("billing_entries", "fee_description")
    op.drop_constraint("ck_billing_fee_type", "billing_entries", type_="check")
    op.create_check_constraint(
        "ck_billing_fee_type", "billing_entries",
        "entry_type NOT IN ('deduction', 'deduction_reversal') OR (fee_type IS NOT NULL AND fee_type IN ('customs_tax', 'declaration_operation_fee', 'lhr_weight_handling', 'lhr_clearance'))",
    )
