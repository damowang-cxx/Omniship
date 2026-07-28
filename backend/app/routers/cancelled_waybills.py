from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import require_admin
from app.db.models import User
from app.db.session import get_db
from app.schemas.cancelled_waybill import CancelledWaybillListResponse
from app.services.cancelled_waybill_service import CancelledWaybillService


router = APIRouter(
    prefix="/api/v1/cancelled-waybills",
    tags=["cancelled-waybills"],
)


@router.get("", response_model=CancelledWaybillListResponse)
def list_cancelled_waybills(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_admin),
) -> CancelledWaybillListResponse:
    return CancelledWaybillService(db).list_cancelled_waybills()
