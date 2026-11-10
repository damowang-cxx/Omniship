"""LHR charges for customers enrolled in the global fee schedule."""
import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from uuid import UUID

from app.schemas.supplier import LhrBillingConfig


@dataclass(frozen=True)
class LhrCharges:
    clearance_eur: Decimal
    weight_rate_gbp: Decimal
    weight_fee_gbp: Decimal
    surcharge_gbp: Decimal
    surcharge_description: str | None

    @property
    def total_gbp(self) -> Decimal:
        return self.weight_fee_gbp + self.surcharge_gbp


def calculate_lhr_charges(
    *, config: LhrBillingConfig | None, user_id: UUID,
    waybill_number: str, gross_weight_kg: Decimal,
) -> LhrCharges:
    customer_rate = next((item.rate_gbp_per_kg for item in config.customer_rates if item.user_id == user_id), None) if config is not None else None
    if customer_rate is None:
        return LhrCharges(
            clearance_eur=Decimal("0.00"),
            weight_rate_gbp=Decimal("0.00"),
            weight_fee_gbp=Decimal("0.00"),
            surcharge_gbp=Decimal("0.00"),
            surcharge_description=None,
        )
    assert config is not None
    weight_fee = (gross_weight_kg * customer_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    prefix_match = re.match(r"^\s*(\d{3})", waybill_number)
    if prefix_match is None:
        raise ValueError("LHR Air Waybill Number must start with a three-digit airline prefix")
    prefix = prefix_match.group(1)
    rule = next((item for item in config.surcharge_rules if prefix in item.prefixes), None)
    surcharge = Decimal("0.00")
    description = None
    if rule is not None:
        if rule.mode == "fixed":
            surcharge = rule.amount_gbp
            description = f"LHR 货站附加费 · {rule.name} · {prefix} · fixed"
        else:
            rounded_weight = int(gross_weight_kg.to_integral_value(rounding=ROUND_CEILING))
            band = next((item for item in rule.bands if item.min_weight_kg <= rounded_weight and (item.max_weight_kg is None or rounded_weight <= item.max_weight_kg)), None)
            if band is None:
                raise ValueError(f"LHR surcharge rule {rule.name} has no weight band for {rounded_weight} kg")
            surcharge = band.amount_gbp
            upper = str(band.max_weight_kg) if band.max_weight_kg is not None else "above"
            description = f"LHR 货站附加费 · {rule.name} · {prefix} · {band.min_weight_kg}–{upper} kg (rounded up)"
    return LhrCharges(
        clearance_eur=config.clearance_fee_eur,
        weight_rate_gbp=customer_rate,
        weight_fee_gbp=weight_fee,
        surcharge_gbp=surcharge,
        surcharge_description=description,
    )
