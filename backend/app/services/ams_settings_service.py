"""Read archived global AMS settings after pricing moved into templates."""
from sqlalchemy.orm import Session

from app.repositories.supplier_repository import SupplierRepository
from app.schemas.supplier import AmsBillingConfig, AmsBillingSettingsItem


class AmsSettingsService:
    def __init__(self, db: Session):
        self.suppliers = SupplierRepository(db)

    def get(self) -> AmsBillingSettingsItem:
        settings = self.suppliers.get_settings()
        return AmsBillingSettingsItem(
            config=AmsBillingConfig.model_validate(settings.ams_billing) if settings.ams_billing is not None else None,
            version=settings.ams_billing_version,
        )
