from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.waybill_upload import WaybillUploadUserItem


WaybillTrackingStatus = Literal[
    "created",
    "noa_received",
    "received",
    "ready_to_scan",
    "scanning",
    "pending_clearance",
    "partial_inbound",
    "inbound",
    "partial_outbound",
    "outbound",
]


class WaybillItem(BaseModel):
    id: UUID
    public_code: str = Field(alias="publicCode")
    upload_id: UUID = Field(alias="uploadId")
    user_id: UUID = Field(alias="userId")
    number: str
    status: WaybillTrackingStatus
    status_changed_at: datetime = Field(alias="statusChangedAt")
    weight_kg: Decimal = Field(alias="weightKg")
    pieces: int
    received_count: int = Field(alias="receivedCount")
    received_total: int = Field(alias="receivedTotal")
    in_warehouse_count: int = Field(alias="inWarehouseCount")
    released_count: int = Field(alias="releasedCount")
    outbound_count: int = Field(alias="outboundCount")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    user: WaybillUploadUserItem | None = None

    model_config = ConfigDict(populate_by_name=True)


class WaybillListResponse(BaseModel):
    items: list[WaybillItem]

    model_config = ConfigDict(populate_by_name=True)


class WaybillUpdateRequest(BaseModel):
    status: WaybillTrackingStatus | None = None
    receivedCount: int | None = Field(default=None, ge=0)
    receivedTotal: int | None = Field(default=None, ge=0)
    inWarehouseCount: int | None = Field(default=None, ge=0)
    releasedCount: int | None = Field(default=None, ge=0)
    outboundCount: int | None = Field(default=None, ge=0)
