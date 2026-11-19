"""Verify moving the flat fee leaves historical template and billing data intact."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


def test_global_ams_tax_migration_defaults_existing_settings_and_preserves_history():
    path = Path(__file__).resolve().parents[1] / "alembic/versions/202611190003_global_ams_tax_handling.py"
    spec = spec_from_file_location("global_ams_tax_migration", path)
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE billing_settings (id INTEGER PRIMARY KEY, unit_tax_eur NUMERIC(12,2))"))
        connection.execute(text("INSERT INTO billing_settings VALUES (1, 3.00)"))
        connection.execute(text("CREATE TABLE supplier_versions (id INTEGER PRIMARY KEY, config TEXT)"))
        connection.execute(text("INSERT INTO supplier_versions VALUES (1, :config)"), {"config": '{"amsBilling":{"taxHandlingFeeEur":"4.25"}}'})
        connection.execute(text("CREATE TABLE billing_entries (id INTEGER PRIMARY KEY, fee_type TEXT, amount NUMERIC(12,2))"))
        connection.execute(text("INSERT INTO billing_entries VALUES (1, 'ams_tax_handling', 4.25)"))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            assert connection.execute(text("SELECT unit_tax_eur, ams_tax_handling_fee_eur FROM billing_settings")).one() == (3, 8)
            assert connection.scalar(text("SELECT amount FROM billing_entries")) == 4.25
            assert connection.scalar(text("SELECT config FROM supplier_versions")) == '{"amsBilling":{"taxHandlingFeeEur":"4.25"}}'
            migration.downgrade()
        assert "ams_tax_handling_fee_eur" not in {column["name"] for column in inspect(connection).get_columns("billing_settings")}
        assert connection.scalar(text("SELECT amount FROM billing_entries")) == 4.25
    engine.dispose()
