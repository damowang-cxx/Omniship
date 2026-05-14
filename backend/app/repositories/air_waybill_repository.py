from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import AirWaybill, AirWaybillDestination, AirWaybillDetail
from app.repositories.waybill_user_binding_repository import (
    WaybillUserBindingRepository,
    normalize_waybill_number,
)
from app.services.omniship_scraper import SUMMARY_HASH_FIELDS, build_summary_hash


SUMMARY_FIELDS = [
    "number",
    "status",
    "weight_kg_raw",
    "received_raw",
    "parcels_raw",
    "in_warehouse_raw",
    "released_raw",
    "outbound_raw",
    "actions_raw",
    "action_href",
]


class AirWaybillRepository:
    def __init__(self, db: Session):
        self.db = db

    def bulk_create(self, scrape_run_id: UUID, rows: list[dict]) -> list[AirWaybill]:
        scraped_at = datetime.now(timezone.utc)
        entities = [
            AirWaybill(
                scrape_run_id=scrape_run_id,
                number=row["number"],
                status=row.get("status"),
                status_changed_at_raw=row.get("status_changed_at_raw"),
                weight_kg_raw=row.get("weight_kg_raw"),
                received_raw=row.get("received_raw"),
                parcels_raw=row.get("parcels_raw"),
                in_warehouse_raw=row.get("in_warehouse_raw"),
                released_raw=row.get("released_raw"),
                outbound_raw=row.get("outbound_raw"),
                actions_raw=row.get("actions_raw"),
                action_href=row.get("action_href"),
                scraped_at=scraped_at,
            )
            for row in rows
        ]
        self.db.add_all(entities)
        self.db.flush()
        return entities

    def list_by_scrape_run(self, scrape_run_id: UUID) -> list[AirWaybill]:
        statement = (
            select(AirWaybill)
            .where(AirWaybill.scrape_run_id == scrape_run_id)
            .order_by(AirWaybill.created_at.asc(), AirWaybill.id.asc())
        )
        return list(self.db.execute(statement).scalars().all())

    def list_current(self) -> list[AirWaybill]:
        statement = select(AirWaybill).order_by(
            AirWaybill.last_seen_at.desc(),
            AirWaybill.created_at.desc(),
            AirWaybill.id.desc(),
        )
        rows = self.db.execute(statement).scalars().all()
        by_number: dict[str, AirWaybill] = {}
        for row in rows:
            by_number.setdefault(row.number, row)
        return list(by_number.values())

    def list_current_for_user(self, user_id: UUID) -> list[AirWaybill]:
        allowed_numbers = WaybillUserBindingRepository(
            self.db
        ).get_normalized_numbers_for_user(user_id)
        if not allowed_numbers:
            return []

        return [
            row
            for row in self.list_current()
            if normalize_waybill_number(row.number) in allowed_numbers
        ]

    def get_by_number(self, number: str) -> AirWaybill | None:
        statement = (
            select(AirWaybill)
            .where(AirWaybill.number == number)
            .order_by(
                AirWaybill.last_seen_at.desc(),
                AirWaybill.created_at.desc(),
                AirWaybill.id.desc(),
            )
            .limit(1)
        )
        return self.db.execute(statement).scalar_one_or_none()

    def user_can_access(self, *, user_id: UUID, number: str) -> bool:
        return WaybillUserBindingRepository(self.db).has_binding(
            user_id=user_id,
            number=number,
        )

    def get_summary_hashes(self) -> dict[str, str]:
        hashes: dict[str, str] = {}
        for row in self.list_current():
            hashes[row.number] = build_summary_hash(
                {
                    field: getattr(row, field, None)
                    for field in SUMMARY_HASH_FIELDS
                }
            )
        return hashes

    def upsert_summary(
        self,
        scrape_run_id: UUID,
        row: dict,
        summary_hash: str,
    ) -> tuple[AirWaybill, str]:
        now = datetime.now(timezone.utc)
        existing = self.get_by_number(row["number"])

        if existing is None:
            entity = AirWaybill(
                scrape_run_id=scrape_run_id,
                last_scrape_run_id=scrape_run_id,
                first_seen_at=now,
                last_seen_at=now,
                last_summary_scraped_at=now,
                scraped_at=now,
                summary_hash=summary_hash,
            )
            for field in SUMMARY_FIELDS:
                setattr(entity, field, row.get(field))
            self.db.add(entity)
            self.db.flush()
            return entity, "inserted"

        existing.last_seen_at = now
        existing.last_summary_scraped_at = now
        existing.last_scrape_run_id = scrape_run_id
        existing.scrape_run_id = scrape_run_id
        existing.scraped_at = now

        existing_hash = build_summary_hash(
            {field: getattr(existing, field, None) for field in SUMMARY_HASH_FIELDS}
        )

        if existing_hash == summary_hash:
            existing.actions_raw = row.get("actions_raw")
            existing.action_href = row.get("action_href")
            existing.summary_hash = summary_hash
            self.db.flush()
            return existing, "skipped"

        for field in SUMMARY_FIELDS:
            setattr(existing, field, row.get(field))
        existing.summary_hash = summary_hash
        existing.detail_error_message = None
        self.db.flush()
        return existing, "updated"

    def mark_detail_success(
        self, number: str, scrape_run_id: UUID, detail_hash: str
    ) -> AirWaybill | None:
        now = datetime.now(timezone.utc)
        row = self.get_by_number(number)
        if row is None:
            return None
        row.detail_hash = detail_hash
        row.detail_error_message = None
        row.last_detail_scraped_at = now
        row.last_scrape_run_id = scrape_run_id
        self.db.flush()
        return row

    def mark_detail_failure(
        self, number: str, scrape_run_id: UUID, error_message: str
    ) -> AirWaybill | None:
        row = self.get_by_number(number)
        if row is None:
            return None
        row.detail_error_message = error_message
        row.last_scrape_run_id = scrape_run_id
        self.db.flush()
        return row

    def upsert_detail(self, detail: dict) -> AirWaybillDetail:
        now = datetime.now(timezone.utc)
        number = detail["waybill_number"]
        statement = (
            select(AirWaybillDetail)
            .where(AirWaybillDetail.waybill_number == number)
            .limit(1)
        )
        entity = self.db.execute(statement).scalar_one_or_none()

        values = {
            key: value
            for key, value in detail.items()
            if key not in {"destinations"} and hasattr(AirWaybillDetail, key)
        }
        values["scraped_at"] = now

        if entity is None:
            entity = AirWaybillDetail(**values)
            self.db.add(entity)
        else:
            for key, value in values.items():
                setattr(entity, key, value)
            entity.updated_at = now

        self.db.flush()
        return entity

    def replace_destinations(
        self, waybill_number: str, destinations: list[dict]
    ) -> list[AirWaybillDestination]:
        now = datetime.now(timezone.utc)
        self.db.execute(
            delete(AirWaybillDestination).where(
                AirWaybillDestination.waybill_number == waybill_number
            )
        )
        entities = [
            AirWaybillDestination(
                waybill_number=waybill_number,
                name=destination["name"],
                country=destination.get("country"),
                units_received_raw=destination.get("units_received_raw"),
                units_outbound_raw=destination.get("units_outbound_raw"),
                total_weight_raw=destination.get("total_weight_raw"),
                released_raw=destination.get("released_raw"),
                sort_order=index,
                scraped_at=now,
            )
            for index, destination in enumerate(destinations)
        ]
        self.db.add_all(entities)
        self.db.flush()
        return entities

    def get_detail(self, number: str) -> AirWaybillDetail | None:
        statement = (
            select(AirWaybillDetail)
            .where(AirWaybillDetail.waybill_number == number)
            .limit(1)
        )
        return self.db.execute(statement).scalar_one_or_none()

    def list_destinations(self, number: str) -> list[AirWaybillDestination]:
        statement = (
            select(AirWaybillDestination)
            .where(AirWaybillDestination.waybill_number == number)
            .order_by(AirWaybillDestination.sort_order.asc())
        )
        return list(self.db.execute(statement).scalars().all())
