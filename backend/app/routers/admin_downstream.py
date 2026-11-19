from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import require_admin
from app.db.models import User
from app.db.session import get_db
from app.services.downstream_sync import DownstreamError, DownstreamService, PROVIDERS


router = APIRouter(prefix="/api/v1/admin/downstream", tags=["admin-downstream"])


class Assignment(BaseModel):
    providerCode: str | None = None


class Locks(BaseModel):
    statusLocked: bool | None = None
    milestoneLocks: list[str] | None = None
    dataLocks: list[str] | None = None


class ReadIncidents(BaseModel):
    incidentIds: list[UUID] = Field(default_factory=list)


@router.get("/providers")
def providers(_: User = Depends(require_admin)) -> list[dict]:
    return [{"code": code, "name": name} for code, name in PROVIDERS.items()]


@router.get("/bindings")
def bindings(public_codes: str | None = Query(default=None, alias="publicCodes"),
             db: Session = Depends(get_db), _: User = Depends(require_admin)) -> list[dict]:
    codes = [code.strip() for code in public_codes.split(",") if code.strip()] if public_codes else None
    return DownstreamService(db).list_bindings(codes)


@router.get("/incidents")
def incidents(db: Session = Depends(get_db), actor: User = Depends(require_admin)) -> list[dict]:
    return DownstreamService(db).list_incidents(actor.id)


@router.post("/incidents/read")
def mark_incidents_read(payload: ReadIncidents, db: Session = Depends(get_db),
                        actor: User = Depends(require_admin)) -> dict:
    DownstreamService(db).mark_incidents_read(actor.id, payload.incidentIds)
    return {"ok": True}


@router.get("/waybills/{public_code}")
def detail(public_code: str, db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict:
    try:
        return DownstreamService(db).detail(public_code)
    except DownstreamError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/waybills/{public_code}")
def assign(public_code: str, payload: Assignment, db: Session = Depends(get_db),
           actor: User = Depends(require_admin)) -> dict:
    try:
        return DownstreamService(db).assign(actor, public_code, payload.providerCode)
    except DownstreamError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/waybills/{public_code}/locks")
def locks(public_code: str, payload: Locks, db: Session = Depends(get_db),
          actor: User = Depends(require_admin)) -> dict:
    try:
        return DownstreamService(db).set_locks(actor, public_code,
                                                payload.statusLocked, payload.milestoneLocks, payload.dataLocks)
    except DownstreamError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
