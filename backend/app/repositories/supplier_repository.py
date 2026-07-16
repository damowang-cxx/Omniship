from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import BillingSettings, Supplier, SupplierVersion
from app.services.supplier_defaults import QLS_CONFIG, QLS_SUPPLIER_ID, QLS_VERSION_ID


class SupplierRepository:
    def __init__(self, db: Session):
        self.db = db

    def ensure_defaults(self) -> None:
        if self.db.get(Supplier, QLS_SUPPLIER_ID) is None:
            supplier = Supplier(
                id=QLS_SUPPLIER_ID,
                name="QLS",
                status="active",
                current_version_number=1,
            )
            self.db.add(supplier)
            self.db.flush()
            self.db.add(
                SupplierVersion(
                    id=QLS_VERSION_ID,
                    supplier_id=supplier.id,
                    version_number=1,
                    config=QLS_CONFIG,
                )
            )
        if self.db.get(BillingSettings, 1) is None:
            self.db.add(
                BillingSettings(
                    id=1,
                    unit_tax_eur=Decimal("3.00"),
                    taxable_airports=["AMS"],
                    tax_effective_date=date(2026, 7, 1),
                )
            )
        self.db.flush()

    def list(self, *, include_inactive: bool) -> list[Supplier]:
        statement = select(Supplier)
        if not include_inactive:
            statement = statement.where(Supplier.status == "active")
        statement = statement.order_by(Supplier.name.asc())
        return list(self.db.execute(statement).scalars().all())

    def get(self, supplier_id: UUID) -> Supplier | None:
        return self.db.get(Supplier, supplier_id)

    def get_by_name(self, name: str) -> Supplier | None:
        statement = select(Supplier).where(
            func.lower(Supplier.name) == name.strip().lower()
        )
        return self.db.execute(statement).scalar_one_or_none()

    def get_current_version(self, supplier: Supplier) -> SupplierVersion | None:
        statement = select(SupplierVersion).where(
            SupplierVersion.supplier_id == supplier.id,
            SupplierVersion.version_number == supplier.current_version_number,
        )
        return self.db.execute(statement).scalar_one_or_none()

    def get_version(self, version_id: UUID) -> SupplierVersion | None:
        return self.db.get(SupplierVersion, version_id)

    def create(
        self,
        *,
        name: str,
        config: dict,
        created_by_user_id: UUID,
    ) -> tuple[Supplier, SupplierVersion]:
        supplier = Supplier(
            name=name.strip(),
            status="active",
            current_version_number=1,
            created_by_user_id=created_by_user_id,
        )
        self.db.add(supplier)
        self.db.flush()
        version = SupplierVersion(
            supplier_id=supplier.id,
            version_number=1,
            config=config,
            created_by_user_id=created_by_user_id,
        )
        self.db.add(version)
        self.db.flush()
        return supplier, version

    def publish_version(
        self,
        *,
        supplier: Supplier,
        config: dict,
        created_by_user_id: UUID,
    ) -> SupplierVersion:
        next_version = supplier.current_version_number + 1
        version = SupplierVersion(
            supplier_id=supplier.id,
            version_number=next_version,
            config=config,
            created_by_user_id=created_by_user_id,
        )
        supplier.current_version_number = next_version
        self.db.add(version)
        self.db.flush()
        return version

    def get_settings(self) -> BillingSettings:
        settings = self.db.get(BillingSettings, 1)
        if settings is None:
            self.ensure_defaults()
            settings = self.db.get(BillingSettings, 1)
        assert settings is not None
        return settings
