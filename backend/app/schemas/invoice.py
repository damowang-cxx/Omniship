from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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
    issuerCompanyName: str | None = Field(default=None, min_length=1, max_length=255)
    issuerAddressInfo: str | None = Field(default=None, min_length=1, max_length=2000)
    beneficiaryName: str | None = Field(default=None, min_length=1, max_length=255)
    bankAccount: str | None = Field(default=None, min_length=1, max_length=255)
    bankNameAndCode: str | None = Field(default=None, min_length=1, max_length=500)
    branchCode: str | None = Field(default=None, min_length=1, max_length=120)
    swiftBic: str | None = Field(default=None, min_length=1, max_length=120)
    bankAddress: str | None = Field(default=None, min_length=1, max_length=2000)

    @model_validator(mode="after")
    def require_at_least_one_value(self):
        if not self.model_fields_set:
            raise ValueError("Provide at least one invoice setting")
        return self


class InvoiceEligibleDeductionItem(BaseModel):
    id: UUID
    waybill_number: str = Field(alias="waybillNumber")
    quantity: int
    unit_rate: Decimal = Field(alias="unitRate")
    amount: Decimal
    extra_fee_total: Decimal = Field(alias="extraFeeTotal")
    total_amount: Decimal = Field(alias="totalAmount")
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
    extra_fee_total: Decimal = Field(alias="extraFeeTotal")
    total_amount: Decimal = Field(alias="totalAmount")

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
    deductionIds: list[UUID] = Field(min_length=1, max_length=500)
    issuedDate: date

    @field_validator("deductionIds")
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
