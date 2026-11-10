"""Move new LHR fee configuration to global billing settings."""
from alembic import op
import sqlalchemy as sa

revision = "202611100002"
down_revision = "202611100001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("billing_settings", sa.Column("lhr_billing", sa.JSON(), nullable=True))
    op.add_column("billing_settings", sa.Column("lhr_billing_version", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT COUNT(*) FROM billing_settings WHERE lhr_billing IS NOT NULL")).scalar():
        raise RuntimeError("Cannot downgrade while global LHR fee configuration exists")
    op.drop_column("billing_settings", "lhr_billing_version")
    op.drop_column("billing_settings", "lhr_billing")
