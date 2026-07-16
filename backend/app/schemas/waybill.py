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
    "cleared",
    "partial_inbound",
    "inbound",
    "partial_outbound",
    "outbound",
]
WaybillFycoStatus = Literal["released", "fyco"]
WaybillParcelStatus = Literal[
    "created",
    "pending_check",
    "inspection",
    "released",
    "temporary_released",
    "exception",
    "confiscated",
    "destroyed",
    "on_hold",
    "inbound",
    "outbound",
]


class WaybillPodFileItem(BaseModel):
    id: UUID
    original_filename: str = Field(alias="originalFilename")
    content_type: str | None = Field(default=None, alias="contentType")
    size_bytes: int = Field(alias="sizeBytes")
    created_at: datetime = Field(alias="createdAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class WaybillItem(BaseModel):
    id: UUID
    public_code: str = Field(alias="publicCode")
    upload_id: UUID = Field(alias="uploadId")
    user_id: UUID = Field(alias="userId")
    number: str
    status: WaybillTrackingStatus
    airport_of_departure: str | None = Field(default=None, alias="airportOfDeparture")
    airport_of_arrival: str | None = Field(default=None, alias="airportOfArrival")
    status_changed_at: datetime = Field(alias="statusChangedAt")
    weight_kg: Decimal = Field(alias="weightKg")
    pieces: int
    customs_cartons: int | None = Field(default=None, alias="customsCartons")
    customs_amount: Decimal | None = Field(default=None, alias="customsAmount")
    received_count: int = Field(alias="receivedCount")
    received_total: int = Field(alias="receivedTotal")
    in_warehouse_count: int = Field(alias="inWarehouseCount")
    pallet_count: int = Field(alias="palletCount")
    fyco_status: WaybillFycoStatus | None = Field(default=None, alias="fycoStatus")
    released_count: int = Field(alias="releasedCount")
    outbound_count: int = Field(alias="outboundCount")
    noa_at: datetime | None = Field(default=None, alias="noaAt")
    collection_at: datetime | None = Field(default=None, alias="collectionAt")
    scanned_at: datetime | None = Field(default=None, alias="scannedAt")
    customs_clearance_at: datetime | None = Field(
        default=None, alias="customsClearanceAt"
    )
    outbound_at: datetime | None = Field(default=None, alias="outboundAt")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    user: WaybillUploadUserItem | None = None
    pod_files: list[WaybillPodFileItem] = Field(
        default_factory=list, alias="podFiles"
    )

    model_config = ConfigDict(populate_by_name=True)


class WaybillPodDeleteResponse(BaseModel):
    status: Literal["deleted"]
    pod_file_id: UUID = Field(alias="podFileId")

    model_config = ConfigDict(populate_by_name=True)


class WaybillParcelItem(BaseModel):
    id: UUID
    parcel_unit_number: str = Field(alias="parcelUnitNumber")
    status: WaybillParcelStatus
    number_of_items: int | None = Field(default=None, alias="numberOfItems")
    weight_kg: Decimal | None = Field(default=None, alias="weightKg")
    destination_raw: str | None = Field(default=None, alias="destinationRaw")
    destination_code: str | None = Field(default=None, alias="destinationCode")
    destination_name: str | None = Field(default=None, alias="destinationName")
    inbound: bool
    outbound: bool
    special_instruction: bool = Field(alias="specialInstruction")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class WaybillParcelListResponse(BaseModel):
    items: list[WaybillParcelItem]

    model_config = ConfigDict(populate_by_name=True)


class WaybillParcelBulkUpdateRequest(BaseModel):
    parcelIds: list[UUID] = Field(min_length=1)
    status: WaybillParcelStatus | None = None
    inbound: bool | None = None
    outbound: bool | None = None
    specialInstruction: bool | None = None


class WaybillListResponse(BaseModel):
    items: list[WaybillItem]

    model_config = ConfigDict(populate_by_name=True)


class WaybillUpdateRequest(BaseModel):
    status: WaybillTrackingStatus | None = None
    airportOfDeparture: str | None = Field(default=None, max_length=120)
    airportOfArrival: str | None = Field(default=None, max_length=3)
    receivedCount: int | None = Field(default=None, ge=0)
    receivedTotal: int | None = Field(default=None, ge=0)
    inWarehouseCount: int | None = Field(default=None, ge=0)
    palletCount: int | None = Field(default=None, ge=0)
    fycoStatus: WaybillFycoStatus | None = None
    releasedCount: int | None = Field(default=None, ge=0)
    outboundCount: int | None = Field(default=None, ge=0)
    noaAt: datetime | None = None
    collectionAt: datetime | None = None
    scannedAt: datetime | None = None
    customsClearanceAt: datetime | None = None
    outboundAt: datetime | None = None
