from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, require_admin
from app.db.models import User
from app.db.session import get_db
from app.schemas.supplier import (
    SupplierCreateRequest,
    SupplierItem,
    SupplierListResponse,
    SupplierUpdateRequest,
    SupplierVersionCreateRequest,
)
from app.services.supplier_service import SupplierService, SupplierValidationError


router = APIRouter(prefix="/api/v1/suppliers", tags=["suppliers"])


def _error(exc: SupplierValidationError) -> HTTPException:
    code = status.HTTP_404_NOT_FOUND if "not found" in str(exc).lower() else status.HTTP_400_BAD_REQUEST
    return HTTPException(status_code=code, detail=str(exc))


@router.get("", response_model=SupplierListResponse)
def list_suppliers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SupplierListResponse:
    try:
        return SupplierListResponse(
            items=SupplierService(db).list_suppliers(actor=current_user)
        )
    except SupplierValidationError as exc:
        raise _error(exc) from exc


@router.post("", response_model=SupplierItem, status_code=status.HTTP_201_CREATED)
def create_supplier(
    payload: SupplierCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> SupplierItem:
    try:
        return SupplierService(db).create_supplier(
            actor=current_user,
            name=payload.name,
            config=payload.config,
            request=request,
        )
    except SupplierValidationError as exc:
        raise _error(exc) from exc


@router.post("/{supplier_id}/versions", response_model=SupplierItem)
def publish_supplier_version(
    supplier_id: UUID,
    payload: SupplierVersionCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> SupplierItem:
    try:
        return SupplierService(db).publish_version(
            actor=current_user,
            supplier_id=supplier_id,
            config=payload.config,
            request=request,
        )
    except SupplierValidationError as exc:
        raise _error(exc) from exc


@router.patch("/{supplier_id}", response_model=SupplierItem)
def update_supplier(
    supplier_id: UUID,
    payload: SupplierUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> SupplierItem:
    try:
        return SupplierService(db).update_supplier(
            actor=current_user,
            supplier_id=supplier_id,
            name=payload.name,
            status=payload.status,
            request=request,
        )
    except SupplierValidationError as exc:
        raise _error(exc) from exc
