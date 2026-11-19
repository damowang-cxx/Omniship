"""Charge one global AMS tax handling amount per upload for every customer."""
from alembic import op
import sqlalchemy as sa


revision = "202611190003"
down_revision = "202611190002"
branch_labels = None
depends_on = None


def upgrade():
    # Historical supplier versions and ledger snapshots remain unchanged.
    op.add_column(
        "billing_settings",
        sa.Column("ams_tax_handling_fee_eur", sa.Numeric(12, 2), nullable=False, server_default="8.00"),
    )


def downgrade():
    op.drop_column("billing_settings", "ams_tax_handling_fee_eur")
