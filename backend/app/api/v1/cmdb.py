import csv
import io
import json
from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from openpyxl import Workbook
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import desc, or_
from sqlalchemy.orm import Session

from app.core.security import get_db, require_roles
from app.models.cmdb import (
    CIAlias, CIAttribute, CIAttributeHistory, CIClass, CIHealthSnapshot,
    CIIdentifier, CILifecycle, CILifecycleHistory, CIReconciliationCandidate,
    CIRelationship, CIRelationshipType, CIStatus, CIType, ConfigurationItem,
    DependencyGraph, RelationshipHistory,
)
from app.models.hierarchy import Property
from app.models.device import Device
from app.models.discovered_device import DiscoveredDevice
from app.models.property_access import UserPropertyAccess
from app.services.audit_service import create_audit_log
from app.services.cmdb_service import (
    add_relationship, calculate_health, ci_identifier, graph_for,
    impact_analysis, normalize_identifier, reconciliation_candidates,
    save_graph_snapshot, set_attribute, transition_lifecycle,
)
from app.websocket.connection_manager import manager

router=APIRouter(prefix="/cmdb",tags=["Enterprise CMDB"])
reader=require_roles(["admin","superadmin","technician","viewer"]);contributor=require_roles(["admin","superadmin","technician"]);admin=require_roles(["admin","superadmin"])


class CIWrite(BaseModel):
    property_id:UUID|None=None;department_id:UUID|None=None;type_id:UUID;class_id:UUID;name:str=Field(min_length=2,max_length=180);display_name:str|None=Field(None,max_length=220);description:str|None=Field(None,max_length=30000);category:str|None=Field(None,max_length=100);owner_id:str|None=None;status:str=Field("active",pattern=r"^(active|inactive|maintenance|retired|archived)$");lifecycle_stage:str=Field("planned",pattern=r"^(planned|ordered|installed|operational|maintenance|retired|archived)$");criticality:str=Field("medium",pattern=r"^(low|medium|high|critical)$");operational_status:str=Field("unknown",pattern=r"^(unknown|online|offline|degraded|maintenance|retired)$");installation_date:date|None=None;warranty_date:date|None=None;retirement_date:date|None=None;manufacturer:str|None=Field(None,max_length=160);model:str|None=Field(None,max_length=160);serial_number:str|None=Field(None,max_length=180);asset_id:UUID|None=None;discovered_device_id:UUID|None=None;discovery_source:str=Field("manual",pattern=r"^(manual|network_discovery|snmp|active_directory|configuration_management|csv_import|device)$");source_reference:str|None=Field(None,max_length=180)
class CIPatch(BaseModel):
    name:str|None=Field(None,min_length=2,max_length=180);display_name:str|None=Field(None,max_length=220);description:str|None=Field(None,max_length=30000);category:str|None=Field(None,max_length=100);owner_id:str|None=None;department_id:UUID|None=None;criticality:str|None=Field(None,pattern=r"^(low|medium|high|critical)$");operational_status:str|None=Field(None,pattern=r"^(unknown|online|offline|degraded|maintenance|retired)$");installation_date:date|None=None;warranty_date:date|None=None;retirement_date:date|None=None;manufacturer:str|None=Field(None,max_length=160);model:str|None=Field(None,max_length=160);serial_number:str|None=Field(None,max_length=180);verification_status:str|None=Field(None,pattern=r"^(unverified|verified|stale|failed)$")
class ClassWrite(BaseModel):name:str=Field(min_length=2,max_length=100);code:str=Field(pattern=r"^[a-z][a-z0-9_]{1,59}$");domain:str=Field(max_length=60);description:str|None=Field(None,max_length=10000);enabled:bool=True
class TypeWrite(BaseModel):class_id:UUID;name:str=Field(min_length=2,max_length=120);code:str=Field(pattern=r"^[a-z][a-z0-9_]{1,79}$");category:str|None=Field(None,max_length=100);attribute_schema:dict=Field(default_factory=dict);enabled:bool=True
class AttributeWrite(BaseModel):name:str=Field(pattern=r"^[a-z][a-z0-9_.-]{1,99}$");data_type:str=Field(max_length=30);value_text:str|None=Field(None,max_length=20000);value_number:float|None=None;value_boolean:bool|None=None;unit:str|None=Field(None,max_length=40);source:str=Field("manual",pattern=r"^(manual|network_discovery|snmp|active_directory|configuration_management|csv_import)$");verified:bool=False;reason:str=Field("Attribute updated",min_length=2,max_length=500)
class IdentifierWrite(BaseModel):identifier_type:str=Field(pattern=r"^(serial|asset_tag|mac|ip|hostname|fqdn|uuid|cloud_id|vendor_id)$");value:str=Field(min_length=1,max_length=255);primary:bool=False;verified:bool=False;source:str=Field("manual",max_length=40)
class AliasWrite(BaseModel):alias:str=Field(min_length=1,max_length=255);alias_type:str=Field("name",pattern=r"^(name|hostname|legacy_name|service_name)$")
class RelationshipWrite(BaseModel):target_ci_id:UUID;relationship_type_id:UUID;evidence:str=Field(min_length=3,max_length=10000);confidence:int=Field(100,ge=0,le=100)
class RelationshipAction(BaseModel):reason:str=Field(min_length=3,max_length=1000)
class LifecycleWrite(BaseModel):target_stage:str=Field(pattern=r"^(planned|ordered|installed|operational|maintenance|retired|archived)$");reason:str=Field(min_length=3,max_length=1000)
class ReconcileWrite(BaseModel):
    property_id:UUID|None=None;source_types:list[str]=Field(default_factory=lambda:["device","network_discovery"],max_length=6);limit:int=Field(500,ge=1,le=2000)
    @model_validator(mode="after")
    def sources(self):
        if not self.source_types or not set(self.source_types).issubset({"device","network_discovery","snmp","active_directory","configuration_management","csv_import"}):raise ValueError("Unsupported reconciliation source")
        return self
class CandidateDecision(BaseModel):action:str=Field(pattern=r"^(create|link|reject|ignore)$");type_id:UUID|None=None;class_id:UUID|None=None;notes:str=Field(min_length=2,max_length=2000)
class BulkWrite(BaseModel):ci_ids:list[UUID]=Field(min_length=1,max_length=100);action:str=Field(pattern=r"^(verify|mark_stale|maintenance)$");reason:str=Field(min_length=3,max_length=1000)


def allowed_properties(db,user):
    if user.role in {"admin","superadmin"}:return None
    return [r.property_id for r in db.query(UserPropertyAccess).filter_by(user_id=user.id,enabled=True).all()]
def require_property(db,user,property_id):
    if property_id is None:
        if user.role not in {"admin","superadmin"}:raise HTTPException(403,"Corporate CIs require administrator access")
        return
    if not db.get(Property,property_id):raise HTTPException(404,"Property not found")
    allowed=allowed_properties(db,user)
    if allowed is not None and property_id not in allowed:raise HTTPException(403,"Property is not authorized")
def scoped(q,column,db,user):
    allowed=allowed_properties(db,user);return q if allowed is None else q.filter(column.in_(allowed))
def ci_or_404(db,user,ci_id):
    row=db.get(ConfigurationItem,ci_id)
    if not row:raise HTTPException(404,"Configuration item not found")
    require_property(db,user,row.property_id);return row
def commit(db,user,action,entity,row,message):
    create_audit_log(db,user.username,action,entity,str(row.id),message);db.commit();db.refresh(row);manager.broadcast_from_thread({"type":"cmdb_record_updated","entity_type":entity,"entity_id":str(row.id),"property_id":str(getattr(row,"property_id","") or "") or None});return row


@router.get("/dashboard")
def dashboard(db:Session=Depends(get_db),user=Depends(reader)):
    q=scoped(db.query(ConfigurationItem),ConfigurationItem.property_id,db,user);total=q.count();relq=db.query(CIRelationship).join(ConfigurationItem,ConfigurationItem.id==CIRelationship.source_ci_id);relq=scoped(relq,ConfigurationItem.property_id,db,user)
    latest=scoped(db.query(CIHealthSnapshot),CIHealthSnapshot.property_id,db,user).order_by(desc(CIHealthSnapshot.calculated_at)).first()
    return {"total_cis":total,"critical_cis":q.filter_by(criticality="critical").count(),"unverified":q.filter(ConfigurationItem.verification_status!="verified").count(),"orphan_cis":latest.orphan_cis if latest else 0,"duplicates":latest.duplicate_candidates if latest else 0,"relationships":relq.filter(CIRelationship.status=="active").count(),"health_score":latest.health_score if latest else None,"lifecycle":dict(q.with_entities(ConfigurationItem.lifecycle_stage, __import__('sqlalchemy').func.count(ConfigurationItem.id)).group_by(ConfigurationItem.lifecycle_stage).all()),"recent":q.order_by(desc(ConfigurationItem.updated_at)).limit(10).all()}


@router.get("/classes")
def classes(db:Session=Depends(get_db),_=Depends(reader)):return {"items":db.query(CIClass).order_by(CIClass.domain,CIClass.name).all()}
@router.post("/classes",status_code=201)
def create_class(payload:ClassWrite,db:Session=Depends(get_db),user=Depends(admin)):
    row=CIClass(**payload.model_dump());db.add(row);return commit(db,user,"CI_CLASS_CREATED","CIClass",row,"Created CMDB class")
@router.get("/types")
def types(class_id:UUID|None=None,db:Session=Depends(get_db),_=Depends(reader)):
    q=db.query(CIType)
    if class_id:q=q.filter_by(class_id=class_id)
    return {"items":q.order_by(CIType.name).all()}
@router.post("/types",status_code=201)
def create_type(payload:TypeWrite,db:Session=Depends(get_db),user=Depends(admin)):
    if not db.get(CIClass,payload.class_id):raise HTTPException(422,"Unknown CI class")
    values=payload.model_dump();values["attribute_schema"]=json.dumps(values["attribute_schema"]);row=CIType(**values);db.add(row);return commit(db,user,"CI_TYPE_CREATED","CIType",row,"Created CMDB type")
@router.get("/statuses")
def statuses(db:Session=Depends(get_db),_=Depends(reader)):return {"items":db.query(CIStatus).order_by(CIStatus.name).all()}
@router.get("/lifecycles")
def lifecycles(db:Session=Depends(get_db),_=Depends(reader)):return {"items":db.query(CILifecycle).order_by(CILifecycle.sequence_order).all()}


@router.get("/items")
def list_items(search:str|None=None,property_id:UUID|None=None,class_id:UUID|None=None,type_id:UUID|None=None,status:str|None=None,lifecycle_stage:str|None=None,criticality:str|None=None,orphan_only:bool=False,page:int=Query(1,ge=1),page_size:int=Query(25,ge=1,le=100),sort:str=Query("updated_at",pattern=r"^(name|ci_number|updated_at|criticality|status)$"),db:Session=Depends(get_db),user=Depends(reader)):
    q=scoped(db.query(ConfigurationItem),ConfigurationItem.property_id,db,user)
    if search:q=q.filter(or_(ConfigurationItem.ci_number.ilike(f"%{search[:120]}%"),ConfigurationItem.name.ilike(f"%{search[:120]}%"),ConfigurationItem.serial_number.ilike(f"%{search[:120]}%"),ConfigurationItem.manufacturer.ilike(f"%{search[:120]}%")))
    for key,value in (("property_id",property_id),("class_id",class_id),("type_id",type_id),("status",status),("lifecycle_stage",lifecycle_stage),("criticality",criticality)):
        if value is not None:q=q.filter(getattr(ConfigurationItem,key)==value)
    if property_id:require_property(db,user,property_id)
    if orphan_only:
        linked=db.query(CIRelationship.source_ci_id).filter(CIRelationship.status=="active").union(db.query(CIRelationship.target_ci_id).filter(CIRelationship.status=="active"));q=q.filter(~ConfigurationItem.id.in_(linked))
    total=q.count();column=getattr(ConfigurationItem,sort);order=column.asc() if sort in {"name","ci_number"} else column.desc();return {"items":q.order_by(order).offset((page-1)*page_size).limit(page_size).all(),"total":total,"page":page,"page_size":page_size}
@router.post("/items",status_code=201)
def create_item(payload:CIWrite,db:Session=Depends(get_db),user=Depends(contributor)):
    require_property(db,user,payload.property_id);ctype=db.get(CIType,payload.type_id)
    if not ctype or ctype.class_id!=payload.class_id:raise HTTPException(422,"CI type does not belong to selected class")
    if payload.asset_id:
        asset=db.get(Device,payload.asset_id)
        if not asset:raise HTTPException(422,"Asset reference not found")
        if asset.property_id and asset.property_id!=payload.property_id:raise HTTPException(409,"Asset and CI property do not match")
    if payload.discovered_device_id and not db.get(DiscoveredDevice,payload.discovered_device_id):raise HTTPException(422,"Discovery reference not found")
    row=ConfigurationItem(ci_number=ci_identifier(db),created_by=user.id,**payload.model_dump());db.add(row);db.flush();db.add(CILifecycleHistory(ci_id=row.id,previous_stage=None,current_stage=row.lifecycle_stage,reason="CI created",actor_id=user.id));return commit(db,user,"CI_CREATED","ConfigurationItem",row,"Created reviewed configuration item")
@router.get("/items/{ci_id}")
def get_item(ci_id:UUID,db:Session=Depends(get_db),user=Depends(reader)):return ci_or_404(db,user,ci_id)
@router.patch("/items/{ci_id}")
def update_item(ci_id:UUID,payload:CIPatch,db:Session=Depends(get_db),user=Depends(contributor)):
    row=ci_or_404(db,user,ci_id)
    if row.lifecycle_stage=="archived":raise HTTPException(409,"Archived CIs cannot be edited")
    for key,value in payload.model_dump(exclude_unset=True).items():setattr(row,key,value)
    row.updated_by=user.id;row.updated_at=datetime.now(timezone.utc);return commit(db,user,"CI_UPDATED","ConfigurationItem",row,"Updated CI master data")
@router.delete("/items/{ci_id}")
def archive_item(ci_id:UUID,reason:str=Query(min_length=3,max_length=1000),db:Session=Depends(get_db),user=Depends(admin)):
    row=ci_or_404(db,user,ci_id)
    if row.lifecycle_stage!="retired":raise HTTPException(409,"Only retired CIs may be archived")
    transition_lifecycle(db,row,"archived",reason,user);db.commit();return {"archived":True,"ci_id":str(row.id)}
@router.post("/items/{ci_id}/lifecycle")
def lifecycle(ci_id:UUID,payload:LifecycleWrite,db:Session=Depends(get_db),user=Depends(contributor)):
    row=ci_or_404(db,user,ci_id)
    if payload.target_stage=="archived" and user.role not in {"admin","superadmin"}:raise HTTPException(403,"Administrator permission is required to archive a CI")
    transition_lifecycle(db,row,payload.target_stage,payload.reason,user);db.commit();return row
@router.get("/items/{ci_id}/lifecycle")
def lifecycle_history(ci_id:UUID,db:Session=Depends(get_db),user=Depends(reader)):ci_or_404(db,user,ci_id);return {"items":db.query(CILifecycleHistory).filter_by(ci_id=ci_id).order_by(desc(CILifecycleHistory.occurred_at)).all()}


@router.get("/items/{ci_id}/attributes")
def attributes(ci_id:UUID,db:Session=Depends(get_db),user=Depends(reader)):ci_or_404(db,user,ci_id);return {"items":db.query(CIAttribute).filter_by(ci_id=ci_id).order_by(CIAttribute.name).all()}
@router.put("/items/{ci_id}/attributes",status_code=201)
def update_attribute(ci_id:UUID,payload:AttributeWrite,db:Session=Depends(get_db),user=Depends(contributor)):
    ci=ci_or_404(db,user,ci_id);row=set_attribute(db,ci,payload,user);return commit(db,user,"CI_ATTRIBUTE_UPDATED","CIAttribute",row,f"Updated {payload.name}")
@router.get("/attributes/{attribute_id}/history")
def attribute_history(attribute_id:UUID,db:Session=Depends(get_db),user=Depends(reader)):
    row=db.get(CIAttribute,attribute_id)
    if not row:raise HTTPException(404,"CI attribute not found")
    ci_or_404(db,user,row.ci_id);return {"items":db.query(CIAttributeHistory).filter_by(attribute_id=row.id).order_by(desc(CIAttributeHistory.changed_at)).all()}
@router.post("/items/{ci_id}/identifiers",status_code=201)
def add_identifier(ci_id:UUID,payload:IdentifierWrite,db:Session=Depends(get_db),user=Depends(contributor)):
    ci_or_404(db,user,ci_id);row=CIIdentifier(ci_id=ci_id,normalized_value=normalize_identifier(payload.identifier_type,payload.value),**payload.model_dump());db.add(row);return commit(db,user,"CI_IDENTIFIER_ADDED","CIIdentifier",row,f"Added {payload.identifier_type} identifier")
@router.get("/items/{ci_id}/identifiers")
def identifiers(ci_id:UUID,db:Session=Depends(get_db),user=Depends(reader)):ci_or_404(db,user,ci_id);return {"items":db.query(CIIdentifier).filter_by(ci_id=ci_id).all()}
@router.post("/items/{ci_id}/aliases",status_code=201)
def add_alias(ci_id:UUID,payload:AliasWrite,db:Session=Depends(get_db),user=Depends(contributor)):
    ci_or_404(db,user,ci_id);row=CIAlias(ci_id=ci_id,normalized_alias=payload.alias.strip().lower(),**payload.model_dump());db.add(row);return commit(db,user,"CI_ALIAS_ADDED","CIAlias",row,"Added CI alias")


@router.get("/relationship-types")
def relationship_types(db:Session=Depends(get_db),_=Depends(reader)):return {"items":db.query(CIRelationshipType).filter_by(enabled=True).order_by(CIRelationshipType.name).all()}
@router.post("/items/{ci_id}/relationships",status_code=201)
def create_relationship(ci_id:UUID,payload:RelationshipWrite,db:Session=Depends(get_db),user=Depends(contributor)):
    source=ci_or_404(db,user,ci_id);target=ci_or_404(db,user,payload.target_ci_id);rel_type=db.get(CIRelationshipType,payload.relationship_type_id)
    if not rel_type or not rel_type.enabled:raise HTTPException(422,"Unknown relationship type")
    row=add_relationship(db,source,target,rel_type,payload.evidence,payload.confidence,user);db.commit();db.refresh(row);return row
@router.get("/items/{ci_id}/relationships")
def item_relationships(ci_id:UUID,direction:str=Query("both",pattern=r"^(upstream|downstream|both)$"),db:Session=Depends(get_db),user=Depends(reader)):
    ci_or_404(db,user,ci_id);q=db.query(CIRelationship).filter(CIRelationship.status=="active")
    q=q.filter(CIRelationship.target_ci_id==ci_id) if direction=="upstream" else q.filter(CIRelationship.source_ci_id==ci_id) if direction=="downstream" else q.filter(or_(CIRelationship.source_ci_id==ci_id,CIRelationship.target_ci_id==ci_id));return {"items":q.limit(1000).all()}
@router.post("/relationships/{relationship_id}/suppress")
def suppress_relationship(relationship_id:UUID,payload:RelationshipAction,db:Session=Depends(get_db),user=Depends(contributor)):
    row=db.get(CIRelationship,relationship_id)
    if not row:raise HTTPException(404,"CI relationship not found")
    ci_or_404(db,user,row.source_ci_id);previous=json.dumps({"status":row.status});row.status="suppressed";row.valid_to=datetime.now(timezone.utc);db.add(RelationshipHistory(relationship_id=row.id,action="suppressed",previous_state=previous,current_state=json.dumps({"status":row.status}),reason=payload.reason,actor_id=user.id));return commit(db,user,"CI_RELATIONSHIP_SUPPRESSED","CIRelationship",row,payload.reason)
@router.get("/relationships/{relationship_id}/history")
def relationship_history(relationship_id:UUID,db:Session=Depends(get_db),user=Depends(reader)):
    row=db.get(CIRelationship,relationship_id)
    if not row:raise HTTPException(404,"CI relationship not found")
    ci_or_404(db,user,row.source_ci_id);return {"items":db.query(RelationshipHistory).filter_by(relationship_id=row.id).order_by(desc(RelationshipHistory.occurred_at)).all()}


@router.get("/dependency-graph")
def dependency_graph(root_ci_id:UUID|None=None,property_id:UUID|None=None,max_depth:int=Query(6,ge=1,le=12),max_nodes:int=Query(1000,ge=1,le=2000),db:Session=Depends(get_db),user=Depends(reader)):
    if root_ci_id:
        root=ci_or_404(db,user,root_ci_id)
        if property_id and root.property_id!=property_id:raise HTTPException(409,"Root CI is outside the selected property")
        property_id=property_id or root.property_id
    if not root_ci_id and not property_id and allowed_properties(db,user) is not None:raise HTTPException(422,"A property or root CI is required")
    if property_id:require_property(db,user,property_id)
    graph=graph_for(db,root_ci_id,property_id,max_depth,max_nodes);return graph
@router.post("/dependency-graph/snapshot",status_code=201)
def snapshot_graph(root_ci_id:UUID|None=None,property_id:UUID|None=None,db:Session=Depends(get_db),user=Depends(admin)):
    if root_ci_id:ci_or_404(db,user,root_ci_id)
    if property_id:require_property(db,user,property_id)
    row=save_graph_snapshot(db,graph_for(db,root_ci_id,property_id),property_id,root_ci_id,user);return commit(db,user,"CI_GRAPH_SNAPSHOT_CREATED","DependencyGraph",row,"Created deterministic dependency graph snapshot")
@router.get("/items/{ci_id}/impact")
def impact(ci_id:UUID,max_depth:int=Query(6,ge=1,le=12),db:Session=Depends(get_db),user=Depends(reader)):return impact_analysis(db,ci_or_404(db,user,ci_id),max_depth)


@router.post("/reconciliation/run")
def run_reconciliation(payload:ReconcileWrite,db:Session=Depends(get_db),user=Depends(admin)):
    require_property(db,user,payload.property_id);result=reconciliation_candidates(db,payload.property_id,payload.limit,payload.source_types);create_audit_log(db,user.username,"CMDB_RECONCILIATION_RUN","CIReconciliationCandidate","batch",f"Created {result['created']}, refreshed {result['updated']}; no CI was auto-created");db.commit();manager.broadcast_from_thread({"type":"cmdb_reconciliation_completed",**result});return result
@router.get("/reconciliation/candidates")
def candidates(status:str|None=None,property_id:UUID|None=None,page:int=Query(1,ge=1),page_size:int=Query(25,ge=1,le=100),db:Session=Depends(get_db),user=Depends(reader)):
    q=scoped(db.query(CIReconciliationCandidate),CIReconciliationCandidate.property_id,db,user)
    if status:q=q.filter_by(status=status)
    if property_id:require_property(db,user,property_id);q=q.filter_by(property_id=property_id)
    total=q.count();return {"items":q.order_by(desc(CIReconciliationCandidate.updated_at)).offset((page-1)*page_size).limit(page_size).all(),"total":total,"page":page,"page_size":page_size}
@router.post("/reconciliation/candidates/{candidate_id}/decision")
def decide_candidate(candidate_id:UUID,payload:CandidateDecision,db:Session=Depends(get_db),user=Depends(admin)):
    candidate=db.get(CIReconciliationCandidate,candidate_id)
    if not candidate:raise HTTPException(404,"Reconciliation candidate not found")
    require_property(db,user,candidate.property_id)
    if candidate.status!="pending":raise HTTPException(409,"Candidate already reviewed")
    ci=None
    if payload.action=="link":
        if not candidate.proposed_ci_id:raise HTTPException(409,"No reviewed CI match is available")
        ci=ci_or_404(db,user,candidate.proposed_ci_id)
        if candidate.source_type=="device" and ci.asset_id and ci.asset_id!=candidate.source_id:raise HTTPException(409,"CI is already linked to another asset")
        if candidate.source_type=="network_discovery" and ci.discovered_device_id and ci.discovered_device_id!=candidate.source_id:raise HTTPException(409,"CI is already linked to another discovery record")
        if candidate.source_type=="device" and not ci.asset_id:ci.asset_id=candidate.source_id
        if candidate.source_type=="network_discovery" and not ci.discovered_device_id:ci.discovered_device_id=candidate.source_id
    elif payload.action=="create":
        if not payload.type_id or not payload.class_id:raise HTTPException(422,"Type and class are required to create a CI")
        ctype=db.get(CIType,payload.type_id)
        if not ctype or ctype.class_id!=payload.class_id:raise HTTPException(422,"Invalid CI type/class")
        values=json.loads(candidate.proposed_values);allowed={k:v for k,v in values.items() if k in {"name","manufacturer","model","serial_number","asset_id","discovered_device_id"} and v is not None};allowed["asset_id"]=UUID(allowed["asset_id"]) if allowed.get("asset_id") else None;allowed["discovered_device_id"]=UUID(allowed["discovered_device_id"]) if allowed.get("discovered_device_id") else None
        ci=ConfigurationItem(ci_number=ci_identifier(db),property_id=candidate.property_id,type_id=payload.type_id,class_id=payload.class_id,display_name=allowed.get("name"),discovery_source=candidate.source_type,source_reference=str(candidate.source_id),created_by=user.id,**allowed);db.add(ci);db.flush();db.add(CILifecycleHistory(ci_id=ci.id,previous_stage=None,current_stage="planned",reason="Reviewed discovery reconciliation",actor_id=user.id));candidate.proposed_ci_id=ci.id
    candidate.status="approved" if payload.action in {"create","link"} else payload.action+"d";candidate.reviewed_by=user.id;candidate.reviewed_at=datetime.now(timezone.utc);db.add(candidate);create_audit_log(db,user.username,"CMDB_RECONCILIATION_DECIDED","CIReconciliationCandidate",str(candidate.id),f"{payload.action}: {payload.notes}");db.commit();return {"candidate":candidate,"configuration_item":ci}


@router.post("/health/recalculate",status_code=201)
def recalculate_health(property_id:UUID|None=None,db:Session=Depends(get_db),user=Depends(admin)):
    require_property(db,user,property_id);row=calculate_health(db,property_id);return commit(db,user,"CMDB_HEALTH_CALCULATED","CIHealthSnapshot",row,"Calculated deterministic CMDB health")
@router.get("/health")
def health(property_id:UUID|None=None,db:Session=Depends(get_db),user=Depends(reader)):
    q=scoped(db.query(CIHealthSnapshot),CIHealthSnapshot.property_id,db,user)
    if property_id:require_property(db,user,property_id);q=q.filter_by(property_id=property_id)
    row=q.order_by(desc(CIHealthSnapshot.calculated_at)).first();return row or {"health_score":None,"status":"not_calculated"}
@router.get("/health/history")
def health_history(property_id:UUID|None=None,page:int=Query(1,ge=1),page_size:int=Query(25,ge=1,le=100),db:Session=Depends(get_db),user=Depends(reader)):
    q=scoped(db.query(CIHealthSnapshot),CIHealthSnapshot.property_id,db,user)
    if property_id:require_property(db,user,property_id);q=q.filter_by(property_id=property_id)
    total=q.count();return {"items":q.order_by(desc(CIHealthSnapshot.calculated_at)).offset((page-1)*page_size).limit(page_size).all(),"total":total,"page":page,"page_size":page_size}
@router.post("/bulk")
def bulk(payload:BulkWrite,db:Session=Depends(get_db),user=Depends(contributor)):
    results=[]
    for ci_id in payload.ci_ids:
        try:
            row=ci_or_404(db,user,ci_id)
            if payload.action=="verify":row.verification_status="verified";row.last_verified_at=datetime.now(timezone.utc)
            elif payload.action=="mark_stale":row.verification_status="stale"
            elif payload.action=="maintenance":transition_lifecycle(db,row,"maintenance",payload.reason,user)
            row.updated_by=user.id;results.append({"ci_id":str(ci_id),"success":True})
        except HTTPException as exc:results.append({"ci_id":str(ci_id),"success":False,"error":exc.detail})
    create_audit_log(db,user.username,"CMDB_BULK_ACTION","ConfigurationItem","batch",f"{payload.action}: {len(results)} reviewed results");db.commit();return {"items":results}


@router.get("/reports/summary")
def report_summary(db:Session=Depends(get_db),user=Depends(reader)):
    q=scoped(db.query(ConfigurationItem),ConfigurationItem.property_id,db,user);latest=scoped(db.query(CIHealthSnapshot),CIHealthSnapshot.property_id,db,user).order_by(desc(CIHealthSnapshot.calculated_at)).first()
    return {"total":q.count(),"critical":q.filter_by(criticality="critical").count(),"discovered":q.filter(ConfigurationItem.discovery_source!="manual").count(),"retired":q.filter_by(lifecycle_stage="retired").count(),"warranty_expired":q.filter(ConfigurationItem.warranty_date<date.today()).count(),"health_score":latest.health_score if latest else None,"orphan_cis":latest.orphan_cis if latest else 0,"duplicate_candidates":latest.duplicate_candidates if latest else 0}
def safe(value):return f"'{value}" if str(value or "").startswith(("=","+","-","@")) else str(value or "")
@router.get("/reports/export")
def export(format:str=Query("csv",pattern=r"^(csv|xlsx|pdf)$"),db:Session=Depends(get_db),user=Depends(reader)):
    rows=scoped(db.query(ConfigurationItem),ConfigurationItem.property_id,db,user).order_by(ConfigurationItem.ci_number).limit(5000).all();headers=["CI Number","Name","Class","Status","Lifecycle","Criticality","Manufacturer","Model","Serial"]
    data=[[safe(r.ci_number),safe(r.name),str(r.class_id),r.status,r.lifecycle_stage,r.criticality,safe(r.manufacturer),safe(r.model),safe(r.serial_number)] for r in rows]
    if format=="csv":out=io.StringIO();w=csv.writer(out);w.writerow(headers);w.writerows(data);return Response(out.getvalue(),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=cmdb-report.csv"})
    if format=="xlsx":book=Workbook();sheet=book.active;sheet.title="CMDB";sheet.append(headers);[sheet.append(row) for row in data];out=io.BytesIO();book.save(out);return Response(out.getvalue(),media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",headers={"Content-Disposition":"attachment; filename=cmdb-report.xlsx"})
    from app.api.v1.knowledge import printable_pdf
    return Response(printable_pdf("HIOP CMDB Report",[" | ".join(map(str,row)) for row in data]),media_type="application/pdf",headers={"Content-Disposition":"attachment; filename=cmdb-report.pdf"})
