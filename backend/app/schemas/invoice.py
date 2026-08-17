from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class InvoicePayerItem(BaseModel):
    company_name: str = Field(alias="companyName")
    address_info: str = Field(alias="addressInfo")

    model_config = ConfigDict(populate_by_name=True)


class InvoiceSettingsItem(BaseModel):
    issuer_company_name: str | None = Field(default=None, alias="issuerCompanyName")
    issuer_address_info: str | None = Field(default=None, alias="issuerAddressInfo")
    beneficiary_name: str | None = Field(default=None, alias="beneficiaryName")
    bank_account: str | None = Field(default=None, alias="bankAccount")
    bank_name_and_code: str | None = Field(default=None, alias="bankNameAndCode")
    branch_code: str | None = Field(default=None, alias="branchCode")
    swift_bic: str | None = Field(default=None, alias="swiftBic")
    bank_address: str | None = Field(default=None, alias="bankAddress")
    stamp_original_filename: str | None = Field(default=None, alias="stampOriginalFilename")
    updated_at: datetime | None = Field(default=None, alias="updatedAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class InvoiceSettingsUpdateRequest(BaseModel):
    issuer_company_name: str = Field(min_length=1, max_length=255, alias="issuerCompanyName")
    issuer_address_info: str = Field(min_length=1, max_length=2000, alias="issuerAddressInfo")
    beneficiary_name: str = Field(min_length=1, max_length=255, alias="beneficiaryName")
    bank_account: str = Field(min_length=1, max_length=255, alias="bankAccount")
    bank_name_and_code: str = Field(min_length=1, max_length=500, alias="bankNameAndCode")
    branch_code: str = Field(min_length=1, max_length=120, alias="branchCode")
    swift_bic: str = Field(min_length=1, max_length=120, alias="swiftBic")
    bank_address: str = Field(min_length=1, max_length=2000, alias="bankAddress")

    model_config = ConfigDict(populate_by_name=True)


class InvoiceEligibleDeductionItem(BaseModel):
    id: UUID
    waybill_number: str = Field(alias="waybillNumber")
    quantity: int
    unit_rate: Decimal = Field(alias="unitRate")
    amount: Decimal
    recorded_at: datetime = Field(alias="recordedAt")

    model_config = ConfigDict(populate_by_name=True)


class InvoiceLineItem(BaseModel):
    id: UUID
    billing_entry_id: UUID = Field(alias="billingEntryId")
    line_number: int = Field(alias="lineNumber")
    waybill_number: str = Field(alias="waybillNumber")
    quantity: int
    unit_rate: Decimal = Field(alias="unitRate")
    amount: Decimal

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class InvoiceItem(BaseModel):
    id: UUID
    invoice_number: str = Field(alias="invoiceNumber")
    status: str
    issued_date: date = Field(alias="issuedDate")
    due_date: date = Field(alias="dueDate")
    total_amount: Decimal = Field(alias="totalAmount")
    payer: InvoicePayerItem
    lines: list[InvoiceLineItem] = []
    created_at: datetime = Field(alias="createdAt")
    voided_at: datetime | None = Field(default=None, alias="voidedAt")
    void_reason: str | None = Field(default=None, alias="voidReason")

    model_config = ConfigDict(populate_by_name=True)


class InvoiceCreateRequest(BaseModel):
    deduction_ids: list[UUID] = Field(min_length=1, max_length=500, alias="deductionIds")
    issued_date: date = Field(alias="issuedDate")

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("deduction_ids")
    @classmethod
    def unique_ids(cls, value: list[UUID]):
        if len(set(value)) != len(value):
            raise ValueError("Each deduction can be selected only once")
        return value


class InvoiceCreateResponse(BaseModel):
    invoices: list[InvoiceItem]

    model_config = ConfigDict(populate_by_name=True)


class InvoiceVoidRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)
