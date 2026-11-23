"""Read-only downstream polling and administrator-only tracking metadata."""

from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
import os
from pathlib import Path
import time
from uuid import UUID
from urllib.parse import quote, urlsplit

import httpx
from dotenv import dotenv_values
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import PROJECT_ROOT, Settings, get_settings
from app.db.models import (
    DownstreamBinding, DownstreamIncident, DownstreamIncidentRead,
    DownstreamSyncEvent, User, WaybillPodFile, WaybillTrackingRecord, WaybillUpload,
)
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.waybill_repository import WaybillRepository
from app.services.pod_files import POD_MAX_BYTES, delete_pod_content, save_pod_content, validate_imported_pod_content


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
MILESTONE_FIELDS = {"noa_at", "collection_at", "scanned_at", "customs_clearance_at", "outbound_at",
                    "airline_record_created_at", "airline_arrived_at", "aj_warehouse_arrived_at"}
DATA_FIELDS = {"received_count", "received_total", "in_warehouse_count", "released_count", "outbound_count", "parcels", "pod_files"}


def aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def parse_time(value: str | None) -> datetime | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError("Timestamp must be an ISO-8601 string")
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

    def download_pod(self, document_id: str, download_url: str | None = None) -> bytes:
        url = download_url or f"{AJ_BASE_URL}/files/pod/{quote(document_id, safe='')}"
        base = urlsplit(AJ_BASE_URL)
        try:
            target = urlsplit(url)
            port = target.port
        except ValueError:
            raise ProviderError("pod_download", "AJ POD 下载地址无效") from None
        if (target.scheme != "https" or target.hostname != base.hostname or port not in (None, 443)
                or target.username or target.password or target.fragment
                or target.path != f"{base.path}/files/pod/{document_id}"):
            raise ProviderError("pod_download", "AJ POD 下载地址不符合当前接口范围")
        # Credentials are restricted to AJ's documented file endpoint, with redirects disabled.
        try:
            with httpx.Client(base_url=AJ_BASE_URL, auth=self.auth, timeout=20.0, transport=self.transport) as client:
                with client.stream("GET", url) as response:
                    if response.status_code != 200:
                        raise ProviderError("pod_download", f"AJ POD {document_id} 下载失败（HTTP {response.status_code}）")
                    content = bytearray()
                    for chunk in response.iter_bytes():
                        content.extend(chunk)
                        if len(content) > POD_MAX_BYTES:
                            raise ProviderError("pod_download", f"AJ POD {document_id} 超过 10 MB")
                    return bytes(content)
        except httpx.HTTPError as exc:
            raise ProviderError("pod_download", f"AJ POD {document_id} 请求失败：{type(exc).__name__}") from exc


def aj_pod_documents(shipment: dict) -> list[dict] | None:
    vendors = shipment.get("vendors")
    orphans = shipment.get("orphan_pod_documents")
    if vendors is None and orphans is None:
        return None
    if not isinstance(vendors, list) or not isinstance(orphans, list):
        raise ProviderError("invalid_response", "AJ POD 渠道或附件列表格式无效")
    groups = [(None, orphans)]
    for vendor in vendors:
        if not isinstance(vendor, dict) or not isinstance(vendor.get("pod_documents"), list):
            raise ProviderError("invalid_response", "AJ 渠道 POD 列表格式无效")
        groups.append((vendor.get("code"), vendor["pod_documents"]))
    selected = {}
    for vendor, documents in groups:
        for document in documents:
            if not isinstance(document, dict):
                raise ProviderError("invalid_response", "AJ POD 附件格式无效")
            if not isinstance(document.get("is_current", True), bool):
                raise ProviderError("invalid_response", "AJ POD 当前版本标记无效")
            if vendor is not None and document.get("is_current") is False:
                continue
            document_id = str(document.get("id", ""))
            version = document.get("version", 1)
            filename = document.get("file_name")
            note = document.get("note")
            download_url = document.get("download_url")
            if not document_id.isdecimal() or int(document_id) <= 0 or len(document_id) > 120:
                raise ProviderError("invalid_response", "AJ POD 文件编号无效")
            if isinstance(version, bool) or not isinstance(version, int) or not 1 <= version <= 2147483647:
                raise ProviderError("invalid_response", "AJ POD 版本号无效")
            if not isinstance(filename, str) or not filename or len(filename) > 255:
                raise ProviderError("invalid_response", "AJ POD 文件名无效")
            filename = Path(filename.replace("\\", "/")).name
            if vendor is not None and (not isinstance(vendor, str) or len(vendor) > 120):
                raise ProviderError("invalid_response", "AJ POD 渠道编号无效")
            if (note is not None and not isinstance(note, str)) or (download_url is not None and not isinstance(download_url, str)):
                raise ProviderError("invalid_response", "AJ POD 备注或下载地址无效")
            try:
                uploaded_at = parse_time(document.get("uploaded_at"))
            except (AttributeError, TypeError, ValueError):
                raise ProviderError("invalid_response", "AJ POD 上传时间无效") from None
            spec = {"id": document_id, "version": version, "filename": filename,
                    "vendor": vendor, "uploaded_at": uploaded_at, "note": note, "download_url": download_url}
            previous = selected.get(document_id)
            if previous is None or version >= previous["version"]:
                selected[document_id] = spec
    return list(selected.values())


@dataclass(frozen=True)
class AJQuantitySummary:
    total: int | None
    vendors: list[dict] | None
    source: str
    warning: str | None = None


def aj_quantity_summary(shipment: dict, pieces: int) -> AJQuantitySummary:
    total = shipment.get("packages")
    valid_total = not isinstance(total, bool) and isinstance(total, int) and total >= 0
    vendors = shipment.get("vendors")
    if vendors is not None and not isinstance(vendors, list):
        raise ValueError("AJ 渠道列表格式无效")
    allocated = 0
    codes = set()
    for vendor in vendors or []:
        if not isinstance(vendor, dict):
            raise ValueError("AJ 渠道数据格式无效")
        code = vendor.get("code")
        count = vendor.get("packages")
        if not isinstance(code, str) or not code or code in codes:
            raise ValueError("AJ 渠道编号为空或重复")
        codes.add(code)
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("AJ 渠道件数无效")
        allocated += count
    total_label = str(total) if valid_total else "未提供" if total is None else "格式无效"
    if vendors:
        channels = "、".join(f"{vendor['code']}: {vendor['packages']}" for vendor in vendors)
        if allocated != pieces:
            raise ValueError(
                f"AJ 总件数为 {total_label}，本地提单件数为 {pieces}，渠道件数合计为 {allocated}（{channels}）；"
                "渠道合计与本地件数不一致，已暂停应收数量、出库数量和出库完成时间同步，请核对数量口径"
            )
        warning = None
        if not valid_total or total != allocated:
            warning = (
                f"AJ 顶层 packages 为 {total_label}，渠道件数合计为 {allocated}（{channels}），本地提单件数为 {pieces}；"
                "渠道合计与本地一致，本轮按渠道数量同步，本地原始件数保持不变"
            )
        return AJQuantitySummary(allocated, vendors, "vendors[].packages", warning)
    if total is None:
        return AJQuantitySummary(None, None, "packages")
    if not valid_total:
        raise ValueError("AJ 总件数格式无效，应为非负整数")
    if total != pieces:
        raise ValueError(
            f"AJ 总件数为 {total}，本地提单件数为 {pieces}；"
            "已暂停应收数量、出库数量和出库完成时间同步，请核对数量口径"
        )
    return AJQuantitySummary(total, None, "packages")


def aj_handover(quantities: AJQuantitySummary) -> tuple[int, datetime | None] | None:
    if quantities.vendors is None:
        return None
    outbound = 0
    times = []
    for vendor in quantities.vendors:
        code = vendor["code"]
        count = vendor["packages"]
        try:
            handed_over = parse_time(vendor.get("handed_over_at"))
        except ValueError:
            raise ValueError(f"AJ {code} 渠道交接时间格式无效") from None
        if handed_over is not None and count > 0:
            outbound += count
            times.append(handed_over)
    final_handover = max(times) if quantities.total > 0 and outbound == quantities.total else None
    return outbound, final_handover


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
    def __init__(self, db: Session, settings: Settings | None = None):
        self.db = db
        self.settings = settings or get_settings()

    def _prepare_pods(self, binding: DownstreamBinding, shipment: dict, client: AJClient) -> dict:
        try:
            documents = aj_pod_documents(shipment)
        except ProviderError as exc:
            return {"documents": None, "downloads": {}, "errors": [exc.detail]}
        prepared = {"documents": documents, "downloads": {}, "errors": []}
        if documents is None or "pod_files" in binding.data_locks:
            return prepared
        existing = {item.provider_document_id: item for item in self.db.scalars(select(WaybillPodFile).where(
            WaybillPodFile.tracking_record_id == binding.tracking_record_id,
            WaybillPodFile.provider_code == binding.provider_code,
        )).all()}
        for document in documents:
            item = existing.get(document["id"])
            if (item is not None and item.provider_document_version == document["version"]
                    and item.original_filename == document["filename"]
                    and aware(item.provider_uploaded_at) == document["uploaded_at"]
                    and Path(item.storage_path).is_file()):
                continue
            try:
                content = client.download_pod(document["id"], document["download_url"])
                prepared["downloads"][document["id"]] = validate_imported_pod_content(document["filename"], content)
            except ProviderError as exc:
                prepared["errors"].append(exc.detail)
            except ValueError as exc:
                prepared["errors"].append(f"AJ POD {document['id']} 文件无效：{exc}")
            except Exception as exc:
                prepared["errors"].append(f"AJ POD {document['id']} 下载异常：{type(exc).__name__}")
        return prepared

    def _sync_pods(self, binding: DownstreamBinding, prepared: dict | None,
                   report: dict, new_paths: list[str], obsolete_paths: list[str]) -> None:
        if "pod_files" in binding.data_locks:
            report["pod_files"] = {"state": "locked"}
            return
        if prepared is None:
            report["pod_files"] = {"state": "unavailable", "detail": "AJ 未提供附件数据或本次未执行附件下载"}
            return
        errors = list(prepared["errors"])
        documents = prepared["documents"]
        if documents is None:
            report["pod_files"] = {"state": "error" if errors else "unavailable", "detail": "；".join(errors) or "AJ 未提供附件列表"}
            return
        existing = {item.provider_document_id: item for item in self.db.scalars(select(WaybillPodFile).where(
            WaybillPodFile.tracking_record_id == binding.tracking_record_id,
            WaybillPodFile.provider_code == binding.provider_code,
        )).all()}
        available = 0
        for document in documents:
            item = existing.get(document["id"])
            payload = prepared["downloads"].get(document["id"])
            if payload is not None:
                try:
                    saved = save_pod_content(binding.tracking_record.upload_id, payload, self.settings)
                except OSError as exc:
                    errors.append(f"AJ POD {document['id']} 保存失败：{type(exc).__name__}")
                    continue
                new_paths.append(saved["storage_path"])
                if item is None:
                    item = WaybillPodFile(tracking_record_id=binding.tracking_record_id,
                                          provider_code=binding.provider_code, provider_document_id=document["id"])
                    self.db.add(item)
                else:
                    obsolete_paths.append(item.storage_path)
                for field in ("original_filename", "content_type", "size_bytes", "sha256", "storage_path"):
                    setattr(item, field, saved[field])
                item.provider_document_version = document["version"]
                item.provider_uploaded_at = document["uploaded_at"]
                self._event(binding, binding.tracking_record.upload.air_waybill_number, "pod_synced",
                            {"documentId": document["id"], "version": document["version"], "vendor": document["vendor"]})
            if item is not None:
                if (item.original_filename == document["filename"]
                        and item.provider_document_version == document["version"]
                        and aware(item.provider_uploaded_at) == document["uploaded_at"]
                        and Path(item.storage_path).is_file()):
                    item.provider_vendor_code = document["vendor"]
                    item.provider_note = document["note"]
                    available += 1
                elif not errors:
                    errors.append(f"AJ POD {document['id']} 附件在查询期间发生变化，将重试")
            elif not errors:
                errors.append(f"AJ POD {document['id']} 本轮未完成下载，将重试")
        if not errors:
            wanted = {document["id"] for document in documents}
            for document_id, item in existing.items():
                if document_id not in wanted:
                    obsolete_paths.append(item.storage_path)
                    self.db.delete(item)
        report["pod_files"] = {
            "state": "error" if errors else "synced", "source": "vendors[].pod_documents / orphan_pod_documents",
            "value": available, "detail": "；".join(errors),
        }

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
        if provider_code == "AJ" and record.upload.airport_of_arrival != "LHR":
            raise DownstreamError("仅 LHR 提单可归属 AJ")
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
            data_locks = {field for field in DATA_FIELDS - {"parcels", "pod_files", "received_total"} if getattr(record, field)}
            if record.received_total != record.upload.pieces:
                data_locks.add("received_total")
            if any(parcel.status != "created" or parcel.inbound or parcel.outbound for parcel in record.parcels):
                data_locks.add("parcels")
            binding = DownstreamBinding(
                tracking_record_id=record.id, provider_code=provider_code,
                assigned_by_user_id=actor.id, assigned_at=now,
                milestone_locks=sorted(field for field in MILESTONE_FIELDS if getattr(record, field)),
                data_locks=sorted(data_locks),
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
                    "snapshot": None, "lastError": None, "dataLocks": [], "syncReport": {}}
        return {
            "publicCode": record.public_code, "providerCode": binding.provider_code,
            "statusLocked": binding.status_locked, "milestoneLocks": binding.milestone_locks,
            "lastCheckedAt": binding.last_checked_at, "lastSuccessAt": binding.last_success_at,
            "remoteStage": binding.remote_stage, "remoteCompletion": binding.remote_completion,
            "remoteUpdatedAt": binding.remote_updated_at, "snapshot": binding.snapshot,
            "lastError": binding.last_error,
            "dataLocks": binding.data_locks, "syncReport": binding.sync_report,
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
                  milestone_locks: list[str] | None, data_locks: list[str] | None = None) -> dict:
        record = self._record(public_code)
        binding = self._binding(record.id)
        if binding is None:
            raise DownstreamError("提单尚未归属下游系统")
        if milestone_locks is not None and set(milestone_locks) - MILESTONE_FIELDS:
            raise DownstreamError("未知的里程碑字段")
        if data_locks is not None and set(data_locks) - DATA_FIELDS:
            raise DownstreamError("未知的同步字段")
        if status_locked is not None:
            binding.status_locked = status_locked
        if milestone_locks is not None:
            binding.milestone_locks = sorted(set(milestone_locks))
        if data_locks is not None:
            binding.data_locks = sorted(set(data_locks))
        AuditLogRepository(self.db).create(
            "update_downstream_locks", actor_user_id=actor.id,
            target_type="waybill_tracking_record", target_id=str(record.id),
            metadata={"statusLocked": binding.status_locked, "milestoneLocks": binding.milestone_locks,
                      "dataLocks": binding.data_locks},
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
                error: ProviderError | None = None, prepared_pods: dict | None = None) -> None:
        if binding.provider_code == "AJ" and binding.tracking_record.upload.airport_of_arrival != "LHR":
            return
        awb = binding.tracking_record.upload.air_waybill_number
        binding.last_checked_at = now
        if error:
            binding.last_error = error.detail
            binding.sync_report = {"request": {"state": "error", "detail": error.detail}}
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
        report = {}
        new_paths: list[str] = []
        obsolete_paths: list[str] = []
        if special:
            binding.last_error = "AJ 提单已拆分或被扣留／销毁，请管理员核查"
            self._incident(binding, awb, "special_shipment", binding.last_error, now)
        elif code not in PROVIDER_STATUS_MAPS[binding.provider_code]:
            binding.last_error = f"AJ 返回未知阶段：{code}"
            self._incident(binding, awb, "unknown_stage", binding.last_error, now)
        else:
            record = binding.tracking_record
            mapped = PROVIDER_STATUS_MAPS[binding.provider_code][code]
            report["status"] = {"state": "locked" if binding.status_locked else "synced", "source": "stage.code", "value": mapped}
            if not binding.status_locked and record.status != mapped:
                old = record.status
                record.status = mapped
                try:
                    record.status_changed_at = parse_time(normalized["stage_entered_at"]) or now
                except (TypeError, ValueError):
                    record.status_changed_at = now
                self._event(binding, awb, "status_changed", {"from": old, "to": mapped, "stage": code})
            milestones = shipment.get("milestones") or {}
            milestone_sources = {"airline_record_created_at": "record_created_airline_at", "airline_arrived_at": "status_1_at",
                                 "noa_at": "status_1_at",
                                 "aj_warehouse_arrived_at": "pick_up_at", "collection_at": "pick_up_at",
                                 "scanned_at": "pick_up_at", "customs_clearance_at": "customs_clearance_at"}
            try:
                quantities = aj_quantity_summary(shipment, record.upload.pieces)
            except ValueError as exc:
                quantities = None
                for field in ("received_total", "outbound_count", "outbound_at"):
                    report[field] = {"state": "error", "detail": str(exc)}
            if quantities is not None:
                if quantities.warning:
                    report["quantity_check"] = {"state": "warning", "detail": quantities.warning}
                if quantities.total is not None and "received_total" not in binding.data_locks:
                    if record.received_total != quantities.total:
                        record.received_total = quantities.total
                        self._event(binding, awb, "count_changed", {"field": "received_total", "to": quantities.total})
                    report["received_total"] = {"state": "synced", "source": quantities.source, "value": quantities.total}
            try:
                handover = aj_handover(quantities) if quantities is not None else None
            except (TypeError, ValueError) as exc:
                handover = None
                report["outbound_count"] = {"state": "error", "detail": str(exc)}
                report["outbound_at"] = {"state": "error", "detail": str(exc)}
            if handover is not None:
                outbound_count, outbound_at = handover
                if "outbound_count" not in binding.data_locks:
                    if record.outbound_count != outbound_count:
                        record.outbound_count = outbound_count
                        self._event(binding, awb, "count_changed", {"field": "outbound_count", "to": outbound_count})
                    report["outbound_count"] = {"state": "synced", "source": "vendors[].handed_over_at / packages", "value": outbound_count}
                if outbound_at is not None:
                    milestones = {**milestones, "handover_complete_at": outbound_at.isoformat()}
                    milestone_sources["outbound_at"] = "handover_complete_at"
            for field in sorted(MILESTONE_FIELDS):
                source = milestone_sources.get(field)
                if field in binding.milestone_locks:
                    report[field] = {"state": "locked"}
                    continue
                if field in report:
                    continue
                milestone = milestones.get(source) if source else None
                if milestone is None or milestone == "":
                    report[field] = {"state": "unavailable", "detail": "AJ 尚未提供对应时间"}
                    continue
                try:
                    parsed = parse_time(milestone)
                except (TypeError, ValueError):
                    report[field] = {"state": "error", "detail": f"AJ {source} 时间格式无效"}
                else:
                    report[field] = {"state": "synced", "source": "max(vendors[].handed_over_at)" if field == "outbound_at" else f"milestones.{source}", "value": milestone}
                    if field == "noa_at":
                        report[field]["detail"] = "AJ 未提供独立 NOA 时间，按航司到达时间代填"
                    if field == "scanned_at":
                        report[field]["detail"] = "按 AJ pick_up_at 代填扫描入仓时间"
                    if field == "collection_at":
                        report[field]["detail"] = "按 AJ pick_up_at 代填提货时间"
                    if aware(getattr(record, field)) != parsed:
                        setattr(record, field, parsed)
                        self._event(binding, awb, "milestone_changed", {"field": field, "to": milestone})
            for field in DATA_FIELDS - {"pod_files"}:
                if field in binding.data_locks:
                    report[field] = {"state": "locked"}
                    continue
                if field in report:
                    continue
                report[field] = {"state": "unavailable",
                                 "detail": "等待 AJ 数量或包裹明细数据"}
        try:
            if not special and code in PROVIDER_STATUS_MAPS[binding.provider_code]:
                self._sync_pods(binding, prepared_pods, report, new_paths, obsolete_paths)
                errors = [item["detail"] for item in report.values() if item["state"] == "error"]
                if errors:
                    binding.last_error = "；".join(dict.fromkeys(errors))
                    self._incident(binding, awb, "sync_fields", binding.last_error, now)
                else:
                    self._resolve(binding.id, now)
            binding.sync_report = report or {"request": {"state": "error", "detail": binding.last_error}}
            self.db.commit()
        except Exception:
            self.db.rollback()
            for path in new_paths:
                delete_pod_content(path, self.settings)
            raise
        for path in obsolete_paths:
            delete_pod_content(path, self.settings)

    def run_due(self, client: AJClient | None = None, now: datetime | None = None) -> int:
        provided_now = now
        now = now or datetime.now(timezone.utc)
        bindings = self.db.scalars(select(DownstreamBinding).options(
            joinedload(DownstreamBinding.tracking_record).joinedload(WaybillTrackingRecord.upload)
        )).all()
        due = [item for item in bindings if item.tracking_record.upload.status == "approved" and
               (item.provider_code != "AJ" or item.tracking_record.upload.airport_of_arrival == "LHR") and
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
            prepared_pods = None
            try:
                if previous_request_at is not None:
                    time.sleep(max(0.0, minimum_interval - (time.monotonic() - previous_request_at)))
                previous_request_at = time.monotonic()
                result = provider_client.fetch(binding.tracking_record.upload.air_waybill_number)
                try:
                    normalized = PROVIDER_NORMALIZERS[binding.provider_code](result)
                except (KeyError, TypeError, AttributeError, ValueError):
                    normalized = None
                if (normalized and normalized["awb"] == binding.tracking_record.upload.air_waybill_number
                        and not normalized["special"] and normalized["stage_code"] in PROVIDER_STATUS_MAPS[binding.provider_code]):
                    prepared_pods = self._prepare_pods(binding, result, provider_client)
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
            if (current.tracking_record.upload.status != "approved"
                    or (current.provider_code == "AJ" and current.tracking_record.upload.airport_of_arrival != "LHR")):
                self.db.rollback()
                continue
            self.process(current, provided_now or datetime.now(timezone.utc),
                         shipment=result, error=fetch_error, prepared_pods=prepared_pods)
        return len(due)
