from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.models import (
    WaybillParcel,
    WaybillPodFile,
    WaybillTrackingRecord,
    WaybillUpload,
)
from app.repositories.waybill_upload_repository import normalize_waybill_number


class WaybillRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_public_code(self, public_code: str) -> WaybillTrackingRecord | None:
        statement = (
            select(WaybillTrackingRecord)
            .options(
                joinedload(WaybillTrackingRecord.upload),
                joinedload(WaybillTrackingRecord.upload).joinedload(
                    WaybillUpload.files
                ),
                joinedload(WaybillTrackingRecord.user),
                joinedload(WaybillTrackingRecord.pod_files),
                joinedload(WaybillTrackingRecord.parcels),
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
                joinedload(WaybillTrackingRecord.upload).joinedload(
                    WaybillUpload.files
                ),
                joinedload(WaybillTrackingRecord.user),
                joinedload(WaybillTrackingRecord.pod_files),
                joinedload(WaybillTrackingRecord.parcels),
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
                joinedload(WaybillTrackingRecord.upload).joinedload(
                    WaybillUpload.files
                ),
                joinedload(WaybillTrackingRecord.user),
                joinedload(WaybillTrackingRecord.pod_files),
                joinedload(WaybillTrackingRecord.parcels),
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
            pallet_count=0,
            fyco_status="released",
            released_count=0,
            outbound_count=0,
        )
        self.db.add(record)
        self.db.flush()
        return record

    def add_pod_file(
        self,
        *,
        record: WaybillTrackingRecord,
        uploaded_by_user_id: UUID,
        original_filename: str,
        storage_path: str,
        content_type: str | None,
        size_bytes: int,
        sha256: str,
    ) -> WaybillPodFile:
        file = WaybillPodFile(
            tracking_record_id=record.id,
            uploaded_by_user_id=uploaded_by_user_id,
            original_filename=original_filename,
            storage_path=storage_path,
            content_type=content_type,
            size_bytes=size_bytes,
            sha256=sha256,
        )
        self.db.add(file)
        self.db.flush()
        return file

    def delete_pod_file(self, file: WaybillPodFile) -> None:
        self.db.delete(file)
        self.db.flush()

    def replace_parcels(
        self,
        record: WaybillTrackingRecord,
        parcel_payloads: list[dict],
    ) -> list[WaybillParcel]:
        for parcel in list(record.parcels):
            self.db.delete(parcel)
        self.db.flush()

        parcels = [
            WaybillParcel(
                tracking_record_id=record.id,
                parcel_unit_number=payload["parcel_unit_number"],
                status=payload.get("status", "created"),
                number_of_items=payload["number_of_items"],
                weight_kg=payload["weight_kg"],
                destination_raw=payload["destination_raw"],
                destination_code=payload["destination_code"],
                destination_name=payload["destination_name"],
                inbound=payload.get("inbound", False),
                outbound=payload.get("outbound", False),
                special_instruction=payload.get("special_instruction", False),
            )
            for payload in parcel_payloads
        ]
        self.db.add_all(parcels)
        self.db.flush()
        return parcels

    def update_parcels(
        self,
        parcels: list[WaybillParcel],
        *,
        status: str | None = None,
        inbound: bool | None = None,
        outbound: bool | None = None,
        special_instruction: bool | None = None,
    ) -> list[WaybillParcel]:
        for parcel in parcels:
            if status is not None:
                parcel.status = status
            if inbound is not None:
                parcel.inbound = inbound
            if outbound is not None:
                parcel.outbound = outbound
            if special_instruction is not None:
                parcel.special_instruction = special_instruction
        self.db.flush()
        return parcels

    def update(
        self,
        record: WaybillTrackingRecord,
        *,
        status: str | None = None,
        received_count: int | None = None,
        received_total: int | None = None,
        in_warehouse_count: int | None = None,
        pallet_count: int | None = None,
        fyco_status: str | None = None,
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
        if pallet_count is not None:
            record.pallet_count = pallet_count
        if fyco_status is not None:
            record.fyco_status = fyco_status
        if released_count is not None:
            record.released_count = released_count
        if outbound_count is not None:
            record.outbound_count = outbound_count
        for field_name, value in (milestone_updates or {}).items():
            setattr(record, field_name, value)
        self.db.flush()
        return record
