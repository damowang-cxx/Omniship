import hashlib
import random
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
from pathlib import Path
from uuid import UUID
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import Request, UploadFile
from sqlalchemy.orm import Session

from app.core.config import PROJECT_ROOT, Settings, get_settings
from app.db.models import BillingEntry, Invoice, InvoiceLine, InvoiceSettings, User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.invoice_repository import InvoiceRepository
from app.repositories.user_repository import UserRepository
from app.schemas.invoice import (
    InvoiceCreateRequest,
    InvoiceEligibleDeductionItem,
    InvoiceItem,
    InvoiceLineItem,
    InvoicePayerItem,
    InvoiceSettingsItem,
    InvoiceSettingsUpdateRequest,
)
from app.services.invoice_export_service import DETAIL_MAX_LINES, build_invoice_workbook
from app.services.request_context import get_request_ip, get_request_user_agent


STAMP_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
STAMP_MAX_BYTES = 10 * 1024 * 1024
STAMP_ANCHORS = ("A14", "B18", "A22", "B26", "A30", "B34")


class InvoiceValidationError(ValueError):
    pass


class InvoicePermissionError(PermissionError):
    pass


class InvoiceConflictError(InvoiceValidationError):
    pass


class InvoiceService:
    def __init__(self, db: Session, settings: Settings | None = None):
        self.db = db
        self.settings = settings or get_settings()
        self.invoices = InvoiceRepository(db)
        self.users = UserRepository(db)
        self.audit_logs = AuditLogRepository(db)

    def get_settings(self, *, actor: User) -> InvoiceSettingsItem:
        self._require_admin(actor)
        settings = self.invoices.get_settings()
        return InvoiceSettingsItem.model_validate(settings) if settings else InvoiceSettingsItem()

    async def update_settings(
        self, *, actor: User, payload: InvoiceSettingsUpdateRequest, stamp: UploadFile | None, request: Request
    ) -> InvoiceSettingsItem:
        self._require_admin(actor)
        settings = self.invoices.get_or_create_settings()
        field_map = {
            "issuerCompanyName": "issuer_company_name", "issuerAddressInfo": "issuer_address_info",
            "beneficiaryName": "beneficiary_name", "bankAccount": "bank_account",
            "bankNameAndCode": "bank_name_and_code", "branchCode": "branch_code",
            "swiftBic": "swift_bic", "bankAddress": "bank_address",
        }
        changed_fields = payload.model_dump(exclude_unset=True).keys()
        for field in changed_fields:
            value = getattr(payload, field)
            if value is not None:
                setattr(settings, field_map[field], value.strip())
        if stamp is not None and stamp.filename:
            stamp_data = await self._collect_stamp(stamp)
            path = self._save_stamp(stamp_data)
            settings.stamp_original_filename = stamp_data["original_filename"]
            settings.stamp_content_type = stamp_data["content_type"]
            settings.stamp_storage_path = str(path)
        settings.updated_by_user_id = actor.id
        self.audit_logs.create(
            "update_invoice_settings", actor_user_id=actor.id, target_type="invoice_settings", target_id="1",
            ip_address=get_request_ip(request), user_agent=get_request_user_agent(request),
            metadata={"fields": sorted(changed_fields), "stampUploaded": stamp is not None and bool(stamp.filename)},
        )
        self.db.commit()
        self.db.refresh(settings)
        return InvoiceSettingsItem.model_validate(settings)

    def list_eligible(self, *, actor: User, user_id: UUID) -> list[InvoiceEligibleDeductionItem]:
        self._assert_access(actor, user_id)
        entries = self._list_user_entries(user_id)
        active_ids = self.invoices.active_invoice_entry_ids([entry.id for entry in entries])
        reversed_ids = {
            entry.reversal_of_entry_id
            for entry in entries
            if entry.entry_type == "deduction_reversal" and entry.reversal_of_entry_id is not None
        }
        return [
            InvoiceEligibleDeductionItem(
                id=entry.id, waybill_number=entry.waybill_number or "-", quantity=entry.billable_unit_count or 0,
                unit_rate=entry.unit_rate or Decimal("0.00"), amount=entry.amount, recorded_at=entry.created_at,
            )
            for entry in entries
            if entry.id not in active_ids and entry.id not in reversed_ids and self._is_eligible_entry(entry)
        ]

    def list_invoices(self, *, actor: User, user_id: UUID) -> list[InvoiceItem]:
        self._assert_access(actor, user_id)
        return [self._item(invoice) for invoice in self.invoices.list_invoices(user_id)]

    def get_invoice(self, *, actor: User, user_id: UUID, invoice_id: UUID) -> InvoiceItem:
        invoice = self._get_authorized_invoice(actor, user_id, invoice_id)
        return self._item(invoice)

    def create_invoices(
        self, *, actor: User, user_id: UUID, payload: InvoiceCreateRequest, request: Request
    ) -> list[InvoiceItem]:
        self._assert_access(actor, user_id)
        user = self.users.get_by_id(user_id)
        if user is None:
            raise InvoiceValidationError("User not found")
        if not user.payer_company_name or not user.payer_address_info:
            raise InvoiceValidationError("Payer information must be configured before invoicing")
        settings = self.invoices.get_settings()
        if not self._settings_complete(settings):
            raise InvoiceValidationError("Invoice settings and stamp image must be configured before invoicing")

        selected = self.invoices.get_entries_for_update(user_id, payload.deductionIds)
        if len(selected) != len(payload.deductionIds):
            raise InvoiceValidationError("One or more selected deductions were not found")
        active_ids = self.invoices.active_invoice_entry_ids([entry.id for entry in selected])
        reversed_ids = {
            entry.reversal_of_entry_id
            for entry in self._list_user_entries(user_id)
            if entry.entry_type == "deduction_reversal" and entry.reversal_of_entry_id is not None
        }
        invalid = [
            entry for entry in selected
            if not self._is_eligible_entry(entry) or entry.id in active_ids or entry.id in reversed_ids
        ]
        if invalid:
            raise InvoiceConflictError("One or more selected deductions are no longer available for invoicing")

        ordered = sorted(selected, key=lambda entry: (entry.created_at, str(entry.id)))
        payer_snapshot = {"companyName": user.payer_company_name, "addressInfo": user.payer_address_info}
        issuer_snapshot = self._issuer_snapshot(settings)
        created: list[Invoice] = []
        try:
            for start in range(0, len(ordered), DETAIL_MAX_LINES):
                lines = ordered[start : start + DETAIL_MAX_LINES]
                total = sum((Decimal(line.amount) for line in lines), Decimal("0.00")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                invoice = Invoice(
                    user_id=user.id,
                    invoice_number=self.invoices.next_number(payload.issuedDate),
                    status="issued",
                    issued_date=payload.issuedDate,
                    due_date=payload.issuedDate + timedelta(days=4),
                    total_amount=total,
                    payer_snapshot=payer_snapshot,
                    issuer_snapshot=issuer_snapshot,
                    stamp_storage_path=settings.stamp_storage_path,
                    stamp_position=self._stamp_position(),
                    created_by_user_id=actor.id,
                )
                self.db.add(invoice)
                self.db.flush()
                for line_number, entry in enumerate(lines, start=1):
                    self.db.add(InvoiceLine(
                        invoice_id=invoice.id, billing_entry_id=entry.id, line_number=line_number,
                        waybill_number=entry.waybill_number or "-", quantity=entry.billable_unit_count or 0,
                        unit_rate=entry.unit_rate or Decimal("0.00"), amount=entry.amount,
                    ))
                created.append(invoice)
            self.db.flush()
            self.audit_logs.create(
                "create_invoices", actor_user_id=actor.id, target_type="user", target_id=str(user.id),
                ip_address=get_request_ip(request), user_agent=get_request_user_agent(request),
                metadata={"invoiceNumbers": [item.invoice_number for item in created], "deductionCount": len(selected)},
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return [self._item(self.invoices.get_invoice(invoice.id)) for invoice in created]

    def void_invoice(self, *, actor: User, user_id: UUID, invoice_id: UUID, reason: str, request: Request) -> InvoiceItem:
        self._require_admin(actor)
        invoice = self.invoices.get_invoice_for_update(invoice_id)
        if invoice is None or invoice.user_id != user_id:
            raise InvoiceValidationError("Invoice not found")
        if invoice.status != "issued":
            raise InvoiceConflictError("Invoice has already been voided")
        invoice.status = "voided"
        invoice.void_reason = reason.strip()
        invoice.voided_at = datetime.now(timezone.utc)
        invoice.voided_by_user_id = actor.id
        self.audit_logs.create(
            "void_invoice", actor_user_id=actor.id, target_type="invoice", target_id=str(invoice.id),
            ip_address=get_request_ip(request), user_agent=get_request_user_agent(request), metadata={"reason": invoice.void_reason},
        )
        self.db.commit()
        return self._item(invoice)

    def export_invoice(self, *, actor: User, user_id: UUID, invoice_id: UUID, request: Request) -> tuple[bytes, str]:
        invoice = self._get_authorized_invoice(actor, user_id, invoice_id)
        self.audit_logs.create(
            "download_invoice_excel", actor_user_id=actor.id, target_type="invoice", target_id=str(invoice.id),
            ip_address=get_request_ip(request), user_agent=get_request_user_agent(request),
        )
        self.db.commit()
        return build_invoice_workbook(invoice), f"{invoice.invoice_number}.xlsx"

    def export_invoice_batch(self, *, actor: User, user_id: UUID, invoice_ids: list[UUID], request: Request) -> tuple[bytes, str]:
        if not invoice_ids:
            raise InvoiceValidationError("At least one invoice is required")
        invoices = [self._get_authorized_invoice(actor, user_id, invoice_id) for invoice_id in invoice_ids]
        if len(invoices) == 1:
            content, filename = self.export_invoice(actor=actor, user_id=user_id, invoice_id=invoice_ids[0], request=request)
            return content, filename
        output = BytesIO()
        with ZipFile(output, "w", ZIP_DEFLATED) as archive:
            for invoice in invoices:
                archive.writestr(f"{invoice.invoice_number}.xlsx", build_invoice_workbook(invoice))
        self.audit_logs.create(
            "download_invoice_zip", actor_user_id=actor.id, target_type="user", target_id=str(user_id),
            ip_address=get_request_ip(request), user_agent=get_request_user_agent(request), metadata={"invoiceCount": len(invoices)},
        )
        self.db.commit()
        return output.getvalue(), f"invoices-{date.today():%Y%m%d}.zip"

    def _list_user_entries(self, user_id: UUID) -> list[BillingEntry]:
        from sqlalchemy import select
        statement = select(BillingEntry).where(BillingEntry.user_id == user_id).order_by(BillingEntry.created_at.asc(), BillingEntry.id.asc())
        return list(self.db.execute(statement).scalars().all())

    def _get_authorized_invoice(self, actor: User, user_id: UUID, invoice_id: UUID) -> Invoice:
        self._assert_access(actor, user_id)
        invoice = self.invoices.get_invoice(invoice_id)
        if invoice is None or invoice.user_id != user_id:
            raise InvoiceValidationError("Invoice not found")
        return invoice

    def _assert_access(self, actor: User, user_id: UUID) -> None:
        if actor.id != user_id and actor.role != "admin":
            raise InvoicePermissionError("Cannot access another user's invoices")

    def _require_admin(self, actor: User) -> None:
        if actor.role != "admin":
            raise InvoicePermissionError("Admin permission required")

    @staticmethod
    def _is_eligible_entry(entry: BillingEntry) -> bool:
        return entry.entry_type == "deduction" and entry.billable_unit_count is not None and entry.unit_rate is not None

    @staticmethod
    def _settings_complete(settings: InvoiceSettings | None) -> bool:
        return bool(settings and settings.stamp_storage_path and all(getattr(settings, field) for field in (
            "issuer_company_name", "issuer_address_info", "beneficiary_name", "bank_account",
            "bank_name_and_code", "branch_code", "swift_bic", "bank_address",
        )))

    @staticmethod
    def _issuer_snapshot(settings: InvoiceSettings) -> dict:
        return {
            "issuerCompanyName": settings.issuer_company_name,
            "issuerAddressInfo": settings.issuer_address_info,
            "beneficiaryName": settings.beneficiary_name,
            "bankAccount": settings.bank_account,
            "bankNameAndCode": settings.bank_name_and_code,
            "branchCode": settings.branch_code,
            "swiftBic": settings.swift_bic,
            "bankAddress": settings.bank_address,
        }

    @staticmethod
    def _stamp_position() -> dict:
        return {"anchor": random.choice(STAMP_ANCHORS), "width": 86, "height": 86}

    def _item(self, invoice: Invoice | None) -> InvoiceItem:
        if invoice is None:
            raise InvoiceValidationError("Invoice not found")
        return InvoiceItem(
            id=invoice.id, invoice_number=invoice.invoice_number, status=invoice.status,
            issued_date=invoice.issued_date, due_date=invoice.due_date, total_amount=invoice.total_amount,
            payer=InvoicePayerItem(**invoice.payer_snapshot),
            lines=[InvoiceLineItem(
                id=line.id, billing_entry_id=line.billing_entry_id, line_number=line.line_number,
                waybill_number=line.waybill_number, quantity=line.quantity, unit_rate=line.unit_rate, amount=line.amount,
            ) for line in invoice.lines],
            created_at=invoice.created_at, voided_at=invoice.voided_at, void_reason=invoice.void_reason,
        )

    async def _collect_stamp(self, stamp: UploadFile) -> dict:
        filename = Path(stamp.filename or "").name
        extension = Path(filename).suffix.lower()
        if extension not in STAMP_EXTENSIONS:
            raise InvoiceValidationError("Stamp must be a JPG, PNG, or WebP image")
        content = await stamp.read()
        if not content or len(content) > STAMP_MAX_BYTES:
            raise InvoiceValidationError("Stamp image must be smaller than 10 MB")
        try:
            from PIL import Image, UnidentifiedImageError
        except ImportError as exc:
            raise InvoiceValidationError("Image processing support is unavailable") from exc
        try:
            with Image.open(BytesIO(content)) as image:
                image.verify()
        except (UnidentifiedImageError, OSError):
            raise InvoiceValidationError("Stamp file content is not a valid image")
        return {"original_filename": filename, "extension": ".jpg" if extension == ".jpeg" else extension, "content_type": stamp.content_type, "content": content}

    def _save_stamp(self, payload: dict) -> Path:
        root = self.settings.invoice_stamp_storage_dir
        if not root.is_absolute():
            root = PROJECT_ROOT / root
        root.mkdir(parents=True, exist_ok=True)
        # Normalize every uploaded seal to a semi-transparent PNG. The stored file
        # becomes the immutable image used by all invoices created under this setup.
        path = root / f"{uuid.uuid4().hex}.png"
        from PIL import Image
        with Image.open(BytesIO(payload["content"])) as image:
            rgba = image.convert("RGBA")
            alpha = rgba.getchannel("A").point(lambda value: value * 110 // 255)
            rgba.putalpha(alpha)
            rgba.save(path, "PNG")
        return path
