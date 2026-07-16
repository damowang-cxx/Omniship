import hashlib
import logging
import re
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from uuid import UUID

from fastapi import Request, UploadFile
from sqlalchemy.orm import Session

from app.core.config import PROJECT_ROOT, Settings, get_settings
from app.db.models import BillingEntry, User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.billing_repository import BillingRepository
from app.repositories.supplier_repository import SupplierRepository
from app.repositories.user_repository import UserRepository
from app.repositories.waybill_upload_repository import WaybillUploadRepository
from app.schemas.billing import (
    BillingAccountResponse,
    BillingEntryItem,
    BillingReceiptItem,
    BillingTaxEstimateResponse,
    RetroactiveBillingFailureItem,
    RetroactiveBillingResponse,
    RetroactiveBillingSuccessItem,
)
from app.schemas.supplier import SupplierVersionConfig
from app.schemas.user import UserPublic
from app.services.request_context import get_request_ip, get_request_user_agent
from app.services.supplier_rule_engine import SupplierRuleEngine, SupplierStructureError


RECEIPT_MAX_BYTES = 10 * 1024 * 1024
RECEIPT_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ESTIMATE_MAX_BYTES = 25 * 1024 * 1024

logger = logging.getLogger(__name__)


class BillingValidationError(ValueError):
    pass


class BillingPermissionError(PermissionError):
    pass


class BillingService:
    def __init__(self, db: Session, settings: Settings | None = None):
        self.db = db
        self.settings = settings or get_settings()
        self.billing = BillingRepository(db)
        self.users = UserRepository(db)
        self.suppliers = SupplierRepository(db)
        self.uploads = WaybillUploadRepository(db)
        self.audit_logs = AuditLogRepository(db)

    def get_account(self, *, actor: User, user_id: UUID | None = None) -> BillingAccountResponse:
        target_user_id = user_id or actor.id
        if target_user_id != actor.id and actor.role != "admin":
            raise BillingPermissionError("Cannot view another user's billing account")

        user = self.users.get_by_id(target_user_id)
        if user is None:
            raise BillingValidationError("User not found")
        entries = self.billing.list_for_user(user.id)
        deductions = [self._build_entry(entry) for entry in entries if entry.entry_type == "deduction"]
        recharges = [self._build_entry(entry) for entry in entries if entry.entry_type == "recharge"]
        return BillingAccountResponse(
            user=UserPublic.model_validate(user),
            deductions=deductions,
            recharges=recharges,
        )

    async def recharge(
        self,
        *,
        actor: User,
        user_id: UUID,
        amount: str,
        receipt: UploadFile | None,
        request: Request,
    ) -> BillingAccountResponse:
        if actor.role != "admin":
            raise BillingPermissionError("Admin permission required")
        recharge_amount = self._parse_amount(amount)
        user = self.billing.get_user_for_update(user_id)
        if user is None:
            raise BillingValidationError("User not found")

        receipt_payload = await self._collect_receipt(receipt)
        user.balance = (Decimal(user.balance) + recharge_amount).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        entry = self.billing.create_recharge(
            user_id=user.id,
            amount=recharge_amount,
            balance_after=user.balance,
            created_by_user_id=actor.id,
        )

        saved_path: Path | None = None
        try:
            if receipt_payload is not None:
                saved_path = self._save_receipt(user.id, entry.id, receipt_payload)
                entry.receipt_original_filename = receipt_payload["original_filename"]
                entry.receipt_storage_path = str(saved_path)
                entry.receipt_content_type = receipt_payload["content_type"]
                entry.receipt_size_bytes = receipt_payload["size_bytes"]
                entry.receipt_sha256 = receipt_payload["sha256"]

            self.audit_logs.create(
                "recharge_user",
                actor_user_id=actor.id,
                target_type="user",
                target_id=str(user.id),
                ip_address=get_request_ip(request),
                user_agent=get_request_user_agent(request),
                metadata={
                    "amount": str(recharge_amount),
                    "currency": "EUR",
                    "balanceAfter": str(user.balance),
                    "receiptUploaded": receipt_payload is not None,
                },
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            if saved_path is not None:
                saved_path.unlink(missing_ok=True)
            raise

        return self.get_account(actor=actor, user_id=user.id)

    async def estimate_tax(
        self,
        *,
        pre_alert_file: UploadFile,
        supplier_id: UUID,
        airport_of_arrival: str,
    ) -> BillingTaxEstimateResponse:
        if not pre_alert_file.filename:
            raise BillingValidationError("Upload Pre Alert File is required")
        airport = airport_of_arrival.strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", airport):
            raise BillingValidationError("Airport of Arrival must be a three-letter IATA code")
        supplier = self.suppliers.get(supplier_id)
        if supplier is None:
            raise BillingValidationError("Supplier not found")
        if supplier.status != "active":
            raise BillingValidationError("Supplier is inactive")
        version = self.suppliers.get_current_version(supplier)
        if version is None:
            raise BillingValidationError("Supplier version not found")
        content = await pre_alert_file.read()
        if len(content) > ESTIMATE_MAX_BYTES:
            raise BillingValidationError("Upload Pre Alert File exceeds the 25 MB estimate limit")
        try:
            evaluation = SupplierRuleEngine().evaluate(
                filename=Path(pre_alert_file.filename).name,
                content=content,
                config=SupplierVersionConfig.model_validate(version.config),
            )
        except SupplierStructureError as exc:
            raise BillingValidationError(str(exc)) from exc
        settings = self.suppliers.get_settings()
        taxable = airport in settings.taxable_airports
        unit_rate = Decimal(settings.unit_tax_eur)
        estimated_tax = (
            unit_rate * evaluation.distinct_count if taxable else Decimal("0.00")
        ).quantize(Decimal("0.01"))
        return BillingTaxEstimateResponse(
            supplier_id=supplier.id,
            supplier_name=supplier.name,
            supplier_version_id=version.id,
            supplier_version_number=version.version_number,
            taxable_airport=taxable,
            billable_unit_count=evaluation.distinct_count,
            unit_rate=unit_rate,
            estimated_tax=estimated_tax,
            warning_count=evaluation.issue_count,
            warnings=[issue.as_dict() for issue in evaluation.issues[:5]],
            currency="EUR",
        )

    def apply_retroactive_billing(
        self,
        *,
        actor: User,
        waybill_numbers: list[str],
        request: Request,
    ) -> RetroactiveBillingResponse:
        if actor.role != "admin":
            raise BillingPermissionError("Admin permission required")

        settings = self.suppliers.get_settings()
        unit_rate = Decimal(settings.unit_tax_eur)
        taxable_airports = set(settings.taxable_airports)
        effective_date = settings.tax_effective_date
        candidates = []
        for supplier in self.suppliers.list(include_inactive=False):
            version = self.suppliers.get_current_version(supplier)
            if version is not None:
                candidates.append(
                    (
                        supplier.id,
                        supplier.name,
                        version.id,
                        version.version_number,
                        SupplierVersionConfig.model_validate(version.config),
                    )
                )

        succeeded: list[RetroactiveBillingSuccessItem] = []
        failed: list[RetroactiveBillingFailureItem] = []
        for number in waybill_numbers:
            try:
                item = self._apply_one_retroactive_deduction(
                    actor=actor,
                    requested_number=number,
                    request=request,
                    unit_rate=unit_rate,
                    taxable_airports=taxable_airports,
                    effective_date=effective_date,
                    candidates=candidates,
                )
                self.db.commit()
                succeeded.append(item)
            except BillingValidationError as exc:
                self.db.rollback()
                failed.append(
                    RetroactiveBillingFailureItem(
                        waybill_number=number,
                        reason=str(exc),
                    )
                )
            except Exception:
                self.db.rollback()
                logger.exception("Retroactive billing failed for waybill %s", number)
                failed.append(
                    RetroactiveBillingFailureItem(
                        waybill_number=number,
                        reason="Unexpected processing error",
                    )
                )

        return RetroactiveBillingResponse(
            requested_count=len(waybill_numbers),
            succeeded_count=len(succeeded),
            failed_count=len(failed),
            succeeded=succeeded,
            failed=failed,
        )

    def _apply_one_retroactive_deduction(
        self,
        *,
        actor: User,
        requested_number: str,
        request: Request,
        unit_rate: Decimal,
        taxable_airports: set[str],
        effective_date: date,
        candidates: list[tuple[UUID, str, UUID, int, SupplierVersionConfig]],
    ) -> RetroactiveBillingSuccessItem:
        matches = self.uploads.find_for_retroactive_billing(requested_number)
        if not matches:
            raise BillingValidationError("Waybill upload was not found")
        if len(matches) > 1:
            raise BillingValidationError("Multiple uploads use this waybill number")
        upload = matches[0]
        if upload.status != "approved":
            raise BillingValidationError("Waybill is not approved")
        if upload.created_at.date() < effective_date:
            raise BillingValidationError(
                f"Waybill predates the tax effective date {effective_date.isoformat()}"
            )
        if self.billing.get_deduction_for_upload(upload.id) is not None:
            raise BillingValidationError("Customs tax has already been recorded")

        airport = (upload.airport_of_arrival or "").strip().upper()
        if airport not in taxable_airports:
            raise BillingValidationError("Arrival airport is not taxable")
        pre_alert = next(
            (item for item in upload.files if item.file_kind == "customer_pre_alert"),
            None,
        )
        if pre_alert is None:
            raise BillingValidationError("Upload Pre Alert File was not found")
        path = Path(pre_alert.storage_path)
        if not path.is_file():
            raise BillingValidationError("Upload Pre Alert File is missing")
        content = path.read_bytes()

        selected = None
        structure_errors = []
        for supplier_id, supplier_name, version_id, version_number, config in candidates:
            try:
                evaluation = SupplierRuleEngine().evaluate(
                    filename=pre_alert.original_filename,
                    content=content,
                    config=config,
                )
                selected = (
                    supplier_id,
                    supplier_name,
                    version_id,
                    version_number,
                    evaluation,
                )
                break
            except SupplierStructureError as exc:
                structure_errors.append(f"{supplier_name}: {exc}")
        if selected is None:
            summary = "; ".join(structure_errors[:3])
            raise BillingValidationError(
                f"No active supplier format recognized the Pre Alert File{': ' + summary if summary else ''}"
            )

        supplier_id, supplier_name, version_id, version_number, evaluation = selected
        amount = (unit_rate * evaluation.distinct_count).quantize(Decimal("0.01"))
        if amount <= 0:
            raise BillingValidationError("Calculated customs tax is zero")

        user = self.billing.get_user_for_update(upload.user_id)
        if user is None:
            raise BillingValidationError("Waybill owner was not found")
        user.balance = (Decimal(user.balance) - amount).quantize(Decimal("0.01"))
        upload.supplier_id = supplier_id
        upload.supplier_version_id = version_id
        upload.validation_issue_count = evaluation.issue_count
        upload.validation_issues = [issue.as_dict() for issue in evaluation.issues]
        self.billing.create_deduction(
            user_id=user.id,
            amount=amount,
            balance_after=user.balance,
            waybill_upload_id=upload.id,
            waybill_number=upload.air_waybill_number,
            supplier_id=supplier_id,
            supplier_name=supplier_name,
            supplier_version_number=version_number,
            arrival_airport=airport,
            billable_unit_count=evaluation.distinct_count,
            unit_rate=unit_rate,
            created_by_user_id=actor.id,
            billing_source="retroactive",
        )
        self.audit_logs.create(
            "retroactive_customs_deduction",
            actor_user_id=actor.id,
            target_type="waybill_upload",
            target_id=str(upload.id),
            ip_address=get_request_ip(request),
            user_agent=get_request_user_agent(request),
            metadata={
                "waybillNumber": upload.air_waybill_number,
                "supplierName": supplier_name,
                "supplierVersion": version_number,
                "billableUnitCount": evaluation.distinct_count,
                "unitRate": str(unit_rate),
                "amount": str(amount),
                "balanceAfter": str(user.balance),
            },
        )
        return RetroactiveBillingSuccessItem(
            waybill_number=upload.air_waybill_number,
            supplier_name=supplier_name,
            supplier_version_number=version_number,
            billable_unit_count=evaluation.distinct_count,
            unit_rate=unit_rate,
            amount=amount,
            balance_after=user.balance,
            warning_count=evaluation.issue_count,
        )

    def get_receipt(
        self,
        *,
        actor: User,
        user_id: UUID,
        entry_id: UUID,
        request: Request,
    ) -> BillingEntry:
        if actor.role != "admin":
            raise BillingPermissionError("Admin permission required")
        entry = self.billing.get_entry(entry_id)
        if entry is None or entry.user_id != user_id or entry.entry_type != "recharge":
            raise BillingValidationError("Recharge record not found")
        if not entry.receipt_storage_path or not Path(entry.receipt_storage_path).is_file():
            raise BillingValidationError("Receipt image not found")

        self.audit_logs.create(
            "download_recharge_receipt",
            actor_user_id=actor.id,
            target_type="billing_entry",
            target_id=str(entry.id),
            ip_address=get_request_ip(request),
            user_agent=get_request_user_agent(request),
            metadata={"userId": str(user_id)},
        )
        self.db.commit()
        return entry

    def _parse_amount(self, value: str) -> Decimal:
        try:
            amount = Decimal(value.strip()).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        except (InvalidOperation, AttributeError):
            raise BillingValidationError("Recharge amount must be a valid number")
        if amount <= 0:
            raise BillingValidationError("Recharge amount must be greater than zero")
        if amount > Decimal("9999999999.99"):
            raise BillingValidationError("Recharge amount exceeds the account limit")
        return amount

    async def _collect_receipt(self, receipt: UploadFile | None) -> dict | None:
        if receipt is None or not receipt.filename:
            return None
        filename = Path(receipt.filename).name
        extension = Path(filename).suffix.lower()
        if extension not in RECEIPT_EXTENSIONS:
            raise BillingValidationError("Receipt must be a JPG, PNG, or WebP image")
        content = await receipt.read()
        if not content:
            raise BillingValidationError("Receipt image is empty")
        if len(content) > RECEIPT_MAX_BYTES:
            raise BillingValidationError("Receipt image must be smaller than 10 MB")
        if not self._matches_image_signature(extension, content):
            raise BillingValidationError("Receipt file content is not a valid image")
        return {
            "original_filename": filename,
            "extension": ".jpg" if extension == ".jpeg" else extension,
            "content_type": receipt.content_type,
            "content": content,
            "size_bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }

    def _save_receipt(self, user_id: UUID, entry_id: UUID, payload: dict) -> Path:
        storage_root = self.settings.billing_receipt_storage_dir
        if not storage_root.is_absolute():
            storage_root = PROJECT_ROOT / storage_root
        receipt_dir = storage_root / str(user_id) / str(entry_id)
        receipt_dir.mkdir(parents=True, exist_ok=True)
        path = receipt_dir / f"{uuid.uuid4().hex}{payload['extension']}"
        path.write_bytes(payload["content"])
        return path

    def _matches_image_signature(self, extension: str, content: bytes) -> bool:
        if extension in {".jpg", ".jpeg"}:
            return content.startswith(b"\xff\xd8\xff")
        if extension == ".png":
            return content.startswith(b"\x89PNG\r\n\x1a\n")
        if extension == ".webp":
            return len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP"
        return False

    def _build_entry(self, entry: BillingEntry) -> BillingEntryItem:
        receipt = None
        if (
            entry.receipt_original_filename
            and entry.receipt_size_bytes is not None
        ):
            receipt = BillingReceiptItem(
                original_filename=entry.receipt_original_filename,
                content_type=entry.receipt_content_type,
                size_bytes=entry.receipt_size_bytes,
            )
        return BillingEntryItem(
            id=entry.id,
            entry_type=entry.entry_type,
            amount=entry.amount,
            currency=entry.currency,
            balance_after=entry.balance_after,
            waybill_upload_id=entry.waybill_upload_id,
            waybill_number=entry.waybill_number,
            supplier_id=entry.supplier_id,
            supplier_name=entry.supplier_name,
            supplier_version_number=entry.supplier_version_number,
            arrival_airport=entry.arrival_airport,
            billable_unit_count=entry.billable_unit_count,
            unit_rate=entry.unit_rate,
            billing_source=entry.billing_source,
            created_by_user_id=entry.created_by_user_id,
            receipt=receipt,
            created_at=entry.created_at,
        )
