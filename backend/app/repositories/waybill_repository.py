from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.models import WaybillTrackingRecord, WaybillUpload
from app.repositories.waybill_upload_repository import normalize_waybill_number


class WaybillRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_public_code(self, public_code: str) -> WaybillTrackingRecord | None:
        statement = (
            select(WaybillTrackingRecord)
            .options(
                joinedload(WaybillTrackingRecord.upload),
                joinedload(WaybillTrackingRecord.user),
            )
            .where(WaybillTrackingRecord.public_code == public_code.upper())
            .limit(1)
        )
        return self.db.execute(statement).unique().scalar_one_or_none()

    def get_by_upload_id(self, upload_id: UUID) -> WaybillTrackingRecord | None:
        statement = (
            select(WaybillTrackingRecord)
            .options(
                joinedload(WaybillTrackingRecord.upload),
                joinedload(WaybillTrackingRecord.user),
            )
            .where(WaybillTrackingRecord.upload_id == upload_id)
            .limit(1)
        )
        return self.db.execute(statement).unique().scalar_one_or_none()

    def public_code_exists(self, public_code: str) -> bool:
        statement = (
            select(WaybillTrackingRecord.id)
            .where(WaybillTrackingRecord.public_code == public_code.upper())
            .limit(1)
        )
        return self.db.execute(statement).scalar_one_or_none() is not None

    def list(
        self,
        *,
        user_id: UUID | None = None,
        status: str | None = None,
        query: str | None = None,
    ) -> list[WaybillTrackingRecord]:
        statement = (
            select(WaybillTrackingRecord)
            .join(WaybillTrackingRecord.upload)
            .options(
                joinedload(WaybillTrackingRecord.upload),
                joinedload(WaybillTrackingRecord.user),
            )
            .where(WaybillUpload.status == "approved")
        )
        if user_id is not None:
            statement = statement.where(WaybillTrackingRecord.user_id == user_id)
        if status:
            statement = statement.where(WaybillTrackingRecord.status == status)
        if query:
            normalized_query = normalize_waybill_number(query)
            pattern = f"%{query.strip()}%"
            normalized_pattern = f"%{normalized_query}%"
            statement = statement.where(
                WaybillUpload.air_waybill_number.ilike(pattern)
                | WaybillUpload.normalized_air_waybill_number.ilike(normalized_pattern)
            )

        statement = statement.order_by(
            WaybillTrackingRecord.status_changed_at.desc(),
            WaybillTrackingRecord.created_at.desc(),
            WaybillTrackingRecord.id.desc(),
        )
        return list(self.db.execute(statement).unique().scalars().all())

    def create_for_upload(
        self,
        *,
        upload: WaybillUpload,
        public_code: str,
    ) -> WaybillTrackingRecord:
        record = WaybillTrackingRecord(
            upload_id=upload.id,
            user_id=upload.user_id,
            public_code=public_code.upper(),
            status="created",
            status_changed_at=upload.reviewed_at or upload.updated_at,
            received_count=0,
            received_total=upload.pieces,
            in_warehouse_count=0,
            released_count=0,
            outbound_count=0,
        )
        self.db.add(record)
        self.db.flush()
        return record

    def update(
        self,
        record: WaybillTrackingRecord,
        *,
        status: str | None = None,
        received_count: int | None = None,
        received_total: int | None = None,
        in_warehouse_count: int | None = None,
        released_count: int | None = None,
        outbound_count: int | None = None,
        milestone_updates: dict[str, object] | None = None,
    ) -> WaybillTrackingRecord:
        if status is not None:
            record.status = status
        if received_count is not None:
            record.received_count = received_count
        if received_total is not None:
            record.received_total = received_total
        if in_warehouse_count is not None:
            record.in_warehouse_count = in_warehouse_count
        if released_count is not None:
            record.released_count = released_count
        if outbound_count is not None:
            record.outbound_count = outbound_count
        for field_name, value in (milestone_updates or {}).items():
            setattr(record, field_name, value)
        self.db.flush()
        return record
