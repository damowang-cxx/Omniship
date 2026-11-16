"""AMS per-waybill tax handling and optional customer weight charges."""
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from app.schemas.supplier import AmsBillingConfig


def calculate_ams_tax_handling_fee(config: AmsBillingConfig | None) -> Decimal:
    return config.tax_handling_fee_eur if config is not None else Decimal("0.00")


def calculate_ams_weight_fee(
    config: AmsBillingConfig | None, user_id: UUID, gross_weight_kg: Decimal
) -> tuple[Decimal, Decimal]:
    rate = next(
        (item.rate_eur_per_kg for item in config.customer_rates if item.user_id == user_id),
        Decimal("0.00"),
    ) if config is not None else Decimal("0.00")
    amount = (gross_weight_kg * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return rate, amount
