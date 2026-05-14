import pytest
from sqlalchemy import select

from app.core.config import Settings
from app.db.models import AirWaybill, ScrapeRun
from app.repositories.scrape_run_repository import ScrapeRunRepository
from app.services.air_waybill_scheduler import AirWaybillAutoRefreshScheduler


class FakeSettings:
    omniship_username = "secret-user"
    omniship_password = "secret-pass"
    omniship_incremental_stop_after_unchanged = 10


class FakeIncrementalScraper:
    settings = FakeSettings()
    calls = 0

    async def scrape_air_waybill_summaries(self, **_kwargs):
        self.calls += 1
        return [
            {
                "number": "784-84063276",
                "status": "created",
                "weight_kg_raw": "12.50",
                "received_raw": "0 / 50",
                "parcels_raw": "92",
                "in_warehouse_raw": "0.00% (0)",
                "released_raw": "0.00% (0)",
                "outbound_raw": "0.00% (0)",
                "actions_raw": "View",
            }
        ]

    async def scrape_waybill_details(self, _rows):
        return []


class ExistingSessionFactory:
    def __init__(self, db_session):
        self.db_session = db_session

    def __call__(self):
        return self

    def __enter__(self):
        return self.db_session

    def __exit__(self, *_args):
        return None


def scheduler_settings() -> Settings:
    return Settings(
        air_waybill_auto_refresh_enabled=True,
        air_waybill_auto_refresh_interval_seconds=60,
        air_waybill_auto_refresh_initial_delay_seconds=3600,
    )


@pytest.mark.asyncio
async def test_scheduler_trigger_once_runs_incremental_refresh(db_session):
    scraper = FakeIncrementalScraper()
    scheduler = AirWaybillAutoRefreshScheduler(
        scheduler_settings(),
        session_factory=ExistingSessionFactory(db_session),
        scraper_factory=lambda: scraper,
    )

    result = await scheduler.trigger_once()

    assert result is not None
    assert result.status == "success"
    assert result.mode == "incremental"
    assert result.row_count == 1
    assert scraper.calls == 1
    waybill = db_session.execute(select(AirWaybill)).scalar_one()
    assert waybill.number == "784-84063276"


@pytest.mark.asyncio
async def test_scheduler_skips_when_refresh_is_already_running(db_session):
    ScrapeRunRepository(db_session).create_running(mode="incremental")
    db_session.commit()
    scraper = FakeIncrementalScraper()
    scheduler = AirWaybillAutoRefreshScheduler(
        scheduler_settings(),
        session_factory=ExistingSessionFactory(db_session),
        scraper_factory=lambda: scraper,
    )

    result = await scheduler.trigger_once()

    assert result is None
    assert scraper.calls == 0
    runs = db_session.execute(select(ScrapeRun)).scalars().all()
    assert len(runs) == 1
    assert runs[0].status == "running"
