from datetime import datetime, timedelta, timezone
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock
from zipfile import ZipFile
import pytest
from fastapi import HTTPException
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.v1.local_agents import ALLOWED_JOBS, ObservationWrite, _validate_network_job, agent_router, agent_view, authenticate_agent, download_windows_installer, ingest
from app.core.security import get_db

def agent(**values):
    base=dict(id="row",agent_id="HIOP-AGENT-TEST",organization_id="11111111-1111-1111-1111-111111111111",property_id="22222222-2222-2222-2222-222222222222",name="Test",version="1.0.0",hostname="host",last_seen=None,last_heartbeat=None,last_discovery=None,last_monitoring=None,uptime_seconds=0,pending_queue=0,queue_capacity=10000,registered_at=datetime.now(timezone.utc),revoked_at=None,retired_at=None)
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

def test_agent_download_includes_update_and_confirmed_removal_tools():
    response=download_windows_installer(SimpleNamespace(base_url="https://hiop.example/"),SimpleNamespace(),None)
    with ZipFile(BytesIO(response.body)) as archive:
        names=set(archive.namelist())
        assert {"setup.json","install-user.ps1","uninstall-user.ps1","Remove HIOP Agent.cmd"} <= names
        setup=archive.read("setup.json").decode()
        installer=archive.read("install-user.ps1").decode()
        uninstaller=archive.read("uninstall-user.ps1").decode()
    assert "https://hiop.example" in setup
    assert "Updating the existing HIOP agent without changing its enrollment." in installer
    assert "Type REMOVE to continue" in uninstaller
