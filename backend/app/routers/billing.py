from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
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
from app.services.billing_service import (
    BillingPermissionError,
    BillingService,
    BillingValidationError,
)
from app.services.supplier_service import SupplierService


router = APIRouter(prefix="/api/v1/billing", tags=["billing"])


def _billing_error(exc: Exception) -> HTTPException:
    if isinstance(exc, BillingPermissionError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    code = (
        status.HTTP_404_NOT_FOUND
        if str(exc) in {"User not found", "Recharge record not found", "Receipt image not found"}
        else status.HTTP_400_BAD_REQUEST
    )
    return HTTPException(status_code=code, detail=str(exc))


@router.get("/me", response_model=BillingAccountResponse)
def get_my_billing_account(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BillingAccountResponse:
    return BillingService(db).get_account(actor=current_user)


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
