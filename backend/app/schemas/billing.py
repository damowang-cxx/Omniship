from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.user import UserPublic


class BillingReceiptItem(BaseModel):
    original_filename: str = Field(alias="originalFilename")
    content_type: str | None = Field(default=None, alias="contentType")
    size_bytes: int = Field(alias="sizeBytes")

    model_config = ConfigDict(populate_by_name=True)


class BillingEntryItem(BaseModel):
    id: UUID
    entry_type: str = Field(alias="entryType")
    amount: Decimal
    currency: str
    balance_after: Decimal = Field(alias="balanceAfter")
    waybill_upload_id: UUID | None = Field(default=None, alias="waybillUploadId")
    waybill_number: str | None = Field(default=None, alias="waybillNumber")
    supplier_id: UUID | None = Field(default=None, alias="supplierId")
    supplier_name: str | None = Field(default=None, alias="supplierName")
    supplier_version_number: int | None = Field(default=None, alias="supplierVersionNumber")
    arrival_airport: str | None = Field(default=None, alias="arrivalAirport")
    billable_unit_count: int | None = Field(default=None, alias="billableUnitCount")
    unit_rate: Decimal | None = Field(default=None, alias="unitRate")
    billing_source: str | None = Field(default=None, alias="billingSource")
    created_by_user_id: UUID | None = Field(default=None, alias="createdByUserId")
    receipt: BillingReceiptItem | None = None
    created_at: datetime = Field(alias="createdAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class BillingAccountResponse(BaseModel):
    user: UserPublic
    deductions: list[BillingEntryItem]
    recharges: list[BillingEntryItem]

    model_config = ConfigDict(populate_by_name=True)


class BillingTaxEstimateResponse(BaseModel):
    supplier_id: UUID = Field(alias="supplierId")
    supplier_name: str = Field(alias="supplierName")
    supplier_version_id: UUID = Field(alias="supplierVersionId")
    supplier_version_number: int = Field(alias="supplierVersionNumber")
    taxable_airport: bool = Field(alias="taxableAirport")
    billable_unit_count: int = Field(alias="billableUnitCount")
    unit_rate: Decimal = Field(alias="unitRate")
    estimated_tax: Decimal = Field(alias="estimatedTax")
    warning_count: int = Field(alias="warningCount")
    warnings: list[dict]
    currency: str = "EUR"

    model_config = ConfigDict(populate_by_name=True)


class RetroactiveBillingRequest(BaseModel):
    waybillNumbers: list[str] = Field(min_length=1, max_length=500)

    @field_validator("waybillNumbers")
    @classmethod
    def normalize_numbers(cls, values: list[str]):
        normalized = []
        for value in values:
            number = value.strip()
            if not number:
                continue
            if len(number) > 255:
                raise ValueError("Waybill numbers may contain at most 255 characters")
            if number not in normalized:
                normalized.append(number)
        if not normalized:
            raise ValueError("At least one waybill number is required")
        return normalized


class RetroactiveBillingSuccessItem(BaseModel):
    waybill_number: str = Field(alias="waybillNumber")
    supplier_name: str = Field(alias="supplierName")
    supplier_version_number: int = Field(alias="supplierVersionNumber")
    billable_unit_count: int = Field(alias="billableUnitCount")
    unit_rate: Decimal = Field(alias="unitRate")
    amount: Decimal
    balance_after: Decimal = Field(alias="balanceAfter")
    warning_count: int = Field(alias="warningCount")

    model_config = ConfigDict(populate_by_name=True)


class RetroactiveBillingFailureItem(BaseModel):
    waybill_number: str = Field(alias="waybillNumber")
    reason: str

    model_config = ConfigDict(populate_by_name=True)


class RetroactiveBillingResponse(BaseModel):
    requested_count: int = Field(alias="requestedCount")
    succeeded_count: int = Field(alias="succeededCount")
    failed_count: int = Field(alias="failedCount")
    succeeded: list[RetroactiveBillingSuccessItem]
    failed: list[RetroactiveBillingFailureItem]

    model_config = ConfigDict(populate_by_name=True)
