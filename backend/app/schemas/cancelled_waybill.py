from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CancelWaybillRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        reason = value.strip()
        if not reason:
            raise ValueError("Cancellation reason is required")
        return reason


class CancelledWaybillItem(BaseModel):
    id: UUID
    original_upload_id: UUID = Field(alias="originalUploadId")
    user_id: UUID | None = Field(default=None, alias="userId")
    user_email: str = Field(alias="userEmail")
    username: str
    uploaded_by_email: str | None = Field(default=None, alias="uploadedByEmail")
    supplier_id: UUID | None = Field(default=None, alias="supplierId")
    supplier_name: str | None = Field(default=None, alias="supplierName")
    supplier_version_number: int | None = Field(
        default=None, alias="supplierVersionNumber"
    )
    shipment_type: str = Field(alias="shipmentType")
    air_waybill_number: str = Field(alias="airWaybillNumber")
    gross_weight_kg: Decimal = Field(alias="grossWeightKg")
    pieces: int
    arrival_flight_number: str | None = Field(
        default=None, alias="arrivalFlightNumber"
    )
    airport_of_departure: str | None = Field(
        default=None, alias="airportOfDeparture"
    )
    airport_of_arrival: str | None = Field(default=None, alias="airportOfArrival")
    original_status: str = Field(alias="originalStatus")
    uploaded_at: datetime = Field(alias="uploadedAt")
    file_count: int = Field(alias="fileCount")
    tax_amount_deleted: Decimal = Field(alias="taxAmountDeleted")
    refunded_amount: Decimal = Field(alias="refundedAmount")
    balance_after_refund: Decimal | None = Field(
        default=None, alias="balanceAfterRefund"
    )
    currency: str
    reason: str
    cancelled_by_user_id: UUID | None = Field(
        default=None, alias="cancelledByUserId"
    )
    cancelled_by_email: str = Field(alias="cancelledByEmail")
    cancelled_at: datetime = Field(alias="cancelledAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class CancelledWaybillListResponse(BaseModel):
    items: list[CancelledWaybillItem]


class CancelWaybillResponse(BaseModel):
    status: str = "cancelled"
    upload_id: UUID = Field(alias="uploadId")
    refunded_amount: Decimal = Field(alias="refundedAmount")
    balance_after_refund: Decimal = Field(alias="balanceAfterRefund")
    record: CancelledWaybillItem

    model_config = ConfigDict(populate_by_name=True)
