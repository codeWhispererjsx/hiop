import csv, hashlib, io, json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from openpyxl import Workbook
from pydantic import BaseModel, Field
from sqlalchemy import and_, desc, func, or_
from sqlalchemy.orm import Session

from app.core.security import get_db, require_roles
from app.models.analytics import SLAMeasurement
from app.models.asset_management import Contract, EnterpriseAsset, Vendor
from app.models.business_intelligence import KPI, KPIValue
from app.models.change_management import ChangeRequest
from app.models.hierarchy import Organization, Property
from app.models.incidents import OperationalIncident
from app.models.multi_property import (AdministrativeScope, BusinessUnit, ConfigurationPolicy, CorporateAdministrator, Country, DelegatedAdministrator, ExecutiveOperationsCache, GlobalNotification, GlobalSetting, InheritedSetting, Policy, PolicyAssignment, PolicyCompliance, PolicyException, PolicyVersion, PropertyCluster, PropertyGroup, PropertyHierarchyMembership, PropertySetting, Region, RegionalAdministrator, RegionalSetting, PropertyAdministrator)
from app.services.audit_service import create_audit_log
from app.services.multi_property_service import SCOPE_TYPES, active_scopes, allowed_property_ids, effective_permissions, property_ids_for_scope, require_property, require_scope

router=APIRouter(prefix="/enterprise",tags=["Multi-Property Operations & Corporate Management"])
reader=require_roles(["admin","superadmin","technician","viewer"]); manager=require_roles(["admin","superadmin"])
AUDIENCES=("ceo","cio","regional_director","corporate_it","regional_it","property_it","engineering")

class UnitWrite(BaseModel): organization_id:UUID; parent_id:UUID|None=None; name:str; code:str=Field(pattern=r"^[A-Z0-9_-]{2,40}$"); unit_type:str="business_unit"
class RegionWrite(BaseModel): organization_id:UUID; business_unit_id:UUID|None=None; name:str; code:str=Field(pattern=r"^[A-Z0-9_-]{2,40}$"); timezone:str="UTC"
class CountryWrite(BaseModel): region_id:UUID; name:str; iso_code:str=Field(min_length=2,max_length=3)
class GroupWrite(BaseModel): country_id:UUID; parent_id:UUID|None=None; name:str; code:str=Field(pattern=r"^[A-Z0-9_-]{2,40}$")
class ClusterWrite(BaseModel): property_group_id:UUID; name:str; code:str=Field(pattern=r"^[A-Z0-9_-]{2,40}$")
class MembershipWrite(BaseModel): property_id:UUID; property_group_id:UUID; property_cluster_id:UUID|None=None
class ScopeWrite(BaseModel): user_id:str; scope_type:str=Field(pattern="^("+"|".join(sorted(SCOPE_TYPES))+")$"); scope_id:UUID|None=None; permission_set:list[str]=Field(default_factory=list,max_length=200); overrides:dict[str,bool]=Field(default_factory=dict); inherited:bool=True; starts_at:datetime|None=None; expires_at:datetime|None=None; administrator_type:str=Field("delegated",pattern=r"^(corporate|regional|property|delegated)$"); reason:str|None=None; approval_reference:str|None=None
class SettingWrite(BaseModel): scope_type:str=Field(pattern=r"^(global|region|property)$"); scope_id:UUID; key:str=Field(pattern=r"^[a-z][a-z0-9_.-]{2,159}$"); value:str; enforced:bool=False
class PolicyWrite(BaseModel): organization_id:UUID; code:str=Field(pattern=r"^[A-Z0-9_-]{2,50}$"); title:str; category:str=Field(pattern=r"^(security|change|asset|documentation|compliance|operations)$"); content:str
class AssignmentWrite(BaseModel): scope_type:str=Field(pattern=r"^(organization|region|country|property_group|property_cluster|property)$"); scope_id:UUID; mandatory:bool=True
class ComplianceWrite(BaseModel): property_id:UUID; status:str=Field(pattern=r"^(compliant|non_compliant|not_applicable|not_assessed)$"); evidence:dict=Field(default_factory=dict)
class ExceptionWrite(BaseModel): property_id:UUID; reason:str; expires_at:datetime
class NotificationWrite(BaseModel): organization_id:UUID; scope_type:str=Field(pattern=r"^(organization|region|property)$"); scope_id:UUID|None=None; notification_type:str=Field(pattern=r"^(corporate|broadcast|maintenance|emergency|escalation)$"); severity:str=Field(pattern=r"^(info|warning|critical)$"); title:str; message:str; escalation_chain:list[str]=Field(default_factory=list); publish_at:datetime|None=None; expires_at:datetime|None=None

def page(q,p,s): return {"items":q.offset((p-1)*s).limit(s).all(),"total":q.count(),"page":p,"page_size":s}
def row(db,model,id,label):
    item=db.get(model,id)
    if not item: raise HTTPException(404,f"{label} not found")
    return item
def commit(db,user,action,entity,item,message): db.flush();create_audit_log(db,user.username,action,entity,str(item.id),message);db.commit();db.refresh(item);return item
def scoped_ids(db,user): return allowed_property_ids(db,user)
def ensure_property(db,user,property_id):
    try:return require_property(db,user,property_id)
    except PermissionError as exc:raise HTTPException(403,str(exc)) from exc
def ensure_scope(db,user,scope_type,scope_id):
    try:require_scope(db,user,scope_type,scope_id)
    except PermissionError as exc:raise HTTPException(403,str(exc)) from exc
def structure_ids(db,ids):
    memberships=db.query(PropertyHierarchyMembership).filter(PropertyHierarchyMembership.property_id.in_(ids)).all();group_ids={x.property_group_id for x in memberships};cluster_ids={x.property_cluster_id for x in memberships if x.property_cluster_id};country_ids={r[0] for r in db.query(PropertyGroup.country_id).filter(PropertyGroup.id.in_(group_ids))};region_ids={r[0] for r in db.query(Country.region_id).filter(Country.id.in_(country_ids))};organization_ids={r[0] for r in db.query(Property.organization_id).filter(Property.id.in_(ids),Property.organization_id.isnot(None))};return {"memberships":memberships,"groups":group_ids,"clusters":cluster_ids,"countries":country_ids,"regions":region_ids,"organizations":organization_ids}

@router.get("/organizations")
def organizations(page_number:int=Query(1,alias="page",ge=1),page_size:int=Query(50,ge=1,le=100),db:Session=Depends(get_db),user=Depends(reader)):
    ids=scoped_ids(db,user);org_ids=structure_ids(db,ids)["organizations"];q=db.query(Organization).filter(Organization.id.in_(org_ids)) if user.role!="superadmin" else db.query(Organization);return page(q.order_by(Organization.name),page_number,page_size)
@router.get("/hierarchy")
def hierarchy(organization_id:UUID|None=None,db:Session=Depends(get_db),user=Depends(reader)):
    if user.role=="superadmin":
        orgs=db.query(Organization);orgs=orgs.filter_by(id=organization_id) if organization_id else orgs;org_rows=orgs.all();org_ids={x.id for x in org_rows};return {"organizations":org_rows,"business_units":db.query(BusinessUnit).filter(BusinessUnit.organization_id.in_(org_ids)).all(),"regions":db.query(Region).filter(Region.organization_id.in_(org_ids)).all(),"countries":db.query(Country).all(),"property_groups":db.query(PropertyGroup).all(),"property_clusters":db.query(PropertyCluster).all(),"memberships":db.query(PropertyHierarchyMembership).all(),"properties":db.query(Property).filter(Property.organization_id.in_(org_ids)).all()}
    allowed=scoped_ids(db,user);struct=structure_ids(db,allowed);properties=db.query(Property).filter(Property.id.in_(allowed));properties=properties.filter_by(organization_id=organization_id) if organization_id else properties;org_ids=struct["organizations"]&({organization_id} if organization_id else struct["organizations"])
    return {"organizations":db.query(Organization).filter(Organization.id.in_(org_ids)).all(),"business_units":db.query(BusinessUnit).filter(BusinessUnit.organization_id.in_(org_ids)).all(),"regions":db.query(Region).filter(Region.id.in_(struct["regions"]),Region.organization_id.in_(org_ids)).all(),"countries":db.query(Country).filter(Country.id.in_(struct["countries"])).all(),"property_groups":db.query(PropertyGroup).filter(PropertyGroup.id.in_(struct["groups"])).all(),"property_clusters":db.query(PropertyCluster).filter(PropertyCluster.id.in_(struct["clusters"])).all(),"memberships":struct["memberships"],"properties":properties.all()}
@router.post("/business-units",status_code=201)
def create_unit(body:UnitWrite,db:Session=Depends(get_db),user=Depends(manager)):
    ensure_scope(db,user,"organization",body.organization_id)
    depth=0;path="/"
    if body.parent_id:
        parent=row(db,BusinessUnit,body.parent_id,"Parent business unit");depth=parent.depth+1;path=f"{parent.path}{parent.id}/"
    item=BusinessUnit(**body.model_dump(),depth=depth,path=path);db.add(item);return commit(db,user,"CREATE","business_unit",item,"Created enterprise business unit")
@router.post("/regions",status_code=201)
def create_region(body:RegionWrite,db:Session=Depends(get_db),user=Depends(manager)):ensure_scope(db,user,"organization",body.organization_id);item=Region(**body.model_dump());db.add(item);return commit(db,user,"CREATE","region",item,"Created enterprise region")
@router.get("/regions")
def regions(organization_id:UUID|None=None,page_number:int=Query(1,alias="page",ge=1),page_size:int=Query(50,ge=1,le=100),db:Session=Depends(get_db),user=Depends(reader)):struct=structure_ids(db,scoped_ids(db,user));q=db.query(Region) if user.role=="superadmin" else db.query(Region).filter(Region.id.in_(struct["regions"]));q=q.filter_by(organization_id=organization_id) if organization_id else q;return page(q.order_by(Region.name),page_number,page_size)
@router.post("/countries",status_code=201)
def create_country(body:CountryWrite,db:Session=Depends(get_db),user=Depends(manager)):ensure_scope(db,user,"region",body.region_id);item=Country(**body.model_dump());db.add(item);return commit(db,user,"CREATE","country",item,"Created enterprise country")
@router.post("/property-groups",status_code=201)
def create_group(body:GroupWrite,db:Session=Depends(get_db),user=Depends(manager)):ensure_scope(db,user,"country",body.country_id);item=PropertyGroup(**body.model_dump());db.add(item);return commit(db,user,"CREATE","property_group",item,"Created property group")
@router.get("/property-groups")
def groups(page_number:int=Query(1,alias="page",ge=1),page_size:int=Query(50,ge=1,le=100),db:Session=Depends(get_db),user=Depends(reader)):struct=structure_ids(db,scoped_ids(db,user));q=db.query(PropertyGroup) if user.role=="superadmin" else db.query(PropertyGroup).filter(PropertyGroup.id.in_(struct["groups"]));return page(q.order_by(PropertyGroup.name),page_number,page_size)
@router.post("/property-clusters",status_code=201)
def create_cluster(body:ClusterWrite,db:Session=Depends(get_db),user=Depends(manager)):ensure_scope(db,user,"property_group",body.property_group_id);item=PropertyCluster(**body.model_dump());db.add(item);return commit(db,user,"CREATE","property_cluster",item,"Created property cluster")
@router.put("/property-memberships/{property_id}")
def set_membership(property_id:UUID,body:MembershipWrite,db:Session=Depends(get_db),user=Depends(manager)):
    if property_id!=body.property_id:raise HTTPException(422,"Property path and payload must match")
    ensure_property(db,user,property_id);ensure_scope(db,user,"property_group",body.property_group_id)
    item=db.query(PropertyHierarchyMembership).filter_by(property_id=property_id).first() or PropertyHierarchyMembership(property_id=property_id,property_group_id=body.property_group_id);db.add(item);item.property_group_id=body.property_group_id;item.property_cluster_id=body.property_cluster_id;return commit(db,user,"ASSIGN","property_hierarchy",item,"Assigned property to corporate hierarchy")

@router.get("/administration/scopes")
def scopes(user_id:str|None=None,db:Session=Depends(get_db),user=Depends(manager)):
    q=db.query(AdministrativeScope);q=q.filter_by(user_id=user_id) if user_id else q;visible=[]
    for item in q.order_by(desc(AdministrativeScope.created_at)).limit(500):
        try:require_scope(db,user,item.scope_type,item.scope_id);visible.append(item)
        except PermissionError:continue
    return {"items":visible}
@router.post("/administration/scopes",status_code=201)
def create_scope(body:ScopeWrite,db:Session=Depends(get_db),user=Depends(manager)):
    if body.scope_id:ensure_scope(db,user,body.scope_type,body.scope_id)
    if body.expires_at and body.expires_at<=datetime.now(timezone.utc):raise HTTPException(422,"Administrative assignment must expire in the future")
    data=body.model_dump(exclude={"administrator_type","reason","approval_reference"});data["permission_set"]=json.dumps(data["permission_set"],sort_keys=True);data["overrides"]=json.dumps(data["overrides"],sort_keys=True);data["starts_at"]=data["starts_at"] or datetime.now(timezone.utc);item=AdministrativeScope(**data,delegated_by=str(user.id));db.add(item);db.flush()
    if body.administrator_type=="corporate":db.add(CorporateAdministrator(scope_id=item.id))
    elif body.administrator_type=="regional":db.add(RegionalAdministrator(scope_id=item.id,region_id=body.scope_id))
    elif body.administrator_type=="property":db.add(PropertyAdministrator(scope_id=item.id,property_id=body.scope_id))
    else:db.add(DelegatedAdministrator(scope_id=item.id,reason=body.reason or "Approved delegation",approval_reference=body.approval_reference or "manual-approval"))
    return commit(db,user,"GRANT","administrative_scope",item,"Granted scoped administrative authority")
@router.get("/administration/effective-permissions")
def permissions(property_id:UUID|None=None,db:Session=Depends(get_db),user=Depends(reader)):
    if property_id:ensure_property(db,user,property_id)
    return {"user_id":str(user.id),"property_id":property_id,"permissions":effective_permissions(db,user,property_id),"property_ids":sorted(map(str,scoped_ids(db,user)))}

@router.put("/settings")
def setting(body:SettingWrite,db:Session=Depends(get_db),user=Depends(manager)):
    ensure_scope(db,user,{"global":"organization","region":"region","property":"property"}[body.scope_type],body.scope_id)
    models={"global":(GlobalSetting,"organization_id"),"region":(RegionalSetting,"region_id"),"property":(PropertySetting,"property_id")};model,key=models[body.scope_type];item=db.query(model).filter(getattr(model,key)==body.scope_id,model.key==body.key).first() or model(**{key:body.scope_id,"key":body.key,"value":body.value,"updated_by":str(user.id)});db.add(item);item.value=body.value;item.updated_by=str(user.id)
    if body.scope_type=="global":item.enforced=body.enforced
    return commit(db,user,"UPDATE","enterprise_setting",item,"Updated inherited enterprise setting")
@router.get("/settings/effective/{property_id}")
def effective_settings(property_id:UUID,db:Session=Depends(get_db),user=Depends(reader)):
    ensure_property(db,user,property_id);prop=row(db,Property,property_id,"Property");membership=db.query(PropertyHierarchyMembership).filter_by(property_id=property_id).first();region_id=None
    if membership:region_id=db.query(Country.region_id).join(PropertyGroup,PropertyGroup.country_id==Country.id).filter(PropertyGroup.id==membership.property_group_id).scalar()
    global_rows=db.query(GlobalSetting).filter_by(organization_id=prop.organization_id).all();regional_rows=db.query(RegionalSetting).filter_by(region_id=region_id).all() if region_id else [];property_rows=db.query(PropertySetting).filter_by(property_id=property_id).all();values={r.key:{"value":r.value,"source":"global","enforced":r.enforced} for r in global_rows};values.update({r.key:{"value":r.value,"source":"region","enforced":False} for r in regional_rows if not values.get(r.key,{}).get("enforced")});values.update({r.key:{"value":r.value,"source":"property","enforced":False} for r in property_rows if not values.get(r.key,{}).get("enforced")});return {"property_id":property_id,"settings":values}

@router.get("/policies")
def policies(status:str|None=None,page_number:int=Query(1,alias="page",ge=1),page_size:int=Query(50,ge=1,le=100),db:Session=Depends(get_db),user=Depends(reader)):org_ids=structure_ids(db,scoped_ids(db,user))["organizations"];q=db.query(Policy) if user.role=="superadmin" else db.query(Policy).filter(Policy.organization_id.in_(org_ids));q=q.filter_by(status=status) if status else q;return page(q.order_by(desc(Policy.updated_at)),page_number,page_size)
@router.post("/policies",status_code=201)
def create_policy(body:PolicyWrite,db:Session=Depends(get_db),user=Depends(manager)):ensure_scope(db,user,"organization",body.organization_id);data=body.model_dump(exclude={"content"});item=Policy(**data,owner_id=str(user.id));db.add(item);db.flush();db.add(PolicyVersion(policy_id=item.id,version=1,content=body.content));return commit(db,user,"CREATE","corporate_policy",item,"Created versioned corporate policy")
@router.post("/policies/{policy_id}/publish")
def publish(policy_id:UUID,db:Session=Depends(get_db),user=Depends(manager)):item=row(db,Policy,policy_id,"Policy");ensure_scope(db,user,"organization",item.organization_id);version=db.query(PolicyVersion).filter_by(policy_id=policy_id,version=item.current_version).first();version.status="published";version.approved_by=str(user.id);version.approved_at=datetime.now(timezone.utc);item.status="published";return commit(db,user,"PUBLISH","corporate_policy",item,"Published reviewed corporate policy")
@router.post("/policies/{policy_id}/assignments",status_code=201)
def assign_policy(policy_id:UUID,body:AssignmentWrite,db:Session=Depends(get_db),user=Depends(manager)):policy=row(db,Policy,policy_id,"Policy");ensure_scope(db,user,"organization",policy.organization_id);ensure_scope(db,user,body.scope_type,body.scope_id);item=PolicyAssignment(policy_id=policy_id,**body.model_dump(),assigned_by=str(user.id));db.add(item);return commit(db,user,"ASSIGN","policy_assignment",item,"Assigned policy to hierarchy scope")
@router.post("/policy-assignments/{assignment_id}/compliance")
def assess(assignment_id:UUID,body:ComplianceWrite,db:Session=Depends(get_db),user=Depends(reader)):
    ensure_property(db,user,body.property_id);row(db,PolicyAssignment,assignment_id,"Policy assignment");item=db.query(PolicyCompliance).filter_by(assignment_id=assignment_id,property_id=body.property_id).first() or PolicyCompliance(assignment_id=assignment_id,property_id=body.property_id);db.add(item);item.status=body.status;item.evidence=json.dumps(body.evidence,sort_keys=True);item.assessed_by=str(user.id);item.assessed_at=datetime.now(timezone.utc);return commit(db,user,"ASSESS","policy_compliance",item,"Recorded deterministic policy assessment")
@router.post("/policy-assignments/{assignment_id}/exceptions",status_code=201)
def exception(assignment_id:UUID,body:ExceptionWrite,db:Session=Depends(get_db),user=Depends(reader)):ensure_property(db,user,body.property_id);item=PolicyException(assignment_id=assignment_id,**body.model_dump(),requested_by=str(user.id));db.add(item);return commit(db,user,"REQUEST","policy_exception",item,"Requested time-bounded policy exception")
@router.post("/policy-exceptions/{exception_id}/{decision}")
def decide_exception(exception_id:UUID,decision:str,db:Session=Depends(get_db),user=Depends(manager)):
    if decision not in ("approve","reject"):raise HTTPException(422,"Decision must be approve or reject")
    item=row(db,PolicyException,exception_id,"Policy exception");ensure_property(db,user,item.property_id);item.status="approved" if decision=="approve" else "rejected";item.approved_by=str(user.id);item.decided_at=datetime.now(timezone.utc);return commit(db,user,decision.upper(),"policy_exception",item,"Reviewed policy exception")

def dashboard_payload(db,ids,audience):
    incidents=db.query(OperationalIncident).filter(OperationalIncident.property_id.in_(ids),~OperationalIncident.status.in_(("resolved","closed")));assets=db.query(EnterpriseAsset).filter(EnterpriseAsset.property_id.in_(ids));changes=db.query(ChangeRequest).filter(ChangeRequest.property_id.in_(ids),~ChangeRequest.status.in_(("completed","closed","cancelled")));sla=db.query(SLAMeasurement).filter(SLAMeasurement.entity_type=="property",SLAMeasurement.entity_id.in_(ids));total_sla=sla.count();met=sla.filter(SLAMeasurement.target_met.is_(True)).count();properties=db.query(Property).filter(Property.id.in_(ids)).all();rankings=[]
    for prop in properties:
        open_count=incidents.filter(OperationalIncident.property_id==prop.id).count();asset_count=assets.filter(EnterpriseAsset.property_id==prop.id).count();rankings.append({"property_id":str(prop.id),"name":prop.name,"health_score":max(0,100-open_count*5),"open_incidents":open_count,"assets":asset_count})
    rankings.sort(key=lambda x:(-x["health_score"],x["name"]));struct=structure_ids(db,ids);notifications=db.query(GlobalNotification).filter(GlobalNotification.status=="published",or_(GlobalNotification.expires_at.is_(None),GlobalNotification.expires_at>datetime.now(timezone.utc)),or_(and_(GlobalNotification.scope_type=="organization",GlobalNotification.organization_id.in_(struct["organizations"])),and_(GlobalNotification.scope_type=="region",GlobalNotification.scope_id.in_(struct["regions"])),and_(GlobalNotification.scope_type=="property",GlobalNotification.scope_id.in_(ids)))).order_by(desc(GlobalNotification.created_at)).limit(10).all();return {"audience":audience,"scope":{"property_count":len(ids)},"global_health":round(sum(r["health_score"] for r in rankings)/max(1,len(rankings)),2),"open_incidents":incidents.count(),"major_incidents":incidents.filter(OperationalIncident.severity.in_(("critical","major","sev1"))).count(),"active_changes":changes.count(),"assets":assets.count(),"sla_compliance":round(met*100/max(1,total_sla),2),"property_rankings":rankings,"regional_comparisons":[],"notifications":notifications}
@router.get("/executive-dashboard")
def executive_dashboard(audience:str=Query("corporate_it",pattern="^("+"|".join(AUDIENCES)+")$"),property_id:UUID|None=None,db:Session=Depends(get_db),user=Depends(reader)):
    ids=scoped_ids(db,user)
    if property_id:ensure_property(db,user,property_id);ids={property_id}
    return dashboard_payload(db,ids,audience)
@router.get("/cross-property/analytics")
def cross_property_analytics(db:Session=Depends(get_db),user=Depends(reader)):return dashboard_payload(db,scoped_ids(db,user),"cross_property_analytics")
@router.get("/cross-property/operations")
def cross_property_operations(db:Session=Depends(get_db),user=Depends(reader)):
    ids=scoped_ids(db,user);return {"property_ids":sorted(map(str,ids)),"incidents":db.query(OperationalIncident).filter(OperationalIncident.property_id.in_(ids)).count(),"shared_vendors":db.query(Vendor).filter(Vendor.status=="active").count(),"shared_contracts":db.query(Contract).filter(or_(Contract.property_id.is_(None),Contract.property_id.in_(ids))).count(),"isolation_enforced":True}
@router.get("/search")
def global_search(q:str=Query(min_length=2,max_length=120),page_size:int=Query(50,ge=1,le=100),db:Session=Depends(get_db),user=Depends(reader)):
    ids=scoped_ids(db,user);properties=db.query(Property).filter(Property.id.in_(ids),Property.name.ilike(f"%{q}%")).limit(page_size).all();incidents=db.query(OperationalIncident).filter(OperationalIncident.property_id.in_(ids),or_(OperationalIncident.title.ilike(f"%{q}%"),OperationalIncident.incident_number.ilike(f"%{q}%"))).limit(page_size).all();assets=db.query(EnterpriseAsset).filter(EnterpriseAsset.property_id.in_(ids),or_(EnterpriseAsset.asset_number.ilike(f"%{q}%"),EnterpriseAsset.asset_tag.ilike(f"%{q}%"))).limit(page_size).all();return {"items":[*[{"type":"property","id":str(x.id),"title":x.name,"property_id":str(x.id)} for x in properties],*[{"type":"incident","id":str(x.id),"title":x.title,"property_id":str(x.property_id)} for x in incidents],*[{"type":"asset","id":str(x.id),"title":x.asset_number,"property_id":str(x.property_id)} for x in assets]],"isolation_enforced":True}

@router.post("/notifications",status_code=201)
def create_notification(body:NotificationWrite,db:Session=Depends(get_db),user=Depends(manager)):ensure_scope(db,user,body.scope_type,body.scope_id or body.organization_id);data=body.model_dump();data["escalation_chain"]=json.dumps(data["escalation_chain"]);item=GlobalNotification(**data,created_by=str(user.id));db.add(item);return commit(db,user,"CREATE","global_notification",item,"Created governed notification")
@router.post("/notifications/{notification_id}/publish")
def publish_notification(notification_id:UUID,db:Session=Depends(get_db),user=Depends(manager)):item=row(db,GlobalNotification,notification_id,"Notification");ensure_scope(db,user,item.scope_type,item.scope_id or item.organization_id);item.status="published";item.publish_at=item.publish_at or datetime.now(timezone.utc);return commit(db,user,"PUBLISH","global_notification",item,"Published scoped enterprise notification")
@router.get("/reports")
def reports(db:Session=Depends(get_db),user=Depends(reader)):
    data=dashboard_payload(db,scoped_ids(db,user),"report");return {"reports":["Corporate KPI Reports","Regional Comparisons","Property Rankings","SLA Compliance by Region","Asset Distribution","Incident Distribution","Executive Monthly Reports","Compliance Reports","Operational Health Reports"],"summary":data}
def pdf_bytes(lines):
    esc=[str(x).replace("\\","\\\\").replace("(","\\(").replace(")","\\)")[:110] for x in lines[:45]];content="BT /F1 10 Tf 40 790 Td 13 TL "+" Tj T* ".join(f"({x})" for x in esc)+" Tj ET";objs=["<< /Type /Catalog /Pages 2 0 R >>","<< /Type /Pages /Kids [3 0 R] /Count 1 >>","<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",f"<< /Length {len(content.encode())} >>\nstream\n{content}\nendstream","<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"];out=bytearray(b"%PDF-1.4\n");offsets=[]
    for i,obj in enumerate(objs,1):offsets.append(len(out));out.extend(f"{i} 0 obj\n{obj}\nendobj\n".encode())
    x=len(out);out.extend(f"xref\n0 6\n0000000000 65535 f \n".encode());[out.extend(f"{o:010} 00000 n \n".encode()) for o in offsets];out.extend(f"trailer << /Size 6 /Root 1 0 R >>\nstartxref\n{x}\n%%EOF".encode());return bytes(out)
@router.get("/reports/export")
def export_report(format:str=Query(pattern=r"^(pdf|xlsx|csv)$"),db:Session=Depends(get_db),user=Depends(reader)):
    data=dashboard_payload(db,scoped_ids(db,user),"corporate_report");headers=["Property","Health Score","Open Incidents","Assets"];rows=[[x["name"],x["health_score"],x["open_incidents"],x["assets"]] for x in data["property_rankings"]]
    if format=="csv":s=io.StringIO();w=csv.writer(s);w.writerow(["HIOP Multi-Property Operations"]);w.writerow(headers);w.writerows(rows);return Response(s.getvalue(),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=hiop-corporate.csv"})
    if format=="xlsx":wb=Workbook();ws=wb.active;ws.title="Property Health";ws.append(["HIOP Multi-Property Operations"]);ws.append(headers);[ws.append(x) for x in rows];out=io.BytesIO();wb.save(out);return Response(out.getvalue(),media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",headers={"Content-Disposition":"attachment; filename=hiop-corporate.xlsx"})
    return Response(pdf_bytes(["HIOP Multi-Property Operations",*headers,*[" | ".join(map(str,x)) for x in rows]]),media_type="application/pdf",headers={"Content-Disposition":"attachment; filename=hiop-corporate.pdf"})
