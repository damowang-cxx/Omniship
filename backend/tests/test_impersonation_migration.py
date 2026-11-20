from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


def test_impersonation_migration_preserves_sessions_and_revokes_impersonation_on_downgrade():
    path = Path(__file__).resolve().parents[1] / "alembic/versions/202611200001_add_customer_impersonation.py"
    spec = spec_from_file_location("impersonation_migration", path)
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE users (id CHAR(32) PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE user_sessions (id INTEGER PRIMARY KEY, user_id CHAR(32) REFERENCES users(id), revoked_at DATETIME)"))
        connection.execute(text("INSERT INTO users VALUES ('admin'), ('customer')"))
        connection.execute(text("INSERT INTO user_sessions VALUES (1, 'admin', NULL), (2, 'customer', NULL)"))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            assert connection.execute(text("SELECT impersonated_user_id FROM user_sessions")).all() == [(None,), (None,)]
            foreign_keys = inspect(connection).get_foreign_keys("user_sessions")
            assert any(key["constrained_columns"] == ["impersonated_user_id"] for key in foreign_keys)
            connection.execute(text("UPDATE user_sessions SET impersonated_user_id = 'customer' WHERE id = 1"))
            migration.downgrade()
        assert "impersonated_user_id" not in {column["name"] for column in inspect(connection).get_columns("user_sessions")}
        assert connection.scalar(text("SELECT revoked_at FROM user_sessions WHERE id = 1")) is not None
        assert connection.scalar(text("SELECT revoked_at FROM user_sessions WHERE id = 2")) is None
    engine.dispose()
