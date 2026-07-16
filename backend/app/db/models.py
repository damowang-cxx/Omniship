import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    current_version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    versions: Mapped[list["SupplierVersion"]] = relationship(
        back_populates="supplier", cascade="all, delete-orphan"
    )


class SupplierVersion(Base):
    __tablename__ = "supplier_versions"
    __table_args__ = (
        UniqueConstraint("supplier_id", "version_number", name="uq_supplier_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    config: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    supplier: Mapped[Supplier] = relationship(back_populates="versions")


class BillingSettings(Base):
    __tablename__ = "billing_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    unit_tax_eur: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("3.00")
    )
    taxable_airports: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=lambda: ["AMS"]
    )
    tax_effective_date: Mapped[date] = mapped_column(
        Date, nullable=False, default=date(2026, 7, 1)
    )
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class WaybillUpload(Base):
    __tablename__ = "waybill_uploads"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    uploaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    supplier_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("supplier_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    shipment_type: Mapped[str] = mapped_column(String(20), nullable=False)
    air_waybill_number: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_air_waybill_number: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )
    gross_weight_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    pieces: Mapped[int] = mapped_column(Integer, nullable=False)
    arrival_flight_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    airport_of_departure: Mapped[str | None] = mapped_column(String(120), nullable=True)
    airport_of_arrival: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending_review")
    validation_issue_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    validation_issues: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    user: Mapped["User"] = relationship(
        foreign_keys=[user_id],
        back_populates="waybill_uploads",
    )
    uploaded_by: Mapped["User | None"] = relationship(foreign_keys=[uploaded_by_user_id])
    reviewed_by: Mapped["User | None"] = relationship(foreign_keys=[reviewed_by_user_id])
    supplier: Mapped[Supplier] = relationship(foreign_keys=[supplier_id])
    supplier_version: Mapped[SupplierVersion] = relationship(
        foreign_keys=[supplier_version_id]
    )
    files: Mapped[list["WaybillUploadFile"]] = relationship(
        back_populates="upload", cascade="all, delete-orphan"
    )
    tracking_record: Mapped["WaybillTrackingRecord | None"] = relationship(
        back_populates="upload", cascade="all, delete-orphan", uselist=False
    )
    billing_entry: Mapped["BillingEntry | None"] = relationship(
        back_populates="waybill_upload", uselist=False
    )

    @property
    def supplier_name(self) -> str | None:
        return self.supplier.name if self.supplier else None

    @property
    def supplier_version_number(self) -> int | None:
        return self.supplier_version.version_number if self.supplier_version else None


class WaybillTrackingRecord(Base):
    __tablename__ = "waybill_tracking_records"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    upload_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("waybill_uploads.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    public_code: Mapped[str] = mapped_column(
        String(8), nullable=False, unique=True, index=True
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="created")
    status_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    received_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    received_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    in_warehouse_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pallet_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fyco_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    released_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    outbound_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    noa_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    collection_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    scanned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    customs_clearance_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    outbound_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    upload: Mapped["WaybillUpload"] = relationship(back_populates="tracking_record")
    user: Mapped["User"] = relationship()
    pod_files: Mapped[list["WaybillPodFile"]] = relationship(
        back_populates="tracking_record",
        cascade="all, delete-orphan",
        order_by="WaybillPodFile.created_at",
    )
    parcels: Mapped[list["WaybillParcel"]] = relationship(
        back_populates="tracking_record",
        cascade="all, delete-orphan",
        order_by="WaybillParcel.parcel_unit_number",
    )


class WaybillUploadFile(Base):
    __tablename__ = "waybill_upload_files"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    upload_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("waybill_uploads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    upload: Mapped["WaybillUpload"] = relationship(back_populates="files")


class WaybillPodFile(Base):
    __tablename__ = "waybill_pod_files"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tracking_record_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("waybill_tracking_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    uploaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    tracking_record: Mapped["WaybillTrackingRecord"] = relationship(
        back_populates="pod_files"
    )
    uploaded_by: Mapped["User | None"] = relationship(
        foreign_keys=[uploaded_by_user_id]
    )


class WaybillParcel(Base):
    __tablename__ = "waybill_parcels"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tracking_record_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("waybill_tracking_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parcel_unit_number: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="created")
    number_of_items: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    destination_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    destination_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    destination_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    inbound: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    outbound: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    special_instruction: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    tracking_record: Mapped["WaybillTrackingRecord"] = relationship(
        back_populates="parcels"
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    username: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="user")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    balance: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00"), server_default="0"
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    created_by: Mapped["User | None"] = relationship(remote_side=[id])
    sessions: Mapped[list["UserSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    waybill_uploads: Mapped[list["WaybillUpload"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="WaybillUpload.user_id",
    )
    billing_entries: Mapped[list["BillingEntry"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="BillingEntry.user_id",
    )


class BillingEntry(Base):
    __tablename__ = "billing_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entry_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    balance_after: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    waybill_upload_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("waybill_uploads.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
        index=True,
    )
    waybill_number: Mapped[str | None] = mapped_column(String(255), nullable=True)
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True
    )
    supplier_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    supplier_version_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    arrival_airport: Mapped[str | None] = mapped_column(String(3), nullable=True)
    billable_unit_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unit_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    billing_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    receipt_original_filename: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    receipt_storage_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    receipt_content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    receipt_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    receipt_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    user: Mapped["User"] = relationship(
        back_populates="billing_entries", foreign_keys=[user_id]
    )
    created_by: Mapped["User | None"] = relationship(
        foreign_keys=[created_by_user_id]
    )
    waybill_upload: Mapped["WaybillUpload | None"] = relationship(
        back_populates="billing_entry"
    )


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_token_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped[User] = relationship(back_populates="sessions")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    target_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(80), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    audit_metadata: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    actor: Mapped[User | None] = relationship()
