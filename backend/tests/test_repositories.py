from app.repositories.air_waybill_repository import AirWaybillRepository
from app.repositories.scrape_run_repository import ScrapeRunRepository


def test_create_success_run_and_query_latest_snapshot(db_session):
    run_repo = ScrapeRunRepository(db_session)
    waybill_repo = AirWaybillRepository(db_session)

    run = run_repo.create_running()
    waybill_repo.bulk_create(
        run.id,
        [
            {
                "number": "123456",
                "status": "Released",
                "status_changed_at_raw": "2026-05-10 18:22",
                "weight_kg_raw": "12.50",
                "received_raw": "Yes",
                "parcels_raw": "68 / 68",
                "in_warehouse_raw": "Yes",
                "released_raw": "Yes",
                "outbound_raw": "No",
                "actions_raw": "View",
            }
        ],
    )
    run_repo.mark_success(run.id, 1)
    db_session.commit()

    latest_run = run_repo.get_latest_success()
    assert latest_run is not None
    assert latest_run.status == "success"
    assert latest_run.row_count == 1

    rows = waybill_repo.list_by_scrape_run(latest_run.id)
    assert len(rows) == 1
    assert rows[0].number == "123456"
    assert rows[0].parcels_raw == "68 / 68"
