from datetime import datetime, timedelta, timezone
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock
from zipfile import ZipFile
import pytest
from fastapi import HTTPException
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.v1.local_agents import ALLOWED_JOBS, DeviceActionCreate, ObservationWrite, _select_inventory_match, _validate_network_job, agent_router, agent_view, authenticate_agent, create_asset_action, create_device_action, download_windows_installer, ingest, reconcile_agent_discovery
from app.core.security import get_db

def agent(**values):
    base=dict(id="row",agent_id="HIOP-AGENT-TEST",organization_id="11111111-1111-1111-1111-111111111111",property_id="22222222-2222-2222-2222-222222222222",device_id=None,name="Test",version="1.0.0",hostname="host",last_seen=None,last_heartbeat=None,last_discovery=None,last_monitoring=None,uptime_seconds=0,pending_queue=0,queue_capacity=10000,registered_at=datetime.now(timezone.utc),revoked_at=None,retired_at=None)
    base.update(values);return SimpleNamespace(**base)
def test_job_protocol_has_no_arbitrary_command():
    assert "EXECUTE_COMMAND" not in ALLOWED_JOBS
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

def test_device_action_requires_confirmation_and_queues_only_allowlisted_operation():
    property_id="22222222-2222-2222-2222-222222222222"
    device=SimpleNamespace(
        id="device-1",property_id=property_id,inventory_status="Active",
        ad_operating_system="Microsoft Windows 11 Enterprise",
    )
    registration=agent(
        id="agent-row",organization_id="11111111-1111-1111-1111-111111111111",
        property_id=property_id,device_id="device-1",last_heartbeat=datetime.now(timezone.utc),
        revoked_at=None,retired_at=None,
    )
    device_query=MagicMock()
    device_query.filter_by.return_value.join.return_value.filter.return_value.with_for_update.return_value.first.return_value=device
    agent_query=MagicMock()
    agent_query.filter_by.return_value.all.return_value=[registration]
    user_query=MagicMock()
    user_query.filter.return_value.first.return_value=None
    db=MagicMock()
    db.query.side_effect=[device_query,agent_query,user_query]
    response=create_device_action(
        "device-1",DeviceActionCreate(action="LOCK",confirm=True),db,
        SimpleNamespace(username="admin",id="user-1"),"11111111-1111-1111-1111-111111111111",
    )
    queued=next(call.args[0] for call in db.add.call_args_list if getattr(call.args[0],"job_type",None)=="DEVICE_ACTION")
    assert response["status"]=="queued"
    assert queued.agent_id=="agent-row"
    assert queued.payload=='{"action":"LOCK"}'
    with pytest.raises(HTTPException) as exc:
        create_device_action(
            "device-1",DeviceActionCreate(action="RESTART",confirm=False),MagicMock(),
            SimpleNamespace(username="admin",id="user-1"),"11111111-1111-1111-1111-111111111111",
        )
    assert exc.value.status_code==422

def test_asset_action_queues_for_one_online_windows_agent(monkeypatch):
    property_id="22222222-2222-2222-2222-222222222222"
    monkeypatch.setattr("app.api.v1.local_agents.allowed_property_ids",lambda *_args:{property_id})
    monkeypatch.setattr("app.api.v1.local_agents.create_audit_log",lambda *_args,**_kwargs:None)
    asset=SimpleNamespace(
        id="asset-1",property_id=property_id,status="active",
        device_type="Desktop",name="FO-DT-01",
    )
    registration=agent(
        id="agent-row",organization_id="11111111-1111-1111-1111-111111111111",
        property_id=property_id,managed_asset_id="asset-1",
        operating_system="Windows 11",last_heartbeat=datetime.now(timezone.utc),
        revoked_at=None,retired_at=None,
    )
    asset_query=MagicMock()
    asset_query.filter_by.return_value.with_for_update.return_value.first.return_value=asset
    agent_query=MagicMock()
    agent_query.filter_by.return_value.all.return_value=[registration]
    db=MagicMock()
    db.query.side_effect=[asset_query,agent_query]

    response=create_asset_action(
        "asset-1",DeviceActionCreate(action="LOCK",confirm=True),db,
        SimpleNamespace(username="admin",id="user-1"),
        "11111111-1111-1111-1111-111111111111",
    )

    queued=next(call.args[0] for call in db.add.call_args_list if getattr(call.args[0],"job_type",None)=="DEVICE_ACTION")
    assert response["status"]=="queued"
    assert queued.agent_id=="agent-row"
    assert queued.payload=='{"action":"LOCK"}'

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
    assert "Python 3.12" not in installer
    assert "Type REMOVE to continue" in uninstaller
