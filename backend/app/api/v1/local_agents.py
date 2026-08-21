import hashlib, hmac, ipaddress, json, secrets
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.rate_limit import OperationRateLimiter
from app.core.security import get_db, require_roles
from app.core.tenant import allowed_property_ids, organization_context
from app.models.hierarchy import Property
from app.models.discovery_intelligence import DiscoveryPolicy
from app.models.local_agent import AgentEnrollment, AgentJob, AgentObservation, LocalAgentRegistration
from app.models.user import User
from app.services.audit_service import create_audit_log
from app.services.billing_service import enforce_limit

admin_router=APIRouter(prefix="/local-agents",tags=["Local Agents"])
agent_router=APIRouter(prefix="/agent",tags=["Agent Protocol"])
manager=require_roles(["platformadmin","admin"]);reader=require_roles(["platformadmin","admin","technician","viewer"])
enrollment_limiter=OperationRateLimiter(limit=10,window_seconds=60);ingestion_limiter=OperationRateLimiter(limit=120,window_seconds=60)
ALLOWED_JOBS={"DISCOVERY","MONITORING","PING","DNS_LOOKUP","ARP_SNAPSHOT","SNMP_POLL","AD_ENRICHMENT"}
ALLOWED_SOURCES={"discovery","monitoring","icmp","dns","arp","dhcp","snmp","active_directory","windows"}

def _digest(value:str)->str:return hashlib.sha256(value.encode()).hexdigest()

class EnrollmentCreate(BaseModel):
    name:str=Field(min_length=2,max_length=160);property_id:UUID;expires_minutes:int=Field(default=15,ge=5,le=60)
class EnrollRequest(BaseModel):
    enrollment_token:str=Field(min_length=32,max_length=512);hostname:str=Field(min_length=1,max_length=255);version:str=Field(min_length=1,max_length=50);api_version:int=Field(default=1,ge=1,le=1)
class HeartbeatRequest(BaseModel):
    version:str=Field(min_length=1,max_length=50);hostname:str=Field(min_length=1,max_length=255);uptime_seconds:int=Field(ge=0);pending_queue:int=Field(default=0,ge=0,le=1_000_000);queue_capacity:int=Field(default=10000,ge=1,le=1_000_000);last_successful_job:str|None=Field(default=None,max_length=80)
class JobCreate(BaseModel):
    job_type:str;payload:dict=Field(default_factory=dict);timeout_seconds:int=Field(default=120,ge=5,le=3600)
class JobUpdate(BaseModel):
    status:Literal["started","completed","failed","timed_out"];error:str|None=Field(default=None,max_length=1000)
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
    return {key:getattr(row,key) for key in ("id","agent_id","organization_id","property_id","name","version","hostname","last_seen","last_heartbeat","last_discovery","last_monitoring","uptime_seconds","pending_queue","queue_capacity","registered_at")}|{"status":effective}

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
    return [agent_view(x) for x in db.query(LocalAgentRegistration).filter(LocalAgentRegistration.organization_id==org,LocalAgentRegistration.property_id.in_(allowed)).order_by(LocalAgentRegistration.name).all()]

@admin_router.post("/enrollments",status_code=201)
def create_enrollment(body:EnrollmentCreate,request:Request,db:Session=Depends(get_db),actor:User=Depends(manager),org=Depends(organization_context)):
    enrollment_limiter.check(f"enroll:{request.client.host if request.client else 'unknown'}:{actor.id}");_property(db,actor,org,body.property_id);enforce_limit(db,org,"agents")
    token=secrets.token_urlsafe(40);row=AgentEnrollment(organization_id=org,property_id=body.property_id,name=body.name.strip(),token_hash=_digest(token),expires_at=datetime.now(timezone.utc)+timedelta(minutes=body.expires_minutes),created_by=actor.id)
    db.add(row);db.flush();create_audit_log(db,actor.username,"AGENT_ENROLLMENT_CREATED","AgentEnrollment",str(row.id),f"Created one-time enrollment for property {body.property_id}");db.commit()
    return {"id":row.id,"enrollment_token":token,"expires_at":row.expires_at,"property_id":row.property_id,"name":row.name}

@admin_router.post("/{agent_id}/revoke")
def revoke_agent(agent_id:UUID,db:Session=Depends(get_db),actor:User=Depends(manager),org=Depends(organization_context)):
    row=db.query(LocalAgentRegistration).filter_by(id=agent_id,organization_id=org).first()
    if not row or row.property_id not in allowed_property_ids(db,actor,org):raise HTTPException(404,"Agent not found")
    row.revoked_at=datetime.now(timezone.utc);row.status="revoked";row.credential_hash=None;create_audit_log(db,actor.username,"AGENT_REVOKED","LocalAgent",str(row.id),f"Revoked {row.agent_id}");db.commit();return agent_view(row)

@admin_router.post("/{agent_id}/jobs",status_code=201)
def create_job(agent_id:UUID,body:JobCreate,db:Session=Depends(get_db),actor:User=Depends(manager),org=Depends(organization_context)):
    kind=body.job_type.strip().upper()
    if kind not in ALLOWED_JOBS:raise HTTPException(422,"Unsupported agent job type")
    agent=db.query(LocalAgentRegistration).filter_by(id=agent_id,organization_id=org).first()
    if not agent or agent.property_id not in allowed_property_ids(db,actor,org) or agent.revoked_at:raise HTTPException(404,"Active agent not found")
    _validate_network_job(db,agent,kind,body.payload)
    row=AgentJob(agent_id=agent.id,organization_id=agent.organization_id,property_id=agent.property_id,job_type=kind,payload=json.dumps(body.payload,separators=(",",":")),timeout_seconds=body.timeout_seconds,created_by=actor.id);db.add(row);db.commit();db.refresh(row);return {"id":row.id,"job_type":row.job_type,"status":row.status}

@agent_router.post("/enroll",status_code=201)
def enroll(body:EnrollRequest,request:Request,db:Session=Depends(get_db)):
    enrollment_limiter.check(f"machine-enroll:{request.client.host if request.client else 'unknown'}");now=datetime.now(timezone.utc)
    enrollment=db.query(AgentEnrollment).filter(AgentEnrollment.token_hash==_digest(body.enrollment_token),AgentEnrollment.used_at.is_(None),AgentEnrollment.revoked_at.is_(None),AgentEnrollment.expires_at>now).with_for_update().first()
    if not enrollment:raise HTTPException(401,"Enrollment credential is invalid, expired, or already used")
    secret=secrets.token_urlsafe(48);public_id=f"HIOP-AGENT-{secrets.token_hex(8).upper()}"
    row=LocalAgentRegistration(agent_id=public_id,organization_id=enrollment.organization_id,property_id=enrollment.property_id,name=enrollment.name,status="online",version=body.version,hostname=body.hostname,credential_hash=_digest(secret),last_seen=now,last_heartbeat=now,registered_by=enrollment.created_by);enrollment.used_at=now;db.add(row)
    try:db.commit();db.refresh(row)
    except IntegrityError as exc:db.rollback();raise HTTPException(409,"An agent with this name is already registered") from exc
    return {"agent_id":row.agent_id,"credential":f"{row.agent_id}.{secret}","organization_id":row.organization_id,"property_id":row.property_id,"agent_api_version":1}

@agent_router.post("/heartbeat")
def heartbeat(body:HeartbeatRequest,db:Session=Depends(get_db),agent=Depends(authenticate_agent)):
    now=datetime.now(timezone.utc);agent.status="online";agent.last_seen=agent.last_heartbeat=now;agent.version=body.version;agent.hostname=body.hostname;agent.uptime_seconds=body.uptime_seconds;agent.pending_queue=body.pending_queue;agent.queue_capacity=body.queue_capacity;db.commit();return {"status":"accepted","server_time":now,"agent_api_version":1}

@agent_router.get("/jobs")
def jobs(db:Session=Depends(get_db),agent=Depends(authenticate_agent)):
    rows=db.query(AgentJob).filter_by(agent_id=agent.id,organization_id=agent.organization_id,property_id=agent.property_id,status="queued").filter(AgentJob.available_at<=datetime.now(timezone.utc)).order_by(AgentJob.created_at).limit(20).all()
    return [{"id":x.id,"type":x.job_type,"payload":json.loads(x.payload),"timeout_seconds":x.timeout_seconds} for x in rows]

@agent_router.post("/jobs/{job_id}")
def update_job(job_id:UUID,body:JobUpdate,db:Session=Depends(get_db),agent=Depends(authenticate_agent)):
    row=db.query(AgentJob).filter_by(id=job_id,agent_id=agent.id,organization_id=agent.organization_id,property_id=agent.property_id).first()
    if not row:raise HTTPException(404,"Job not found")
    now=datetime.now(timezone.utc);row.status=body.status;row.error=body.error
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
    if body.source=="discovery":agent.last_discovery=agent.last_seen
    if body.source in {"monitoring","icmp","snmp"}:agent.last_monitoring=agent.last_seen
    db.commit();db.refresh(row);return {"status":"accepted","id":row.id}
