from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ScrapeRun


class ScrapeRunRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_running(
        self,
        source_system: str = "omniship",
        page_name: str = "air_waybills",
        mode: str = "incremental",
    ) -> ScrapeRun:
        run = ScrapeRun(
            source_system=source_system,
            page_name=page_name,
            started_at=datetime.now(timezone.utc),
            status="running",
            mode=mode,
            row_count=0,
        )
        self.db.add(run)
        self.db.flush()
        return run

    def update_progress(
        self,
        run_id: UUID,
        *,
        total_count: int | None = None,
        processed_count: int | None = None,
        inserted_count: int | None = None,
        updated_count: int | None = None,
        skipped_count: int | None = None,
        detail_failed_count: int | None = None,
        row_count: int | None = None,
    ) -> ScrapeRun:
        run = self.get_by_id(run_id)
        updates = {
            "total_count": total_count,
            "processed_count": processed_count,
            "inserted_count": inserted_count,
            "updated_count": updated_count,
            "skipped_count": skipped_count,
            "detail_failed_count": detail_failed_count,
            "row_count": row_count,
        }
        for field, value in updates.items():
            if value is not None:
                setattr(run, field, value)
        self.db.flush()
        return run

    def mark_success(
        self,
        run_id: UUID,
        row_count: int,
        *,
        total_count: int | None = None,
        processed_count: int | None = None,
        inserted_count: int | None = None,
        updated_count: int | None = None,
        skipped_count: int | None = None,
        detail_failed_count: int | None = None,
    ) -> ScrapeRun:
        run = self.get_by_id(run_id)
        run.status = "success"
        run.row_count = row_count
        if total_count is not None:
            run.total_count = total_count
        if processed_count is not None:
            run.processed_count = processed_count
        if inserted_count is not None:
            run.inserted_count = inserted_count
        if updated_count is not None:
            run.updated_count = updated_count
        if skipped_count is not None:
            run.skipped_count = skipped_count
        if detail_failed_count is not None:
            run.detail_failed_count = detail_failed_count
        run.finished_at = datetime.now(timezone.utc)
        run.error_message = None
        self.db.flush()
        return run

    def mark_failed(
        self,
        run_id: UUID,
        error_message: str,
        *,
        row_count: int | None = None,
    ) -> ScrapeRun:
        run = self.get_by_id(run_id)
        run.status = "failed"
        run.row_count = 0 if row_count is None else row_count
        run.finished_at = datetime.now(timezone.utc)
        run.error_message = error_message
        self.db.flush()
        return run

    def get_by_id(self, run_id: UUID) -> ScrapeRun:
        run = self.db.get(ScrapeRun, run_id)
        if run is None:
            raise ValueError(f"Scrape run not found: {run_id}")
        return run

    def get_latest_success(
        self, source_system: str = "omniship", page_name: str = "air_waybills"
    ) -> ScrapeRun | None:
        statement = (
            select(ScrapeRun)
            .where(
                ScrapeRun.source_system == source_system,
                ScrapeRun.page_name == page_name,
                ScrapeRun.status == "success",
            )
            .order_by(ScrapeRun.finished_at.desc(), ScrapeRun.created_at.desc())
            .limit(1)
        )
        return self.db.execute(statement).scalar_one_or_none()

    def get_latest(
        self, source_system: str = "omniship", page_name: str = "air_waybills"
    ) -> ScrapeRun | None:
        statement = (
            select(ScrapeRun)
            .where(
                ScrapeRun.source_system == source_system,
                ScrapeRun.page_name == page_name,
            )
            .order_by(ScrapeRun.created_at.desc())
            .limit(1)
        )
        return self.db.execute(statement).scalar_one_or_none()

    def get_latest_running(
        self, source_system: str = "omniship", page_name: str = "air_waybills"
    ) -> ScrapeRun | None:
        statement = (
            select(ScrapeRun)
            .where(
                ScrapeRun.source_system == source_system,
                ScrapeRun.page_name == page_name,
                ScrapeRun.status == "running",
            )
            .order_by(ScrapeRun.created_at.desc())
            .limit(1)
        )
        return self.db.execute(statement).scalar_one_or_none()
