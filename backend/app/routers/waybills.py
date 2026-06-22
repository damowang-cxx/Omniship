from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, require_admin
from app.db.models import User
from app.db.session import get_db
from app.schemas.waybill import (
    WaybillItem,
    WaybillListResponse,
    WaybillParcelBulkUpdateRequest,
    WaybillParcelListResponse,
    WaybillPodDeleteResponse,
    WaybillUpdateRequest,
)
from app.services.waybill_service import (
    WaybillPermissionError,
    WaybillService,
    WaybillValidationError,
)


router = APIRouter(prefix="/api/v1/waybills", tags=["waybills"])

POD_MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}


def _pod_media_type(original_filename: str, content_type: str | None) -> str:
    if content_type:
        return content_type
    extension = Path(original_filename).suffix.lower()
    return POD_MEDIA_TYPES.get(extension, "application/octet-stream")


@router.get("", response_model=WaybillListResponse)
def list_waybills(
    user_id: UUID | None = Query(default=None, alias="userId"),
    waybill_status: str | None = Query(default=None, alias="status"),
    query: str | None = Query(default=None, alias="q"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WaybillListResponse:
    try:
        return WaybillService(db).list_waybills(
            current_user,
            user_id=user_id,
            status=waybill_status,
            query=query,
        )
    except WaybillValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/{public_code}/pod", response_model=WaybillItem, status_code=status.HTTP_201_CREATED)
async def upload_waybill_pod_file(
    public_code: str,
    request: Request,
    pod_file: UploadFile = File(..., alias="podFile"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> WaybillItem:
    try:
        return await WaybillService(db).upload_pod_file(
            current_user,
            public_code=public_code,
            file=pod_file,
            request=request,
        )
    except WaybillPermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except WaybillValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/{public_code}/pod/{pod_file_id}/download")
def download_waybill_pod_file(
    public_code: str,
    pod_file_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    try:
        file = WaybillService(db).get_pod_download_file(
            current_user,
            public_code=public_code,
            pod_file_id=pod_file_id,
            request=request,
        )
    except WaybillPermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except WaybillValidationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return FileResponse(
        path=file.storage_path,
        media_type=_pod_media_type(file.original_filename, file.content_type),
        filename=file.original_filename,
    )


@router.delete("/{public_code}/pod/{pod_file_id}", response_model=WaybillPodDeleteResponse)
def delete_waybill_pod_file(
    public_code: str,
    pod_file_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> WaybillPodDeleteResponse:
    try:
        return WaybillService(db).delete_pod_file(
            current_user,
            public_code=public_code,
            pod_file_id=pod_file_id,
            request=request,
        )
    except WaybillPermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except WaybillValidationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/{public_code}/parcels", response_model=WaybillParcelListResponse)
def get_waybill_parcels(
    public_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WaybillParcelListResponse:
    try:
        return WaybillService(db).get_parcels(current_user, public_code=public_code)
    except WaybillPermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except WaybillValidationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch("/{public_code}/parcels", response_model=WaybillParcelListResponse)
def update_waybill_parcels(
    public_code: str,
    payload: WaybillParcelBulkUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> WaybillParcelListResponse:
    try:
        return WaybillService(db).update_parcels(
            current_user,
            public_code=public_code,
            payload=payload,
            request=request,
        )
    except WaybillPermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except WaybillValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/{public_code}", response_model=WaybillItem)
def get_waybill(
    public_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WaybillItem:
    try:
        return WaybillService(db).get_waybill(current_user, public_code=public_code)
    except WaybillPermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except WaybillValidationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch("/{public_code}", response_model=WaybillItem)
def update_waybill(
    public_code: str,
    payload: WaybillUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> WaybillItem:
    try:
        return WaybillService(db).update_waybill(
            current_user,
            public_code=public_code,
            payload=payload,
            request=request,
        )
    except WaybillPermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except WaybillValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
