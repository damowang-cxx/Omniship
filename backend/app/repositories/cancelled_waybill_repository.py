from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CancelledWaybill, User, WaybillUpload


class CancelledWaybillRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_all(self) -> list[CancelledWaybill]:
        statement = select(CancelledWaybill).order_by(
            CancelledWaybill.cancelled_at.desc(),
            CancelledWaybill.id.desc(),
        )
        return list(self.db.execute(statement).scalars().all())

    def create(
        self,
        *,
        upload: WaybillUpload,
        owner: User,
        actor: User,
        reason: str,
        tax_amount_deleted: Decimal,
        refunded_amount: Decimal,
        balance_after_refund: Decimal,
    ) -> CancelledWaybill:
        record = CancelledWaybill(
            original_upload_id=upload.id,
            user_id=owner.id,
            user_email=owner.email,
            username=owner.username,
            uploaded_by_email=upload.uploaded_by.email if upload.uploaded_by else None,
            supplier_id=upload.supplier_id,
            supplier_name=upload.supplier_name,
            supplier_version_number=upload.supplier_version_number,
            shipment_type=upload.shipment_type,
            air_waybill_number=upload.air_waybill_number,
            gross_weight_kg=upload.gross_weight_kg,
            pieces=upload.pieces,
            arrival_flight_number=upload.arrival_flight_number,
            airport_of_departure=upload.airport_of_departure,
            airport_of_arrival=upload.airport_of_arrival,
            original_status=upload.status,
            uploaded_at=upload.created_at,
            file_count=len(upload.files),
            tax_amount_deleted=tax_amount_deleted,
            refunded_amount=refunded_amount,
            balance_after_refund=balance_after_refund,
            currency="EUR",
            reason=reason,
            cancelled_by_user_id=actor.id,
            cancelled_by_email=actor.email,
        )
        self.db.add(record)
        self.db.flush()
        return record
