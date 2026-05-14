import asyncio
import logging
from contextlib import suppress
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import SessionLocal
from app.repositories.scrape_run_repository import ScrapeRunRepository
from app.schemas.scrape_run import ScrapeRunSummary
from app.services.air_waybill_service import AirWaybillService
from app.services.omniship_scraper import OmnishipScraper


logger = logging.getLogger(__name__)


class AirWaybillAutoRefreshScheduler:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        session_factory: Callable[[], Session] = SessionLocal,
        scraper_factory: Callable[[], OmnishipScraper] = OmnishipScraper,
    ):
        self.settings = settings or get_settings()
        self.session_factory = session_factory
        self.scraper_factory = scraper_factory
        self._task: asyncio.Task | None = None
        self._stop_event: asyncio.Event | None = None

    async def start(self) -> None:
        if not self.settings.air_waybill_auto_refresh_enabled:
            logger.info("Air Waybill automatic hourly refresh is disabled")
            return
        if self._task and not self._task.done():
            return

        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "Air Waybill automatic refresh scheduled every %s seconds",
            self._interval_seconds,
        )

    async def stop(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
        self._task = None
        self._stop_event = None

    async def trigger_once(self) -> ScrapeRunSummary | None:
        with self.session_factory() as db:
            running_run = ScrapeRunRepository(db).get_latest_running()
            if running_run is not None:
                logger.info(
                    "Skipping automatic Air Waybill refresh because run %s is still running",
                    running_run.id,
                )
                return None

            service = AirWaybillService(db=db, scraper=self.scraper_factory())
            run = service.create_refresh_run("incremental")
            logger.info("Automatic Air Waybill refresh started: %s", run.run_id)
            result = await service.run_refresh(run.run_id, "incremental")
            logger.info(
                "Automatic Air Waybill refresh finished: %s status=%s rows=%s",
                result.run_id,
                result.status,
                result.row_count,
            )
            return result

    async def _run_loop(self) -> None:
        stop_event = self._stop_event
        if stop_event is None:
            return

        await self._wait_or_stop(self._initial_delay_seconds)
        while not stop_event.is_set():
            try:
                await self.trigger_once()
            except Exception:
                logger.exception("Automatic Air Waybill refresh failed unexpectedly")

            await self._wait_or_stop(self._interval_seconds)

    async def _wait_or_stop(self, seconds: int) -> None:
        stop_event = self._stop_event
        if stop_event is None or seconds <= 0:
            return

        with suppress(asyncio.TimeoutError):
            await asyncio.wait_for(stop_event.wait(), timeout=seconds)

    @property
    def _interval_seconds(self) -> int:
        return max(60, self.settings.air_waybill_auto_refresh_interval_seconds)

    @property
    def _initial_delay_seconds(self) -> int:
        return max(0, self.settings.air_waybill_auto_refresh_initial_delay_seconds)
