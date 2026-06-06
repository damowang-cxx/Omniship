from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, require_admin
from app.db.models import User
from app.db.session import get_db
from app.schemas.waybill import WaybillItem, WaybillListResponse, WaybillUpdateRequest
from app.services.waybill_service import (
    WaybillPermissionError,
    WaybillService,
    WaybillValidationError,
)


router = APIRouter(prefix="/api/v1/waybills", tags=["waybills"])


@router.get("", response_model=WaybillListResponse)
def list_waybills(
    user_id: UUID | None = Query(default=None, alias="userId"),
    waybill_status: str | None = Query(default=None, alias="status"),
    query: str | None = Query(default=None, alias="q"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WaybillListResponse:
    try:
        return WaybillService(db).list_waybills(
            current_user,
            user_id=user_id,
            status=waybill_status,
            query=query,
        )
    except WaybillValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/{public_code}", response_model=WaybillItem)
def get_waybill(
    public_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WaybillItem:
    try:
        return WaybillService(db).get_waybill(current_user, public_code=public_code)
    except WaybillPermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except WaybillValidationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch("/{public_code}", response_model=WaybillItem)
def update_waybill(
    public_code: str,
    payload: WaybillUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> WaybillItem:
    try:
        return WaybillService(db).update_waybill(
            current_user,
            public_code=public_code,
            payload=payload,
            request=request,
        )
    except WaybillPermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except WaybillValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
