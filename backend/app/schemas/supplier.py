import re
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SemanticField = Literal[
    "parcel_unit_number",
    "destination",
    "number_of_items",
    "weight_kg",
]
ValueType = Literal["text", "number", "integer", "country"]
BlankPolicy = Literal["allow", "required", "skip_row"]
LocatorMode = Literal["column", "header"]


class SupplierWorkbookConfig(BaseModel):
    sheet_mode: Literal["first", "named"] = Field(default="first", alias="sheetMode")
    sheet_name: str | None = Field(default=None, alias="sheetName")
    header_row: int = Field(default=1, ge=1, le=1000, alias="headerRow")
    data_start_row: int = Field(default=2, ge=1, le=10000, alias="dataStartRow")

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode="after")
    def validate_layout(self):
        if self.sheet_mode == "named" and not (self.sheet_name or "").strip():
            raise ValueError("Named worksheet requires a sheet name")
        if self.data_start_row <= self.header_row:
            raise ValueError("Data start row must be after the header row")
        return self


class SupplierRuleConstraints(BaseModel):
    min_value: Decimal | None = Field(default=None, alias="minValue")
    max_value: Decimal | None = Field(default=None, alias="maxValue")
    min_length: int | None = Field(default=None, ge=0, le=10000, alias="minLength")
    max_length: int | None = Field(default=None, ge=0, le=10000, alias="maxLength")
    pattern: str | None = Field(default=None, max_length=120)
    allowed_values: list[str] = Field(default_factory=list, alias="allowedValues")
    unique: bool = False

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("pattern")
    @classmethod
    def validate_safe_pattern(cls, value: str | None):
        if not value:
            return None
        if "(?" in value or re.search(r"\\[1-9]", value):
            raise ValueError("Regex lookarounds and backreferences are not supported")
        if re.search(r"(?:\*|\+|\?|\{\d+,?\})\s*(?:\*|\+|\?|\{)", value) or re.search(
            r"\([^)]*(?:\||\*|\+|\?|\{)[^)]*\)\s*(?:\*|\+|\?|\{)", value
        ):
            raise ValueError("Nested regex quantifiers are not supported")
        try:
            re.compile(value)
        except re.error as exc:
            raise ValueError("Regex pattern is invalid") from exc
        return value

    @model_validator(mode="after")
    def validate_ranges(self):
        if self.min_value is not None and self.max_value is not None:
            if self.min_value > self.max_value:
                raise ValueError("Minimum value cannot exceed maximum value")
        if self.min_length is not None and self.max_length is not None:
            if self.min_length > self.max_length:
                raise ValueError("Minimum length cannot exceed maximum length")
        return self


class SupplierFieldRule(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,49}$")
    name: str = Field(min_length=1, max_length=120)
    semantic_field: SemanticField | None = Field(default=None, alias="semanticField")
    locator_mode: LocatorMode = Field(alias="locatorMode")
    locator_value: str = Field(min_length=1, max_length=255, alias="locatorValue")
    value_type: ValueType = Field(alias="valueType")
    blank_policy: BlankPolicy = Field(default="allow", alias="blankPolicy")
    case_insensitive: bool = Field(default=False, alias="caseInsensitive")
    allow_unknown_country: bool = Field(default=True, alias="allowUnknownCountry")
    country_aliases: dict[str, str] = Field(default_factory=dict, alias="countryAliases")
    constraints: SupplierRuleConstraints = Field(default_factory=SupplierRuleConstraints)

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("locator_value")
    @classmethod
    def normalize_locator(cls, value: str, info):
        value = value.strip()
        mode = info.data.get("locator_mode")
        if mode == "column":
            value = value.upper()
            if not re.fullmatch(r"[A-Z]{1,3}", value):
                raise ValueError("Excel column must contain one to three letters")
        return value

    @field_validator("country_aliases")
    @classmethod
    def validate_aliases(cls, value: dict[str, str]):
        normalized = {}
        for source, code in value.items():
            source_key = source.strip()
            country_code = code.strip().upper()
            if not source_key or not re.fullmatch(r"[A-Z]{2}", country_code):
                raise ValueError("Country aliases must map non-empty values to ISO-2 codes")
            normalized[source_key] = country_code
        return normalized


class SupplierVersionConfig(BaseModel):
    workbook: SupplierWorkbookConfig = Field(default_factory=SupplierWorkbookConfig)
    fields: list[SupplierFieldRule] = Field(min_length=1, max_length=100)
    row_key_field_key: str = Field(alias="rowKeyFieldKey")
    billing_group_field_key: str = Field(alias="billingGroupFieldKey")
    billing_distinct_field_key: str = Field(alias="billingDistinctFieldKey")

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode="before")
    @classmethod
    def upgrade_legacy_billing_config(cls, value):
        if not isinstance(value, dict):
            return value
        has_group_field = (
            "billingGroupFieldKey" in value or "billing_group_field_key" in value
        )
        if has_group_field:
            return value
        distinct_field = value.get(
            "billingDistinctFieldKey", value.get("billing_distinct_field_key")
        )
        if distinct_field is None:
            return value
        upgraded = dict(value)
        upgraded["billingGroupFieldKey"] = distinct_field
        return upgraded

    @model_validator(mode="after")
    def validate_fields(self):
        keys = [field.key for field in self.fields]
        if len(keys) != len(set(keys)):
            raise ValueError("Supplier field keys must be unique")
        semantic_fields = [field.semantic_field for field in self.fields if field.semantic_field]
        if len(semantic_fields) != len(set(semantic_fields)):
            raise ValueError("Each system field can only be mapped once")
        field_map = {field.key: field for field in self.fields}
        if self.row_key_field_key not in field_map:
            raise ValueError("Row key field does not exist")
        if self.billing_group_field_key not in field_map:
            raise ValueError("Billing group field does not exist")
        if self.billing_distinct_field_key not in field_map:
            raise ValueError("Billing distinct field does not exist")
        if field_map[self.row_key_field_key].blank_policy != "skip_row":
            raise ValueError("Row key field must use the skip-row blank policy")
        return self


class SupplierCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    config: SupplierVersionConfig


class SupplierVersionCreateRequest(BaseModel):
    config: SupplierVersionConfig


class SupplierUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    status: Literal["active", "inactive"] | None = None


class SupplierVersionItem(BaseModel):
    id: UUID
    version_number: int = Field(alias="versionNumber")
    config: SupplierVersionConfig
    created_by_user_id: UUID | None = Field(default=None, alias="createdByUserId")
    created_at: datetime = Field(alias="createdAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class SupplierItem(BaseModel):
    id: UUID
    name: str
    status: str
    current_version_number: int = Field(alias="currentVersionNumber")
    current_version: SupplierVersionItem = Field(alias="currentVersion")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class SupplierListResponse(BaseModel):
    items: list[SupplierItem]


class BillingSettingsItem(BaseModel):
    unit_tax_eur: Decimal = Field(alias="unitTaxEur")
    taxable_airports: list[str] = Field(alias="taxableAirports")
    tax_effective_date: date = Field(alias="taxEffectiveDate")
    updated_at: datetime = Field(alias="updatedAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class BillingSettingsUpdateRequest(BaseModel):
    unitTaxEur: Decimal
    taxableAirports: list[str]
    taxEffectiveDate: date | None = None

    @field_validator("unitTaxEur")
    @classmethod
    def validate_unit_tax(cls, value: Decimal):
        if value < 0 or value > Decimal("999999.99"):
            raise ValueError("Unit tax must be between 0 and 999999.99 EUR")
        if value.as_tuple().exponent < -2:
            raise ValueError("Unit tax may contain at most two decimal places")
        return value.quantize(Decimal("0.01"))

    @field_validator("taxableAirports")
    @classmethod
    def normalize_airports(cls, values: list[str]):
        if len(values) > 200:
            raise ValueError("At most 200 taxable airports may be configured")
        normalized = []
        for value in values:
            airport = value.strip().upper()
            if not re.fullmatch(r"[A-Z]{3}", airport):
                raise ValueError("Airport codes must be three-letter IATA codes")
            if airport not in normalized:
                normalized.append(airport)
        return normalized

    @property
    def unit_tax_eur(self) -> Decimal:
        return self.unitTaxEur

    @property
    def taxable_airports(self) -> list[str]:
        return self.taxableAirports

    @property
    def tax_effective_date(self) -> date | None:
        return self.taxEffectiveDate
