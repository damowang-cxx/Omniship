"""Allow an administrator session to enter a customer's client."""
from alembic import op
import sqlalchemy as sa


revision = "202611200001"
down_revision = "202611190003"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user_sessions") as batch:
        batch.add_column(sa.Column("impersonated_user_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_user_sessions_impersonated_user_id", "users", ["impersonated_user_id"], ["id"],
            ondelete="CASCADE",
        )


def downgrade():
    # Never turn an in-use customer session into an administrator session on rollback.
    op.execute("UPDATE user_sessions SET revoked_at = CURRENT_TIMESTAMP WHERE impersonated_user_id IS NOT NULL")
    with op.batch_alter_table("user_sessions") as batch:
        batch.drop_constraint("fk_user_sessions_impersonated_user_id", type_="foreignkey")
        batch.drop_column("impersonated_user_id")
