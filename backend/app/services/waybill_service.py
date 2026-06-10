import secrets
import string
from datetime import datetime, timezone
from uuid import UUID

from fastapi import Request
from sqlalchemy.orm import Session

from app.db.models import User, WaybillTrackingRecord, WaybillUpload
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.waybill_repository import WaybillRepository
from app.schemas.waybill import WaybillItem, WaybillListResponse, WaybillUpdateRequest
from app.schemas.waybill_upload import WaybillUploadUserItem
from app.services.request_context import get_request_ip, get_request_user_agent


WAYBILL_STATUSES = {
    "created",
    "noa_received",
    "received",
    "ready_to_scan",
    "scanning",
    "pending_clearance",
    "partial_inbound",
    "inbound",
    "partial_outbound",
    "outbound",
}
PUBLIC_CODE_ALPHABET = string.ascii_uppercase + string.digits
MILESTONE_PAYLOAD_TO_MODEL = {
    "noaAt": "noa_at",
    "collectionAt": "collection_at",
    "scannedAt": "scanned_at",
    "customsClearanceAt": "customs_clearance_at",
    "outboundAt": "outbound_at",
}


class WaybillValidationError(ValueError):
    pass


class WaybillPermissionError(PermissionError):
    pass


class WaybillService:
    def __init__(self, db: Session):
        self.db = db
        self.waybills = WaybillRepository(db)
        self.audit_logs = AuditLogRepository(db)

    def ensure_tracking_for_upload(
        self,
        upload: WaybillUpload,
    ) -> WaybillTrackingRecord:
        existing = self.waybills.get_by_upload_id(upload.id)
        if existing is not None:
            return existing

        for _ in range(50):
            public_code = self._generate_public_code()
            if not self.waybills.public_code_exists(public_code):
                return self.waybills.create_for_upload(
                    upload=upload,
                    public_code=public_code,
                )
        raise WaybillValidationError("Unable to generate a unique waybill public code")

    def list_waybills(
        self,
        actor: User,
        *,
        user_id: UUID | None = None,
        status: str | None = None,
        query: str | None = None,
    ) -> WaybillListResponse:
        if status and status not in WAYBILL_STATUSES:
            raise WaybillValidationError("Waybill status is invalid")

        scoped_user_id = user_id if actor.role == "admin" else actor.id
        records = self.waybills.list(
            user_id=scoped_user_id,
            status=status,
            query=query,
        )
        return WaybillListResponse(items=[self._build_item(record) for record in records])

    def get_waybill(self, actor: User, *, public_code: str) -> WaybillItem:
        record = self._get_visible_record(actor, public_code=public_code)
        return self._build_item(record)

    def update_waybill(
        self,
        actor: User,
        *,
        public_code: str,
        payload: WaybillUpdateRequest,
        request: Request,
    ) -> WaybillItem:
        if actor.role != "admin":
            raise WaybillPermissionError("Admin permission required")
        record = self._get_visible_record(actor, public_code=public_code)

        status_changed = payload.status is not None and payload.status != record.status
        if status_changed:
            record.status_changed_at = datetime.now(timezone.utc)

        self._validate_counts(record, payload)
        milestone_updates = {
            model_field: getattr(payload, payload_field)
            for payload_field, model_field in MILESTONE_PAYLOAD_TO_MODEL.items()
            if payload_field in payload.model_fields_set
        }
        self.waybills.update(
            record,
            status=payload.status,
            received_count=payload.receivedCount,
            received_total=payload.receivedTotal,
            in_warehouse_count=payload.inWarehouseCount,
            released_count=payload.releasedCount,
            outbound_count=payload.outboundCount,
            milestone_updates=milestone_updates,
        )
        self.audit_logs.create(
            "update_waybill_tracking",
            actor_user_id=actor.id,
            target_type="waybill_tracking_record",
            target_id=str(record.id),
            ip_address=get_request_ip(request),
            user_agent=get_request_user_agent(request),
            metadata={
                "publicCode": record.public_code,
                "airWaybillNumber": record.upload.air_waybill_number,
                "status": record.status,
                "statusChanged": status_changed,
                "milestoneFields": list(milestone_updates.keys()),
            },
        )
        self.db.commit()
        self.db.refresh(record)
        refreshed = self.waybills.get_by_public_code(record.public_code)
        if refreshed is None:
            raise WaybillValidationError("Waybill not found")
        return self._build_item(refreshed)

    def _get_visible_record(
        self,
        actor: User,
        *,
        public_code: str,
    ) -> WaybillTrackingRecord:
        record = self.waybills.get_by_public_code(public_code)
        if record is None or record.upload.status != "approved":
            raise WaybillValidationError("Waybill not found")
        if actor.role != "admin" and record.user_id != actor.id:
            raise WaybillPermissionError("Cannot access another user's waybill")
        return record

    def _validate_counts(
        self,
        record: WaybillTrackingRecord,
        payload: WaybillUpdateRequest,
    ) -> None:
        pieces = record.upload.pieces
        count_fields = {
            "receivedCount": payload.receivedCount,
            "receivedTotal": payload.receivedTotal,
            "inWarehouseCount": payload.inWarehouseCount,
            "releasedCount": payload.releasedCount,
            "outboundCount": payload.outboundCount,
        }
        for label, value in count_fields.items():
            if value is not None and value > pieces:
                raise WaybillValidationError(f"{label} cannot exceed the waybill pieces")

    def _build_item(self, record: WaybillTrackingRecord) -> WaybillItem:
        upload = record.upload
        return WaybillItem(
            id=record.id,
            publicCode=record.public_code,
            uploadId=record.upload_id,
            userId=record.user_id,
            number=upload.air_waybill_number,
            status=record.status,
            statusChangedAt=record.status_changed_at,
            weightKg=upload.gross_weight_kg,
            pieces=upload.pieces,
            receivedCount=record.received_count,
            receivedTotal=record.received_total,
            inWarehouseCount=record.in_warehouse_count,
            releasedCount=record.released_count,
            outboundCount=record.outbound_count,
            noaAt=record.noa_at,
            collectionAt=record.collection_at,
            scannedAt=record.scanned_at,
            customsClearanceAt=record.customs_clearance_at,
            outboundAt=record.outbound_at,
            createdAt=record.created_at,
            updatedAt=record.updated_at,
            user=WaybillUploadUserItem.model_validate(record.user)
            if record.user is not None
            else None,
        )

    def _generate_public_code(self) -> str:
        return "".join(secrets.choice(PUBLIC_CODE_ALPHABET) for _ in range(8))
