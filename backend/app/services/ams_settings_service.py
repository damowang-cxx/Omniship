"""One AMS fee schedule, separate from Supplier Pre Alert versions."""
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import BillingSettings, User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.supplier_repository import SupplierRepository
from app.schemas.supplier import AmsBillingConfig, AmsBillingSettingsItem
from app.services.request_context import get_request_ip, get_request_user_agent


class AmsSettingsValidationError(ValueError):
    pass


class AmsSettingsService:
    def __init__(self, db: Session):
        self.db = db
        self.suppliers = SupplierRepository(db)
        self.audit_logs = AuditLogRepository(db)

    def get(self) -> AmsBillingSettingsItem:
        settings = self.suppliers.get_settings()
        return AmsBillingSettingsItem(
            config=AmsBillingConfig.model_validate(settings.ams_billing) if settings.ams_billing is not None else None,
            version=settings.ams_billing_version,
        )

    def update(self, *, actor: User, config: AmsBillingConfig | None, request: Request) -> AmsBillingSettingsItem:
        if config is not None:
            for rate in config.customer_rates:
                customer = self.db.get(User, rate.user_id)
                if customer is None or customer.role != "user":
                    raise AmsSettingsValidationError(f"AMS customer {rate.user_id} was not found")
        self.suppliers.get_settings()
        settings = self.db.execute(select(BillingSettings).where(BillingSettings.id == 1).with_for_update()).scalar_one()
        settings.ams_billing = config.model_dump(mode="json", by_alias=True) if config is not None else None
        settings.ams_billing_version += 1
        settings.updated_by_user_id = actor.id
        self.audit_logs.create(
            "update_ams_billing_settings",
            actor_user_id=actor.id,
            target_type="billing_settings",
            target_id="1",
            ip_address=get_request_ip(request),
            user_agent=get_request_user_agent(request),
            metadata={
                "version": settings.ams_billing_version,
                "enabled": config is not None,
                "customerRateCount": len(config.customer_rates) if config is not None else 0,
                "taxHandlingFeeEur": str(config.tax_handling_fee_eur) if config is not None else "0.00",
            },
        )
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return self.get()
