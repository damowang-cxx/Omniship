from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, require_admin
from app.db.models import User
from app.db.session import get_db
from app.schemas.waybill_upload import (
    WaybillPreAlertUploadResponse,
    WaybillUploadDeleteResponse,
    WaybillUploadListResponse,
    WaybillUploadRequest,
    WaybillUploadResponse,
    WaybillUploadStatusUpdateRequest,
    WaybillUploadItem,
)
from app.services.waybill_upload_service import (
    WaybillUploadPermissionError,
    WaybillUploadService,
    WaybillUploadValidationError,
)


router = APIRouter(prefix="/api/v1/waybill-uploads", tags=["waybill-uploads"])


@router.get("", response_model=WaybillUploadListResponse)
def list_waybill_uploads(
    user_id: UUID | None = Query(default=None, alias="userId"),
    platform_submission_status: str | None = Query(
        default=None,
        alias="platformSubmissionStatus",
    ),
    upload_status: str | None = Query(default=None, alias="status"),
    query: str | None = Query(default=None, alias="q"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WaybillUploadListResponse:
    try:
        return WaybillUploadService(db).list_uploads(
            current_user,
            user_id=user_id,
            platform_submission_status=platform_submission_status,
            status=upload_status,
            query=query,
        )
    except WaybillUploadValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("", response_model=WaybillUploadResponse, status_code=status.HTTP_201_CREATED)
def upload_waybill_numbers(
    payload: WaybillUploadRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WaybillUploadResponse:
    return WaybillUploadService(db).bind_numbers(
        actor=current_user,
        numbers=payload.numbers,
        request=request,
    )


async def _create_pre_alert_upload(
    *,
    request: Request,
    db: Session,
    current_user: User,
    platform: str,
    shipment_type: str,
    air_waybill_number: str,
    gross_weight_kg: str,
    pieces: str,
    arrival_flight_number: str | None,
    air_waybill_documents: list[UploadFile],
    pre_alert_file: UploadFile,
    target_user_id: UUID | None,
) -> WaybillPreAlertUploadResponse:
    try:
        return await WaybillUploadService(db).create_pre_alert_upload(
            actor=current_user,
            request=request,
            platform=platform,
            shipment_type=shipment_type,
            air_waybill_number=air_waybill_number,
            gross_weight_kg=gross_weight_kg,
            pieces=pieces,
            arrival_flight_number=arrival_flight_number,
            air_waybill_documents=air_waybill_documents,
            pre_alert_file=pre_alert_file,
            target_user_id=target_user_id,
        )
    except WaybillUploadPermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except WaybillUploadValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/file",
    response_model=WaybillPreAlertUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_pre_alert_file(
    request: Request,
    platform: str = Form(...),
    shipment_type: str = Form(..., alias="shipmentType"),
    air_waybill_number: str = Form(..., alias="airWaybillNumber"),
    gross_weight_kg: str = Form(..., alias="grossWeightKg"),
    pieces: str = Form(...),
    arrival_flight_number: str | None = Form(default=None, alias="arrivalFlightNumber"),
    target_user_id: UUID | None = Form(default=None, alias="targetUserId"),
    air_waybill_documents: list[UploadFile] = File(..., alias="airWaybillDocuments"),
    pre_alert_file: UploadFile = File(..., alias="preAlertFile"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WaybillPreAlertUploadResponse:
    return await _create_pre_alert_upload(
        request=request,
        db=db,
        current_user=current_user,
        platform=platform,
        shipment_type=shipment_type,
        air_waybill_number=air_waybill_number,
        gross_weight_kg=gross_weight_kg,
        pieces=pieces,
        arrival_flight_number=arrival_flight_number,
        air_waybill_documents=air_waybill_documents,
        pre_alert_file=pre_alert_file,
        target_user_id=target_user_id,
    )


@router.post(
    "/pre-alert",
    response_model=WaybillPreAlertUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_pre_alert(
    request: Request,
    platform: str = Form(...),
    shipment_type: str = Form(..., alias="shipmentType"),
    air_waybill_number: str = Form(..., alias="airWaybillNumber"),
    gross_weight_kg: str = Form(..., alias="grossWeightKg"),
    pieces: str = Form(...),
    arrival_flight_number: str | None = Form(default=None, alias="arrivalFlightNumber"),
    target_user_id: UUID | None = Form(default=None, alias="targetUserId"),
    air_waybill_documents: list[UploadFile] = File(..., alias="airWaybillDocuments"),
    pre_alert_file: UploadFile = File(..., alias="preAlertFile"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WaybillPreAlertUploadResponse:
    return await _create_pre_alert_upload(
        request=request,
        db=db,
        current_user=current_user,
        platform=platform,
        shipment_type=shipment_type,
        air_waybill_number=air_waybill_number,
        gross_weight_kg=gross_weight_kg,
        pieces=pieces,
        arrival_flight_number=arrival_flight_number,
        air_waybill_documents=air_waybill_documents,
        pre_alert_file=pre_alert_file,
        target_user_id=target_user_id,
    )


@router.patch("/{upload_id}/status", response_model=WaybillUploadItem)
def update_waybill_upload_status(
    upload_id: UUID,
    payload: WaybillUploadStatusUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> WaybillUploadItem:
    try:
        return WaybillUploadService(db).update_status(
            actor=current_user,
            upload_id=upload_id,
            status=payload.status,
            request=request,
        )
    except WaybillUploadValidationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{upload_id}/manual-submit", response_model=WaybillUploadItem)
def manual_submit_waybill_upload(
    upload_id: UUID,
    request: Request,
    force: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> WaybillUploadItem:
    try:
        return WaybillUploadService(db).manual_submit(
            actor=current_user,
            upload_id=upload_id,
            force=force,
            request=request,
        )
    except WaybillUploadPermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except WaybillUploadValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/{upload_id}/files/{file_id}/download")
def download_waybill_upload_file(
    upload_id: UUID,
    file_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    try:
        file = WaybillUploadService(db).get_download_file(
            actor=current_user,
            upload_id=upload_id,
            file_id=file_id,
            request=request,
        )
    except WaybillUploadPermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except WaybillUploadValidationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return FileResponse(
        path=file.storage_path,
        media_type=file.content_type or "application/octet-stream",
        filename=file.original_filename,
    )


@router.delete("/{upload_id}", response_model=WaybillUploadDeleteResponse)
def delete_waybill_upload(
    upload_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WaybillUploadDeleteResponse:
    try:
        return WaybillUploadService(db).delete_upload(
            actor=current_user,
            upload_id=upload_id,
            request=request,
        )
    except WaybillUploadPermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except WaybillUploadValidationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
