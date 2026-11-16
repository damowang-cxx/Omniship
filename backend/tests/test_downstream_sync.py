from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import httpx
from sqlalchemy import select

from app.db.models import (
    DownstreamBinding, DownstreamIncident, DownstreamSyncEvent,
    SupplierVersion, WaybillTrackingRecord, WaybillUpload,
)
from app.repositories.waybill_repository import WaybillRepository
from app.schemas.waybill import WaybillUpdateRequest
from app.services.downstream_sync import AJClient, AJ_STATUS_MAP, DownstreamService, ProviderError
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
