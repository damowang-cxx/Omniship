from datetime import datetime, timedelta, timezone
from decimal import Decimal
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest
import httpx
from sqlalchemy import select

from app.db.models import (
    DownstreamBinding, DownstreamIncident, DownstreamSyncEvent,
    SupplierVersion, WaybillPodFile, WaybillTrackingRecord, WaybillUpload,
)
from app.repositories.waybill_repository import WaybillRepository
from app.schemas.waybill import WaybillUpdateRequest
from app.services.downstream_sync import AJ_BASE_URL, AJClient, AJ_STATUS_MAP, DownstreamService, ProviderError
from app.core.config import get_settings
from app.services.waybill_service import WaybillService
from tests.auth_helpers import create_test_user, login


AWB = "932-77644803"
NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


def create_waybill(db):
    admin = create_test_user(db, email="admin@example.com", role="admin")
    user = create_test_user(db, email="user@example.com")
    version = db.scalars(select(SupplierVersion)).first()
    upload = WaybillUpload(
        user_id=user.id, supplier_id=version.supplier_id, supplier_version_id=version.id,
        shipment_type="Air", air_waybill_number=AWB, normalized_air_waybill_number="93277644803",
        gross_weight_kg=Decimal("12.500"), pieces=12, status="approved", reviewed_at=NOW,
        airport_of_departure="HKG", airport_of_arrival="LHR",
    )
    db.add(upload)
    db.flush()
    record = WaybillRepository(db).create_for_upload(upload=upload, public_code="AJTEST01")
    db.commit()
    return admin, user, record


def shipment(stage="AWAITING_CUSTOMS", clearance="2026-11-16T10:00:00+00:00", **extra):
    return {
        "awb": AWB,
        "stage": {"code": stage, "entered_at": "2026-11-16T11:00:00+00:00"},
        "completion": {"code": "IN_TRANSIT"},
        "milestones": {"customs_clearance_at": clearance},
        "last_updated_at": "2026-11-16T11:30:00+00:00",
        "split": {"is_split_parent": False}, "archived": None,
        **extra,
    }


def binding_for(db, record):
    return db.scalar(select(DownstreamBinding).where(DownstreamBinding.tracking_record_id == record.id))


@pytest.mark.parametrize("airport", ["AMS", "CDG"])
def test_only_lhr_waybills_can_be_assigned_to_aj(client, db_session, airport):
    admin, _, record = create_waybill(db_session)
    record.upload.airport_of_arrival = airport
    db_session.commit()
    login(client, email=admin.email)
    response = client.put(f"/api/v1/admin/downstream/waybills/{record.public_code}", json={"providerCode": "AJ"})
    assert response.status_code == 400
    assert "仅 LHR" in response.json()["detail"]
    assert binding_for(db_session, record) is None


def test_existing_non_lhr_binding_is_never_polled_or_applied_and_can_be_removed(db_session):
    admin, _, record = create_waybill(db_session)
    service = DownstreamService(db_session)
    service.assign(admin, record.public_code, "AJ")
    record.upload.airport_of_arrival = "AMS"
    db_session.commit()

    class UnexpectedClient:
        def fetch(self, awb):
            pytest.fail("Non-LHR waybills must not call AJ")

    assert service.run_due(UnexpectedClient(), NOW) == 0
    binding = binding_for(db_session, record)
    service.process(binding, NOW, shipment("HANDED_OVER"))
    db_session.refresh(record)
    assert record.status == "created"
    assert binding.last_checked_at is None
    service.assign(admin, record.public_code, None)
    assert binding_for(db_session, record) is None


def test_airport_change_during_fetch_discards_aj_response(db_session):
    admin, _, record = create_waybill(db_session)
    service = DownstreamService(db_session)
    service.assign(admin, record.public_code, "AJ")

    class AirportChangingClient:
        def fetch(self, awb):
            record.upload.airport_of_arrival = "AMS"
            db_session.commit()
            return shipment("HANDED_OVER")

    service.run_due(AirportChangingClient(), NOW)
    db_session.refresh(record)
    assert record.status == "created"
    assert record.customs_clearance_at is None


def test_warehouse_arrival_is_lhr_only_and_customer_response_hides_provider(client, db_session):
    admin, user, record = create_waybill(db_session)
    record.aj_warehouse_arrived_at = NOW
    db_session.add(WaybillPodFile(
        tracking_record_id=record.id, original_filename="proof.pdf", content_type="application/pdf",
        size_bytes=5, storage_path="proof.pdf", sha256="0" * 64,
        provider_code="AJ", provider_document_id="41", provider_document_version=2,
        provider_vendor_code="INTERNAL", provider_uploaded_at=NOW, provider_note="AJ internal note",
    ))
    db_session.commit()
    login(client, email=user.email)
    body = client.get(f"/api/v1/waybills/{record.public_code}").json()
    assert body["warehouseArrivedAt"] is not None
    assert "ajWarehouseArrivedAt" not in body
    assert all(value is None for field, value in body["podFiles"][0].items() if field.startswith("provider"))
    assert "AJ internal note" not in str(body)
    login(client, email=admin.email)
    body = client.get(f"/api/v1/waybills/{record.public_code}").json()
    assert body["podFiles"][0]["providerCode"] == "AJ"
    record.upload.airport_of_arrival = "AMS"
    db_session.commit()
    assert client.get(f"/api/v1/waybills/{record.public_code}").json()["warehouseArrivedAt"] is None
    response = client.patch(f"/api/v1/waybills/{record.public_code}", json={"warehouseArrivedAt": NOW.isoformat()})
    assert response.status_code == 400
    record.upload.airport_of_arrival = "LHR"
    db_session.commit()
    response = client.patch(f"/api/v1/waybills/{record.public_code}", json={"warehouseArrivedAt": (NOW + timedelta(hours=1)).isoformat()})
    assert response.status_code == 200
    assert response.json()["warehouseArrivedAt"].startswith("2026-11-16T13:00:00")


@pytest.mark.parametrize("stage,expected", AJ_STATUS_MAP.items())
def test_each_aj_stage_maps_to_local_status(db_session, stage, expected):
    admin, _, record = create_waybill(db_session)
    service = DownstreamService(db_session)
    service.assign(admin, record.public_code, "AJ")
    service.process(binding_for(db_session, record), NOW, shipment(stage))
    db_session.refresh(record)
    assert record.status == expected
    assert record.customs_clearance_at.replace(tzinfo=timezone.utc) == NOW - timedelta(hours=2)


def test_manual_status_and_milestone_are_locked_until_released(client, db_session):
    admin, _, record = create_waybill(db_session)
    assert login(client, email=admin.email).status_code == 200
    assert client.put(f"/api/v1/admin/downstream/waybills/{record.public_code}", json={"providerCode": "AJ"}).status_code == 200
    service = DownstreamService(db_session)
    service.process(binding_for(db_session, record), NOW, shipment())
    response = client.patch(f"/api/v1/waybills/{record.public_code}", json={
        "status": "scanning", "customsClearanceAt": "2026-11-15T09:00:00Z",
    })
    assert response.status_code == 200
    binding = binding_for(db_session, record)
    assert binding.status_locked is True
    assert binding.milestone_locks == ["customs_clearance_at"]
    service.process(binding, NOW + timedelta(minutes=5), shipment("HANDED_OVER", "2026-11-16T12:00:00Z"))
    db_session.refresh(record)
    assert record.status == "scanning"
    assert record.customs_clearance_at.replace(tzinfo=timezone.utc) == datetime(2026, 11, 15, 9, tzinfo=timezone.utc)
    assert client.patch(f"/api/v1/admin/downstream/waybills/{record.public_code}/locks", json={
        "statusLocked": False, "milestoneLocks": [],
    }).status_code == 200
    service.process(binding, NOW + timedelta(minutes=10), shipment("HANDED_OVER", "2026-11-16T12:00:00Z"))
    db_session.refresh(record)
    assert record.status == "outbound"
    assert record.customs_clearance_at.replace(tzinfo=timezone.utc) == NOW


def test_missing_twice_after_five_minutes_creates_one_recoverable_incident(db_session):
    admin, _, record = create_waybill(db_session)
    service = DownstreamService(db_session)
    service.assign(admin, record.public_code, "AJ")
    binding = binding_for(db_session, record)
    missing = ProviderError("not_found", "AJ 未找到该提单，或当前账号无权访问")
    service.process(binding, NOW, error=missing)
    assert db_session.scalars(select(DownstreamIncident)).all() == []
    service.process(binding, NOW + timedelta(minutes=4), error=missing)
    assert db_session.scalars(select(DownstreamIncident)).all() == []
    service.process(binding, NOW + timedelta(minutes=5), error=missing)
    incidents = db_session.scalars(select(DownstreamIncident)).all()
    assert len(incidents) == 1 and incidents[0].resolved_at is None
    service.process(binding, NOW + timedelta(minutes=10), error=missing)
    assert len(db_session.scalars(select(DownstreamIncident)).all()) == 1
    service.process(binding, NOW + timedelta(minutes=15), shipment())
    db_session.refresh(incidents[0])
    assert incidents[0].resolved_at is not None


def test_network_failure_alerts_only_after_second_poll(db_session):
    admin, _, record = create_waybill(db_session)
    service = DownstreamService(db_session)
    service.assign(admin, record.public_code, "AJ")
    binding = binding_for(db_session, record)
    network_error = ProviderError("network", "AJ 服务返回 HTTP 503")
    service.process(binding, NOW, error=network_error)
    assert db_session.scalars(select(DownstreamIncident)).all() == []
    service.process(binding, NOW + timedelta(minutes=5), error=network_error)
    assert db_session.scalar(select(DownstreamIncident)).kind == "network"


def test_special_shipment_does_not_overwrite_status(db_session):
    admin, _, record = create_waybill(db_session)
    service = DownstreamService(db_session)
    service.assign(admin, record.public_code, "AJ")
    service.process(binding_for(db_session, record), NOW, shipment("HANDED_OVER", split={"is_split_parent": True}))
    db_session.refresh(record)
    assert record.status == "created"
    assert db_session.scalar(select(DownstreamIncident)).kind == "special_shipment"


def test_downstream_endpoints_are_admin_only_and_user_waybill_stays_clean(client, db_session):
    admin, user, record = create_waybill(db_session)
    assert login(client, email=admin.email).status_code == 200
    assign = client.put(f"/api/v1/admin/downstream/waybills/{record.public_code}", json={"providerCode": "AJ"})
    assert assign.status_code == 200
    assert client.get("/api/v1/admin/downstream/bindings").json()[0]["providerCode"] == "AJ"
    assert login(client, email=user.email).status_code == 200
    assert client.get("/api/v1/admin/downstream/bindings").status_code == 403
    assert client.get("/api/v1/admin/downstream/incidents").status_code == 403
    assert client.get(f"/api/v1/admin/downstream/waybills/{record.public_code}").status_code == 403
    assert client.put(f"/api/v1/admin/downstream/waybills/{record.public_code}", json={"providerCode": None}).status_code == 403
    response = client.get(f"/api/v1/waybills/{record.public_code}")
    assert response.status_code == 200
    assert "providerCode" not in response.json()
    assert "remoteStage" not in response.json()


def test_repeated_identical_snapshot_does_not_repeat_status_event(db_session):
    admin, _, record = create_waybill(db_session)
    service = DownstreamService(db_session)
    service.assign(admin, record.public_code, "AJ")
    binding = binding_for(db_session, record)
    service.process(binding, NOW, shipment())
    service.process(binding, NOW + timedelta(minutes=5), shipment())
    events = db_session.scalars(select(DownstreamSyncEvent).where(DownstreamSyncEvent.event_type == "status_changed")).all()
    assert len(events) == 1
    milestone_events = db_session.scalars(select(DownstreamSyncEvent).where(DownstreamSyncEvent.event_type == "milestone_changed")).all()
    assert len(milestone_events) == 1


def test_aj_correction_can_move_unlocked_status_backward(db_session):
    admin, _, record = create_waybill(db_session)
    service = DownstreamService(db_session)
    service.assign(admin, record.public_code, "AJ")
    binding = binding_for(db_session, record)
    service.process(binding, NOW, shipment("HANDED_OVER"))
    service.process(binding, NOW + timedelta(minutes=5), shipment("AWAITING_CUSTOMS"))
    db_session.refresh(record)
    assert record.status == "pending_clearance"


def test_due_polling_and_removal_stop_future_queries(db_session):
    admin, _, record = create_waybill(db_session)
    service = DownstreamService(db_session)
    service.assign(admin, record.public_code, "AJ")

    class FakeClient:
        calls = 0

        def fetch(self, awb):
            self.calls += 1
            assert awb == AWB
            return shipment()

    client = FakeClient()
    assert service.run_due(client, NOW) == 1
    assert service.run_due(client, NOW + timedelta(minutes=4)) == 0
    assert service.run_due(client, NOW + timedelta(minutes=5)) == 1
    assert client.calls == 2
    service.stop_for_removed_record(record)
    db_session.commit()
    assert service.run_due(client, NOW + timedelta(minutes=10)) == 0


def test_aj_client_reads_root_style_credentials_and_encodes_awb(tmp_path):
    credentials = tmp_path / "aj-credentials.env"
    credentials.write_text("AJ_API_USERNAME=test-user\nAJ_API_PASSWORD=test-pass\n", encoding="utf-8")

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"].startswith("Basic ")
        assert request.url.raw_path.endswith(b"shipments/932-77644803%2F1")
        return httpx.Response(200, json={"ok": True, "shipment": shipment(awb="932-77644803/1")})

    client = AJClient(credentials_path=credentials, transport=httpx.MockTransport(handle))
    assert client.fetch("932-77644803/1")["awb"] == "932-77644803/1"


def test_unassigned_during_fetch_does_not_apply_late_response(db_session):
    admin, _, record = create_waybill(db_session)
    service = DownstreamService(db_session)
    service.assign(admin, record.public_code, "AJ")

    class FakeClient:
        def fetch(self, awb):
            service.assign(admin, record.public_code, None)
            return shipment("HANDED_OVER")

    service.run_due(FakeClient(), NOW)
    db_session.refresh(record)
    assert record.status == "created"
    assert binding_for(db_session, record) is None


def test_review_change_stops_sync_and_resolves_incident(client, db_session):
    admin, _, record = create_waybill(db_session)
    assert login(client, email=admin.email).status_code == 200
    service = DownstreamService(db_session)
    service.assign(admin, record.public_code, "AJ")
    service.process(binding_for(db_session, record), NOW,
                    error=ProviderError("authentication", "AJ 账号认证失败（HTTP 401）"))
    response = client.patch(f"/api/v1/waybill-uploads/{record.upload_id}/status", json={"status": "rejected"})
    assert response.status_code == 200
    assert binding_for(db_session, record) is None
    assert db_session.scalar(select(DownstreamIncident)).resolved_at is not None


def completed_shipment():
    result = shipment("HANDED_OVER")
    result["packages"] = 12
    result["milestones"].update({
        "record_created_airline_at": "2026-11-15T09:00:00+00:00",
        "status_1_at": "2026-11-15T12:00:00+00:00",
        "pick_up_at": "2026-11-16T08:00:00+00:00",
    })
    result["vendors"] = [{
        "code": "DPD", "packages": 12, "handed_over_at": "2026-11-16T11:00:00+00:00",
        "pod_documents": [{"id": 41, "file_name": "proof.pdf", "version": 1, "is_current": True,
                           "uploaded_at": "2026-11-16T11:30:00+00:00", "note": None,
                           "download_url": f"{AJ_BASE_URL}/files/pod/41"}],
    }]
    result["orphan_pod_documents"] = []
    return result


class PodClient:
    def __init__(self, result):
        self.result = result
        self.downloads = []
        self.failure = None

    def fetch(self, awb):
        assert awb == AWB
        return deepcopy(self.result)

    def download_pod(self, document_id, download_url=None):
        self.downloads.append(document_id)
        if self.failure:
            raise self.failure
        return b"%PDF-1.4\nproof " + document_id.encode()


def test_documented_times_handover_and_pods_sync_without_inventing_missing_fields(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "upload_storage_dir", tmp_path)
    admin, _, record = create_waybill(db_session)
    service = DownstreamService(db_session)
    service.assign(admin, record.public_code, "AJ")
    provider = PodClient(completed_shipment())
    assert service.run_due(provider, NOW) == 1
    db_session.refresh(record)
    binding = binding_for(db_session, record)
    assert record.status == "outbound"
    assert record.outbound_count == 12
    assert record.outbound_at.replace(tzinfo=timezone.utc) == NOW - timedelta(hours=1)
    assert record.airline_record_created_at.replace(tzinfo=timezone.utc) == NOW - timedelta(days=1, hours=3)
    assert record.airline_arrived_at.replace(tzinfo=timezone.utc) == NOW - timedelta(days=1)
    assert record.noa_at.replace(tzinfo=timezone.utc) == record.airline_arrived_at.replace(tzinfo=timezone.utc)
    assert record.aj_warehouse_arrived_at.replace(tzinfo=timezone.utc) == NOW - timedelta(hours=4)
    assert record.scanned_at.replace(tzinfo=timezone.utc) == NOW - timedelta(hours=1)
    assert record.collection_at is None
    assert binding.sync_report["noa_at"]["state"] == "synced"
    assert binding.sync_report["noa_at"]["source"] == "milestones.status_1_at"
    assert binding.sync_report["scanned_at"]["source"] == "min(vendors[].handed_over_at)"
    assert record.received_count == record.in_warehouse_count == 0
    assert binding.sync_report["received_count"]["state"] == "unavailable"
    assert binding.sync_report["parcels"]["state"] == "unavailable"
    pod = db_session.scalars(select(WaybillPodFile)).one()
    assert pod.provider_document_id == "41" and pod.provider_vendor_code == "DPD"
    assert Path(pod.storage_path).read_bytes().startswith(b"%PDF")
    assert service.run_due(provider, NOW + timedelta(minutes=5)) == 1
    assert provider.downloads == ["41"]
    assert len(db_session.scalars(select(WaybillPodFile)).all()) == 1


def test_noa_uses_airline_arrival_when_available_but_keeps_its_own_manual_lock(client, db_session):
    admin, _, record = create_waybill(db_session)
    service = DownstreamService(db_session)
    service.assign(admin, record.public_code, "AJ")
    result = shipment()
    binding = binding_for(db_session, record)

    service.process(binding, NOW, result)
    assert record.airline_arrived_at is record.noa_at is None
    assert binding.sync_report["noa_at"]["state"] == "unavailable"

    result["milestones"]["status_1_at"] = "2026-11-15T12:00:00+00:00"
    service.process(binding, NOW + timedelta(minutes=5), result)
    assert record.airline_arrived_at.replace(tzinfo=timezone.utc) == NOW - timedelta(days=1)
    assert record.noa_at.replace(tzinfo=timezone.utc) == NOW - timedelta(days=1)

    login(client, email=admin.email)
    response = client.patch(f"/api/v1/waybills/{record.public_code}", json={
        "noaAt": "2026-11-15T10:00:00Z",
    })
    assert response.status_code == 200, response.text
    assert "noa_at" in binding.milestone_locks
    assert "airline_arrived_at" not in binding.milestone_locks

    result["milestones"]["status_1_at"] = "2026-11-15T13:00:00+00:00"
    service.process(binding, NOW + timedelta(minutes=10), result)
    assert record.airline_arrived_at.replace(tzinfo=timezone.utc) == NOW - timedelta(days=1) + timedelta(hours=1)
    assert record.noa_at.replace(tzinfo=timezone.utc) == NOW - timedelta(days=1, hours=2)
    assert binding.sync_report["noa_at"]["state"] == "locked"


@pytest.mark.parametrize("extension,media_type", [
    (".doc", "application/msword"),
    (".docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    (".ajpod", "application/octet-stream"),
])
def test_aj_source_pods_import_download_and_deduplicate_without_relaxing_manual_uploads(
    client, db_session, tmp_path, monkeypatch, extension, media_type,
):
    monkeypatch.setattr(get_settings(), "upload_storage_dir", tmp_path)
    admin, customer, record = create_waybill(db_session)
    result = completed_shipment()
    filename = f"{AWB}_EMPTYBOX_v1{extension}"
    result["vendors"][0]["pod_documents"][0]["file_name"] = filename
    content = b"{\\rtf1\\ansi Empty box POD}"
    if extension == ".docx":
        output = BytesIO()
        with ZipFile(output, "w") as archive:
            archive.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
            archive.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>')
        content = output.getvalue()

    class SourceFormatClient(PodClient):
        def download_pod(self, document_id, download_url=None):
            self.downloads.append(document_id)
            return content

    service = DownstreamService(db_session)
    service.assign(admin, record.public_code, "AJ")
    provider = SourceFormatClient(result)
    service.run_due(provider, NOW)
    file = db_session.scalars(select(WaybillPodFile)).one()
    assert file.original_filename == filename and file.content_type == media_type
    assert Path(file.storage_path).read_bytes() == content
    binding = binding_for(db_session, record)
    assert binding.last_error is None and binding.sync_report["pod_files"]["state"] == "synced"
    service.run_due(provider, NOW + timedelta(minutes=5))
    assert provider.downloads == ["41"]
    assert len(db_session.scalars(select(WaybillPodFile)).all()) == 1
    login(client, email=customer.email)
    downloaded = client.get(f"/api/v1/waybills/{record.public_code}/pod/{file.id}/download")
    assert downloaded.status_code == 200, downloaded.text
    assert downloaded.content == content
    assert downloaded.headers["content-type"] == media_type
    assert downloaded.headers["content-disposition"].startswith("attachment;")
    assert filename in downloaded.headers["content-disposition"]
    assert downloaded.headers["x-content-type-options"] == "nosniff"
    login(client, email=admin.email)
    uploaded = client.post(f"/api/v1/waybills/{record.public_code}/pod", files={"podFile": (filename, content, media_type)})
    assert uploaded.status_code == 400, uploaded.text
    assert "PDF, JPEG, or PNG" in uploaded.json()["detail"]


@pytest.mark.parametrize("bad_file", ["empty.doc", "oversize.doc", "invalid.pdf"])
def test_invalid_aj_files_keep_previous_pod_and_do_not_block_other_fields(db_session, tmp_path, monkeypatch, bad_file):
    monkeypatch.setattr(get_settings(), "upload_storage_dir", tmp_path)
    admin, _, record = create_waybill(db_session)
    service = DownstreamService(db_session)
    service.assign(admin, record.public_code, "AJ")
    service.run_due(PodClient(completed_shipment()), NOW)
    old_file = db_session.scalars(select(WaybillPodFile)).one()
    old_path = Path(old_file.storage_path)
    result = completed_shipment()
    result["milestones"]["customs_clearance_at"] = NOW.isoformat()
    result["vendors"][0]["pod_documents"][0].update({"id": 42, "file_name": bad_file, "version": 2,
                                                      "download_url": f"{AJ_BASE_URL}/files/pod/42"})

    class InvalidFileClient(PodClient):
        def download_pod(self, document_id, download_url=None):
            if bad_file == "oversize.doc":
                return b"x" * (10 * 1024 * 1024 + 1)
            return b"not a PDF" if bad_file == "invalid.pdf" else b""

    service.run_due(InvalidFileClient(result), NOW + timedelta(minutes=5))
    assert db_session.scalars(select(WaybillPodFile)).one().id == old_file.id
    assert old_path.is_file()
    assert binding_for(db_session, record).sync_report["pod_files"]["state"] == "error"
    assert record.customs_clearance_at.replace(tzinfo=timezone.utc) == NOW
    assert record.outbound_count == 12


def test_quantity_mismatch_reports_both_values_once_preserves_counts_and_recovers(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "upload_storage_dir", tmp_path)
    admin, _, record = create_waybill(db_session)
    service = DownstreamService(db_session)
    service.assign(admin, record.public_code, "AJ")
    result = completed_shipment()
    provider = PodClient(result)
    service.run_due(provider, NOW)
    old_outbound_at = record.outbound_at
    result["packages"] = result["vendors"][0]["packages"] = 14
    result["stage"]["code"] = "AWAITING_COLLECTION"
    result["milestones"]["customs_clearance_at"] = NOW.isoformat()
    service.run_due(provider, NOW + timedelta(minutes=5))
    binding = binding_for(db_session, record)
    assert "AJ 总件数为 14，本地提单件数为 12" in binding.last_error
    assert binding.last_error.count("AJ 总件数") == 1
    assert record.received_total == record.outbound_count == 12
    assert record.outbound_at == old_outbound_at
    assert record.status == "cleared" and record.customs_clearance_at.replace(tzinfo=timezone.utc) == NOW
    assert binding.sync_report["pod_files"]["state"] == "synced"
    for field in ("received_total", "outbound_count", "outbound_at"):
        assert binding.sync_report[field]["state"] == "error"
    incident = db_session.scalars(select(DownstreamIncident)).one()
    service.run_due(provider, NOW + timedelta(minutes=10))
    assert db_session.scalars(select(DownstreamIncident)).one().id == incident.id
    result["packages"] = result["vendors"][0]["packages"] = 12
    service.run_due(provider, NOW + timedelta(minutes=15))
    assert binding.last_error is None
    assert incident.resolved_at is not None
    assert binding.sync_report["outbound_count"]["state"] == "synced"


def test_vendor_quantities_matching_local_pieces_override_top_level_with_nonblocking_warning(db_session):
    admin, _, record = create_waybill(db_session)
    record.upload.pieces = record.received_total = 98
    db_session.commit()
    service = DownstreamService(db_session)
    service.assign(admin, record.public_code, "AJ")
    result = shipment("NOT_ARRIVED", clearance=None, packages=1, shipper_ref="RM(98)", vendors=[{
        "code": "RM", "packages": 97, "handed_over_at": None, "pod_documents": [],
    }], orphan_pod_documents=[])
    # An old blocking incident must resolve once channel quantities are corrected.
    service.process(binding_for(db_session, record), NOW, result)
    incident = db_session.scalars(select(DownstreamIncident)).one()
    result["vendors"][0]["packages"] = 98
    service.process(binding_for(db_session, record), NOW + timedelta(minutes=5), result)
    binding = binding_for(db_session, record)
    assert binding.last_error is None and incident.resolved_at is not None
    assert binding.sync_report["quantity_check"]["state"] == "warning"
    assert "顶层 packages 为 1" in binding.sync_report["quantity_check"]["detail"]
    assert "渠道件数合计为 98（RM: 98），本地提单件数为 98" in binding.sync_report["quantity_check"]["detail"]
    assert binding.sync_report["received_total"] == {"state": "synced", "source": "vendors[].packages", "value": 98}
    assert record.received_total == 98 and record.outbound_count == 0 and record.outbound_at is None
    assert record.status == "created" and record.received_count == record.in_warehouse_count == 0
    result["vendors"][0].update({"packages": 60, "handed_over_at": "2026-11-16T10:00:00+00:00"})
    result["vendors"].append({"code": "EVRI", "packages": 38, "handed_over_at": None, "pod_documents": []})
    service.process(binding, NOW + timedelta(minutes=10), result)
    assert record.outbound_count == 60 and record.outbound_at is None
    assert record.scanned_at.replace(tzinfo=timezone.utc) == NOW - timedelta(hours=2)
    result["vendors"][1]["handed_over_at"] = "2026-11-16T11:45:00+00:00"
    service.process(binding, NOW + timedelta(minutes=15), result)
    assert record.outbound_count == 98
    assert record.outbound_at.replace(tzinfo=timezone.utc) == NOW - timedelta(minutes=15)
    assert record.upload.pieces == 98 and binding.snapshot["packages"] == 1
    assert binding.last_error is None


def test_matching_top_level_does_not_bypass_a_vendor_total_that_differs_from_local(db_session):
    admin, _, record = create_waybill(db_session)
    service = DownstreamService(db_session)
    service.assign(admin, record.public_code, "AJ")
    result = completed_shipment()
    service.process(binding_for(db_session, record), NOW, result)
    previous_outbound_at = record.outbound_at
    result["vendors"][0]["packages"] = 98
    service.process(binding_for(db_session, record), NOW + timedelta(minutes=5), result)
    binding = binding_for(db_session, record)
    assert "本地提单件数为 12，渠道件数合计为 98" in binding.last_error
    assert record.upload.pieces == record.received_total == record.outbound_count == 12
    assert record.outbound_at == previous_outbound_at
    assert record.scanned_at.replace(tzinfo=timezone.utc) == NOW - timedelta(hours=1)
    assert "quantity_check" not in binding.sync_report
    for field in ("received_total", "outbound_count", "outbound_at", "scanned_at"):
        assert binding.sync_report[field]["state"] == "error"


def test_partial_handover_counts_channels_and_waits_for_all_times(db_session):
    admin, _, record = create_waybill(db_session)
    service = DownstreamService(db_session)
    service.assign(admin, record.public_code, "AJ")
    result = completed_shipment()
    result["vendors"][0]["packages"] = 4
    result["vendors"].append({"code": "EVRI", "packages": 8, "handed_over_at": None, "pod_documents": []})
    service.process(binding_for(db_session, record), NOW, result)
    assert record.outbound_count == 4
    assert record.outbound_at is None
    assert record.scanned_at.replace(tzinfo=timezone.utc) == NOW - timedelta(hours=1)
    result["vendors"][1]["handed_over_at"] = "2026-11-16T10:45:00+00:00"
    service.process(binding_for(db_session, record), NOW + timedelta(minutes=5), result)
    assert record.outbound_count == 12
    assert record.scanned_at.replace(tzinfo=timezone.utc) == NOW - timedelta(hours=1, minutes=15)
    assert record.outbound_at.replace(tzinfo=timezone.utc) == NOW - timedelta(hours=1)


def test_pod_completion_does_not_infer_handover_count_and_mismatch_is_reported(db_session):
    admin, _, record = create_waybill(db_session)
    service = DownstreamService(db_session)
    service.assign(admin, record.public_code, "AJ")
    result = completed_shipment()
    result["completion"]["code"] = "PARTIAL"
    result["vendors"][0]["handed_over_at"] = None
    service.process(binding_for(db_session, record), NOW, result)
    assert record.outbound_count == 0 and record.outbound_at is None
    assert record.scanned_at is None
    assert binding_for(db_session, record).sync_report["scanned_at"]["state"] == "unavailable"
    result["vendors"][0]["packages"] = 13
    service.process(binding_for(db_session, record), NOW + timedelta(minutes=5), result)
    assert record.outbound_count == 0 and record.outbound_at is None
    assert binding_for(db_session, record).sync_report["outbound_count"]["state"] == "error"


def test_manual_counts_and_all_documented_times_lock_until_explicitly_unlocked(client, db_session):
    admin, _, record = create_waybill(db_session)
    service = DownstreamService(db_session)
    service.assign(admin, record.public_code, "AJ")
    service.process(binding_for(db_session, record), NOW, completed_shipment())
    login(client, email=admin.email)
    response = client.patch(f"/api/v1/waybills/{record.public_code}", json={
        "outboundCount": 5, "airlineArrivedAt": "2026-11-15T10:00:00Z",
        "scannedAt": "2026-11-16T09:00:00Z",
    })
    assert response.status_code == 200, response.text
    binding = binding_for(db_session, record)
    assert "outbound_count" in binding.data_locks
    assert "airline_arrived_at" in binding.milestone_locks
    assert "scanned_at" in binding.milestone_locks
    service.process(binding, NOW + timedelta(minutes=5), completed_shipment())
    assert record.outbound_count == 5
    assert record.airline_arrived_at.replace(tzinfo=timezone.utc) == NOW - timedelta(days=1, hours=2)
    assert record.scanned_at.replace(tzinfo=timezone.utc) == NOW - timedelta(hours=3)
    response = client.patch(f"/api/v1/admin/downstream/waybills/{record.public_code}/locks", json={"dataLocks": [], "milestoneLocks": []})
    assert response.status_code == 200, response.text
    service.process(binding, NOW + timedelta(minutes=10), completed_shipment())
    assert record.outbound_count == 12
    assert record.airline_arrived_at.replace(tzinfo=timezone.utc) == NOW - timedelta(days=1)
    assert record.scanned_at.replace(tzinfo=timezone.utc) == NOW - timedelta(hours=1)


def test_pod_new_version_replaces_synced_file_preserves_manual_file_and_retries_errors(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "upload_storage_dir", tmp_path)
    admin, _, record = create_waybill(db_session)
    manual_path = tmp_path / "manual.pdf"
    manual_path.write_bytes(b"%PDF manual")
    db_session.add(WaybillPodFile(tracking_record_id=record.id, original_filename="manual.pdf",
                                storage_path=str(manual_path), size_bytes=11, sha256="manual"))
    db_session.commit()
    service = DownstreamService(db_session)
    service.assign(admin, record.public_code, "AJ")
    provider = PodClient(completed_shipment())
    provider.failure = ProviderError("pod_download", "POD temporary error")
    service.run_due(provider, NOW)
    assert binding_for(db_session, record).sync_report["pod_files"]["state"] == "error"
    provider.failure = None
    service.run_due(provider, NOW + timedelta(minutes=5))
    old_file = db_session.scalar(select(WaybillPodFile).where(WaybillPodFile.provider_document_id == "41"))
    old_path = Path(old_file.storage_path)
    document = provider.result["vendors"][0]["pod_documents"][0]
    document.update({"id": 42, "version": 2, "file_name": "new-proof.pdf",
                     "download_url": f"{AJ_BASE_URL}/files/pod/42", "note": "Signature incomplete"})
    service.run_due(provider, NOW + timedelta(minutes=10))
    files = db_session.scalars(select(WaybillPodFile)).all()
    assert len(files) == 2 and manual_path.is_file()
    assert not old_path.exists()
    assert next(file for file in files if file.provider_document_id == "42").provider_note == "Signature incomplete"
    service.run_due(provider, NOW + timedelta(minutes=15))
    assert provider.downloads == ["41", "41", "42"]


def test_manually_deleted_synced_pod_stays_locked_until_unlocked(client, db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "upload_storage_dir", tmp_path)
    admin, _, record = create_waybill(db_session)
    service = DownstreamService(db_session)
    service.assign(admin, record.public_code, "AJ")
    provider = PodClient(completed_shipment())
    service.run_due(provider, NOW)
    file = db_session.scalars(select(WaybillPodFile)).one()
    login(client, email=admin.email)
    result = client.delete(f"/api/v1/waybills/{record.public_code}/pod/{file.id}")
    assert result.status_code == 200, result.text
    service.run_due(provider, NOW + timedelta(minutes=5))
    assert db_session.scalars(select(WaybillPodFile)).all() == []
    assert provider.downloads == ["41"]
    service.set_locks(admin, record.public_code, None, None, [])
    service.run_due(provider, NOW + timedelta(minutes=10))
    assert len(db_session.scalars(select(WaybillPodFile)).all()) == 1


def test_pod_files_are_cleaned_up_when_commit_fails(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "upload_storage_dir", tmp_path)
    admin, _, record = create_waybill(db_session)
    service = DownstreamService(db_session)
    service.assign(admin, record.public_code, "AJ")

    def fail_commit():
        raise RuntimeError("commit failed")

    monkeypatch.setattr(db_session, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="commit failed"):
        service.run_due(PodClient(completed_shipment()), NOW)
    assert list(tmp_path.rglob("*.pdf")) == []
    assert db_session.scalars(select(WaybillPodFile)).all() == []


def test_pod_unlock_after_preparation_preserves_old_file_until_downloaded(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "upload_storage_dir", tmp_path)
    admin, _, record = create_waybill(db_session)
    service = DownstreamService(db_session)
    service.assign(admin, record.public_code, "AJ")
    provider = PodClient(completed_shipment())
    service.run_due(provider, NOW)
    old_file = db_session.scalars(select(WaybillPodFile)).one()
    old_path = Path(old_file.storage_path)
    document = provider.result["vendors"][0]["pod_documents"][0]
    document.update({"id": 42, "version": 2, "download_url": f"{AJ_BASE_URL}/files/pod/42"})
    service.set_locks(admin, record.public_code, None, None, ["pod_files"])
    binding = binding_for(db_session, record)
    prepared = service._prepare_pods(binding, provider.result, provider)
    service.set_locks(admin, record.public_code, None, None, [])
    service.process(binding, NOW + timedelta(minutes=5), provider.result, prepared_pods=prepared)
    assert db_session.scalars(select(WaybillPodFile)).one().id == old_file.id
    assert old_path.is_file()
    assert binding.sync_report["pod_files"]["state"] == "error"
    service.run_due(provider, NOW + timedelta(minutes=10))
    assert db_session.scalars(select(WaybillPodFile)).one().provider_document_id == "42"
    assert not old_path.exists()


def test_aj_pod_download_authentication_and_origin_restriction(tmp_path):
    credentials = tmp_path / "aj.env"
    credentials.write_text("AJ_API_USERNAME=test\nAJ_API_PASSWORD=secret\n", encoding="utf-8")
    calls = []

    def handle(request):
        calls.append(request.url.path)
        assert request.headers["Authorization"].startswith("Basic ")
        assert request.url.path.endswith("/files/pod/41")
        return httpx.Response(200, content=b"%PDF proof")

    client = AJClient(credentials_path=credentials, transport=httpx.MockTransport(handle))
    assert client.download_pod("41", f"{AJ_BASE_URL}/files/pod/41") == b"%PDF proof"
    with pytest.raises(ProviderError):
        client.download_pod("41", "https://example.com/file")
    assert len(calls) == 1


def test_unassignment_during_pod_download_discards_late_file(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "upload_storage_dir", tmp_path)
    admin, _, record = create_waybill(db_session)
    service = DownstreamService(db_session)
    service.assign(admin, record.public_code, "AJ")

    class UnassigningClient(PodClient):
        def download_pod(self, document_id, download_url=None):
            service.assign(admin, record.public_code, None)
            return super().download_pod(document_id, download_url)

    service.run_due(UnassigningClient(completed_shipment()), NOW)
    assert binding_for(db_session, record) is None
    assert db_session.scalars(select(WaybillPodFile)).all() == []
    assert list(tmp_path.rglob("*.pdf")) == []


def test_orphan_pods_import_and_superseded_vendor_versions_are_skipped(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "upload_storage_dir", tmp_path)
    admin, _, record = create_waybill(db_session)
    service = DownstreamService(db_session)
    service.assign(admin, record.public_code, "AJ")
    result = completed_shipment()
    old = {**result["vendors"][0]["pod_documents"][0], "id": 40, "is_current": False}
    result["vendors"][0]["pod_documents"].append(old)
    result["orphan_pod_documents"] = [{**old, "id": 52, "file_name": "orphan.pdf", "download_url": f"{AJ_BASE_URL}/files/pod/52"}]
    provider = PodClient(result)
    service.run_due(provider, NOW)
    assert set(provider.downloads) == {"41", "52"}
    files = db_session.scalars(select(WaybillPodFile)).all()
    assert len(files) == 2
    assert next(file for file in files if file.provider_document_id == "52").provider_vendor_code is None
