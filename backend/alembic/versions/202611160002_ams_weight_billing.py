"""Add global AMS customer weight pricing and ledger fee type."""
from alembic import op
import sqlalchemy as sa


revision = "202611160002"
down_revision = "202611160001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("billing_settings", sa.Column("ams_billing", sa.JSON(), nullable=True))
    op.add_column("billing_settings", sa.Column("ams_billing_version", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("cancelled_waybills", sa.Column("ams_weight_fee_amount_deleted", sa.Numeric(12, 2), nullable=False, server_default="0"))
    op.drop_constraint("ck_billing_fee_type", "billing_entries", type_="check")
    op.create_check_constraint(
        "ck_billing_fee_type", "billing_entries",
        "entry_type NOT IN ('deduction', 'deduction_reversal') OR (fee_type IS NOT NULL AND fee_type IN ('customs_tax', 'declaration_operation_fee', 'lhr_weight_handling', 'lhr_clearance', 'lhr_terminal_surcharge', 'ams_weight_handling'))",
    )


def downgrade():
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT COUNT(*) FROM billing_entries WHERE fee_type='ams_weight_handling'")).scalar():
        raise RuntimeError("Cannot downgrade while AMS weight billing entries exist")
    if connection.execute(sa.text("SELECT COUNT(*) FROM billing_settings WHERE ams_billing IS NOT NULL")).scalar():
        raise RuntimeError("Cannot downgrade while AMS pricing is configured")
    if connection.execute(sa.text("SELECT COUNT(*) FROM cancelled_waybills WHERE ams_weight_fee_amount_deleted <> 0")).scalar():
        raise RuntimeError("Cannot downgrade while AMS fee cancellation history exists")
    op.drop_constraint("ck_billing_fee_type", "billing_entries", type_="check")
    op.create_check_constraint(
        "ck_billing_fee_type", "billing_entries",
        "entry_type NOT IN ('deduction', 'deduction_reversal') OR (fee_type IS NOT NULL AND fee_type IN ('customs_tax', 'declaration_operation_fee', 'lhr_weight_handling', 'lhr_clearance', 'lhr_terminal_surcharge'))",
    )
    op.drop_column("billing_settings", "ams_billing_version")
    op.drop_column("billing_settings", "ams_billing")
    op.drop_column("cancelled_waybills", "ams_weight_fee_amount_deleted")
