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


class LhrCustomerRate(BaseModel):
    user_id: UUID = Field(alias="userId")
    rate_gbp_per_kg: Decimal = Field(gt=0, max_digits=10, decimal_places=2, alias="rateGbpPerKg")

    model_config = ConfigDict(populate_by_name=True)


class LhrWeightBand(BaseModel):
    min_weight_kg: int = Field(ge=0, alias="minWeightKg")
    max_weight_kg: int | None = Field(default=None, ge=0, alias="maxWeightKg")
    amount_gbp: Decimal = Field(gt=0, max_digits=10, decimal_places=2, alias="amountGbp")

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode="after")
    def validate_bounds(self):
        if self.max_weight_kg is not None and self.max_weight_kg < self.min_weight_kg:
            raise ValueError("Weight band maximum must be at least its minimum")
        return self


class LhrSurchargeRule(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    mode: Literal["fixed", "weight_bands"]
    prefixes: list[str] = Field(min_length=1, max_length=100)
    amount_gbp: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2, alias="amountGbp")
    bands: list[LhrWeightBand] = Field(default_factory=list, max_length=30)

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("prefixes")
    @classmethod
    def normalize_prefixes(cls, values: list[str]) -> list[str]:
        prefixes = [value.strip() for value in values]
        if any(not re.fullmatch(r"\d{3}", value) for value in prefixes):
            raise ValueError("Air waybill prefixes must be exactly three digits")
        if len(prefixes) != len(set(prefixes)):
            raise ValueError("Air waybill prefixes must be unique within a rule")
        return prefixes

    @model_validator(mode="after")
    def validate_mode(self):
        if self.mode == "fixed":
            if self.amount_gbp is None or self.bands:
                raise ValueError("Fixed surcharge requires an amount and no weight bands")
        else:
            if self.amount_gbp is not None or not self.bands:
                raise ValueError("Weight-band surcharge requires bands and no fixed amount")
            ordered = sorted(self.bands, key=lambda band: band.min_weight_kg)
            if ordered[0].min_weight_kg != 0 or ordered[-1].max_weight_kg is not None:
                raise ValueError("Weight bands must cover from 0 kg through an open-ended final band")
            for previous, current in zip(ordered, ordered[1:]):
                if previous.max_weight_kg is None or current.min_weight_kg != previous.max_weight_kg + 1:
                    raise ValueError("Weight bands must be contiguous without overlaps or gaps")
        return self


class LhrBillingConfig(BaseModel):
    clearance_fee_eur: Decimal = Field(gt=0, max_digits=10, decimal_places=2, alias="clearanceFeeEur")
    customer_rates: list[LhrCustomerRate] = Field(default_factory=list, max_length=1000, alias="customerRates")
    surcharge_rules: list[LhrSurchargeRule] = Field(default_factory=list, max_length=100, alias="surchargeRules")

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode="after")
    def validate_uniqueness(self):
        user_ids = [rate.user_id for rate in self.customer_rates]
        if len(user_ids) != len(set(user_ids)):
            raise ValueError("Each customer may have only one LHR price")
        prefixes = [prefix for rule in self.surcharge_rules for prefix in rule.prefixes]
        if len(prefixes) != len(set(prefixes)):
            raise ValueError("A prefix may appear in only one LHR surcharge rule")
        return self


class LhrBillingSettingsItem(BaseModel):
    config: LhrBillingConfig | None = None
    version: int = 0


class LhrBillingSettingsUpdateRequest(BaseModel):
    config: LhrBillingConfig | None = None


class SupplierVersionConfig(BaseModel):
    workbook: SupplierWorkbookConfig = Field(default_factory=SupplierWorkbookConfig)
    fields: list[SupplierFieldRule] = Field(min_length=1, max_length=100)
    billing_group_column: str | None = Field(default=None, alias="billingGroupColumn")
    billing_distinct_column: str | None = Field(
        default=None, alias="billingDistinctColumn"
    )
    lhr_billing: LhrBillingConfig | None = Field(default=None, alias="lhrBilling")
    # Retained only so historical supplier versions continue to parse. New versions
    # use the independent Excel columns above and do not need field-rule references.
    row_key_field_key: str | None = Field(default=None, alias="rowKeyFieldKey")
    billing_group_field_key: str | None = Field(
        default=None, alias="billingGroupFieldKey"
    )
    billing_distinct_field_key: str | None = Field(
        default=None, alias="billingDistinctFieldKey"
    )

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode="before")
    @classmethod
    def upgrade_legacy_billing_config(cls, value):
        if not isinstance(value, dict):
            return value
        upgraded = dict(value)
        has_direct_columns = bool(
            value.get("billingGroupColumn", value.get("billing_group_column"))
            or value.get(
                "billingDistinctColumn", value.get("billing_distinct_column")
            )
        )
        if has_direct_columns:
            return upgraded

        has_group_field = (
            "billingGroupFieldKey" in value or "billing_group_field_key" in value
        )
        if not has_group_field:
            distinct_field = value.get(
                "billingDistinctFieldKey", value.get("billing_distinct_field_key")
            )
            if distinct_field is not None:
                upgraded["billingGroupFieldKey"] = distinct_field

        row_key = upgraded.get("rowKeyFieldKey", upgraded.get("row_key_field_key"))
        fields = upgraded.get("fields")
        if row_key and isinstance(fields, list):
            normalized_fields = []
            for field in fields:
                if isinstance(field, dict) and field.get("key") == row_key:
                    normalized_field = dict(field)
                    normalized_field["blankPolicy"] = "skip_row"
                    normalized_fields.append(normalized_field)
                else:
                    normalized_fields.append(field)
            upgraded["fields"] = normalized_fields
        return upgraded

    @field_validator("billing_group_column", "billing_distinct_column")
    @classmethod
    def normalize_billing_column(cls, value: str | None):
        if value is None:
            return None
        column = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{1,3}", column):
            raise ValueError("Excel billing column must contain one to three letters")
        return column

    @model_validator(mode="after")
    def validate_fields(self):
        keys = [field.key for field in self.fields]
        if len(keys) != len(set(keys)):
            raise ValueError("Supplier field keys must be unique")
        semantic_fields = [field.semantic_field for field in self.fields if field.semantic_field]
        if len(semantic_fields) != len(set(semantic_fields)):
            raise ValueError("Each system field can only be mapped once")

        has_group_column = self.billing_group_column is not None
        has_distinct_column = self.billing_distinct_column is not None
        if has_group_column or has_distinct_column:
            if not (has_group_column and has_distinct_column):
                raise ValueError(
                    "Both waybill and carton billing columns must be configured"
                )
            return self

        # Legacy field-rule mode is read-only compatibility for versions that were
        # published before deduction columns became independent inputs.
        field_map = {field.key: field for field in self.fields}
        if not self.row_key_field_key or self.row_key_field_key not in field_map:
            raise ValueError("Row key field does not exist")
        if (
            not self.billing_group_field_key
            or self.billing_group_field_key not in field_map
        ):
            raise ValueError("Billing group field does not exist")
        if (
            not self.billing_distinct_field_key
            or self.billing_distinct_field_key not in field_map
        ):
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
