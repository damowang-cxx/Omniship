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
from app.repositories.waybill_upload_repository import WaybillUploadRepository
from app.repositories.waybill_user_binding_repository import (
    WaybillUserBindingRepository,
    normalize_waybill_number,
)
from app.schemas.waybill_upload import (
    WaybillPreAlertUploadResponse,
    WaybillUploadDeleteResponse,
    WaybillUploadItem,
    WaybillUploadListResponse,
    WaybillUploadResponse,
)
from app.services.alline_waybill_uploader import (
    AllineWaybillUploadError,
    AllineWaybillUploader,
)
from app.services.request_context import get_request_ip, get_request_user_agent


SHIPMENT_TYPES = {"Air", "Road", "Train"}
UPLOAD_PLATFORMS = {"ALLINE"}
UPLOAD_STATUSES = {"pending_review", "approved", "rejected"}
PLATFORM_SUBMISSION_STATUSES = {"pending", "success", "failed"}
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
        self.bindings = WaybillUserBindingRepository(db)
        self.uploads = WaybillUploadRepository(db)
        self.users = UserRepository(db)
        self.audit_logs = AuditLogRepository(db)

    def list_uploads(
        self,
        actor: User,
        *,
        user_id: UUID | None = None,
        platform_submission_status: str | None = None,
        status: str | None = None,
        query: str | None = None,
    ) -> WaybillUploadListResponse:
        if (
            platform_submission_status
            and platform_submission_status not in PLATFORM_SUBMISSION_STATUSES
        ):
            raise WaybillUploadValidationError("Platform submission status is invalid")
        if status and status not in UPLOAD_STATUSES:
            raise WaybillUploadValidationError("Upload status is invalid")

        uploads = (
            self.uploads.list_all(
                user_id=user_id,
                platform_submission_status=platform_submission_status,
                status=status,
                query=query,
            )
            if actor.role == "admin"
            else self.uploads.list_for_user(
                actor.id,
                platform_submission_status=platform_submission_status,
                status=status,
                query=query,
            )
        )
        return WaybillUploadListResponse(
            items=[WaybillUploadItem.model_validate(upload) for upload in uploads]
        )

    def bind_numbers(
        self,
        *,
        actor: User,
        numbers: list[str],
        request: Request,
    ) -> WaybillUploadResponse:
        created, skipped_count = self.bindings.create_many(
            user_id=actor.id,
            numbers=numbers,
            created_by_user_id=actor.id,
            source="upload",
        )
        self.audit_logs.create(
            "upload_waybill_numbers",
            actor_user_id=actor.id,
            target_type="waybill_user_binding",
            target_id=str(actor.id),
            ip_address=get_request_ip(request),
            user_agent=get_request_user_agent(request),
            metadata={
                "boundCount": len(created),
                "skippedCount": skipped_count,
            },
        )
        self.db.commit()
        return WaybillUploadResponse(
            bound_count=len(created),
            skipped_count=skipped_count,
            numbers=[binding.number for binding in created],
        )

    async def create_pre_alert_upload(
        self,
        *,
        actor: User,
        request: Request,
        platform: str,
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
        platform = self._validate_platform(platform)
        shipment_type = self._validate_shipment_type(shipment_type)
        air_waybill_number = self._validate_air_waybill_number(
            air_waybill_number,
            target_user,
        )
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

        upload = self.uploads.create(
            user_id=target_user.id,
            uploaded_by_user_id=actor.id,
            platform=platform,
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
                    "platform": platform,
                    "shipmentType": shipment_type,
                },
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            for saved_file in saved_files:
                Path(saved_file["storage_path"]).unlink(missing_ok=True)
            raise

        final_upload = await self._submit_to_platform(upload.id, request)
        return self._build_pre_alert_response(final_upload)

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
        removed_binding_count = 0
        if upload.platform_submission_status == "success":
            removed_binding_count = self.bindings.delete_for_user_number_source(
                user_id=upload.user_id,
                number=upload.air_waybill_number,
                source="pre_alert_upload",
            )

        self.audit_logs.create(
            "delete_waybill_upload",
            actor_user_id=actor.id,
            target_type="waybill_upload",
            target_id=str(upload.id),
            ip_address=get_request_ip(request),
            user_agent=get_request_user_agent(request),
            metadata={
                "platform": upload.platform,
                "airWaybillNumber": upload.air_waybill_number,
                "boundUserId": str(upload.user_id),
                "removedBinding": bool(removed_binding_count),
                "localOnly": True,
            },
        )
        self.uploads.delete(upload)
        self.db.commit()
        self._delete_upload_storage(upload_id, file_paths)
        return WaybillUploadDeleteResponse(
            status="deleted",
            upload_id=upload_id,
            removed_binding=bool(removed_binding_count),
        )

    def manual_submit(
        self,
        *,
        actor: User,
        upload_id: UUID,
        force: bool,
        request: Request,
    ) -> WaybillUploadItem:
        if actor.role != "admin":
            raise WaybillUploadPermissionError("Admin permission required")

        upload = self.uploads.get_by_id(upload_id)
        if upload is None:
            raise WaybillUploadValidationError("Waybill upload not found")
        if upload.platform_submission_status == "success" and not force:
            raise WaybillUploadValidationError(
                "Upload already succeeded; force=true is required"
            )

        existing_binding = self.bindings.get_any_binding(upload.air_waybill_number)
        if existing_binding is not None and existing_binding.user_id != upload.user_id:
            raise WaybillUploadValidationError(
                "This Air Waybill Number is already bound to another user"
            )

        upload = self.uploads.update_platform_submission(
            upload=upload,
            status="success",
            method="manual",
        )
        self.bindings.create_many(
            user_id=upload.user_id,
            numbers=[upload.air_waybill_number],
            created_by_user_id=actor.id,
            source="pre_alert_upload",
        )
        self.audit_logs.create(
            "manual_platform_upload_success",
            actor_user_id=actor.id,
            target_type="waybill_upload",
            target_id=str(upload.id),
            ip_address=get_request_ip(request),
            user_agent=get_request_user_agent(request),
            metadata={
                "platform": upload.platform,
                "airWaybillNumber": upload.air_waybill_number,
                "boundUserId": str(upload.user_id),
                "force": force,
            },
        )
        self.db.commit()
        refreshed_upload = self.uploads.get_by_id(upload.id)
        if refreshed_upload is None:
            raise WaybillUploadValidationError("Waybill upload not found")
        return WaybillUploadItem.model_validate(refreshed_upload)

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

    async def _submit_to_platform(
        self,
        upload_id: UUID,
        request: Request,
    ) -> WaybillUpload:
        upload = self.uploads.get_by_id(upload_id)
        if upload is None:
            raise WaybillUploadValidationError("Waybill upload not found")

        if upload.platform != "ALLINE":
            raise WaybillUploadValidationError("Platform is invalid")

        try:
            await AllineWaybillUploader(self.settings).submit_upload(upload)
            upload = self.uploads.update_platform_submission(
                upload=upload,
                status="success",
                method="automated",
            )
            self.bindings.create_many(
                user_id=upload.user_id,
                numbers=[upload.air_waybill_number],
                created_by_user_id=upload.uploaded_by_user_id,
                source="pre_alert_upload",
            )
            self.audit_logs.create(
                "platform_upload_success",
                actor_user_id=upload.uploaded_by_user_id,
                target_type="waybill_upload",
                target_id=str(upload.id),
                ip_address=get_request_ip(request),
                user_agent=get_request_user_agent(request),
                metadata={
                    "platform": upload.platform,
                    "airWaybillNumber": upload.air_waybill_number,
                },
            )
        except AllineWaybillUploadError as exc:
            error_message = self._sanitize_platform_error(str(exc))
            upload = self.uploads.update_platform_submission(
                upload=upload,
                status="failed",
                error_message=error_message,
                method="automated",
            )
            self.audit_logs.create(
                "platform_upload_failed",
                actor_user_id=upload.uploaded_by_user_id,
                target_type="waybill_upload",
                target_id=str(upload.id),
                ip_address=get_request_ip(request),
                user_agent=get_request_user_agent(request),
                metadata={
                    "platform": upload.platform,
                    "airWaybillNumber": upload.air_waybill_number,
                    "error": error_message,
                },
            )

        self.db.commit()
        refreshed_upload = self.uploads.get_by_id(upload_id)
        if refreshed_upload is None:
            raise WaybillUploadValidationError("Waybill upload not found")
        return refreshed_upload

    def _build_pre_alert_response(
        self,
        upload: WaybillUpload,
    ) -> WaybillPreAlertUploadResponse:
        return WaybillPreAlertUploadResponse(
            upload_id=upload.id,
            platform=upload.platform,
            air_waybill_number=upload.air_waybill_number,
            status=upload.status,
            platform_submission_status=upload.platform_submission_status,
            platform_submission_method=upload.platform_submission_method,
            platform_submission_error=upload.platform_submission_error,
            platform_submitted_at=upload.platform_submitted_at,
            bound_user_id=upload.user_id,
        )

    def _sanitize_platform_error(self, message: str) -> str:
        cleaned = message
        for secret in [self.settings.omniship_password, self.settings.omniship_username]:
            if secret:
                cleaned = cleaned.replace(secret, "[redacted]")
        return cleaned[:1000]

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

    def _validate_platform(self, value: str) -> str:
        platform = value.strip().upper()
        if platform not in UPLOAD_PLATFORMS:
            raise WaybillUploadValidationError("Platform is invalid")
        return platform

    def _validate_shipment_type(self, value: str) -> str:
        shipment_type = value.strip()
        if shipment_type not in SHIPMENT_TYPES:
            raise WaybillUploadValidationError("Shipment Type is invalid")
        return shipment_type

    def _validate_air_waybill_number(self, value: str, target_user: User) -> str:
        number = value.strip()
        if not number:
            raise WaybillUploadValidationError("Air Waybill Number is required")
        if not normalize_waybill_number(number):
            raise WaybillUploadValidationError("Air Waybill Number is invalid")
        if self.uploads.get_successful_by_normalized_number(number) is not None:
            raise WaybillUploadValidationError(
                "This Air Waybill Number has already been uploaded"
            )

        existing_binding = self.bindings.get_any_binding(number)
        if existing_binding is not None and existing_binding.user_id != target_user.id:
            raise WaybillUploadValidationError(
                "This Air Waybill Number is already bound to another user"
            )
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
