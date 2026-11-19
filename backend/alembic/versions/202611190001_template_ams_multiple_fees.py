"""Allow distinct AMS channel deductions on the same upload."""
from alembic import op
import sqlalchemy as sa

revision = "202611190001"
down_revision = "202611160003"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_index("uq_upload_fee_type", table_name="billing_entries")
    op.create_index(
        "uq_upload_fee_type", "billing_entries", ["waybill_upload_id", "fee_type"], unique=True,
        postgresql_where=sa.text("fee_type <> 'ams_weight_handling'"),
        sqlite_where=sa.text("fee_type <> 'ams_weight_handling'"),
    )
    op.create_index(
        "uq_upload_ams_detail", "billing_entries", ["waybill_upload_id", "fee_description"], unique=True,
        postgresql_where=sa.text("fee_type = 'ams_weight_handling'"),
        sqlite_where=sa.text("fee_type = 'ams_weight_handling'"),
    )


def downgrade():
    duplicate = op.get_bind().execute(sa.text(
        "SELECT 1 FROM billing_entries WHERE fee_type = 'ams_weight_handling' "
        "AND waybill_upload_id IS NOT NULL GROUP BY waybill_upload_id HAVING COUNT(*) > 1 LIMIT 1"
    )).first()
    if duplicate:
        raise RuntimeError("Cannot downgrade while uploads have multiple AMS channel deductions")
    op.drop_index("uq_upload_ams_detail", table_name="billing_entries")
    op.drop_index("uq_upload_fee_type", table_name="billing_entries")
    op.create_index("uq_upload_fee_type", "billing_entries", ["waybill_upload_id", "fee_type"], unique=True)
