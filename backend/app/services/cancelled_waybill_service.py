from sqlalchemy.orm import Session

from app.repositories.cancelled_waybill_repository import CancelledWaybillRepository
from app.schemas.cancelled_waybill import (
    CancelledWaybillItem,
    CancelledWaybillListResponse,
)


class CancelledWaybillService:
    def __init__(self, db: Session):
        self.cancelled_waybills = CancelledWaybillRepository(db)

    def list_cancelled_waybills(self) -> CancelledWaybillListResponse:
        return CancelledWaybillListResponse(
            items=[
                CancelledWaybillItem.model_validate(item)
                for item in self.cancelled_waybills.list_all()
            ]
        )
