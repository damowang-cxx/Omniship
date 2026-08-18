from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, require_admin
from app.db.models import User
from app.db.session import get_db
from app.schemas.billing import (
    BillingAccountResponse,
    BillingTaxEstimateResponse,
    RetroactiveBillingRequest,
    RetroactiveBillingResponse,
)
from app.schemas.supplier import BillingSettingsItem, BillingSettingsUpdateRequest
from app.schemas.invoice import (
    InvoiceCreateRequest,
    InvoiceCreateResponse,
    InvoiceEligibleDeductionItem,
    InvoiceItem,
    InvoiceSettingsItem,
    InvoiceSettingsUpdateRequest,
    InvoiceVoidRequest,
)
from app.services.invoice_service import (
    InvoiceConflictError,
    InvoicePermissionError,
    InvoiceService,
    InvoiceValidationError,
)
from app.services.billing_service import (
    BillingConflictError,
    BillingPermissionError,
    BillingService,
    BillingValidationError,
)
from app.services.supplier_service import SupplierService


router = APIRouter(prefix="/api/v1/billing", tags=["billing"])


def _billing_error(exc: Exception) -> HTTPException:
    if isinstance(exc, BillingPermissionError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, BillingConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    code = (
        status.HTTP_404_NOT_FOUND
        if str(exc)
        in {
            "User not found",
            "Recharge record not found",
            "Receipt image not found",
            "Deduction record not found",
        }
        else status.HTTP_400_BAD_REQUEST
    )
    return HTTPException(status_code=code, detail=str(exc))


def _invoice_error(exc: Exception) -> HTTPException:
    if isinstance(exc, InvoicePermissionError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, InvoiceConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND if str(exc) in {"User not found", "Invoice not found"} else status.HTTP_400_BAD_REQUEST,
        detail=str(exc),
    )


@router.get("/me", response_model=BillingAccountResponse)
def get_my_billing_account(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BillingAccountResponse:
    return BillingService(db).get_account(actor=current_user)


@router.get("/me/export")
def export_my_billing_account(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    content, filename = BillingService(db).export_account(
        actor=current_user,
        request=request,
    )
    return Response(
        content=content,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/users/{user_id}", response_model=BillingAccountResponse)
def get_user_billing_account(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> BillingAccountResponse:
    try:
        return BillingService(db).get_account(actor=current_user, user_id=user_id)
    except (BillingPermissionError, BillingValidationError) as exc:
        raise _billing_error(exc) from exc


@router.get("/users/{user_id}/export")
def export_user_billing_account(
    user_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Response:
    try:
        content, filename = BillingService(db).export_account(
            actor=current_user,
            request=request,
            user_id=user_id,
        )
    except (BillingPermissionError, BillingValidationError) as exc:
        raise _billing_error(exc) from exc
    return Response(
        content=content,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/users/{user_id}/recharges", response_model=BillingAccountResponse)
async def recharge_user(
    user_id: UUID,
    request: Request,
    amount: str = Form(...),
    receipt: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> BillingAccountResponse:
    try:
        return await BillingService(db).recharge(
            actor=current_user,
            user_id=user_id,
            amount=amount,
            receipt=receipt,
            request=request,
        )
    except (BillingPermissionError, BillingValidationError) as exc:
        raise _billing_error(exc) from exc


@router.post(
    "/users/{user_id}/recharges/{entry_id}/cancel",
    response_model=BillingAccountResponse,
)
def cancel_recharge(
    user_id: UUID,
    entry_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> BillingAccountResponse:
    try:
        return BillingService(db).cancel_recharge(
            actor=current_user,
            user_id=user_id,
            entry_id=entry_id,
            request=request,
        )
    except (BillingPermissionError, BillingValidationError) as exc:
        raise _billing_error(exc) from exc


@router.post(
    "/users/{user_id}/deductions/{entry_id}/cancel",
    response_model=BillingAccountResponse,
)
def cancel_customs_tax(
    user_id: UUID,
    entry_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> BillingAccountResponse:
    try:
        return BillingService(db).cancel_deduction(
            actor=current_user,
            user_id=user_id,
            entry_id=entry_id,
            request=request,
        )
    except (BillingPermissionError, BillingValidationError) as exc:
        raise _billing_error(exc) from exc


@router.get("/users/{user_id}/recharges/{entry_id}/receipt")
def get_recharge_receipt(
    user_id: UUID,
    entry_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> FileResponse:
    try:
        entry = BillingService(db).get_receipt(
            actor=current_user,
            user_id=user_id,
            entry_id=entry_id,
            request=request,
        )
    except (BillingPermissionError, BillingValidationError) as exc:
        raise _billing_error(exc) from exc
    return FileResponse(
        path=entry.receipt_storage_path,
        media_type=entry.receipt_content_type or "application/octet-stream",
    )


@router.post("/estimate", response_model=BillingTaxEstimateResponse)
async def estimate_pre_alert_tax(
    pre_alert_file: UploadFile = File(..., alias="preAlertFile"),
    supplier_id: UUID = Form(..., alias="supplierId"),
    airport_of_arrival: str = Form(..., alias="airportOfArrival"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> BillingTaxEstimateResponse:
    try:
        return await BillingService(db).estimate_tax(
            pre_alert_file=pre_alert_file,
            supplier_id=supplier_id,
            airport_of_arrival=airport_of_arrival,
        )
    except BillingValidationError as exc:
        raise _billing_error(exc) from exc


@router.get("/settings", response_model=BillingSettingsItem)
def get_billing_settings(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> BillingSettingsItem:
    return SupplierService(db).get_settings()


@router.post("/retroactive", response_model=RetroactiveBillingResponse)
def apply_retroactive_billing(
    payload: RetroactiveBillingRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> RetroactiveBillingResponse:
    try:
        return BillingService(db).apply_retroactive_billing(
            actor=current_user,
            waybill_numbers=payload.waybillNumbers,
            request=request,
        )
    except (BillingPermissionError, BillingValidationError) as exc:
        raise _billing_error(exc) from exc


@router.patch("/settings", response_model=BillingSettingsItem)
def update_billing_settings(
    payload: BillingSettingsUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> BillingSettingsItem:
    return SupplierService(db).update_settings(
        actor=current_user,
        payload=payload,
        request=request,
    )


@router.get("/invoice-settings", response_model=InvoiceSettingsItem)
def get_invoice_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> InvoiceSettingsItem:
    return InvoiceService(db).get_settings(actor=current_user)


@router.patch("/invoice-settings", response_model=InvoiceSettingsItem)
async def update_invoice_settings(
    request: Request,
    payload: InvoiceSettingsUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> InvoiceSettingsItem:
    try:
        return await InvoiceService(db).update_settings(
            actor=current_user, payload=payload, stamp=None, request=request
        )
    except (InvoicePermissionError, InvoiceValidationError) as exc:
        raise _invoice_error(exc) from exc


@router.post("/invoice-settings/stamp", response_model=InvoiceSettingsItem)
async def update_invoice_stamp(
    request: Request,
    stamp: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> InvoiceSettingsItem:
    try:
        return await InvoiceService(db).update_settings(
            actor=current_user,
            payload=InvoiceSettingsUpdateRequest.model_construct(),
            stamp=stamp,
            request=request,
        )
    except (InvoicePermissionError, InvoiceValidationError) as exc:
        raise _invoice_error(exc) from exc


def _invoice_download_response(content: bytes, filename: str) -> Response:
    media_type = "application/zip" if filename.endswith(".zip") else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return Response(content=content, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/me/invoices/eligible", response_model=list[InvoiceEligibleDeductionItem])
def get_my_invoiceable_deductions(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[InvoiceEligibleDeductionItem]:
    return InvoiceService(db).list_eligible(actor=current_user, user_id=current_user.id)


@router.get("/users/{user_id}/invoices/eligible", response_model=list[InvoiceEligibleDeductionItem])
def get_user_invoiceable_deductions(
    user_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(require_admin)
) -> list[InvoiceEligibleDeductionItem]:
    return InvoiceService(db).list_eligible(actor=current_user, user_id=user_id)


@router.get("/me/invoices", response_model=list[InvoiceItem])
def list_my_invoices(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[InvoiceItem]:
    return InvoiceService(db).list_invoices(actor=current_user, user_id=current_user.id)


@router.get("/users/{user_id}/invoices", response_model=list[InvoiceItem])
def list_user_invoices(
    user_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(require_admin)
) -> list[InvoiceItem]:
    return InvoiceService(db).list_invoices(actor=current_user, user_id=user_id)


@router.post("/me/invoices", response_model=InvoiceCreateResponse, status_code=status.HTTP_201_CREATED)
def create_my_invoices(
    payload: InvoiceCreateRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> InvoiceCreateResponse:
    try:
        return InvoiceCreateResponse(invoices=InvoiceService(db).create_invoices(actor=current_user, user_id=current_user.id, payload=payload, request=request))
    except (InvoicePermissionError, InvoiceValidationError) as exc:
        raise _invoice_error(exc) from exc


@router.post("/users/{user_id}/invoices", response_model=InvoiceCreateResponse, status_code=status.HTTP_201_CREATED)
def create_user_invoices(
    user_id: UUID, payload: InvoiceCreateRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_admin)
) -> InvoiceCreateResponse:
    try:
        return InvoiceCreateResponse(invoices=InvoiceService(db).create_invoices(actor=current_user, user_id=user_id, payload=payload, request=request))
    except (InvoicePermissionError, InvoiceValidationError) as exc:
        raise _invoice_error(exc) from exc


@router.get("/me/invoices/download")
def download_my_invoice_batch(
    request: Request, invoice_ids: list[UUID] = Query(alias="invoiceIds"), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> Response:
    try:
        return _invoice_download_response(*InvoiceService(db).export_invoice_batch(actor=current_user, user_id=current_user.id, invoice_ids=invoice_ids, request=request))
    except (InvoicePermissionError, InvoiceValidationError) as exc:
        raise _invoice_error(exc) from exc


@router.get("/users/{user_id}/invoices/download")
def download_user_invoice_batch(
    user_id: UUID, request: Request, invoice_ids: list[UUID] = Query(alias="invoiceIds"), db: Session = Depends(get_db), current_user: User = Depends(require_admin)
) -> Response:
    try:
        return _invoice_download_response(*InvoiceService(db).export_invoice_batch(actor=current_user, user_id=user_id, invoice_ids=invoice_ids, request=request))
    except (InvoicePermissionError, InvoiceValidationError) as exc:
        raise _invoice_error(exc) from exc


@router.post("/users/{user_id}/invoices/{invoice_id}/void", response_model=InvoiceItem)
def void_user_invoice(
    user_id: UUID, invoice_id: UUID, payload: InvoiceVoidRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_admin)
) -> InvoiceItem:
    try:
        return InvoiceService(db).void_invoice(actor=current_user, user_id=user_id, invoice_id=invoice_id, reason=payload.reason, request=request)
    except (InvoicePermissionError, InvoiceValidationError) as exc:
        raise _invoice_error(exc) from exc
