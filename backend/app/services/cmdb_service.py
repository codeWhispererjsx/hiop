import hashlib
import json
import re
from collections import deque
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import or_

from app.models.cmdb import (
    CIAttribute, CIAttributeHistory, CIHealthSnapshot, CIIdentifier,
    CILifecycleHistory, CIReconciliationCandidate, CIRelationship,
    CIRelationshipType, ConfigurationItem, DependencyGraph,
    RelationshipHistory,
)
from app.models.device import Device
from app.models.discovered_device import DiscoveredDevice
from app.services.audit_service import create_audit_log
from app.websocket.connection_manager import manager


LIFECYCLE_TRANSITIONS = {
    "planned": {"ordered", "archived"}, "ordered": {"installed", "planned"},
    "installed": {"operational", "maintenance"},
    "operational": {"maintenance", "retired"},
    "maintenance": {"operational", "retired"}, "retired": {"archived"},
    "archived": set(),
}
ATTRIBUTE_TYPES = {"string", "integer", "decimal", "boolean", "date", "datetime", "ip", "mac", "url", "json"}
DEPENDENCY_CODES = {"runs_on", "hosts", "depends_on", "uses", "supports", "contained_in", "located_in", "managed_by", "monitored_by"}


def ci_identifier(db) -> str:
    year = datetime.now(timezone.utc).year; prefix = f"CI-{year}-"
    latest = db.query(ConfigurationItem.ci_number).filter(ConfigurationItem.ci_number.like(f"{prefix}%")).order_by(ConfigurationItem.ci_number.desc()).first()
    number = int(latest[0].rsplit("-", 1)[-1]) + 1 if latest else 1
    return f"{prefix}{number:07d}"


def normalize_identifier(kind: str, value: str) -> str:
    clean = value.strip().lower()
    if kind == "mac": clean = re.sub(r"[^0-9a-f]", "", clean)
    if kind in {"hostname", "fqdn", "name"}: clean = clean.rstrip(".")
    if not clean or len(clean) > 255: raise HTTPException(422, "Invalid CI identifier")
    return clean


def attribute_value(payload) -> str:
    values = [payload.value_text, payload.value_number, payload.value_boolean]
    if sum(value is not None for value in values) != 1: raise HTTPException(422, "Exactly one attribute value is required")
    if payload.data_type not in ATTRIBUTE_TYPES: raise HTTPException(422, "Unsupported CI attribute type")
    value = next(value for value in values if value is not None)
    if payload.data_type == "integer" and (not isinstance(value, float) or not value.is_integer()): raise HTTPException(422, "Integer attributes require an integer numeric value")
    if payload.data_type == "ip":
        from ipaddress import ip_address
        try: ip_address(str(value))
        except ValueError as exc: raise HTTPException(422, "Invalid IP attribute") from exc
    if payload.data_type == "mac" and not re.fullmatch(r"(?:[0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}", str(value)): raise HTTPException(422, "Invalid MAC attribute")
    if payload.data_type == "json":
        try: json.loads(str(value))
        except json.JSONDecodeError as exc: raise HTTPException(422, "Invalid JSON attribute") from exc
    return json.dumps(value, default=str)


def set_attribute(db, ci, payload, user):
    current = db.query(CIAttribute).filter_by(ci_id=ci.id, name=payload.name).first(); serialized = attribute_value(payload)
    if current:
        previous = json.dumps(current.value_text if current.value_text is not None else current.value_number if current.value_number is not None else current.value_boolean)
        db.add(CIAttributeHistory(attribute_id=current.id, previous_value=previous, current_value=serialized, changed_by=user.id, reason=payload.reason))
        for field, value in payload.model_dump(exclude={"reason"}).items(): setattr(current, field, value)
        current.updated_by = user.id; current.updated_at = datetime.now(timezone.utc); return current
    row = CIAttribute(ci_id=ci.id, updated_by=user.id, **payload.model_dump(exclude={"reason"})); db.add(row); db.flush()
    db.add(CIAttributeHistory(attribute_id=row.id, previous_value=None, current_value=serialized, changed_by=user.id, reason=payload.reason)); return row


def transition_lifecycle(db, ci, target, reason, user):
    if target not in LIFECYCLE_TRANSITIONS.get(ci.lifecycle_stage, set()): raise HTTPException(409, f"Invalid CI lifecycle transition: {ci.lifecycle_stage} -> {target}")
    previous = ci.lifecycle_stage; ci.lifecycle_stage = target; ci.updated_by = user.id; ci.updated_at = datetime.now(timezone.utc)
    if target == "retired": ci.retirement_date = ci.retirement_date or datetime.now(timezone.utc).date(); ci.operational_status = "retired"
    if target == "archived": ci.status = "archived"
    db.add(CILifecycleHistory(ci_id=ci.id, previous_stage=previous, current_stage=target, reason=reason, actor_id=user.id))
    create_audit_log(db, user.username, "CI_LIFECYCLE_CHANGED", "ConfigurationItem", str(ci.id), f"{previous} -> {target}: {reason}")
    manager.broadcast_from_thread({"type":"cmdb_ci_lifecycle_changed","ci_id":str(ci.id),"stage":target,"property_id":str(ci.property_id) if ci.property_id else None})
    return ci


def relationship_snapshot(row):
    return json.dumps({"source_ci_id":str(row.source_ci_id),"target_ci_id":str(row.target_ci_id),"relationship_type_id":str(row.relationship_type_id),"status":row.status,"confidence":row.confidence},sort_keys=True)


def add_relationship(db, source, target, rel_type, evidence, confidence, user):
    if source.id == target.id: raise HTTPException(422, "A CI cannot relate to itself")
    if source.property_id and target.property_id and source.property_id != target.property_id and rel_type.code in {"contained_in", "located_in"}: raise HTTPException(409, "Containment and location relationships cannot cross properties")
    existing = db.query(CIRelationship).filter_by(source_ci_id=source.id,target_ci_id=target.id,relationship_type_id=rel_type.id).first()
    if existing and existing.status == "active": raise HTTPException(409, "Relationship already exists")
    row = existing or CIRelationship(source_ci_id=source.id,target_ci_id=target.id,relationship_type_id=rel_type.id,created_by=user.id)
    previous = relationship_snapshot(row) if existing else None; row.status="active"; row.source="manual"; row.evidence=evidence; row.confidence=confidence; row.valid_to=None; row.updated_at=datetime.now(timezone.utc); db.add(row); db.flush()
    db.add(RelationshipHistory(relationship_id=row.id,action="restored" if existing else "created",previous_state=previous,current_state=relationship_snapshot(row),reason=evidence,actor_id=user.id))
    create_audit_log(db,user.username,"CI_RELATIONSHIP_CREATED","CIRelationship",str(row.id),f"Reviewed {rel_type.code} relationship")
    manager.broadcast_from_thread({"type":"cmdb_relationship_updated","relationship_id":str(row.id),"source_ci_id":str(source.id),"target_ci_id":str(target.id)})
    return row


def graph_for(db, root_id=None, property_id=None, max_depth=8, max_nodes=2000):
    query = db.query(ConfigurationItem).filter(ConfigurationItem.status != "archived")
    if property_id: query = query.filter(ConfigurationItem.property_id == property_id)
    allowed_ids = {row.id for row in query.limit(max_nodes).all()}
    if root_id and root_id not in allowed_ids: allowed_ids.add(root_id)
    rel_types = {row.id:row.code for row in db.query(CIRelationshipType).all()}
    relationships = db.query(CIRelationship).filter(CIRelationship.status == "active",CIRelationship.source_ci_id.in_(allowed_ids),CIRelationship.target_ci_id.in_(allowed_ids)).limit(max_nodes*4).all()
    adjacency = {}; reverse = {}
    for rel in relationships:
        adjacency.setdefault(rel.source_ci_id,[]).append((rel.target_ci_id,rel)); reverse.setdefault(rel.target_ci_id,[]).append((rel.source_ci_id,rel))
    selected = set(allowed_ids)
    if root_id:
        selected={root_id}; queue=deque([(root_id,0)])
        while queue and len(selected)<max_nodes:
            node,depth=queue.popleft()
            if depth>=max_depth: continue
            for neighbor,_ in adjacency.get(node,[])+reverse.get(node,[]):
                if neighbor not in selected: selected.add(neighbor); queue.append((neighbor,depth+1))
    nodes=db.query(ConfigurationItem).filter(ConfigurationItem.id.in_(selected)).all(); edges=[r for r in relationships if r.source_ci_id in selected and r.target_ci_id in selected]
    cycles=[]; visiting=set(); visited=set()
    def visit(node,path):
        if node in visiting: cycles.append([str(v) for v in path[path.index(node):]+[node]]); return
        if node in visited:return
        visiting.add(node)
        for neighbor,rel in adjacency.get(node,[]):
            if rel_types.get(rel.relationship_type_id) in DEPENDENCY_CODES: visit(neighbor,path+[neighbor])
        visiting.remove(node);visited.add(node)
    for node in selected:
        if len(cycles)>=50:break
        visit(node,[node])
    return {"nodes":nodes,"relationships":edges,"relationship_types":rel_types,"cycles":cycles,"truncated":len(allowed_ids)>=max_nodes}


def save_graph_snapshot(db, graph, property_id, root_id, user):
    data=json.dumps({"nodes":[str(n.id) for n in graph["nodes"]],"relationships":[str(r.id) for r in graph["relationships"]],"cycles":graph["cycles"]},sort_keys=True)
    version=db.query(DependencyGraph).filter_by(property_id=property_id,root_ci_id=root_id).count()+1
    row=DependencyGraph(property_id=property_id,root_ci_id=root_id,graph_version=version,node_count=len(graph["nodes"]),edge_count=len(graph["relationships"]),checksum_sha256=hashlib.sha256(data.encode()).hexdigest(),graph_data=data,created_by=user.id);db.add(row);return row


def impact_analysis(db, ci, max_depth=6):
    graph=graph_for(db,root_id=ci.id,property_id=ci.property_id,max_depth=max_depth,max_nodes=1000)
    rel_types=graph["relationship_types"]; downstream={}; queue=deque([(ci.id,0)]); seen={ci.id}
    for rel in graph["relationships"]: downstream.setdefault(rel.source_ci_id,[]).append(rel)
    impacted=[]
    while queue:
        node,depth=queue.popleft()
        if depth>=max_depth:continue
        for rel in downstream.get(node,[]):
            if rel_types.get(rel.relationship_type_id) not in DEPENDENCY_CODES or rel.target_ci_id in seen:continue
            seen.add(rel.target_ci_id); impacted.append({"ci_id":str(rel.target_ci_id),"depth":depth+1,"relationship":rel_types.get(rel.relationship_type_id)});queue.append((rel.target_ci_id,depth+1))
    from app.models.change_management import ChangeRelationship
    from app.models.incidents import OperationalIncidentSource
    from app.models.knowledge import KnowledgeRelationship
    counts={
        "changes":db.query(ChangeRelationship).filter_by(target_type="configuration_item",target_id=ci.id).count(),
        "incidents":db.query(OperationalIncidentSource).filter(OperationalIncidentSource.source_entity_type.in_(("configuration_item","ci")),OperationalIncidentSource.source_entity_id==ci.id).count(),
        "knowledge":db.query(KnowledgeRelationship).filter(or_(KnowledgeRelationship.source_id==ci.id,KnowledgeRelationship.target_id==ci.id)).filter(or_(KnowledgeRelationship.source_type.in_(("configuration_item","ci")),KnowledgeRelationship.target_type.in_(("configuration_item","ci")))).count(),
    }
    risk="critical" if ci.criticality=="critical" and impacted else "high" if len(impacted)>=5 else "medium" if impacted else "low"
    return {"root_ci":ci,"potentially_impacted":impacted,"direct_count":sum(i["depth"]==1 for i in impacted),"indirect_count":sum(i["depth"]>1 for i in impacted),"linked_records":counts,"cycles":graph["cycles"],"risk":risk,"warning":"Impact is deterministic relationship analysis, not a guaranteed outage prediction."}


def reconciliation_candidates(db, property_id=None, limit=500, source_types=None):
    source_types=set(source_types or ("device","network_discovery"))
    created=updated=0
    device_query=db.query(Device)
    if property_id:device_query=device_query.filter(Device.property_id==property_id)
    for device in (device_query.limit(limit) if "device" in source_types else []):
        existing=db.query(ConfigurationItem).filter(or_(ConfigurationItem.asset_id==device.id,ConfigurationItem.serial_number==device.serial_number)).first()
        score=100 if existing and existing.asset_id==device.id else 95 if existing else 0; level="exact" if score>=95 else "none"; action="link" if existing else "create"
        row=db.query(CIReconciliationCandidate).filter_by(source_type="device",source_id=device.id).first()
        values={"name":device.hostname,"serial_number":device.serial_number,"manufacturer":device.brand,"model":device.model,"property_id":str(device.property_id) if device.property_id else None,"asset_id":str(device.id)}
        if not row: row=CIReconciliationCandidate(source_type="device",source_id=device.id,property_id=device.property_id,candidate_name=device.hostname);db.add(row);created+=1
        else:updated+=1
        row.proposed_ci_id=existing.id if existing else None;row.identifiers=json.dumps({"serial":device.serial_number,"mac":device.mac_address,"ip":device.ip_address});row.proposed_values=json.dumps(values);row.score=score;row.match_level=level;row.evidence=json.dumps(["explicit_asset_link"] if score==100 else ["exact_serial"] if score==95 else []);row.conflicts="[]";row.recommended_action=action;row.updated_at=datetime.now(timezone.utc)
    discovery_query=db.query(DiscoveredDevice)
    # Legacy discovery records do not carry a property ID. They remain in the
    # corporate review queue until an administrator assigns property context.
    for discovered in (discovery_query.limit(limit) if "network_discovery" in source_types and property_id is None else []):
        existing=db.query(ConfigurationItem).filter(or_(ConfigurationItem.discovered_device_id==discovered.id,ConfigurationItem.asset_id==discovered.approved_device_id if discovered.approved_device_id else False)).first()
        score=100 if existing and existing.discovered_device_id==discovered.id else 90 if existing else 0;level="exact" if score==100 else "strong" if score else "none"
        row=db.query(CIReconciliationCandidate).filter_by(source_type="network_discovery",source_id=discovered.id).first()
        values={"name":discovered.hostname or discovered.ip_address,"manufacturer":discovered.vendor,"discovered_device_id":str(discovered.id),"discovery_source":"network_discovery"}
        if not row:row=CIReconciliationCandidate(source_type="network_discovery",source_id=discovered.id,property_id=None,candidate_name=values["name"]);db.add(row);created+=1
        else:updated+=1
        row.proposed_ci_id=existing.id if existing else None;row.identifiers=json.dumps({"mac":discovered.mac_address,"ip":discovered.ip_address,"hostname":discovered.hostname});row.proposed_values=json.dumps(values);row.score=score;row.match_level=level;row.evidence=json.dumps(["explicit_discovery_link"] if score==100 else ["approved_device_link"] if score else []);row.conflicts="[]";row.recommended_action="link" if existing else "create";row.updated_at=datetime.now(timezone.utc)
    db.flush();return {"created":created,"updated":updated}


def calculate_health(db, property_id=None):
    q=db.query(ConfigurationItem).filter(ConfigurationItem.status!="archived")
    if property_id:q=q.filter(ConfigurationItem.property_id==property_id)
    total=q.count(); verified=q.filter(ConfigurationItem.verification_status=="verified").count(); stale=q.filter(or_(ConfigurationItem.last_verified_at.is_(None),ConfigurationItem.last_verified_at<datetime.now(timezone.utc)-timedelta(days=30))).count(); missing=q.filter(ConfigurationItem.owner_id.is_(None)).count()
    ids=[row[0] for row in q.with_entities(ConfigurationItem.id).limit(10000).all()];linked=set()
    if ids:
        for source,target in db.query(CIRelationship.source_ci_id,CIRelationship.target_ci_id).filter(CIRelationship.status=="active",or_(CIRelationship.source_ci_id.in_(ids),CIRelationship.target_ci_id.in_(ids))):linked.update(value for value in (source,target) if value in ids)
    orphan=max(0,total-len(linked));duplicates=db.query(CIReconciliationCandidate).filter(CIReconciliationCandidate.status=="pending",CIReconciliationCandidate.match_level.in_(("exact","strong")))
    if property_id:duplicates=duplicates.filter(CIReconciliationCandidate.property_id==property_id)
    duplicate_count=duplicates.count(); completeness=round((total-orphan)*100/max(1,total),2);coverage=round(q.filter(ConfigurationItem.discovery_source!="manual").count()*100/max(1,total),2)
    score=round(max(0,100-(stale/max(1,total)*25)-(orphan/max(1,total)*20)-(missing/max(1,total)*15)-min(20,duplicate_count*2)))
    row=CIHealthSnapshot(property_id=property_id,health_score=score,total_cis=total,verified_cis=verified,stale_cis=stale,orphan_cis=orphan,duplicate_candidates=duplicate_count,missing_owners=missing,relationship_completeness=completeness,discovery_coverage=coverage,details=json.dumps({"freshness_days":30}));db.add(row);return row
