import hashlib
import logging
import re
import secrets
import string
import uuid
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from fastapi import Request, UploadFile
from sqlalchemy.orm import Session

from app.core.config import PROJECT_ROOT, Settings, get_settings
from app.db.models import (
    User,
    WaybillParcel,
    WaybillPodFile,
    WaybillTrackingRecord,
    WaybillUpload,
)
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.supplier_repository import SupplierRepository
from app.repositories.waybill_repository import WaybillRepository
from app.schemas.waybill import (
    WaybillItem,
    WaybillListResponse,
    WaybillParcelBulkUpdateRequest,
    WaybillParcelItem,
    WaybillParcelListResponse,
    WaybillPodDeleteResponse,
    WaybillUpdateRequest,
)
from app.schemas.supplier import SupplierVersionConfig
from app.schemas.waybill_upload import WaybillUploadUserItem
from app.services.request_context import get_request_ip, get_request_user_agent
from app.services.supplier_rule_engine import SupplierRuleEngine, SupplierStructureError


WAYBILL_STATUSES = {
    "created",
    "noa_received",
    "received",
    "ready_to_scan",
    "scanning",
    "pending_clearance",
    "cleared",
    "partial_inbound",
    "inbound",
    "partial_outbound",
    "outbound",
}
PARCEL_STATUSES = {
    "created",
    "pending_check",
    "inspection",
    "released",
    "temporary_released",
    "exception",
    "confiscated",
    "destroyed",
    "on_hold",
    "inbound",
    "outbound",
}
PUBLIC_CODE_ALPHABET = string.ascii_uppercase + string.digits
POD_MAX_FILES = 2
POD_MAX_BYTES = 10 * 1024 * 1024
POD_FILE_TYPES = {
    ".pdf": ("PDF", "application/pdf", (b"%PDF",)),
    ".jpg": ("JPEG", "image/jpeg", (b"\xff\xd8\xff",)),
    ".jpeg": ("JPEG", "image/jpeg", (b"\xff\xd8\xff",)),
    ".png": ("PNG", "image/png", (b"\x89PNG\r\n\x1a\n",)),
}
POD_ALLOWED_FORMATS = "PDF, JPEG, or PNG"
MILESTONE_PAYLOAD_TO_MODEL = {
    "noaAt": "noa_at",
    "collectionAt": "collection_at",
    "scannedAt": "scanned_at",
    "customsClearanceAt": "customs_clearance_at",
    "outboundAt": "outbound_at",
}

logger = logging.getLogger(__name__)


class WaybillValidationError(ValueError):
    pass


class WaybillPermissionError(PermissionError):
    pass


class WaybillService:
    def __init__(self, db: Session, settings: Settings | None = None):
        self.db = db
        self.settings = settings or get_settings()
        self.waybills = WaybillRepository(db)
        self.suppliers = SupplierRepository(db)
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

        airport_fields_changed = []
        if "airportOfDeparture" in payload.model_fields_set:
            departure = (payload.airportOfDeparture or "").strip().upper()
            if not departure:
                raise WaybillValidationError("Airport of Departure is required")
            record.upload.airport_of_departure = departure
            airport_fields_changed.append("airportOfDeparture")
        if "airportOfArrival" in payload.model_fields_set:
            arrival = (payload.airportOfArrival or "").strip().upper()
            if not re.fullmatch(r"[A-Z]{3}", arrival):
                raise WaybillValidationError(
                    "Airport of Arrival must be a three-letter IATA code"
                )
            record.upload.airport_of_arrival = arrival
            airport_fields_changed.append("airportOfArrival")

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
            pallet_count=payload.palletCount,
            fyco_status=payload.fycoStatus,
            update_fyco_status="fycoStatus" in payload.model_fields_set,
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
                "fycoStatus": record.fyco_status,
                "statusChanged": status_changed,
                "milestoneFields": list(milestone_updates.keys()),
                "airportFields": airport_fields_changed,
                "airportOfDeparture": record.upload.airport_of_departure,
                "airportOfArrival": record.upload.airport_of_arrival,
            },
        )
        self.db.commit()
        self.db.refresh(record)
        refreshed = self.waybills.get_by_public_code(record.public_code)
        if refreshed is None:
            raise WaybillValidationError("Waybill not found")
        return self._build_item(refreshed)

    async def upload_pod_file(
        self,
        actor: User,
        *,
        public_code: str,
        file: UploadFile,
        request: Request,
    ) -> WaybillItem:
        if actor.role != "admin":
            raise WaybillPermissionError("Admin permission required")
        record = self._get_visible_record(actor, public_code=public_code)
        if len(record.pod_files) >= POD_MAX_FILES:
            raise WaybillValidationError("POD supports up to 2 files")

        file_payload = await self._collect_pod_file(file)
        saved_file = self._save_pod_file(record, file_payload)
        try:
            pod_file = self.waybills.add_pod_file(
                record=record,
                uploaded_by_user_id=actor.id,
                original_filename=saved_file["original_filename"],
                storage_path=saved_file["storage_path"],
                content_type=saved_file["content_type"],
                size_bytes=saved_file["size_bytes"],
                sha256=saved_file["sha256"],
            )
            self.audit_logs.create(
                "upload_waybill_pod_file",
                actor_user_id=actor.id,
                target_type="waybill_pod_file",
                target_id=str(pod_file.id),
                ip_address=get_request_ip(request),
                user_agent=get_request_user_agent(request),
                metadata={
                    "publicCode": record.public_code,
                    "airWaybillNumber": record.upload.air_waybill_number,
                    "filename": saved_file["original_filename"],
                    "sizeBytes": saved_file["size_bytes"],
                },
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            self._delete_pod_storage_file(saved_file["storage_path"])
            raise

        refreshed = self.waybills.get_by_public_code(record.public_code)
        if refreshed is None:
            raise WaybillValidationError("Waybill not found")
        return self._build_item(refreshed)

    def delete_pod_file(
        self,
        actor: User,
        *,
        public_code: str,
        pod_file_id: UUID,
        request: Request,
    ) -> WaybillPodDeleteResponse:
        if actor.role != "admin":
            raise WaybillPermissionError("Admin permission required")
        record = self._get_visible_record(actor, public_code=public_code)
        pod_file = self._find_pod_file(record, pod_file_id)
        if pod_file is None:
            raise WaybillValidationError("POD file not found")

        storage_path = pod_file.storage_path
        self.audit_logs.create(
            "delete_waybill_pod_file",
            actor_user_id=actor.id,
            target_type="waybill_pod_file",
            target_id=str(pod_file.id),
            ip_address=get_request_ip(request),
            user_agent=get_request_user_agent(request),
            metadata={
                "publicCode": record.public_code,
                "airWaybillNumber": record.upload.air_waybill_number,
                "filename": pod_file.original_filename,
            },
        )
        self.waybills.delete_pod_file(pod_file)
        self.db.commit()
        self._delete_pod_storage_file(storage_path)
        return WaybillPodDeleteResponse(status="deleted", podFileId=pod_file_id)

    def get_pod_download_file(
        self,
        actor: User,
        *,
        public_code: str,
        pod_file_id: UUID,
        request: Request,
    ) -> WaybillPodFile:
        record = self._get_visible_record(actor, public_code=public_code)
        pod_file = self._find_pod_file(record, pod_file_id)
        if pod_file is None:
            raise WaybillValidationError("POD file not found")
        if not Path(pod_file.storage_path).is_file():
            raise WaybillValidationError("POD file is missing")

        self.audit_logs.create(
            "download_waybill_pod_file",
            actor_user_id=actor.id,
            target_type="waybill_pod_file",
            target_id=str(pod_file.id),
            ip_address=get_request_ip(request),
            user_agent=get_request_user_agent(request),
            metadata={
                "publicCode": record.public_code,
                "airWaybillNumber": record.upload.air_waybill_number,
                "filename": pod_file.original_filename,
            },
        )
        self.db.commit()
        return pod_file

    def sync_parcels_for_record(
        self,
        record: WaybillTrackingRecord,
        *,
        force: bool = False,
    ) -> bool:
        if record.parcels and not force:
            return False

        pre_alert_file = self._get_pre_alert_file(record.upload)
        if pre_alert_file is None:
            if not force:
                return False
            raise WaybillValidationError("Upload Pre Alert File not found")
        file_path = Path(pre_alert_file.storage_path)
        if not file_path.is_file():
            if not force:
                return False
            raise WaybillValidationError("Upload Pre Alert File is missing")

        supplier_version = self.suppliers.get_version(record.upload.supplier_version_id)
        if supplier_version is None:
            raise WaybillValidationError("Supplier version not found")
        try:
            evaluation = SupplierRuleEngine().evaluate(
                filename=pre_alert_file.original_filename,
                content=file_path.read_bytes(),
                config=SupplierVersionConfig.model_validate(supplier_version.config),
            )
        except SupplierStructureError as exc:
            if not force:
                logger.info(
                    "Skipping optional parcel sync for historical upload %s: %s",
                    record.upload_id,
                    exc,
                )
                return False
            raise WaybillValidationError(str(exc)) from exc

        if not evaluation.parcels:
            return False

        self.waybills.replace_parcels(
            record,
            [
                {
                    "parcel_unit_number": parcel.parcel_unit_number,
                    "number_of_items": parcel.number_of_items,
                    "weight_kg": parcel.weight_kg,
                    "destination_raw": parcel.destination_raw,
                    "destination_code": parcel.destination_code,
                    "destination_name": parcel.destination_name,
                }
                for parcel in evaluation.parcels
            ],
        )
        return True

    def get_parcels(
        self,
        actor: User,
        *,
        public_code: str,
    ) -> WaybillParcelListResponse:
        record = self._get_visible_record(actor, public_code=public_code)
        changed = self.sync_parcels_for_record(record, force=False)
        if changed:
            self.db.commit()
            refreshed = self.waybills.get_by_public_code(record.public_code)
            if refreshed is None:
                raise WaybillValidationError("Waybill not found")
            record = refreshed
        return self._build_parcel_list(record.parcels)

    def update_parcels(
        self,
        actor: User,
        *,
        public_code: str,
        payload: WaybillParcelBulkUpdateRequest,
        request: Request,
    ) -> WaybillParcelListResponse:
        if actor.role != "admin":
            raise WaybillPermissionError("Admin permission required")
        record = self._get_visible_record(actor, public_code=public_code)
        changed = self.sync_parcels_for_record(record, force=False)

        if (
            payload.status is None
            and payload.inbound is None
            and payload.outbound is None
            and payload.specialInstruction is None
        ):
            raise WaybillValidationError("At least one parcel field is required")
        if payload.status is not None and payload.status not in PARCEL_STATUSES:
            raise WaybillValidationError("Parcel status is invalid")

        parcel_ids = set(payload.parcelIds)
        selected_parcels = [
            parcel for parcel in record.parcels if parcel.id in parcel_ids
        ]
        if len(selected_parcels) != len(parcel_ids):
            raise WaybillValidationError("One or more parcels were not found")

        self.waybills.update_parcels(
            selected_parcels,
            status=payload.status,
            inbound=payload.inbound,
            outbound=payload.outbound,
            special_instruction=payload.specialInstruction,
        )
        self.audit_logs.create(
            "update_waybill_parcels",
            actor_user_id=actor.id,
            target_type="waybill_tracking_record",
            target_id=str(record.id),
            ip_address=get_request_ip(request),
            user_agent=get_request_user_agent(request),
            metadata={
                "publicCode": record.public_code,
                "airWaybillNumber": record.upload.air_waybill_number,
                "parcelIds": [str(parcel_id) for parcel_id in payload.parcelIds],
                "status": payload.status,
                "inbound": payload.inbound,
                "outbound": payload.outbound,
                "specialInstruction": payload.specialInstruction,
                "lazyParsed": changed,
            },
        )
        self.db.commit()
        refreshed = self.waybills.get_by_public_code(record.public_code)
        if refreshed is None:
            raise WaybillValidationError("Waybill not found")
        return self._build_parcel_list(refreshed.parcels)

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

    def _find_pod_file(
        self,
        record: WaybillTrackingRecord,
        pod_file_id: UUID,
    ) -> WaybillPodFile | None:
        return next((item for item in record.pod_files if item.id == pod_file_id), None)

    async def _collect_pod_file(self, file: UploadFile) -> dict:
        if not file or not file.filename:
            raise WaybillValidationError("POD file is required")

        filename = Path(file.filename).name
        extension = Path(filename).suffix.lower()
        file_type = POD_FILE_TYPES.get(extension)
        if file_type is None:
            raise WaybillValidationError(
                f"{filename} must be a {POD_ALLOWED_FORMATS} file"
            )

        content = await file.read()
        if not content:
            raise WaybillValidationError(f"{filename} is empty")
        if len(content) > POD_MAX_BYTES:
            raise WaybillValidationError(f"{filename} exceeds the size limit")
        format_label, media_type, signatures = file_type
        if not content.startswith(signatures):
            raise WaybillValidationError(f"{filename} must be a valid {format_label} file")

        return {
            "original_filename": filename,
            "content_type": media_type,
            "content": content,
            "size_bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "extension": extension,
        }

    def _save_pod_file(self, record: WaybillTrackingRecord, file_payload: dict) -> dict:
        storage_root = self._storage_root()
        upload_dir = storage_root / str(record.upload_id) / "pod"
        upload_dir.mkdir(parents=True, exist_ok=True)
        storage_path = upload_dir / f"{uuid.uuid4().hex}{file_payload['extension']}"
        storage_path.write_bytes(file_payload["content"])
        return {
            **file_payload,
            "storage_path": str(storage_path),
        }

    def _storage_root(self) -> Path:
        storage_root = self.settings.upload_storage_dir
        if not storage_root.is_absolute():
            storage_root = PROJECT_ROOT / storage_root
        storage_root.mkdir(parents=True, exist_ok=True)
        return storage_root

    def _delete_pod_storage_file(self, storage_path: str) -> None:
        storage_root = self._storage_root().resolve()
        try:
            path = Path(storage_path).resolve()
            if path.is_relative_to(storage_root):
                path.unlink(missing_ok=True)
        except Exception:
            logger.warning(
                "Failed to delete local POD storage file %s",
                storage_path,
                exc_info=True,
            )

    def _get_pre_alert_file(self, upload: WaybillUpload):
        return next(
            (
                file
                for file in upload.files
                if file.file_kind == "customer_pre_alert"
            ),
            None,
        )

    def _build_parcel_list(
        self,
        parcels: list[WaybillParcel],
    ) -> WaybillParcelListResponse:
        sorted_parcels = sorted(parcels, key=lambda parcel: parcel.parcel_unit_number)
        return WaybillParcelListResponse(
            items=[WaybillParcelItem.model_validate(parcel) for parcel in sorted_parcels]
        )

    def _build_item(self, record: WaybillTrackingRecord) -> WaybillItem:
        upload = record.upload
        billing_entry = upload.billing_entry
        return WaybillItem(
            id=record.id,
            publicCode=record.public_code,
            uploadId=record.upload_id,
            userId=record.user_id,
            number=upload.air_waybill_number,
            status=record.status,
            airportOfDeparture=upload.airport_of_departure,
            airportOfArrival=upload.airport_of_arrival,
            statusChangedAt=record.status_changed_at,
            weightKg=upload.gross_weight_kg,
            pieces=upload.pieces,
            customsCartons=billing_entry.billable_unit_count if billing_entry else None,
            customsAmount=billing_entry.amount if billing_entry else None,
            receivedCount=record.received_count,
            receivedTotal=record.received_total,
            inWarehouseCount=record.in_warehouse_count,
            palletCount=record.pallet_count,
            fycoStatus=record.fyco_status,
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
            podFiles=record.pod_files,
        )

    def _generate_public_code(self) -> str:
        return "".join(secrets.choice(PUBLIC_CODE_ALPHABET) for _ in range(8))
