import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
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


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_system: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    page_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    mode: Mapped[str] = mapped_column(String(30), nullable=False, default="incremental")
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inserted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    detail_failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    air_waybills: Mapped[list["AirWaybill"]] = relationship(
        back_populates="scrape_run",
        cascade="all, delete-orphan",
        foreign_keys="AirWaybill.scrape_run_id",
    )


class AirWaybill(Base):
    __tablename__ = "air_waybills"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scrape_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("scrape_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    number: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status_changed_at_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    weight_kg_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    received_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    parcels_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    in_warehouse_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    released_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    outbound_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actions_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_href: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    detail_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    last_summary_scraped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_detail_scraped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_scrape_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("scrape_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    detail_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    scrape_run: Mapped[ScrapeRun] = relationship(
        back_populates="air_waybills", foreign_keys=[scrape_run_id]
    )


class AirWaybillDetail(Base):
    __tablename__ = "air_waybill_details"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    waybill_number: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    waybill_status: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status_changed_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    uploaded_on_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    date_received_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    airline_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    incoming_flight_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    arrived_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ground_handler_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    broker_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    units_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    units_inbound_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    units_outbound_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pre_alert_weight_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gross_weight_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    odd_sized_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class AirWaybillDestination(Base):
    __tablename__ = "air_waybill_destinations"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    waybill_number: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    country: Mapped[str | None] = mapped_column(String(255), nullable=True)
    units_received_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    units_outbound_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    total_weight_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    released_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class WaybillUserBinding(Base):
    __tablename__ = "waybill_user_bindings"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "normalized_number",
            name="uq_waybill_user_bindings_user_normalized_number",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    number: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_number: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="upload")
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    user: Mapped["User"] = relationship(
        back_populates="waybill_bindings", foreign_keys=[user_id]
    )
    created_by: Mapped["User | None"] = relationship(
        foreign_keys=[created_by_user_id]
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
    platform: Mapped[str] = mapped_column(String(40), nullable=False, default="ALLINE")
    shipment_type: Mapped[str] = mapped_column(String(20), nullable=False)
    air_waybill_number: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_air_waybill_number: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )
    gross_weight_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    pieces: Mapped[int] = mapped_column(Integer, nullable=False)
    arrival_flight_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending_review")
    platform_submission_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending",
    )
    platform_submission_method: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="automated",
    )
    platform_submission_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    platform_submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
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
    files: Mapped[list["WaybillUploadFile"]] = relationship(
        back_populates="upload", cascade="all, delete-orphan"
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
    waybill_bindings: Mapped[list["WaybillUserBinding"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", foreign_keys="WaybillUserBinding.user_id"
    )
    waybill_uploads: Mapped[list["WaybillUpload"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="WaybillUpload.user_id",
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
