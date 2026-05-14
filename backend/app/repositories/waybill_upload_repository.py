from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.models import WaybillUpload, WaybillUploadFile
from app.repositories.waybill_user_binding_repository import normalize_waybill_number


class WaybillUploadRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, upload_id: UUID) -> WaybillUpload | None:
        statement = (
            select(WaybillUpload)
            .options(joinedload(WaybillUpload.files), joinedload(WaybillUpload.user))
            .where(WaybillUpload.id == upload_id)
            .limit(1)
        )
        return self.db.execute(statement).unique().scalar_one_or_none()

    def get_successful_by_normalized_number(self, number: str) -> WaybillUpload | None:
        normalized = normalize_waybill_number(number)
        statement = (
            select(WaybillUpload)
            .where(
                WaybillUpload.normalized_air_waybill_number == normalized,
                WaybillUpload.platform_submission_status == "success",
            )
            .order_by(WaybillUpload.created_at.desc(), WaybillUpload.id.desc())
            .limit(1)
        )
        return self.db.execute(statement).scalar_one_or_none()

    def list_for_user(
        self,
        user_id: UUID,
        *,
        platform_submission_status: str | None = None,
        status: str | None = None,
        query: str | None = None,
    ) -> list[WaybillUpload]:
        return self.list(
            user_id=user_id,
            platform_submission_status=platform_submission_status,
            status=status,
            query=query,
        )

    def list_all(
        self,
        *,
        user_id: UUID | None = None,
        platform_submission_status: str | None = None,
        status: str | None = None,
        query: str | None = None,
    ) -> list[WaybillUpload]:
        return self.list(
            user_id=user_id,
            platform_submission_status=platform_submission_status,
            status=status,
            query=query,
        )

    def list(
        self,
        *,
        user_id: UUID | None = None,
        platform_submission_status: str | None = None,
        status: str | None = None,
        query: str | None = None,
    ) -> list[WaybillUpload]:
        statement = (
            select(WaybillUpload)
            .options(joinedload(WaybillUpload.files), joinedload(WaybillUpload.user))
        )
        if user_id is not None:
            statement = statement.where(WaybillUpload.user_id == user_id)
        if platform_submission_status:
            statement = statement.where(
                WaybillUpload.platform_submission_status == platform_submission_status
            )
        if status:
            statement = statement.where(WaybillUpload.status == status)
        if query:
            normalized_query = normalize_waybill_number(query)
            pattern = f"%{query.strip()}%"
            normalized_pattern = f"%{normalized_query}%"
            statement = statement.where(
                WaybillUpload.air_waybill_number.ilike(pattern)
                | WaybillUpload.normalized_air_waybill_number.ilike(normalized_pattern)
            )
        statement = statement.order_by(
            WaybillUpload.created_at.desc(),
            WaybillUpload.id.desc(),
        )
        return list(self.db.execute(statement).unique().scalars().all())

    def create(
        self,
        *,
        user_id: UUID,
        uploaded_by_user_id: UUID,
        platform: str,
        shipment_type: str,
        air_waybill_number: str,
        gross_weight_kg,
        pieces: int,
        arrival_flight_number: str | None,
    ) -> WaybillUpload:
        upload = WaybillUpload(
            user_id=user_id,
            uploaded_by_user_id=uploaded_by_user_id,
            platform=platform,
            shipment_type=shipment_type,
            air_waybill_number=air_waybill_number,
            normalized_air_waybill_number=normalize_waybill_number(
                air_waybill_number
            ),
            gross_weight_kg=gross_weight_kg,
            pieces=pieces,
            arrival_flight_number=arrival_flight_number,
            status="pending_review",
        )
        self.db.add(upload)
        self.db.flush()
        return upload

    def add_file(
        self,
        *,
        upload_id: UUID,
        file_kind: str,
        original_filename: str,
        storage_path: str,
        content_type: str | None,
        size_bytes: int,
        sha256: str,
    ) -> WaybillUploadFile:
        file = WaybillUploadFile(
            upload_id=upload_id,
            file_kind=file_kind,
            original_filename=original_filename,
            storage_path=storage_path,
            content_type=content_type,
            size_bytes=size_bytes,
            sha256=sha256,
        )
        self.db.add(file)
        self.db.flush()
        return file

    def update_status(
        self,
        *,
        upload: WaybillUpload,
        status: str,
        reviewed_by_user_id: UUID,
    ) -> WaybillUpload:
        upload.status = status
        upload.reviewed_by_user_id = reviewed_by_user_id
        upload.reviewed_at = datetime.now(timezone.utc)
        self.db.flush()
        return upload

    def update_platform_submission(
        self,
        *,
        upload: WaybillUpload,
        status: str,
        error_message: str | None = None,
        method: str = "automated",
    ) -> WaybillUpload:
        upload.platform_submission_status = status
        upload.platform_submission_method = method
        upload.platform_submission_error = error_message
        upload.platform_submitted_at = (
            datetime.now(timezone.utc) if status == "success" else None
        )
        self.db.flush()
        return upload

    def delete(self, upload: WaybillUpload) -> None:
        self.db.delete(upload)
        self.db.flush()
