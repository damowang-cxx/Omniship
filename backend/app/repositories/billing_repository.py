from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import BillingEntry, User


class BillingRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_user_for_update(self, user_id: UUID) -> User | None:
        statement = select(User).where(User.id == user_id).with_for_update()
        return self.db.execute(statement).scalar_one_or_none()

    def list_for_user(self, user_id: UUID) -> list[BillingEntry]:
        statement = (
            select(BillingEntry)
            .where(BillingEntry.user_id == user_id)
            .order_by(BillingEntry.created_at.desc(), BillingEntry.id.desc())
        )
        return list(self.db.execute(statement).scalars().all())

    def get_entry(self, entry_id: UUID) -> BillingEntry | None:
        return self.db.get(BillingEntry, entry_id)

    def get_deduction_for_upload(self, upload_id: UUID) -> BillingEntry | None:
        statement = select(BillingEntry).where(
            BillingEntry.waybill_upload_id == upload_id,
            BillingEntry.entry_type == "deduction",
        )
        return self.db.execute(statement).scalar_one_or_none()

    def create_recharge(
        self,
        *,
        user_id: UUID,
        amount: Decimal,
        balance_after: Decimal,
        created_by_user_id: UUID,
    ) -> BillingEntry:
        entry = BillingEntry(
            user_id=user_id,
            entry_type="recharge",
            amount=amount,
            currency="EUR",
            balance_after=balance_after,
            created_by_user_id=created_by_user_id,
        )
        self.db.add(entry)
        self.db.flush()
        return entry

    def create_deduction(
        self,
        *,
        user_id: UUID,
        amount: Decimal,
        balance_after: Decimal,
        waybill_upload_id: UUID,
        waybill_number: str,
        supplier_id: UUID,
        supplier_name: str,
        supplier_version_number: int,
        arrival_airport: str,
        billable_unit_count: int,
        unit_rate: Decimal,
        created_by_user_id: UUID,
        billing_source: str = "upload",
    ) -> BillingEntry:
        entry = BillingEntry(
            user_id=user_id,
            entry_type="deduction",
            amount=amount,
            currency="EUR",
            balance_after=balance_after,
            waybill_upload_id=waybill_upload_id,
            waybill_number=waybill_number,
            supplier_id=supplier_id,
            supplier_name=supplier_name,
            supplier_version_number=supplier_version_number,
            arrival_airport=arrival_airport,
            billable_unit_count=billable_unit_count,
            unit_rate=unit_rate,
            billing_source=billing_source,
            created_by_user_id=created_by_user_id,
        )
        self.db.add(entry)
        self.db.flush()
        return entry
