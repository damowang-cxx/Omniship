"""Read-only downstream polling and administrator-only tracking metadata."""

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import time
from uuid import UUID
from urllib.parse import quote

import httpx
from dotenv import dotenv_values
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import PROJECT_ROOT
from app.db.models import (
    DownstreamBinding, DownstreamIncident, DownstreamIncidentRead,
    DownstreamSyncEvent, User, WaybillTrackingRecord, WaybillUpload,
)
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.waybill_repository import WaybillRepository


AJ_BASE_URL = "https://www.ajwwworkspace.com/ShipFlow-UK/api/v1"
PROVIDERS = {"AJ": "AJ"}
POLL_INTERVAL = timedelta(minutes=5)
AJ_STATUS_MAP = {
    "NOT_ARRIVED": "created",
    "IN_FLIGHT": "created",
    "AWAITING_CUSTOMS": "pending_clearance",
    "AWAITING_COLLECTION": "cleared",
    "AWAITING_HANDOVER": "inbound",
    "HANDED_OVER": "outbound",
}
PROVIDER_STATUS_MAPS = {"AJ": AJ_STATUS_MAP}
MILESTONE_FIELDS = {"customs_clearance_at"}


def aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return aware(datetime.fromisoformat(value.replace("Z", "+00:00")))


class DownstreamError(ValueError):
    pass


class ProviderError(Exception):
    def __init__(self, kind: str, detail: str):
        self.kind = kind
        self.detail = detail
        super().__init__(detail)


class AJClient:
    def __init__(self, credentials_path: Path | None = None,
                 transport: httpx.BaseTransport | None = None):
        values = dotenv_values(credentials_path or PROJECT_ROOT / "aj-credentials.env")
        username = values.get("AJ_API_USERNAME")
        password = values.get("AJ_API_PASSWORD")
        if not username or not password:
            raise ProviderError("configuration", "AJ 账号或密码尚未填写")
        self.auth = httpx.BasicAuth(username, password)
        self.transport = transport

    def fetch(self, awb: str) -> dict:
        try:
            with httpx.Client(base_url=AJ_BASE_URL, auth=self.auth, timeout=10.0, transport=self.transport) as client:
                response = client.get(f"shipments/{quote(awb, safe='')}")
        except httpx.HTTPError as exc:
            raise ProviderError("network", f"AJ 请求失败：{type(exc).__name__}") from exc
        if response.status_code == 404:
            raise ProviderError("not_found", "AJ 未找到该提单，或当前账号无权访问")
        if response.status_code in (401, 403):
            raise ProviderError("authentication", f"AJ 账号认证失败（HTTP {response.status_code}）")
        if response.status_code != 200:
            raise ProviderError("network", f"AJ 服务返回 HTTP {response.status_code}")
        try:
            body = response.json()
            shipment = body["shipment"]
            if not body.get("ok") or not isinstance(shipment, dict):
                raise ValueError("invalid response")
            return shipment
        except (ValueError, KeyError, TypeError) as exc:
            raise ProviderError("invalid_response", "AJ 返回的提单数据格式无效") from exc

    def ping(self) -> dict:
        try:
            with httpx.Client(base_url=AJ_BASE_URL, auth=self.auth, timeout=10.0, transport=self.transport) as client:
                response = client.get("ping")
        except httpx.HTTPError as exc:
            raise ProviderError("network", f"AJ 请求失败：{type(exc).__name__}") from exc
        if response.status_code != 200:
            raise ProviderError("authentication", f"AJ Ping 返回 HTTP {response.status_code}")
        try:
            body = response.json()
            if not isinstance(body, dict) or body.get("ok") is not True:
                raise ValueError("invalid ping response")
            return body
        except ValueError as exc:
            raise ProviderError("invalid_response", "AJ Ping 返回数据格式无效") from exc


def normalize_aj(shipment: dict) -> dict:
    stage = shipment.get("stage") or {}
    completion = shipment.get("completion") or {}
    if not isinstance(stage, dict) or not isinstance(completion, dict):
        raise ValueError("invalid AJ stage or completion")
    split = shipment.get("split") or {}
    milestones = shipment.get("milestones") or {}
    if not isinstance(split, dict) or not isinstance(milestones, dict):
        raise ValueError("invalid AJ split or milestones")
    stage_code = stage.get("code")
    completion_code = completion.get("code")
    if stage_code is not None and not isinstance(stage_code, str):
        raise ValueError("invalid AJ stage code")
    if completion_code is not None and not isinstance(completion_code, str):
        raise ValueError("invalid AJ completion code")
    return {
        "awb": shipment.get("awb"),
        "stage_code": stage_code,
        "stage_entered_at": stage.get("entered_at"),
        "completion_code": completion_code,
        "remote_updated_at": shipment.get("last_updated_at"),
        "customs_clearance_at": milestones.get("customs_clearance_at"),
        "special": bool(split.get("is_split_parent") or shipment.get("archived") is not None),
    }


PROVIDER_CLIENTS = {"AJ": AJClient}
PROVIDER_NORMALIZERS = {"AJ": normalize_aj}


class DownstreamService:
    def __init__(self, db: Session):
        self.db = db

    def _record(self, public_code: str) -> WaybillTrackingRecord:
        record = WaybillRepository(self.db).get_by_public_code(public_code)
        if record is None or record.upload.status != "approved":
            raise DownstreamError("提单不存在或尚未审核通过")
        return record

    def _binding(self, record_id: UUID) -> DownstreamBinding | None:
        return self.db.scalar(select(DownstreamBinding).where(DownstreamBinding.tracking_record_id == record_id))

    def _event(self, binding: DownstreamBinding, awb: str, event_type: str, detail: dict) -> None:
        self.db.add(DownstreamSyncEvent(binding_id=binding.id, provider_code=binding.provider_code,
                                        awb=awb, event_type=event_type, detail=detail))

    def _resolve(self, binding_id: UUID, now: datetime) -> None:
        incidents = self.db.scalars(select(DownstreamIncident).where(
            DownstreamIncident.binding_id == binding_id, DownstreamIncident.resolved_at.is_(None)
        )).all()
        for incident in incidents:
            incident.resolved_at = now

    def _incident(self, binding: DownstreamBinding, awb: str, kind: str, detail: str, now: datetime) -> None:
        existing = self.db.scalar(select(DownstreamIncident).where(
            DownstreamIncident.binding_id == binding.id,
            DownstreamIncident.kind == kind,
            DownstreamIncident.resolved_at.is_(None),
        ))
        if existing is None:
            self._resolve(binding.id, now)
            self.db.add(DownstreamIncident(binding_id=binding.id, provider_code=binding.provider_code,
                                           awb=awb, kind=kind, detail=detail, opened_at=now))
            self._event(binding, awb, "incident_opened", {"kind": kind, "detail": detail})
        else:
            existing.detail = detail

    def assign(self, actor: User, public_code: str, provider_code: str | None) -> dict:
        record = self._record(public_code)
        if provider_code is not None and provider_code not in PROVIDERS:
            raise DownstreamError("未知的下游系统")
        binding = self._binding(record.id)
        now = datetime.now(timezone.utc)
        if binding and binding.provider_code == provider_code:
            return self.detail(public_code)
        if binding:
            self._resolve(binding.id, now)
            self._event(binding, record.upload.air_waybill_number, "unassigned", {})
            self.db.delete(binding)
            self.db.flush()
        if provider_code:
            binding = DownstreamBinding(
                tracking_record_id=record.id, provider_code=provider_code,
                assigned_by_user_id=actor.id, assigned_at=now,
                milestone_locks=["customs_clearance_at"] if record.customs_clearance_at else [],
            )
            self.db.add(binding)
            self.db.flush()
            self._event(binding, record.upload.air_waybill_number, "assigned", {})
        AuditLogRepository(self.db).create(
            "update_downstream_assignment", actor_user_id=actor.id,
            target_type="waybill_tracking_record", target_id=str(record.id),
            metadata={"awb": record.upload.air_waybill_number, "providerCode": provider_code},
        )
        self.db.commit()
        return self.detail(public_code)

    def stop_for_removed_record(self, record: WaybillTrackingRecord | None) -> None:
        if record is None:
            return
        binding = self._binding(record.id)
        if binding is None:
            return
        now = datetime.now(timezone.utc)
        self._resolve(binding.id, now)
        self._event(binding, record.upload.air_waybill_number, "unassigned", {"reason": "waybill_removed"})
        self.db.delete(binding)
        self.db.flush()

    def detail(self, public_code: str) -> dict:
        record = self._record(public_code)
        binding = self._binding(record.id)
        if binding is None:
            return {"publicCode": record.public_code, "providerCode": None, "statusLocked": False,
                    "milestoneLocks": [], "lastCheckedAt": None, "lastSuccessAt": None,
                    "remoteStage": None, "remoteCompletion": None, "remoteUpdatedAt": None,
                    "snapshot": None, "lastError": None}
        return {
            "publicCode": record.public_code, "providerCode": binding.provider_code,
            "statusLocked": binding.status_locked, "milestoneLocks": binding.milestone_locks,
            "lastCheckedAt": binding.last_checked_at, "lastSuccessAt": binding.last_success_at,
            "remoteStage": binding.remote_stage, "remoteCompletion": binding.remote_completion,
            "remoteUpdatedAt": binding.remote_updated_at, "snapshot": binding.snapshot,
            "lastError": binding.last_error,
        }

    def list_bindings(self, public_codes: list[str] | None = None) -> list[dict]:
        statement = select(DownstreamBinding).options(
            joinedload(DownstreamBinding.tracking_record).joinedload(WaybillTrackingRecord.upload)
        )
        if public_codes is not None:
            statement = statement.where(DownstreamBinding.tracking_record.has(
                WaybillTrackingRecord.public_code.in_(public_codes)
            ))
        bindings = self.db.scalars(statement).all()
        return [{"publicCode": item.tracking_record.public_code,
                 "awb": item.tracking_record.upload.air_waybill_number,
                 "providerCode": item.provider_code, "statusLocked": item.status_locked,
                 "lastSuccessAt": item.last_success_at, "lastError": item.last_error} for item in bindings]

    def set_locks(self, actor: User, public_code: str, status_locked: bool | None,
                  milestone_locks: list[str] | None) -> dict:
        record = self._record(public_code)
        binding = self._binding(record.id)
        if binding is None:
            raise DownstreamError("提单尚未归属下游系统")
        if milestone_locks is not None and set(milestone_locks) - MILESTONE_FIELDS:
            raise DownstreamError("未知的里程碑字段")
        if status_locked is not None:
            binding.status_locked = status_locked
        if milestone_locks is not None:
            binding.milestone_locks = milestone_locks
        AuditLogRepository(self.db).create(
            "update_downstream_locks", actor_user_id=actor.id,
            target_type="waybill_tracking_record", target_id=str(record.id),
            metadata={"statusLocked": binding.status_locked, "milestoneLocks": binding.milestone_locks},
        )
        self.db.commit()
        return self.detail(public_code)

    def list_incidents(self, admin_id: UUID) -> list[dict]:
        incidents = self.db.scalars(select(DownstreamIncident).order_by(DownstreamIncident.opened_at.desc()).limit(100)).all()
        read_ids = set(self.db.scalars(select(DownstreamIncidentRead.incident_id).where(
            DownstreamIncidentRead.admin_user_id == admin_id,
        )).all())
        return [{"id": str(item.id), "providerCode": item.provider_code, "awb": item.awb,
                 "kind": item.kind, "detail": item.detail, "openedAt": item.opened_at,
                 "resolvedAt": item.resolved_at, "read": item.id in read_ids} for item in incidents]

    def mark_incidents_read(self, admin_id: UUID, incident_ids: list[UUID]) -> None:
        existing = set(self.db.scalars(select(DownstreamIncidentRead.incident_id).where(
            DownstreamIncidentRead.admin_user_id == admin_id,
            DownstreamIncidentRead.incident_id.in_(incident_ids),
        )).all())
        valid = set(self.db.scalars(select(DownstreamIncident.id).where(DownstreamIncident.id.in_(incident_ids))).all())
        self.db.add_all(DownstreamIncidentRead(admin_user_id=admin_id, incident_id=item)
                        for item in valid - existing)
        self.db.commit()

    def process(self, binding: DownstreamBinding, now: datetime, shipment: dict | None = None,
                error: ProviderError | None = None) -> None:
        awb = binding.tracking_record.upload.air_waybill_number
        binding.last_checked_at = now
        if error:
            binding.last_error = error.detail
            if error.kind == "not_found":
                binding.first_network_error_at = None
                if binding.first_missing_at is None:
                    binding.first_missing_at = now
                    self._event(binding, awb, "missing_pending", {"detail": error.detail})
                elif now - aware(binding.first_missing_at) >= POLL_INTERVAL:
                    self._incident(binding, awb, "not_found", error.detail, now)
            elif error.kind == "network":
                binding.first_missing_at = None
                if binding.first_network_error_at is None:
                    binding.first_network_error_at = now
                    self._event(binding, awb, "network_retry_pending", {"detail": error.detail})
                elif now - aware(binding.first_network_error_at) >= POLL_INTERVAL:
                    self._incident(binding, awb, error.kind, error.detail, now)
            else:
                binding.first_missing_at = None
                binding.first_network_error_at = None
                self._incident(binding, awb, error.kind, error.detail, now)
            self.db.commit()
            return

        try:
            normalized = PROVIDER_NORMALIZERS[binding.provider_code](shipment)
        except (KeyError, TypeError, AttributeError, ValueError):
            self.process(binding, now, error=ProviderError("invalid_response", "AJ 返回的提单数据格式无效"))
            return
        if normalized["awb"] != awb:
            self.process(binding, now, error=ProviderError("invalid_response", "AJ 返回的提单号与查询提单不一致"))
            return
        binding.last_success_at = now
        binding.first_missing_at = None
        binding.first_network_error_at = None
        binding.last_error = None
        code = normalized["stage_code"]
        binding.remote_stage = code
        binding.remote_completion = normalized["completion_code"]
        try:
            binding.remote_updated_at = parse_time(normalized["remote_updated_at"])
        except (TypeError, ValueError):
            binding.remote_updated_at = None
        changed = binding.snapshot != shipment
        binding.snapshot = shipment
        if changed:
            self._event(binding, awb, "snapshot_changed", {"stage": code, "completion": binding.remote_completion})

        special = normalized["special"]
        if special:
            binding.last_error = "AJ 提单已拆分或被扣留／销毁，请管理员核查"
            self._incident(binding, awb, "special_shipment", binding.last_error, now)
        elif code not in PROVIDER_STATUS_MAPS[binding.provider_code]:
            binding.last_error = f"AJ 返回未知阶段：{code}"
            self._incident(binding, awb, "unknown_stage", binding.last_error, now)
        else:
            self._resolve(binding.id, now)
            record = binding.tracking_record
            mapped = PROVIDER_STATUS_MAPS[binding.provider_code][code]
            if not binding.status_locked and record.status != mapped:
                old = record.status
                record.status = mapped
                try:
                    record.status_changed_at = parse_time(normalized["stage_entered_at"]) or now
                except (TypeError, ValueError):
                    record.status_changed_at = now
                self._event(binding, awb, "status_changed", {"from": old, "to": mapped, "stage": code})
            milestone = normalized["customs_clearance_at"]
            if "customs_clearance_at" not in binding.milestone_locks:
                try:
                    parsed = parse_time(milestone)
                except (TypeError, ValueError):
                    binding.last_error = "AJ 清关时间格式无效"
                    self._incident(binding, awb, "invalid_response", binding.last_error, now)
                else:
                    if aware(record.customs_clearance_at) != parsed:
                        record.customs_clearance_at = parsed
                        self._event(binding, awb, "milestone_changed", {"field": "customs_clearance_at", "to": milestone})
        self.db.commit()

    def run_due(self, client: AJClient | None = None, now: datetime | None = None) -> int:
        provided_now = now
        now = now or datetime.now(timezone.utc)
        bindings = self.db.scalars(select(DownstreamBinding).options(
            joinedload(DownstreamBinding.tracking_record).joinedload(WaybillTrackingRecord.upload)
        )).all()
        due = [item for item in bindings if item.tracking_record.upload.status == "approved" and
               (item.last_checked_at is None or now - aware(item.last_checked_at) >= POLL_INTERVAL)]
        minimum_interval = max(0.0, float(os.getenv("AJ_MIN_REQUEST_INTERVAL_SECONDS", "0.5")))
        previous_request_at: float | None = None
        clients: dict[str, AJClient] = {}
        for binding in due:
            if client is None:
                try:
                    provider_client = clients.get(binding.provider_code)
                    if provider_client is None:
                        provider_client = PROVIDER_CLIENTS[binding.provider_code]()
                        clients[binding.provider_code] = provider_client
                except ProviderError as exc:
                    self.process(binding, now, error=exc)
                    continue
            else:
                provider_client = client
            result: dict | None = None
            fetch_error: ProviderError | None = None
            try:
                if previous_request_at is not None:
                    time.sleep(max(0.0, minimum_interval - (time.monotonic() - previous_request_at)))
                previous_request_at = time.monotonic()
                result = provider_client.fetch(binding.tracking_record.upload.air_waybill_number)
            except ProviderError as exc:
                fetch_error = exc
            except Exception as exc:
                fetch_error = ProviderError("network", f"AJ 同步发生未预期错误：{type(exc).__name__}")
            # Assignment and manual locks may have changed while the HTTP call was in flight.
            current = self.db.scalar(
                select(DownstreamBinding).where(DownstreamBinding.id == binding.id)
                .with_for_update(of=DownstreamBinding)
                .execution_options(populate_existing=True)
            )
            if current is None:
                self.db.rollback()
                continue
            self.db.refresh(current.tracking_record)
            self.db.refresh(current.tracking_record.upload)
            if current.tracking_record.upload.status != "approved":
                self.db.rollback()
                continue
            self.process(current, provided_now or datetime.now(timezone.utc),
                         shipment=result, error=fetch_error)
        return len(due)
