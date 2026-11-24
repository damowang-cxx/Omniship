"""Template-specific AMS charges matched to Excel channels and row weights."""
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from openpyxl.utils.cell import column_index_from_string

from app.schemas.supplier import AmsChargeItem, SupplierVersionConfig
from app.services.supplier_rule_engine import SupplierRuleEngine, SupplierStructureError


AMS_WEIGHT_DIFFERENCE_NAME = "清关费重量差异补收"


@dataclass(frozen=True)
class AmsWeightDifference:
    weight_kg: Decimal
    amount: Decimal
    charges: list[AmsChargeItem]


def calculate_ams_weight_difference(charges: list[AmsChargeItem], gross_weight_kg: Decimal) -> AmsWeightDifference:
    if not charges:
        return AmsWeightDifference(Decimal("0.000"), Decimal("0.00"), [])
    difference = gross_weight_kg - sum((charge.quantity for charge in charges), Decimal("0.000"))
    if difference <= 0:
        return AmsWeightDifference(Decimal("0.000"), Decimal("0.00"), [])
    if any(charge.fee_description == AMS_WEIGHT_DIFFERENCE_NAME for charge in charges):
        raise SupplierStructureError("AMS 收费明细名称不能与清关费重量差异补收相同")
    # Both gross and Excel weights have at most three decimals. Allocate each 0.001 kg
    # remainder to a configured detail in order so the displayed shares sum exactly.
    milli_kg = int(difference * 1000)
    shared, remainder = divmod(milli_kg, len(charges))
    allocations = []
    for index, charge in enumerate(charges):
        quantity = Decimal(shared + (index < remainder)) / 1000
        amount = (quantity * charge.unit_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        allocations.append(AmsChargeItem(
            fee_description=charge.fee_description, quantity=quantity,
            unit_rate=charge.unit_rate, amount=amount,
        ))
    total = sum((allocation.amount for allocation in allocations), Decimal("0.00"))
    if total >= Decimal("10000000000"):
        raise SupplierStructureError("AMS 重量差异补收金额超过支持范围")
    return AmsWeightDifference(difference, total, allocations)


def calculate_ams_charges(
    *, filename: str, content: bytes, config: SupplierVersionConfig, user_id: UUID | None,
) -> list[AmsChargeItem]:
    billing = config.ams_billing
    if billing is None:
        return []
    customer = next((rate for rate in billing.customer_rates if rate.user_id == user_id), None)
    if customer is None:
        return []

    engine = SupplierRuleEngine()
    header, rows = engine.read_workbook(filename=filename, content=content, config=config)
    match_index = column_index_from_string(billing.match_column) - 1
    weight_index = column_index_from_string(billing.weight_column) - 1
    column_count = max([len(header), *(len(row) for _, row in rows)])
    if max(match_index, weight_index) >= column_count:
        raise SupplierStructureError("AMS 匹配列或重量列超出上传 Excel 的列范围")
    if billing.match_header:
        actual_header = str(header[match_index] or "").strip() if match_index < len(header) else ""
        if actual_header.casefold() != billing.match_header.casefold():
            raise SupplierStructureError(f"AMS {billing.match_column} 列标题应为 {billing.match_header}")

    weights = {fee.match_value: Decimal("0.000") for fee in customer.fees}
    for row_number, row in rows:
        value = str(row[match_index] or "").strip() if match_index < len(row) else ""
        if value not in weights:
            continue
        raw_weight = row[weight_index] if weight_index < len(row) else None
        weight = engine.parse_decimal(raw_weight)
        if weight is None or not weight.is_finite() or weight < 0 or weight >= Decimal("1000000000") or weight.as_tuple().exponent < -3:
            raise SupplierStructureError(f"AMS 第 {row_number} 行重量须为非负数，最多三位小数")
        weights[value] += weight

    charges = []
    for fee in customer.fees:
        quantity = weights[fee.match_value]
        amount = (quantity * fee.rate_eur_per_kg).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if quantity >= Decimal("1000000000") or amount >= Decimal("10000000000"):
            raise SupplierStructureError(f"AMS {fee.match_value} 的重量或金额超过支持范围")
        if quantity > 0:
            charges.append(AmsChargeItem(
                fee_description=fee.match_value, quantity=quantity,
                unit_rate=fee.rate_eur_per_kg, amount=amount,
            ))
    return charges
