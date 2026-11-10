"""Opt-in integration checks against the configured PostgreSQL, in an owned schema.

Run with RUN_POSTGRES_TESTS=1. No existing application tables are modified.
"""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData, Table, create_engine, select, text
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.core.config import get_settings
from app.db.models import BillingEntry, User
from app.services.waybill_service import WaybillService, WaybillBillingConflictError
from tests.auth_helpers import create_test_user
from tests.test_operation_fees import legacy_upload

pytestmark = pytest.mark.skipif(os.environ.get("RUN_POSTGRES_TESTS") != "1", reason="Opt-in isolated PostgreSQL migration/concurrency checks")


def test_migration_and_concurrent_backfill(tmp_path, monkeypatch):
    engine = create_engine(get_settings().database_url)
    if engine.dialect.name != "postgresql":
        pytest.skip("Configured database is not PostgreSQL")
    schema = "operation_fee_test_" + uuid4().hex
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped = create_engine(get_settings().database_url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
        with scoped.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "202608180002")
            metadata = MetaData()
            users = Table("users", metadata, autoload_with=connection)
            entries = Table("billing_entries", metadata, autoload_with=connection)
            invoices = Table("invoices", metadata, autoload_with=connection)
            lines = Table("invoice_lines", metadata, autoload_with=connection)
            uid, eid, rid, iid, lid = [uuid4() for _ in range(5)]
            now = datetime.now(timezone.utc)
            connection.execute(users.insert().values(id=uid, email="history@example.com", username="History", password_hash="unused",
                role="user", status="active", balance=Decimal("20.00"), created_at=now, updated_at=now))
            for entry_id, entry_type, balance, reversal in [(eid, "deduction", "14.00", None), (rid, "deduction_reversal", "20.00", eid)]:
                connection.execute(entries.insert().values(id=entry_id, user_id=uid, entry_type=entry_type, amount=Decimal("6.00"), currency="EUR",
                    balance_after=Decimal(balance), reversal_of_entry_id=reversal, created_at=now))
            connection.execute(invoices.insert().values(id=iid, user_id=uid, invoice_number="HISTORY", status="issued", issued_date=date(2026, 8, 1),
                due_date=date(2026, 8, 5), total_amount=Decimal("6.00"), payer_snapshot={}, issuer_snapshot={}, created_at=now))
            connection.execute(lines.insert().values(id=lid, invoice_id=iid, billing_entry_id=eid, line_number=1, waybill_number="LEGACY",
                quantity=2, unit_rate=Decimal("3.00"), amount=Decimal("6.00"), extra_fee_total=Decimal("0.00")))
            command.upgrade(config, "head")
            assert connection.execute(text("SELECT fee_type, amount FROM billing_entries ORDER BY entry_type")).all() == [
                ("customs_tax", Decimal("6.00")), ("customs_tax", Decimal("6.00"))]
            assert connection.scalar(text("SELECT balance FROM users WHERE email='history@example.com'")) == Decimal("20.00")
            assert connection.execute(text("SELECT fee_type, fee_name, amount FROM invoice_lines")).one() == ("customs_tax", "Customs tax", Decimal("6.00"))
            assert connection.scalar(text("SELECT gbp_balance FROM users WHERE email='history@example.com'")) == Decimal("0.00")
            assert connection.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='billing_settings' AND column_name IN ('lhr_billing', 'lhr_billing_version') ORDER BY column_name")).scalars().all() == ["lhr_billing", "lhr_billing_version"]
            assert connection.scalar(text("SELECT currency FROM invoices WHERE invoice_number='HISTORY'")) == "EUR"
            assert connection.scalar(text("SELECT currency FROM invoice_lines WHERE billing_entry_id=:id"), {"id": eid}) == "EUR"
            assert connection.scalar(text("SELECT data_type FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='invoice_lines' AND column_name='quantity'")) == "numeric"

        with Session(scoped) as db:
            admin = create_test_user(db, email="admin@example.com", role="admin")
            owner = create_test_user(db, email="owner@example.com", balance="20.00")
            _, code = legacy_upload(db, owner, tmp_path)
            admin_id, owner_id = admin.id, owner.id

        # Both requests must load the old state before either attempts the lock.
        barrier = Barrier(2)
        original = WaybillService._get_visible_record

        def load_together(self, actor, *, public_code):
            record = original(self, actor, public_code=public_code)
            if not self.db.info.get("synchronized"):
                self.db.info["synchronized"] = True
                barrier.wait(timeout=10)
            return record

        monkeypatch.setattr(WaybillService, "_get_visible_record", load_together)

        def backfill():
            with Session(scoped) as db:
                try:
                    result = WaybillService(db).backfill_operation_fee(db.get(User, admin_id), public_code=code,
                        request=Request({"type": "http", "headers": [], "client": ("127.0.0.1", 1234)}))
                    return result.operation_fee_status
                except WaybillBillingConflictError:
                    return "conflict"

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: backfill(), range(2)))
        assert sorted(results) == ["conflict", "paid"]
        with Session(scoped) as db:
            assert db.get(User, owner_id).balance == Decimal("14.00")
            charged = db.scalars(select(BillingEntry).where(BillingEntry.user_id == owner_id)).all()
            assert len(charged) == 1
            assert charged[0].fee_type == "declaration_operation_fee"
    finally:
        scoped.dispose()
        # schema consists exclusively of the constant prefix and a generated UUID.
        assert schema.startswith("operation_fee_test_") and len(schema) == 51
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()
