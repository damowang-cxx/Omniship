from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.db.models import BillingEntry, Invoice, InvoiceCounter, InvoiceLine, InvoiceSettings


class InvoiceRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_settings(self) -> InvoiceSettings | None:
        return self.db.get(InvoiceSettings, 1)

    def get_or_create_settings(self) -> InvoiceSettings:
        settings = self.get_settings()
        if settings is None:
            settings = InvoiceSettings(id=1)
            self.db.add(settings)
            self.db.flush()
        return settings

    def list_invoices(self, user_id: UUID) -> list[Invoice]:
        statement = (
            select(Invoice)
            .where(Invoice.user_id == user_id)
            .options(joinedload(Invoice.lines))
            .order_by(Invoice.created_at.desc(), Invoice.id.desc())
        )
        return list(self.db.execute(statement).unique().scalars().all())

    def get_invoice(self, invoice_id: UUID) -> Invoice | None:
        statement = select(Invoice).where(Invoice.id == invoice_id).options(joinedload(Invoice.lines))
        return self.db.execute(statement).unique().scalar_one_or_none()

    def get_invoice_for_update(self, invoice_id: UUID) -> Invoice | None:
        # Keep the row lock on the invoice table only.  A joined eager load here
        # produces a LEFT OUTER JOIN, which PostgreSQL rejects with FOR UPDATE
        # (it cannot lock the nullable side of that join).  Loading lines in a
        # separate SELECT retains the response data without weakening the lock.
        statement = (
            select(Invoice).where(Invoice.id == invoice_id).options(selectinload(Invoice.lines)).with_for_update()
        )
        return self.db.execute(statement).unique().scalar_one_or_none()

    def get_entries_for_update(self, user_id: UUID, entry_ids: list[UUID]) -> list[BillingEntry]:
        statement = (
            select(BillingEntry)
            .where(BillingEntry.user_id == user_id, BillingEntry.id.in_(entry_ids))
            .with_for_update()
        )
        return list(self.db.execute(statement).scalars().all())

    def active_invoice_entry_ids(self, entry_ids: list[UUID]) -> set[UUID]:
        if not entry_ids:
            return set()
        statement = (
            select(InvoiceLine.billing_entry_id)
            .join(Invoice, Invoice.id == InvoiceLine.invoice_id)
            .where(Invoice.status == "issued", InvoiceLine.billing_entry_id.in_(entry_ids))
        )
        return set(self.db.execute(statement).scalars().all())

    def next_number(self, issued_date: date) -> str:
        counter = self.db.get(InvoiceCounter, issued_date.year, with_for_update=True)
        if counter is None:
            counter = InvoiceCounter(year=issued_date.year, last_sequence=0)
            self.db.add(counter)
            self.db.flush()
        counter.last_sequence += 1
        return f"INV{issued_date.year % 100:02d}{counter.last_sequence:03d}"
