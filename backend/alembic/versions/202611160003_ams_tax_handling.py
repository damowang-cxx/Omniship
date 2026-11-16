"""Add a per-waybill AMS tax handling charge."""
from alembic import op
import sqlalchemy as sa


revision = "202611160003"
down_revision = "202611160002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("cancelled_waybills", sa.Column("ams_tax_handling_amount_deleted", sa.Numeric(12, 2), nullable=False, server_default="0"))
    op.drop_constraint("ck_billing_fee_type", "billing_entries", type_="check")
    op.create_check_constraint(
        "ck_billing_fee_type", "billing_entries",
        "entry_type NOT IN ('deduction', 'deduction_reversal') OR (fee_type IS NOT NULL AND fee_type IN ('customs_tax', 'declaration_operation_fee', 'lhr_weight_handling', 'lhr_clearance', 'lhr_terminal_surcharge', 'ams_weight_handling', 'ams_tax_handling'))",
    )


def downgrade():
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT COUNT(*) FROM billing_entries WHERE fee_type='ams_tax_handling'")).scalar():
        raise RuntimeError("Cannot downgrade while AMS tax handling billing entries exist")
    if connection.execute(sa.text("SELECT COUNT(*) FROM cancelled_waybills WHERE ams_tax_handling_amount_deleted <> 0")).scalar():
        raise RuntimeError("Cannot downgrade while AMS tax handling cancellation history exists")
    op.drop_constraint("ck_billing_fee_type", "billing_entries", type_="check")
    op.create_check_constraint(
        "ck_billing_fee_type", "billing_entries",
        "entry_type NOT IN ('deduction', 'deduction_reversal') OR (fee_type IS NOT NULL AND fee_type IN ('customs_tax', 'declaration_operation_fee', 'lhr_weight_handling', 'lhr_clearance', 'lhr_terminal_surcharge', 'ams_weight_handling'))",
    )
    op.drop_column("cancelled_waybills", "ams_tax_handling_amount_deleted")
