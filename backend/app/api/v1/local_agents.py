import hashlib, hmac, ipaddress, json, secrets
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.rate_limit import OperationRateLimiter
from app.core.security import get_db, require_roles
from app.core.tenant import allowed_property_ids, organization_context
from app.models.device import Device
from app.models.discovery_intelligence import DiscoveryApprovalLink
from app.models.asset_intelligence import ManagedAsset
from app.models.hierarchy import Floor, Property
from app.models.discovery_intelligence import DiscoveryPolicy
from app.models.local_agent import AgentEnrollment, AgentJob, AgentMetricSample, AgentObservation, AgentPowerEvent, LocalAgentRegistration
from app.models.network_scan import NetworkScan
from app.models.user import User
from app.services.audit_service import create_audit_log
from app.services.billing_service import enforce_limit

admin_router=APIRouter(prefix="/local-agents",tags=["Local Agents"])
agent_router=APIRouter(prefix="/agent",tags=["Agent Protocol"])
manager=require_roles(["platformadmin","admin"]);reader=require_roles(["platformadmin","admin","technician","viewer"])
enrollment_limiter=OperationRateLimiter(limit=10,window_seconds=60);ingestion_limiter=OperationRateLimiter(limit=120,window_seconds=60);notice_limiter=OperationRateLimiter(limit=10,window_seconds=60)
ALLOWED_JOBS={"DISCOVERY","MONITORING","PING","DNS_LOOKUP","ARP_SNAPSHOT","AD_ENRICHMENT"}
ALLOWED_SOURCES={"discovery","monitoring","icmp","dns","arp","dhcp","active_directory","windows"}

def _digest(value:str)->str:return hashlib.sha256(value.encode()).hexdigest()

class EnrollmentCreate(BaseModel):
    name:str=Field(min_length=2,max_length=160);property_id:UUID;expires_minutes:int=Field(default=15,ge=5,le=60)
class EnrollRequest(BaseModel):
    enrollment_token:str=Field(min_length=32,max_length=512);hostname:str=Field(min_length=1,max_length=255);version:str=Field(min_length=1,max_length=50);api_version:int=Field(default=1,ge=1,le=1)
class HeartbeatRequest(BaseModel):
    version:str=Field(min_length=1,max_length=50);hostname:str=Field(min_length=1,max_length=255);uptime_seconds:int=Field(ge=0);pending_queue:int=Field(default=0,ge=0,le=1_000_000);queue_capacity:int=Field(default=10000,ge=1,le=1_000_000);last_successful_job:str|None=Field(default=None,max_length=80);cpu_percent:float|None=Field(default=None,ge=0,le=100);memory_total_bytes:int|None=Field(default=None,ge=0);memory_free_bytes:int|None=Field(default=None,ge=0);disk_free_bytes:int|None=Field(default=None,ge=0);ip_address:str|None=Field(default=None,max_length=64);operating_system:str|None=Field(default=None,max_length=255);logged_user:str|None=Field(default=None,max_length=255);last_update:datetime|None=None;fast_startup_enabled:bool|None=None;lid_close_action:str|None=Field(default=None,max_length=80);battery_health_percent:float|None=Field(default=None,ge=0,le=100);pending_windows_updates:int|None=Field(default=None,ge=0,le=10000);last_shutdown_at:datetime|None=None
class JobCreate(BaseModel):
    job_type:str;payload:dict=Field(default_factory=dict);timeout_seconds:int=Field(default=120,ge=5,le=3600)
class JobUpdate(BaseModel):
    status:Literal["started","completed","failed","timed_out","cancelled"];error:str|None=Field(default=None,max_length=1000)
class AdminNoticeCreate(BaseModel):
    agent_ids:list[UUID]=Field(min_length=1,max_length=10)
    message:str=Field(min_length=1,max_length=240)
    reason:str=Field(min_length=5,max_length=250)

    @field_validator("agent_ids")
    @classmethod
    def unique_agents(cls,value):
        if len(set(value))!=len(value):raise ValueError("Each target agent may appear only once")
        return value

    @field_validator("message","reason")
    @classmethod
    def trim_notice_text(cls,value):
        value=value.strip()
        if not value:raise ValueError("This field must contain non-space characters")
        if any(ord(character)<32 for character in value):raise ValueError("Control characters are not allowed")
        return value
class PowerEventWrite(BaseModel):
    event_id:UUID
    event_type:Literal["END_OF_DAY_NUDGE","END_OF_DAY_PROMPT","END_OF_DAY_STAY_ON","END_OF_DAY_SHUTDOWN_BLOCKED","END_OF_DAY_SHUTDOWN_REQUESTED","SMART_LOCK_REQUESTED","SMART_LOCK_APPLIED","SMART_LOCK_FAILED"]
    occurred_at:datetime
    reason:str|None=Field(default=None,max_length=250)

    @model_validator(mode="after")
    def validate_event(self):
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("Event time must include a timezone.")
        if self.occurred_at.astimezone(timezone.utc)>datetime.now(timezone.utc)+timedelta(minutes=5):
            raise ValueError("Event time cannot be more than five minutes in the future.")
        if self.event_type=="END_OF_DAY_STAY_ON" and (not self.reason or len(self.reason.strip())<5):
            raise ValueError("Staying on requires a reason of at least five characters.")
        if self.reason and any(ord(character)<32 for character in self.reason):
            raise ValueError("Control characters are not allowed in the reason.")
        if self.reason is not None:
            self.reason=self.reason.strip() or None
        return self
class ObservationWrite(BaseModel):
    observation_id:str=Field(min_length=8,max_length=80);source:str;observed_at:datetime;schema_version:int=Field(default=1,ge=1,le=1);payload:dict;organization_id:UUID|None=None;property_id:UUID|None=None

def _property(db,user,org,pid):
    if pid not in allowed_property_ids(db,user,org):raise HTTPException(403,"Property is outside your permitted scope")
    row=db.query(Property).filter(Property.id==pid,Property.organization_id==org,Property.is_active.is_(True)).first()
    if not row:raise HTTPException(404,"Property not found")
    return row

def _approved_networks(db:Session,property_id:UUID):
    networks=[]
    for row in db.query(DiscoveryPolicy.authorized_ranges).filter(DiscoveryPolicy.property_id==property_id,DiscoveryPolicy.enabled.is_(True)).all():
        try:values=json.loads(row[0])
        except (TypeError,json.JSONDecodeError):continue
        for value in values:
            try:networks.append(ipaddress.ip_network(value,strict=False))
            except ValueError:continue
    return networks

def _validate_network_job(db:Session,agent:LocalAgentRegistration,kind:str,payload:dict):
    if kind not in {"DISCOVERY","PING","MONITORING","DNS_LOOKUP"}:return
    approved=_approved_networks(db,agent.property_id)
    if not approved:raise HTTPException(422,"No approved property network policy is configured")
    try:
        if kind=="DISCOVERY":
            requested=ipaddress.ip_network(payload["cidr"],strict=False)
            allowed=any(requested.subnet_of(network) for network in approved if requested.version==network.version)
        else:
            target=ipaddress.ip_address(payload["target"])
            allowed=any(target in network for network in approved if target.version==network.version)
    except (KeyError,ValueError) as exc:raise HTTPException(422,"A valid approved network target is required") from exc
    if not allowed:raise HTTPException(403,"Agent job target is outside approved property networks")

def agent_view(row):
    now=datetime.now(timezone.utc)
    if row.revoked_at:effective="revoked"
    elif row.retired_at:effective="retired"
    elif not row.last_heartbeat:effective="pending"
    else:
        age=(now-row.last_heartbeat).total_seconds();effective="online" if age<=120 else "stale" if age<=600 else "offline"
    values = {key: getattr(row, key, None) for key in (
        "id", "agent_id", "organization_id", "property_id", "device_id", "managed_asset_id", "name",
        "version", "hostname", "last_seen", "last_heartbeat", "last_discovery",
        "last_monitoring", "uptime_seconds", "pending_queue", "queue_capacity",
        "registered_at",
    )}
    values.update({
        key: getattr(row, key, None) for key in (
            "cpu_percent", "memory_total_bytes", "memory_free_bytes", "disk_free_bytes",
            "ip_address", "operating_system", "logged_user", "last_update",
            "fast_startup_enabled", "lid_close_action", "battery_health_percent",
            "pending_windows_updates", "last_shutdown_at",
        )
    })
    return values | {"status": effective}

def authenticate_agent(authorization:str|None=Header(default=None),db:Session=Depends(get_db)):
    if not authorization or not authorization.startswith("Agent "):raise HTTPException(status.HTTP_401_UNAUTHORIZED,"Agent credential required")
    raw=authorization[6:].strip()
    if "." not in raw:raise HTTPException(status.HTTP_401_UNAUTHORIZED,"Invalid agent credential")
    public_id,secret=raw.split(".",1);row=db.query(LocalAgentRegistration).filter_by(agent_id=public_id).first()
    if not row or not row.credential_hash or not hmac.compare_digest(row.credential_hash,_digest(secret)):raise HTTPException(status.HTTP_401_UNAUTHORIZED,"Invalid agent credential")
    if row.revoked_at or row.retired_at:raise HTTPException(status.HTTP_401_UNAUTHORIZED,"Agent credential has been revoked")
    if row.credential_expires_at and row.credential_expires_at<=datetime.now(timezone.utc):raise HTTPException(status.HTTP_401_UNAUTHORIZED,"Agent credential has expired")
    return row

@admin_router.get("")
def list_agents(db:Session=Depends(get_db),user:User=Depends(reader),org=Depends(organization_context)):
    allowed=allowed_property_ids(db,user,org)
    rows=db.query(LocalAgentRegistration,Device,Floor,ManagedAsset).outerjoin(Device,LocalAgentRegistration.device_id==Device.id).outerjoin(Floor,Device.floor_id==Floor.id).outerjoin(ManagedAsset,LocalAgentRegistration.managed_asset_id==ManagedAsset.id).filter(LocalAgentRegistration.organization_id==org,LocalAgentRegistration.property_id.in_(allowed)).order_by(LocalAgentRegistration.name).all()
    return [
        agent_view(agent)|{
            "ip_address":agent.ip_address or (device.ip_address if device else None),
            "department":device.department if device else asset.department_name if asset else None,
            "location":device.location if device else asset.location_name if asset else None,
            "operating_system":agent.operating_system or (device.ad_operating_system if device else None),
            "floor":floor.display_name or floor.name if floor else None,
            "mac_address":device.mac_address if device else None,
            "managed_asset_name":asset.name if asset else None,
        }
        for agent,device,floor,asset in rows
    ]

@admin_router.get("/jobs/{job_id}")
def get_agent_job(job_id:UUID,db:Session=Depends(get_db),actor:User=Depends(manager),org=Depends(organization_context)):
    row=db.query(AgentJob).filter_by(id=job_id,organization_id=org).first()
    if not row or row.job_type!="ADMIN_NOTICE" or row.property_id not in allowed_property_ids(db,actor,org):raise HTTPException(404,"Agent job not found")
    return {"id":str(row.id),"job_type":row.job_type,"action":None,"status":row.status,"created_at":row.created_at,"started_at":row.started_at,"completed_at":row.completed_at,"error":row.error}

@admin_router.get("/{agent_id}/history")
def agent_history(agent_id:UUID,db:Session=Depends(get_db),actor:User=Depends(manager),org=Depends(organization_context)):
    agent=db.query(LocalAgentRegistration).filter_by(id=agent_id,organization_id=org).first()
    if not agent or agent.property_id not in allowed_property_ids(db,actor,org):raise HTTPException(404,"Agent not found")
    rows=db.query(AgentJob).filter_by(agent_id=agent.id,organization_id=org,job_type="ADMIN_NOTICE").order_by(AgentJob.created_at.desc()).limit(10).all()
    return [{"id":str(row.id),"job_type":row.job_type,"action":None,"status":row.status,"created_at":row.created_at,"started_at":row.started_at,"completed_at":row.completed_at,"error":row.error,"created_by":row.created_by} for row in rows]

@admin_router.get("/{agent_id}/metrics")
def agent_metrics(agent_id:UUID,db:Session=Depends(get_db),actor:User=Depends(manager),org=Depends(organization_context)):
    agent=db.query(LocalAgentRegistration).filter_by(id=agent_id,organization_id=org).first()
    if not agent or agent.property_id not in allowed_property_ids(db,actor,org):raise HTTPException(404,"Agent not found")
    cutoff=datetime.now(timezone.utc)-timedelta(days=7)
    rows=db.query(AgentMetricSample).filter_by(agent_id=agent.id,organization_id=org).filter(AgentMetricSample.recorded_at>=cutoff).order_by(AgentMetricSample.recorded_at.asc()).limit(2500).all()
    return [{"recorded_at":row.recorded_at,"uptime_seconds":row.uptime_seconds,"cpu_percent":row.cpu_percent,"memory_total_bytes":row.memory_total_bytes,"memory_free_bytes":row.memory_free_bytes,"disk_free_bytes":row.disk_free_bytes} for row in rows]

@admin_router.get("/installer/windows")
def download_windows_installer(request:Request, actor:User=Depends(manager), org=Depends(organization_context)):
    from io import BytesIO
    from pathlib import Path
    from zipfile import ZipFile, ZIP_STORED
    from fastapi.responses import Response
    bundle=Path(__file__).resolve().parents[2]/"distributions"/"hiop-agent-windows.zip"
    distribution=Path(__file__).resolve().parents[2]/"distributions"
    if not bundle.is_file():
        raise HTTPException(503,"The Windows agent download is not available. Contact your HIOP administrator.")
    output=BytesIO()
    with ZipFile(bundle,"r") as source, ZipFile(output,"w",ZIP_STORED) as archive:
        for entry in source.infolist():
            if entry.filename in {"setup.json","install-user.ps1","uninstall-user.ps1","Install HIOP Agent.cmd","Remove HIOP Agent.cmd","Connect HIOP.cmd"} or entry.filename.startswith("hiop_agent/"):
                continue
            archive.writestr(entry,source.read(entry.filename))
        for filename in ("install-user.ps1","uninstall-user.ps1","Install HIOP Agent.cmd","Remove HIOP Agent.cmd"):
            script=distribution/filename
            if not script.is_file():
                raise HTTPException(503,"The Windows agent setup files are incomplete.")
            archive.write(script,filename)
        archive.writestr("setup.json",json.dumps({"backend_url":str(request.base_url).rstrip("/")}))
    return Response(output.getvalue(),media_type="application/zip",headers={"Content-Disposition":'attachment; filename="HIOP-Agent-Windows.zip"',"Cache-Control":"no-store"})

@admin_router.post("/enrollments",status_code=201)
def create_enrollment(body:EnrollmentCreate,request:Request,db:Session=Depends(get_db),actor:User=Depends(manager),org=Depends(organization_context)):
    enrollment_limiter.check(f"enroll:{request.client.host if request.client else 'unknown'}:{actor.id}");_property(db,actor,org,body.property_id);enforce_limit(db,org,"agents")
    token=secrets.token_urlsafe(40);row=AgentEnrollment(organization_id=org,property_id=body.property_id,name=body.name.strip(),token_hash=_digest(token),expires_at=datetime.now(timezone.utc)+timedelta(minutes=body.expires_minutes),created_by=actor.id)
    db.add(row);db.flush();create_audit_log(db,actor.username,"AGENT_ENROLLMENT_CREATED","AgentEnrollment",str(row.id),f"Created one-time enrollment for property {body.property_id}");db.commit()
    return {"id":row.id,"enrollment_token":token,"expires_at":row.expires_at,"property_id":row.property_id,"name":row.name}

@admin_router.post("/notices",status_code=201)
def create_admin_notice(body:AdminNoticeCreate,request:Request,db:Session=Depends(get_db),actor:User=Depends(manager),org=Depends(organization_context)):
    notice_limiter.check(f"notice:{actor.id}")
    allowed=allowed_property_ids(db,actor,org)
    agents=db.query(LocalAgentRegistration).filter(
        LocalAgentRegistration.id.in_(body.agent_ids),
        LocalAgentRegistration.organization_id==org,
        LocalAgentRegistration.property_id.in_(allowed),
        LocalAgentRegistration.revoked_at.is_(None),
        LocalAgentRegistration.retired_at.is_(None),
    ).all()
    if len(agents)!=len(body.agent_ids):raise HTTPException(404,"One or more active agents were not found")
    now=datetime.now(timezone.utc)
    queued=[]
    for agent in agents:
        row=AgentJob(
            agent_id=agent.id,organization_id=agent.organization_id,property_id=agent.property_id,
            job_type="ADMIN_NOTICE",
            payload=json.dumps({"message":body.message,"reason":body.reason},separators=(",",":")),
            timeout_seconds=900,created_by=actor.id,
        )
        db.add(row);db.flush()
        create_audit_log(
            db,actor.username,"ADMIN_NOTICE_QUEUED","LocalAgent",str(agent.id),
            f"Notice queued for {agent.name} ({agent.agent_id}). Reason: {body.reason}. Message: {body.message}",
            organization_id=org,property_id=agent.property_id,
            source_ip=request.client.host if request.client else None,
        )
        queued.append({"id":str(row.id),"agent_id":str(agent.id),"status":"queued","expires_at":now+timedelta(minutes=15)})
    db.commit()
    return {"notices":queued}

@admin_router.post("/{agent_id}/revoke")
def revoke_agent(agent_id:UUID,db:Session=Depends(get_db),actor:User=Depends(manager),org=Depends(organization_context)):
    row=db.query(LocalAgentRegistration).filter_by(id=agent_id,organization_id=org).first()
    if not row or row.property_id not in allowed_property_ids(db,actor,org):raise HTTPException(404,"Agent not found")
    row.revoked_at=datetime.now(timezone.utc);row.status="revoked";row.credential_hash=None;create_audit_log(db,actor.username,"AGENT_REVOKED","LocalAgent",str(row.id),f"Revoked {row.agent_id}");db.commit();return agent_view(row)

@admin_router.post("/{agent_id}/jobs",status_code=201)
def create_job(agent_id:UUID,body:JobCreate,db:Session=Depends(get_db),actor:User=Depends(manager),org=Depends(organization_context)):
    kind=body.job_type.strip().upper()
    if kind not in ALLOWED_JOBS:raise HTTPException(422,"Unsupported agent job type")
    if kind == "AD_ENRICHMENT":raise HTTPException(409,"This agent version does not yet support Active Directory collection")
    agent=db.query(LocalAgentRegistration).filter_by(id=agent_id,organization_id=org).first()
    if not agent or agent.property_id not in allowed_property_ids(db,actor,org) or agent.revoked_at:raise HTTPException(404,"Active agent not found")
    _validate_network_job(db,agent,kind,body.payload)
    row=AgentJob(agent_id=agent.id,organization_id=agent.organization_id,property_id=agent.property_id,job_type=kind,payload=json.dumps(body.payload,separators=(",",":")),timeout_seconds=body.timeout_seconds,created_by=actor.id);db.add(row);db.flush();create_audit_log(db,actor.username,"AGENT_JOB_CREATED","LocalAgent",str(agent.id),f"Queued {kind} agent job {row.id}");db.commit();db.refresh(row);return {"id":row.id,"job_type":row.job_type,"status":row.status}

@agent_router.post("/enroll",status_code=201)
def enroll(body:EnrollRequest,request:Request,db:Session=Depends(get_db)):
    enrollment_limiter.check(f"machine-enroll:{request.client.host if request.client else 'unknown'}");now=datetime.now(timezone.utc)
    enrollment=db.query(AgentEnrollment).filter(AgentEnrollment.token_hash==_digest(body.enrollment_token),AgentEnrollment.used_at.is_(None),AgentEnrollment.revoked_at.is_(None),AgentEnrollment.expires_at>now).with_for_update().first()
    if not enrollment:raise HTTPException(401,"Enrollment credential is invalid, expired, or already used")
    hostname=body.hostname.strip()
    devices=db.query(Device).filter(
        Device.property_id==enrollment.property_id,
        func.lower(Device.hostname)==hostname.lower(),
    ).limit(2).all()
    device=devices[0] if len(devices)==1 else None
    assets=db.query(ManagedAsset).filter(
        ManagedAsset.organization_id==enrollment.organization_id,
        ManagedAsset.property_id==enrollment.property_id,
        func.lower(ManagedAsset.name)==hostname.lower(),
    ).limit(2).all()
    if device:
        linked_assets=db.query(ManagedAsset).filter(
                ManagedAsset.organization_id==enrollment.organization_id,
                ManagedAsset.property_id==enrollment.property_id,
                ManagedAsset.device_id==device.id,
            ).limit(2).all()
        assets_by_id={asset.id:asset for asset in (*assets,*linked_assets)}
        assets=list(assets_by_id.values())
    managed_asset=assets[0] if len(assets)==1 else None
    secret=secrets.token_urlsafe(48);public_id=f"HIOP-AGENT-{secrets.token_hex(8).upper()}"
    row=LocalAgentRegistration(agent_id=public_id,organization_id=enrollment.organization_id,property_id=enrollment.property_id,device_id=device.id if device else None,managed_asset_id=managed_asset.id if managed_asset else None,name=enrollment.name,status="online",version=body.version,hostname=hostname,credential_hash=_digest(secret),last_seen=now,last_heartbeat=now,registered_by=enrollment.created_by);enrollment.used_at=now;db.add(row)
    try:db.commit();db.refresh(row)
    except IntegrityError as exc:db.rollback();raise HTTPException(409,"An agent with this name is already registered") from exc
    return {"agent_id":row.agent_id,"credential":f"{row.agent_id}.{secret}","organization_id":row.organization_id,"property_id":row.property_id,"agent_api_version":1}

@agent_router.post("/heartbeat")
def heartbeat(body:HeartbeatRequest,db:Session=Depends(get_db),agent=Depends(authenticate_agent)):
    now=datetime.now(timezone.utc);agent.status="online";agent.last_seen=agent.last_heartbeat=now;agent.version=body.version;agent.hostname=body.hostname;agent.uptime_seconds=body.uptime_seconds;agent.pending_queue=body.pending_queue;agent.queue_capacity=body.queue_capacity
    for field in ("cpu_percent","memory_total_bytes","memory_free_bytes","disk_free_bytes","ip_address","operating_system","logged_user","last_update"):
        value=getattr(body,field)
        if value is not None:setattr(agent,field,value)
    for field in ("fast_startup_enabled","lid_close_action","battery_health_percent","pending_windows_updates","last_shutdown_at"):
        if field in body.model_fields_set:setattr(agent,field,getattr(body,field))
    last_sample=db.query(AgentMetricSample.recorded_at).filter_by(agent_id=agent.id).order_by(AgentMetricSample.recorded_at.desc()).first()
    if not last_sample or now-last_sample[0]>=timedelta(minutes=5):
        db.add(AgentMetricSample(agent_id=agent.id,organization_id=agent.organization_id,property_id=agent.property_id,uptime_seconds=body.uptime_seconds,cpu_percent=body.cpu_percent,memory_total_bytes=body.memory_total_bytes,memory_free_bytes=body.memory_free_bytes,disk_free_bytes=body.disk_free_bytes,recorded_at=now))
    db.commit();return {"status":"accepted","server_time":now,"agent_api_version":1,"smart_lock_timeout_seconds":300}

@agent_router.post("/power-events",status_code=202)
def report_power_event(body:PowerEventWrite,request:Request,db:Session=Depends(get_db),agent=Depends(authenticate_agent)):
    ingestion_limiter.check(f"power-event:{agent.agent_id}:{request.client.host if request.client else 'unknown'}")
    existing=db.query(AgentPowerEvent).filter_by(agent_id=agent.id,event_id=str(body.event_id)).first()
    if existing:return {"status":"duplicate"}
    row=AgentPowerEvent(
        agent_id=agent.id,organization_id=agent.organization_id,property_id=agent.property_id,
        event_id=str(body.event_id),event_type=body.event_type,reason=body.reason,occurred_at=body.occurred_at,
    )
    db.add(row)
    occurred=body.occurred_at.astimezone(timezone.utc).isoformat()
    description=f"{body.event_type.replace('_',' ').title()} at {occurred}."
    if body.reason:description+=f" Reason: {body.reason}"
    create_audit_log(
        db,f"Agent {agent.agent_id}",f"LOCAL_AGENT_{body.event_type}","LocalAgent",str(agent.id),description,
        organization_id=agent.organization_id,property_id=agent.property_id,
        source_ip=request.client.host if request.client else None,
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        duplicate=db.query(AgentPowerEvent).filter_by(agent_id=agent.id,event_id=str(body.event_id)).first()
        if duplicate:return {"status":"duplicate"}
        raise
    return {"status":"recorded"}

@agent_router.get("/jobs")
def jobs(db:Session=Depends(get_db),agent=Depends(authenticate_agent)):
    rows=db.query(AgentJob).filter_by(agent_id=agent.id,organization_id=agent.organization_id,property_id=agent.property_id,status="queued").filter(AgentJob.job_type.in_(ALLOWED_JOBS),AgentJob.available_at<=datetime.now(timezone.utc)).order_by(AgentJob.created_at).limit(20).all()
    return [{"id":x.id,"type":x.job_type,"payload":json.loads(x.payload),"timeout_seconds":x.timeout_seconds} for x in rows]

@agent_router.get("/notices")
def agent_notices(db:Session=Depends(get_db),agent=Depends(authenticate_agent)):
    now=datetime.now(timezone.utc)
    expiry=now-timedelta(minutes=15)
    expired=db.query(AgentJob).filter_by(
        agent_id=agent.id,organization_id=agent.organization_id,
        property_id=agent.property_id,job_type="ADMIN_NOTICE",status="queued",
    ).filter(AgentJob.created_at<expiry).limit(100).all()
    for row in expired:
        row.status="timed_out"
        row.completed_at=now
    if expired:
        db.commit()
    rows=db.query(AgentJob).filter_by(
        agent_id=agent.id,organization_id=agent.organization_id,
        property_id=agent.property_id,job_type="ADMIN_NOTICE",status="queued",
    ).filter(AgentJob.created_at>=expiry).order_by(AgentJob.created_at).limit(10).all()
    return [{"id":str(row.id),"message":json.loads(row.payload)["message"]} for row in rows]

@agent_router.post("/notices/{notice_id}/ack")
def acknowledge_agent_notice(notice_id:UUID,request:Request,db:Session=Depends(get_db),agent=Depends(authenticate_agent)):
    row=db.query(AgentJob).filter_by(
        id=notice_id,agent_id=agent.id,organization_id=agent.organization_id,
        property_id=agent.property_id,job_type="ADMIN_NOTICE",
    ).with_for_update().first()
    if not row:raise HTTPException(404,"Notice not found")
    if row.status=="completed":return {"status":"display_requested"}
    if row.status!="queued":raise HTTPException(409,"Notice is no longer available")
    now=datetime.now(timezone.utc)
    if row.created_at<now-timedelta(minutes=15):
        row.status="timed_out"
        row.completed_at=now
        db.commit()
        raise HTTPException(409,"Notice has expired")
    row.status="completed"
    row.started_at=now
    row.completed_at=now
    create_audit_log(
        db,f"Agent {agent.agent_id}","ADMIN_NOTICE_DISPLAY_REQUESTED","LocalAgent",str(agent.id),
        f"Tray requested display of notice {row.id}. {json.loads(row.payload).get('reason','')}",
        organization_id=agent.organization_id,property_id=agent.property_id,
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    return {"status":"display_requested"}

@agent_router.get("/jobs/{job_id}")
def job_state(job_id:UUID,db:Session=Depends(get_db),agent=Depends(authenticate_agent)):
    row=db.query(AgentJob).filter_by(id=job_id,agent_id=agent.id,organization_id=agent.organization_id,property_id=agent.property_id).first()
    if not row or row.job_type not in ALLOWED_JOBS:raise HTTPException(404,"Job not found")
    return {"status":row.status}

@agent_router.post("/jobs/{job_id}")
def update_job(job_id:UUID,body:JobUpdate,db:Session=Depends(get_db),agent=Depends(authenticate_agent)):
    row=db.query(AgentJob).filter_by(id=job_id,agent_id=agent.id,organization_id=agent.organization_id,property_id=agent.property_id).with_for_update().first()
    if not row or row.job_type not in ALLOWED_JOBS:raise HTTPException(404,"Job not found")
    from app.models.discovery_intelligence import DiscoveryJob
    linked=json.loads(row.payload).get("discovery_job_id")
    discovery=db.query(DiscoveryJob).filter_by(id=UUID(linked),property_id=agent.property_id).with_for_update().first() if linked else None
    if row.status in {"cancelled","cancelling"} and body.status!="cancelled":
        return {"status":row.status}
    if row.status in {"completed","failed","timed_out"}: return {"status":row.status}
    now=datetime.now(timezone.utc);row.status=body.status;row.error=body.error
    if discovery:
        discovery.status={"started":"running","completed":"completed","cancelled":"cancelled"}.get(body.status,"failed")
        discovery.current_stage={"started":"agent_discovery","completed":"completed"}.get(body.status,body.status)
        if body.status=="started": discovery.started_at=now
        else: discovery.completed_at=now
    if body.status=="started":row.started_at=now
    else:row.completed_at=now
    db.commit();return {"status":row.status}

@agent_router.post("/observations",status_code=202)
def ingest(body:ObservationWrite,request:Request,db:Session=Depends(get_db),agent=Depends(authenticate_agent)):
    ingestion_limiter.check(f"ingest:{agent.agent_id}:{request.client.host if request.client else 'unknown'}")
    if body.source not in ALLOWED_SOURCES:raise HTTPException(422,"Unsupported observation source")
    if body.organization_id and body.organization_id!=agent.organization_id:raise HTTPException(403,"Organization claim does not match agent identity")
    if body.property_id and body.property_id!=agent.property_id:raise HTTPException(403,"Property claim does not match agent identity")
    encoded=json.dumps(body.payload,separators=(",",":"))
    if len(encoded.encode())>1_000_000:raise HTTPException(413,"Observation payload exceeds 1 MB")
    existing=db.query(AgentObservation).filter_by(agent_id=agent.id,observation_id=body.observation_id).first()
    if existing:return {"status":"duplicate","id":existing.id}
    row=AgentObservation(observation_id=body.observation_id,agent_id=agent.id,organization_id=agent.organization_id,property_id=agent.property_id,source=body.source,schema_version=body.schema_version,observed_at=body.observed_at,payload=encoded);db.add(row);agent.last_seen=datetime.now(timezone.utc)
    if body.source=="discovery":
        agent.last_discovery=agent.last_seen
        ingest_discovery(db,agent,body.payload)
    if body.source in {"monitoring","icmp"}:
        agent.last_monitoring=agent.last_seen
        if body.source in {"monitoring","icmp"}:
            ingest_monitoring(db,agent,body.payload)
    db.commit();db.refresh(row);return {"status":"accepted","id":row.id}


def ingest_monitoring(db,agent,payload):
    from app.models.device import Device
    from app.models.network_scan import NetworkScan
    from app.services.alert_event_service import evaluate_scan
    from app.services.automation_event_outbox_service import process_outbox_batch
    config=payload.get("result",{})
    if not isinstance(config,dict):raise HTTPException(422,"Invalid monitoring result")
    job_id=payload.get("job_id")
    task=None
    if job_id:
        try: task=db.query(AgentJob).filter_by(id=UUID(str(job_id)),agent_id=agent.id,organization_id=agent.organization_id,property_id=agent.property_id).first()
        except ValueError: raise HTTPException(422,"Invalid monitoring job reference")
    job_payload=json.loads(task.payload) if task and task.payload else {}
    device_id=job_payload.get("device_id")
    device=None
    if device_id:
        try: device=db.query(Device).filter_by(id=UUID(str(device_id)),property_id=agent.property_id).first()
        except ValueError: device=None
    target=str(config.get("target") or job_payload.get("target") or "")
    if not device and target:
        device=db.query(Device).filter_by(ip_address=target,property_id=agent.property_id).first()
    if not device:return
    previous=device.network_status
    scan=NetworkScan(device_id=device.id,ip_address=device.ip_address,status="Online" if config.get("reachable") else "Offline",response_time=config.get("latency_ms"))
    db.add(scan);db.flush();device.network_status=scan.status;evaluate_scan(db,device,scan)
    if previous!=scan.status:
        from app.services.settings_service import read_network
        from app.services.automation_event_outbox_service import publish_internal_event
        runtime=read_network(db)
        publish_internal_event(db,event_type="device_offline" if scan.status=="Offline" else "device_restored",property_id=device.property_id,source_entity_type="device",source_entity_id=device.id,safe_payload={"automatic_ticket":runtime["automatic_offline_tickets"],"source":"local_agent"},severity="critical" if scan.status=="Offline" else "informational",status=scan.status.lower(),correlation_key=f"device:{device.id}:network")
        process_outbox_batch(db,25)


def ingest_discovery(db,agent,payload):
    from app.models.discovery_intelligence import DiscoveryJob, DiscoveryResult
    from app.services.discovery_intelligence_service import DiscoveryIntelligenceService
    from app.services.discovery_collectors import evidence
    try: job_id=UUID(str(payload.get("job_id")))
    except ValueError: raise HTTPException(422,"A discovery job reference is required")
    task=db.query(AgentJob).filter_by(id=job_id,agent_id=agent.id,organization_id=agent.organization_id,property_id=agent.property_id).with_for_update().first()
    if not task:raise HTTPException(403,"Observation does not belong to this agent's job")
    config=json.loads(task.payload)
    if not config.get("discovery_job_id"):return
    scan=db.query(DiscoveryJob).filter_by(id=UUID(config["discovery_job_id"]),property_id=agent.property_id).with_for_update().first()
    if not scan or scan.status in {"cancelled","cancelling","failed"}:return
    result=payload.get("result",{})
    if not isinstance(result,dict):raise HTTPException(422,"Invalid discovery result")
    network=ipaddress.ip_network(config["cidr"])
    devices=result.get("devices",[])
    if not isinstance(devices,list) or len(devices)>1024:raise HTTPException(422,"Invalid discovery result size")
    service=DiscoveryIntelligenceService(db)
    inventory_candidates=db.query(Device).filter(Device.property_id==agent.property_id).all()
    for item in devices:
        if not isinstance(item,dict):raise HTTPException(422,"Invalid discovered device")
        try: address=ipaddress.ip_address(item.get("target",""))
        except ValueError:raise HTTPException(422,"Invalid discovered address")
        if address not in network:raise HTTPException(422,"Discovered address is outside the requested network")
        if item.get("reachable"):
            mac=_agent_text(item,"mac_address",17)
            if mac and not _normalized_mac(mac):raise HTTPException(422,"Invalid discovered MAC address")
            hostname=_agent_text(item,"hostname",255)
            observation={"ip_address":str(address),"hostname":hostname,"hostnames":[hostname] if hostname else [],"dns_status":item.get("dns_status"),"mac_address":mac,"evidence":[evidence("ping_response",item.get("reachability_source") or "local_agent","reachable",verified=True)]}
            if mac:observation["evidence"].append(evidence("mac_address","local_agent",mac,verified=False))
            if hostname:observation["evidence"].append(evidence("hostname_match",item.get("hostname_source") or "local_agent",hostname,verified=item.get("hostname_source") in {"reverse_dns","netbios"}))
            root=service.ingest(scan,observation)
            root.confidence_reason="Local agent confirmed network reachability and hostname evidence." if item.get("hostname") else "Local agent confirmed network reachability. Hostname was unavailable."
            reconcile_agent_discovery(db,agent,root,str(address),item,inventory_candidates)
    computer=result.get("agent_computer")
    if computer is not None:
        if not isinstance(computer,dict):raise HTTPException(422,"Invalid local Windows inventory")
        adapters=computer.get("network_adapters",[])
        if not isinstance(adapters,list) or len(adapters)>64:raise HTTPException(422,"Invalid local Windows adapter inventory")
        for adapter in adapters:
            if not isinstance(adapter,dict):raise HTTPException(422,"Invalid local Windows adapter")
            try: address=ipaddress.ip_address(adapter.get("ip_address",""))
            except ValueError:raise HTTPException(422,"Invalid local Windows adapter address")
            if address.version!=network.version or address not in network:continue
            mac=_agent_text(adapter,"mac_address",17)
            if mac and not _normalized_mac(mac):raise HTTPException(422,"Invalid local Windows MAC address")
            hostname=_agent_text(computer,"hostname",255)
            observation={
                "ip_address":str(address),
                "hostname":hostname,
                "hostnames":[hostname] if hostname else [],
                "mac_address":mac,
                "mac_address_source":_agent_text(adapter,"mac_address_source",40),
                "vendor":_agent_text(computer,"manufacturer",160),
                "manufacturer":_agent_text(computer,"manufacturer",160),
                "model":_agent_text(computer,"model",180),
                "serial_number":_agent_text(computer,"serial_number",180),
                "operating_system":_agent_text(computer,"operating_system",180),
                "version":_agent_text(computer,"operating_system_version",180),
                "memory":computer.get("memory"),
                "cpu":_agent_text(computer,"processor",255),
                "nics":adapters,
                "device_type":"Windows Computer",
                "evidence":[evidence("windows_inventory","local_agent",agent.agent_id,verified=True)],
            }
            if mac:observation["evidence"].append(evidence("mac_address","local_agent",mac,verified=True))
            if observation["serial_number"]:observation["evidence"].append(evidence("serial_number","local_agent",observation["serial_number"],verified=True))
            if hostname:observation["evidence"].append(evidence("hostname_match","local_agent",hostname,verified=True))
            if observation["operating_system"]:observation["evidence"].append(evidence("operating_system","local_agent",observation["operating_system"],verified=True))
            root=service.ingest(scan,observation)
            reconcile_agent_discovery(db,agent,root,str(address),observation,inventory_candidates)
    try: scanned=int(result.get("scanned",0))
    except (ValueError,TypeError):raise HTTPException(422,"Invalid discovery progress")
    scan.hosts_completed=max(scan.hosts_completed or 0,min(max(0,scanned),scan.hosts_total or 1024))


def _normalized_mac(value):
    normalized="".join(character for character in str(value or "").casefold() if character.isalnum())
    return normalized if len(normalized)==12 and all(character in "0123456789abcdef" for character in normalized) else None


def _normalized_identity_text(value):
    return str(value or "").strip().rstrip(".").casefold().split(".",1)[0]


def _agent_text(payload,key,maximum):
    value=payload.get(key)
    if value is None:return None
    if not isinstance(value,str):raise HTTPException(422,f"Invalid agent inventory field: {key}")
    value=value.strip()
    if len(value)>maximum:raise HTTPException(422,f"Agent inventory field exceeds the supported length: {key}")
    return value or None


def _select_inventory_match(agent,result,candidates,*,mac_is_trusted=True):
    """Return only a unique same-property identity match; IP alone is not identity."""
    scoped=[device for device in candidates if device.property_id==agent.property_id]
    serial=str(result.serial_number or "").strip().casefold()
    mac=_normalized_mac(result.mac_address) if mac_is_trusted else None
    hostname=_normalized_identity_text(result.primary_hostname or result.fqdn)
    matches=[]
    if serial:
        matches.append([device for device in scoped if str(device.serial_number or "").strip().casefold()==serial])
    if mac:
        matches.append([device for device in scoped if _normalized_mac(device.mac_address)==mac])
    if any(len(rows)>1 for rows in matches):
        return None,None
    matched=[rows[0] for rows in matches if len(rows)==1]
    if matched:
        if len({device.id for device in matched})!=1:
            return None,None
        device=matched[0]
        if serial and device.serial_number and str(device.serial_number).strip().casefold()!=serial:
            return None,None
        if mac and device.mac_address and _normalized_mac(device.mac_address)!=mac:
            return None,None
        return device,"strong"
    if not hostname:
        return None,None
    hostname_matches=[device for device in scoped if _normalized_identity_text(device.hostname)==hostname]
    if len(hostname_matches)!=1:
        return None,None
    device=hostname_matches[0]
    if result.serial_number and device.serial_number and str(result.serial_number).strip().casefold()!=str(device.serial_number).strip().casefold():
        return None,None
    if mac_is_trusted and result.mac_address and device.mac_address and _normalized_mac(result.mac_address)!=_normalized_mac(device.mac_address):
        return None,None
    return device,"hostname"


def reconcile_agent_discovery(db,agent,result,observed_ip,item,candidates):
    if result.property_id!=agent.property_id:
        return None
    trusted_mac=item.get("mac_address_source")=="local_adapter"
    device,match_strength=_select_inventory_match(agent,result,candidates,mac_is_trusted=trusted_mac)
    if not device:
        return None
    if result.serial_number:
        serial_owner=db.query(Device.id).filter(
            func.lower(Device.serial_number)==str(result.serial_number).strip().casefold(),
        ).first()
        if serial_owner and serial_owner[0]!=device.id:
            return None
    if trusted_mac and result.mac_address:
        normalized_mac=_normalized_mac(result.mac_address)
        mac_owner=db.query(Device.id).filter(
            func.replace(func.replace(func.replace(func.lower(Device.mac_address),":",""),"-",""),".","")==normalized_mac,
        ).first()
        if mac_owner and mac_owner[0]!=device.id:
            return None

    link=db.get(DiscoveryApprovalLink,result.id)
    if link and link.device_id!=device.id:
        return None
    if item.get("device_type")=="Windows Computer" and trusted_mac:
        if agent.device_id and agent.device_id!=device.id:
            return None
        agent.device_id=device.id
    if not link:
        db.add(DiscoveryApprovalLink(result_id=result.id,device_id=device.id))
    from app.services.device_identity_service import DeviceIdentityService
    DeviceIdentityService(db).apply(result,agent.organization_id,actor=f"Agent {agent.agent_id}")

    def is_unknown(value):
        return not value or str(value).strip().casefold() in {"unknown","unknown device","n/a","not available"}

    if is_unknown(device.device_type) and not is_unknown(result.device_type):
        device.device_type=result.device_type
    if is_unknown(device.brand) and not is_unknown(result.vendor):
        device.brand=result.vendor
    if is_unknown(device.model) and not is_unknown(result.model):
        device.model=result.model
    if result.serial_number and not device.serial_number:
        serial_owner=db.query(Device.id).filter(
            func.lower(Device.serial_number)==str(result.serial_number).strip().casefold(),
            Device.id!=device.id,
        ).first()
        if not serial_owner:
            device.serial_number=result.serial_number
    if trusted_mac and result.mac_address and not device.mac_address:
        normalized_mac=_normalized_mac(result.mac_address)
        mac_owner=db.query(Device.id).filter(
            func.replace(func.replace(func.replace(func.lower(Device.mac_address),":",""),"-",""),".","")==normalized_mac,
            Device.id!=device.id,
        ).first()
        if not mac_owner:
            device.mac_address=result.mac_address
    if not device.ad_operating_system and result.operating_system:
        device.ad_operating_system=result.operating_system
    if not device.ad_operating_system_version and result.configuration_snapshot:
        try:
            snapshot=json.loads(result.configuration_snapshot)
        except (TypeError,json.JSONDecodeError):
            snapshot={}
        version=snapshot.get("version")
        if isinstance(version,str) and version.strip():
            device.ad_operating_system_version=version.strip()
    if not device.description and result.description:
        device.description=result.description
        device.description_source=result.description_source or "Discovery"

    if match_strength=="strong":
        occupied_ip=db.query(Device.id).filter(
            Device.property_id==agent.property_id,
            Device.ip_address==observed_ip,
            Device.id!=device.id,
        ).first()
        if not occupied_ip:
            device.ip_address=observed_ip

    previous_status=device.network_status
    device.network_status="Online"
    scan_record=NetworkScan(
        device_id=device.id,
        ip_address=observed_ip,
        status="Online",
        response_time=item.get("latency_ms"),
    )
    db.add(scan_record)
    db.flush()
    from app.services.alert_event_service import evaluate_scan
    evaluate_scan(db,device,scan_record)
    if previous_status!="Online":
        from app.services.automation_event_outbox_service import process_outbox_batch, publish_internal_event
        from app.services.settings_service import read_network
        runtime=read_network(db)
        publish_internal_event(
            db,
            event_type="device_restored",
            property_id=device.property_id,
            source_entity_type="device",
            source_entity_id=device.id,
            safe_payload={"automatic_ticket":runtime["automatic_offline_tickets"],"source":"local_agent"},
            severity="informational",
            status="online",
            correlation_key=f"device:{device.id}:network",
        )
        process_outbox_batch(db,25)
    return device
