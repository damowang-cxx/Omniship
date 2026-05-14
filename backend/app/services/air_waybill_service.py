from sqlalchemy.orm import Session

from app.db.models import User
from app.db.session import SessionLocal
from app.repositories.air_waybill_repository import AirWaybillRepository
from app.repositories.scrape_run_repository import ScrapeRunRepository
from app.schemas.air_waybill import (
    AirWaybillDestinationItem,
    AirWaybillDetailItem,
    AirWaybillDetailResponse,
    AirWaybillItem,
    AirWaybillLatestResponse,
)
from app.schemas.scrape_run import ScrapeRunSummary, ScrapeStatusResponse
from app.services.omniship_scraper import (
    OmnishipScraper,
    build_detail_hash,
    build_summary_hash,
)


def sanitize_error_message(message: str, secrets: list[str]) -> str:
    sanitized = message
    for secret in secrets:
        if secret:
            sanitized = sanitized.replace(secret, "[redacted]")
    return sanitized


def summarize_run(run) -> ScrapeRunSummary:
    return ScrapeRunSummary(
        run_id=run.id,
        status=run.status,
        mode=run.mode,
        row_count=run.row_count,
        total_count=run.total_count,
        processed_count=run.processed_count,
        inserted_count=run.inserted_count,
        updated_count=run.updated_count,
        skipped_count=run.skipped_count,
        detail_failed_count=run.detail_failed_count,
        started_at=run.started_at,
        finished_at=run.finished_at,
        error_message=run.error_message,
    )


class AirWaybillService:
    def __init__(self, db: Session, scraper: OmnishipScraper):
        self.db = db
        self.scraper = scraper
        self.runs = ScrapeRunRepository(db)
        self.air_waybills = AirWaybillRepository(db)

    async def scrape(self) -> ScrapeRunSummary:
        run = self.runs.create_running()
        self.db.commit()
        self.db.refresh(run)
        run_id = run.id

        try:
            rows = await self.scraper.scrape_air_waybills()
            self.air_waybills.bulk_create(run_id, rows)
            run = self.runs.mark_success(run_id, len(rows))
            self.db.commit()
            self.db.refresh(run)
            return summarize_run(run)
        except Exception as exc:
            self.db.rollback()
            error_message = sanitize_error_message(
                str(exc),
                [
                    self.scraper.settings.omniship_username,
                    self.scraper.settings.omniship_password,
                ],
            )
            run = self.runs.mark_failed(run_id, error_message)
            self.db.commit()
            self.db.refresh(run)
            return summarize_run(run)

    def get_latest_success(self, current_user: User) -> AirWaybillLatestResponse:
        run = self.runs.get_latest_success()
        if run is None:
            return AirWaybillLatestResponse(latest_run=None, items=[])

        rows = (
            self.air_waybills.list_current()
            if current_user.role == "admin"
            else self.air_waybills.list_current_for_user(current_user.id)
        )
        return AirWaybillLatestResponse(
            latest_run=summarize_run(run),
            items=[AirWaybillItem.model_validate(row) for row in rows],
        )

    def get_latest_status(self) -> ScrapeStatusResponse:
        run = self.runs.get_latest()
        return ScrapeStatusResponse(latest_run=summarize_run(run) if run else None)

    def create_refresh_run(self, mode: str) -> ScrapeRunSummary:
        run = self.runs.create_running(mode=mode)
        self.db.commit()
        self.db.refresh(run)
        return summarize_run(run)

    def get_run(self, run_id) -> ScrapeRunSummary:
        return summarize_run(self.runs.get_by_id(run_id))

    async def run_refresh(self, run_id, mode: str) -> ScrapeRunSummary:
        inserted_count = 0
        updated_count = 0
        skipped_count = 0
        detail_failed_count = 0
        processed_count = 0
        total_count = 0

        try:
            existing_hashes = (
                {} if mode == "full" else self.air_waybills.get_summary_hashes()
            )
            rows = await self.scraper.scrape_air_waybill_summaries(
                mode=mode,
                existing_hashes=existing_hashes,
                stop_after_unchanged=getattr(
                    self.scraper.settings,
                    "omniship_incremental_stop_after_unchanged",
                    30,
                ),
            )
            rows = self._dedupe_rows(rows)
            details_to_fetch: list[dict] = []
            total_count = len(rows)
            self.runs.update_progress(run_id, total_count=total_count, row_count=len(rows))
            self.db.commit()

            for row in rows:
                summary_hash = build_summary_hash(row)
                entity, action = self.air_waybills.upsert_summary(
                    run_id, row, summary_hash
                )
                if action == "inserted":
                    inserted_count += 1
                elif action == "updated":
                    updated_count += 1
                else:
                    skipped_count += 1

                if mode == "full" or action in {"inserted", "updated"} or not entity.detail_hash:
                    details_to_fetch.append(row)

                processed_count += 1
                if processed_count % 25 == 0:
                    self.runs.update_progress(
                        run_id,
                        processed_count=processed_count,
                        inserted_count=inserted_count,
                        updated_count=updated_count,
                        skipped_count=skipped_count,
                    )
                    self.db.commit()

            total_count += len(details_to_fetch)
            self.runs.update_progress(
                run_id,
                total_count=total_count,
                processed_count=processed_count,
                inserted_count=inserted_count,
                updated_count=updated_count,
                skipped_count=skipped_count,
            )
            self.db.commit()

            if details_to_fetch:
                detail_results = await self.scraper.scrape_waybill_details(details_to_fetch)
                for result in detail_results:
                    number = result["number"]
                    if result.get("error") or not result.get("detail"):
                        detail_failed_count += 1
                        self.air_waybills.mark_detail_failure(
                            number,
                            run_id,
                            sanitize_error_message(
                                result.get("error") or "Detail scrape failed",
                                [
                                    self.scraper.settings.omniship_username,
                                    self.scraper.settings.omniship_password,
                                ],
                            ),
                        )
                    else:
                        detail = result["detail"]
                        detail_hash = build_detail_hash(detail)
                        self.air_waybills.upsert_detail(detail)
                        self.air_waybills.replace_destinations(
                            detail["waybill_number"], detail.get("destinations", [])
                        )
                        self.air_waybills.mark_detail_success(
                            detail["waybill_number"], run_id, detail_hash
                        )

                    processed_count += 1
                    if processed_count % 10 == 0:
                        self.runs.update_progress(
                            run_id,
                            processed_count=processed_count,
                            detail_failed_count=detail_failed_count,
                        )
                        self.db.commit()

            run = self.runs.mark_success(
                run_id,
                len(rows),
                total_count=total_count,
                processed_count=total_count,
                inserted_count=inserted_count,
                updated_count=updated_count,
                skipped_count=skipped_count,
                detail_failed_count=detail_failed_count,
            )
            self.db.commit()
            self.db.refresh(run)
            return summarize_run(run)
        except Exception as exc:
            self.db.rollback()
            error_message = sanitize_error_message(
                str(exc),
                [
                    self.scraper.settings.omniship_username,
                    self.scraper.settings.omniship_password,
                ],
            )
            run = self.runs.mark_failed(run_id, error_message)
            self.db.commit()
            self.db.refresh(run)
            return summarize_run(run)

    def get_detail(
        self, number: str, current_user: User
    ) -> AirWaybillDetailResponse | None:
        summary = self.air_waybills.get_by_number(number)
        if summary is None:
            return None
        if current_user.role != "admin" and not self.air_waybills.user_can_access(
            user_id=current_user.id,
            number=summary.number,
        ):
            return None

        detail = self.air_waybills.get_detail(summary.number)
        destinations = self.air_waybills.list_destinations(summary.number)
        return AirWaybillDetailResponse(
            summary=AirWaybillItem.model_validate(summary),
            detail=AirWaybillDetailItem.model_validate(detail) if detail else None,
            destinations=[
                AirWaybillDestinationItem.model_validate(destination)
                for destination in destinations
            ],
        )

    def _dedupe_rows(self, rows: list[dict]) -> list[dict]:
        seen: set[str] = set()
        unique_rows: list[dict] = []
        for row in rows:
            number = row.get("number")
            if not number or number in seen:
                continue
            seen.add(number)
            unique_rows.append(row)
        return unique_rows


def run_air_waybill_refresh_task(run_id, mode: str) -> None:
    with SessionLocal() as db:
        service = AirWaybillService(db=db, scraper=OmnishipScraper())
        import asyncio

        asyncio.run(service.run_refresh(run_id, mode))
