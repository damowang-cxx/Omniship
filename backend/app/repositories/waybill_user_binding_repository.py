import re
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import WaybillUserBinding


def normalize_waybill_number(number: str) -> str:
    return re.sub(r"[-\s]", "", number.strip().lower())


class WaybillUserBindingRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_normalized_numbers_for_user(self, user_id: UUID) -> set[str]:
        statement = select(WaybillUserBinding.normalized_number).where(
            WaybillUserBinding.user_id == user_id
        )
        return {
            normalized
            for normalized in self.db.execute(statement).scalars().all()
            if normalized
        }

    def has_binding(self, *, user_id: UUID, number: str) -> bool:
        normalized = normalize_waybill_number(number)
        if not normalized:
            return False

        statement = (
            select(WaybillUserBinding.id)
            .where(
                WaybillUserBinding.user_id == user_id,
                WaybillUserBinding.normalized_number == normalized,
            )
            .limit(1)
        )
        return self.db.execute(statement).scalar_one_or_none() is not None

    def has_any_binding(self, number: str) -> bool:
        normalized = normalize_waybill_number(number)
        if not normalized:
            return False

        return self.get_any_binding(number) is not None

    def get_any_binding(self, number: str) -> WaybillUserBinding | None:
        normalized = normalize_waybill_number(number)
        if not normalized:
            return None

        statement = (
            select(WaybillUserBinding)
            .where(WaybillUserBinding.normalized_number == normalized)
            .limit(1)
        )
        return self.db.execute(statement).scalar_one_or_none()

    def create_many(
        self,
        *,
        user_id: UUID,
        numbers: list[str],
        created_by_user_id: UUID | None,
        source: str = "upload",
    ) -> tuple[list[WaybillUserBinding], int]:
        existing = self.get_normalized_numbers_for_user(user_id)
        seen: set[str] = set()
        created: list[WaybillUserBinding] = []
        skipped_count = 0

        for raw_number in numbers:
            number = raw_number.strip()
            normalized = normalize_waybill_number(number)
            if not number or not normalized:
                skipped_count += 1
                continue
            if normalized in existing or normalized in seen:
                skipped_count += 1
                continue

            seen.add(normalized)
            binding = WaybillUserBinding(
                user_id=user_id,
                number=number,
                normalized_number=normalized,
                source=source,
                created_by_user_id=created_by_user_id,
            )
            self.db.add(binding)
            created.append(binding)

        self.db.flush()
        return created, skipped_count

    def delete_for_user_number_source(
        self,
        *,
        user_id: UUID,
        number: str,
        source: str,
    ) -> int:
        normalized = normalize_waybill_number(number)
        if not normalized:
            return 0

        result = self.db.execute(
            delete(WaybillUserBinding).where(
                WaybillUserBinding.user_id == user_id,
                WaybillUserBinding.normalized_number == normalized,
                WaybillUserBinding.source == source,
            )
        )
        self.db.flush()
        return int(result.rowcount or 0)
