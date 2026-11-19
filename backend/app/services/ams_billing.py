"""Template-specific AMS charges matched to Excel channels and row weights."""
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from openpyxl.utils.cell import column_index_from_string

from app.schemas.supplier import AmsChargeItem, SupplierVersionConfig
from app.services.supplier_rule_engine import SupplierRuleEngine, SupplierStructureError


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
