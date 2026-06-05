import hashlib
import logging
import re
import shutil
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import UUID

from fastapi import Request, UploadFile
from sqlalchemy.orm import Session

from app.core.config import PROJECT_ROOT, Settings, get_settings
from app.db.models import User, WaybillUpload, WaybillUploadFile
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.user_repository import UserRepository
from app.repositories.waybill_upload_repository import (
    WaybillUploadRepository,
    normalize_waybill_number,
)
from app.schemas.waybill_upload import (
    WaybillPreAlertUploadResponse,
    WaybillUploadDeleteResponse,
    WaybillUploadItem,
    WaybillUploadListResponse,
)
from app.services.pre_alert_validator import (
    PreAlertValidationError,
    validate_pre_alert_excel,
)
from app.services.request_context import get_request_ip, get_request_user_agent


SHIPMENT_TYPES = {"Air", "Road", "Train"}
UPLOAD_STATUSES = {"pending_review", "approved", "rejected"}
PDF_MAX_BYTES = 10 * 1024 * 1024
PRE_ALERT_MAX_BYTES = 20 * 1024 * 1024
PDF_EXTENSIONS = {".pdf"}
EXCEL_EXTENSIONS = {".xls", ".xlsx"}

logger = logging.getLogger(__name__)


class WaybillUploadValidationError(ValueError):
    pass


class WaybillUploadPermissionError(PermissionError):
    pass


class WaybillUploadService:
    def __init__(self, db: Session, settings: Settings | None = None):
        self.db = db
        self.settings = settings or get_settings()
        self.uploads = WaybillUploadRepository(db)
        self.users = UserRepository(db)
        self.audit_logs = AuditLogRepository(db)

    def list_uploads(
        self,
        actor: User,
        *,
        user_id: UUID | None = None,
        status: str | None = None,
        query: str | None = None,
    ) -> WaybillUploadListResponse:
        if status and status not in UPLOAD_STATUSES:
            raise WaybillUploadValidationError("Upload status is invalid")

        uploads = (
            self.uploads.list_all(
                user_id=user_id,
                status=status,
                query=query,
            )
            if actor.role == "admin"
            else self.uploads.list_for_user(
                actor.id,
                status=status,
                query=query,
            )
        )
        return WaybillUploadListResponse(
            items=[WaybillUploadItem.model_validate(upload) for upload in uploads]
        )

    async def create_pre_alert_upload(
        self,
        *,
        actor: User,
        request: Request,
        shipment_type: str,
        air_waybill_number: str,
        gross_weight_kg: str,
        pieces: str,
        arrival_flight_number: str | None,
        air_waybill_documents: list[UploadFile],
        pre_alert_file: UploadFile,
        target_user_id: UUID | None = None,
    ) -> WaybillPreAlertUploadResponse:
        target_user = self._resolve_target_user(actor, target_user_id)
        shipment_type = self._validate_shipment_type(shipment_type)
        air_waybill_number = self._validate_air_waybill_number(air_waybill_number)
        gross_weight = self._parse_positive_decimal(
            gross_weight_kg,
            "Air Waybill Gross Weight (KG)",
        )
        pieces_value = self._parse_positive_int(pieces, "Air Waybill Pieces")
        arrival_flight_number = (arrival_flight_number or "").strip() or None

        documents = await self._collect_files(
            air_waybill_documents,
            file_kind="air_waybill_document",
            allowed_extensions=PDF_EXTENSIONS,
            max_bytes=PDF_MAX_BYTES,
            required=True,
        )
        pre_alert = await self._collect_files(
            [pre_alert_file],
            file_kind="customer_pre_alert",
            allowed_extensions=EXCEL_EXTENSIONS,
            max_bytes=PRE_ALERT_MAX_BYTES,
            required=True,
        )
        self._validate_pre_alert_file(pre_alert[0])

        upload = self.uploads.create(
            user_id=target_user.id,
            uploaded_by_user_id=actor.id,
            shipment_type=shipment_type,
            air_waybill_number=air_waybill_number,
            gross_weight_kg=gross_weight,
            pieces=pieces_value,
            arrival_flight_number=arrival_flight_number,
        )
        saved_files = []
        try:
            for file_payload in [*documents, *pre_alert]:
                saved_files.append(self._save_file(upload.id, file_payload))

            for saved_file in saved_files:
                self.uploads.add_file(
                    upload_id=upload.id,
                    file_kind=saved_file["file_kind"],
                    original_filename=saved_file["original_filename"],
                    storage_path=saved_file["storage_path"],
                    content_type=saved_file["content_type"],
                    size_bytes=saved_file["size_bytes"],
                    sha256=saved_file["sha256"],
                )

            self.audit_logs.create(
                "upload_pre_alert",
                actor_user_id=actor.id,
                target_type="waybill_upload",
                target_id=str(upload.id),
                ip_address=get_request_ip(request),
                user_agent=get_request_user_agent(request),
                metadata={
                    "airWaybillNumber": air_waybill_number,
                    "boundUserId": str(target_user.id),
                    "shipmentType": shipment_type,
                },
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            for saved_file in saved_files:
                Path(saved_file["storage_path"]).unlink(missing_ok=True)
            raise

        refreshed_upload = self.uploads.get_by_id(upload.id)
        if refreshed_upload is None:
            raise WaybillUploadValidationError("Waybill upload not found")
        return self._build_pre_alert_response(refreshed_upload)

    def update_status(
        self,
        *,
        actor: User,
        upload_id: UUID,
        status: str,
        request: Request,
    ) -> WaybillUploadItem:
        if actor.role != "admin":
            raise WaybillUploadPermissionError("Admin permission required")
        if status not in UPLOAD_STATUSES:
            raise WaybillUploadValidationError("Invalid upload status")

        upload = self.uploads.get_by_id(upload_id)
        if upload is None:
            raise WaybillUploadValidationError("Waybill upload not found")

        upload = self.uploads.update_status(
            upload=upload,
            status=status,
            reviewed_by_user_id=actor.id,
        )
        self.audit_logs.create(
            "review_waybill_upload",
            actor_user_id=actor.id,
            target_type="waybill_upload",
            target_id=str(upload.id),
            ip_address=get_request_ip(request),
            user_agent=get_request_user_agent(request),
            metadata={
                "airWaybillNumber": upload.air_waybill_number,
                "status": status,
            },
        )
        self.db.commit()
        self.db.refresh(upload)
        refreshed_upload = self.uploads.get_by_id(upload.id)
        if refreshed_upload is None:
            raise WaybillUploadValidationError("Waybill upload not found")
        return WaybillUploadItem.model_validate(refreshed_upload)

    def delete_upload(
        self,
        *,
        actor: User,
        upload_id: UUID,
        request: Request,
    ) -> WaybillUploadDeleteResponse:
        upload = self.uploads.get_by_id(upload_id)
        if upload is None:
            raise WaybillUploadValidationError("Waybill upload not found")
        if actor.role != "admin" and upload.user_id != actor.id:
            raise WaybillUploadPermissionError("Cannot delete another user's upload")

        file_paths = [file.storage_path for file in upload.files]

        self.audit_logs.create(
            "delete_waybill_upload",
            actor_user_id=actor.id,
            target_type="waybill_upload",
            target_id=str(upload.id),
            ip_address=get_request_ip(request),
            user_agent=get_request_user_agent(request),
            metadata={
                "airWaybillNumber": upload.air_waybill_number,
                "boundUserId": str(upload.user_id),
                "localOnly": True,
            },
        )
        self.uploads.delete(upload)
        self.db.commit()
        self._delete_upload_storage(upload_id, file_paths)
        return WaybillUploadDeleteResponse(
            status="deleted",
            upload_id=upload_id,
        )

    def get_download_file(
        self,
        *,
        actor: User,
        upload_id: UUID,
        file_id: UUID,
        request: Request,
    ) -> WaybillUploadFile:
        upload = self.uploads.get_by_id(upload_id)
        if upload is None:
            raise WaybillUploadValidationError("Waybill upload not found")
        if actor.role != "admin" and upload.user_id != actor.id:
            raise WaybillUploadPermissionError("Cannot download another user's upload")

        file = next((item for item in upload.files if item.id == file_id), None)
        if file is None:
            raise WaybillUploadValidationError("Upload file not found")
        if not Path(file.storage_path).is_file():
            raise WaybillUploadValidationError("Upload file is missing")

        self.audit_logs.create(
            "download_waybill_upload_file",
            actor_user_id=actor.id,
            target_type="waybill_upload_file",
            target_id=str(file.id),
            ip_address=get_request_ip(request),
            user_agent=get_request_user_agent(request),
            metadata={
                "uploadId": str(upload.id),
                "airWaybillNumber": upload.air_waybill_number,
                "fileKind": file.file_kind,
                "filename": file.original_filename,
            },
        )
        self.db.commit()
        return file

    def _build_pre_alert_response(
        self,
        upload: WaybillUpload,
    ) -> WaybillPreAlertUploadResponse:
        return WaybillPreAlertUploadResponse(
            upload_id=upload.id,
            air_waybill_number=upload.air_waybill_number,
            status=upload.status,
            bound_user_id=upload.user_id,
        )

    def _validate_pre_alert_file(self, file_payload: dict) -> None:
        try:
            validate_pre_alert_excel(
                filename=file_payload["original_filename"],
                content=file_payload["content"],
            )
        except PreAlertValidationError as exc:
            raise WaybillUploadValidationError(str(exc)) from exc

    def _resolve_target_user(self, actor: User, target_user_id: UUID | None) -> User:
        if target_user_id is None:
            return actor
        if actor.role != "admin":
            raise WaybillUploadPermissionError("Only admins can upload for another user")

        user = self.users.get_by_id(target_user_id)
        if user is None:
            raise WaybillUploadValidationError("Target user not found")
        if user.status != "active":
            raise WaybillUploadValidationError("Target user is disabled")
        return user

    def _validate_shipment_type(self, value: str) -> str:
        shipment_type = value.strip()
        if shipment_type not in SHIPMENT_TYPES:
            raise WaybillUploadValidationError("Shipment Type is invalid")
        return shipment_type

    def _validate_air_waybill_number(self, value: str) -> str:
        number = value.strip()
        if not number:
            raise WaybillUploadValidationError("Air Waybill Number is required")
        if not normalize_waybill_number(number):
            raise WaybillUploadValidationError("Air Waybill Number is invalid")
        return number

    def _parse_positive_decimal(self, value: str, label: str) -> Decimal:
        try:
            parsed = Decimal(value.strip())
        except (InvalidOperation, AttributeError) as exc:
            raise WaybillUploadValidationError(f"{label} must be a number") from exc
        if parsed <= 0:
            raise WaybillUploadValidationError(f"{label} must be greater than 0")
        return parsed

    def _parse_positive_int(self, value: str, label: str) -> int:
        if not value or not re.fullmatch(r"\d+", value.strip()):
            raise WaybillUploadValidationError(f"{label} must be a number")
        parsed = int(value.strip())
        if parsed <= 0:
            raise WaybillUploadValidationError(f"{label} must be greater than 0")
        return parsed

    async def _collect_files(
        self,
        files: list[UploadFile],
        *,
        file_kind: str,
        allowed_extensions: set[str],
        max_bytes: int,
        required: bool,
    ) -> list[dict]:
        if required and not files:
            raise WaybillUploadValidationError("Required file is missing")

        collected = []
        for file in files:
            if not file or not file.filename:
                continue
            filename = Path(file.filename).name
            extension = Path(filename).suffix.lower()
            if extension not in allowed_extensions:
                raise WaybillUploadValidationError(
                    f"{filename} has an unsupported file type"
                )

            content = await file.read()
            if not content:
                raise WaybillUploadValidationError(f"{filename} is empty")
            if len(content) > max_bytes:
                raise WaybillUploadValidationError(f"{filename} exceeds the size limit")
            if file_kind == "air_waybill_document" and not content.startswith(b"%PDF"):
                raise WaybillUploadValidationError(f"{filename} must be a PDF file")

            collected.append(
                {
                    "file_kind": file_kind,
                    "original_filename": filename,
                    "content_type": file.content_type,
                    "content": content,
                    "size_bytes": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "extension": extension,
                }
            )

        if required and not collected:
            raise WaybillUploadValidationError("Required file is missing")
        return collected

    def _save_file(self, upload_id: UUID, file_payload: dict) -> dict:
        storage_root = self._storage_root()
        upload_dir = storage_root / str(upload_id)
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

    def _delete_upload_storage(self, upload_id: UUID, file_paths: list[str]) -> None:
        storage_root = self._storage_root().resolve()
        upload_dir = (storage_root / str(upload_id)).resolve()
        try:
            if upload_dir.exists() and upload_dir.is_relative_to(storage_root):
                shutil.rmtree(upload_dir)
                return

            for file_path in file_paths:
                path = Path(file_path).resolve()
                if path.is_relative_to(storage_root):
                    path.unlink(missing_ok=True)
        except Exception:
            logger.warning(
                "Failed to delete local upload storage for %s",
                upload_id,
                exc_info=True,
            )
