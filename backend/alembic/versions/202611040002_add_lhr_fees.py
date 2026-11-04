"""Add dual currency wallet and per-currency invoice snapshots for LHR."""
from alembic import op
import sqlalchemy as sa

revision = "202611040002"
down_revision = "202611040001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("gbp_balance", sa.Numeric(12, 2), nullable=False, server_default="0"))
    op.drop_constraint("ck_billing_fee_type", "billing_entries", type_="check")
    op.create_check_constraint("ck_billing_fee_type", "billing_entries", "entry_type NOT IN ('deduction', 'deduction_reversal') OR (fee_type IS NOT NULL AND fee_type IN ('customs_tax', 'declaration_operation_fee', 'lhr_weight_handling', 'lhr_clearance'))")
    op.add_column("billing_entries", sa.Column("quantity", sa.Numeric(12, 3), nullable=True))
    op.alter_column("invoice_lines", "quantity", existing_type=sa.Integer(), type_=sa.Numeric(12, 3), existing_nullable=False)
    op.add_column("invoices", sa.Column("currency", sa.String(3), nullable=False, server_default="EUR"))
    op.add_column("invoice_lines", sa.Column("currency", sa.String(3), nullable=False, server_default="EUR"))
    op.add_column("cancelled_waybills", sa.Column("gbp_fee_amount_deleted", sa.Numeric(12, 2), nullable=False, server_default="0"))
    op.add_column("cancelled_waybills", sa.Column("gbp_refunded_amount", sa.Numeric(12, 2), nullable=False, server_default="0"))
    op.add_column("cancelled_waybills", sa.Column("lhr_clearance_amount_deleted", sa.Numeric(12, 2), nullable=False, server_default="0"))
    op.add_column("cancelled_waybills", sa.Column("gbp_balance_after_refund", sa.Numeric(12, 2), nullable=True))


def downgrade():
    if op.get_bind().execute(sa.text("SELECT COUNT(*) FROM billing_entries WHERE fee_type IN ('lhr_weight_handling', 'lhr_clearance') OR currency='GBP'")).scalar():
        raise RuntimeError("Cannot downgrade while LHR or GBP billing history exists")
    if op.get_bind().execute(sa.text("SELECT COUNT(*) FROM cancelled_waybills WHERE gbp_fee_amount_deleted <> 0 OR gbp_refunded_amount <> 0 OR lhr_clearance_amount_deleted <> 0")).scalar():
        raise RuntimeError("Cannot downgrade while LHR cancellation history exists")
    if op.get_bind().execute(sa.text("SELECT COUNT(*) FROM users WHERE gbp_balance <> 0")).scalar():
        raise RuntimeError("Cannot downgrade while GBP balances exist")
    if op.get_bind().execute(sa.text("SELECT COUNT(*) FROM invoices WHERE currency='GBP'")).scalar():
        raise RuntimeError("Cannot downgrade while GBP invoices exist")
    op.drop_column("cancelled_waybills", "gbp_balance_after_refund")
    op.drop_column("cancelled_waybills", "lhr_clearance_amount_deleted")
    op.drop_column("cancelled_waybills", "gbp_refunded_amount")
    op.drop_column("cancelled_waybills", "gbp_fee_amount_deleted")
    op.drop_column("invoice_lines", "currency")
    op.drop_column("invoices", "currency")
    op.alter_column("invoice_lines", "quantity", existing_type=sa.Numeric(12, 3), type_=sa.Integer(), existing_nullable=False)
    op.drop_column("billing_entries", "quantity")
    op.drop_constraint("ck_billing_fee_type", "billing_entries", type_="check")
    op.create_check_constraint("ck_billing_fee_type", "billing_entries", "entry_type NOT IN ('deduction', 'deduction_reversal') OR (fee_type IS NOT NULL AND fee_type IN ('customs_tax', 'declaration_operation_fee'))")
    op.drop_column("users", "gbp_balance")
