from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WaybillUploadFileItem(BaseModel):
    id: UUID
    file_kind: str = Field(alias="fileKind")
    original_filename: str = Field(alias="originalFilename")
    content_type: str | None = Field(default=None, alias="contentType")
    size_bytes: int = Field(alias="sizeBytes")
    sha256: str
    created_at: datetime = Field(alias="createdAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class WaybillUploadUserItem(BaseModel):
    id: UUID
    email: str
    username: str

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class WaybillPreAlertUploadResponse(BaseModel):
    upload_id: UUID = Field(alias="uploadId")
    air_waybill_number: str = Field(alias="airWaybillNumber")
    status: str
    bound_user_id: UUID = Field(alias="boundUserId")

    model_config = ConfigDict(populate_by_name=True)


class WaybillUploadItem(BaseModel):
    id: UUID
    user_id: UUID = Field(alias="userId")
    uploaded_by_user_id: UUID | None = Field(default=None, alias="uploadedByUserId")
    shipment_type: str = Field(alias="shipmentType")
    air_waybill_number: str = Field(alias="airWaybillNumber")
    gross_weight_kg: Decimal = Field(alias="grossWeightKg")
    pieces: int
    arrival_flight_number: str | None = Field(default=None, alias="arrivalFlightNumber")
    status: str
    reviewed_by_user_id: UUID | None = Field(default=None, alias="reviewedByUserId")
    reviewed_at: datetime | None = Field(default=None, alias="reviewedAt")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    user: WaybillUploadUserItem | None = None
    uploaded_by: WaybillUploadUserItem | None = Field(default=None, alias="uploadedBy")
    files: list[WaybillUploadFileItem] = []

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class WaybillUploadListResponse(BaseModel):
    items: list[WaybillUploadItem]

    model_config = ConfigDict(populate_by_name=True)


class WaybillUploadStatusUpdateRequest(BaseModel):
    status: str = Field(pattern="^(pending_review|approved|rejected)$")


class WaybillUploadDeleteResponse(BaseModel):
    status: str
    upload_id: UUID = Field(alias="uploadId")

    model_config = ConfigDict(populate_by_name=True)
