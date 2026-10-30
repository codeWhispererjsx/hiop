from datetime import datetime, timedelta, timezone
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID
from zipfile import ZipFile
import pytest
from fastapi import HTTPException
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.v1.local_agents import ALLOWED_JOBS, AdminNoticeCreate, JobCreate, ObservationWrite, _select_inventory_match, _validate_network_job, acknowledge_agent_notice, agent_notices, agent_router, agent_view, authenticate_agent, create_admin_notice, create_job, download_windows_installer, ingest, reconcile_agent_discovery
from app.core.security import get_db

def agent(**values):
    base=dict(id="row",agent_id="HIOP-AGENT-TEST",organization_id="11111111-1111-1111-1111-111111111111",property_id="22222222-2222-2222-2222-222222222222",device_id=None,name="Test",version="1.0.0",hostname="host",last_seen=None,last_heartbeat=None,last_discovery=None,last_monitoring=None,uptime_seconds=0,pending_queue=0,queue_capacity=10000,registered_at=datetime.now(timezone.utc),revoked_at=None,retired_at=None)
    base.update(values);return SimpleNamespace(**base)
def test_job_protocol_has_no_arbitrary_command():
    assert "EXECUTE_COMMAND" not in ALLOWED_JOBS

def test_endpoint_control_jobs_are_not_accepted():
    with pytest.raises(HTTPException) as exc:
        create_job(
            "agent-id",JobCreate(job_type="DEVICE_ACTION",payload={"action":"SHUTDOWN"}),
            MagicMock(),SimpleNamespace(id="user-id"),"11111111-1111-1111-1111-111111111111",
        )
    assert exc.value.status_code==422

def test_admin_notice_is_bounded_and_requires_unique_targets():
    with pytest.raises(ValueError):
        AdminNoticeCreate(agent_ids=["22222222-2222-2222-2222-222222222222"]*2,message="Notice",reason="Scheduled maintenance")
    with pytest.raises(ValueError):
        AdminNoticeCreate(agent_ids=["22222222-2222-2222-2222-222222222222"],message="x"*241,reason="Scheduled maintenance")
    with pytest.raises(ValueError):
        AdminNoticeCreate(agent_ids=["22222222-2222-2222-2222-222222222222"],message="Line one\nLine two",reason="Scheduled maintenance")

def test_admin_notice_is_targeted_scoped_and_audited(monkeypatch):
    target=agent(id="33333333-3333-3333-3333-333333333333",name="Front desk",agent_id="HIOP-AGENT-01")
    monkeypatch.setattr("app.api.v1.local_agents.allowed_property_ids",lambda *_args:{"22222222-2222-2222-2222-222222222222"})
    audit=MagicMock()
    monkeypatch.setattr("app.api.v1.local_agents.create_audit_log",audit)
    db=MagicMock()
    db.query.return_value.filter.return_value.all.return_value=[target]
    request=SimpleNamespace(client=SimpleNamespace(host="192.0.2.10"))
    response=create_admin_notice(
        AdminNoticeCreate(agent_ids=[UUID("33333333-3333-3333-3333-333333333333")],message="Maintenance starts soon.",reason="Scheduled network maintenance"),
        request,db,SimpleNamespace(id="user-id",username="admin"),UUID("11111111-1111-1111-1111-111111111111"),
    )
    queued=next(call.args[0] for call in db.add.call_args_list if getattr(call.args[0],"job_type",None)=="ADMIN_NOTICE")
    assert queued.agent_id=="33333333-3333-3333-3333-333333333333"
    assert queued.timeout_seconds==900
    assert '"message":"Maintenance starts soon."' in queued.payload
    assert '"reason":"Scheduled network maintenance"' in queued.payload
    assert response["notices"][0]["status"]=="queued"
    assert audit.call_args.kwargs["source_ip"]=="192.0.2.10"

def test_agent_notice_delivery_expires_old_notices_and_acknowledges_delivery(monkeypatch):
    now=datetime.now(timezone.utc)
    expired=SimpleNamespace(status="queued",created_at=now-timedelta(minutes=20),completed_at=None)
    pending=SimpleNamespace(
        id="notice-id",status="queued",created_at=now,payload='{"message":"Save your work","reason":"Maintenance"}',
        started_at=None,completed_at=None,
    )
    expired_query=MagicMock()
    expired_query.filter_by.return_value.filter.return_value.limit.return_value.all.return_value=[expired]
    pending_query=MagicMock()
    pending_query.filter_by.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value=[pending]
    db=MagicMock()
    db.query.side_effect=[expired_query,pending_query]
    notices=agent_notices(db,agent())
    assert notices==[{"id":"notice-id","message":"Save your work"}]
    assert expired.status=="timed_out"
    db.commit.assert_called_once()

    audit=MagicMock()
    monkeypatch.setattr("app.api.v1.local_agents.create_audit_log",audit)
    ack_query=MagicMock()
    ack_query.filter_by.return_value.with_for_update.return_value.first.return_value=pending
    db.query.side_effect=None
    db.query.return_value=ack_query
    result=acknowledge_agent_notice(
        UUID("44444444-4444-4444-4444-444444444444"),
        SimpleNamespace(client=SimpleNamespace(host="192.0.2.11")),db,agent(),
    )
    assert result=={"status":"display_requested"}
    assert audit.call_args.args[2]=="ADMIN_NOTICE_DISPLAY_REQUESTED"
    assert pending.status=="completed"
    assert pending.started_at is not None
    assert pending.completed_at is not None
    db.commit.assert_called()
def test_agent_status_uses_heartbeat_freshness():
    now=datetime.now(timezone.utc)
    assert agent_view(agent(last_heartbeat=now))["status"]=="online"
    assert agent_view(agent(last_heartbeat=now-timedelta(minutes=5)))["status"]=="stale"
    assert agent_view(agent(last_heartbeat=now-timedelta(minutes=20)))["status"]=="offline"
    assert agent_view(agent(last_heartbeat=now,revoked_at=now))["status"]=="revoked"

def test_missing_machine_credential_fails_closed():
    with pytest.raises(HTTPException) as exc:authenticate_agent(None,MagicMock())
    assert exc.value.status_code==401
def test_agent_cannot_claim_another_property():
    body=ObservationWrite(observation_id="observation-123",source="icmp",observed_at=datetime.now(timezone.utc),payload={},property_id="33333333-3333-3333-3333-333333333333")
    request=SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
    with pytest.raises(HTTPException) as exc:ingest(body,request,MagicMock(),agent())
    assert exc.value.status_code==403
def test_agent_api_never_returns_credential_hash():
    assert "credential_hash" not in agent_view(agent())

def test_real_http_rejects_property_tampering():
    app=FastAPI();app.include_router(agent_router);app.dependency_overrides[authenticate_agent]=lambda:agent();app.dependency_overrides[get_db]=lambda:MagicMock()
    response=TestClient(app).post("/agent/observations",json={"observation_id":"http-observation-1","source":"icmp","observed_at":datetime.now(timezone.utc).isoformat(),"schema_version":1,"payload":{},"property_id":"33333333-3333-3333-3333-333333333333"})
    assert response.status_code==403

def test_real_http_rejects_missing_agent_credential():
    app=FastAPI();app.include_router(agent_router);app.dependency_overrides[get_db]=lambda:MagicMock()
    assert TestClient(app).post("/agent/heartbeat",json={"version":"1.0.0","hostname":"test","uptime_seconds":1}).status_code==401

def test_network_jobs_fail_closed_without_property_policy():
    query=MagicMock();query.filter.return_value.all.return_value=[];db=MagicMock();db.query.return_value=query
    with pytest.raises(HTTPException) as exc:_validate_network_job(db,agent(),"DISCOVERY",{"cidr":"10.50.0.0/24"})
    assert exc.value.status_code==422

def test_agent_discovery_matches_unique_hostname_only_within_its_property():
    property_id="22222222-2222-2222-2222-222222222222"
    agent_row=SimpleNamespace(property_id=property_id)
    result=SimpleNamespace(serial_number=None,mac_address=None,primary_hostname="frontdesk.example.test",fqdn=None)
    same_property=SimpleNamespace(id="device-1",property_id=property_id,hostname="FrontDesk.example.test",serial_number=None,mac_address=None)
    other_property=SimpleNamespace(id="device-2",property_id="33333333-3333-3333-3333-333333333333",hostname="frontdesk.example.test",serial_number=None,mac_address=None)
    device,basis=_select_inventory_match(agent_row,result,[same_property,other_property])
    assert device is same_property
    assert basis=="hostname"

def test_agent_discovery_does_not_match_by_ip_or_ambiguous_hostname():
    property_id="22222222-2222-2222-2222-222222222222"
    agent_row=SimpleNamespace(property_id=property_id)
    result=SimpleNamespace(serial_number=None,mac_address=None,primary_hostname="frontdesk",fqdn=None)
    first=SimpleNamespace(id="device-1",property_id=property_id,hostname="frontdesk",serial_number=None,mac_address=None,ip_address="10.0.0.1")
    second=SimpleNamespace(id="device-2",property_id=property_id,hostname="frontdesk",serial_number=None,mac_address=None,ip_address="10.0.0.2")
    assert _select_inventory_match(agent_row,result,[first,second])==(None,None)
    assert _select_inventory_match(agent_row,SimpleNamespace(serial_number=None,mac_address=None,primary_hostname=None,fqdn=None),[first])==(None,None)

def test_agent_discovery_refuses_conflicting_strong_identity_matches():
    property_id="22222222-2222-2222-2222-222222222222"
    agent_row=SimpleNamespace(property_id=property_id)
    result=SimpleNamespace(serial_number="SERIAL-1",mac_address="00:11:22:33:44:55",primary_hostname="host-a",fqdn=None)
    by_serial=SimpleNamespace(id="device-1",property_id=property_id,hostname="host-a",serial_number="SERIAL-1",mac_address=None)
    by_mac=SimpleNamespace(id="device-2",property_id=property_id,hostname="host-b",serial_number=None,mac_address="00-11-22-33-44-55")
    assert _select_inventory_match(agent_row,result,[by_serial,by_mac])==(None,None)

def test_agent_arp_mac_is_not_treated_as_verified_inventory_identity():
    property_id="22222222-2222-2222-2222-222222222222"
    agent_row=SimpleNamespace(property_id=property_id)
    result=SimpleNamespace(serial_number=None,mac_address="00:11:22:33:44:55",primary_hostname="frontdesk",fqdn=None)
    device=SimpleNamespace(id="device-1",property_id=property_id,hostname="frontdesk",serial_number=None,mac_address="aa:bb:cc:dd:ee:ff")
    assert _select_inventory_match(agent_row,result,[device],mac_is_trusted=False)==(device,"hostname")

def test_agent_discovery_reconciliation_links_match_and_records_network_history(monkeypatch):
    monkeypatch.setattr("app.services.device_identity_service.DeviceIdentityService.apply",lambda *_args,**_kwargs:None)
    monkeypatch.setattr("app.services.alert_event_service.evaluate_scan",lambda *_args,**_kwargs:None)
    property_id="22222222-2222-2222-2222-222222222222"
    device=SimpleNamespace(
        id="device-1",property_id=property_id,hostname="FrontDesk",serial_number=None,
        mac_address=None,device_type="Unknown Device",brand="Unknown",model="Unknown",
        description=None,description_source=None,ip_address="10.0.0.8",network_status="Online",
        ad_operating_system=None,ad_operating_system_version=None,
    )
    result=SimpleNamespace(
        id="result-1",property_id=property_id,serial_number=None,mac_address=None,
        primary_hostname="frontdesk",fqdn=None,device_type="Unknown Device",
        vendor=None,model=None,description=None,description_source=None,
        operating_system=None,configuration_snapshot="{}",
    )
    db=MagicMock()
    db.get.return_value=None
    db.query.return_value.filter.return_value.all.return_value=[device]
    matched=reconcile_agent_discovery(db,agent(property_id=property_id),result,"10.0.0.9",{"latency_ms":12,"mac_address_source":"arp"},[device])
    assert matched is device
    assert device.ip_address=="10.0.0.8"
    assert device.network_status=="Online"
    assert db.add.call_count==2
    added=[call.args[0] for call in db.add.call_args_list]
    assert any(getattr(row,"result_id",None)=="result-1" and getattr(row,"device_id",None)=="device-1" for row in added)
    network_history=next(row for row in added if hasattr(row,"response_time"))
    assert network_history.ip_address=="10.0.0.9"
    assert network_history.response_time==12

def test_local_windows_inventory_enriches_only_missing_managed_device_fields(monkeypatch):
    monkeypatch.setattr("app.services.device_identity_service.DeviceIdentityService.apply",lambda *_args,**_kwargs:None)
    monkeypatch.setattr("app.services.alert_event_service.evaluate_scan",lambda *_args,**_kwargs:None)
    property_id="22222222-2222-2222-2222-222222222222"
    device=SimpleNamespace(
        id="device-1",property_id=property_id,hostname="FrontDesk",serial_number=None,
        mac_address=None,device_type="Unknown Device",brand="Unknown",model="Unknown",
        description=None,description_source=None,ip_address="10.0.0.8",network_status="Online",
        ad_operating_system=None,ad_operating_system_version=None,department="IT",location="Front Desk",
    )
    result=SimpleNamespace(
        id="result-1",property_id=property_id,serial_number="SERIAL-42",
        mac_address="00:11:22:33:44:55",primary_hostname="frontdesk",fqdn=None,
        device_type="Windows Computer",vendor="Dell",model="Latitude 5540",
        description=None,description_source=None,operating_system="Windows 11 Enterprise",
        configuration_snapshot='{"version":"10.0.26100"}',
    )
    db=MagicMock()
    db.get.return_value=None
    db.query.return_value.filter.return_value.first.return_value=None
    matched=reconcile_agent_discovery(
        db,agent(property_id=property_id),result,"10.0.0.9",
        {"device_type":"Windows Computer","mac_address_source":"local_adapter"},[device],
    )
    assert matched is device
    assert device.serial_number=="SERIAL-42"
    assert device.mac_address=="00:11:22:33:44:55"
    assert device.brand=="Dell"
    assert device.model=="Latitude 5540"
    assert device.ad_operating_system=="Windows 11 Enterprise"
    assert device.ad_operating_system_version=="10.0.26100"
    assert device.department=="IT"
    assert device.location=="Front Desk"

def test_windows_agent_is_bound_to_the_unique_matched_managed_device(monkeypatch):
    monkeypatch.setattr("app.services.device_identity_service.DeviceIdentityService.apply",lambda *_args,**_kwargs:None)
    monkeypatch.setattr("app.services.alert_event_service.evaluate_scan",lambda *_args,**_kwargs:None)
    property_id="22222222-2222-2222-2222-222222222222"
    device=SimpleNamespace(
        id="device-1",property_id=property_id,hostname="FrontDesk",serial_number="SERIAL-42",
        mac_address="00:11:22:33:44:55",device_type="Windows Computer",brand="Dell",
        model="Latitude 5540",description=None,description_source=None,ip_address="10.0.0.8",
        network_status="Online",ad_operating_system="Windows 11",ad_operating_system_version=None,
    )
    result=SimpleNamespace(
        id="result-1",property_id=property_id,serial_number="SERIAL-42",
        mac_address="00:11:22:33:44:55",primary_hostname="frontdesk",fqdn=None,
        device_type="Windows Computer",vendor="Dell",model="Latitude 5540",
        description=None,description_source=None,operating_system="Windows 11",
        configuration_snapshot="{}",
    )
    registration=agent(property_id=property_id)
    db=MagicMock()
    db.get.return_value=None
    db.query.return_value.filter.return_value.first.return_value=None
    matched=reconcile_agent_discovery(
        db,registration,result,"10.0.0.9",
        {"device_type":"Windows Computer","mac_address_source":"local_adapter"},[device],
    )
    assert matched is device
    assert registration.device_id=="device-1"

def test_agent_download_includes_update_and_confirmed_removal_tools():
    response=download_windows_installer(SimpleNamespace(base_url="https://hiop.example/"),SimpleNamespace(),None)
    with ZipFile(BytesIO(response.body)) as archive:
        names=set(archive.namelist())
        assert {"setup.json","install-user.ps1","uninstall-user.ps1","Install HIOP Agent.cmd","Remove HIOP Agent.cmd","service/Hiop.Agent.Service.exe","tray/Hiop.Agent.Tray.exe"} <= names
        assert not any(name.startswith("hiop_agent/") for name in names)
        setup=archive.read("setup.json").decode()
        installer=archive.read("install-user.ps1").decode()
        uninstaller=archive.read("uninstall-user.ps1").decode()
    assert "https://hiop.example" in setup
    assert "Updating the existing HIOP agent without changing its enrollment." in installer
    assert "sc.exe create" in installer
    assert "NT AUTHORITY\\LocalService" in installer
    assert "HIOPAgentCommandBroker" in installer
    assert "sc.exe delete" in installer
    assert "HIOP Agent Command Broker" not in installer
    assert "Python 3.12" not in installer
    assert "Type REMOVE to continue" in uninstaller
