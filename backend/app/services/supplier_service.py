from uuid import UUID

from fastapi import Request
from sqlalchemy.orm import Session

from app.db.models import Supplier, SupplierVersion, User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.supplier_repository import SupplierRepository
from app.schemas.supplier import (
    BillingSettingsItem,
    BillingSettingsUpdateRequest,
    SupplierItem,
    SupplierVersionConfig,
    SupplierVersionItem,
)
from app.services.request_context import get_request_ip, get_request_user_agent


class SupplierValidationError(ValueError):
    pass


class SupplierService:
    def __init__(self, db: Session):
        self.db = db
        self.suppliers = SupplierRepository(db)
        self.audit_logs = AuditLogRepository(db)

    def list_suppliers(self, *, actor: User) -> list[SupplierItem]:
        self.suppliers.ensure_defaults()
        suppliers = self.suppliers.list(include_inactive=actor.role == "admin")
        return [self._build_item(supplier) for supplier in suppliers]

    def create_supplier(
        self,
        *,
        actor: User,
        name: str,
        config: SupplierVersionConfig,
        request: Request,
    ) -> SupplierItem:
        if self.suppliers.get_by_name(name) is not None:
            raise SupplierValidationError("Supplier name already exists")
        supplier, _ = self.suppliers.create(
            name=name,
            config=config.model_dump(mode="json", by_alias=True),
            created_by_user_id=actor.id,
        )
        self._audit(
            action="create_supplier",
            actor=actor,
            supplier=supplier,
            request=request,
            metadata={"name": supplier.name, "version": 1},
        )
        self.db.commit()
        self.db.refresh(supplier)
        return self._build_item(supplier)

    def publish_version(
        self,
        *,
        actor: User,
        supplier_id: UUID,
        config: SupplierVersionConfig,
        request: Request,
    ) -> SupplierItem:
        supplier = self._get_supplier(supplier_id)
        version = self.suppliers.publish_version(
            supplier=supplier,
            config=config.model_dump(mode="json", by_alias=True),
            created_by_user_id=actor.id,
        )
        self._audit(
            action="publish_supplier_version",
            actor=actor,
            supplier=supplier,
            request=request,
            metadata={"name": supplier.name, "version": version.version_number},
        )
        self.db.commit()
        self.db.refresh(supplier)
        return self._build_item(supplier)

    def update_supplier(
        self,
        *,
        actor: User,
        supplier_id: UUID,
        name: str | None,
        status: str | None,
        request: Request,
    ) -> SupplierItem:
        supplier = self._get_supplier(supplier_id)
        if name is not None and name.strip().lower() != supplier.name.lower():
            existing = self.suppliers.get_by_name(name)
            if existing is not None and existing.id != supplier.id:
                raise SupplierValidationError("Supplier name already exists")
            supplier.name = name.strip()
        if status is not None:
            supplier.status = status
        self._audit(
            action="update_supplier",
            actor=actor,
            supplier=supplier,
            request=request,
            metadata={"name": supplier.name, "status": supplier.status},
        )
        self.db.commit()
        self.db.refresh(supplier)
        return self._build_item(supplier)

    def get_settings(self) -> BillingSettingsItem:
        self.suppliers.ensure_defaults()
        return BillingSettingsItem.model_validate(self.suppliers.get_settings())

    def update_settings(
        self,
        *,
        actor: User,
        payload: BillingSettingsUpdateRequest,
        request: Request,
    ) -> BillingSettingsItem:
        settings = self.suppliers.get_settings()
        settings.unit_tax_eur = payload.unit_tax_eur
        settings.taxable_airports = payload.taxable_airports
        if payload.tax_effective_date is not None:
            settings.tax_effective_date = payload.tax_effective_date
        settings.updated_by_user_id = actor.id
        self.audit_logs.create(
            "update_billing_settings",
            actor_user_id=actor.id,
            target_type="billing_settings",
            target_id="1",
            ip_address=get_request_ip(request),
            user_agent=get_request_user_agent(request),
            metadata={
                "unitTaxEur": str(payload.unit_tax_eur),
                "taxableAirports": payload.taxable_airports,
                "taxEffectiveDate": settings.tax_effective_date.isoformat(),
            },
        )
        self.db.commit()
        self.db.refresh(settings)
        return BillingSettingsItem.model_validate(settings)

    def _get_supplier(self, supplier_id: UUID) -> Supplier:
        supplier = self.suppliers.get(supplier_id)
        if supplier is None:
            raise SupplierValidationError("Supplier not found")
        return supplier

    def _build_item(self, supplier: Supplier) -> SupplierItem:
        version = self.suppliers.get_current_version(supplier)
        if version is None:
            raise SupplierValidationError("Supplier version not found")
        return SupplierItem(
            id=supplier.id,
            name=supplier.name,
            status=supplier.status,
            current_version_number=supplier.current_version_number,
            current_version=self._build_version(version),
            created_at=supplier.created_at,
            updated_at=supplier.updated_at,
        )

    def _build_version(self, version: SupplierVersion) -> SupplierVersionItem:
        return SupplierVersionItem(
            id=version.id,
            version_number=version.version_number,
            config=SupplierVersionConfig.model_validate(version.config),
            created_by_user_id=version.created_by_user_id,
            created_at=version.created_at,
        )

    def _audit(
        self,
        *,
        action: str,
        actor: User,
        supplier: Supplier,
        request: Request,
        metadata: dict,
    ) -> None:
        self.audit_logs.create(
            action,
            actor_user_id=actor.id,
            target_type="supplier",
            target_id=str(supplier.id),
            ip_address=get_request_ip(request),
            user_agent=get_request_user_agent(request),
            metadata=metadata,
        )
