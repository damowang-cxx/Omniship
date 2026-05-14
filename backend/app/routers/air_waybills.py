from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, require_admin
from app.db.models import User
from app.db.session import get_db
from app.repositories.audit_log_repository import AuditLogRepository
from app.schemas.air_waybill import AirWaybillDetailResponse, AirWaybillLatestResponse
from app.schemas.scrape_run import ScrapeRunSummary, ScrapeStatusResponse
from app.services.air_waybill_service import (
    AirWaybillService,
    run_air_waybill_refresh_task,
)
from app.services.omniship_scraper import OmnishipScraper
from app.services.request_context import get_request_ip, get_request_user_agent


router = APIRouter(prefix="/api/v1/air-waybills", tags=["air-waybills"])


def get_scraper() -> OmnishipScraper:
    return OmnishipScraper()


def get_air_waybill_service(
    db: Session = Depends(get_db),
    scraper: OmnishipScraper = Depends(get_scraper),
) -> AirWaybillService:
    return AirWaybillService(db=db, scraper=scraper)


@router.post("/scrape", response_model=ScrapeRunSummary)
async def scrape_air_waybills(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
    service: AirWaybillService = Depends(get_air_waybill_service),
) -> ScrapeRunSummary:
    result = await service.scrape()
    AuditLogRepository(db).create(
        "trigger_scrape",
        actor_user_id=current_user.id,
        target_type="air_waybills",
        target_id=str(result.run_id),
        ip_address=get_request_ip(request),
        user_agent=get_request_user_agent(request),
        metadata={"status": result.status, "rowCount": result.row_count},
    )
    db.commit()
    return result


def create_refresh_response(
    *,
    mode: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session,
    current_user: User,
    service: AirWaybillService,
) -> ScrapeRunSummary:
    result = service.create_refresh_run(mode)
    AuditLogRepository(db).create(
        "trigger_scrape",
        actor_user_id=current_user.id,
        target_type="air_waybills",
        target_id=str(result.run_id),
        ip_address=get_request_ip(request),
        user_agent=get_request_user_agent(request),
        metadata={
            "mode": mode,
            "status": result.status,
            "rowCount": result.row_count,
        },
    )
    db.commit()
    background_tasks.add_task(run_air_waybill_refresh_task, result.run_id, mode)
    return result


@router.post("/refresh", response_model=ScrapeRunSummary)
def refresh_air_waybills(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
    service: AirWaybillService = Depends(get_air_waybill_service),
) -> ScrapeRunSummary:
    return create_refresh_response(
        mode="incremental",
        request=request,
        background_tasks=background_tasks,
        db=db,
        current_user=current_user,
        service=service,
    )


@router.post("/full-refresh", response_model=ScrapeRunSummary)
def full_refresh_air_waybills(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
    service: AirWaybillService = Depends(get_air_waybill_service),
) -> ScrapeRunSummary:
    return create_refresh_response(
        mode="full",
        request=request,
        background_tasks=background_tasks,
        db=db,
        current_user=current_user,
        service=service,
    )


@router.get("/latest", response_model=AirWaybillLatestResponse)
def get_latest_air_waybills(
    current_user: User = Depends(get_current_user),
    service: AirWaybillService = Depends(get_air_waybill_service),
) -> AirWaybillLatestResponse:
    return service.get_latest_success(current_user)


@router.get("/scrape-status", response_model=ScrapeStatusResponse)
def get_scrape_status(
    _: User = Depends(require_admin),
    service: AirWaybillService = Depends(get_air_waybill_service),
) -> ScrapeStatusResponse:
    return service.get_latest_status()


@router.get("/scrape-runs/{run_id}", response_model=ScrapeRunSummary)
def get_scrape_run(
    run_id: UUID,
    _: User = Depends(require_admin),
    service: AirWaybillService = Depends(get_air_waybill_service),
) -> ScrapeRunSummary:
    return service.get_run(run_id)


@router.get("/{number}", response_model=AirWaybillDetailResponse)
def get_air_waybill_detail(
    number: str,
    current_user: User = Depends(get_current_user),
    service: AirWaybillService = Depends(get_air_waybill_service),
) -> AirWaybillDetailResponse:
    result = service.get_detail(number, current_user)
    if result is None:
        raise HTTPException(status_code=404, detail="Air Waybill not found")
    return result
